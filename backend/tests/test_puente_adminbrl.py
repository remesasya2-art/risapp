"""
tests/test_puente_adminbrl.py — El puente que paga y devuelve retiros.

POR QUE ESTE ARCHIVO EXISTE

    `routes/adminbrl_bridge.py` es una API con clave que aprueba y rechaza
    retiros: descuenta plata de un banco real y devuelve saldo a usuarios. No
    tenía un solo test que lo importara — ni siquiera de su autenticación.

    Es el cuarto de los seis módulos que mueven plata y estaban sin cubrir, y
    otro que toqué en el PR #57: su devolución acreditaba SIEMPRE `balance_ris`
    sin mirar `currency_input`, así que un envío pagado en USDT volvía
    convertido en RIS. Y no dejaba línea en el libro.

QUE SE PRUEBA
    La puerta (la clave de API), la aprobación (que descuente el banco y deje su
    asiento) y el rechazo (que devuelva a la moneda correcta, deje su línea, y
    se plante cuando no puede hacerlo bien).
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


def _cargar_puente():
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
    import routes.adminbrl_bridge as ab
    return ab


ab = _cargar_puente()
from fastapi import HTTPException                                   # noqa: E402

CLAVE = "clave-de-prueba-muy-larga-y-secreta"


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True
    monkeypatch.setattr(ab, "ADMINBRL_API_KEY", CLAVE)
    ab._failed_attempts.clear()

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(ab, "create_notification", _nada)
    return b


async def _mundo(base, moneda_origen="RIS", monto_ris=300, monto_ves=27600,
                 saldo_usuario=0, saldo_banco=100000):
    await base.users.insert_one({
        "user_id": "usr_ana", "email": "ana@x.com", "name": "Ana", "role": "user",
        "balance_ris": d(saldo_usuario), "balance_usdt": d(0)})
    await base.transactions.insert_one({
        "transaction_id": "tx_1", "display_id": "R-0001", "user_id": "usr_ana",
        "type": "withdrawal", "status": "pending",
        "currency_input": moneda_origen, "currency_output": "VES",
        "amount_input": monto_ris, "amount_output": monto_ves,
        "beneficiary_data": {"full_name": "María Pérez", "bank_name": "Banesco"}})
    await base.bank_accounts.insert_one({
        "bank_id": "bnk_ves", "name": "Banesco", "currency": "VES",
        "balance": d(saldo_banco)})


def _pedido(accion="approve", **extra):
    return ab.ProcessWithdrawalRequest(
        transaction_id="tx_1", action=accion, **extra)


async def _lineas(base):
    return await base.ledger.find({"user_id": "usr_ana"}).to_list(50)


# ══════════════════════════════════════════════════════════════════════════
# 1. La puerta: sin clave no se toca un peso
# ══════════════════════════════════════════════════════════════════════════

def test_sin_clave_no_se_puede_procesar_nada(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido(bank_id="bnk_ves"), x_adminbrl_key=None)
        assert e.value.status_code == 401
        banco = await base.bank_accounts.find_one({"bank_id": "bnk_ves"})
        assert bancos.saldo_de(banco) == Decimal("100000.00")
    corre(caso())


def test_con_una_clave_equivocada_tampoco(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido(bank_id="bnk_ves"),
                                        x_adminbrl_key="clave-que-no-es")
        assert e.value.status_code == 401
    corre(caso())


def test_si_el_servidor_no_tiene_clave_configurada_se_planta(base, monkeypatch):
    """Sin clave configurada no se abre la puerta: se dice que no está lista."""
    async def caso():
        monkeypatch.setattr(ab, "ADMINBRL_API_KEY", "")
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido(bank_id="bnk_ves"), x_adminbrl_key=CLAVE)
        assert e.value.status_code == 503
    corre(caso())


def test_despues_de_varios_intentos_fallidos_se_bloquea(base):
    """Una API con clave y sin límite de intentos es una clave que se adivina."""
    async def caso():
        await _mundo(base)
        vistos = []
        for _ in range(ab._MAX_FAILED_ATTEMPTS + 1):
            with pytest.raises(HTTPException) as e:
                await ab.process_withdrawal(_pedido(bank_id="bnk_ves"),
                                            x_adminbrl_key="mal")
            vistos.append(e.value.status_code)
        assert 429 in vistos, "nunca se bloqueó tras los intentos fallidos"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Aprobar: la plata sale del banco y queda registrada
# ══════════════════════════════════════════════════════════════════════════

def test_aprobar_descuenta_el_banco_y_deja_su_asiento(base):
    async def caso():
        await _mundo(base, monto_ves=27600, saldo_banco=100000)
        r = await ab.process_withdrawal(_pedido("approve", bank_id="bnk_ves"),
                                        x_adminbrl_key=CLAVE)
        assert "aprobado" in r["message"].lower()
        banco = await base.bank_accounts.find_one({"bank_id": "bnk_ves"})
        assert bancos.saldo_de(banco) == Decimal("72400.00")
        asiento = await base.bank_ledger.find_one({"reference": "tx_1"})
        assert asiento is not None, "el banco se movió sin dejar asiento"
        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "completed"
    corre(caso())


def test_aprobar_sin_banco_no_hace_nada(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("approve"), x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "pending"
    corre(caso())


def test_aprobar_con_un_banco_inexistente_no_hace_nada(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("approve", bank_id="bnk_fantasma"),
                                        x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "pending"
    corre(caso())


def test_una_transaccion_ya_procesada_no_se_vuelve_a_procesar(base):
    """Sin esto, aprobar dos veces descuenta el banco dos veces."""
    async def caso():
        await _mundo(base)
        await ab.process_withdrawal(_pedido("approve", bank_id="bnk_ves"),
                                    x_adminbrl_key=CLAVE)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("approve", bank_id="bnk_ves"),
                                        x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        banco = await base.bank_accounts.find_one({"bank_id": "bnk_ves"})
        assert bancos.saldo_de(banco) == Decimal("72400.00"), "descontó dos veces"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Rechazar: la devolución vuelve a la moneda de ORIGEN
# ══════════════════════════════════════════════════════════════════════════

def test_rechazar_devuelve_el_saldo_y_deja_su_linea(base):
    async def caso():
        await _mundo(base, monto_ris=300, saldo_usuario=0)
        r = await ab.process_withdrawal(_pedido("reject", rejection_reason="Datos malos"),
                                        x_adminbrl_key=CLAVE)
        assert "rechazado" in r["message"].lower()
        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("300.00")

        linea, = await _lineas(base)
        assert linea["movement_type"] == "refund_envio"
        assert linea["direction"] == "credit"
        assert linea["amount"] == 300.0
        assert linea["account"] == "balance_ris"
        assert linea["metadata"]["via"] == "adminbrl_bridge"

        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "rejected"
        assert tx["rejection_reason"] == "Datos malos"
    corre(caso())


def test_un_envio_pagado_en_USDT_no_se_devuelve_en_RIS(base):
    """EL DEFECTO QUE ARREGLO EL PR #57.

    El puente devolvía siempre a `balance_ris` sin mirar `currency_input`, así
    que un envío pagado en USDT volvía convertido en RIS: plata que no es la
    suya. Su lista de pendientes no filtra por moneda, así que el caso llega.

    El Panel sí sabe devolver cripto a su billetera; el puente manda ese caso
    allá en vez de devolver mal.
    """
    async def caso():
        await _mundo(base, moneda_origen="USDT", monto_ris=50, saldo_usuario=0)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("reject"), x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        assert "USDT" in str(e.value.detail)
        assert "Panel" in str(e.value.detail)

        doc = await base.users.find_one({"user_id": "usr_ana"})
        assert saldos.saldo_de(doc) == Decimal("0.00"), (
            "devolvió en RIS un envío que se pagó en USDT")
        assert saldos.saldo_de(doc, "balance_usdt") == Decimal("0.00")
        assert await _lineas(base) == []
        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "pending", "y no puede quedar rechazado a medias"
    corre(caso())


@pytest.mark.parametrize("moneda", ["USDT", "USDC"])
def test_las_dos_monedas_cripto_se_mandan_al_panel(base, moneda):
    async def caso():
        await _mundo(base, moneda_origen=moneda, monto_ris=50)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("reject"), x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        assert await _lineas(base) == []
    corre(caso())


def test_una_accion_inventada_se_rechaza(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(_pedido("borrar"), x_adminbrl_key=CLAVE)
        assert e.value.status_code == 400
        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "pending"
    corre(caso())


def test_una_transaccion_que_no_existe_da_404(base):
    async def caso():
        await _mundo(base)
        pedido = ab.ProcessWithdrawalRequest(transaction_id="tx_fantasma", action="reject")
        with pytest.raises(HTTPException) as e:
            await ab.process_withdrawal(pedido, x_adminbrl_key=CLAVE)
        assert e.value.status_code == 404
    corre(caso())


def test_el_rechazo_deja_el_libro_cuadrado(base):
    from services import contabilidad

    async def caso():
        await _mundo(base, monto_ris=300, saldo_usuario=0)
        await ledger.create_opening_entries()
        await ab.process_withdrawal(_pedido("reject"), x_adminbrl_key=CLAVE)
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())
