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


# ══════════════════════════════════════════════════════════════════════════
# La devolución de un retiro rechazado
# ══════════════════════════════════════════════════════════════════════════

def _retiro_pendiente(base, moneda="RIS"):
    campo = {"RIS": "balance_ris", "USDT": "balance_usdt"}[moneda]
    corre(base.users.insert_one({"user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente",
                                 "role": "user", campo: to_decimal128("10.00")}))
    corre(base.transactions.insert_one({"transaction_id": "tx_ret", "type": "withdrawal", "status": "pending",
                                        "user_id": "u_1", "amount_input": 40.0, "currency_input": moneda,
                                        "currency_output": "VES", "amount_output": 4000.0}))


def _rechazar():
    from routes.admin import retiros
    return retiros.process_withdrawal({"transaction_id": "tx_ret", "action": "reject"}, None, admin=SUPER)


def _cuenta(base, campo="balance_ris"):
    return from_db(corre(base.users.find_one({"user_id": "u_1"})).get(campo))


def _estado_del_retiro(base):
    return corre(base.transactions.find_one({"transaction_id": "tx_ret"}))["status"]


def test_RECHAZAR_DEVUELVE_EL_SALDO_DEJA_LA_LINEA_Y_MARCA_EL_RETIRO(base):
    _retiro_pendiente(base)
    corre(_rechazar())
    assert _cuenta(base) == Decimal("50.00") and _estado_del_retiro(base) == "rejected"
    (linea,) = corre(base.ledger.find({"transaction_id": "tx_ret"}).to_list(5))
    assert linea["movement_type"] == "refund_envio"


def test_RECHAZAR_UN_RETIRO_EN_USDT_DEVUELVE_USDT(base):
    _retiro_pendiente(base, "USDT")
    corre(_rechazar())
    assert _cuenta(base, "balance_usdt") == Decimal("50.00") and _estado_del_retiro(base) == "rejected"


@solo_con_transacciones
def test_RECHAZAR_SI_LA_LINEA_FALLA_NI_DEVOLUCION_NI_ESTADO(base):
    """Sin transacciones, la plata quedaba devuelta sin su línea."""
    _retiro_pendiente(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_rechazar())
    assert _cuenta(base) == Decimal("10.00") and _estado_del_retiro(base) == "pending"


@solo_con_transacciones
def test_RECHAZAR_EN_USDT_SI_LA_LINEA_CRIPTO_FALLA_NI_DEVOLUCION_NI_ESTADO(base):
    from services import ledger_crypto
    _retiro_pendiente(base, "USDT")
    corre(base.create_collection(ledger_crypto.LEDGER_COLLECTION, validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_rechazar())
    assert _cuenta(base, "balance_usdt") == Decimal("10.00") and _estado_del_retiro(base) == "pending"


@solo_con_transacciones
def test_RECHAZAR_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    from services import ledger

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger, "quantize_money", no_se_puede)
    _retiro_pendiente(base)
    with pytest.raises(ValueError):
        corre(_rechazar())
    assert _cuenta(base) == Decimal("10.00") and _estado_del_retiro(base) == "pending"


@solo_con_transacciones
def test_RECHAZAR_EN_USDT_UN_ERROR_DEL_LIBRO_CRIPTO_ANTES_DE_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    from services import ledger_crypto

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger_crypto, "quantize_money", no_se_puede)
    _retiro_pendiente(base, "USDT")
    with pytest.raises(ValueError):
        corre(_rechazar())
    assert _cuenta(base, "balance_usdt") == Decimal("10.00") and _estado_del_retiro(base) == "pending"


# ══════════════════════════════════════════════════════════════════════════
# La devolución de un pago incompleto en cripto
# ══════════════════════════════════════════════════════════════════════════

def _orden_incompleta(base):
    corre(base.users.insert_one({"user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente",
                                 "role": "user", "balance_usdt": to_decimal128("1.00")}))
    corre(base.transactions.insert_one({"transaction_id": "tx_inc", "display_id": "RIS-7", "type": "withdrawal",
                                        "status": "underpaid_review", "user_id": "u_1",
                                        "currency_input": "USDT", "actually_paid": 12.5,
                                        "topup_actually_paid": 2.5}))


def _devolver_incompleto():
    from routes.admin import pagos_incompletos
    return pagos_incompletos.rechazar_orden_y_reembolsar_saldo("tx_inc", admin=SUPER)


def _orden_incompleta_estado(base):
    return corre(base.transactions.find_one({"transaction_id": "tx_inc"}))


def test_INCOMPLETO_RECHAZA_DEVUELVE_ASIENTA_Y_ANOTA(base):
    _orden_incompleta(base)
    r = corre(_devolver_incompleto())
    assert r["refunded"] == 15.0
    assert _cuenta(base, "balance_usdt") == Decimal("16.00")
    orden = _orden_incompleta_estado(base)
    assert orden["status"] == "rejected" and orden["refund_amount"] == 15.0
    (linea,) = corre(base.ledger.find({"reference.id": "tx_inc"}).to_list(5))
    assert linea["movement_type"] == "reembolso_pago_incompleto"


def test_INCOMPLETO_DOS_VECES_DEVUELVE_UNA(base):
    from fastapi import HTTPException
    _orden_incompleta(base)
    corre(_devolver_incompleto())
    with pytest.raises(HTTPException) as e:
        corre(_devolver_incompleto())
    assert e.value.status_code == 409 and _cuenta(base, "balance_usdt") == Decimal("16.00")


@solo_con_transacciones
def test_INCOMPLETO_SI_LA_LINEA_FALLA_LA_ORDEN_SIGUE_EN_REVISION(base):
    """Sin transacciones, la orden quedaba rechazada; y si lo que fallaba era
    la devolución, rechazada y sin devolver, con el botón ya inútil."""
    _orden_incompleta(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_devolver_incompleto())
    assert _cuenta(base, "balance_usdt") == Decimal("1.00")
    assert _orden_incompleta_estado(base)["status"] == "underpaid_review", "el botón ya no se podría reintentar"


@solo_con_transacciones
def test_INCOMPLETO_UN_ERROR_DEL_LIBRO_ANTES_DE_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    from services import ledger_crypto

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger_crypto, "quantize_money", no_se_puede)
    _orden_incompleta(base)
    with pytest.raises(ValueError):
        corre(_devolver_incompleto())
    assert _cuenta(base, "balance_usdt") == Decimal("1.00")
    assert _orden_incompleta_estado(base)["status"] == "underpaid_review"


@solo_con_transacciones
def test_INCOMPLETO_SI_LA_CONFIRMACION_FALLA_NO_QUEDA_NADA(base, monkeypatch):
    """Los campos de la devolución son lo último que se escribe: sólo se ve
    que van adentro si algo falla después de ellos."""
    from services import transacciones

    async def todo_y_se_aborta(trabajo):
        async with await transacciones.mongo_client.start_session() as sesion:
            async with sesion.start_transaction():
                await trabajo(sesion)
                raise RuntimeError("la confirmación falló")
    monkeypatch.setattr(transacciones, "en_una_transaccion", todo_y_se_aborta)
    _orden_incompleta(base)
    with pytest.raises(RuntimeError):
        corre(_devolver_incompleto())
    orden = _orden_incompleta_estado(base)
    assert orden["status"] == "underpaid_review" and "refund_amount" not in orden
    assert _cuenta(base, "balance_usdt") == Decimal("1.00") and corre(base.ledger.count_documents({})) == 0
