"""
Qué se acepta como «una imagen» cuando llega en el cuerpo de un pedido.

DE QUE SE TRATA

    Los documentos del KYC, los comprobantes de recarga y los de retiro llegan
    como TEXTO adentro del JSON: normalmente un `data:image/jpeg;base64,…` que
    arma el navegador. El servidor los guardaba tal cual, sin mirarlos, y las
    pantallas del panel los ponían después en un `<a href>` o en un
    `window.open`.

    O sea que el campo era, en la práctica, texto libre elegido por quien sube
    el archivo, y quien lo abría era un administrador. Un
    `javascript:fetch('/api/admin/…')` guardado ahí se ejecutaba en la sesión
    del que estaba revisando el KYC.

    El filtro del navegador (`frontend/src/utils/urlDeArchivo.js`) ya no deja
    abrir eso. Esto es la otra mitad: que no se guarde. Las dos hacen falta —
    el filtro protege lo que YA está guardado, y esto evita que entre más.

QUE SE ACEPTA

    1. `data:image/<tipo>;base64,…` con un tipo que no ejecuta nada. SVG no:
       lleva scripts adentro y el navegador los corre.
    2. Una ruta nuestra (`/api/media/…`, `/api/static/…`).
    3. Una URL `https://`.

    Nada más. En particular, nada que empiece con un esquema que no sea ése,
    escrito como esté escrito: los espacios y los caracteres de control se
    sacan antes de mirar, porque el navegador también los ignora.

POR QUE UN TOPE DE TAMANO

    Un `data:` de base64 viaja adentro del documento de Mongo. Sin tope, una
    foto de 40 MB entra hasta chocar contra el límite de 16 MB del documento, y
    lo que se rompe no es la subida: es la lectura de esa colección, para todos,
    desde ese momento.

    El tope está en bytes del texto recibido, que es lo que efectivamente se va
    a guardar. El `content-length` lo elige el cliente.

LO QUE ESTO NO HACE

    No mira los bytes de la imagen. Un `data:image/png;base64,` con basura
    adentro pasa: se guarda algo que ningún visor va a poder abrir. Mirar la
    firma real de los bytes ya lo hace `services/envios_archivos.py`, para las
    fotos de los envíos, que es el camino nuevo. Para estos campos —que son el
    camino viejo, con base64 adentro del documento— acá se corta lo que puede
    EJECUTARSE, que es lo que hace daño; lo que no se puede ver se nota solo, al
    intentar verlo.
"""
import logging
import re

logger = logging.getLogger(__name__)

# 8 MB de texto. Una foto de teléfono en JPEG ronda 2-4 MB, y en base64 crece un
# tercio: con 8 se acepta cualquier foto razonable y se corta antes de acercarse
# al límite de 16 MB que tiene un documento de Mongo.
TOPE_BYTES = 8 * 1024 * 1024

# Los mismos que acepta el navegador en `frontend/src/utils/urlDeArchivo.js`.
# SVG queda afuera en los dos lados, y por el mismo motivo.
TIPOS_PERMITIDOS = {"png", "jpeg", "jpg", "gif", "webp", "bmp", "avif"}

_CONTROLES = re.compile("[\u0000-\u0020\u007f]")
_DATA = re.compile(r"^data:image/([a-z0-9.+-]+)[;,]", re.IGNORECASE)


class ImagenInvalida(ValueError):
    """Lo que llegó no se puede guardar como imagen. El mensaje va al usuario."""


def _sin_lo_que_el_navegador_ignora(valor: str) -> str:
    return _CONTROLES.sub("", valor)


def es_imagen_aceptable(valor) -> bool:
    """`True` si se puede guardar. No levanta nunca: para filtrar listas."""
    try:
        limpiar_imagen(valor)
        return True
    except ImagenInvalida:
        return False


def limpiar_imagen(valor, *, campo: str = "la imagen") -> str:
    """Devuelve el valor tal como llegó si se puede guardar; si no, levanta.

    Se devuelve el ORIGINAL, no el normalizado: sacarle caracteres a un base64
    válido lo rompería. La normalización es sólo para decidir.
    """
    if not isinstance(valor, str):
        raise ImagenInvalida(f"{campo}: no llegó una imagen.")

    if len(valor.encode("utf-8")) > TOPE_BYTES:
        raise ImagenInvalida(
            f"{campo} pesa demasiado. Sacá la foto con menos resolución o "
            "mandá una más liviana.")

    limpio = _sin_lo_que_el_navegador_ignora(valor)
    if not limpio:
        raise ImagenInvalida(f"{campo}: no llegó una imagen.")

    m = _DATA.match(limpio)
    if m:
        if m.group(1).lower() not in TIPOS_PERMITIDOS:
            raise ImagenInvalida(
                f"{campo}: ese formato no se acepta. Mandá una foto en JPG o PNG.")
        return valor

    # Una ruta nuestra. `//` no: eso es otro sitio con nuestro mismo protocolo.
    if limpio.startswith("/") and not limpio.startswith("//"):
        return valor

    if limpio.lower().startswith("https://"):
        return valor

    # Acá cae `javascript:`, `data:text/html`, `file:`, `vbscript:` y cualquier
    # otro esquema. Se registra porque no es un error de tipeo de nadie: alguien
    # armó el pedido a mano.
    logger.warning("imagen_recibida: se rechazó un valor con esquema no permitido "
                   "en %s (empieza con %r)", campo, limpio[:24])
    raise ImagenInvalida(f"{campo}: la dirección no se puede abrir. Subí la foto de nuevo.")


def limpiar_imagen_opcional(valor, *, campo: str = "la imagen"):
    """Igual, pero un vacío es un vacío legítimo y devuelve `None`."""
    if valor is None:
        return None
    if isinstance(valor, str) and not _sin_lo_que_el_navegador_ignora(valor):
        return None
    return limpiar_imagen(valor, campo=campo)


def limpiar_lista(valores, *, campo: str = "los comprobantes"):
    """Una lista de imágenes. Si alguna no sirve, no entra NINGUNA.

    Guardar tres de cuatro deja al operador mirando un juego incompleto sin
    saberlo, que es peor que un error claro.
    """
    if valores is None:
        return None
    if not isinstance(valores, (list, tuple)):
        raise ImagenInvalida(f"{campo}: no llegó una lista.")
    return [limpiar_imagen(v, campo=campo) for v in valores]
