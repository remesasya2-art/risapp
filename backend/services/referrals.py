"""
Referral and partner bonus service
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

async def process_referral_bonus(user_id: str, recharge_amount: float):
    """Process referral bonus when a user makes a recharge"""
    from database import db
    from services.notifications import create_notification
    
    # Get the user
    user = await db.users.find_one({"user_id": user_id})
    if not user or not user.get("referred_by"):
        return
    
    # Get the partner who referred this user
    partner = await db.users.find_one({"referral_code": user.get("referred_by")})
    if not partner or partner.get("role") not in ["socio", "socio_gestor"]:
        return
    
    # Check if this is the user's first recharge (milestone bonus)
    first_recharge = await db.transactions.count_documents({
        "user_id": user_id,
        "type": "recharge_ves",
        "status": "completed"
    }) == 1
    
    # Get partner settings
    settings = await db.app_settings.find_one({"setting_id": "partner_settings"})
    commission_rate = settings.get("commission_rate", 2.0) / 100 if settings else 0.02
    milestone_bonus = settings.get("milestone_bonus", 5.0) if settings else 5.0
    
    total_bonus = 0
    
    # First-time referral bonus
    if first_recharge:
        total_bonus += milestone_bonus
        logger.info(f"First recharge milestone bonus {milestone_bonus} RIS for partner {partner['user_id']}")
    
    # Commission on recharge
    commission = recharge_amount * commission_rate
    total_bonus += commission
    
    if total_bonus > 0:
        # Add bonus to partner balance
        _partner_after_doc = await db.users.find_one_and_update(
            {"user_id": partner["user_id"]},
            {"$inc": {"balance_ris": total_bonus}},
            return_document=True
        )
        # Libro mayor RIS (no interrumpe el abono del bono)
        try:
            from services.ledger import record_ris_entry
            _pb_after = (_partner_after_doc or {}).get("balance_ris")
            await record_ris_entry(
                user_id=partner["user_id"],
                movement_type="bono_referido",
                amount=total_bonus,
                direction="credit",
                account="balance_ris",
                balance_before=(_pb_after - total_bonus) if _pb_after is not None else None,
                balance_after=_pb_after,
                reference_kind="referral",
                reference_id=user_id,
                actor_type="system",
                actor_id="referrals",
                metadata={"referred_user_id": user_id, "first_recharge": first_recharge, "recharge_amount": recharge_amount},
                notes="Bono/comisión de referido",
            )
        except Exception as e:
            logger.warning(f"Ledger bono_referido no registrado: {e}")
        
        # Record earning
        earning = {
            "earning_id": f"earn_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "partner_id": partner["user_id"],
            "referred_user_id": user_id,
            "type": "milestone" if first_recharge else "commission",
            "amount": total_bonus,
            "recharge_amount": recharge_amount,
            "commission_rate": commission_rate * 100,
            "created_at": datetime.now(timezone.utc)
        }
        await db.partner_earnings.insert_one(earning)
        
        # Notify partner
        await create_notification(
            user_id=partner["user_id"],
            title="💰 Comisión Recibida",
            message=f"Has recibido {total_bonus:.2f} RIS de comisión por tu referido.",
            notification_type="partner_bonus",
            data={"amount": total_bonus, "referred_user_id": user_id}
        )
        
        logger.info(f"Partner {partner['user_id']} received {total_bonus:.2f} RIS bonus")
