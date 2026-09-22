"""
tests/test_libro_en_decimal.py — las líneas del libro guardan la plata en
Decimal128, conviven con las viejas en float, y la pantalla que las lista
no se cae.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")
from bson.decimal128 import Decimal128                       # noqa: E402

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services import ledger, ledger_crypto                    # noqa: E402
from services.money import to_decimal128                      # noqa: E402


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base():
    m = mongomock_motor.AsyncMongoMockClient()["libro_decimal"]
    usar_base(m)
    ledger._indexes_ready = False
    ya(m.users.insert_one({"user_id": "u1", "email": "u1@ejemplo.test", "name": "Uno", "role": "user"}))
    return m


def test_LA_LINEA_SE_GUARDA_EN_DECIMAL128_Y_NO_EN_FLOAT(base):
    ya(ledger.record_ris_entry(user_id="u1", movement_type="recarga_pix", amount="0.1", direction="credit",
                               balance_before="0.2", balance_after="0.3"))
    linea = ya(base.ledger.find_one({"user_id": "u1"}))
    for campo in ("amount", "signed_amount", "balance_before", "balance_after"):
        assert isinstance(linea[campo], Decimal128), campo
    assert linea["amount"].to_decimal() == Decimal("0.10") and linea["balance_after"].to_decimal() == Decimal("0.30")


def test_un_float_entra_sin_su_ruido_y_un_debito_lleva_el_signo(base):
    ya(ledger.record_ris_entry(user_id="u1", movement_type="envio_ves", amount=0.1 + 0.2, direction="debit"))
    linea = ya(base.ledger.find_one({"user_id": "u1"}))
    assert linea["amount"].to_decimal() == Decimal("0.30") and linea["signed_amount"].to_decimal() == Decimal("-0.30")


def test_UN_FLOAT_SE_REDONDEA_COMO_SE_LEE_Y_NO_COMO_SE_GUARDA_EN_BINARIO(base):
    """1.005 en binario es 1.00499999…: redondeado «desde el float» da 1.00,
    que es un centavo menos de lo que la persona escribió. Se pasa por su
    texto, como hace `to_decimal`, y da 1.01."""
    ya(ledger.record_ris_entry(user_id="u1", movement_type="envio_ves", amount=1.005, direction="credit"))
    assert ya(base.ledger.find_one({"user_id": "u1"}))["amount"].to_decimal() == Decimal("1.01")


def test_UN_MONTO_GRANDE_NO_PIERDE_CENTAVOS_EN_EL_CAMINO(base):
    """Un float guarda unos dieciséis dígitos: con dieciocho, los centavos
    se pierden. En Decimal, no."""
    ya(ledger.record_ris_entry(user_id="u1", movement_type="ajuste_admin", amount="1234567890123456.78", direction="credit",
                               balance_before="0", balance_after="1234567890123456.78"))
    linea = ya(base.ledger.find_one({"user_id": "u1"}))
    assert linea["amount"].to_decimal() == Decimal("1234567890123456.78")
    assert linea["balance_after"].to_decimal() == Decimal("1234567890123456.78")


def test_LAS_LINEAS_VIEJAS_EN_FLOAT_Y_LAS_NUEVAS_SE_SUMAN_JUNTAS(base):
    ya(base.ledger.insert_one({"user_id": "u1", "account": "balance_ris", "signed_amount": 100.1, "amount": 100.1,
                               "direction": "credit", "movement_type": "viejo", "book": "RIS"}))
    ya(ledger.record_ris_entry(user_id="u1", movement_type="recarga_pix", amount="0.2", direction="credit"))
    assert ya(ledger.sum_ris_balance("u1")) == Decimal("100.30")


def test_el_libro_cripto_guarda_ocho_decimales(base):
    ya(ledger_crypto.record_crypto_entry(user_id="u1", currency="usdt", movement_type="deposito_cripto",
                                         amount="12.3456789", direction="credit", balance_before=0, balance_after="12.3456789"))
    linea = ya(base.ledger.find_one({"book": "USDT"}))
    assert linea["amount"].to_decimal() == Decimal("12.34567890") and isinstance(linea["balance_after"], Decimal128)


def test_LA_PANTALLA_QUE_LISTA_LAS_LINEAS_NO_SE_CAE_CON_DECIMAL128(base):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.ledger_admin import router
    ya(base.users.update_one({"user_id": "u1"}, {"$set": {"balance_ris": to_decimal128("100.30")}}))
    ya(ledger.record_ris_entry(user_id="u1", movement_type="recarga_pix", amount="100.30", direction="credit",
                               balance_before="0", balance_after="100.30", metadata={"tarifa": to_decimal128("1.5")}))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_super_admin] = lambda: User(user_id="u_jefa", name="J", email="j@ejemplo.test", role="super_admin")
    r = TestClient(app).get("/api/admin/ledger/entries?user_id=u1")
    assert r.status_code == 200, r.text
    e = r.json()["entries"][0]
    assert e["amount"] == 100.3 and e["signed_amount"] == 100.3 and e["metadata"]["tarifa"] == 1.5
    assert r.json()["diff"] == 0


def test_la_apertura_y_el_cierre_escriben_en_decimal(base):
    ya(base.users.update_one({"user_id": "u1"}, {"$set": {"balance_ris": to_decimal128("1234567890123456.75")}}))
    ya(ledger.create_opening_entries())
    apertura = ya(base.ledger.find_one({"movement_type": "saldo_apertura"}))
    assert isinstance(apertura["amount"], Decimal128) and apertura["amount"].to_decimal() == Decimal("1234567890123456.75")
    ya(ledger.create_closing_entries(actor_id="u_jefa", motivo="prueba"))
    cierre = ya(base.ledger.find_one({"movement_type": "cierre_de_libro"}))
    assert isinstance(cierre["amount"], Decimal128) and cierre["signed_amount"].to_decimal() == Decimal("-1234567890123456.75")
    assert ya(ledger.sum_ris_balance("u1")) == Decimal("0.00")
