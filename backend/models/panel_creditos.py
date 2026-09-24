"""
models/panel_creditos.py — Lo que el panel ve de los depósitos en cripto: la
lista y el reporte por día.

LOS DOS DEVOLVIAN CADA DEPOSITO ENTERO

    Cada depósito salía tal como lo guarda la integración con el proveedor
    de pagos: con la dirección a la que se pagó, la etiqueta de la red, el
    texto del error cuando la acreditación falló y la última vez que llegó un
    aviso del proveedor. La pantalla muestra el pedido, la fecha, quién, el
    monto, la moneda, de dónde vino, la nota y el estado.

    El contrato deja eso, más lo que identifica y explica cada depósito (la
    red, lo que se pagó y lo que se acreditó, la comisión). El texto del
    error no: es un mensaje interno, y se ve en el registro del servidor.

El reporte en CSV no pasa por acá: es un archivo, y FastAPI lo devuelve tal
cual aunque la ruta tenga contrato.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


DepositoCripto = _simple("DepositoCripto", (
    "order_id", "payment_id", "user_id", "user_name", "user_email", "currency", "pay_currency", "network",
    "amount", "pay_amount", "fee_amount", "credit_amount", "status", "last_payment_status", "credited",
    "created_at", "credited_at", "source", "admin_note"))


class DepositosCripto(BaseModel):
    total: Escalar = None
    counts: Optional[Dict[str, Escalar]] = None
    items: List[DepositoCripto] = []


RangoDelReporte = _simple("RangoDelReporte", ("date_from", "date_to"))
TotalesDelReporte = _simple("TotalesDelReporte", ("usdt", "usdc", "count"))
DiaDelReporte = _simple("DiaDelReporte", ("date", "usdt", "usdc", "count"))


class ReporteDeDepositosCripto(BaseModel):
    range: Optional[RangoDelReporte] = None
    currency: Escalar = None
    totals: Optional[TotalesDelReporte] = None
    by_day: List[DiaDelReporte] = []
    items: List[DepositoCripto] = []
