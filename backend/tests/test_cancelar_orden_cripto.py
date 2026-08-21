"""
Tests del endpoint de cancelacion de una orden de envio cripto (issue #105).

Corren AISLADOS: no tocan Mongo, no llaman a NOWPayments y no levantan el
servidor. Se reemplaza `db` en routes.transactions por una coleccion en memoria
que implementa lo justo que usa el endpoint: find_one_and_update condicionado al
estado (el claim atomico) y find_one para el diagnostico posterior.

Cubre:
  1. Orden en 'awaiting_payment'         -> 200 y queda 'cancelled_by_user'
  2. Carrera: el estado ya cambio        -> 409 y la orden NO se toca
  3. Orden de otro usuario / inexistente -> 404
"""

import asyncio
import copy
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("NOWPAYMENTS_IPN_KEY", "test-ipn-key")

import routes.transactions as tx_routes  # noqa: E402


# ---------------------------------------------------------------------------
# Doble de Mongo: solo lo que usa el endpoint de cancelar.
# ---------------------------------------------------------------------------

def _match(doc, query):
    return all(doc.get(field) == cond for field, cond in query.items())


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return copy.deepcopy(doc)
        return None

    async def find_one_and_update(self, query, update, return_document=None):
        for doc in self.docs:
            if _match(doc, query):
                for field, value in (update.get("$set") or {}).items():
                    doc[field] = value
                return copy.deepcopy(doc)
        return None


class FakeDB:
    def __init__(self, docs=None):
        self.transactions = FakeCollection(docs)


class FakeUser:
    def __init__(self, user_id="user_1"):
        self.user_id = user_id


def _orden(status="awaiting_payment", user_id="user_1"):
    return {
        "transaction_id": "tx_abc",
        "user_id": user_id,
        "type": "withdrawal",
        "status": status,
        "funded_from": "payment",
        "amount_input": 25.0,
        "currency_input": "USDT",
    }


def _instalar_db(monkeypatch, docs):
    fake_db = FakeDB(docs)
    monkeypatch.setattr(tx_routes, "db", fake_db)
    return fake_db


def _cancelar(user_id="user_1", transaction_id="tx_abc"):
    return asyncio.run(
        tx_routes.cancelar_orden_cripto(transaction_id, current_user=FakeUser(user_id))
    )


# ---------------------------------------------------------------------------

def test_cancelar_desde_awaiting_payment_funciona(monkeypatch):
    """Camino feliz: todavia no llego ningun pago, la orden se cancela."""
    db = _instalar_db(monkeypatch, [_orden()])

    resp = _cancelar()

    assert resp["ok"] is True
    assert resp["status"] == "cancelled_by_user"
    assert resp["transaction_id"] == "tx_abc"
    assert db.transactions.docs[0]["status"] == "cancelled_by_user"
    assert db.transactions.docs[0].get("cancelled_at") is not None


@pytest.mark.parametrize(
    "estado_actual",
    ["pending", "awaiting_topup", "underpaid_review", "finished", "cancelled_by_user"],
)
def test_carrera_estado_ya_cambio_devuelve_409(monkeypatch, estado_actual):
    """Carrera con el webhook.

    Si entre que el usuario mira el QR y aprieta el boton entra un pago, el
    webhook ya movio el status. El claim atomico no matchea, asi que no tocamos
    nada y devolvemos 409 para que el frontend refresque el estado real en vez
    de asumir que la orden quedo cancelada.
    """
    db = _instalar_db(monkeypatch, [_orden(status=estado_actual)])

    with pytest.raises(HTTPException) as exc:
        _cancelar()

    assert exc.value.status_code == 409
    assert db.transactions.docs[0]["status"] == estado_actual
    assert "cancelled_at" not in db.transactions.docs[0]


def test_orden_de_otro_usuario_da_404(monkeypatch):
    """No se puede cancelar la orden de otro: ni siquiera se ve."""
    db = _instalar_db(monkeypatch, [_orden(user_id="user_2")])

    with pytest.raises(HTTPException) as exc:
        _cancelar(user_id="user_1")

    assert exc.value.status_code == 404
    assert db.transactions.docs[0]["status"] == "awaiting_payment"


def test_orden_inexistente_da_404(monkeypatch):
    _instalar_db(monkeypatch, [])

    with pytest.raises(HTTPException) as exc:
        _cancelar(transaction_id="tx_no_existe")

    assert exc.value.status_code == 404
