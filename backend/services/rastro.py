"""
services/rastro.py — El número que une un error con su línea en el registro.

EL PROBLEMA, EN UNA ESCENA

    Alguien escribe a soporte: «me dio error al recargar, como a las tres».
    Del otro lado hay un registro con miles de líneas por minuto y ninguna
    forma de saber cuál es la suya. Se termina adivinando por la hora, o
    pidiéndole que lo intente de nuevo mientras alguien mira.

    Con un rastro, esa conversación es: «pasame el código que te mostró» y una
    búsqueda.

COMO FUNCIONA

    A cada pedido se le pone un rastro corto. Viaja en tres lugares:

      · en la cabecera `X-Request-ID` de la respuesta, para quien integra;
      · en TODA línea de registro que ese pedido produzca, sin que nadie
        tenga que acordarse de agregarlo;
      · en el cuerpo de un error 500, que es donde el usuario está trabado y
        necesita algo que decirle a soporte.

    Lo de «sin que nadie tenga que acordarse» es la parte que lo hace servir:
    se apoya en un `ContextVar`, que en asyncio acompaña a la tarea que atiende
    el pedido. Un `logger.info` escrito hace dos años, adentro de un servicio
    que no sabe que existe este módulo, sale con su rastro igual.

SI VIENE DE AFUERA, SE LIMPIA — Y ESTO NO ES UN DETALLE

    Si el pedido ya trae `X-Request-ID`, se respeta: así el rastro cruza desde
    el sistema de quien llama y se puede seguir de punta a punta.

    Pero esa cabecera **la escribe quien hace el pedido**, y termina en cada
    línea del registro. Sin limpiarla, un salto de línea puesto a propósito
    parte la línea en dos y la segunda mitad se lee después como una línea de
    registro más, con la forma que quiera quien la mandó. Es el mismo agujero
    que se cerró en el buzón de avisos del CSP.

    Así que sólo pasan letras, números, punto, guion y guion bajo, y como mucho
    64 caracteres. Cualquier otra cosa se descarta y se genera uno nuestro.
"""
import contextvars
import logging
import re
import uuid

# El valor cuando no hay pedido: una tarea de fondo, el arranque, un test.
SIN_PEDIDO = "-"

CABECERA = "X-Request-ID"

# Lo único que se acepta de afuera. Ver el encabezado.
_LIMPIO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_EL_RASTRO: contextvars.ContextVar[str] = contextvars.ContextVar(
    "rastro_del_pedido", default=SIN_PEDIDO)


def nuevo() -> str:
    """Un rastro nuevo. Corto a propósito: alguien lo va a leer por teléfono."""
    return uuid.uuid4().hex[:12]


def limpiar(valor) -> str:
    """El rastro que vino de afuera, o uno nuestro si no sirve."""
    if isinstance(valor, str) and _LIMPIO.match(valor):
        return valor
    return nuevo()


def actual() -> str:
    """El rastro del pedido que se está atendiendo."""
    return _EL_RASTRO.get()


def poner(valor: str):
    """Deja el rastro puesto para esta tarea. Devuelve el testigo para sacarlo."""
    return _EL_RASTRO.set(valor)


def sacar(testigo) -> None:
    _EL_RASTRO.reset(testigo)


class _Filtro(logging.Filter):
    """Le agrega el rastro a cada línea, venga de donde venga."""

    def filter(self, record):
        record.rastro = actual()
        return True


# El formato viejo era el de `basicConfig`: «NIVEL:modulo:mensaje». Se le agrega
# el rastro adelante y se deja el resto igual, para que las búsquedas que ya se
# hacen sobre el texto del mensaje sigan funcionando.
FORMATO = "%(levelname)s:[%(rastro)s]:%(name)s:%(message)s"


def configurar_el_registro() -> None:
    """Pone el rastro en todas las líneas. Se llama una vez, al arrancar.

    NO LEVANTA NUNCA. Un registro sin rastro es peor que uno con rastro, pero
    una aplicación que no arranca por el formato del log es muchísimo peor.
    """
    try:
        filtro = _Filtro()
        formato = logging.Formatter(FORMATO)
        for manejador in logging.getLogger().handlers:
            manejador.setFormatter(formato)
            manejador.addFilter(filtro)
    except Exception:                                     # pragma: no cover
        logging.getLogger(__name__).warning(
            "no se pudo poner el rastro en el registro")


class Rastro:
    """El middleware. Le pone su rastro a cada pedido y lo devuelve en la cabecera.

    VA REGISTRADO EL ULTIMO, Y ESO ES LO QUE LO PONE PRIMERO

        Starlette envuelve al revés: `add_middleware` inserta al principio de
        la lista, así que el último registrado queda por fuera de todos. Este
        tiene que ser el más externo para que hasta un pedido que rechaza el
        tope de cuerpo —o la puerta del borde— salga con rastro. Justamente
        los rechazados son los que después hay que poder encontrar.

    ES ASGI PELADO Y NO `@app.middleware("http")`

        El decorador arma un `Request` y una `Response` completos por pedido.
        Esto corre en TODOS, incluidos los que otro middleware va a cortar, así
        que hace lo mínimo: leer una cabecera y escribir otra.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        de_afuera = None
        for nombre, valor in scope.get("headers") or []:
            if nombre.lower() == CABECERA.lower().encode():
                de_afuera = valor.decode("latin-1", "replace")
                break

        rastro = limpiar(de_afuera)
        testigo = poner(rastro)

        async def mandar(evento):
            if evento["type"] == "http.response.start":
                cabeceras = list(evento.get("headers") or [])
                cabeceras.append((CABECERA.lower().encode(), rastro.encode()))
                evento = {**evento, "headers": cabeceras}
            await send(evento)

        try:
            await self.app(scope, receive, mandar)
        finally:
            sacar(testigo)
