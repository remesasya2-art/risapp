"""
tests/test_personal_sin_transacciones.py — El personal no mueve plata propia.

POR QUE ESTE ARCHIVO EXISTE, Y POR QUE HAY DOS CANDADOS

    Se midieron las diez rutas por las que un usuario mueve plata en esta app.
    Sólo UNA pasa por `saldos.mover` en el momento del pedido. Las otras nueve
    crean una transacción pendiente o arrancan un cobro externo —un PIX, un
    invoice de Lightning, un pago con tarjeta— que liquida DESPUÉS, cuando
    llega un webhook.

    Un candado sólo en la puerta de las rutas dejaría entrar todo eso por
    atrás: el webhook no pasa por ninguna puerta. Por eso hay dos, y el que de
    verdad cierra la regla es el de abajo.

    Lo que más se prueba acá es justamente ese: que el saldo de una cuenta de
    personal no se mueva NI SIQUIERA cuando la orden viene de un webhook.
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

from services import ledger, personal, saldos                       # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True
    return b


async def _mundo(base):
    from services.money import to_decimal128
    await base.users.insert_one({
        "user_id": "usr_ana", "email": "ana@ejemplo.com",
        "balance_ris": to_decimal128(0), "role": "user"})
    await base.users.insert_one({
        "user_id": "emp_beto", "email": "beto@risappbr.com",
        "balance_ris": to_decimal128(0), "role": "admin",
        personal.CAMPO: True})


async def _saldo(base, uid):
    return saldos.saldo_de(await base.users.find_one({"user_id": uid}))


# ══════════════════════════════════════════════════════════════════════════
# El candado de fondo: saldos.mover
# ══════════════════════════════════════════════════════════════════════════

def test_a_un_usuario_comun_se_le_acredita_normalmente(base):
    async def caso():
        await _mundo(base)
        await saldos.mover(base, "usr_ana", 100, movimiento="pago_tarjeta",
                           reference_kind="card_payment", reference_id="p1",
                           actor_type="user", actor_id="usr_ana")
        assert await _saldo(base, "usr_ana") == Decimal("100.00")
    corre(caso())


def test_AL_PERSONAL_NO_SE_LE_ACREDITA(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(personal.TransaccionPersonalProhibida):
            await saldos.mover(base, "emp_beto", 100,
                               movimiento="pago_tarjeta",
                               reference_kind="card_payment", reference_id="p1",
                               actor_type="user", actor_id="emp_beto")
        assert await _saldo(base, "emp_beto") == Decimal("0.00")
        assert await base.ledger.count_documents({}) == 0
    corre(caso())


def test_EL_WEBHOOK_TAMPOCO_le_acredita(base):
    """El caso que la puerta no puede atajar.

    Nueve de las diez formas de mover plata liquidan después, por un webhook
    que no pasa por ninguna dependencia de FastAPI. Si el candado estuviera
    sólo en la puerta, esto acreditaría.
    """
    async def caso():
        await _mundo(base)
        with pytest.raises(personal.TransaccionPersonalProhibida):
            await saldos.mover(base, "emp_beto", 250,
                               movimiento="recarga_pix",
                               reference_kind="pix", reference_id="pix_1",
                               actor_type="webhook", actor_id="mercadopago")
        assert await _saldo(base, "emp_beto") == Decimal("0.00")
    corre(caso())


def test_al_personal_tampoco_se_le_DEBITA(base):
    async def caso():
        await _mundo(base)
        with pytest.raises(personal.TransaccionPersonalProhibida):
            await saldos.mover(base, "emp_beto", -10, movimiento="envio_ris",
                               reference_kind="envio", reference_id="e1",
                               actor_type="user", actor_id="emp_beto")
    corre(caso())


def test_EL_AJUSTE_DEL_ADMIN_SI_PASA(base):
    """La excepción, y es a propósito.

    Es un movimiento DE la empresa sobre esa cuenta, no del empleado a título
    propio. Sin esto, un saldo mal cargado en una cuenta de personal no se
    podría corregir ni desde el panel.
    """
    async def caso():
        await _mundo(base)
        await saldos.mover(base, "emp_beto", 50, movimiento="ajuste_admin",
                           reference_kind="manual", reference_id="aj1",
                           actor_type="admin", actor_id="usr_super")
        assert await _saldo(base, "emp_beto") == Decimal("50.00")
    corre(caso())


def test_el_cierre_de_libro_tambien_pasa(base):
    """Si no, el borrado total no podría cerrar la cuenta de un empleado."""
    async def caso():
        await _mundo(base)
        await saldos.mover(base, "emp_beto", 50, movimiento="ajuste_admin",
                           reference_kind="manual", reference_id="aj1",
                           actor_type="admin", actor_id="usr_super")
        await saldos.mover(base, "emp_beto", -50, movimiento="cierre_de_libro",
                           reference_kind="wipe", reference_id="w1",
                           actor_type="admin", actor_id="usr_super")
        assert await _saldo(base, "emp_beto") == Decimal("0.00")
    corre(caso())


def test_SI_NO_SE_PUEDE_COMPROBAR_QUIEN_ES_NO_SE_ACREDITA(base, monkeypatch):
    """Ante la duda, frena. Esta función existe para no dejar pasar plata."""
    async def caso():
        await _mundo(base)

        class _UsuariosRotos:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def find_one(s, filtro, *a, **k):
                if personal.CAMPO in (a[0] if a else k.get("projection") or {}):
                    raise RuntimeError("la base no responde")
                return await s._real.find_one(filtro, *a, **k)

        class _Base:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                real = getattr(s._real, n)
                return _UsuariosRotos(real) if n == "users" else real

            def __getitem__(s, n):
                real = s._real[n]
                return _UsuariosRotos(real) if n == "users" else real

        with pytest.raises(personal.TransaccionPersonalProhibida):
            await saldos.mover(_Base(base), "usr_ana", 100,
                               movimiento="pago_tarjeta",
                               reference_kind="card_payment", reference_id="p1",
                               actor_type="user", actor_id="usr_ana")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# La puerta, y la guarda de que siga puesta
# ══════════════════════════════════════════════════════════════════════════

def test_es_personal_lee_dict_y_objeto():
    class Usuario:
        def __init__(s, marca):
            setattr(s, personal.CAMPO, marca)

    assert personal.es_personal({personal.CAMPO: True}) is True
    assert personal.es_personal({personal.CAMPO: False}) is False
    assert personal.es_personal({}) is False
    assert personal.es_personal(None) is False
    assert personal.es_personal(Usuario(True)) is True
    assert personal.es_personal(Usuario(False)) is False


def test_la_dependencia_de_puerta_existe_y_frena():
    """La puerta da el mensaje claro; el candado de abajo es el que cierra."""
    import ast
    import pathlib
    fuente = pathlib.Path(_BACKEND, "routes/dependencies.py").read_text()
    arbol = ast.parse(fuente)
    fn = next((n for n in arbol.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "sin_transacciones_personales"), None)
    assert fn is not None, \
        "desapareció sin_transacciones_personales de routes/dependencies.py"
    cuerpo = ast.unparse(fn)
    assert "es_personal" in cuerpo
    assert "403" in cuerpo


def test_LA_EXCEPCION_NO_SE_PUEDE_AGRANDAR_SIN_QUE_SE_NOTE():
    """Los movimientos que un empleado puede recibir están declarados.

    Agregar uno a esa lista es abrirle una puerta a la plata propia, así que
    tiene que ser una decisión visible y no un renglón que pasa en un diff.
    """
    assert saldos.MOVIMIENTOS_PERMITIDOS_AL_PERSONAL == frozenset({
        "ajuste_admin", "cierre_de_libro",
    }), (
        "cambió la lista de movimientos permitidos al personal. Si es a "
        "propósito, actualizá este test explicando por qué ese movimiento no "
        "es 'a título personal'.")


# ══════════════════════════════════════════════════════════════════════════
# La guarda: que no aparezca una ruta nueva sin puerta
# ══════════════════════════════════════════════════════════════════════════

# Las diez rutas por las que hoy un usuario mueve plata. Están escritas una
# por una a propósito: agregar la once tiene que ser una decisión visible, con
# alguien pensando si lleva puerta o no, y no un renglón que pasa en un diff.
RUTAS_DE_PLATA = {
    "/api/btc/generar-invoice",
    "/api/credits/deposit",
    "/api/gestor/pix/create",
    "/api/gestor/pix/simulate-payment/{payment_id}",
    "/api/payments/card/process",
    "/api/payments/card/quote",
    "/api/reais/send",
    "/api/recharge/ves",
    "/api/withdraw",
    "/api/withdraw-crypto",
}


def _nombres_de_dependencias(dependant, visto=None):
    visto = visto if visto is not None else set()
    salida = []
    for d in getattr(dependant, "dependencies", []) or []:
        if id(d) in visto:
            continue
        visto.add(id(d))
        if getattr(d, "call", None):
            salida.append(d.call.__name__)
        salida.extend(_nombres_de_dependencias(d, visto))
    return salida


@pytest.fixture(scope="module")
def app_armada():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "ris_test")
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return app


def test_TODAS_LAS_RUTAS_DE_PLATA_TIENEN_LA_PUERTA(app_armada):
    sin_puerta = []
    vistas = set()
    for ruta in app_armada.routes:
        camino = getattr(ruta, "path", None)
        if camino not in RUTAS_DE_PLATA:
            continue
        vistas.add(camino)
        dependant = getattr(ruta, "dependant", None)
        if dependant is None:                             # pragma: no cover
            continue
        if "sin_transacciones_personales" not in _nombres_de_dependencias(dependant):
            sin_puerta.append(camino)

    assert not sin_puerta, (
        "Estas rutas mueven plata de un usuario y no tienen la puerta que "
        "frena a las cuentas del personal:\n  " + "\n  ".join(sorted(sin_puerta)) +
        "\n\nAgregá dependencies=[Depends(sin_transacciones_personales)] al "
        "decorador.")

    faltan = RUTAS_DE_PLATA - vistas
    assert not faltan, (
        "Estas rutas están en la lista y ya no existen en la app: "
        f"{sorted(faltan)}. Si se renombraron, actualizá RUTAS_DE_PLATA; si "
        "se borraron, sacalas.")
