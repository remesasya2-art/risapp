"""
La salud de la aplicación: si la base responde, y quién se entera cuando
deja de responder.

POR QUE

    `/api/health` contestaba «healthy» fijo, sin mirar nada. Un monitor que
    lo consultaba veía verde con Mongo caído, porque el proceso web seguía
    vivo aunque no pudiera leer ni una cuenta. Y nadie del equipo se
    enteraba hasta que un cliente avisaba.

QUE MIRA

    base          que Mongo contesta, y en cuánto tiempo.
    cpf_unico     que existe el candado que impide dos cuentas con el mismo
                  CPF. Hoy falta porque hay repetidos (ver
                  `services/cpf_de_la_cuenta.py`); cuando se resuelvan, este
                  renglón se pone verde solo.

COMO AVISA

    Un reloj adentro del proceso revisa cada cinco minutos y avisa por la
    campana del equipo, sólo a los super administradores, SOLO CUANDO CAMBIA:
    de bien a mal y de mal a bien. Un aviso que se repite cada cinco minutos
    es un aviso que alguien silencia. Con varios procesos, el turno
    (`services/turnos.py`) hace que revise uno solo.

    Cada vuelta deja una línea con la marca `SALUD|`, pase lo que pase, por
    el mismo motivo que el reloj del BCV: el silencio de un reloj muerto y
    el de «todo bien» no pueden verse iguales.

POR QUE `/api/health` SIGUE CONTESTANDO 200 CON LA BASE CAIDA

    Railway reinicia el proceso cuando el ping de vida falla. Reiniciar la
    aplicación no levanta a Mongo; sólo agrega un bucle de reinicios encima
    de la caída. El ping dice `base: false` para el monitor que sepa leerlo,
    y el aviso al equipo va por la campana. Y no consulta la base en cada
    llamada: devuelve lo último que vio el reloj, que es lo que hace que una
    ruta anónima siga siendo barata.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

CADA_SEGUNDOS = 300
TURNO = "salud_de_la_app"
SEGUNDOS_DEL_TURNO = 240          # menos que CADA_SEGUNDOS, o el turno nunca caduca
LATIDO = "SALUD|"
CUANTOS_CAMBIOS_SE_RECUERDAN = 20

_estado = {"ultimo_ok": None, "ultima_revision": None, "ultimas_fallas": [], "cambios": [], "corriendo": False}
_tarea: Optional[asyncio.Task] = None


async def revisar(db) -> dict:
    from services.cpf_de_la_cuenta import NOMBRE_DEL_INDICE
    ahora = datetime.now(timezone.utc)
    comprobaciones = []
    arranque = time.monotonic()
    try:
        await db.list_collection_names()
        ms = int((time.monotonic() - arranque) * 1000)
        comprobaciones.append({"nombre": "base", "ok": True, "detalle": f"Mongo responde en {ms} ms", "grave": True})
    except Exception as e:
        comprobaciones.append({"nombre": "base", "ok": False, "detalle": f"Mongo no responde: {type(e).__name__}: {e}", "grave": True})
        return {"ok": False, "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}
    try:
        indices = await db.users.index_information()
        hay = NOMBRE_DEL_INDICE in indices
        comprobaciones.append({"nombre": "cpf_unico", "ok": hay, "grave": False,
                               "detalle": "el candado de un CPF por cuenta está" if hay else
                               "FALTA el candado de un CPF por cuenta: hay cuentas con el CPF repetido (ver Usuarios → CPF repetidos)"})
    except Exception as e:
        comprobaciones.append({"nombre": "cpf_unico", "ok": False, "grave": False, "detalle": f"no se pudo mirar: {type(e).__name__}"})
    return {"ok": all(c["ok"] for c in comprobaciones), "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}


async def _avisar(titulo: str, mensaje: str, grave: bool) -> None:
    from services.notifications import avisar_al_personal
    await avisar_al_personal(title=titulo, message=mensaje, notification_type="error" if grave else "warning",
                             solo_super_admin=True, data={"seccion": "salud"})


async def vigilar(db, *, forzar: bool = False) -> Optional[dict]:
    """Una vuelta: revisa y avisa sólo si el estado cambió. `forzar` salta
    el turno (para el botón del panel y los tests)."""
    from services import turnos
    if not forzar and not await turnos.me_toca(db, TURNO, segundos=SEGUNDOS_DEL_TURNO):
        logger.info("%s me salteé la vuelta: el turno lo tiene otro proceso", LATIDO)
        return None
    r = await revisar(db)
    fallas = [c for c in r["comprobaciones"] if not c["ok"]]
    anterior = _estado["ultimo_ok"]
    _estado.update(ultimo_ok=r["ok"], ultima_revision=r["revisado_en"], ultimas_fallas=[c["nombre"] for c in fallas])
    logger.info("%s %s · %s", LATIDO, "bien" if r["ok"] else "MAL", "; ".join(f"{c['nombre']}: {c['detalle']}" for c in r["comprobaciones"]))
    if anterior is None or anterior == r["ok"]:
        return r
    grave = any(c["grave"] for c in fallas)
    if r["ok"]:
        titulo, mensaje = "La aplicación volvió a estar sana", "Todas las comprobaciones pasan."
    else:
        titulo = "La aplicación NO está sana" + (" (grave)" if grave else "")
        mensaje = "; ".join(f"{c['nombre']}: {c['detalle']}" for c in fallas)
    _estado["cambios"] = ([{"momento": r["revisado_en"], "ok": r["ok"], "fallas": _estado["ultimas_fallas"], "titulo": titulo}]
                          + _estado["cambios"])[:CUANTOS_CAMBIOS_SE_RECUERDAN]
    (logger.error if not r["ok"] else logger.info)("%s CAMBIO: %s · %s", LATIDO, titulo, mensaje)
    try:
        await _avisar(titulo, mensaje, grave)
    except Exception:
        logger.exception("%s no se pudo avisar al personal", LATIDO)
    return r


def ultimo_ok_de_la_base() -> Optional[bool]:
    """Para el ping de vida: lo último que vio el reloj, sin consultar nada."""
    if _estado["ultimo_ok"] is None:
        return None
    return "base" not in _estado["ultimas_fallas"]


def estado() -> dict:
    return {"ultimo_ok": _estado["ultimo_ok"], "ultima_revision": _estado["ultima_revision"],
            "ultimas_fallas": list(_estado["ultimas_fallas"]), "cambios": list(_estado["cambios"]),
            "corriendo": _estado["corriendo"], "cada_segundos": CADA_SEGUNDOS}


async def _bucle(db):
    _estado["corriendo"] = True
    try:
        while True:
            try:
                await vigilar(db)
            except Exception as e:
                logger.error("%s la vuelta falló y el reloj sigue: %s: %s", LATIDO, type(e).__name__, e)
            await asyncio.sleep(CADA_SEGUNDOS)
    finally:
        _estado["corriendo"] = False


def arrancar(db) -> None:
    global _tarea
    if _tarea is not None and not _tarea.done():
        return
    _tarea = asyncio.create_task(_bucle(db))


async def parar() -> None:
    global _tarea
    if _tarea is None:
        return
    _tarea.cancel()
    try:
        await _tarea
    except (asyncio.CancelledError, Exception):
        pass
    _tarea = None


def reiniciar_para_tests():
    _estado.update({"ultimo_ok": None, "ultima_revision": None, "ultimas_fallas": [], "cambios": [], "corriendo": False})
