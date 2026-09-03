"""
tests/test_cuenta_pasarela_unica.py — Una sola cuenta "Mercado Pago", no dos.

POR QUE ESTE ARCHIVO EXISTE

    La cuenta contable de Mercado Pago la crea el código solo, la primera vez
    que entra un cobro. Y estaba escrita DOS VECES, en gestor_pix (PIX) y en
    payments_card (tarjeta), las dos así:

        bank = await db.bank_accounts.find_one({"name": ..., "currency": ...})
        if not bank:
            bank = {"bank_id": f"mp_{uuid4().hex[:8]}", ...}
            await db.bank_accounts.insert_one(bank)

    Con el `bank_id` generado AL AZAR en cada creación. Son justo los dos
    caminos que corren a la vez cuando entra un pago: los dos leen que no hay
    cuenta, los dos crean una, y quedan dos filas "Mercado Pago" en BRL con
    ids distintos y el saldo repartido entre las dos.

    No es plata perdida —la conciliación del pozo suma todas las cuentas en
    BRL, así que el total cierra igual— pero el panel muestra dos filas
    idénticas que el operador no puede distinguir, y cada cobro siguiente cae
    en la que el `find_one` devuelva primero.

    Y había un tercer detalle: `bancos.asegurar_cuenta` ya existía para esto y
    no la llamaba nadie. Estaba muerta desde que se escribió.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import bancos                                        # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


async def _cuentas_mp(base):
    return [c async for c in base.bank_accounts.find(
        {"name": "Mercado Pago", "currency": "BRL"})]


# ══════════════════════════════════════════════════════════════════════════
# La pasarela
# ══════════════════════════════════════════════════════════════════════════

def test_LLAMARLA_DOS_VECES_NO_CREA_DOS_CUENTAS(base):
    """Los dos caminos del pago entran acá. Sólo puede quedar una cuenta."""
    async def caso():
        a = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        b = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")

        assert a["bank_id"] == b["bank_id"], \
            "cada llamada se armó su propia cuenta con otro bank_id"
        assert len(await _cuentas_mp(base)) == 1
    corre(caso())


def test_EL_PATRON_VIEJO_SI_CREA_DOS(base):
    """Reproduce el bug como estaba escrito. Prueba que había algo que arreglar."""
    async def caso():
        import uuid
        from datetime import datetime, timezone
        from services.money import to_decimal128

        # Los DOS miran antes de que ninguno escriba: lo que pasa cuando el
        # PIX y la tarjeta entran a la vez.
        visto_a = await base.bank_accounts.find_one(
            {"name": "Mercado Pago", "currency": "BRL"})
        visto_b = await base.bank_accounts.find_one(
            {"name": "Mercado Pago", "currency": "BRL"})
        assert visto_a is None and visto_b is None

        for _ in range(2):
            await base.bank_accounts.insert_one({
                "bank_id": f"mp_{uuid.uuid4().hex[:8]}",
                "name": "Mercado Pago", "currency": "BRL",
                "balance": to_decimal128(0), "is_gateway": True,
                "created_at": datetime.now(timezone.utc)})

        cuentas = await _cuentas_mp(base)
        assert len(cuentas) == 2, "el patrón viejo tendría que duplicar"
        assert cuentas[0]["bank_id"] != cuentas[1]["bank_id"], \
            "dos filas iguales con ids distintos: el panel no las distingue"
    corre(caso())


def test_la_cuenta_nace_con_saldo_en_decimal(base):
    """Si nace en float, el pozo arrastra el error de coma flotante."""
    async def caso():
        from bson.decimal128 import Decimal128
        c = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        assert isinstance(c["balance"], Decimal128), type(c["balance"])
        assert bancos.saldo_de(c) == Decimal("0.00")
        assert c["is_gateway"] is True
    corre(caso())


def test_no_pisa_el_saldo_de_la_cuenta_que_ya_existia(base):
    """`$setOnInsert`: si la cuenta está, se devuelve tal cual, con su plata."""
    async def caso():
        primera = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        await bancos.ajustar(base, primera["bank_id"], 500)

        otra_vez = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        assert bancos.saldo_de(otra_vez) == Decimal("500.00"), \
            "la volvió a crear y se llevó puesto el saldo"
    corre(caso())


def test_dos_pasarelas_distintas_son_dos_cuentas(base):
    async def caso():
        a = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        b = await bancos.asegurar_pasarela(
            base, name="Stripe", currency="BRL", prefijo_id="st")
        assert a["bank_id"] != b["bank_id"]
        assert await base.bank_accounts.count_documents({}) == 2
    corre(caso())


def test_la_misma_pasarela_en_otra_moneda_es_otra_cuenta(base):
    async def caso():
        a = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")
        b = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="VES", prefijo_id="mp")
        assert a["bank_id"] != b["bank_id"]
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# La cuenta común, por bank_id
# ══════════════════════════════════════════════════════════════════════════

def test_asegurar_cuenta_tampoco_duplica(base):
    async def caso():
        a = await bancos.asegurar_cuenta(
            base, bank_id="bco_1", name="Banco do Brasil", currency="brl")
        b = await bancos.asegurar_cuenta(
            base, bank_id="bco_1", name="Banco do Brasil", currency="brl")
        assert a["bank_id"] == b["bank_id"]
        assert await base.bank_accounts.count_documents({}) == 1
        assert a["currency"] == "BRL", "la moneda tiene que quedar en mayúsculas"
    corre(caso())


def test_asegurar_cuenta_respeta_el_saldo_que_ya_habia(base):
    async def caso():
        await bancos.asegurar_cuenta(
            base, bank_id="bco_1", name="B", currency="BRL", saldo_inicial=100)
        await bancos.ajustar(base, "bco_1", 50)
        otra = await bancos.asegurar_cuenta(
            base, bank_id="bco_1", name="B", currency="BRL", saldo_inicial=100)
        assert bancos.saldo_de(otra) == Decimal("150.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# La carrera de verdad, y los índices que la cierran
# ══════════════════════════════════════════════════════════════════════════

def test_LA_CARRERA_una_lectura_ciega_no_alcanza_para_duplicar(base):
    """El entrelazado real, simulado.

    Llamar dos veces seguidas no prueba nada: el patrón viejo también devuelve
    la misma cuenta si el primero ya terminó de escribir. Lo que rompía era el
    ORDEN: los dos leen antes de que ninguno escriba.

    Acá se envuelve la base para que `find_one` sobre bank_accounts conteste
    siempre "no hay nada", que es lo que ve el segundo camino cuando el primero
    todavía no escribió. Con un `find_one` + `insert_one` eso crea una segunda
    cuenta; con un `upsert` no, porque el filtro se evalúa dentro de la misma
    escritura.
    """
    async def caso():
        primera = await bancos.asegurar_pasarela(
            base, name="Mercado Pago", currency="BRL", prefijo_id="mp")

        class _CuentasCiegas:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def find_one(s, *a, **k):
                return None          # como si el otro todavía no hubiera escrito

        class _BaseCiega:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                real = getattr(s._real, n)
                return _CuentasCiegas(real) if n == "bank_accounts" else real

            def __getitem__(s, n):
                real = s._real[n]
                return _CuentasCiegas(real) if n == "bank_accounts" else real

        segunda = await bancos.asegurar_pasarela(
            _BaseCiega(base), name="Mercado Pago", currency="BRL",
            prefijo_id="mp")

        assert segunda["bank_id"] == primera["bank_id"], \
            "leyendo en falso creó una cuenta nueva: es el patrón viejo"
        assert len(await _cuentas_mp(base)) == 1
    corre(caso())


def test_los_indices_que_cierran_la_ventana_del_todo(base):
    """El `upsert` achica la ventana; el índice único la cierra."""
    async def caso():
        await bancos.asegurar_indices(base)
        nombres = list((await base.bank_accounts.index_information()).keys())
        assert "ux_bank_id" in nombres, nombres
    corre(caso())


def test_asegurar_indices_no_tumba_el_arranque_si_ya_hay_duplicados(base):
    """Que el índice no se pueda crear es una noticia, no un motivo para no arrancar."""
    async def caso():
        from datetime import datetime, timezone
        from services.money import to_decimal128
        for _ in range(2):
            await base.bank_accounts.insert_one({
                "bank_id": "mp_REPETIDO", "name": "Mercado Pago",
                "currency": "BRL", "is_gateway": True,
                "balance": to_decimal128(0),
                "created_at": datetime.now(timezone.utc)})

        await bancos.asegurar_indices(base)      # no levanta
        assert await base.bank_accounts.count_documents({}) == 2
    corre(caso())
