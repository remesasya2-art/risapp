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

    Con la MISMA definición. Si las opciones no coinciden —`unique`, `sparse`—
    Mongo no lo reescribe: lo rechaza con IndexOptionsConflict. Por eso la
    lista de abajo declara cada índice tal como ya está en la base, y los
    choques que igual aparezcan se cuentan aparte de los fallos: un índice que
    ya está no es un dato sucio, y mezclarlos esconde el aviso que importa.
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
    # SIN `sparse`, y no por descuido: el `lifespan` viejo de server.py ya
    # creó este índice como `unique` a secas, y ESE bloque sí corría. Mongo
    # no reescribe un índice que ya está: si las opciones no coinciden
    # —`sparse` es una opción— rechaza la creación con IndexOptionsConflict,
    # y en toda base donde la aplicación ya arrancó esto fallaría en cada
    # arranque, para siempre. Declararlo igual a lo que hay es lo que hace
    # que la línea de abajo sea un no-op en vez de un error diario.
    #
    # No se pierde nada: `sparse` sólo sirve para permitir varios documentos
    # SIN la clave, y todo caso tiene `caso_id` —lo pone la migración y lo
    # ponen las altas—. Los otros dos únicos sí lo llevan porque son índices
    # nuevos, sin nada previo con qué chocar.
    ("soporte_casos", "caso_id", {"unique": True}),
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


# (colección, nombre) de los índices que el `lifespan` viejo creó y que los de
# arriba dejaron sin trabajo. Van por NOMBRE porque es así como se borran.
#
#   · soporte_casos/estado_1_area_1 — lo reemplaza `area_1_estado_1`. Un
#     filtro por igualdad sobre los dos campos usa el compuesto sin importar
#     en qué orden estén declarados, así que tener los dos es pagar dos
#     escrituras por cada alta de caso para responder la misma consulta.
#   · soporte_pedidos/caso_id_1 — lo reemplaza `caso_id_1_creado_en_1`, que
#     lo tiene de prefijo. Un índice cuyo prefijo es otro índice no aporta.
#
# Se borran DESPUES de crear (ver `_crear`), nunca antes: así no hay un
# instante en que la consulta se quede sin ningún índice que la cubra.
SOBRANTES = (
    ("soporte_casos", "estado_1_area_1"),
    ("soporte_pedidos", "caso_id_1"),
)


async def _borrar_sobrantes(db) -> list:
    """Saca los índices que quedaron sin trabajo. No lanza.

    Borrar uno que no está es lo normal —base nueva, o segundo arranque— y no
    es un error: se ignora en silencio. Lo que se devuelve es lo que de verdad
    se borró, que es lo único que vale la pena contar.
    """
    borrados = []
    for coleccion, nombre in SOBRANTES:
        try:
            await db[coleccion].drop_index(nombre)
            borrados.append(f"{coleccion}/{nombre}")
            logger.info(f"soporte: se borró el índice viejo {coleccion}/{nombre}")
        except Exception:
            # IndexNotFound es el caso esperado y no se loguea para no llenar
            # el arranque de ruido. Cualquier otro fallo tampoco importa: un
            # índice de más es lento, no incorrecto.
            pass
    return borrados


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
        return {"creados": 0, "fallidos": [], "conflictos": [], "sobrantes": [],
                "timeout": False, "sin_base": True}

    try:
        return await asyncio.wait_for(_crear(db), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            f"soporte: la creación de índices no terminó en {timeout_s}s. La "
            "aplicación levanta igual; los que falten se crean en el próximo "
            "arranque.")
        return {"creados": 0, "fallidos": [], "conflictos": [], "sobrantes": [],
                "timeout": True}


def _es_conflicto_de_opciones(e) -> bool:
    """¿Es «ya existe con otras opciones» (IndexOptionsConflict, 85)?

    Se mira el código y, si no viene, el texto: mongomock levanta la misma
    situación sin número, y los tests corren sobre mongomock.
    """
    if getattr(e, "code", None) == 85:
        return True
    return "already exists with different options" in str(e)


async def _crear(db) -> dict:
    creados, fallidos, conflictos = 0, [], []
    for coleccion, claves, opciones in INDICES:
        try:
            await db[coleccion].create_index(claves, **opciones)
            creados += 1
        except Exception as e:
            if _es_conflicto_de_opciones(e):
                # El índice ESTA, con otras opciones. No es un problema de
                # datos y no se arregla solo, así que va en su propia lista:
                # mezclarlo con `fallidos` sería enterrar el aviso que de
                # verdad importa —«hay duplicados»— bajo ruido de cada
                # arranque. Y NO se borra para recrearlo: sobre una colección
                # grande eso deja la base sin el único justo mientras se
                # reconstruye. Se informa y lo decide una persona.
                conflictos.append({"coleccion": coleccion, "claves": claves,
                                   "error": str(e)})
                logger.info(
                    f"soporte: el índice {coleccion}/{claves} ya existe con "
                    f"otras opciones; se deja el que está ({e})")
                continue
            # Un único sobre datos que ya violan la unicidad falla acá, y es
            # información valiosa: dice que hay duplicados. Se loguea con la
            # colección y la clave para poder ir a buscarlos.
            fallidos.append({"coleccion": coleccion, "claves": claves,
                             "error": str(e)})
            logger.warning(
                f"soporte: no se pudo crear el índice {coleccion}/{claves}: {e}")

    sobrantes = await _borrar_sobrantes(db)

    logger.info(
        f"soporte: {creados} índices listos, {len(fallidos)} con problemas, "
        f"{len(conflictos)} ya estaban con otras opciones, "
        f"{len(sobrantes)} viejos borrados")
    return {"creados": creados, "fallidos": fallidos, "conflictos": conflictos,
            "sobrantes": sobrantes, "timeout": False}
