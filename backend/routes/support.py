"""
Support routes - Support chat system
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import db
from routes.dependencies import get_current_user, get_super_admin
from models.user import User
from services.whatsapp import send_whatsapp_notification
from services.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])


class SupportMessage(BaseModel):
    message: str


class AdminSupportResponse(BaseModel):
    user_id: str
    message: str


class CloseChat(BaseModel):
    user_id: str


# ============== USER SUPPORT ENDPOINTS ==============

@router.post("/support/send")
async def send_support_message(msg: SupportMessage, current_user: User = Depends(get_current_user)):
    """Send message to support"""
    message_doc = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "user_name": current_user.name or "Usuario",
        "user_email": current_user.email,
        "message": msg.message,
        "sender": "user",
        "created_at": datetime.now(timezone.utc),
        "read": False
    }
    await db.support_messages.insert_one(message_doc)
    
    # Mark chat as active
    await db.support_chats.update_one(
        {"user_id": current_user.user_id},
        {
            "$set": {
                "last_message": msg.message,
                "last_message_at": datetime.now(timezone.utc),
                "status": "active",
                "user_name": current_user.name or "Usuario",
                "user_email": current_user.email,
                "unread_count": 1
            },
            "$inc": {"total_messages": 1},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)}
        },
        upsert=True
    )
    
    # Send WhatsApp notification to admin
    whatsapp_message = f"""💬 NUEVO MENSAJE DE SOPORTE

👤 Usuario: {current_user.name or 'Usuario'}
📧 Email: {current_user.email}

📝 Mensaje:
{msg.message[:200]}{'...' if len(msg.message) > 200 else ''}

🔔 Responde desde el Panel de Admin"""
    
    await send_whatsapp_notification(whatsapp_message)
    
    # Create notification for all super admins
    admins = await db.users.find({"role": {"$in": ["super_admin", "admin"]}}).to_list(10)
    for admin in admins:
        await create_notification(
            user_id=admin.get("user_id"),
            title="💬 Nuevo mensaje de soporte",
            message=f"{current_user.name}: {msg.message[:50]}...",
            notification_type="support_message"
        )
    
    return {"success": True, "message_id": message_doc["message_id"]}


@router.get("/support/history")
async def get_support_history(current_user: User = Depends(get_current_user)):
    """Get support chat history"""
    messages = await db.support_messages.find(
        {"user_id": current_user.user_id},
        {"_id": 0}
    ).sort("created_at", 1).limit(100).to_list(100)
    return messages


@router.get("/support/conversation")
async def get_support_conversation(current_user: User = Depends(get_current_user)):
    """Get support conversation status"""
    chat = await db.support_chats.find_one(
        {"user_id": current_user.user_id},
        {"_id": 0}
    )
    return chat or {"status": "none"}


# ============== ADMIN SUPPORT ENDPOINTS ==============

@router.get("/admin/support/chats")
async def get_admin_support_chats(current_user: User = Depends(get_super_admin)):
    """Get all support chats for admin"""
    chats = await db.support_chats.find(
        {},
        {"_id": 0}
    ).sort("last_message_at", -1).to_list(100)
    return chats


@router.get("/admin/support/chat/{user_id}")
async def get_admin_chat_messages(user_id: str, current_user: User = Depends(get_super_admin)):
    """Get chat messages for a specific user"""
    messages = await db.support_messages.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return messages


@router.post("/admin/support/respond")
async def admin_respond(response: AdminSupportResponse, current_user: User = Depends(get_super_admin)):
    """Admin responds to support chat"""
    message_doc = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "user_id": response.user_id,
        "admin_id": current_user.user_id,
        "admin_name": current_user.name or "Admin",
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
            "last_responder": current_user.name or "Admin",
            "unread_count": 0
        }}
    )
    
    # Create notification for user
    await create_notification(
        user_id=response.user_id,
        title="💬 Respuesta de Soporte",
        message=f"{response.message[:50]}...",
        notification_type="support_response"
    )
    
    return {"success": True}


@router.post("/admin/support/close")
async def close_chat(data: CloseChat, current_user: User = Depends(get_super_admin)):
    """Close a support chat"""
    await db.support_chats.update_one(
        {"user_id": data.user_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc)}}
    )
    return {"success": True}
