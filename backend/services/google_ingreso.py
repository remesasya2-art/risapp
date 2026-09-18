"""
services/google_ingreso.py — Verificar que una credencial de Google es de
verdad, y quedarse sólo con lo que hace falta.

COMO FUNCIONA, EN DOS LINEAS

    El botón de Google, en el navegador, le entrega a la aplicación un token
    firmado por Google que dice «este correo es de esta persona y lo
    confirmé yo». Acá se comprueba la firma contra las claves públicas de
    Google, que el token sea para ESTA aplicación (el id de cliente) y que
    no haya vencido. Eso lo hace la librería oficial; lo que se agrega
    encima son las comprobaciones que la librería no hace por nosotros.

LO QUE LA LIBRERIA NO MIRA Y ACA SI

    · `email_verified`. Google puede emitir un token para una cuenta cuyo
      correo NO confirmó (pasa con algunos dominios de empresa). Sin esta
      guarda, quien controle un dominio arma un token con el correo de otro
      y entra a su cuenta.
    · El emisor. Sólo `accounts.google.com`, con y sin https.
    · La audiencia, otra vez: la librería la comprueba, pero se vuelve a
      mirar acá para que una versión futura que la relaje no abra la puerta.

EL ID DE CLIENTE ES PUBLICO Y NO HAY SECRETO

    Con este flujo la aplicación no guarda ningún secreto de Google: el id
    de cliente va en el HTML de cualquier sitio que use el botón, y lo que
    protege la puerta es la firma del token, no un secreto nuestro. Por eso
    se configura con UNA variable (`GOOGLE_CLIENT_ID`) y se le sirve al
    navegador por una ruta pública. Sin la variable, no hay botón y la
    puerta contesta 503: nada se rompe, sólo falta la función.
"""
import logging
import os

import requests as _requests
from cachecontrol import CacheControl
from google.auth.transport import requests as _google_requests
from google.oauth2 import id_token as _id_token

logger = logging.getLogger(__name__)

EMISORES = ("accounts.google.com", "https://accounts.google.com")

# Un token de Google mide unos 1000 caracteres. Más de esto no es un token.
TOPE_DE_LA_CREDENCIAL = 4096


class CredencialInvalida(ValueError):
    """Con el motivo adentro, para el registro. A la persona se le dice
    siempre lo mismo: no hay por qué contarle a quien prueba tokens qué
    comprobación falló."""


def id_de_cliente() -> str:
    """Se lee cada vez y no al importar: así el test la cambia sin
    reimportar, y así una variable puesta en caliente cuenta."""
    return (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()


def configurado() -> bool:
    return bool(id_de_cliente())


_transporte = None


def _el_transporte():
    """Con caché HTTP: las claves públicas de Google cambian cada tanto y
    traen cabeceras de caché. Sin esto, cada ingreso es un viaje a Google."""
    global _transporte
    if _transporte is None:
        _transporte = _google_requests.Request(session=CacheControl(_requests.Session()))
    return _transporte


def leer_las_afirmaciones(credencial: str) -> dict:
    """Firma, vencimiento y audiencia: lo hace la librería oficial. Es lo
    único que habla con Google, y lo único que los tests reemplazan."""
    return _id_token.verify_oauth2_token(credencial, _el_transporte(), id_de_cliente())


def verificar_credencial(credencial) -> dict:
    """Devuelve `{"email", "sub", "nombre"}` o levanta `CredencialInvalida`.

    Corre sincrónica (habla con Google por HTTP); la ruta la manda a un hilo.
    """
    if not configurado():
        raise CredencialInvalida("sin id de cliente")
    if not isinstance(credencial, str) or not credencial or len(credencial) > TOPE_DE_LA_CREDENCIAL:
        raise CredencialInvalida("credencial vacía o demasiado larga")
    try:
        afirmaciones = leer_las_afirmaciones(credencial)
    except Exception as e:
        raise CredencialInvalida(f"Google no la reconoció: {type(e).__name__}")
    if not isinstance(afirmaciones, dict):
        raise CredencialInvalida("respuesta rara de la librería")
    if afirmaciones.get("iss") not in EMISORES:
        raise CredencialInvalida("emisor desconocido")
    if afirmaciones.get("aud") != id_de_cliente():
        raise CredencialInvalida("el token es para otra aplicación")
    if afirmaciones.get("email_verified") is not True:
        raise CredencialInvalida("Google no confirmó el correo")
    email = str(afirmaciones.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise CredencialInvalida("sin correo")
    sub = str(afirmaciones.get("sub") or "").strip()
    if not sub:
        raise CredencialInvalida("sin identificador")
    nombre = str(afirmaciones.get("name") or "").strip()[:100]
    return {"email": email, "sub": sub, "nombre": nombre}
