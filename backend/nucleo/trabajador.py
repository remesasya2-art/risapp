"""
El trabajador: el bucle que despacha eventos y corre trabajos.

DONDE CORRE

    En el mismo proceso web, como los tres bucles que ya existen (la tasa
    del BCV, el contador de uso, el barrido de cobros). Decisión del dueño
    para el laboratorio: cero servicios nuevos en Railway. El día que haga
    falta un proceso aparte, `una_vuelta` y `latir` son funciones: un
    comando propio las llama en su propio bucle y este archivo no cambia.

MIRA EL INTERRUPTOR EN CADA VUELTA

    No alcanza con mirarlo al arrancar: prender o apagar el núcleo desde
    Configuración tiene que surtir efecto sin redesplegar (regla del
    proyecto: configurar nunca requiere editar código). Con el núcleo
    apagado o sin base el bucle no toca nada y duerme más largo. Y falla
    cerrado, como el modo: si no puede leer la configuración, no trabaja.

NO SE MUERE

    Un error en una vuelta se anota y se sigue. Es la misma regla del
    barrido de cobros, por el mismo motivo: un bucle que se corta por un
    error de base deja la cola parada hasta el próximo despliegue, y nadie
    se entera.
"""
import asyncio
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Optional

from nucleo import base, cola, modo, tareas

logger = logging.getLogger(__name__)

NOMBRE = f"{socket.gethostname()}:{os.getpid()}"

CADA_CUANTO_ENCENDIDO = 3       # segundos entre vueltas con el núcleo prendido
CADA_CUANTO_APAGADO = 30        # con el núcleo apagado, una mirada al interruptor cada tanto
TOPE_POR_VUELTA = 50            # trabajos por vuelta, para no acaparar el proceso web

_tarea = None
_estado = {"nombre": NOMBRE, "corriendo": False, "vueltas": 0, "ultima_vuelta": None,
           "ultimo_error": None, "ultimo_modo": None}


async def correr_uno(*, ahora: Optional[datetime] = None) -> Optional[dict]:
    """Toma un trabajo, lo corre y lo marca. None si no había nada."""
    async with base.sesion() as s:
        trabajo = await cola.tomar(s, trabajador=NOMBRE, ahora=ahora)
    if trabajo is None:
        return None
    manejador = tareas.MANEJADORES.get(trabajo["tipo"])
    if manejador is None:
        async with base.sesion() as s:
            await cola.matar(s, trabajo["id"], trabajador=NOMBRE, ahora=ahora,
                             error=f"No hay manejador para el tipo «{trabajo['tipo']}».")
        return {"id": trabajo["id"], "tipo": trabajo["tipo"], "estado": cola.MUERTO}
    try:
        resultado = await manejador(trabajo["carga"])
    except Exception as e:
        async with base.sesion() as s:
            r = await cola.fallar(s, trabajo["id"], trabajador=NOMBRE, ahora=ahora,
                                  error=f"{type(e).__name__}: {e}")
        logger.warning("nucleo: el trabajo %s (%s) falló en el intento %s: %s",
                       trabajo["id"], trabajo["tipo"], trabajo["intentos"], e)
        return {"id": trabajo["id"], "tipo": trabajo["tipo"], "estado": r["estado"]}
    async with base.sesion() as s:
        await cola.terminar(s, trabajo["id"], trabajador=NOMBRE, ahora=ahora,
                            resultado=str(resultado) if resultado is not None else None)
    return {"id": trabajo["id"], "tipo": trabajo["tipo"], "estado": cola.HECHO}


async def una_vuelta(*, ahora: Optional[datetime] = None, tope: int = TOPE_POR_VUELTA) -> dict:
    """Despacha los eventos pendientes y corre hasta `tope` trabajos. No
    mira el interruptor: eso lo hace `latir`. Desde el panel se llama a
    mano («Procesar ahora»)."""
    async with base.sesion() as s:
        despachados = await cola.despachar_eventos(s, tareas.SUSCRIPCIONES, ahora=ahora)
    cuenta = {cola.HECHO: 0, cola.MUERTO: 0, cola.PENDIENTE: 0}
    corridos = 0
    for _ in range(tope):
        r = await correr_uno(ahora=ahora)
        if r is None:
            break
        corridos += 1
        cuenta[r["estado"]] = cuenta.get(r["estado"], 0) + 1
    return {"despachados": despachados, "corridos": corridos, "hechos": cuenta[cola.HECHO],
            "muertos": cuenta[cola.MUERTO], "reintentan": cuenta[cola.PENDIENTE]}


async def latir(db) -> bool:
    """Una vuelta del bucle: mira el interruptor y, si el núcleo está
    prendido y con base, trabaja. Devuelve si trabajó."""
    m = await modo.leer(db)
    _estado["ultimo_modo"] = modo.NOMBRES.get(m, "apagado")
    if not (modo.se_puede_usar(m) and base.hay_base()):
        return False
    r = await una_vuelta()
    _estado["vueltas"] += 1
    _estado["ultima_vuelta"] = datetime.now(timezone.utc).isoformat()
    _estado["ultimo_error"] = None
    if r["corridos"] or r["despachados"]:
        logger.info("nucleo: vuelta del trabajador: %s", r)
    return True


async def _bucle(db):
    _estado["corriendo"] = True
    try:
        while True:
            trabajo = False
            try:
                trabajo = await latir(db)
            except Exception as e:
                # NO SE CORTA EL BUCLE. Ver el encabezado.
                _estado["ultimo_error"] = f"{type(e).__name__}: {e}"
                logger.error("nucleo: falló una vuelta del trabajador: %s", e)
            await asyncio.sleep(CADA_CUANTO_ENCENDIDO if trabajo else CADA_CUANTO_APAGADO)
    finally:
        _estado["corriendo"] = False


def arrancar(db) -> None:
    """Deja corriendo el trabajador. Se llama una vez, al arrancar."""
    global _tarea
    if _tarea is not None and not _tarea.done():
        return
    _tarea = asyncio.create_task(_bucle(db))


async def parar() -> None:
    """Corta el bucle. Para el apagado. Un trabajo a medias queda en curso
    con su turno: vence solo y el próximo proceso lo retoma."""
    global _tarea
    if _tarea is not None:
        _tarea.cancel()
        try:
            await _tarea
        except (asyncio.CancelledError, Exception):
            pass
        _tarea = None
    _estado["corriendo"] = False


def estado() -> dict:
    """Lo que la pestaña muestra del trabajador."""
    return dict(_estado)
