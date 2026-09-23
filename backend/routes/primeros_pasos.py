"""La tarjeta «Primeros pasos» del panel del cliente. Sólo lectura, y sólo
de la propia cuenta: el estado se calcula con el `user_id` de la sesión y
no con uno que venga en el pedido."""
from fastapi import APIRouter, Depends

from database import db
from models.user import User
from routes.dependencies import get_current_user
from services import primeros_pasos
from models.reglas_publicas import MisPrimerosPasos

router = APIRouter(prefix="/primeros-pasos", tags=["Primeros pasos"])


@router.get("", response_model=MisPrimerosPasos)
async def ver(current_user: User = Depends(get_current_user)):
    return await primeros_pasos.estado(db, current_user.user_id)
