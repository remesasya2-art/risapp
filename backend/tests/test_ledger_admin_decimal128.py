"""
tests/test_ledger_admin_decimal128.py — Las herramientas del libro, con el saldo
en Decimal128.

QUE PASO

    Desde que `services/saldos.py` es el dueño del saldo, TODO movimiento deja
    `users.balance_ris` en `Decimal128`. Las tres herramientas de super_admin
    del libro seguían leyéndolo así:

        bal = float(u.get("balance_ris") or 0)

    `float(Decimal128)` es un `TypeError`, y el `or 0` no salva nada porque un
    `Decimal128` es *truthy*. O sea que las tres rutas que sirven justamente
    para auditar el libro —crear las líneas de apertura, reconciliar y ver las
    líneas de un usuario— devolvían 500 sobre cualquier usuario que hubiera
    movido plata.

    Es el peor lugar donde podía estar: son las herramientas con las que se
    mide si la contabilidad cuadra, y para la cuenta ómnibus ese control es el
    que hay que poder correr todos los días.

    (La reconciliación NUEVA —`/admin/ledger/reconciliacion`, en
    `services/contabilidad.py`— nunca tuvo el problema: lee con `to_decimal`.
    Hay un test acá que lo fija, para que las dos no vuelvan a divergir.)
"""
import asyncio
import os
import subprocess
import sys
import textwrap
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

from services import ledger                                          # noqa: E402
from services.money import ZERO                                     # noqa: E402


def _cargar_ledger_admin():
    """Carga `routes/ledger_admin.py` sin arrastrar el paquete `routes` entero.

    `routes/__init__.py` importa el motor contable, que hace
    `from database import client` — y el doble de `database` que instala
    `conftest` sólo expone `db`. Es el mismo apaño que usa
    `tests/test_recarga_ves.py`: se arma el paquete a mano apuntando al
    directorio, y se stubea `routes.dependencies`, que es lo único que estas
    rutas necesitan de él.
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
    import routes.ledger_admin as la
    return la


ledger_admin = _cargar_ledger_admin()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True      # mongomock no necesita los índices
    return b


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"
    role = "super_admin"


# El saldo, guardado de las dos formas que conviven hoy en la base.
GUARDADO_COMO = [
    pytest.param(lambda x: float(x), id="float"),
    pytest.param(lambda x: Decimal128(Decimal(str(x))), id="Decimal128"),
]


# ══════════════════════════════════════════════════════════════════════════
# 1. La razón de existir de este archivo
# ══════════════════════════════════════════════════════════════════════════

def test_float_de_un_Decimal128_revienta_y_el_or_cero_no_lo_salva():
    """En un intérprete limpio, porque `conftest` parcha `Decimal128`.

    Se reproduce la expresión EXACTA que estaba en las tres rutas.
    """
    guion = textwrap.dedent("""
        from decimal import Decimal
        from bson.decimal128 import Decimal128
        v = Decimal128(Decimal("1000.50"))
        assert bool(v) is True, "si fuera falsy, el `or 0` lo salvaría"
        try:
            float(v or 0)
        except TypeError:
            print("REVIENTA")
        else:
            raise SystemExit("ya no revienta: revisar si el arreglo sigue haciendo falta")
    """)
    proceso = subprocess.run([sys.executable, "-c", guion],
                             capture_output=True, text=True)
    assert proceso.returncode == 0, proceso.stderr
    assert "REVIENTA" in proceso.stdout


# ══════════════════════════════════════════════════════════════════════════
# 2. sum_ris_balance: exacto, y en Decimal
# ══════════════════════════════════════════════════════════════════════════

def test_la_suma_del_libro_no_deriva(base):
    """Mil líneas de 0.01 dan 10.00 exacto.

    Con el `$sum` de Mongo sobre floats, mil sumas binarias no dan 10.00, y un
    descuadre de 0.0000000001 que sólo existe por el tipo manda a revisar una
    cuenta que está perfecta.
    """
    async def caso():
        await base.ledger.insert_many([
            {"user_id": "usr_ana", "account": "balance_ris", "signed_amount": 0.01}
            for _ in range(1000)])
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("10.00")
    corre(caso())


def test_la_suma_del_libro_separa_las_cuentas(base):
    async def caso():
        await base.ledger.insert_many([
            {"user_id": "usr_g", "account": "balance_ris", "signed_amount": 100.0},
            {"user_id": "usr_g", "account": "balance_ris_terceros", "signed_amount": 250.0},
            {"user_id": "otro", "account": "balance_ris", "signed_amount": 999.0},
        ])
        assert await ledger.sum_ris_balance("usr_g") == Decimal("100.00")
        assert await ledger.sum_ris_balance("usr_g", "balance_ris_terceros") == Decimal("250.00")
    corre(caso())


def test_un_usuario_sin_libro_suma_cero(base):
    async def caso():
        assert await ledger.sum_ris_balance("usr_fantasma") == ZERO
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Las líneas de apertura
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("como", GUARDADO_COMO)
def test_la_apertura_funciona_con_el_saldo_guardado_de_las_dos_formas(base, como):
    """Antes, con el saldo en Decimal128, esto era un TypeError."""
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "email": "ana@x.com", "name": "Ana",
            "role": "user", "balance_ris": como(1500)})
        r = await ledger.create_opening_entries()
        assert r["aperturas_creadas"] == 1, r
        linea, = await base.ledger.find({"user_id": "usr_ana"}).to_list(10)
        assert linea["movement_type"] == "saldo_apertura"
        assert linea["direction"] == "credit"
        assert linea["amount"] == 1500.0
        assert linea["balance_before"] == 0.0
        assert linea["balance_after"] == 1500.0
        # Y después de abrir, el libro cuadra contra el saldo.
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("1500.00")
    corre(caso())


def test_la_apertura_respeta_los_movimientos_que_el_libro_ya_tenia(base):
    """La apertura es saldo_actual − suma_del_libro, no el saldo entero."""
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("1500.00"))})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "account": "balance_ris",
            "movement_type": "recarga_pix", "signed_amount": 200.0})
        await ledger.create_opening_entries()
        apertura, = await base.ledger.find(
            {"user_id": "usr_ana", "movement_type": "saldo_apertura"}).to_list(10)
        assert apertura["amount"] == 1300.0
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("1500.00")
    corre(caso())


def test_la_apertura_es_idempotente(base):
    """Se puede correr dos veces sin duplicar: es una migración, y alguien la
    va a correr dos veces."""
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("500.00"))})
        primera = await ledger.create_opening_entries()
        segunda = await ledger.create_opening_entries()
        assert primera["aperturas_creadas"] == 1
        assert segunda["aperturas_creadas"] == 0
        lineas = await base.ledger.find({"user_id": "usr_ana"}).to_list(10)
        assert len(lineas) == 1
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("500.00")
    corre(caso())


def test_reabrir_NO_tapa_un_descuadre_posterior(base):
    """La guarda de idempotencia importa por esto, y no por no duplicar.

    Si después de la apertura el saldo se movió sin dejar línea —que es
    exactamente el agujero que hay que encontrar— volver a correr la migración
    NO puede inventar una segunda línea de apertura que haga cuadrar el libro.
    Taparía el descuadre en vez de mostrarlo, y la reconciliación diría que todo
    está bien sobre plata que se movió sin registro.

    Sin la guarda, la primera corrida deja el libro cuadrado, el saldo cambia por
    fuera, y la segunda corrida ve `opening = 200` y lo escribe: el descuadre
    desaparece del informe y nadie se entera nunca.
    """
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("500.00"))})
        await ledger.create_opening_entries()
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("500.00")

        # El saldo se mueve SIN línea de libro: el agujero.
        await base.users.update_one(
            {"user_id": "usr_ana"},
            {"$set": {"balance_ris": Decimal128(Decimal("700.00"))}})

        segunda = await ledger.create_opening_entries()
        assert segunda["aperturas_creadas"] == 0, (
            "la migración inventó una segunda apertura y tapó el descuadre")
        aperturas = await base.ledger.find(
            {"user_id": "usr_ana", "movement_type": "saldo_apertura"}).to_list(10)
        assert len(aperturas) == 1

        # Y el descuadre sigue estando donde tiene que estar: a la vista.
        r = await ledger_admin.reconcile(admin=_Admin())
        assert r["ok"] is False
        assert r["mismatches"][0]["diff"] == 200.0
    corre(caso())


def test_un_saldo_negativo_abre_con_una_linea_de_debito(base):
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("-40.00"))})
        await ledger.create_opening_entries()
        linea, = await base.ledger.find({"user_id": "usr_ana"}).to_list(10)
        assert linea["direction"] == "debit"
        assert linea["amount"] == 40.0
        assert await ledger.sum_ris_balance("usr_ana") == Decimal("-40.00")
    corre(caso())


def test_un_usuario_que_ya_cuadra_no_recibe_apertura(base):
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("300.00"))})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "account": "balance_ris",
            "movement_type": "recarga_pix", "signed_amount": 300.0})
        r = await ledger.create_opening_entries()
        assert r["aperturas_creadas"] == 0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. Las dos rutas de super_admin
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("como", GUARDADO_COMO)
def test_reconcile_no_revienta_y_encuentra_el_descuadre(base, como):
    async def caso():
        await base.users.insert_many([
            {"user_id": "usr_ok", "email": "ok@x.com", "role": "user",
             "balance_ris": como(100)},
            {"user_id": "usr_mal", "email": "mal@x.com", "role": "user",
             "balance_ris": como(500)},
        ])
        await base.ledger.insert_one({
            "user_id": "usr_ok", "account": "balance_ris", "signed_amount": 100.0})
        # `usr_mal` tiene saldo y ni una línea: ese es el descuadre.
        r = await ledger_admin.reconcile(admin=_Admin())
        assert r["checked"] == 2
        assert r["ok"] is False
        assert r["mismatches_count"] == 1
        d, = r["mismatches"]
        assert d["user_id"] == "usr_mal"
        assert d["balance_ris"] == 500.0
        assert d["ledger_sum"] == 0.0
        assert d["diff"] == 500.0
    corre(caso())


def test_reconcile_dice_ok_cuando_todo_cuadra(base):
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user",
            "balance_ris": Decimal128(Decimal("250.00"))})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "account": "balance_ris", "signed_amount": 250.0})
        r = await ledger_admin.reconcile(admin=_Admin())
        assert r["ok"] is True
        assert r["mismatches"] == []
    corre(caso())


@pytest.mark.parametrize("como", GUARDADO_COMO)
def test_entries_no_revienta_y_muestra_saldo_contra_libro(base, como):
    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "role": "user", "balance_ris": como(80)})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "account": "balance_ris",
            "movement_type": "recarga_pix", "signed_amount": 100.0,
            "created_at": 1})
        r = await ledger_admin.list_entries(user_id="usr_ana", limit=100,
                                            admin=_Admin())
        assert r["balance_ris"] == 80.0
        assert r["ledger_sum"] == 100.0
        assert r["diff"] == -20.0
        assert r["count"] == 1
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. Que las dos reconciliaciones no vuelvan a divergir
# ══════════════════════════════════════════════════════════════════════════

def test_la_reconciliacion_nueva_tambien_lee_el_saldo_en_Decimal128(base):
    """La de `contabilidad.py` nunca tuvo el bug —lee con `to_decimal`— y este
    test lo fija: es la que se usa desde el panel para medir la divergencia."""
    from services import contabilidad

    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "email": "ana@x.com", "role": "user",
            "balance_ris": Decimal128(Decimal("500.00"))})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "book": "RIS", "account": "balance_ris",
            "direction": "credit", "amount": 500.0})
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r
        assert r["usuarios_revisados"] == 1
    corre(caso())


def test_las_dos_reconciliaciones_ven_el_mismo_descuadre(base):
    """Si difieren, una de las dos miente y no hay forma de saber cuál."""
    from routes import ledger_admin
    from services import contabilidad

    async def caso():
        await base.users.insert_one({
            "user_id": "usr_ana", "email": "ana@x.com", "role": "user",
            "balance_ris": Decimal128(Decimal("500.00"))})
        await base.ledger.insert_one({
            "user_id": "usr_ana", "book": "RIS", "account": "balance_ris",
            "direction": "credit", "amount": 120.0, "signed_amount": 120.0})

        vieja = await ledger_admin.reconcile(admin=_Admin())
        nueva = await contabilidad.reconciliacion(db=base)

        assert vieja["mismatches_count"] == 1
        assert nueva["descuadres_totales"] == 1
        assert vieja["mismatches"][0]["diff"] == 380.0
        assert nueva["descuadres"][0]["diferencia"] == "380.00"
    corre(caso())
