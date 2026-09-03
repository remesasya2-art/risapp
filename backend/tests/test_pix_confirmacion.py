"""
tests/test_pix_confirmacion.py — El camino por donde ENTRA la plata.

POR QUE ESTE ARCHIVO EXISTE

    `routes/gestor_pix.py` no tenía un solo test que siquiera lo importara. Es
    el camino por el que la plata entra a la app: un PIX confirmado por Mercado
    Pago acredita el saldo de un usuario y el banco de la pasarela.

    Y en el PR #57 yo lo reescribí —pasó de un `$inc` a mano a
    `services.saldos.mover`— sin ningún test que ejercitara el sitio de la
    llamada. Los tests de aquel PR cubrían el MODULO `saldos`, no sus llamadores:
    si me hubiera equivocado de signo, de cuenta o de tipo de movimiento al
    cablearlo, nada lo habría agarrado.

    De los seis módulos del backend que mueven plata y que ningún test importa,
    cinco los toqué en ese PR. Éste es el primero que se cubre, por ser el que
    más plata mueve.

QUE SE PRUEBA
    El circuito completo contra mongomock: el reclamo atómico del pago, a qué
    cuenta va según el rol, la línea del libro, el cupo sin KYC, el banco de la
    pasarela y su asiento — y sobre todo, que un webhook repetido NO acredite
    dos veces.
"""
import asyncio
import os
import sys
import types
from datetime import datetime, timezone
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

from services import ledger, saldos                                 # noqa: E402


def _cargar_gestor_pix():
    """Carga el módulo sin arrastrar el paquete `routes` entero.

    `routes/__init__.py` importa el motor contable, que hace
    `from database import client`, y el doble de `database` que instala
    `conftest` sólo expone `db`. Mismo apaño que usan los otros tests de rutas.
    """
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
    import routes.gestor_pix as gp
    return gp


gp = _cargar_gestor_pix()


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True

    # El correo y las notificaciones no son lo que se está probando, y salir a
    # la red desde un test lo haría lento y frágil.
    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(gp, "create_notification", _nada)
    monkeypatch.setattr(gp, "notify_pix_received", _nada)
    return b


async def _usuario(base, user_id="usr_ana", rol="user", **saldos_iniciales):
    doc = {"user_id": user_id, "email": f"{user_id}@x.com", "name": "Ana",
           "role": rol, "balance_ris": d(0), "balance_ris_terceros": d(0)}
    doc.update(saldos_iniciales)
    await base.users.insert_one(doc)
    return user_id


async def _pago(base, payment_id="pix_1", user_id="usr_ana", monto=500,
                terceros=False, estado="pending"):
    await base.gestor_pix_payments.insert_one({
        "payment_id": payment_id, "gestor_id": user_id, "user_id": user_id,
        "amount_ris": monto, "amount_brl": monto, "amount_ves": monto * 92,
        "client_name": "Cliente Test", "mp_payment_id": "MP-123",
        "is_gestor_terceros": terceros, "status": estado,
        "created_at": datetime.now(timezone.utc)})
    return payment_id


async def _lineas(base, user_id="usr_ana"):
    return await base.ledger.find({"user_id": user_id}).to_list(50)


# ══════════════════════════════════════════════════════════════════════════
# 1. La plata llega, y llega a la cuenta correcta
# ══════════════════════════════════════════════════════════════════════════

def test_un_pix_confirmado_acredita_el_saldo_principal(base):
    async def caso():
        await _usuario(base)
        await _pago(base, monto=500)
        assert await gp.process_pix_confirmation("pix_1", "usr_ana") is True
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("500.00")
        assert saldos.saldo_de(doc, "balance_ris_terceros") == Decimal("0.00")
    corre(caso())


def test_un_gestor_cobrando_de_terceros_va_a_la_cuenta_de_terceros(base):
    """Es la bifurcación que decide de quién es la plata. Equivocarla mezcla el
    dinero de los clientes de un gestor con el suyo propio."""
    async def caso():
        await _usuario(base, "usr_gestor", rol="socio_gestor")
        await _pago(base, "pix_g", "usr_gestor", monto=800, terceros=True)
        assert await gp.process_pix_confirmation("pix_g", "usr_gestor") is True
        doc = await base.users.find_one({"user_id": "usr_gestor"})
        assert saldos.saldo_de(doc, "balance_ris_terceros") == Decimal("800.00")
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("0.00")
        linea, = await _lineas(base, "usr_gestor")
        assert linea["account"] == "balance_ris_terceros"
    corre(caso())


def test_un_gestor_recargando_lo_suyo_va_a_su_saldo_principal(base):
    """Mismo rol, `is_gestor_terceros` en falso: la plata es del gestor."""
    async def caso():
        await _usuario(base, "usr_gestor", rol="socio_gestor")
        await _pago(base, "pix_p", "usr_gestor", monto=300, terceros=False)
        await gp.process_pix_confirmation("pix_p", "usr_gestor")
        doc = await base.users.find_one({"user_id": "usr_gestor"})
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("300.00")
        assert saldos.saldo_de(doc, "balance_ris_terceros") == Decimal("0.00")
    corre(caso())


def test_un_usuario_comun_marcado_como_terceros_igual_va_al_principal(base):
    """La bifurcación exige LAS DOS condiciones: rol de gestor Y bandera."""
    async def caso():
        await _usuario(base, "usr_ana", rol="user")
        await _pago(base, "pix_1", "usr_ana", monto=100, terceros=True)
        await gp.process_pix_confirmation("pix_1", "usr_ana")
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc, "balance_ris") == Decimal("100.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Un webhook repetido NO puede acreditar dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_el_mismo_pago_confirmado_dos_veces_acredita_UNA(base):
    """Mercado Pago reintenta. Es el peor error posible de este camino: pagar
    una vez y recibir dos veces."""
    async def caso():
        await _usuario(base)
        await _pago(base, monto=500)
        primera = await gp.process_pix_confirmation("pix_1", "usr_ana")
        segunda = await gp.process_pix_confirmation("pix_1", "usr_ana")
        assert primera is True
        assert segunda is False, "el segundo webhook tiene que rebotar"
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("500.00")
        assert len(await _lineas(base)) == 1, "y no puede duplicar la línea"
    corre(caso())


def test_un_pago_que_ya_estaba_pagado_no_vuelve_a_acreditar(base):
    async def caso():
        await _usuario(base)
        await _pago(base, monto=500, estado="paid")
        assert await gp.process_pix_confirmation("pix_1", "usr_ana") is False
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
    corre(caso())


def test_un_pago_inexistente_no_acredita_nada(base):
    async def caso():
        await _usuario(base)
        assert await gp.process_pix_confirmation("pix_fantasma", "usr_ana") is False
        assert await _lineas(base) == []
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La línea del libro: sin ella la reconciliación se enciende
# ══════════════════════════════════════════════════════════════════════════

def test_la_acreditacion_deja_su_linea_con_el_contexto_completo(base):
    async def caso():
        await _usuario(base)
        await _pago(base, monto=500)
        await gp.process_pix_confirmation("pix_1", "usr_ana")
        linea, = await _lineas(base)
        assert linea["movement_type"] == "recarga_pix"
        assert linea["direction"] == "credit"
        assert linea["amount"] == 500.0
        assert linea["account"] == "balance_ris"
        assert linea["balance_before"] == 0.0
        assert linea["balance_after"] == 500.0
        assert linea["reference"] == {"kind": "pix_payment", "id": "pix_1"}
        assert linea["actor"]["type"] == "webhook"
        assert linea["actor"]["id"] == "mercadopago"
        assert linea["metadata"]["mp_payment_id"] == "MP-123"
    corre(caso())


def test_el_saldo_y_el_libro_quedan_cuadrados(base):
    """El control que de verdad importa, sobre el camino que más plata mueve."""
    from services import contabilidad

    async def caso():
        await _usuario(base)
        for i, monto in enumerate((100, 250.50, 33.33)):
            await _pago(base, f"pix_{i}", monto=monto)
            await gp.process_pix_confirmation(f"pix_{i}", "usr_ana")
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("383.83")
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())


def test_acreditar_sobre_un_saldo_que_ya_existe_encadena_bien(base):
    """El `balance_before` de la línea tiene que ser el saldo real de antes."""
    async def caso():
        await _usuario(base, balance_ris=d(1000))
        await _pago(base, monto=250)
        await gp.process_pix_confirmation("pix_1", "usr_ana")
        linea, = await _lineas(base)
        assert (linea["balance_before"], linea["balance_after"]) == (1000.0, 1250.0)
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. El cupo sin KYC viaja en la misma escritura
# ══════════════════════════════════════════════════════════════════════════

def test_la_recarga_consume_el_cupo_sin_kyc(base):
    async def caso():
        await _usuario(base)
        await _pago(base, monto=120)
        await gp.process_pix_confirmation("pix_1", "usr_ana")
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert doc["kyc_quota"]["ops"] == 1
        assert doc["kyc_quota"]["ris"] == 120.0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. El pago queda marcado, y la marca es lo que corta el reintento
# ══════════════════════════════════════════════════════════════════════════

def test_el_pago_queda_en_pagado_con_su_fecha(base):
    async def caso():
        await _usuario(base)
        await _pago(base, monto=500)
        await gp.process_pix_confirmation("pix_1", "usr_ana")
        pago = await base.gestor_pix_payments.find_one({"payment_id": "pix_1"})
        assert pago["status"] == "paid"
        assert pago.get("paid_at") is not None
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 6. El webhook de tarjeta — el otro camino de entrada
# ══════════════════════════════════════════════════════════════════════════
#
# Este era uno de los agujeros del diario que tapó el PR #57: acreditaba con un
# `$inc` de un float crudo y no dejaba línea. Además la contabilidad del banco
# colgaba de un `if user:` — si la relectura del usuario no devolvía nada, la
# plata entraba y el banco de la pasarela no se enteraba.

class _MPFalso:
    """Un doble de Mercado Pago que contesta lo que se le diga."""
    def __init__(self, estado="approved"):
        self.estado = estado
        self.consultas = 0

    def get_payment_status(self, mp_payment_id):
        self.consultas += 1
        return {"status": self.estado, "amount": 100.0} if self.estado else None


@pytest.fixture
def mp(monkeypatch):
    doble = _MPFalso()
    monkeypatch.setattr(gp, "mercadopago_service", doble)
    monkeypatch.setattr(gp, "MP_AVAILABLE", True)
    return doble


async def _pago_tarjeta(base, payment_id="MP-9", user_id="usr_ana", monto=100,
                        estado="pending"):
    await base.card_payments.insert_one({
        "payment_id": payment_id, "user_id": user_id, "amount_ris": monto,
        "fee_brl": 4.99, "total_charged_brl": monto + 4.99, "status": estado})
    return await base.card_payments.find_one({"payment_id": payment_id})


def test_el_webhook_de_tarjeta_acredita_y_asienta(base, mp):
    async def caso():
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        r = await gp._handle_card_webhook(pago, "MP-9")
        assert r["processed"] is True
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("100.00")
        linea, = await _lineas(base)
        assert linea["movement_type"] == "pago_tarjeta"
        assert linea["direction"] == "credit"
        assert linea["reference"] == {"kind": "card_payment", "id": "MP-9"}
        assert linea["metadata"]["fee_brl"] == 4.99
    corre(caso())


def test_el_webhook_de_tarjeta_acredita_el_banco_de_la_pasarela(base, mp):
    """La contabilidad del banco NO puede colgar de que la relectura del usuario
    devuelva algo: antes iba dentro de un `if user:`."""
    async def caso():
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        await gp._handle_card_webhook(pago, "MP-9")
        banco = await base.bank_accounts.find_one({"name": "Mercado Pago"})
        assert banco is not None, "no se acreditó el banco de la pasarela"
        assert banco["currency"] == "BRL"
        from services import bancos
        assert bancos.saldo_de(banco) == Decimal("100.00")
        asiento = await base.bank_ledger.find_one({"reference": "MP-9"})
        assert asiento is not None, "el banco se movió sin dejar asiento"
    corre(caso())


def test_el_webhook_de_tarjeta_repetido_no_acredita_dos_veces(base, mp):
    async def caso():
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        await gp._handle_card_webhook(pago, "MP-9")
        # El segundo llega con el pago ya marcado, como en producción.
        pago2 = await base.card_payments.find_one({"payment_id": "MP-9"})
        r = await gp._handle_card_webhook(pago2, "MP-9")
        assert r.get("already_processed") is True
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("100.00")
        assert len(await _lineas(base)) == 1
    corre(caso())


def test_un_pago_que_mercado_pago_no_aprueba_no_acredita(base, mp):
    """La app no se cree el webhook: vuelve a preguntarle a Mercado Pago."""
    async def caso():
        mp.estado = "rejected"
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        r = await gp._handle_card_webhook(pago, "MP-9")
        assert r.get("processed") is not True
        assert r["status"] == "rejected"
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
        assert await _lineas(base) == []
        assert mp.consultas >= 1, "tiene que verificar contra Mercado Pago"
    corre(caso())


def test_si_mercado_pago_no_contesta_no_se_acredita_nada(base, mp):
    async def caso():
        mp.estado = None          # la consulta devuelve None
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        r = await gp._handle_card_webhook(pago, "MP-9")
        assert r.get("processed") is not True
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00")
    corre(caso())


def test_el_saldo_y_el_libro_cuadran_tambien_por_tarjeta(base, mp):
    from services import contabilidad

    async def caso():
        await _usuario(base)
        pago = await _pago_tarjeta(base, monto=100)
        await gp._handle_card_webhook(pago, "MP-9")
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())
