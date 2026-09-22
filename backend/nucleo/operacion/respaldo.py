"""
El respaldo de lo que la ley obliga a conservar, y la prueba de que sirve.

QUE SE EXPORTA

    Las tablas de conservación obligatoria: el libro entero (plan, cuentas,
    asientos, partidas, cierres), los legajos y sus verificaciones y cruces,
    las operaciones con su línea de tiempo y los avisos del riel, las alertas,
    los casos con sus notas y las comunicaciones al COAF, los reportes, los
    incidentes con sus notas, los reclamos, la bitácora y las aprobaciones.
    NO se exportan la cola (eventos y trabajos son operación del momento) ni
    las tablas del simulador (son datos de mentira).

    El formato es una línea JSON por fila (JSON Lines): se lee con cualquier
    herramienta, se puede recorrer sin cargarlo entero, y una fila rota no
    rompe el archivo. La primera línea es la cabecera; la última, el cierre,
    con la cantidad de filas y el hash SHA-256 de todo lo anterior.

LA FIRMA

    Si el secreto `llave_de_respaldo` está configurado, el archivo se firma
    con HMAC-SHA256 y la firma viaja aparte. Quien tenga el archivo y la
    llave puede probar que salió de acá y que nadie lo tocó. Sin llave, el
    respaldo sale igual —un respaldo sin firma es mejor que ninguno— y lo
    dice: `firmado: false`.

LA COMPROBACION

    Un respaldo que no se probó es una esperanza. `comprobar` toma el archivo
    (y la firma) y verifica: que el hash del cierre coincide con el contenido,
    que la firma es la de la llave, que la cadena de hashes del libro se
    recompone desde las filas exportadas y llega íntegra, y lo mismo con la
    bitácora. Es lo que un auditor haría con el archivo en la mano, y es lo
    que hay que hacer cada tanto para saber que el respaldo se puede leer.

    El contenido NO se guarda en la base: el sentido de un respaldo es estar
    en otro lado. La tabla `respaldos` guarda cuándo, quién, cuánto, el hash
    y el resultado de la última comprobación.
"""
import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from nucleo import base, libro
from nucleo.esquema import (
    HASH_DEL_PRINCIPIO, alertas, aprobaciones, asientos, avisos_riel, bitacora as tabla_bitacora, caso_notas, casos,
    cierres, comunicaciones, cruces, cuentas, incidente_notas, incidentes, operacion_estados, operaciones, partidas,
    plan_de_cuentas, reclamos, reportes, respaldos, titulares, verificaciones,
)
from nucleo.operacion import bitacora, secretos as _secretos

VERSION = 1
TIPO = "respaldo_nucleo"

# En este orden: cada tabla después de las que referencia, para que un
# restaurador que las cargue de arriba abajo no choque con una clave ajena.
TABLAS_QUE_SE_CONSERVAN = (
    plan_de_cuentas, cuentas, asientos, partidas, cierres,
    titulares, verificaciones, cruces,
    operaciones, operacion_estados, avisos_riel,
    casos, alertas, caso_notas, comunicaciones,
    reportes, incidentes, incidente_notas, reclamos,
    tabla_bitacora, aprobaciones,
)


class RespaldoInvalido(ValueError):
    pass


def _ahora():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _valor(v):
    if isinstance(v, datetime):
        return _aware(v).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def _linea(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def firmar(contenido: str) -> Optional[str]:
    llave = _secretos.secretos().leer("llave_de_respaldo")
    if not llave:
        return None
    return hmac.new(llave.encode("utf-8"), contenido.encode("utf-8"), hashlib.sha256).hexdigest()


async def exportar(sesion, *, actor: str, ahora: Optional[datetime] = None) -> tuple:
    """(contenido, firma o None, resumen)."""
    ahora = ahora or _ahora()
    lineas = [_linea({"tipo": TIPO, "version": VERSION, "momento": ahora.isoformat(), "actor": actor,
                      "tablas": [t.name for t in TABLAS_QUE_SE_CONSERVAN]})]
    por_tabla = {}
    for tabla in TABLAS_QUE_SE_CONSERVAN:
        orden = [c for c in tabla.primary_key.columns]
        filas = (await sesion.execute(select(tabla).order_by(*orden))).all()
        por_tabla[tabla.name] = len(filas)
        for f in filas:
            lineas.append(_linea({"tabla": tabla.name, "fila": {k: _valor(v) for k, v in f._mapping.items()}}))
    cuerpo = "\n".join(lineas) + "\n"
    total = sum(por_tabla.values())
    cierre = _linea({"tipo": "fin", "filas": total, "hash": _hash(cuerpo)})
    contenido = cuerpo + cierre + "\n"
    firma = firmar(contenido)
    resumen = {"filas": total, "tablas": por_tabla, "bytes": len(contenido.encode("utf-8")),
               "hash": _hash(contenido), "firmado": firma is not None}
    return contenido, firma, resumen


async def crear(*, actor: str, ahora: Optional[datetime] = None) -> dict:
    """Exporta, registra y anota. Devuelve el contenido para que quien lo
    pidió lo guarde afuera."""
    ahora = ahora or _ahora()
    async with base.sesion() as s:
        contenido, firma, resumen = await exportar(s, actor=actor, ahora=ahora)
        r = await s.execute(respaldos.insert().values(
            momento=ahora, actor=actor, filas=resumen["filas"], tablas=json.dumps(resumen["tablas"]),
            bytes=resumen["bytes"], hash=resumen["hash"], firmado=resumen["firmado"]))
        await bitacora.anotar(s, actor=actor, accion="respaldo.creado", objetivo=resumen["hash"][:16],
                              despues={"filas": resumen["filas"], "bytes": resumen["bytes"], "firmado": resumen["firmado"]}, ahora=ahora)
        fila = _fila((await s.execute(select(respaldos).where(respaldos.c.id == r.inserted_primary_key[0]))).first())
    return {**fila, "contenido": contenido, "firma": firma}


def comprobar(contenido: str, firma: Optional[str] = None) -> dict:
    """Lo que un auditor haría con el archivo en la mano."""
    salida = {"ok": False, "hash_ok": False, "firma": "sin_firma", "filas": 0, "tablas": {},
              "libro": None, "bitacora": None, "motivo": None}
    lineas = contenido.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    if len(lineas) < 2:
        salida["motivo"] = "el archivo no tiene cabecera y cierre"
        return salida
    try:
        cabecera, cierre = json.loads(lineas[0]), json.loads(lineas[-1])
    except json.JSONDecodeError:
        salida["motivo"] = "la cabecera o el cierre no son JSON"
        return salida
    if cabecera.get("tipo") != TIPO or cierre.get("tipo") != "fin":
        salida["motivo"] = "no es un respaldo del núcleo"
        return salida
    cuerpo = "\n".join(lineas[:-1]) + "\n"
    salida["hash_ok"] = _hash(cuerpo) == cierre.get("hash")
    if not salida["hash_ok"]:
        salida["motivo"] = "el hash del cierre no coincide con el contenido: el archivo fue alterado o está incompleto"
        return salida
    if firma:
        llave = _secretos.secretos().leer("llave_de_respaldo")
        if not llave:
            salida["firma"] = "sin_llave"
        else:
            esperada = hmac.new(llave.encode("utf-8"), contenido.encode("utf-8"), hashlib.sha256).hexdigest()
            salida["firma"] = "ok" if hmac.compare_digest(esperada, firma) else "invalida"
            if salida["firma"] == "invalida":
                salida["motivo"] = "la firma no es la de la llave de respaldo"
                return salida
    filas = [json.loads(l) for l in lineas[1:-1]]
    salida["filas"] = len(filas)
    if salida["filas"] != cierre.get("filas"):
        salida["motivo"] = f"el cierre dice {cierre.get('filas')} filas y hay {salida['filas']}"
        return salida
    for f in filas:
        salida["tablas"][f["tabla"]] = salida["tablas"].get(f["tabla"], 0) + 1
    salida["libro"] = _comprobar_libro([f["fila"] for f in filas if f["tabla"] == "asientos"],
                                       [f["fila"] for f in filas if f["tabla"] == "partidas"])
    salida["bitacora"] = _comprobar_bitacora([f["fila"] for f in filas if f["tabla"] == "bitacora"])
    salida["ok"] = salida["libro"]["ok"] and salida["bitacora"]["ok"] and salida["firma"] != "invalida"
    if not salida["ok"]:
        salida["motivo"] = salida["libro"].get("motivo") or salida["bitacora"].get("motivo")
    return salida


def _comprobar_libro(filas_asientos: list, filas_partidas: list) -> dict:
    por_asiento = {}
    for p in sorted(filas_partidas, key=lambda p: (p["asiento"], p["orden"])):
        por_asiento.setdefault(p["asiento"], []).append(
            libro.Partida(cuenta_contable=p["cuenta_contable"], debe=p["debe"], haber=p["haber"], cuenta=p["cuenta"]))
    previo, esperado = HASH_DEL_PRINCIPIO, 1
    for a in sorted(filas_asientos, key=lambda a: a["numero"]):
        if a["numero"] != esperado:
            return {"ok": False, "asientos": len(filas_asientos), "roto_en": a["numero"], "motivo": f"hueco en la numeración del libro: esperaba {esperado}"}
        if a["hash_previo"] != previo:
            return {"ok": False, "asientos": len(filas_asientos), "roto_en": a["numero"], "motivo": "el libro exportado no encadena"}
        recalculado = libro._hash_de(a["numero"], date.fromisoformat(a["fecha"]), a["descripcion"], a["referencia"], a["comando"],
                                     a["actor"], por_asiento.get(a["numero"], []), a["hash_previo"])
        if recalculado != a["hash"]:
            return {"ok": False, "asientos": len(filas_asientos), "roto_en": a["numero"], "motivo": "un asiento exportado no coincide con su hash"}
        previo, esperado = a["hash"], esperado + 1
    return {"ok": True, "asientos": len(filas_asientos), "roto_en": None, "motivo": None, "hash_final": previo}


def _comprobar_bitacora(filas: list) -> dict:
    previo = HASH_DEL_PRINCIPIO
    for b in sorted(filas, key=lambda b: b["id"]):
        if b["hash_previo"] != previo:
            return {"ok": False, "renglones": len(filas), "roto_en": b["id"], "motivo": "la bitácora exportada no encadena"}
        if bitacora.hash_de(datetime.fromisoformat(b["momento"]), b["actor"], b["accion"], b["objetivo"], b["antes"], b["despues"],
                            b["detalle"], b["hash_previo"]) != b["hash"]:
            return {"ok": False, "renglones": len(filas), "roto_en": b["id"], "motivo": "un renglón exportado de la bitácora no coincide con su hash"}
        previo = b["hash"]
    return {"ok": True, "renglones": len(filas), "roto_en": None, "motivo": None, "hash_final": previo}


async def comprobar_y_anotar(contenido: str, firma: Optional[str], *, actor: str, ahora: Optional[datetime] = None) -> dict:
    """Comprueba y, si el archivo es uno de los registrados, guarda el
    resultado en su fila. Siempre queda en la bitácora."""
    ahora = ahora or _ahora()
    resultado = comprobar(contenido, firma)
    h = _hash(contenido)
    async with base.sesion() as s:
        conocido = (await s.execute(select(respaldos).where(respaldos.c.hash == h))).first()
        if conocido is not None:
            await s.execute(respaldos.update().where(respaldos.c.id == conocido.id).values(
                comprobado_en=ahora, comprobacion=json.dumps(resultado, ensure_ascii=False, default=str)))
        await bitacora.anotar(s, actor=actor, accion="respaldo.comprobado", objetivo=h[:16],
                              despues={"ok": resultado["ok"], "firma": resultado["firma"], "filas": resultado["filas"],
                                       "registrado": conocido is not None}, detalle=resultado["motivo"], ahora=ahora)
    return {**resultado, "hash": h, "registrado": conocido is not None}


# ─── para mirar ───────────────────────────────────────────────────────────

def _fila(r) -> dict:
    return {"id": r.id, "momento": _aware(r.momento).isoformat(), "actor": r.actor, "filas": r.filas,
            "tablas": json.loads(r.tablas), "bytes": r.bytes, "hash": r.hash, "firmado": r.firmado,
            "comprobado_en": _aware(r.comprobado_en).isoformat() if r.comprobado_en else None,
            "comprobacion": json.loads(r.comprobacion) if r.comprobacion else None}


async def listar(limite: int = 30) -> list:
    async with base.sesion() as s:
        return [_fila(r) for r in (await s.execute(select(respaldos).order_by(respaldos.c.id.desc()).limit(limite))).all()]
