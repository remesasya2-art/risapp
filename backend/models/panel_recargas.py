"""
models/panel_recargas.py — Lo que el panel ve de las recargas: la cola de
recargas en bolívares, el control de referencias repetidas, y las rutas
viejas de recargas y registros de pago.

La cola en bolívares se arma campo por campo (`services/recargas_ves.cola`):
el contrato fija esos campos.

TRES RUTAS VIEJAS DEVOLVIAN DOCUMENTOS ENTEROS

    `/recharges/pending` devolvía cada operación de recarga tal cual está en
    la base (menos las fotos), y `/payment-records` y `/payment-records/{id}`
    cada registro de pago entero —el segundo, con la foto—. Ninguna pantalla
    de hoy las usa. Se les pone contrato con los campos que escribe el único
    lugar que las llena (`admin_routes.approve_recharge`), en vez de sacarlas:
    los permisos del panel todavía las nombran (`services/permisos.py`), y
    sacar una ruta que alguien puede estar usando desde afuera es una
    decisión, no un arreglo.

Un test (`tests/test_contratos_del_panel.py`) compara lo que lee la pantalla
de recargas con el contrato, y recorre la cola por HTTP contra su servicio.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


Antiguedad = _simple("AntiguedadDeLaRecarga", ("horas", "nivel"))

# ── La cola de recargas en bolívares ──────────────────────────────────────

RecargaEnLaCola = _simple("RecargaEnLaCola", (
    "transaction_id", "referencia", "posicion", "user_id", "user_name", "user_email", "user_phone",
    "amount_ves", "amount_ris", "rate_used", "status", "proof_image",
    "destination_bank", "destination_bank_id", "destination_bank_name", "reference_digits",
    "rejection_reason", "payment_method", "created_at", "processed_at", "processed_by",
    "assigned_to", "assigned_to_name", "banco_elegido_a_mano", "falta_banco", "falta_comprobante"),
    antiguedad=(Optional[Antiguedad], None))

ContadoresDeRecargas = _simple("ContadoresDeRecargas", (
    "total", "pendientes", "aprobadas", "rechazadas", "ves_pendiente", "sin_banco", "sin_comprobante"),
    mas_vieja=(Optional[Antiguedad], None))


class ColaDeRecargasVes(BaseModel):
    recharges: List[RecargaEnLaCola] = []
    total: Escalar = None
    limite: Escalar = None
    saltear: Escalar = None
    hay_mas: Escalar = None
    estado: Escalar = None
    busqueda: Escalar = None
    counters: Optional[ContadoresDeRecargas] = None


FaltantesDeRecargas = _simple("FaltantesDeRecargas", ("total_pendientes", "sin_banco", "sin_comprobante"))


class RecargasVesPendientes(BaseModel):
    recharges: List[RecargaEnLaCola] = []
    faltantes: Optional[FaltantesDeRecargas] = None


# ── Referencias repetidas ─────────────────────────────────────────────────

RecargaConLaMismaReferencia = _simple("RecargaConLaMismaReferencia", (
    "transaction_id", "user_id", "user_name", "user_email", "amount_ves", "status", "created_at",
    "is_other_user"))


class ControlDeReferencia(BaseModel):
    digits: Escalar = None
    has_collision: Escalar = None
    matches: List[RecargaConLaMismaReferencia] = []
    first_registered: Optional[RecargaConLaMismaReferencia] = None


# ── Las rutas viejas ──────────────────────────────────────────────────────

# Una recarga pendiente: lo que describe la operación, sin las fotos.
RecargaPendiente = _simple("RecargaPendiente", (
    "transaction_id", "display_id", "user_id", "user_name", "user_email", "type", "status",
    "amount_input", "currency_input", "amount_output", "currency_output", "amount_brl", "amount_ris",
    "amount_ves", "rate", "rate_used", "payment_method", "created_at", "completed_at"))


class RecargasPendientes(BaseModel):
    recharges: List[RecargaPendiente] = []


FotoDeLaRecarga = _simple("FotoDeLaRecarga", ("transaction_id", "proof_image", "amount_input", "status"))

# Un registro de pago: lo que escribe `approve_recharge`. La foto sólo en el
# detalle de uno: la lista no la traía y sigue sin traerla.
RegistroDePago = _simple("RegistroDePago", (
    "record_type", "transaction_id", "user_id", "user_name", "user_email", "amount_brl", "amount_ris",
    "proof_image", "approved_by", "approved_by_email", "processed_via", "created_at", "completed_at",
    "recorded_at"))


class RegistrosDePago(BaseModel):
    records: List[RegistroDePago] = []
