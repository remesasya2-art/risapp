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

async def tarifa_vigente(db=None, ahora=None) -> dict | None:
    """La versión sin cerrar y YA vigente. Nunca lanza.

    El filtro por fecha no es un detalle: `vigente_desde` existe para poder dejar
    un aumento programado, y sin comparar contra hoy ese aumento rige desde el
    momento en que se guarda. El super administrador cree que programó algo para
    el mes que viene y en realidad lo publicó.

    Sin tarifa el módulo no cotiza, y eso se responde con `disponible: false`,
    no con un 500.
    """
    ahora = ahora or datetime.now(timezone.utc)
    try:
        base = await _db(db)
        candidatas = await base.tarifas_envio.find(
            {"vigente_hasta": None}, {"_id": 0}).sort("vigente_desde", -1).to_list(None)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la tarifa vigente: {e}")
        return None

    vigentes = []
    for t in candidatas or []:
        desde = t.get("vigente_desde")
        if desde is None:
            # Sin fecha de inicio no es una versión publicada, es un borrador.
            continue
        if isinstance(desde, str):
            try:
                desde = datetime.fromisoformat(desde.replace("Z", "+00:00"))
            except ValueError:
                continue
        if not isinstance(desde, datetime):
            continue
        if desde.tzinfo is None:
            desde = desde.replace(tzinfo=timezone.utc)
        if desde <= ahora:
            vigentes.append((desde, t))
    if not vigentes:
        return None
    return max(vigentes, key=lambda x: x[0])[1]


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
    }


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

    resultado = {
        "transportistas": salida,
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
