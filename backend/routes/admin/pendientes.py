"""
routes/admin/pendientes.py — Los contadores de pendientes de cada sección del panel.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException

from models.user import User
from models.panel_tablero import PendientesDelPanel
from routes.dependencies import get_current_user
from services.notifications import ROLES_DEL_PERSONAL
from services import pendientes as pendientes_svc

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== LOS PENDIENTES DE CADA SECCION ==============
#
# POR QUE NO PASA POR `get_crm_user`
#
#   Los dos guardas con permiso exigen UN permiso por ruta, y esta ruta no
#   tiene uno: es un resumen que cruza nueve secciones con nueve guardianes
#   distintos. Declararla bajo cualquiera de ellos sería mentir sobre lo que
#   protege; inventar un permiso nuevo dejaría sin números a todo el personal
#   que ya existe, hasta que alguien se lo marcara a mano.
#
#   El filtro está adentro y es por sección: `services/pendientes.contar_para`
#   devuelve sólo los contadores de las secciones que ESTE usuario puede abrir.
#   Un cliente no recibe ninguno; un agente recibe los suyos y no se entera de
#   cuántos retiros hay esperando.

@router.get("/pendientes", response_model=PendientesDelPanel, response_model_exclude_unset=True)
async def get_pendientes(current_user: User = Depends(get_current_user)):
    """Cuánto trabajo espera en cada pestaña, para quien pregunta."""
    if current_user.role not in ROLES_DEL_PERSONAL:
        raise HTTPException(status_code=403, detail="CRM access required")

    pendientes, usuarios = await asyncio.gather(
        pendientes_svc.contar_para(current_user),
        pendientes_svc.total_de_usuarios(),
    )
    return {"pendientes": pendientes, "usuarios": usuarios}
