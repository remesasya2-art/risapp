"""
Acreditar un pago UNA sola vez, aunque el aviso llegue dos veces.

EL PROBLEMA

    Mercado Pago liquida las tarjetas de forma sincrónica (`binary_mode`) Y
    además manda un webhook por el mismo pago. Los dos caminos del backend
    —`payments_card.process_card_payment` y `gestor_pix._handle_card_webhook`—
    acreditan saldo, y los dos se protegían así:

        existente = await db.processed_webhooks.find_one({"webhook_event_id": x})
        if not existente:
            await db.processed_webhooks.insert_one({...})
            await saldos.mover(...)          # acredita

    Entre el `find_one` y el `insert_one` hay una ventana. Si el webhook entra
    mientras el flujo sincrónico todavía está corriendo —que es exactamente el
    caso para el que ese guard fue escrito— los dos leen que no hay nada, los
    dos insertan, y los dos acreditan. El usuario cobra dos veces por un pago.

    Y no alcanzaba con dar vuelta el orden: sin un índice ÚNICO sobre
    `webhook_event_id`, dos `insert_one` simultáneos entran los dos igual. El
    índice existía en `accounting_engine.ensure_indexes()`, pero eso sólo corre
    si un super admin llama a mano a POST /admin/accounting/v2/bootstrap-indexes.
    En el arranque no se creaba.

LA REGLA ACÁ ES LA OPUESTA A LA DE services/idempotency.py

    Aquel módulo dice, y hace bien, que ante la duda deja pasar la operación:
    se trata de CREAR una solicitud de envío, que después un administrador
    aprueba, y bloquear una solicitud legítima es peor que un duplicado raro.

    Acá no hay administrador después. Acá se acredita saldo. Un duplicado es
    plata que sale sin que nadie la mire, y no hay ningún paso posterior donde
    aparezca. Así que ante la duda NO se acredita: quien no pudo reclamar el
    evento se abstiene, y si algo falla queda un ERROR en el log con el id del
    evento para revisarlo a mano. Un cobro que hay que repetir se arregla; un
    saldo acreditado de más hay que ir a buscarlo.
"""
import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

COLECCION = "processed_webhooks"
CAMPO = "webhook_event_id"
NOMBRE_INDICE = "ux_webhook_event"

# Cuánto se guarda el registro de un evento ya procesado. Tiene que ser más
# largo que cualquier reintento que el proveedor pueda hacer; si el registro
# expira antes, un reintento tardío vuelve a acreditar.
DIAS_DE_RETENCION = 180


async def asegurar_indice(db) -> bool:
    """Crea el índice único sobre `webhook_event_id`. Devuelve si quedó puesto.

    Se llama al arrancar la app y también, por las dudas, en CADA reclamo.
    `createIndex` sobre un índice que ya existe es una operación barata, y no
    cachear el resultado es deliberado: un caché en una variable de módulo
    supone que el proceso habla siempre con la misma base, y el precio de que
    esa suposición sea falsa es acreditar un pago dos veces. Un viaje de ida y
    vuelta más por pago, en un camino que ya llama a la API de Mercado Pago,
    no se nota. Un saldo de más hay que ir a buscarlo.

    Si falla porque YA HAY duplicados, eso no es un problema de índices: es la
    prueba de que algún pago se procesó dos veces. Se registra como ERROR con
    los eventos repetidos, porque hay que ir a mirar esos saldos.
    """
    try:
        await db[COLECCION].create_index(CAMPO, unique=True, name=NOMBRE_INDICE)
        await db[COLECCION].create_index(
            "processed_at",
            expireAfterSeconds=60 * 60 * 24 * DIAS_DE_RETENCION,
            name="ttl_processed_at")
        return True
    except Exception as e:
        repetidos = await duplicados(db)
        if repetidos:
            logger.error(
                "PAGOS PROCESADOS DOS VECES: no se pudo crear el índice único "
                "de %s porque ya hay eventos repetidos en la base. Estos saldos "
                "hay que revisarlos a mano: %s", COLECCION, repetidos)
        else:
            logger.error(
                "SIN INDICE UNICO en %s.%s (%s). Mientras falte, dos avisos "
                "simultáneos del mismo pago pueden acreditar dos veces.",
                COLECCION, CAMPO, e)
        return False


async def duplicados(db, limite: int = 50) -> list:
    """Los `webhook_event_id` que aparecen más de una vez. Sólo lee."""
    try:
        cursor = db[COLECCION].aggregate([
            {"$group": {"_id": f"${CAMPO}", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$limit": limite},
        ])
        return [{"evento": d["_id"], "veces": d["n"]} async for d in cursor]
    except Exception as e:                                # pragma: no cover
        logger.warning("No se pudieron listar duplicados de %s: %s", COLECCION, e)
        return []


async def reclamar(db, evento_id: str, *, proveedor: str, session=None) -> bool:
    """Reclama el derecho a acreditar `evento_id`. UNO solo lo consigue.

    Devuelve True si este proceso es el que tiene que acreditar, y False si el
    evento ya estaba tomado — en cuyo caso el llamador NO debe tocar el saldo.

    Escribe primero y mira después: el `insert_one` sobre un índice único es la
    única operación que dos procesos simultáneos no pueden ganar los dos.
    """
    if not evento_id:
        # Sin id no hay forma de reconocer un repetido. Acreditar a ciegas es
        # justo lo que este módulo existe para no hacer.
        logger.error("Se pidió reclamar un evento sin id (proveedor=%s)", proveedor)
        return False

    await asegurar_indice(db)
    try:
        await db[COLECCION].insert_one(
            {
                CAMPO: evento_id,
                "provider": proveedor,
                "processed_at": datetime.now(timezone.utc),
            },
            session=session,
        )
        return True
    except DuplicateKeyError:
        logger.info("Evento %s ya procesado (%s): no se acredita de nuevo",
                    evento_id, proveedor)
        return False
    except Exception as e:
        # No se pudo dejar la marca. Acreditar igual sería acreditar sin red.
        logger.error("No se pudo reclamar el evento %s (%s): %s. NO se acredita.",
                     evento_id, proveedor, e)
        return False
