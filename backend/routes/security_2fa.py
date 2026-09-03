"""
Security layer v2 — 2FA (TOTP) + Rate Limiting + Admin Audit Log
================================================================

Phase 1 quick wins:
- Obligatory 2FA TOTP for super_admin role
- Backup codes (10 single-use codes, bcrypt-hashed)
- Rate limiting on /api/auth/login-password and /api/auth/2fa/verify
  (5 attempts per IP per 15 min)
- Reduced session timeout for admin/super_admin (30 min)
- Admin access audit log (login events with IP/country)
- Security HTTP headers middleware

Strategy: ADDITIVE. We do NOT replace the existing login endpoint.
- /api/auth/2fa/setup-init    → start enrollment (generates secret + QR)
- /api/auth/2fa/setup-confirm → verify first TOTP code + enable + return backup codes
- /api/auth/2fa/verify        → after password login, verify TOTP and issue full session
- /api/auth/2fa/status        → check if 2FA is enabled for current user
- /api/auth/2fa/disable       → super-admin can disable for themselves with TOTP confirmation

Login flow for super_admin:
1. POST /api/auth/login-password → if super_admin + 2FA enabled, returns
   pending_token (5 min lifetime, type=2fa_pending) instead of session_token
2. POST /api/auth/2fa/verify with pending_token + TOTP code → issues real session_token
3. If super_admin without 2FA → returns pending_token + enrollment_required
   so frontend redirects to setup
"""
import logging
import secrets as py_secrets
import string
import uuid
import io
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import pyotp
import qrcode
from bson.decimal128 import Decimal128
from fastapi import APIRouter, Request, Depends, HTTPException, Response
from pymongo.errors import OperationFailure
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import db
from models.user import User
from routes.dependencies import get_current_user, set_session_cookie
from utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================
ADMIN_SESSION_MINUTES = 30           # admin/super_admin
USER_SESSION_DAYS = 7                # normal users (unchanged)
TWOFA_PENDING_MINUTES = 5            # short-lived intermediate token
BACKUP_CODES_COUNT = 10
BACKUP_CODE_LENGTH = 10
ISSUER_NAME = "RIS App"
ADMIN_ROLES = {"admin", "super_admin"}
SUPER_ADMIN_ROLE = "super_admin"

# Cuánto se conserva una sesión DESPUÉS de vencida, antes de que Mongo la
# borre sola. No es el control de acceso —eso lo hace routes/dependencies.py
# comparando expires_at en cada request— sino la limpieza: sin esto la
# colección crece para siempre.
TTL_SESIONES_VENCIDAS = 60 * 60 * 24 * 30          # 30 días
CONFLICTO_DE_OPCIONES_DE_INDICE = 85               # IndexOptionsConflict

# ============================================================
# Rate Limiter (per IP)
# ============================================================
def get_real_client_ip(request: Request) -> str:
    """Usa X-Forwarded-For (IP real del cliente detras del proxy de Railway); si no existe, cae de vuelta a get_remote_address."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=get_real_client_ip, default_limits=[])


# ─── Cómo se pide el límite, y por qué no con el decorador ────────────────
#
# `@limiter.limit(...)` sobre una función definida ADENTRO de un handler se
# aplica de nuevo en cada pedido, y cada aplicación agrega una entrada más a
# `limiter._route_limits[nombre]`. La lista no se limpia nunca.
#
# El efecto no es cosmético: `_check_request_limit` recorre esa lista entera
# y descuenta UNA unidad por cada entrada. Con veinte entradas acumuladas,
# un solo pedido consume veinte del cupo, así que el login empezaba a
# devolver 429 a CUALQUIERA —incluso desde una IP que nunca había entrado—
# después de veinte ingresos, y sólo se recuperaba reiniciando el proceso.
# Medido: el ingreso número 21 desde una IP nueva se rechazaba. Y la lista
# crecía sin techo mientras el servidor vivía.
#
# `frenar()` hace lo mismo que el decorador —una consulta al mismo
# contador, con la misma clave por IP— pero sin registrar nada. Se llama, no
# se decora, así que no hay nada que se acumule.
#
# Para un handler de ruta común el decorador está bien: FastAPI lo aplica una
# sola vez, al importar. Así se usa abajo en /verify.

_REGLAS: dict = {}


def frenar(request: Request, alcance: str, regla: str) -> None:
    """Descuenta una unidad del cupo de esta IP. Levanta 429 si se pasó.

    `alcance` separa los contadores entre endpoints: sin él, gastar el cupo
    de "olvidé mi contraseña" dejaría a esa IP sin poder iniciar sesión.
    """
    from limits import parse

    parsed = _REGLAS.get(regla)
    if parsed is None:
        parsed = _REGLAS[regla] = parse(regla)

    clave = get_real_client_ip(request)
    if not limiter.limiter.hit(parsed, clave, alcance):
        logger.warning("Límite %s alcanzado por %s en %s", regla, clave, alcance)
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Esperá unos minutos y volvé a probar.")
# ============================================================
# Router
# ============================================================
router = APIRouter(prefix="/auth/2fa", tags=["2FA Security"])


# ============================================================
# Pydantic schemas
# ============================================================
class TwoFAVerifyRequest(BaseModel):
    pending_token: str
    code: str = Field(..., min_length=6, max_length=12)


class TwoFASetupConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TwoFADisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


# ============================================================
# Helpers
# ============================================================
def _generate_backup_codes() -> tuple[List[str], List[str]]:
    """Return (plain_codes, hashed_codes). Plain returned once to user."""
    alphabet = string.ascii_uppercase + string.digits
    plain: List[str] = []
    seen = set()
    while len(plain) < BACKUP_CODES_COUNT:
        code = "".join(py_secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        if code not in seen:
            seen.add(code)
            plain.append(code)
    hashes = [hash_password(c) for c in plain]
    return plain, hashes


def _sanitize_for_json(value):
        """Recursively convert BSON/datetime types into JSON-serializable values (e.g. Decimal128)."""
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: _sanitize_for_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_sanitize_for_json(v) for v in value]
        return value

def _make_qr_data_url(otpauth_url: str) -> str:
    """Generate a base64 PNG data URL from the otpauth URI."""
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _session_duration_for(role: Optional[str]) -> timedelta:
    if role in ADMIN_ROLES:
        return timedelta(minutes=ADMIN_SESSION_MINUTES)
    return timedelta(days=USER_SESSION_DAYS)


async def issue_session_token(
    user: dict, request: Optional[Request] = None, two_factor_used: bool = False
) -> str:
    """Create a session token with role-aware expiration + audit log if admin."""
    token = py_secrets.token_urlsafe(32)
    role = user.get("role", "user")
    duration = _session_duration_for(role)
    session = {
        "session_id": f"sess_{uuid.uuid4().hex[:12]}",
        "session_token": token,
        "user_id": user["user_id"],
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + duration,
        "is_active": True,
        "two_factor_used": two_factor_used,
    }
    await db.user_sessions.insert_one(session)

    # Audit log for admin logins
    if role in ADMIN_ROLES:
        ip = "unknown"
        country = None
        user_agent = None
        if request is not None:
            ip = request.client.host if request.client else "unknown"
            country = request.headers.get("cf-ipcountry")
            user_agent = request.headers.get("user-agent", "")[:200]
        await db.admin_access_log.insert_one({
            "_id": uuid.uuid4().hex,
            "user_id": user["user_id"],
            "email": user.get("email"),
            "role": role,
            "ip": ip,
            "country": country,
            "user_agent": user_agent,
            "two_factor_used": two_factor_used,
            "session_minutes": ADMIN_SESSION_MINUTES,
            "created_at": datetime.now(timezone.utc),
        })

    return token


async def _create_pending_token(user_id: str, purpose: str = "2fa_login") -> str:
    """Short-lived token for the 2FA challenge step (5 min)."""
    token = py_secrets.token_urlsafe(24)
    await db.twofa_pending.insert_one({
        "_id": uuid.uuid4().hex,
        "token": token,
        "user_id": user_id,
        "purpose": purpose,  # '2fa_login' or '2fa_enroll'
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=TWOFA_PENDING_MINUTES),
        "consumed": False,
    })
    return token


async def _consume_pending_token(token: str) -> Optional[dict]:
    doc = await db.twofa_pending.find_one_and_update(
        {"token": token, "consumed": False, "expires_at": {"$gt": datetime.now(timezone.utc)}},
        {"$set": {"consumed": True}},
    )
    return doc


# ============================================================
# Index bootstrap
# ============================================================
async def _asegurar_ttl_de_sesiones():
    """Deja `user_sessions.expires_at` con TTL, aunque ya exista sin él."""
    opciones = {"expireAfterSeconds": TTL_SESIONES_VENCIDAS, "name": "expires_at_1"}
    try:
        await db.user_sessions.create_index("expires_at", **opciones)
        logger.info("user_sessions: TTL de sesiones vencidas verificado")
        return
    except OperationFailure as e:
        if e.code != CONFLICTO_DE_OPCIONES_DE_INDICE:
            logger.warning(f"user_sessions TTL index: {e}")
            return
    # El índice está pero con otras opciones (sin TTL). Se rehace.
    try:
        await db.user_sessions.drop_index("expires_at_1")
        await db.user_sessions.create_index("expires_at", **opciones)
        logger.info("user_sessions: el índice de expires_at existía sin TTL; "
                    "se rehízo con TTL. Las sesiones vencidas vuelven a "
                    "borrarse solas.")
    except Exception as e:
        logger.warning(f"user_sessions TTL index: no se pudo rehacer: {e}")


async def ensure_security_indexes():
    await db.twofa_pending.create_index("token", unique=True)
    await db.twofa_pending.create_index("expires_at", expireAfterSeconds=60 * 30)
    await db.admin_access_log.create_index([("user_id", 1), ("created_at", -1)])
    await db.admin_access_log.create_index([("created_at", -1)])
    # Limpieza de sesiones: se borran 30 días después de haber vencido.
    #
    # En la base de producción este índice ya existe SIN TTL —lo creaba
    # server.py con el mismo nombre y sin expireAfterSeconds, y como corre
    # antes, ganaba— así que esta línea venía fallando en cada arranque con
    # IndexOptionsConflict y las sesiones vencidas no se borraban nunca.
    #
    # Mongo no cambia las opciones de un índice existente: hay que tirarlo y
    # rehacerlo. Es barato y no rompe nada mientras tanto: el vencimiento se
    # comprueba al leer la sesión (routes/dependencies.py), no depende del TTL.
    await _asegurar_ttl_de_sesiones()
    logger.info("2FA security indexes ensured")


# ============================================================
# Endpoints — Setup / Enrollment
# ============================================================
@router.get("/status")
async def twofa_status(current_user: User = Depends(get_current_user)):
    user = await db.users.find_one({"user_id": current_user.user_id})
    enabled = bool(user.get("two_factor_enabled", False))
    return {
        "enabled": enabled,
        "role": user.get("role", "user"),
        "is_required": user.get("role") == SUPER_ADMIN_ROLE,
        "backup_codes_remaining": len(user.get("two_factor_backup_hashes", [])),
    }


async def _user_from_pending_token(pending_token: str, expected_purpose: str) -> dict:
    """Look up user from a pending_token (without consuming it). Used by setup flow."""
    doc = await db.twofa_pending.find_one({
        "token": pending_token,
        "consumed": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if not doc:
        raise HTTPException(status_code=401, detail="Token de verificación expirado o inválido")
    if doc.get("purpose") != expected_purpose:
        raise HTTPException(status_code=403, detail="Token no autorizado para esta operación")
    user = await db.users.find_one({"user_id": doc["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


class TwoFASetupInitFromPendingRequest(BaseModel):
    pending_token: str


class TwoFASetupConfirmFromPendingRequest(BaseModel):
    pending_token: str
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/enroll-init")
async def twofa_enroll_init(data: TwoFASetupInitFromPendingRequest):
    """Initial enrollment using a pending_token from login (no session needed)."""
    user = await _user_from_pending_token(data.pending_token, expected_purpose="2fa_enroll")
    if user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA ya está activo")

    secret = pyotp.random_base32()
    otpauth_url = pyotp.TOTP(secret).provisioning_uri(
        name=user["email"], issuer_name=ISSUER_NAME
    )
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"two_factor_secret_pending": secret}},
    )
    return {
        "secret": secret,
        "otpauth_url": otpauth_url,
        "qr_code_data_url": _make_qr_data_url(otpauth_url),
        "issuer": ISSUER_NAME,
        "account": user["email"],
    }


@router.post("/enroll-confirm")
async def twofa_enroll_confirm(request: Request, response: Response, data: TwoFASetupConfirmFromPendingRequest):
    """Confirm enrollment with first TOTP code + consume pending_token + issue session."""
    pending = await _consume_pending_token(data.pending_token)
    if not pending or pending.get("purpose") != "2fa_enroll":
        raise HTTPException(status_code=401, detail="Token de enrolamiento inválido o expirado")

    user = await db.users.find_one({"user_id": pending["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    secret = user.get("two_factor_secret_pending")
    if not secret:
        raise HTTPException(status_code=400, detail="No hay secret pendiente. Inicia enrollment primero.")

    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código incorrecto")

    plain_codes, hashed_codes = _generate_backup_codes()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {
                "two_factor_enabled": True,
                "two_factor_secret": secret,
                "two_factor_backup_hashes": hashed_codes,
                "two_factor_enabled_at": datetime.now(timezone.utc),
                "last_login": datetime.now(timezone.utc),
            },
            "$unset": {"two_factor_secret_pending": ""},
        },
    )
    # Issue real session token now
    user = await db.users.find_one({"user_id": user["user_id"]})
    token = await issue_session_token(user, request=request, two_factor_used=True)
    set_session_cookie(response, token)

    user_response = {
        k: v for k, v in user.items()
        if k not in ["_id", "password_hash", "two_factor_secret",
                     "two_factor_secret_pending", "two_factor_backup_hashes"]
    }

    return {
        "message": "2FA activado correctamente",
        "session_token": token,
        "user": _sanitize_for_json(user_response),
        "backup_codes": plain_codes,
        "important": "Guarda estos códigos en un lugar seguro. NO se mostrarán de nuevo.",
    }


@router.post("/setup-init")
async def twofa_setup_init(current_user: User = Depends(get_current_user)):
    """Start 2FA enrollment: generate secret + QR. Does NOT enable yet."""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA ya está activo")

    secret = pyotp.random_base32()
    otpauth_url = pyotp.TOTP(secret).provisioning_uri(
        name=user["email"], issuer_name=ISSUER_NAME
    )
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"two_factor_secret_pending": secret}},
    )
    return {
        "secret": secret,  # show as fallback for manual entry
        "otpauth_url": otpauth_url,
        "qr_code_data_url": _make_qr_data_url(otpauth_url),
        "issuer": ISSUER_NAME,
        "account": user["email"],
    }


@router.post("/setup-confirm")
async def twofa_setup_confirm(
    data: TwoFASetupConfirmRequest,
    current_user: User = Depends(get_current_user),
):
    """Confirm enrollment with first TOTP code, generate backup codes."""
    user = await db.users.find_one({"user_id": current_user.user_id})
    secret = user.get("two_factor_secret_pending")
    if not secret:
        raise HTTPException(status_code=400, detail="Inicia el proceso de configuración primero")

    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código incorrecto")

    plain_codes, hashed_codes = _generate_backup_codes()

    await db.users.update_one(
        {"user_id": current_user.user_id},
        {
            "$set": {
                "two_factor_enabled": True,
                "two_factor_secret": secret,
                "two_factor_backup_hashes": hashed_codes,
                "two_factor_enabled_at": datetime.now(timezone.utc),
            },
            "$unset": {"two_factor_secret_pending": ""},
        },
    )
    return {
        "message": "2FA activado correctamente",
        "backup_codes": plain_codes,
        "important": "Guarda estos códigos en un lugar seguro. NO se mostrarán de nuevo.",
    }


@router.post("/disable")
async def twofa_disable(
    data: TwoFADisableRequest,
    current_user: User = Depends(get_current_user),
):
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA no está activo")

    secret = user.get("two_factor_secret")
    if not pyotp.TOTP(secret).verify(data.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código incorrecto")

    # super_admin role can't fully disable (it's required) — we just refresh
    if user.get("role") == SUPER_ADMIN_ROLE:
        raise HTTPException(
            status_code=403,
            detail="Super admins no pueden desactivar 2FA. Usa 'Regenerar' para cambiar de dispositivo.",
        )

    await db.users.update_one(
        {"user_id": current_user.user_id},
        {
            "$set": {"two_factor_enabled": False},
            "$unset": {
                "two_factor_secret": "",
                "two_factor_backup_hashes": "",
                "two_factor_enabled_at": "",
            },
        },
    )
    return {"message": "2FA desactivado"}


# ============================================================
# Endpoints — Login Verify (post-password)
# ============================================================
@router.post("/verify")
@limiter.limit("10/15minutes")
async def twofa_verify(request: Request, response: Response, data: TwoFAVerifyRequest):
    """Exchange pending_token + TOTP/backup code for a real session_token."""
    pending = await _consume_pending_token(data.pending_token)
    if not pending:
        raise HTTPException(status_code=401, detail="Token de verificación expirado o inválido")

    user = await db.users.find_one({"user_id": pending["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Cuenta suspendida")

    code = (data.code or "").strip().upper()
    valid = False
    used_backup = False

    # Try TOTP first (6 digits)
    if len(code) == 6 and code.isdigit() and user.get("two_factor_secret"):
        if pyotp.TOTP(user["two_factor_secret"]).verify(code, valid_window=1):
            valid = True

    # Try backup code (10 chars alphanumeric)
    if not valid and user.get("two_factor_backup_hashes"):
        remaining = []
        for h in user["two_factor_backup_hashes"]:
            if not valid and verify_password(code, h):
                valid = True
                used_backup = True
            else:
                remaining.append(h)
        if used_backup:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"two_factor_backup_hashes": remaining}},
            )

    if not valid:
        raise HTTPException(status_code=401, detail="Código inválido")

    # Issue real session
    token = await issue_session_token(user, request=request, two_factor_used=True)
    set_session_cookie(response, token)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}},
    )

    user_response = {k: v for k, v in user.items() if k not in ["_id", "password_hash", "two_factor_secret", "two_factor_secret_pending", "two_factor_backup_hashes"]}

    return {
        "message": "Login exitoso (2FA)",
        "session_token": token,
        "user": _sanitize_for_json(user_response),
        "used_backup_code": used_backup,
        "backup_codes_remaining": len(user.get("two_factor_backup_hashes", [])) - (1 if used_backup else 0),
    }


# ============================================================
# Admin access log endpoint (consult)
# ============================================================
@router.get("/admin-access-log")
async def admin_access_log(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    if current_user.role != SUPER_ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Solo super_admin")
    cursor = db.admin_access_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    entries = await cursor.to_list(limit)
    for e in entries:
        if isinstance(e.get("created_at"), datetime):
            e["created_at"] = e["created_at"].isoformat()
    return {"entries": entries, "count": len(entries)}


class TwoFARegenerateBackupRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/regenerate-backup-codes")
async def twofa_regenerate_backup_codes(
    data: TwoFARegenerateBackupRequest,
    current_user: User = Depends(get_current_user),
):
    """Regenerate the 10 backup codes without touching the TOTP secret/QR. Requires a valid current TOTP code."""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA no esta activo")

    secret = user.get("two_factor_secret")
    _code = (data.code or "").strip().replace(" ", "")
    if not secret or not pyotp.TOTP(secret).verify(_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Codigo incorrecto")

    plain_codes, hashed_codes = _generate_backup_codes()
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"two_factor_backup_hashes": hashed_codes}},
    )
    return {
        "message": "Codigos de respaldo regenerados",
        "backup_codes": plain_codes,
        "important": "Guarda estos codigos en un lugar seguro. NO se mostraran de nuevo.",
    }
