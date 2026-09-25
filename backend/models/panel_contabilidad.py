"""
models/panel_contabilidad.py — Lo que devuelven las rutas de contabilidad que
no tienen pantalla: los bancos y su libro, las tasas de USDT, las operaciones
de compra y venta, el libro de USDT, el reporte por ruta, y el motor contable
nuevo (lotes, ventas P2P, informe ejecutivo, su registro y la conciliación).

POR QUE TIENEN CONTRATO SI NADIE LAS MIRA

    Las dos pantallas de contabilidad (`Accounting.jsx` y `AccountingV2.jsx`)
    se borraron del frontend el 1 de junio de 2026 y el backend quedó igual.
    No se sacaron: crear y borrar un banco sólo se puede hacer por acá, y de
    esos bancos dependen Retiros y Recargas en bolívares. Mientras sigan
    vivas, que digan qué devuelven: la mayoría leía documentos enteros de la
    base.

LO QUE QUEDA AFUERA

    Quién hizo cada cosa por su identificador interno (`created_by`,
    `updated_by`) en los documentos que se listan. El registro del motor
    (`/v2/audit-log`) sí dice quién, en `actor`: para eso existe.

    Los campos que son objetos armados por el motor (las tasas del momento,
    los lotes consumidos, las comisiones por moneda) quedan libres: los arma
    el motor, no se escriben a mano, y cambian con él.

Un test (`tests/test_contratos_de_contabilidad.py`) corre cada ruta con
datos y compara con lo que devolvía.
"""
from typing import Any, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── Los bancos y su libro ─────────────────────────────────────────────────

MensajeDeContabilidad = _simple("MensajeDeContabilidad", ("message",))
BancoCreado = _simple("BancoCreado", ("message", "bank_id"))
MovimientoManual = _simple("MovimientoManual", ("message", "new_balance"))

BancoDelLibro = _simple("BancoDelLibro", ("bank_id", "name", "currency", "balance", "created_at"))

# Lo escriben cinco lugares (routes/accounting.py, gestor_pix.py, admin.py,
# payments_card.py): la unión de sus campos, sin quién lo cargó.
LineaDelBanco = _simple("LineaDelBanco", (
    "bank_id", "bank_name", "date", "type", "concept", "amount", "balance_after", "reference", "notes",
    "source", "ledger_id", "created_at"))


class LibroDeUnBanco(BaseModel):
    bank: Optional[BancoDelLibro] = None
    entries: List[LineaDelBanco] = []
    total: Escalar = None
    page: Escalar = None
    pages: Escalar = None


SaldoDeUnBanco = _simple("SaldoDeUnBanco", ("bank_id", "name", "balance"))


class AlcanzaElSaldo(BaseModel):
    currency: Escalar = None
    total_balance: Escalar = None
    required: Escalar = None
    sufficient: Escalar = None
    banks: List[SaldoDeUnBanco] = []


# ── Las tasas y las operaciones con USDT ──────────────────────────────────

TasaDeUsdt = _simple("TasaDeUsdt", ("date", "route", "buy_rate", "sell_rate", "updated_at"))
TasasDeUsdt = List[TasaDeUsdt]

OperacionRegistrada = _simple("OperacionRegistrada", ("message", "operation_id", "total_fiat"))

OperacionConUsdt = _simple("OperacionConUsdt", (
    "operation_id", "date", "route", "operation_type", "amount_usdt", "rate", "total_fiat", "bank_id",
    "bank_name", "notes", "created_at"))
OperacionesConUsdt = List[OperacionConUsdt]

LineaDelLibroDeUsdt = _simple("LineaDelLibroDeUsdt", (
    "route", "date", "type", "concept", "amount_usdt", "rate", "total_fiat", "avg_cost", "balance_after",
    "bank_name", "reference", "notes", "created_at"))


class LibroDeUsdt(BaseModel):
    balance: Escalar = None
    entries: List[LineaDelLibroDeUsdt] = []
    total: Escalar = None
    page: Escalar = None
    pages: Escalar = None


FilaDelReporte = _simple("FilaDelReporte", (
    "fecha", "id_usuario", "cliente", "ruta_remesa", "valor_transaccion", "moneda", "tasa_dia",
    "cantidad_entregar", "tasa_compra", "usdt_comprados", "pais_destino", "usdt_vendidos", "tasa_venta",
    "total_entregado", "ganancia_usdt"))


class ReporteDeContabilidad(BaseModel):
    route: Escalar = None
    period: Escalar = None
    start_date: Escalar = None
    end_date: Escalar = None
    rows: List[FilaDelReporte] = []
    total_transactions: Escalar = None
    total_ganancia_usdt: Escalar = None


# ── El motor contable nuevo (v2) ──────────────────────────────────────────

LoteDeUsdt = _simple("LoteDeUsdt", (
    "lot_id", "purchase_id", "initial_usdt", "remaining_usdt", "cost_per_usdt_brl", "is_exhausted",
    "hidden_from_admin", "created_at"))


class LotesDeUsdt(BaseModel):
    lots: List[LoteDeUsdt] = []
    count: Escalar = None


InventarioDeUsdt = _simple("InventarioDeUsdt", (
    "total_usdt_remaining", "total_cost_brl_locked", "weighted_avg_cost_brl_per_usdt", "lots_count"))

VentaP2P = _simple("VentaP2P", (
    "sale_id", "usdt_amount", "ves_received", "rate_sell_ves_usdt", "fifo_cost_brl",
    "total_cost_usd_equivalent", "net_profit_usdt", "profit_percentage", "bank_account_id",
    "hidden_from_admin", "created_at"),
    lots_consumed=(Optional[Any], None),
    rates_snapshot=(Optional[Any], None))


class VentasP2P(BaseModel):
    sales: List[VentaP2P] = []
    count: Escalar = None


RangoDelInforme = create_model("RangoDelInforme", **{"from": (Escalar, None), "to": (Escalar, None)})
PasivosDelInforme = _simple("PasivosDelInforme", (
    "circulation_ris", "escrow_withdrawing_ves", "total_adjusted_liability_ves"))
LiquidezDelInforme = _simple("LiquidezDelInforme", ("available_ves", "available_brl"))
ArbitrajeDelInforme = _simple("ArbitrajeDelInforme", (
    "volume_usdt_sold", "gross_profit_usdt_p2p", "gateway_fees_usdt_equivalent", "real_net_profit_usdt",
    "simple_average_roi", "weighted_net_real_roi"))
PasarelasDelInforme = _simple("PasarelasDelInforme", (
    "total_volume_processed_brl", "total_fees_paid_brl", "real_fiat_efficiency_percentage"),
    total_fees_paid_by_currency=(Optional[Any], None))
BancosDelInforme = _simple("BancosDelInforme", ("total_withdrawal_outbound_fees_ves", "audit_note"))


class InformeEjecutivo(BaseModel):
    reporting_timezone: Escalar = None
    filter_range: Optional[RangoDelInforme] = None
    rates_snapshot: Optional[Any] = None
    advertencias: Optional[Any] = None
    liabilities: Optional[PasivosDelInforme] = None
    corporate_liquidity: Optional[LiquidezDelInforme] = None
    arbitrage_performance: Optional[ArbitrajeDelInforme] = None
    gateway_operational_expenses: Optional[PasarelasDelInforme] = None
    local_bank_expenses: Optional[BancosDelInforme] = None


LineaDelMotor = _simple("LineaDelMotor", ("action", "severity", "reference_id", "actor", "created_at"),
                        previous_state=(Optional[Any], None),
                        current_state=(Optional[Any], None))


class RegistroDelMotor(BaseModel):
    entries: List[LineaDelMotor] = []
    count: Escalar = None


Conciliacion = _simple("Conciliacion", ("status", "message", "tx_id", "gross", "fee", "net_to_bank"))
