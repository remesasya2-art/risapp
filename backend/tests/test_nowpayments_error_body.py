"""
El cuerpo del error de NOWPayments tiene que quedar en el log.

Antes, las 5 funciones que hablan con la API usaban `raise_for_status()` pelado.
httpx pone en la excepcion solo "Client error '400 Bad Request' for url ...", asi
que el motivo real -- por ejemplo AMOUNT_MINIMAL_ERROR con el minimo exacto -- se
perdia, y arriba se veia un 502 generico imposible de diagnosticar.

No se crea ningun pago real: se usa httpx.MockTransport para simular la respuesta
de NOWPayments, asi que estos tests no tocan la red ni la cuenta del comercio.

Corren con asyncio.run() dentro de tests sincronos, como el resto de la suite, para
no sumar pytest-asyncio como dependencia nueva.
"""
import asyncio
import json
import logging
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import nowpayments  # noqa: E402


# Un 400 real de NOWPayments, con la forma que devuelve la API.
CUERPO_400 = json.dumps({
    "statusCode": 400,
    "code": "AMOUNT_MINIMAL_ERROR",
    "message": "amount_minimal_error: minimal amount for usdttrc20 is 11.78",
})


@pytest.fixture
def responder(monkeypatch):
    """Hace que cualquier AsyncClient del modulo hable con un transporte falso."""
    def instalar(status: int, body: str, content_type: str = "application/json"):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text=body, headers={"content-type": content_type})

        original = httpx.AsyncClient

        def fabricar(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(*args, **kwargs)

        monkeypatch.setattr(nowpayments.httpx, "AsyncClient", fabricar)
    return instalar


def _kwargs_create_payment():
    return dict(
        price_amount=11.83,
        price_currency="usd",
        pay_currency="usdttrc20",
        order_id="send_usdt_user123_abc",
        order_description="Envio de prueba",
        is_fee_paid_by_user=True,
    )


def _kwargs_create_invoice():
    return dict(
        price_amount=10.0,
        price_currency="usd",
        pay_currency="usdttrc20",
        order_id="dep_user123_abc",
        order_description="Deposito de prueba",
    )


LLAMADAS = {
    "get_status": lambda: nowpayments.get_status(),
    "get_min_amount": lambda: nowpayments.get_min_amount("usdttrc20"),
    "get_merchant_coins": lambda: nowpayments.get_merchant_coins(),
    "create_invoice": lambda: nowpayments.create_invoice(**_kwargs_create_invoice()),
    "create_payment": lambda: nowpayments.create_payment(**_kwargs_create_payment()),
}


# --------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", sorted(LLAMADAS))
def test_el_cuerpo_del_400_queda_en_el_log(nombre, responder, caplog):
    """Las 5 funciones dejan el cuerpo del error en el log y siguen fallando igual."""
    responder(400, CUERPO_400)

    with caplog.at_level(logging.ERROR, logger="services.nowpayments"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(LLAMADAS[nombre]())

    logueado = "\n".join(r.getMessage() for r in caplog.records)
    assert "AMOUNT_MINIMAL_ERROR" in logueado, f"{nombre}: el cuerpo no llego al log"
    assert "minimal amount for usdttrc20 is 11.78" in logueado
    assert "HTTP 400" in logueado


def test_el_contexto_identifica_la_llamada(responder, caplog):
    """El log dice QUE llamada fallo, no solo que fallo algo."""
    responder(400, CUERPO_400)

    with caplog.at_level(logging.ERROR, logger="services.nowpayments"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(nowpayments.create_payment(**_kwargs_create_payment()))

    logueado = "\n".join(r.getMessage() for r in caplog.records)
    assert "POST /payment" in logueado
    assert "usdttrc20" in logueado           # la red que fallo
    assert "11.83" in logueado               # el monto que fallo
    assert "send_usdt_user123_abc" in logueado   # para cruzar con la orden


def test_la_excepcion_se_relanza_sin_cambios(responder):
    """Loguear no cambia el comportamiento: el llamador sigue viendo el mismo error.

    routes/transactions.py depende de que create_payment levante para marcar la
    orden payment_error y responder 502.
    """
    responder(400, CUERPO_400)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        asyncio.run(nowpayments.create_payment(**_kwargs_create_payment()))

    assert exc.value.response.status_code == 400
    assert "AMOUNT_MINIMAL_ERROR" in exc.value.response.text


def test_un_cuerpo_enorme_se_corta(responder, caplog):
    """Un 502 de proxy puede devolver HTML entero; no queremos eso completo en el log."""
    responder(502, "<html>" + "x" * 9000 + "</html>", content_type="text/html")

    with caplog.at_level(logging.ERROR, logger="services.nowpayments"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(nowpayments.get_status())

    logueado = "\n".join(r.getMessage() for r in caplog.records)
    assert len(logueado) < nowpayments._MAX_BODY_LOG + 500
    assert "chars)" in logueado          # deja constancia de cuanto se corto


def test_un_cuerpo_vacio_no_rompe(responder, caplog):
    """Sin cuerpo el log tiene que decirlo, no fallar al formatear."""
    responder(500, "")

    with caplog.at_level(logging.ERROR, logger="services.nowpayments"):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(nowpayments.get_status())

    logueado = "\n".join(r.getMessage() for r in caplog.records)
    assert "(vacio)" in logueado
    assert "HTTP 500" in logueado


def test_una_respuesta_ok_no_loguea_nada(responder, caplog):
    """El camino feliz queda igual que siempre: sin ruido en el log."""
    responder(200, json.dumps({"min_amount": 11.781252, "currency_from": "usdttrc20"}))

    with caplog.at_level(logging.ERROR, logger="services.nowpayments"):
        data = asyncio.run(nowpayments.get_min_amount("usdttrc20"))

    assert data["min_amount"] == 11.781252
    assert caplog.records == []
