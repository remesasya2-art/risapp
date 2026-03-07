"""
Helper utilities
"""
import logging

logger = logging.getLogger(__name__)

async def get_next_withdrawal_id() -> str:
    """Get the next sequential withdrawal display ID"""
    from database import db
    
    # Find the highest display_id
    last_tx = await db.transactions.find_one(
        {"display_id": {"$exists": True, "$ne": None}},
        sort=[("display_id", -1)]
    )
    
    if last_tx and last_tx.get("display_id"):
        try:
            # Extract number from display_id (format: "000001")
            last_num = int(last_tx["display_id"].lstrip("0") or "0")
            next_num = last_num + 1
        except (ValueError, AttributeError):
            next_num = 1
    else:
        next_num = 1
    
    return f"{next_num:06d}"  # Format as 6-digit string with leading zeros
