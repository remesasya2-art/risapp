"""
services/soporte_indices.py — Los índices de la mesa de ayuda.

POR QUE ESTE MODULO EXISTE

    Los índices de la mesa de ayuda estaban escritos DOS VECES, en dos
    archivos, con listas distintas:

      · `database.py`, dentro de `create_indexes()` — la lista completa y
        pensada, con los tres únicos que protegen la colección.
      · `server.py`, dentro del `lifespan` — un subconjunto, sin ninguno de
        los únicos.

    Y sólo corría la segunda. `create_indexes()` la llama `init_db()`, y a
    `init_db()` no la llama nadie: las dos funciones están vivas en el
    archivo y muertas en la aplicación. Se puede comprobar en un grep.

    Resultado: los índices que alguien se tomó el trabajo de pensar —el único
    de `mensaje_id`, el de `pedido_id`, el de `[estado, actualizado_en]`— no
    existen en la base, y nada lo dice. Peor que no tenerlos escritos: están
    escritos, así que el próximo que lea el archivo va a creer que están.

    Este módulo es la ÚNICA fuente. Se engancha en el `lifespan` como
    `envios_indices`, `auditoria` e `invitaciones`, que es el patrón que en
    este proyecto sí corre.

POR QUE IMPORTA JUSTO AHORA

    `migrations/002_chats_a_casos.py` está por volcar todo el historial de
    `support_chats` acá adentro. Dos de estos índices tienen que existir
    ANTES de esa corrida, no después:

      · `mensaje_id` único es la red que impide que una migración cortada a
        la mitad y vuelta a correr duplique mensajes. La migración se cuida
        sola comparando contra lo ya movido, pero su propio comentario da por
        sentado este índice, y hoy no está.
      · `[estado, actualizado_en]` es exactamente la consulta de la bandeja
        del asesor: filtra por estado y ordena por fecha. Hoy hay
        `[estado, area]`, que sirve para el filtro y NO para el orden. Con la
        colección casi vacía da igual; con el historial adentro es un scan
        cada doce segundos por cada asesor conectado.

NINGUN ERROR DE ACA PUEDE TUMBAR EL ARRANQUE, NI DEMORARLO

    Mismo criterio que envíos, y por el mismo motivo: un índice que no se
    pudo crear es un problema de rendimiento, no de corrección. Cada fallo se
    loguea y se sigue, y hay un tope de tiempo para todo el bloque —con Mongo
    inalcanzable, cada `create_index` espera su propio timeout de selección de
    servidor y la suma es un arranque colgado.

    Crear un índice en Mongo es idempotente: si ya existe con la misma
    definición, no pasa nada. Por eso esto corre en cada arranque.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Las colecciones que el módulo usa, para poder responder "qué toca la mesa de
# ayuda" sin leer todo el código.
COLECCIONES = ("soporte_casos", "soporte_mensajes", "soporte_pedidos",
               "quick_replies")

# (colección, claves, opciones). El orden importa poco salvo por una cosa: los
# únicos van primero, porque son los que pueden fallar sobre datos sucios y
# queremos verlos en el log del arranque aunque el tope de tiempo corte el
# resto.
INDICES = (
    # ─── casos ────────────────────────────────────────────────────────────
    ("soporte_casos", "caso_id", {"unique": True, "sparse": True}),
    # La bandeja del asesor: filtra por estado y ORDENA por actualizado_en.
    # Las dos mitades en el mismo índice o el orden se hace en memoria.
    ("soporte_casos", [("estado", 1), ("actualizado_en", -1)], {}),
    # «Mis casos» del cliente, ordenados por lo último que pasó.
    ("soporte_casos", [("user_id", 1), ("actualizado_en", -1)], {}),
    # La bandeja filtrada por área, y «los míos» del asesor.
    ("soporte_casos", [("area", 1), ("estado", 1)], {}),
    ("soporte_casos", [("asignado_a", 1), ("estado", 1)], {}),
    # El número NO es único a propósito: si la migración trajera uno repetido
    # —el contador y las altas nuevas corren a la vez—, un único haría fallar
    # la creación y, en una lista dentro de un solo try, se llevaría puestos
    # los índices que vienen después. Se indexa para poder buscar por número,
    # que es lo que el cliente dicta por teléfono.
    ("soporte_casos", "numero", {}),

    # ─── mensajes ─────────────────────────────────────────────────────────
    # El único que sostiene la idempotencia de la migración.
    ("soporte_mensajes", "mensaje_id", {"unique": True, "sparse": True}),
    ("soporte_mensajes", [("caso_id", 1), ("creado_en", 1)], {}),

    # ─── pedidos a otra área ──────────────────────────────────────────────
    ("soporte_pedidos", "pedido_id", {"unique": True, "sparse": True}),
    ("soporte_pedidos", [("area", 1), ("estado", 1)], {}),
    ("soporte_pedidos", [("caso_id", 1), ("creado_en", 1)], {}),

    # ─── respuestas rápidas ───────────────────────────────────────────────
    ("quick_replies", [("created_at", 1)], {}),
)


# Tope para TODO el bloque, no por índice. Con la base sana, crear once
# índices que ya existen tarda milisegundos; si esto se agota, la base no está
# en condiciones y lo que importa es que la aplicación levante igual.
TIMEOUT_TOTAL_S = 20.0


async def asegurar_indices(db=None, timeout_s: float = TIMEOUT_TOTAL_S) -> dict:
    """Crea los índices de la mesa de ayuda. Idempotente, acotada, y no lanza.

    Devuelve un resumen —creados, fallidos, si se agotó el tiempo— para que el
    arranque lo loguee y para poder testearla sin una base real.
    """
    try:
        if db is None:
            from database import db as db_real
            db = db_real
    except Exception as e:                                   # pragma: no cover
        logger.warning(f"soporte: no hay base para crear índices: {e}")
        return {"creados": 0, "fallidos": [], "timeout": False, "sin_base": True}

    try:
        return await asyncio.wait_for(_crear(db), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            f"soporte: la creación de índices no terminó en {timeout_s}s. La "
            "aplicación levanta igual; los que falten se crean en el próximo "
            "arranque.")
        return {"creados": 0, "fallidos": [], "timeout": True}


async def _crear(db) -> dict:
    creados, fallidos = 0, []
    for coleccion, claves, opciones in INDICES:
        try:
            await db[coleccion].create_index(claves, **opciones)
            creados += 1
        except Exception as e:
            # Un único sobre datos que ya violan la unicidad falla acá, y es
            # información valiosa: dice que hay duplicados. Se loguea con la
            # colección y la clave para poder ir a buscarlos.
            fallidos.append({"coleccion": coleccion, "claves": claves,
                             "error": str(e)})
            logger.warning(
                f"soporte: no se pudo crear el índice {coleccion}/{claves}: {e}")

    logger.info(f"soporte: {creados} índices listos, {len(fallidos)} con problemas")
    return {"creados": creados, "fallidos": fallidos, "timeout": False}
