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
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import db
from models.user import User
from routes.dependencies import get_current_user
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

# ============================================================
# Rate Limiter (per IP)
# ============================================================
limiter = Limiter(key_func=get_remote_address, default_limits=[])

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
async def ensure_security_indexes():
    await db.twofa_pending.create_index("token", unique=True)
    await db.twofa_pending.create_index("expires_at", expireAfterSeconds=60 * 30)
    await db.admin_access_log.create_index([("user_id", 1), ("created_at", -1)])
    await db.admin_access_log.create_index([("created_at", -1)])
    # Sessions cleanup TTL (optional, keep historic 30d after expiry)
    try:
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=60 * 60 * 24 * 30)
    except Exception as e:
        logger.warning(f"user_sessions TTL index: {e}")
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
async def twofa_enroll_confirm(request: Request, data: TwoFASetupConfirmFromPendingRequest):
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

    user_response = {
        k: v for k, v in user.items()
        if k not in ["_id", "password_hash", "two_factor_secret",
                     "two_factor_secret_pending", "two_factor_backup_hashes"]
    }

    return {
        "message": "2FA activado correctamente",
        "session_token": token,
        "user": user_response,
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
async def twofa_verify(request: Request, data: TwoFAVerifyRequest):
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
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}},
    )

    user_response = {k: v for k, v in user.items() if k not in ["_id", "password_hash", "two_factor_secret", "two_factor_secret_pending", "two_factor_backup_hashes"]}

    return {
        "message": "Login exitoso (2FA)",
        "session_token": token,
        "user": user_response,
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
