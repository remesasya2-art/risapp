"""
routes/referidos.py — El código de referido, que ahora tiene todo el mundo.

QUE CAMBIO

    Antes el código de referido y su enlace eran una cosa de SOCIOS: existía
    un rol aparte, con su pantalla, su panel de comisiones y su tabla de
    ganancias. Sólo quien tenía ese rol podía ver su enlace.

    Eso se desarmó. Ahora cada usuario recibe su código al registrarse —eso ya
    pasaba, `routes/auth.py` se lo asigna a todos— y esta ruta se lo devuelve
    a cualquiera que la pida sobre su propia cuenta. Sin roles, sin permisos
    especiales y sin panel.

POR QUE SE GENERA ACA, Y CON CONDICION

    El código nace con la cuenta (`services/alta_de_cuenta.py`). Pero hay
    cuentas de cliente que no lo tienen: las que nacieron antes de que
    existiera. A esas la tarjeta del perfil no se les dibujaba, y el dueño
    del proyecto lo vio como «no se ve el código de referido».

    Durante un tiempo esta ruta se negó a generarlo, con un buen motivo: dos
    pedidos simultáneos de la misma persona crearían dos códigos distintos, y
    el que pierda la carrera se queda con un enlace que ya no apunta a nadie.

    Ese motivo sigue en pie contra la forma OBVIA de hacerlo —«si leí vacío,
    escribo uno»—, que pisa lo que el otro pedido acaba de escribir. No
    contra ésta: la escritura lleva la condición «sólo si todavía no tiene»,
    así que de dos pedidos simultáneos uno solo escribe; y después los dos
    RELEEN de la base en vez de devolver lo que generaron. Los dos ven el
    mismo código, el que quedó.

    Sólo a clientes (`role == "user"`). Administradores y personal nacen sin
    código a propósito: no pueden operar como clientes, y un enlace de
    invitación con su nombre no tiene nada que ofrecer.
"""
import logging

from fastapi import APIRouter, Depends

from config import FRONTEND_URL
from database import db
from models.user import User
from routes.dependencies import get_current_user
from services import alta_de_cuenta

logger = logging.getLogger(__name__)
from models.cuenta import MiCodigoDeReferido, MisReferidos
router = APIRouter(prefix="/referidos", tags=["referidos"])


@router.get("/mis-referidos", response_model=MisReferidos)
async def mis_referidos(pagina: int = 1,
                        current_user: User = Depends(get_current_user)):
    """Los referidos de QUIEN PREGUNTA, y nada más.

    El `user_id` sale de la sesión y no de un parámetro. Si viniera por la
    dirección, cualquiera podría pedir la lista de referidos de otro cambiando
    un número —y ahí adentro van nombres de terceros—.
    """
    from services import bonos
    return await bonos.mis_referidos(db, current_user.user_id, pagina=pagina)


@router.get("/mi-codigo", response_model=MiCodigoDeReferido)
async def mi_codigo(current_user: User = Depends(get_current_user)):
    """El código de referido de quien pregunta, y su enlace para compartir."""
    # Sólo el código. Sin proyección esto traería el usuario entero —documento,
    # teléfono, saldos— para devolver una cadena de ocho caracteres.
    persona = await db.users.find_one({"user_id": current_user.user_id},
                                      {"_id": 0, "referral_code": 1})
    codigo = (persona or {}).get("referral_code") or ""

    if not codigo and current_user.role == "user":
        # `$in: [None, ""]` cubre las tres formas de «no tiene»: el campo
        # ausente (Mongo lo iguala a null), null guardado y la cadena vacía.
        # Con sólo `$exists: False`, una cuenta con null quedaría sin código
        # para siempre.
        await db.users.update_one(
            {"user_id": current_user.user_id, "referral_code": {"$in": [None, ""]}},
            {"$set": {"referral_code": alta_de_cuenta.nuevo_codigo_de_referido()}})
        # Se relee en vez de devolver el que se acaba de generar: si otro
        # pedido ganó la carrera, esta escritura no hizo nada y el código
        # bueno es el suyo.
        persona = await db.users.find_one({"user_id": current_user.user_id},
                                          {"_id": 0, "referral_code": 1})
        codigo = (persona or {}).get("referral_code") or ""
        if codigo:
            logger.info("REFERIDO| %s recibió su código al pedirlo (cuenta anterior al código)",
                        current_user.user_id)

    return {
        "codigo": codigo,
        "enlace": f"{FRONTEND_URL}/register?ref={codigo}" if codigo else "",
    }
