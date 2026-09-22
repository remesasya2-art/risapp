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
from nucleo.identidad import formas as id_formas, legajos, simulador as id_simulador
from nucleo.cumplimiento import calendario, incidentes as cumpl_incidentes, ouvidoria as cumpl_ouvidoria
from nucleo.operacion import aprobaciones, bitacora
from nucleo.reportes import ReporteInvalido, registro as reportes_reg
from nucleo.reportes.periodos import PeriodoInvalido
from nucleo.riesgo import casos as riesgo_casos, monitoreo
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


class Verificacion(BaseModel):
    id: int
    proveedor: str
    puntaje_documento: int
    puntaje_vida: int
    puntaje_rostro: int
    situacion_cpf: str
    nombre_en_documento: str
    documento_vencido: bool
    aprobada: bool
    motivos: list[str]
    momento: Optional[str] = None


class Cruce(BaseModel):
    id: int
    titular: str
    lista: str
    clase: str
    nombre_en_lista: str
    detalle: Optional[str] = None
    momento: Optional[str] = None
    resuelto: bool
    resolucion: Optional[str] = None
    resuelto_por: Optional[str] = None
    resuelto_en: Optional[str] = None


class Legajo(BaseModel):
    id: str
    documento: str
    tipo: str
    nombre: str
    nacimiento: Optional[str] = None
    ocupacion: Optional[str] = None
    renta_declarada: Optional[str] = None
    pep_declarado: bool
    pep: bool
    origen_de_fondos: Optional[str] = None
    nivel_de_riesgo: Optional[str] = None
    estado: str
    vigente_hasta: Optional[str] = None
    motivo: Optional[str] = None
    decidido_por: Optional[str] = None
    cruzado_en: Optional[str] = None
    creado: Optional[str] = None
    actualizado: Optional[str] = None
    verificaciones: list[Verificacion] = Field(default_factory=list)
    cruces: list[Cruce] = Field(default_factory=list)


class Alerta(BaseModel):
    id: int
    titular: str
    cuenta: str
    operacion: str
    regla: str
    detalle: dict
    momento: Optional[str] = None
    caso: Optional[str] = None


class NotaDeCaso(BaseModel):
    autor: str
    texto: str
    momento: Optional[str] = None


class AlertaDelCaso(BaseModel):
    id: int
    regla: str
    operacion: str
    detalle: dict
    momento: Optional[str] = None


class Caso(BaseModel):
    id: str
    titular: str
    origen: str
    estado: str
    analista: Optional[str] = None
    detalle: Optional[str] = None
    abierto_en: Optional[str] = None
    analizar_hasta: Optional[str] = None
    concluido_en: Optional[str] = None
    conclusion: Optional[str] = None
    comunicar: Optional[bool] = None
    comunicar_hasta: Optional[str] = None
    aprobado_por: Optional[str] = None
    comunicado_en: Optional[str] = None
    acuse: Optional[str] = None
    archivado_en: Optional[str] = None
    analisis_vencido: bool
    comunicacion_vencida: bool
    notas: list[NotaDeCaso] = Field(default_factory=list)
    alertas: list[AlertaDelCaso] = Field(default_factory=list)


class Comunicacion(BaseModel):
    id: int
    caso: Optional[str] = None
    tipo: str
    periodo: Optional[int] = None
    archivo: str
    acuse: str
    enviada_en: Optional[str] = None
    enviada_por: str
    aprobada_por: str
    comunicador: str


class Riesgo(BaseModel):
    comunicador: str
    umbrales: dict
    resumen_alertas: dict
    resumen_casos: dict
    alertas: list[Alerta]
    casos: list[Caso]
    comunicaciones: list[Comunicacion]


class Reporte(BaseModel):
    id: int
    tipo: str
    periodo: str
    version: int
    documento: str
    resumen: dict
    estado: str
    generado_en: Optional[str] = None
    generado_por: str
    transmitido_en: Optional[str] = None
    transmitido_por: Optional[str] = None
    protocolo: Optional[str] = None
    transmisor: Optional[str] = None
    archivo: Optional[str] = None


class CuentaCosif(BaseModel):
    codigo: str
    nombre: str
    cosif: str


class Reportes(BaseModel):
    transmisor: str
    tipos: list[str]
    cosif: list[CuentaCosif]
    resumen: dict
    reportes: list[Reporte]


class NotaDeIncidente(BaseModel):
    autor: str
    texto: str
    momento: Optional[str] = None


class Incidente(BaseModel):
    id: str
    tipo: str
    titulo: str
    inicio: Optional[str] = None
    fin: Optional[str] = None
    impacto: str
    clientes_afectados: int
    relevante: bool
    estado: str
    causa: Optional[str] = None
    acciones: Optional[str] = None
    abierto_en: Optional[str] = None
    abierto_por: str
    comunicar_hasta: Optional[str] = None
    comunicado_en: Optional[str] = None
    comunicado_por: Optional[str] = None
    protocolo: Optional[str] = None
    cerrado_en: Optional[str] = None
    cerrado_por: Optional[str] = None
    comunicacion_vencida: bool
    notas: list[NotaDeIncidente]


class Reclamo(BaseModel):
    id: str
    protocolo: str
    titular: Optional[str] = None
    canal: str
    asunto: str
    descripcion: str
    caso_soporte: Optional[str] = None
    estado: str
    abierto_en: Optional[str] = None
    abierto_por: str
    responder_hasta: str
    respuesta: Optional[str] = None
    resultado: Optional[str] = None
    respondido_en: Optional[str] = None
    respondido_por: Optional[str] = None
    vencido: bool
    en_plazo: Optional[bool] = None


class Obligacion(BaseModel):
    obligacion: str
    periodicidad: str
    fuente: str
    plazo: str
    periodo: str
    vence: str
    dias: int
    estado: str
    vencido: bool
    detalle: str
    reporte: Optional[int] = None
    protocolo: Optional[str] = None


class AccionConPlazo(BaseModel):
    accion: str
    referencia: str
    titulo: str
    vence: str
    dias: int
    vencido: bool
    fuente: str


class Cumplimiento(BaseModel):
    resumen_calendario: dict
    calendario: list[Obligacion]
    acciones: list[AccionConPlazo]
    resumen_incidentes: dict
    incidentes: list[Incidente]
    tipos_de_incidente: list[str]
    resumen_reclamos: dict
    reclamos: list[Reclamo]
    canales: list[str]
    resultados: list[str]


class PedidoDeAprobacion(BaseModel):
    id: str
    accion: str
    objetivo: str
    carga: dict
    motivo: str
    estado: str
    pedido_por: str
    pedido_en: Optional[str] = None
    vence_en: Optional[str] = None
    decidido_por: Optional[str] = None
    decidido_en: Optional[str] = None
    nota: Optional[str] = None
    ejecutado_en: Optional[str] = None
    resultado: Optional[str] = None


class RenglonDeBitacora(BaseModel):
    id: int
    momento: str
    actor: str
    accion: str
    objetivo: str
    antes: Optional[dict] = None
    despues: Optional[dict] = None
    detalle: Optional[str] = None
    hash: str


class PanelDeOperacion(BaseModel):
    # No «Operacion»: ese nombre ya es el de una operación por un riel (PIX).
    resumen_aprobaciones: dict
    aprobaciones: list[PedidoDeAprobacion]
    acciones_con_cuatro_ojos: list[str]
    bitacora: list[RenglonDeBitacora]
    cadena_de_la_bitacora: Cadena
    claves_configurables: list[str]


class PersonaDePrueba(BaseModel):
    documento: str
    nombre: str
    comportamiento: str


class Identidad(BaseModel):
    verificador: str
    listas: str
    personas_de_prueba: list[PersonaDePrueba]
    origenes_de_fondos: list[str]
    niveles_de_riesgo: list[str]
    titulares: list[Legajo]


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
    titular: str = Field(min_length=1, max_length=40)      # el id del titular con legajo aprobado
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


class NuevoTitular(BaseModel):
    documento: str = Field(min_length=11, max_length=14)
    nombre: str = Field(min_length=1, max_length=120)
    nacimiento: Optional[str] = Field(default=None, max_length=10)
    ocupacion: Optional[str] = Field(default=None, max_length=80)
    renta_declarada: Optional[str] = Field(default=None, max_length=24)
    pep_declarado: bool = False
    origen_de_fondos: Optional[str] = Field(default=None, max_length=30)


class Aprobacion(BaseModel):
    nivel_de_riesgo: str = Field(pattern="^(bajo|medio|alto)$")


class Rechazo(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class Resolucion(BaseModel):
    resolucion: str = Field(min_length=1, max_length=300)


class NuevoCaso(BaseModel):
    titular: str = Field(min_length=1, max_length=40)
    detalle: str = Field(min_length=1, max_length=300)


class ComoQuien(BaseModel):
    # SOLO LABORATORIO: actuar a nombre de otra persona, para poder mostrar
    # los cuatro ojos con un solo super administrador logueado. En ACTIVO
    # se ignora: quien actúa es quien está logueado. Hay test y mutación.
    como: Optional[str] = Field(default=None, min_length=1, max_length=80)


class NotaNueva(ComoQuien):
    texto: str = Field(min_length=1, max_length=1000)


class ConclusionDelCaso(ComoQuien):
    conclusion: str = Field(min_length=1, max_length=2000)
    comunicar: bool


class NoOcurrencia(ComoQuien):
    anio: int = Field(ge=2020, le=2100)


class PedidoDeReporte(BaseModel):
    tipo: str = Field(pattern="^(" + "|".join(reportes_reg.TIPOS) + ")$")
    periodo: str = Field(min_length=4, max_length=10)


class NuevoIncidente(BaseModel):
    tipo: str = Field(pattern="^(" + "|".join(cumpl_incidentes.TIPOS) + ")$")
    titulo: str = Field(min_length=1, max_length=200)
    impacto: str = Field(min_length=1, max_length=2000)
    clientes_afectados: int = Field(ge=0, le=10_000_000)
    relevante: bool = False
    inicio: Optional[str] = Field(default=None, max_length=32)   # ISO; vacío es «ahora»


class CierreDeIncidente(BaseModel):
    causa: str = Field(min_length=1, max_length=2000)
    acciones: str = Field(min_length=1, max_length=2000)
    fin: Optional[str] = Field(default=None, max_length=32)


class NuevoReclamo(BaseModel):
    canal: str = Field(pattern="^(" + "|".join(cumpl_ouvidoria.CANALES) + ")$")
    asunto: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(min_length=1, max_length=4000)
    titular: Optional[str] = Field(default=None, max_length=40)
    caso_soporte: Optional[str] = Field(default=None, max_length=20)


class RespuestaDelReclamo(BaseModel):
    respuesta: str = Field(min_length=1, max_length=4000)
    resultado: str = Field(pattern="^(" + "|".join(cumpl_ouvidoria.RESULTADOS) + ")$")


class PedidoDeConfiguracion(BaseModel):
    clave: str = Field(pattern="^nucleo_[a-z0-9_]+$")
    valor: str = Field(min_length=1, max_length=24)
    motivo: str = Field(min_length=1, max_length=300)


class Motivo(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class Decision(ComoQuien):
    aprobar: bool
    nota: Optional[str] = Field(default=None, max_length=300)


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


async def _anotar(admin: User, accion: str, objetivo, antes=None, despues=None, detalle: Optional[str] = None):
    """La bitácora del núcleo, DESPUES de que la acción salió bien. Si falla,
    no deshace la acción (ver nucleo/operacion/bitacora.py)."""
    await bitacora.anotar_sin_romper(actor=admin.user_id, accion=accion, objetivo=str(objetivo),
                                     antes=antes, despues=despues, detalle=detalle)


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
    try:
        return await comandos.crear_cuenta(titular_ref=pedido.titular, moneda=pedido.moneda, de_prueba=True)
    except legajos.LegajoNoApto as e:
        raise HTTPException(status_code=409, detail=str(e))


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
        c = await comandos.cerrar_dia(dia=pedido.dia, actor=admin.user_id, nota=pedido.nota)
    except DiaCerrado as e:
        raise HTTPException(status_code=409, detail=str(e))
    await _anotar(admin, "cierre.dia", c["dia"], despues={"hasta_asiento": c["hasta_asiento"], "hash_final": c["hash_final"]}, detalle=pedido.nota)
    return c


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
    await _anotar(admin, "cola.reintento", trabajo_id, antes={"estado": cola.MUERTO}, despues={"estado": cola.PENDIENTE})
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


# ── identidad ──────────────────────────────────────────────────────────────

def _error_de_legajo(e: Exception):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/laboratorio/identidad", response_model=Identidad)
async def identidad(estado: Optional[str] = None, admin: User = Depends(get_super_admin),
                    _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from nucleo.identidad import listas as _l, verificador as _v
    return {"verificador": _v().nombre, "listas": _l().nombre,
            "personas_de_prueba": [{"documento": d, "nombre": n, "comportamiento": c}
                                   for d, n, _nac, c in id_simulador.PERSONAS_DE_PRUEBA],
            "origenes_de_fondos": list(id_formas.ORIGENES_DE_FONDOS),
            "niveles_de_riesgo": list(id_formas.NIVELES_DE_RIESGO),
            "titulares": await legajos.listar(estado=estado)}


@router.post("/laboratorio/identidad/titulares", response_model=Legajo)
async def crear_titular(pedido: NuevoTitular, admin: User = Depends(get_super_admin),
                        _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await legajos.crear_titular(documento=pedido.documento, nombre=pedido.nombre, actor=admin.user_id,
                                           nacimiento=pedido.nacimiento, ocupacion=pedido.ocupacion,
                                           renta_declarada=pedido.renta_declarada, pep_declarado=pedido.pep_declarado,
                                           origen_de_fondos=pedido.origen_de_fondos)
    except (legajos.LegajoInvalido, comandos.MontoInvalido, ValueError) as e:
        raise _error_de_legajo(e)


@router.get("/laboratorio/identidad/titulares/{titular_id}", response_model=Legajo)
async def titular(titular_id: str, admin: User = Depends(get_super_admin),
                  _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await legajos.detalle(titular_id)
    except legajos.LegajoInvalido as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/laboratorio/identidad/titulares/{titular_id}/verificar", response_model=Verificacion)
async def verificar(titular_id: str, admin: User = Depends(get_super_admin),
                    _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await legajos.verificar(titular_id, actor=admin.user_id)
    except legajos.LegajoInvalido as e:
        raise _error_de_legajo(e)


@router.post("/laboratorio/identidad/titulares/{titular_id}/cruzar", response_model=list[Cruce])
async def cruzar(titular_id: str, admin: User = Depends(get_super_admin),
                 _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await legajos.cruzar(titular_id, actor=admin.user_id)
    except legajos.LegajoInvalido as e:
        raise _error_de_legajo(e)


@router.post("/laboratorio/identidad/titulares/{titular_id}/aprobar", response_model=Legajo)
async def aprobar(titular_id: str, pedido: Aprobacion, admin: User = Depends(get_super_admin),
                  _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        l = await legajos.aprobar(titular_id, nivel_de_riesgo=pedido.nivel_de_riesgo, actor=admin.user_id)
    except legajos.LegajoInvalido as e:
        raise _error_de_legajo(e)
    await _anotar(admin, "legajo.aprobado", titular_id, despues={"nivel_de_riesgo": pedido.nivel_de_riesgo, "vigente_hasta": l.get("vigente_hasta")})
    return l


@router.post("/laboratorio/identidad/titulares/{titular_id}/rechazar", response_model=Legajo)
async def rechazar(titular_id: str, pedido: Rechazo, admin: User = Depends(get_super_admin),
                   _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        l = await legajos.rechazar(titular_id, motivo=pedido.motivo, actor=admin.user_id)
    except legajos.LegajoInvalido as e:
        raise _error_de_legajo(e)
    await _anotar(admin, "legajo.rechazado", titular_id, detalle=pedido.motivo)
    return l


@router.post("/laboratorio/identidad/cruces/{cruce_id}/resolver", response_model=Cruce)
async def resolver_cruce(cruce_id: int, pedido: Resolucion, admin: User = Depends(get_super_admin),
                         _m: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        c = await legajos.resolver_cruce(cruce_id, resolucion=pedido.resolucion, actor=admin.user_id)
    except legajos.LegajoInvalido as e:
        raise _error_de_legajo(e)
    await _anotar(admin, "cruce.resuelto", cruce_id, detalle=pedido.resolucion)
    return c


# ── riesgo ─────────────────────────────────────────────────────────────────

def _quien(admin: User, como: Optional[str], modo_vigente: int) -> str:
    """Quién actúa. En laboratorio se puede decir «como» otra persona, para
    mostrar los cuatro ojos; en activo, siempre quien está logueado."""
    if como and modo_vigente == modo.LABORATORIO:
        return como
    return admin.user_id


def _error_de_caso(e: Exception):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/laboratorio/riesgo", response_model=Riesgo)
async def riesgo(admin: User = Depends(get_super_admin),
                 modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from nucleo.riesgo import comunicador
    return {"comunicador": comunicador().nombre, "umbrales": await monitoreo.umbrales(),
            "resumen_alertas": await monitoreo.resumen(), "resumen_casos": await riesgo_casos.resumen(),
            "alertas": await monitoreo.listar(), "casos": await riesgo_casos.listar(),
            "comunicaciones": await riesgo_casos.listar_comunicaciones()}


@router.post("/laboratorio/riesgo/evaluar/{operacion_id}", response_model=list[Alerta])
async def evaluar(operacion_id: str, admin: User = Depends(get_super_admin),
                  modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """Vuelve a correr las reglas sobre una operación, a mano."""
    nuevas = await monitoreo.evaluar_operacion(operacion_id)
    return [a for a in await monitoreo.listar() if a["operacion"] == operacion_id and a["id"] in {n["id"] for n in nuevas}]


@router.post("/laboratorio/riesgo/casos", response_model=Caso)
async def abrir_caso(pedido: NuevoCaso, admin: User = Depends(get_super_admin),
                     modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        k = await riesgo_casos.abrir(titular=pedido.titular, origen="manual", actor=admin.user_id, detalle=pedido.detalle)
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)
    await _anotar(admin, "caso.abierto", k["id"], despues={"titular": pedido.titular}, detalle=pedido.detalle)
    return k


@router.get("/laboratorio/riesgo/casos/{caso_id}", response_model=Caso)
async def caso(caso_id: str, admin: User = Depends(get_super_admin),
               modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await riesgo_casos.detalle(caso_id)
    except riesgo_casos.CasoInvalido as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/laboratorio/riesgo/casos/{caso_id}/tomar", response_model=Caso)
async def tomar_caso(caso_id: str, pedido: ComoQuien, admin: User = Depends(get_super_admin),
                     modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await riesgo_casos.tomar(caso_id, analista=_quien(admin, pedido.como, modo_vigente))
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)


@router.post("/laboratorio/riesgo/casos/{caso_id}/anotar", response_model=Caso)
async def anotar_caso(caso_id: str, pedido: NotaNueva, admin: User = Depends(get_super_admin),
                      modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await riesgo_casos.anotar(caso_id, autor=_quien(admin, pedido.como, modo_vigente), texto=pedido.texto)
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)


@router.post("/laboratorio/riesgo/casos/{caso_id}/concluir", response_model=Caso)
async def concluir_caso(caso_id: str, pedido: ConclusionDelCaso, admin: User = Depends(get_super_admin),
                        modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        k = await riesgo_casos.concluir(caso_id, analista=_quien(admin, pedido.como, modo_vigente),
                                        conclusion=pedido.conclusion, comunicar=pedido.comunicar)
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)
    await _anotar(admin, "caso.concluido", caso_id, despues={"estado": k["estado"], "comunicar": pedido.comunicar, "analista": k["analista"]})
    return k


@router.post("/laboratorio/riesgo/casos/{caso_id}/aprobar_comunicacion", response_model=Caso)
async def aprobar_comunicacion(caso_id: str, pedido: ComoQuien, admin: User = Depends(get_super_admin),
                               modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        k = await riesgo_casos.aprobar_comunicacion(caso_id, aprobador=_quien(admin, pedido.como, modo_vigente))
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)
    await _anotar(admin, "caso.comunicado", caso_id, despues={"acuse": k["acuse"], "aprobado_por": k["aprobado_por"]})
    return k


@router.post("/laboratorio/riesgo/no_ocurrencia", response_model=Comunicacion)
async def no_ocurrencia(pedido: NoOcurrencia, admin: User = Depends(get_super_admin),
                        modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """La declaración anual. Quien la pide es quien está logueado; «como»
    nombra a la segunda firma (en laboratorio)."""
    try:
        m = await riesgo_casos.declarar_no_ocurrencia(anio=pedido.anio, actor=admin.user_id,
                                                       aprobador=_quien(admin, pedido.como, modo_vigente))
    except riesgo_casos.CasoInvalido as e:
        raise _error_de_caso(e)
    await _anotar(admin, "coaf.no_ocurrencia", pedido.anio, despues={"acuse": m["acuse"], "aprobada_por": m["aprobada_por"]})
    return m


# ── reportes regulatorios ──────────────────────────────────────────────────

def _error_de_reporte(e: Exception):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/laboratorio/reportes", response_model=Reportes)
async def reportes(admin: User = Depends(get_super_admin),
                   modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from nucleo import plan
    from nucleo.reportes import transmisor
    return {"transmisor": transmisor().nombre, "tipos": list(reportes_reg.TIPOS),
            "cosif": [{"codigo": c, "nombre": n, "cosif": plan.cosif_de(c)} for c, n, *_ in plan.CUENTAS],
            "resumen": await reportes_reg.resumen(), "reportes": await reportes_reg.listar()}


@router.post("/laboratorio/reportes/generar", response_model=Reporte)
async def generar_reporte(pedido: PedidoDeReporte, admin: User = Depends(get_super_admin),
                          modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        r = await reportes_reg.generar(pedido.tipo, pedido.periodo, actor=admin.user_id)
    except (ReporteInvalido, PeriodoInvalido) as e:
        raise _error_de_reporte(e)
    await _anotar(admin, "reporte.generado", f"{pedido.tipo} {pedido.periodo}", despues={"id": r["id"], "version": r["version"], "resumen": r["resumen"]})
    return r


@router.get("/laboratorio/reportes/{reporte_id}", response_model=Reporte)
async def reporte(reporte_id: int, admin: User = Depends(get_super_admin),
                  modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await reportes_reg.detalle(reporte_id)
    except ReporteInvalido as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/laboratorio/reportes/{reporte_id}/transmitir", response_model=PedidoDeAprobacion)
async def transmitir_reporte(reporte_id: int, pedido: Motivo, admin: User = Depends(get_super_admin),
                             modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """Mandarle un archivo al regulador es de cuatro ojos: acá se PIDE; otra
    persona lo aprueba en /laboratorio/operacion y ahí se transmite."""
    try:
        r = await reportes_reg.detalle(reporte_id)
        if r["protocolo"]:
            raise ReporteInvalido(f"El reporte {reporte_id} ya se transmitió (protocolo {r['protocolo']}).")
        return await aprobaciones.pedir(accion="transmitir_reporte", objetivo=f"reporte:{reporte_id}",
                                        carga={"reporte_id": reporte_id, "documento": r["documento"], "periodo": r["periodo"], "version": r["version"]},
                                        actor=admin.user_id, motivo=pedido.motivo)
    except (ReporteInvalido, aprobaciones.AprobacionInvalida) as e:
        raise _error_de_reporte(e)


# ── cumplimiento: incidentes, ouvidoria y calendario ──────────────────────

def _momento(texto: Optional[str]):
    """Un ISO opcional a datetime con zona; vacío es None (= ahora)."""
    if not texto:
        return None
    from datetime import datetime, timezone
    try:
        m = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"«{texto}» no es una fecha y hora.")
    return m if m.tzinfo else m.replace(tzinfo=timezone.utc)


@router.get("/laboratorio/cumplimiento", response_model=Cumplimiento)
async def cumplimiento(admin: User = Depends(get_super_admin),
                       modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    return {"resumen_calendario": await calendario.resumen(), "calendario": await calendario.obligaciones(),
            "acciones": await calendario.acciones_con_plazo(),
            "resumen_incidentes": await cumpl_incidentes.resumen(), "incidentes": await cumpl_incidentes.listar(),
            "tipos_de_incidente": list(cumpl_incidentes.TIPOS),
            "resumen_reclamos": await cumpl_ouvidoria.resumen(), "reclamos": await cumpl_ouvidoria.listar(),
            "canales": list(cumpl_ouvidoria.CANALES), "resultados": list(cumpl_ouvidoria.RESULTADOS)}


@router.post("/laboratorio/cumplimiento/incidentes", response_model=Incidente)
async def abrir_incidente(pedido: NuevoIncidente, admin: User = Depends(get_super_admin),
                          modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        i = await cumpl_incidentes.abrir(tipo=pedido.tipo, titulo=pedido.titulo, impacto=pedido.impacto,
                                         clientes_afectados=pedido.clientes_afectados, relevante=pedido.relevante,
                                         actor=admin.user_id, inicio=_momento(pedido.inicio))
    except cumpl_incidentes.IncidenteInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _anotar(admin, "incidente.abierto", i["id"], despues={"tipo": pedido.tipo, "relevante": pedido.relevante, "clientes_afectados": pedido.clientes_afectados}, detalle=pedido.titulo)
    return i


@router.post("/laboratorio/cumplimiento/incidentes/{incidente_id}/anotar", response_model=Incidente)
async def anotar_incidente(incidente_id: str, pedido: NotaNueva, admin: User = Depends(get_super_admin),
                           modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        return await cumpl_incidentes.anotar(incidente_id, autor=_quien(admin, pedido.como, modo_vigente), texto=pedido.texto)
    except cumpl_incidentes.IncidenteInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/laboratorio/cumplimiento/incidentes/{incidente_id}/comunicar", response_model=PedidoDeAprobacion)
async def comunicar_incidente(incidente_id: str, pedido: Motivo, admin: User = Depends(get_super_admin),
                              modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """Avisarle al BCB es de cuatro ojos: acá se PIDE; otra persona lo
    aprueba en /laboratorio/operacion y ahí se comunica."""
    try:
        i = await cumpl_incidentes.detalle(incidente_id)
        if not i["relevante"]:
            raise cumpl_incidentes.IncidenteInvalido("Un incidente no relevante no se comunica al BCB.")
        if i["protocolo"]:
            raise cumpl_incidentes.IncidenteInvalido(f"El incidente ya se comunicó (protocolo {i['protocolo']}).")
        return await aprobaciones.pedir(accion="comunicar_incidente", objetivo=f"incidente:{incidente_id}",
                                        carga={"incidente_id": incidente_id, "titulo": i["titulo"], "comunicar_hasta": i["comunicar_hasta"]},
                                        actor=admin.user_id, motivo=pedido.motivo)
    except (cumpl_incidentes.IncidenteInvalido, aprobaciones.AprobacionInvalida) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/laboratorio/cumplimiento/incidentes/{incidente_id}/cerrar", response_model=Incidente)
async def cerrar_incidente(incidente_id: str, pedido: CierreDeIncidente, admin: User = Depends(get_super_admin),
                           modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        i = await cumpl_incidentes.cerrar(incidente_id, actor=admin.user_id, causa=pedido.causa,
                                          acciones=pedido.acciones, fin=_momento(pedido.fin))
    except cumpl_incidentes.IncidenteInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _anotar(admin, "incidente.cerrado", incidente_id, despues={"causa": pedido.causa, "acciones": pedido.acciones, "fin": i["fin"]})
    return i


@router.post("/laboratorio/cumplimiento/reclamos", response_model=Reclamo)
async def abrir_reclamo(pedido: NuevoReclamo, admin: User = Depends(get_super_admin),
                        modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        r = await cumpl_ouvidoria.abrir(canal=pedido.canal, asunto=pedido.asunto, descripcion=pedido.descripcion,
                                        actor=admin.user_id, titular=pedido.titular, caso_soporte=pedido.caso_soporte)
    except cumpl_ouvidoria.ReclamoInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _anotar(admin, "reclamo.abierto", r["protocolo"], despues={"canal": pedido.canal, "responder_hasta": r["responder_hasta"], "caso_soporte": pedido.caso_soporte}, detalle=pedido.asunto)
    return r


@router.post("/laboratorio/cumplimiento/reclamos/{reclamo_id}/responder", response_model=Reclamo)
async def responder_reclamo(reclamo_id: str, pedido: RespuestaDelReclamo, admin: User = Depends(get_super_admin),
                            modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    try:
        r = await cumpl_ouvidoria.responder(reclamo_id, actor=admin.user_id, respuesta=pedido.respuesta, resultado=pedido.resultado)
    except cumpl_ouvidoria.ReclamoInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _anotar(admin, "reclamo.respondido", r["protocolo"], despues={"resultado": pedido.resultado, "en_plazo": r["en_plazo"]})
    return r


# ── operación: bitácora y cuatro ojos ─────────────────────────────────────

def _error_de_aprobacion(e: Exception):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/laboratorio/operacion", response_model=PanelDeOperacion)
async def operacion(admin: User = Depends(get_super_admin),
                    modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    from services import configuracion
    async with base.sesion() as s:
        cadena = await bitacora.verificar_cadena(s)
    return {"resumen_aprobaciones": await aprobaciones.resumen(), "aprobaciones": await aprobaciones.listar(),
            "acciones_con_cuatro_ojos": list(aprobaciones.EJECUTORES), "bitacora": await bitacora.listar(limite=100),
            "cadena_de_la_bitacora": {"ok": cadena["ok"], "asientos": cadena["renglones"], "roto_en": cadena["roto_en"],
                                      "motivo": cadena["motivo"], "hash_final": cadena.get("hash_final")},
            "claves_configurables": [c for c in configuracion.AJUSTES if c.startswith(aprobaciones.CLAVES_DEL_NUCLEO)]}


@router.post("/laboratorio/operacion/configuracion", response_model=PedidoDeAprobacion)
async def pedir_configuracion(pedido: PedidoDeConfiguracion, admin: User = Depends(get_super_admin),
                              modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """Pedir un cambio de `nucleo_modo` o de un umbral. Se valida acá, para
    que quien apruebe no apruebe un valor fuera de rango."""
    from services import configuracion
    try:
        valor, motivo_de_rechazo = configuracion.normalizar(pedido.clave, pedido.valor)
    except configuracion.AjusteDesconocido:
        raise HTTPException(status_code=400, detail=f"No existe el ajuste «{pedido.clave}».")
    if motivo_de_rechazo:
        raise HTTPException(status_code=400, detail=motivo_de_rechazo)
    try:
        return await aprobaciones.pedir(accion="configurar", objetivo=pedido.clave, carga={"clave": pedido.clave, "valor": pedido.valor},
                                        actor=admin.user_id, motivo=pedido.motivo)
    except aprobaciones.AprobacionInvalida as e:
        raise _error_de_aprobacion(e)


@router.post("/laboratorio/operacion/aprobaciones/{pedido_id}/decidir", response_model=PedidoDeAprobacion)
async def decidir_aprobacion(pedido_id: str, pedido: Decision, admin: User = Depends(get_super_admin),
                             modo_vigente: int = Depends(modo.exigir_encendido), _b=Depends(_con_base)):
    """La segunda firma. En laboratorio, «como» nombra a quien decide."""
    try:
        return await aprobaciones.decidir(pedido_id, actor=_quien(admin, pedido.como, modo_vigente), aprobar=pedido.aprobar, nota=pedido.nota)
    except aprobaciones.AprobacionInvalida as e:
        raise _error_de_aprobacion(e)
