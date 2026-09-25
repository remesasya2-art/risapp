"""
tests/test_salidas_de_saldo.py — Los envíos que el cliente paga con su saldo:
el débito, la orden y la línea del libro van juntos cuando hay transacciones.

Ver `services/salidas_de_saldo.py`. Lo que importa sólo se ve contra un Mongo
de verdad (mongomock no tiene transacciones); CI corre este archivo contra uno
con réplicas. Los casos que no dependen de transacciones corren también sobre
mongomock, y prueban que el camino de un solo nodo sigue siendo el de siempre.
"""
import os
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

from conftest import ensenarle_decimal128_a_mongomock                 # noqa: E402
ensenarle_decimal128_a_mongomock()

from fastapi import HTTPException                                    # noqa: E402

from _mongo_de_verdad import MONGO_DE_VERDAD, base_para, corre       # noqa: E402
from models.user import User                                         # noqa: E402
from services import salidas_de_saldo                                # noqa: E402
from services.money import from_db, to_decimal128                    # noqa: E402

solo_con_transacciones = pytest.mark.skipif(
    not MONGO_DE_VERDAD, reason="sin RIS_MONGO_DE_VERDAD no hay transacciones (mongomock no las tiene)")

LIBRO_QUE_RECHAZA_TODO = {"$jsonSchema": {"required": ["campo_que_ninguna_linea_tiene"]}}
CLIENTE = User(user_id="u_1", name="Cliente", email="cliente@ejemplo.test", role="user")


@pytest.fixture
def base(monkeypatch):
    yield from base_para(monkeypatch, "ris_salidas_de_saldo")


def _preparar(base, saldo="100.00"):
    corre(base.users.insert_one({"user_id": "u_1", "email": CLIENTE.email, "name": "Cliente",
                                 "role": "user", "balance_ris": to_decimal128(saldo)}))
    corre(base.beneficiaries.insert_one({"beneficiary_id": "b_br", "user_id": "u_1", "pais": "BR",
                                         "full_name": "Destinatario", "cpf": "00000000000",
                                         "pix_key": "destinatario@ejemplo.test"}))


def _saldo(base):
    return from_db(corre(base.users.find_one({"user_id": "u_1"}))["balance_ris"])


def _cuantos(base, coleccion):
    return corre(base[coleccion].count_documents({}))


def _a_brasil(monto, beneficiario="b_br"):
    return salidas_de_saldo.cobrar_envio_a_brasil(
        CLIENTE, SimpleNamespace(amount=monto, beneficiary_id=beneficiario))


# ══════════════════════════════════════════════════════════════════════════
# El envío a Brasil
# ══════════════════════════════════════════════════════════════════════════

def test_A_BRASIL_DESCUENTA_CREA_LA_ORDEN_Y_ASIENTA(base):
    _preparar(base)
    user, _, tx_id, display_id, amount_brl = corre(_a_brasil(30.0))
    assert _saldo(base) == Decimal("70.00") and amount_brl == 30.0
    orden = corre(base.transactions.find_one({"transaction_id": tx_id}))
    assert orden["display_id"] == display_id and orden["status"] == "pending"
    (linea,) = corre(base.ledger.find({"transaction_id": tx_id}).to_list(5))
    assert linea["movement_type"] == "envio_reais" and from_db(linea["balance_after"]) == Decimal("70.00")


def test_A_BRASIL_SIN_SALDO_NO_ESCRIBE_NADA(base):
    _preparar(base, saldo="10.00")
    with pytest.raises(HTTPException) as e:
        corre(_a_brasil(30.0))
    assert e.value.status_code == 400
    assert _saldo(base) == Decimal("10.00") and _cuantos(base, "transactions") == 0


def test_A_BRASIL_CON_UN_BENEFICIARIO_QUE_NO_EXISTE_EL_SALDO_VUELVE(base):
    _preparar(base)
    with pytest.raises(HTTPException) as e:
        corre(_a_brasil(30.0, beneficiario="b_nadie"))
    assert e.value.status_code == 404
    assert _saldo(base) == Decimal("100.00") and _cuantos(base, "transactions") == 0


@solo_con_transacciones
def test_A_BRASIL_SI_LA_LINEA_FALLA_NO_HAY_DEBITO_NI_ORDEN(base):
    """Sin transacciones, el saldo se descontaba y la orden quedaba creada
    aunque la línea del libro no se escribiera."""
    _preparar(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_a_brasil(30.0))
    assert _saldo(base) == Decimal("100.00"), "se descontó sin su línea"
    assert _cuantos(base, "transactions") == 0, "quedó una orden sin su débito asentado"


@solo_con_transacciones
def test_A_BRASIL_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    """Cuando el servidor rechaza la línea, aborta la transacción por su
    cuenta. Cuando el error es de este lado —la línea ni se llegó a armar—
    el servidor no se entera, y lo único que deshace el débito es que el
    `try` del libro deje salir el error. Si se lo tragara, la transacción
    confirmaría el débito y la orden sin su línea."""
    from services import ledger

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger, "quantize_money", no_se_puede)
    _preparar(base)
    with pytest.raises(ValueError):
        corre(_a_brasil(30.0))
    assert _saldo(base) == Decimal("100.00") and _cuantos(base, "transactions") == 0


# ══════════════════════════════════════════════════════════════════════════
# El retiro en bolívares, que puede salir de dos cuentas
# ══════════════════════════════════════════════════════════════════════════

def _con_bono(base, bono="20.00"):
    from services import bonos
    corre(base.users.update_one({"user_id": "u_1"}, {"$set": {
        "bono": {"estado": bonos.LIBERADO}, bonos.CUENTA_DEL_BONO: to_decimal128(bono)}}))


def _retiro_ves(monto=50.0):
    orden = {"transaction_id": "tx_ves", "display_id": "RIS-1", "user_id": "u_1", "type": "withdrawal",
             "amount_input": monto, "currency_input": "RIS", "currency_output": "VES", "status": "pending"}
    return salidas_de_saldo.cobrar_retiro_en_bolivares(
        CLIENTE, SimpleNamespace(amount=monto), transaction=orden, tx_id="tx_ves", display_id="RIS-1",
        ris_to_ves=100.0, amount_ves=monto * 100, beneficiary_data={"full_name": "Destinatario"})


def _bono(base):
    from services import bonos
    return from_db(corre(base.users.find_one({"user_id": "u_1"})).get(bonos.CUENTA_DEL_BONO))


def test_EN_BOLIVARES_DESCUENTA_CREA_LA_ORDEN_Y_ASIENTA(base):
    _preparar(base)
    corre(_retiro_ves(50.0))
    assert _saldo(base) == Decimal("50.00") and _cuantos(base, "transactions") == 1
    (linea,) = corre(base.ledger.find({"transaction_id": "tx_ves"}).to_list(5))
    assert linea["movement_type"] == "envio_ves" and linea["account"] == "balance_ris"


def test_EN_BOLIVARES_EL_BONO_SE_GASTA_PRIMERO_Y_CADA_CUENTA_TIENE_SU_LINEA(base):
    _preparar(base)
    _con_bono(base, "20.00")
    corre(_retiro_ves(50.0))
    assert _bono(base) == Decimal("0.00") and _saldo(base) == Decimal("70.00")
    cuentas = sorted(linea["account"] for linea in corre(base.ledger.find({"transaction_id": "tx_ves"}).to_list(5)))
    assert cuentas == ["balance_ris", "balance_ris_bono"]


def test_EN_BOLIVARES_SIN_SALDO_NO_ESCRIBE_NADA(base):
    _preparar(base, saldo="10.00")
    with pytest.raises(HTTPException) as e:
        corre(_retiro_ves(50.0))
    assert e.value.status_code == 400 and _saldo(base) == Decimal("10.00") and _cuantos(base, "transactions") == 0


@solo_con_transacciones
def test_EN_BOLIVARES_SI_UNA_LINEA_FALLA_NI_EL_SALDO_NI_EL_BONO_SE_MUEVEN(base):
    _preparar(base)
    _con_bono(base, "20.00")
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_retiro_ves(50.0))
    assert _saldo(base) == Decimal("100.00") and _bono(base) == Decimal("20.00")
    assert _cuantos(base, "transactions") == 0


@solo_con_transacciones
def test_EN_BOLIVARES_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    from services import ledger

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger, "quantize_money", no_se_puede)
    _preparar(base)
    with pytest.raises(ValueError):
        corre(_retiro_ves(50.0))
    assert _saldo(base) == Decimal("100.00") and _cuantos(base, "transactions") == 0
