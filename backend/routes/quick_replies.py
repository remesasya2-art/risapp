"""
Respuestas rápidas de la mesa de ayuda.

POR QUE ESTA EN SU PROPIO ARCHIVO

    Vivían en `routes/support.py`, junto al chat viejo de un documento por
    usuario. Ese chat se apagó —lo reemplazó la mesa de ayuda por casos— y
    estas tres rutas eran lo ÚNICO de aquel archivo que alguna pantalla
    seguía usando: `MesaDeAyuda.jsx` las pide al abrir.

    Dejarlas donde estaban obligaba a mantener montado un router con diez
    endpoints muertos para no perder tres vivos. Están acá para que apagar lo
    muerto no dependiera de conservar lo vivo.
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import db
from routes.dependencies import get_crm_user
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quick-replies"])


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
