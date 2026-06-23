"""
Idempotencia para operaciones que crean movimientos (envíos y recargas).
Evita que un doble clic o un reintento de red cree la misma operación dos veces.
El cliente envía una 'idempotency_key' única por intento; si llega repetida, el
servidor reconoce que ya la procesó y devuelve el resultado original en vez de
crear una segunda operación.

Filosofía de seguridad: NUNCA bloquea un envío legítimo. Si la idempotencia
falla por cualquier motivo, degrada con gracia (deja pasar la operación). Es
preferible arriesgar un duplicado raro que impedir una operación real.

NO altera el flujo de aprobación: el super administrador sigue siendo quien
verifica, aprueba o rechaza. Esto solo afecta la CREACIÓN de la solicitud.
"""
import logging
from datetime import datetime, timezone
from database import db

logger = logging.getLogger(__name__)

IDEMPOTENCY_COLLECTION = "idempotency_keys"

_idem_indexes_ready = False


async def _ensure_idem_indexes():
    global _idem_indexes_ready
    if _idem_indexes_ready:
        return
    try:
        await db[IDEMPOTENCY_COLLECTION].create_index(
            [("user_id", 1), ("action", 1), ("key", 1)], unique=True
        )
        await db[IDEMPOTENCY_COLLECTION].create_index([("created_at", -1)])
        _idem_indexes_ready = True
    except Exception as e:
        logger.warning(f"No se pudieron crear índices de idempotencia: {e}")


async def claim_idempotency(user_id: str, action: str, key: str):
    """Intenta reclamar una clave de idempotencia para (user_id, action, key).

    Devuelve una tupla (es_nueva, registro_existente):
      - (True, None): clave nueva; el llamador debe proceder y luego llamar a
        store_idempotency_result con el resultado.
      - (False, doc): ya existía. Si doc['result'] no es None, es una repetición
        de una operación ya completada y el llamador debe devolver ese resultado
        en vez de crear otra.

    Si la idempotencia falla por cualquier motivo, devuelve (True, None) para no
    bloquear el flujo (degrada con gracia).
    """
    if not key:
        return True, None
    try:
        await _ensure_idem_indexes()
        try:
            await db[IDEMPOTENCY_COLLECTION].insert_one({
                "user_id": user_id,
                "action": action,
                "key": key,
                "status": "processing",
                "result": None,
                "created_at": datetime.now(timezone.utc),
            })
            return True, None
        except Exception:
            # Inserción duplicada: la clave ya fue reclamada por otra petición
            existing = await db[IDEMPOTENCY_COLLECTION].find_one(
                {"user_id": user_id, "action": action, "key": key}
            )
            return False, existing
    except Exception as e:
        logger.warning(f"claim_idempotency degradado (action={action}): {e}")
        return True, None


async def store_idempotency_result(user_id: str, action: str, key: str, result: dict):
    """Guarda el resultado de una operación contra su clave, para que una
    repetición posterior devuelva exactamente lo mismo. Nunca lanza."""
    if not key:
        return
    try:
        await db[IDEMPOTENCY_COLLECTION].update_one(
            {"user_id": user_id, "action": action, "key": key},
            {"$set": {
                "status": "completed",
                "result": result,
                "completed_at": datetime.now(timezone.utc),
            }},
        )
    except Exception as e:
        logger.warning(f"store_idempotency_result fallo (action={action}): {e}")
