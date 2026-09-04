"""
Un tope para el tamaño del cuerpo de un pedido.

QUE PASABA SIN ESTO

    Nada limitaba cuánto se podía mandar. Un solo pedido con un cuerpo de varios
    gigabytes se leía entero en memoria antes de que ninguna ruta lo mirara, y
    el proceso se quedaba sin memoria. No hace falta ninguna credencial: la
    validación de la ruta corre DESPUES de que FastAPI ya armó el cuerpo.

    Es la clase de falla que no se ve en los tests ni en el uso normal, y que
    tumba la aplicación entera con una línea de `curl`.

POR QUE NO ALCANZA CON MIRAR `Content-Length`

    Lo manda el cliente. Un pedido con `Transfer-Encoding: chunked` no lo lleva,
    y uno que miente lo declara chico y manda grande. Así que se hacen las dos
    cosas: se rechaza temprano al que declara de más —para no leer nada— y se
    CUENTA lo que efectivamente va llegando, cortando en cuanto pasa el tope.

    El conteo es lo que protege de verdad. El `Content-Length` sólo ahorra
    trabajo.

DE CUANTO ES EL TOPE

    El pedido más grande que hace la aplicación es el envío del KYC: cuatro
    fotos en base64, cada una hasta 8 MB (`services/imagen_recibida.py`). Con
    40 MB entra con margen y se corta muy por debajo de lo que hace daño.

    `TOPE_CUERPO_MB` lo cambia sin tocar el código.

LO QUE ESTO NO ES

    No es una defensa contra alguien que abre mil conexiones a la vez: eso se
    para más afuera, en el proxy. Es el piso: que un pedido solo no pueda pedir
    memoria sin límite.
"""
import logging
import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def _tope() -> int:
    try:
        mb = int(os.environ.get("TOPE_CUERPO_MB", "40"))
    except (TypeError, ValueError):
        mb = 40
    return max(1, mb) * 1024 * 1024


class LimiteDeCuerpo:
    """Middleware ASGI que corta un pedido cuyo cuerpo pasa el tope.

    Va en ASGI y no en `@app.middleware("http")` porque tiene que meterse ANTES
    de que se arme el cuerpo. Un middleware HTTP recibe el `Request` ya
    construido: para entonces la memoria ya se pidió.
    """

    def __init__(self, app: ASGIApp, tope: int | None = None):
        self.app = app
        self.tope = tope if tope is not None else _tope()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declarado = self._declarado(scope)
        if declarado is not None and declarado > self.tope:
            # Dice de entrada que trae más de lo permitido: se corta sin leer.
            await self._demasiado_grande(send)
            return

        leidos = 0
        excedido = False

        async def contando() -> Message:
            nonlocal leidos, excedido
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                leidos += len(mensaje.get("body", b"") or b"")
                if leidos > self.tope:
                    excedido = True
                    # Se corta el cuerpo acá. La ruta ve un pedido incompleto y
                    # falla sola; lo importante es que no se siga leyendo.
                    return {"type": "http.disconnect"}
            return mensaje

        async def midiendo(mensaje: Message) -> None:
            if excedido and mensaje["type"] == "http.response.start":
                await self._demasiado_grande(send)
                return
            if excedido and mensaje["type"] == "http.response.body":
                return
            await send(mensaje)

        await self.app(scope, contando, midiendo)

    def _declarado(self, scope: Scope):
        for nombre, valor in scope.get("headers") or []:
            if nombre.lower() == b"content-length":
                try:
                    return int(valor)
                except (TypeError, ValueError):
                    return None
        return None

    async def _demasiado_grande(self, send: Send) -> None:
        logger.warning("limite_de_cuerpo: se rechazó un pedido de más de %d bytes",
                       self.tope)
        cuerpo = b'{"detail":"El archivo es demasiado grande."}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(cuerpo)).encode())],
        })
        await send({"type": "http.response.body", "body": cuerpo})
