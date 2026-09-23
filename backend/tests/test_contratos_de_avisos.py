"""
tests/test_contratos_de_avisos.py — la campana trae de cada aviso lo que sus
pantallas leen, y nada más. Ver models/avisos.py.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
LO_QUE_LEEN_LAS_PANTALLAS = {"notification_id", "title", "message", "type", "data", "read", "created_at"}


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_avisos"]
    usar_base(m)
    ya(m.notifications.insert_many([
        {"notification_id": "n2", "user_id": "u_ana", "ambito": "personal", "title": "Tu envío se completó",
         "message": "Enviamos 1.825,00 Bs a José.", "type": "btc_enviado", "data": {"remesa_id": "r1"},
         "read": False, "created_at": AHORA, "enviado_por": "u_operador", "nota_interna": "cliente frecuente"},
        {"notification_id": "n1", "user_id": "u_ana", "title": "Bienvenida", "message": "Hola",
         "type": "sistema", "read": True, "created_at": AHORA},
    ]))
    return m


def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.notifications import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


SECRETOS = ("u_operador", "cliente frecuente", "nota_interna", '"user_id"', '"ambito"')


def test_LA_CAMPANA_TRAE_LO_QUE_LEE_Y_NADA_MAS(base):
    r = cliente().get("/api/notifications")
    assert r.status_code == 200, r.text
    avisos = {a["notification_id"]: a for a in r.json()}
    assert set(avisos["n2"]) == LO_QUE_LEEN_LAS_PANTALLAS
    assert avisos["n2"]["data"] == {"remesa_id": "r1"}, "la pantalla usa `data` para saber a dónde llevar"
    assert "data" not in avisos["n1"], "lo que el aviso no tiene no sale como null"
    for s in SECRETOS:
        assert s not in r.text, s


def test_EL_CONTADOR(base):
    r = cliente().get("/api/notifications/unread-count")
    assert r.status_code == 200 and r.json() == {"unread_count": 1}


class _BaseQueAnota:
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "notifications":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            def find(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return coleccion.find(filtro, proyeccion, *a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_LA_PROYECCION_SOLA_PIDE_LO_QUE_LEEN_LAS_PANTALLAS(base):
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    cliente().get("/api/notifications")
    (proyeccion,) = anotadas
    assert {c for c, v in proyeccion.items() if v == 1} == LO_QUE_LEEN_LAS_PANTALLAS


def test_EL_CONTRATO_SOLO_CORTA_LO_QUE_SE_COLE(base, monkeypatch):
    import routes.notifications as rutas
    monkeypatch.setattr(rutas, "LO_QUE_VE_DE_UN_AVISO", {"_id": 0})
    r = cliente().get("/api/notifications")
    assert r.status_code == 200, r.text
    for s in SECRETOS:
        assert s not in r.text, s


def test_LAS_PANTALLAS_NO_LEEN_NADA_QUE_NO_LLEGUE():
    """Si una pantalla empieza a leer un campo nuevo del aviso, tiene que
    agregarse a la lista: si no, llega vacío y nadie avisa."""
    import re
    raiz = Path(__file__).resolve().parents[2] / "frontend" / "src"
    leidos = set()
    for archivo in ("components/NotificationBell.jsx", "components/CampanaDelEquipo.jsx", "pages/Notifications.jsx"):
        fuente = (raiz / archivo).read_text(encoding="utf-8")
        leidos |= set(re.findall(r"\b(?:n|notif|notification|aviso)\??\.([a-z_]+)", fuente))
    faltan = leidos - LO_QUE_LEEN_LAS_PANTALLAS - {"length", "map", "filter", "some", "find"}
    assert not faltan, f"las pantallas leen {sorted(faltan)} y la lista no los trae"
