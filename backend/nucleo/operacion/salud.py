"""
La salud del núcleo: lo que se mira de verdad, y quién avisa.

QUE MIRA

    base        que la base contesta.
    esquema     que la última migración aplicada es la última escrita.
    trabajador  que el bucle está corriendo y latió hace poco.
    cola        que no hay trabajos muertos.
    libro       que la cadena de hashes del libro está íntegra.
    bitacora    que la cadena de la bitácora está íntegra.
    plazos      que ninguna obligación ni acción con plazo está vencida.
    secretos    que están los secretos obligatorios para el modo vigente.

    Cada una dice `ok`, un detalle y si es `grave`. Grave es lo que compromete
    la plata o la prueba: base, libro, bitácora. El resto es trabajo pendiente.

QUIEN AVISA

    El trabajador llama a `vigilar` cada cinco minutos. Cuando la salud pasa
    de bien a mal (o de mal a bien) se avisa UNA vez, por los `AVISADORES`
    que `server.py` registró (la campana del equipo y el correo de la
    aplicación; el núcleo no los conoce). Y queda en la bitácora. No se
    avisa en cada vuelta: un aviso que se repite cada cinco minutos es un
    aviso que alguien silencia.

LA SONDA ANONIMA

    `server.py` publica `/api/health/nucleo`, que contesta 200 o 503 con
    sólo `{"ok": …}` y nada más, para el monitor externo que no puede
    loguearse. Con el núcleo apagado contesta 404, como todo lo demás.
"""
import logging
import pathlib
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, text

from nucleo import base, libro, modo
from nucleo.esquema import trabajos
from nucleo.operacion import bitacora, secretos as _secretos

logger = logging.getLogger("nucleo.salud")

CADA_SEGUNDOS = 300
LATIDO_MAXIMO = timedelta(minutes=5)
GRAVES = ("base", "libro", "bitacora")

# async (titulo: str, mensaje: str, grave: bool) -> None. Los llena server.py.
AVISADORES: list = []

_estado = {"ultimo_ok": None, "ultima_revision": None, "ultimas_fallas": []}


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ultima_migracion_escrita() -> Optional[str]:
    carpeta = pathlib.Path(__file__).resolve().parents[1] / "migraciones" / "versiones"
    revisiones = []
    for archivo in sorted(carpeta.glob("0*.py")):
        m = re.search(r'^revision\s*=\s*"([^"]+)"', archivo.read_text(encoding="utf-8"), re.M)
        if m:
            revisiones.append(m.group(1))
    return max(revisiones) if revisiones else None


async def revisar(ahora: Optional[datetime] = None, modo_vigente: Optional[int] = None) -> dict:
    from nucleo import trabajador
    from nucleo.cumplimiento import calendario
    ahora = ahora or datetime.now(timezone.utc)
    if modo_vigente is None:
        modo_vigente = await modo.leer()
    comprobaciones = []

    def agregar(nombre, ok, detalle):
        comprobaciones.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle, "grave": nombre in GRAVES})

    if not base.hay_base():
        agregar("base", False, f"sin base: falta {base.VARIABLE}")
        return {"ok": False, "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}
    try:
        async with base.sesion() as s:
            await s.execute(text("SELECT 1"))
            agregar("base", True, base.descripcion_de_la_url())
            try:
                aplicada = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
            except Exception:
                aplicada = None
            escrita = ultima_migracion_escrita()
            if aplicada is None:
                agregar("esquema", True, "sin tabla de migraciones: esquema creado directo (tests o vista previa)")
            else:
                agregar("esquema", aplicada == escrita, f"aplicada {aplicada}, última escrita {escrita}")
            muertos = int((await s.execute(select(func.count()).select_from(trabajos).where(trabajos.c.estado == "muerto"))).scalar_one())
            agregar("cola", muertos == 0, f"{muertos} trabajos muertos" if muertos else "sin trabajos muertos")
            cadena = await libro.verificar_cadena(s)
            agregar("libro", cadena["ok"], f"{cadena['asientos']} asientos" + ("" if cadena["ok"] else f" · rota en {cadena['roto_en']}: {cadena['motivo']}"))
            cb = await bitacora.verificar_cadena(s)
            agregar("bitacora", cb["ok"], f"{cb['renglones']} renglones" + ("" if cb["ok"] else f" · rota en {cb['roto_en']}: {cb['motivo']}"))
    except Exception as e:
        agregar("base", False, f"{type(e).__name__}: {e}")
        return {"ok": False, "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}

    t = trabajador.estado()
    ultima = datetime.fromisoformat(t["ultima_vuelta"]) if t.get("ultima_vuelta") else None
    late = t.get("corriendo") and ultima is not None and ahora - _aware(ultima) <= LATIDO_MAXIMO
    agregar("trabajador", late, ("corriendo, último latido " + ultima.isoformat()) if late else
            ("no está corriendo" if not t.get("corriendo") else f"sin latir desde {ultima.isoformat() if ultima else 'el arranque'}"))
    cal = await calendario.resumen()
    agregar("plazos", cal["vencidas"] == 0 and cal["acciones_vencidas"] == 0,
            f"{cal['vencidas']} obligaciones vencidas · {cal['acciones_vencidas']} acciones vencidas")
    faltan = _secretos.faltantes(modo_vigente)
    agregar("secretos", not faltan, ("faltan: " + ", ".join(faltan)) if faltan else f"los obligatorios en {modo.NOMBRES[modo_vigente]} están")
    return {"ok": all(c["ok"] for c in comprobaciones), "revisado_en": ahora.isoformat(), "comprobaciones": comprobaciones}


async def avisar(titulo: str, mensaje: str, grave: bool) -> None:
    for avisador in list(AVISADORES):
        try:
            await avisador(titulo, mensaje, grave)
        except Exception:
            logger.exception("nucleo: un avisador de salud falló")


async def vigilar(ahora: Optional[datetime] = None, forzar: bool = False) -> Optional[dict]:
    """Cada `CADA_SEGUNDOS`: revisa y avisa sólo cuando el estado CAMBIA."""
    ahora = ahora or datetime.now(timezone.utc)
    ultima = _estado["ultima_revision"]
    if not forzar and ultima is not None and (ahora - ultima).total_seconds() < CADA_SEGUNDOS:
        return None
    _estado["ultima_revision"] = ahora
    r = await revisar(ahora=ahora)
    fallas = [c for c in r["comprobaciones"] if not c["ok"]]
    _estado["ultimas_fallas"] = [c["nombre"] for c in fallas]
    anterior = _estado["ultimo_ok"]
    _estado["ultimo_ok"] = r["ok"]
    if anterior is None or anterior == r["ok"]:
        return r
    if r["ok"]:
        titulo, mensaje, grave = "El núcleo volvió a estar sano", "Todas las comprobaciones pasan.", False
    else:
        grave = any(c["grave"] for c in fallas)
        titulo = "El núcleo NO está sano" + (" (grave)" if grave else "")
        mensaje = "; ".join(f"{c['nombre']}: {c['detalle']}" for c in fallas)
    await avisar(titulo, mensaje, grave)
    await bitacora.anotar_sin_romper(actor="salud", accion="salud.cambio", objetivo="nucleo",
                                     antes={"ok": anterior}, despues={"ok": r["ok"], "fallas": _estado["ultimas_fallas"]}, detalle=titulo)
    return r


async def ok_para_la_sonda() -> bool:
    """Lo que la sonda anónima contesta: lo ÚLTIMO que vio la vigilancia,
    sin recalcular nada. Una sonda que cualquiera puede llamar y que
    recorre el libro entero es una puerta para tumbar el servidor; ésta
    lee un valor guardado. Sólo la primera vez, si la vigilancia todavía no
    corrió, revisa una vez y lo guarda."""
    if _estado["ultimo_ok"] is None:
        await vigilar(forzar=True)
    return bool(_estado["ultimo_ok"])


def estado() -> dict:
    return {"ultimo_ok": _estado["ultimo_ok"], "ultima_revision": _estado["ultima_revision"].isoformat() if _estado["ultima_revision"] else None,
            "ultimas_fallas": list(_estado["ultimas_fallas"]), "avisadores": len(AVISADORES)}


def reiniciar_para_tests():
    _estado.update({"ultimo_ok": None, "ultima_revision": None, "ultimas_fallas": []})
