"""
services/preparar_la_base.py — Lo que el arranque hace en la base (índices,
migraciones, el cofre), en segundo plano y recién cuando la base contesta.

POR QUE NO SE HACE ANTES DE EMPEZAR A ATENDER

    Hasta el 25 de septiembre de 2026 todo esto corría dentro del arranque, uno
    detrás de otro, y el servidor no contestaba ningún pedido hasta terminar.
    Con Mongo sano son dos segundos. Con Mongo sin primario, cada paso espera
    30 segundos a que aparezca uno antes de rendirse, y son decenas de pasos.

    Ese día Mongo se quedó sin primario después de un reinicio. El backend se
    redesplegó para volver atrás, no contestó `/api/health` en los cinco
    minutos que espera Railway, y Railway dio el despliegue por fallido: la
    página pasó a «Not Found» y el corte duró lo que tardó Mongo, más el
    despliegue del backend, más volver a desplegarlo.

    Ahora el servidor atiende enseguida. Si la base no contesta, cada pedido
    que la necesita da error —lo mismo que pasaría con el servidor arriba— y
    la salud lo dice en su línea «base». Cuando la base vuelve, esto corre solo.

POR QUE ESPERA A LA BASE EN VEZ DE CORRER DIRECTO

    Corrido directo con la base caída, cada paso falla, deja su error escrito,
    y no se reintenta hasta el próximo despliegue: el índice único que impide
    acreditar dos veces el mismo pago quedaría sin revisar hasta entonces.
    Esperar a que la base conteste y RECIÉN AHÍ correr todo deja las cosas
    igual que un arranque normal, sólo que más tarde.

LO QUE CAMBIA EN UN ARRANQUE NORMAL

    Casi nada: los primeros pedidos pueden llegar mientras se revisan los
    índices. En producción los índices ya existen —cada arranque los vuelve a
    pedir y Mongo contesta «ya está»—, así que no hay una ventana sin ellos.
"""
import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Entre intentos: 1, 2, 4, 8, 16 y después cada 30 segundos. Cada intento ya
# espera por su cuenta lo que tarda el controlador en rendirse (30 s), así que
# esto no martilla a una base que está volviendo.
ESPERA_INICIAL_S = 1
ESPERA_MAXIMA_S = 30

_tarea: Optional[asyncio.Task] = None


async def esperar_la_base(db, dormir: Callable[[float], Awaitable] = asyncio.sleep) -> int:
    """Vuelve cuando la base contesta un `ping`. Devuelve cuántos intentos
    fallaron antes, para el registro."""
    espera = ESPERA_INICIAL_S
    fallidos = 0
    while True:
        try:
            await db.command("ping")
            return fallidos
        except Exception as e:
            fallidos += 1
            logger.warning(
                "ARRANQUE| la base no contesta (intento %d): %s. El servidor ya "
                "atiende; los índices se revisan cuando vuelva. Reintento en %d s",
                fallidos, str(e)[:200], espera)
            await dormir(espera)
            espera = min(espera * 2, ESPERA_MAXIMA_S)


async def _esperar_y_preparar(db, preparar: Callable[[], Awaitable]) -> None:
    fallidos = await esperar_la_base(db)
    if fallidos:
        logger.info("ARRANQUE| la base volvió después de %d intento(s); reviso los índices", fallidos)
    try:
        await preparar()
    except Exception:
        # Cada paso de `preparar` ya atrapa y anota lo suyo; esto es la red
        # por si algo se escapa. Sin ella, el error de una tarea de fondo sólo
        # aparece como «Task exception was never retrieved» al apagar.
        logger.exception("ARRANQUE| la preparación de la base se cortó")
        return
    logger.info("ARRANQUE| base preparada")


def arrancar(db, preparar: Callable[[], Awaitable]) -> asyncio.Task:
    """Lanza la preparación en segundo plano y vuelve enseguida."""
    global _tarea
    _tarea = asyncio.create_task(_esperar_y_preparar(db, preparar))
    return _tarea


async def parar() -> None:
    global _tarea
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
        try:
            await _tarea
        except (asyncio.CancelledError, Exception):
            pass
    _tarea = None
