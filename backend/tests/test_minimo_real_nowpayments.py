"""
El minimo que mostramos tiene que ser el que NOWPayments realmente exige.

CONTEXTO
    NOWPayments devuelve DOS minimos distintos para la misma moneda segun contra
    que se la consulte. Para usdttrc20:
        currency_to=usdttrc20 -> 11.72 USDT   (minimo "directo")
        currency_to=usd       -> 12.36 USDT   (minimo via su exchange interno)
    Todos nuestros pagos se crean con is_fee_paid_by_user=True + fixed_rate=True,
    o sea que pasan por el exchange: el minimo que aplica es el segundo. Con el
    primero le mostrabamos al usuario un piso mas bajo del que la pasarela iba a
    exigir y el pago fallaba con un error generico (confirmado en produccion:
    12.05 rechazado, 13 aceptado).

QUE SE CUBRE
    1. get_min_amount consulta currency_to = la moneda fiat, no la cripto.
    2. El margen de seguridad del 10% se aplica una sola vez y redondea hacia arriba.
    3. effective_min_amount: margen, piso de negocio, respaldo y cache.
    4. El envio cripto (camino B) rechaza el monto insuficiente ANTES de escribir
       la orden en la base — no quedan mas filas huerfanas en payment_error.
    5. Cuando NOWPayments rechaza igual, el motivo real llega al usuario.

No se toca la red ni Mongo: httpx.MockTransport para la API y dobles en memoria
para la base, con asyncio.run() dentro de tests sincronos como el resto de la suite.
"""
import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import nowpayments  # noqa: E402
from services import min_amount as min_amount_module  # noqa: E402
import routes.transactions as tx_routes  # noqa: E402
import routes.credits as credits_routes  # noqa: E402


@pytest.fixture(autouse=True)
def cache_limpia():
    """Cada test arranca sin cache de minimos (es estado de proceso)."""
    min_amount_module.clear_cache()
    yield
    min_amount_module.clear_cache()


@pytest.fixture
def api_falsa(monkeypatch):
    """Reemplaza el transporte de httpx y devuelve la lista de requests vistos."""
    vistos = []

    def instalar(handler):
        original = httpx.AsyncClient

        def fabricar(*args, **kwargs):
            def envoltura(request: httpx.Request) -> httpx.Response:
                vistos.append(request)
                return handler(request)
            kwargs["transport"] = httpx.MockTransport(envoltura)
            return original(*args, **kwargs)

        monkeypatch.setattr(nowpayments.httpx, "AsyncClient", fabricar)
        return vistos

    return instalar


# --------------------------------------------------------------------------
# 1. La consulta va contra la moneda fiat
# --------------------------------------------------------------------------

def test_get_min_amount_consulta_currency_to_fiat(api_falsa):
    vistos = api_falsa(lambda req: httpx.Response(200, json={"min_amount": 12.363435}))

    asyncio.run(nowpayments.get_min_amount("usdttrc20"))

    params = vistos[0].url.params
    assert params["currency_from"] == "usdttrc20"
    # El fix: antes iba "usdttrc20" y devolvia el minimo directo (mas bajo).
    assert params["currency_to"] == "usd"
    assert params["fiat_equivalent"] == "usd"


def test_get_min_amount_respeta_otro_fiat(api_falsa):
    vistos = api_falsa(lambda req: httpx.Response(200, json={"min_amount": 1.0}))

    asyncio.run(nowpayments.get_min_amount("usdcerc20", fiat_equivalent="eur"))

    assert vistos[0].url.params["currency_to"] == "eur"


# --------------------------------------------------------------------------
# 2. El margen
# --------------------------------------------------------------------------

def test_margen_redondea_hacia_arriba():
    # 12.363435 * 1.10 = 13.5997785 -> 13.60 (nunca 13.59: comeria el margen)
    assert min_amount_module.with_margin(12.363435) == 13.60
    assert min_amount_module.with_margin(11.72) == 12.90
    assert min_amount_module.with_margin(10.0) == 11.0


# --------------------------------------------------------------------------
# 3. effective_min_amount
# --------------------------------------------------------------------------

def _instalar_min_amount(monkeypatch, valores):
    """Doble de nowpayments.get_min_amount; `valores` se consume por llamada.

    Un elemento float devuelve ese min_amount, una excepcion la levanta.
    Devuelve la lista de tickers consultados.
    """
    consultados = []
    pendientes = list(valores)

    async def fake_get_min_amount(currency, fiat_equivalent="usd"):
        consultados.append(currency)
        valor = pendientes.pop(0) if pendientes else valores[-1]
        if isinstance(valor, Exception):
            raise valor
        return {"min_amount": valor, "currency_from": currency}

    monkeypatch.setattr(min_amount_module.nowpayments, "get_min_amount", fake_get_min_amount)
    return consultados


def test_effective_min_aplica_margen_y_conserva_el_crudo(monkeypatch):
    _instalar_min_amount(monkeypatch, [12.363435])

    info = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))

    assert info["min_amount"] == 13.60
    assert info["min_amount_raw"] == 12.363435
    assert info["source"] == "nowpayments"


def test_effective_min_respeta_el_piso_de_negocio(monkeypatch):
    _instalar_min_amount(monkeypatch, [1.0])

    info = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))

    # 1.0 con margen es 1.10, pero por debajo de 10 no operamos.
    assert info["min_amount"] == 10.0
    assert info["min_amount_raw"] == 1.0


def test_effective_min_cae_al_respaldo_si_la_api_falla(monkeypatch):
    _instalar_min_amount(monkeypatch, [RuntimeError("min-amount caido")])

    info = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))

    assert info["min_amount"] == 10.0
    assert info["min_amount_raw"] is None
    assert info["source"] == "fallback"


def test_effective_min_cachea_por_moneda_y_red(monkeypatch):
    consultados = _instalar_min_amount(monkeypatch, [12.363435, 30.0])

    primera = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))
    segunda = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))

    assert consultados == ["usdttrc20"], "la segunda consulta tenia que salir de la cache"
    assert primera == segunda

    # Otra red es otra clave: si consulta.
    asyncio.run(min_amount_module.effective_min_amount("usdtbsc"))
    assert consultados == ["usdttrc20", "usdtbsc"]


def test_effective_min_no_cachea_el_respaldo(monkeypatch):
    _instalar_min_amount(monkeypatch, [RuntimeError("caido"), 12.363435])

    primera = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))
    segunda = asyncio.run(min_amount_module.effective_min_amount("usdttrc20"))

    assert primera["source"] == "fallback"
    # Una caida pasajera no puede quedar pegada varios minutos.
    assert segunda["source"] == "nowpayments"
    assert segunda["min_amount"] == 13.60


# --------------------------------------------------------------------------
# 4. El envio cripto no escribe la orden si el monto no llega al minimo
# --------------------------------------------------------------------------

class _ColeccionFalsa:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.insertados = []
        self.actualizados = []

    async def find_one(self, query=None, projection=None, sort=None):
        return self.docs[0] if self.docs else None

    async def insert_one(self, doc):
        self.insertados.append(doc)
        return type("R", (), {"inserted_id": "fake"})()

    async def update_one(self, query, update, **kwargs):
        self.actualizados.append((query, update))
        return type("R", (), {"modified_count": 1})()


class _DBFalsa:
    def __init__(self, beneficiario, tasa):
        self.beneficiaries = _ColeccionFalsa([beneficiario])
        self.rates = _ColeccionFalsa([tasa])
        self.transactions = _ColeccionFalsa()


@pytest.fixture
def envio(monkeypatch):
    """Aisla /withdraw-crypto: base en memoria, idempotencia y NOWPayments falsos."""
    db = _DBFalsa(
        beneficiario={
            "beneficiary_id": "ben_1", "user_id": "user_1", "full_name": "Ana Perez",
            "id_document": "V12345678", "bank": "Banesco", "bank_code": "0134",
            "phone_number": "04141234567", "account_number": "01340000000000000000",
            "payment_type": "transferencia",
        },
        tasa={"usdtris_to_ves": 40.0, "usdcris_to_ves": 40.0},
    )
    pagos = []

    class FakeNowPayments:
        mensaje_de_error = staticmethod(nowpayments.mensaje_de_error)

        @staticmethod
        async def create_payment(**kwargs):
            pagos.append(kwargs)
            return {
                "payment_id": "pay_1",
                "pay_address": "TDireccionDePrueba00000000000000000",
                "pay_amount": 14.2,
                "network": "trx",
            }

    async def fake_claim(*a, **k):
        return True, None

    async def fake_store(*a, **k):
        return None

    async def fake_next_id():
        return "W-0001"

    async def fake_notify(**k):
        return "notif"

    monkeypatch.setattr(tx_routes, "db", db)
    monkeypatch.setattr(tx_routes, "nowpayments", FakeNowPayments)
    monkeypatch.setattr(tx_routes, "claim_idempotency", fake_claim)
    monkeypatch.setattr(tx_routes, "store_idempotency_result", fake_store)
    monkeypatch.setattr(tx_routes, "get_next_withdrawal_id", fake_next_id)
    monkeypatch.setattr(tx_routes, "create_notification", fake_notify)
    return {"db": db, "pagos": pagos}


class _Usuario:
    user_id = "user_1"
    email = "ana@example.com"


def _pedido(monto):
    return tx_routes.CryptoSendRequest(
        currency="usdt", amount=monto, beneficiary_id="ben_1",
        network="usdttrc20", use_balance=False, idempotency_key="idem_1",
    )


def _fijar_minimo(monkeypatch, minimo):
    async def fake_effective(pay_currency, **kwargs):
        return {"min_amount": minimo, "min_amount_raw": minimo / 1.1, "source": "nowpayments"}
    monkeypatch.setattr(tx_routes, "effective_min_amount", fake_effective)


def test_envio_por_debajo_del_minimo_no_escribe_nada(envio, monkeypatch):
    from fastapi import HTTPException

    _fijar_minimo(monkeypatch, 13.60)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tx_routes.create_crypto_withdrawal(_pedido(12.05), current_user=_Usuario()))

    assert exc.value.status_code == 400
    assert "13.60" in exc.value.detail
    # Lo que motiva el cambio: antes quedaba una fila huerfana en payment_error.
    assert envio["db"].transactions.insertados == []
    assert envio["db"].transactions.actualizados == []
    assert envio["pagos"] == []


def test_envio_en_el_minimo_crea_la_orden(envio, monkeypatch):
    _fijar_minimo(monkeypatch, 13.60)

    resp = asyncio.run(tx_routes.create_crypto_withdrawal(_pedido(13.60), current_user=_Usuario()))

    assert resp["status"] == "awaiting_payment"
    assert len(envio["db"].transactions.insertados) == 1
    assert len(envio["pagos"]) == 1
    # No se toca la decision de negocio de quien paga la comision.
    assert envio["pagos"][0]["is_fee_paid_by_user"] is True


def test_envio_usa_el_minimo_de_la_red_pedida(envio, monkeypatch):
    consultadas = []

    async def fake_effective(pay_currency, **kwargs):
        consultadas.append(pay_currency)
        return {"min_amount": 5.0, "min_amount_raw": 4.5, "source": "nowpayments"}

    monkeypatch.setattr(tx_routes, "effective_min_amount", fake_effective)
    asyncio.run(tx_routes.create_crypto_withdrawal(_pedido(10.0), current_user=_Usuario()))

    assert consultadas == ["usdttrc20"]


# --------------------------------------------------------------------------
# 5. El motivo real del rechazo llega al usuario
# --------------------------------------------------------------------------

def _error_http(status: int, body: str, content_type: str = "application/json"):
    request = httpx.Request("POST", "https://api.nowpayments.io/v1/payment")
    response = httpx.Response(status, text=body, headers={"content-type": content_type}, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_mensaje_de_error_extrae_el_message():
    exc = _error_http(400, json.dumps({
        "statusCode": 400, "code": "AMOUNT_MINIMAL_ERROR", "message": "amountTo is too small",
    }))
    assert nowpayments.mensaje_de_error(exc) == "amountTo is too small"


def test_mensaje_de_error_devuelve_none_si_no_es_json():
    exc = _error_http(502, "<html><body>Bad Gateway</body></html>", content_type="text/html")
    assert nowpayments.mensaje_de_error(exc) is None


def test_mensaje_de_error_devuelve_none_sin_respuesta():
    assert nowpayments.mensaje_de_error(RuntimeError("timeout")) is None


def test_detalle_error_pago_incluye_el_motivo():
    exc = _error_http(400, json.dumps({"message": "amountTo is too small"}))

    detalle_envio = tx_routes._detalle_error_pago(exc)
    detalle_deposito = credits_routes._detalle_error_pago(exc)

    for detalle in (detalle_envio, detalle_deposito):
        assert "amountTo is too small" in detalle
        assert detalle.startswith("No se pudo iniciar el pago.")


def test_detalle_error_pago_cae_al_generico():
    exc = _error_http(502, "no json aca", content_type="text/plain")

    assert tx_routes._detalle_error_pago(exc) == tx_routes.ERROR_PAGO_GENERICO
    assert credits_routes._detalle_error_pago(exc) == credits_routes.ERROR_PAGO_GENERICO


def test_envio_propaga_el_motivo_de_la_pasarela(envio, monkeypatch):
    from fastapi import HTTPException

    _fijar_minimo(monkeypatch, 5.0)

    class NowPaymentsQueRechaza:
        mensaje_de_error = staticmethod(nowpayments.mensaje_de_error)

        @staticmethod
        async def create_payment(**kwargs):
            raise _error_http(400, json.dumps({"message": "amountTo is too small"}))

    monkeypatch.setattr(tx_routes, "nowpayments", NowPaymentsQueRechaza)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(tx_routes.create_crypto_withdrawal(_pedido(10.0), current_user=_Usuario()))

    assert exc.value.status_code == 502
    assert "amountTo is too small" in exc.value.detail
    # La orden si se inserto (el rechazo no era previsible) y queda marcada.
    assert envio["db"].transactions.actualizados[-1][1]["$set"]["status"] == "payment_error"


# --------------------------------------------------------------------------
# 6. /credits/networks ordena de menor a mayor minimo
# --------------------------------------------------------------------------

def test_networks_devuelve_minimo_por_red_y_ordena(monkeypatch):
    minimos = {"usdttrc20": 13.60, "usdtbsc": 11.00, "usdterc20": 42.00}

    async def fake_merchant_coins():
        return ["usdttrc20", "usdterc20", "usdtbsc", "usdcerc20"]

    async def fake_effective(pay_currency, **kwargs):
        return {"min_amount": minimos[pay_currency], "min_amount_raw": None, "source": "nowpayments"}

    monkeypatch.setattr(credits_routes.nowpayments, "get_merchant_coins", fake_merchant_coins)
    monkeypatch.setattr(credits_routes, "effective_min_amount", fake_effective)

    resp = asyncio.run(credits_routes.list_networks(currency="usdt", current_user=_Usuario()))

    tickers = [n["ticker"] for n in resp["networks"]]
    assert tickers == ["usdtbsc", "usdttrc20", "usdterc20"]
    assert [n["min_amount"] for n in resp["networks"]] == [11.00, 13.60, 42.00]
    # La red por defecto sigue marcada aunque ya no sea la primera.
    assert [n["ticker"] for n in resp["networks"] if n["is_default"]] == ["usdttrc20"]
