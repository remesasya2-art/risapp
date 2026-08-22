"""
Fase 1: el webhook entrante de WhatsApp no puede tocar plata.

Antes, un mensaje del numero admin autorizado cerraba ordenes sin pasar por el
Panel: "listo" -> completed, "cancelar" -> cancelled + reembolso (siempre a
balance_ris, incluso para envios pagados en USDT/USDC). Este test cierra esa
puerta con la prueba mas fuerte que se puede escribir para el caso: los dobles
de Mongo REGISTRAN CUALQUIER ESCRITURA, y se exige que la lista quede vacia.

Los payloads van firmados con la HMAC real de Twilio (RequestValidator), asi
que atraviesan la validacion de firma y el chequeo de numero autorizado: se
prueba el peor caso, no un mensaje que igual iba a ser rechazado.
"""
import asyncio
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

AUTH_TOKEN = "test-twilio-auth-token"
ADMIN_NUMBER = "whatsapp:+584140000000"
PUBLIC_HOST = "www.risappbr.com"
WEBHOOK_PATH = "/api/webhooks/twilio/whatsapp"

from twilio.request_validator import RequestValidator  # noqa: E402

import routes.webhooks as wh  # noqa: E402


# --------------------------------------------------------------------------
# Dobles: cualquier escritura queda registrada
# --------------------------------------------------------------------------

class WriteAttempt(Exception):
    """Se levanta si el codigo intenta escribir pese al corte."""


class SpyCollection:
    def __init__(self, name, docs, writes):
        self.name = name
        self.docs = list(docs)
        self._writes = writes

    async def find_one(self, query, projection=None, sort=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return copy.deepcopy(doc)
        return None

    async def update_one(self, query, update, **kw):
        self._writes.append((self.name, "update_one", query, update))
        raise WriteAttempt(f"escritura inesperada en {self.name}: {update}")

    async def update_many(self, query, update, **kw):
        self._writes.append((self.name, "update_many", query, update))
        raise WriteAttempt(f"escritura inesperada en {self.name}: {update}")

    async def find_one_and_update(self, query, update, **kw):
        self._writes.append((self.name, "find_one_and_update", query, update))
        raise WriteAttempt(f"escritura inesperada en {self.name}: {update}")

    async def insert_one(self, doc):
        self._writes.append((self.name, "insert_one", None, doc))
        raise WriteAttempt(f"insert inesperado en {self.name}")


class SpyDB:
    def __init__(self, transactions, users):
        self.writes = []
        self.transactions = SpyCollection("transactions", transactions, self.writes)
        self.users = SpyCollection("users", users, self.writes)
        self.notifications = SpyCollection("notifications", [], self.writes)


class FakeURL:
    def __init__(self, path):
        self.scheme = "https"
        self.path = path
        self.query = ""


class FakeRequest:
    def __init__(self, params, signature):
        self._params = params
        self.url = FakeURL(WEBHOOK_PATH)
        self.headers = {
            "X-Twilio-Signature": signature,
            "x-forwarded-proto": "https",
            "x-forwarded-host": PUBLIC_HOST,
            "host": PUBLIC_HOST,
        }

    async def form(self):
        return self._params


def _signed(params):
    """Firma el payload igual que lo haria Twilio contra la URL publica."""
    url = f"https://{PUBLIC_HOST}{WEBHOOK_PATH}"
    signature = RequestValidator(AUTH_TOKEN).compute_signature(url, params)
    return FakeRequest(params, signature)


ORDEN_USDT = {
    "_id": "oid1",
    "transaction_id": "tx_abc123",
    "display_id": "R-0001",
    "user_id": "user123",
    "type": "withdrawal",
    "status": "pending",
    "currency_input": "USDT",       # el caso del bug de moneda
    "currency_output": "VES",
    "amount_input": 100.0,
    "amount_output": 12000.0,
    "whatsapp_active": True,        # la bandera que quedo pegada
    "beneficiary_data": {"full_name": "Beneficiario Test"},
}

USUARIO = {"user_id": "user123", "name": "Usuario Test", "balance_ris": 0.0, "balance_usdt": 0.0}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(wh, "TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setattr(wh, "ADMIN_WHATSAPP_NUMBER", ADMIN_NUMBER)

    async def _no_notificar(*a, **k):
        raise WriteAttempt("no deberia notificarse nada")

    monkeypatch.setattr(wh, "create_notification", _no_notificar)

    def _no_responder(*a, **k):
        raise WriteAttempt("no deberia responderse por WhatsApp")

    monkeypatch.setattr(wh, "send_whatsapp_reply", _no_responder)

    spy = SpyDB([ORDEN_USDT], [USUARIO])
    monkeypatch.setattr(wh, "db", spy)
    return spy


def _post(body="", num_media=0, **extra):
    params = {
        "From": ADMIN_NUMBER,
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": str(num_media),
        "MessageSid": "SM00000000000000000000000000000000",
    }
    params.update(extra)
    return asyncio.run(wh.twilio_whatsapp_webhook(_signed(params)))


def _sin_efecto(res, spy):
    assert res.status_code == 200
    assert spy.writes == [], f"el webhook intento escribir: {spy.writes}"
    doc = spy.transactions.docs[0]
    assert doc["status"] == "pending"
    assert doc["whatsapp_active"] is True     # ni siquiera se limpia la bandera
    assert "completed_at" not in doc
    assert "whatsapp_completed_by" not in doc
    assert "cancelled_at" not in doc
    assert spy.users.docs[0]["balance_ris"] == 0.0
    assert spy.users.docs[0]["balance_usdt"] == 0.0


# --------------------------------------------------------------------------

@pytest.mark.parametrize("comando", ["listo", "lista", "hecho", "completado", "ok", "done"])
def test_listo_no_cierra_la_orden(db, comando):
    """El comando que marcaba completed ahora no hace nada."""
    _sin_efecto(_post(body=comando), db)


@pytest.mark.parametrize("comando", ["cancelar", "cancel", "rechazar"])
def test_cancelar_no_reembolsa_ni_cancela(db, comando):
    """El comando que reembolsaba (y lo hacia en la moneda equivocada) no corre."""
    _sin_efecto(_post(body=comando), db)


def test_imagen_no_se_acumula(db):
    """Las imagenes ya no se descargan ni se agregan a proof_images."""
    res = _post(
        num_media=1,
        MediaUrl0="https://api.twilio.com/2010-04-01/Accounts/AC0/Messages/MM0/Media/ME0",
        MediaContentType0="image/jpeg",
    )
    _sin_efecto(res, db)
    assert "proof_images" not in db.transactions.docs[0]


def test_info_y_comandos_desconocidos_tampoco_responden(db):
    """Ni siquiera los comandos de solo lectura contestan: no sale nada por Twilio."""
    _sin_efecto(_post(body="info"), db)
    _sin_efecto(_post(body="cualquier otra cosa"), db)


def test_mayusculas_y_espacios_tampoco_pasan(db):
    """El handler normaliza a minusculas; el corte va despues, asi que igual cae."""
    _sin_efecto(_post(body="  LISTO  "), db)


def test_firma_invalida_sigue_siendo_403(db):
    """El corte no aflojo la validacion de firma: sigue rechazando lo no firmado."""
    req = FakeRequest({"From": ADMIN_NUMBER, "Body": "listo", "NumMedia": "0"}, "firma-falsa")
    res = asyncio.run(wh.twilio_whatsapp_webhook(req))
    assert res.status_code == 403
    assert db.writes == []


def test_la_bandera_de_corte_esta_puesta():
    """Guarda explicita: si alguien la apaga sin querer, este test lo grita."""
    assert wh.WHATSAPP_INBOUND_DISABLED is True
