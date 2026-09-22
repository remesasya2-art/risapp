"""
El respaldo automático de la base: un reloj que lo crea cada día, lo firma,
lo guarda afuera y lo comprueba, sin que nadie tenga que acordarse.

POR QUE

    Con el respaldo manual (`services/respaldo_de_mongo.py`) el RPO —cuánto se
    puede perder— es «lo que tarde el operador entre un respaldo y el
    siguiente». Eso es una esperanza, no un número. Este módulo lo vuelve un
    número: 24 horas.

DONDE SE GUARDA

    En el almacén de objetos que la aplicación ya usa para las fotos de los
    envíos (`services/envios_almacen.py`, R2 o cualquier S3), bajo su propia
    carpeta `respaldos/`. No hace falta un servicio ni una credencial nueva.
    Sin almacén configurado no hay a dónde guardar: el reloj no hace nada y la
    salud de la aplicación lo dice en rojo.

QUE HACE CADA VEZ

    1. Exporta y firma, igual que el botón; el archivo lleva la firma adentro.
    2. Lo sube al almacén: `respaldos/risapp-respaldo-<momento>.jsonl`.
    3. Lo vuelve a LEER del almacén y comprueba ESO entero (cada línea, el
       hash del cierre, la firma). No lo que tenía en memoria: lo que quedó
       guardado, que es lo único que va a existir el día que haga falta.
    4. Lo registra en la misma tabla que los manuales, con `origen=automatico`
       y dónde quedó; y en la auditoría.
    5. NO poda. El token de R2 no puede borrar, a propósito (ver
       `envios_almacen.py`: una falla o un abuso de la aplicación no puede
       vaciar el bucket, ni el de fotos ni el de respaldos). La retención es
       una regla de ciclo de vida del bucket, configurada en Cloudflare:
       «borrar los objetos bajo `respaldos/` a los 30 días». Cuando R2 se
       lleva uno, la aplicación se entera al pedir el enlace de descarga
       (una cabecera, permiso de lectura) y marca la fila con `borrado_en`.

    Si algo falla en el medio, grita (`services/gritos.py`): fila en Errores y
    campana a los super administradores. Un respaldo que falla en silencio es
    exactamente un respaldo que no existe.

CUANDO

    El reloj se despierta cada hora, con turno (`services/turnos.py`) para que
    con varios procesos corra uno solo, y hace el respaldo si el último
    automático que salió bien tiene más de 23 horas. Con 23 y no 24 la hora no
    se va corriendo un poquito cada día. Se puede apagar desde Configuración,
    y pedir uno «ahora» desde la pestaña de respaldos.

LO QUE NO HACE

    No sube los manuales: el botón sigue bajando el archivo al navegador para
    que el operador lo guarde donde quiera. Y no restaura: eso es a mano, con
    el procedimiento del dossier (sección 9.1).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

CADA_SEGUNDOS = 3600
TURNO = "respaldo_automatico"
SEGUNDOS_DEL_TURNO = 3000               # menos que CADA_SEGUNDOS, o el turno nunca caduca
HORAS_ENTRE_RESPALDOS = 23
HORAS_PARA_ESTAR_SANO = 26              # un día más un margen para el reloj y la subida
PREFIJO = "respaldos"
ACTOR = "reloj"
SEGUNDOS_PARA_SUBIR = 180               # 70 MB por una conexión de servidor: sobra
LATIDO = "RESPALDO|"
AJUSTE_ENCENDIDO = "respaldo_automatico_encendido"
RETENCION_RECOMENDADA_DIAS = 30         # la regla de ciclo de vida que se configura en R2

_estado = {"ultima_vuelta": None, "ultimo_resultado": None, "corriendo": False}
_tarea: Optional[asyncio.Task] = None


def configurado() -> bool:
    from services import envios_almacen
    return envios_almacen.configurado()


async def encendido(db) -> bool:
    from services import configuracion
    try:
        return int(await configuracion.leer(db, AJUSTE_ENCENDIDO)) == 1
    except Exception as e:
        logger.warning("%s no se pudo leer el ajuste; se toma como prendido: %s", LATIDO, e)
        return True


def _clave(ahora: datetime) -> str:
    return f"{PREFIJO}/risapp-respaldo-{ahora.strftime('%Y-%m-%dT%H%M%S')}.jsonl"


async def ultimo_bueno(db) -> Optional[dict]:
    """El último automático que quedó guardado afuera y comprobado."""
    from services.respaldo_de_mongo import COLECCION_DEL_REGISTRO
    return await db[COLECCION_DEL_REGISTRO].find_one(
        {"origen": "automatico", "error": None, "almacen": {"$ne": None}, "comprobacion.ok": True},
        sort=[("momento", -1)])


def _aware(v):
    return v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) and v.tzinfo is None else v


async def hace_falta(db, ahora: Optional[datetime] = None) -> bool:
    ahora = ahora or datetime.now(timezone.utc)
    u = await ultimo_bueno(db)
    if u is None:
        return True
    return ahora - _aware(u["momento"]) >= timedelta(hours=HORAS_ENTRE_RESPALDOS)


async def correr(db, *, ahora: Optional[datetime] = None, forzar: bool = False, quien=None, request=None) -> dict:
    """Un respaldo completo: exportar, subir, comprobar, registrar, podar.
    `forzar` salta el ajuste de apagado (el botón «ahora» del panel)."""
    from services import envios_almacen, gritos
    from services import respaldo_de_mongo as rm
    ahora = ahora or datetime.now(timezone.utc)
    if not configurado():
        return {"hecho": False, "motivo": "sin_almacen"}
    if not forzar and not await encendido(db):
        return {"hecho": False, "motivo": "apagado"}
    actor = getattr(quien, "user_id", None) or ACTOR

    try:
        contenido, firma, resumen = await rm.exportar(db, actor=actor, ahora=ahora)
    except Exception as e:
        await gritos.respaldo_fallido(db, paso="exportar la base", error=e)
        return {"hecho": False, "motivo": "exportar", "error": str(e)}

    archivo = contenido + rm.linea_de_firma(resumen["hash"], firma, resumen["documentos"])
    clave = _clave(ahora)
    subido = await envios_almacen.poner(clave, archivo.encode("utf-8"), "application/x-ndjson", presupuesto=SEGUNDOS_PARA_SUBIR)
    almacen = {"bucket": envios_almacen.bucket_actual(), "clave": clave, "bytes": len(archivo.encode("utf-8")), "borrado_en": None} if subido else None

    # La comprobación, sobre lo que QUEDO en el almacén: se vuelve a leer de
    # ahí. Comprobar el texto que se tenía en memoria diría «bien» aunque el
    # bucket hubiera guardado otra cosa, o nada.
    comprobacion = {"ok": False, "hash_ok": False, "firma": "sin_firma", "documentos": 0, "colecciones": {}, "motivo": "no se guardó"}
    error = None
    if not subido:
        error = "no se pudo guardar en el almacén de objetos"
    else:
        vuelto, motivo = await envios_almacen.traer(clave, tope=len(archivo.encode("utf-8")) + 1, presupuesto=SEGUNDOS_PARA_SUBIR)
        if vuelto is None:
            comprobacion["motivo"] = f"no se pudo volver a leer del almacén ({motivo})"
        else:
            comprobacion = rm.comprobar(vuelto.decode("utf-8", errors="replace"))
        if not comprobacion["ok"]:
            error = f"lo guardado en el almacén no pasa la comprobación: {comprobacion.get('motivo')}"
    comprobacion["hash"] = resumen["hash"]
    comprobacion["registrado"] = True
    comprobacion["en"] = "servidor"
    registro = await rm.registrar(db, resumen, ahora=ahora, actor=actor, origen="automatico", quien=quien, request=request,
                                  almacen=almacen, comprobacion=comprobacion, error=error)
    if error:
        await gritos.respaldo_fallido(db, paso="guardar y comprobar el respaldo", error=error)
        return {"hecho": False, "motivo": "almacen" if not subido else "comprobacion", "error": error, "id": registro["id"]}

    logger.info("%s guardado %s (%d documentos, %d bytes), comprobado", LATIDO, clave, resumen["documentos"], almacen["bytes"])
    return {"hecho": True, "id": registro["id"], "clave": clave, "documentos": resumen["documentos"],
            "bytes": almacen["bytes"], "hash": resumen["hash"]}


async def enlace_de_descarga(db, registro_id: str, *, segundos: int = 600) -> Optional[str]:
    """Un enlace directo al almacén, firmado y con vencimiento, para bajar un
    automático sin que los 70 MB pasen por la aplicación. Antes de firmar
    pregunta si el objeto sigue ahí: si la regla de retención de R2 ya se lo
    llevó, marca la fila y no devuelve nada."""
    from bson import ObjectId
    from services import envios_almacen
    from services.respaldo_de_mongo import COLECCION_DEL_REGISTRO
    try:
        fila = await db[COLECCION_DEL_REGISTRO].find_one({"_id": ObjectId(registro_id)})
    except Exception:
        return None
    almacen = (fila or {}).get("almacen") or {}
    if not almacen.get("clave") or almacen.get("borrado_en"):
        return None
    if await envios_almacen.existe(almacen["clave"], bucket=almacen.get("bucket")) is False:
        await db[COLECCION_DEL_REGISTRO].update_one({"_id": fila["_id"]}, {"$set": {"almacen.borrado_en": datetime.now(timezone.utc)}})
        logger.info("%s %s ya no está en el almacén: lo borró la regla de retención", LATIDO, almacen["clave"])
        return None
    return await envios_almacen.url_firmada(almacen["clave"], segundos=segundos, bucket=almacen.get("bucket"))


async def vigilar(db, *, forzar: bool = False, ahora: Optional[datetime] = None) -> Optional[dict]:
    """Una vuelta del reloj: con turno, y sólo si hace falta."""
    from services import turnos
    if not forzar and not await turnos.me_toca(db, TURNO, segundos=SEGUNDOS_DEL_TURNO):
        logger.info("%s me salteé la vuelta: el turno lo tiene otro proceso", LATIDO)
        return None
    ahora = ahora or datetime.now(timezone.utc)
    _estado["ultima_vuelta"] = ahora.isoformat()
    if not configurado():
        logger.warning("%s sin almacén de objetos: no hay a dónde guardar (ENVIOS_R2_*)", LATIDO)
        return {"hecho": False, "motivo": "sin_almacen"}
    if not await hace_falta(db, ahora):
        logger.info("%s el último automático tiene menos de %d h; no hace falta", LATIDO, HORAS_ENTRE_RESPALDOS)
        return {"hecho": False, "motivo": "reciente"}
    r = await correr(db, ahora=ahora)                    # `correr` mira el ajuste de apagado
    _estado["ultimo_resultado"] = r
    if not r["hecho"]:
        logger.warning("%s no se hizo: %s", LATIDO, r.get("error") or r.get("motivo"))
    return r


async def para_la_salud(db, ahora: Optional[datetime] = None) -> tuple:
    """(ok, detalle, grave) para la tira de salud de la aplicación."""
    ahora = ahora or datetime.now(timezone.utc)
    if not configurado():
        return False, "no hay almacén de objetos: el respaldo automático no tiene dónde guardar (ENVIOS_R2_* en Railway)", False
    if not await encendido(db):
        return False, "el respaldo automático está APAGADO en Configuración", False
    u = await ultimo_bueno(db)
    if u is None:
        return False, "todavía no hay ningún respaldo automático guardado afuera", False
    horas = (ahora - _aware(u["momento"])).total_seconds() / 3600
    if horas > HORAS_PARA_ESTAR_SANO:
        return False, f"el último respaldo automático es de hace {int(horas)} h (tiene que haber uno por día)", False
    return True, f"último respaldo automático de hace {int(horas)} h, guardado afuera y comprobado ({u['documentos']} documentos)", False


def estado() -> dict:
    return {"corriendo": _estado["corriendo"], "ultima_vuelta": _estado["ultima_vuelta"],
            "ultimo_resultado": _estado["ultimo_resultado"], "cada_segundos": CADA_SEGUNDOS,
            "configurado": configurado(), "prefijo": PREFIJO, "retencion_recomendada_dias": RETENCION_RECOMENDADA_DIAS}


async def _bucle(db):
    _estado["corriendo"] = True
    try:
        while True:
            try:
                await vigilar(db)
            except Exception:
                logger.exception("%s la vuelta falló", LATIDO)
            await asyncio.sleep(CADA_SEGUNDOS)
    finally:
        _estado["corriendo"] = False


def arrancar(db) -> None:
    global _tarea
    if _tarea is None or _tarea.done():
        _tarea = asyncio.get_event_loop().create_task(_bucle(db))
        logger.info("%s reloj del respaldo automático en marcha (cada %d s)", LATIDO, CADA_SEGUNDOS)


async def parar() -> None:
    global _tarea
    if _tarea is not None:
        _tarea.cancel()
        try:
            await _tarea
        except (asyncio.CancelledError, Exception):
            pass
        _tarea = None


def reiniciar_para_tests() -> None:
    _estado.update(ultima_vuelta=None, ultimo_resultado=None, corriendo=False)
