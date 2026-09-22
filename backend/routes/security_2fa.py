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
- /api/auth/2fa/enroll-init    → alta del segundo factor, DURANTE el login
- /api/auth/2fa/enroll-confirm → confirma el primer código, lo enciende y emite sesión
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
import os
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

from services.ip_cliente import ip_del_cliente

from database import db
from services import personal as _personal
from services.email_notifications import notify_dos_pasos_activado
from models.user import User
from routes.dependencies import get_current_user, set_session_cookie
from services.perfil import para_su_dueno
from utils.security import hash_password_async, verify_password_async

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
    """La IP en la que se puede confiar para contar intentos.

    ANTES ESTO SE PODIA FALSEAR, Y CON ELLO TODOS LOS LIMITES

        La versión anterior tomaba el PRIMER valor de `X-Forwarded-For`, que es
        una cabecera que manda el cliente. Un proxy no la reemplaza: le agrega
        la IP real AL FINAL. Así que un pedido enviado con

            X-Forwarded-For: 1.2.3.4

        llegaba como «1.2.3.4, <ip real>» y el primer valor era el que había
        elegido quien atacaba. Cambiándolo en cada intento, cada uno caía en un
        contador distinto: el ingreso, el reseteo de contraseña, la invitación
        del personal y el segundo factor quedaban sin límite efectivo.

        La lógica correcta —leer de derecha a izquierda, y preferir la cabecera
        que escribe Cloudflare— vive en `services/ip_cliente.py`, con sus
        pruebas. Esta función queda como el nombre por el que la conoce el
        resto del archivo.
    """
    ip = ip_del_cliente(request)
    return ip or get_remote_address(request)

# Se conserva por su `key_func` y porque `server.py` se lo pasa a la aplicación
# para el manejador de errores de slowapi. La CUENTA ya no sale de acá: ver el
# bloque de abajo.
limiter = Limiter(key_func=get_real_client_ip, default_limits=[])


# ══════════════════════════════════════════════════════════════════════════
# DONDE SE LLEVA LA CUENTA DE INTENTOS
# ══════════════════════════════════════════════════════════════════════════
#
# Son dieciocho límites y casi todos protegen lo mismo: contraseñas, códigos de
# verificación y recuperación de cuenta. O sea que esta cuenta ES la defensa
# contra quien prueba de a miles.
#
# EN MEMORIA —lo que había— TIENE DOS COSTOS
#
#     · CADA DESPLIEGUE LA PONE EN CERO. Quien está frenado por haber probado
#       veinte contraseñas arranca limpio con el despliegue siguiente, y en
#       este repositorio se despliega seguido.
#     · CON VARIOS PROCESOS SE MULTIPLICA. Cada proceso lleva su propia cuenta,
#       así que «20 intentos cada 15 minutos» pasa a ser 20 POR PROCESO. Es lo
#       que impedía prender `--workers`.
#
# EN LA BASE, CUANDO SE PRENDE
#
#     `LIMITES_EN_LA_BASE=si` lleva la cuenta a Mongo, que ya está ahí: sin
#     servicio nuevo y sin costo. Los contadores se borran solos (la librería
#     les pone caducidad), así que no hay nada que limpiar.
#
#     ARRANCA APAGADO, igual que la política de contenido y el cofre. Un
#     mecanismo nuevo en el camino del login que se despliega solo un viernes
#     es peor que el problema que viene a resolver. Se prende con una variable
#     de entorno en Railway, sin tocar una línea de código.
#
# SI LA BASE NO CONTESTA, EL PEDIDO NO PASA
#
#     Comprobado contra el almacén de verdad apuntado a una dirección muerta:
#     levanta. O sea que un problema de base devuelve error en vez de dejar
#     entrar a cualquiera sin contarlo. Es la dirección correcta — lo contrario
#     sería que la defensa contra la fuerza bruta desapareciera justo cuando la
#     base está en problemas.
#
#     Y no cuesta nada en la práctica: con Mongo caído no funciona ninguna
#     pantalla, porque todas leen de ahí.
#
# POR QUE NO SE USA EL ALMACEN DE SLOWAPI
#
#     Porque no se puede. slowapi 0.1.9 sólo acepta almacenes SINCRONOS
#     —construirlo con uno asíncrono levanta `AssertionError`— y el de Mongo
#     síncrono se queda esperando la respuesta ADENTRO DEL HILO, que es
#     exactamente lo que se sacó de toda la aplicación. Así que la cuenta se le
#     pide directo a `limits`, que es la librería que slowapi usa por dentro.
#
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
# Ahora NO QUEDA NINGUN decorador: el último, el de `/verify`, también pasó a
# `frenar()`. Con la cuenta afuera de slowapi, el decorador ya no tenía de
# dónde sacarla.

_REGLAS: dict = {}
_CONTADOR = None


def _en_la_base() -> bool:
    """¿La cuenta va a Mongo? Se decide por variable de entorno, no por código.
    La regla vive en `services/limites_en_la_base.py`, que también la lee la
    salud de la aplicación."""
    from services import limites_en_la_base
    return limites_en_la_base.activo()


def _armar_el_contador():
    """El contador, con el almacén que corresponda.

    Los dos son ASINCRONOS, también el de memoria. Tener un solo camino evita
    que el de producción sea uno que los tests nunca recorren.
    """
    from limits.aio.strategies import FixedWindowRateLimiter
    from limits.storage import storage_from_string

    if _en_la_base():
        from config import MONGO_URL
        # `async+` delante sirve para `mongodb://` y para `mongodb+srv://`:
        # los dos esquemas existen con ese prefijo.
        almacen = storage_from_string("async+" + MONGO_URL)
        logger.info("Los límites de intentos se cuentan en la base")
    else:
        almacen = storage_from_string("async+memory://")
    return FixedWindowRateLimiter(almacen)


def el_contador():
    """El contador, armado una sola vez."""
    global _CONTADOR
    if _CONTADOR is None:
        _CONTADOR = _armar_el_contador()
    return _CONTADOR


def reiniciar_la_cuenta() -> None:
    """Olvida todo lo contado. Para los tests, que arrancan de cero cada uno."""
    global _CONTADOR
    _CONTADOR = None


async def frenar(request: Request, alcance: str, regla: str) -> None:
    """Descuenta una unidad del cupo de esta IP. Levanta 429 si se pasó.

    `alcance` separa los contadores entre endpoints: sin él, gastar el cupo
    de "olvidé mi contraseña" dejaría a esa IP sin poder iniciar sesión.

    ES `async`, Y HAY QUE ESPERARLA. Llamarla sin `await` no falla: devuelve
    una corrutina, Python tira un aviso que nadie lee, y ESE ENDPOINT SE QUEDA
    SIN LIMITE. Un login sin límite es fuerza bruta libre. Hay una guarda que
    recorre el código exigiendo el `await` (`tests/test_limite_por_ip.py`).
    """
    from limits import parse

    parsed = _REGLAS.get(regla)
    if parsed is None:
        parsed = _REGLAS[regla] = parse(regla)

    clave = get_real_client_ip(request)
    if not await el_contador().hit(parsed, clave, alcance):
        logger.warning("Límite %s alcanzado por %s en %s", regla, clave, alcance)
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Esperá unos minutos y volvé a probar.")
async def frenar_por_cuenta(user_id: str, alcance: str, regla: str) -> None:
    """Como `frenar`, pero el cupo es de la CUENTA y no de la IP.

    POR QUE HACE FALTA UN SEGUNDO CONTADOR

        Todos los límites de esta aplicación eran por IP, y eso protege la
        puerta de entrada: quien no tiene sesión sólo tiene su IP. Pero quien
        YA tiene sesión tiene además una cuenta, y una cuenta que cambia de
        red —datos del celular, wifi, un VPN— cambia de IP y arranca de cero.
        Para las rutas que mueven plata, eso era no tener límite.

        El contador es el mismo de siempre (`el_contador()`), así que vive en
        la base y lo comparten los workers. Sólo cambia la clave: `cuenta:` y
        el id, en vez de la IP. El prefijo evita que un user_id que casualmente
        se parezca a una IP pise el contador de una IP.

    ES `async`, Y HAY QUE ESPERARLA, por el mismo motivo que `frenar`: la
    guarda de `tests/test_limite_por_ip.py` también la recorre a ella.
    """
    from limits import parse

    parsed = _REGLAS.get(regla)
    if parsed is None:
        parsed = _REGLAS[regla] = parse(regla)

    clave = f"cuenta:{user_id}"
    if not await el_contador().hit(parsed, clave, alcance):
        logger.warning("Límite %s alcanzado por la cuenta %s en %s", regla, user_id, alcance)
        raise HTTPException(
            status_code=429,
            detail="Hiciste demasiadas operaciones seguidas. Esperá un rato y volvé a probar.")


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


class TwoFADisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


# ============================================================
# Helpers
# ============================================================
async def _generate_backup_codes() -> tuple[List[str], List[str]]:
    """Return (plain_codes, hashed_codes). Plain returned once to user.

    LOS DIEZ SE CIFRAN A LA VEZ, Y ES POR DOS MOTIVOS DISTINTOS

        Uno por uno eran diez veces 266 milisegundos: **2,7 segundos** con la
        aplicación entera congelada, porque corre en un solo hilo. En otro hilo
        ya no congela a nadie, pero seguirían siendo 2,7 segundos de espera para
        quien está prendiendo su segundo factor. Cifrándolos a la vez, son los
        mismos 266 milisegundos que uno solo.
    """
    import asyncio

    alphabet = string.ascii_uppercase + string.digits
    plain: List[str] = []
    seen = set()
    while len(plain) < BACKUP_CODES_COUNT:
        code = "".join(py_secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        if code not in seen:
            seen.add(code)
            plain.append(code)
    hashes = list(await asyncio.gather(*[hash_password_async(c) for c in plain]))
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
        # LA MISMA REGLA QUE APLICA EL INGRESO, Y DE LA MISMA FUENTE. Acá
        # decía `role == super_admin` por su cuenta, y a un `admin` o a un
        # `agent` le contestaba que no era obligatorio justo antes de que el
        # login se lo exigiera. Dos respuestas para la misma pregunta.
        "is_required": _personal.exige_dos_pasos(user),
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

    plain_codes, hashed_codes = await _generate_backup_codes()
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

    # Lo que es suyo para ver, y nada más. La lista y el motivo están en
    # `services/perfil.py`. Acá había una lista de lo PROHIBIDO de cinco
    # nombres —una de las cinco que había, todas distintas entre sí— y dejaba
    # salir el hash del PIN y las credenciales de la huella, que la lista de
    # `/webauthn/login/verify` sí tapaba.
    user_response = para_su_dueno(user)

    return {
        "message": "2FA activado correctamente",
        "session_token": token,
        "user": _sanitize_for_json(user_response),
        "backup_codes": plain_codes,
        "important": "Guarda estos códigos en un lugar seguro. NO se mostrarán de nuevo.",
    }


# ══════════════════════════════════════════════════════════════════════════
# ACA VIVIAN `/setup-init` Y `/setup-confirm`, Y SE FUERON
# ══════════════════════════════════════════════════════════════════════════
#
# Eran el alta del segundo factor CON SESION YA ABIERTA: el camino del
# perfil. Sólo exigían estar logueado, así que cualquier cliente podía
# llamarlas, encender `two_factor_enabled` y recibir sus códigos de
# respaldo.
#
# EL PROBLEMA NO ERA QUE FALTARA UNA PANTALLA. Era que las puertas de
# entrada NO MIRAN esa marca cuando la cuenta es un cliente: la exigen sólo
# al personal y a los administradores (`services/personal.exige_dos_pasos`,
# usada por `routes/auth.py`, `routes/google_ingreso.py` y
# `routes/webauthn_login.py`). O sea que quien las usara quedaba con el
# segundo factor «activado», la ruta de estado se lo confirmaba, el ingreso
# lo ignoraba, y encima no podía apagarlo sin un código del teléfono.
# Protección que no protege y de la que no se puede salir.
#
# Se comprobó antes de sacarlas: NINGUN código del repositorio las llamaba.
# Ni una pantalla, ni un test. Estaban vivas, alcanzables por HTTP y sin
# dueño.
#
# El factor extra del cliente es la HUELLA (`routes/webauthn_login.py`), que
# sí tiene pantalla en el perfil y sí se respeta al entrar.
#
# SI ALGUN DIA SE QUIERE OFRECER EL SEGUNDO FACTOR AL CLIENTE, el camino no
# es volver a poner esto: es que las tres puertas respeten la marca, que la
# regla siga viviendo en un solo lugar, y que un super administrador pueda
# apagárselo a quien perdió el teléfono.
#
# ESE DIA LLEGO, Y LAS TRES CONDICIONES ESTAN:
#
#   · Las puertas la respetan. `personal.pide_dos_pasos` decide, y la miran
#     el ingreso con contraseña y el de Google. Las otras dos que emiten
#     sesión están exentas con motivo escrito, y hay un test que exige que
#     toda puerta nueva declare el suyo.
#   · La regla vive en un solo lugar. Antes estaba copiada palabra por
#     palabra en dos rutas de ingreso.
#   · El reinicio existe. Recursos Humanos puede limpiárselo a quien perdió
#     el teléfono Y los códigos de respaldo.
#
# Así que abajo vuelve el alta con sesión, que es el camino del perfil. La
# diferencia con las rutas que se fueron no está en estas funciones: está en
# que ahora el ingreso mira lo que encienden.


class ActivarDosPasosConfirm(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/activar-init")
async def activar_dos_pasos_init(current_user: User = Depends(get_current_user)):
    """Le muestra el código QR a quien quiere activarlo desde su perfil.

    No enciende nada: sólo deja un secreto PENDIENTE. Mientras no llegue el
    primer código correcto, la cuenta sigue exactamente como estaba. Así,
    alguien que abre la pantalla y se arrepiente no queda a medio camino.
    """
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="Ya tenés la verificación en dos pasos activada")

    secret = pyotp.random_base32()
    otpauth_url = pyotp.TOTP(secret).provisioning_uri(
        name=user["email"], issuer_name=ISSUER_NAME)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"two_factor_secret_pending": secret}})
    return {
        "secret": secret,
        "otpauth_url": otpauth_url,
        "qr_code_data_url": _make_qr_data_url(otpauth_url),
        "issuer": ISSUER_NAME,
        "account": user["email"],
    }


@router.post("/activar-confirm")
async def activar_dos_pasos_confirm(request: Request, datos: ActivarDosPasosConfirm,
                                    current_user: User = Depends(get_current_user)):
    """Confirma con el primer código y lo enciende. Devuelve los de respaldo.

    NO EMITE SESION, a diferencia de `enroll-confirm`: quien llega acá ya
    tiene una. Devolver otra sería darle dos sesiones vivas por activar una
    protección.
    """
    # El mismo freno que `/verify`, y por lo mismo: acá se prueba un código
    # de seis dígitos. Sin freno, mil intentos lo adivinan.
    await frenar(request, "auth.2fa_activar", "10/15minutes")

    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if user.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="Ya tenés la verificación en dos pasos activada")

    secret = user.get("two_factor_secret_pending")
    if not secret:
        raise HTTPException(status_code=400, detail="Primero pedí el código QR")

    if not pyotp.TOTP(secret).verify(datos.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código incorrecto")

    plain_codes, hashed_codes = await _generate_backup_codes()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"two_factor_enabled": True,
                  "two_factor_secret": secret,
                  "two_factor_backup_hashes": hashed_codes,
                  "two_factor_enabled_at": datetime.now(timezone.utc)},
         "$unset": {"two_factor_secret_pending": ""}})

    # El aviso es la mitad de la defensa, igual que en el reinicio desde
    # Recursos Humanos: si alguien con la sesión tomada activa el segundo
    # factor, el dueño de la cuenta se entera AHORA y no cuando no pueda
    # entrar. Va en su propio `try`: que el correo falle no puede dejar la
    # activación a medias, con los códigos de respaldo ya mostrados una vez
    # y sin forma de volver a verlos.
    try:
        await notify_dos_pasos_activado(user.get("email"), user.get("name") or "")
    except Exception as e:                                # pragma: no cover
        logger.warning("no se pudo avisar la activación de dos pasos: %s", e)

    return {
        "message": "Verificación en dos pasos activada",
        "backup_codes": plain_codes,
        "important": "Guardá estos códigos en un lugar seguro. NO se muestran de nuevo.",
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
async def twofa_verify(request: Request, response: Response, data: TwoFAVerifyRequest):
    """Exchange pending_token + TOTP/backup code for a real session_token."""
    await frenar(request, "auth.2fa_verify", "10/15minutes")

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
            if not valid and await verify_password_async(code, h):
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

    # Lo que es suyo para ver, y nada más. La lista y el motivo están en
    # `services/perfil.py`. Acá había una lista de lo PROHIBIDO de cinco
    # nombres —una de las cinco que había, todas distintas entre sí— y dejaba
    # salir el hash del PIN y las credenciales de la huella, que la lista de
    # `/webauthn/login/verify` sí tapaba.
    user_response = para_su_dueno(user)

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

    plain_codes, hashed_codes = await _generate_backup_codes()
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"two_factor_backup_hashes": hashed_codes}},
    )
    return {
        "message": "Codigos de respaldo regenerados",
        "backup_codes": plain_codes,
        "important": "Guarda estos codigos en un lugar seguro. NO se mostraran de nuevo.",
    }
