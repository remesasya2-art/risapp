"""
routes/media.py — El proxy que trae una foto de Twilio.

POR QUE EXISTE

    Las fotos que llegan por WhatsApp viven en Twilio y hay que autenticarse
    para bajarlas. El navegador no puede: las credenciales no salen del
    servidor. Así que la pantalla pide `/api/media/twilio/<path>` y el servidor
    va a buscarla con las credenciales puestas.

EL AGUJERO QUE ESTE ARCHIVO TENIA

    El `<path>` iba directo a la URL, sin mirarlo:

        twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{path}"

    `path:path` de FastAPI se traga las barras, así que el pedido lo escribía
    entero quien llamaba. Cualquier usuario con sesión podía apuntar el proxy a
    OTRA parte de la API de Twilio y el servidor le ponía nuestras credenciales:

        /api/media/twilio/AC.../Messages.json
            → los cuerpos de TODOS los SMS de la cuenta. Ahí adentro van los
              códigos de verificación que la aplicación le manda a la gente.
        /api/media/twilio/AC.../Recordings.json
        /api/media/twilio/AC.../IncomingPhoneNumbers.json

    No hacía falta romper nada: la ruta se lo daba armado.

    Y con `follow_redirects=True`, la respuesta de Twilio podía mandar el
    pedido a otro lado con la cabecera de autenticación todavía puesta.

COMO SE CIERRA

    1. EL PATH TIENE UNA SOLA FORMA POSIBLE y se exige entera. Los
       identificadores de Twilio son un prefijo de dos letras y 32 dígitos
       hexadecimales: se piden así, con un ancla al principio y otra al final.
       Nada de «empieza con AC».
    2. LA CUENTA TIENE QUE SER LA NUESTRA. Aunque el formato calce, si el SID
       no es el de esta aplicación no se pide.
    3. LOS REDIRECCIONAMIENTOS NO SE SIGUEN CON LAS CREDENCIALES PUESTAS. Twilio
       contesta con un salto al CDN donde están los bytes; ese salto se sigue a
       mano, UNA sola vez, sin autenticación y sólo hacia los dominios donde
       Twilio guarda los medios.
    4. HAY UN TOPE DE BYTES. Sin tope, la respuesta de un tercero decide cuánta
       memoria usa nuestro servidor.

LO QUE ESTO NO RESUELVE

    Cualquiera con sesión puede pedir el medio de cualquier otro si conoce los
    tres identificadores. No son adivinables —34 caracteres cada uno— así que el
    secreto es el identificador mismo. Se deja anotado porque es una decisión, no
    un descuido: atar cada medio a su dueño requiere guardar esa relación, que
    hoy no existe.
"""
import logging
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from models.user import User
from routes.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/media", tags=["media"])

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

# La única forma que tiene un medio de Twilio. `AC` la cuenta, `MM` el mensaje,
# `ME` el medio; 32 hexadecimales cada uno. Anclado en las dos puntas: sin el
# `$` final, «AC…/Media/ME…/../../Messages.json» calzaría igual.
FORMA_DEL_MEDIO = re.compile(
    r"^(AC[0-9a-fA-F]{32})/Messages/MM[0-9a-fA-F]{32}/Media/ME[0-9a-fA-F]{32}$")

# A dónde puede saltar Twilio con los bytes. Se compara por sufijo de dominio,
# con el punto adelante, para que `evil-twiliocdn.com` no cuente como uno.
DOMINIOS_DE_MEDIOS = (".twiliocdn.com", ".twilio.com", ".amazonaws.com")

# 25 MB. Un MMS de Twilio no llega ni cerca; el tope existe para que la
# respuesta de un tercero no decida cuánta memoria usa este proceso.
TOPE_BYTES = 25 * 1024 * 1024


def _es_dominio_de_medios(url: str) -> bool:
    try:
        partes = httpx.URL(url)
    except Exception:
        return False
    if partes.scheme != "https":
        return False
    host = (partes.host or "").lower()
    return any(host == d.lstrip(".") or host.endswith(d) for d in DOMINIOS_DE_MEDIOS)


async def _traer(client: httpx.AsyncClient, url: str, auth):
    """Un pedido, sin seguir saltos. Los saltos los decide quien llama."""
    return await client.get(url, auth=auth, follow_redirects=False, timeout=30.0)


def url_de_medio(valor: str):
    """La URL de Twilio de la que se pueden bajar estos bytes, o `None`.

    Acepta las dos formas que hay guardadas en la base: la ruta de nuestro proxy
    y la URL completa de Twilio. Las dos pasan por la MISMA validación de forma
    y de cuenta.

    Existe como función porque hay dos lugares que bajan medios —esta ruta y la
    migración de `admin.py`— y el segundo comprobaba el destino con
    `"api.twilio.com" in url`. Eso es una subcadena, no un dominio: la URL
    `https://cualquier-cosa.example/?x=api.twilio.com` la pasa, y ese pedido
    salía con nuestro usuario y contraseña de Twilio adentro. Peor todavía,
    esos valores venían de un campo que hasta ahora nadie validaba al guardar.
    """
    if not valor or not isinstance(valor, str):
        return None

    texto = valor.strip()
    for prefijo in ("/api/media/twilio/",
                    "https://api.twilio.com/2010-04-01/Accounts/"):
        if texto.startswith(prefijo):
            path = texto[len(prefijo):]
            break
    else:
        return None

    calza = FORMA_DEL_MEDIO.match(path)
    if not calza or calza.group(1) != TWILIO_ACCOUNT_SID:
        return None
    return f"https://api.twilio.com/2010-04-01/Accounts/{path}"


async def bajar_medio(client: httpx.AsyncClient, url: str):
    """Los bytes y su tipo, o `None` si no se pudieron traer.

    `url` tiene que venir de `url_de_medio()`. El salto al CDN se sigue UNA vez,
    sin las credenciales y sólo a los dominios donde Twilio guarda los medios:
    seguirlo con la cabecera puesta es entregarle nuestro usuario y contraseña a
    donde sea que apunte el `Location`.
    """
    respuesta = await _traer(client, url, (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))

    if respuesta.status_code in (301, 302, 303, 307, 308):
        destino = respuesta.headers.get("location") or ""
        if not _es_dominio_de_medios(destino):
            logger.error("media: Twilio redirigió a un dominio inesperado")
            return None
        respuesta = await _traer(client, destino, None)

    if respuesta.status_code != 200:
        logger.error("media: Twilio contestó %s", respuesta.status_code)
        return None

    contenido = respuesta.content
    if len(contenido) > TOPE_BYTES:
        logger.error("media: la respuesta pasó el tope de %d bytes", TOPE_BYTES)
        return None

    # El `content-type` lo elige el otro lado, y con él se decide cómo
    # interpreta el navegador estos bytes. Un `text/html` acá es una página que
    # corre en nuestro origen; se acepta sólo lo que puede ser una foto y, si no
    # calza, se manda como descarga.
    tipo = (respuesta.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not tipo.startswith("image/") or tipo == "image/svg+xml":
        tipo = "application/octet-stream"

    return contenido, tipo


@router.get("/twilio/{path:path}")
async def proxy_twilio_media(path: str, current_user: User = Depends(get_current_user)):
    """Trae una foto de Twilio con nuestras credenciales y la devuelve."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured")

    calza = FORMA_DEL_MEDIO.match(path or "")
    if not calza:
        # No se dice qué falló: quien manda esto está probando qué acepta.
        logger.warning("media: se rechazó un path que no es un medio (%r) — usuario %s",
                       (path or "")[:120], getattr(current_user, "user_id", "?"))
        raise HTTPException(status_code=404, detail="Media not found")

    if calza.group(1) != TWILIO_ACCOUNT_SID:
        logger.warning("media: se pidió un medio de otra cuenta de Twilio — usuario %s",
                       getattr(current_user, "user_id", "?"))
        raise HTTPException(status_code=404, detail="Media not found")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{path}"

    try:
        async with httpx.AsyncClient() as client:
            bajado = await bajar_medio(client, url)
            if bajado is None:
                raise HTTPException(status_code=404, detail="Media not found")
            contenido, tipo = bajado

            return Response(
                content=contenido,
                media_type=tipo,
                headers={
                    "Cache-Control": "private, max-age=86400",
                    # Que el navegador no adivine el tipo por los bytes y
                    # termine ejecutando lo que le mandamos como imagen.
                    "X-Content-Type-Options": "nosniff",
                },
            )

    except httpx.RequestError as e:
        logger.error(f"Error fetching Twilio media: {e}")
        raise HTTPException(status_code=500, detail="Error fetching media")


def convert_twilio_url_to_proxy(url: str, base_url: str = "") -> str:
    """De la URL de Twilio a la nuestra.

    Entra: https://api.twilio.com/2010-04-01/Accounts/AC…/Messages/MM…/Media/ME…
    Sale:  /api/media/twilio/AC…/Messages/MM…/Media/ME…

    Se exige la forma completa, la misma que exige la ruta. Antes alcanzaba con
    «/Accounts/AC» seguido de cualquier cosa, así que esta función podía fabricar
    una dirección que la ruta después rechaza — o, peor, aceptaba.
    """
    if not url:
        return url

    m = re.search(r"/Accounts/(AC[0-9a-fA-F]{32}/Messages/MM[0-9a-fA-F]{32}"
                  r"/Media/ME[0-9a-fA-F]{32})(?:[?#]|$)", url)
    if m:
        return f"{base_url}/api/media/twilio/{m.group(1)}"

    return url
