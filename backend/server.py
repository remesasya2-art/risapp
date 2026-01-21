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
    full_name: Optional[str] = None  # For card validation
    document_number: Optional[str] = None
    cpf_number: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None  # admin user_id
    rejection_reason: Optional[str] = None
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
    
    # Send WhatsApp notification to team
    try:
        await whatsapp_service.send_withdrawal_notification(
            transaction.dict(),
            current_user.dict()
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