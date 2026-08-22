"""
Tests de la medicion de merma real de NOWPayments.

`actually_paid` es lo que entra a la direccion de pago; `outcome_amount` es lo
que NOWPayments acredita al comercio ya descontada su comision interna. El VES
prometido al beneficiario (`amount_output`) se fija al crear la orden y NO se
recalcula: estos tests verifican que ahora la diferencia queda registrada, y
--sobre todo-- que registrarla no cambia una coma de lo que se paga.

Corren AISLADOS igual que test_underpaid_tiers.py: db en memoria, NOWPayments
falso, IPN armado a mano y firmado con la misma HMAC-SHA512 real.

Cubre:
  1. outcome_amount presente        -> merma positiva, amount_output intacto
  2. outcome_amount ausente         -> merma_ves = None (no 0, no excepcion)
  3. outcome_amount ilegible        -> merma_ves = None
  4. outcome convertido > prometido -> merma negativa (valida, no es error)
  5. rama topup: suma de outcomes, y None si falta uno de los dos tramos
  6. el reporte del admin: filtro por fecha, total acumulado y sin_outcome
"""
import asyncio
import copy
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

IPN_KEY = "test-ipn-key"
os.environ.setdefault("NOWPAYMENTS_IPN_KEY", IPN_KEY)

from services import nowpayments as nowpayments_module  # noqa: E402

nowpayments_module.IPN_KEY = IPN_KEY

import routes.transactions as tx_routes  # noqa: E402
import routes.admin as admin_routes  # noqa: E402


# --------------------------------------------------------------------------
# Doble de Mongo
# --------------------------------------------------------------------------

def _match(doc, query):
    for field, cond in query.items():
        value = doc.get(field)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$gte" in cond and not (value is not None and value >= cond["$gte"]):
                return False
            if "$lt" in cond and not (value is not None and value < cond["$lt"]):
                return False
        elif value != cond:
            return False
    return True


def _apply(doc, update):
    for field, value in (update.get("$set") or {}).items():
        doc[field] = value


class _Cursor:
    """Cursor asincrono minimo: solo lo que usa el reporte (sort + async for)."""

    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        self._docs = sorted(
            self._docs,
            key=lambda d: (d.get(field) is None, d.get(field)),
            reverse=direction == -1,
        )
        return self

    def __aiter__(self):
        async def gen():
            for doc in self._docs:
                yield copy.deepcopy(doc)

        return gen()


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return copy.deepcopy(doc)
        return None

    def find(self, query, projection=None):
        return _Cursor([d for d in self.docs if _match(d, query)])

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                return
        return

    async def find_one_and_update(self, query, update, return_document=None):
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                return copy.deepcopy(doc)
        return None


class FakeDB:
    def __init__(self, docs=None, users=None):
        self.transactions = FakeCollection(docs)
        self.users = FakeCollection(users or [])


class FakeRequest:
    def __init__(self, body: bytes, signature: str):
        self._body = body
        self.headers = {"x-nowpayments-sig": signature}

    async def body(self):
        return self._body


def _sign(payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    return raw, hmac.new(IPN_KEY.encode("utf-8"), raw, hashlib.sha512).hexdigest()


ORDER_ID = "send_usdt_user123_abcdef123456"
TOPUP_ORDER_ID = f"topup_{ORDER_ID}"

# 100 USDT a tasa 120 -> 12000 VES prometidos. NOWPayments pide 101 (fee incluida).
RATE = 120.0
PROMETIDO_VES = 12000.0


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
        "amount_output": PROMETIDO_VES,
        "rate": RATE,
        "payment_order_id": ORDER_ID,
        "pay_currency": "usdttrc20",
        "network": "trx",
        "pay_amount": 101.0,
        "funded_from": "payment",
        "paid_ratio": 0.0,
        "created_at": datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def entorno(monkeypatch):
    """Aisla el webhook: side effects espiados, NOWPayments falso."""
    notificaciones = []

    async def fake_create_notification(user_id, title, message, notification_type="info", data=None):
        notificaciones.append(notification_type)
        return "notif_test"

    monkeypatch.setattr(tx_routes, "create_notification", fake_create_notification)

    class FakeNowPayments:
        verify_ipn_signature = staticmethod(nowpayments_module.verify_ipn_signature)

        @staticmethod
        async def get_min_amount(currency, fiat_equivalent="usd"):
            return {"min_amount": 1.0}

        @staticmethod
        async def create_payment(**kwargs):
            return {
                "payment_id": "pay_topup_1",
                "pay_address": "TTopUpAddress0000000000000000000000",
                "pay_amount": 11.5,
                "network": "trx",
            }

    monkeypatch.setattr(tx_routes, "nowpayments", FakeNowPayments)
    return notificaciones


def _instalar_db(monkeypatch, docs, users=None):
    fake_db = FakeDB(docs, users)
    monkeypatch.setattr(tx_routes, "db", fake_db)
    return fake_db


def _webhook(payload):
    raw, sig = _sign(payload)
    return asyncio.run(tx_routes.webhook_crypto_send(FakeRequest(raw, sig)))


# --------------------------------------------------------------------------
# 1. outcome_amount presente -> merma positiva
# --------------------------------------------------------------------------

def test_outcome_presente_calcula_merma_positiva(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])

    # Entraron 101 a la direccion, pero NOWPayments solo acredita 99.5.
    # esperado = 99.5 * 120 = 11940 -> merma = 12000 - 11940 = 60
    res = _webhook({
        "order_id": ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 101.0,
        "outcome_amount": 99.5,
        "outcome_currency": "usdttrc20",
    })

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["outcome_amount"] == 99.5           # guardado tal cual
    assert doc["outcome_currency"] == "usdttrc20"
    assert doc["merma_ves"] == pytest.approx(60.0)
    assert isinstance(doc["merma_calculada_at"], datetime)

    # Lo que importa: no se toco nada de lo que se le paga al beneficiario.
    assert doc["amount_output"] == PROMETIDO_VES
    assert doc["rate"] == RATE
    assert doc["status"] == "pending"


def test_merma_no_altera_el_camino_de_underpaid(entorno, monkeypatch):
    """Medir la merma no debe cambiar el nivel en que cae la orden."""
    db = _instalar_db(monkeypatch, [_orden()])

    # 50/101 = 0.495 -> nivel 3, igual que antes de este cambio.
    res = _webhook({
        "order_id": ORDER_ID,
        "payment_status": "partially_paid",
        "actually_paid": 50.0,
        "outcome_amount": 49.5,
    })

    assert res["status"] == "underpaid_review"
    doc = db.transactions.docs[0]
    assert doc["status"] == "underpaid_review"
    assert doc["amount_output"] == PROMETIDO_VES
    # 12000 - 49.5*120 = 6060
    assert doc["merma_ves"] == pytest.approx(6060.0)


# --------------------------------------------------------------------------
# 2 y 3. outcome_amount ausente o ilegible -> None, nunca 0
# --------------------------------------------------------------------------

def test_sin_outcome_en_el_payload_merma_queda_null(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])

    res = _webhook({
        "order_id": ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 101.0,
    })

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["merma_ves"] is None       # None, NO 0.0
    assert doc["outcome_amount"] is None
    assert doc["amount_output"] == PROMETIDO_VES
    assert doc["status"] == "pending"     # el flujo siguio normal


def test_outcome_ilegible_no_revienta_y_deja_null(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])

    res = _webhook({
        "order_id": ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 101.0,
        "outcome_amount": "no-es-un-numero",
    })

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["merma_ves"] is None
    assert doc["outcome_amount"] == "no-es-un-numero"   # crudo, sin transformar
    assert doc["status"] == "pending"


def test_sin_rate_no_inventa_merma(entorno, monkeypatch):
    """Sin el rate del alta no hay con que convertir: None, no 0."""
    db = _instalar_db(monkeypatch, [_orden(rate=None)])

    _webhook({
        "order_id": ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 101.0,
        "outcome_amount": 99.5,
    })

    doc = db.transactions.docs[0]
    assert doc["merma_ves"] is None
    assert doc["outcome_amount"] == 99.5   # el dato crudo igual se guarda


# --------------------------------------------------------------------------
# 4. merma negativa -> resultado valido
# --------------------------------------------------------------------------

def test_outcome_mayor_al_prometido_da_merma_negativa(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden()])

    # esperado = 101 * 120 = 12120 > 12000 prometidos -> merma = -120
    res = _webhook({
        "order_id": ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 101.0,
        "outcome_amount": 101.0,
    })

    assert res["processed"] is True       # no es un error
    doc = db.transactions.docs[0]
    assert doc["merma_ves"] == pytest.approx(-120.0)
    assert doc["status"] == "pending"
    assert doc["amount_output"] == PROMETIDO_VES


# --------------------------------------------------------------------------
# 5. Rama topup
# --------------------------------------------------------------------------

def _orden_con_topup(**overrides):
    doc = _orden(
        status="awaiting_topup",
        actually_paid=90.0,
        outcome_amount=89.0,
        outcome_currency="usdttrc20",
        paid_ratio=90.0 / 101.0,
        topup_order_id=TOPUP_ORDER_ID,
        topup_pay_amount=11.5,
        topup_pay_currency="usdttrc20",
        topup_created_at=datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc),
    )
    doc.update(overrides)
    return doc


def test_topup_suma_los_dos_outcomes(entorno, monkeypatch):
    db = _instalar_db(monkeypatch, [_orden_con_topup()])

    # total acreditado = 89 + 10 = 99 -> esperado = 11880 -> merma = 120
    res = _webhook({
        "order_id": TOPUP_ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 11.0,
        "outcome_amount": 10.0,
    })

    assert res["processed"] is True
    doc = db.transactions.docs[0]
    assert doc["topup_outcome_amount"] == 10.0
    assert doc["merma_ves"] == pytest.approx(120.0)
    assert doc["amount_output"] == PROMETIDO_VES
    assert doc["status"] == "pending"


def test_topup_sin_outcome_no_suma_parcial(entorno, monkeypatch):
    """Si falta el outcome de un tramo, el total es desconocido: None.

    Sumar solo el tramo conocido daria una merma enorme e inventada.
    """
    db = _instalar_db(monkeypatch, [_orden_con_topup()])

    _webhook({
        "order_id": TOPUP_ORDER_ID,
        "payment_status": "finished",
        "actually_paid": 11.0,
    })

    doc = db.transactions.docs[0]
    assert doc["merma_ves"] is None
    assert doc["amount_output"] == PROMETIDO_VES


# --------------------------------------------------------------------------
# 6. Reporte del admin
# --------------------------------------------------------------------------

def _reporte(monkeypatch, docs, date_from=None, date_to=None):
    """Llama al endpoint directo. Los defaults van explicitos porque sin FastAPI
    resolviendolos los Query(None) llegarian como objetos Query, no como None."""
    fake_db = FakeDB(docs, users=[{"user_id": "user123", "email": "a@b.com", "full_name": "Ana"}])
    monkeypatch.setattr(admin_routes, "db", fake_db)
    return asyncio.run(
        admin_routes.reporte_merma_nowpayments(date_from=date_from, date_to=date_to, admin=None)
    )


def test_reporte_acumula_total_y_cuenta_las_no_medibles(monkeypatch):
    docs = [
        _orden(_id="a", transaction_id="tx_a", merma_ves=60.0, actually_paid=101.0,
               outcome_amount=99.5, status="completed"),
        _orden(_id="b", transaction_id="tx_b", merma_ves=40.0, actually_paid=101.0,
               outcome_amount=99.7, status="completed",
               created_at=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)),
        # medida, pero a favor del negocio
        _orden(_id="c", transaction_id="tx_c", merma_ves=-25.0, actually_paid=101.0,
               outcome_amount=101.2, status="completed",
               created_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)),
        # pago recibido pero el IPN no trajo outcome -> no medible
        _orden(_id="d", transaction_id="tx_d", merma_ves=None, actually_paid=101.0,
               created_at=datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)),
        # nunca se pago -> ni siquiera cuenta como no medible
        _orden(_id="e", transaction_id="tx_e", merma_ves=None,
               created_at=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc)),
    ]
    res = _reporte(monkeypatch, docs)

    assert res["total"] == 3
    assert res["sin_outcome"] == 1
    assert res["totales"]["merma_ves"] == pytest.approx(75.0)          # 60 + 40 - 25
    assert res["totales"]["merma_ves_en_contra"] == pytest.approx(100.0)
    assert res["totales"]["merma_ves_a_favor_del_negocio"] == pytest.approx(-25.0)
    assert [o["orden_id"] for o in res["ordenes"]] == ["tx_a", "tx_b", "tx_c"]
    assert res["ordenes"][0]["user_email"] == "a@b.com"


def test_reporte_filtra_por_rango_de_fechas(monkeypatch):
    docs = [
        _orden(_id="a", transaction_id="tx_a", merma_ves=60.0, actually_paid=101.0,
               created_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)),
        _orden(_id="b", transaction_id="tx_b", merma_ves=40.0, actually_paid=101.0,
               created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)),
    ]
    res = _reporte(monkeypatch, docs, date_from="2026-08-10", date_to="2026-08-10")

    assert res["total"] == 1
    assert res["ordenes"][0]["orden_id"] == "tx_a"
    assert res["totales"]["merma_ves"] == pytest.approx(60.0)


def test_reporte_rechaza_rango_invertido(monkeypatch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _reporte(monkeypatch, [], date_from="2026-08-20", date_to="2026-08-10")
    assert exc.value.status_code == 400
