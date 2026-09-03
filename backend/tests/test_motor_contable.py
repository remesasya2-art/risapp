"""
tests/test_motor_contable.py — El motor contable: webhooks, bancos y FIFO.

POR QUE ESTE ARCHIVO EXISTE

    `services/accounting_engine.py` es el sexto y último de los módulos que
    mueven plata y no tenía un solo test que lo importara. Ni siquiera se podía
    importar desde un test: hace `from database import db, client`, y el doble
    de `database` del conftest sólo traía `db`. Por eso también se caían dos
    archivos de test que ni lo mencionan (`test_cancelar_orden_cripto.py` y
    `test_credit_history_unificado.py`): los arrastraba `routes/__init__`.

LO QUE MAS IMPORTA ACA

    1. Que un webhook repetido no acredite dos veces. Es plata que entra: si el
       proveedor reintenta —y reintentan— el banco se acredita de nuevo.
    2. Que el débito atómico no deje pagar de más. La comprobación va dentro del
       filtro de la escritura, no antes.
    3. Que el inventario FIFO se consuma en orden y no se pueda vender lo que no
       hay.
    4. Que el saldo del banco siga siendo Decimal128 después de que el motor lo
       toque. Un solo `$inc` con float y el pozo empieza a arrastrar centavos.

    Este entorno corre mongomock, que no tiene transacciones multi-documento.
    No es una limitación del test: es la misma situación de un mongod suelto,
    que es lo que el propio motor detecta y anuncia con un warning. Lo que se
    prueba acá vale para ese caso, que es el peor.
"""
import asyncio
import os
import sys
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

from services import accounting_engine as ae                        # noqa: E402
from services import bancos                                         # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


def saldo(doc):
    """El saldo del banco como Decimal, venga como venga."""
    return bancos.saldo_de(doc)


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    # El motor cachea si el cluster soporta transacciones. Sin resetearlo, el
    # primer test decide por todos los demás y el orden pasa a importar.
    monkeypatch.setattr(ae, "_SUPPORTS_TRANSACTIONS", None, raising=False)
    return b


async def _indices(base):
    """Los índices únicos que el motor da por hechos.

    `ensure_indexes()` los crea en producción al arrancar. Un test que no los
    crea probaría un mundo donde la idempotencia del webhook no existe, y daría
    verde justo donde el producto se rompe.
    """
    await base.processed_webhooks.create_index("webhook_event_id", unique=True)
    await base.usdt_lots.create_index("purchase_id", unique=True, sparse=True)


async def _banco(base, bank_id="bco_1", saldo_inicial="1000.00", **extra):
    doc = {
        "bank_id": bank_id,
        "name": f"Banco {bank_id}",
        "currency": "BRL",
        "balance": d(saldo_inicial),
    }
    doc.update(extra)
    await base.bank_accounts.insert_one(doc)
    return doc


async def _tx(base, transaction_id="tx_1", **campos):
    doc = {
        "transaction_id": transaction_id,
        "status": "pending",
        "amount_brl": 100.0,
        "bank_account_id": "bco_1",
    }
    doc.update(campos)
    await base.transactions.insert_one(doc)
    return doc


async def _tasas(base, brl_usd=5.0, bcv=50.0):
    await base.rates.insert_one({"brl_to_usd": brl_usd, "ris_to_ves": 110,
                                 "ves_to_ris_rate": 140, "usd_to_ves": bcv})
    await base.bcv_rates.insert_one({"rates": {"dolar": bcv}})


# ══════════════════════════════════════════════════════════════════════════
# 1. El webhook que entra: plata que se acredita al banco
# ══════════════════════════════════════════════════════════════════════════

def test_el_webhook_acredita_el_neto_y_se_queda_la_comision(base):
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="1000.00")
        await _tx(base, amount_brl=100.0)

        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.0, "BRL")

        assert r["status"] == "SUCCESSFULLY_CONCILIATED"
        assert r["fee"] == 1.0          # 1% de 100
        assert r["net_to_bank"] == 99.0

        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("1099.00"), "el neto no llegó al banco"

        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "approved"
        assert tx["net_amount_received"] == 99.0

        comision = await base.gateway_fee_ledger.find_one({})
        assert comision["fee_deducted"] == 1.0
        assert comision["currency"] == "BRL"
    corre(caso())


def test_EL_REINTENTO_del_proveedor_no_acredita_dos_veces(base):
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="1000.00")
        await _tx(base, amount_brl=100.0)

        primero = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.0, "BRL")
        segundo = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.0, "BRL")

        assert primero["status"] == "SUCCESSFULLY_CONCILIATED"
        assert segundo["status"] == "IGNORED_DUPLICATE"

        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("1099.00"), "se acreditó dos veces"
        assert await base.gateway_fee_ledger.count_documents({}) == 1
    corre(caso())


def test_una_transaccion_ya_aprobada_no_se_vuelve_a_acreditar(base):
    """Otro evento, misma transacción: el id del webhook no lo ataja."""
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="1000.00")
        await _tx(base, status="approved", amount_brl=100.0)

        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_OTRO", "mercadopago", "tx_1", 100.0, "BRL")

        assert r["status"] == "ALREADY_PROCESSED"
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("1000.00"), "acreditó sobre una ya aprobada"
    corre(caso())


def test_un_monto_que_no_cuadra_suspende_la_transaccion_y_no_acredita(base):
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="1000.00")
        await _tx(base, amount_brl=100.0)

        with pytest.raises(ValueError, match="Descuadre"):
            await ae.WebhookConciliationService.process_incoming_payment(
                "evt_1", "mercadopago", "tx_1", 40.0, "BRL")

        tx = await base.transactions.find_one({"transaction_id": "tx_1"})
        assert tx["status"] == "suspended", "quedó cobrable con el monto mal"
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("1000.00")
        assert await base.gateway_fee_ledger.count_documents({}) == 0
    corre(caso())


def test_un_centavo_de_diferencia_se_tolera(base):
    """El redondeo del proveedor no puede suspender un cobro legítimo."""
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="0.00")
        await _tx(base, amount_brl=100.0)

        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.01, "BRL")
        assert r["status"] == "SUCCESSFULLY_CONCILIATED"
    corre(caso())


def test_dos_centavos_de_diferencia_ya_no(base):
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="0.00")
        await _tx(base, amount_brl=100.0)
        with pytest.raises(ValueError, match="Descuadre"):
            await ae.WebhookConciliationService.process_incoming_payment(
                "evt_1", "mercadopago", "tx_1", 100.02, "BRL")
    corre(caso())


def test_en_VES_se_compara_contra_el_monto_en_VES(base):
    """Comparar VES contra amount_brl suspendería todo cobro en bolívares."""
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _tx(base, amount_brl=100.0, amount_ves=4000.0)

        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "pasarela_ve", "tx_1", 4000.0, "VES")

        assert r["status"] == "SUCCESSFULLY_CONCILIATED"
        assert r["fee"] == 40.0
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("3960.00")
    corre(caso())


def test_una_transaccion_que_no_existe_no_acredita_nada(base):
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="1000.00")
        with pytest.raises(ValueError, match="no encontrada"):
            await ae.WebhookConciliationService.process_incoming_payment(
                "evt_1", "mercadopago", "tx_FANTASMA", 100.0, "BRL")
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("1000.00")
    corre(caso())


def test_sin_banco_destino_la_transaccion_se_aprueba_igual(base):
    """No hay banco al cual acreditar: no se inventa uno ni se rompe."""
    async def caso():
        await _indices(base)
        await _tx(base, amount_brl=100.0, bank_account_id=None)
        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.0, "BRL")
        assert r["status"] == "SUCCESSFULLY_CONCILIATED"
        assert await base.bank_accounts.count_documents({}) == 0
    corre(caso())


def test_el_banco_destino_alternativo_tambien_se_acredita(base):
    async def caso():
        await _indices(base)
        await _banco(base, bank_id="bco_alt", saldo_inicial="0.00")
        await _tx(base, amount_brl=100.0, bank_account_id=None,
                  destination_bank_id="bco_alt")
        await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 100.0, "BRL")
        bco = await base.bank_accounts.find_one({"bank_id": "bco_alt"})
        assert saldo(bco) == Decimal("99.00")
    corre(caso())


def test_EL_SALDO_DEL_BANCO_SIGUE_SIENDO_DECIMAL_despues_del_webhook(base):
    """La regresión que ya apareció tres veces en este repo.

    Un `$inc` con float convierte el campo a double y a partir de ahí el pozo
    arrastra el error de coma flotante. La conciliación mira justo ese total.
    """
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="0.00")
        await _tx(base, amount_brl=0.10)
        await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 0.10, "BRL")
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert isinstance(bco["balance"], Decimal128), \
            f"el saldo dejó de ser Decimal128: es {type(bco['balance'])}"
    corre(caso())


def test_la_comision_se_redondea_una_sola_vez(base):
    """1% de 33.33 = 0.3333. Redondear dos veces da 0.34 en vez de 0.33."""
    async def caso():
        await _indices(base)
        await _banco(base, saldo_inicial="0.00")
        await _tx(base, amount_brl=33.33)
        r = await ae.WebhookConciliationService.process_incoming_payment(
            "evt_1", "mercadopago", "tx_1", 33.33, "BRL")
        assert r["fee"] == 0.33
        assert r["net_to_bank"] == 33.0
        assert round(r["fee"] + r["net_to_bank"], 2) == 33.33, \
            "comisión + neto no reconstruyen el bruto"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. El débito atómico del banco
# ══════════════════════════════════════════════════════════════════════════

def test_el_debito_descuenta_cuando_hay_con_que(base):
    async def caso():
        await _banco(base, saldo_inicial="500.00")
        r = await ae.CoreAccountingEngine.atomic_debit_from_bank(
            "bco_1", 200.0, None)
        assert saldo(r) == Decimal("300.00")
    corre(caso())


def test_el_debito_por_el_saldo_exacto_pasa(base):
    """El guard es `>=`, no `>`: vaciar la cuenta es legítimo."""
    async def caso():
        await _banco(base, saldo_inicial="500.00")
        r = await ae.CoreAccountingEngine.atomic_debit_from_bank(
            "bco_1", 500.0, None)
        assert saldo(r) == Decimal("0.00")
    corre(caso())


def test_EL_DEBITO_SIN_FONDOS_NO_ESCRIBE_NADA(base):
    async def caso():
        await _banco(base, saldo_inicial="100.00")
        with pytest.raises(ValueError, match="fondos insuficientes"):
            await ae.CoreAccountingEngine.atomic_debit_from_bank(
                "bco_1", 100.01, None)
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("100.00"), "quedó en negativo"
    corre(caso())


def test_una_cuenta_oculta_no_se_puede_debitar(base):
    async def caso():
        await _banco(base, saldo_inicial="500.00", hidden_from_admin=True)
        with pytest.raises(ValueError, match="deshabilitada"):
            await ae.CoreAccountingEngine.atomic_debit_from_bank(
                "bco_1", 10.0, None)
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("500.00")
    corre(caso())


def test_una_cuenta_que_no_existe_no_se_puede_debitar(base):
    async def caso():
        with pytest.raises(ValueError):
            await ae.CoreAccountingEngine.atomic_debit_from_bank(
                "bco_FANTASMA", 10.0, None)
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. El inventario de USDT
# ══════════════════════════════════════════════════════════════════════════

def test_un_lote_con_cantidades_invalidas_no_entra(base):
    async def caso():
        for usdt, costo in ((0, 5.0), (-10, 5.0), (10, 0), (10, -5.0)):
            with pytest.raises(ValueError, match="inválidas"):
                await ae.CoreAccountingEngine.register_usdt_lot(
                    initial_usdt=usdt, cost_per_usdt_brl=costo)
        assert await base.usdt_lots.count_documents({}) == 0
    corre(caso())


def test_la_misma_compra_no_se_carga_dos_veces(base):
    async def caso():
        await _indices(base)
        await ae.CoreAccountingEngine.register_usdt_lot(
            initial_usdt=100, cost_per_usdt_brl=5.0, purchase_id="compra_1")
        with pytest.raises(ValueError, match="ya registrado"):
            await ae.CoreAccountingEngine.register_usdt_lot(
                initial_usdt=100, cost_per_usdt_brl=5.0, purchase_id="compra_1")
        assert await base.usdt_lots.count_documents({}) == 1
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. El arbitraje P2P: FIFO y ganancia
# ══════════════════════════════════════════════════════════════════════════

async def _lote(base, usdt, costo_brl, cuando, oculto=False, agotado=False):
    import uuid
    from datetime import datetime, timezone, timedelta
    await base.usdt_lots.insert_one({
        "_id": uuid.uuid4().hex,
        "initial_usdt": float(usdt),
        "remaining_usdt": float(usdt),
        "cost_per_usdt_brl": float(costo_brl),
        "is_exhausted": agotado,
        "hidden_from_admin": oculto,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=cuando),
    })


def test_el_FIFO_consume_primero_el_lote_mas_viejo(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 50, costo_brl=4.0, cuando=0)    # el viejo, barato
        await _lote(base, 50, costo_brl=9.0, cuando=5)    # el nuevo, caro

        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")

        assert len(r["lots_consumed"]) == 1
        assert r["lots_consumed"][0]["cost_per_usdt_brl"] == 4.0, \
            "consumió el lote nuevo antes que el viejo"
        assert r["fifo_cost_brl"] == 200.0
    corre(caso())


def test_el_FIFO_parte_la_venta_entre_dos_lotes(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 30, costo_brl=4.0, cuando=0)
        await _lote(base, 50, costo_brl=6.0, cuando=5)

        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")

        assert [c["deducted"] for c in r["lots_consumed"]] == [30, 20]
        # 30×4 + 20×6 = 240
        assert r["fifo_cost_brl"] == 240.0

        lotes = [x async for x in base.usdt_lots.find({}).sort("created_at", 1)]
        assert lotes[0]["is_exhausted"] is True
        assert lotes[0]["remaining_usdt"] == 0
        assert lotes[1]["is_exhausted"] is False
        assert lotes[1]["remaining_usdt"] == 30
    corre(caso())


def test_un_lote_oculto_no_se_vende(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=4.0, cuando=0, oculto=True)
        await _lote(base, 100, costo_brl=6.0, cuando=5)

        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")

        assert r["lots_consumed"][0]["cost_per_usdt_brl"] == 6.0
        oculto = await base.usdt_lots.find_one({"hidden_from_admin": True})
        assert oculto["remaining_usdt"] == 100, "se tocó un lote oculto"
    corre(caso())


def test_un_lote_agotado_no_se_vuelve_a_vender(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=4.0, cuando=0, agotado=True)
        await _lote(base, 100, costo_brl=6.0, cuando=5)
        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")
        assert r["lots_consumed"][0]["cost_per_usdt_brl"] == 6.0
    corre(caso())


def test_cantidades_invalidas_no_arrancan_el_arbitraje(base):
    async def caso():
        await _tasas(base)
        for usdt, ves in ((0, 100), (-1, 100), (10, 0), (10, -1)):
            with pytest.raises(ValueError, match="inválidas"):
                await ae.CoreAccountingEngine.execute_p2p_arbitrage(
                    amount_usdt_to_sell=usdt, amount_ves_received=ves,
                    bank_account_id="bco_1", admin_id="adm")
        assert await base.p2p_sales.count_documents({}) == 0
    corre(caso())


def test_sin_tasas_configuradas_el_arbitraje_no_corre(base):
    async def caso():
        await _lote(base, 100, costo_brl=4.0, cuando=0)
        with pytest.raises(RuntimeError, match="tasas"):
            await ae.CoreAccountingEngine.execute_p2p_arbitrage(
                amount_usdt_to_sell=50, amount_ves_received=2500,
                bank_account_id="bco_1", admin_id="adm")
    corre(caso())


def test_los_VES_cobrados_entran_al_banco(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=4.0, cuando=0)
        await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("2500.00")
        assert isinstance(bco["balance"], Decimal128)
    corre(caso())


def test_INVENTARIO_INSUFICIENTE_no_vende_ni_toca_los_lotes(base):
    """Sin transacciones —un mongod suelto— nada revierte los lotes ya tocados.

    Si el motor descuenta lote por lote y recién al final descubre que no
    alcanzaba, el inventario queda comido y la venta nunca ocurrió: USDT que
    desaparece del stock sin haberse vendido. La comprobación tiene que ir
    ANTES de tocar el primer lote.
    """
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 30, costo_brl=4.0, cuando=0)
        await _lote(base, 20, costo_brl=6.0, cuando=5)

        with pytest.raises(ValueError, match="Inventario insuficiente"):
            await ae.CoreAccountingEngine.execute_p2p_arbitrage(
                amount_usdt_to_sell=100, amount_ves_received=5000,
                bank_account_id="bco_1", admin_id="adm")

        lotes = [x async for x in base.usdt_lots.find({}).sort("created_at", 1)]
        assert [x["remaining_usdt"] for x in lotes] == [30, 20], \
            "la venta falló pero el inventario quedó consumido"
        assert not any(x["is_exhausted"] for x in lotes)
        assert await base.p2p_sales.count_documents({}) == 0
        bco = await base.bank_accounts.find_one({"bank_id": "bco_1"})
        assert saldo(bco) == Decimal("0.00")
    corre(caso())


def test_LA_GANANCIA_DEPENDE_DE_CUANTOS_VES_SE_COBRARON(base):
    """La misma venta cobrada casi gratis no puede reportar la misma ganancia.

    La cuenta pivotea en USD: los VES cobrados se pasan a USD a la tasa BCV
    —así lo dice el encabezado del propio módulo, "VES→USD via bcv_ves_usd"— y
    se comparan contra el costo en USD del USDT entregado. Si la conversión se
    hace con la tasa de la propia venta (ves_recibidos / usdt_vendidos), la
    división se cancela contra sí misma y los VES dejan de influir: vender 50
    USDT por 2.500 VES o por 1 VES reportaría exactamente la misma ganancia.
    """
    async def caso():
        await _tasas(base, brl_usd=5.0, bcv=50.0)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 200, costo_brl=4.0, cuando=0)

        buena = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")
        regalada = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=1,
            bank_account_id="bco_1", admin_id="adm")

        # Costo: 50 USDT × 4 BRL = 200 BRL ÷ 5 = 40 USD.
        # Venta buena: 2500 VES ÷ 50 = 50 USD  →  +10
        # Venta regalada: 1 VES ÷ 50 = 0.02 USD  →  −39.98
        assert buena["net_profit_usdt"] == 10.0
        assert regalada["net_profit_usdt"] < 0, \
            "regalar 50 USDT por 1 VES se reportó como ganancia"
        assert buena["net_profit_usdt"] != regalada["net_profit_usdt"]
    corre(caso())


def test_una_venta_a_perdida_deja_una_alerta_CRITICAL(base):
    async def caso():
        await _tasas(base, brl_usd=5.0, bcv=50.0)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=20.0, cuando=0)   # carísimo

        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")

        assert r["net_profit_usdt"] < 0
        alerta = await base.accounting_audit_log.find_one(
            {"action": "P2P_LOSS_DETECTED"})
        assert alerta is not None, "una venta a pérdida pasó sin alerta"
        assert alerta["severity"] == "CRITICAL"
    corre(caso())


def test_una_venta_con_ganancia_no_dispara_la_alerta(base):
    async def caso():
        await _tasas(base, brl_usd=5.0, bcv=50.0)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=4.0, cuando=0)
        await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")
        assert await base.accounting_audit_log.count_documents(
            {"action": "P2P_LOSS_DETECTED"}) == 0
    corre(caso())


def test_la_venta_queda_registrada_con_su_rastro(base):
    async def caso():
        await _tasas(base)
        await _banco(base, saldo_inicial="0.00", currency="VES")
        await _lote(base, 100, costo_brl=4.0, cuando=0)

        r = await ae.CoreAccountingEngine.execute_p2p_arbitrage(
            amount_usdt_to_sell=50, amount_ves_received=2500,
            bank_account_id="bco_1", admin_id="adm")

        venta = await base.p2p_sales.find_one({"sale_id": r["sale_id"]})
        assert venta["usdt_amount"] == 50
        assert venta["ves_received"] == 2500
        assert venta["created_by"] == "adm"
        # La foto de las tasas del momento: sin ella, un reporte de hace un mes
        # se recalcula con las tasas de hoy.
        assert venta["rates_snapshot"]["market_brl_usd"] == 5.0
        assert await base.accounting_audit_log.count_documents(
            {"action": "P2P_ARBITRAGE_COMPLETE"}) == 1
        assert await base.accounting_audit_log.count_documents(
            {"action": "FIFO_LOT_DISPATCH"}) == 1
    corre(caso())
