"""
tests/test_pago_una_sola_vez.py — Que un pago con tarjeta se acredite UNA vez.

POR QUE ESTE ARCHIVO EXISTE

    Mercado Pago liquida las tarjetas de forma sincrónica (`binary_mode`) Y
    además manda un webhook por el mismo pago. Los dos caminos del backend
    acreditan saldo, y los dos se protegían con

        existente = await db.processed_webhooks.find_one({...})
        if not existente:
            await db.processed_webhooks.insert_one({...})
            acreditar()

    Entre el `find_one` y el `insert_one` hay una ventana. Si el webhook entra
    mientras el flujo sincrónico todavía corre —el caso exacto para el que ese
    guard fue escrito— los dos leen que no hay nada, los dos insertan, y los
    dos acreditan.

    Y dar vuelta el orden no alcanzaba: sin un índice ÚNICO sobre
    `webhook_event_id`, dos `insert_one` simultáneos entran los dos igual. El
    índice estaba definido en `accounting_engine.ensure_indexes()`, que sólo
    corre si un super admin llama a mano a
    POST /admin/accounting/v2/bootstrap-indexes. En el arranque no se creaba.

    Los dos tests que más importan acá son los que REPRODUCEN el cobro doble:
    uno con el patrón viejo, otro sin el índice. Si alguna vez dejan de fallar
    contra el código roto, este archivo dejó de servir.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import ledger                                         # noqa: E402
from services import pagos_una_sola_vez as una_vez                   # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True
    return b


# ══════════════════════════════════════════════════════════════════════════
# 1. El reclamo
# ══════════════════════════════════════════════════════════════════════════

def test_el_primero_reclama_y_el_segundo_no(base):
    async def caso():
        assert await una_vez.reclamar(base, "card_99", proveedor="mp") is True
        assert await una_vez.reclamar(base, "card_99", proveedor="mp") is False
        assert await base.processed_webhooks.count_documents({}) == 1
    corre(caso())


def test_eventos_distintos_se_reclaman_los_dos(base):
    async def caso():
        assert await una_vez.reclamar(base, "card_1", proveedor="mp") is True
        assert await una_vez.reclamar(base, "card_2", proveedor="mp") is True
    corre(caso())


def test_UN_EVENTO_SIN_ID_NO_SE_ACREDITA(base):
    """Sin id no hay forma de reconocer un repetido: acreditar sería a ciegas."""
    async def caso():
        for vacio in ("", None):
            assert await una_vez.reclamar(base, vacio, proveedor="mp") is False
        assert await base.processed_webhooks.count_documents({}) == 0
    corre(caso())


def test_SI_NO_SE_PUEDE_DEJAR_LA_MARCA_NO_SE_ACREDITA(base, monkeypatch):
    """La regla opuesta a services/idempotency.py, y es a propósito.

    Aquel módulo ante la duda deja pasar, y hace bien: crea una solicitud que
    después un admin aprueba. Acá se acredita saldo y no hay nadie después.
    """
    async def caso():
        # Envolver la BASE, no la colección: mongomock devuelve un objeto de
        # colección NUEVO en cada acceso a `base.processed_webhooks`, así que
        # un monkeypatch sobre esa colección no lo ve el código bajo prueba.
        class _ColeccionRota:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def insert_one(s, *a, **k):
                raise RuntimeError("la base no responde")

        class _BaseRota:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                real = getattr(s._real, n)
                return _ColeccionRota(real) if n == "processed_webhooks" else real

            def __getitem__(s, n):
                real = s._real[n]
                return _ColeccionRota(real) if n == "processed_webhooks" else real

        assert await una_vez.reclamar(
            _BaseRota(base), "card_7", proveedor="mp") is False
        assert await base.processed_webhooks.count_documents({}) == 0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. El índice, que es la parte que sostiene todo
# ══════════════════════════════════════════════════════════════════════════

def test_el_indice_unico_queda_puesto(base):
    async def caso():
        assert await una_vez.asegurar_indice(base) is True
        nombres = list((await base.processed_webhooks.index_information()).keys())
        assert una_vez.NOMBRE_INDICE in nombres, nombres
    corre(caso())


def test_SIN_INDICE_UNICO_EL_MISMO_PAGO_ENTRA_DOS_VECES(base, monkeypatch):
    """La demostración de por qué el índice no es un detalle de rendimiento.

    Escribir primero y mirar después no sirve de nada si la base acepta las dos
    escrituras. Esto es lo que pasaba en producción, donde el índice sólo se
    creaba llamando a mano a un endpoint de super admin.
    """
    async def caso():
        async def _sin_indice(*a, **k):
            return True                      # como si el índice ya estuviera
        monkeypatch.setattr(una_vez, "asegurar_indice", _sin_indice)

        assert await una_vez.reclamar(base, "card_99", proveedor="mp") is True
        assert await una_vez.reclamar(base, "card_99", proveedor="mp") is True
        assert await base.processed_webhooks.count_documents({}) == 2, \
            "sin índice único, los dos avisos entraron — y los dos acreditarían"
    corre(caso())


def test_si_ya_hay_duplicados_se_los_puede_listar(base):
    """Que el índice no se pueda crear ES la prueba de que ya se cobró doble."""
    async def caso():
        for _ in range(2):
            await base.processed_webhooks.insert_one({
                "webhook_event_id": "card_REPETIDO",
                "provider": "mp",
                "processed_at": datetime.now(timezone.utc)})
        await base.processed_webhooks.insert_one({
            "webhook_event_id": "card_SANO", "provider": "mp",
            "processed_at": datetime.now(timezone.utc)})

        repetidos = await una_vez.duplicados(base)
        assert repetidos == [{"evento": "card_REPETIDO", "veces": 2}]
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La carrera real: los dos caminos del pago con tarjeta
# ══════════════════════════════════════════════════════════════════════════

async def _usuario(base):
    from bson.decimal128 import Decimal128
    from decimal import Decimal
    await base.users.insert_one({
        "user_id": "usr_1", "email": "ana@ejemplo.com",
        "balance_ris": Decimal128(Decimal("0.00"))})


async def _saldo(base):
    from services.saldos import saldo_de
    u = await base.users.find_one({"user_id": "usr_1"})
    return saldo_de(u, "balance_ris")


def test_LA_CARRERA_el_flujo_sincronico_y_el_webhook_no_acreditan_los_dos(base):
    """Los dos caminos existen y corren a la vez. Sólo uno puede acreditar."""
    async def caso():
        from services import saldos
        await _usuario(base)

        async def acreditar_si_gano(evento):
            if await una_vez.reclamar(base, evento, proveedor="mercadopago_card"):
                await saldos.mover(
                    base, "usr_1", 100, movimiento="pago_tarjeta",
                    reference_kind="card_payment", reference_id="pay_1",
                    actor_type="user", actor_id="usr_1")
                return True
            return False

        # Los dos caminos, sobre el MISMO pago, uno detrás del otro.
        gano_sincronico = await acreditar_si_gano("card_pay_1")
        gano_webhook = await acreditar_si_gano("card_pay_1")

        assert [gano_sincronico, gano_webhook] == [True, False]
        assert await _saldo(base) == 100, \
            f"se acreditó dos veces: quedó {await _saldo(base)}"
        assert await base.ledger.count_documents({}) == 1, \
            "dos líneas de libro para un solo pago"
    corre(caso())


def test_EL_PATRON_VIEJO_SI_ACREDITA_DOS_VECES(base):
    """Reproduce el bug tal como estaba escrito, para que quede el registro.

    Este test NO prueba el arreglo: prueba que había algo que arreglar. Si
    algún día pasa a dar un solo cobro, es que alguien cambió el escenario y
    hay que revisar por qué.
    """
    async def caso():
        from services import saldos
        await _usuario(base)
        await una_vez.asegurar_indice(base)

        # El patrón de antes: los DOS miran antes de que ninguno escriba, que
        # es exactamente lo que pasa cuando entran a la vez.
        visto_a = await base.processed_webhooks.find_one(
            {"webhook_event_id": "card_pay_1"})
        visto_b = await base.processed_webhooks.find_one(
            {"webhook_event_id": "card_pay_1"})
        assert visto_a is None and visto_b is None

        for quien in ("a", "b"):
            if quien == "a" or True:      # ninguno vio nada, los dos siguen
                await saldos.mover(
                    base, "usr_1", 100, movimiento="pago_tarjeta",
                    reference_kind="card_payment", reference_id="pay_1",
                    actor_type="user", actor_id="usr_1")

        assert await _saldo(base) == 200, \
            "el patrón viejo tendría que acreditar dos veces; si no, revisar"
    corre(caso())
