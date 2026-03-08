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
    """Get current exchange rate"""
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    if not rate:
        return {"ris_to_ves": 92.0, "ves_to_ris": 0.0109}
    
    return {
        "ris_to_ves": rate.get("ris_to_ves", 92.0),
        "ves_to_ris": rate.get("ves_to_ris", 0.0109),
        "updated_at": rate.get("updated_at")
    }

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
        "status": "pending"
    })
    
    # Count active in WhatsApp
    active_in_whatsapp = await db.transactions.count_documents({
        "type": "withdrawal",
        "status": "pending",
        "whatsapp_active": True
    })
    
    # Calculate total VES pending
    pending_cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending"
    })
    
    total_ves = 0
    async for tx in pending_cursor:
        total_ves += tx.get("amount_output", 0)
    
    return {
        "total_pending": total_pending,
        "active_in_whatsapp": active_in_whatsapp,
        "waiting_in_queue": total_pending - active_in_whatsapp,
        "total_ves_pending": round(total_ves, 2)
    }
