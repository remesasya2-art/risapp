"""
tests/test_pago_tarjeta.py — El pago con tarjeta, de punta a punta.

POR QUE ESTE ARCHIVO EXISTE

    `routes/payments_card.py` es el segundo camino por el que entra plata, y no
    tenía un solo test que lo importara. En el PR #57 lo reescribí —el crédito
    pasó de un `$inc` a mano a `services.saldos.mover`— sin nada que ejercitara
    el sitio de la llamada.

    Es el segundo de los seis módulos que mueven plata y estaban sin cubrir.

QUE SE PRUEBA, Y POR QUE ESO

    La ruta cobra una tarjeta de verdad contra Mercado Pago. Lo que puede salir
    mal no es el «camino feliz»: es cobrar y no acreditar, acreditar sin cobrar,
    o acreditar dos veces. Además tiene una puerta de KYC que, si se cae, deja
    entrar plata sin identificar — lo primero que mira cualquier proveedor de
    pagos.

    Mercado Pago se reemplaza por un doble que contesta lo que se le diga. No es
    por comodidad: cobrarle a una tarjeta desde un test es exactamente lo que un
    test no puede hacer.
"""
import asyncio
import os
import sys
import types
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import bancos, ledger, saldos                         # noqa: E402


def _cargar_payments_card():
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete
    if "routes.dependencies" not in sys.modules:
        deps = types.ModuleType("routes.dependencies")
        for nombre in ("get_current_user", "get_admin_user", "get_crm_user",
                       "get_super_admin", "get_verified_user"):
            setattr(deps, nombre, (lambda n: (lambda: None))(nombre))
        sys.modules["routes.dependencies"] = deps
    import routes.payments_card as pc
    return pc


pc = _cargar_payments_card()
from fastapi import HTTPException                                   # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


class _Usuario:
    def __init__(self, verificado=True, user_id="usr_ana"):
        self.user_id = user_id
        self.email = "ana@x.com"
        self.name = "Ana"
        self.role = "user"
        self.verification_status = "verified" if verificado else "pending"


class _RespuestaMP:
    """Lo que devuelve la API de Mercado Pago, sin salir a la red."""
    def __init__(self, status_code=201, cuerpo=None):
        self.status_code = status_code
        self._cuerpo = cuerpo if cuerpo is not None else {}

    def json(self):
        return self._cuerpo


class _ClienteMP:
    """Reemplaza a `httpx.AsyncClient`. Guarda lo que se le pidió."""
    respuesta = None
    error = None
    llamadas = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _ClienteMP.llamadas.append({"url": url, "json": json, "headers": headers})
        if _ClienteMP.error:
            raise _ClienteMP.error
        return _ClienteMP.respuesta


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True

    _ClienteMP.llamadas = []
    _ClienteMP.error = None
    _ClienteMP.respuesta = _RespuestaMP(201, {
        "id": 998877, "status": "approved", "status_detail": "accredited"})
    monkeypatch.setattr(pc.httpx, "AsyncClient", _ClienteMP)
    monkeypatch.setenv("MERCADOPAGO_ACCESS_TOKEN", "TEST-TOKEN")

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(pc, "create_notification", _nada)
    return b


async def _con_saldo(base, monto=0, user_id="usr_ana"):
    await base.users.insert_one({
        "user_id": user_id, "email": "ana@x.com", "name": "Ana",
        "role": "user", "balance_ris": d(monto)})


def _cuerpo(monto=100.0, tipo="credit_card"):
    return pc.CardPaymentInput(
        token="tok_123", amount_ris=monto, payment_method_id="visa",
        payment_type_id=tipo, payer_email="ana@x.com",
        identification=pc.PayerIdentification(type="CPF", number="12345678900"))


async def _lineas(base, user_id="usr_ana"):
    return await base.ledger.find({"user_id": user_id}).to_list(50)


# ══════════════════════════════════════════════════════════════════════════
# 1. Las puertas: lo que NO tiene que llegar a cobrarse
# ══════════════════════════════════════════════════════════════════════════

def test_un_usuario_sin_verificar_no_puede_pagar_con_tarjeta(base):
    """La puerta de KYC. Si se cae, entra plata sin identificar — lo primero
    que mira cualquier proveedor de pagos."""
    async def caso():
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(), current_user=_Usuario(verificado=False))
        assert e.value.status_code == 403
        assert _ClienteMP.llamadas == [], "no se puede haber llamado a Mercado Pago"
        assert await _lineas(base) == []
    corre(caso())


@pytest.mark.parametrize("monto", [4.99, 5000.01])
def test_los_montos_fuera_de_rango_se_rechazan_antes_de_cobrar(base, monto):
    async def caso():
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(monto), current_user=_Usuario())
        assert e.value.status_code == 400
        assert _ClienteMP.llamadas == []
    corre(caso())


@pytest.mark.parametrize("monto", [5.0, 5000.0])
def test_los_montos_en_el_borde_SI_se_aceptan(base, monto):
    """El borde exacto tiene que entrar: rechazarlo es rechazar plata buena."""
    async def caso():
        await _con_saldo(base)
        r = await pc.process_card_payment(_cuerpo(monto), current_user=_Usuario())
        assert r["status"] == "approved"
    corre(caso())


def test_un_tipo_de_tarjeta_inventado_se_rechaza(base):
    async def caso():
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(tipo="cripto"), current_user=_Usuario())
        assert e.value.status_code == 400
        assert _ClienteMP.llamadas == []
    corre(caso())


def test_sin_token_de_mercado_pago_no_se_intenta_cobrar(base, monkeypatch):
    async def caso():
        monkeypatch.delenv("MERCADOPAGO_ACCESS_TOKEN", raising=False)
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(), current_user=_Usuario())
        assert e.value.status_code == 500
        assert _ClienteMP.llamadas == []
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Cobrar y acreditar: que las dos cosas pasen, o ninguna
# ══════════════════════════════════════════════════════════════════════════

def test_un_pago_aprobado_acredita_y_asienta(base):
    async def caso():
        await _con_saldo(base)
        r = await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert r["status"] == "approved"
        assert r["amount_ris_credited"] == 100.0

        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("100.00")

        linea, = await _lineas(base)
        assert linea["movement_type"] == "pago_tarjeta"
        assert linea["direction"] == "credit"
        assert linea["amount"] == 100.0
        assert linea["reference"] == {"kind": "card_payment", "id": "998877"}
        assert linea["actor"]["type"] == "user"
    corre(caso())


def test_un_pago_RECHAZADO_no_acredita_nada(base):
    """Cobrar sin acreditar es malo; acreditar sin cobrar es peor."""
    async def caso():
        _ClienteMP.respuesta = _RespuestaMP(201, {
            "id": 55, "status": "rejected", "status_detail": "cc_rejected_bad_filled_security_code"})
        await _con_saldo(base)
        r = await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert r["status"] == "rejected"
        assert r["amount_ris_credited"] == 0
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
        assert await _lineas(base) == []
    corre(caso())


def test_un_pago_pendiente_tampoco_acredita(base):
    async def caso():
        _ClienteMP.respuesta = _RespuestaMP(201, {
            "id": 56, "status": "in_process", "status_detail": "pending_review"})
        await _con_saldo(base)
        r = await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert r["status"] == "in_process"
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
    corre(caso())


def test_si_mercado_pago_contesta_un_error_no_se_acredita(base):
    async def caso():
        _ClienteMP.respuesta = _RespuestaMP(400, {"message": "Tarjeta inválida"})
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert e.value.status_code == 400
        assert "Tarjeta inválida" in str(e.value.detail)
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
    corre(caso())


def test_si_se_cae_la_red_no_se_acredita(base):
    """Un timeout no puede acreditar: no sabemos si la tarjeta se cobró."""
    import httpx as _httpx

    async def caso():
        _ClienteMP.error = _httpx.ConnectTimeout("se cayó")
        await _con_saldo(base)
        with pytest.raises(HTTPException) as e:
            await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert e.value.status_code == 502
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
        assert await _lineas(base) == []
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Que no se acredite dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_si_el_webhook_ya_lo_proceso_el_camino_sincronico_no_duplica(base):
    """El pago se acredita por DOS caminos —la respuesta directa y el webhook—
    y los dos pueden llegar. Cobrar una vez y acreditar dos es el peor error."""
    async def caso():
        await _con_saldo(base)
        # El webhook llegó primero y dejó su marca.
        await base.processed_webhooks.insert_one(
            {"webhook_event_id": "card_998877", "provider": "mercadopago_card"})
        r = await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        assert r["status"] == "approved"
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00"), "acreditó dos veces"
        assert await _lineas(base) == []
    corre(caso())


def test_el_pago_deja_su_marca_para_que_el_webhook_no_duplique(base):
    async def caso():
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        marca = await base.processed_webhooks.find_one(
            {"webhook_event_id": "card_998877"})
        assert marca is not None, "sin la marca, el webhook acreditaría de nuevo"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. La comisión: el usuario recibe lo neto y la empresa paga la diferencia
# ══════════════════════════════════════════════════════════════════════════

def test_se_cobra_el_monto_MAS_la_comision_y_se_acredita_solo_lo_neto(base):
    """Si esto se invierte, o el usuario paga de menos o recibe de menos."""
    async def caso():
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())

        cobrado = _ClienteMP.llamadas[-1]["json"]["transaction_amount"]
        assert cobrado > 100.0, "a la tarjeta se le cobra el neto MAS la comisión"

        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("100.00"), (
            "al usuario se le acredita el NETO, no lo cobrado")

        comision, = await base.gateway_fee_ledger.find({}).to_list(10)
        assert comision["gross_amount"] == cobrado
        assert comision["net_amount"] == 100.0
        assert comision["fee_deducted"] == round(cobrado - 100.0, 2)
    corre(caso())


def test_la_tarjeta_de_debito_paga_menos_comision_que_la_de_credito(base):
    async def caso():
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0, "debit_card"), current_user=_Usuario())
        debito = _ClienteMP.llamadas[-1]["json"]["transaction_amount"]
        _ClienteMP.llamadas = []
        _ClienteMP.respuesta = _RespuestaMP(201, {
            "id": 998878, "status": "approved", "status_detail": "accredited"})
        await pc.process_card_payment(_cuerpo(100.0, "credit_card"), current_user=_Usuario())
        credito = _ClienteMP.llamadas[-1]["json"]["transaction_amount"]
        assert debito < credito
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. La contabilidad del banco de la pasarela
# ══════════════════════════════════════════════════════════════════════════

def test_el_pago_acredita_el_banco_de_la_pasarela_y_deja_su_asiento(base):
    async def caso():
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        banco = await base.bank_accounts.find_one({"name": "Mercado Pago"})
        assert banco is not None
        assert banco["currency"] == "BRL"
        assert bancos.saldo_de(banco) == Decimal("100.00")
        asiento = await base.bank_ledger.find_one({"reference": "998877"})
        assert asiento is not None, "el banco se movió sin dejar asiento"
    corre(caso())


def test_el_saldo_y_el_libro_cuadran_despues_de_pagar(base):
    from services import contabilidad

    async def caso():
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())


def test_el_intento_queda_registrado_aunque_lo_rechacen(base):
    """Un pago rechazado también es información: sin el registro no hay forma
    de saber por qué a un usuario le rebotó la tarjeta."""
    async def caso():
        _ClienteMP.respuesta = _RespuestaMP(201, {
            "id": 77, "status": "rejected", "status_detail": "cc_rejected_insufficient_amount"})
        await _con_saldo(base)
        await pc.process_card_payment(_cuerpo(100.0), current_user=_Usuario())
        intento = await base.card_payments.find_one({"payment_id": "77"})
        assert intento is not None
        assert intento["status"] == "rejected"
        assert intento["status_detail"] == "cc_rejected_insufficient_amount"
        assert intento["user_id"] == "usr_ana"
    corre(caso())
