"""
Authentication routes
"""
import uuid
import re
import secrets
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Response
from typing import Optional

from database import db
from services.money import from_db, to_float
from models.user import User, UserSession
from models.requests import (
    SetPasswordRequest, LoginWithPasswordRequest, RegisterUserRequest,
    VerifyEmailCodeRequest, ResendVerificationCodeRequest,
    RequestPasswordResetRequest, ResetPasswordRequest, ChangePasswordRequest
)
from routes.dependencies import get_current_user, set_session_cookie, clear_session_cookie
from services.email import send_verification_email, send_password_reset_email
from services.email_notifications import notify_login, notify_password_change
from utils.security import hash_password, verify_password, validate_password, generate_temp_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    user = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0, "password_hash": 0})
    if user:
        user['password_set'] = user.get('password_set', False)
        # Normaliza los montos para que la API devuelva siempre numeros limpios,
        # tolerando datos viejos (float) y futuros (Decimal128). No cambia el valor hoy.
        for f in ("balance_ris", "balance_ves", "balance_ris_terceros", "balance_personal", "balance_terceros", "balance_usdt", "balance_usdc"):
            if f in user and user[f] is not None:
                user[f] = to_float(from_db(user[f]))
    return user

@router.post("/logout")
async def logout(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    """Logout current session"""
    # Resolver el token igual que get_current_user: cookie -> Authorization: Bearer -> X-Session-ID
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        token = request.headers.get("X-Session-ID")
    # Invalidar la sesion en el servidor: borrar por token y todas las sesiones del usuario
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    await db.user_sessions.delete_many({"user_id": current_user.user_id})
    clear_session_cookie(response)
    return {"message": "Sesión cerrada exitosamente"}

@router.post("/register")
async def register_user(request: RegisterUserRequest):
    """Register new user with email verification"""
    # Validate email
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, request.email):
        raise HTTPException(status_code=400, detail="Email inválido")
    
    email_lower = request.email.lower().strip()

    # Rechazar correos en la lista negra
    if await db.blacklist.find_one({"type": "email", "value": email_lower}):
        raise HTTPException(status_code=400, detail="Este correo no puede registrarse. Contacta a soporte.")

    # Check existing user
    existing = await db.users.find_one({"email": email_lower})
    if existing:
        if existing.get("email_verified", False):
            raise HTTPException(status_code=400, detail="Este email ya está registrado")
        else:
            await db.users.delete_one({"email": email_lower})
            await db.pending_verifications.delete_many({"email": email_lower})
    
    # Validate passwords
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Generate verification code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # Store pending registration
    pending = {
        "email": email_lower,
        "name": request.name.strip(),
        "password_hash": hash_password(request.password),
        "verification_code": verification_code,
        "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        "created_at": datetime.now(timezone.utc),
        "attempts": 0,
        "referred_by": request.referred_by.strip().upper() if request.referred_by else None
    }
    
    await db.pending_verifications.delete_many({"email": email_lower})
    await db.pending_verifications.insert_one(pending)
    
    # Send email
    email_sent = await send_verification_email(email_lower, verification_code, request.name.strip())
    
    logger.info(f"Registration initiated for {email_lower}")
    
    return {
        "message": "Código de verificación enviado a tu correo",
        "email": email_lower,
        "email_sent": email_sent,
        "code_expires_in_minutes": 15
    }

@router.post("/verify-email")
async def verify_email_code(request: VerifyEmailCodeRequest, response: Response):
    """Verify email code and complete registration"""
    email_lower = request.email.lower().strip()
    
    pending = await db.pending_verifications.find_one({"email": email_lower})
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación pendiente")
    
    # Check expiration
    expires_at = pending["code_expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) > expires_at:
        await db.pending_verifications.delete_one({"email": email_lower})
        raise HTTPException(status_code=400, detail="El código ha expirado")
    
    # Check attempts
    if pending.get("attempts", 0) >= 5:
        await db.pending_verifications.delete_one({"email": email_lower})
        raise HTTPException(status_code=400, detail="Demasiados intentos fallidos")
    
    # Verify code
    if pending["verification_code"] != request.code.strip():
        await db.pending_verifications.update_one(
            {"email": email_lower},
            {"$inc": {"attempts": 1}}
        )
        raise HTTPException(status_code=400, detail="Código incorrecto")
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    # Generate referral code
    referral_code = f"REF{uuid.uuid4().hex[:8].upper()}"
    
    user = {
        "user_id": user_id,
        "email": email_lower,
        "name": pending["name"],
        "password_hash": pending["password_hash"],
        "password_set": True,
        "email_verified": True,
        "balance_ris": 0.0,
        "balance_ves": 0.0,
        "role": "user",
        "verification_status": "unverified",
        "referred_by": pending.get("referred_by"),
        "referral_code": referral_code,
        "created_at": datetime.now(timezone.utc),
        "terms_accepted": True,
        "terms_accepted_at": datetime.now(timezone.utc),
        "terms_version": "2026-06-29"
    }
    
    await db.users.insert_one(user)
    await db.pending_verifications.delete_one({"email": email_lower})
    
    # Create session
    session_token = secrets.token_urlsafe(32)
    session = {
        "session_id": f"sess_{uuid.uuid4().hex[:12]}",
        "session_token": session_token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "is_active": True
    }
    await db.user_sessions.insert_one(session)
    set_session_cookie(response, session_token)
    
    logger.info(f"User {email_lower} registered successfully")
    
    return {
        "message": "Registro completado exitosamente",
        "session_token": session_token,
        "user": {
            "user_id": user_id,
            "email": email_lower,
            "name": pending["name"],
            "role": "user"
        }
    }

@router.post("/resend-verification-code")
async def resend_verification_code(request: Request, body: ResendVerificationCodeRequest):
    """Resend verification code"""
    from routes.security_2fa import limiter

    # 5/15min: sin esto, resend resetea el contador de intentos de /verify-email
    # a 0 cada vez, permitiendo fuerza bruta indefinida del codigo de 6 digitos.
    @limiter.limit("5/15minutes")
    async def _do_resend(request: Request, body: ResendVerificationCodeRequest):
        email_lower = body.email.lower().strip()

        pending = await db.pending_verifications.find_one({"email": email_lower})
        if not pending:
            raise HTTPException(status_code=400, detail="No hay verificación pendiente")

        verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])

        await db.pending_verifications.update_one(
            {"email": email_lower},
            {
                "$set": {
                    "verification_code": verification_code,
                    "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
                    "attempts": 0
                }
            }
        )

        email_sent = await send_verification_email(email_lower, verification_code, pending["name"])

        return {
            "message": "Nuevo código enviado",
            "email_sent": email_sent
        }

    return await _do_resend(request, body)

@router.post("/login-password")
async def login_with_password(request: Request, response: Response, body: LoginWithPasswordRequest):
    """Login with email and password.

    Security layer:
    - super_admin with 2FA enabled → returns pending_token (frontend must POST /api/auth/2fa/verify)
    - super_admin without 2FA → returns pending_token + enrollment_required=true
    - admin/super_admin sessions expire in 30 min; regular users in 7 days
    """
    # Rate limit imported lazily to avoid circular imports
    from routes.security_2fa import (
        limiter, issue_session_token, _create_pending_token,
        ADMIN_ROLES, SUPER_ADMIN_ROLE,
    )

    # 20/15min per IP — bloquea brute-force pero NO penaliza usuarios reales
    # detrás de NAT/oficina/wifi compartido. La defensa fuerte contra ataques
    # a cuentas privilegiadas es el 2FA obligatorio en super_admin.
    @limiter.limit("20/15minutes")
    async def _do_login(request: Request, body):
        email_lower = body.email.lower().strip()

        user = await db.users.find_one({"email": email_lower})
        if not user:
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        if not user.get("email_verified"):
            raise HTTPException(status_code=401, detail="Email no verificado")

        if not user.get("password_set") or not user.get("password_hash"):
            raise HTTPException(status_code=401, detail="No tienes contraseña configurada")

        if user.get("status") == "suspended":
            raise HTTPException(status_code=403, detail="Tu cuenta ha sido suspendida. Contacta al administrador.")

        if not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        role = user.get("role", "user")
        is_admin = role in ADMIN_ROLES
        twofa_enabled = bool(user.get("two_factor_enabled", False))

        # Super admin without 2FA → force enrollment
        if role == SUPER_ADMIN_ROLE and not twofa_enabled:
            pending = await _create_pending_token(user["user_id"], purpose="2fa_enroll")
            return {
                "message": "Configura 2FA para continuar",
                "two_factor_enrollment_required": True,
                "pending_token": pending,
                "email": user["email"],
                "user_id": user["user_id"],
            }

        # Admin/super_admin with 2FA enabled → challenge
        if is_admin and twofa_enabled:
            pending = await _create_pending_token(user["user_id"], purpose="2fa_login")
            return {
                "message": "Ingresa tu código 2FA para continuar",
                "two_factor_required": True,
                "pending_token": pending,
                "email": user["email"],
            }

        # Normal user (or admin without 2FA — admin role NOT required to have 2FA, only super_admin)
        token = await issue_session_token(user, request=request, two_factor_used=False)

        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )

        logger.info(f"User {user['user_id']} logged in with password (2FA={twofa_enabled})")

        try:
            await notify_login(
                email=user["email"],
                user_name=user.get("name", "Usuario"),
                device="Web Browser"
            )
        except Exception as e:
            logger.warning(f"Failed to send login notification: {e}")

        for f in ("balance_ris", "balance_ves", "balance_ris_terceros", "balance_personal", "balance_terceros", "balance_usdt", "balance_usdc"):
            if f in user and user[f] is not None:
                user[f] = to_float(from_db(user[f]))
        user_response = {
            k: v for k, v in user.items()
            if k not in ["_id", "password_hash", "two_factor_secret",
                         "two_factor_secret_pending", "two_factor_backup_hashes"]
        }

        return {
            "message": "Login exitoso",
            "session_token": token,
            "user": user_response,
            "must_change_password": user.get("must_change_password", False)
        }

    result = await _do_login(request, body)
    if isinstance(result, dict) and result.get("session_token"):
        set_session_cookie(response, result["session_token"])
    return result

@router.post("/request-password-reset")
async def request_password_reset(request: Request, body: RequestPasswordResetRequest):
    """Request password reset"""
    from routes.security_2fa import limiter

    # 5/15min: evita bombardeo de emails de reseteo a una victima.
    @limiter.limit("5/15minutes")
    async def _do_request_reset(request: Request, body: RequestPasswordResetRequest):
        email_lower = body.email.lower().strip()

        user = await db.users.find_one({"email": email_lower})
        if not user:
            # Don't reveal if user exists
            return {"message": "Si el email existe, recibirás instrucciones"}

        temp_password = generate_temp_password()

        await db.users.update_one(
            {"email": email_lower},
            {
                "$set": {
                    "password_reset_token": hash_password(temp_password),
                    "password_reset_expires": datetime.now(timezone.utc) + timedelta(hours=1),
                    "must_change_password": True
                }
            }
        )

        await send_password_reset_email(email_lower, temp_password)

        return {"message": "Si el email existe, recibirás instrucciones"}

    return await _do_request_reset(request, body)

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password with temp password"""
    email_lower = request.email.lower().strip()
    
    user = await db.users.find_one({"email": email_lower})
    if not user:
        raise HTTPException(status_code=400, detail="Usuario no encontrado")
    
    reset_token = user.get("password_reset_token")
    reset_expires = user.get("password_reset_expires")
    
    if not reset_token or not reset_expires:
        raise HTTPException(status_code=400, detail="No hay solicitud de reseteo pendiente")
    
    if reset_expires.tzinfo is None:
        reset_expires = reset_expires.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) > reset_expires:
        raise HTTPException(status_code=400, detail="El enlace ha expirado")
    
    if not verify_password(request.temp_password, reset_token):
        raise HTTPException(status_code=400, detail="Contraseña temporal inválida")
    
    # Validate new password
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Update password
    await db.users.update_one(
        {"email": email_lower},
        {
            "$set": {
                "password_hash": hash_password(request.new_password),
                "password_set": True,
                "must_change_password": False
            },
            "$unset": {
                "password_reset_token": "",
                "password_reset_expires": ""
            }
        }
    )
    
    return {"message": "Contraseña actualizada exitosamente"}

@router.post("/change-password")
async def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user)):
    """Change password for logged in user"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    if not verify_password(request.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {
            "$set": {
                "password_hash": hash_password(request.new_password),
                "must_change_password": False
            }
        }
    )
    
    # Send password change notification
    try:
        await notify_password_change(
            email=user["email"],
            user_name=user.get("name", "Usuario")
        )
    except Exception as e:
        logger.warning(f"Failed to send password change notification: {e}")
    
    return {"message": "Contraseña cambiada exitosamente"}

@router.get("/password-status")
async def get_password_status(current_user: User = Depends(get_current_user)):
    """Check if user needs to change password"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    return {
        "password_set": user.get("password_set", False),
        "must_change_password": user.get("must_change_password", False)
    }

@router.post("/register-fcm-token")
async def register_fcm_token(request: Request, current_user: User = Depends(get_current_user)):
    """Register FCM token for push notifications"""
    data = await request.json()
    fcm_token = data.get('fcm_token')
    
    if not fcm_token:
        raise HTTPException(status_code=400, detail="FCM token required")
    
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"push_token": fcm_token}}
    )
    
    return {"message": "Token registrado"}

@router.post("/heartbeat")
async def heartbeat(current_user: User = Depends(get_current_user)):
    """Update user online status"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_online": True, "last_seen": datetime.now(timezone.utc)}}
    )
    return {"status": "ok"}

@router.post("/offline")
async def mark_offline(current_user: User = Depends(get_current_user)):
    """Mark user as offline"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}}
    )
    return {"status": "ok"}

# NOTA — acá abajo estaba TODO este archivo otra vez, y no se podía borrar
# desde cualquiera de las dos puntas.
#
# Las líneas 508 a 1014 repetían el docstring, los imports, el `router` y los
# trece handlers de arriba. Los cuerpos eran idénticos, pero los imports NO:
# la segunda copia importaba
#
#     from fastapi import APIRouter, Request, Depends, HTTPException, Header
#     from routes.dependencies import get_current_user
#
# sin `Response`, sin `set_session_cookie` y sin `clear_session_cookie` — que
# sus propios cuerpos usaban en logout, verify_email_code y
# login_with_password. Andaba de casualidad: esos tres nombres estaban en el
# namespace del módulo porque los había importado la PRIMERA copia.
#
# Y la que atendía los pedidos era la segunda, porque `router = APIRouter(...)`
# se volvía a asignar en la línea 534: los trece handlers de arriba quedaban
# registrados en un router huérfano que nadie incluía.
#
# O sea que el "borrar el duplicado" evidente —sacar la primera mitad, la que
# parece muerta— dejaba a login, logout y verificación de email levantando
# NameError en la primera llamada. Se conserva la primera copia, que tiene los
# imports completos, y se borra la segunda.
