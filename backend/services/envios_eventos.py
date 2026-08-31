"""
services/envios_eventos.py — La bitacora del envio, append-only.

QUE ES Y QUE NO ES
    Es el "que paso y cuando" de cada paquete: quien lo movio, desde que estado,
    hacia cual, y con que datos. Se escribe y no se toca mas, como el ledger.

    NO es el estado. El estado vive en el documento del envio y es uno solo; esto
    es la historia de como llego ahi. Confundirlos lleva a reconstruir el estado
    recorriendo eventos, que es lento y se desincroniza el dia que un evento no
    se escriba.

POR QUE NUNCA LANZA
    Un evento que no se pudo escribir no puede deshacer un movimiento que ya
    ocurrio. Si el paquete paso a `esperando_postagem` y la bitacora falla, el
    paquete SIGUE en `esperando_postagem`: tirar un error ahi le diria al usuario
    que su confirmacion no se guardo cuando si se guardo, y lo llevaria a
    confirmar de nuevo.

    El fallo se loguea como ERROR y no como warning, porque una bitacora que
    falla siempre y en silencio deja al modulo sin forma de contestar que paso —
    y eso se descubre justo cuando hace falta.
"""

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def registrar(envio: dict, de_estado: str, a_estado: str, actor_type: str,
                    actor_id: str = None, detalle: dict = None, db=None,
                    ahora=None) -> str | None:
    """Escribe una linea en la bitacora. Devuelve el evento_id, o None si fallo."""
    ahora = ahora or datetime.now(timezone.utc)
    evento = {
        # El uuid ENTERO, no doce caracteres. Con el indice unico que declara
        # envios_indices, una colision no produce una fila duplicada: produce un
        # E11000 que esta funcion atrapa, loguea y convierte en None. O sea, una
        # linea de bitacora que se pierde en silencio, en la coleccion que existe
        # justamente para poder contestar que paso. Veinte caracteres mas.
        "evento_id": f"eve_{uuid.uuid4().hex}",
        "envio_id": (envio or {}).get("envio_id"),
        "display_id": (envio or {}).get("display_id"),
        "user_id": (envio or {}).get("user_id"),
        "de_estado": de_estado,
        "a_estado": a_estado,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "detalle": detalle or {},
        "created_at": ahora,
    }
    try:
        base = await _db(db)
        await base.envios_eventos.insert_one(dict(evento))
    except Exception as e:
        logger.error(
            f"envios: no se pudo escribir el evento {de_estado}->{a_estado} de "
            f"{evento['envio_id']}: {e}")
        return None
    return evento["evento_id"]


async def historial(envio_id: str, db=None, limite: int = 200) -> list[dict]:
    """Los eventos de un envio, del mas viejo al mas nuevo. Nunca lanza."""
    try:
        base = await _db(db)
        return await base.envios_eventos.find(
            {"envio_id": envio_id}, {"_id": 0}
        ).sort("created_at", 1).to_list(limite)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el historial de {envio_id}: {e}")
        return []
