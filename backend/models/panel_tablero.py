"""
models/panel_tablero.py — Lo que queda del panel: el tablero y los
pendientes, los reportes, el lector de comprobantes, el uso, los errores, la
configuración, las tasas y las del BCV, la lista negra, el Bitcoin, y las dos
rutas viejas de operaciones.

LO QUE SE ARMA CAMPO POR CAMPO

    El tablero, los pendientes, los reportes, el uso, los errores, la
    configuración y el Bitcoin ya se armaban a mano en su ruta o su servicio:
    los contratos fijan esos campos. Lo que esos servicios calculan por dentro
    (los totales de un reporte, las funciones del uso, las rutas de los
    errores) queda libre: son resúmenes que arma el servicio, no documentos de
    la base, y su forma es del servicio.

LO QUE SALIA DE LA BASE TAL CUAL

    Las tasas, su historial, las del BCV, la lista negra y los errores
    registrados se leían con `{"_id": 0}` como única exclusión. Los contratos
    dejan los campos que escribe el único lugar que escribe en cada colección.
    Queda afuera quién cambió la tasa o bloqueó a alguien por su
    identificador interno.

LAS DOS RUTAS VIEJAS DE OPERACIONES DEVOLVIAN LA OPERACION ENTERA

    `GET /admin/transactions` (cada operación, menos las fotos) y
    `GET /admin/transactions/{id}` (la operación con sus fotos) devolvían el
    documento tal cual está en la base: con todo lo que cada medio de pago le
    fue anotando y con el beneficiario copiado entero. Ninguna pantalla de hoy
    las usa. Se les pone contrato —lo que describe la operación, y el
    beneficiario recortado por la misma lista que usa el historial del
    cliente— en vez de sacarlas: los permisos del panel todavía las nombran.

Un test (`tests/test_contratos_del_tablero.py`) recorre cada ruta con datos.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar
from models.movimientos import BeneficiarioDeLaOperacion


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


_Libre = (Optional[Any], None)

# ── El tablero y los pendientes ───────────────────────────────────────────

TableroDelPanel = _simple("TableroDelPanel", (
    "total_users", "verified_users", "pending_withdrawals", "completed_today", "total_volume_ris",
    "total_volume_ves"))


class PendientesDelPanel(BaseModel):
    pendientes: Dict[str, Escalar] = {}
    usuarios: Escalar = None


# ── Los reportes ──────────────────────────────────────────────────────────

FuenteDeReporte = _simple("FuenteDeReporte", ("clave", "etiqueta"))


class FuentesDeReporte(BaseModel):
    fuentes: List[FuenteDeReporte] = []


# El reporte en JSON. En planilla o CSV sale como archivo y no pasa por acá.
ReporteGenerado = _simple("ReporteGenerado", (
    "generado_at", "inicio_utc", "fin_utc", "operaciones", "truncado", "hay_mas"),
    criterios=_Libre, totales=_Libre, filas=_Libre)

TotalesDeMerma = _simple("TotalesDeMerma", (
    "merma_ves", "merma_ves_a_favor_del_negocio", "merma_ves_en_contra", "ves_prometido",
    "merma_pct_sobre_prometido"))
OrdenConMerma = _simple("OrdenConMerma", (
    "orden_id", "display_id", "created_at", "paid_at", "merma_calculada_at", "status", "user_email", "user_name",
    "moneda", "red", "rate", "amount_input", "amount_output", "pay_amount", "actually_paid", "outcome_amount",
    "outcome_currency", "topup_actually_paid", "topup_outcome_amount", "paid_ratio", "underpaid", "merma_ves"))


class MermaDeNowpayments(BaseModel):
    desde: Escalar = None
    hasta: Escalar = None
    total: Escalar = None
    sin_outcome: Escalar = None
    totales: Optional[TotalesDeMerma] = None
    ordenes: List[OrdenConMerma] = []


DesempenoDelLector = _simple("DesempenoDelLector", (
    "ventana", "lotes", "miradas", "resueltas", "corregidas", "avisadas", "no_pudo", "sin_lector", "de_antes",
    "desde", "hasta", "estado"))

UsoDeLaApp = _simple("UsoDeLaApp", ("dias", "desde", "hasta"),
                     funciones=_Libre, sin_uso=_Libre, por_dia=_Libre, base=_Libre)

# ── Los errores registrados ───────────────────────────────────────────────

# Lo que escribe `services/errores.anotar`, el único que escribe ahí. La
# traza y la IP se muestran a propósito: la pantalla existe para diagnosticar,
# y la lee sólo el super administrador.
ErrorRegistrado = _simple("ErrorRegistrado", (
    "rastro", "metodo", "ruta", "status", "tipo", "mensaje", "traza", "user_id", "ip", "cuando"))


class ErroresRegistrados(BaseModel):
    lineas: List[ErrorRegistrado] = []
    total: Escalar = None
    limite: Escalar = None
    saltar: Escalar = None


ResumenDeErrores = _simple("ResumenDeErrores", ("horas", "total"), rutas=_Libre, ultimo=_Libre)

# ── La configuración ──────────────────────────────────────────────────────

# Cada ajuste es la entrada del catálogo (`configuracion.catalogo_para_la_
# pantalla`) más su valor. Su forma es del catálogo, que es la que dibuja la
# pantalla: queda libre.


class ConfiguracionDelPanel(BaseModel):
    ajustes: List[Any] = []
    cambiados: List[Escalar] = []


# ── Las tasas ─────────────────────────────────────────────────────────────

# Los campos que escriben los dos únicos lugares que escriben la tasa
# (`database.py` al sembrar y `routes/admin.update_rates`), y los dos que
# lee el motor contable. Sin quién la cambió.
_CAMPOS_DE_LA_TASA = ("rate_id", "ris_to_ves", "ves_to_ris", "ves_to_ris_rate", "brl_to_ris", "usdtris_to_ves",
                      "usdcris_to_ves", "usd_to_ves", "brl_to_usd", "updated_at")
TasasDelSistema = _simple("TasasDelSistema", _CAMPOS_DE_LA_TASA)
TasaActualizada = _simple("TasaActualizada", ("message", *_CAMPOS_DE_LA_TASA))

CambioDeTasa = _simple("CambioDeTasa", (
    "route", "old_rate", "new_rate", "change_type", "admin_email", "reason", "timestamp"))


class HistorialDeTasas(BaseModel):
    entries: List[CambioDeTasa] = []
    count: Escalar = None


LecturaDelBcv = _simple("LecturaDelBcv", (
    "value_date", "fetched_at", "vencida", "edad_horas", "horas_de_vigencia"),
    rates=(Optional[Dict[str, Escalar]], None))


class HistorialDelBcv(BaseModel):
    entries: List[LecturaDelBcv] = []
    count: Escalar = None


BcvActualizado = _simple("BcvActualizado", ("success", "saved_new_snapshot"),
                         latest=(Optional[LecturaDelBcv], None))

# ── La lista negra ────────────────────────────────────────────────────────

# Quién bloqueó, por su nombre: es lo que la pantalla muestra. Su
# identificador interno (`banned_by`) queda afuera, igual que en las tasas.
EntradaDeLaListaNegra = _simple("EntradaDeLaListaNegra", (
    "blacklist_id", "type", "value", "reason", "banned_by_name", "banned_at"))


class ListaNegra(BaseModel):
    items: List[EntradaDeLaListaNegra] = []
    total: Escalar = None


AccionEnLaListaNegra = _simple("AccionEnLaListaNegra", ("success", "message", "blacklist_id"))

# ── El Bitcoin ────────────────────────────────────────────────────────────

ConfiguracionBtc = _simple("ConfiguracionBtc", (
    "margen", "comision", "tasa_usd_ves", "tasa_fijada_en", "tasa_horas_restantes", "tasa_vencida",
    "tasa_limite_horas", "btc_price_usd", "btc_price_source"),
    example=_Libre, defaults=_Libre)
ConfiguracionBtcGuardada = _simple("ConfiguracionBtcGuardada", ("success",), changes=_Libre)

TotalesBtc = _simple("TotalesBtc", ("count", "total_usd", "total_ves"))


class EstadisticasBtc(BaseModel):
    by_estado: Dict[str, TotalesBtc] = {}
    totals: Optional[TotalesBtc] = None


BeneficiarioBtc = _simple("BeneficiarioBtc", (
    "full_name", "id_document", "phone", "bank", "account_number", "payment_type"))
RemesaBtc = _simple("RemesaBtc", (
    "remesa_id", "user_id", "user_email", "user_name", "estado", "estado_label", "usd_cliente", "ves_recibe",
    "btc_pagar", "sats", "precio_btc_usado", "precio_con_margen", "tasa_ves", "memo", "payment_hash",
    "operador_id", "creado_en", "pagado_en", "enviado_en", "cancelado_en", "expira_en", "comprobante",
    "operador_nombre", "tipo"),
    beneficiario=(Optional[BeneficiarioBtc], None))


class RemesasBtc(BaseModel):
    items: List[RemesaBtc] = []
    counts: Dict[str, Escalar] = {}
    page: Escalar = None
    page_size: Escalar = None
    total: Escalar = None
    total_pages: Escalar = None


RemesaBtcEnviada = _simple("RemesaBtcEnviada", ("success", "message", "via"))

# ── Mantenimiento y las rutas viejas de operaciones ───────────────────────

FotosConvertidas = _simple("FotosConvertidas", ("message", "transactions_fixed"), errors=(List[Escalar], []))

_OPERACION = (
    "transaction_id", "display_id", "user_id", "user_name", "user_email", "type", "status", "route",
    "amount_input", "currency_input", "amount_output", "currency_output", "amount_brl", "amount_ris",
    "amount_ves", "currency", "rate", "rate_used", "payment_method", "created_at", "completed_at",
    "processed_at", "rejection_reason")
OperacionDelPanel = _simple("OperacionDelPanel", _OPERACION,
                            beneficiary_data=(Optional[BeneficiarioDeLaOperacion], None))


class OperacionesDelPanel(BaseModel):
    transactions: List[OperacionDelPanel] = []
    total: Escalar = None


# El detalle sí trae las fotos: es donde se viene a verlas.
DetalleDeOperacion = _simple("DetalleDeOperacion", (*_OPERACION, "proof_image"),
                             proof_images=(List[Escalar], []),
                             beneficiary_data=(Optional[BeneficiarioDeLaOperacion], None))
