"""
tests/test_la_moneda_de_lo_que_recibe_el_beneficiario.py — «40,00 VES» que eran reales.

QUE PASABA

    El historial del cliente mostraba, debajo del monto, lo que recibe el
    beneficiario. Y le ponía «VES» A MANO. Cuando se escribió, todos los
    envíos iban a Venezuela; después llegó el corredor a Brasil y nadie volvió
    a esa línea. Una orden de 4.400 bolívares a Brasil mostraba:

        João Silva                    -4.400,00 VES
        21 sept, 03:57 · #000505          40,00 VES   ← eran 40 reales

    Y no se podía arreglar sólo en la pantalla: el servidor no le mandaba la
    moneda de salida (`currency_output` no estaba en `LO_QUE_VE_EL_CLIENTE`).
    Apareció en la revisión general del 21 de septiembre de 2026, mirando la
    captura del historial.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que el servidor mande la moneda de salida de cada orden.
    2. Que la pantalla la lea, en vez de escribirla a mano.
    3. Que la equivalencia en dólares BCV se muestre sólo sobre bolívares:
       dividir reales por la tasa del BCV da un número que no es nada.

LA PLATA SE ESCRIBE CON `to_decimal128`, igual que la escribe la aplicación.
"""
import asyncio
import os
import pathlib
import re
import sys
import types

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from routes.transactions import LO_QUE_VE_EL_CLIENTE                 # noqa: E402
from services.money import to_decimal128                             # noqa: E402

_PANTALLA = (pathlib.Path(_BACKEND).parent / "frontend" / "src" / "components"
             / "dashboard" / "TransactionItem.jsx")

CLIENTE_ID = "u_ana"


def _ya(corrutina):
    return asyncio.run(corrutina)


def _sin_webpush():
    """`pywebpush` no compila en este entorno y las rutas lo arrastran."""
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


def _app(nombre):
    _sin_webpush()
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.user import User
    from routes.transactions import router
    from routes import dependencies as deps

    ana = User(user_id=CLIENTE_ID, name="Ana Cliente", email="ana@ejemplo.test",
               role="user")

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ana
    return TestClient(app), base


def _orden(tx_id, entra, sale, moneda_entra, moneda_sale, **extra):
    return {
        "transaction_id": tx_id, "display_id": "000505", "user_id": CLIENTE_ID,
        "type": "withdrawal", "status": "awaiting_payment",
        "amount_input": to_decimal128(entra), "amount_output": to_decimal128(sale),
        "currency_input": moneda_entra, "currency_output": moneda_sale,
        **extra,
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. El servidor manda la moneda de salida
# ══════════════════════════════════════════════════════════════════════════

def test_LA_ORDEN_A_BRASIL_LLEGA_CON_SU_MONEDA():
    cliente, base = _app("ris_moneda_brasil")
    _ya(base.transactions.insert_one(
        _orden("tx_br", "4400", "40", "VES", "BRL")))
    tx = cliente.get("/api/transactions").json()["transactions"][0]
    assert tx["currency_output"] == "BRL", (
        "el historial no trae la moneda de salida: la pantalla va a mostrar "
        "«VES» a lo que son reales")


def test_la_orden_a_venezuela_tambien():
    cliente, base = _app("ris_moneda_venezuela")
    _ya(base.transactions.insert_one(
        _orden("tx_ve", "100", "11000", "RIS", "VES")))
    tx = cliente.get("/api/transactions").json()["transactions"][0]
    assert tx["currency_output"] == "VES"


def test_esta_en_la_lista_de_lo_permitido():
    """La lista es el contrato. Si alguien la «limpia», este test lo dice con
    el motivo, en vez de que un cliente pregunte por qué ve VES."""
    assert LO_QUE_VE_EL_CLIENTE.get("currency_output") == 1


# ══════════════════════════════════════════════════════════════════════════
# 2. La pantalla la lee, no la escribe a mano
# ══════════════════════════════════════════════════════════════════════════

def _linea_del_monto_de_salida():
    """La línea que pinta `amount_output` con su unidad."""
    lineas = _PANTALLA.read_text(encoding="utf-8").splitlines()
    for n, linea in enumerate(lineas):
        if "fmt(tx.amount_output)}" in linea:
            return n + 1, linea
    raise AssertionError(
        "no se encontró la línea que muestra lo que recibe el beneficiario: "
        "la pantalla cambió de forma y esta guarda dejó de mirarla")


def test_LA_PANTALLA_NO_ESCRIBE_LA_MONEDA_A_MANO():
    n, linea = _linea_del_monto_de_salida()
    assert not re.search(r"amount_output\)\}\s*VES", linea), (
        f"TransactionItem.jsx:{n} le pone «VES» a mano a lo que recibe el "
        f"beneficiario: una orden a Brasil vuelve a mostrar reales como "
        f"bolívares")
    assert "monedaSalida" in linea, (
        f"TransactionItem.jsx:{n} no lee la moneda de salida")


def test_la_moneda_de_salida_sale_de_la_orden_con_VES_de_respaldo():
    """Las órdenes viejas no tienen `currency_output` guardado. Sin respaldo
    mostrarían el monto sin moneda, que se lee como un error."""
    fuente = _PANTALLA.read_text(encoding="utf-8")
    assert "const monedaSalida = tx.currency_output || 'VES';" in fuente


def test_LA_EQUIVALENCIA_EN_DOLARES_BCV_SOLO_SOBRE_BOLIVARES():
    """Dividir reales por la tasa del BCV da un número que no es nada, y se
    mostraba al lado del monto con la misma letra que los datos de verdad."""
    fuente = _PANTALLA.read_text(encoding="utf-8")
    i = fuente.index("bcv_usd_ves > 0 && (")
    # La condición tiene que estar en la misma expresión, justo antes.
    antes = fuente[max(0, i - 60):i]
    assert "monedaSalida === 'VES' &&" in antes, (
        "la equivalencia en dólares BCV se muestra para cualquier moneda")
