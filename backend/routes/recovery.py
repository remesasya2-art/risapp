"""
Password Recovery routes - Identity verification and password reset
"""
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from pymongo import ReturnDocument

from database import db
from services.email_notifications import send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recovery", tags=["recovery"])


class VerifyIdentityRequest(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: str
    cpf: str
    document_number: str  # RNM, CI or Passport


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    recovery_token: str
    new_password: str


class SupportContactRequest(BaseModel):
    email: EmailStr
    subject: str
    phone_number: str
    message: str  # Max 200 characters


@router.post("/verify-identity")
async def verify_identity(data: VerifyIdentityRequest, request: Request):
    """Step 1: Verify user identity with personal data"""
    from routes.security_2fa import frenar

    async def _do_verify(request: Request, data: VerifyIdentityRequest):
        # 5/15min por IP: evita que se use este endpoint como oráculo para
        # fuerza-brutear CPF/teléfono/documento de una víctima campo por campo.
        frenar(request, "recovery.verify_identity", "5/15minutes")
        GENERIC_ERROR = "Los datos no coinciden con nuestros registros"

        # Find user by email
        user = await db.users.find_one({"email": data.email.lower()})
        if not user:
            # No revelamos si el correo existe o no: mismo mensaje que un dato incorrecto.
            raise HTTPException(status_code=400, detail=GENERIC_ERROR)

        # Verify personal data matches
        user_cpf = (user.get("cpf_number") or "").replace(".", "").replace("-", "")
        input_cpf = data.cpf.replace(".", "").replace("-", "")

        verification = await db.verifications.find_one({"user_id": user["user_id"]}, sort=[("submitted_at", -1)])

        matches = True

        stored_name = (verification.get("full_name") if verification else user.get("name", "")).lower().strip()
        input_name = data.full_name.lower().strip()
        if stored_name != input_name:
            matches = False

        stored_phone = (verification.get("phone_number") if verification else user.get("phone_number", "")).replace(" ", "").replace("-", "")
        input_phone = data.phone_number.replace(" ", "").replace("-", "")
        if stored_phone != input_phone and stored_phone[-8:] != input_phone[-8:]:
            matches = False

        stored_cpf = (verification.get("cpf_number") if verification else user_cpf).replace(".", "").replace("-", "")
        if stored_cpf != input_cpf:
            matches = False

        stored_doc = (verification.get("document_number") if verification else user.get("document_number", "")).replace(" ", "").upper()
        input_doc = data.document_number.replace(" ", "").upper()
        if stored_doc != input_doc:
            matches = False

        if not matches:
            # No revelamos cual campo especifico fallo (evita el oraculo campo-por-campo).
            raise HTTPException(status_code=400, detail=GENERIC_ERROR)

        # Generate 6-digit verification code
        code = str(random.randint(100000, 999999))

        # Store recovery attempt with expiration (5 minutes)
        recovery_id = f"rec_{uuid.uuid4().hex[:12]}"
        await db.password_recovery.delete_many({"email": data.email.lower()})  # Remove old attempts
        await db.password_recovery.insert_one({
            "recovery_id": recovery_id,
            "email": data.email.lower(),
            "user_id": user["user_id"],
            "code": code,
            "attempts": 0,
            "max_attempts": 3,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "created_at": datetime.now(timezone.utc),
            "verified": False
        })

        # Send code via email
        try:
            await send_email(
                to_email=data.email,
                subject="🔐 RIS App - Código de Recuperación",
                html_content=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #6366f1;">Recuperación de Contraseña</h2>
                    <p>Hola {data.full_name},</p>
                    <p>Tu código de verificación es:</p>
                    <div style="background: #f3f4f6; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                        <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #111827;">{code}</span>
                    </div>
                    <p style="color: #ef4444; font-weight: 600;">⚠️ Este código expira en 5 minutos.</p>
                    <p style="color: #6b7280; font-size: 14px;">Si no solicitaste este código, ignora este mensaje.</p>
                </div>
                """
            )
            logger.info(f"Recovery code sent to {data.email}")
        except Exception as e:
            logger.error(f"Failed to send recovery email: {e}")
            raise HTTPException(status_code=500, detail="Error al enviar el código. Intenta nuevamente.")

        return {
            "success": True,
            "message": "Código enviado a tu correo",
            "email_masked": data.email[:3] + "***" + data.email[data.email.index("@"):]
        }
    return await _do_verify(request, data)


@router.post("/verify-code")
async def verify_code(data: VerifyCodeRequest, request: Request):
    """Step 2: Verify the code sent to email"""
    from routes.security_2fa import frenar

    # 20/15min. Adentro hay un contador de intentos por solicitud, pero se lleva
    # en el documento: pedir una solicitud nueva lo reinicia. El tope por IP es
    # el que cuenta las pruebas sin importar cuántas solicitudes se abran.
    frenar(request, "recovery.verify_code", "20/15minutes")
    
    # Find recovery attempt
    recovery = await db.password_recovery.find_one({
        "email": data.email.lower(),
        "verified": False
    })
    
    if not recovery:
        raise HTTPException(status_code=400, detail="No hay solicitud de recuperación pendiente")
    
    # Check expiration
    if datetime.now(timezone.utc) > recovery["expires_at"].replace(tzinfo=timezone.utc):
        await db.password_recovery.delete_one({"_id": recovery["_id"]})
        raise HTTPException(status_code=400, detail="El código ha expirado. Solicita uno nuevo.")
    
    # Check attempts
    if recovery["attempts"] >= recovery["max_attempts"]:
        await db.password_recovery.delete_one({"_id": recovery["_id"]})
        raise HTTPException(status_code=400, detail="Máximo de intentos alcanzado. Solicita un nuevo código.")
    
    # Verify code
    if recovery["code"] != data.code:
        await db.password_recovery.update_one(
            {"_id": recovery["_id"]},
            {"$inc": {"attempts": 1}}
        )
        remaining = recovery["max_attempts"] - recovery["attempts"] - 1
        raise HTTPException(
            status_code=400, 
            detail=f"Código incorrecto. Te quedan {remaining} intento(s)."
        )
    
    # Generate recovery token for password reset
    recovery_token = uuid.uuid4().hex
    await db.password_recovery.update_one(
        {"_id": recovery["_id"]},
        {
            "$set": {
                "verified": True,
                "recovery_token": recovery_token,
                "verified_at": datetime.now(timezone.utc),
                "token_expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)
            }
        }
    )
    
    return {
        "success": True,
        "message": "Código verificado correctamente",
        "recovery_token": recovery_token
    }


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, request: Request):
    """Step 3: Set new password"""
    from routes.security_2fa import frenar

    # 10/15min. El `recovery_token` son 128 bits al azar y no se adivina; lo que
    # se frena es el costo de hashear una contraseña nueva en cada llamada.
    frenar(request, "recovery.reset_password", "10/15minutes")

    # Validate password strength
    password = data.new_password
    errors = []
    
    if len(password) < 8:
        errors.append("mínimo 8 caracteres")
    if not any(c.isupper() for c in password):
        errors.append("al menos una mayúscula")
    if not any(c.islower() for c in password):
        errors.append("al menos una minúscula")
    if not any(c.isdigit() for c in password):
        errors.append("al menos un número")
    
    if errors:
        raise HTTPException(
            status_code=400,
            detail=f"La contraseña debe tener: {', '.join(errors)}"
        )
    
    # Find and validate recovery
    recovery = await db.password_recovery.find_one({
        "email": data.email.lower(),
        "recovery_token": data.recovery_token,
        "verified": True
    })
    
    if not recovery:
        raise HTTPException(status_code=400, detail="Token de recuperación inválido")
    
    # Check token expiration
    if datetime.now(timezone.utc) > recovery["token_expires_at"].replace(tzinfo=timezone.utc):
        await db.password_recovery.delete_one({"_id": recovery["_id"]})
        raise HTTPException(status_code=400, detail="El token ha expirado. Inicia el proceso nuevamente.")
    
    # Hash new password
    import bcrypt
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Update user password
    await db.users.update_one(
        {"user_id": recovery["user_id"]},
        {
            "$set": {
                "password_hash": hashed,
                "password_set": True,
                "password_updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # Delete recovery record
    await db.password_recovery.delete_one({"_id": recovery["_id"]})
    
    # Send confirmation email
    user = await db.users.find_one({"user_id": recovery["user_id"]})
    try:
        await send_email(
            to_email=data.email,
            subject="✅ RIS App - Contraseña Actualizada",
            html_content=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #16a34a;">Contraseña Actualizada</h2>
                <p>Hola {user.get('name', '')},</p>
                <p>Tu contraseña ha sido cambiada exitosamente.</p>
                <p style="color: #6b7280; font-size: 14px;">Si no realizaste este cambio, contacta a soporte inmediatamente.</p>
            </div>
            """
        )
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
    
    logger.info(f"Password reset successful for {data.email}")
    
    return {
        "success": True,
        "message": "Contraseña actualizada correctamente. Ya puedes iniciar sesión."
    }


@router.post("/support-contact")
async def support_contact(data: SupportContactRequest, request: Request):
    """Send support contact request"""
    from routes.security_2fa import frenar

    # 5/hora. Cada llamada manda un mensaje a soporte con texto que escribe
    # quien llama. Sin tope, es una vía para llenar la bandeja de soporte y
    # tapar los pedidos reales, que es donde termina doliendo.
    frenar(request, "recovery.support_contact", "5/hour")

    # Validate message length
    if len(data.message) > 200:
        raise HTTPException(status_code=400, detail="El mensaje no puede exceder 200 caracteres")
    
    if len(data.message) < 10:
        raise HTTPException(status_code=400, detail="El mensaje debe tener al menos 10 caracteres")
    
    # Store support request
    support_id = f"sup_{uuid.uuid4().hex[:12]}"
    # Número de caso secuencial y atómico (TKT-000123)
    counter = await db.counters.find_one_and_update(
        {"_id": "support_case"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    case_number = counter.get("seq", 1)
    case_code = f"TKT-{case_number:06d}"
    await db.support_requests.insert_one({
        "support_id": support_id,
        "case_number": case_number,
        "case_code": case_code,
        "email": data.email.lower(),
        "subject": data.subject,
        "phone_number": data.phone_number,
        "message": data.message,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    })
    
    # Send notification to admin (optional - could be configured)
    logger.info(f"Support request received: {support_id} from {data.email}")
    
    # Send confirmation to user
    try:
        await send_email(
            to_email=data.email,
            subject="📩 RIS App - Solicitud de Soporte Recibida",
            html_content=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #6366f1;">Solicitud Recibida</h2>
                <p>Hemos recibido tu solicitud de soporte.</p>
                <div style="background: #f3f4f6; padding: 15px; border-radius: 10px; margin: 15px 0;">
                    <p style="margin: 0;"><strong>Asunto:</strong> {data.subject}</p>
                    <p style="margin: 10px 0 0 0;"><strong>Mensaje:</strong> {data.message}</p>
                </div>
                <p>Nuestro equipo te contactará pronto al correo o teléfono proporcionado.</p>
                <p style="color: #6b7280; font-size: 14px;">Número de ticket: {support_id}</p>
            </div>
            """
        )
    except Exception as e:
        logger.error(f"Failed to send support confirmation: {e}")
    
    return {
        "success": True,
        "message": "Solicitud enviada. Te contactaremos pronto.",
        "ticket_id": support_id
    }
