"""
services/correo.py — La única puerta por la que sale un correo.

EL PROBLEMA QUE RESUELVE: EL CORREO FRENABA LA APLICACION ENTERA

    `resend.Emails.send()` es una llamada que ESPERA: abre una conexión a un
    servicio ajeno y se queda ahí hasta que contesta. Estaba metida dentro de
    funciones `async`, que son las que atienden los pedidos.

    En Python, una espera de ésas dentro de código `async` no para sólo a quien
    la hizo: para el hilo entero. Mientras salía un correo, el servidor NO
    ATENDIA A NADIE. Y uno de los cinco lugares era el inicio de sesión, así
    que cada vez que alguien entraba, todos los demás esperaban a Resend.

    Acá se manda en OTRO HILO (`asyncio.to_thread`). El que atiende queda libre
    para seguir contestando mientras el correo viaja.

DOS FORMAS DE MANDAR, Y NO SON LA MISMA

    `enviar` espera la respuesta y dice si salió. Es para cuando la pantalla
    necesita saberlo: el código de verificación del registro, sin ir más lejos,
    porque si no salió hay que decírselo a quien se está registrando.

    `en_segundo_plano` no espera. Es para la cortesía: «entraste a tu cuenta»,
    «se movió tu saldo». El aviso ya quedó guardado adentro de la aplicación;
    que el correo tarde un segundo no puede ser un segundo más de ruedita para
    quien acaba de operar.

UN SOLO REMITENTE

    Había TRES valores por omisión distintos, en tres archivos:

        config.py                 FROM_EMAIL    -> noreply@example.com
        services/email_notifications.py  SENDER_EMAIL  -> notificaciones@risapp.com
        server.py                 SENDER_EMAIL  -> noreply@risappbr.com

    El del medio apunta a un dominio que no es de la empresa. Si esa variable
    faltaba, los correos de seguridad salían desde ahí, Resend los rechazaba, y
    el error se tragaba en silencio: la función devolvía «no se envió» y nadie
    miraba.

    Acá se decide una sola vez. `FROM_EMAIL` manda; `SENDER_EMAIL` queda como
    respaldo para no romper una instalación que sólo tenga configurada esa.

Y SI ESTA MAL CONFIGURADO, SE GRITA

    `revisar()` se llama al arrancar y deja dicho en el registro qué falta. Un
    correo que no sale y no se nota es indistinguible de uno que sí salió, y es
    la peor de las tres situaciones: el usuario cree que le avisamos.
"""
import asyncio
import logging
import os

from config import RESEND_API_KEY, FROM_EMAIL

logger = logging.getLogger(__name__)

APP = "RIS App"

# Los valores de ejemplo que trae el proyecto. Que quede uno de éstos puesto es
# lo mismo que no haber configurado nada, y hay que decirlo igual de fuerte.
_DE_EJEMPLO = ("example.com", "risapp.com")


def _remitente() -> str:
    """De qué dirección salen los correos. Ver el encabezado."""
    valor = (FROM_EMAIL or "").strip() or (os.getenv("SENDER_EMAIL") or "").strip()
    if not valor:
        return ""
    # Resend acepta «Nombre <casilla>»; si ya viene así, se respeta.
    return valor if "<" in valor else f"{APP} <{valor}>"


REMITENTE = _remitente()


def configurado() -> tuple[bool, str]:
    """¿Se puede mandar un correo? Y si no, por qué no."""
    if not RESEND_API_KEY:
        return False, "falta RESEND_API_KEY: no sale ningún correo."
    if not REMITENTE:
        return False, ("no hay remitente: configurá FROM_EMAIL con una casilla "
                       "de un dominio verificado en Resend.")
    for ejemplo in _DE_EJEMPLO:
        if ejemplo in REMITENTE:
            return False, (
                f"el remitente es {REMITENTE!r}, que usa {ejemplo}. Ese dominio "
                "no está verificado en Resend: los correos se van a rechazar "
                "sin que nadie se entere. Configurá FROM_EMAIL.")
    return True, f"los correos salen desde {REMITENTE}."


def revisar() -> bool:
    """Se llama al arrancar. Deja dicho si el correo está bien configurado."""
    listo, motivo = configurado()
    if listo:
        logger.info("Correo: %s", motivo)
    else:
        logger.error("CORREO MAL CONFIGURADO: %s", motivo)
    return listo


async def enviar(destinatario: str, asunto: str, html: str, *,
                 que_es: str = "correo") -> bool:
    """Manda uno y espera. Devuelve si salió.

    No levanta nunca: quien llama acaba de hacer un trabajo de verdad y ese
    trabajo ya está hecho. Lo que hace falta saber es si el correo salió, y eso
    se devuelve.
    """
    listo, motivo = configurado()
    if not listo:
        logger.error("No se mandó el %s: %s", que_es, motivo)
        return False

    try:
        import resend
        resend.api_key = RESEND_API_KEY
        # EN OTRO HILO. Es la línea que arregla el problema del encabezado:
        # `resend.Emails.send` bloquea, y acá adentro bloquea a un hilo que no
        # atiende pedidos.
        await asyncio.to_thread(resend.Emails.send, {
            "from": REMITENTE,
            "to": [destinatario],
            "subject": asunto,
            "html": html,
        })
        logger.info("Salió el %s", que_es)
        return True
    except Exception as e:
        logger.error("No se pudo mandar el %s: %s: %s",
                     que_es, type(e).__name__, e)
        return False


# Las tareas en curso, con una referencia fuerte.
#
# `asyncio` sólo guarda una referencia DEBIL a las tareas que corren. Sin esta
# lista, el recolector de basura puede llevarse una tarea a mitad de camino y el
# correo no sale nunca, sin ningún error en el registro.
_EN_VUELO: set = set()


def en_segundo_plano(destinatario: str, asunto: str, html: str, *,
                     que_es: str = "correo") -> None:
    """Manda uno sin esperar. Para la cortesía, no para lo que hay que confirmar."""
    coro = enviar(destinatario, asunto, html, que_es=que_es)
    try:
        tarea = asyncio.create_task(coro)
    except RuntimeError:
        # Sin bucle corriendo —un script, un test sincrónico— no hay dónde
        # encolar. No es un error del que valga la pena morirse, pero la
        # corrutina hay que cerrarla: si no, Python avisa de una que nunca se
        # esperó, y ese aviso aparece en un lugar que no tiene nada que ver.
        coro.close()
        logger.warning("No hay bucle para mandar el %s en segundo plano", que_es)
        return
    _EN_VUELO.add(tarea)
    tarea.add_done_callback(_EN_VUELO.discard)
