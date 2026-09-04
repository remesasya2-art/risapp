"""
BCV (Banco Central de Venezuela) scraper service.
Scrapes https://www.bcv.org.ve/ for official USD/EUR/CNY/TRY/RUB rates vs VES.
Stores snapshots in `bcv_rates` collection for history.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BCV_URL = "https://www.bcv.org.ve/"
CURRENCY_IDS = ["dolar", "euro", "yuan", "lira", "rublo"]
CARACAS_TZ = timezone(timedelta(hours=-4))

# ─── Por qué esto no es `verify=False` ────────────────────────────────────
#
# Esta consulta traía `verify=False`, que apaga la verificación del
# certificado TLS. Con eso, cualquiera que pueda interponerse en la conexión
# —una red comprometida, un DNS envenenado— sirve su propia página y la
# aplicación se cree la tasa que le manden.
#
# El valor raspado no es la tasa que se le cobra al cliente: eso vive en
# `db.rates`, y acá se escribe en `db.bcv_rates`. Pero
# `services/accounting_engine.py` lo lee como referencia BCV, así que una
# tasa falsa distorsiona la contabilidad. Y apagar la verificación del
# certificado es, además, lo primero que marca cualquier revisión de
# seguridad de un proveedor de pagos.
#
# El motivo original era casi con seguridad práctico: el sitio del BCV ha
# tenido la cadena de certificados incompleta. La respuesta correcta a eso es
# aportar el certificado que falta, no dejar de mirar.
#
# LA ESCOTILLA, Y POR QUE EXISTE
#
#   Si mañana la cadena del BCV se rompe otra vez, esto deja de traer la
#   tasa. Eso es lo correcto —mejor sin dato que con un dato inventado por un
#   tercero— pero puede dejar la referencia contable congelada sin que nadie
#   lo note. Por eso el ERROR es explícito y nombra la variable.
#
#   `BCV_TLS_INSEGURO=1` reactiva el comportamiento viejo. No es un
#   equivalente: avisa en CADA consulta, con nivel WARNING y diciendo que el
#   dato no es confiable. Un agujero ruidoso y deliberado no es lo mismo que
#   uno silencioso y permanente.
BCV_TLS_INSEGURO = os.environ.get("BCV_TLS_INSEGURO", "").strip() in ("1", "true", "True")


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
    """Fetch current BCV rates. Returns dict with rates, value_date, fetched_at.

    Verifica el certificado del servidor. Si no valida, NO cae a una conexión
    sin verificar: levanta, y el llamador registra el fallo. Un dato que pudo
    haber puesto un tercero es peor que no tener dato.
    """
    if BCV_TLS_INSEGURO:
        logger.warning(
            "BCV: consultando SIN verificar el certificado TLS porque "
            "BCV_TLS_INSEGURO está activada. La tasa que se guarde puede "
            "haberla puesto un tercero. Sacá la variable en cuanto se pueda.")

    try:
        async with httpx.AsyncClient(verify=not BCV_TLS_INSEGURO, timeout=30,
                                     follow_redirects=True) as client:
            r = await client.get(BCV_URL)
            r.raise_for_status()
    except httpx.ConnectError as e:
        # Se distingue del resto a propósito: un fallo de TLS pide una acción
        # concreta —conseguir el certificado intermedio del BCV— y perderlo
        # entre los timeouts de red es cómo se termina con la referencia
        # contable congelada sin que nadie sepa por qué.
        if "certificate" in str(e).lower() or "ssl" in str(e).lower():
            logger.error(
                "BCV: el certificado TLS del sitio no valida (%s). NO se "
                "guarda ninguna tasa: un dato servido por un tercero sería "
                "peor que ninguno. Si el sitio tiene la cadena incompleta, "
                "hay que aportar el certificado intermedio; como último "
                "recurso existe BCV_TLS_INSEGURO=1, que avisa en cada "
                "consulta.", e)
        raise

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
