"""
Accounting v2 — endpoints for the new Enterprise Accounting Engine.
Production-ready FIFO + P2P + executive reports + audit log.

These endpoints live under /api/admin/accounting/v2 and do NOT replace
existing /api/admin/accounting/* routes; they coexist while the frontend
migrates to the new model.
"""
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.dependencies import get_super_admin
from models.user import User
from database import db
from services.accounting_engine import (
    CoreAccountingEngine,
    ExecutiveReportService,
    WebhookConciliationService,
    ensure_indexes,
    CARACAS_TZ,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/accounting/v2", tags=["AccountingV2"])


# ---------- Pydantic schemas ----------
class UsdtLotInput(BaseModel):
    initial_usdt: float = Field(..., gt=0)
    cost_per_usdt_brl: float = Field(..., gt=0)
    purchase_id: Optional[str] = None


class P2PSaleInput(BaseModel):
    amount_usdt_to_sell: float = Field(..., gt=0)
    amount_ves_received: float = Field(..., gt=0)
    bank_account_id: str


class WebhookConciliateInput(BaseModel):
    webhook_event_id: str
    provider: str
    transaction_id: str
    amount_received: float = Field(..., gt=0)
    currency: str = Field(..., pattern="^(BRL|VES|USDT)$")


# ---------- Bootstrap ----------
@router.post("/bootstrap-indexes")
async def bootstrap_indexes(admin: User = Depends(get_super_admin)):
    """Create or re-ensure all engine indexes. Safe to call multiple times."""
    await ensure_indexes()
    return {"message": "Índices del motor contable v2 verificados"}


# ---------- USDT Lots (FIFO inventory) ----------
@router.post("/usdt-lots")
async def add_usdt_lot(data: UsdtLotInput, admin: User = Depends(get_super_admin)):
    try:
        lot = await CoreAccountingEngine.register_usdt_lot(
            initial_usdt=data.initial_usdt,
            cost_per_usdt_brl=data.cost_per_usdt_brl,
            purchase_id=data.purchase_id,
            actor=admin.user_id,
        )
        if "created_at" in lot and isinstance(lot["created_at"], datetime):
            lot["created_at"] = lot["created_at"].isoformat()
        return lot
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/usdt-lots")
async def list_usdt_lots(
    only_active: bool = False, admin: User = Depends(get_super_admin)
):
    query = {"hidden_from_admin": {"$ne": True}}
    if only_active:
        query["is_exhausted"] = False
    cursor = db.usdt_lots.find(query, {"_id": 0}).sort("created_at", 1)
    lots = await cursor.to_list(500)
    for lot in lots:
        if isinstance(lot.get("created_at"), datetime):
            lot["created_at"] = lot["created_at"].isoformat()
    return {"lots": lots, "count": len(lots)}


@router.get("/usdt-inventory-summary")
async def usdt_inventory_summary(admin: User = Depends(get_super_admin)):
    """Aggregate active inventory: total USDT remaining + weighted avg cost."""
    pipeline = [
        {"$match": {"is_exhausted": False, "hidden_from_admin": {"$ne": True}}},
        {
            "$group": {
                "_id": None,
                "total_usdt_remaining": {"$sum": "$remaining_usdt"},
                "total_cost_brl_locked": {
                    "$sum": {"$multiply": ["$remaining_usdt", "$cost_per_usdt_brl"]}
                },
                "lots_count": {"$sum": 1},
            }
        },
    ]
    res = await db.usdt_lots.aggregate(pipeline).to_list(1)
    if not res:
        return {
            "total_usdt_remaining": 0,
            "total_cost_brl_locked": 0,
            "weighted_avg_cost_brl_per_usdt": 0,
            "lots_count": 0,
        }
    r = res[0]
    total_usdt = r["total_usdt_remaining"] or 0
    total_brl = r["total_cost_brl_locked"] or 0
    return {
        "total_usdt_remaining": round(total_usdt, 2),
        "total_cost_brl_locked": round(total_brl, 2),
        "weighted_avg_cost_brl_per_usdt": round(total_brl / total_usdt, 4)
        if total_usdt > 0
        else 0,
        "lots_count": r["lots_count"],
    }


# ---------- P2P Sales ----------
@router.post("/p2p-sales")
async def execute_p2p_sale(
    data: P2PSaleInput, admin: User = Depends(get_super_admin)
):
    try:
        sale = await CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=data.amount_usdt_to_sell,
            amount_ves_received=data.amount_ves_received,
            bank_account_id=data.bank_account_id,
            admin_id=admin.user_id,
        )
        return sale
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/p2p-sales")
async def list_p2p_sales(
    limit: int = Query(50, ge=1, le=500),
    admin: User = Depends(get_super_admin),
):
    cursor = db.p2p_sales.find(
        {"hidden_from_admin": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    sales = await cursor.to_list(limit)
    for s in sales:
        if isinstance(s.get("created_at"), datetime):
            s["created_at"] = s["created_at"].isoformat()
    return {"sales": sales, "count": len(sales)}


# ---------- Executive Report ----------
def _default_range_caracas(days: int = 1):
    now_car = datetime.now(CARACAS_TZ)
    start = (now_car - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    end = now_car.strftime("%Y-%m-%d")
    return start, end


@router.get("/executive-report")
async def executive_report(
    start: Optional[str] = None,
    end: Optional[str] = None,
    range_days: int = Query(1, ge=1, le=365),
    admin: User = Depends(get_super_admin),
):
    """Generate the consolidated executive report. Defaults to today (Caracas)."""
    if not start or not end:
        start, end = _default_range_caracas(range_days)
    try:
        return await ExecutiveReportService.generate_report(start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- Audit Log ----------
@router.get("/audit-log")
async def get_audit_log(
    severity: Optional[str] = Query(None, pattern="^(INFO|WARNING|CRITICAL)$"),
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(get_super_admin),
):
    query = {}
    if severity:
        query["severity"] = severity
    if action:
        query["action"] = action
    cursor = (
        db.accounting_audit_log.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    entries = await cursor.to_list(limit)
    for e in entries:
        if isinstance(e.get("created_at"), datetime):
            e["created_at"] = e["created_at"].isoformat()
    return {"entries": entries, "count": len(entries)}


# ---------- Webhook (manual conciliation trigger) ----------
@router.post("/webhook-conciliate")
async def webhook_conciliate(
    data: WebhookConciliateInput, admin: User = Depends(get_super_admin)
):
    """Manual trigger for webhook reconciliation. Used by integration tests
    and admin-driven recovery. Production webhooks call the same engine
    directly from /api/webhooks/* handlers."""
    try:
        return await WebhookConciliationService.process_incoming_payment(
            webhook_event_id=data.webhook_event_id,
            provider=data.provider,
            transaction_id=data.transaction_id,
            amount_received=data.amount_received,
            currency=data.currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
