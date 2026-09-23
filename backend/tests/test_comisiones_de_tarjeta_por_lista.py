"""
tests/test_comisiones_de_tarjeta_por_lista.py — la configuración del pago con
tarjeta muestra tres comisiones y nada más de lo que haya guardado.

`_get_card_fees` junta las de fábrica con TODO lo de `app_settings.card_fees`,
y `/payments/card/config` lo devolvía entero a cualquier cliente. Ver
`ComisionesDeTarjeta` en routes/payments_card.py.
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

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")
NOTA = "negociado con el procesador: 3.1%"


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["comisiones_tarjeta"]
    usar_base(m)
    ya(m.app_settings.insert_one({"key": "card_fees", "value": {
        "credit_pct": 4.99, "nota_interna": NOTA, "costo_real_pct": 3.1}}))
    return m


def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.payments_card import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


def test_EL_CLIENTE_VE_LAS_TRES_COMISIONES_Y_NADA_MAS(base):
    r = cliente().get("/api/payments/card/config")
    assert r.status_code == 200, r.text
    assert r.json()["fees"] == {"credit_pct": 4.99, "debit_pct": 1.99, "flat_brl": 0.4}
    assert NOTA not in r.text and "costo_real_pct" not in r.text


def test_EL_CALCULO_INTERNO_SIGUE_LEYENDO_LO_GUARDADO(base):
    from routes.payments_card import _get_card_fees
    fees = ya(_get_card_fees())
    assert fees["credit_pct"] == 4.99 and fees["nota_interna"] == NOTA


def test_EL_CONTRATO_SOLO_CORTA_LO_QUE_EL_RECORTE_DEJE_PASAR(base, monkeypatch):
    """Si alguien vuelve a mandar `fees` entero, el contrato corta igual."""
    import routes.payments_card as tarjeta
    todo = {**tarjeta.DEFAULT_CARD_FEES, "nota_interna": NOTA, "costo_real_pct": 3.1}
    monkeypatch.setattr(tarjeta, "DEFAULT_CARD_FEES", todo)
    r = cliente().get("/api/payments/card/config")
    assert r.status_code == 200, r.text
    assert NOTA not in r.text and "costo_real_pct" not in r.text


def test_LA_RUTA_TIENE_SU_CONTRATO():
    from routes.payments_card import router
    (ruta,) = [r for r in router.routes if r.path.endswith("/config") and "GET" in r.methods]
    assert ruta.response_model.__name__ == "ConfigDeTarjeta"


def test_EL_RECORTE_SOLO_SIN_EL_CONTRATO(base):
    """La primera capa, probada sin la segunda: la función de la ruta llamada
    directo, sin que FastAPI le aplique el contrato."""
    from routes.payments_card import get_card_config
    salida = ya(get_card_config(current_user=ANA))
    assert set(salida["fees"]) == {"credit_pct", "debit_pct", "flat_brl"}
