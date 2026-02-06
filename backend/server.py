from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import json
import base64
from openpyxl import Workbook
from io import BytesIO
import bcrypt
import secrets
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client as TwilioClient
from whatsapp_service import whatsapp_service
from mercadopago_service import mercadopago_service
from admin_routes import admin_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Twilio SMS Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Stripe configuration (disabled - using Mercado Pago PIX)
# stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_placeholder')

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer()

# =======================
# SMS VERIFICATION SERVICE
# =======================
async def send_verification_sms(phone_number: str, code: str, name: str) -> bool:
    """Send verification code via SMS using Twilio"""
    if not twilio_client or not TWILIO_PHONE_NUMBER:
        logger.warning("Twilio not configured - SMS not sent")
        return False
    
    try:
        # Format phone number (ensure it has country code)
        formatted_phone = phone_number.strip()
        if not formatted_phone.startswith('+'):
            # Assume Brazil if no country code
            formatted_phone = '+55' + formatted_phone.lstrip('0')
        
        message = twilio_client.messages.create(
            body=f"🔐 RIS App - Hola {name}!\n\nTu código de verificación es: {code}\n\nEste código expira en 15 minutos.",
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        
        logger.info(f"📱 SMS sent to {formatted_phone} - SID: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
        return False

# =======================
# MODELS
# =======================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    balance_ris: float = 0.0
    # Authentication/Security fields
    password_hash: Optional[str] = None  # Hashed password
    password_set: bool = False  # True if user has set a password
    password_changed_at: Optional[datetime] = None
    password_reset_token: Optional[str] = None
    password_reset_expires: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    # Role and permissions
    role: str = "user"  # user, admin, super_admin
    permissions: List[str] = []  # List of specific permissions
    created_by_admin: Optional[str] = None  # If created as sub-admin
    # KYC/Verification fields
    verification_status: str = "pending"  # pending, verified, rejected
    id_document_image: Optional[str] = None  # base64
    cpf_image: Optional[str] = None  # base64
    selfie_image: Optional[str] = None  # base64 - live selfie
    full_name: Optional[str] = None  # For card validation
    document_number: Optional[str] = None
    cpf_number: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None  # admin user_id
    rejection_reason: Optional[str] = None
    # Declaration acceptance
    accepted_declaration: bool = False
    declaration_accepted_at: Optional[datetime] = None
    # Policy acceptance (LGPD compliance)
    accepted_policies: bool = False
    policies_version: Optional[str] = None  # Version of policies accepted
    policies_accepted_at: Optional[datetime] = None
    policies_ip_address: Optional[str] = None  # IP at time of acceptance
    # Push notifications
    fcm_token: Optional[str] = None  # Firebase Cloud Messaging token
    # Admin status
    is_active: bool = True
    last_login: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Available permissions for sub-admins
ADMIN_PERMISSIONS = {
    "withdrawals.view": "Ver retiros",
    "withdrawals.process": "Procesar retiros",
    "recharges.view": "Ver recargas",
    "recharges.approve": "Aprobar recargas",
    "support.view": "Ver chats de soporte",
    "support.respond": "Responder chats",
    "support.close": "Cerrar chats",
    "users.view": "Ver usuarios",
    "users.edit": "Editar usuarios",
    "kyc.view": "Ver KYC",
    "kyc.approve": "Aprobar/Rechazar KYC",
    "transactions.view": "Ver transacciones",
    "transactions.export": "Exportar transacciones",
    "settings.view": "Ver configuración",
    "settings.edit": "Editar configuración",
    "admins.view": "Ver administradores",
    "admins.create": "Crear sub-administradores",
    "admins.edit": "Editar sub-administradores",
    "dashboard.view": "Ver dashboard",
}

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ExchangeRate(BaseModel):
    ris_to_ves: float = 78.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = None

class Beneficiary(BaseModel):
    beneficiary_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    full_name: str
    account_number: str
    id_document: str
    phone_number: str
    bank: str
    bank_code: Optional[str] = None  # Venezuelan bank code (e.g., 0102)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Transaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: str  # "recharge" or "withdrawal"
    status: str  # "pending", "completed", "rejected"
    amount_input: float  # REAIS or RIS
    amount_output: float  # RIS or VES
    # For recharge
    stripe_payment_intent_id: Optional[str] = None
    # For withdrawal
    beneficiary_data: Optional[dict] = None
    proof_image: Optional[str] = None  # base64
    processed_by: Optional[str] = None  # admin user_id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class SessionDataResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: str
    session_token: str

# Request/Response Models
class RechargeRequest(BaseModel):
    amount: float  # In REAIS

class WithdrawalRequest(BaseModel):
    amount_ris: float
    beneficiary_data: dict

class ProcessWithdrawalRequest(BaseModel):
    transaction_id: str
    proof_image: str  # base64

class UpdateRateRequest(BaseModel):
    ris_to_ves: float

class BeneficiaryCreate(BaseModel):
    full_name: str
    account_number: str
    id_document: str
    phone_number: str
    bank: str
    bank_code: Optional[str] = None  # Venezuelan bank code (e.g., 0102)

class VerificationRequest(BaseModel):
    full_name: str
    document_number: str
    cpf_number: str
    id_document_image: str  # base64
    cpf_image: str  # base64
    selfie_image: str  # base64 - live selfie

class VerificationDecision(BaseModel):
    user_id: str
    approved: bool
    rejection_reason: Optional[str] = None

# Security/Password Models
class SetPasswordRequest(BaseModel):
    password: str
    confirm_password: str

class LoginWithPasswordRequest(BaseModel):
    email: str
    password: str

class RegisterUserRequest(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str
    phone: Optional[str] = None

class VerifyEmailCodeRequest(BaseModel):
    email: str
    code: str

class ResendVerificationCodeRequest(BaseModel):
    email: str

class RequestPasswordResetRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    reset_token: str
    new_password: str
    confirm_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str
    selfie_image: str  # Live selfie for verification

# =======================
# PASSWORD UTILITIES
# =======================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password requirements:
    - Minimum 7 characters
    - Must contain letters (a-z, A-Z)
    - Must contain numbers (0-9)
    - Must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)
    """
    if len(password) < 7:
        return False, "La contraseña debe tener al menos 7 caracteres"
    
    if not re.search(r'[a-zA-Z]', password):
        return False, "La contraseña debe contener al menos una letra"
    
    if not re.search(r'[0-9]', password):
        return False, "La contraseña debe contener al menos un número"
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
        return False, "La contraseña debe contener al menos un carácter especial (!@#$%^&*...)"
    
    return True, "OK"

def generate_reset_token() -> str:
    """Generate a secure reset token"""
    return secrets.token_urlsafe(32)

def generate_temp_password() -> str:
    """Generate a temporary password"""
    return secrets.token_urlsafe(8)

async def send_password_reset_email(email: str, temp_password: str):
    """Send password reset email with temporary password"""
    try:
        # Simple email sending (you should configure with proper SMTP in production)
        subject = "RIS App - Código de Recuperación de Contraseña"
        body = f"""
Hola,

Has solicitado recuperar tu contraseña en RIS App.

Tu código temporal de acceso es: {temp_password}

Este código expira en 15 minutos.

Si no solicitaste este cambio, ignora este mensaje.

Saludos,
Equipo RIS
"""
        # Log for now (in production, use proper email service)
        logger.info(f"Password reset email for {email}: Temp password = {temp_password}")
        
        # Try to send via SMTP if configured
        smtp_host = os.getenv('SMTP_HOST', '')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_pass = os.getenv('SMTP_PASS', '')
        
        if smtp_host and smtp_user:
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            logger.info(f"Password reset email sent to {email}")
        else:
            # Fallback: create notification in-app
            user = await db.users.find_one({"email": email})
            if user:
                await create_notification(
                    user_id=user['user_id'],
                    title="🔐 Código de Recuperación",
                    message=f"Tu código temporal es: {temp_password}. Expira en 15 minutos.",
                    notification_type="password_reset",
                    data={"temp_password": temp_password}
                )
            logger.info(f"Password reset notification created for {email}")
            
        return True
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")
        return False

# =======================
# AUTH DEPENDENCIES
# =======================

async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Get current user from session token (cookie or header)"""
    session_token = None
    
    # Check cookie first
    session_token = request.cookies.get('session_token')
    
    # Fallback to Authorization header
    if not session_token and authorization:
        if authorization.startswith('Bearer '):
            session_token = authorization[7:]
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Find session
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    # Check expiration
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user_doc = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(**user_doc)

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Check if user is admin or super_admin"""
    user_data = await db.users.find_one({"user_id": current_user.user_id})
    role = user_data.get('role', 'user') if user_data else 'user'
    
    if role not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Update current_user with role and permissions
    current_user.role = role
    current_user.permissions = user_data.get('permissions', []) if user_data else []
    return current_user

async def get_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Check if user is super_admin"""
    user_data = await db.users.find_one({"user_id": current_user.user_id})
    role = user_data.get('role', 'user') if user_data else 'user'
    
    if role != 'super_admin':
        raise HTTPException(status_code=403, detail="Super admin access required")
    
    current_user.role = role
    current_user.permissions = list(ADMIN_PERMISSIONS.keys())
    return current_user

def has_permission(user: User, permission: str) -> bool:
    """Check if user has specific permission"""
    if user.role == 'super_admin':
        return True
    if user.role == 'admin':
        # Admin has all except admin management
        admin_only = ['admins.create', 'admins.edit']
        return permission not in admin_only
    return permission in user.permissions

def require_permission(permission: str):
    """Dependency to check for specific permission"""
    async def checker(admin_user: User = Depends(get_admin_user)):
        if not has_permission(admin_user, permission):
            raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
        return admin_user
    return checker

async def get_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Check if user is verified"""
    if current_user.verification_status != "verified":
        raise HTTPException(
            status_code=403, 
            detail="Account not verified. Please complete verification first."
        )
    return current_user

# =======================
# AUTH ROUTES
# =======================

@api_router.post("/auth/session")
async def create_session(request: Request, x_session_id: str = Header(..., alias="X-Session-ID")):
    """Exchange session_id for user data and session_token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": x_session_id}
            )
            response.raise_for_status()
            user_data = response.json()
        
        # Create or update user
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        existing_user = await db.users.find_one({"email": user_data["email"]}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user["user_id"]
            # Invalidate all previous sessions (single session policy)
            await db.user_sessions.delete_many({"user_id": user_id})
        else:
            # Create new user
            new_user = User(
                user_id=user_id,
                email=user_data["email"],
                name=user_data["name"],
                picture=user_data.get("picture"),
                balance_ris=0.0
            )
            await db.users.insert_one(new_user.dict())
        
        # Create session
        session_token = user_data["session_token"]
        session = UserSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        await db.user_sessions.insert_one(session.dict())
        
        # Update last login
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )
        
        return SessionDataResponse(**user_data)
    except Exception as e:
        logging.error(f"Session creation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    # Get user from DB to include all fields
    user = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0, "password_hash": 0})
    if user:
        # Add password_set status
        user['password_set'] = user.get('password_set', False)
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    session_token = request.cookies.get('session_token')
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    return {"message": "Logged out successfully"}

@api_router.post("/auth/register-fcm-token")
async def register_fcm_token(request: Request, current_user: User = Depends(get_current_user)):
    """Register FCM token for push notifications"""
    try:
        data = await request.json()
        fcm_token = data.get('fcm_token')
        
        if not fcm_token:
            raise HTTPException(status_code=400, detail="FCM token is required")
        
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {"fcm_token": fcm_token}}
        )
        
        logger.info(f"FCM token registered for user {current_user.user_id}")
        return {"message": "FCM token registered successfully"}
        
    except Exception as e:
        logger.error(f"Error registering FCM token: {e}")
        raise HTTPException(status_code=500, detail="Error registering FCM token")

@api_router.post("/auth/heartbeat")
async def user_heartbeat(current_user: User = Depends(get_current_user)):
    """Update user's last seen timestamp (call every 30 seconds to show online status)"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"last_seen": datetime.now(timezone.utc), "is_online": True}}
    )
    return {"status": "ok"}

@api_router.post("/auth/offline")
async def user_offline(current_user: User = Depends(get_current_user)):
    """Mark user as offline"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}}
    )
    return {"status": "ok"}

@api_router.get("/admin/users")
async def get_all_users(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all registered users with online status"""
    # Consider users online if last_seen within 2 minutes
    online_threshold = datetime.now(timezone.utc) - timedelta(minutes=2)
    
    users = await db.users.find(
        {},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "phone": 1,
            "picture": 1,
            "balance_ris": 1,
            "role": 1,
            "verification_status": 1,
            "email_verified": 1,
            "is_online": 1,
            "last_seen": 1,
            "created_at": 1,
            "registration_method": 1
        }
    ).sort("created_at", -1).to_list(1000)
    
    # Update online status based on last_seen
    for user in users:
        last_seen = user.get("last_seen")
        if last_seen:
            if isinstance(last_seen, datetime):
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                user["is_online"] = last_seen > online_threshold
            else:
                user["is_online"] = False
        else:
            user["is_online"] = False
    
    # Count stats
    total_users = len(users)
    online_users = sum(1 for u in users if u.get("is_online"))
    verified_users = sum(1 for u in users if u.get("verification_status") == "verified")
    
    return {
        "users": users,
        "stats": {
            "total": total_users,
            "online": online_users,
            "verified": verified_users
        }
    }

# =======================
# PASSWORD/SECURITY ROUTES
# =======================

@api_router.post("/auth/set-password")
async def set_password(request: SetPasswordRequest, current_user: User = Depends(get_current_user)):
    """Set password for user after Google login (first time)"""
    
    # Check if passwords match
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    # Validate password
    is_valid, message = validate_password(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Check if user already has password
    user = await db.users.find_one({"user_id": current_user.user_id})
    if user.get('password_set'):
        raise HTTPException(status_code=400, detail="Ya tienes una contraseña configurada. Usa 'cambiar contraseña' si deseas modificarla.")
    
    # Hash and save password
    hashed = hash_password(request.password)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "password_hash": hashed,
            "password_set": True,
            "password_changed_at": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"Password set for user {current_user.user_id}")
    return {"message": "Contraseña configurada exitosamente"}

@api_router.post("/auth/register")
async def register_user(request: RegisterUserRequest):
    """Step 1: Register user and send verification code to email"""
    
    # Validate email format
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, request.email):
        raise HTTPException(status_code=400, detail="Email inválido")
    
    email_lower = request.email.lower().strip()
    
    # Check if email already exists and is verified
    existing_user = await db.users.find_one({"email": email_lower})
    if existing_user:
        if existing_user.get("email_verified", False):
            raise HTTPException(status_code=400, detail="Este email ya está registrado. Intenta iniciar sesión.")
        else:
            # Delete unverified user to allow re-registration
            await db.users.delete_one({"email": email_lower})
            await db.pending_verifications.delete_many({"email": email_lower})
    
    # Validate passwords match
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    # Validate password strength
    is_valid, message = validate_password(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Validate name
    if not request.name or len(request.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="El nombre debe tener al menos 2 caracteres")
    
    # Generate 6-digit verification code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # Store pending registration
    pending_data = {
        "email": email_lower,
        "name": request.name.strip(),
        "phone": request.phone.strip() if request.phone else None,
        "password_hash": hash_password(request.password),
        "verification_code": verification_code,
        "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        "created_at": datetime.now(timezone.utc),
        "attempts": 0
    }
    
    # Remove any existing pending verification for this email
    await db.pending_verifications.delete_many({"email": email_lower})
    await db.pending_verifications.insert_one(pending_data)
    
    # Send verification code via SMS
    logger.info(f"📧 Verification code for {email_lower}: {verification_code}")
    
    # Send SMS if phone provided
    sms_sent = False
    if request.phone:
        sms_sent = await send_verification_sms(request.phone.strip(), verification_code, request.name.strip())
        if sms_sent:
            logger.info(f"📱 SMS verification code sent to {request.phone}")
        else:
            logger.warning(f"⚠️ SMS could not be sent, code logged above")
    
    return {
        "message": "Código de verificación enviado" + (" por SMS" if sms_sent else ". Revisa los logs."),
        "email": email_lower,
        "sms_sent": sms_sent,
        "code_expires_in_minutes": 15
    }
    
    logger.info(f"Registration initiated for {email_lower}, verification code sent")
    
    return {
        "message": "Código de verificación enviado a tu email",
        "email": email_lower,
        "code_expires_in_minutes": 15
    }

@api_router.post("/auth/verify-email")
async def verify_email_code(request: VerifyEmailCodeRequest):
    """Step 2: Verify email code and complete registration"""
    
    email_lower = request.email.lower().strip()
    
    # Find pending verification
    pending = await db.pending_verifications.find_one({"email": email_lower})
    
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación pendiente para este email. Regístrate nuevamente.")
    
    # Check if code expired
    if datetime.now(timezone.utc) > pending["code_expires_at"].replace(tzinfo=timezone.utc):
        await db.pending_verifications.delete_one({"email": email_lower})
        raise HTTPException(status_code=400, detail="El código ha expirado. Solicita uno nuevo.")
    
    # Check attempts
    if pending.get("attempts", 0) >= 5:
        await db.pending_verifications.delete_one({"email": email_lower})
        raise HTTPException(status_code=400, detail="Demasiados intentos fallidos. Regístrate nuevamente.")
    
    # Verify code
    if pending["verification_code"] != request.code.strip():
        # Increment attempts
        await db.pending_verifications.update_one(
            {"email": email_lower},
            {"$inc": {"attempts": 1}}
        )
        remaining = 5 - (pending.get("attempts", 0) + 1)
        raise HTTPException(status_code=400, detail=f"Código incorrecto. Te quedan {remaining} intentos.")
    
    # Code is correct - create the user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    new_user = {
        "user_id": user_id,
        "email": email_lower,
        "name": pending["name"],
        "phone": pending.get("phone"),
        "picture": None,
        "balance_ris": 0.0,
        "password_hash": pending["password_hash"],
        "password_set": True,
        "password_changed_at": datetime.now(timezone.utc),
        "role": "user",
        "permissions": [],
        "verification_status": "pending",  # KYC status
        "email_verified": True,  # Email is now verified
        "email_verified_at": datetime.now(timezone.utc),
        "accepted_policies": False,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "registration_method": "email"
    }
    
    await db.users.insert_one(new_user)
    
    # Delete pending verification
    await db.pending_verifications.delete_one({"email": email_lower})
    
    # Create session automatically after registration
    session_token = secrets.token_urlsafe(32)
    session_data = {
        "user_id": user_id,
        "session_token": session_token,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "login_method": "registration"
    }
    await db.user_sessions.insert_one(session_data)
    
    logger.info(f"✅ User registered successfully: {email_lower}")
    
    return {
        "message": "¡Registro completado exitosamente!",
        "session_token": session_token,
        "user": {
            "user_id": user_id,
            "email": email_lower,
            "name": pending["name"],
            "picture": None,
            "balance_ris": 0.0,
            "verification_status": "pending",
            "role": "user",
            "password_set": True,
            "email_verified": True
        }
    }

@api_router.post("/auth/resend-verification-code")
async def resend_verification_code(request: ResendVerificationCodeRequest):
    """Resend verification code via SMS"""
    
    email_lower = request.email.lower().strip()
    
    # Find pending verification
    pending = await db.pending_verifications.find_one({"email": email_lower})
    
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación pendiente para este email. Regístrate nuevamente.")
    
    # Generate new code
    new_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # Update pending verification
    await db.pending_verifications.update_one(
        {"email": email_lower},
        {"$set": {
            "verification_code": new_code,
            "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "attempts": 0
        }}
    )
    
    logger.info(f"📧 New verification code for {email_lower}: {new_code}")
    
    # Send SMS if phone is available
    sms_sent = False
    if pending.get("phone"):
        sms_sent = await send_verification_sms(pending["phone"], new_code, pending.get("name", "Usuario"))
    
    return {
        "message": "Nuevo código enviado" + (" por SMS" if sms_sent else ""),
        "sms_sent": sms_sent,
        "code_expires_in_minutes": 15
    }

@api_router.post("/auth/login-password")
async def login_with_password(request: LoginWithPasswordRequest):
    """Login with email and password"""
    
    # Find user by email
    user = await db.users.find_one({"email": request.email.lower()})
    if not user:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    
    # Check if account is locked
    if user.get('locked_until'):
        lock_time = user['locked_until']
        if lock_time.tzinfo is None:
            lock_time = lock_time.replace(tzinfo=timezone.utc)
        if lock_time > datetime.now(timezone.utc):
            remaining = int((lock_time - datetime.now(timezone.utc)).total_seconds() / 60)
            raise HTTPException(status_code=423, detail=f"Cuenta bloqueada. Intenta en {remaining} minutos.")
    
    # Check if user has password set
    if not user.get('password_set') or not user.get('password_hash'):
        raise HTTPException(status_code=400, detail="No tienes contraseña configurada. Inicia sesión con Google primero.")
    
    # Verify password
    if not verify_password(request.password, user['password_hash']):
        # Increment failed attempts
        failed_attempts = user.get('failed_login_attempts', 0) + 1
        update_data = {"failed_login_attempts": failed_attempts}
        
        # Lock account after 5 failed attempts for 15 minutes
        if failed_attempts >= 5:
            update_data['locked_until'] = datetime.now(timezone.utc) + timedelta(minutes=15)
            await db.users.update_one({"email": request.email.lower()}, {"$set": update_data})
            raise HTTPException(status_code=423, detail="Cuenta bloqueada por múltiples intentos fallidos. Intenta en 15 minutos.")
        
        await db.users.update_one({"email": request.email.lower()}, {"$set": update_data})
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    
    # Invalidate all previous sessions for this user (single session policy)
    await db.user_sessions.delete_many({"user_id": user['user_id']})
    
    # Reset failed attempts and create new session
    session_token = secrets.token_urlsafe(32)
    session_data = {
        "user_id": user['user_id'],
        "session_token": session_token,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "login_method": "password"
    }
    await db.user_sessions.insert_one(session_data)
    
    # Update user
    await db.users.update_one(
        {"email": request.email.lower()},
        {"$set": {
            "failed_login_attempts": 0,
            "locked_until": None,
            "last_login": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"User {user['user_id']} logged in with password")
    
    return {
        "message": "Login exitoso",
        "session_token": session_token,
        "user": {
            "user_id": user['user_id'],
            "email": user['email'],
            "name": user['name'],
            "picture": user.get('picture'),
            "balance_ris": user.get('balance_ris', 0),
            "verification_status": user.get('verification_status', 'pending'),
            "role": user.get('role', 'user'),
            "password_set": True
        }
    }

@api_router.post("/auth/request-password-reset")
async def request_password_reset(request: RequestPasswordResetRequest):
    """Request password reset - sends temp password via email/notification"""
    
    user = await db.users.find_one({"email": request.email.lower()})
    if not user:
        # Don't reveal if email exists for security
        return {"message": "Si el email existe, recibirás un código de recuperación."}
    
    # Generate temporary password
    temp_password = generate_temp_password()
    
    # Hash the temp password and save
    await db.users.update_one(
        {"email": request.email.lower()},
        {"$set": {
            "password_reset_token": hash_password(temp_password),
            "password_reset_expires": datetime.now(timezone.utc) + timedelta(minutes=15)
        }}
    )
    
    # Send email
    await send_password_reset_email(request.email, temp_password)
    
    return {"message": "Si el email existe, recibirás un código de recuperación."}

@api_router.post("/auth/verify-reset-token")
async def verify_reset_token(email: str, token: str):
    """Verify reset token is valid"""
    user = await db.users.find_one({"email": email.lower()})
    if not user:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    if not user.get('password_reset_token') or not user.get('password_reset_expires'):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    # Check expiration
    expires = user['password_reset_expires']
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Código expirado. Solicita uno nuevo.")
    
    # Verify token
    if not verify_password(token, user['password_reset_token']):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    return {"valid": True, "message": "Código válido"}

@api_router.post("/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using temp token"""
    
    # Verify token first
    user = await db.users.find_one({"email": request.email.lower()})
    if not user:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    if not user.get('password_reset_token') or not user.get('password_reset_expires'):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    # Check expiration
    expires = user['password_reset_expires']
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Código expirado. Solicita uno nuevo.")
    
    # Verify token
    if not verify_password(request.reset_token, user['password_reset_token']):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    
    # Validate new password
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Update password
    hashed = hash_password(request.new_password)
    await db.users.update_one(
        {"email": request.email.lower()},
        {"$set": {
            "password_hash": hashed,
            "password_set": True,
            "password_changed_at": datetime.now(timezone.utc),
            "password_reset_token": None,
            "password_reset_expires": None,
            "failed_login_attempts": 0,
            "locked_until": None
        }}
    )
    
    # Invalidate all sessions
    await db.user_sessions.delete_many({"user_id": user['user_id']})
    
    logger.info(f"Password reset for user {user['user_id']}")
    return {"message": "Contraseña actualizada exitosamente. Por favor inicia sesión."}

@api_router.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user)):
    """Change password - requires current password and live selfie"""
    
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    # Verify current password
    if not user.get('password_hash') or not verify_password(request.current_password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")
    
    # Validate new password
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas nuevas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Check that current and new password are different
    if request.current_password == request.new_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser diferente a la actual")
    
    # Verify selfie is provided (liveness check would be done on frontend)
    if not request.selfie_image or not request.selfie_image.startswith('data:image'):
        raise HTTPException(status_code=400, detail="Se requiere una selfie en vivo para cambiar la contraseña")
    
    # Save selfie as verification record
    verification_record = {
        "user_id": current_user.user_id,
        "type": "password_change",
        "selfie_image": request.selfie_image,
        "timestamp": datetime.now(timezone.utc),
        "ip_address": None  # Could be added from request
    }
    await db.security_verifications.insert_one(verification_record)
    
    # Update password
    hashed = hash_password(request.new_password)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "password_hash": hashed,
            "password_changed_at": datetime.now(timezone.utc)
        }}
    )
    
    # Invalidate all other sessions except current
    current_session = await db.user_sessions.find_one({"user_id": current_user.user_id})
    if current_session:
        await db.user_sessions.delete_many({
            "user_id": current_user.user_id,
            "_id": {"$ne": current_session['_id']}
        })
    
    logger.info(f"Password changed for user {current_user.user_id}")
    return {"message": "Contraseña cambiada exitosamente"}

@api_router.get("/auth/password-status")
async def get_password_status(current_user: User = Depends(get_current_user)):
    """Check if user has password set"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    return {
        "password_set": user.get('password_set', False),
        "password_changed_at": user.get('password_changed_at')
    }

# =======================
# POLICIES ROUTES
# =======================

CURRENT_POLICIES_VERSION = "1.0"

@api_router.get("/policies")
async def get_policies():
    """Get current policies text and version"""
    policies_path = Path(__file__).parent / 'policies' / 'POLITICAS_RIS.md'
    
    if policies_path.exists():
        with open(policies_path, 'r', encoding='utf-8') as f:
            policies_text = f.read()
    else:
        policies_text = "Políticas no disponibles"
    
    return {
        "version": CURRENT_POLICIES_VERSION,
        "content": policies_text,
        "last_updated": "2026-01-24"
    }

@api_router.post("/policies/accept")
async def accept_policies(request: Request, current_user: User = Depends(get_current_user)):
    """Accept policies - required before using the app"""
    try:
        # Get client IP
        forwarded_for = request.headers.get('X-Forwarded-For')
        client_ip = forwarded_for.split(',')[0] if forwarded_for else request.client.host
        
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {
                "accepted_policies": True,
                "policies_version": CURRENT_POLICIES_VERSION,
                "policies_accepted_at": datetime.now(timezone.utc),
                "policies_ip_address": client_ip
            }}
        )
        
        logger.info(f"User {current_user.user_id} accepted policies v{CURRENT_POLICIES_VERSION} from IP {client_ip}")
        
        return {
            "message": "Políticas aceptadas exitosamente",
            "version": CURRENT_POLICIES_VERSION,
            "accepted_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error accepting policies: {e}")
        raise HTTPException(status_code=500, detail="Error al aceptar las políticas")

@api_router.get("/policies/status")
async def get_policies_status(current_user: User = Depends(get_current_user)):
    """Check if user has accepted current policies"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    accepted = user.get('accepted_policies', False)
    user_version = user.get('policies_version')
    needs_update = user_version != CURRENT_POLICIES_VERSION if accepted else True
    
    return {
        "accepted": accepted,
        "user_version": user_version,
        "current_version": CURRENT_POLICIES_VERSION,
        "needs_acceptance": not accepted or needs_update,
        "accepted_at": user.get('policies_accepted_at')
    }

# =======================
# VERIFICATION/KYC ROUTES
# =======================

@api_router.post("/verification/submit")
async def submit_verification(request: VerificationRequest, current_user: User = Depends(get_current_user)):
    """Submit documents for verification"""
    # Update user with verification data
    # The selfie becomes the user's profile picture (cannot be changed later)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "full_name": request.full_name,
            "document_number": request.document_number,
            "cpf_number": request.cpf_number,
            "id_document_image": request.id_document_image,
            "cpf_image": request.cpf_image,
            "selfie_image": request.selfie_image,
            "picture": request.selfie_image,  # Selfie becomes permanent profile picture
            "picture_locked": True,  # Mark picture as locked/unchangeable
            "verification_status": "pending",
            "verification_submitted_at": datetime.now(timezone.utc),
            "accepted_declaration": True,
            "declaration_accepted_at": datetime.now(timezone.utc)
        }}
    )
    
    # Create notification for all admins about new verification
    admins = await db.users.find({"role": {"$in": ["admin", "super_admin"]}}).to_list(100)
    for admin in admins:
        admin_notification = {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": admin["user_id"],
            "title": "🆕 Nueva Verificación KYC",
            "message": f"{request.full_name} ha enviado documentos para verificación. Requiere revisión urgente.",
            "type": "kyc_pending",
            "priority": "high",
            "data": {
                "target_user_id": current_user.user_id,
                "user_name": request.full_name,
                "user_email": current_user.email
            },
            "read": False,
            "created_at": datetime.now(timezone.utc)
        }
        await db.notifications.insert_one(admin_notification)
        
        # Send push notification to admin
        if admin.get("fcm_token"):
            try:
                await send_push_notification(
                    admin["fcm_token"],
                    "🆕 Nueva Verificación KYC",
                    f"{request.full_name} necesita verificación urgente"
                )
            except Exception as e:
                logger.error(f"Error sending push to admin: {e}")
    
    # Create notification for user
    user_notification = {
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "title": "📄 Documentación Enviada",
        "message": "Tu documentación ha sido enviada exitosamente. Recibirás una respuesta en minutos.",
        "type": "verification_submitted",
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    await db.notifications.insert_one(user_notification)
    
    logger.info(f"Verification submitted by {current_user.user_id}, admins notified")
    
    return {"message": "Verificación enviada exitosamente. Recibirás una respuesta pronto."}

@api_router.get("/verification/status")
async def get_verification_status(current_user: User = Depends(get_current_user)):
    """Get current verification status"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    # Check if documents were submitted
    documents_submitted = user.get("verification_submitted_at") is not None or user.get("id_document_image") is not None
    
    return {
        "status": current_user.verification_status,
        "rejection_reason": current_user.rejection_reason,
        "documents_submitted": documents_submitted
    }

@api_router.get("/admin/verifications/pending")
async def get_pending_verifications(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all pending verifications with full data"""
    users = await db.users.find(
        {"verification_status": "pending", "id_document_image": {"$ne": None}},
        {
            "_id": 0,
            "user_id": 1,
            "name": 1,
            "email": 1,
            "full_name": 1,
            "document_number": 1,
            "cpf_number": 1,
            "id_document_image": 1,
            "cpf_image": 1,
            "selfie_image": 1,
            "created_at": 1,
            "verification_submitted_at": 1
        }
    ).sort("verification_submitted_at", -1).to_list(1000)
    return users

@api_router.post("/admin/verifications/decide")
async def decide_verification(decision: VerificationDecision, admin_user: User = Depends(get_admin_user)):
    """Admin: Approve or reject verification"""
    update_data = {
        "verification_status": "verified" if decision.approved else "rejected",
        "verified_at": datetime.now(timezone.utc) if decision.approved else None,
        "verified_by": admin_user.user_id if decision.approved else None,
        "rejection_reason": decision.rejection_reason if not decision.approved else None
    }
    
    result = await db.users.update_one(
        {"user_id": decision.user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user info for notification
    user = await db.users.find_one({"user_id": decision.user_id})
    
    # Send notification to user about verification result
    if decision.approved:
        notification = {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": decision.user_id,
            "title": "✅ ¡Cuenta Verificada!",
            "message": "Felicidades! Tu cuenta ha sido verificada exitosamente. Ya puedes realizar todas las operaciones.",
            "type": "verification_approved",
            "priority": "high",
            "read": False,
            "created_at": datetime.now(timezone.utc)
        }
    else:
        notification = {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": decision.user_id,
            "title": "❌ Verificación Rechazada",
            "message": f"Tu verificación fue rechazada. Motivo: {decision.rejection_reason or 'Documentos no válidos'}. Por favor, vuelve a enviar los documentos.",
            "type": "verification_rejected",
            "priority": "high",
            "read": False,
            "created_at": datetime.now(timezone.utc)
        }
    
    await db.notifications.insert_one(notification)
    
    # Send push notification to user
    if user and user.get("fcm_token"):
        try:
            title = "✅ ¡Cuenta Verificada!" if decision.approved else "❌ Verificación Rechazada"
            message = "Ya puedes operar" if decision.approved else "Revisa tus documentos"
            await send_push_notification(user["fcm_token"], title, message)
        except Exception as e:
            logger.error(f"Error sending push to user: {e}")
    
    logger.info(f"Verification {'approved' if decision.approved else 'rejected'} for user {decision.user_id} by admin {admin_user.user_id}")
    
    return {"message": f"Usuario {'aprobado' if decision.approved else 'rechazado'} exitosamente"}

# =======================
# USER ROUTES
# =======================

@api_router.get("/user/balance")
async def get_balance(current_user: User = Depends(get_current_user)):
    return {"balance_ris": current_user.balance_ris}

# =======================
# EXCHANGE RATE ROUTES
# =======================

@api_router.get("/rate")
async def get_rate():
    """Get current RIS to VES exchange rate"""
    rate_doc = await db.exchange_rates.find_one({}, {"_id": 0})
    if not rate_doc:
        # Create default rate
        default_rate = ExchangeRate()
        await db.exchange_rates.insert_one(default_rate.dict())
        return default_rate
    return ExchangeRate(**rate_doc)

@api_router.post("/rate")
async def update_rate(request: UpdateRateRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Update exchange rate"""
    new_rate = ExchangeRate(
        ris_to_ves=request.ris_to_ves,
        updated_by=admin_user.user_id
    )
    await db.exchange_rates.delete_many({})
    await db.exchange_rates.insert_one(new_rate.dict())
    return new_rate

# =======================
# BENEFICIARY ROUTES
# =======================

@api_router.post("/beneficiaries")
async def create_beneficiary(beneficiary: BeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Save a new beneficiary"""
    new_beneficiary = Beneficiary(
        user_id=current_user.user_id,
        **beneficiary.dict()
    )
    await db.beneficiaries.insert_one(new_beneficiary.dict())
    return new_beneficiary

@api_router.get("/beneficiaries")
async def get_beneficiaries(current_user: User = Depends(get_current_user)):
    """Get all beneficiaries for current user"""
    beneficiaries = await db.beneficiaries.find(
        {"user_id": current_user.user_id},
        {"_id": 0}
    ).to_list(1000)
    return [Beneficiary(**b) for b in beneficiaries]

@api_router.delete("/beneficiaries/{beneficiary_id}")
async def delete_beneficiary(beneficiary_id: str, current_user: User = Depends(get_current_user)):
    """Delete a beneficiary"""
    result = await db.beneficiaries.delete_one({
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return {"message": "Beneficiary deleted"}

# =======================
# STRIPE/RECHARGE ROUTES (DISABLED - Using Mercado Pago PIX)
# =======================

# Stripe integration is temporarily disabled
# Payment will be processed via Mercado Pago PIX
# See /pix/create endpoint below

# =======================
# WITHDRAWAL ROUTES
# =======================

@api_router.post("/withdrawal/create")
async def create_withdrawal(request: WithdrawalRequest, current_user: User = Depends(get_current_user)):
    """Create withdrawal request (RIS -> VES)"""
    # Get current rate
    rate_doc = await db.exchange_rates.find_one({}, {"_id": 0})
    if not rate_doc:
        rate = 78.0
    else:
        rate = rate_doc["ris_to_ves"]
    
    # Check if user has enough balance
    if current_user.balance_ris < request.amount_ris:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Calculate VES amount
    amount_ves = request.amount_ris * rate
    
    # Create transaction
    transaction = Transaction(
        user_id=current_user.user_id,
        type="withdrawal",
        status="pending",
        amount_input=request.amount_ris,
        amount_output=amount_ves,
        beneficiary_data=request.beneficiary_data
    )
    await db.transactions.insert_one(transaction.dict())
    
    # Immediately deduct RIS from balance
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$inc": {"balance_ris": -request.amount_ris}}
    )
    
    # Send WhatsApp notification to team with transaction ID
    try:
        # Get bank code if available
        bank_code = request.beneficiary_data.get('bank_code', '')
        bank_name = request.beneficiary_data.get('bank', '')
        bank_info = f"{bank_code} - {bank_name}" if bank_code else bank_name
        
        # Enhanced message with clear instructions and bank code for easy payment
        message = f"""🔔 *NUEVO RETIRO PENDIENTE*

💰 Monto: {request.amount_ris:.2f} RIS → {amount_ves:.2f} VES
👤 Usuario: {current_user.name}
📧 Email: {current_user.email}

📋 *DATOS PARA TRANSFERENCIA:*
🏦 Banco: {bank_info}
💳 Cuenta: {request.beneficiary_data.get('account_number')}
👤 Titular: {request.beneficiary_data.get('full_name')}
🆔 Cédula: {request.beneficiary_data.get('id_document')}
📱 Teléfono: {request.beneficiary_data.get('phone_number')}

🔢 ID Transacción: {transaction.transaction_id}

---
✅ Responde con foto del comprobante para completar"""

        from twilio.rest import Client
        twilio_client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        
        twilio_client.messages.create(
            from_=os.getenv('TWILIO_WHATSAPP_FROM'),
            body=message,
            to=os.getenv('TWILIO_WHATSAPP_TO')
        )
    except Exception as e:
        logger.error(f"WhatsApp notification error: {e}")
    
    return transaction

@api_router.get("/withdrawal/pending")
async def get_pending_withdrawals(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all pending withdrawals"""
    withdrawals = await db.transactions.find(
        {"type": "withdrawal", "status": "pending"},
        {"_id": 0}
    ).to_list(1000)
    return [Transaction(**w) for w in withdrawals]

@api_router.post("/withdrawal/process")
async def process_withdrawal(request: ProcessWithdrawalRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Mark withdrawal as completed and upload proof"""
    # Update transaction
    result = await db.transactions.update_one(
        {"transaction_id": request.transaction_id},
        {"$set": {
            "status": "completed",
            "proof_image": request.proof_image,
            "processed_by": admin_user.user_id,
            "completed_at": datetime.now(timezone.utc)
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # TODO: Send push notification to user
    
    return {"message": "Withdrawal processed successfully"}

# =======================
# PIX RECHARGE ROUTES
# =======================

class PixRechargeRequest(BaseModel):
    amount: float
    cpf: str

@api_router.post("/pix/create")
async def create_pix_payment(request: PixRechargeRequest, current_user: User = Depends(get_current_user)):
    """Create a PIX payment for recharging RIS balance"""
    
    # Validate amount (min 10, max 2000 BRL)
    if request.amount < 10:
        raise HTTPException(status_code=400, detail="El monto mínimo es R$ 10,00")
    if request.amount > 2000:
        raise HTTPException(status_code=400, detail="El monto máximo por transacción es R$ 2.000,00")
    
    # Check verification status
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Debes completar la verificación de tu cuenta primero")
    
    # Check for consecutive payments with the same amount
    last_pending_recharge = await db.transactions.find_one(
        {
            "user_id": current_user.user_id,
            "type": "recharge",
            "status": "pending",
            "amount_input": request.amount
        },
        sort=[("created_at", -1)]
    )
    
    if last_pending_recharge:
        raise HTTPException(
            status_code=400, 
            detail=f"Ya tienes una recarga pendiente de R$ {request.amount:.2f}. Completa o cancela esa transacción primero, o elige un monto diferente."
        )
    
    # Generate unique transaction ID
    transaction_id = str(uuid.uuid4())
    
    # Get user name parts
    name_parts = current_user.name.split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else first_name
    
    # Create PIX payment with Mercado Pago
    pix_result = mercadopago_service.create_pix_payment(
        amount=request.amount,
        description=f"Recarga RIS - {request.amount} BRL",
        payer_email=current_user.email,
        payer_first_name=first_name,
        payer_last_name=last_name,
        payer_cpf=request.cpf,
        external_reference=transaction_id
    )
    
    if not pix_result or not pix_result.get("success"):
        error_msg = pix_result.get("error", "Error al crear el pago PIX") if pix_result else "Error al crear el pago PIX"
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Save pending transaction to database
    transaction_data = {
        "transaction_id": transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge",
        "payment_method": "pix",
        "status": "pending",
        "amount_input": request.amount,  # BRL
        "amount_output": request.amount,  # RIS (1:1)
        "mercadopago_payment_id": pix_result.get("payment_id"),
        "pix_qr_code": pix_result.get("qr_code"),
        "pix_qr_code_base64": pix_result.get("qr_code_base64"),
        "pix_expiration": pix_result.get("expiration"),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(transaction_data)
    
    logger.info(f"PIX payment created for user {current_user.user_id}: {transaction_id}")
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "payment_id": pix_result.get("payment_id"),
        "qr_code": pix_result.get("qr_code"),
        "qr_code_base64": pix_result.get("qr_code_base64"),
        "expiration": pix_result.get("expiration"),
        "amount_brl": request.amount,
        "amount_ris": request.amount
    }

@api_router.get("/pix/status/{transaction_id}")
async def get_pix_status(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Check PIX payment status"""
    
    # Find transaction
    transaction = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "user_id": current_user.user_id
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    # If already completed, return status
    if transaction.get("status") == "completed":
        return {
            "status": "completed",
            "amount_ris": transaction.get("amount_output"),
            "completed_at": transaction.get("completed_at")
        }
    
    # Check with Mercado Pago
    payment_id = transaction.get("mercadopago_payment_id")
    if payment_id:
        payment_status = mercadopago_service.get_payment_status(payment_id)
        
        if payment_status and payment_status.get("status") == "approved":
            # Payment approved - credit user's balance
            amount_ris = transaction.get("amount_output", 0)
            
            # Update user balance
            await db.users.update_one(
                {"user_id": current_user.user_id},
                {"$inc": {"balance_ris": amount_ris}}
            )
            
            # Update transaction status
            await db.transactions.update_one(
                {"transaction_id": transaction_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            
            logger.info(f"PIX payment completed for user {current_user.user_id}: +{amount_ris} RIS")
            
            return {
                "status": "completed",
                "amount_ris": amount_ris,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        
        return {
            "status": payment_status.get("status", "pending") if payment_status else "pending",
            "status_detail": payment_status.get("status_detail") if payment_status else None
        }
    
    return {"status": "pending"}

# =======================
# PIX VERIFICATION WITH PROOF
# =======================

class PixVerifyWithProofRequest(BaseModel):
    transaction_id: str
    proof_image: str  # base64

@api_router.post("/pix/verify-with-proof")
async def verify_pix_with_proof(request: PixVerifyWithProofRequest, current_user: User = Depends(get_current_user)):
    """Verify PIX payment manually with proof of payment image"""
    
    # Find transaction
    transaction = await db.transactions.find_one({
        "transaction_id": request.transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge",
        "status": "pending"
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    # First, check with Mercado Pago if payment is already approved
    payment_id = transaction.get("mercadopago_payment_id")
    is_auto_approved = False
    
    if payment_id:
        payment_status = mercadopago_service.get_payment_status(payment_id)
        if payment_status and payment_status.get("status") == "approved":
            is_auto_approved = True
    
    amount_ris = transaction.get("amount_output", 0)
    
    if is_auto_approved:
        # Payment already approved by Mercado Pago - complete immediately
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": amount_ris}}
        )
        
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "proof_image": request.proof_image,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "verification_method": "auto_mercadopago_with_proof"
            }}
        )
        
        logger.info(f"PIX payment auto-completed with proof for user {current_user.user_id}: +{amount_ris} RIS")
        
        return {
            "status": "completed",
            "amount_ris": amount_ris,
            "message": "Pago confirmado y saldo acreditado"
        }
    else:
        # Payment not yet confirmed by Mercado Pago - set to pending_review for admin verification
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "pending_review",
                "proof_image": request.proof_image,
                "updated_at": datetime.now(timezone.utc),
                "verification_method": "manual_proof"
            }}
        )
        
        # Create notification for user
        await create_notification(
            user_id=current_user.user_id,
            title="📝 Comprobante Recibido",
            message=f"Tu comprobante de R$ {transaction.get('amount_input', 0):.2f} está siendo verificado. Te notificaremos cuando se confirme.",
            notification_type="recharge_pending_review",
            data={"transaction_id": request.transaction_id}
        )
        
        logger.info(f"PIX payment pending review for user {current_user.user_id}: {request.transaction_id}")
        
        return {
            "status": "pending_review",
            "message": "Comprobante enviado. Será revisado y recibirás una notificación cuando se confirme."
        }

@api_router.post("/pix/cancel/{transaction_id}")
async def cancel_pix_payment(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Cancel a pending PIX payment that was not completed"""
    
    # Find the pending transaction
    transaction = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge",
        "status": {"$in": ["pending", "pending_review"]}
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o no se puede cancelar")
    
    # Check if already completed
    if transaction.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Esta transacción ya fue completada y no se puede cancelar")
    
    # Update transaction status to cancelled
    await db.transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc),
            "cancelled_by": "user",
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"PIX payment cancelled by user {current_user.user_id}: {transaction_id}")
    
    return {
        "status": "cancelled",
        "message": "La recarga ha sido cancelada correctamente",
        "transaction_id": transaction_id
    }

@api_router.get("/transaction/{transaction_id}/proof")
async def get_transaction_proof(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get the proof image for a specific transaction"""
    
    transaction = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "user_id": current_user.user_id
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    proof_image = transaction.get("proof_image")
    
    if not proof_image:
        raise HTTPException(status_code=404, detail="Esta transacción no tiene comprobante")
    
    return {
        "transaction_id": transaction_id,
        "proof_image": proof_image,
        "status": transaction.get("status"),
        "amount_input": transaction.get("amount_input"),
        "amount_output": transaction.get("amount_output"),
        "completed_at": transaction.get("completed_at")
    }

@api_router.post("/webhooks/mercadopago")
async def mercadopago_webhook(request: Request):
    """Webhook to receive Mercado Pago payment notifications"""
    try:
        data = await request.json()
        
        logger.info(f"Mercado Pago webhook received: {data}")
        
        # Handle payment notification
        if data.get("type") == "payment":
            payment_id = data.get("data", {}).get("id")
            
            if payment_id:
                # Get payment details
                payment_status = mercadopago_service.get_payment_status(payment_id)
                
                if payment_status and payment_status.get("status") == "approved":
                    external_reference = payment_status.get("external_reference")
                    
                    if external_reference:
                        # Find and update transaction
                        transaction = await db.transactions.find_one({
                            "transaction_id": external_reference,
                            "status": "pending"
                        })
                        
                        if transaction:
                            amount_ris = transaction.get("amount_output", 0)
                            user_id = transaction.get("user_id")
                            
                            # Update user balance
                            await db.users.update_one(
                                {"user_id": user_id},
                                {"$inc": {"balance_ris": amount_ris}}
                            )
                            
                            # Update transaction status
                            await db.transactions.update_one(
                                {"transaction_id": external_reference},
                                {"$set": {
                                    "status": "completed",
                                    "completed_at": datetime.now(timezone.utc),
                                    "updated_at": datetime.now(timezone.utc)
                                }}
                            )
                            
                            logger.info(f"PIX payment auto-completed via webhook: {external_reference}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing Mercado Pago webhook: {e}")
        return {"status": "error"}

# =======================
# SUPPORT CHAT
# =======================

class SupportMessageRequest(BaseModel):
    message: str
    image: Optional[str] = None  # base64 image

@api_router.post("/support/send")
async def send_support_message(request: SupportMessageRequest, current_user: User = Depends(get_current_user)):
    """Send a support message to admin via WhatsApp"""
    
    if not request.message and not request.image:
        raise HTTPException(status_code=400, detail="Debes enviar un mensaje o una imagen")
    
    if request.message and len(request.message) > 500:
        raise HTTPException(status_code=400, detail="El mensaje es demasiado largo (máximo 500 caracteres)")
    
    try:
        from twilio.rest import Client
        twilio_client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        
        # Format message for admin
        message_text = request.message.strip() if request.message else "[Imagen adjunta]"
        
        support_message = f"""📩 *MENSAJE DE SOPORTE*

👤 *Usuario:* {current_user.name}
📧 *Email:* {current_user.email}
🆔 *ID:* {current_user.user_id}

💬 *Mensaje:*
{message_text}

---
Responde a este mensaje para contactar al usuario."""

        # If there's an image, we need to upload it and send as media
        if request.image:
            # Save image temporarily and get URL
            import base64
            import tempfile
            import os as os_module
            
            # Extract base64 data
            if ',' in request.image:
                image_data = request.image.split(',')[1]
            else:
                image_data = request.image
            
            # Decode and save to temp file
            image_bytes = base64.b64decode(image_data)
            
            # Save to a publicly accessible location or use a service
            # For now, we'll save it and note in the message
            # In production, you'd upload to S3/CloudStorage and get a URL
            
            # Save support message with image to database first
            support_record = {
                "user_id": current_user.user_id,
                "user_name": current_user.name,
                "user_email": current_user.email,
                "message": message_text,
                "image": request.image,  # Store full base64
                "sent_via": "whatsapp",
                "created_at": datetime.now(timezone.utc)
            }
            result = await db.support_messages.insert_one(support_record)
            
            # Send text message to WhatsApp (image notification)
            support_message_with_image = f"""📩 *MENSAJE DE SOPORTE* 📷

👤 *Usuario:* {current_user.name}
📧 *Email:* {current_user.email}
🆔 *ID:* {current_user.user_id}

💬 *Mensaje:*
{message_text}

📷 *Imagen adjunta* - Ver en panel admin o base de datos
ID Mensaje: {str(result.inserted_id)}

---
Responde a este mensaje para contactar al usuario."""
            
            twilio_client.messages.create(
                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                body=support_message_with_image,
                to=os.getenv('TWILIO_WHATSAPP_TO')
            )
        else:
            # No image, just text
            twilio_client.messages.create(
                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                body=support_message,
                to=os.getenv('TWILIO_WHATSAPP_TO')
            )
            
            # Save support message to database
            support_record = {
                "user_id": current_user.user_id,
                "user_name": current_user.name,
                "user_email": current_user.email,
                "message": message_text,
                "sent_via": "whatsapp",
                "created_at": datetime.now(timezone.utc)
            }
            await db.support_messages.insert_one(support_record)
        
        logger.info(f"Support message sent from {current_user.email}" + (" with image" if request.image else ""))
        
        return {"status": "success", "message": "Mensaje enviado correctamente"}
        
    except Exception as e:
        logger.error(f"Error sending support message: {e}")
        raise HTTPException(status_code=500, detail="No se pudo enviar el mensaje. Intenta de nuevo.")

@api_router.get("/support/history")
async def get_support_history(current_user: User = Depends(get_current_user)):
    """Get user's support message history"""
    messages = await db.support_messages.find(
        {"user_id": current_user.user_id}
    ).sort("created_at", -1).to_list(50)
    
    for m in messages:
        m['_id'] = str(m['_id'])
    
    return messages

@api_router.get("/support/conversation")
async def get_support_conversation(current_user: User = Depends(get_current_user)):
    """Get full support conversation (user messages + admin responses)"""
    
    # Get user's sent messages
    user_messages = await db.support_messages.find(
        {"user_id": current_user.user_id}
    ).to_list(100)
    
    # Get admin responses to this user
    admin_responses = await db.support_responses.find(
        {"user_id": current_user.user_id}
    ).to_list(100)
    
    # Combine and format messages
    conversation = []
    
    for msg in user_messages:
        conversation.append({
            "id": str(msg['_id']),
            "text": msg.get('message', ''),
            "image": msg.get('image'),  # Include image if present
            "sender": "user",
            "timestamp": msg.get('created_at').isoformat() if msg.get('created_at') else None
        })
    
    for resp in admin_responses:
        conversation.append({
            "id": str(resp['_id']),
            "text": resp.get('message', ''),
            "sender": "admin",
            "timestamp": resp.get('created_at').isoformat() if resp.get('created_at') else None
        })
    
    # Sort by timestamp
    conversation.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '')
    
    return conversation

# =======================
# IN-APP NOTIFICATIONS
# =======================

@api_router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user)):
    """Get user's notifications"""
    notifications = await db.notifications.find(
        {"user_id": current_user.user_id}
    ).sort("created_at", -1).limit(50).to_list(50)
    
    for n in notifications:
        n['_id'] = str(n['_id'])
    
    return {"notifications": notifications}

@api_router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications"""
    count = await db.notifications.count_documents({
        "user_id": current_user.user_id,
        "read": False
    })
    return {"count": count}

@api_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: User = Depends(get_current_user)):
    """Mark notification as read"""
    from bson import ObjectId
    await db.notifications.update_one(
        {"_id": ObjectId(notification_id), "user_id": current_user.user_id},
        {"$set": {"read": True}}
    )
    return {"message": "Notification marked as read"}

@api_router.post("/notifications/read-all")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    await db.notifications.update_many(
        {"user_id": current_user.user_id, "read": False},
        {"$set": {"read": True}}
    )
    return {"message": "All notifications marked as read"}

async def create_notification(user_id: str, title: str, message: str, notification_type: str, data: dict = None):
    """Helper function to create a notification"""
    notification = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    await db.notifications.insert_one(notification)
    logger.info(f"Notification created for user {user_id}: {title}")

# =======================
# TRANSACTION ROUTES
# =======================

@api_router.get("/transactions")
async def get_transactions(type: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Get user transactions (optional filter by type: 'recharge' or 'withdrawal')"""
    query = {"user_id": current_user.user_id}
    if type:
        query["type"] = type
    
    transactions = await db.transactions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Transaction(**t) for t in transactions]

@api_router.get("/transactions/export")
async def export_transactions(admin_user: User = Depends(get_admin_user)):
    """Admin: Export all transactions to Excel"""
    transactions = await db.transactions.find({}, {"_id": 0}).to_list(10000)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ["Transaction ID", "User ID", "Type", "Status", "Amount Input", "Amount Output", 
               "Created At", "Completed At", "Beneficiary"]
    ws.append(headers)
    
    # Data
    for t in transactions:
        beneficiary_name = ""
        if t.get("beneficiary_data"):
            beneficiary_name = t["beneficiary_data"].get("full_name", "")
        
        ws.append([
            t.get("transaction_id", ""),
            t.get("user_id", ""),
            t.get("type", ""),
            t.get("status", ""),
            t.get("amount_input", 0),
            t.get("amount_output", 0),
            str(t.get("created_at", "")),
            str(t.get("completed_at", "")),
            beneficiary_name
        ])
    
    # Save to bytes
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"}
    )

# =======================
# ADMIN RECORDS & MANUAL APPROVAL
# =======================

@api_router.get("/admin/payment-records")
async def get_admin_payment_records(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all payment records with proof images"""
    records = await db.admin_payment_records.find(
        {},
        {"proof_image": 0}  # Exclude large base64 images from list view
    ).sort("recorded_at", -1).to_list(1000)
    
    for r in records:
        r['_id'] = str(r['_id'])
    
    return {"records": records}

@api_router.get("/admin/payment-records/{record_id}")
async def get_admin_payment_record_detail(record_id: str, admin_user: User = Depends(get_admin_user)):
    """Admin: Get a specific payment record with full details including proof image"""
    from bson import ObjectId
    
    record = await db.admin_payment_records.find_one({"_id": ObjectId(record_id)})
    
    if not record:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    
    record['_id'] = str(record['_id'])
    return record

@api_router.get("/admin/pending-recharges")
async def get_pending_recharges(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all recharges pending review (with uploaded proof)"""
    recharges = await db.transactions.find(
        {"type": "recharge", "status": "pending_review"},
        {"proof_image": 0}  # Exclude large base64 images from list view
    ).sort("created_at", -1).to_list(1000)
    
    # Get user info for each recharge
    result = []
    for r in recharges:
        user = await db.users.find_one({"user_id": r.get("user_id")})
        r['_id'] = str(r['_id'])
        r['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        r['user_email'] = user.get('email', 'N/A') if user else 'N/A'
        result.append(r)
    
    return {"recharges": result}

@api_router.get("/admin/recharge/{transaction_id}/proof")
async def get_recharge_proof(transaction_id: str, admin_user: User = Depends(get_admin_user)):
    """Admin: Get proof image for a specific recharge"""
    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    return {
        "transaction_id": transaction_id,
        "proof_image": transaction.get("proof_image"),
        "amount_input": transaction.get("amount_input"),
        "status": transaction.get("status")
    }

class ApproveRechargeRequest(BaseModel):
    transaction_id: str
    approved: bool
    rejection_reason: Optional[str] = None

@api_router.post("/admin/recharge/approve")
async def approve_recharge(request: ApproveRechargeRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Approve or reject a recharge with uploaded proof"""
    
    transaction = await db.transactions.find_one({
        "transaction_id": request.transaction_id,
        "status": "pending_review"
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    user_id = transaction.get("user_id")
    amount_ris = transaction.get("amount_output", 0)
    
    if request.approved:
        # Credit user's balance
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"balance_ris": amount_ris}}
        )
        
        # Update transaction status
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "approved_by": admin_user.user_id,
                "verification_method": "admin_manual_approval"
            }}
        )
        
        # Save admin record
        user = await db.users.find_one({"user_id": user_id})
        admin_record = {
            "record_type": "recharge_approved",
            "transaction_id": request.transaction_id,
            "user_id": user_id,
            "user_name": user.get('name', 'N/A') if user else 'N/A',
            "user_email": user.get('email', 'N/A') if user else 'N/A',
            "amount_brl": transaction.get("amount_input", 0),
            "amount_ris": amount_ris,
            "proof_image": transaction.get("proof_image"),
            "approved_by": admin_user.user_id,
            "approved_by_email": admin_user.email,
            "processed_via": "admin_panel",
            "created_at": transaction.get("created_at"),
            "completed_at": datetime.now(timezone.utc),
            "recorded_at": datetime.now(timezone.utc)
        }
        
        await db.admin_payment_records.insert_one(admin_record)
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga Confirmada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue confirmada. +{amount_ris:.2f} RIS agregados a tu cuenta.",
            notification_type="recharge_completed",
            data={"transaction_id": request.transaction_id, "amount_ris": amount_ris}
        )
        
        logger.info(f"Recharge {request.transaction_id} approved by admin {admin_user.email}")
        return {"message": "Recarga aprobada y saldo acreditado", "status": "completed"}
    else:
        # Reject recharge
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "rejected",
                "updated_at": datetime.now(timezone.utc),
                "rejected_by": admin_user.user_id,
                "rejection_reason": request.rejection_reason or "Comprobante inválido"
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga Rechazada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue rechazada. Razón: {request.rejection_reason or 'Comprobante inválido'}",
            notification_type="recharge_rejected",
            data={"transaction_id": request.transaction_id}
        )
        
        logger.info(f"Recharge {request.transaction_id} rejected by admin {admin_user.email}")
        return {"message": "Recarga rechazada", "status": "rejected"}

# =======================
# TWILIO WHATSAPP WEBHOOK
# =======================

@api_router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(request: Request):
    """Webhook to receive WhatsApp messages from Twilio"""
    try:
        form_data = await request.form()
        
        # Extract message data
        from_number = form_data.get('From', '')
        body = form_data.get('Body', '')
        num_media = int(form_data.get('NumMedia', 0))
        message_sid = form_data.get('MessageSid', '')
        
        logger.info(f"=== WEBHOOK WHATSAPP RECIBIDO ===")
        logger.info(f"From: {from_number}")
        logger.info(f"Body: {body}")
        logger.info(f"NumMedia: {num_media}")
        
        # Check if message has media (image)
        if num_media > 0:
            media_url = form_data.get('MediaUrl0', '')
            media_content_type = form_data.get('MediaContentType0', '')
            
            logger.info(f"Media URL: {media_url}")
            logger.info(f"Media Type: {media_content_type}")
            
            # Download the image
            if media_url and 'image' in media_content_type:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    # Twilio requires authentication to download media
                    auth = (
                        os.getenv('TWILIO_ACCOUNT_SID'),
                        os.getenv('TWILIO_AUTH_TOKEN')
                    )
                    response = await client.get(media_url, auth=auth)
                    
                    logger.info(f"Media download status: {response.status_code}")
                    
                    if response.status_code == 200:
                        # Convert to base64
                        import base64
                        image_base64 = f"data:{media_content_type};base64,{base64.b64encode(response.content).decode()}"
                        
                        logger.info("Imagen descargada y convertida a base64")
                        
                        # Extract transaction ID from message body
                        transaction_id = None
                        if body:
                            import re
                            # Try to find transaction_id (UUID format) or MongoDB ObjectId
                            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', body, re.IGNORECASE)
                            if uuid_match:
                                # Search by transaction_id field
                                tx = await db.transactions.find_one({"transaction_id": uuid_match.group(1), "status": "pending"})
                                if tx:
                                    transaction_id = str(tx['_id'])
                                    logger.info(f"Transaction found by UUID: {transaction_id}")
                            
                            if not transaction_id:
                                # Try ObjectId format
                                oid_match = re.search(r'ID[:\s]*([a-f0-9]{24})', body, re.IGNORECASE)
                                if oid_match:
                                    transaction_id = oid_match.group(1)
                                    logger.info(f"Transaction ID from ObjectId: {transaction_id}")
                        
                        # If no ID in current message, find the most recent pending transaction
                        if not transaction_id:
                            logger.info("No ID encontrado en mensaje, buscando retiro pendiente más reciente...")
                            recent_withdrawal = await db.transactions.find_one(
                                {"type": "withdrawal", "status": "pending"},
                                sort=[("created_at", -1)]
                            )
                            if recent_withdrawal:
                                transaction_id = str(recent_withdrawal['_id'])
                                logger.info(f"Retiro pendiente encontrado: {transaction_id}")
                        
                        if transaction_id:
                            from bson import ObjectId
                            
                            # Get transaction before update to have all data
                            tx_before = await db.transactions.find_one({"_id": ObjectId(transaction_id)})
                            
                            if not tx_before:
                                logger.error(f"Transacción no encontrada: {transaction_id}")
                                return {"status": "error", "message": "Transaction not found"}
                            
                            if tx_before.get('status') != 'pending':
                                logger.warning(f"Transacción ya procesada: {transaction_id}")
                                # Still send confirmation
                                from twilio.rest import Client
                                twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                                twilio_client.messages.create(
                                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                    body=f"⚠️ Esta transacción ya fue procesada anteriormente.\nID: {tx_before.get('transaction_id', transaction_id)}",
                                    to=from_number
                                )
                                return {"status": "already_processed"}
                            
                            # Update transaction
                            result = await db.transactions.update_one(
                                {"_id": ObjectId(transaction_id), "status": "pending"},
                                {"$set": {
                                    "status": "completed",
                                    "proof_image": image_base64,
                                    "completed_at": datetime.now(timezone.utc),
                                    "updated_at": datetime.now(timezone.utc),
                                    "processed_via": "whatsapp"
                                }}
                            )
                            
                            logger.info(f"Update result: modified_count={result.modified_count}")
                            
                            if result.modified_count > 0:
                                # Get full transaction data
                                completed_tx = await db.transactions.find_one({"_id": ObjectId(transaction_id)})
                                user_id = completed_tx.get('user_id')
                                tx_id = completed_tx.get('transaction_id', transaction_id)
                                
                                # Get user info
                                user = await db.users.find_one({"user_id": user_id})
                                
                                beneficiary = completed_tx.get('beneficiary_data', {})
                                amount_ris = completed_tx.get('amount_input', 0)
                                amount_ves = completed_tx.get('amount_output', 0)
                                
                                logger.info(f"Transacción completada: {tx_id}")
                                logger.info(f"Usuario: {user_id}, Monto: {amount_ris} RIS -> {amount_ves} VES")
                                
                                # ============================
                                # SAVE ADMIN RECORD
                                # ============================
                                admin_record = {
                                    "record_type": "withdrawal_completed",
                                    "transaction_id": tx_id,
                                    "mongo_id": transaction_id,
                                    "user_id": user_id,
                                    "user_name": user.get('name', 'N/A') if user else 'N/A',
                                    "user_email": user.get('email', 'N/A') if user else 'N/A',
                                    "amount_ris": amount_ris,
                                    "amount_ves": amount_ves,
                                    "beneficiary": {
                                        "full_name": beneficiary.get('full_name', 'N/A'),
                                        "bank": beneficiary.get('bank', 'N/A'),
                                        "bank_code": beneficiary.get('bank_code', 'N/A'),
                                        "account_number": beneficiary.get('account_number', 'N/A'),
                                        "id_document": beneficiary.get('id_document', 'N/A'),
                                        "phone_number": beneficiary.get('phone_number', 'N/A')
                                    },
                                    "proof_image": image_base64,
                                    "processed_via": "whatsapp",
                                    "processed_by_phone": from_number,
                                    "whatsapp_message_sid": message_sid,
                                    "created_at": completed_tx.get('created_at'),
                                    "completed_at": datetime.now(timezone.utc),
                                    "recorded_at": datetime.now(timezone.utc)
                                }
                                
                                await db.admin_payment_records.insert_one(admin_record)
                                logger.info(f"Registro admin guardado para TX: {tx_id}")
                                
                                # ============================
                                # CREATE IN-APP NOTIFICATION
                                # ============================
                                await create_notification(
                                    user_id=user_id,
                                    title="✅ Retiro Completado",
                                    message=f"Tu retiro de {amount_ris:.2f} RIS ({amount_ves:.2f} VES) a {beneficiary.get('full_name', 'beneficiario')} fue procesado exitosamente. ID: {tx_id[:8]}...",
                                    notification_type="withdrawal_completed",
                                    data={
                                        "transaction_id": tx_id,
                                        "amount_ris": amount_ris,
                                        "amount_ves": amount_ves
                                    }
                                )
                                logger.info(f"Notificación in-app creada para usuario {user_id}")
                                
                                # Try push notification
                                if user and user.get('fcm_token'):
                                    try:
                                        from push_service import push_service
                                        await push_service.send_withdrawal_completed_notification(
                                            push_token=user['fcm_token'],
                                            transaction_id=tx_id,
                                            amount_ris=amount_ris,
                                            amount_ves=amount_ves,
                                            beneficiary_name=beneficiary.get('full_name', 'Beneficiario')
                                        )
                                        logger.info("Push notification enviada")
                                    except Exception as e:
                                        logger.warning(f"Push notification falló: {e}")
                                
                                # ============================
                                # SEND WHATSAPP CONFIRMATION TO ADMIN
                                # ============================
                                from twilio.rest import Client
                                twilio_client = Client(
                                    os.getenv('TWILIO_ACCOUNT_SID'),
                                    os.getenv('TWILIO_AUTH_TOKEN')
                                )
                                
                                confirmation_msg = f"""✅ *RETIRO PROCESADO EXITOSAMENTE*

📋 *Detalles:*
🔢 ID: {tx_id}
💰 Monto: {amount_ris:.2f} RIS → {amount_ves:.2f} VES
👤 Beneficiario: {beneficiary.get('full_name', 'N/A')}
🏦 Banco: {beneficiary.get('bank_code', '')} {beneficiary.get('bank', 'N/A')}

✅ Usuario notificado
✅ Registro guardado
✅ Historial actualizado"""
                                
                                twilio_client.messages.create(
                                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                    body=confirmation_msg,
                                    to=from_number
                                )
                                logger.info("Confirmación WhatsApp enviada al admin")
                                
                                return {"status": "success", "transaction_id": tx_id}
                            else:
                                logger.warning(f"No se pudo actualizar transacción: {transaction_id}")
                        else:
                            logger.warning("No se encontró ninguna transacción pendiente")
                            # Notify admin
                            from twilio.rest import Client
                            twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                            twilio_client.messages.create(
                                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                body="⚠️ No se encontró ninguna transacción pendiente para procesar.",
                                to=from_number
                            )
                    else:
                        logger.error(f"Error descargando imagen: {response.status_code}")
        else:
            # Message without image - could be a support response or command
            logger.info("Mensaje sin imagen - verificando si es respuesta de soporte o comando")
            
            if body and body.strip():
                import re
                body_lower = body.strip().lower()
                
                # Check for close/end chat commands
                close_commands = ['cerrar', '/cerrar', 'close', '/close', 'finalizar', '/finalizar', 'resolver', '/resolver']
                is_close_command = any(cmd in body_lower for cmd in close_commands)
                
                # Look for user_id pattern in the message (user_XXXX)
                user_match = re.search(r'user_([a-f0-9]+)', body, re.IGNORECASE)
                
                target_user_id = None
                response_message = body.strip()
                
                if user_match:
                    # Admin included user ID in message
                    target_user_id = f"user_{user_match.group(1)}"
                    # Remove the user ID from the message to get clean response
                    response_message = re.sub(r'user_[a-f0-9]+\s*', '', body).strip()
                    logger.info(f"User ID encontrado en mensaje: {target_user_id}")
                else:
                    # Find the most recent open support conversation
                    recent_support = await db.support_messages.find_one(
                        {"status": {"$ne": "closed"}},
                        sort=[("created_at", -1)]
                    )
                    if not recent_support:
                        # Fallback to any recent support message
                        recent_support = await db.support_messages.find_one(
                            {},
                            sort=[("created_at", -1)]
                        )
                    if recent_support:
                        target_user_id = recent_support.get('user_id')
                        logger.info(f"Respondiendo al último mensaje de soporte de: {target_user_id}")
                
                if target_user_id:
                    # Get user info
                    user = await db.users.find_one({"user_id": target_user_id})
                    
                    if user:
                        from twilio.rest import Client
                        twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                        
                        if is_close_command:
                            # Close the support conversation
                            # Mark all messages from this user as closed
                            await db.support_messages.update_many(
                                {"user_id": target_user_id},
                                {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc)}}
                            )
                            
                            # Get optional closing message (text after the command)
                            closing_message = response_message
                            for cmd in close_commands:
                                closing_message = closing_message.replace(cmd, '').strip()
                            
                            if not closing_message:
                                closing_message = "Tu caso de soporte ha sido resuelto. ¡Gracias por contactarnos!"
                            
                            # Save closing message as admin response
                            admin_response = {
                                "user_id": target_user_id,
                                "message": f"🔒 Chat cerrado: {closing_message}",
                                "sender": "admin",
                                "type": "close",
                                "from_phone": from_number,
                                "created_at": datetime.now(timezone.utc)
                            }
                            await db.support_responses.insert_one(admin_response)
                            
                            # Create notification for user
                            await create_notification(
                                user_id=target_user_id,
                                title="✅ Caso de Soporte Resuelto",
                                message=closing_message,
                                notification_type="support_closed",
                                data={"closing_message": closing_message}
                            )
                            
                            logger.info(f"Chat de soporte cerrado para {target_user_id}")
                            
                            # Confirm to admin
                            twilio_client.messages.create(
                                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                body=f"✅ Chat cerrado con {user.get('name', target_user_id)}.\nEl usuario ha sido notificado.",
                                to=from_number
                            )
                        else:
                            # Regular response (not a close command)
                            # Save the admin response
                            admin_response = {
                                "user_id": target_user_id,
                                "message": response_message,
                                "sender": "admin",
                                "from_phone": from_number,
                                "created_at": datetime.now(timezone.utc)
                            }
                            await db.support_responses.insert_one(admin_response)
                            
                            # Create notification for user
                            await create_notification(
                                user_id=target_user_id,
                                title="💬 Respuesta de Soporte",
                                message=response_message[:200] + ("..." if len(response_message) > 200 else ""),
                                notification_type="support_response",
                                data={"full_message": response_message}
                            )
                            
                            logger.info(f"Respuesta de soporte enviada a {target_user_id}")
                            
                            # Confirm to admin with available commands
                            twilio_client.messages.create(
                                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                body=f"✅ Respuesta enviada a {user.get('name', target_user_id)}\n\n💡 Comandos: cerrar, finalizar, resolver",
                                to=from_number
                            )
                    else:
                        logger.warning(f"Usuario no encontrado: {target_user_id}")
                        from twilio.rest import Client
                        twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                        twilio_client.messages.create(
                            from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                            body=f"⚠️ Usuario {target_user_id} no encontrado",
                            to=from_number
                        )
                else:
                    logger.info("No se pudo determinar el destinatario de la respuesta")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}

# =======================
# ADMIN PANEL - COMPLETE ENDPOINTS
# =======================

# --- Dashboard ---
@api_router.get("/admin/dashboard")
async def get_admin_dashboard(admin_user: User = Depends(get_admin_user)):
    """Get dashboard statistics"""
    if not has_permission(admin_user, "dashboard.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get statistics
    total_users = await db.users.count_documents({"role": {"$ne": "admin"}})
    verified_users = await db.users.count_documents({"verification_status": "verified"})
    pending_kyc = await db.users.count_documents({"verification_status": "pending", "id_document_image": {"$ne": None}})
    
    total_transactions = await db.transactions.count_documents({})
    pending_withdrawals = await db.transactions.count_documents({"type": "withdrawal", "status": "pending"})
    pending_recharges = await db.transactions.count_documents({"type": "recharge", "status": "pending_review"})
    completed_transactions = await db.transactions.count_documents({"status": "completed"})
    
    open_support = await db.support_messages.count_documents({"status": {"$ne": "closed"}})
    
    # Volume calculations
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$type", "total": {"$sum": "$amount_input"}}}
    ]
    volumes = await db.transactions.aggregate(pipeline).to_list(10)
    volume_by_type = {v["_id"]: v["total"] for v in volumes}
    
    # Get rate
    rate = await db.settings.find_one({"key": "exchange_rate"})
    current_rate = rate.get("ris_to_ves", 78) if rate else 78
    
    return {
        "users": {
            "total": total_users,
            "verified": verified_users,
            "pending_kyc": pending_kyc
        },
        "transactions": {
            "total": total_transactions,
            "completed": completed_transactions,
            "pending_withdrawals": pending_withdrawals,
            "pending_recharges": pending_recharges
        },
        "support": {
            "open_chats": open_support
        },
        "volume": {
            "withdrawals": volume_by_type.get("withdrawal", 0),
            "recharges": volume_by_type.get("recharge", 0)
        },
        "current_rate": current_rate
    }

# --- Sub-Admin Management ---
class CreateSubAdminRequest(BaseModel):
    email: str
    name: str
    permissions: List[str]

class UpdateSubAdminRequest(BaseModel):
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None

@api_router.get("/admin/permissions-list")
async def get_permissions_list(admin_user: User = Depends(get_admin_user)):
    """Get list of all available permissions"""
    return ADMIN_PERMISSIONS

@api_router.get("/admin/sub-admins")
async def get_sub_admins(admin_user: User = Depends(get_super_admin)):
    """Get all sub-administrators (super_admin only)"""
    admins = await db.users.find(
        {"role": {"$in": ["admin", "super_admin"]}},
        {"id_document_image": 0, "cpf_image": 0, "selfie_image": 0}
    ).to_list(100)
    
    for a in admins:
        a['_id'] = str(a['_id'])
    
    return admins

@api_router.post("/admin/sub-admins")
async def create_sub_admin(request: CreateSubAdminRequest, admin_user: User = Depends(get_super_admin)):
    """Create a new sub-administrator (super_admin only)"""
    
    # Check if user already exists
    existing = await db.users.find_one({"email": request.email})
    
    if existing:
        # Update existing user to admin
        await db.users.update_one(
            {"email": request.email},
            {"$set": {
                "role": "admin",
                "permissions": request.permissions,
                "created_by_admin": admin_user.user_id,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        return {"message": f"Usuario {request.email} promovido a admin", "user_id": existing.get('user_id')}
    else:
        # Create new admin user
        new_admin = {
            "user_id": f"admin_{uuid.uuid4().hex[:12]}",
            "email": request.email,
            "name": request.name,
            "role": "admin",
            "permissions": request.permissions,
            "is_active": True,
            "balance_ris": 0,
            "verification_status": "verified",  # Admins don't need KYC
            "created_by_admin": admin_user.user_id,
            "created_at": datetime.now(timezone.utc)
        }
        await db.users.insert_one(new_admin)
        return {"message": f"Admin {request.email} creado", "user_id": new_admin['user_id']}

@api_router.put("/admin/sub-admins/{user_id}")
async def update_sub_admin(user_id: str, request: UpdateSubAdminRequest, admin_user: User = Depends(get_super_admin)):
    """Update a sub-administrator (super_admin only)"""
    
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    
    if target.get('role') == 'super_admin' and admin_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="No puedes modificar a otro super_admin")
    
    update_data = {"updated_at": datetime.now(timezone.utc)}
    if request.permissions is not None:
        update_data["permissions"] = request.permissions
    if request.is_active is not None:
        update_data["is_active"] = request.is_active
    if request.name is not None:
        update_data["name"] = request.name
    
    await db.users.update_one({"user_id": user_id}, {"$set": update_data})
    return {"message": "Admin actualizado"}

@api_router.delete("/admin/sub-admins/{user_id}")
async def delete_sub_admin(user_id: str, admin_user: User = Depends(get_super_admin)):
    """Remove admin role from user (super_admin only)"""
    
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    
    if target.get('role') == 'super_admin':
        raise HTTPException(status_code=403, detail="No puedes eliminar a un super_admin")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": "user", "permissions": []}}
    )
    return {"message": "Rol de admin removido"}

# --- Users Management ---
@api_router.get("/admin/users")
async def get_all_users(
    admin_user: User = Depends(get_admin_user),
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all users with pagination"""
    if not has_permission(admin_user, "users.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {"role": {"$in": ["user", None]}}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    if status:
        query["verification_status"] = status
    
    users = await db.users.find(
        query,
        {"id_document_image": 0, "cpf_image": 0, "selfie_image": 0}
    ).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    total = await db.users.count_documents(query)
    
    for u in users:
        u['_id'] = str(u['_id'])
    
    return {"users": users, "total": total}

@api_router.get("/admin/users/{user_id}")
async def get_user_detail(user_id: str, admin_user: User = Depends(get_admin_user)):
    """Get detailed user info including KYC documents"""
    if not has_permission(admin_user, "users.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user['_id'] = str(user['_id'])
    
    # Get user's transaction history summary
    tx_count = await db.transactions.count_documents({"user_id": user_id})
    tx_volume = await db.transactions.aggregate([
        {"$match": {"user_id": user_id, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_input"}}}
    ]).to_list(1)
    
    user['transaction_count'] = tx_count
    user['transaction_volume'] = tx_volume[0]['total'] if tx_volume else 0
    
    return user

@api_router.get("/admin/users/{user_id}/complete")
async def get_user_complete_info(user_id: str, admin_user: User = Depends(get_admin_user)):
    """
    Super Admin: Get COMPLETE user information including:
    - Full profile data
    - Registration date and method
    - KYC documents and status
    - All transactions (recharges and withdrawals)
    - All beneficiaries
    - Account activity (logins, last seen)
    - Balance history
    """
    if not has_permission(admin_user, "users.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get user with all fields (except password hash)
    user = await db.users.find_one(
        {"user_id": user_id},
        {"password_hash": 0, "password_reset_token": 0}
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user['_id'] = str(user['_id'])
    
    # ========== TRANSACTIONS ==========
    # Get ALL transactions for this user
    all_transactions = await db.transactions.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    
    # Separate by type
    recharges = [tx for tx in all_transactions if tx.get('type') == 'recharge']
    withdrawals = [tx for tx in all_transactions if tx.get('type') == 'withdrawal']
    
    # Calculate stats
    completed_recharges = [tx for tx in recharges if tx.get('status') == 'completed']
    completed_withdrawals = [tx for tx in withdrawals if tx.get('status') == 'completed']
    pending_recharges = [tx for tx in recharges if tx.get('status') == 'pending']
    pending_withdrawals = [tx for tx in withdrawals if tx.get('status') == 'pending']
    
    total_recharged = sum(tx.get('amount_output', 0) for tx in completed_recharges)
    total_withdrawn = sum(tx.get('amount_input', 0) for tx in completed_withdrawals)
    total_ves_sent = sum(tx.get('amount_output', 0) for tx in completed_withdrawals)
    
    # ========== BENEFICIARIES ==========
    beneficiaries = await db.beneficiaries.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # ========== NOTIFICATIONS ==========
    notifications = await db.notifications.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    
    # ========== SUPPORT MESSAGES ==========
    support_messages = await db.support_messages.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # ========== ADMIN BALANCE ADJUSTMENTS ==========
    balance_adjustments = await db.admin_logs.find(
        {"user_id": user_id, "type": "admin_adjustment"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    
    # Build complete response
    return {
        # ===== PROFILE INFO =====
        "profile": {
            "user_id": user.get("user_id"),
            "email": user.get("email"),
            "name": user.get("name"),
            "full_name": user.get("full_name"),
            "phone": user.get("phone"),
            "picture": user.get("picture"),
            "role": user.get("role", "user"),
            "balance_ris": user.get("balance_ris", 0),
            "registration_method": user.get("registration_method", "google"),
            "created_at": user.get("created_at"),
            "last_login": user.get("last_login"),
            "last_seen": user.get("last_seen"),
            "is_online": user.get("is_online", False),
            "is_active": user.get("is_active", True),
        },
        
        # ===== KYC / VERIFICATION =====
        "kyc": {
            "verification_status": user.get("verification_status", "pending"),
            "email_verified": user.get("email_verified", False),
            "email_verified_at": user.get("email_verified_at"),
            "document_number": user.get("document_number"),
            "cpf_number": user.get("cpf_number"),
            "id_document_image": user.get("id_document_image"),
            "cpf_image": user.get("cpf_image"),
            "selfie_image": user.get("selfie_image"),
            "verification_submitted_at": user.get("verification_submitted_at"),
            "verified_at": user.get("verified_at"),
            "verified_by": user.get("verified_by"),
            "rejection_reason": user.get("rejection_reason"),
            "accepted_declaration": user.get("accepted_declaration", False),
            "declaration_accepted_at": user.get("declaration_accepted_at"),
            "accepted_policies": user.get("accepted_policies", False),
            "policies_accepted_at": user.get("policies_accepted_at"),
        },
        
        # ===== SECURITY =====
        "security": {
            "password_set": user.get("password_set", False),
            "password_changed_at": user.get("password_changed_at"),
            "failed_login_attempts": user.get("failed_login_attempts", 0),
            "locked_until": user.get("locked_until"),
            "fcm_token": "Configurado" if user.get("fcm_token") else "No configurado",
        },
        
        # ===== TRANSACTION STATISTICS =====
        "stats": {
            "total_transactions": len(all_transactions),
            "total_recharges": len(recharges),
            "total_withdrawals": len(withdrawals),
            "completed_recharges": len(completed_recharges),
            "completed_withdrawals": len(completed_withdrawals),
            "pending_recharges": len(pending_recharges),
            "pending_withdrawals": len(pending_withdrawals),
            "total_recharged_ris": total_recharged,
            "total_withdrawn_ris": total_withdrawn,
            "total_ves_sent": total_ves_sent,
            "total_beneficiaries": len(beneficiaries),
        },
        
        # ===== RECHARGE HISTORY =====
        "recharges": [{
            "transaction_id": tx.get("transaction_id"),
            "amount_brl": tx.get("amount_input"),
            "amount_ris": tx.get("amount_output"),
            "status": tx.get("status"),
            "payment_method": tx.get("payment_method", "pix"),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "has_proof": bool(tx.get("proof_image")),
        } for tx in recharges],
        
        # ===== WITHDRAWAL HISTORY =====
        "withdrawals": [{
            "transaction_id": tx.get("transaction_id"),
            "amount_ris": tx.get("amount_input"),
            "amount_ves": tx.get("amount_output"),
            "status": tx.get("status"),
            "beneficiary": tx.get("beneficiary_data", {}),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "processed_by": tx.get("processed_by"),
            "has_proof": bool(tx.get("proof_image")),
            "rejection_reason": tx.get("rejection_reason"),
        } for tx in withdrawals],
        
        # ===== BENEFICIARIES =====
        "beneficiaries": [{
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "bank": b.get("bank"),
            "bank_code": b.get("bank_code"),
            "account_number": b.get("account_number"),
            "id_document": b.get("id_document"),
            "phone_number": b.get("phone_number"),
            "created_at": b.get("created_at"),
        } for b in beneficiaries],
        
        # ===== RECENT NOTIFICATIONS =====
        "notifications": [{
            "notification_id": n.get("notification_id"),
            "title": n.get("title"),
            "message": n.get("message"),
            "type": n.get("type"),
            "read": n.get("read", False),
            "created_at": n.get("created_at"),
        } for n in notifications],
        
        # ===== SUPPORT HISTORY =====
        "support_messages": [{
            "message_id": m.get("message_id"),
            "sender": m.get("sender"),
            "text": m.get("text"),
            "created_at": m.get("created_at"),
        } for m in support_messages],
        
        # ===== BALANCE ADJUSTMENTS BY ADMIN =====
        "balance_adjustments": balance_adjustments,
    }

@api_router.put("/admin/users/{user_id}/balance")
async def update_user_balance(user_id: str, amount: float, admin_user: User = Depends(get_admin_user)):
    """Manually adjust user balance"""
    if not has_permission(admin_user, "users.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"balance_ris": amount}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Log the adjustment
    adjustment = {
        "type": "admin_adjustment",
        "user_id": user_id,
        "amount": amount,
        "admin_id": admin_user.user_id,
        "created_at": datetime.now(timezone.utc)
    }
    await db.admin_logs.insert_one(adjustment)
    
    return {"message": f"Balance ajustado en {amount} RIS"}

# --- Transactions ---
@api_router.get("/admin/transactions")
async def get_all_transactions(
    admin_user: User = Depends(get_admin_user),
    skip: int = 0,
    limit: int = 50,
    type: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all transactions with filters"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {}
    if type:
        query["type"] = type
    if status:
        query["status"] = status
    
    transactions = await db.transactions.find(
        query,
        {"proof_image": 0}  # Exclude large images
    ).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    total = await db.transactions.count_documents(query)
    
    # Get user info for each transaction
    for tx in transactions:
        tx['_id'] = str(tx['_id'])
        user = await db.users.find_one({"user_id": tx.get('user_id')}, {"name": 1, "email": 1})
        tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return {"transactions": transactions, "total": total}

@api_router.get("/admin/transactions/{transaction_id}")
async def get_transaction_detail(transaction_id: str, admin_user: User = Depends(get_admin_user)):
    """Get transaction detail including proof image"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    tx = await db.transactions.find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    tx['_id'] = str(tx['_id'])
    
    user = await db.users.find_one({"user_id": tx.get('user_id')}, {"name": 1, "email": 1})
    tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
    tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return tx

# --- Support Chat Management ---
@api_router.get("/admin/support/chats")
async def get_support_chats(admin_user: User = Depends(get_admin_user), status: Optional[str] = None):
    """Get all support chats"""
    if not has_permission(admin_user, "support.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get unique users with support messages
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "last_message": {"$last": "$message"},
            "last_date": {"$max": "$created_at"},
            "message_count": {"$sum": 1},
            "status": {"$last": "$status"}
        }},
        {"$sort": {"last_date": -1}}
    ]
    
    if status:
        pipeline.insert(0, {"$match": {"status": status}})
    
    chats = await db.support_messages.aggregate(pipeline).to_list(100)
    
    # Get user info for each chat
    result = []
    for chat in chats:
        user = await db.users.find_one({"user_id": chat['_id']}, {"name": 1, "email": 1})
        result.append({
            "user_id": chat['_id'],
            "user_name": user.get('name', 'N/A') if user else 'N/A',
            "user_email": user.get('email', 'N/A') if user else 'N/A',
            "last_message": chat['last_message'][:100] + "..." if len(chat.get('last_message', '')) > 100 else chat.get('last_message', ''),
            "last_date": chat['last_date'],
            "message_count": chat['message_count'],
            "status": chat.get('status', 'open')
        })
    
    return result

@api_router.get("/admin/support/chat/{user_id}")
async def get_support_chat_detail(user_id: str, admin_user: User = Depends(get_admin_user)):
    """Get full chat history with a user"""
    if not has_permission(admin_user, "support.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get user messages
    user_messages = await db.support_messages.find({"user_id": user_id}).to_list(100)
    
    # Get admin responses
    admin_responses = await db.support_responses.find({"user_id": user_id}).to_list(100)
    
    # Combine and sort
    conversation = []
    for msg in user_messages:
        conversation.append({
            "id": str(msg['_id']),
            "text": msg.get('message', ''),
            "image": msg.get('image'),
            "sender": "user",
            "timestamp": msg.get('created_at').isoformat() if msg.get('created_at') else None
        })
    
    for resp in admin_responses:
        conversation.append({
            "id": str(resp['_id']),
            "text": resp.get('message', ''),
            "sender": "admin",
            "timestamp": resp.get('created_at').isoformat() if resp.get('created_at') else None
        })
    
    conversation.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '')
    
    # Get user info
    user = await db.users.find_one({"user_id": user_id}, {"name": 1, "email": 1})
    
    return {
        "user_id": user_id,
        "user_name": user.get('name', 'N/A') if user else 'N/A',
        "user_email": user.get('email', 'N/A') if user else 'N/A',
        "messages": conversation
    }

class AdminSupportResponse(BaseModel):
    user_id: str
    message: str

@api_router.post("/admin/support/respond")
async def admin_respond_support(request: AdminSupportResponse, admin_user: User = Depends(get_admin_user)):
    """Send a response to user from admin panel"""
    if not has_permission(admin_user, "support.respond"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Save response
    admin_response = {
        "user_id": request.user_id,
        "message": request.message,
        "sender": "admin",
        "admin_id": admin_user.user_id,
        "admin_name": admin_user.name,
        "created_at": datetime.now(timezone.utc)
    }
    await db.support_responses.insert_one(admin_response)
    
    # Create notification
    await create_notification(
        user_id=request.user_id,
        title="💬 Respuesta de Soporte",
        message=request.message[:200] + ("..." if len(request.message) > 200 else ""),
        notification_type="support_response",
        data={"full_message": request.message}
    )
    
    return {"message": "Respuesta enviada"}

class CloseSupportRequest(BaseModel):
    user_id: str
    closing_message: Optional[str] = None

@api_router.post("/admin/support/close")
async def admin_close_support(request: CloseSupportRequest, admin_user: User = Depends(get_admin_user)):
    """Close a support chat from admin panel"""
    if not has_permission(admin_user, "support.close"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    closing_msg = request.closing_message or "Tu caso de soporte ha sido resuelto. ¡Gracias por contactarnos!"
    
    # Mark as closed
    await db.support_messages.update_many(
        {"user_id": request.user_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc), "closed_by": admin_user.user_id}}
    )
    
    # Save closing message
    admin_response = {
        "user_id": request.user_id,
        "message": f"🔒 Chat cerrado: {closing_msg}",
        "sender": "admin",
        "type": "close",
        "admin_id": admin_user.user_id,
        "created_at": datetime.now(timezone.utc)
    }
    await db.support_responses.insert_one(admin_response)
    
    # Notify user
    await create_notification(
        user_id=request.user_id,
        title="✅ Caso de Soporte Resuelto",
        message=closing_msg,
        notification_type="support_closed",
        data={"closing_message": closing_msg}
    )
    
    return {"message": "Chat cerrado"}

# --- Process Withdrawal from Admin Panel ---
class ProcessWithdrawalAdminRequest(BaseModel):
    transaction_id: str
    action: str  # "approve" or "reject"
    proof_image: Optional[str] = None
    rejection_reason: Optional[str] = None

@api_router.post("/admin/withdrawals/process")
async def process_withdrawal_admin(request: ProcessWithdrawalAdminRequest, admin_user: User = Depends(get_admin_user)):
    """Process withdrawal from admin panel"""
    if not has_permission(admin_user, "withdrawals.process"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    tx = await db.transactions.find_one({"transaction_id": request.transaction_id, "status": "pending"})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    if request.action == "approve":
        if not request.proof_image:
            raise HTTPException(status_code=400, detail="Se requiere imagen de comprobante")
        
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "proof_image": request.proof_image,
                "completed_at": datetime.now(timezone.utc),
                "processed_by": admin_user.user_id,
                "processed_via": "admin_panel"
            }}
        )
        
        # Notify user
        user = await db.users.find_one({"user_id": tx['user_id']})
        beneficiary = tx.get('beneficiary_data', {})
        await create_notification(
            user_id=tx['user_id'],
            title="✅ Retiro Completado",
            message=f"Tu retiro de {tx['amount_input']:.2f} RIS a {beneficiary.get('full_name', 'beneficiario')} fue procesado.",
            notification_type="withdrawal_completed",
            data={"transaction_id": request.transaction_id}
        )
        
        return {"message": "Retiro aprobado y usuario notificado"}
    
    elif request.action == "reject":
        # Return balance to user
        await db.users.update_one(
            {"user_id": tx['user_id']},
            {"$inc": {"balance_ris": tx['amount_input']}}
        )
        
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "rejected",
                "rejection_reason": request.rejection_reason or "Rechazado por administrador",
                "rejected_at": datetime.now(timezone.utc),
                "rejected_by": admin_user.user_id
            }}
        )
        
        await create_notification(
            user_id=tx['user_id'],
            title="❌ Retiro Rechazado",
            message=f"Tu retiro de {tx['amount_input']:.2f} RIS fue rechazado. {request.rejection_reason or ''}. El monto fue devuelto a tu balance.",
            notification_type="withdrawal_rejected",
            data={"transaction_id": request.transaction_id}
        )
        
        return {"message": "Retiro rechazado y balance devuelto"}
    
    raise HTTPException(status_code=400, detail="Acción inválida")

# =======================
# HEALTH CHECK
# =======================

@api_router.get("/")
async def root():
    return {"message": "RIS App API"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy"}

@api_router.post("/test-whatsapp")
async def test_whatsapp():
    """Test endpoint to send a WhatsApp message"""
    try:
        test_transaction = {
            "transaction_id": "TEST-123",
            "amount_input": 100.0,
            "amount_output": 7800.0,
            "beneficiary_data": {
                "full_name": "Test Beneficiary",
                "bank": "Banco Test",
                "account_number": "1234-5678-9012",
                "id_document": "V-12345678",
                "phone_number": "+58 412-1234567"
            }
        }
        
        test_user = {
            "name": "Test User",
            "email": "test@example.com"
        }
        
        result = await whatsapp_service.send_withdrawal_notification(
            test_transaction,
            test_user
        )
        
        if result:
            return {"status": "success", "message": "WhatsApp test message sent!"}
        else:
            return {"status": "error", "message": "Failed to send WhatsApp message"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Include the routers in the main app
app.include_router(api_router)
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()