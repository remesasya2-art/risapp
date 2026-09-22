"""
La salud de la aplicación: si la base responde, y quién se entera cuando
deja de responder.

POR QUE

    `/api/health` contestaba «healthy» fijo, sin mirar nada. Un monitor que
    lo consultaba veía verde con Mongo caído, porque el proceso web seguía
    vivo aunque no pudiera leer ni una cuenta. Y nadie del equipo se
    enteraba hasta que un cliente avisaba.

QUE MIRA

    base          que Mongo contesta, y en cuánto tiempo. Si no contesta, no
                  se mira nada más: todo lo demás vive ahí.
    cpf_unico     que existe el candado que impide dos cuentas con el mismo
                  CPF. Hoy falta porque hay repetidos (ver
                  `services/cpf_de_la_cuenta.py`); cuando se resuelvan, este
                  renglón se pone verde solo.
    transacciones que el Mongo es un conjunto de réplicas. Con un nodo
                  suelto el motor contable corre SIN transacciones: un cobro
                  que mueve el saldo y escribe el libro son dos escrituras
                  separadas, y la segunda puede no pasar. Lo detecta
                  `accounting_engine` al arrancar y lo decía sólo en el log.
    bcv           que el último raspado del BCV está dentro de su vigencia.
                  Vencido, el dólar del panel le gana; pero un raspador que
                  lleva días muerto es algo que alguien tiene que saber.
    cofre         que los documentos se guardan cifrados y la llave puesta es
                  la que los cifró. Una llave equivocada es GRAVE: el KYC no
                  puede abrir ni guardar documentos.
    contadores    que los límites de intentos se cuentan en la base y no en
                  la memoria del proceso, donde se reinician con cada
                  despliegue y no sirven con más de un proceso.

    Sólo `base` y una llave equivocada del cofre son graves. Lo demás es
    «no sana», que en el Resumen se ve en rojo y avisa al equipo, pero no
    es una caída.

    Cada comprobación va en su propio `try`: una que explota no puede dejar
    a las otras sin mirar, y se muestra como falla con el motivo.

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
    for nombre, mirar in (("cpf_unico", _cpf_unico), ("transacciones", _transacciones), ("bcv", _bcv),
                          ("cofre", _cofre), ("contadores", _contadores)):
        try:
            ok, detalle, grave = await mirar(db)
        except Exception as e:
            ok, detalle, grave = False, f"no se pudo mirar: {type(e).__name__}: {e}", False
        comprobaciones.append({"nombre": nombre, "ok": ok, "detalle": detalle, "grave": grave})
    return {"ok": all(c["ok"] for c in comprobaciones), "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}


async def _cpf_unico(db):
    from services.cpf_de_la_cuenta import NOMBRE_DEL_INDICE
    hay = NOMBRE_DEL_INDICE in await db.users.index_information()
    return (hay, "el candado de un CPF por cuenta está" if hay else
            "FALTA el candado de un CPF por cuenta: hay cuentas con el CPF repetido (ver Usuarios → CPF repetidos)", False)


async def _transacciones(db):
    from services.accounting_engine import hay_transacciones
    if await hay_transacciones():
        return True, "Mongo es un conjunto de réplicas: los cobros se escriben en una sola operación", False
    return (False, "Mongo es de UN solo nodo: la aplicación corre sin transacciones, y un cobro que mueve "
                   "el saldo y escribe el libro son dos escrituras separadas. Hace falta un conjunto de réplicas (replica set)", False)


async def _bcv(db):
    from services.bcv_scraper import vigencia
    v = await vigencia(db)
    if not v["hay_raspado"]:
        return False, "no hay ningún raspado del BCV guardado", False
    edad = v["edad_horas"]
    # Las horas vienen con dos decimales; en una tira de estado «2 h» alcanza.
    cuanto = "de hace menos de una hora" if edad is not None and edad < 1 else f"de hace {int(edad)} h"
    if v["sirve"]:
        return True, f"dólar BCV {cuanto} (vigencia {v['horas_de_vigencia']} h)", False
    return False, f"la tasa del BCV está VENCIDA: {cuanto}, con vigencia de {v['horas_de_vigencia']} h; el dólar del panel le gana", False


async def _cofre(db):
    from services import cofre
    estado = await cofre.revisar(db)
    if estado["modo"] != "cifrando":
        return False, "el cofre está APAGADO: los documentos de identidad se guardan en claro (COFRE_MODO=cifrando)", False
    grave = estado["motivo"] in ("llave_equivocada", "sin_llave")
    return bool(estado["ok"]), estado["detalle"], grave


async def _contadores(db):
    from services import limites_en_la_base
    if limites_en_la_base.activo():
        return True, "los límites de intentos se cuentan en la base", False
    return (False, "los límites de intentos se cuentan en la MEMORIA del proceso: se reinician con cada despliegue "
                   f"y no sirven con más de un proceso ({limites_en_la_base.VARIABLE}=si en Railway)", False)


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
