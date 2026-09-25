"""
models/fuera_del_panel.py — Lo que devuelven las últimas rutas de datos que no
tenían contrato: la cola de pagos, el registro de accesos al panel, la marca de
enviado del operador de Bitcoin y las tres del PIX de la recarga.

LO QUE QUEDA SIN CONTRATO, A PROPOSITO

    - Las opciones de la huella (`/webauthn/*/options`): las arma la librería
      del estándar WebAuthn, campo por campo, a partir de nuestros datos. Un
      contrato ahí no protege nada de la base, y si la librería agrega un campo
      que el navegador espera, el contrato se lo comería y la entrada con huella
      fallaría sin error.
    - Los webhooks: les contestamos a Mercado Pago, Blink y NOWPayments, no a
      una pantalla.
    - Los archivos, las fotos y lo de Twilio.

Un test (`tests/test_contratos_fuera_del_panel.py`) recorre cada una.
"""
from typing import List

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── La cola de pagos (`/withdrawal/queue-stats`) ──────────────────────────

TotalPorMoneda = _simple("TotalPorMoneda", ("moneda", "total", "ordenes"))


class ColaDePagos(BaseModel):
    total_pending: Escalar = None
    waiting_in_queue: Escalar = None
    total_ves_pending: Escalar = None
    total_ris_pending: Escalar = None
    por_moneda: List[TotalPorMoneda] = []
    por_origen: List[TotalPorMoneda] = []


# ── Los accesos al panel (`/auth/2fa/admin-access-log`) ───────────────────

# Lo que escribe `security_2fa` al abrir una sesión del panel, el único que
# escribe ahí. La IP y el navegador salen a propósito: es el registro de quién
# entró, y lo lee sólo el super administrador.
AccesoAlPanel = _simple("AccesoAlPanel", (
    "user_id", "email", "role", "ip", "country", "user_agent", "two_factor_used", "session_minutes",
    "created_at"))


class RegistroDeAccesos(BaseModel):
    entries: List[AccesoAlPanel] = []
    count: Escalar = None


# ── Bitcoin: la marca de enviado del operador ─────────────────────────────

EnvioMarcadoPorElOperador = _simple("EnvioMarcadoPorElOperador", ("ok", "msg", "remesa_id"))

# ── El PIX de la recarga ──────────────────────────────────────────────────

PixCreado = _simple("PixCreado", (
    "payment_id", "mp_payment_id", "qr_code", "qr_code_base64", "copy_paste_code", "amount_ris", "amount_brl",
    "amount_ves", "expires_at", "expires_in_seconds"))
PixCancelado = _simple("PixCancelado", ("success", "message"))
PagoSimulado = _simple("PagoSimulado", ("status", "payment_id", "amount_ris", "new_balance_terceros"))
