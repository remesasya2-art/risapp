"""
tests/test_respaldo_de_mongo.py — la exportación de la base de la
aplicación, su firma, y la comprobación que prueba que se puede leer.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")
from bson import json_util                                    # noqa: E402
from bson.binary import Binary                                # noqa: E402

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services import respaldo_de_mongo as resp                # noqa: E402
from services.money import to_decimal128                      # noqa: E402

JEFA = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base(monkeypatch):
    monkeypatch.delenv("LLAVE_DE_RESPALDO", raising=False)
    monkeypatch.delenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", raising=False)
    m = mongomock_motor.AsyncMongoMockClient()["respaldo_mongo"]
    usar_base(m)
    ya(m.users.insert_one({"user_id": "u1", "email": "u1@ejemplo.test", "balance_ris": to_decimal128("10.50"),
                           "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}))
    ya(m.verifications.insert_one({"user_id": "u1", "documento": Binary(b"\x00\x01cifrado")}))
    ya(m.ledger.insert_one({"user_id": "u1", "amount": to_decimal128("10.50")}))
    ya(m.user_sessions.insert_one({"user_id": "u1", "token": "secreto-de-sesion"}))       # no se conserva
    ya(m.bcv_rates.insert_one({"rate": 36.5}))                                            # se regenera sola
    return m


def test_EL_RESPALDO_LLEVA_LO_QUE_SE_CONSERVA_CON_SUS_TIPOS_Y_NO_LAS_SESIONES(base):
    r = ya(resp.crear(base, quien=JEFA))
    lineas = r["contenido"].strip().split("\n")
    cabecera, cierre = json_util.loads(lineas[0]), json_util.loads(lineas[-1])
    assert cabecera["tipo"] == "respaldo_risapp" and cierre["documentos"] == 3 == r["documentos"]
    filas = [json_util.loads(l) for l in lineas[1:-1]]
    assert {f["coleccion"] for f in filas} == {"users", "verifications", "ledger"}
    assert "secreto-de-sesion" not in r["contenido"] and "user_sessions" not in {f["coleccion"] for f in filas}
    usuario = next(f["doc"] for f in filas if f["coleccion"] == "users")
    assert usuario["balance_ris"].to_decimal() == Decimal("10.50")                       # Decimal128 conservado
    assert usuario["created_at"].year == 2026                                            # fecha conservada
    assert next(f["doc"] for f in filas if f["coleccion"] == "verifications")["documento"] == b"\x00\x01cifrado"
    assert r["firmado"] is False and r["firma"] is None
    assert ya(resp.listar(base))[0]["hash"] == r["hash"] and "contenido" not in ya(resp.listar(base))[0]
    assert ya(base.auditoria.find_one({"accion": "respaldo.creado"}))["actor"]["user_id"] == "u_jefa"


def test_LA_COMPROBACION_PASA_CON_EL_ARCHIVO_INTACTO_Y_FALLA_CON_UNO_TOCADO(base, monkeypatch):
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    assert r["firmado"] is True and len(r["firma"]) == 64
    c = ya(resp.comprobar_y_anotar(base, r["contenido"], r["firma"], quien=JEFA))
    assert c["ok"] is True and c["hash_ok"] is True and c["firma"] == "ok" and c["registrado"] is True
    assert set(c["colecciones"]) == {"users", "verifications", "ledger"} and c["documentos"] == 3
    assert ya(resp.listar(base))[0]["comprobacion"]["ok"] is True
    tocado = r["contenido"].replace('"10.50"', '"99.50"', 1)
    assert tocado != r["contenido"]
    c = resp.comprobar(tocado, r["firma"])
    assert c["ok"] is False and c["hash_ok"] is False and "alterado" in c["motivo"]
    assert resp.comprobar(r["contenido"], "0" * 64)["firma"] == "invalida"
    monkeypatch.delenv("LLAVE_DE_RESPALDO")
    assert resp.comprobar(r["contenido"], r["firma"])["firma"] == "sin_llave"
    assert ya(base.auditoria.count_documents({"accion": "respaldo.comprobado"})) == 1


def test_la_llave_del_nucleo_sirve_si_no_hay_una_propia(monkeypatch):
    monkeypatch.setenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", "la-del-nucleo")
    assert resp.hay_llave() and resp.firmar("x") is not None
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "la-propia")
    import hashlib, hmac
    assert resp.firmar("x") == hmac.new(b"la-propia", b"x", hashlib.sha256).hexdigest()


def test_UN_DOCUMENTO_SACADO_CON_EL_CIERRE_REHECHO_SE_NOTA_POR_LA_CUENTA(base):
    """Alguien saca una línea y rehace el hash del cierre para que coincida:
    la cantidad de documentos del cierre sigue siendo la original, y eso lo
    delata."""
    import hashlib
    r = ya(resp.crear(base, quien=JEFA))
    lineas = r["contenido"].strip().split("\n")
    cierre = json_util.loads(lineas[-1])
    sin_una = lineas[:-2] + [lineas[-1]]                       # se saca el último documento
    cuerpo = "\n".join(sin_una[:-1]) + "\n"
    cierre["hash"] = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
    rehecho = cuerpo + json_util.dumps(cierre, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True, separators=(",", ":")) + "\n"
    c = resp.comprobar(rehecho)
    assert c["hash_ok"] is True and c["ok"] is False and "el cierre dice 3 documentos y hay 2" in c["motivo"]


def test_un_archivo_que_no_es_un_respaldo_se_rechaza_con_motivo():
    assert "cabecera" in resp.comprobar("")["motivo"]
    assert "JSON" in resp.comprobar("hola\nchau\n")["motivo"]
    assert "no es un respaldo" in resp.comprobar('{"tipo":"otro"}\n{"tipo":"fin"}\n')["motivo"]


def test_las_colecciones_que_se_conservan_no_incluyen_lo_efimero():
    for efimera in ("user_sessions", "password_recovery", "twofa_pending", "pending_verifications", "notifications", "bcv_rates", "rates", "counters", "contadores"):
        assert efimera not in resp.COLECCIONES_QUE_SE_CONSERVAN, efimera
    for vital in ("users", "transactions", "ledger", "verifications", "auditoria", "config", "gestor_pix_payments"):
        assert vital in resp.COLECCIONES_QUE_SE_CONSERVAN, vital


# ─── por HTTP ─────────────────────────────────────────────────────────────

def test_por_http_solo_el_super_administrador_y_la_lista_no_trae_el_contenido(base, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.respaldo_admin import router
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    c = TestClient(app)
    assert c.get("/api/admin/respaldos").status_code in (401, 403)
    assert c.post("/api/admin/respaldos").status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    r = c.get("/api/admin/respaldos")
    assert r.status_code == 200 and r.json()["llave_configurada"] is True and "users" in r.json()["colecciones_que_se_conservan"]
    r = c.post("/api/admin/respaldos")
    assert r.status_code == 200 and r.json()["firmado"] is True and r.json()["contenido"].startswith('{"actor"')
    contenido, firma = r.json()["contenido"], r.json()["firma"]
    assert c.get("/api/admin/respaldos").json()["respaldos"][0]["contenido"] is None
    r = c.post("/api/admin/respaldos/comprobar", json={"contenido": contenido, "firma": firma})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["registrado"] is True
    r = c.post("/api/admin/respaldos/comprobar", json={"contenido": contenido + "x", "firma": firma})
    assert r.status_code == 200 and r.json()["ok"] is False
