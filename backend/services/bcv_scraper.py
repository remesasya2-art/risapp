"""
BCV (Banco Central de Venezuela) scraper service.
Scrapes https://www.bcv.org.ve/ for official USD/EUR/CNY/TRY/RUB rates vs VES.
Stores snapshots in `bcv_rates` collection for history.

DOS COSAS QUE ESTE MODULO APRENDIO A LA FUERZA

    1. EL SITIO DEL BCV MANDA LA CADENA DE CERTIFICADOS INCOMPLETA, y por eso
       dejó de poder consultarse. No es que su certificado sea falso: falta la
       pieza del medio que lo une a una raíz conocida. El navegador la busca
       sola; Python no. Ahora se busca: ver `services/cadena_tls.py`.

    2. UNA TASA VIEJA NO PUEDE HACERSE PASAR POR LA DE HOY. Mientras lo de
       arriba estuvo roto, el raspador no trajo nada y la contabilidad siguió
       usando el último número raspado — sin mirar de cuándo era, y ganándole
       al que el operador cargaba a mano en el panel. O sea: cambiar la tasa en
       el panel no cambiaba la contabilidad. Por eso ahora el dato tiene fecha
       de vencimiento (`vigencia`), y vencido pierde.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

from services import cadena_tls

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
# aportar el certificado que falta, no dejar de mirar. ESO YA ESTA HECHO, y se
# hace solo: `services/cadena_tls.py` consigue la pieza que falta y reintenta
# CON la verificación puesta.
#
# LA ESCOTILLA, Y POR QUE SIGUE EXISTIENDO
#
#   Si mañana la conexión al BCV se rompe por un motivo que completar la cadena
#   no arregla, esto deja de traer la tasa. Eso es lo correcto —mejor sin dato
#   que con un dato inventado por un tercero— y ahora además la tasa vieja no
#   se hace pasar por nueva. Pero la escotilla se queda para el día que haga
#   falta salir del paso.
#
#   `BCV_TLS_INSEGURO=1` reactiva el comportamiento viejo. No es un
#   equivalente: avisa en CADA consulta, con nivel WARNING y diciendo que el
#   dato no es confiable. Un agujero ruidoso y deliberado no es lo mismo que
#   uno silencioso y permanente.
BCV_TLS_INSEGURO = os.environ.get("BCV_TLS_INSEGURO", "").strip() in ("1", "true", "True")

# Cuántas horas vale un raspado si nadie configuró otra cosa. El número de
# verdad lo pone el panel (`configuracion.bcv_horas_de_vigencia`); esto es el
# piso para cuando la base no contesta.
HORAS_DE_VIGENCIA_POR_OMISION = 24


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


# ══════════════════════════════════════════════════════════════════════════
# Traer la página, con el certificado verificado
# ══════════════════════════════════════════════════════════════════════════

def _es_fallo_de_certificado(error) -> bool:
    """¿Este fallo de conexión es del certificado y no de la red?

    Se distingue a propósito: un fallo de TLS pide una acción concreta y
    perderlo entre los timeouts de red es cómo se termina con la referencia
    contable congelada sin que nadie sepa por qué.
    """
    texto = str(error).lower()
    return "certificate" in texto or "ssl" in texto


async def _pedir(verificacion):
    """Una consulta al sitio del BCV. `verificacion` es lo que se le pasa a
    `httpx`: `True` para el depósito de siempre, o un contexto TLS con la pieza
    que falta ya adentro. En los dos casos SE VERIFICA."""
    async with httpx.AsyncClient(verify=verificacion, timeout=30,
                                 follow_redirects=True) as cliente:
        respuesta = await cliente.get(BCV_URL)
        respuesta.raise_for_status()
        return respuesta


async def _traer_la_pagina():
    """La página del BCV. Dos intentos, y el segundo NO afloja nada.

    El primero es el de siempre. Si falla por el certificado, se va a buscar la
    pieza que el servidor del BCV no manda y se reintenta con ella puesta — la
    verificación sigue encendida y completa, así que si la pieza no alcanzara la
    conexión falla igual. Todo el detalle está en `services/cadena_tls.py`.
    """
    if BCV_TLS_INSEGURO:
        logger.warning(
            "BCV: consultando SIN verificar el certificado TLS porque "
            "BCV_TLS_INSEGURO está activada. La tasa que se guarde puede "
            "haberla puesto un tercero. Sacá la variable en cuanto se pueda.")
        return await _pedir(False)

    try:
        return await _pedir(True)
    except httpx.ConnectError as primero:
        if not _es_fallo_de_certificado(primero):
            raise
        return await _reintentar_completando_la_cadena(primero)


async def _reintentar_completando_la_cadena(primero):
    """El segundo intento: con la pieza que falta, y verificando igual."""
    url = httpx.URL(BCV_URL)
    host, puerto = url.host, url.port or 443
    try:
        contexto = await cadena_tls.contexto_para(host, puerto)
    except Exception as e:
        logger.error(
            "BCV: el certificado TLS del sitio no valida y tampoco se pudo "
            "completar la cadena sola (%s: %s). NO se guarda ninguna tasa: un "
            "dato servido por un tercero sería peor que ninguno. Como último "
            "recurso existe BCV_TLS_INSEGURO=1, que avisa en cada consulta.",
            type(e).__name__, e)
        # Se levanta el fallo ORIGINAL, no éste. Es el que el llamador sabe
        # nombrar —«no se pudo contactar BCV»— y el motivo por el que no se pudo
        # completar la cadena ya quedó entero en el registro de arriba.
        raise primero from e

    logger.warning(
        "BCV: el sitio manda la cadena de certificados incompleta. Se consiguió "
        "la pieza que falta y se reintenta CON la verificación puesta.")
    try:
        return await _pedir(contexto)
    except httpx.ConnectError as segundo:
        if _es_fallo_de_certificado(segundo):
            # La pieza guardada dejó de servir. Lo normal es que la autoridad
            # la haya rotado: se tira, y la próxima consulta va a buscar la
            # nueva. Sin esto habría que reiniciar el servidor — y el botón
            # «Actualizar ahora» del panel ya alcanza para reintentar.
            cadena_tls.olvidar(host, puerto)
            logger.error(
                "BCV: la pieza que completaba la cadena dejó de servir (%s). "
                "Se descartó; la próxima consulta va a buscar la nueva.",
                segundo)
        raise


async def fetch_bcv_rates() -> dict:
    """Fetch current BCV rates. Returns dict with rates, value_date, fetched_at.

    Verifica el certificado del servidor. Si no valida, NO cae a una conexión
    sin verificar: levanta, y el llamador registra el fallo. Un dato que pudo
    haber puesto un tercero es peor que no tener dato.
    """
    r = await _traer_la_pagina()

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


# ══════════════════════════════════════════════════════════════════════════
# La fecha de vencimiento del dato raspado
# ══════════════════════════════════════════════════════════════════════════

def _edad_en_horas(cuando):
    """Cuántas horas tiene este dato, o `None` si no se puede saber.

    `None` NO ES CERO, y la diferencia es el punto de todo esto: un dato sin
    fecha no se puede afirmar vigente, y lo que no se puede afirmar no le gana
    a lo que una persona cargó a mano.
    """
    if not isinstance(cuando, datetime):
        return None
    if cuando.tzinfo is None:
        # Mongo devuelve las fechas sin zona; en esta base se guardan en UTC.
        cuando = cuando.replace(tzinfo=timezone.utc)
    segundos = (datetime.now(timezone.utc) - cuando).total_seconds()
    # Un dato con fecha futura es raro (reloj desfasado) pero no es viejo.
    return round(max(0.0, segundos) / 3600, 2)


async def horas_de_vigencia(db) -> int:
    """Cuántas horas vale un raspado. Lo decide el panel."""
    try:
        from services import configuracion
        return int(await configuracion.leer(db, "bcv_horas_de_vigencia"))
    except Exception as e:
        # Que no se pueda leer el ajuste no puede tirar abajo la contabilidad.
        logger.warning("BCV: no se pudo leer bcv_horas_de_vigencia (%s); se "
                       "usan %d horas.", e, HORAS_DE_VIGENCIA_POR_OMISION)
        return HORAS_DE_VIGENCIA_POR_OMISION


async def vigencia(db, session=None) -> dict:
    """Qué tan viejo es el último raspado, y si todavía se le puede creer.

    Es la función que decide quién le gana a quién en `accounting_engine`, y la
    que el panel usa para pintar la tarjeta en rojo.
    """
    horas = await horas_de_vigencia(db)
    doc = await db.bcv_rates.find_one(
        {}, {"_id": 0, "rates": 1, "value_date": 1, "fetched_at": 1},
        sort=[("fetched_at", -1)], session=session)

    dolar = ((doc or {}).get("rates") or {}).get("dolar")
    if not dolar:
        return {"hay_raspado": False, "dolar": None, "fetched_at": None,
                "edad_horas": None, "vencida": False, "sirve": False,
                "horas_de_vigencia": horas}

    edad = _edad_en_horas(doc.get("fetched_at"))
    vencida = edad is None or edad > horas
    cuando = doc.get("fetched_at")
    return {
        "hay_raspado": True,
        "dolar": dolar,
        "fetched_at": cuando.isoformat() if hasattr(cuando, "isoformat") else None,
        "edad_horas": edad,
        "vencida": vencida,
        "sirve": not vencida,
        "horas_de_vigencia": horas,
    }


async def get_latest(db) -> dict | None:
    doc = await db.bcv_rates.find_one({}, {"_id": 0}, sort=[("fetched_at", -1)])
    if doc:
        ts = doc.get("fetched_at")
        if ts and hasattr(ts, "isoformat"):
            doc["fetched_at"] = ts.isoformat()
        # La antigüedad viaja con el dato: una pantalla que muestra un número
        # sin decir de cuándo es, miente por omisión.
        estado = await vigencia(db)
        doc["vencida"] = estado["vencida"]
        doc["edad_horas"] = estado["edad_horas"]
        doc["horas_de_vigencia"] = estado["horas_de_vigencia"]
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

# El nombre del turno. Lo comparten el reloj de acá y el botón de refrescar del
# panel: son los dos únicos que raspan, y no tienen por qué hacerlo a la vez.
TURNO = "bcv"

# Cuánto dura el turno. Tiene que alcanzar para una raspada completa —el pedido
# al BCV espera hasta 30 segundos, y hay un reintento que completa la cadena de
# certificados— y ser MUCHO menos que cada cuánto corre el reloj, o el turno
# nunca estaría caducado y la tasa dejaría de actualizarse.
#
# Dos minutos también deja el botón del panel casi siempre libre: quien lo
# aprieta justo después de una raspada automática no tiene que esperar.
SEGUNDOS_DEL_TURNO = 120


async def _scheduler_loop(db, interval_seconds: int):
    """Background loop: fetches BCV rates periodically.

    UN SOLO PROCESO RASPA, AUNQUE HAYA VARIOS

        Este reloj vive adentro del proceso de la aplicación. Hoy hay uno solo
        —`railway.toml` arranca sin `--workers`— así que corre una vez porque
        no hay más procesos, no porque nadie lo haya frenado.

        Con cuatro procesos serían cuatro raspadas por hora al sitio del BCV
        —lento, del gobierno venezolano, y que puede bloquear por exceso—, más
        filas duplicadas en el historial y avisos de vencimiento repetidos a
        cada super administrador.

        El turno lo resuelve sin infraestructura nueva: se lo lleva uno y los
        demás se saltan la vuelta. Ver `services/turnos.py`.
    """
    from services import turnos

    while True:
        if not await turnos.me_toca(db, TURNO, segundos=SEGUNDOS_DEL_TURNO):
            # Otro proceso está raspando ahora mismo, o acaba de hacerlo. No
            # hay nada que hacer en esta vuelta.
            await asyncio.sleep(interval_seconds)
            continue

        try:
            snap = await fetch_bcv_rates()
            saved = await save_snapshot(db, snap)
            if saved:
                logger.info(f"BCV rates updated: {snap['rates']}")
            else:
                logger.debug("BCV rates unchanged, skipped")
        except Exception as e:
            logger.warning(f"BCV fetch failed: {e}")

        # PASE LO QUE PASE ARRIBA, se mira la antigüedad y se avisa si hace
        # falta. Está afuera del `try` a propósito: el caso que importa avisar
        # es justamente el que entra por el `except`.
        try:
            from services import aviso_de_bcv
            await aviso_de_bcv.avisar_si_vencio(db, await vigencia(db))
        except Exception as e:
            logger.warning(f"BCV: no se pudo revisar la antigüedad: {e}")

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
