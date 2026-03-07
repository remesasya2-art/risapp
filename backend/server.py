from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse, FileResponse
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
from web_push_service import web_push_service
import asyncio
import resend

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
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
TWILIO_WHATSAPP_TO = os.getenv('TWILIO_WHATSAPP_TO')

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Stripe configuration (disabled - using Mercado Pago PIX)
# stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_placeholder')

# Resend Email Configuration
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'noreply@risappbr.com')

# Initialize Resend
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

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

async def send_whatsapp_notification(message_body: str) -> bool:
    """Send WhatsApp notification to admin using Twilio"""
    if not twilio_client or not TWILIO_WHATSAPP_TO:
        logger.warning("Twilio WhatsApp not configured - message not sent")
        return False
    
    try:
        message = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_FROM,
            to=TWILIO_WHATSAPP_TO
        )
        
        logger.info(f"📲 WhatsApp sent - SID: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp: {e}")
        return False

async def send_next_pending_withdrawal_whatsapp():
    """
    FIFO System: Send the next pending withdrawal via WhatsApp.
    Finds the oldest pending withdrawal and sends it, marking it as active.
    """
    try:
        # First, clean up: ensure no "ghost" active withdrawals exist
        # (completed transactions that still have whatsapp_active: true)
        await db.transactions.update_many(
            {"status": {"$ne": "pending"}, "whatsapp_active": True},
            {"$set": {"whatsapp_active": False}}
        )
        
        # Get the OLDEST pending withdrawal (FIFO)
        next_withdrawal = await db.transactions.find_one(
            {"type": "withdrawal", "status": "pending"},
            sort=[("created_at", 1)]
        )
        
        if not next_withdrawal:
            logger.info("📋 FIFO: No hay retiros pendientes en cola")
            return None
        
        # Check if this withdrawal is already active
        if next_withdrawal.get('whatsapp_active', False):
            logger.info(f"📋 FIFO: El retiro {next_withdrawal.get('display_id', next_withdrawal.get('transaction_id'))} ya está activo")
            return None
        
        # Get user info
        user = await db.users.find_one({"user_id": next_withdrawal['user_id']})
        if not user:
            logger.error(f"Usuario no encontrado para retiro: {next_withdrawal.get('transaction_id')}")
            return None
        
        beneficiary = next_withdrawal.get('beneficiary_data', {})
        full_name = beneficiary.get('full_name', 'N/A')
        id_document = beneficiary.get('id_document', 'N/A')
        amount_ves = next_withdrawal.get('amount_output', 0)
        display_id = next_withdrawal.get('display_id', next_withdrawal.get('transaction_id', 'N/A')[:8])
        payment_type = beneficiary.get('payment_type', 'transferencia')
        
        # Build WhatsApp message based on payment type
        if payment_type == 'pago_movil':
            bank_code = beneficiary.get('bank_code', '') or beneficiary.get('bank', '')
            phone_number = beneficiary.get('phone_number', 'N/A')
            message = f"""{full_name}
{bank_code}
{id_document}
{phone_number}
{amount_ves:.2f} Bs

📱 PAGO MÓVIL
👤 Usuario: {user.get('name', 'N/A')}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""
        else:
            account_number = beneficiary.get('account_number', 'N/A')
            bank_name = beneficiary.get('bank', '')
            message = f"""{full_name}
{account_number}
{id_document}
{amount_ves:.2f} Bs

🏦 TRANSFERENCIA ({bank_name})
👤 Usuario: {user.get('name', 'N/A')}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""
        
        # Send WhatsApp
        whatsapp_sent = await send_whatsapp_notification(message)
        
        if whatsapp_sent:
            # Mark as active in WhatsApp
            await db.transactions.update_one(
                {"_id": next_withdrawal['_id']},
                {"$set": {
                    "whatsapp_active": True,
                    "whatsapp_notified": True,
                    "whatsapp_notified_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"📋 FIFO: Retiro enviado a WhatsApp - ID: {display_id}")
            return display_id
        else:
            logger.error("📋 FIFO: Error enviando mensaje WhatsApp")
            return None
        
    except Exception as e:
        logger.error(f"Error en FIFO WhatsApp: {e}")
        import traceback
        traceback.print_exc()
        return None

async def send_verification_email(email: str, code: str, name: str) -> bool:
    """Send verification code via email using Resend"""
    if not RESEND_API_KEY:
        logger.warning("Resend not configured - email not sent")
        return False
    
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8f9fc;">
            <div style="background-color: #ffffff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #6366f1; margin: 0; font-size: 28px;">RIS App</h1>
                    <p style="color: #9ca3af; margin: 5px 0 0 0;">Tu billetera digital</p>
                </div>
                
                <h2 style="color: #111827; margin-bottom: 20px;">¡Hola {name}!</h2>
                
                <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                    Tu código de verificación es:
                </p>
                
                <div style="background-color: #f3f4f6; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 36px; font-weight: bold; color: #6366f1; letter-spacing: 8px;">{code}</span>
                </div>
                
                <p style="color: #6b7280; font-size: 14px; line-height: 1.6;">
                    Este código expira en <strong>15 minutos</strong>.
                </p>
                
                <p style="color: #6b7280; font-size: 14px; line-height: 1.6;">
                    Si no solicitaste este código, puedes ignorar este mensaje.
                </p>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #9ca3af; font-size: 12px; text-align: center;">
                    © 2026 RIS App - Remesas Internacionales Seguras
                </p>
            </div>
        </body>
        </html>
        """
        
        params = {
            "from": SENDER_EMAIL,
            "to": [email],
            "subject": f"🔐 RIS App - Tu código de verificación: {code}",
            "html": html_content
        }
        
        # Run sync SDK in thread to keep FastAPI non-blocking
        email_response = await asyncio.to_thread(resend.Emails.send, params)
        
        logger.info(f"📧 Email sent to {email} - ID: {email_response.get('id')}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email via Resend: {e}")
        return False

async def send_push_notification(push_token: str, title: str, body: str, data: dict = None) -> bool:
    """Send push notification using Expo Push API or Firebase FCM"""
    if not push_token:
        logger.warning("⚠️ No push token provided")
        return False
    
    logger.info(f"🔔 Enviando push notification...")
    logger.info(f"   Token: {push_token[:40]}...")
    logger.info(f"   Title: {title}")
    logger.info(f"   Body: {body}")
    
    # Detectar tipo de token
    is_expo_token = push_token.startswith('ExponentPushToken')
    is_fcm_token = not is_expo_token and len(push_token) > 100  # FCM tokens son largos
    
    logger.info(f"   Tipo de token: {'Expo' if is_expo_token else 'FCM' if is_fcm_token else 'Desconocido'}")
    
    if not is_expo_token and is_fcm_token:
        # Token de FCM - intentar usar Firebase Admin SDK
        logger.warning("⚠️ Token de FCM detectado. Se requiere Firebase Admin SDK para enviar.")
        logger.warning("⚠️ El usuario necesita volver a abrir la app para registrar un token de Expo válido.")
        return False
    
    try:
        # Expo Push API endpoint
        expo_push_url = "https://exp.host/--/api/v2/push/send"
        
        message = {
            "to": push_token,
            "sound": "default",
            "title": title,
            "body": body,
            "priority": "high",
        }
        
        if data:
            message["data"] = data
        
        logger.info(f"📤 Enviando a Expo Push API...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                expo_push_url,
                json=message,
                headers={
                    "Accept": "application/json",
                    "Accept-encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                }
            )
            
            result = response.json()
            logger.info(f"📥 Respuesta de Expo Push API: status={response.status_code}, result={result}")
            
            if response.status_code == 200:
                # Verificar si hay errores en la respuesta
                if isinstance(result, dict) and result.get("data"):
                    ticket = result["data"]
                    if isinstance(ticket, list) and len(ticket) > 0:
                        ticket = ticket[0]
                    if ticket.get("status") == "error":
                        error_type = ticket.get("details", {}).get("error", "")
                        if error_type == "DeviceNotRegistered":
                            logger.error(f"❌ Token inválido o dispositivo no registrado")
                        else:
                            logger.error(f"❌ Error en ticket: {ticket.get('message')} - {ticket.get('details')}")
                        return False
                    elif ticket.get("status") == "ok":
                        logger.info(f"✅ Push notification enviada exitosamente. Ticket ID: {ticket.get('id')}")
                        return True
                
                logger.info(f"✅ Push notification enviada (status 200)")
                return True
            else:
                logger.error(f"❌ Push notification failed: {result}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error sending push notification: {e}")
        return False

async def send_push_to_user(user_id: str, title: str, body: str, data: dict = None) -> bool:
    """Send push notification to a specific user by user_id"""
    user = await db.users.find_one({"user_id": user_id}, {"fcm_token": 1})
    if user and user.get("fcm_token"):
        return await send_push_notification(user["fcm_token"], title, body, data)
    return False

async def send_push_to_admins(title: str, body: str, data: dict = None) -> int:
    """Send push notification to all admins with FCM tokens"""
    sent_count = 0
    admins = await db.users.find(
        {"role": {"$in": ["admin", "super_admin"]}, "fcm_token": {"$exists": True, "$ne": None}},
        {"fcm_token": 1}
    ).to_list(100)
    
    for admin in admins:
        if admin.get("fcm_token"):
            success = await send_push_notification(admin["fcm_token"], title, body, data)
            if success:
                sent_count += 1
    
    return sent_count

# =======================
# REFERRAL BONUS SYSTEM
# =======================

async def get_next_withdrawal_id() -> str:
    """Generate next incremental withdrawal ID (000001, 000002, etc.)"""
    counter = await db.counters.find_one_and_update(
        {"_id": "withdrawal_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    return str(counter["seq"]).zfill(6)  # Format as 000001, 000002, etc.

async def process_referral_bonus(user_id: str, recharge_amount: float):
    """
    Process referral bonuses when a user recharges.
    - If user was referred and total reaches 100 RI$: Pay 5 RI$ bonus to partner
    - After milestone: Pay 1% commission on each recharge
    """
    try:
        # Get the user
        user = await db.users.find_one({"user_id": user_id})
        if not user or not user.get("referred_by"):
            return  # User was not referred
        
        partner_id = user.get("referred_by")
        partner = await db.users.find_one({"user_id": partner_id, "role": "socio"})
        if not partner:
            return  # Partner no longer exists or is not a socio
        
        # Update user's total recharged
        new_total = user.get("total_recharged", 0) + recharge_amount
        bonus_already_paid = user.get("referral_bonus_paid", False)
        
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"total_recharged": new_total}}
        )
        
        # Check if milestone reached (100 RI$) and bonus not yet paid
        if not bonus_already_paid and new_total >= 100:
            # Pay 5 RI$ bonus to partner
            await db.users.update_one(
                {"user_id": partner_id},
                {"$inc": {"balance_ris": 5.0}}
            )
            
            # Mark bonus as paid
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"referral_bonus_paid": True}}
            )
            
            # Record the bonus transaction
            bonus_record = {
                "record_id": f"ref_bonus_{uuid.uuid4().hex[:12]}",
                "type": "referral_milestone_bonus",
                "partner_id": partner_id,
                "partner_name": partner.get("name", ""),
                "referred_user_id": user_id,
                "referred_user_name": user.get("name", ""),
                "amount": 5.0,
                "milestone_reached": 100.0,
                "created_at": datetime.now(timezone.utc)
            }
            await db.referral_earnings.insert_one(bonus_record)
            
            # Notify partner
            await create_notification(
                user_id=partner_id,
                title="🎉 ¡Bono de Referido!",
                message=f"Tu referido {user.get('name', 'Usuario')} alcanzó 100 RI$ en recargas. ¡Ganaste 5 RI$ de bonificación!",
                notification_type="referral_bonus",
                data={"bonus_amount": 5.0, "referred_user": user.get("name", "")}
            )
            
            logger.info(f"✅ Referral milestone bonus paid: 5 RI$ to {partner_id} for user {user_id}")
        
        # If milestone already reached, pay 1% commission
        elif bonus_already_paid:
            commission = recharge_amount * 0.01  # 1%
            if commission > 0:
                await db.users.update_one(
                    {"user_id": partner_id},
                    {"$inc": {"balance_ris": commission}}
                )
                
                # Record the commission
                commission_record = {
                    "record_id": f"ref_comm_{uuid.uuid4().hex[:12]}",
                    "type": "referral_commission",
                    "partner_id": partner_id,
                    "partner_name": partner.get("name", ""),
                    "referred_user_id": user_id,
                    "referred_user_name": user.get("name", ""),
                    "recharge_amount": recharge_amount,
                    "commission_rate": 0.01,
                    "amount": commission,
                    "created_at": datetime.now(timezone.utc)
                }
                await db.referral_earnings.insert_one(commission_record)
                
                logger.info(f"✅ Referral commission paid: {commission:.2f} RI$ to {partner_id} for recharge of {recharge_amount} RI$")
    
    except Exception as e:
        logger.error(f"Error processing referral bonus: {e}")
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
    ris_to_ves: float = 92.0        # 1 RIS = 92 VES (para enviar a Venezuela)
    ves_to_ris: float = 102.0       # 102 VES = 1 RIS (para recargar con Bolívares)
    ris_to_brl: float = 1.0         # 1 RIS = 1 BRL (para enviar a Brasil)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = None

# Bank info for VES payments
class VESPaymentInfo(BaseModel):
    bank_name: str = "Banco de Venezuela"
    bank_code: str = "0102"
    account_holder: str = "RIS REMESAS C.A."
    account_number: str = "01020123456789012345"
    account_type: str = "Corriente"
    phone_number: str = "04121234567"
    id_document: str = "J-12345678-9"

class Beneficiary(BaseModel):
    beneficiary_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    full_name: str
    payment_type: str = "transferencia"  # "pago_movil" or "transferencia"
    account_number: Optional[str] = None  # For transferencia (20 digits)
    id_document: str  # Cedula (only numbers)
    phone_number: Optional[str] = None  # For pago_movil (11 digits)
    bank: str
    bank_code: Optional[str] = None  # Venezuelan bank code (e.g., 0134)
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
    payment_type: str = "transferencia"  # "pago_movil" or "transferencia"
    account_number: Optional[str] = None  # For transferencia
    id_document: str  # Cedula
    phone_number: Optional[str] = None  # For pago_movil
    bank: str
    bank_code: Optional[str] = None

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
    referral_code: Optional[str] = None  # Código de referido opcional

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
    """Send password reset email with temporary password using Resend"""
    if not RESEND_API_KEY:
        logger.warning("Resend not configured - password reset email not sent")
        return False
    
    try:
        # Get user name
        user = await db.users.find_one({"email": email})
        user_name = user.get('name', 'Usuario') if user else 'Usuario'
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8f9fc;">
            <div style="background-color: #ffffff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #6366f1; margin: 0; font-size: 28px;">RIS App</h1>
                    <p style="color: #9ca3af; margin: 5px 0 0 0;">Recuperación de Contraseña</p>
                </div>
                
                <h2 style="color: #111827; margin-bottom: 20px;">¡Hola {user_name}!</h2>
                
                <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                    Has solicitado recuperar tu contraseña. Tu código temporal es:
                </p>
                
                <div style="background-color: #fef3c7; border: 2px solid #f59e0b; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; color: #92400e; letter-spacing: 4px;">{temp_password}</span>
                </div>
                
                <p style="color: #dc2626; font-size: 14px; line-height: 1.6; font-weight: 500;">
                    ⚠️ Este código expira en <strong>15 minutos</strong>.
                </p>
                
                <p style="color: #6b7280; font-size: 14px; line-height: 1.6;">
                    Si no solicitaste este cambio, ignora este mensaje. Tu cuenta está segura.
                </p>
                
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #9ca3af; font-size: 12px; text-align: center;">
                    © 2026 RIS App - Remesas Internacionales Seguras
                </p>
            </div>
        </body>
        </html>
        """
        
        params = {
            "from": SENDER_EMAIL,
            "to": [email],
            "subject": f"🔐 RIS App - Código de Recuperación: {temp_password}",
            "html": html_content
        }
        
        # Run sync SDK in thread to keep FastAPI non-blocking
        email_response = await asyncio.to_thread(resend.Emails.send, params)
        
        logger.info(f"🔐 Password reset email sent to {email} - ID: {email_response.get('id')}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending password reset email via Resend: {e}")
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
# DOWNLOAD BUILD ROUTE (Dev environment only)
# =======================

@api_router.get("/download-build")
async def download_build():
    """Download frontend build zip (dev environment only)"""
    build_path = Path(__file__).parent / "downloads" / "frontend_build.zip"
    if not build_path.exists():
        raise HTTPException(status_code=404, detail="Build file not found")
    return FileResponse(
        path=str(build_path),
        filename="frontend_build.zip",
        media_type="application/zip"
    )

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
        
        logger.info(f"📱 Registrando FCM token para usuario {current_user.user_id}")
        logger.info(f"   Token recibido: {fcm_token[:30] if fcm_token else 'None'}...")
        
        if not fcm_token:
            logger.warning(f"⚠️ FCM token vacío para usuario {current_user.user_id}")
            raise HTTPException(status_code=400, detail="FCM token is required")
        
        result = await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {"fcm_token": fcm_token}}
        )
        
        logger.info(f"✅ FCM token registrado para usuario {current_user.user_id}")
        logger.info(f"   Modified count: {result.modified_count}")
        return {"message": "FCM token registered successfully", "success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error registrando FCM token: {e}")
        raise HTTPException(status_code=500, detail="Error registering FCM token")

@api_router.get("/push/status")
async def get_push_status(current_user: User = Depends(get_current_user)):
    """Get push notification status for current user"""
    user = await db.users.find_one({"user_id": current_user.user_id}, {"fcm_token": 1, "email": 1})
    
    if not user:
        return {"status": "error", "message": "Usuario no encontrado"}
    
    fcm_token = user.get("fcm_token")
    
    if not fcm_token:
        return {
            "status": "not_configured",
            "message": "No tienes notificaciones configuradas",
            "token_type": None,
            "action_required": "Abre la app en tu dispositivo móvil y acepta los permisos de notificaciones."
        }
    
    is_expo_token = fcm_token.startswith('ExponentPushToken')
    is_fcm_token = not is_expo_token and len(fcm_token) > 100
    
    if is_expo_token:
        return {
            "status": "ready",
            "message": "Notificaciones configuradas correctamente",
            "token_type": "expo",
            "token_preview": f"{fcm_token[:30]}..."
        }
    elif is_fcm_token:
        return {
            "status": "needs_update",
            "message": "Tu token de notificaciones necesita actualizarse",
            "token_type": "fcm_native",
            "action_required": "Cierra y vuelve a abrir la app RIS en tu dispositivo móvil para actualizar el token."
        }
    else:
        return {
            "status": "unknown",
            "message": "Token de formato desconocido",
            "token_type": "unknown"
        }


@api_router.delete("/push/token")
async def clear_push_token(current_user: User = Depends(get_current_user)):
    """Clear push token to force re-registration"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$unset": {"fcm_token": ""}}
    )
    logger.info(f"🔔 Token push eliminado para usuario {current_user.user_id}")
    return {"status": "success", "message": "Token eliminado. Abre la app móvil para registrar uno nuevo."}


@api_router.post("/push/test")
async def test_push_notification(current_user: User = Depends(get_current_user)):
    """Test push notification for current user"""
    logger.info(f"🔔 Probando push notification para usuario {current_user.user_id}")
    
    user = await db.users.find_one({"user_id": current_user.user_id}, {"fcm_token": 1, "email": 1, "name": 1})
    
    if not user:
        logger.warning(f"⚠️ Usuario no encontrado: {current_user.user_id}")
        return {"status": "error", "message": "Usuario no encontrado"}
    
    fcm_token = user.get("fcm_token")
    logger.info(f"   Token del usuario: {fcm_token[:40] if fcm_token else 'No configurado'}...")
    
    if not fcm_token:
        logger.warning(f"⚠️ No hay token push para usuario {current_user.user_id}")
        return {
            "status": "error", 
            "message": "No tienes un token de notificaciones registrado. Asegúrate de haber dado permisos de notificaciones en la app.",
            "token_configured": False,
            "action_required": "Abre la app en tu dispositivo móvil y acepta los permisos de notificaciones."
        }
    
    # Verificar tipo de token
    is_expo_token = fcm_token.startswith('ExponentPushToken')
    is_fcm_token = not is_expo_token and len(fcm_token) > 100
    
    if is_fcm_token:
        logger.warning(f"⚠️ Token de FCM detectado para usuario {current_user.user_id}")
        return {
            "status": "error",
            "message": "Tu token de notificaciones es un token de Firebase antiguo. Necesitas actualizar la app.",
            "token_configured": True,
            "token_type": "fcm_native",
            "action_required": "Cierra y vuelve a abrir la app RIS en tu dispositivo móvil para actualizar el token de notificaciones."
        }
    
    success = await send_push_notification(
        fcm_token,
        "🔔 Prueba de Notificación",
        f"¡Hola {user.get('name', 'Usuario')}! Las notificaciones funcionan correctamente.",
        {"type": "test", "timestamp": datetime.now(timezone.utc).isoformat()}
    )
    
    if success:
        logger.info(f"✅ Push notification de prueba enviada a {current_user.user_id}")
        return {
            "status": "success", 
            "message": "¡Notificación enviada exitosamente! Deberías recibirla en tu dispositivo.",
            "token_configured": True,
            "token_type": "expo"
        }
    else:
        logger.error(f"❌ Error enviando push notification de prueba a {current_user.user_id}")
        return {
            "status": "error", 
            "message": "Error al enviar la notificación. Por favor, cierra y vuelve a abrir la app para actualizar tu token.",
            "token_configured": True,
            "action_required": "Cierra y vuelve a abrir la app RIS en tu dispositivo móvil."
        }

@api_router.post("/push/send-to-user/{user_id}")
async def send_push_to_specific_user(
    user_id: str,
    request: Request,
    admin_user: User = Depends(get_admin_user)
):
    """Admin: Send push notification to a specific user"""
    data = await request.json()
    title = data.get("title", "Notificación RIS")
    body = data.get("body", "")
    
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required")
    
    success = await send_push_to_user(user_id, title, body, {"type": "admin_message"})
    
    if success:
        return {"status": "success", "message": f"Push notification sent to user {user_id}"}
    else:
        return {"status": "error", "message": "User doesn't have push notifications enabled"}

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
        {"deleted": {"$ne": True}},
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

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin_user: User = Depends(get_super_admin)):
    """Super Admin: Soft delete a user"""
    # Cannot delete yourself
    if user_id == admin_user.user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    
    # Check if user exists
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Cannot delete other super_admins
    if user.get("role") == "super_admin":
        raise HTTPException(status_code=403, detail="No puedes eliminar a otro super administrador")
    
    # Soft delete - mark as deleted
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "deleted": True,
                "deleted_at": datetime.now(timezone.utc),
                "deleted_by": admin_user.user_id
            }
        }
    )
    
    return {"message": f"Usuario {user.get('name', user.get('email'))} eliminado correctamente"}

@api_router.get("/admin/users/deleted")
async def get_deleted_users(admin_user: User = Depends(get_super_admin)):
    """Super Admin: Get all deleted users"""
    users = await db.users.find(
        {"deleted": True},
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
            "created_at": 1,
            "deleted_at": 1,
            "deleted_by": 1
        }
    ).sort("deleted_at", -1).to_list(1000)
    
    return {"users": users}

@api_router.post("/admin/users/{user_id}/restore")
async def restore_user(user_id: str, admin_user: User = Depends(get_super_admin)):
    """Super Admin: Restore a deleted user"""
    user = await db.users.find_one({"user_id": user_id, "deleted": True})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario eliminado no encontrado")
    
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$unset": {"deleted": "", "deleted_at": "", "deleted_by": ""},
        }
    )
    
    return {"message": f"Usuario {user.get('name', user.get('email'))} restaurado correctamente"}

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
    
    # Check if email already exists (including deleted users - they can be restored)
    existing_user = await db.users.find_one({"email": email_lower})
    if existing_user:
        if existing_user.get("deleted"):
            raise HTTPException(status_code=400, detail="Este email pertenece a una cuenta eliminada. Contacta al administrador para restaurarla.")
        elif existing_user.get("email_verified", False):
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
        "attempts": 0,
        "referral_code": request.referral_code.strip().upper() if request.referral_code else None
    }
    
    # Remove any existing pending verification for this email
    await db.pending_verifications.delete_many({"email": email_lower})
    await db.pending_verifications.insert_one(pending_data)
    
    # Log verification code (for debugging)
    logger.info(f"📧 Verification code for {email_lower}: {verification_code}")
    
    # Send verification email
    email_sent = await send_verification_email(email_lower, verification_code, request.name.strip())
    
    # Also send SMS if phone provided
    sms_sent = False
    if request.phone:
        sms_sent = await send_verification_sms(request.phone.strip(), verification_code, request.name.strip())
        if sms_sent:
            logger.info(f"📱 SMS verification code sent to {request.phone}")
    
    # Build response message
    if email_sent:
        message = "Código de verificación enviado a tu correo"
        if sms_sent:
            message += " y SMS"
    elif sms_sent:
        message = "Código de verificación enviado por SMS"
    else:
        message = "Código de verificación generado. Revisa los logs."
    
    logger.info(f"Registration initiated for {email_lower}, email_sent={email_sent}, sms_sent={sms_sent}")
    
    return {
        "message": message,
        "email": email_lower,
        "email_sent": email_sent,
        "sms_sent": sms_sent,
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
    
    # Check if referral code is valid
    referred_by_user = None
    referral_code_used = pending.get("referral_code")
    if referral_code_used:
        referred_by_user = await db.users.find_one({
            "referral_code": referral_code_used,
            "role": "socio"
        })
        if not referred_by_user:
            logger.warning(f"Código de referido inválido: {referral_code_used}")
            referral_code_used = None  # Ignore invalid code
    
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
        "verification_status": "unverified",  # KYC status - starts as unverified until docs submitted
        "email_verified": True,  # Email is now verified
        "email_verified_at": datetime.now(timezone.utc),
        "accepted_policies": False,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "registration_method": "email",
        # Referral system fields
        "referred_by": referred_by_user["user_id"] if referred_by_user else None,
        "referred_by_code": referral_code_used,
        "total_recharged": 0.0,  # Total recargas acumuladas
        "referral_bonus_paid": False,  # Si ya se pagó el bono de 5 RI$
        "referral_code": None  # Solo los socios tienen código
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

class UpdatePhoneRequest(BaseModel):
    email: str
    phone: str

@api_router.post("/auth/update-phone")
async def update_phone_number(request: UpdatePhoneRequest):
    """Update phone number for pending verification"""
    
    email_lower = request.email.lower().strip()
    new_phone = request.phone.strip()
    
    # Validate phone
    if not new_phone or len(new_phone) < 10:
        raise HTTPException(status_code=400, detail="Número de teléfono inválido")
    
    # Ensure phone has country code
    if not new_phone.startswith('+'):
        new_phone = '+55' + new_phone.lstrip('0')
    
    # Find pending verification
    pending = await db.pending_verifications.find_one({"email": email_lower})
    
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación pendiente para este email")
    
    # Update phone in pending verification
    await db.pending_verifications.update_one(
        {"email": email_lower},
        {"$set": {"phone": new_phone}}
    )
    
    logger.info(f"📱 Phone updated for {email_lower}: {new_phone}")
    
    return {
        "message": "Número actualizado",
        "phone": new_phone
    }

@api_router.post("/auth/resend-verification-code")
async def resend_verification_code(request: ResendVerificationCodeRequest):
    """Resend verification code via email and SMS"""
    
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
    
    # Send email
    email_sent = await send_verification_email(email_lower, new_code, pending.get("name", "Usuario"))
    
    # Send SMS if phone is available
    sms_sent = False
    if pending.get("phone"):
        sms_sent = await send_verification_sms(pending["phone"], new_code, pending.get("name", "Usuario"))
    
    # Build response message
    if email_sent:
        message = "Nuevo código enviado a tu correo"
        if sms_sent:
            message += " y SMS"
    elif sms_sent:
        message = "Nuevo código enviado por SMS"
    else:
        message = "Nuevo código generado"
    
    return {
        "message": message,
        "email_sent": email_sent,
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
    
    # Check if user must change password (temporary password)
    must_change_password = user.get('must_change_password', False)
    
    return {
        "message": "Login exitoso",
        "session_token": session_token,
        "must_change_password": must_change_password,
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

class SetNewPasswordRequest(BaseModel):
    new_password: str
    confirm_password: str

@api_router.post("/auth/set-new-password")
async def set_new_password(request: SetNewPasswordRequest, current_user: User = Depends(get_current_user)):
    """Set new password after temporary password login (no current password required)"""
    
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Check if user actually needs to change password
    if not user.get('must_change_password'):
        raise HTTPException(status_code=400, detail="No se requiere cambio de contraseña")
    
    # Validate new password
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Update password and clear the flag
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "password_hash": hash_password(request.new_password),
            "must_change_password": False,
            "password_changed_at": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"User {current_user.user_id} set new password after temporary login")
    return {"message": "Contraseña establecida exitosamente"}

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
    
    # Check if CPF is already used by another user
    cpf_normalized = request.cpf_number.replace(".", "").replace("-", "").strip()
    existing_cpf = await db.users.find_one({
        "cpf_number": {"$regex": f"^{cpf_normalized}$|^{request.cpf_number}$", "$options": "i"},
        "user_id": {"$ne": current_user.user_id}
    })
    if existing_cpf:
        raise HTTPException(status_code=400, detail="Este CPF ya está registrado por otro usuario")
    
    # Update user with verification data
    # The selfie becomes the user's profile picture (cannot be changed later)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "full_name": request.full_name,
            "document_number": request.document_number,
            "cpf_number": cpf_normalized,  # Store normalized CPF
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
    
    # Send push notification to user (FCM for mobile)
    if user and user.get("fcm_token"):
        try:
            title = "✅ ¡Cuenta Verificada!" if decision.approved else "❌ Verificación Rechazada"
            message = "Ya puedes operar" if decision.approved else "Revisa tus documentos"
            await send_push_notification(user["fcm_token"], title, message)
        except Exception as e:
            logger.error(f"Error sending push to user: {e}")
    
    # Send web push notification
    if decision.approved:
        await send_web_push_to_user(
            user_id=decision.user_id,
            title="🎉 ¡Cuenta Verificada!",
            body="Tu identidad ha sido verificada. Ya puedes usar todas las funciones de RIS.",
            url="/profile"
        )
    else:
        await send_web_push_to_user(
            user_id=decision.user_id,
            title="⚠️ Verificación Rechazada",
            body=f"Tu verificación fue rechazada. Motivo: {decision.rejection_reason or 'Documentos no válidos'}",
            url="/verification"
        )
    
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
    """Get all exchange rates"""
    rate_doc = await db.exchange_rates.find_one({}, {"_id": 0})
    if not rate_doc:
        # Create default rates
        default_rate = ExchangeRate()
        await db.exchange_rates.insert_one(default_rate.dict())
        return default_rate.dict()
    
    # Ensure all rate fields exist
    result = {
        "ris_to_ves": rate_doc.get("ris_to_ves", 92.0),
        "ves_to_ris": rate_doc.get("ves_to_ris", 102.0),
        "ris_to_brl": rate_doc.get("ris_to_brl", 1.0),
        "updated_at": rate_doc.get("updated_at"),
        "updated_by": rate_doc.get("updated_by")
    }
    return result

@api_router.get("/ves-payment-info")
async def get_ves_payment_info():
    """Get bank info for VES payments (Pago Móvil / Transferencia)"""
    info = await db.ves_payment_info.find_one({}, {"_id": 0})
    if not info:
        # Default payment info
        default_info = VESPaymentInfo()
        await db.ves_payment_info.insert_one(default_info.dict())
        return default_info.dict()
    return info

class UpdateAllRatesRequest(BaseModel):
    ris_to_ves: float
    ves_to_ris: Optional[float] = None
    ris_to_brl: Optional[float] = None

@api_router.post("/rate")
async def update_rate(request: UpdateAllRatesRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Update exchange rates"""
    new_rate = {
        "ris_to_ves": request.ris_to_ves,
        "ves_to_ris": request.ves_to_ris if request.ves_to_ris else request.ris_to_ves + 10,
        "ris_to_brl": request.ris_to_brl if request.ris_to_brl else 1.0,
        "updated_at": datetime.now(timezone.utc),
        "updated_by": admin_user.user_id
    }
    await db.exchange_rates.delete_many({})
    await db.exchange_rates.insert_one(new_rate)
    # Return without _id
    return {
        "ris_to_ves": new_rate["ris_to_ves"],
        "ves_to_ris": new_rate["ves_to_ris"],
        "ris_to_brl": new_rate["ris_to_brl"],
        "updated_at": new_rate["updated_at"],
        "updated_by": new_rate["updated_by"]
    }

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

@api_router.post("/withdrawals")
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
    
    # Get next incremental display ID
    display_id = await get_next_withdrawal_id()
    
    # Create transaction
    transaction = Transaction(
        user_id=current_user.user_id,
        type="withdrawal",
        status="pending",
        amount_input=request.amount_ris,
        amount_output=amount_ves,
        beneficiary_data=request.beneficiary_data
    )
    
    # Add display_id to transaction
    tx_dict = transaction.dict()
    tx_dict['display_id'] = display_id
    await db.transactions.insert_one(tx_dict)
    
    # Immediately deduct RIS from balance
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$inc": {"balance_ris": -request.amount_ris}}
    )
    
    # FIFO System: Only send WhatsApp if there's no active withdrawal in queue
    try:
        # Check if there's already an active withdrawal being processed via WhatsApp
        active_withdrawal = await db.transactions.find_one({
            "type": "withdrawal",
            "status": "pending",
            "whatsapp_active": True
        })
        
        if active_withdrawal:
            # There's already one being processed, just send a short notification with totals
            logger.info(f"📋 FIFO: Retiro {transaction.transaction_id} agregado a cola. Retiro activo: {active_withdrawal.get('transaction_id')}")
            
            # Calculate total Bs pending (including this new one)
            pipeline = [
                {"$match": {"type": "withdrawal", "status": "pending"}},
                {"$group": {"_id": None, "total_ves": {"$sum": "$amount_output"}, "count": {"$sum": 1}}}
            ]
            total_result = await db.transactions.aggregate(pipeline).to_list(1)
            total_ves = (total_result[0]['total_ves'] if total_result else 0) + amount_ves
            pending_count = (total_result[0]['count'] if total_result else 0) + 1
            
            # Send SHORT notification with count and total Bs
            await send_whatsapp_notification(f"""📋 {pending_count} solicitudes pendientes en cola.
💵 TOTAL Bs PENDIENTES: {total_ves:,.2f} Bs ({pending_count} retiros)""")
        else:
            # No active withdrawal, this becomes the active one
            # Get beneficiary data
            full_name = request.beneficiary_data.get('full_name', 'N/A')
            id_document = request.beneficiary_data.get('id_document', 'N/A')
            payment_type = request.beneficiary_data.get('payment_type', 'transferencia')
            bank_code = request.beneficiary_data.get('bank_code', '') or request.beneficiary_data.get('bank', '')
            
            # Build message based on payment type
            if payment_type == 'pago_movil':
                phone_number = request.beneficiary_data.get('phone_number', 'N/A')
                # Pago Móvil format: Name, Bank Code, Cedula, Phone, Amount
                message = f"""{full_name}
{bank_code}
{id_document}
{phone_number}
{amount_ves:.2f} Bs

📱 PAGO MÓVIL
👤 Usuario: {current_user.name}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""
            else:
                account_number = request.beneficiary_data.get('account_number', 'N/A')
                bank_name = request.beneficiary_data.get('bank', '')
                # Transferencia format: Name, Account, Cedula, Amount
                message = f"""{full_name}
{account_number}
{id_document}
{amount_ves:.2f} Bs

🏦 TRANSFERENCIA ({bank_name})
👤 Usuario: {current_user.name}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""

            from twilio.rest import Client
            twilio_client_local = Client(
                os.getenv('TWILIO_ACCOUNT_SID'),
                os.getenv('TWILIO_AUTH_TOKEN')
            )
            
            twilio_client_local.messages.create(
                from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                body=message,
                to=os.getenv('TWILIO_WHATSAPP_TO')
            )
            
            # Mark as ACTIVE in WhatsApp queue
            await db.transactions.update_one(
                {"transaction_id": transaction.transaction_id},
                {"$set": {
                    "whatsapp_active": True,
                    "whatsapp_notified": True,
                    "whatsapp_notified_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"📋 FIFO: Retiro {transaction.transaction_id} enviado como activo a WhatsApp")
            
    except Exception as e:
        logger.error(f"WhatsApp notification error: {e}")
    
    return transaction

@api_router.get("/withdrawal/pending")
async def get_pending_withdrawals(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all pending withdrawals with FIFO queue info"""
    withdrawals = await db.transactions.find(
        {"type": "withdrawal", "status": "pending"},
        {"_id": 0}
    ).sort("created_at", 1).to_list(1000)  # FIFO order
    
    # Add queue position and active status
    result = []
    for idx, w in enumerate(withdrawals):
        tx = dict(w)
        tx['queue_position'] = idx + 1
        tx['is_active_in_whatsapp'] = w.get('whatsapp_active', False)
        result.append(tx)
    
    # Queue stats
    active_count = sum(1 for w in withdrawals if w.get('whatsapp_active', False))
    queue_count = len(withdrawals) - active_count
    
    return {
        "withdrawals": result,
        "queue_stats": {
            "total_pending": len(withdrawals),
            "active_in_whatsapp": active_count,
            "waiting_in_queue": queue_count
        }
    }

@api_router.get("/withdrawal/queue-stats")
async def get_withdrawal_queue_stats(admin_user: User = Depends(get_admin_user)):
    """Admin: Get withdrawal queue statistics including total Bs"""
    pending_count = await db.transactions.count_documents({
        "type": "withdrawal",
        "status": "pending"
    })
    
    active_in_whatsapp = await db.transactions.count_documents({
        "type": "withdrawal",
        "status": "pending",
        "whatsapp_active": True
    })
    
    waiting_in_queue = pending_count - active_in_whatsapp
    
    # Calculate total Bs pending
    pipeline = [
        {"$match": {"type": "withdrawal", "status": "pending"}},
        {"$group": {"_id": None, "total_ves": {"$sum": "$amount_output"}, "total_ris": {"$sum": "$amount_input"}}}
    ]
    total_result = await db.transactions.aggregate(pipeline).to_list(1)
    total_ves = total_result[0]['total_ves'] if total_result else 0
    total_ris = total_result[0]['total_ris'] if total_result else 0
    
    return {
        "total_pending": pending_count,
        "active_in_whatsapp": active_in_whatsapp,
        "waiting_in_queue": waiting_in_queue,
        "total_ves_pending": total_ves,
        "total_ris_pending": total_ris
    }

@api_router.get("/admin/withdrawals/cleanup-check")
async def check_withdrawals_cleanup(admin_user: User = Depends(get_admin_user)):
    """Admin: Check for orphaned or stuck pending withdrawals"""
    if admin_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo SuperAdmin puede usar esta función")
    
    # Find all pending withdrawals
    pending = await db.transactions.find({
        "type": "withdrawal",
        "status": "pending"
    }).to_list(100)
    
    orphaned = []
    for tx in pending:
        orphaned.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id", tx.get("transaction_id", "")[:8]),
            "beneficiary": tx.get("beneficiary_data", {}).get("full_name", "N/A"),
            "amount_ves": tx.get("amount_output", 0),
            "created_at": tx.get("created_at"),
            "whatsapp_active": tx.get("whatsapp_active", False),
        })
    
    return {
        "pending_count": len(orphaned),
        "pending_transactions": orphaned
    }

@api_router.post("/admin/withdrawals/cleanup")
async def cleanup_withdrawals(admin_user: User = Depends(get_admin_user)):
    """Admin: Mark all stuck pending withdrawals as cancelled"""
    if admin_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo SuperAdmin puede usar esta función")
    
    # Find and cancel all pending withdrawals
    result = await db.transactions.update_many(
        {"type": "withdrawal", "status": "pending"},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc),
                "cancelled_by": admin_user.user_id,
                "cancellation_reason": "Limpieza manual por admin"
            },
            "$unset": {"whatsapp_active": "", "pending_images": ""}
        }
    )
    
    # Also refund the balance to users
    pending = await db.transactions.find({
        "type": "withdrawal",
        "status": "cancelled",
        "cancellation_reason": "Limpieza manual por admin"
    }).to_list(100)
    
    refunded_count = 0
    for tx in pending:
        user_id = tx.get("user_id")
        amount = tx.get("amount_input", 0)
        if user_id and amount > 0:
            await db.users.update_one(
                {"user_id": user_id},
                {"$inc": {"balance_ris": amount}}
            )
            refunded_count += 1
    
    return {
        "cleaned_count": result.modified_count,
        "refunded_count": refunded_count,
        "message": f"Se cancelaron {result.modified_count} transacciones y se reembolsaron {refunded_count} usuarios"
    }

@api_router.delete("/admin/withdrawals/delete/{transaction_id}")
async def delete_single_withdrawal(transaction_id: str, admin_user: User = Depends(get_admin_user)):
    """Admin: Delete a single stuck/test withdrawal"""
    if admin_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo SuperAdmin puede usar esta función")
    
    tx = await db.transactions.find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    # Refund user if pending
    if tx.get("status") == "pending":
        user_id = tx.get("user_id")
        amount = tx.get("amount_input", 0)
        if user_id and amount > 0:
            await db.users.update_one(
                {"user_id": user_id},
                {"$inc": {"balance_ris": amount}}
            )
    
    # Delete the transaction
    await db.transactions.delete_one({"transaction_id": transaction_id})
    
    return {"message": f"Transacción {transaction_id} eliminada", "refunded": tx.get("status") == "pending"}
async def process_withdrawal(request: ProcessWithdrawalRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Mark withdrawal as completed and upload proof"""
    # Get transaction first to get user_id
    transaction = await db.transactions.find_one({"transaction_id": request.transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
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
    
    # Send push notification to user
    await send_web_push_to_user(
        user_id=transaction["user_id"],
        title="✅ Envío Completado",
        body=f"Tu envío de {transaction.get('amount_input', 0):.2f} RIS ha sido procesado exitosamente.",
        url="/history"
    )
    
    return {"message": "Withdrawal processed successfully"}

# =======================
# VES RECHARGE ROUTES (Manual Payment)
# =======================

class VESRechargeRequest(BaseModel):
    amount_ves: float
    amount_ris: float
    payment_method: str  # 'pago_movil' or 'transferencia'
    voucher_image: str  # base64
    bank: Optional[str] = None  # banco_venezuela or banesco

@api_router.post("/recharge/ves")
async def create_ves_recharge(request: VESRechargeRequest, current_user: User = Depends(get_current_user)):
    """Create a VES recharge request (manual payment with voucher upload)"""
    
    # Validate amounts
    if request.amount_ves <= 0 or request.amount_ris <= 0:
        raise HTTPException(status_code=400, detail="Los montos deben ser mayores a 0")
    
    # Check verification status
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Debes completar la verificación de tu cuenta primero")
    
    # Validate voucher image
    if not request.voucher_image or not request.voucher_image.startswith('data:image'):
        raise HTTPException(status_code=400, detail="Debes adjuntar el comprobante de pago")
    
    # Generate transaction ID
    transaction_id = str(uuid.uuid4())
    
    # Create transaction with pending_manual_approval status
    transaction_data = {
        "transaction_id": transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge_ves",
        "payment_method": request.payment_method,
        "status": "pending_manual_approval",
        "amount_input": request.amount_ves,  # VES paid
        "amount_output": request.amount_ris,  # RIS to receive
        "voucher_image": request.voucher_image,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(transaction_data)
    
    # Create notification for admins
    admins = await db.users.find({"role": {"$in": ["admin", "super_admin"]}}).to_list(100)
    for admin in admins:
        admin_notification = {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": admin["user_id"],
            "title": "💵 Nueva Recarga VES Pendiente",
            "message": f"{current_user.name} ha enviado una recarga de {request.amount_ves:.2f} VES ({request.amount_ris:.2f} RIS)",
            "type": "ves_recharge_pending",
            "priority": "high",
            "data": {
                "transaction_id": transaction_id,
                "user_name": current_user.name,
                "amount_ves": request.amount_ves,
                "amount_ris": request.amount_ris
            },
            "read": False,
            "created_at": datetime.now(timezone.utc)
        }
        await db.notifications.insert_one(admin_notification)
    
    # Create notification for user
    user_notification = {
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "title": "📤 Recarga Enviada",
        "message": f"Tu recarga de {request.amount_ves:.2f} VES está siendo procesada. Te notificaremos cuando sea aprobada.",
        "type": "ves_recharge_submitted",
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    await db.notifications.insert_one(user_notification)
    
    logger.info(f"VES recharge created: {transaction_id} by user {current_user.user_id} - {request.amount_ves} VES -> {request.amount_ris} RIS")
    
    # Send WhatsApp notification to admin
    whatsapp_message = f"""💵 *Nueva Recarga VES*

👤 Usuario: {current_user.name}
📧 Email: {current_user.email}

💰 Monto: {request.amount_ves:,.2f} VES
🪙 RIS a acreditar: {request.amount_ris:.2f} RIS
💳 Método: {'Pago Móvil' if request.payment_method == 'pago_movil' else 'Transferencia'}

⏳ Estado: Pendiente de aprobación

🔗 Revisa en el panel de admin"""
    
    await send_whatsapp_notification(whatsapp_message)
    
    return {
        "message": "Solicitud de recarga enviada correctamente",
        "transaction_id": transaction_id,
        "status": "pending_manual_approval"
    }

# Admin endpoint to get pending VES recharges
@api_router.get("/admin/recharges/ves/pending")
async def get_pending_ves_recharges(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all VES recharges pending manual approval"""
    recharges = await db.transactions.find(
        {"type": "recharge_ves", "status": "pending_manual_approval"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    
    # Get user info for each recharge
    result = []
    for r in recharges:
        user = await db.users.find_one({"user_id": r["user_id"]}, {"_id": 0, "name": 1, "email": 1, "picture": 1})
        r["user_name"] = user.get("name") if user else "Usuario"
        r["user_email"] = user.get("email") if user else ""
        r["user_picture"] = user.get("picture") if user else None
        result.append(r)
    
    return {"recharges": result}

# Admin endpoint to approve/reject VES recharge
class ApproveVESRechargeRequest(BaseModel):
    transaction_id: str
    approved: bool
    rejection_reason: Optional[str] = None

@api_router.post("/admin/recharges/ves/approve")
async def approve_ves_recharge(request: ApproveVESRechargeRequest, admin_user: User = Depends(get_admin_user)):
    """Admin: Approve or reject a VES recharge"""
    
    # Find the transaction
    transaction = await db.transactions.find_one({"transaction_id": request.transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    if transaction.get("status") != "pending_manual_approval":
        raise HTTPException(status_code=400, detail="Esta transacción ya fue procesada")
    
    user_id = transaction["user_id"]
    amount_ris = transaction["amount_output"]
    amount_ves = transaction["amount_input"]
    
    if request.approved:
        # Approve: add RIS to user balance
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"balance_ris": amount_ris}}
        )
        
        # Process referral bonus if applicable
        await process_referral_bonus(user_id, amount_ris)
        
        # Update transaction status
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "processed_by": admin_user.user_id,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga Aprobada",
            message=f"Tu recarga de {amount_ves:.2f} VES ha sido aprobada. Se han acreditado {amount_ris:.2f} RIS a tu cuenta.",
            notification_type="ves_recharge_approved",
            data={"transaction_id": request.transaction_id, "amount_ris": amount_ris}
        )
        
        # Send web push notification
        await send_web_push_to_user(
            user_id=user_id,
            title="💰 Recarga Completada",
            body=f"Tu recarga de {amount_ris:.2f} RIS ha sido acreditada a tu cuenta.",
            url="/history"
        )
        
        logger.info(f"VES recharge approved: {request.transaction_id} - {amount_ris} RIS credited to {user_id}")
        return {"message": "Recarga aprobada y RIS acreditados"}
    
    else:
        # Reject: update status only
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "rejected",
                "rejection_reason": request.rejection_reason or "Rechazado por administrador",
                "processed_by": admin_user.user_id,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga Rechazada",
            message=f"Tu recarga de {amount_ves:.2f} VES fue rechazada. Motivo: {request.rejection_reason or 'Datos del comprobante incorrectos'}",
            notification_type="ves_recharge_rejected",
            data={"transaction_id": request.transaction_id, "reason": request.rejection_reason}
        )
        
        # Send web push notification
        await send_web_push_to_user(
            user_id=user_id,
            title="❌ Recarga Rechazada",
            body=f"Tu recarga fue rechazada. Motivo: {request.rejection_reason or 'Datos incorrectos'}",
            url="/history"
        )
        
        logger.info(f"VES recharge rejected: {request.transaction_id} - Reason: {request.rejection_reason}")
        return {"message": "Recarga rechazada"}

# =======================
# PIX RECHARGE ROUTES
# =======================

class PixRechargeRequest(BaseModel):
    amount_brl: float = Field(alias="amount_brl")
    payer_cpf: str = Field(alias="payer_cpf")
    
    class Config:
        populate_by_name = True

@api_router.post("/pix/create")
async def create_pix_payment(request: PixRechargeRequest, current_user: User = Depends(get_current_user)):
    """Create a PIX payment for recharging RIS balance"""
    
    # Validate amount (min 10, max 2000 BRL)
    if request.amount_brl < 10:
        raise HTTPException(status_code=400, detail="El monto mínimo es R$ 10,00")
    if request.amount_brl > 2000:
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
            "amount_input": request.amount_brl
        },
        sort=[("created_at", -1)]
    )
    
    if last_pending_recharge:
        raise HTTPException(
            status_code=400, 
            detail=f"Ya tienes una recarga pendiente de R$ {request.amount_brl:.2f}. Completa o cancela esa transacción primero, o elige un monto diferente."
        )
    
    # Generate unique transaction ID
    transaction_id = str(uuid.uuid4())
    
    # Get user name parts
    name_parts = current_user.name.split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else first_name
    
    # Create PIX payment with Mercado Pago
    pix_result = mercadopago_service.create_pix_payment(
        amount=request.amount_brl,
        description=f"Recarga RIS - {request.amount_brl} BRL",
        payer_email=current_user.email,
        payer_first_name=first_name,
        payer_last_name=last_name,
        payer_cpf=request.payer_cpf,
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
        "amount_input": request.amount_brl,  # BRL
        "amount_output": request.amount_brl,  # RIS (1:1)
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
        "amount_brl": request.amount_brl,
        "amount_ris": request.amount_brl
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

# Upload proof endpoint (alias for verify-with-proof for frontend compatibility)
class PixUploadProofRequest(BaseModel):
    transaction_id: str
    proof_image: str  # base64

@api_router.post("/pix/upload-proof")
async def upload_pix_proof(request: PixUploadProofRequest, current_user: User = Depends(get_current_user)):
    """Upload proof of PIX payment for manual verification"""
    
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
        
        # Process referral bonus if applicable
        await process_referral_bonus(current_user.user_id, amount_ris)
        
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "proof_image": request.proof_image,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "auto_approved": True
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=current_user.user_id,
            title="✅ Recarga Completada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue aprobada. +{amount_ris:.2f} RIS",
            notification_type="recharge_completed",
            data={"transaction_id": request.transaction_id, "amount_ris": amount_ris}
        )
        
        logger.info(f"PIX payment auto-approved for user {current_user.user_id}: +{amount_ris} RIS")
        
        return {
            "status": "completed",
            "message": "Pago verificado automáticamente",
            "amount_ris": amount_ris
        }
    
    # Payment not auto-approved - save proof for manual review
    await db.transactions.update_one(
        {"transaction_id": request.transaction_id},
        {"$set": {
            "status": "pending_review",
            "proof_image": request.proof_image,
            "proof_uploaded_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # Notify admins about pending review
    admins = await db.users.find({"role": {"$in": ["admin", "super_admin"]}}).to_list(100)
    for admin in admins:
        await create_notification(
            user_id=admin["user_id"],
            title="📝 Recarga PIX Pendiente",
            message=f"{current_user.name} envió comprobante de R$ {transaction.get('amount_input', 0):.2f}. Requiere revisión.",
            notification_type="pix_review_pending",
            data={"transaction_id": request.transaction_id, "user_id": current_user.user_id}
        )
    
    logger.info(f"PIX proof uploaded for review: {request.transaction_id} by user {current_user.user_id}")
    
    return {
        "status": "pending_review",
        "message": "Comprobante enviado. Un administrador revisará tu pago pronto."
    }

# Cancel PIX payment
class PixCancelRequest(BaseModel):
    transaction_id: str

@api_router.post("/pix/cancel")
async def cancel_pix_payment(request: PixCancelRequest, current_user: User = Depends(get_current_user)):
    """Cancel a pending PIX payment"""
    
    # Find transaction
    transaction = await db.transactions.find_one({
        "transaction_id": request.transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge",
        "status": {"$in": ["pending", "pending_review"]}
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    # Update transaction status
    await db.transactions.update_one(
        {"transaction_id": request.transaction_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc),
            "cancelled_by": "user",
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"PIX payment cancelled by user: {request.transaction_id}")
    
    return {"message": "Recarga cancelada correctamente"}

@api_router.get("/pix/pending")
async def get_pending_pix(current_user: User = Depends(get_current_user)):
    """Get any pending PIX transaction for the current user"""
    
    # Find pending PIX transaction (either pending or pending_review)
    pending_tx = await db.transactions.find_one(
        {
            "user_id": current_user.user_id,
            "type": "recharge",
            "payment_method": "pix",
            "status": {"$in": ["pending", "pending_review"]}
        },
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    
    if not pending_tx:
        return {"has_pending": False, "pending_transaction": None}
    
    # Check if PIX has expired (30 minutes from creation)
    created_at = pending_tx.get("created_at")
    if created_at:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        expiration_time = created_at + timedelta(minutes=30)
        
        if datetime.now(timezone.utc) > expiration_time:
            # Mark as expired if not already
            if pending_tx.get("status") == "pending":
                await db.transactions.update_one(
                    {"transaction_id": pending_tx["transaction_id"]},
                    {"$set": {
                        "status": "expired",
                        "expired_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }}
                )
                return {"has_pending": False, "pending_transaction": None}
    
    # Return pending transaction with PIX data
    return {
        "has_pending": True,
        "pending_transaction": {
            "transaction_id": pending_tx.get("transaction_id"),
            "amount_brl": pending_tx.get("amount_input"),
            "amount_ris": pending_tx.get("amount_output"),
            "status": pending_tx.get("status"),
            "qr_code": pending_tx.get("pix_qr_code"),
            "qr_code_base64": pending_tx.get("pix_qr_code_base64"),
            "expiration": pending_tx.get("pix_expiration"),
            "created_at": pending_tx.get("created_at").isoformat() if pending_tx.get("created_at") else None,
            "proof_uploaded": pending_tx.get("proof_image") is not None
        }
    }

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
        message_text = request.message.strip() if request.message else "[Imagen adjunta]"
        
        # Guardar mensaje en la base de datos PRIMERO
        support_record = {
            "user_id": current_user.user_id,
            "user_name": current_user.name,
            "user_email": current_user.email,
            "message": message_text,
            "image": request.image if request.image else None,
            "sent_via": "app",
            "status": "pending",
            "created_at": datetime.now(timezone.utc)
        }
        result = await db.support_messages.insert_one(support_record)
        message_id = str(result.inserted_id)
        
        # Intentar enviar por WhatsApp (opcional)
        whatsapp_sent = False
        try:
            twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
            twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
            whatsapp_from = os.getenv('TWILIO_WHATSAPP_FROM')
            whatsapp_to = os.getenv('TWILIO_WHATSAPP_TO')
            
            if twilio_sid and twilio_token and whatsapp_from and whatsapp_to:
                from twilio.rest import Client
                twilio_client = Client(twilio_sid, twilio_token)
                
                support_message = f"""📩 *MENSAJE DE SOPORTE*

👤 *Usuario:* {current_user.name}
📧 *Email:* {current_user.email}
🆔 *ID:* {current_user.user_id}

💬 *Mensaje:*
{message_text}

{"📷 *Imagen adjunta*" if request.image else ""}
ID Mensaje: {message_id}

---
Responde a este mensaje para contactar al usuario."""
                
                twilio_client.messages.create(
                    from_=whatsapp_from,
                    body=support_message,
                    to=whatsapp_to
                )
                whatsapp_sent = True
                
                # Actualizar estado en DB
                await db.support_messages.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"sent_via": "whatsapp", "status": "sent"}}
                )
        except Exception as whatsapp_error:
            logger.warning(f"WhatsApp notification failed (message saved to DB): {whatsapp_error}")
        
        logger.info(f"Support message saved from {current_user.email} (WhatsApp: {whatsapp_sent})")
        
        return {
            "status": "success", 
            "message": "Mensaje enviado correctamente",
            "message_id": message_id
        }
        
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
    
    result = []
    for n in notifications:
        # Use notification_id if exists, otherwise use _id
        notif_id = n.get('notification_id') or str(n['_id'])
        result.append({
            "notification_id": notif_id,
            "user_id": n.get("user_id"),
            "title": n.get("title"),
            "message": n.get("message"),
            "type": n.get("type"),
            "data": n.get("data", {}),
            "read": n.get("read", False),
            "created_at": n.get("created_at")
        })
    
    return result

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
    # Try to find by notification_id first (new format), then by _id (old format)
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user.user_id},
        {"$set": {"read": True}}
    )
    
    # If not found by notification_id, try _id for backwards compatibility
    if result.modified_count == 0:
        try:
            from bson import ObjectId
            await db.notifications.update_one(
                {"_id": ObjectId(notification_id), "user_id": current_user.user_id},
                {"$set": {"read": True}}
            )
        except Exception:
            pass
    
    return {"message": "Notification marked as read"}

@api_router.post("/notifications/read-all")
@api_router.post("/notifications/mark-all-read")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    await db.notifications.update_many(
        {"user_id": current_user.user_id, "read": False},
        {"$set": {"read": True}}
    )
    return {"message": "All notifications marked as read"}

async def create_notification(user_id: str, title: str, message: str, notification_type: str, data: dict = None, send_push: bool = True):
    """Helper function to create a notification and optionally send push notification"""
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"
    notification = {
        "notification_id": notification_id,
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
    
    # Send push notifications if enabled
    if send_push:
        push_data = {"type": notification_type, "notification_id": notification_id}
        if data:
            push_data.update(data)
        
        # Try FCM/Expo push (for native mobile apps)
        try:
            await send_push_to_user(user_id, title, message, push_data)
        except Exception as e:
            logger.error(f"Error sending FCM push notification: {e}")
        
        # Also send Web Push (for browsers/PWA)
        try:
            await send_web_push_to_user(user_id, title, message, url="/notifications")
        except Exception as e:
            logger.error(f"Error sending web push notification: {e}")

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
    # Return all fields including proof_image for voucher display
    return transactions

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
        
        # Check if message is a command to process pending images
        body_lower = body.strip().lower() if body else ""
        process_commands = ['listo', 'ok', 'completar', 'procesar', 'enviar', 'done', 'ready']
        is_process_command = body_lower in process_commands
        
        # Check if message has media (images)
        if num_media > 0:
            # Download ALL images from the message
            import base64
            from bson import ObjectId
            images_base64 = []
            
            for i in range(int(num_media)):
                media_url = form_data.get(f'MediaUrl{i}', '')
                media_content_type = form_data.get(f'MediaContentType{i}', '')
                
                logger.info(f"Media {i} URL: {media_url}")
                
                if media_url and 'image' in media_content_type:
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        auth = (
                            os.getenv('TWILIO_ACCOUNT_SID'),
                            os.getenv('TWILIO_AUTH_TOKEN')
                        )
                        response = await client.get(media_url, auth=auth)
                        
                        if response.status_code == 200:
                            image_base64 = f"data:{media_content_type};base64,{base64.b64encode(response.content).decode()}"
                            images_base64.append(image_base64)
                            logger.info(f"Imagen {i+1} descargada")
            
            if images_base64:
                logger.info(f"Total imágenes descargadas: {len(images_base64)}")
                
                # Find the ACTIVE withdrawal (first check for whatsapp_active, then oldest pending)
                active_withdrawal = await db.transactions.find_one(
                    {"type": "withdrawal", "status": "pending", "whatsapp_active": True}
                )
                
                logger.info(f"Búsqueda whatsapp_active=True: {'Encontrado' if active_withdrawal else 'No encontrado'}")
                
                if not active_withdrawal:
                    # Fall back to oldest pending withdrawal
                    active_withdrawal = await db.transactions.find_one(
                        {"type": "withdrawal", "status": "pending"},
                        sort=[("created_at", 1)]
                    )
                    logger.info(f"Búsqueda fallback (oldest): {'Encontrado' if active_withdrawal else 'No encontrado'}")
                
                if not active_withdrawal:
                    from twilio.rest import Client
                    twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                    twilio_client.messages.create(
                        from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                        body="⚠️ No hay retiros pendientes.",
                        to=from_number
                    )
                    return {"status": "no_pending"}
                
                tx_id = active_withdrawal.get('transaction_id')
                display_id = active_withdrawal.get('display_id', tx_id[:8] if tx_id else 'N/A')
                mongo_id = active_withdrawal['_id']
                
                logger.info(f"Transacción activa encontrada: {display_id} (MongoDB ID: {mongo_id})")
                
                # ATOMIC operation: Use $push with $each to add images (prevents race conditions)
                # Also set whatsapp_active and initialize pending_images if needed
                result = await db.transactions.update_one(
                    {"_id": mongo_id, "status": "pending"},
                    {
                        "$push": {"pending_images": {"$each": images_base64}},
                        "$set": {"whatsapp_active": True}
                    }
                )
                
                logger.info(f"Update result - matched: {result.matched_count}, modified: {result.modified_count}")
                
                # Get updated document to get accurate count
                updated_tx = await db.transactions.find_one({"_id": mongo_id})
                total_images = len(updated_tx.get('pending_images', [])) if updated_tx else len(images_base64)
                
                # Send confirmation of images received
                from twilio.rest import Client
                twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                twilio_client.messages.create(
                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                    body=f"📷 {total_images} imagen(es) recibida(s) para ID: {display_id}\n\n✅ Escribe *listo* para procesar\n📷 O envía más imágenes",
                    to=from_number
                )
                
                logger.info(f"Imágenes agregadas al buffer: {total_images} total para TX {display_id}")
                return {"status": "images_buffered", "count": total_images}
        
        # Handle "listo" command to process buffered images
        elif is_process_command:
            logger.info(f"Comando de procesar recibido: {body}")
            from bson import ObjectId
            
            # Find active withdrawal with pending images
            active_withdrawal = await db.transactions.find_one(
                {"type": "withdrawal", "status": "pending", "whatsapp_active": True, "pending_images": {"$exists": True, "$ne": []}}
            )
            
            if not active_withdrawal:
                from twilio.rest import Client
                twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                twilio_client.messages.create(
                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                    body="⚠️ No hay imágenes pendientes para procesar.\nEnvía primero las imágenes del voucher.",
                    to=from_number
                )
                return {"status": "no_pending_images"}
            
            # Get pending images
            images_base64 = active_withdrawal.get('pending_images', [])
            tx_id = active_withdrawal.get('transaction_id')
            display_id = active_withdrawal.get('display_id', tx_id[:8] if tx_id else 'N/A')
            mongo_id = active_withdrawal['_id']
            
            logger.info(f"Procesando {len(images_base64)} imágenes para TX {display_id}")
            
            # Complete the transaction
            result = await db.transactions.update_one(
                {"_id": mongo_id, "status": "pending"},
                {"$set": {
                    "status": "completed",
                    "proof_images": images_base64,
                    "proof_image": images_base64[0] if images_base64 else None,
                    "completed_at": datetime.now(timezone.utc),
                    "processed_via": "whatsapp",
                    "whatsapp_active": False
                },
                "$unset": {"pending_images": ""}}
            )
            
            if result.modified_count > 0:
                user = await db.users.find_one({"user_id": active_withdrawal['user_id']})
                beneficiary = active_withdrawal.get('beneficiary_data', {})
                amount_ris = active_withdrawal.get('amount_input', 0)
                amount_ves = active_withdrawal.get('amount_output', 0)
                
                # Save admin record
                await db.admin_payment_records.insert_one({
                    "record_type": "withdrawal_completed",
                    "transaction_id": tx_id,
                    "display_id": display_id,
                    "user_id": active_withdrawal['user_id'],
                    "amount_ris": amount_ris,
                    "amount_ves": amount_ves,
                    "beneficiary": beneficiary,
                    "proof_images": images_base64,
                    "image_count": len(images_base64),
                    "processed_via": "whatsapp",
                    "completed_at": datetime.now(timezone.utc)
                })
                
                # Notify user
                await create_notification(
                    user_id=active_withdrawal['user_id'],
                    title="✅ Retiro Completado",
                    message=f"Tu retiro de {amount_ris:.2f} RIS ({amount_ves:.2f} Bs) fue procesado. ID: {display_id}",
                    notification_type="withdrawal_completed",
                    data={"transaction_id": tx_id}
                )
                
                # Send confirmation to admin
                from twilio.rest import Client
                twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                
                confirmation_msg = f"""✅ RETIRO PROCESADO

🔢 ID: {display_id}
💰 {amount_ris:.2f} RIS → {amount_ves:.2f} Bs
👤 {beneficiary.get('full_name', 'N/A')}
📷 {len(images_base64)} imagen(es)

✅ Usuario notificado"""
                
                twilio_client.messages.create(
                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                    body=confirmation_msg,
                    to=from_number
                )
                
                # Send next withdrawal
                next_tx = await send_next_pending_withdrawal_whatsapp()
                if next_tx:
                    logger.info(f"📋 FIFO: Siguiente retiro enviado: {next_tx}")
                else:
                    pending_count = await db.transactions.count_documents({"type": "withdrawal", "status": "pending"})
                    if pending_count == 0:
                        await send_whatsapp_notification("📭 No hay más retiros pendientes.")
                
                return {"status": "success", "images_processed": len(images_base64)}
            else:
                return {"status": "error", "message": "No se pudo actualizar"}
        
        # Handle text-only messages (support chat, etc.)
        else:
            # Text message without images - could be support chat
            logger.info("Mensaje de texto sin imágenes - posible chat de soporte")
            
            # Find the most recent open support conversation
            support_conv = await db.support_conversations.find_one(
                {"status": "open"},
                sort=[("last_message_at", -1)]
            )
            
            if support_conv and body:
                # Add admin response to conversation
                await db.support_conversations.update_one(
                    {"_id": support_conv['_id']},
                    {
                        "$push": {
                            "messages": {
                                "sender": "admin",
                                "message": body,
                                "timestamp": datetime.now(timezone.utc)
                            }
                        },
                        "$set": {"last_message_at": datetime.now(timezone.utc)}
                    }
                )
                logger.info(f"Respuesta de admin agregada a conversación: {support_conv.get('conversation_id')}")
            
            return {"status": "text_processed"}
    
    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}



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
    pending_ves_recharges = await db.transactions.count_documents({"type": "recharge_ves", "status": "pending_manual_approval"})
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
            "pending_recharges": pending_recharges + pending_ves_recharges,
            "pending_ves_recharges": pending_ves_recharges
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
            "recharge_id": tx.get("recharge_id") or tx.get("transaction_id"),
            "amount_brl": tx.get("amount_input"),
            "amount_ris": tx.get("amount_output"),
            "status": tx.get("status"),
            "payment_method": tx.get("payment_method", "pix"),
            "source": tx.get("source", "pix"),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "proof_image": tx.get("proof_image"),
            "voucher_url": tx.get("voucher_url"),
            "has_proof": bool(tx.get("proof_image") or tx.get("voucher_url")),
        } for tx in recharges],
        
        # ===== WITHDRAWAL HISTORY =====
        "withdrawals": [{
            "transaction_id": tx.get("transaction_id"),
            "amount_ris": tx.get("amount_input"),
            "amount_ves": tx.get("amount_output"),
            "status": tx.get("status"),
            "beneficiary": tx.get("beneficiary_data", {}),
            "beneficiary_name": tx.get("beneficiary_data", {}).get("full_name") or tx.get("beneficiary_name"),
            "beneficiary_bank": tx.get("beneficiary_data", {}).get("bank") or tx.get("beneficiary_bank"),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "processed_by": tx.get("processed_by"),
            "proof_image": tx.get("proof_image"),
            "voucher_url": tx.get("voucher_url"),
            "has_proof": bool(tx.get("proof_image") or tx.get("voucher_url")),
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
    message: str = ""
    image: Optional[str] = None

@api_router.post("/admin/support/respond")
async def admin_respond_support(request: AdminSupportResponse, admin_user: User = Depends(get_admin_user)):
    """Send a response to user from admin panel"""
    if not has_permission(admin_user, "support.respond"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Validate that at least message or image is provided
    if not request.message.strip() and not request.image:
        raise HTTPException(status_code=400, detail="Debes enviar un mensaje o una imagen")
    
    # Save response
    admin_response = {
        "user_id": request.user_id,
        "message": request.message,
        "image": request.image,
        "sender": "admin",
        "admin_id": admin_user.user_id,
        "admin_name": admin_user.name,
        "created_at": datetime.now(timezone.utc)
    }
    await db.support_responses.insert_one(admin_response)
    
    # Create notification
    notification_message = request.message[:200] if request.message else "📷 Te enviaron una imagen"
    if request.message and len(request.message) > 200:
        notification_message += "..."
    
    await create_notification(
        user_id=request.user_id,
        title="💬 Respuesta de Soporte",
        message=notification_message,
        notification_type="support_response",
        data={"full_message": request.message, "has_image": bool(request.image)}
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

# --- Admin Withdrawals/Remittances Endpoints ---
@api_router.get("/admin/withdrawals/all")
async def get_all_withdrawals(admin_user: User = Depends(get_admin_user)):
    """Get all withdrawals/remittances with all statuses"""
    if not has_permission(admin_user, "withdrawals.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get all withdrawal transactions
    cursor = db.transactions.find({
        "type": "withdrawal"
    }).sort("created_at", -1).limit(500)
    
    withdrawals = []
    async for tx in cursor:
        # Get user info
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("full_name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_input": tx.get("amount_input", 0),
            "amount_output": tx.get("amount_output", 0),
            "rate": tx.get("rate", 0),
            "commission": tx.get("commission", 0),
            "status": tx.get("status", "pending"),
            "beneficiary_data": tx.get("beneficiary_data", {}),
            "created_at": tx.get("created_at"),
            "updated_at": tx.get("updated_at"),
            "completed_at": tx.get("completed_at"),
            "proof_image": tx.get("proof_image"),
            "proof_images": tx.get("proof_images", []),
            "pending_images": tx.get("pending_images", []),
            "whatsapp_active": tx.get("whatsapp_active", False),
            "processed_by": tx.get("processed_by"),
        })
    
    return withdrawals

@api_router.get("/admin/withdrawals/pending")
async def admin_get_pending_withdrawals(admin_user: User = Depends(get_admin_user)):
    """Get only pending withdrawals for processing"""
    if not has_permission(admin_user, "withdrawals.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending"
    }).sort("created_at", 1)  # Oldest first
    
    withdrawals = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("full_name") if user else "Unknown",
            "amount_input": tx.get("amount_input", 0),
            "amount_output": tx.get("amount_output", 0),
            "rate": tx.get("rate", 0),
            "status": tx.get("status"),
            "beneficiary_data": tx.get("beneficiary_data", {}),
            "created_at": tx.get("created_at"),
            "pending_images": tx.get("pending_images", []),
            "whatsapp_active": tx.get("whatsapp_active", False),
        })
    
    return withdrawals

# --- Process Withdrawal from Admin Panel ---
class ProcessWithdrawalAdminRequest(BaseModel):
    transaction_id: str
    action: str  # "approve" or "reject"
    proof_image: Optional[str] = None  # Single image (backwards compatibility)
    proof_images: Optional[List[str]] = None  # Multiple images
    rejection_reason: Optional[str] = None

@api_router.post("/admin/withdrawals/process")
async def process_withdrawal_admin(request: ProcessWithdrawalAdminRequest, admin_user: User = Depends(get_admin_user)):
    """Process withdrawal from admin panel with support for multiple images"""
    if not has_permission(admin_user, "withdrawals.process"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    tx = await db.transactions.find_one({"transaction_id": request.transaction_id, "status": "pending"})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    if request.action == "approve":
        # Get images (support both single and multiple)
        images = request.proof_images if request.proof_images else ([request.proof_image] if request.proof_image else [])
        
        if not images:
            raise HTTPException(status_code=400, detail="Se requiere al menos una imagen de comprobante")
        
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {
                "$set": {
                    "status": "completed",
                    "proof_image": images[0],  # First image for backwards compatibility
                    "proof_images": images,  # All images
                    "completed_at": datetime.now(timezone.utc),
                    "processed_by": admin_user.user_id,
                    "processed_via": "admin_panel"
                },
                "$unset": {"pending_images": "", "whatsapp_active": ""}
            }
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
        
        # FIFO: Send next pending withdrawal to WhatsApp
        next_tx = await send_next_pending_withdrawal_whatsapp()
        if next_tx:
            logger.info(f"📋 FIFO (Admin Panel): Siguiente retiro enviado a WhatsApp: {next_tx}")
        
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
        
        # FIFO: Send next pending withdrawal to WhatsApp (even after rejection)
        next_tx = await send_next_pending_withdrawal_whatsapp()
        if next_tx:
            logger.info(f"📋 FIFO (Admin Panel - Reject): Siguiente retiro enviado a WhatsApp: {next_tx}")
        
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

# ====================
# WEB PUSH NOTIFICATIONS ROUTES
# ====================

class PushSubscriptionRequest(BaseModel):
    """Push subscription data from browser"""
    endpoint: str
    keys: dict  # contains p256dh and auth keys

class SendNotificationRequest(BaseModel):
    """Request to send a notification"""
    title: str
    body: str
    url: str = "/"

@api_router.get("/push/web/vapid-public-key")
async def get_vapid_public_key():
    """Get the VAPID public key for client-side subscription"""
    public_key = web_push_service.get_public_key()
    if not public_key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"publicKey": public_key}

@api_router.post("/push/web/subscribe")
async def subscribe_to_push(
    request: PushSubscriptionRequest, 
    current_user: User = Depends(get_current_user)
):
    """Subscribe user to push notifications"""
    try:
        subscription_data = {
            "endpoint": request.endpoint,
            "keys": request.keys
        }
        
        # Update user's push subscription in database
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {
                "web_push_subscription": subscription_data,
                "web_push_enabled": True,
                "web_push_subscribed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"User {current_user.user_id} subscribed to web push notifications")
        return {"success": True, "message": "Suscripción exitosa a notificaciones"}
        
    except Exception as e:
        logger.error(f"Error subscribing to push: {e}")
        raise HTTPException(status_code=500, detail="Error al suscribirse a notificaciones")

@api_router.post("/push/web/unsubscribe")
async def unsubscribe_from_push(current_user: User = Depends(get_current_user)):
    """Unsubscribe user from push notifications"""
    try:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$set": {
                "web_push_subscription": None,
                "web_push_enabled": False
            }}
        )
        
        logger.info(f"User {current_user.user_id} unsubscribed from web push notifications")
        return {"success": True, "message": "Desuscripción exitosa"}
        
    except Exception as e:
        logger.error(f"Error unsubscribing from push: {e}")
        raise HTTPException(status_code=500, detail="Error al desuscribirse")

@api_router.get("/push/web/status")
async def get_web_push_status(current_user: User = Depends(get_current_user)):
    """Get current web push notification subscription status"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {
        "enabled": user.get("web_push_enabled", False),
        "subscribed": user.get("web_push_subscription") is not None,
        "subscribed_at": user.get("web_push_subscribed_at")
    }

@api_router.post("/push/web/test")
async def send_web_test_notification(current_user: User = Depends(get_current_user)):
    """Send a test web push notification to the current user"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    subscription = user.get("web_push_subscription")
    if not subscription:
        raise HTTPException(status_code=400, detail="No estás suscrito a notificaciones")
    
    success = web_push_service.send_notification(
        subscription=subscription,
        title="🔔 Notificación de Prueba",
        body="¡Las notificaciones push están funcionando correctamente!",
        url="/profile"
    )
    
    if success:
        return {"success": True, "message": "Notificación de prueba enviada"}
    else:
        raise HTTPException(status_code=500, detail="Error al enviar notificación")

# Helper function to send push notification to a user
async def send_web_push_to_user(user_id: str, title: str, body: str, url: str = "/"):
    """Send a web push notification to a specific user"""
    user = await db.users.find_one({"user_id": user_id})
    if not user or not user.get("web_push_subscription"):
        return False
    
    return web_push_service.send_notification(
        subscription=user["web_push_subscription"],
        title=title,
        body=body,
        url=url
    )

# Note: Routers are included at the end of the file after all endpoints are defined

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

# =======================
# PARTNER (SOCIO) ENDPOINTS
# =======================

class AssignPartnerRoleRequest(BaseModel):
    user_id: str
    referral_code: Optional[str] = None

@api_router.post("/admin/assign-partner")
async def assign_partner_role(request: AssignPartnerRoleRequest, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Assign 'socio' role to a user"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.get("role") == "socio":
        raise HTTPException(status_code=400, detail="El usuario ya es socio")
    
    # Generate unique referral code if not provided
    referral_code = request.referral_code
    if not referral_code:
        # Generate code from name + random
        name_part = ''.join(user.get("name", "USER").split()).upper()[:4]
        random_part = uuid.uuid4().hex[:4].upper()
        referral_code = f"{name_part}{random_part}"
    
    # Ensure code is unique
    existing = await db.users.find_one({"referral_code": referral_code})
    if existing:
        referral_code = f"{referral_code}{uuid.uuid4().hex[:2].upper()}"
    
    await db.users.update_one(
        {"user_id": request.user_id},
        {"$set": {
            "role": "socio",
            "referral_code": referral_code.upper(),
            "became_partner_at": datetime.now(timezone.utc)
        }}
    )
    
    # Notify the new partner
    await create_notification(
        user_id=request.user_id,
        title="🎉 ¡Eres Socio!",
        message=f"Tu cuenta ha sido promovida a Socio. Tu código de referido es: {referral_code.upper()}. ¡Compártelo y gana comisiones!",
        notification_type="partner_assigned",
        data={"referral_code": referral_code.upper()}
    )
    
    logger.info(f"User {request.user_id} assigned as partner with code {referral_code}")
    
    return {
        "message": "Usuario asignado como socio exitosamente",
        "referral_code": referral_code.upper()
    }

@api_router.delete("/admin/remove-partner/{user_id}")
async def remove_partner_role(user_id: str, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Remove 'socio' role from a user"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.get("role") != "socio":
        raise HTTPException(status_code=400, detail="El usuario no es socio")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "role": "user",
            "referral_code": None
        }}
    )
    
    return {"message": "Rol de socio removido exitosamente"}

@api_router.get("/admin/partners")
async def get_all_partners(admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Get all partners with their stats"""
    partners = await db.users.find({"role": "socio"}).to_list(500)
    
    result = []
    for partner in partners:
        partner_id = partner["user_id"]
        
        # Count referrals
        referrals_count = await db.users.count_documents({"referred_by": partner_id})
        
        # Calculate total earnings
        earnings = await db.referral_earnings.find({"partner_id": partner_id}).to_list(1000)
        total_earnings = sum(e.get("amount", 0) for e in earnings)
        
        # This month earnings
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_earnings = sum(e.get("amount", 0) for e in earnings if e.get("created_at", datetime.min.replace(tzinfo=timezone.utc)) >= month_start)
        
        result.append({
            "user_id": partner_id,
            "name": partner.get("name", ""),
            "email": partner.get("email", ""),
            "referral_code": partner.get("referral_code", ""),
            "referrals_count": referrals_count,
            "total_earnings": round(total_earnings, 2),
            "month_earnings": round(month_earnings, 2),
            "balance_ris": partner.get("balance_ris", 0),
            "became_partner_at": partner.get("became_partner_at"),
            "created_at": partner.get("created_at")
        })
    
    return result

class ChangeUserRoleRequest(BaseModel):
    user_id: str
    new_role: str  # user, socio, socio_gestor
    referral_code: Optional[str] = None  # For socio
    gestor_code: Optional[str] = None  # For socio_gestor

@api_router.post("/admin/change-role")
async def change_user_role(request: ChangeUserRoleRequest, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Change user role to any allowed role"""
    allowed_roles = ["user", "socio", "socio_gestor"]
    if request.new_role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Rol no válido. Roles permitidos: {', '.join(allowed_roles)}")
    
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    current_role = user.get("role", "user")
    if current_role in ["admin", "super_admin"]:
        raise HTTPException(status_code=400, detail="No se puede cambiar el rol de administradores")
    
    if current_role == request.new_role:
        raise HTTPException(status_code=400, detail=f"El usuario ya tiene el rol '{request.new_role}'")
    
    update_data = {
        "role": request.new_role,
        "role_updated_at": datetime.now(timezone.utc),
        "role_updated_by": admin_user.user_id
    }
    
    # Handle specific role requirements
    if request.new_role == "socio":
        # Generate referral code
        referral_code = request.referral_code
        if not referral_code:
            name_part = ''.join(user.get("name", "USER").split()).upper()[:4]
            random_part = uuid.uuid4().hex[:4].upper()
            referral_code = f"{name_part}{random_part}"
        
        existing = await db.users.find_one({"referral_code": referral_code})
        if existing:
            referral_code = f"{referral_code}{uuid.uuid4().hex[:2].upper()}"
        
        update_data["referral_code"] = referral_code.upper()
        update_data["became_partner_at"] = datetime.now(timezone.utc)
        # Clear gestor fields
        update_data["gestor_code"] = None
        
    elif request.new_role == "socio_gestor":
        # Generate gestor code
        gestor_code = request.gestor_code
        if not gestor_code:
            name_part = ''.join(user.get("name", "GESTOR").split()).upper()[:4]
            random_part = uuid.uuid4().hex[:4].upper()
            gestor_code = f"G{name_part}{random_part}"
        
        update_data["gestor_code"] = gestor_code.upper()
        update_data["became_gestor_at"] = datetime.now(timezone.utc)
        # Clear socio fields
        update_data["referral_code"] = None
        
    else:  # user
        # Clear all special role fields
        update_data["referral_code"] = None
        update_data["gestor_code"] = None
    
    await db.users.update_one({"user_id": request.user_id}, {"$set": update_data})
    
    # Send notification to user
    role_names = {
        "user": "Usuario",
        "socio": "Socio (Referidor)",
        "socio_gestor": "Socio Gestor"
    }
    
    notification_messages = {
        "user": "Tu rol ha sido cambiado a Usuario normal.",
        "socio": f"¡Felicidades! Ahora eres Socio. Tu código de referido es: {update_data.get('referral_code', '')}. ¡Compártelo y gana comisiones!",
        "socio_gestor": f"¡Felicidades! Ahora eres Socio Gestor. Código: {update_data.get('gestor_code', '')}. Puedes procesar remesas de terceros."
    }
    
    await create_notification(
        user_id=request.user_id,
        title=f"🎉 Rol Actualizado: {role_names[request.new_role]}",
        message=notification_messages[request.new_role],
        notification_type="role_changed",
        data={"new_role": request.new_role}
    )
    
    logger.info(f"User {request.user_id} role changed from '{current_role}' to '{request.new_role}' by {admin_user.user_id}")
    
    return {
        "message": f"Rol cambiado exitosamente a '{role_names[request.new_role]}'",
        "new_role": request.new_role,
        "referral_code": update_data.get("referral_code"),
        "gestor_code": update_data.get("gestor_code")
    }

class AdminResetPasswordRequest(BaseModel):
    user_id: str

@api_router.post("/admin/reset-password")
async def admin_reset_user_password(request: AdminResetPasswordRequest, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Reset user password to a temporary one-time password"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.get("role") in ["admin", "super_admin"]:
        raise HTTPException(status_code=400, detail="No se puede restablecer la contraseña de administradores")
    
    # Generate temporary password (8 characters: letters and numbers)
    import random
    import string
    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Hash the temporary password
    hashed_password = hash_password(temp_password)
    
    # Update user with temporary password and flag
    await db.users.update_one(
        {"user_id": request.user_id},
        {"$set": {
            "password_hash": hashed_password,
            "must_change_password": True,
            "password_reset_at": datetime.now(timezone.utc),
            "password_reset_by": admin_user.user_id
        }}
    )
    
    # Send notification to user
    await create_notification(
        user_id=request.user_id,
        title="🔐 Contraseña Restablecida",
        message="Tu contraseña ha sido restablecida por un administrador. Al iniciar sesión, deberás establecer una nueva contraseña.",
        notification_type="password_reset",
        data={}
    )
    
    # Also send email with temporary password
    user_email = user.get("email")
    user_name = user.get("name", "Usuario")
    
    if user_email and RESEND_API_KEY:
        try:
            email_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                    .container {{ max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 30px; }}
                    .password-box {{ background: #f3f4f6; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0; }}
                    .temp-password {{ font-size: 28px; font-weight: 700; letter-spacing: 3px; color: #111827; font-family: monospace; }}
                    .warning {{ background: #fef3c7; border-radius: 8px; padding: 12px; margin-top: 16px; font-size: 13px; color: #92400e; }}
                    .footer {{ text-align: center; padding: 20px; color: #9ca3af; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">RIS App</h1>
                    </div>
                    <div class="content">
                        <p style="font-size: 16px; color: #374151;">Hola {user_name},</p>
                        <p style="font-size: 15px; color: #374151; line-height: 1.6;">
                            Tu contraseña ha sido restablecida por un administrador. Usa la siguiente contraseña temporal para iniciar sesión:
                        </p>
                        <div class="password-box">
                            <p style="font-size: 12px; color: #6b7280; margin: 0 0 8px 0;">Contraseña temporal:</p>
                            <p class="temp-password">{temp_password}</p>
                        </div>
                        <div class="warning">
                            ⚠️ Esta contraseña es de <strong>un solo uso</strong>. Al iniciar sesión, deberás establecer una nueva contraseña.
                        </div>
                    </div>
                    <div class="footer">
                        © 2025 RIS App - Todos los derechos reservados
                    </div>
                </div>
            </body>
            </html>
            """
            
            email_params = {
                "from": SENDER_EMAIL,
                "to": [user_email],
                "subject": "🔐 Tu contraseña temporal - RIS App",
                "html": email_html
            }
            
            await asyncio.to_thread(resend.Emails.send, email_params)
            logger.info(f"Temporary password email sent to {user_email}")
        except Exception as e:
            logger.error(f"Error sending password reset email: {e}")
    
    logger.info(f"Password reset for user {request.user_id} by admin {admin_user.user_id}")
    
    return {
        "message": "Contraseña restablecida exitosamente",
        "temp_password": temp_password,
        "email_sent": bool(user_email and RESEND_API_KEY)
    }

@api_router.get("/admin/partners/{partner_id}/referrals")
async def get_partner_referrals(partner_id: str, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Get all users referred by a specific partner"""
    partner = await db.users.find_one({"user_id": partner_id, "role": "socio"})
    if not partner:
        raise HTTPException(status_code=404, detail="Socio no encontrado")
    
    referrals = await db.users.find({"referred_by": partner_id}).to_list(500)
    
    result = []
    for user in referrals:
        result.append({
            "user_id": user["user_id"],
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "total_recharged": user.get("total_recharged", 0),
            "bonus_milestone_reached": user.get("referral_bonus_paid", False),
            "created_at": user.get("created_at"),
            "is_active": user.get("is_active", True)
        })
    
    return {
        "partner": {
            "user_id": partner_id,
            "name": partner.get("name", ""),
            "referral_code": partner.get("referral_code", "")
        },
        "referrals": result
    }

@api_router.get("/partner/dashboard")
async def get_partner_dashboard(current_user: User = Depends(get_current_user)):
    """Partner: Get own referral dashboard"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio":
        raise HTTPException(status_code=403, detail="Acceso solo para socios")
    
    partner_id = current_user.user_id
    referral_code = user.get("referral_code", "")
    
    # Get referrals
    referrals = await db.users.find({"referred_by": partner_id}).to_list(500)
    
    # Get earnings
    earnings = await db.referral_earnings.find({"partner_id": partner_id}).sort("created_at", -1).to_list(100)
    
    # Calculate stats
    total_earnings = sum(e.get("amount", 0) for e in earnings)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_earnings = sum(e.get("amount", 0) for e in earnings if e.get("created_at", datetime.min.replace(tzinfo=timezone.utc)) >= month_start)
    
    # Active referrals (those who have recharged)
    active_referrals = len([r for r in referrals if r.get("total_recharged", 0) > 0])
    
    # Referrals list
    referrals_list = []
    for r in referrals:
        referrals_list.append({
            "name": r.get("name", "Usuario"),
            "total_recharged": r.get("total_recharged", 0),
            "milestone_reached": r.get("referral_bonus_paid", False),
            "created_at": r.get("created_at")
        })
    
    # Recent earnings
    recent_earnings = []
    for e in earnings[:20]:
        recent_earnings.append({
            "type": e.get("type"),
            "amount": e.get("amount", 0),
            "referred_user_name": e.get("referred_user_name", ""),
            "created_at": e.get("created_at")
        })
    
    return {
        "referral_code": referral_code,
        "referral_link": f"https://www.risappbr.com/register?ref={referral_code}",
        "stats": {
            "total_referrals": len(referrals),
            "active_referrals": active_referrals,
            "total_earnings": round(total_earnings, 2),
            "month_earnings": round(month_earnings, 2)
        },
        "referrals": referrals_list,
        "recent_earnings": recent_earnings
    }

@api_router.get("/partner/referral-link")
async def get_referral_link(current_user: User = Depends(get_current_user)):
    """Partner: Get shareable referral link"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio":
        raise HTTPException(status_code=403, detail="Acceso solo para socios")
    
    referral_code = user.get("referral_code", "")
    
    return {
        "referral_code": referral_code,
        "referral_link": f"https://www.risappbr.com/register?ref={referral_code}"
    }

# =======================
# SOCIO GESTOR ENDPOINTS
# =======================

class SetGestorCommissionRequest(BaseModel):
    commission_percentage: float  # e.g., 5.0 for 5%

class AssignGestorRoleRequest(BaseModel):
    user_id: str

class GestorBeneficiaryRequest(BaseModel):
    full_name: str
    phone: str
    bank_name: str
    account_number: str
    cedula: str
    notes: Optional[str] = None

class GestorTransactionRequest(BaseModel):
    third_party_user_id: str  # The user who paid
    beneficiary_id: str  # Beneficiary in Venezuela
    amount_ris: float  # Amount in RIS
    amount_ves: float  # Amount in VES to send
    third_party_phone: Optional[str] = None  # For WhatsApp notification

@api_router.get("/admin/gestor-commission")
async def get_gestor_commission(admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Get current gestor commission rate"""
    settings = await db.app_settings.find_one({"setting_id": "gestor_commission"})
    if not settings:
        return {"commission_percentage": 5.0}  # Default 5%
    return {"commission_percentage": settings.get("value", 5.0)}

@api_router.post("/admin/gestor-commission")
async def set_gestor_commission(request: SetGestorCommissionRequest, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Set gestor commission rate"""
    if request.commission_percentage < 0 or request.commission_percentage > 50:
        raise HTTPException(status_code=400, detail="La comisión debe estar entre 0% y 50%")
    
    await db.app_settings.update_one(
        {"setting_id": "gestor_commission"},
        {"$set": {
            "setting_id": "gestor_commission",
            "value": request.commission_percentage,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": admin_user.user_id
        }},
        upsert=True
    )
    
    logger.info(f"Gestor commission set to {request.commission_percentage}% by {admin_user.user_id}")
    return {"message": f"Comisión de gestor establecida en {request.commission_percentage}%"}

@api_router.post("/admin/assign-gestor")
async def assign_gestor_role(request: AssignGestorRoleRequest, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Assign 'socio_gestor' role to a user"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.get("role") == "socio_gestor":
        raise HTTPException(status_code=400, detail="El usuario ya es socio gestor")
    
    # Generate unique gestor code
    name_part = ''.join(user.get("name", "GESTOR").split()).upper()[:4]
    random_part = uuid.uuid4().hex[:4].upper()
    gestor_code = f"G{name_part}{random_part}"
    
    await db.users.update_one(
        {"user_id": request.user_id},
        {"$set": {
            "role": "socio_gestor",
            "gestor_code": gestor_code,
            "became_gestor_at": datetime.now(timezone.utc)
        }}
    )
    
    # Notify the new gestor
    await create_notification(
        user_id=request.user_id,
        title="🏪 ¡Eres Socio Gestor!",
        message=f"Tu cuenta ha sido promovida a Socio Gestor. Código: {gestor_code}. Ahora puedes procesar remesas de terceros.",
        notification_type="gestor_assigned",
        data={"gestor_code": gestor_code}
    )
    
    logger.info(f"User {request.user_id} assigned as gestor with code {gestor_code}")
    return {"message": "Usuario asignado como socio gestor exitosamente", "gestor_code": gestor_code}

@api_router.delete("/admin/remove-gestor/{user_id}")
async def remove_gestor_role(user_id: str, admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Remove 'socio_gestor' role from a user"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.get("role") != "socio_gestor":
        raise HTTPException(status_code=400, detail="El usuario no es socio gestor")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": "user", "gestor_code": None}}
    )
    
    return {"message": "Rol de socio gestor removido exitosamente"}

@api_router.get("/admin/gestors")
async def get_all_gestors(admin_user: User = Depends(get_super_admin)):
    """SuperAdmin: Get all gestors with their stats"""
    gestors = await db.users.find({"role": "socio_gestor"}).to_list(500)
    
    result = []
    for gestor in gestors:
        gestor_id = gestor["user_id"]
        
        # Count transactions processed
        tx_count = await db.gestor_transactions.count_documents({"gestor_id": gestor_id})
        
        # Calculate total volume
        transactions = await db.gestor_transactions.find({"gestor_id": gestor_id}).to_list(1000)
        total_volume = sum(t.get("amount_ris", 0) for t in transactions)
        
        result.append({
            "user_id": gestor_id,
            "name": gestor.get("name", ""),
            "email": gestor.get("email", ""),
            "gestor_code": gestor.get("gestor_code", ""),
            "transactions_count": tx_count,
            "total_volume": round(total_volume, 2),
            "balance_ris": gestor.get("balance_ris", 0),
            "became_gestor_at": gestor.get("became_gestor_at"),
            "created_at": gestor.get("created_at")
        })
    
    return result

# Gestor own endpoints
@api_router.get("/gestor/dashboard")
async def get_gestor_dashboard(current_user: User = Depends(get_current_user)):
    """Gestor: Get own dashboard"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    
    gestor_id = current_user.user_id
    
    # Get commission rate
    settings = await db.app_settings.find_one({"setting_id": "gestor_commission"})
    commission = settings.get("value", 5.0) if settings else 5.0
    
    # Get beneficiaries
    beneficiaries = await db.gestor_beneficiaries.find({"gestor_id": gestor_id}).to_list(100)
    
    # Get recent transactions
    transactions = await db.gestor_transactions.find({"gestor_id": gestor_id}).sort("created_at", -1).limit(20).to_list(20)
    
    # Stats
    all_tx = await db.gestor_transactions.find({"gestor_id": gestor_id}).to_list(1000)
    total_volume = sum(t.get("amount_ris", 0) for t in all_tx)
    
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_tx = [t for t in all_tx if t.get("created_at", datetime.min.replace(tzinfo=timezone.utc)) >= month_start]
    month_volume = sum(t.get("amount_ris", 0) for t in month_tx)
    
    # Format beneficiaries
    beneficiaries_list = []
    for b in beneficiaries:
        beneficiaries_list.append({
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "phone": b.get("phone"),
            "bank_name": b.get("bank_name"),
            "account_number": b.get("account_number")[-4:] if b.get("account_number") else "",
            "cedula": b.get("cedula"),
            "created_at": b.get("created_at")
        })
    
    # Format transactions
    transactions_list = []
    for t in transactions:
        transactions_list.append({
            "transaction_id": t.get("transaction_id"),
            "third_party_name": t.get("third_party_name"),
            "beneficiary_name": t.get("beneficiary_name"),
            "amount_ris": t.get("amount_ris"),
            "amount_ves": t.get("amount_ves"),
            "status": t.get("status"),
            "created_at": t.get("created_at")
        })
    
    return {
        "gestor_code": user.get("gestor_code", ""),
        "balance_ris": user.get("balance_ris", 0),
        "commission_percentage": commission,
        "stats": {
            "total_transactions": len(all_tx),
            "total_volume": round(total_volume, 2),
            "month_transactions": len(month_tx),
            "month_volume": round(month_volume, 2)
        },
        "beneficiaries": beneficiaries_list,
        "recent_transactions": transactions_list
    }

@api_router.post("/gestor/beneficiaries")
async def add_gestor_beneficiary(request: GestorBeneficiaryRequest, current_user: User = Depends(get_current_user)):
    """Gestor: Add a new beneficiary"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    
    beneficiary_id = f"gben_{uuid.uuid4().hex[:12]}"
    
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "gestor_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "phone": request.phone.strip(),
        "bank_name": request.bank_name.strip(),
        "account_number": request.account_number.strip(),
        "cedula": request.cedula.strip(),
        "notes": request.notes,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.gestor_beneficiaries.insert_one(beneficiary)
    
    logger.info(f"Gestor {current_user.user_id} added beneficiary {beneficiary_id}")
    return {"message": "Beneficiario agregado exitosamente", "beneficiary_id": beneficiary_id}

@api_router.get("/gestor/beneficiaries")
async def get_gestor_beneficiaries(current_user: User = Depends(get_current_user)):
    """Gestor: Get all beneficiaries"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    
    beneficiaries = await db.gestor_beneficiaries.find({"gestor_id": current_user.user_id}).to_list(100)
    
    result = []
    for b in beneficiaries:
        result.append({
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "phone": b.get("phone"),
            "bank_name": b.get("bank_name"),
            "account_number": b.get("account_number"),
            "cedula": b.get("cedula"),
            "notes": b.get("notes"),
            "created_at": b.get("created_at")
        })
    
    return result

@api_router.post("/gestor/process-transaction")
async def process_gestor_transaction(request: GestorTransactionRequest, current_user: User = Depends(get_current_user)):
    """Gestor: Process a third-party transaction"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    
    # Check gestor has enough balance
    if user.get("balance_ris", 0) < request.amount_ris:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para procesar esta transacción")
    
    # Verify third party user exists
    third_party = await db.users.find_one({"user_id": request.third_party_user_id})
    if not third_party:
        raise HTTPException(status_code=404, detail="Usuario tercero no encontrado")
    
    # Verify beneficiary exists
    beneficiary = await db.gestor_beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "gestor_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")
    
    # Get commission rate
    settings = await db.app_settings.find_one({"setting_id": "gestor_commission"})
    commission_rate = settings.get("value", 5.0) / 100 if settings else 0.05
    commission_amount = request.amount_ris * commission_rate
    
    # Create transaction
    tx_id = f"gtx_{uuid.uuid4().hex[:12]}"
    
    gestor_transaction = {
        "transaction_id": tx_id,
        "gestor_id": current_user.user_id,
        "gestor_name": user.get("name", ""),
        "third_party_user_id": request.third_party_user_id,
        "third_party_name": third_party.get("name", ""),
        "third_party_phone": request.third_party_phone or third_party.get("phone", ""),
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_name": beneficiary.get("full_name", ""),
        "beneficiary_phone": beneficiary.get("phone", ""),
        "beneficiary_bank": beneficiary.get("bank_name", ""),
        "beneficiary_account": beneficiary.get("account_number", ""),
        "amount_ris": request.amount_ris,
        "amount_ves": request.amount_ves,
        "commission_rate": commission_rate * 100,
        "commission_amount": commission_amount,
        "status": "pending",  # pending -> processing -> completed
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.gestor_transactions.insert_one(gestor_transaction)
    
    # Deduct from gestor balance
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$inc": {"balance_ris": -request.amount_ris}}
    )
    
    # Create corresponding withdrawal transaction for admin to process
    withdrawal_tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    withdrawal = {
        "transaction_id": withdrawal_tx_id,
        "user_id": current_user.user_id,  # Gestor is the user for admin panel
        "type": "withdrawal_ves",
        "status": "pending",
        "amount_input": request.amount_ris,
        "amount_output": request.amount_ves,
        "beneficiary_id": request.beneficiary_id,
        "gestor_transaction_id": tx_id,  # Link to gestor transaction
        "is_gestor_transaction": True,
        "third_party_user_id": request.third_party_user_id,
        "third_party_name": third_party.get("name", ""),
        "third_party_phone": request.third_party_phone or third_party.get("phone", ""),
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(withdrawal)
    
    # Notify gestor
    await create_notification(
        user_id=current_user.user_id,
        title="📤 Transacción Registrada",
        message=f"Envío de {request.amount_ves:.2f} VES a {beneficiary.get('full_name')} registrado. Pendiente de procesamiento.",
        notification_type="gestor_transaction",
        data={"transaction_id": tx_id, "amount_ves": request.amount_ves}
    )
    
    logger.info(f"Gestor transaction {tx_id} created by {current_user.user_id}")
    
    return {
        "message": "Transacción registrada exitosamente",
        "transaction_id": tx_id,
        "withdrawal_id": withdrawal_tx_id,
        "amount_ris": request.amount_ris,
        "amount_ves": request.amount_ves,
        "commission": commission_amount,
        "beneficiary": beneficiary.get("full_name")
    }

@api_router.get("/gestor/transactions")
async def get_gestor_transactions(current_user: User = Depends(get_current_user)):
    """Gestor: Get all transactions"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    
    transactions = await db.gestor_transactions.find({"gestor_id": current_user.user_id}).sort("created_at", -1).to_list(100)
    
    result = []
    for t in transactions:
        result.append({
            "transaction_id": t.get("transaction_id"),
            "third_party_name": t.get("third_party_name"),
            "beneficiary_name": t.get("beneficiary_name"),
            "amount_ris": t.get("amount_ris"),
            "amount_ves": t.get("amount_ves"),
            "commission_amount": t.get("commission_amount"),
            "status": t.get("status"),
            "voucher_url": t.get("voucher_url"),
            "created_at": t.get("created_at"),
            "completed_at": t.get("completed_at")
        })
    
    return result

# Include the routers in the main app (must be after all endpoints are defined)
app.include_router(api_router)
app.include_router(admin_router)

@app.on_event("startup")
async def startup_db_client():
    """Create database indexes on startup"""
    try:
        # Create unique index for email (sparse to allow nulls)
        await db.users.create_index("email", unique=True, sparse=True)
        # Create index for cpf_number (not unique due to existing duplicates)
        # Validation is done at application level
        await db.users.create_index("cpf_number", sparse=True)
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
# Last update: 2026-02-22T21:10:38Z - Support chat fix
