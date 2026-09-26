"""
services/piso_de_peticiones.py — Un techo de pedidos por IP para TODA la API.

PARA QUE

    Sólo frenaban las rutas con `frenar(...)` puesto a mano: entrada,
    recuperación y las de dinero. El historial, el saldo, los avisos y todo
    el panel no tenían tope: un programa podía pedirlos mil veces por
    segundo y lo único que lo paraba era que el servidor se cayera.

DOS TECHOS, Y POR QUE

    · Clientes: lo que no es del panel. Un cliente con la pantalla abierta
      hace 6 pedidos por minuto; esperando un pago o en soporte, hasta 30.
      Trescientos por minuto por IP es diez veces eso: no molesta a una
      persona ni a un wifi compartido, y corta a un programa.
    · Panel (`/api/admin/...`): el personal es poco, conocido y pasa por
      segundo factor, pero SONDEA: una mesa de ayuda abierta son 35 pedidos
      por minuto, y una oficina de cinco detrás de una sola IP, 175. Por eso
      su techo es aparte y mucho más alto.

ARRANCA SOLO AVISANDO, Y ESO NO ES TIMIDEZ

    Los números de arriba salen de leer el código, no de medir tráfico
    real. Un techo mal elegido deja a una oficina entera afuera en el
    primer minuto, y se ve como «la aplicación anda mal», no como «llegaste
    al límite». Así que en modo reporte (el de fábrica) NO se corta nada:
    cada IP que se pasa queda anotada en la pestaña Errores, una vez por
    minuto, con su cuenta. Cuando el registro muestre que sólo se pasan
    programas y no personas, se pasa a cortar desde Configuración, sin
    tocar código. Es el mismo trato que la política de contenido y la
    puerta del borde.

LOS TRES NUMEROS SE LEEN DEL CATALOGO, CON UNA CACHE CORTA

    `services/configuracion.py` no tiene caché a propósito, y con razón: se
    lee de a puñados y en momentos fríos. Esto corre EN CADA PEDIDO, y una
    consulta a Mongo por pedido para decidir si se cuenta el pedido sería
    duplicar el tráfico que se quiere acotar. Se releen cada 30 segundos:
    un cambio desde el panel tarda como mucho eso en aplicarse.

SI EL CONTADOR SE ROMPE, SE DEJA PASAR

    Un techo que no se puede consultar no puede tirar abajo la aplicación
    entera. Queda en el registro, y sigue.
"""
import logging
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from services import configuracion, errores, rastro
from services.ip_cliente import ip_del_cliente

logger = logging.getLogger(__name__)

PREFIJO_DE_LA_API = "/api/"
# El ping de vida de Railway no pasa por el piso. Contarlo exige ir a la base
# —los ajustes, y en producción el contador mismo—, y con Mongo caído cada ping
# esperaba 30 segundos: Railway daba por muerto un servidor que estaba arriba.
# Es lo que terminó de tumbar la página el 25 de septiembre de 2026. El ping no
# toca la base (routes/basic.py), así que no hay nada que proteger contándolo.
SIN_PISO = frozenset({"/api/health"})
PREFIJO_DEL_PANEL = "/api/admin"

ALCANCE_CLIENTES = "piso.clientes"
ALCANCE_PANEL = "piso.panel"

AJUSTE_CLIENTES = "piso_peticiones_clientes_por_ip_por_minuto"
AJUSTE_PANEL = "piso_peticiones_panel_por_ip_por_minuto"
AJUSTE_EXIGIR = "piso_peticiones_exigir"

CADA_CUANTO_SE_RELEE = 30           # segundos
TIPO_DEL_AVISO = "PisoDePeticiones"
MENSAJE_DEL_429 = "Demasiados pedidos seguidos. Esperá un minuto y volvé a probar."

_ajustes = {"leido_en": 0.0, "clientes": None, "panel": None, "exigir": False}
# (ip, alcance, minuto) ya avisados, para no llenar Errores con el mismo
# aviso cien veces en el mismo minuto.
_avisados: dict = {}


def _olvidar() -> None:
    """Para los tests: los ajustes se releen y los avisos arrancan de cero."""
    _ajustes.update({"leido_en": 0.0, "clientes": None, "panel": None, "exigir": False})
    _avisados.clear()


def _defectos():
    return {
        "clientes": configuracion.AJUSTES[AJUSTE_CLIENTES].defecto,
        "panel": configuracion.AJUSTES[AJUSTE_PANEL].defecto,
        "exigir": False,
    }


async def ajustes(db, ahora=None) -> dict:
    """Los tres números, releídos cada 30 segundos. Nunca levanta."""
    ahora = time.monotonic() if ahora is None else ahora
    if _ajustes["clientes"] is not None and ahora - _ajustes["leido_en"] < CADA_CUANTO_SE_RELEE:
        return _ajustes
    try:
        clientes = int(await configuracion.leer(db, AJUSTE_CLIENTES))
        panel = int(await configuracion.leer(db, AJUSTE_PANEL))
        exigir = int(await configuracion.leer(db, AJUSTE_EXIGIR)) == 1
    except Exception as e:
        logger.warning("piso de peticiones: no se pudieron leer los ajustes (%s)", e)
        if _ajustes["clientes"] is None:
            _ajustes.update(_defectos())
    else:
        _ajustes.update({"clientes": clientes, "panel": panel, "exigir": exigir})
    _ajustes["leido_en"] = ahora
    return _ajustes


def es_del_panel(camino: str) -> bool:
    return camino == PREFIJO_DEL_PANEL or camino.startswith(PREFIJO_DEL_PANEL + "/")


async def _se_paso(ip: str, alcance: str, por_minuto: int) -> bool:
    """True si esta IP ya gastó su cupo del minuto. Si el contador falla,
    False: ver el encabezado."""
    from limits import parse
    from routes.security_2fa import el_contador
    try:
        return not await el_contador().hit(parse(f"{por_minuto}/minute"), ip, alcance)
    except Exception as e:
        logger.warning("piso de peticiones: el contador no respondió (%s); se deja pasar", e)
        return False


async def _avisar(db, *, ip: str, alcance: str, por_minuto: int, metodo: str, camino: str) -> bool:
    """Una línea en Errores por IP, alcance y minuto. Devuelve si se anotó."""
    minuto = int(time.time() // 60)
    clave = (ip, alcance, minuto)
    if clave in _avisados:
        return False
    # Se olvidan los minutos viejos para que esto no crezca sin fin.
    for vieja in [k for k in _avisados if k[2] < minuto - 1]:
        _avisados.pop(vieja, None)
    _avisados[clave] = True
    await errores.anotar(
        db, rastro=rastro.actual(), metodo=metodo, ruta=camino, status=429,
        tipo=TIPO_DEL_AVISO,
        mensaje=(f"La IP {ip} superó {por_minuto} pedidos por minuto en {alcance}. "
                 "Modo reporte: no se cortó nada. Si esto es una persona, subí el "
                 "número en Configuración; si es un programa, pasá a cortar."),
        ip=ip)
    return True


class Piso:
    """El middleware. ASGI pelado, como `rastro.Rastro`, y por lo mismo:
    corre en todos los pedidos y no puede permitirse armar respuestas de
    más. Sólo mira `/api/...`; lo estático no se cuenta."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        camino = scope.get("path", "")
        if scope["type"] != "http" or not camino.startswith(PREFIJO_DE_LA_API) or camino in SIN_PISO:
            await self.app(scope, receive, send)
            return
        from database import db

        metodo = scope.get("method", "")
        ip = ip_del_cliente(Request(scope))
        a = await ajustes(db)
        alcance, techo = ((ALCANCE_PANEL, a["panel"]) if es_del_panel(camino)
                          else (ALCANCE_CLIENTES, a["clientes"]))

        if await _se_paso(ip, alcance, techo):
            if a["exigir"]:
                logger.warning("Piso %s/min alcanzado por %s en %s: cortado", techo, ip, alcance)
                respuesta = JSONResponse(
                    status_code=429,
                    content={"detail": MENSAJE_DEL_429, "request_id": rastro.actual()})
                await respuesta(scope, receive, send)
                return
            await _avisar(db, ip=ip, alcance=alcance, por_minuto=techo,
                          metodo=metodo, camino=camino)
        await self.app(scope, receive, send)
