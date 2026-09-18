"""Lo que el super administrador ve del uso. Sólo lectura.

Sólo `get_super_admin`: es el cuadro de mando del negocio, no una tarea que
se delegue. Un colaborador con permisos de KYC no tiene por qué saber cuántas
cuentas entran por semana.
"""
from fastapi import APIRouter, Depends

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import uso

router = APIRouter(prefix="/admin/uso", tags=["Uso"])

# Los períodos que la pantalla ofrece. Se acota acá y no se confía en el
# número que llega: 90 es lo que se guarda, pedir 900 traería lo mismo con
# un gráfico vacío al costado.
DIAS_PERMITIDOS = (7, 30, 90)


@router.get("")
async def ver(dias: int = 30, admin: User = Depends(get_super_admin)):
    if dias not in DIAS_PERMITIDOS:
        dias = 30
    return await uso.todo(db, dias=dias)
