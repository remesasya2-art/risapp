"""
Los CPF repetidos, desde el panel: verlos y resolverlos sin entrar a la base.

    Dos cuentas con el mismo CPF impiden crear el candado de «un CPF, una
    cuenta» (services/cpf_de_la_cuenta.py). Cuál es la buena lo decide una
    persona mirando las dos; acá está la lista para mirarlas y la acción para
    liberar el CPF de la otra, con motivo y con rastro en la auditoría.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import cpf_de_la_cuenta

# El prefijo NO es `/admin/users`: ahí vive `GET /admin/users/{user_id}`, que
# atrapa `cpf-repetidos` como si fuera un usuario y contesta «no encontrado».
# Se vio en la vista previa antes de salir.
router = APIRouter(prefix="/admin", tags=["cpf-repetidos"])


class CuentaConCpf(BaseModel):
    user_id: str
    nombre: Optional[str] = None
    email: Optional[str] = None
    creada: Optional[str] = None
    ultimo_ingreso: Optional[str] = None
    verificacion: Optional[str] = None
    estado: Optional[str] = None
    borrada: bool
    vetada: bool
    saldo_ris: float


class CpfRepetido(BaseModel):
    cpf: str                      # tapado: sólo los últimos tres dígitos
    cuentas: list[CuentaConCpf]


class CpfRepetidos(BaseModel):
    repetidos: list[CpfRepetido]
    candado: bool                 # si el índice único de users.cpf_number existe


class Liberacion(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class CpfLiberado(BaseModel):
    user_id: str
    cpf: str
    indice: str
    quedan_repetidos: int


@router.get("/cpf-repetidos", response_model=CpfRepetidos)
async def ver_cpf_repetidos(_: User = Depends(get_super_admin)):
    indices = await db.users.index_information()
    return {"repetidos": await cpf_de_la_cuenta.repetidos(db), "candado": cpf_de_la_cuenta.NOMBRE_DEL_INDICE in indices}


@router.post("/users/{user_id}/cpf/liberar", response_model=CpfLiberado)
async def liberar_cpf(user_id: str, cuerpo: Liberacion, request: Request, quien: User = Depends(get_super_admin)):
    try:
        return await cpf_de_la_cuenta.liberar(db, user_id, motivo=cuerpo.motivo, quien=quien, request=request)
    except cpf_de_la_cuenta.NoSePuedeLiberar as e:
        raise HTTPException(status_code=400, detail=str(e))
