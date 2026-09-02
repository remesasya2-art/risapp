"""
services/envios_catalogo.py — Lo que la pantalla necesita saber antes de cotizar.

DOS PREGUNTAS, Y LAS DOS SE CONTESTAN LEYENDO
    "¿A dónde puedo mandar?" —el catálogo de destinos— y "¿qué caja me van a
    aceptar?" —los límites físicos—. Ninguna de las dos mueve nada; las dos las
    hace la pantalla antes de que el usuario tipee un peso.

POR QUE LOS LIMITES NO ESTAN EN EL FRONTEND
    Es el bug que arregló el PR #40 un escalón más arriba: la pantalla anunciaba
    un techo de R$ 2.000 que el servidor no validaba, porque el número vivía en
    dos lados y solo uno de los dos mandaba. Acá el mismo número sale de una sola
    fuente —la intersección de los transportistas activos— y lo consumen la
    pantalla y el servidor.

SIN CONFIGURACION, "NO DISPONIBLE" NO ES UN ERROR
    Antes de que el super administrador cargue el primer transportista, el módulo
    no puede cotizar. Eso no es una falla: es un estado normal del sistema recién
    instalado, y tiene que contestarse con un `disponible: false` y la lista de lo
    que falta — no con un 500 ni con una lista vacía que la pantalla interprete
    como "no hay restricciones".

EL CACHE Y SU BUG CLASICO
    El catálogo se lee en cada cotización y cambia una vez por mes, así que se
    cachea. Y ahí aparece el problema de siempre: **el super administrador agrega
    una agencia, guarda, y no aparece** hasta que Railway reinicie. Por eso el
    TTL es corto y hay una invalidación explícita.

    Las dos cosas, no una: la invalidación es el mecanismo y el TTL es la red por
    si alguien agrega una escritura y se olvida de llamarla. Hoy `invalidar_cache`
    no tiene ningún llamador y es correcto que así sea: el panel que escribe
    llega en el PR D2, y esta función existe para que ese PR la use en vez de
    tener que descubrir el problema en producción.
"""

import logging
import time
from datetime import datetime, timezone

from decimal import Decimal

from services import envios_origenes
from services.referencias import transportistas_activos, codigo_de, _activo
from services.envios_policy import (
    limites_efectivos, limites_payload, configuracion_incompleta,
    CATEGORIAS_PROHIBIDAS_POR_DEFECTO, TERMINOS_VERSION,
)

logger = logging.getLogger(__name__)

TTL_CATALOGO_S = 300

_cache: dict = {}


def invalidar_cache(clave: str = None) -> None:
    """La llamará el panel al guardar (PR D2). Sin esto, el TTL tarda en mostrar
    el cambio y el que lo guardó cree que no se guardó."""
    if clave is None:
        _cache.clear()
    else:
        _cache.pop(clave, None)


def _cacheado(clave: str):
    entrada = _cache.get(clave)
    if entrada and entrada[0] > time.monotonic():
        return entrada[1]
    return None


def _guardar(clave: str, valor, ttl_s: int = TTL_CATALOGO_S):
    _cache[clave] = (time.monotonic() + ttl_s, valor)
    return valor


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


# ─── Tarifa vigente ───────────────────────────────────────────────────────

# Cuántas versiones se miran para elegir la vigente. Con una tarifa nueva por
# mes son dieciséis años; el corte existe para que la consulta no crezca sola.
_VERSIONES_A_MIRAR = 200

# Solo las fechas y la identidad: es lo único que hace falta para decidir CUÁL
# rige. El documento entero se trae después, y solo el que ganó.
#
# No es una micro-optimización. `GET /envios/limites` es pública, no pide sesión,
# no está cacheada y no tiene rate limit; traer 200 tarifas completas —con sus
# escalones, sobrecargos, descuentos y temporadas— en cada request anónima es una
# amplificación de doscientos a uno contra el único endpoint que cualquiera puede
# martillar. Esta proyección la cubre el índice.
_PROYECCION_VENTANA = {"_id": 0, "version_id": 1, "vigente_desde": 1,
                       "vigente_hasta": 1, "anulada": 1}


def _fecha(valor):
    """Una fecha comparable, o None. Tolera el ISO en texto y el naive de motor."""
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


async def tarifa_vigente(db=None, ahora=None) -> dict | None:
    """La versión que está cobrando en este momento. Nunca lanza.

    Vigente es `vigente_desde <= ahora < vigente_hasta`, y las dos mitades de esa
    condición importan por razones distintas.

    **La de abajo**, porque `vigente_desde` existe para poder dejar un aumento
    programado: sin compararlo contra hoy, ese aumento rige desde que se guarda y
    el super administrador cree que programó algo cuando en realidad lo publicó.

    **La de arriba**, porque al publicar un aumento programado la versión actual
    se cierra con la fecha FUTURA en que dejará de regir. Buscar solo las que
    tienen `vigente_hasta: None` la dejaría afuera desde el instante en que se
    programa el reemplazo — y el módulo se quedaría sin tarifa un mes entero
    antes de tiempo, que fue exactamente lo que encontró el test del aumento
    programado.

    Sin tarifa el módulo no cotiza, y eso se responde con `disponible: false`,
    no con un 500.
    """
    ahora = ahora or datetime.now(timezone.utc)
    try:
        base = await _db(db)
        candidatas = await base.tarifas_envio.find(
            {}, _PROYECCION_VENTANA).sort("vigente_desde", -1).to_list(_VERSIONES_A_MIRAR)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la tarifa vigente: {e}")
        return None

    vigentes = []
    for t in candidatas or []:
        if t.get("anulada"):
            # Programada y después reemplazada por una corrección: nunca rigió.
            continue
        desde = _fecha(t.get("vigente_desde"))
        if desde is None or desde > ahora:
            # Sin fecha de inicio es un borrador; con una futura, algo programado.
            continue
        hasta = _fecha(t.get("vigente_hasta"))
        if hasta is not None and hasta <= ahora:
            continue                       # ya la reemplazaron
        vigentes.append((desde, t.get("version_id")))
    if not vigentes:
        return None

    gana = max(vigentes, key=lambda x: x[0])[1]
    try:
        return await base.tarifas_envio.find_one({"version_id": gana}, {"_id": 0})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo leer la versión {gana}: {e}")
        return None


# ─── Límites ──────────────────────────────────────────────────────────────

async def limites(db=None) -> dict:
    """Los límites físicos que valen hoy, con lo que falta si no se puede operar.

    Devuelve siempre la misma forma. `disponible` es lo único que la pantalla
    necesita mirar para decidir si muestra el formulario o un cartel.
    """
    activos = []
    for rol in ("brasil", "venezuela"):
        activos += await transportistas_activos(rol, db=db)

    tarifa = await tarifa_vigente(db=db)
    propios = (tarifa or {}).get("limites_propios") or {}
    efectivos = limites_efectivos(activos, propios)
    faltantes = configuracion_incompleta(activos, tarifa)

    return {
        "disponible": not faltantes,
        # Diagnóstico interno. La ruta pública lo reemplaza por un mensaje.
        "faltantes": faltantes,
        "limites": _json_seguro(limites_payload(efectivos)),
        # Quién impone cada límite, por su CÓDIGO. La pantalla puede decir "el
        # transportista TRP-7K2M no despacha más de 100 cm de lado" en vez de una
        # regla anónima que el usuario no puede verificar.
        "impuesto_por": {
            clave: _quien(activos, clave, propios)
            for clave in efectivos
        },
        "tarifa_version": (tarifa or {}).get("version_id"),
        "moneda": (tarifa or {}).get("moneda") or "RIS",
        "prohibidos": (tarifa or {}).get("prohibidos") or CATEGORIAS_PROHIBIDAS_POR_DEFECTO,
        "terminos_version": TERMINOS_VERSION,
        # El minimo de caracteres de la descripcion. Sale acá porque la pantalla
        # lo necesita para avisar ANTES de que alguien complete seis campos, y
        # porque tenerlo escrito en el cliente es como el PR #40 llego a anunciar
        # topes que el servidor no validaba — el mismo error, en el otro sentido.
        "descripcion_min_caracteres": await _minimo_de_descripcion(db=db),
    }


async def _minimo_de_descripcion(db=None) -> int:
    """Cuantos caracteres pide la descripcion del contenido. Nunca lanza.

    El default de codigo y no el de la pantalla: si el bloque `contenido` no se
    puede leer, contestar un numero inventado hace que la pantalla habilite el
    boton y el servidor rechace.
    """
    from services.envios_policy import DESCRIPCION_MIN_CARACTERES as DESCRIPCION_MINIMA
    try:
        from services.envios_config import leer
        contenido = await leer("contenido", db=db) or {}
        valor = int(contenido.get("descripcion_min_caracteres") or DESCRIPCION_MINIMA)
        # El MISMO rango que aplica `validar_descripcion`. Contestar un número
        # que el validador después no acepta es peor que no contestarlo.
        return valor if 3 <= valor <= 200 else DESCRIPCION_MINIMA
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo leer el mínimo de descripción: {e}")
        return DESCRIPCION_MINIMA


def _quien(activos, clave, propios):
    from services.envios_policy import quien_impone
    return quien_impone(activos, clave, propios)


# ─── Catálogo de destinos ─────────────────────────────────────────────────

async def catalogo(db=None, usar_cache: bool = True) -> dict:
    """Transportistas de destino con sus agencias activas, para el formulario.

    Acá SÍ viajan los nombres comerciales: son datos que el super administrador
    cargó y que el usuario tiene que leer para elegir. La regla es que el nombre
    no viva en el código, no que sea secreto.
    """
    if usar_cache:
        en_cache = _cacheado("catalogo")
        if en_cache is not None:
            return en_cache

    transportistas, ok = await _transportistas_de_destino(db=db)
    salida = []
    for t in transportistas:
        agencias, ok_agencias = await _agencias_de(t.get("transportista_id"), db=db)
        ok = ok and ok_agencias
        salida.append({
            "transportista_id": t.get("transportista_id"),
            "codigo": codigo_de(t),
            "nombre": t.get("nombre"),
            "agencias": agencias,
        })

    # Los orígenes viajan acá y no en una ruta propia: el formulario ya pide este
    # catálogo, ya está cacheado, y una ruta más sería una llamada más para
    # pintar la misma pantalla. Las escrituras del panel invalidan el caché, que
    # es lo que hace que una ciudad recién cargada aparezca sin esperar el TTL.
    origenes, ok_origenes = await envios_origenes.listar(db=db)
    ok = ok and ok_origenes

    resultado = {
        "transportistas": salida,
        # Un catálogo VACÍO no es un error y no apaga nada: el usuario escribe su
        # CEP a mano, cotiza igual, y su ciudad queda propuesta. Lo único que se
        # pierde sin catálogo es la referencia del tramo brasileño, que es
        # orientativa y nunca entró en ningún total.
        "origenes": origenes,
        # Sin transportistas de destino no hay a dónde mandar, y la pantalla
        # tiene que decirlo en vez de mostrar un desplegable vacío.
        "disponible": ok and bool(salida) and any(t["agencias"] for t in salida),
        "degradado": not ok,
    }
    # Un resultado degradado NO se cachea. Un hipo de la base durante cinco
    # segundos dejaría "no disponible" pegado cinco minutos para todo el mundo,
    # mucho después de que la base se recuperó.
    if usar_cache and ok:
        _guardar("catalogo", resultado)
    return resultado


async def _agencias_de(transportista_id, db=None) -> tuple[list[dict], bool]:
    """(agencias activas, se_pudo_leer).

    El filtro por `activa` se hace en Python y no en la consulta, por lo mismo
    que explica referencias.py: `{"activa": True}` en Mongo no matchea un
    `activa: 1` ni un `"true"`, y una agencia dada de alta desde el panel
    desaparecería del formulario sin un solo log.
    """
    if not transportista_id:
        return [], True
    try:
        base = await _db(db)
        filas = await base.agencias.find(
            {"transportista_id": transportista_id},
            {"_id": 0, "codigo": 1, "nombre": 1, "estado": 1, "ciudad": 1,
             "direccion": 1, "zona": 1, "activa": 1},
        ).sort("estado", 1).to_list(None)
    except Exception as e:
        logger.warning(f"envios: no se pudieron leer las agencias de {transportista_id}: {e}")
        return [], False
    return [{k: v for k, v in f.items() if k != "activa"}
            for f in filas if _activo({"activo": f.get("activa")})], True


async def _transportistas_de_destino(db=None) -> tuple[list[dict], bool]:
    """Las fichas para el catálogo, CON el nombre comercial.

    No reusa `referencias.transportistas_activos` a propósito: aquella proyección
    excluye `nombre` deliberadamente, porque su módulo no debe hacerlo viajar a
    un log. Acá el nombre es justamente lo que el usuario necesita leer para
    elegir a dónde manda, así que la consulta es otra — y el que la lee sabe qué
    está pidiendo.
    """
    try:
        base = await _db(db)
        filas = await base.transportistas.find(
            {"rol": "venezuela"},
            {"_id": 0, "transportista_id": 1, "codigo": 1, "nombre": 1,
             "orden": 1, "activo": 1},
        ).sort("orden", 1).to_list(None)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el catálogo de transportistas: {e}")
        return [], False
    return [t for t in filas if _activo(t)], True


def _json_seguro(payload: dict) -> dict:
    """Los límites como los quiere el JSON: floats finitos, o None.

    Un límite guardado como "Infinity" llega hasta acá como float('inf'), y
    starlette serializa con allow_nan=False: el ValueError ocurre DESPUÉS de que
    el handler retornó, así que ningún try/except de la ruta lo atrapa y el
    usuario ve un 500 sin traza útil. Un valor no finito es un dato roto, y un
    dato roto es "no hay límite declarado".
    """
    salida = {}
    for clave, valor in (payload or {}).items():
        if valor is None:
            salida[clave] = None
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            salida[clave] = None
            continue
        if numero != numero or numero in (float("inf"), float("-inf")):
            logger.warning(f"envios: el límite {clave} tiene un valor no finito: {valor!r}")
            salida[clave] = None
            continue
        salida[clave] = numero
    return salida
