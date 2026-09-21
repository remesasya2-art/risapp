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
from nucleo import base, cola, comandos, modo, tareas, trabajador
from nucleo.libro import AsientoInvalido, DiaCerrado
from nucleo.rieles import operaciones as rieles_op, pix, simulador
from routes.dependencies import get_super_admin

router = APIRouter(prefix="/nucleo", tags=["Núcleo"])


# ── contratos de salida ────────────────────────────────────────────────────

class Cadena(BaseModel):
    ok: bool
    asientos: int
    roto_en: Optional[int] = None
    motivo: Optional[str] = None
    hash_final: Optional[str] = None


class ResumenDeLaCola(BaseModel):
    pendiente: int
    en_curso: int
    hecho: int
    muerto: int
    eventos: int
    eventos_sin_publicar: int


class Trabajador(BaseModel):
    nombre: str
    corriendo: bool
    vueltas: int
    ultima_vuelta: Optional[str] = None
    ultimo_error: Optional[str] = None
    ultimo_modo: Optional[str] = None


class Estado(BaseModel):
    modo: int
    modo_nombre: str
    base: str
    conectada: bool
    cuentas: int
    asientos: int
    ultimo_cierre: Optional[str] = None
    cadena: Optional[Cadena] = None
    cola: Optional[ResumenDeLaCola] = None
    trabajador: Optional[Trabajador] = None
    detalle: Optional[str] = None


class Trabajo(BaseModel):
    id: int
    tipo: str
    clave: str
    carga: dict
    estado: str
    intentos: int
    max_intentos: int
    proximo_intento: Optional[str] = None
    tomado_por: Optional[str] = None
    tomado_hasta: Optional[str] = None
    ultimo_error: Optional[str] = None
    resultado: Optional[str] = None
    origen_evento: Optional[int] = None
    creado: Optional[str] = None
    terminado: Optional[str] = None


class Evento(BaseModel):
    id: int
    tipo: str
    clave: str
    carga: dict
    creado: Optional[str] = None
    publicado: Optional[str] = None


class Cola(BaseModel):
    resumen: ResumenDeLaCola
    trabajador: Trabajador
    trabajos: list[Trabajo]
    eventos: list[Evento]


class TrabajoEncolado(BaseModel):
    id: int
    nuevo: bool


class Paso(BaseModel):
    despachados: int
    corridos: int
    hechos: int
    muertos: int
    reintentan: int


class Reintento(BaseModel):
    id: int
    estado: str


class EstadoDeOperacion(BaseModel):
    estado: str
    detalle: Optional[str] = None
    momento: Optional[str] = None


class Operacion(BaseModel):
    id: str
    riel: str
    direccion: str
    estado: str
    cuenta: str
    monto: str
    referencia: str
    txid: Optional[str] = None
    end_to_end: Optional[str] = None
    clave: Optional[str] = None
    contraparte: Optional[dict] = None
    descripcion: Optional[str] = None
    motivo: Optional[str] = None
    origen: Optional[str] = None
    codigo_br: Optional[str] = None
    creada: Optional[str] = None
    actualizada: Optional[str] = None
    historial: list[EstadoDeOperacion] = Field(default_factory=list)


class AvisoDelRiel(BaseModel):
    id: int
    riel: str
    id_externo: str
    tipo: str
    carga: dict
    recibido: Optional[str] = None
    procesado: Optional[str] = None
    resultado: Optional[str] = None


class ClaveDePrueba(BaseModel):
    clave: str
    nombre: str
    banco: str
    comportamiento: str


class Titular(BaseModel):
    clave: str
    tipo: str
    nombre: str
    documento: str
    ispb: str
    banco: str


class Rieles(BaseModel):
    riel: str
    ispb: str
    claves_de_prueba: list[ClaveDePrueba]
    motivos_de_devolucion: dict
    resumen: dict
    operaciones: list[Operacion]
    avisos: list[AvisoDelRiel]


class AvisoRecibido(BaseModel):
    id: int
    nuevo: bool


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


class NuevoCobro(BaseModel):
    cuenta: str = Field(min_length=1, max_length=40)
    monto: str = Field(min_length=1, max_length=24)
    descripcion: Optional[str] = Field(default=None, max_length=140)


class PagoSimulado(BaseModel):
    pagador_clave: str = Field(default="ana@ejemplo.test", min_length=1, max_length=120)


class NuevoPago(BaseModel):
    cuenta: str = Field(min_length=1, max_length=40)
    clave: str = Field(min_length=1, max_length=120)
    monto: str = Field(min_length=1, max_length=24)
    referencia: Optional[str] = Field(default=None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=140)


class ResultadoSimulado(BaseModel):
    estado: str = Field(pattern="^(ACSC|RJCT)$")
    motivo: Optional[str] = Field(default=None, max_length=4)


class NuevaDevolucion(BaseModel):
    operacion: str = Field(min_length=1, max_length=40)
    monto: str = Field(min_length=1, max_length=24)
    motivo: str = Field(pattern="^(MD06|SL02|FR01|BE08)$")


class NuevoTrabajo(BaseModel):
    # Sólo los de laboratorio: desde la pestaña no se encola un aviso real.
    tipo: str = Field(pattern="^(" + "|".join(tareas.DE_LABORATORIO) + ")$")
    clave: Optional[str] = Field(default=None, min_length=1, max_length=120)
    carga: dict = Field(default_factory=dict)


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
    return {"modo": modo_vigente, "modo_nombre": modo.NOMBRES[modo_vigente], "trabajador": trabajador.estado(), **e}


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


# ── la cola ────────────────────────────────────────────────────────────────

@router.get("/laboratorio/cola", response_model=Cola)
async def cola_(limite: int = 50, admin: User = Depends(get_super_admin),
                _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    limite = max(1, min(limite, 200))
    async with base.sesion() as s:
        return {"resumen": await cola.resumen(s), "trabajador": trabajador.estado(),
                "trabajos": await cola.listar_trabajos(s, limite=limite),
                "eventos": await cola.listar_eventos(s, limite=limite)}


@router.post("/laboratorio/cola/trabajos", response_model=TrabajoEncolado)
async def encolar(pedido: NuevoTrabajo, admin: User = Depends(get_super_admin),
                  _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """Encola un trabajo de laboratorio. Sin clave, una nueva cada vez."""
    import secrets
    clave = pedido.clave or f"lab-{secrets.token_hex(4)}"
    async with base.sesion() as s:
        return await cola.encolar(s, tipo=pedido.tipo, clave=clave, carga=pedido.carga)


@router.post("/laboratorio/cola/paso", response_model=Paso)
async def paso(admin: User = Depends(get_super_admin), _m: int = Depends(modo.exigir_encendido),
               _b=Depends(_con_base)):
    """Una vuelta del trabajador, ahora, sin esperar al bucle."""
    return await trabajador.una_vuelta()


@router.post("/laboratorio/cola/trabajos/{trabajo_id}/reintentar", response_model=Reintento)
async def reintentar(trabajo_id: int, admin: User = Depends(get_super_admin),
                     _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    async with base.sesion() as s:
        if not await cola.reintentar(s, trabajo_id):
            raise HTTPException(status_code=409, detail="Sólo se reintenta un trabajo muerto.")
    return {"id": trabajo_id, "estado": cola.PENDIENTE}


# ── los rieles ─────────────────────────────────────────────────────────────
#
#   Todo lo de acá pasa por `nucleo/rieles/operaciones.py`; las rutas sólo
#   traducen errores a códigos. Las de «simular» existen porque el riel es
#   el simulador: cuando haya uno real, esas dos no van a tener sentido y se
#   sacan (y devuelven 400 si el riel vigente no es el simulador).

def _error_de_operacion(e: Exception):
    if isinstance(e, rieles_op.ClaveDesconocida):
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


def _solo_simulador():
    from nucleo.rieles import vigente
    r = vigente()
    if not isinstance(r, simulador.Simulador):
        raise HTTPException(status_code=400, detail="Sólo se simula contra el simulador.")
    return r


@router.get("/laboratorio/rieles", response_model=Rieles)
async def rieles(limite: int = 50, admin: User = Depends(get_super_admin),
                 _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from nucleo.rieles import vigente
    r = vigente()
    limite = max(1, min(limite, 200))
    return {"riel": r.nombre, "ispb": r.ispb,
            "claves_de_prueba": [{"clave": c, "nombre": n, "banco": b, "comportamiento": comp}
                                 for c, _t, n, _d, _i, b, comp in simulador.CLAVES_DE_PRUEBA],
            "motivos_de_devolucion": pix.MOTIVOS_DE_DEVOLUCION,
            "resumen": await rieles_op.resumen(),
            "operaciones": await rieles_op.listar(limite),
            "avisos": await rieles_op.listar_avisos(limite)}


@router.get("/laboratorio/rieles/claves/{clave}", response_model=Titular)
async def clave(clave: str, admin: User = Depends(get_super_admin),
                _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        t = await rieles_op.consultar_clave(clave)
    except pix.ClaveInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))
    if t is None:
        raise HTTPException(status_code=404, detail="La clave no está en el DICT.")
    return t


@router.get("/laboratorio/rieles/operaciones/{operacion_id}", response_model=Operacion)
async def operacion(operacion_id: str, admin: User = Depends(get_super_admin),
                    _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await rieles_op.detalle(operacion_id)
    except rieles_op.OperacionInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/laboratorio/rieles/cobros", response_model=Operacion)
async def cobrar(pedido: NuevoCobro, admin: User = Depends(get_super_admin),
                 _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await rieles_op.crear_cobro(cuenta_id=pedido.cuenta, monto=pedido.monto,
                                           descripcion=pedido.descripcion or "", actor=admin.user_id)
    except (rieles_op.OperacionInvalida, comandos.MontoInvalido, ValueError) as e:
        raise _error_de_operacion(e)


@router.post("/laboratorio/rieles/cobros/{operacion_id}/simular_pago", response_model=AvisoRecibido)
async def simular_pago(operacion_id: str, pedido: PagoSimulado, admin: User = Depends(get_super_admin),
                       _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    r = _solo_simulador()
    try:
        op = await rieles_op.detalle(operacion_id)
    except rieles_op.OperacionInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    if op["direccion"] != rieles_op.ENTRADA:
        raise HTTPException(status_code=400, detail="Sólo se simula el pago de un cobro.")
    try:
        async with base.sesion() as s:
            return await r.simular_pago_del_cobro(s, txid=op["txid"], monto=comandos.a_centavos(op["monto"]),
                                                  pagador_clave=pedido.pagador_clave)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/laboratorio/rieles/pagos", response_model=Operacion)
async def pagar(pedido: NuevoPago, admin: User = Depends(get_super_admin),
                _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    import secrets
    referencia = pedido.referencia or f"lab-{secrets.token_hex(4)}"
    try:
        return await rieles_op.ordenar_pago(cuenta_id=pedido.cuenta, clave=pedido.clave, monto=pedido.monto,
                                            referencia=referencia, actor=admin.user_id,
                                            descripcion=pedido.descripcion or "")
    except (rieles_op.ClaveDesconocida, rieles_op.OperacionInvalida, pix.ClaveInvalida,
            AsientoInvalido, comandos.MontoInvalido) as e:
        raise _error_de_operacion(e)
    except DiaCerrado as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/laboratorio/rieles/pagos/{operacion_id}/simular_resultado", response_model=AvisoRecibido)
async def simular_resultado(operacion_id: str, pedido: ResultadoSimulado, admin: User = Depends(get_super_admin),
                            _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    r = _solo_simulador()
    try:
        op = await rieles_op.detalle(operacion_id)
    except rieles_op.OperacionInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    if op["direccion"] == rieles_op.ENTRADA or not op["end_to_end"]:
        raise HTTPException(status_code=400, detail="Sólo se simula el resultado de un pago o una devolución.")
    try:
        async with base.sesion() as s:
            return await r.simular_resultado(s, end_to_end=op["end_to_end"], estado=pedido.estado, motivo=pedido.motivo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/laboratorio/rieles/devoluciones", response_model=Operacion)
async def devolver(pedido: NuevaDevolucion, admin: User = Depends(get_super_admin),
                   _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await rieles_op.devolver(operacion_id=pedido.operacion, monto=pedido.monto, motivo=pedido.motivo,
                                        actor=admin.user_id)
    except (rieles_op.OperacionInvalida, AsientoInvalido, comandos.MontoInvalido) as e:
        raise _error_de_operacion(e)
    except DiaCerrado as e:
        raise HTTPException(status_code=409, detail=str(e))
