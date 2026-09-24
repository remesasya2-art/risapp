"""
models/acciones_de_dinero.py — Lo que contestan las acciones del cliente que
mueven plata: pedir un retiro, cotizar y pagar un envío, recargar, pagar con
tarjeta, depositar cripto y generar una factura Bitcoin.

Hasta acá los contratos de salida cubrían lo que el cliente CONSULTA. Estas
son las rutas donde el cliente MANDA algo, y su respuesta puede llevarse datos
de más igual que una consulta: ya pasó con la cotización de encomiendas, que
le mostraba al cliente el margen.

Hoy todas arman la respuesta campo por campo, así que en pantalla no cambia
nada. El contrato es la segunda capa: el día que alguien escriba
`return orden` en una tarde apurada, sale sólo lo que está acá.

Y una razón más, propia de estas rutas: varias guardan la respuesta para
devolverla igual si el cliente reintenta (la idempotencia), y esa copia sale
de la base. Lo que se lee de la base pasa por el contrato antes de salir.

Un test (`tests/test_contratos_de_acciones_de_dinero.py`) compara las claves
que devuelve cada ruta, leídas del código, con su contrato: el contrato que
se come un campo deja la pantalla con un hueco y no avisa.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ── Enviar reais (desde el saldo) ─────────────────────────────────────────

MiEnvioDeReais = _simple("MiEnvioDeReais", (
    "success", "transaction_id", "display_id", "amount_brl"))

# ── Retiro a bolívares desde el saldo ─────────────────────────────────────

MiRetiroPedido = _simple("MiRetiroPedido", (
    "message", "transaction_id", "display_id", "amount_ris", "amount_ves", "rate"))

# ── Envío cripto: pagado por la pasarela o desde el saldo ─────────────────

MiEnvioCripto = _simple("MiEnvioCripto", (
    "transaction_id", "display_id", "order_id", "status", "funded_from",
    "pay_address", "pay_amount", "pay_currency", "payin_extra_id", "network",
    "network_label", "amount_crypto", "amount_ves", "rate", "currency"))

MiOrdenCriptoCancelada = _simple("MiOrdenCriptoCancelada", (
    "ok", "transaction_id", "status"))

# ── Recarga en bolívares ──────────────────────────────────────────────────

MiRecargaVes = _simple("MiRecargaVes", (
    "message", "transaction_id", "display_id", "amount_ves", "amount_ris"))

# ── Cotizar el envío a Venezuela (PIX o tarjeta al final) ─────────────────

# Lo que se le cobraría con tarjeta de crédito o de débito: el envío, la
# comisión y el total, las tres cifras (ver la ruta: sin el desglose, quien ve
# el total cree que le cobran de más).
DesgloseDeTarjeta = _simple("DesgloseDeTarjeta", (
    "envio_brl", "comision_brl", "total_brl"))

MiCotizacionVes = create_model(
    "MiCotizacionVes",
    credit_card=(Optional[DesgloseDeTarjeta], None),
    debit_card=(Optional[DesgloseDeTarjeta], None),
    **{c: (Escalar, None) for c in (
        "transaction_id", "display_id", "amount_ris", "amount_ves", "rate",
        "bono_aplicado", "amount_brl", "qr_code", "qr_code_base64",
        "copy_paste_code", "expires_at", "expires_in_seconds", "metodo",
        "payment_order_id")})

# ── Enviar reais pagando en bolívares ─────────────────────────────────────


class MiCotizacionReais(BaseModel):
    transaction_id: Escalar = None
    display_id: Escalar = None
    amount_ves: Escalar = None
    amount_brl: Escalar = None
    rate: Escalar = None
    # Sólo los NOMBRES de los bancos: la ruta los lee con una proyección que
    # trae el nombre y nada más. El número de cuenta y el titular los da la
    # pantalla de pago, no la cotización.
    bancos: List[str] = []
    expires_at: Escalar = None
    expires_in_seconds: Escalar = None


MiComprobanteRecibido = _simple("MiComprobanteRecibido", (
    "message", "transaction_id", "status"))

# ── Tarjeta ───────────────────────────────────────────────────────────────

MiCotizacionDeTarjeta = _simple("MiCotizacionDeTarjeta", (
    "amount_ris", "amount_brl_net", "fee_brl", "total_charged_brl", "payment_type_id"))

MiPagoConTarjeta = _simple("MiPagoConTarjeta", (
    "status", "status_detail", "payment_id", "amount_ris_credited",
    "total_charged_brl", "fee_brl"))

# ── Depósito cripto ───────────────────────────────────────────────────────

MiDepositoCripto = _simple("MiDepositoCripto", (
    "order_id", "pay_address", "pay_amount", "pay_currency", "payin_extra_id",
    "network", "network_label", "credit_amount", "fee_amount", "fee_percentage"))

# ── Bitcoin ───────────────────────────────────────────────────────────────

# Sin `precio_con_margen`, que la orden guarda en la base: con él y el precio
# de mercado (que es público, lo publica `/btc/precio`) el cliente saca el
# margen exacto de la operación. Hoy la ruta no lo devuelve; el contrato
# asegura que no empiece a hacerlo.
MiFacturaBtc = _simple("MiFacturaBtc", (
    "remesa_id", "qr", "payment_request", "btc", "sats", "usd", "ves_recibe",
    "precio_btc_usado", "tasa_ves", "expira_en_segundos", "expira_en", "aviso"))

MiRemesaCancelada = _simple("MiRemesaCancelada", ("ok", "msg"))
