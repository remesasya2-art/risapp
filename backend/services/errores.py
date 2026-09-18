"""El registro de errores que el super administrador puede ver.

QUE PASABA

    Cuando algo se rompía, el error iba al log de Railway y ahí se quedaba.
    `rastro.py` ya le pone a cada pedido un código que viaja en la respuesta
    y en cada línea del log, y eso sirve para ENCONTRAR un error cuando un
    cliente escribe. Pero nada guardaba los errores, ni había pantalla: el
    super administrador no tenía forma de saber que algo estaba fallando
    hasta que alguien se quejaba.

QUE HACE

    Cada error de servidor —un 500 no previsto, o un 5xx levantado a
    propósito, como el 503 de «no pudimos generar el cobro»— se asienta acá,
    con su rastro, la ruta, quién lo sufrió y desde dónde. Una pestaña del
    panel lo lista, de más nuevo a más viejo, con un resumen de las últimas
    horas arriba.

QUE SE GUARDA, Y QUE NO

    Lista de lo PERMITIDO: rastro, método, ruta, código de estado, tipo de
    la excepción, mensaje, traza, usuario, IP y cuándo. Nada más.

    NUNCA el cuerpo del pedido, ni las cabeceras, ni la consulta. Un pedido
    que falló al entrar trae la contraseña en el cuerpo; uno con sesión trae
    el token en la cabecera. Un registro de errores que guarde eso es la
    colección más peligrosa de la base.

    Y el mensaje se limpia: el texto de una excepción de Mongo trae la cadena
    de conexión con la contraseña adentro; el de una de Mercado Pago, el
    token. Se tachan antes de guardar. No es perfecto —una clave con una
    forma que no se conoce pasa—, pero las formas conocidas no.

NUNCA LEVANTA

    Si asentar falla, queda un ERROR en el log y nada más. El manejador de
    errores es lo último que está de pie cuando todo lo demás se cayó; no
    puede ser él quien tire la respuesta al piso.

SE BORRA SOLO

    Un índice TTL borra cada línea a los 30 días. Un registro de errores que
    crece para siempre termina siendo el problema que quería mostrar.
"""
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLECCION = "errores"
DIAS_QUE_SE_GUARDAN = 30
MAX_MENSAJE = 500
MAX_TRAZA = 4000

# Lo que NO puede quedar escrito en el mensaje ni en la traza.
_SECRETOS = (
    # mongodb://usuario:CONTRASEÑA@host
    (re.compile(r"(mongodb(?:\+srv)?://[^:/\s]+:)[^@\s]+@"), r"\1***@"),
    # Tokens de Mercado Pago
    (re.compile(r"\b(APP_USR|TEST)-[A-Za-z0-9-]{8,}"), r"\1-***"),
    # Cabeceras de autorización pegadas en un mensaje
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    # Cualquier cosa que parezca clave=valor con nombre de secreto
    (re.compile(r"(?i)\b((?:api[_-]?key|secret|password|token|passwd)\s*[=:]\s*)\S+"), r"\1***"),
)


def _limpiar(texto, tope: int) -> str:
    texto = "" if texto is None else str(texto)
    for patron, reemplazo in _SECRETOS:
        texto = patron.sub(reemplazo, texto)
    return texto[:tope]


async def anotar(db, *, rastro, metodo, ruta, status, tipo, mensaje,
                 traza=None, user_id=None, ip=None) -> None:
    """Asienta un error. Nunca levanta."""
    linea = {
        "rastro": str(rastro or "-")[:64],
        "metodo": str(metodo or "")[:10],
        "ruta": str(ruta or "")[:200],
        "status": int(status or 500),
        "tipo": str(tipo or "")[:120],
        "mensaje": _limpiar(mensaje, MAX_MENSAJE),
        "traza": _limpiar(traza, MAX_TRAZA) if traza else None,
        "user_id": str(user_id)[:64] if user_id else None,
        "ip": str(ip)[:64] if ip else None,
        "cuando": datetime.now(timezone.utc),
    }
    try:
        await db[COLECCION].insert_one(linea)
    except Exception as e:                                  # pragma: no cover
        logger.error("errores: no se pudo asentar %s %s (%s): %s",
                     linea["metodo"], linea["ruta"], linea["rastro"], e)


async def preparar_indices(db) -> None:
    """El TTL que los borra a los 30 días, y los índices de la pantalla."""
    await db[COLECCION].create_index(
        "cuando", expireAfterSeconds=DIAS_QUE_SE_GUARDAN * 24 * 3600)
    await db[COLECCION].create_index([("ruta", 1), ("cuando", -1)])
    await db[COLECCION].create_index("rastro")


def _con_zona(linea: dict) -> dict:
    cuando = linea.get("cuando")
    if isinstance(cuando, datetime):
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=timezone.utc)
        linea["cuando"] = cuando.isoformat()
    return linea


async def buscar(db, *, ruta=None, status=None, rastro=None,
                 limite=100, saltar=0) -> dict:
    """Los errores, de más nuevo a más viejo. Sólo lee."""
    filtro = {}
    if ruta:
        filtro["ruta"] = ruta
    if status:
        filtro["status"] = int(status)
    if rastro:
        filtro["rastro"] = rastro
    limite = max(1, min(int(limite), 500))
    # Desempate por `_id`: dos errores en el mismo milisegundo empatan en
    # `cuando`, y sin esto el orden entre ellos queda al azar de la base.
    # El `_id` crece con cada inserción, así que «más nuevo primero» se
    # cumple también dentro del mismo milisegundo.
    cursor = db[COLECCION].find(filtro, {"_id": 0}).sort(
        [("cuando", -1), ("_id", -1)]).skip(max(0, int(saltar))).limit(limite)
    lineas = [_con_zona(x) async for x in cursor]
    return {
        "lineas": lineas,
        "total": await db[COLECCION].count_documents(filtro),
        "limite": limite,
        "saltar": max(0, int(saltar)),
    }


async def resumen(db, *, horas: int = 24) -> dict:
    """Cuántos hubo en las últimas horas, y en qué rutas. Es lo primero que
    se ve al abrir la pestaña: si el número es cero, no hay nada que leer."""
    from datetime import timedelta
    desde = datetime.now(timezone.utc) - timedelta(hours=max(1, int(horas)))
    filtro = {"cuando": {"$gte": desde}}
    por_ruta = {}
    ultimo = None
    async for x in db[COLECCION].find(filtro, {"_id": 0, "ruta": 1, "cuando": 1}):
        por_ruta[x.get("ruta") or "?"] = por_ruta.get(x.get("ruta") or "?", 0) + 1
        c = x.get("cuando")
        if c and (ultimo is None or c > ultimo):
            ultimo = c
    rutas = sorted(({"ruta": r, "cuantos": n} for r, n in por_ruta.items()),
                   key=lambda d: -d["cuantos"])
    return {
        "horas": horas,
        "total": sum(por_ruta.values()),
        "rutas": rutas[:20],
        "ultimo": _con_zona({"cuando": ultimo})["cuando"] if ultimo else None,
    }
