"""
Tests del sistema de 3 niveles para pagos incompletos (envio cripto directo).

Corren AISLADOS: no tocan Mongo, no llaman a NOWPayments y no levantan el
servidor. Se reemplaza `db` por una coleccion en memoria y `nowpayments` por un
doble, y se le pasa al webhook un payload de IPN armado a mano y firmado con la
misma HMAC-SHA512 que usa NOWPayments, para que tambien se ejercite la
verificacion de firma.

Cubre las 4 ramas de nivel del pago original + el ciclo del topup:
  1. ratio >= 0.98                         -> pending
  2. 0.80 <= ratio < 0.98 y topup creado   -> awaiting_topup
  3. 0.80 <= ratio < 0.98 y topup imposible-> underpaid_review
  4. ratio < 0.80                          -> underpaid_review
  5. topup que completa                    -> pending
  6. topup que sigue corto                 -> underpaid_review
  7. topup failed/expired                  -> underpaid_review
"""
import asyncio
import copy
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

IPN_KEY = "test-ipn-key"
os.environ.setdefault("NOWPAYMENTS_IPN_KEY", IPN_KEY)

from services import nowpayments as nowpayments_module  # noqa: E402

nowpayments_module.IPN_KEY = IPN_KEY

import routes.transactions as tx_routes  # noqa: E402


# --------------------------------------------------------------------------
# Doble de Mongo: lo justo para lo que usa el webhook.
# --------------------------------------------------------------------------

def _match(doc, query):
    for field, cond in query.items():
        value = doc.get(field)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$lte" in cond and not (value is not None and value <= cond["$lte"]):
                return False
        elif value != cond:
            return False
    return True


def _apply(doc, update):
    for field, value in (update.get("$set") or {}).items():
        doc[field] = value


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return copy.deepcopy(doc)
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                return
        return

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                count += 1

        class _Res:
            modified_count = count

        return _Res()

    async def find_one_and_update(self, query, update, return_document=None):
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                return copy.deepcopy(doc)
        return None


class FakeDB:
    def __init__(self, docs=None):
        self.transactions = FakeCollection(docs)


class FakeRequest:
    def __init__(self, body: bytes, signature: str):
        self._body = body
        self.headers = {"x-nowpayments-sig": signature}

    async def body(self):
        return self._body


def _sign(payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(IPN_KEY.encode("utf-8"), raw, hashlib.sha512).hexdigest()
    return raw, sig


ORDER_ID = "send_usdt_user123_abcdef123456"
TOPUP_ORDER_ID = f"topup_{ORDER_ID}"


def _orden(**overrides):
    doc = {
        "_id": "oid1",
        "transaction_id": "tx_abc123",
        "display_id": "R-0001",
        "user_id": "user123",
        "type": "withdrawal",
        "status": "awaiting_payment",
        "currency_input": "USDT",
        "currency_output": "VES",
        "amount_input": 100.0,
        "amount_output": 12000.0,
        "payment_order_id": ORDER_ID,
        "pay_currency": "usdttrc20",
        "network": "trx",          # nombre de red: NO es un ticker pagable
        "pay_amount": 101.0,       # monto pedido por NOWPayments (incluye fee)
        "funded_from": "payment",
        "paid_ratio": 0.0,
    }
    doc.update(overrides)
    return doc


class _Espias:
    def __init__(self):
        self.notificaciones = []
        self.pagos_creados = []


@pytest.fixture
def entorno(monkeypatch):
    """Aisla el webhook: db en memoria, NOWPayments falso, side effects espiados."""
    espias = _Espias()

    async def fake_create_notification(user_id, title, message, notification_type="info", data=None):
        espias.notificaciones.append(
            {"user_id": user_id, "title": title, "type": notification_type, "data": data}
        )
        return "notif_test"

    monkeypatch.setattr(tx_routes, "create_notification", fake_create_notification)
    return espias


def _instalar_db(monkeypatch, docs):
    fake_db = FakeDB(docs)
    monkeypatch.setattr(tx_routes, "db", fake_db)
    return fake_db


def _instalar_nowpayments(monkeypatch, espias, *, min_amount=1.0, payment=None, falla_pago=False):
    class FakeNowPayments:
        verify_ipn_signature = staticmethod(nowpayments_module.verify_ipn_signature)

        @staticmethod
        async def get_min_amount(currency, fiat_equivalent="usd"):
            if min_amount is None:
                raise RuntimeError("min-amount caido")
            return {"min_amount": min_amount, "currency_from": currency}

        @staticmethod
        async def create_payment(**kwargs):
            espias.pagos_creados.append(kwargs)
            if falla_pago:
                raise RuntimeError("NOWPayments rechazo el pago")
            return payment or {
                "payment_id": "pay_topup_1",
                "pay_address": "TTopUpAddress0000000000000000000000",
                "pay_amount": 20.5,
                "network": "trx",
            }

    monkeypatch.setattr(tx_routes, "nowpayments", FakeNowPayments)


def _webhook(payload):
    raw, sig = _sign(payload)
    return asyncio.run(tx_routes.webhook_crypto_send(FakeRequest(raw, sig)))


# --------------------------------------------------------------------------
# Nivel 1: alcanza
# --------------------------------------------------------------------------

def test_nivel1_pago_completo_pasa_a_pending(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    res = _webhook({"order_id": ORDER_ID, "payment_status": "finished", "actually_paid": 101.0})

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["status"] == "pending"
    assert doc["underpaid"] is False
    assert doc["paid_ratio"] == pytest.approx(1.0)
    assert entorno.notificaciones[0]["type"] == "crypto_send_paid"


def test_nivel1_parcial_dentro_de_tolerancia_pasa_a_pending(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    # 99.5 / 101 = 0.985 -> por encima de 0.98
    res = _webhook({"order_id": ORDER_ID, "payment_status": "partially_paid", "actually_paid": 99.5})

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["status"] == "pending"
    assert doc["underpaid"] is True
    assert entorno.pagos_creados == []   # no se pide diferencia


# --------------------------------------------------------------------------
# Nivel 2: falto poco -> se cobra la diferencia
# --------------------------------------------------------------------------

def test_nivel2_genera_topup_y_queda_awaiting_topup(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    # 90 / 101 = 0.891 -> entre 0.80 y 0.98
    res = _webhook({"order_id": ORDER_ID, "payment_status": "partially_paid", "actually_paid": 90.0})

    assert res["status"] == "awaiting_topup"
    doc = db.transactions.docs[0]
    assert doc["status"] == "awaiting_topup"
    assert doc["topup_order_id"] == TOPUP_ORDER_ID
    assert doc["topup_pay_address"] == "TTopUpAddress0000000000000000000000"
    assert doc["topup_pay_currency"] == "usdttrc20"
    assert isinstance(doc["topup_created_at"], datetime)

    creado = entorno.pagos_creados[0]
    assert creado["order_id"] == TOPUP_ORDER_ID
    assert creado["price_amount"] == pytest.approx(11.0)   # 101 - 90
    assert creado["price_currency"] == "usd"
    # El ticker pagable sale de pay_currency, NO de network ('trx' no es ticker).
    assert creado["pay_currency"] == "usdttrc20"

    assert entorno.notificaciones[0]["type"] == "crypto_send_awaiting_topup"
    assert entorno.notificaciones[0]["data"] == {"transaction_id": "tx_abc123"}


def test_nivel2_sin_minimo_alcanzable_cae_a_revision(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    # El faltante (11) queda por debajo del minimo pagable de la red (50).
    _instalar_nowpayments(monkeypatch, entorno, min_amount=50.0)

    res = _webhook({"order_id": ORDER_ID, "payment_status": "partially_paid", "actually_paid": 90.0})

    assert res["status"] == "underpaid_review"
    assert db.transactions.docs[0]["status"] == "underpaid_review"
    assert entorno.pagos_creados == []
    assert entorno.notificaciones[0]["type"] == "crypto_send_underpaid_review"


def test_nivel2_si_nowpayments_falla_cae_a_revision(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno, falla_pago=True)

    res = _webhook({"order_id": ORDER_ID, "payment_status": "partially_paid", "actually_paid": 90.0})

    assert res["status"] == "underpaid_review"
    assert db.transactions.docs[0]["status"] == "underpaid_review"
    assert len(entorno.pagos_creados) == 1   # se intento, fallo, no se reintenta


# --------------------------------------------------------------------------
# Nivel 3: falto demasiado
# --------------------------------------------------------------------------

def test_nivel3_pago_muy_corto_va_a_revision(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    # 50 / 101 = 0.495 -> por debajo de 0.80
    res = _webhook({"order_id": ORDER_ID, "payment_status": "partially_paid", "actually_paid": 50.0})

    assert res["status"] == "underpaid_review"
    doc = db.transactions.docs[0]
    assert doc["status"] == "underpaid_review"
    assert doc["paid_ratio"] == pytest.approx(50.0 / 101.0)
    assert entorno.pagos_creados == []
    assert entorno.notificaciones[0]["type"] == "crypto_send_underpaid_review"


# --------------------------------------------------------------------------
# Ciclo del topup
# --------------------------------------------------------------------------

def _orden_con_topup(**overrides):
    base = {
        "status": "awaiting_topup",
        "actually_paid": 90.0,
        "paid_ratio": 90.0 / 101.0,
        "topup_order_id": TOPUP_ORDER_ID,
        "topup_pay_address": "TTopUpAddress0000000000000000000000",
        "topup_pay_amount": 11.5,
        "topup_pay_currency": "usdttrc20",
        "topup_network": "trx",
        "topup_created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return _orden(**base)


def test_topup_completo_cierra_la_orden(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden_con_topup()])
    _instalar_nowpayments(monkeypatch, entorno)

    # 90 + 11 = 101 -> ratio 1.0
    res = _webhook({"order_id": TOPUP_ORDER_ID, "payment_status": "finished", "actually_paid": 11.0})

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["status"] == "pending"
    assert doc["topup_actually_paid"] == 11.0
    assert doc["paid_ratio"] == pytest.approx(1.0)
    assert doc["underpaid"] is False


def test_topup_insuficiente_va_a_revision(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden_con_topup()])
    _instalar_nowpayments(monkeypatch, entorno)

    # 90 + 2 = 92 -> 0.91, sigue por debajo de 0.98
    res = _webhook({"order_id": TOPUP_ORDER_ID, "payment_status": "partially_paid", "actually_paid": 2.0})

    assert res["status"] == "underpaid_review"
    doc = db.transactions.docs[0]
    assert doc["status"] == "underpaid_review"
    assert doc["topup_actually_paid"] == 2.0
    assert entorno.notificaciones[0]["type"] == "crypto_send_underpaid_review"


def test_topup_expirado_va_a_revision(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden_con_topup()])
    _instalar_nowpayments(monkeypatch, entorno)

    res = _webhook({"order_id": TOPUP_ORDER_ID, "payment_status": "expired"})

    assert res["processed"] is False
    assert db.transactions.docs[0]["status"] == "underpaid_review"
    assert entorno.notificaciones[0]["type"] == "crypto_send_underpaid_review"


def test_pago_original_expirado_no_mata_una_orden_con_topup_abierto(entorno, monkeypatch):
    """El IPN 'expired' del pago original no debe cancelar una orden que ya esta
    esperando la diferencia: ese pago ya cumplio su ciclo."""
    db = _instalar_db(monkeypatch, [_orden_con_topup()])
    _instalar_nowpayments(monkeypatch, entorno)

    _webhook({"order_id": ORDER_ID, "payment_status": "expired"})

    assert db.transactions.docs[0]["status"] == "awaiting_topup"


def test_finished_tardio_del_pago_original_cierra_orden_en_revision(entorno, monkeypatch):
    """NOWPayments puede mandar un 'finished' despues de un 'partially_paid'.
    Si al final entro todo el dinero, la orden se cierra aunque haya caido a
    awaiting_topup / underpaid_review."""
    db = _instalar_db(monkeypatch, [_orden(status="underpaid_review", paid_ratio=0.5, actually_paid=50.0)])
    _instalar_nowpayments(monkeypatch, entorno)

    res = _webhook({"order_id": ORDER_ID, "payment_status": "finished", "actually_paid": 101.0})

    assert res["processed"] is True
    assert db.transactions.docs[0]["status"] == "pending"


# --------------------------------------------------------------------------
# Guardas del webhook
# --------------------------------------------------------------------------

def test_firma_invalida_es_rechazada(entorno, monkeypatch):
    _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    from fastapi import HTTPException

    payload = {"order_id": ORDER_ID, "payment_status": "finished", "actually_paid": 101.0}
    raw = json.dumps(payload).encode("utf-8")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(tx_routes.webhook_crypto_send(FakeRequest(raw, "firma-mentirosa")))
    assert exc.value.status_code == 401


def test_estado_intermedio_no_cambia_nada(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    res = _webhook({"order_id": ORDER_ID, "payment_status": "confirming", "actually_paid": 40.0})

    assert res["processed"] is False
    doc = db.transactions.docs[0]
    assert doc["status"] == "awaiting_payment"
    assert doc["paid_ratio"] == 0.0     # no se calcula nivel todavia


def test_order_id_desconocido_no_rompe(entorno, monkeypatch):
    _instalar_db(monkeypatch, [_orden()])
    _instalar_nowpayments(monkeypatch, entorno)

    res = _webhook({"order_id": "send_usdt_otro_999", "payment_status": "finished", "actually_paid": 101.0})

    assert res["error"] == "order_not_found"


def test_ticker_pagable_ignora_el_nombre_de_red():
    """tx['network'] ('trx') no es un ticker; el ticker sale de pay_currency."""
    assert tx_routes._ticker_pagable({"pay_currency": "usdttrc20", "network": "trx"}) == "usdttrc20"
    # Sin pay_currency se reconstruye desde la moneda de origen.
    assert tx_routes._ticker_pagable({"currency_input": "USDT"}) == "usdttrc20"
    assert tx_routes._ticker_pagable({"currency_input": "USDC"}) == "usdc"


def test_vencimiento_del_topup():
    ahora = datetime.now(timezone.utc)
    assert tx_routes._topup_vencido(ahora) is False
    assert tx_routes._topup_vencido(ahora - timedelta(hours=47)) is False
    assert tx_routes._topup_vencido(ahora - timedelta(hours=49)) is True
    # Fechas naive (como las devuelve Mongo) se tratan como UTC.
    assert tx_routes._topup_vencido(datetime.utcnow() - timedelta(hours=49)) is True
    assert tx_routes._topup_vencido(None) is False


# --------------------------------------------------------------------------
# Endpoint de status: vencimiento del topup y campos expuestos
# --------------------------------------------------------------------------

class _Usuario:
    user_id = "user123"


def test_status_expone_los_datos_del_topup(entorno, monkeypatch):
    _instalar_db(monkeypatch, [_orden_con_topup()])

    res = asyncio.run(
        tx_routes.get_crypto_withdrawal_status("tx_abc123", current_user=_Usuario())
    )

    assert res["status"] == "awaiting_topup"
    assert res["topup_pay_address"] == "TTopUpAddress0000000000000000000000"
    assert res["topup_pay_amount"] == 11.5
    assert res["topup_pay_currency"] == "usdttrc20"
    assert res["topup_expires_at"] is not None


def test_status_vence_el_topup_y_lo_pasa_a_revision(entorno, monkeypatch):
    vencido = datetime.now(timezone.utc) - timedelta(hours=49)
    db = _instalar_db(monkeypatch, [_orden_con_topup(topup_created_at=vencido)])

    res = asyncio.run(
        tx_routes.get_crypto_withdrawal_status("tx_abc123", current_user=_Usuario())
    )

    assert res["status"] == "underpaid_review"
    assert "topup_pay_address" not in res
    assert db.transactions.docs[0]["status"] == "underpaid_review"
    assert db.transactions.docs[0]["topup_expired"] is True
    assert entorno.notificaciones[0]["type"] == "crypto_send_underpaid_review"


def test_status_de_orden_ajena_da_404(entorno, monkeypatch):
    _instalar_db(monkeypatch, [_orden_con_topup()])

    from fastapi import HTTPException

    class _Otro:
        user_id = "user999"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tx_routes.get_crypto_withdrawal_status("tx_abc123", current_user=_Otro()))
    assert exc.value.status_code == 404
