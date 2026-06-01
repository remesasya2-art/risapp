"""
BCV (Banco Central de Venezuela) scraper service.
Scrapes https://www.bcv.org.ve/ for official USD/EUR/CNY/TRY/RUB rates vs VES.
Stores snapshots in `bcv_rates` collection for history.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BCV_URL = "https://www.bcv.org.ve/"
CURRENCY_IDS = ["dolar", "euro", "yuan", "lira", "rublo"]
CARACAS_TZ = timezone(timedelta(hours=-4))


def _parse_value(text: str) -> float | None:
    """BCV uses comma as decimal separator (Latin) and no thousands sep.
    Example: '481,69890000' -> 481.6989
    """
    if not text:
        return None
    clean = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


async def fetch_bcv_rates() -> dict:
    """Fetch current BCV rates. Returns dict with rates, value_date, fetched_at."""
    async with httpx.AsyncClient(verify=False, timeout=30, follow_redirects=True) as client:
        r = await client.get(BCV_URL)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    rates = {}
    for cur in CURRENCY_IDS:
        el = soup.find(id=cur)
        if not el:
            continue
        strong = el.find("strong")
        raw = (strong.text if strong else el.text).strip()
        val = _parse_value(raw)
        if val is not None:
            rates[cur] = val

    # Value date (published date from BCV)
    value_date = None
    fecha_el = soup.find(class_="pull-right dinpro center")
    if fecha_el:
        value_date = fecha_el.text.strip().replace("Fecha Valor:", "").strip()

    return {
        "rates": rates,
        "value_date": value_date,
        "fetched_at": datetime.now(timezone.utc),
    }


async def save_snapshot(db, snapshot: dict) -> bool:
    """Save a BCV snapshot. Skips if identical to last snapshot (same rates)."""
    if not snapshot.get("rates"):
        return False

    last = await db.bcv_rates.find_one(
        {}, {"_id": 0, "rates": 1, "value_date": 1}, sort=[("fetched_at", -1)]
    )
    if last and last.get("rates") == snapshot["rates"] and last.get("value_date") == snapshot.get("value_date"):
        return False

    await db.bcv_rates.insert_one({**snapshot})
    return True


async def get_latest(db) -> dict | None:
    doc = await db.bcv_rates.find_one({}, {"_id": 0}, sort=[("fetched_at", -1)])
    if doc:
        ts = doc.get("fetched_at")
        if ts and hasattr(ts, "isoformat"):
            doc["fetched_at"] = ts.isoformat()
    return doc


async def get_history(db, limit: int = 50) -> list[dict]:
    cursor = db.bcv_rates.find({}, {"_id": 0}).sort("fetched_at", -1).limit(min(limit, 500))
    items = await cursor.to_list(500)
    for it in items:
        ts = it.get("fetched_at")
        if ts and hasattr(ts, "isoformat"):
            it["fetched_at"] = ts.isoformat()
    return items


# ========== Background scheduler ==========

_scheduler_task: asyncio.Task | None = None
DEFAULT_INTERVAL_HOURS = 3  # Check every 3 hours


async def _scheduler_loop(db, interval_seconds: int):
    """Background loop: fetches BCV rates periodically."""
    while True:
        try:
            snap = await fetch_bcv_rates()
            saved = await save_snapshot(db, snap)
            if saved:
                logger.info(f"BCV rates updated: {snap['rates']}")
            else:
                logger.debug("BCV rates unchanged, skipped")
        except Exception as e:
            logger.warning(f"BCV fetch failed: {e}")
        await asyncio.sleep(interval_seconds)


def start_scheduler(db, interval_hours: float = DEFAULT_INTERVAL_HOURS):
    """Start the background scheduler. Safe to call multiple times."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return  # Already running
    interval_seconds = int(interval_hours * 3600)
    _scheduler_task = asyncio.create_task(_scheduler_loop(db, interval_seconds))
    logger.info(f"BCV scheduler started (every {interval_hours}h)")


def stop_scheduler():
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
