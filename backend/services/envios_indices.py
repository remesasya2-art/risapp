"""
services/envios_indices.py — Las colecciones del modulo de envios y sus indices.

POR QUE ESTE MODULO EXISTE Y NO ESTA EN database.py
    `create_indexes()` de database.py ya tiene cuarenta lineas de indices de todo
    el sistema. Sumarle las diecinueve de envios lo vuelve una lista imposible de leer,
    y ademas los indices de un modulo tienen que poder moverse con el modulo:
    borrarlo un dia deberia ser borrar un archivo, no cazar lineas sueltas.

    La forma de engancharlo es la de `routes/security_2fa.ensure_security_indexes`
    —una funcion que el `lifespan` llama en su propio try— pero con una
    diferencia deliberada: aquella deja que el primer indice que falla aborte el
    resto, y esta los intenta todos y ademas se rinde por tiempo. El motivo esta
    abajo.

QUE HACE Y QUE NO HACE
    Crea la ESTRUCTURA, nunca los DATOS. No hay seed de transportistas, ni de
    agencias, ni de tarifas: todo eso se carga desde el panel (§12). Un seed con
    una empresa de ejemplo es exactamente como un nombre real termina en el
    repositorio y despues no sale mas.

    Crear un indice en Mongo es idempotente: si ya existe con la misma
    definicion, no pasa nada. Por eso esto puede correr en cada arranque.

NINGUN ERROR DE ACA PUEDE TUMBAR EL ARRANQUE, NI DEMORARLO
    Un indice que no se pudo crear es un problema de rendimiento, no de
    correccion: la aplicacion funciona igual, mas lenta. Tumbar el arranque de
    toda la app por eso seria cambiar un problema chico por uno grave, asi que
    cada fallo se loguea y se sigue.

    Pero "se sigue" tiene una trampa que casi entra: con Mongo inalcanzable, cada
    create_index espera su propio serverSelectionTimeoutMS —treinta segundos por
    defecto— y veinte indices en serie son diez minutos de arranque colgado. En
    Railway eso es un healthcheck que falla y un crash-loop: la aplicacion entera
    caida por unos indices que no son criticos.

    Por eso hay un TOPE DE TIEMPO para todo el bloque. Si se agota, se loguea lo
    que falto y la aplicacion levanta igual. Los indices que quedaron sin crear
    se crean en el proximo arranque, cuando la base responda.
"""

import asyncio
import logging

from services.referencias import INDICES as INDICES_REFERENCIAS

logger = logging.getLogger(__name__)

# Las colecciones que el modulo usa. La lista existe para poder responder "que
# toca este modulo" sin leer todo el codigo, y para el chequeo de arranque.
COLECCIONES = (
    "envios",
    "envios_eventos",
    "transportistas",
    "agencias",
    "zonas",
    "tarifas_envio",
    "matrices_referencia",
    "colaboradores_retiro",
    "envios_archivos",
    "envios_lotes",
)

# (coleccion, claves, opciones). Las opciones son las de create_index.
INDICES = (
    # ─── envios ───────────────────────────────────────────────────────────
    ("envios", [("user_id", 1), ("created_at", -1)], {}),
    ("envios", "envio_id", {"unique": True, "sparse": True}),
    # sparse en los dos: si algun dia el display_id o el token se asignan en un
    # segundo paso, el segundo documento sin el campo choca con el primero por
    # un unico sobre null. Cuesta nada ahora y es un incidente despues.
    ("envios", "display_id", {"unique": True, "sparse": True}),
    # Opaco y unico: el token del seguimiento publico NUNCA es secuencial.
    ("envios", "tracking_token", {"unique": True, "sparse": True}),
    # La cola del operador, que es la consulta mas frecuente del panel.
    ("envios", [("estado", 1), ("created_at", -1)], {}),
    ("envios", "destino.agencia_codigo", {"sparse": True}),
    # Unico: dos envios con el mismo comprobante son dos cobros sobre un solo
    # despacho, y el segundo se descubre en el mostrador de Pacaraima.
    ("envios", "origen.codigo_objeto", {"unique": True, "sparse": True}),
    # El lote de retiro: agrupa los envios que viajaron juntos, que es lo que
    # hace posible la vista de rentabilidad por viaje (§2.3).
    ("envios", "origen.lote_retiro_id", {"sparse": True}),
    # El barrido de precios observados ordena por fecha sin filtrar. Sin este
    # indice es un COLLSCAN con sort en memoria, y Mongo aborta el sort al pasar
    # los 32 MB: la pantalla empieza a decir "sin observaciones" con un 200 OK.
    ("envios", [("created_at", -1)], {}),
    # La deduplicacion de cotizaciones: mismo usuario, mismo pedido, todavia
    # vigente. Sin esto, un doble clic deja dos envios de los que uno queda a la
    # deriva con datos personales de un tercero adentro.
    ("envios", [("user_id", 1), ("estado", 1), ("cotizacion.huella", 1)], {}),
    # TTL PARCIAL: solo borra las cotizaciones que nunca se confirmaron, cuando
    # su propia fecha de vencimiento paso. Un TTL a secas sobre `vence_at`
    # borraria envios reales; con el filtro, un documento deja de ser candidato
    # en el instante en que su estado cambia. Lo que queda es basura: un precio
    # que ya no se puede aceptar, guardando el nombre y el telefono de alguien.
    ("envios", "cotizacion.vence_at",
     {"expireAfterSeconds": 0, "partialFilterExpression": {"estado": "cotizado"}}),

    # ─── eventos (append-only, como el ledger) ────────────────────────────
    ("envios_eventos", [("envio_id", 1), ("created_at", 1)], {}),
    ("envios_eventos", "evento_id", {"unique": True, "sparse": True}),

    # ─── catalogo, todo cargado desde el panel ────────────────────────────
    ("transportistas", "transportista_id", {"unique": True, "sparse": True}),
    ("transportistas", "codigo", {"unique": True, "sparse": True}),
    ("agencias", [("transportista_id", 1), ("activa", 1), ("estado", 1)], {}),
    # El codigo de agencia es unico DENTRO de cada transportista, no en todo el
    # sistema: dos empresas distintas pueden llamar "001" a su sucursal central,
    # y un unico global le impediria al panel guardar la segunda con un E11000
    # que solo aparece como warning en el arranque.
    ("agencias", [("transportista_id", 1), ("codigo", 1)], {"unique": True}),
    # zonas: indice a secas, sin unicidad. Todavia no hay nada que escriba esta
    # coleccion, y una restriccion inventada antes del primer escritor es una
    # forma barata de bloquear el panel el dia que exista.
    ("zonas", [("transportista_id", 1), ("estado", 1)], {}),

    # ─── tarifas: la vigente se resuelve por VENTANA, no por "sin cierre" ──
    # La consulta que elige la vigente no filtra por vigente_hasta —eso se
    # decide en Python, porque las fechas guardadas como texto no matchean un
    # $gte— y ordena por vigente_desde. Sin este indice esa consulta es un
    # COLLSCAN, y la sirve un endpoint publico y sin rate limit.
    ("tarifas_envio", "version_id", {"unique": True, "sparse": True}),
    ("tarifas_envio", [("vigente_desde", -1)], {}),
    ("tarifas_envio", [("vigente_hasta", 1), ("vigente_desde", -1)], {}),
    # El historial del panel ordena por fecha de creacion, no de vigencia: una
    # version programada se crea hoy y rige el mes que viene.
    ("tarifas_envio", [("creada_at", -1)], {}),

    # ─── archivos: comprobantes y evidencias ──────────────────────────────
    ("envios_archivos", "asset_id", {"unique": True, "sparse": True}),
    ("envios_archivos", [("envio_id", 1), ("clase", 1)], {}),
    # Para detectar el mismo comprobante subido en dos envios distintos.
    ("envios_archivos", "sha256", {}),
    # La migracion pregunta "cuales siguen en Mongo" en cada lote. Sin esto es un
    # scan de la coleccion mas pesada del modulo por cada click del panel.
    ("envios_archivos", "almacen", {}),

    # ─── lotes de retiro: el viaje a la agencia ───────────────────────────
    ("envios_lotes", "lote_id", {"unique": True, "sparse": True}),
    ("envios_lotes", [("created_at", -1)], {}),

    # ─── nomina de retiro ─────────────────────────────────────────────────
    ("colaboradores_retiro", "colaborador_id", {"unique": True, "sparse": True}),
) + tuple(
    # Los de las matrices los declara referencias.py, al lado de las consultas
    # que los usan, para que no se desincronicen.
    (coleccion, claves, {}) for coleccion, claves in INDICES_REFERENCIAS
)


# Tope para TODO el bloque, no por índice. Con la base sana, crear veinte
# índices que ya existen tarda milisegundos; si esto se agota, la base no está
# en condiciones y lo que importa es que la aplicación levante igual.
TIMEOUT_TOTAL_S = 20.0


async def ensure_envios_indexes(db=None, timeout_s: float = TIMEOUT_TOTAL_S) -> dict:
    """Crea los índices del módulo. Idempotente, acotada en tiempo, y no lanza.

    Devuelve un resumen —creados, fallidos, si se agotó el tiempo— para que el
    arranque lo loguee y para poder testearla sin una base real.
    """
    try:
        if db is None:
            from database import db as db_real
            db = db_real
    except Exception as e:                                   # pragma: no cover
        logger.warning(f"envios: no hay base para crear índices: {e}")
        return {"creados": 0, "fallidos": [], "timeout": False, "sin_base": True}

    try:
        return await asyncio.wait_for(_crear(db), timeout=timeout_s)
    except asyncio.TimeoutError:
        # Los que falten se crean en el próximo arranque, cuando la base
        # responda. Crear un índice es idempotente, así que reintentar es gratis.
        logger.warning(
            f"envios: la creación de índices no terminó en {timeout_s}s. La aplicación "
            "levanta igual; los índices que falten se crean en el próximo arranque."
        )
        return {"creados": 0, "fallidos": [], "timeout": True}


async def _crear(db) -> dict:
    creados, fallidos = 0, []
    for coleccion, claves, opciones in INDICES:
        try:
            await db[coleccion].create_index(claves, **opciones)
            creados += 1
        except Exception as e:
            # Un índice único sobre datos que ya violan la unicidad falla acá, y
            # es información valiosa: dice que hay duplicados que alguien metió a
            # mano. Se loguea con la colección y la clave para poder buscarlos.
            fallidos.append({"coleccion": coleccion, "claves": claves, "error": str(e)})
            logger.warning(f"envios: no se pudo crear el índice {coleccion}/{claves}: {e}")

    logger.info(f"envios: {creados} índices listos, {len(fallidos)} con problemas")
    return {"creados": creados, "fallidos": fallidos, "timeout": False}
