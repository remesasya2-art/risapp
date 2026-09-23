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

SE BORRA A MANO, Y NADA SE BORRA SOLO

    No hay vencimiento automático. Fue una decisión: un aviso que desaparece
    solo es un aviso que alguien no llegó a leer, y nadie se entera de que
    existió.

    Y el borrado en tanda NUNCA toca lo que no se leyó. «Limpiar leídas»
    limpia lo leído; para tirar algo sin leer hay que abrirlo y borrarlo de a
    uno, mirándolo. Un botón que vacía la bandeja entera de un clic es un
    botón que alguien aprieta sin querer.

EL PAGINADO DEVUELVE UNA LISTA, NO UN SOBRE

    Se sigue devolviendo la lista pelada, como siempre. «Hay más» se deduce de
    que hayan venido tantos como se pidieron.

    Envolverla en `{"notificaciones": [...], "hay_mas": true}` habría sido más
    explícito y habría dejado la campana del panel vacía durante los minutos
    que van del despliegue del servidor al de la pantalla. El costo de esto es
    un pedido de más cuando el total es múltiplo exacto del tamaño de página.

SIN EL PARAMETRO, TODO

    A propósito. El servidor se despliega antes que la pantalla, y en esos
    minutos la campana vieja sigue pidiendo sin filtro. Devolverle una lista
    vacía sería un apagón de avisos por cada despliegue.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from database import db
from routes.dependencies import get_current_user
from models.user import User
from typing import List
from models.avisos import AvisosSinLeer, LO_QUE_VE_DE_UN_AVISO, UnAviso
from services.notifications import PERSONAL, TRABAJO

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

# Cuántos avisos trae una página, y hasta cuántos puede pedir quien insista.
# El tope de arriba existe para que un `limite=100000` no se traiga la
# colección entera a memoria.
_POR_PAGINA = 20
_TOPE = 100


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


# El orden. `notification_id` está para desempatar: dos avisos escritos en el
# mismo instante —pasa: una operación dispara dos— quedarían en orden
# arbitrario, y el paginado, que se apoya en el orden, se saltearía uno.
_ORDEN = [("created_at", -1), ("notification_id", -1)]


def _mas_viejos_que(antes_de: str | None, ultimo_id: str | None) -> dict:
    """El corte para pedir la página siguiente.

    Se pagina por CONTENIDO —«dame los más viejos que éste»— y no por posición
    —«saltea los primeros 20»—. La diferencia se ve cuando llega un aviso
    nuevo mientras alguien está mirando: con posiciones, todo se corre uno y la
    página siguiente repite el último que ya se vio.
    """
    if not antes_de:
        return {}

    try:
        corte = datetime.fromisoformat(antes_de.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"`antes_de` no es una fecha: {antes_de!r}")

    if not ultimo_id:
        return {"created_at": {"$lt": corte}}
    # Con el identificador se desempata dentro del mismo instante. Sin esto, de
    # dos avisos con la misma hora uno se pierde entre página y página.
    return {"$or": [
        {"created_at": {"$lt": corte}},
        {"created_at": corte, "notification_id": {"$lt": ultimo_id}},
    ]}


@router.get("/notifications", response_model=List[UnAviso], response_model_exclude_unset=True)
async def get_notifications(current_user: User = Depends(get_current_user),
                            ambito: str | None = Query(None),
                            limite: int = Query(_POR_PAGINA, ge=1, le=_TOPE),
                            antes_de: str | None = Query(None),
                            ultimo_id: str | None = Query(None),
                            solo_sin_leer: bool = Query(False)):
    """Una página de avisos, del más nuevo al más viejo.

    Para pedir la siguiente se mandan la fecha y el identificador del último
    que se recibió. Que vengan `limite` significa que puede haber más.
    """
    filtro = _bandeja(current_user.user_id, ambito)
    if solo_sin_leer:
        filtro["read"] = False

    corte = _mas_viejos_que(antes_de, ultimo_id)
    if corte:
        filtro = {"$and": [filtro, corte]}

    # Sólo lo que leen las pantallas. Ver models/avisos.py.
    return await db.notifications.find(
        filtro, LO_QUE_VE_DE_UN_AVISO,
    ).sort(_ORDEN).limit(limite).to_list(limite)


@router.get("/notifications/unread-count", response_model=AvisosSinLeer)
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


@router.delete("/notifications/leidas")
async def borrar_leidas(current_user: User = Depends(get_current_user),
                        ambito: str | None = Query(None)):
    """«Limpiar leídas»: borra lo LEIDO de una bandeja. Nunca lo demás.

    Que esto no pueda tocar un aviso sin leer es la mitad del diseño. Un botón
    que vacía la bandeja entera de un clic es un botón que alguien aprieta sin
    querer, y lo que se lleva puesto no vuelve: el aviso era la única copia de
    «tu retiro se completó» que esa persona iba a ver.

    Para tirar algo sin leer hay que abrirlo y borrarlo de a uno, mirándolo.
    """
    filtro = _bandeja(current_user.user_id, ambito)
    filtro["read"] = True
    r = await db.notifications.delete_many(filtro)
    return {"success": True, "borrados": r.deleted_count}


@router.delete("/notifications/{notification_id}")
async def borrar_notificacion(notification_id: str,
                              current_user: User = Depends(get_current_user)):
    """Borra uno. El `user_id` del filtro es lo que impide borrar el de otro.

    Devuelve 404 si no existe o no es suyo: las dos cosas se contestan igual a
    propósito. Distinguirlas dejaría averiguar, probando identificadores, qué
    avisos tiene otra persona.
    """
    r = await db.notifications.delete_one(
        {"notification_id": notification_id, "user_id": current_user.user_id})
    if not r.deleted_count:
        raise HTTPException(status_code=404, detail="No se encontró ese aviso.")
    return {"success": True}
