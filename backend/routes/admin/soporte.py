"""
routes/admin/soporte.py — Las solicitudes de ayuda y las calificaciones de cada asesor.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.user import User
from models.panel_soporte import (AccionDeSoporte, CalificacionesPorAsesor, PrioridadDeLaSolicitud,
                                   RespuestaPorCorreo, SolicitudesDeAyuda, SolicitudResuelta, SolicitudTomada)
from pydantic import BaseModel
from routes.dependencies import (get_super_admin, get_crm_user)
from services.email_notifications import send_email
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== SUPPORT REQUESTS ==============

@router.get("/support-requests", response_model=SolicitudesDeAyuda, response_model_exclude_unset=True)
async def get_support_requests(admin: User = Depends(get_crm_user)):
    """Get all support requests"""
    requests = await db.support_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"requests": requests}

@router.post("/support-requests/{request_id}/resolve", response_model=SolicitudResuelta, response_model_exclude_unset=True)
async def resolve_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Mark a support request as resolved"""
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc),
            "resolved_by": admin.user_id
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    logger.info(f"Support request {request_id} resolved by {admin.user_id}")
    return {"message": "Solicitud marcada como resuelta"}

class SupportReplyRequest(BaseModel):
    message: str

@router.post("/support-requests/{request_id}/reply", response_model=RespuestaPorCorreo, response_model_exclude_unset=True)
async def reply_support_request(request_id: str, data: SupportReplyRequest, admin: User = Depends(get_crm_user)):
    """Responde una solicitud de soporte por correo (vía Resend) y guarda la respuesta."""
    text = (data.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    to_email = req.get("email")
    if not to_email:
        raise HTTPException(status_code=400, detail="La solicitud no tiene correo de contacto")
    subject_orig = req.get("subject") or "tu solicitud"
    original_msg = req.get("message") or ""
    safe_reply = text.replace("\n", "<br>")
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Respuesta de soporte - RISApp</h2>
        <p>Hola,</p>
        <p>Gracias por contactarnos. En respuesta a tu solicitud <strong>"{subject_orig}"</strong>:</p>
        <div style="background: #f3f4f6; border-left: 4px solid #6366f1; padding: 14px 16px; border-radius: 8px; margin: 16px 0; color: #1f2937;">
            {safe_reply}
        </div>
        <p style="color: #6b7280; font-size: 13px;">Tu mensaje original: "{original_msg}"</p>
        <div style="background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 12px 14px; margin: 18px 0 8px;">
            <p style="color: #92400e; font-size: 13px; margin: 0; line-height: 1.5;">
                <strong>No respondas este correo</strong>, no podemos leer las respuestas por esta via. El equipo de RISApp se pondra en contacto contigo directamente a traves de los numeros de contacto y el correo que nos dejaste.
            </p>
        </div>
    </div>
    """
    email_sent = await send_email(
        to_email=to_email,
        subject=f"Re: {subject_orig} - Soporte RISApp",
        html_content=html_content,
    )
    reply_doc = {
        "message": text,
        "admin_id": admin.user_id,
        "admin_name": getattr(admin, "name", None) or "Soporte",
        "sent_at": datetime.now(timezone.utc),
        "email_sent": bool(email_sent),
    }
    await db.support_requests.update_one(
        {"support_id": request_id},
        {
            "$push": {"replies": reply_doc},
            "$set": {
                "responded_at": datetime.now(timezone.utc),
                "responded_by": admin.user_id,
            },
        },
    )
    if not email_sent:
        return {"success": False, "email_sent": False, "message": "Respuesta guardada, pero el correo no se pudo enviar (revisa la configuracion de Resend)."}
    return {"success": True, "email_sent": True, "message": "Respuesta enviada por correo"}

@router.post("/support-requests/{request_id}/claim", response_model=SolicitudTomada, response_model_exclude_unset=True)
async def claim_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Toma (claim) una solicitud de soporte de forma ATÓMICA: solo uno puede tomarla."""
    result = await db.support_requests.update_one(
        {"support_id": request_id, "$or": [{"assigned_to": None}, {"assigned_to": {"$exists": False}}, {"assigned_to": ""}]},
        {"$set": {
            "assigned_to": admin.user_id,
            "assigned_to_name": admin.name or "Operador",
            "assigned_at": datetime.now(timezone.utc),
        }}
    )
    if result.modified_count == 1:
        return {"success": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    existing = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1, "assigned_to_name": 1})
    if existing and existing.get("assigned_to") == admin.user_id:
        return {"success": True, "already_mine": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    return {"success": False, "assigned_to": (existing or {}).get("assigned_to"), "assigned_to_name": (existing or {}).get("assigned_to_name")}

@router.post("/support-requests/{request_id}/release", response_model=AccionDeSoporte, response_model_exclude_unset=True)
async def release_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Suelta una solicitud. Solo el dueño del caso o un super admin."""
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if req.get("assigned_to") and req.get("assigned_to") != admin.user_id and admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo quien atiende el caso o un super admin puede liberarlo")
    await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"assigned_to": None, "assigned_to_name": None, "assigned_at": None}}
    )
    return {"success": True}


class SetPriorityRequest(BaseModel):
    priority: str

@router.post("/support-requests/{request_id}/priority", response_model=PrioridadDeLaSolicitud, response_model_exclude_unset=True)
async def set_support_priority(request_id: str, data: SetPriorityRequest, admin: User = Depends(get_crm_user)):
    """Cambia la prioridad de una solicitud de soporte."""
    valid = ["baja", "normal", "alta", "urgente"]
    if data.priority not in valid:
        raise HTTPException(status_code=400, detail="Prioridad inválida")
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"priority": data.priority}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {"success": True, "priority": data.priority}

@router.get("/agent-ratings", response_model=CalificacionesPorAsesor, response_model_exclude_unset=True)
async def get_agent_ratings(admin: User = Depends(get_super_admin)):
    """Resumen interno de calificaciones por agente (solo super admin)."""
    ratings = await db.ratings.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    agents = {}
    for r in ratings:
        aid = r.get("agent_id") or "sin_asignar"
        aname = r.get("agent_name") or "Sin asignar"
        if aid not in agents:
            agents[aid] = {"agent_id": aid, "agent_name": aname, "count": 0, "sum_stars": 0, "ratings": []}
        a = agents[aid]
        a["count"] += 1
        a["sum_stars"] += (r.get("stars") or 0)
        a["ratings"].append({
            "stars": r.get("stars"),
            "comment": r.get("comment") or "",
            "channel": r.get("channel"),
            # `case_ref` de respaldo, y no por prolijidad: las calificaciones
            # que ya están guardadas se escribieron sólo con ese campo, así que
            # sin el respaldo el panel seguiría sin decir de qué caso habla
            # hasta que llegue una calificación nueva. Para un caso `case_ref`
            # es el identificador interno; para un chat viejo es el usuario,
            # que es justo con lo que se abría esa conversación.
            "case_code": r.get("case_code") or r.get("case_ref"),
            "created_at": r.get("created_at"),
        })
    result = []
    for a in agents.values():
        avg = round(a["sum_stars"] / a["count"], 2) if a["count"] else 0
        result.append({
            "agent_id": a["agent_id"],
            "agent_name": a["agent_name"],
            "count": a["count"],
            "average": avg,
            "ratings": a["ratings"],
        })
    result.sort(key=lambda x: (-x["average"], -x["count"]))
    return {"agents": result, "total": len(ratings)}
