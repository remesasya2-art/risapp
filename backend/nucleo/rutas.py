"""
Las rutas del núcleo. Todas del super administrador, todas detrás del
interruptor, todas con contrato de salida.

    `Depends(get_super_admin)` primero y `Depends(modo.exigir_encendido)`
    después: a un cliente le contestan 401/403 antes de mirar el modo, y con
    el núcleo apagado el super administrador recibe 404. Ninguna ruta de acá
    aparece en `/limits` ni la nombra una pantalla de cliente; hay tests.

    Todo lo que se crea desde el laboratorio es `de_prueba`. El día que haya
    licencia, ACTIVO va a exigir otra cosa; hoy no existe esa otra cosa.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from models.user import User
from nucleo import base, comandos, modo
from nucleo.libro import AsientoInvalido, DiaCerrado
from routes.dependencies import get_super_admin

router = APIRouter(prefix="/nucleo", tags=["Núcleo"])


# ── contratos de salida ────────────────────────────────────────────────────

class Cadena(BaseModel):
    ok: bool
    asientos: int
    roto_en: Optional[int] = None
    motivo: Optional[str] = None
    hash_final: Optional[str] = None


class Estado(BaseModel):
    modo: int
    modo_nombre: str
    base: str
    conectada: bool
    cuentas: int
    asientos: int
    ultimo_cierre: Optional[str] = None
    cadena: Optional[Cadena] = None
    detalle: Optional[str] = None


class Cuenta(BaseModel):
    id: str
    titular_ref: str
    moneda: str
    estado: str
    de_prueba: bool
    saldo: str
    creada: Optional[str] = None


class PartidaVista(BaseModel):
    cuenta_contable: str
    cuenta: Optional[str] = None
    debe: int
    haber: int


class Asiento(BaseModel):
    numero: int
    fecha: str
    momento: Optional[str] = None
    descripcion: str
    referencia: str
    comando: str
    actor: str
    hash_previo: str
    hash: str
    partidas: list[PartidaVista]


class FilaDelBalance(BaseModel):
    codigo: str
    nombre: str
    grupo: str
    naturaleza: str
    debe: int
    haber: int
    saldo: int


class Balance(BaseModel):
    filas: list[FilaDelBalance]
    total_debe: int
    total_haber: int
    cuadra: bool


class Cierre(BaseModel):
    dia: str
    hasta_asiento: int
    hash_final: str
    asientos: int
    total_debe: int
    total_haber: int
    cerrado_en: Optional[str] = None
    cerrado_por: str
    nota: Optional[str] = None


class NumeroDeAsiento(BaseModel):
    numero: int


# ── contratos de entrada ───────────────────────────────────────────────────

class NuevaCuenta(BaseModel):
    titular_ref: str = Field(min_length=1, max_length=80)
    moneda: str = Field(default="BRL", min_length=3, max_length=3)


class Movimiento(BaseModel):
    tipo: str = Field(pattern="^(acreditar|debitar|transferir|tarifa)$")
    cuenta: Optional[str] = None            # acreditar, debitar, tarifa
    desde: Optional[str] = None             # transferir
    hacia: Optional[str] = None             # transferir
    monto: str = Field(min_length=1, max_length=24)   # «100.00», texto siempre
    referencia: str = Field(min_length=1, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=200)


class PedidoDeCierre(BaseModel):
    dia: date
    nota: Optional[str] = Field(default=None, max_length=500)


# ── helpers ────────────────────────────────────────────────────────────────

def _sin_base():
    raise HTTPException(status_code=503, detail=base.SinBase().args[0])


async def _con_base():
    if not base.hay_base():
        _sin_base()


# ── rutas ──────────────────────────────────────────────────────────────────

@router.get("/estado", response_model=Estado)
async def estado(admin: User = Depends(get_super_admin), modo_vigente: int = Depends(modo.exigir_encendido)):
    e = await comandos.estado()
    return {"modo": modo_vigente, "modo_nombre": modo.NOMBRES[modo_vigente], **e}


@router.get("/laboratorio/cuentas", response_model=list[Cuenta])
async def cuentas(admin: User = Depends(get_super_admin), _m: int = Depends(modo.exigir_encendido),
                  _b=Depends(_con_base)):
    return await comandos.listar_cuentas()


@router.post("/laboratorio/cuentas", response_model=Cuenta)
async def crear_cuenta(pedido: NuevaCuenta, admin: User = Depends(get_super_admin),
                       _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    return await comandos.crear_cuenta(titular_ref=pedido.titular_ref, moneda=pedido.moneda, de_prueba=True)


@router.post("/laboratorio/movimientos", response_model=NumeroDeAsiento)
async def mover(pedido: Movimiento, admin: User = Depends(get_super_admin),
                _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    actor = admin.user_id
    comunes = dict(monto=pedido.monto, referencia=pedido.referencia, actor=actor)
    if pedido.descripcion:
        comunes["descripcion"] = pedido.descripcion
    try:
        if pedido.tipo == "transferir":
            if not (pedido.desde and pedido.hacia):
                raise HTTPException(status_code=400, detail="Una transferencia necesita «desde» y «hacia».")
            numero = await comandos.transferir(desde=pedido.desde, hacia=pedido.hacia, **comunes)
        else:
            if not pedido.cuenta:
                raise HTTPException(status_code=400, detail="Falta la cuenta.")
            fn = {"acreditar": comandos.acreditar, "debitar": comandos.debitar,
                  "tarifa": comandos.cobrar_tarifa}[pedido.tipo]
            numero = await fn(cuenta_id=pedido.cuenta, **comunes)
    except (AsientoInvalido, comandos.MontoInvalido) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DiaCerrado as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"numero": numero}


@router.get("/laboratorio/libro", response_model=list[Asiento])
async def libro_(limite: int = 50, desde: Optional[int] = None, admin: User = Depends(get_super_admin),
                 _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from nucleo import libro
    async with base.sesion() as s:
        return await libro.listar_asientos(s, limite=max(1, min(limite, 200)), desde_numero=desde)


@router.get("/laboratorio/balance", response_model=Balance)
async def balance(admin: User = Depends(get_super_admin), _m: int = Depends(modo.exigir_encendido),
                  _b=Depends(_con_base)):
    from nucleo import libro
    async with base.sesion() as s:
        return await libro.balance_de_comprobacion(s)


@router.get("/laboratorio/cadena", response_model=Cadena)
async def cadena(admin: User = Depends(get_super_admin), _m: int = Depends(modo.exigir_encendido),
                 _b=Depends(_con_base)):
    from nucleo import libro
    async with base.sesion() as s:
        return await libro.verificar_cadena(s)


@router.get("/laboratorio/cierres", response_model=list[Cierre])
async def cierres(admin: User = Depends(get_super_admin), _m: int = Depends(modo.exigir_encendido),
                  _b=Depends(_con_base)):
    from nucleo import libro
    async with base.sesion() as s:
        return await libro.listar_cierres(s)


@router.post("/laboratorio/cierres", response_model=Cierre)
async def cerrar(pedido: PedidoDeCierre, admin: User = Depends(get_super_admin),
                 _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await comandos.cerrar_dia(dia=pedido.dia, actor=admin.user_id, nota=pedido.nota)
    except DiaCerrado as e:
        raise HTTPException(status_code=409, detail=str(e))
