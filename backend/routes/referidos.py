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

POR QUE NO SE GENERA ACA

    El código se crea UNA VEZ, al registrarse, y se guarda. Generarlo acá
    —«si no tiene, se lo hago»— parece más robusto y es peor: dos pedidos
    simultáneos de la misma persona crearían dos códigos distintos, y el que
    pierda la carrera se queda con un enlace que ya no apunta a nadie.

    Si una cuenta vieja no tuviera código, esta ruta devuelve vacío y se ve.
    Preferimos que se vea a que se arregle sola de una forma que puede dejar
    referidos huérfanos.
"""
import logging

from fastapi import APIRouter, Depends

from config import FRONTEND_URL
from database import db
from models.user import User
from routes.dependencies import get_current_user

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
    return {
        "codigo": codigo,
        "enlace": f"{FRONTEND_URL}/register?ref={codigo}" if codigo else "",
    }
