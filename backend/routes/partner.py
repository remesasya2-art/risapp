"""
Partner (Socio) routes - Referral system
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.user import User
from routes.dependencies import get_current_user
from config import FRONTEND_URL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/partner", tags=["partner"])

async def require_partner(current_user: User = Depends(get_current_user)) -> User:
    """Require socio or socio_gestor role"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") not in ["socio", "socio_gestor"]:
        raise HTTPException(status_code=403, detail="Acceso solo para socios")
    return current_user

@router.get("/dashboard")
async def get_partner_dashboard(current_user: User = Depends(require_partner)):
    """Get partner dashboard with earnings and referrals"""
    partner_id = current_user.user_id
    user = await db.users.find_one({"user_id": partner_id})
    
    # Get referrals
    referrals = await db.users.find({"referred_by": user.get("referral_code")}).to_list(500)
    
    # Get earnings
    earnings = await db.partner_earnings.find({"partner_id": partner_id}).to_list(1000)
    total_earnings = sum(e.get("amount", 0) for e in earnings)
    
    # This month's earnings
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_earnings = []
    for e in earnings:
        created = e.get("created_at")
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= month_start:
                month_earnings.append(e)
    month_total = sum(e.get("amount", 0) for e in month_earnings)
    
    # Get settings
    settings = await db.app_settings.find_one({"setting_id": "partner_settings"})
    commission_rate = settings.get("commission_rate", 2.0) if settings else 2.0
    milestone_bonus = settings.get("milestone_bonus", 5.0) if settings else 5.0
    
    # Referrals list with stats
    referrals_list = []
    for r in referrals:
        # Count completed transactions for this referral
        tx_count = await db.transactions.count_documents({
            "user_id": r["user_id"],
            "status": "completed"
        })
        
        referrals_list.append({
            "user_id": r["user_id"],
            "name": r.get("name", ""),
            "email": r.get("email", ""),
            "created_at": r.get("created_at"),
            "transactions_count": tx_count
        })
    
    return {
        "referral_code": user.get("referral_code", ""),
        "referral_link": f"{FRONTEND_URL}/register?ref={user.get('referral_code', '')}",
        "stats": {
            "total_referrals": len(referrals),
            "total_earnings": round(total_earnings, 2),
            "month_earnings": round(month_total, 2),
            "commission_rate": commission_rate,
            "milestone_bonus": milestone_bonus
        },
        "referrals": referrals_list,
        "recent_earnings": [
            {
                "earning_id": e.get("earning_id"),
                "type": e.get("type"),
                "amount": e.get("amount"),
                "referred_user_id": e.get("referred_user_id"),
                "created_at": e.get("created_at")
            }
            for e in sorted(earnings, key=lambda x: x.get("created_at", datetime.min), reverse=True)[:20]
        ]
    }

@router.get("/referral-link")
async def get_referral_link(current_user: User = Depends(require_partner)):
    """Get partner referral link"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    referral_code = user.get("referral_code", "")
    
    return {
        "referral_code": referral_code,
        "referral_link": f"{FRONTEND_URL}/register?ref={referral_code}"
    }
