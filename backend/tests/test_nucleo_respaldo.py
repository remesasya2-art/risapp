"""
tests/test_nucleo_respaldo.py — la exportación de lo que se conserva, su
firma, y la comprobación que la prueba.
"""
import asyncio
import inspect
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from _nucleo_comun import cuenta_aprobada                                     # noqa: E402
from conftest import usar_base                                                # noqa: E402
from nucleo import base, comandos, plan                                       # noqa: E402
from nucleo.operacion import bitacora, respaldo                               # noqa: E402


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia():
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())
    usar_base(mongomock_motor.AsyncMongoMockClient()["nucleo_respaldo"])

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())


def con_movimientos():
    a, b = cuenta_aprobada("u_ana"), cuenta_aprobada("u_beto")
    ya(comandos.acreditar(cuenta_id=a, monto="100.00", referencia="in-1", actor="t", fecha=date(2026, 9, 3)))
    ya(comandos.transferir(desde=a, hacia=b, monto="40.00", referencia="tr-1", actor="t", fecha=date(2026, 9, 4)))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 4), actor="t"))
    return a, b


def test_EL_RESPALDO_LLEVA_LO_QUE_SE_CONSERVA_Y_NADA_DEL_SIMULADOR_NI_DE_LA_COLA(monkeypatch):
    monkeypatch.delenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", raising=False)
    con_movimientos()
    ya(bitacora.anotar_sin_romper(actor="ana", accion="cierre.dia", objetivo="2026-09-04"))
    r = ya(respaldo.crear(actor="ana"))
    lineas = r["contenido"].strip().split("\n")
    cabecera, cierre = json.loads(lineas[0]), json.loads(lineas[-1])
    assert cabecera["tipo"] == "respaldo_nucleo" and cabecera["actor"] == "ana"
    assert cierre["tipo"] == "fin" and cierre["filas"] == len(lineas) - 2 == r["filas"]
    tablas = {json.loads(l)["tabla"] for l in lineas[1:-1]}
    assert {"asientos", "partidas", "cierres", "cuentas", "titulares", "plan_de_cuentas", "bitacora"} <= tablas
    assert not tablas & {"eventos", "trabajos", "sim_claves", "sim_personas", "sim_listas"}
    assert r["tablas"]["asientos"] == 2 and r["tablas"]["partidas"] == 4 and r["tablas"]["cierres"] == 1
    assert r["firmado"] is False and r["firma"] is None
    assert [x["accion"] for x in ya(bitacora.listar())][0] == "respaldo.creado"
    assert ya(respaldo.listar())[0]["hash"] == r["hash"] and "contenido" not in ya(respaldo.listar())[0]


def test_LA_COMPROBACION_PASA_CON_EL_ARCHIVO_INTACTO_Y_FALLA_CON_UNO_TOCADO(monkeypatch):
    monkeypatch.setenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", "llave-de-prueba")
    con_movimientos()
    r = ya(respaldo.crear(actor="ana"))
    assert r["firmado"] is True and len(r["firma"]) == 64
    c = ya(respaldo.comprobar_y_anotar(r["contenido"], r["firma"], actor="auditor"))
    assert c["ok"] is True and c["hash_ok"] is True and c["firma"] == "ok" and c["registrado"] is True
    assert c["libro"]["ok"] is True and c["libro"]["asientos"] == 2 and c["bitacora"]["ok"] is True
    assert ya(respaldo.listar())[0]["comprobacion"]["ok"] is True and ya(respaldo.listar())[0]["comprobado_en"]
    # Un byte cambiado en una fila: el hash del cierre ya no coincide.
    tocado = r["contenido"].replace('"descripcion":"Acreditación"', '"descripcion":"Acreditacion"', 1)
    assert tocado != r["contenido"]
    c = respaldo.comprobar(tocado, r["firma"])
    assert c["ok"] is False and c["hash_ok"] is False and "alterado" in c["motivo"]
    # Una firma ajena, con el archivo intacto.
    c = respaldo.comprobar(r["contenido"], "0" * 64)
    assert c["ok"] is False and c["firma"] == "invalida"
    # Sin la llave, la firma no se puede verificar y se dice.
    monkeypatch.delenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO")
    assert respaldo.comprobar(r["contenido"], r["firma"])["firma"] == "sin_llave"


def test_UN_ASIENTO_ALTERADO_ANTES_DE_EXPORTAR_SE_VE_EN_LA_COMPROBACION():
    """El hash del archivo está bien (el archivo dice lo que hay en la base),
    pero el libro exportado no encadena: alguien tocó la base."""
    from nucleo.esquema import asientos
    con_movimientos()

    async def tocar():
        async with base.sesion() as s:
            await s.execute(asientos.update().where(asientos.c.numero == 1).values(descripcion="otra"))
    ya(tocar())
    r = ya(respaldo.crear(actor="ana"))
    c = respaldo.comprobar(r["contenido"])
    assert c["hash_ok"] is True and c["ok"] is False and c["libro"]["roto_en"] == 1 and "no coincide" in c["motivo"]


def test_UN_LIBRO_EXPORTADO_QUE_NO_ENCADENA_SE_VE_AUNQUE_CADA_ASIENTO_SEA_VALIDO():
    """Cada asiento coincide con su propio hash, pero el segundo apunta a un
    anterior que no es el primero: la comprobación mira el eslabón, no sólo
    el contenido."""
    from nucleo import libro
    con_movimientos()
    r = ya(respaldo.crear(actor="ana"))
    filas = [json.loads(l) for l in r["contenido"].strip().split("\n")[1:-1]]
    asientos_ = [f["fila"] for f in filas if f["tabla"] == "asientos"]
    partidas_ = [f["fila"] for f in filas if f["tabla"] == "partidas"]
    segundo = next(a for a in asientos_ if a["numero"] == 2)
    segundo["hash_previo"] = "f" * 64
    lineas = [libro.Partida(cuenta_contable=p["cuenta_contable"], debe=p["debe"], haber=p["haber"], cuenta=p["cuenta"])
              for p in sorted(partidas_, key=lambda p: p["orden"]) if p["asiento"] == 2]
    segundo["hash"] = libro._hash_de(2, date.fromisoformat(segundo["fecha"]), segundo["descripcion"], segundo["referencia"],
                                     segundo["comando"], segundo["actor"], lineas, segundo["hash_previo"])
    c = respaldo._comprobar_libro(asientos_, partidas_)
    assert c["ok"] is False and c["roto_en"] == 2 and "no encadena" in c["motivo"]


def test_un_archivo_que_no_es_un_respaldo_se_rechaza_con_motivo():
    assert "cabecera" in respaldo.comprobar("")["motivo"]
    assert "JSON" in respaldo.comprobar("hola\nchau\n")["motivo"]
    assert "no es un respaldo" in respaldo.comprobar('{"tipo":"otro"}\n{"tipo":"fin"}\n')["motivo"]


def test_el_orden_de_las_tablas_respeta_las_referencias():
    """Cada tabla exportada va después de las que referencia: un restaurador
    que cargue de arriba abajo no choca con una clave ajena."""
    vistas = []
    for t in respaldo.TABLAS_QUE_SE_CONSERVAN:
        for fk in t.foreign_keys:
            referida = fk.column.table.name
            assert referida in vistas or referida == t.name, (t.name, referida)
        vistas.append(t.name)


def test_no_hay_funcion_que_borre_respaldos_y_el_contenido_no_se_guarda():
    nombres = [n for n, _ in inspect.getmembers(respaldo, inspect.isfunction)]
    assert not [n for n in nombres if n.startswith(("borrar", "eliminar"))]
    assert "respaldos.delete(" not in inspect.getsource(respaldo)
    from nucleo.esquema import respaldos
    assert "contenido" not in {c.name for c in respaldos.columns}
