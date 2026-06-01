"""
Rate history logger: records every transition of the effective exchange rate.
- Manual changes (admin sets new base) → change_type='manual'
- Auto off-hours transitions → change_type='auto_off_hours' / 'auto_in_hours'
- Holidays → change_type='auto_holiday'
"""
from datetime import datetime, timezone, timedelta, date as date_cls

CARACAS_TZ = timezone(timedelta(hours=-4))


async def get_last_entry(db, route: str) -> dict | None:
    return await db.rate_history.find_one(
        {"route": route}, {"_id": 0}, sort=[("timestamp", -1)]
    )


async def log_if_changed(db, route: str, new_rate: float, change_type: str, admin_email: str = None, reason: str = None):
    """Insert a rate history entry only if the rate is different from the last logged one."""
    if new_rate is None:
        return
    new_rate = round(float(new_rate), 4)

    last = await get_last_entry(db, route)
    if last and abs(float(last.get("new_rate", 0)) - new_rate) < 0.0001 and last.get("change_type") == change_type:
        # Same rate & same reason → no need to log again
        return

    entry = {
        "route": route,
        "old_rate": float(last["new_rate"]) if last else None,
        "new_rate": new_rate,
        "change_type": change_type,
        "admin_email": admin_email,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc),
    }
    await db.rate_history.insert_one(entry)


def determine_auto_change_type(config: dict, now: datetime) -> str:
    """Classify why the automatic rate is currently what it is."""
    from services.rate_engine import is_ve_holiday
    if is_ve_holiday(now.date()):
        return "auto_holiday"
    if now.weekday() not in config.get("work_days", [0,1,2,3,4,5]):
        return "auto_weekend"
    hour = now.hour
    if hour < config.get("work_start_hour", 8) or hour >= config.get("work_end_hour", 22):
        return "auto_off_hours"
    return "auto_in_hours"
