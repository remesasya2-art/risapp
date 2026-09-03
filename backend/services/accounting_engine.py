"""
Enterprise Accounting Engine — v11 (production-ready)
======================================================
Port of the Mongoose engine to Python async (Motor + Pydantic).

Coverage:
- FIFO multi-lot USDT inventory (collection: usdt_lots)
- P2P arbitrage sales (collection: p2p_sales) with dimensional analysis
  (USDT pivot: BRL→USD via market_brl_usd, VES→USD via bcv_ves_usd)
- ACID transactions on all multi-document mutations (auto-fallback to
  non-transactional mode on standalone MongoDB for dev environments)
- Webhook idempotency via TTL'd processed_webhooks
- Multi-currency gateway fee tracking (gateway_fee_ledger)
- Atomic bank debit (TOCTOU mitigation)
- AuditLog with severity + previous/current state
- Caracas timezone (UTC-4) on all reports

Collections (new, do NOT break existing ones):
- usdt_lots
- p2p_sales
- processed_webhooks (TTL 180d)
- gateway_fee_ledger
- accounting_audit_log (extended; existing audit_log stays untouched)

Existing collections (touched only via $inc atomic ops):
- bank_accounts, bank_ledger, transactions, users, rates, bcv_rates
"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from pymongo.errors import DuplicateKeyError, OperationFailure

from database import db, client as mongo_client
from services.money import ZERO, from_db, quantize_money, to_float
from services import bancos

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================
CARACAS_TZ = timezone(timedelta(hours=-4))
DEFAULT_GATEWAY_FEE_PERCENTAGE = 0.01  # 1% — TODO: move to GatewayConfig
WEBHOOK_TTL_DAYS = 180

# Cached at startup: True if replica set, False if standalone
_SUPPORTS_TRANSACTIONS: Optional[bool] = None


async def _detect_transaction_support() -> bool:
    """Check once whether the cluster supports multi-document transactions."""
    global _SUPPORTS_TRANSACTIONS
    if _SUPPORTS_TRANSACTIONS is not None:
        return _SUPPORTS_TRANSACTIONS
    try:
        info = await mongo_client.admin.command("hello")
        # Replica sets expose "setName" — standalones don't
        _SUPPORTS_TRANSACTIONS = "setName" in info
    except Exception:
        _SUPPORTS_TRANSACTIONS = False
    if not _SUPPORTS_TRANSACTIONS:
        logger.warning(
            "Accounting engine: standalone MongoDB detected — "
            "running WITHOUT multi-document transactions (dev mode)"
        )
    return _SUPPORTS_TRANSACTIONS


@asynccontextmanager
async def _atomic_session():
    """Yield a Motor session inside a transaction, or None if standalone."""
    if await _detect_transaction_support():
        async with await mongo_client.start_session() as session:
            async with session.start_transaction():
                yield session
    else:
        yield None


# ============================================================
# Indexes (idempotent — safe to call multiple times)
# ============================================================
async def ensure_indexes() -> None:
    """Create required indexes for the new collections. Idempotent."""
    # usdt_lots: sparse unique purchase_id, list-by-creation
    await db.usdt_lots.create_index(
        "purchase_id", unique=True, sparse=True, name="ux_purchase_id"
    )
    await db.usdt_lots.create_index(
        [("is_exhausted", 1), ("hidden_from_admin", 1), ("created_at", 1)],
        name="ix_active_fifo",
    )

    # p2p_sales: by date and visibility
    await db.p2p_sales.create_index(
        [("created_at", 1), ("hidden_from_admin", 1)], name="ix_sales_date"
    )

    # processed_webhooks: unique event_id + TTL 180d
    await db.processed_webhooks.create_index(
        "webhook_event_id", unique=True, name="ux_webhook_event"
    )
    await db.processed_webhooks.create_index(
        "processed_at",
        expireAfterSeconds=60 * 60 * 24 * WEBHOOK_TTL_DAYS,
        name="ttl_processed_at",
    )

    # gateway_fee_ledger: by date and visibility
    await db.gateway_fee_ledger.create_index(
        [("created_at", 1), ("hidden_from_admin", 1)],
        name="ix_fee_date",
    )

    # accounting_audit_log: by reference + severity for fast lookups
    await db.accounting_audit_log.create_index(
        [("reference_id", 1), ("created_at", -1)], name="ix_audit_ref"
    )
    await db.accounting_audit_log.create_index(
        [("severity", 1), ("created_at", -1)], name="ix_audit_severity"
    )

    logger.info("Accounting engine indexes ensured")


# ============================================================
# Helpers
# ============================================================
def _round2(value: float) -> float:
    """Stable 2-decimal rounding (single rounding, no double)."""
    return round(float(value) * 100) / 100


async def _audit(
    session,
    *,
    action: str,
    reference_id: str,
    actor: str,
    previous_state: Optional[Dict[str, Any]] = None,
    current_state: Optional[Dict[str, Any]] = None,
    severity: str = "INFO",
) -> None:
    """Insert an immutable audit record inside the given session."""
    await db.accounting_audit_log.insert_one(
        {
            "_id": uuid.uuid4().hex,
            "action": action,
            "severity": severity,
            "reference_id": str(reference_id),
            "actor": str(actor),
            "previous_state": previous_state,
            "current_state": current_state,
            "created_at": datetime.now(timezone.utc),
        },
        session=session,
    )


async def _get_active_rates(session=None) -> Dict[str, Any]:
    """Read the active rates singleton.

    Maps existing /rates fields to the engine schema:
      ris_to_ves_withdrawal  ← rates.ris_to_ves            (default 110)
      ves_to_ris_recharge    ← rates.ves_to_ris_rate       (default 140)
      bcv_ves_usd            ← latest bcv_rates.rates.dolar (default 50)
      market_brl_usd         ← rates.brl_to_usd            (default 5.0)
    """
    rates = await db.rates.find_one({}, session=session)
    if not rates:
        raise RuntimeError("Sistema sin tasas configuradas")

    # Try to fetch latest BCV from bcv_rates (scraper). Fallback to rates.usd_to_ves.
    bcv_doc = await db.bcv_rates.find_one(
        {}, sort=[("fetched_at", -1)], session=session
    )
    bcv_ves_usd = (
        bcv_doc.get("rates", {}).get("dolar")
        if bcv_doc
        else rates.get("usd_to_ves", 50.0)
    ) or 50.0

    return {
        "ris_to_ves_withdrawal": float(rates.get("ris_to_ves", 110)),
        "ves_to_ris_recharge": float(rates.get("ves_to_ris_rate", 140)),
        "bcv_ves_usd": float(bcv_ves_usd),
        "market_brl_usd": float(rates.get("brl_to_usd", 5.0)),
    }


# ============================================================
# Webhook Conciliation Service
# ============================================================
class WebhookConciliationService:
    """Idempotent reconciliation of incoming gateway webhooks.

    Confirms gross amount matches, applies gateway fee (1%), credits net
    to bank, registers in gateway_fee_ledger, and emits audit log.
    Duplicate webhook_event_id returns IGNORED_DUPLICATE without error.
    """

    @staticmethod
    async def process_incoming_payment(
        webhook_event_id: str,
        provider: str,
        transaction_id: str,
        amount_received: float,
        currency: str,
    ) -> Dict[str, Any]:
        try:
            async with _atomic_session() as session:
                # 1. Idempotency: insert webhook event id (unique)
                try:
                    await db.processed_webhooks.insert_one(
                        {
                            "_id": uuid.uuid4().hex,
                            "webhook_event_id": webhook_event_id,
                            "provider": provider,
                            "processed_at": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
                except DuplicateKeyError:
                    return {
                        "status": "IGNORED_DUPLICATE",
                        "message": "Webhook ya procesado.",
                    }

                # 2. Locate transaction
                tx = await db.transactions.find_one(
                    {"transaction_id": transaction_id}, session=session
                )
                if not tx:
                    raise ValueError(
                        f"Transacción {transaction_id} no encontrada"
                    )

                if tx.get("status") == "approved":
                    return {
                        "status": "ALREADY_PROCESSED",
                        "tx_id": transaction_id,
                    }

                # 3. Validate gross amount with 1¢ tolerance
                expected = (
                    tx.get("amount_brl", 0)
                    if currency == "BRL"
                    else tx.get("amount_ves", 0)
                )
                if abs(expected - amount_received) > 0.01:
                    await db.transactions.update_one(
                        {"transaction_id": transaction_id},
                        {"$set": {"status": "suspended"}},
                        session=session,
                    )
                    raise ValueError(
                        f"Descuadre: esperado {expected}, recibido {amount_received}"
                    )

                # 4. Apply fee with single rounding
                fee = _round2(amount_received * DEFAULT_GATEWAY_FEE_PERCENTAGE)
                net = _round2(amount_received - fee)

                # 5. Update transaction
                await db.transactions.update_one(
                    {"transaction_id": transaction_id},
                    {
                        "$set": {
                            "status": "approved",
                            "gateway_fee_amount": fee,
                            "gateway_fee_currency": currency,
                            "net_amount_received": net,
                            "processed_at": datetime.now(timezone.utc),
                        }
                    },
                    session=session,
                )

                # 6. Credit net to bank atomically
                bank_id = tx.get("bank_account_id") or tx.get("destination_bank_id")
                if bank_id:
                    # En Decimal, como el resto de las escrituras a este
                    # campo: un `$inc` con float arrastra su imprecisión al
                    # total del pozo, que es justo lo que la conciliación mira.
                    await bancos.ajustar(db, bank_id, net, session=session)

                # 7. Register in gateway fee ledger (multi-currency)
                await db.gateway_fee_ledger.insert_one(
                    {
                        "_id": uuid.uuid4().hex,
                        "transaction_id": transaction_id,
                        "gateway_provider": provider,
                        "gross_amount": float(amount_received),
                        "fee_deducted": fee,
                        "currency": currency,
                        "is_reconciled_with_invoice": False,
                        "invoice_reference": None,
                        "hidden_from_admin": tx.get("hidden_from_admin", False),
                        "created_at": datetime.now(timezone.utc),
                    },
                    session=session,
                )

                # 8. AuditLog
                await _audit(
                    session,
                    action="WEBHOOK_CONCILIATED",
                    severity="INFO",
                    reference_id=transaction_id,
                    actor=provider,
                    previous_state={"status": "pending"},
                    current_state={
                        "status": "approved",
                        "webhook_id": webhook_event_id,
                        "gross": float(amount_received),
                        "fee": fee,
                        "net_to_bank": net,
                    },
                )

                return {
                    "status": "SUCCESSFULLY_CONCILIATED",
                    "tx_id": transaction_id,
                    "gross": float(amount_received),
                    "fee": fee,
                    "net_to_bank": net,
                }
        except DuplicateKeyError:
            return {"status": "IGNORED_DUPLICATE"}


# ============================================================
# Core Accounting Engine
# ============================================================
class CoreAccountingEngine:
    """FIFO USDT inventory + P2P arbitrage + atomic bank ops."""

    @staticmethod
    async def register_usdt_lot(
        *,
        initial_usdt: float,
        cost_per_usdt_brl: float,
        purchase_id: Optional[str] = None,
        actor: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """Add a new USDT lot to the FIFO inventory."""
        if initial_usdt <= 0 or cost_per_usdt_brl <= 0:
            raise ValueError("Cantidades inválidas")

        async with _atomic_session() as session:
            lot_id = uuid.uuid4().hex
            doc = {
                "_id": lot_id,
                "purchase_id": purchase_id,
                "initial_usdt": float(initial_usdt),
                "remaining_usdt": float(initial_usdt),
                "cost_per_usdt_brl": float(cost_per_usdt_brl),
                "is_exhausted": False,
                "hidden_from_admin": False,
                "created_at": datetime.now(timezone.utc),
            }
            try:
                await db.usdt_lots.insert_one(doc, session=session)
            except DuplicateKeyError:
                raise ValueError(
                    f"purchase_id ya registrado: {purchase_id}"
                )

            await _audit(
                session,
                action="USDT_LOT_REGISTERED",
                reference_id=lot_id,
                actor=actor,
                previous_state=None,
                current_state={
                    "initial_usdt": float(initial_usdt),
                    "cost_per_usdt_brl": float(cost_per_usdt_brl),
                    "purchase_id": purchase_id,
                },
            )
            doc["lot_id"] = lot_id
            doc.pop("_id", None)
            return doc

    @staticmethod
    async def atomic_debit_from_bank(
        bank_id: str, amount_required: float, session
    ) -> Dict[str, Any]:
        """TOCTOU-safe bank debit. Filters by balance>=amount before $inc."""
        # El guard sigue yendo DENTRO del filtro de la escritura, que es lo que
        # lo hace a prueba de TOCTOU; lo que cambia es que compara y descuenta
        # en Decimal.
        try:
            movimiento = await bancos.ajustar(
                db, bank_id, -amount_required,
                session=session, exigir_saldo=True,
                filtro_extra={"hidden_from_admin": {"$ne": True}})
        except (bancos.SaldoInsuficiente, bancos.CuentaInexistente,
                bancos.CuentaNoDisponible) as e:
            raise ValueError(
                f"Operación denegada: fondos insuficientes en banco {bank_id} "
                f"o cuenta deshabilitada (requerido: {amount_required})"
            ) from e
        return movimiento["banco"]

    @staticmethod
    async def execute_p2p_arbitrage(
        *,
        amount_usdt_to_sell: float,
        amount_ves_received: float,
        bank_account_id: str,
        admin_id: str,
    ) -> Dict[str, Any]:
        """Execute a P2P arbitrage with full FIFO consumption + ACID atomicity.

        Dimensional analysis:
          totalCostInUSD     = totalCostBrl / market_brl_usd   [USD]
          totalRevenueInUSD  = vesReceived  / rateSellVesUsdt  [USD] (≈USDT)
          netProfitUsdt      = USD_revenue − USD_cost          [USDT]
          profitPercentage   = ((revenue/cost) − 1) × 100      [%]
        """
        if amount_usdt_to_sell <= 0 or amount_ves_received <= 0:
            raise ValueError("Cantidades inválidas")

        async with _atomic_session() as session:
            rates = await _get_active_rates(session=session)
            if rates["market_brl_usd"] <= 0:
                raise RuntimeError("market_brl_usd no configurado")

            # FIFO consumption
            cursor = db.usdt_lots.find(
                {"is_exhausted": False, "hidden_from_admin": False},
                sort=[("created_at", 1)],
                session=session,
            )
            lots = [lot async for lot in cursor]

            usdt_remaining = float(amount_usdt_to_sell)
            total_cost_brl = 0.0
            lots_consumed: List[Dict[str, Any]] = []

            for lot in lots:
                if usdt_remaining <= 0:
                    break

                prev_state = {
                    "remaining_usdt": lot["remaining_usdt"],
                    "is_exhausted": lot["is_exhausted"],
                }
                current_remaining = lot["remaining_usdt"]

                if current_remaining >= usdt_remaining:
                    deducted = usdt_remaining
                    new_remaining = current_remaining - usdt_remaining
                    usdt_remaining = 0
                else:
                    deducted = current_remaining
                    new_remaining = 0
                    usdt_remaining -= current_remaining

                is_exhausted = new_remaining == 0

                await db.usdt_lots.update_one(
                    {"_id": lot["_id"]},
                    {
                        "$set": {
                            "remaining_usdt": new_remaining,
                            "is_exhausted": is_exhausted,
                        }
                    },
                    session=session,
                )

                await _audit(
                    session,
                    action="FIFO_LOT_DISPATCH",
                    reference_id=lot["_id"],
                    actor=admin_id,
                    previous_state=prev_state,
                    current_state={
                        "remaining_usdt": new_remaining,
                        "is_exhausted": is_exhausted,
                        "deducted": deducted,
                    },
                )

                total_cost_brl += deducted * lot["cost_per_usdt_brl"]
                lots_consumed.append(
                    {
                        "lot_id": lot["_id"],
                        "deducted": deducted,
                        "cost_per_usdt_brl": lot["cost_per_usdt_brl"],
                    }
                )

            if usdt_remaining > 0:
                raise ValueError(
                    f"Inventario insuficiente. Faltan {usdt_remaining} USDT."
                )

            # Dimensional analysis
            rate_sell_ves_usdt = amount_ves_received / amount_usdt_to_sell
            total_cost_in_usd = total_cost_brl / rates["market_brl_usd"]
            total_revenue_in_usd = amount_ves_received / rate_sell_ves_usdt
            net_profit_usdt = total_revenue_in_usd - total_cost_in_usd
            profit_percentage = (
                ((total_revenue_in_usd / total_cost_in_usd) - 1) * 100
                if total_cost_in_usd > 0
                else 0
            )

            # Loss alert
            if net_profit_usdt < 0:
                await _audit(
                    session,
                    action="P2P_LOSS_DETECTED",
                    severity="CRITICAL",
                    reference_id=f"loss_{abs(net_profit_usdt):.4f}",
                    actor=admin_id,
                    previous_state={"cost_usd": total_cost_in_usd},
                    current_state={
                        "loss_usdt": net_profit_usdt,
                        "rate_p2p": rate_sell_ves_usdt,
                    },
                )

            # Persist sale
            sale_id = uuid.uuid4().hex
            sale_doc = {
                "_id": sale_id,
                "sale_id": sale_id,
                "usdt_amount": float(amount_usdt_to_sell),
                "ves_received": float(amount_ves_received),
                "rate_sell_ves_usdt": rate_sell_ves_usdt,
                "fifo_cost_brl": _round2(total_cost_brl),
                "total_cost_usd_equivalent": _round2(total_cost_in_usd),
                "net_profit_usdt": _round2(net_profit_usdt),
                "profit_percentage": _round2(profit_percentage),
                "bank_account_id": bank_account_id,
                "lots_consumed": lots_consumed,
                "rates_snapshot": rates,
                "hidden_from_admin": False,
                "created_by": admin_id,
                "created_at": datetime.now(timezone.utc),
            }
            await db.p2p_sales.insert_one(sale_doc, session=session)

            # Credit VES to bank atomically
            await bancos.ajustar(db, bank_account_id, amount_ves_received,
                                 session=session)

            # Final close audit
            await _audit(
                session,
                action="P2P_ARBITRAGE_COMPLETE",
                reference_id=sale_id,
                actor=admin_id,
                previous_state=None,
                current_state={
                    "sale_id": sale_id,
                    "net_profit_usdt": sale_doc["net_profit_usdt"],
                    "lots_used": len(lots_consumed),
                },
            )

            # Strip _id for response
            response = {k: v for k, v in sale_doc.items() if k != "_id"}
            response["created_at"] = response["created_at"].isoformat()
            return response


# ============================================================
# Executive Report Service
# ============================================================
class ExecutiveReportService:
    """Generate executive reports across passives, liquidity, arbitrage,
    gateway expenses and local bank expenses, with TZ Caracas."""

    @staticmethod
    async def generate_report(
        start_date_str: str, end_date_str: str
    ) -> Dict[str, Any]:
        # TZ Caracas with millisecond precision
        try:
            start_iso = datetime.fromisoformat(
                f"{start_date_str}T00:00:00.000-04:00"
            )
            end_iso = datetime.fromisoformat(
                f"{end_date_str}T23:59:59.999-04:00"
            )
        except ValueError:
            raise ValueError("Formato de fecha esperado: YYYY-MM-DD")

        rates = await _get_active_rates()
        ris_to_ves_rate = rates["ris_to_ves_withdrawal"]
        market_brl_usd = rates["market_brl_usd"] or 1
        bcv_ves_usd = rates["bcv_ves_usd"] or 1

        date_match = {"created_at": {"$gte": start_iso, "$lte": end_iso}}

        # 1. Liabilities — RIS in circulation + pending withdrawals VES
        users_agg = await db.users.aggregate(
            [{"$group": {"_id": None, "total_ris": {"$sum": "$balance_ris"}}}]
        ).to_list(1)
        total_ris_circulation = to_float(from_db(
            users_agg[0]["total_ris"] if users_agg else 0
        )) or 0

        pending_w_agg = await db.transactions.aggregate(
            [
                {
                    "$match": {
                        "type": "withdrawal",
                        "status": {"$in": ["pending", "processing"]},
                        "hidden_from_admin": {"$ne": True},
                    }
                },
                {"$group": {"_id": None, "total_ves": {"$sum": "$amount_ves"}}},
            ]
        ).to_list(1)
        total_ves_escrow = (
            pending_w_agg[0]["total_ves"] if pending_w_agg else 0
        ) or 0

        # 2. Outbound bank fees in VES (IGTF / commission)
        outbound_fees_agg = await db.transactions.aggregate(
            [
                {
                    "$match": {
                        "type": "withdrawal",
                        "status": "approved",
                        "withdrawal_fee_currency": "VES",
                        "hidden_from_admin": {"$ne": True},
                        "created_at": {"$gte": start_iso, "$lte": end_iso},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_outbound": {"$sum": "$withdrawal_fee_amount"},
                    }
                },
            ]
        ).to_list(1)
        total_withdrawal_fees_ves = (
            outbound_fees_agg[0]["total_outbound"]
            if outbound_fees_agg
            else 0
        ) or 0

        # 3. Liquidity in banks
        banks = await db.bank_accounts.find(
            {"hidden_from_admin": {"$ne": True}}, {"_id": 0}
        ).to_list(200)
        # Se suma con `bancos.saldo_de`, que lee el saldo venga como venga. El
        # `sum(b.get("balance", 0) ...)` que había acá reventaba con TypeError
        # desde que los saldos se escriben en Decimal128: `sum` arranca en el
        # entero 0, y `0 + Decimal128` no existe. El reporte entero se caía.
        total_ves_in_banks = to_float(quantize_money(sum(
            (bancos.saldo_de(b) for b in banks if b.get("currency") == "VES"),
            ZERO)))
        total_brl_in_banks = to_float(quantize_money(sum(
            (bancos.saldo_de(b) for b in banks if b.get("currency") == "BRL"),
            ZERO)))

        # 4. P2P performance
        p2p_match = {
            **date_match,
            "hidden_from_admin": {"$ne": True},
        }
        p2p_agg = await db.p2p_sales.aggregate(
            [
                {"$match": p2p_match},
                {
                    "$group": {
                        "_id": None,
                        "total_usdt_sold": {"$sum": "$usdt_amount"},
                        "total_cost_usd": {
                            "$sum": "$total_cost_usd_equivalent"
                        },
                        "total_profit_usdt": {"$sum": "$net_profit_usdt"},
                        "simple_avg_roi": {"$avg": "$profit_percentage"},
                    }
                },
            ]
        ).to_list(1)
        p2p = (
            p2p_agg[0]
            if p2p_agg
            else {
                "total_usdt_sold": 0,
                "total_cost_usd": 0,
                "total_profit_usdt": 0,
                "simple_avg_roi": 0,
            }
        )
        gross_profit_usdt = p2p["total_profit_usdt"] or 0

        # 5. Multi-currency gateway fees
        fee_groups = await db.gateway_fee_ledger.aggregate(
            [
                {
                    "$match": {
                        **date_match,
                        "hidden_from_admin": {"$ne": True},
                    }
                },
                {
                    "$group": {
                        "_id": "$currency",
                        "total_volume_gross": {"$sum": "$gross_amount"},
                        "total_fees_deducted": {"$sum": "$fee_deducted"},
                    }
                },
            ]
        ).to_list(20)

        gateway_fees_by_currency: List[Dict[str, Any]] = []
        global_gross_brl = 0.0
        global_fees_brl = 0.0
        total_fees_in_usdt_eq = 0.0

        for g in fee_groups:
            cur = g["_id"]
            gross = float(g["total_volume_gross"] or 0)
            fees = float(g["total_fees_deducted"] or 0)
            gateway_fees_by_currency.append(
                {
                    "currency": cur,
                    "gross_volume": _round2(gross),
                    "fees_paid": _round2(fees),
                }
            )
            if cur == "BRL":
                global_gross_brl += gross
                global_fees_brl += fees
                total_fees_in_usdt_eq += fees / market_brl_usd
            elif cur == "VES":
                total_fees_in_usdt_eq += fees / bcv_ves_usd

        # 6. Real net profit + corporate weighted ROI
        real_net_profit_usdt = gross_profit_usdt - total_fees_in_usdt_eq
        total_investment_usd = (
            (p2p["total_cost_usd"] or 0) + total_fees_in_usdt_eq
        )
        net_weighted_roi = (
            (real_net_profit_usdt / total_investment_usd) * 100
            if total_investment_usd > 0
            else 0
        )
        efficiency_pct = (
            ((global_gross_brl - global_fees_brl) / global_gross_brl) * 100
            if global_gross_brl > 0
            else 100
        )

        return {
            "reporting_timezone": "America/Caracas (VET / UTC-4)",
            "filter_range": {
                "from": start_iso.isoformat(),
                "to": end_iso.isoformat(),
            },
            "rates_snapshot": rates,
            "liabilities": {
                "circulation_ris": _round2(total_ris_circulation),
                "escrow_withdrawing_ves": _round2(total_ves_escrow),
                "total_adjusted_liability_ves": _round2(
                    total_ves_escrow + (total_ris_circulation * ris_to_ves_rate)
                ),
            },
            "corporate_liquidity": {
                "available_ves": _round2(total_ves_in_banks),
                "available_brl": _round2(total_brl_in_banks),
            },
            "arbitrage_performance": {
                "volume_usdt_sold": _round2(p2p["total_usdt_sold"] or 0),
                "gross_profit_usdt_p2p": _round2(gross_profit_usdt),
                "gateway_fees_usdt_equivalent": _round2(total_fees_in_usdt_eq),
                "real_net_profit_usdt": _round2(real_net_profit_usdt),
                "simple_average_roi": f"{_round2(p2p['simple_avg_roi'] or 0)}%",
                "weighted_net_real_roi": f"{_round2(net_weighted_roi)}%",
            },
            "gateway_operational_expenses": {
                "total_volume_processed_brl": _round2(global_gross_brl),
                "total_fees_paid_brl": _round2(global_fees_brl),
                "real_fiat_efficiency_percentage": f"{_round2(efficiency_pct)}%",
                "total_fees_paid_by_currency": gateway_fees_by_currency,
            },
            "local_bank_expenses": {
                "total_withdrawal_outbound_fees_ves": _round2(
                    total_withdrawal_fees_ves
                ),
                "audit_note": "Comisiones e impuestos (IGTF) retenidos por bancos al ejecutar transferencias.",
            },
        }
