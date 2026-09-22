"""
El respaldo de la base desde el panel: crearlo y bajarlo, comprobar uno.

    Sólo el super administrador: el archivo lleva los datos de todos los
    clientes. Cada creación y cada comprobación quedan en la auditoría. Ver
    services/respaldo_de_mongo.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import respaldo_de_mongo

router = APIRouter(prefix="/admin/respaldos", tags=["respaldos"])


class Respaldo(BaseModel):
    id: str
    momento: str
    actor: str
    documentos: int
    colecciones: dict
    bytes: int
    hash: str
    firmado: bool
    comprobado_en: Optional[str] = None
    comprobacion: Optional[dict] = None
    contenido: Optional[str] = None     # sólo al crearlo: se devuelve para guardarlo afuera
    firma: Optional[str] = None


class Respaldos(BaseModel):
    llave_configurada: bool
    colecciones_que_se_conservan: list[str]
    respaldos: list[Respaldo]


class RespaldoAComprobar(BaseModel):
    contenido: str = Field(min_length=2, max_length=200_000_000)
    firma: Optional[str] = Field(default=None, max_length=64)


class ComprobacionDeRespaldo(BaseModel):
    ok: bool
    hash_ok: bool
    firma: str
    documentos: int
    colecciones: dict
    motivo: Optional[str] = None
    hash: str
    registrado: bool
    en: Optional[str] = None            # "navegador" cuando la lectura pesada la hizo el navegador


class HuellaAComprobar(BaseModel):
    """Lo que manda el navegador después de leer el archivo entero de su
    lado: sin subirlo. Ver `respaldo_de_mongo.comprobar_huella`."""
    hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    documentos: int = Field(ge=0)
    hash_de_cierre_ok: bool
    lineas_ok: bool
    colecciones: dict = Field(default_factory=dict)
    firma: Optional[str] = Field(default=None, max_length=64)
    motivo_del_navegador: Optional[str] = Field(default=None, max_length=300)


@router.get("", response_model=Respaldos)
async def ver_respaldos(_: User = Depends(get_super_admin)):
    return {"llave_configurada": respaldo_de_mongo.hay_llave(),
            "colecciones_que_se_conservan": list(respaldo_de_mongo.COLECCIONES_QUE_SE_CONSERVAN),
            "respaldos": await respaldo_de_mongo.listar(db)}


@router.post("", response_model=Respaldo)
async def crear_respaldo(request: Request, quien: User = Depends(get_super_admin)):
    """Exporta y devuelve el contenido y la firma. La base sólo guarda el
    registro (cuándo, quién, cuánto, hash) y la auditoría."""
    return await respaldo_de_mongo.crear(db, quien=quien, request=request)


@router.post("/comprobar", response_model=ComprobacionDeRespaldo)
async def comprobar_respaldo(cuerpo: RespaldoAComprobar, request: Request, quien: User = Depends(get_super_admin)):
    """Con el archivo entero. Sirve para un guión o un archivo chico; el
    panel no la usa: un respaldo real pasa el tope de cuerpo (40 MB) y el
    tiempo de Cloudflare. Ver `/comprobar-huella`."""
    return await respaldo_de_mongo.comprobar_y_anotar(db, cuerpo.contenido, cuerpo.firma, quien=quien, request=request)


@router.post("/comprobar-huella", response_model=ComprobacionDeRespaldo)
async def comprobar_huella(cuerpo: HuellaAComprobar, request: Request, quien: User = Depends(get_super_admin)):
    """El navegador leyó el archivo y manda la huella y lo que encontró; acá
    se pone la firma y el registro. Nada de 70 MB viajando."""
    return await respaldo_de_mongo.comprobar_huella(
        db, huella=cuerpo.hash, documentos=cuerpo.documentos, hash_de_cierre_ok=cuerpo.hash_de_cierre_ok,
        lineas_ok=cuerpo.lineas_ok, colecciones=cuerpo.colecciones, firma=cuerpo.firma,
        motivo_del_navegador=cuerpo.motivo_del_navegador, quien=quien, request=request)
