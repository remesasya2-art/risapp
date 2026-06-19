"""
Login con huella (WebAuthn / passkey).
- rp_id = risappbr.com (dominio raíz; cubre también www.risappbr.com).
- origins permitidos = https://risappbr.com y https://www.risappbr.com.
NO reemplaza el login con contraseña: es un desbloqueo rápido opcional que el
usuario (o super_admin) activa desde su perfil. La app nunca ve la huella; solo
guarda una llave pública por dispositivo.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from database import db
from models.user import User
from routes.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webauthn", tags=["webauthn"])

RP_ID = "risappbr.com"
RP_NAME = "RIS App"
ALLOWED_ORIGINS = ["https://risappbr.com", "https://www.risappbr.com"]
CHALLENGE_TTL_SECONDS = 300  # 5 minutos


def _now():
    return datetime.now(timezone.utc)


def _challenge_valido(doc: dict, campo_ts: str) -> bool:
    ts = doc.get(campo_ts)
    if not ts:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_now() - ts).total_seconds() <= CHALLENGE_TTL_SECONDS


class RegisterVerifyBody(BaseModel):
    credential: dict
    label: Optional[str] = None


class LoginOptionsBody(BaseModel):
    email: str


class LoginVerifyBody(BaseModel):
    email: str
    credential: dict


# ---------------------------------------------------------------------------
# REGISTRO (activar huella en este dispositivo) — requiere sesión iniciada
# ---------------------------------------------------------------------------
@router.post("/register/options")
async def register_options(current_user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": current_user.user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    existing = doc.get("webauthn_credentials", []) or []
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in existing if c.get("credential_id")
    ]
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(current_user.user_id).encode("utf-8"),
        user_name=doc.get("email", current_user.user_id),
        user_display_name=doc.get("name", "Usuario"),
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
        exclude_credentials=exclude,
    )
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "webauthn_reg_challenge": bytes_to_base64url(options.challenge),
            "webauthn_reg_challenge_at": _now(),
        }},
    )
    return json.loads(options_to_json(options))


@router.post("/register/verify")
async def register_verify(body: RegisterVerifyBody, current_user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": current_user.user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    challenge = doc.get("webauthn_reg_challenge")
    if not challenge or not _challenge_valido(doc, "webauthn_reg_challenge_at"):
        raise HTTPException(status_code=400, detail="Reto expirado, intenta de nuevo")
    try:
        verification = verify_registration_response(
            credential=json.dumps(body.credential),
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=RP_ID,
            expected_origin=ALLOWED_ORIGINS,
            require_user_verification=False,
        )
    except Exception as e:
        logger.warning(f"WebAuthn registro fallido: {e}")
        raise HTTPException(status_code=400, detail="No se pudo registrar la huella")
    cred_id = bytes_to_base64url(verification.credential_id)
    nueva = {
        "credential_id": cred_id,
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "label": (body.label or "Mi dispositivo")[:60],
        "created_at": _now(),
    }
    # Evita duplicar la misma credencial
    existing = doc.get("webauthn_credentials", []) or []
    existing = [c for c in existing if c.get("credential_id") != cred_id]
    existing.append(nueva)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"webauthn_credentials": existing},
         "$unset": {"webauthn_reg_challenge": "", "webauthn_reg_challenge_at": ""}},
    )
    return {"success": True, "message": "Huella activada en este dispositivo"}


@router.get("/credentials")
async def list_credentials(current_user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": current_user.user_id})
    creds = (doc or {}).get("webauthn_credentials", []) or []
    return {
        "credentials": [
            {
                "credential_id": c.get("credential_id"),
                "label": c.get("label", "Dispositivo"),
                "created_at": c.get("created_at"),
            }
            for c in creds
        ]
    }


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str, current_user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": current_user.user_id})
    creds = (doc or {}).get("webauthn_credentials", []) or []
    nuevos = [c for c in creds if c.get("credential_id") != credential_id]
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"webauthn_credentials": nuevos}},
    )
    return {"success": True, "message": "Dispositivo eliminado"}


# ---------------------------------------------------------------------------
# LOGIN con huella — público (el usuario aún no tiene sesión)
# ---------------------------------------------------------------------------
@router.post("/login/options")
async def login_options(body: LoginOptionsBody):
    email = (body.email or "").lower().strip()
    user = await db.users.find_one({"email": email})
    creds = (user or {}).get("webauthn_credentials", []) or []
    # Respuesta genérica: no confirma si el email existe o tiene huella
    if not user or not creds:
        raise HTTPException(status_code=404, detail="No hay huella registrada para esta cuenta")
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in creds if c.get("credential_id")
    ]
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "webauthn_auth_challenge": bytes_to_base64url(options.challenge),
            "webauthn_auth_challenge_at": _now(),
        }},
    )
    return json.loads(options_to_json(options))


@router.post("/login/verify")
async def login_verify(body: LoginVerifyBody, request: Request):
    email = (body.email or "").lower().strip()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="No se pudo verificar la huella")
    challenge = user.get("webauthn_auth_challenge")
    if not challenge or not _challenge_valido(user, "webauthn_auth_challenge_at"):
        raise HTTPException(status_code=400, detail="Reto expirado, intenta de nuevo")
    creds = user.get("webauthn_credentials", []) or []
    cred_id = body.credential.get("id")
    cred = next((c for c in creds if c.get("credential_id") == cred_id), None)
    if not cred:
        raise HTTPException(status_code=401, detail="Dispositivo no reconocido")
    try:
        verification = verify_authentication_response(
            credential=json.dumps(body.credential),
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=RP_ID,
            expected_origin=ALLOWED_ORIGINS,
            credential_public_key=base64url_to_bytes(cred["public_key"]),
            credential_current_sign_count=cred.get("sign_count", 0),
            require_user_verification=False,
        )
    except Exception as e:
        logger.warning(f"WebAuthn login fallido: {e}")
        raise HTTPException(status_code=401, detail="No se pudo verificar la huella")
    # Actualiza el contador anti-clonación y limpia el reto
    cred["sign_count"] = verification.new_sign_count
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"webauthn_credentials": creds},
         "$unset": {"webauthn_auth_challenge": "", "webauthn_auth_challenge_at": ""}},
    )
    # Emite la sesión igual que el login normal (import diferido evita ciclos)
    from routes.security_2fa import issue_session_token
    token = await issue_session_token(user, request=request, two_factor_used=True)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_login": _now()}},
    )
    user_response = {
        k: v for k, v in user.items()
        if k not in ["_id", "password_hash", "two_factor_secret",
                     "two_factor_secret_pending", "two_factor_backup_hashes",
                     "webauthn_credentials", "webauthn_auth_challenge",
                     "webauthn_reg_challenge", "pin_hash"]
    }
    return {
        "message": "Login exitoso",
        "session_token": token,
        "user": user_response,
        "must_change_password": user.get("must_change_password", False),
    }
