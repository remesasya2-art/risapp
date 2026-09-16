"""
tests/test_un_cobro_sin_codigo_no_es_un_cobro.py

QUE PASABA

    Cuando Mercado Pago no devolvía un código PIX, la ruta escribía un aviso en
    el registro, GUARDABA el cobro con el código vacío, y contestaba 200.

    La persona veía la pantalla de pago con «Código no disponible» donde va el
    código para copiar. O sea: pidió recargar, la aplicación le dijo que sí, y
    le dio algo que no se puede pagar.

    Y en la base quedaba un cobro `pending` que nadie iba a pagar nunca,
    ocupando lugar en la lista de pendientes hasta vencer.

CUANDO PASO

    Al cambiar de aplicación en Mercado Pago, el token quedó inválido:

        ERROR: Failed to create PIX payment:
               {'code': 'unauthorized', 'message': 'invalid access token'}
        INFO:  "POST /api/gestor/pix/create HTTP/1.1"  200 OK

    Durante ese rato, cada intento de recarga se vio como una pantalla rota en
    vez de como un error. Encontrar la causa costó el doble, porque el síntoma
    —«Código no disponible»— no apunta a un problema de credenciales.

QUE PRUEBA ESTE ARCHIVO

    Las dos mitades: que falle diciendo qué pasa, y que NO deje basura en la
    base. La segunda es la que se olvida: una ruta puede fallar correctamente y
    haber guardado igual.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import HTTPException                            # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock  # noqa: E402
from models.user import User                                 # noqa: E402
from routes import gestor_pix                                # noqa: E402
from services.money import to_decimal128                     # noqa: E402

ensenarle_decimal128_a_mongomock()

UN_GESTOR = User(user_id="g_1", email="gestor@ejemplo.com", name="Gestor",
                 role="user")


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_cobro_sin_codigo"]
    usar_base(b)
    corre(b.users.insert_one({
        "user_id": "g_1", "email": "gestor@ejemplo.com", "name": "Gestor",
        "role": "user", "verification_status": "verified",
        "cpf_number": "11144477735",
        "balance_ris": to_decimal128(0),
    }))
    return b


def _pedir(base, request_extra=None):
    """Pide un cobro PIX como lo pide la pantalla."""
    datos = gestor_pix.CreatePixRequest(
        amount_ris=10.0, client_name="Ana Silva",
        client_email="ana@ejemplo.com", client_cpf="11144477735",
        **(request_extra or {}))
    return corre(gestor_pix.create_pix_payment(datos, current_user=UN_GESTOR))


def _mercadopago_caido(monkeypatch, resultado):
    """Mercado Pago contesta lo que se le diga, sin red de por medio."""
    class _Falso:
        def create_pix_payment(self, **kwargs):
            return resultado

    monkeypatch.setattr(gestor_pix, "MP_AVAILABLE", True)
    monkeypatch.setattr(gestor_pix, "mercadopago_service", _Falso())


# ══════════════════════════════════════════════════════════════════════════
# 1. Falla, y dice qué pasa
# ══════════════════════════════════════════════════════════════════════════

def test_EL_TOKEN_INVALIDO_DEVUELVE_UN_ERROR_Y_NO_UN_200(base, monkeypatch):
    """El caso exacto que pasó: el token quedó inválido al cambiar de
    aplicación en Mercado Pago."""
    _mercadopago_caido(monkeypatch, {
        "success": False, "error": "invalid access token", "cause": []})

    with pytest.raises(HTTPException) as e:
        _pedir(base)
    assert e.value.status_code == 503


def test_EL_MENSAJE_NO_LE_ECHA_LA_CULPA_AL_CLIENTE(base, monkeypatch):
    """Y ofrece la otra forma de pagar.

    Casi siempre falla uno solo de los dos caminos, así que decirle «probá con
    tarjeta» le resuelve el problema ahora en vez de mandarlo a esperar.
    """
    _mercadopago_caido(monkeypatch, {"success": False, "error": "lo que sea"})

    with pytest.raises(HTTPException) as e:
        _pedir(base)
    mensaje = str(e.value.detail).lower()
    assert "tarjeta" in mensaje, f"no ofrece la alternativa: {e.value.detail}"
    for palabra in ("error interno", "500", "exception", "traceback"):
        assert palabra not in mensaje


def test_TAMPOCO_PASA_SI_MERCADO_PAGO_DEVUELVE_UN_CODIGO_VACIO(base, monkeypatch):
    """`success: True` con el código vacío es el caso traicionero.

    Contesta que sí y no trae nada: si se mirara sólo `success`, se guardaría
    un cobro impagable igual que antes.
    """
    _mercadopago_caido(monkeypatch, {
        "success": True, "payment_id": 123, "qr_code": "", "qr_code_base64": ""})

    with pytest.raises(HTTPException) as e:
        _pedir(base)
    assert e.value.status_code == 503


# ══════════════════════════════════════════════════════════════════════════
# 2. Y no deja basura en la base
# ══════════════════════════════════════════════════════════════════════════

def test_NO_QUEDA_UN_COBRO_PENDIENTE_QUE_NADIE_VA_A_PAGAR(base, monkeypatch):
    """La mitad que se olvida.

    Una ruta puede fallar correctamente Y haber guardado igual. Cada cobro
    fantasma se queda en la lista de pendientes hasta vencer, y quien la mira
    no tiene cómo distinguirlo de uno real.
    """
    _mercadopago_caido(monkeypatch, {"success": False, "error": "lo que sea"})

    with pytest.raises(HTTPException):
        _pedir(base)

    quedaron = corre(base.gestor_pix_payments.count_documents({}))
    assert quedaron == 0, (
        f"quedaron {quedaron} cobros guardados sin código. Van a aparecer como "
        "pendientes y nadie va a poder pagarlos.")


# ══════════════════════════════════════════════════════════════════════════
# 3. Y el camino bueno sigue andando
# ══════════════════════════════════════════════════════════════════════════

def test_CON_CODIGO_EL_COBRO_SE_CREA_COMO_SIEMPRE(base, monkeypatch):
    """La otra mitad: que la guarda no rompa el caso normal.

    Sin esto, una guarda que rechaza TODO pasaría los tres tests de arriba.
    """
    _mercadopago_caido(monkeypatch, {
        "success": True, "payment_id": 178336825747,
        "qr_code": "00020126580014BR.GOV.BCB.PIX...",
        "qr_code_base64": "iVBORw0KGgo=",
    })

    salida = _pedir(base)
    assert salida.get("payment_id")
    assert corre(base.gestor_pix_payments.count_documents({})) == 1

    guardado = corre(base.gestor_pix_payments.find_one({}))
    assert guardado["qr_code"], "se guardó sin código"
    assert guardado["status"] == "pending"
