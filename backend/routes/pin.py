"""
PIN de seguridad de 4 dígitos.
NO es para iniciar sesión: es una capa de confirmación de operaciones para
usuarios verificados. Se guarda hasheado (bcrypt), con bloqueo escalonado por
intentos fallidos, invalidación tras el bloqueo severo y aviso al usuario.
"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from models.user import User
from routes.dependencies import get_current_user, get_verified_user
from utils.security import hash_password, verify_password
from services.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pin", tags=["pin"])

SEVERE_ATTEMPTS = 9  # invalida el PIN y obliga a restablecerlo desde el perfil


class PinSetRequest(BaseModel):
    password: str   # contraseña de la cuenta (re-autenticación)
    pin: str        # 4 dígitos


class PinVerifyRequest(BaseModel):
    pin: str


class PinDisableRequest(BaseModel):
    password: str


def _is_valid_pin(pin: str) -> bool:
    return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()


def _now():
    return datetime.now(timezone.utc)


async def _get_user_doc(user_id: str) -> dict:
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return doc


def _locked_remaining(doc: dict) -> int:
    """Segundos restantes de bloqueo, o 0 si no está bloqueado."""
    locked_until = doc.get("pin_locked_until")
    if not locked_until:
        return 0
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    delta = (locked_until - _now()).total_seconds()
    return int(delta) if delta > 0 else 0


@router.get("/status")
async def pin_status(current_user: User = Depends(get_current_user)):
    """Estado del PIN para el frontend (sin revelar el PIN)."""
    doc = await _get_user_doc(current_user.user_id)
    remaining = _locked_remaining(doc)
    return {
        "has_pin": bool(doc.get("pin_hash")),
        "must_reset": bool(doc.get("pin_must_reset")),
        "locked": remaining > 0,
        "locked_seconds": remaining,
        "is_super_admin": doc.get("role") == "super_admin",
    }


@router.post("/set")
async def pin_set(data: PinSetRequest, current_user: User = Depends(get_verified_user)):
    """Crea, cambia o restablece el PIN. Requiere la contraseña de la cuenta
    (re-autenticación). Sirve también como restablecimiento desde el perfil."""
    if not _is_valid_pin(data.pin):
        raise HTTPException(status_code=400, detail="El PIN debe ser de 4 dígitos")

    doc = await _get_user_doc(current_user.user_id)
    if not verify_password(data.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")

    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "pin_hash": hash_password(data.pin),
            "pin_set_at": _now(),
            "pin_failed_attempts": 0,
            "pin_locked_until": None,
            "pin_must_reset": False,
        }}
    )

    try:
        await create_notification(
            user_id=current_user.user_id,
            title="PIN de seguridad actualizado",
            message="Configuraste o cambiaste tu PIN de confirmación de operaciones.",
            notification_type="pin_updated",
        )
    except Exception as e:
        logger.warning(f"No se pudo notificar actualización de PIN: {e}")

    return {"success": True, "message": "PIN configurado correctamente"}


@router.post("/verify")
async def pin_verify(data: PinVerifyRequest, current_user: User = Depends(get_verified_user)):
    """Verifica el PIN para confirmar una operación. Bloqueo escalonado:
    3 fallos → 15 min, 6 → 1 h, 9 → 24 h + invalidación (restablecer)."""
    doc = await _get_user_doc(current_user.user_id)
    if not doc.get("pin_hash"):
        raise HTTPException(status_code=400, detail="No tienes un PIN configurado")
    if doc.get("pin_must_reset"):
        raise HTTPException(status_code=403, detail="Debes restablecer tu PIN desde tu perfil")

    remaining = _locked_remaining(doc)
    if remaining > 0:
        raise HTTPException(
            status_code=423,
            detail=f"PIN bloqueado temporalmente. Intenta de nuevo en {remaining // 60 + 1} min"
        )

    if verify_password(data.pin, doc.get("pin_hash", "")):
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {"pin_failed_attempts": 0, "pin_locked_until": None}}
        )
        return {"success": True}

    # PIN incorrecto: incrementar y aplicar bloqueo escalonado
    attempts = int(doc.get("pin_failed_attempts", 0)) + 1
    update = {"pin_failed_attempts": attempts}
    lock_msg = None

    if attempts >= SEVERE_ATTEMPTS:
        update["pin_locked_until"] = _now() + timedelta(hours=24)
        update["pin_must_reset"] = True
        update["pin_hash"] = None  # invalidar por seguridad
        lock_msg = "Tu PIN se bloqueó 24 h y fue desactivado por seguridad. Restablécelo desde tu perfil."
    elif attempts == 6:
        update["pin_locked_until"] = _now() + timedelta(hours=1)
        lock_msg = "Tu PIN se bloqueó 1 hora tras varios intentos fallidos."
    elif attempts == 3:
        update["pin_locked_until"] = _now() + timedelta(minutes=15)
        lock_msg = "Tu PIN se bloqueó 15 minutos tras varios intentos fallidos."

    await db.users.update_one({"user_id": current_user.user_id}, {"$set": update})

    if lock_msg:
        try:
            await create_notification(
                user_id=current_user.user_id,
                title="Alerta de seguridad: PIN",
                message=lock_msg,
                notification_type="pin_locked",
            )
        except Exception as e:
            logger.warning(f"No se pudo notificar bloqueo de PIN: {e}")

    # Respuesta genérica: no revela cuán cerca estuvo
    raise HTTPException(status_code=401, detail="PIN incorrecto")


@router.post("/hint-check")
async def pin_hint_check(current_user: User = Depends(get_verified_user)):
    """Tras un envío: decide si mostrar el aviso suave para configurar el PIN.

    Solo para usuarios verificados SIN PIN (no super_admin) que ya tengan al
    menos 2 envíos completados con éxito. Crea también una notificación en la
    campana. Es recurrente pero discreto: se repite hasta que configure el PIN.
    """
    doc = await _get_user_doc(current_user.user_id)
    if doc.get("role") == "super_admin" or doc.get("pin_hash"):
        return {"hint": False}
    uid = current_user.user_id
    completados = await db.transactions.count_documents(
        {"user_id": uid, "type": "withdrawal", "status": "completed"}
    )
    completados += await db.btc_remesas.count_documents({"user_id": uid, "estado": "enviado"})
    if completados < 2:
        return {"hint": False}
    msg = "Configura tu PIN para mayor seguridad en tu perfil de usuario."
    try:
        await create_notification(
            user_id=uid,
            title="Protege tus envíos",
            message=msg,
            notification_type="pin_hint",
        )
    except Exception as e:
        logger.warning(f"No se pudo crear notificación de aviso de PIN: {e}")
    return {"hint": True, "message": msg}


@router.post("/disable")
async def pin_disable(data: PinDisableRequest, current_user: User = Depends(get_verified_user)):
    """Desactiva el PIN. Requiere la contraseña de la cuenta."""
    doc = await _get_user_doc(current_user.user_id)
    if not verify_password(data.password, doc.get("password_hash", "")):
        raise HTTPException(status_code=403, detail="Contraseña incorrecta")

    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "pin_hash": None,
            "pin_failed_attempts": 0,
            "pin_locked_until": None,
            "pin_must_reset": False,
        }}
    )
    return {"success": True, "message": "PIN desactivado"}
