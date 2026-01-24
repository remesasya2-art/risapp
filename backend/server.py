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
import stripe
import json
import base64
from openpyxl import Workbook
from io import BytesIO
from whatsapp_service import whatsapp_service

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Stripe configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_placeholder')

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer()

# =======================
# MODELS
# =======================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    balance_ris: float = 0.0
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    """Check if user is admin"""
    # In production, check if user has admin role
    # For now, we'll check if email contains 'admin'
    if 'admin' not in current_user.email.lower():
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

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
        
        return SessionDataResponse(**user_data)
    except Exception as e:
        logging.error(f"Session creation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

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
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {
            "full_name": request.full_name,
            "document_number": request.document_number,
            "cpf_number": request.cpf_number,
            "id_document_image": request.id_document_image,
            "cpf_image": request.cpf_image,
            "selfie_image": request.selfie_image,
            "verification_status": "pending",
            "accepted_declaration": True,
            "declaration_accepted_at": datetime.now(timezone.utc)
        }}
    )
    
    return {"message": "Verification submitted successfully. Please wait for admin approval."}

@api_router.get("/verification/status")
async def get_verification_status(current_user: User = Depends(get_current_user)):
    """Get current verification status"""
    return {
        "status": current_user.verification_status,
        "rejection_reason": current_user.rejection_reason
    }

@api_router.get("/admin/verifications/pending")
async def get_pending_verifications(admin_user: User = Depends(get_admin_user)):
    """Admin: Get all pending verifications"""
    users = await db.users.find(
        {"verification_status": "pending"},
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
            "created_at": 1
        }
    ).to_list(1000)
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
    
    return {"message": f"User {'approved' if decision.approved else 'rejected'} successfully"}

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
# STRIPE/RECHARGE ROUTES
# =======================

@api_router.post("/recharge/create-payment-intent")
async def create_payment_intent(request: RechargeRequest, current_user: User = Depends(get_current_user)):
    """Create Stripe payment intent for recharge"""
    try:
        # Validate amount (max 2000 REAIS, min 0.50 REAIS)
        if request.amount > 2000:
            raise HTTPException(status_code=400, detail="Maximum recharge is 2000 REAIS")
        if request.amount < 0.50:
            raise HTTPException(status_code=400, detail="Minimum recharge is 0.50 REAIS")
        
        # Convert to cents (Stripe expects minor units)
        amount_cents = int(request.amount * 100)
        
        # Create payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="brl",
            metadata={
                "user_id": current_user.user_id,
                "type": "recharge"
            },
            automatic_payment_methods={"enabled": True}
        )
        
        # Create pending transaction
        transaction = Transaction(
            user_id=current_user.user_id,
            type="recharge",
            status="pending",
            amount_input=request.amount,
            amount_output=request.amount,  # 1:1 ratio
            stripe_payment_intent_id=payment_intent.id
        )
        await db.transactions.insert_one(transaction.dict())
        
        return {
            "clientSecret": payment_intent.client_secret,
            "transaction_id": transaction.transaction_id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Payment intent creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/recharge/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET', '')
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle payment_intent.succeeded
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        
        # Find transaction
        transaction = await db.transactions.find_one(
            {"stripe_payment_intent_id": payment_intent.id},
            {"_id": 0}
        )
        
        if transaction:
            # Update transaction status
            await db.transactions.update_one(
                {"stripe_payment_intent_id": payment_intent.id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc)
                }}
            )
            
            # Update user balance
            await db.users.update_one(
                {"user_id": transaction["user_id"]},
                {"$inc": {"balance_ris": transaction["amount_output"]}}
            )
            
            # TODO: Send notification to user
    
    return {"status": "success"}

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
        # Enhanced message with clear instructions
        message = f"""🔔 *NUEVO RETIRO PENDIENTE*

💰 Monto: {request.amount_ris:.2f} RIS → {amount_ves:.2f} VES
👤 Usuario: {current_user.name}
📧 Email: {current_user.email}

📋 *BENEFICIARIO:*
Nombre: {request.beneficiary_data.get('full_name')}
Banco: {request.beneficiary_data.get('bank')}
Cuenta: {request.beneficiary_data.get('account_number')}
Cédula: {request.beneficiary_data.get('id_document')}
Teléfono: {request.beneficiary_data.get('phone_number')}

🆔 ID: {transaction.transaction_id}

---
✅ Opción 1: Responde con foto del comprobante
✅ Opción 2: Procesa en admin panel"""

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
        
        logger.info(f"WhatsApp webhook received from {from_number}: {body}")
        logger.info(f"NumMedia: {num_media}")
        
        # Check if message has media (image)
        if num_media > 0:
            media_url = form_data.get('MediaUrl0', '')
            media_content_type = form_data.get('MediaContentType0', '')
            
            logger.info(f"Media received: {media_url} ({media_content_type})")
            
            # Download the image
            if media_url and 'image' in media_content_type:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    # Twilio requires authentication to download media
                    auth = (
                        os.getenv('TWILIO_ACCOUNT_SID'),
                        os.getenv('TWILIO_AUTH_TOKEN')
                    )
                    response = await client.get(media_url, auth=auth)
                    
                    logger.info(f"Media download response: {response.status_code}")
                    
                    if response.status_code == 200:
                        # Convert to base64
                        import base64
                        image_base64 = f"data:{media_content_type};base64,{base64.b64encode(response.content).decode()}"
                        
                        logger.info("Image downloaded and converted to base64")
                        
                        # Extract transaction ID from message body
                        # Look for pattern like "ID: abc123def456" or just the ID
                        transaction_id = None
                        if body:
                            # Try to extract ID from body
                            import re
                            match = re.search(r'ID[:\s]*([a-f0-9]{24})', body, re.IGNORECASE)
                            if match:
                                transaction_id = match.group(1)
                                logger.info(f"Transaction ID extracted from message: {transaction_id}")
                        
                        # If no ID in current message, find the most recent pending transaction
                        if not transaction_id:
                            logger.info("No ID in message, looking for most recent pending withdrawal...")
                            recent_withdrawal = await db.transactions.find_one(
                                {"type": "withdrawal", "status": "pending"},
                                sort=[("created_at", -1)]
                            )
                            if recent_withdrawal:
                                transaction_id = str(recent_withdrawal['_id'])
                                logger.info(f"Found pending transaction: {transaction_id}")
                        
                        if transaction_id:
                            # Update transaction with proof image using _id
                            from bson import ObjectId
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
                                logger.info(f"Transaction {transaction_id} marked as completed via WhatsApp")
                                
                                # Get transaction and user info for push notification
                                completed_tx = await db.transactions.find_one({"_id": ObjectId(transaction_id)})
                                if completed_tx:
                                    user_id = completed_tx.get('user_id')
                                    if user_id:
                                        user = await db.users.find_one({"user_id": user_id})
                                        if user and user.get('fcm_token'):
                                            # Send push notification
                                            from firebase_service import push_service
                                            beneficiary = completed_tx.get('beneficiary_data', {})
                                            await push_service.send_withdrawal_completed_notification(
                                                fcm_token=user['fcm_token'],
                                                transaction_id=transaction_id,
                                                amount_ris=completed_tx.get('amount_input', 0),
                                                amount_ves=completed_tx.get('amount_output', 0),
                                                beneficiary_name=beneficiary.get('full_name', 'Beneficiario')
                                            )
                                            logger.info(f"Push notification sent to user {user_id}")
                                
                                # Send confirmation back via WhatsApp
                                from twilio.rest import Client
                                twilio_client = Client(
                                    os.getenv('TWILIO_ACCOUNT_SID'),
                                    os.getenv('TWILIO_AUTH_TOKEN')
                                )
                                
                                twilio_client.messages.create(
                                    from_=os.getenv('TWILIO_WHATSAPP_FROM'),
                                    body=f"✅ Retiro {transaction_id[:8]}... procesado exitosamente. Usuario notificado.",
                                    to=from_number
                                )
                                logger.info("Confirmation message sent via WhatsApp")
                            else:
                                logger.warning(f"No pending transaction found with ID {transaction_id}")
                        else:
                            logger.warning("Could not find any pending transaction to process")
                    else:
                        logger.error(f"Failed to download media: {response.status_code}")
        else:
            logger.info("No media in message, ignoring")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}

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

# Include the router in the main app
app.include_router(api_router)

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