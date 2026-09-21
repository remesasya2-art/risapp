"""
Los manejadores de la cola y las suscripciones a los eventos.

    Un manejador es una función `async def nombre(carga: dict) -> str | None`.
    Recibe lo que el trabajo lleva en la carga y devuelve, si quiere, un
    texto corto que queda guardado como resultado. Si lanza, el trabajo se
    reintenta con espera creciente; si sigue lanzando, muere y una persona
    lo ve en el panel.

    TIENE QUE SER IDEMPOTENTE: puede correr dos veces si el proceso murió
    justo después de hacer el trabajo y antes de marcarlo hecho. El motivo
    completo está en `nucleo/cola.py`.

LAS SUSCRIPCIONES

    `SUSCRIPCIONES` dice, para cada tipo de evento, qué trabajos se encolan
    cuando el evento se publica. Es un diccionario y no un decorador mágico
    a propósito: se lee de arriba abajo y se ve todo.

LOS DE LABORATORIO

    `eco` y `fallar` existen para probar la cola desde la pestaña: uno
    termina bien y devuelve lo que se le mandó; el otro falla siempre, para
    ver los reintentos y la cola de muertos con los propios ojos. Son los
    únicos que la pestaña puede encolar a mano (`rutas.py` lo limita).
"""
import logging

from nucleo.rieles import operaciones as _rieles
from nucleo.riesgo import monitoreo as _monitoreo

logger = logging.getLogger(__name__)


async def eco(carga: dict) -> str:
    """Devuelve lo que se le mandó. Para ver un trabajo terminar bien."""
    return "eco: " + str(carga.get("mensaje", carga))[:200]


async def fallar(carga: dict) -> None:
    """Falla siempre. Para ver la espera creciente y la cola de muertos."""
    raise RuntimeError(str(carga.get("motivo") or "Falla a propósito, para ver la cola de muertos."))


async def avisar_asiento(carga: dict) -> str:
    """Nació un asiento. En producción acá va el aviso al titular (correo,
    notificación); hoy, en laboratorio, se anota en el registro."""
    logger.info("nucleo: asiento %s registrado (%s, ref %s)",
                carga.get("numero"), carga.get("comando"), carga.get("referencia"))
    return f"asiento {carga.get('numero')} avisado"


async def anotar_cierre(carga: dict) -> str:
    """Cerró un día. En producción acá se arma el informe del cierre; hoy
    se anota en el registro."""
    logger.info("nucleo: día %s cerrado hasta el asiento %s", carga.get("dia"), carga.get("hasta_asiento"))
    return f"cierre del {carga.get('dia')} anotado"


MANEJADORES = {
    "eco": eco,
    "fallar": fallar,
    "avisar_asiento": avisar_asiento,
    "anotar_cierre": anotar_cierre,
    # Los rieles (nucleo/rieles/operaciones.py): hablar con el riel y darle
    # sentido a lo que el riel avisa, los dos con reintentos y cola de muertos.
    "enviar_pago": _rieles.enviar_pago,
    "procesar_aviso": _rieles.procesar_aviso,
    # El monitoreo (nucleo/riesgo/monitoreo.py): las reglas sobre cada
    # operación liquidada.
    "evaluar_riesgo": _monitoreo.evaluar_riesgo,
}

SUSCRIPCIONES = {
    "asiento_registrado": ("avisar_asiento",),
    "dia_cerrado": ("anotar_cierre",),
    "operacion_liquidada": ("evaluar_riesgo",),
}

# Lo que se puede encolar a mano desde la pestaña del laboratorio.
DE_LABORATORIO = ("eco", "fallar")
