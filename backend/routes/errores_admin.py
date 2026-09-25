"""Lo que el super administrador ve de los errores. Sólo lectura.

Sólo `get_super_admin`, igual que el libro de auditoría y por el mismo
motivo: un error trae la ruta, el usuario que lo sufrió y el texto de una
excepción. No es algo que se delegue.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from database import db
from models.panel_tablero import ErroresRegistrados, ResumenDeErrores
from models.user import User
from routes.dependencies import get_super_admin
from services import errores

router = APIRouter(prefix="/admin/errores", tags=["Errores"])


@router.get("", response_model=ErroresRegistrados, response_model_exclude_unset=True)
async def listar(
    ruta: Optional[str] = None,
    status: Optional[int] = None,
    rastro: Optional[str] = None,
    limite: int = 100,
    saltar: int = 0,
    admin: User = Depends(get_super_admin),
):
    return await errores.buscar(db, ruta=ruta, status=status, rastro=rastro,
                                limite=limite, saltar=saltar)


@router.get("/resumen", response_model=ResumenDeErrores, response_model_exclude_unset=True)
async def resumen(horas: int = 24, admin: User = Depends(get_super_admin)):
    return await errores.resumen(db, horas=horas)
