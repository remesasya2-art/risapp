"""
RIS App Backend - Clean Server
Main FastAPI application entry point.
Most endpoints have been migrated to modular routers in /routes/
"""
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer
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
import json
import base64
from openpyxl import Workbook
from io import BytesIO
import bcrypt
import secrets
import re
from twilio.rest import Client as TwilioClient
from whatsapp_service import whatsapp_service
from mercadopago_service import mercadopago_service
from admin_routes import admin_router
from web_push_service import web_push_service
import asyncio
import resend

# Import modular routers
from routes import api_router as modular_api_router
from routes.gestor_pix import router as gestor_pix_router, webhook_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
TWILIO_WHATSAPP_TO = os.getenv('TWILIO_WHATSAPP_TO')

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Resend Email Configuration
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'noreply@risappbr.com')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Create FastAPI app
app = FastAPI(title="RIS App API", version="2.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create router for endpoints not yet migrated to modular structure
legacy_router = APIRouter(prefix="/api")
security = HTTPBearer()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_current_user(request: Request, authorization: Optional[str] = Header(None)):
    """Get current user from session token"""
    session_token = None
    session_token = request.cookies.get('session_token')
    if not session_token and authorization:
        if authorization.startswith('Bearer '):
            session_token = authorization[7:]
    if not session_token:
        session_token = request.headers.get("X-Session-ID")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    expires_at = session.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
    
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

async def require_admin(current_user: dict = Depends(get_current_user)):
    """Require admin or super_admin role"""
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ============================================================================
# NOTIFICATION ENDPOINTS (Not yet migrated)
# ============================================================================

@legacy_router.get("/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    """Get user notifications"""
    notifications = await db.notifications.find(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return notifications

@legacy_router.get("/notifications/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    """Get unread notification count"""
    count = await db.notifications.count_documents({
        "user_id": current_user["user_id"],
        "read": False
    })
    return {"unread_count": count}

@legacy_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Mark notification as read"""
    await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user["user_id"]},
        {"$set": {"read": True}}
    )
    return {"success": True}

@legacy_router.post("/notifications/mark-all-read")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read"""
    await db.notifications.update_many(
        {"user_id": current_user["user_id"], "read": False},
        {"$set": {"read": True}}
    )
    return {"success": True}

# ============================================================================
# SUPPORT CHAT ENDPOINTS (Not yet migrated)
# ============================================================================

class SupportMessage(BaseModel):
    message: str

@legacy_router.post("/support/send")
async def send_support_message(msg: SupportMessage, current_user: dict = Depends(get_current_user)):
    """Send message to support"""
    message_doc = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "user_id": current_user["user_id"],
        "user_name": current_user.get("name", "Usuario"),
        "message": msg.message,
        "sender": "user",
        "created_at": datetime.now(timezone.utc),
        "read": False
    }
    await db.support_messages.insert_one(message_doc)
    
    # Mark chat as active
    await db.support_chats.update_one(
        {"user_id": current_user["user_id"]},
        {
            "$set": {
                "last_message": msg.message,
                "last_message_at": datetime.now(timezone.utc),
                "status": "active",
                "user_name": current_user.get("name", "Usuario")
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)}
        },
        upsert=True
    )
    return {"success": True, "message_id": message_doc["message_id"]}

@legacy_router.get("/support/history")
async def get_support_history(current_user: dict = Depends(get_current_user)):
    """Get support chat history"""
    messages = await db.support_messages.find(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    ).sort("created_at", 1).limit(100).to_list(100)
    return messages

@legacy_router.get("/support/conversation")
async def get_support_conversation(current_user: dict = Depends(get_current_user)):
    """Get support conversation status"""
    chat = await db.support_chats.find_one(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    )
    return chat or {"status": "none"}

# ============================================================================
# ADMIN SUPPORT ENDPOINTS (Not yet migrated)
# ============================================================================

@legacy_router.get("/admin/support/chats")
async def get_admin_support_chats(current_user: dict = Depends(require_admin)):
    """Get all support chats for admin"""
    chats = await db.support_chats.find(
        {},
        {"_id": 0}
    ).sort("last_message_at", -1).to_list(100)
    return chats

@legacy_router.get("/admin/support/chat/{user_id}")
async def get_admin_chat_messages(user_id: str, current_user: dict = Depends(require_admin)):
    """Get chat messages for a specific user"""
    messages = await db.support_messages.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return messages

class AdminSupportResponse(BaseModel):
    user_id: str
    message: str

@legacy_router.post("/admin/support/respond")
async def admin_respond(response: AdminSupportResponse, current_user: dict = Depends(require_admin)):
    """Admin responds to support chat"""
    message_doc = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "user_id": response.user_id,
        "admin_id": current_user["user_id"],
        "admin_name": current_user.get("name", "Admin"),
        "message": response.message,
        "sender": "admin",
        "created_at": datetime.now(timezone.utc),
        "read": False
    }
    await db.support_messages.insert_one(message_doc)
    
    # Update chat
    await db.support_chats.update_one(
        {"user_id": response.user_id},
        {"$set": {
            "last_message": response.message,
            "last_message_at": datetime.now(timezone.utc),
            "last_responder": current_user.get("name", "Admin")
        }}
    )
    return {"success": True}

class CloseChat(BaseModel):
    user_id: str

@legacy_router.post("/admin/support/close")
async def close_chat(data: CloseChat, current_user: dict = Depends(require_admin)):
    """Close a support chat"""
    await db.support_chats.update_one(
        {"user_id": data.user_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc)}}
    )
    return {"success": True}

# ============================================================================
# WEB PUSH ENDPOINTS (Not yet migrated)
# ============================================================================

@legacy_router.get("/push/web/vapid-public-key")
async def get_vapid_public_key():
    """Get VAPID public key for web push"""
    return {"public_key": web_push_service.get_public_key()}

class WebPushSubscription(BaseModel):
    endpoint: str
    keys: dict

@legacy_router.post("/push/web/subscribe")
async def subscribe_web_push(subscription: WebPushSubscription, current_user: dict = Depends(get_current_user)):
    """Subscribe to web push notifications"""
    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": subscription.keys
    }
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"web_push_subscription": sub_info}}
    )
    return {"success": True}

@legacy_router.post("/push/web/unsubscribe")
async def unsubscribe_web_push(current_user: dict = Depends(get_current_user)):
    """Unsubscribe from web push notifications"""
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$unset": {"web_push_subscription": ""}}
    )
    return {"success": True}

@legacy_router.get("/push/web/status")
async def get_web_push_status(current_user: dict = Depends(get_current_user)):
    """Check if user has web push subscription"""
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    return {"subscribed": "web_push_subscription" in user}

@legacy_router.post("/push/web/test")
async def test_web_push(current_user: dict = Depends(get_current_user)):
    """Test web push notification"""
    user = await db.users.find_one({"user_id": current_user["user_id"]})
    sub = user.get("web_push_subscription")
    if not sub:
        raise HTTPException(status_code=400, detail="No web push subscription")
    
    try:
        web_push_service.send_notification(sub, "Test", "Esta es una notificación de prueba")
        return {"success": True}
    except Exception as e:
        logger.error(f"Web push error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# POLICIES ENDPOINTS (Not yet migrated)
# ============================================================================

@legacy_router.get("/policies")
async def get_policies():
    """Get all policies"""
    policies = await db.policies.find({}, {"_id": 0}).to_list(10)
    return policies

class AcceptPolicy(BaseModel):
    policy_type: str

@legacy_router.post("/policies/accept")
async def accept_policy(data: AcceptPolicy, current_user: dict = Depends(get_current_user)):
    """Accept a policy"""
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$addToSet": {"accepted_policies": data.policy_type}}
    )
    return {"success": True}

@legacy_router.get("/policies/status")
async def get_policies_status(current_user: dict = Depends(get_current_user)):
    """Get user's policy acceptance status"""
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    return {"accepted_policies": user.get("accepted_policies", [])}

# ============================================================================
# VES PAYMENT INFO (Not yet migrated)
# ============================================================================

@legacy_router.get("/ves-payment-info")
async def get_ves_payment_info():
    """Get VES payment info for manual transfers"""
    info = await db.settings.find_one({"type": "ves_payment_info"}, {"_id": 0})
    return info or {
        "bank": "Banesco",
        "account_type": "Corriente",
        "account_number": "0134-0000-00-0000000000",
        "holder_name": "RIS APP C.A.",
        "holder_id": "J-00000000-0"
    }

# ============================================================================
# USER BALANCE (Not yet migrated)
# ============================================================================

@legacy_router.get("/user/balance")
async def get_user_balance(current_user: dict = Depends(get_current_user)):
    """Get user balance"""
    return {
        "balance_ris": current_user.get("balance_ris", 0),
        "balance_ris_terceros": current_user.get("balance_ris_terceros", 0),
        "balance_ves": current_user.get("balance_ves", 0)
    }

# ============================================================================
# VERIFICATION ENDPOINTS (Not yet migrated)
# ============================================================================

class VerificationSubmit(BaseModel):
    document_type: str
    document_number: str
    document_front: Optional[str] = None
    document_back: Optional[str] = None
    selfie: Optional[str] = None

@legacy_router.post("/verification/submit")
async def submit_verification(data: VerificationSubmit, current_user: dict = Depends(get_current_user)):
    """Submit identity verification"""
    verification = {
        "verification_id": f"ver_{uuid.uuid4().hex[:12]}",
        "user_id": current_user["user_id"],
        "document_type": data.document_type,
        "document_number": data.document_number,
        "document_front": data.document_front,
        "document_back": data.document_back,
        "selfie": data.selfie,
        "status": "pending",
        "submitted_at": datetime.now(timezone.utc)
    }
    await db.verifications.insert_one(verification)
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"verification_status": "pending"}}
    )
    return {"success": True, "verification_id": verification["verification_id"]}

@legacy_router.get("/verification/status")
async def get_verification_status(current_user: dict = Depends(get_current_user)):
    """Get verification status"""
    verification = await db.verifications.find_one(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    )
    return verification or {"status": "none"}

# ============================================================================
# TRANSACTIONS EXPORT (Not yet migrated)
# ============================================================================

@legacy_router.get("/transactions/export")
async def export_transactions(current_user: dict = Depends(require_admin)):
    """Export all transactions to Excel"""
    transactions = await db.transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Transacciones"
    
    headers = ["ID", "Usuario", "Tipo", "Monto RIS", "Monto VES", "Estado", "Fecha"]
    ws.append(headers)
    
    for tx in transactions:
        ws.append([
            tx.get("display_id", tx.get("transaction_id", ""))[:15],
            tx.get("user_email", ""),
            tx.get("type", ""),
            tx.get("amount_ris", 0),
            tx.get("amount_ves", 0),
            tx.get("status", ""),
            str(tx.get("created_at", ""))[:19]
        ])
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transacciones.xlsx"}
    )

# ============================================================================
# ADMIN DASHBOARD (Not yet migrated)
# ============================================================================

@legacy_router.get("/admin/dashboard")
async def get_admin_dashboard(current_user: dict = Depends(require_admin)):
    """Get admin dashboard stats"""
    # Count users
    total_users = await db.users.count_documents({"is_deleted": {"$ne": True}})
    verified_users = await db.users.count_documents({"verification_status": "verified"})
    
    # Count transactions
    pending_withdrawals = await db.transactions.count_documents({"type": "withdrawal", "status": "pending"})
    completed_today = await db.transactions.count_documents({
        "status": "completed",
        "completed_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)}
    })
    
    # Calculate volumes
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": None, "total_ris": {"$sum": "$amount_ris"}, "total_ves": {"$sum": "$amount_ves"}}}
    ]
    volume = await db.transactions.aggregate(pipeline).to_list(1)
    
    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "pending_withdrawals": pending_withdrawals,
        "completed_today": completed_today,
        "total_volume_ris": volume[0]["total_ris"] if volume else 0,
        "total_volume_ves": volume[0]["total_ves"] if volume else 0
    }

# ============================================================================
# WHATSAPP WEBHOOK (Critical - Keep here)
# ============================================================================

@legacy_router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp messages from Twilio"""
    try:
        form_data = await request.form()
        from_number = form_data.get("From", "")
        body = form_data.get("Body", "").strip()
        
        logger.info(f"WhatsApp webhook received from {from_number}: {body}")
        
        # Process the response
        # This handles withdrawal confirmations via WhatsApp
        if body.upper() in ["SI", "SÍ", "YES", "CONFIRMAR", "OK"]:
            # Find pending withdrawal for this number
            transaction = await db.transactions.find_one({
                "whatsapp_number": from_number.replace("whatsapp:", ""),
                "status": "pending_whatsapp_confirmation"
            })
            
            if transaction:
                await db.transactions.update_one(
                    {"transaction_id": transaction["transaction_id"]},
                    {"$set": {"status": "processing", "whatsapp_confirmed_at": datetime.now(timezone.utc)}}
                )
                logger.info(f"Transaction {transaction['transaction_id']} confirmed via WhatsApp")
        
        return {"success": True}
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"success": False}

# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

# Include modular routers (from routes/)
app.include_router(modular_api_router)

# Include legacy router (endpoints not yet migrated)
app.include_router(legacy_router)

# Include admin router (separate file)
app.include_router(admin_router)

# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_db_client():
    """Create database indexes on startup"""
    try:
        await db.users.create_index("email", unique=True, sparse=True)
        await db.users.create_index("cpf_number", sparse=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("expires_at")
        await db.transactions.create_index("user_id")
        await db.transactions.create_index("status")
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Last update: 2026-03-08 - Cleaned server.py, migrated to modular routers
