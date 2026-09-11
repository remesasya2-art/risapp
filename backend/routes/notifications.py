"""
routes/notifications.py — Lo que la campana le pide al servidor.

DOS BANDEJAS, UNA COLECCION

    Los avisos de TRABAJO —«hay un KYC nuevo», «la tasa venció»— y los
    PERSONALES —«te aprobaron el KYC», «llegó tu recarga»— viven en la misma
    colección y se separan por el campo `ambito` que escribe
    `services/notifications.py`.

    Sin esa separación, a un administrador la campana le mezclaba lo suyo con
    lo del equipo en una sola lista y sin ninguna diferencia visual. La
    campana del panel pide `ambito=trabajo`; la del cliente, `ambito=personal`.

POR QUE «PERSONAL» SE PREGUNTA AL REVES

    Se pregunta por «que NO sea de trabajo», no por «que sea personal».

    Suena igual y no lo es: los avisos guardados antes de que el campo
    existiera no lo tienen. Preguntando `ambito == "personal"` desaparecerían
    de la bandeja de su dueño —y son casi todos los que hay hoy—.

SIN EL PARAMETRO, TODO

    A propósito. El servidor se despliega antes que la pantalla, y en esos
    minutos la campana vieja sigue pidiendo sin filtro. Devolverle una lista
    vacía sería un apagón de avisos por cada despliegue.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from routes.dependencies import get_current_user
from models.user import User
from services.notifications import PERSONAL, TRABAJO

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

# Cuántos avisos se devuelven de una vez. El paginado es de la Fase 4; hasta
# entonces este número es el techo real de lo que la pantalla puede mostrar.
_TOPE = 50


def _bandeja(user_id: str, ambito: str | None) -> dict:
    """El filtro de una bandeja. Ver el encabezado del archivo."""
    if ambito is None:
        return {"user_id": user_id}
    if ambito == TRABAJO:
        return {"user_id": user_id, "ambito": TRABAJO}
    if ambito == PERSONAL:
        return {"user_id": user_id, "ambito": {"$ne": TRABAJO}}
    # Un valor que no se entiende NO se trata como «todo». Un `ambito=persnal`
    # mal escrito devolvería la bandeja entera, y el aviso del equipo aparecería
    # en la campana del cliente sin que nadie se entere de por qué.
    raise HTTPException(
        status_code=400,
        detail=f"Ámbito desconocido: {ambito!r}. Los que hay son "
               f"{PERSONAL!r} y {TRABAJO!r}.")


@router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user),
                            ambito: str | None = Query(None)):
    """Los avisos de una bandeja, del más nuevo al más viejo."""
    return await db.notifications.find(
        _bandeja(current_user.user_id, ambito),
        {"_id": 0},
    ).sort("created_at", -1).limit(_TOPE).to_list(_TOPE)


@router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user),
                           ambito: str | None = Query(None)):
    """El número rojo de la campana."""
    filtro = _bandeja(current_user.user_id, ambito)
    filtro["read"] = False
    return {"unread_count": await db.notifications.count_documents(filtro)}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str,
                                 current_user: User = Depends(get_current_user)):
    """Marca uno como leído. Sin ámbito: un aviso concreto es de una bandeja
    sola, y el `user_id` ya impide tocar el de otra persona."""
    await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user.user_id},
        {"$set": {"read": True}}
    )
    return {"success": True}


@router.post("/notifications/mark-all-read")
async def mark_all_read(current_user: User = Depends(get_current_user),
                        ambito: str | None = Query(None)):
    """«Marcar todas» de UNA bandeja.

    Sin el ámbito esto apagaba las dos: el operador vaciaba su bandeja personal
    y de paso se daba por enterado de cada KYC pendiente del equipo.
    """
    filtro = _bandeja(current_user.user_id, ambito)
    filtro["read"] = False
    resultado = await db.notifications.update_many(filtro, {"$set": {"read": True}})
    return {"success": True, "marcados": resultado.modified_count}
