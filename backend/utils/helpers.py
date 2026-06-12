"""
Helper utilities
"""
import logging

logger = logging.getLogger(__name__)

async def get_next_withdrawal_id() -> str:
        """Get the next sequential withdrawal display ID using atomic MongoDB counter.
            Uses find_one_and_update with $inc to prevent race conditions under concurrent load.
                """
        from database import db

    result = await db.counters.find_one_and_update(
                {"_id": "withdrawal_display_id"},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=True
    )

    next_num = result["seq"]
    return f"{next_num:06d}"  # Format as 6-digit string with leading zeros
