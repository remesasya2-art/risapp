"""
tests/test_conciliacion_pozo.py — El control de solvencia de la cuenta ómnibus.

QUE PREGUNTA CONTESTA ESTE CONTROL

    Con una cuenta ómnibus, la plata de todos los usuarios vive mezclada en un
    solo pozo. La única forma de saber que está toda es comparar lo que la
    empresa DEBE contra lo que la empresa TIENE:

        pasivo  = Σ (balance_ris + balance_ris_terceros) de los usuarios
        activo  = Σ (saldo de las cuentas en BRL)

    RIS y BRL van uno a uno, así que la comparación no pasa por ninguna tasa.

POR QUE NO ALCANZA CON LA RECONCILIACION QUE YA HABIA

    `/reconciliacion` compara el saldo de CADA usuario contra SU libro: si no
    cuadra, la app perdió una línea. Esta compara la SUMA de los saldos contra
    el dinero real: si no cuadra, falta plata.

    **Un libro perfecto sobre un pozo vacío cuadra igual.** Hay un test acá que
    lo demuestra, porque es la razón entera de que este control exista.
"""
import asyncio
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import contabilidad                                   # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def d(x):
    return Decimal128(Decimal(str(x)))


async def _usuarios(base, *saldos):
    """saldos: tuplas (balance_ris, balance_ris_terceros)."""
    await base.users.insert_many([
        {"user_id": f"u{i}", "balance_ris": d(r), "balance_ris_terceros": d(t)}
        for i, (r, t) in enumerate(saldos)])


async def _cuentas(base, *cuentas):
    """cuentas: tuplas (nombre, moneda, saldo, extra...)."""
    await base.bank_accounts.insert_many([
        {"bank_id": f"b{i}", "name": n, "currency": m, "balance": d(s), **extra}
        for i, (n, m, s, *resto) in enumerate(cuentas)
        for extra in [resto[0] if resto else {}]])


# ══════════════════════════════════════════════════════════════════════════
# 1. La cuenta, y su respuesta
# ══════════════════════════════════════════════════════════════════════════

def test_cuando_los_reales_alcanzan(base):
    async def caso():
        await _usuarios(base, (1000, 0), (500, 200))       # pasivo 1700
        await _cuentas(base, ("Itaú", "BRL", 1500), ("Mercado Pago", "BRL", 300))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "1700.00"
        assert r["activo"]["total"] == "1800.00"
        assert r["diferencia"] == "100.00"
        assert r["cubre"] is True
    corre(caso())


def test_cuando_falta_plata(base):
    async def caso():
        await _usuarios(base, (5000, 0))
        await _cuentas(base, ("Itaú", "BRL", 4999.99))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["diferencia"] == "-0.01"
        assert r["cubre"] is False, "un centavo de menos ya es un faltante"
    corre(caso())


def test_el_borde_exacto_cubre(base):
    """Con la plata justa, cubre. En float, 0.1 + 0.2 >= 0.3 es False."""
    async def caso():
        await _usuarios(base, (0.10, 0.20))
        await _cuentas(base, ("Itaú", "BRL", 0.30))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "0.30"
        assert r["diferencia"] == "0.00"
        assert r["cubre"] is True
    corre(caso())


def test_el_saldo_de_terceros_tambien_es_deuda(base):
    """La plata que un gestor tiene de sus clientes también hay que devolverla."""
    async def caso():
        await _usuarios(base, (0, 800))
        await _cuentas(base, ("Itaú", "BRL", 500))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["por_cuenta"]["balance_ris"] == "0.00"
        assert r["pasivo"]["por_cuenta"]["balance_ris_terceros"] == "800.00"
        assert r["cubre"] is False
    corre(caso())


def test_sumar_centavos_no_deriva(base):
    """Mil usuarios con 0.01 dan 10.00 exactos, no 9.99999999."""
    async def caso():
        await base.users.insert_many([
            {"user_id": f"u{i}", "balance_ris": d("0.01")} for i in range(1000)])
        await _cuentas(base, ("Itaú", "BRL", 10))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "10.00"
        assert r["cubre"] is True
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Qué entra y qué no: es donde un control así se rompe en silencio
# ══════════════════════════════════════════════════════════════════════════

def test_los_bolivares_NO_tapan_un_faltante_de_reales(base):
    """LA DECISION CENTRAL del control.

    Los bancos en VES pagan remesas cuyo RIS ya salió del saldo del usuario: no
    respaldan un pasivo. Sumarlos taparía un faltante de reales con bolívares
    que ya tienen dueño — y encima exigiría una tasa, así que el «descuadre» se
    movería solo cada vez que se mueve el bolívar.
    """
    async def caso():
        await _usuarios(base, (10000, 0))
        await _cuentas(base,
                       ("Itaú", "BRL", 1000),
                       ("Banesco", "VES", 9_000_000))     # muchísimo, y no cuenta
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["activo"]["total"] == "1000.00"
        assert r["cubre"] is False
        assert r["diferencia"] == "-9000.00"
        # Pero se informa, porque saber si alcanza para pagar lo pendiente es
        # otra pregunta igual de importante.
        assert r["capital_de_trabajo"]["VES"]["total"] == "9000000.00"
        assert r["capital_de_trabajo"]["VES"]["cuentas"] == 1
    corre(caso())


def test_la_cuenta_de_la_pasarela_SI_es_activo(base):
    """Cuando entra un PIX, el mismo flujo acredita el RIS y la cuenta «Mercado
    Pago» en BRL. Contarla como «plata en tránsito» y dejarla afuera mostraría
    un hueco permanente que no existe."""
    async def caso():
        await _usuarios(base, (1000, 0))
        await _cuentas(base, ("Mercado Pago", "BRL", 1000, {"is_gateway": True}))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["cubre"] is True
        assert r["diferencia"] == "0.00"
        assert r["activo"]["cuentas"][0]["es_pasarela"] is True
    corre(caso())


def test_una_cuenta_oculta_igual_tiene_plata(base):
    """`hidden_from_admin` la esconde de las pantallas, no le saca el dinero.
    Para una pregunta de solvencia, el dinero es dinero."""
    async def caso():
        await _usuarios(base, (1000, 0))
        await _cuentas(base, ("Vieja", "BRL", 1000, {"hidden_from_admin": True}))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["activo"]["total"] == "1000.00"
        assert r["cubre"] is True
        assert r["activo"]["cuentas_ocultas"] == 1, (
            "hay que poder explicar de dónde salió el número")
    corre(caso())


def test_una_cuenta_sin_moneda_no_se_cuenta_como_reales(base):
    """Un documento viejo sin `currency` no puede colarse en el activo."""
    async def caso():
        await _usuarios(base, (1000, 0))
        await base.bank_accounts.insert_one(
            {"bank_id": "raro", "name": "Sin moneda", "balance": d(5000)})
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["activo"]["total"] == "0.00"
        assert r["cubre"] is False
    corre(caso())


@pytest.mark.parametrize("como", [
    pytest.param(lambda x: float(x), id="float"),
    pytest.param(d, id="Decimal128"),
])
def test_da_lo_mismo_como_este_guardado_el_saldo(base, como):
    async def caso():
        await base.users.insert_one({"user_id": "u1", "balance_ris": como(750)})
        await base.bank_accounts.insert_one(
            {"bank_id": "b1", "name": "Itaú", "currency": "BRL",
             "balance": como(750)})
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "750.00"
        assert r["activo"]["total"] == "750.00"
        assert r["cubre"] is True
    corre(caso())


def test_un_usuario_sin_los_campos_de_saldo_no_rompe(base):
    async def caso():
        await base.users.insert_one({"user_id": "u_nuevo"})
        await _cuentas(base, ("Itaú", "BRL", 10))
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "0.00"
        assert r["pasivo"]["usuarios_revisados"] == 1
        assert r["pasivo"]["usuarios_con_saldo"] == 0
    corre(caso())


def test_una_base_vacia_cuadra_en_cero(base):
    async def caso():
        r = await contabilidad.conciliacion_pozo(db=base)
        assert r["pasivo"]["total"] == "0.00"
        assert r["activo"]["total"] == "0.00"
        assert r["cubre"] is True
        assert r["capital_de_trabajo"] == {}
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Por qué este control no lo reemplaza la reconciliación que ya había
# ══════════════════════════════════════════════════════════════════════════

def test_un_libro_PERFECTO_sobre_un_pozo_VACIO_cuadra_igual(base):
    """LA RAZON DE SER de este control, demostrada.

    Cada usuario tiene su saldo respaldado línea por línea en el libro: la
    reconciliación dice que todo está bien. Y en los bancos no hay un peso.
    """
    async def caso():
        await base.users.insert_many([
            {"user_id": "u1", "balance_ris": d(600)},
            {"user_id": "u2", "balance_ris": d(400)},
        ])
        await base.ledger.insert_many([
            {"user_id": "u1", "book": "RIS", "account": "balance_ris",
             "direction": "credit", "amount": 600.0},
            {"user_id": "u2", "book": "RIS", "account": "balance_ris",
             "direction": "credit", "amount": 400.0},
        ])
        # No hay ninguna cuenta bancaria: el pozo está vacío.

        libro = await contabilidad.reconciliacion(db=base)
        pozo = await contabilidad.conciliacion_pozo(db=base)

        assert libro["cuadra"] is True, "el libro está impecable"
        assert pozo["cubre"] is False, "y sin embargo falta TODA la plata"
        assert pozo["diferencia"] == "-1000.00"
    corre(caso())


def test_y_al_reves_un_pozo_lleno_no_arregla_un_libro_roto(base):
    """El otro lado: sobra plata y aun así el libro miente. Hacen falta los dos."""
    async def caso():
        await base.users.insert_one({"user_id": "u1", "balance_ris": d(500)})
        # El libro dice 120: se perdieron líneas por 380.
        await base.ledger.insert_one(
            {"user_id": "u1", "book": "RIS", "account": "balance_ris",
             "direction": "credit", "amount": 120.0})
        await _cuentas(base, ("Itaú", "BRL", 99999))

        libro = await contabilidad.reconciliacion(db=base)
        pozo = await contabilidad.conciliacion_pozo(db=base)

        assert pozo["cubre"] is True, "plata sobra"
        assert libro["cuadra"] is False, "y el libro igual está roto"
        assert libro["descuadres"][0]["diferencia"] == "380.00"
    corre(caso())
