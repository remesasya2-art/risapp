"""
tests/test_nucleo_rutas.py — el laboratorio del núcleo por HTTP, como lo usa
la pestaña del panel.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from nucleo import base as nucleo_base, modo                  # noqa: E402

SUPER = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nucleo.rutas import router
    from routes import dependencies as deps
    base = mongomock_motor.AsyncMongoMockClient()["nucleo_rutas"]
    usar_base(base)
    ya(base.config.insert_one({"clave": modo.CLAVE, "valor": str(modo.LABORATORIO)}))
    nucleo_base.usar("sqlite+aiosqlite://")
    ya(nucleo_base.crear_todo())
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_super_admin] = lambda: SUPER
    return TestClient(app)


def test_el_recorrido_del_laboratorio(cliente):
    r = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_ana"})
    assert r.status_code == 200, r.text
    a = r.json()["id"]
    b = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_beto"}).json()["id"]

    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "in-1"})
    assert r.status_code == 200 and r.json()["numero"] == 1
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "transferir", "desde": a, "hacia": b, "monto": "40.00", "referencia": "tr-1"})
    assert r.status_code == 200 and r.json()["numero"] == 2

    cuentas = {c["id"]: c["saldo"] for c in cliente.get("/api/nucleo/laboratorio/cuentas").json()}
    assert cuentas[a] == "60.00" and cuentas[b] == "40.00"

    libro = cliente.get("/api/nucleo/laboratorio/libro").json()
    assert [x["numero"] for x in libro] == [2, 1]
    assert libro[1]["partidas"][0]["debe"] == 10000

    assert cliente.get("/api/nucleo/laboratorio/balance").json()["cuadra"] is True
    assert cliente.get("/api/nucleo/laboratorio/cadena").json()["ok"] is True

    r = cliente.post("/api/nucleo/laboratorio/cierres", json={"dia": "2026-09-21", "nota": "prueba"})
    assert r.status_code == 200 and r.json()["hasta_asiento"] == 2
    assert cliente.get("/api/nucleo/laboratorio/cierres").json()[0]["dia"] == "2026-09-21"

    e = cliente.get("/api/nucleo/estado").json()
    assert e["cuentas"] == 2 and e["asientos"] == 2 and e["ultimo_cierre"] == "2026-09-21"
    assert e["cadena"]["ok"] is True


def test_los_errores_del_libro_llegan_como_mensajes_claros(cliente):
    a = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_ana"}).json()["id"]
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "debitar", "cuenta": a, "monto": "5.00", "referencia": "d1"})
    assert r.status_code == 400 and "Saldo insuficiente" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "1.005", "referencia": "d2"})
    assert r.status_code == 400 and "dos decimales" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": "cta_nadie", "monto": "1.00", "referencia": "d3"})
    assert r.status_code == 400 and "inexistente" in r.json()["detail"]
    cliente.post("/api/nucleo/laboratorio/cierres", json={"dia": "2099-01-01"})
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "1.00", "referencia": "d4"})
    assert r.status_code == 409 and "cerrado" in r.json()["detail"]


def test_LA_MISMA_REFERENCIA_POR_HTTP_NO_DUPLICA(cliente):
    a = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_ana"}).json()["id"]
    cuerpo = {"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "unica"}
    n1 = cliente.post("/api/nucleo/laboratorio/movimientos", json=cuerpo).json()["numero"]
    n2 = cliente.post("/api/nucleo/laboratorio/movimientos", json=cuerpo).json()["numero"]
    assert n1 == n2
    assert cliente.get("/api/nucleo/laboratorio/cuentas").json()[0]["saldo"] == "100.00"


def test_sin_base_configurada_el_laboratorio_dice_que_falta(cliente, monkeypatch):
    monkeypatch.setattr(nucleo_base, "_motor", None)
    monkeypatch.delenv(nucleo_base.VARIABLE, raising=False)
    r = cliente.get("/api/nucleo/laboratorio/cuentas")
    assert r.status_code == 503 and nucleo_base.VARIABLE in r.json()["detail"]
    e = cliente.get("/api/nucleo/estado").json()
    assert e["conectada"] is False and e["base"] == "sin configurar"


# ─── la cola por HTTP ─────────────────────────────────────────────────────

def test_la_cola_por_http_encola_procesa_y_revive(cliente):
    a = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_ana"}).json()["id"]
    cliente.post("/api/nucleo/laboratorio/movimientos",
                 json={"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "in-1"})
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "carga": {"mensaje": "hola"}})
    assert r.status_code == 200 and r.json()["nuevo"] is True, r.text
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "fallar", "clave": "f1"})
    assert r.status_code == 200
    muerto = r.json()["id"]

    r = cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert r.status_code == 200, r.text
    # el asiento dejó un evento, el evento se despachó como trabajo y corrió
    assert r.json() == {"despachados": 1, "corridos": 3, "hechos": 2, "muertos": 0, "reintentan": 1}

    q = cliente.get("/api/nucleo/laboratorio/cola").json()
    assert q["resumen"]["hecho"] == 2 and q["resumen"]["pendiente"] == 1
    assert q["resumen"]["eventos"] == 1 and q["resumen"]["eventos_sin_publicar"] == 0
    assert q["trabajador"]["nombre"]
    por_tipo = {t["tipo"]: t for t in q["trabajos"]}
    assert por_tipo["eco"]["resultado"] == "eco: hola"
    assert por_tipo["avisar_asiento"]["clave"] == "asiento_registrado:asiento:1"
    assert "a propósito" in por_tipo["fallar"]["ultimo_error"] or "Falla" in por_tipo["fallar"]["ultimo_error"]
    assert q["eventos"][0]["tipo"] == "asiento_registrado" and q["eventos"][0]["publicado"]

    # un pendiente no se reintenta a mano: sólo un muerto
    r = cliente.post(f"/api/nucleo/laboratorio/cola/trabajos/{muerto}/reintentar")
    assert r.status_code == 409

    e = cliente.get("/api/nucleo/estado").json()
    assert e["cola"]["pendiente"] == 1 and e["trabajador"]["nombre"]


def test_DESDE_LA_PESTANA_SOLO_SE_ENCOLAN_LOS_DE_LABORATORIO(cliente):
    """Un aviso real no se fabrica a mano desde un botón."""
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "avisar_asiento", "carga": {}})
    assert r.status_code == 422
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "clave": "misma"})
    r2 = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "clave": "misma"})
    assert r.json()["nuevo"] is True and r2.json()["nuevo"] is False and r.json()["id"] == r2.json()["id"]
