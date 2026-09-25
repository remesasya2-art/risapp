"""
models/panel_encomiendas.py — Lo que el panel ve y hace con las encomiendas:
la puesta en marcha, la configuración, las transportistas y sus agencias, los
orígenes, las tarifas, el retiro en el correo, la cola de envíos, el historial,
la rentabilidad por viaje, las matrices de precios y el almacén de fotos.

CASI TODO SE ARMA CAMPO POR CAMPO

    `routes/envios_admin.py` y los servicios `services/envios_*` arman cada
    respuesta a mano, y ya sacan lo que no se muestra: la cuenta bancaria de
    una transportista (`_sin_cuenta`) y los datos personales de quien retira
    en el correo (`_sin_datos_personales`). Los contratos fijan esa forma: el
    día que alguien agregue «un dato más» a un envío, no sale solo.

LO QUE QUEDA LIBRE, A PROPOSITO

    La configuración de cada bloque, las tarifas (vigente, borrador e
    historial), la regla de peso y los límites de cada transportista. Tienen
    su propio esquema, que valida el servicio al guardar (`ESQUEMAS`,
    `envios_tarifa_editor`), y lo que se lee es exactamente lo que se guardó.
    Repetir acá cada esquema haría que agregar un campo a la tarifa exija
    tocarlo en dos lugares, y el que se olvida del segundo lo pierde en
    silencio en la pantalla que lo edita.

El registro de lo que se hizo en cada envío (cobros, estados) es del
servicio; acá se fija lo que la pantalla recibe.

Un test (`tests/test_contratos_de_encomiendas.py`) recorre el circuito
completo y compara cada lectura con su función llamada a mano.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


_Libre = (Optional[Any], None)
_Textos = (List[Escalar], [])

# ── La puesta en marcha y la configuración ────────────────────────────────

# Cada paso pone lo suyo: la tarifa, su `version_id` y su moneda; el retiro,
# quién está de turno; las agencias, cuál es el punto de entrega.
PasoDeLaPuestaEnMarcha = _simple("PasoDeLaPuestaEnMarcha", (
    "clave", "titulo", "estado", "detalle", "donde", "brasil", "venezuela", "total", "vigentes", "version_id",
    "moneda", "de_turno", "punto_entrega"))


class EstadoDelModulo(BaseModel):
    puede_operar: Escalar = None
    hay_lecturas_fallidas: Escalar = None
    pasos: List[PasoDeLaPuestaEnMarcha] = []
    faltan: Escalar = None
    siguiente: Escalar = None


class BloquesDeConfiguracion(BaseModel):
    bloques: Dict[str, Any] = {}
    disponibles: List[Escalar] = []


# `GET /config/{bloque}` devuelve el bloque tal como se guardó: su forma la
# fija el esquema del bloque, no este archivo.
BloqueDeConfiguracion = Dict[str, Any]
BloqueGuardado = _simple("BloqueGuardado", ("ok", "bloque"), valor=_Libre)

# ── Transportistas y agencias ─────────────────────────────────────────────

Transportista = _simple("Transportista", (
    "transportista_id", "codigo", "nombre", "rol", "activo", "orden", "moneda", "plantilla_rastreo",
    "fuente_referencia", "notas", "cuenta_bancaria", "creado_at", "actualizado_at"),
    regla_peso=_Libre, limites=_Libre)


class Transportistas(BaseModel):
    transportistas: List[Transportista] = []


TransportistaCreada = _simple("TransportistaCreada", ("ok", "transportista_id"))
TransportistaEditada = _simple("TransportistaEditada", ("ok",), valor=(Optional[Transportista], None),
                               avisos=_Textos)
CuentaCambiada = _simple("CuentaCambiada", ("ok", "version_id", "numero"))

Agencia = _simple("Agencia", (
    "transportista_id", "codigo", "nombre", "estado", "ciudad", "direccion", "zona", "codigo_postal", "activa",
    "es_punto_entrega", "creada_at", "actualizada_at"))


class Agencias(BaseModel):
    agencias: List[Agencia] = []


AgenciaCreada = _simple("AgenciaCreada", ("ok", "codigo"))
AgenciaEditada = _simple("AgenciaEditada", ("ok",), valor=(Optional[Agencia], None))

FilaRechazada = _simple("FilaRechazada", ("fila", "motivo"), **{"datos": _Libre})
AgenciasImportadas = _simple("AgenciasImportadas", ("creadas", "actualizadas", "total_rechazadas"),
                             rechazadas=(List[FilaRechazada], []))

# ── Orígenes ──────────────────────────────────────────────────────────────

Origen = _simple("Origen", ("cep", "cep_legible", "ciudad", "uf", "activo", "tiene_matriz", "creado_at",
                            "actualizado_at"))
OrigenPropuesto = _simple("OrigenPropuesto", ("cep", "cep_legible", "pedidos", "ciudad", "uf", "ultima_at",
                                              "primera_at", "estado"))


class Origenes(BaseModel):
    origenes: List[Origen] = []
    uf_disponibles: List[Escalar] = []
    matriz_legible: Escalar = None
    propuestos: List[OrigenPropuesto] = []


OrigenGuardado = _simple("OrigenGuardado", ("ok", "ya_existia", "estado"), valor=(Optional[Origen], None))
OrigenesImportados = _simple("OrigenesImportados", (
    "ok", "confirmado", "nuevas", "actualiza", "actualizadas", "total_rechazadas"),
    rechazadas=(List[FilaRechazada], []),
    muestra_nuevas=(List[Origen], []),
    muestra_actualiza=_Libre)

# ── Tarifas ───────────────────────────────────────────────────────────────


class TarifasDelPanel(BaseModel):
    vigente: Optional[Any] = None
    borrador: Optional[Any] = None
    origen_borrador: Escalar = None
    historial: List[Any] = []


class BorradorGuardado(BaseModel):
    ok: Escalar = None
    borrador: Optional[Any] = None
    advertencias: List[Any] = []


FilaDeLaComparacion = _simple("FilaDeLaComparacion", ("variacion_pct",), caja=_Libre, nuevo=_Libre, actual=_Libre)


class SimulacionDeTarifa(BaseModel):
    comparacion: List[FilaDeLaComparacion] = []
    bloqueos: List[Any] = []
    fecha_simulada: Escalar = None


TarifaPublicada = _simple("TarifaPublicada", ("ok", "version_id", "vigente_desde"))

# ── El retiro en el correo ────────────────────────────────────────────────

# De la nómina, sin CPF ni teléfono (`_sin_datos_personales`). Al crear o
# editar, la respuesta devuelve lo que se acaba de escribir: ésa sí los trae.
Colaborador = _simple("Colaborador", (
    "colaborador_id", "nombre", "cpf", "telefono", "activo", "autorizado_desde", "autorizado_hasta", "notas",
    "creado_at", "creado_por", "actualizado_at"))

VistaPreviaDelRetiro = _simple("VistaPreviaDelRetiro", (
    "disponible", "retirador_id", "retirador_nombre", "retirador_motivo", "destinatario", "razon_social", "agencia",
    "linea_agencia", "modalidad", "caixa_postal", "ciudad", "uf", "cep", "texto_copiable", "congelado_at"),
    faltantes=_Textos)


class RetiroEnElCorreo(BaseModel):
    nomina: List[Colaborador] = []
    vista_previa: Optional[VistaPreviaDelRetiro] = None


ColaboradorGuardado = _simple("ColaboradorGuardado", ("ok",), valor=(Optional[Colaborador], None))
TurnoDesignado = _simple("TurnoDesignado", ("ok", "de_turno"), vista_previa=(Optional[VistaPreviaDelRetiro], None))

# ── La cola, el historial y el ticket ─────────────────────────────────────

EnvioEnLaCola = _simple("EnvioEnLaCola", (
    "envio_id", "display_id", "codigo_objeto", "comprobante_asset_id", "comprobante_verificado",
    "foto_repetida_en", "agencia_destino", "estado_ve", "guarda_vence_at", "dias_de_guarda_restantes",
    "puede_salir", "flete_modalidad", "flete_estado", "puede_entregar", "estado", "created_at"),
    partidas_impagas=_Textos)
GrupoDeLaCola = _simple("GrupoDeLaCola", ("retirador_nombre", "cuantos"), envios=(List[EnvioEnLaCola], []))


class ColaDeEnvios(BaseModel):
    estado: Escalar = None
    total: Escalar = None
    hay_mas: Escalar = None
    degradado: Escalar = None
    grupos: List[GrupoDeLaCola] = []


EnvioDelHistorial = _simple("EnvioDelHistorial", (
    "envio_id", "display_id", "estado", "created_at", "codigo_objeto", "destinatario", "agencia", "ciudad",
    "estado_ve", "guia", "total_ris", "retirado_por", "retirado_at", "espera_retiro"))


class HistorialDeEnvios(BaseModel):
    envios: List[EnvioDelHistorial] = []
    hay_mas: Escalar = None
    degradado: Escalar = None


DestinatarioDelTicket = _simple("DestinatarioDelTicket", ("nombre", "documento", "telefono"))
AgenciaDelTicket = _simple("AgenciaDelTicket", ("nombre", "codigo", "ciudad", "estado_ve", "direccion",
                                                "transportista"))
PagoDelTicket = _simple("PagoDelTicket", ("modalidad", "cobrar_al_recibir", "flete_estado", "flete_monto_ris"))
PaqueteDelTicket = _simple("PaqueteDelTicket", ("peso_kg", "peso_es_verificado", "contenido"))


class TicketDelEnvio(BaseModel):
    envio_id: Escalar = None
    display_id: Escalar = None
    estado: Escalar = None
    codigo_objeto: Escalar = None
    destinatario: Optional[DestinatarioDelTicket] = None
    agencia: Optional[AgenciaDelTicket] = None
    pago: Optional[PagoDelTicket] = None
    paquete: Optional[PaqueteDelTicket] = None
    puede_salir: Escalar = None
    partidas_impagas: List[Escalar] = []


# ── Lo que contesta cada acción sobre un envío ────────────────────────────

CobroDelEnvio = _simple("CobroDelEnvio", ("partida", "estado", "monto_ris", "saldo_restante", "entry_id", "motivo"))
DevolucionDelEnvio = _simple("DevolucionDelEnvio", ("estado", "monto_ris", "saldo_restante", "entry_id"))

# Una sola forma para todas las acciones: cada una pone lo suyo, y con
# `exclude_unset` lo que no puso no sale. Separarlas en diez modelos
# repetiría diez veces `ok`, `envio_id` y `estado`.
AccionSobreUnEnvio = _simple("AccionSobreUnEnvio", (
    "ok", "envio_id", "estado", "ya_verificado", "guarda_vence_at", "guia", "monto_acordado_ris", "rama",
    "diferencia_ris", "total_final_ris", "puede_salir", "correccion"),
    cobro=(Optional[CobroDelEnvio], None),
    devolucion=(Optional[DevolucionDelEnvio], None),
    partidas_impagas=_Textos,
    entrega_final=_Libre,
    desvio=_Libre)

EnvioRetirado = _simple("EnvioRetirado", ("codigo", "envio_id", "display_id"))
EnvioRechazado = _simple("EnvioRechazado", ("codigo", "motivo"))
LoteRetirado = _simple("LoteRetirado", ("ok", "lote_id", "cuantos", "cuantos_rechazados"),
                       retirados=(List[EnvioRetirado], []),
                       rechazados=(List[EnvioRechazado], []))

# ── Rentabilidad por viaje y precios observados ───────────────────────────

EnvioDelViaje = _simple("EnvioDelViaje", ("envio_id", "display_id", "estado", "cobrado_ris", "pendiente_ris",
                                          "peso_verificado_kg"))
Viaje = _simple("Viaje", (
    "lote_id", "retirado_por", "created_at", "cuantos", "cobrado_ris", "pendiente_ris", "peso_total_kg",
    "costo_viaje_ris", "resultado_ris", "costo_por_kg_ris", "falta_el_costo"),
    envios=(List[EnvioDelViaje], []))

Observacion = _simple("Observacion", (
    "rol", "clave", "hasta_kg", "muestras", "promedio", "mediana", "minimo", "maximo", "dispersion", "confiable",
    "por_que_no"))


class PreciosObservados(BaseModel):
    observaciones: List[Observacion] = []
    muestras_minimas: Escalar = None


FilaDeMatriz = _simple("FilaDeMatriz", (
    "transportista_id", "clave", "hasta_kg", "precio", "moneda", "origen", "actualizada_at", "aprobada_por",
    "desactualizada"))
FilaDeMatrizGuardada = _simple("FilaDeMatrizGuardada", ("ok",), fila=(Optional[FilaDeMatriz], None))

CoberturaDeUnaTransportista = _simple("CoberturaDeUnaTransportista", ("transportista_id", "codigo", "rol"),
                                      cargadas=_Textos, necesarias=_Textos, faltan=_Textos)
CoberturaDeMatrices = _simple("CoberturaDeMatrices", ("legible",),
                              transportistas=(List[CoberturaDeUnaTransportista], []))


class Matrices(BaseModel):
    filas: List[FilaDeMatriz] = []
    dias_frescura: Escalar = None
    cobertura: Optional[CoberturaDeMatrices] = None


MatricesImportadas = _simple("MatricesImportadas", (
    "ok", "confirmado", "guardadas", "validas", "total_rechazadas"),
    rechazadas=(List[FilaRechazada], []),
    muestra=_Libre)

# ── El almacén de fotos ───────────────────────────────────────────────────

EstadoDelAlmacen = _simple("EstadoDelAlmacen", (
    "activo", "endpoint_host", "endpoint_https", "hilos", "bucket", "prefijo", "credenciales_cargadas",
    "en_mongo", "en_almacen", "con_problema"),
    variables_faltantes=_Textos)
PruebaDelAlmacen = _simple("PruebaDelAlmacen", ("ok", "detalle"), faltantes=_Textos)
MigracionDelAlmacen = _simple("MigracionDelAlmacen", (
    "activo", "migrados", "fallidos", "sospechosos", "ya_estaban", "parcial"),
    detalle=_Textos)
