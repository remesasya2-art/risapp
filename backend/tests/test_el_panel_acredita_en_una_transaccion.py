"""
tests/test_el_panel_acredita_en_una_transaccion.py — Lo que el panel acredita
—una recarga aprobada, la devolución de un retiro rechazado— va en una sola
transacción cuando el Mongo la tiene.

Aprobar una recarga en bolívares escribe cinco cosas: el saldo del banco, su
libro, el estado de la recarga, el saldo del cliente y su línea. Con un Mongo
de un solo nodo son escrituras separadas y un corte a la mitad deja, por
ejemplo, el banco acreditado y el cliente no. Lo que importa sólo se ve contra
un Mongo de verdad; CI corre este archivo contra uno con réplicas.
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

from conftest import ensenarle_decimal128_a_mongomock                 # noqa: E402
ensenarle_decimal128_a_mongomock()

from _lote_c_comun import SUPER                                      # noqa: E402
from _mongo_de_verdad import MONGO_DE_VERDAD, base_para, corre       # noqa: E402
from services.money import from_db, to_decimal128                    # noqa: E402

solo_con_transacciones = pytest.mark.skipif(
    not MONGO_DE_VERDAD, reason="sin RIS_MONGO_DE_VERDAD no hay transacciones (mongomock no las tiene)")

LIBRO_QUE_RECHAZA_TODO = {"$jsonSchema": {"required": ["campo_que_ninguna_linea_tiene"]}}


@pytest.fixture
def base(monkeypatch):
    yield from base_para(monkeypatch, "ris_el_panel_acredita")


def _saldo(base):
    return from_db(corre(base.users.find_one({"user_id": "u_1"}))["balance_ris"])


# ══════════════════════════════════════════════════════════════════════════
# La recarga en bolívares aprobada
# ══════════════════════════════════════════════════════════════════════════

def _recarga_pendiente(base):
    corre(base.users.insert_one({"user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente",
                                 "role": "user", "balance_ris": to_decimal128("10.00")}))
    corre(base.bank_accounts.insert_one({"bank_id": "bco_ves", "name": "Banco de prueba", "currency": "VES",
                                         "balance": to_decimal128("1000.00")}))
    corre(base.transactions.insert_one({"transaction_id": "tx_rec", "type": "recharge_ves", "status": "pending",
                                        "user_id": "u_1", "amount_ris": 25.0, "amount_ves": 2500.0,
                                        "destination_bank_id": "bco_ves"}))


def _aprobar():
    from routes.admin import recargas_ves
    return recargas_ves.process_ves_recharge("tx_rec", {"action": "approve"}, admin=SUPER)


def _banco(base):
    return from_db(corre(base.bank_accounts.find_one({"bank_id": "bco_ves"}))["balance"])


def _estado(base):
    return corre(base.transactions.find_one({"transaction_id": "tx_rec"}))["status"]


def test_APROBAR_ACREDITA_AL_CLIENTE_Y_AL_BANCO_Y_DEJA_LAS_LINEAS(base):
    _recarga_pendiente(base)
    corre(_aprobar())
    assert _saldo(base) == Decimal("35.00") and _banco(base) == Decimal("3500.00")
    assert _estado(base) == "approved"
    (linea,) = corre(base.ledger.find({"transaction_id": "tx_rec"}).to_list(5))
    assert linea["movement_type"] == "recarga_ves"
    assert corre(base.bank_ledger.count_documents({"reference": "tx_rec"})) == 1


@solo_con_transacciones
def test_APROBAR_SI_LA_LINEA_DEL_CLIENTE_FALLA_NADA_QUEDA_ESCRITO(base):
    """Sin transacciones, el banco quedaba acreditado, la recarga aprobada y
    el cliente con su saldo, sin la línea del libro."""
    _recarga_pendiente(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_aprobar())
    assert _saldo(base) == Decimal("10.00"), "el cliente quedó acreditado sin su línea"
    assert _banco(base) == Decimal("1000.00"), "el banco quedó acreditado"
    assert _estado(base) == "pending", "la recarga quedó aprobada"
    assert corre(base.bank_ledger.count_documents({})) == 0


@solo_con_transacciones
def test_APROBAR_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    from services import ledger

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger, "quantize_money", no_se_puede)
    _recarga_pendiente(base)
    with pytest.raises(ValueError):
        corre(_aprobar())
    assert _saldo(base) == Decimal("10.00") and _banco(base) == Decimal("1000.00") and _estado(base) == "pending"
