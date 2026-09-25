"""
tests/test_los_depositos_cripto_en_una_transaccion.py — Un depósito de USDT o
USDC se marca acreditado, suma el saldo y deja su línea, todo junto, cuando el
Mongo tiene transacciones.

El aviso de NOWPayments marca el depósito «acreditado» ANTES de sumar el saldo:
es lo que impide acreditar dos veces. Con un Mongo de un solo nodo, un corte
entre las dos escrituras dejaba el depósito marcado y el saldo sin sumar, y
nada lo reintentaba. Lo que importa sólo se ve contra un Mongo de verdad; CI
corre este archivo contra uno con réplicas.
"""
import json
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

from _lote_c_comun import SUPER                                      # noqa: E402
from _mongo_de_verdad import MONGO_DE_VERDAD, base_para, corre       # noqa: E402
from services.money import from_db, to_decimal128                    # noqa: E402

solo_con_transacciones = pytest.mark.skipif(
    not MONGO_DE_VERDAD, reason="sin RIS_MONGO_DE_VERDAD no hay transacciones (mongomock no las tiene)")

LIBRO_QUE_RECHAZA_TODO = {"$jsonSchema": {"required": ["campo_que_ninguna_linea_tiene"]}}


@pytest.fixture
def base(monkeypatch):
    from services import nowpayments
    # La firma de NOWPayments tiene sus propios tests; acá se prueba lo que pasa
    # DESPUÉS de una firma válida.
    monkeypatch.setattr(nowpayments, "verify_ipn_signature", lambda cuerpo, firma: "raw")
    yield from base_para(monkeypatch, "ris_depositos_cripto")


def _preparar(base, saldo="5.00"):
    corre(base.users.insert_one({"user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente",
                                 "role": "user", "balance_usdt": to_decimal128(saldo)}))
    corre(base.crypto_deposits.insert_one({"order_id": "dep_1", "user_id": "u_1", "currency": "usdt",
                                           "amount": 20.0, "credited": False, "status": "waiting"}))


class _Aviso:
    """Lo mínimo de un `Request` que lee el aviso: el cuerpo y la firma."""

    def __init__(self, **cuerpo):
        self._cuerpo = json.dumps(cuerpo).encode()
        self.headers = {"x-nowpayments-sig": "firma"}

    async def body(self):
        return self._cuerpo


def _avisar(pagado=20.0):
    from routes import credits
    return credits.nowpayments_webhook(_Aviso(order_id="dep_1", payment_status="finished",
                                              payment_id="p_1", actually_paid=pagado))


def _saldo(base):
    return from_db(corre(base.users.find_one({"user_id": "u_1"}))["balance_usdt"])


def _acreditado(base):
    return corre(base.crypto_deposits.find_one({"order_id": "dep_1"}))["credited"]


def _lineas(base, referencia="dep_1"):
    return corre(base.ledger.find({"reference.id": referencia}).to_list(10))


def _el_libro_no_se_puede_armar(monkeypatch):
    """Un error de este lado: la línea ni llega a la base. El servidor no se
    entera y no aborta nada por su cuenta; lo único que deshace el crédito es
    que el error salga del `try` del libro."""
    from services import ledger_crypto

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger_crypto, "quantize_money", no_se_puede)


# ══════════════════════════════════════════════════════════════════════════
# El aviso de NOWPayments
# ══════════════════════════════════════════════════════════════════════════

def test_EL_AVISO_ACREDITA_MARCA_EL_DEPOSITO_Y_DEJA_LA_LINEA(base):
    _preparar(base)
    r = corre(_avisar())
    assert r["processed"] is True
    assert _saldo(base) == Decimal("25.00") and _acreditado(base) is True
    (linea,) = _lineas(base)
    assert linea["movement_type"] == "deposito_cripto" and linea["direction"] == "credit"


def test_EL_AVISO_REPETIDO_ACREDITA_UNA_SOLA_VEZ(base):
    _preparar(base)
    corre(_avisar())
    r = corre(_avisar())
    assert r["already_processed"] is True
    assert _saldo(base) == Decimal("25.00") and len(_lineas(base)) == 1


@solo_con_transacciones
def test_EL_AVISO_SI_LA_LINEA_FALLA_EL_DEPOSITO_SIGUE_SIN_ACREDITAR(base):
    """Sin transacciones, el depósito quedaba marcado y el saldo sumado sin su
    línea; y si el que fallaba era el crédito, marcado y sin saldo."""
    _preparar(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_avisar())
    assert _saldo(base) == Decimal("5.00"), "se acreditó sin su línea"
    assert _acreditado(base) is False, "el depósito quedó marcado: el próximo aviso no lo reintentaría"


@solo_con_transacciones
def test_EL_AVISO_UN_ERROR_DEL_LIBRO_ANTES_DE_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    _el_libro_no_se_puede_armar(monkeypatch)
    _preparar(base)
    with pytest.raises(ValueError):
        corre(_avisar())
    assert _saldo(base) == Decimal("5.00") and _acreditado(base) is False


@solo_con_transacciones
def test_EL_AVISO_SI_FALLA_EL_CREDITO_EL_PROXIMO_AVISO_LO_ACREDITA(base, monkeypatch):
    """El caso que perdía plata: el depósito marcado y el saldo sin sumar.
    Con la transacción el reclamo se deshace, y NOWPayments reintenta."""
    from services import credits
    original = credits.to_credit_decimal
    llamadas = []

    def falla_la_primera_vez(monto):
        llamadas.append(monto)
        if len(llamadas) == 1:
            raise RuntimeError("se cortó al sumar")
        return original(monto)
    monkeypatch.setattr(credits, "to_credit_decimal", falla_la_primera_vez)
    _preparar(base)
    with pytest.raises(RuntimeError):
        corre(_avisar())
    assert _acreditado(base) is False
    corre(_avisar())
    assert _saldo(base) == Decimal("25.00") and _acreditado(base) is True and len(_lineas(base)) == 1


# ══════════════════════════════════════════════════════════════════════════
# La acreditación manual del panel
# ══════════════════════════════════════════════════════════════════════════

def _a_mano(monkeypatch, monto=7.5):
    from routes import credits_admin
    from services import cripto_abierta

    async def abierta(db):
        return None
    monkeypatch.setattr(cripto_abierta, "exigir_deposito", abierta)
    pedido = SimpleNamespace(email="cliente@ejemplo.test", currency="usdt", amount=monto, note=None)
    return credits_admin.manual_credit(pedido, admin=SUPER)


def test_A_MANO_ACREDITA_DEJA_LA_LINEA_Y_EL_DEPOSITO(base, monkeypatch):
    _preparar(base)
    r = corre(_a_mano(monkeypatch))
    assert _saldo(base) == Decimal("12.50")
    assert corre(base.crypto_deposits.find_one({"order_id": r["order_id"]}))["source"] == "admin_manual"
    (linea,) = _lineas(base, r["order_id"])
    assert linea["movement_type"] == "ajuste_admin_cripto"


@solo_con_transacciones
def test_A_MANO_SI_EL_DEPOSITO_NO_SE_REGISTRA_EL_SALDO_NO_SE_MUEVE(base, monkeypatch):
    """Sin transacciones, el saldo quedaba sumado sin el depósito que lo
    explica en el historial del cliente."""
    _preparar(base)
    corre(base.command("collMod", "crypto_deposits", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(_a_mano(monkeypatch))
    assert _saldo(base) == Decimal("5.00")
    assert corre(base.ledger.count_documents({})) == 0


@solo_con_transacciones
def test_A_MANO_SI_LA_LINEA_FALLA_EL_SALDO_NO_SE_MUEVE(base, monkeypatch):
    _el_libro_no_se_puede_armar(monkeypatch)
    _preparar(base)
    with pytest.raises(ValueError):
        corre(_a_mano(monkeypatch))
    assert _saldo(base) == Decimal("5.00")
    assert corre(base.crypto_deposits.count_documents({"source": "admin_manual"})) == 0


@solo_con_transacciones
def test_A_MANO_SI_LA_CONFIRMACION_FALLA_NO_QUEDA_NI_EL_DEPOSITO(base, monkeypatch):
    """El registro del depósito es lo último que se escribe: sólo se ve que va
    adentro de la transacción si algo falla después de él. Escrito afuera,
    quedaría un depósito «acreditado» sin el saldo que dice."""
    from services import transacciones

    async def todo_y_se_aborta(trabajo):
        async with await transacciones.mongo_client.start_session() as sesion:
            async with sesion.start_transaction():
                await trabajo(sesion)
                raise RuntimeError("la confirmación falló")
    monkeypatch.setattr(transacciones, "en_una_transaccion", todo_y_se_aborta)
    _preparar(base)
    with pytest.raises(RuntimeError):
        corre(_a_mano(monkeypatch))
    assert _saldo(base) == Decimal("5.00")
    assert corre(base.crypto_deposits.count_documents({"source": "admin_manual"})) == 0
    assert corre(base.ledger.count_documents({})) == 0
