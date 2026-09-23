"""
models/dinero_en_transito.py — Los contratos de salida de créditos cripto, PIX
y retiros, vistos por el cliente.

Todas estas rutas ya armaban la respuesta campo por campo: en pantalla no
cambia nada. El contrato es la segunda capa, para que un `return doc` o un
`**pago` escrito en una tarde apurada no mande lo que el documento tenga
adentro —en `gestor_pix_payments`, por ejemplo, el identificador del pago en
el procesador y la nota de seguridad de un pago sospechoso—.

Un test (`tests/test_contratos_de_dinero_en_transito.py`) compara las claves
que devuelve cada ruta, leídas del código, con su contrato: el contrato que
se come un campo deja la pantalla con un hueco y no avisa.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar
from models.movimientos import BeneficiarioDeLaOperacion


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ── Créditos cripto ───────────────────────────────────────────────────────

UnaRed = _simple("UnaRed", ("ticker", "label", "is_default", "min_amount",
                            "min_amount_raw", "min_amount_source"))


class RedesDeCredito(BaseModel):
    currency: Escalar = None
    networks: List[UnaRed] = []
    default_ticker: Escalar = None


MontoMinimoDeCredito = _simple("MontoMinimoDeCredito", (
    "currency", "network", "min_amount", "min_amount_raw", "source"))

EstadoDeMiDeposito = _simple("EstadoDeMiDeposito", (
    "order_id", "status", "credited", "currency", "amount"))

# Los campos de las dos proyecciones de `build_history_pipeline`
# (routes/credits.py) —depósitos y envíos—, más la etiqueta de la moneda que
# se agrega después.
CAMPOS_DEL_HISTORIAL_CRIPTO = (
    "kind", "order_id", "currency", "date", "created_at", "amount",
    "credit_amount", "credited", "credited_at", "status", "network",
    "pay_currency", "fee_amount", "source", "transaction_id", "display_id",
    "completed_at", "amount_output", "currency_output", "rate", "funded_from",
    "rejected_reason", "refund_amount", "refunded_to_balance",
    "refunded_to_balance_field", "currency_label",
)

UnMovimientoCripto = create_model(
    "UnMovimientoCripto",
    beneficiary_data=(Optional[BeneficiarioDeLaOperacion], None),
    **{c: (Escalar, None) for c in CAMPOS_DEL_HISTORIAL_CRIPTO})


class MiHistorialCripto(BaseModel):
    total: Escalar = None
    page: Escalar = None
    limit: Escalar = None
    items: List[UnMovimientoCripto] = []


# ── PIX ───────────────────────────────────────────────────────────────────

MiPixPendiente = _simple("MiPixPendiente", (
    "has_pending", "payment_id", "qr_code", "qr_code_base64", "copy_paste_code",
    "amount_ris", "amount_brl", "expires_at", "expires_in_seconds", "created_at"))

EstadoDeMiPix = _simple("EstadoDeMiPix", (
    "payment_id", "status", "amount_ris", "amount_ves", "created_at", "paid_at"))

MiPixActivo = _simple("MiPixActivo", (
    "has_active", "payment_id", "amount_ris", "amount_ves", "expires_in_seconds"))

UnPixDeMiHistorial = _simple("UnPixDeMiHistorial", (
    "payment_id", "amount_ris", "amount_brl", "client_name", "status",
    "created_at", "paid_at"))


# ── Retiros ───────────────────────────────────────────────────────────────

MiRetiroPendiente = create_model(
    "MiRetiroPendiente",
    beneficiary_data=(Optional[BeneficiarioDeLaOperacion], None),
    **{c: (Escalar, None) for c in (
        "has_pending", "transaction_id", "display_id", "amount_input",
        "amount_output", "created_at")})

EstadoDeMiEnvioCripto = _simple("EstadoDeMiEnvioCripto", (
    "transaction_id", "status", "amount_ves", "paid_ratio", "topup_pay_address",
    "topup_pay_amount", "topup_pay_currency", "topup_network",
    "topup_payin_extra_id", "topup_expires_at"))
