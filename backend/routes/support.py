"""
Support routes - Support chat system
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from pydantic import BaseModel

from database import db
from routes.dependencies import get_current_user, get_super_admin, get_crm_user
from models.user import User
from services.notifications import create_notification
from services.imagen_recibida import ImagenInvalida, limpiar_imagen_opcional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])


class SupportMessage(BaseModel):
    message: str


class AdminSupportResponse(BaseModel):
    user_id: str
    message: str
    image: Optional[str] = None


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
async def get_admin_support_chats(current_user: User = Depends(get_crm_user)):
    """Get all support chats for admin"""
    chats = await db.support_chats.find(
        {},
        {"_id": 0}
    ).sort("last_message_at", -1).to_list(100)
    return chats


@router.get("/admin/support/chat/{user_id}")
async def get_admin_chat_messages(user_id: str, current_user: User = Depends(get_crm_user)):
    """Get chat messages for a specific user"""
    messages = await db.support_messages.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return messages


@router.post("/admin/support/respond")
async def admin_respond(response: AdminSupportResponse, current_user: User = Depends(get_crm_user)):
    """Admin responds to support chat"""
    # El adjunto se mira ANTES de guardarlo, igual que en la mesa de ayuda
    # nueva (`routes/soporte.py::_adjunto`). Acá se guardaba tal cual llegaba:
    # el campo es texto elegido por quien manda el mensaje y lo abre el otro,
    # así que un `javascript:…` escrito ahí quedaba en la base esperando a que
    # alguien abriera «la imagen». De paso entra el tope de tamaño, sin el cual
    # un `data:` grande empuja el documento contra el límite de 16 MB de Mongo
    # y lo que se rompe no es la subida sino la lectura de la conversación.
    try:
        imagen = limpiar_imagen_opcional(response.image, campo="La imagen")
    except ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))

    message_doc = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "user_id": response.user_id,
        "admin_id": current_user.user_id,
        "admin_name": current_user.name or "Admin",
        "message": response.message,
        "image": imagen,
        "sender": "admin",
        "created_at": datetime.now(timezone.utc),
        "read": False
    }
    await db.support_messages.insert_one(message_doc)
    
    # Update chat
    await db.support_chats.update_one(
        {"user_id": response.user_id},
        {"$set": {
            "last_message": response.message or "📷 Imagen",
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
async def close_chat(data: CloseChat, current_user: User = Depends(get_crm_user)):
    """Close a support chat"""
    await db.support_chats.update_one(
        {"user_id": data.user_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc)}}
    )
    return {"success": True}


# ============== QUICK REPLIES (respuestas rápidas compartidas) ==============
class QuickReplyCreate(BaseModel):
    text: str


DEFAULT_QUICK_REPLIES = [
    'Hola {nombre}, ¿en qué puedo ayudarte?',
    'Gracias por tu paciencia, {nombre}. Estoy revisando tu caso.',
    'Tu solicitud está siendo procesada. Te avisaremos al completarse.',
    'Para ayudarte mejor, ¿podrías enviarme una captura de pantalla?',
    '¿Hay algo más en lo que pueda ayudarte, {nombre}?',
    'Gracias por contactarnos. ¡Que tengas un buen día!',
]


@router.get("/admin/quick-replies")
async def get_quick_replies(current_user: User = Depends(get_crm_user)):
    """Lista las respuestas rápidas compartidas (siembra valores por defecto la primera vez)."""
    count = await db.quick_replies.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        seed = [
            {
                "qr_id": f"qr_{uuid.uuid4().hex[:12]}",
                "text": t,
                "created_by": "system",
                "created_by_name": "Sistema",
                "created_at": now,
            }
            for t in DEFAULT_QUICK_REPLIES
        ]
        if seed:
            await db.quick_replies.insert_many(seed)
    items = await db.quick_replies.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return items


@router.post("/admin/quick-replies")
async def create_quick_reply(data: QuickReplyCreate, current_user: User = Depends(get_crm_user)):
    """Crea una respuesta rápida compartida."""
    text = (data.text or "").strip()
    if not text:
        return {"success": False, "error": "empty"}
    doc = {
        "qr_id": f"qr_{uuid.uuid4().hex[:12]}",
        "text": text,
        "created_by": current_user.user_id,
        "created_by_name": current_user.name or "Admin",
        "created_at": datetime.now(timezone.utc),
    }
    await db.quick_replies.insert_one(doc)
    return {"success": True, "qr_id": doc["qr_id"], "text": text}


@router.delete("/admin/quick-replies/{qr_id}")
async def delete_quick_reply(qr_id: str, current_user: User = Depends(get_crm_user)):
    """Elimina una respuesta rápida compartida."""
    await db.quick_replies.delete_one({"qr_id": qr_id})
    return {"success": True}

# ============== ASIGNACIÓN DE CASOS DE CHAT (tomar / soltar) ==============

class ClaimChat(BaseModel):
    user_id: str

@router.post("/admin/support/claim")
async def claim_chat(data: ClaimChat, current_user: User = Depends(get_crm_user)):
    """Toma (claim) una conversación de chat de forma ATÓMICA: solo uno puede tomarla."""
    result = await db.support_chats.update_one(
        {"user_id": data.user_id, "$or": [{"assigned_to": None}, {"assigned_to": {"$exists": False}}, {"assigned_to": ""}]},
        {"$set": {
            "assigned_to": current_user.user_id,
            "assigned_to_name": current_user.name or "Operador",
            "assigned_at": datetime.now(timezone.utc),
        }}
    )
    if result.modified_count == 1:
        return {"success": True, "assigned_to": current_user.user_id, "assigned_to_name": current_user.name or "Operador"}
    existing = await db.support_chats.find_one({"user_id": data.user_id}, {"_id": 0, "assigned_to": 1, "assigned_to_name": 1})
    if existing and existing.get("assigned_to") == current_user.user_id:
        return {"success": True, "already_mine": True, "assigned_to": current_user.user_id, "assigned_to_name": current_user.name or "Operador"}
    return {"success": False, "assigned_to": (existing or {}).get("assigned_to"), "assigned_to_name": (existing or {}).get("assigned_to_name")}

@router.post("/admin/support/release")
async def release_chat(data: ClaimChat, current_user: User = Depends(get_crm_user)):
    """Suelta una conversación. Solo el dueño del caso o un super admin."""
    chat = await db.support_chats.find_one({"user_id": data.user_id}, {"_id": 0, "assigned_to": 1})
    if not chat:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    if chat.get("assigned_to") and chat.get("assigned_to") != current_user.user_id and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo quien atiende el caso o un super admin puede liberarlo")
    await db.support_chats.update_one(
        {"user_id": data.user_id},
        {"$set": {"assigned_to": None, "assigned_to_name": None, "assigned_at": None}}
    )
    return {"success": True}

# ============== CALIFICACIÓN DEL USUARIO (chat) ==============
#
# Acá vivía `POST /support/rate`, que calificaba EL CHAT del usuario. Se quitó
# porque con la mesa de ayuda por casos se podía calificar dos veces la misma
# atención: el cliente cuyo chat se migró califica su caso por
# `/soporte/casos/{caso_id}/calificar`, y además podía volver acá y calificar
# el chat original, que la migración deja intacto a propósito. Eran dos
# documentos en `ratings` por una sola conversación, y los dos entraban en el
# promedio del agente —así que un agente podía subir o bajar su nota según
# cuántos clientes pasaran por las dos puertas—.
#
# La calificación del chat viejo que YA estaba guardada no se toca: sigue en
# `ratings` y sigue contando una vez, que es lo correcto.
#
# No queda un endpoint devolviendo 410 en su lugar porque ninguna pantalla lo
# llamaba: el frontend califica por la ruta de casos desde que se rediseñó.
