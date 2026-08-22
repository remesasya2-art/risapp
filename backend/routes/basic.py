"""
Basic routes - Health check, rates, etc.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
import os

from database import db
from models.user import User
from routes.dependencies import get_current_user
from services.rate_engine import apply_rate_adjustment, load_auto_rate_config, caracas_now
from services.rate_history import log_if_changed, determine_auto_change_type

logger = logging.getLogger(__name__)
router = APIRouter(tags=["basic"])

@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "RIS App API", "version": "2.0.0"}

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@router.get("/rate")
async def get_current_rate():
    """Get current exchange rates - applies auto off-hours adjustment if enabled."""
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    base = {
        "ris_to_ves": (rate or {}).get("ris_to_ves", 110.0),
        "ves_to_ris_rate": (rate or {}).get("ves_to_ris_rate", 140.0),
        "brl_to_ris": (rate or {}).get("brl_to_ris", 1.0),
        "usd_to_ves": (rate or {}).get("usd_to_ves", 50.0),
    }
    config = await load_auto_rate_config(db)
    effective = apply_rate_adjustment(base, config)
    if rate:
        effective["updated_at"] = rate.get("updated_at")
    # Expose base values so admin UI can show both
    effective["base_ris_to_ves"] = base["ris_to_ves"]
    effective["base_ves_to_ris_rate"] = base["ves_to_ris_rate"]

    # Tasas de envío con saldo cripto (USDT/USDC → VES). No llevan ajuste
    # automático por horario (son un valor fijo que configura el admin aparte).
    effective["usdtris_to_ves"] = (rate or {}).get("usdtris_to_ves")
    effective["usdcris_to_ves"] = (rate or {}).get("usdcris_to_ves")

    # Expose BCV USD/EUR rates publicly (read-only)
    bcv = await db.bcv_rates.find_one({}, {"_id": 0, "rates": 1, "value_date": 1, "fetched_at": 1}, sort=[("fetched_at", -1)])
    if bcv and bcv.get("rates"):
        effective["bcv_usd_ves"] = bcv["rates"].get("dolar")
        effective["bcv_eur_ves"] = bcv["rates"].get("euro")
        effective["bcv_value_date"] = bcv.get("value_date")

    # Log rate transitions (only if changed from last entry)
    try:
        now = caracas_now()
        if config.get("enabled"):
            change_type = determine_auto_change_type(config, now)
        else:
            change_type = "manual"
        await log_if_changed(db, "brl_ves", effective.get("ris_to_ves"), change_type)
        await log_if_changed(db, "ves_brl", effective.get("ves_to_ris_rate"), change_type)
    except Exception as e:
        logger.warning(f"Rate history log failed: {e}")

    return effective

@router.get("/download-build")
async def download_build():
    """Download the latest build"""
    build_path = "/app/backend/dist.zip"
    if os.path.exists(build_path):
        return FileResponse(
            build_path,
            media_type="application/zip",
            filename="ris-app-build.zip"
        )
    return {"error": "Build not available"}

@router.get("/withdrawal/queue-stats")
async def get_withdrawal_queue_stats():
    """Get withdrawal queue statistics"""
    # Count pending withdrawals
    total_pending = await db.transactions.count_documents({
        "type": "withdrawal",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    })
    
    # Calculate total VES pending
    pending_cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    })
    
    total_ves = 0
    async for tx in pending_cursor:
        total_ves += tx.get("amount_output", 0)
    
    return {
        "total_pending": total_pending,
        # Sin cola de WhatsApp, todo lo pendiente esta esperando a un operador:
        # waiting_in_queue ya no descuenta nada y coincide con total_pending.
        "waiting_in_queue": total_pending,
        "total_ves_pending": round(total_ves, 2)
    }
