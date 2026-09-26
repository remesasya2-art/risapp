"""
routes/admin/servicios.py — El estado de cada servicio, para el panel.

Sólo lee. Para prender o apagar un servicio, la pantalla usa la ruta de
Configuración de siempre (`PUT /admin/configuracion`): así cada cambio pasa
por la misma validación, los seguros entre ajustes, los cuatro ojos del
núcleo y el libro de auditoría, sin una segunda puerta que haya que mantener
igual. Ver services/servicios.py.
"""
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.panel_servicios import LosServicios
from models.user import User
from routes.dependencies import get_current_user
from services import servicios
from services.notifications import ROLES_DEL_PERSONAL

router = APIRouter(prefix="/admin", tags=["admin"])


# POR QUE NO PASA POR `get_crm_user`, IGUAL QUE LOS PENDIENTES
#
#   Todo el personal ve en el menú si un servicio está apagado: quien atiende
#   tiene que saber que remesas está en pausa antes de que un cliente se lo
#   cuente. No hay un permiso que lo gobierne —no es de ninguna sección— y
#   declararlo bajo uno dejaría sin el dato a quien no lo tenga. El estado de
#   una llave no es información de nadie: el cliente lo ve en `/api/limits`.
@router.get("/servicios", response_model=LosServicios, response_model_exclude_unset=True)
async def ver_servicios(current_user: User = Depends(get_current_user)):
    if current_user.role not in ROLES_DEL_PERSONAL:
        raise HTTPException(status_code=403, detail="CRM access required")
    return {"servicios": await servicios.estado_de_todos(db)}
