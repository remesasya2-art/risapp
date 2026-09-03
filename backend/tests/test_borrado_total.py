"""
tests/test_borrado_total.py — El botón que borra la app, y el libro que sobrevive.

QUE ESTABA MAL

    1. EL LIBRO QUEDABA HUERFANO. El borrado pone los saldos en cero y no toca
       `ledger`. A partir de ahí la reconciliación marca descuadre en TODOS los
       usuarios a la vez, y el informe deja de servir para encontrar el
       descuadre que sí importa.

       La salida obvia —agregar `ledger` a la lista de borrado— sería un error:
       un libro contable es append-only justamente para que no se pueda borrar.
       Así que el borrado lo CIERRA: una línea por cuenta que lo lleva a cero.

    2. LAS BILLETERAS CRIPTO SOBREVIVIAN. Se ponían en cero `balance_ris` y
       `balance_ris_terceros`; `balance_usdt` y `balance_usdc` quedaban con su
       plata intacta y sin ninguna historia detrás.

    3. SIETE COLECCIONES DE PLATA QUEDABAN VIVAS: pagos con tarjeta, depósitos
       cripto, comisiones de pasarela, ganancias de socios, remesas BTC,
       billeteras BTC y ventas P2P.

    4. EL «SOFT-DELETE» ERA CODIGO MUERTO. `_hide_from_admin("transactions")`
       corría DESPUES de vaciar esa misma colección, así que marcaba cero
       documentos. Venía copiado del borrado de contabilidad —donde sí sirve—
       y hacía creer que el usuario conservaba su historial. No lo conservaba.
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

from services import contabilidad, ledger                           # noqa: E402
from services.money import ZERO                                     # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True
    return b


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"
    role = "super_admin"


def d(x, places=2):
    return Decimal128(Decimal(str(x)).quantize(Decimal(1).scaleb(-places)))


async def _mundo(base):
    """Una base con plata en las cuatro cuentas y su libro respaldándola."""
    await base.users.insert_many([
        {"user_id": "u1", "email": "a@x.com", "name": "Ana", "role": "user",
         "balance_ris": d(500), "balance_ris_terceros": d(0),
         "balance_usdt": d("12.34567890", 8), "balance_usdc": d(0, 8)},
        {"user_id": "u2", "email": "b@x.com", "name": "Beto", "role": "socio_gestor",
         "balance_ris": d(100), "balance_ris_terceros": d(700),
         "balance_usdt": d(0, 8), "balance_usdc": d(0, 8)},
    ])
    await base.ledger.insert_many([
        {"user_id": "u1", "book": "RIS", "account": "balance_ris",
         "movement_type": "recarga_pix", "direction": "credit",
         "amount": 500.0, "signed_amount": 500.0},
        {"user_id": "u1", "book": "USDT", "account": "balance_usdt",
         "movement_type": "deposito_cripto", "direction": "credit",
         "amount": 12.3456789, "signed_amount": 12.3456789},
        {"user_id": "u2", "book": "RIS", "account": "balance_ris",
         "movement_type": "recarga_pix", "direction": "credit",
         "amount": 100.0, "signed_amount": 100.0},
        {"user_id": "u2", "book": "RIS", "account": "balance_ris_terceros",
         "movement_type": "recarga_pix", "direction": "credit",
         "amount": 700.0, "signed_amount": 700.0},
    ])


# ══════════════════════════════════════════════════════════════════════════
# 1. El cierre del libro
# ══════════════════════════════════════════════════════════════════════════

def test_el_cierre_lleva_cada_cuenta_a_cero(base):
    async def caso():
        await _mundo(base)
        r = await ledger.create_closing_entries(actor_id="usr_super")
        assert r["cierres_creados"] == 4, r
        assert r["por_cuenta"] == {"balance_ris": 2, "balance_ris_terceros": 1,
                                   "balance_usdt": 1}
        for uid, cuenta, dec in (("u1", "balance_ris", 2), ("u1", "balance_usdt", 8),
                                 ("u2", "balance_ris", 2),
                                 ("u2", "balance_ris_terceros", 2)):
            assert await ledger.sum_ris_balance(uid, cuenta, dec) == ZERO, (uid, cuenta)
    corre(caso())


def test_el_cierre_NO_borra_una_sola_linea(base):
    """La razón de ser del cierre: la historia queda entera."""
    async def caso():
        await _mundo(base)
        antes = await base.ledger.count_documents({})
        await ledger.create_closing_entries(actor_id="usr_super")
        despues = await base.ledger.count_documents({})
        assert despues == antes + 4, "el cierre AGREGA líneas, no las quita"
        # Y las originales siguen ahí, con su tipo de movimiento.
        assert await base.ledger.count_documents({"movement_type": "recarga_pix"}) == 3
        assert await base.ledger.count_documents({"movement_type": "deposito_cripto"}) == 1
    corre(caso())


def test_el_cierre_de_cripto_no_pierde_decimales(base):
    """USDT lleva ocho decimales: cerrarlo a dos dejaría un resto invisible."""
    async def caso():
        await _mundo(base)
        await ledger.create_closing_entries(actor_id="usr_super")
        cierre, = await base.ledger.find(
            {"user_id": "u1", "account": "balance_usdt",
             "movement_type": "cierre_de_libro"}).to_list(10)
        assert cierre["amount"] == pytest.approx(12.3456789, abs=1e-9)
        assert cierre["book"] == "USDT"
        assert await ledger.sum_ris_balance("u1", "balance_usdt", 8) == ZERO
    corre(caso())


def test_el_cierre_de_un_libro_en_negativo_es_un_credito(base):
    async def caso():
        await base.users.insert_one({"user_id": "u1", "balance_ris": d(-40)})
        await base.ledger.insert_one(
            {"user_id": "u1", "book": "RIS", "account": "balance_ris",
             "direction": "debit", "amount": 40.0, "signed_amount": -40.0})
        await ledger.create_closing_entries(actor_id="usr_super")
        cierre, = await base.ledger.find(
            {"movement_type": "cierre_de_libro"}).to_list(10)
        assert cierre["direction"] == "credit"
        assert cierre["amount"] == 40.0
        assert cierre["balance_before"] == -40.0
        assert cierre["balance_after"] == 0.0
    corre(caso())


def test_un_usuario_sin_libro_no_recibe_cierre(base):
    async def caso():
        await base.users.insert_one({"user_id": "u_limpio", "balance_ris": d(0)})
        r = await ledger.create_closing_entries(actor_id="usr_super")
        assert r["cierres_creados"] == 0
        assert await base.ledger.count_documents({}) == 0
    corre(caso())


def test_el_cierre_deja_constancia_de_quien_y_por_que(base):
    async def caso():
        await _mundo(base)
        await ledger.create_closing_entries(
            actor_id="usr_super", actor_email="super@risappbr.com", motivo="wipe_all")
        linea = await base.ledger.find_one({"movement_type": "cierre_de_libro"})
        assert linea["actor"]["id"] == "usr_super"
        assert linea["actor"]["email"] == "super@risappbr.com"
        assert linea["metadata"]["motivo"] == "wipe_all"
        assert linea["reference"]["id"] == "cierre_wipe_all"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que el cierre le hace a la reconciliación — el punto de todo esto
# ══════════════════════════════════════════════════════════════════════════

def test_sin_cierre_la_reconciliacion_se_enciende_entera(base):
    """El estado que había: saldos en cero y el libro lleno."""
    async def caso():
        await _mundo(base)
        await base.users.update_many({}, {"$set": {
            "balance_ris": d(0), "balance_ris_terceros": d(0),
            "balance_usdt": d(0, 8), "balance_usdc": d(0, 8)}})
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is False
        assert r["descuadres_totales"] >= 2, (
            "los dos usuarios tendrían que aparecer descuadrados")
    corre(caso())


def test_con_cierre_la_reconciliacion_cuadra(base):
    """Y el estado que queda ahora: el libro cerrado y los saldos en cero."""
    async def caso():
        await _mundo(base)
        await ledger.create_closing_entries(actor_id="usr_super")
        await base.users.update_many({}, {"$set": {
            "balance_ris": d(0), "balance_ris_terceros": d(0),
            "balance_usdt": d(0, 8), "balance_usdc": d(0, 8)}})
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())


def test_las_dos_patas_apertura_y_cierre_se_anulan_en_el_patrimonio(base):
    """Abrir y después cerrar no puede dejar rastro en el patrimonio."""
    async def caso():
        await base.users.insert_one({"user_id": "u1", "balance_ris": d(500)})
        await ledger.create_opening_entries()
        await ledger.create_closing_entries(actor_id="usr_super")

        saldo = {}
        for linea in await base.ledger.find({"user_id": "u1"}).to_list(50):
            a = contabilidad.asiento_de(linea)
            assert a["clasificado"], f"movimiento sin clasificar: {a}"
            saldo[a["debe"]] = saldo.get(a["debe"], 0) + a["monto"]
            saldo[a["haber"]] = saldo.get(a["haber"], 0) - a["monto"]
        assert "3.1.01" in saldo
        assert saldo["3.1.01"] == 0, f"la apertura y el cierre no se anulan: {saldo}"
        assert saldo["2.1.01"] == 0, "y el pasivo del usuario queda en cero"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La lista de lo que se borra
# ══════════════════════════════════════════════════════════════════════════

def test_las_siete_colecciones_de_plata_estan_en_la_lista():
    """Se llamaba «borrado total» y dejaba siete colecciones de plata vivas."""
    ruta = os.path.join(_BACKEND, "routes", "admin.py")
    fuente = open(ruta, encoding="utf-8").read()
    import ast
    arbol = ast.parse(fuente)
    listas = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name):
            nombre = nodo.targets[0].id
            if nombre in ("_ALL_DATA_COLLECTIONS", "_SALDOS_A_RESETEAR"):
                listas[nombre] = [x.value for x in nodo.value.elts]

    borradas = set(listas["_ALL_DATA_COLLECTIONS"])
    for coleccion in ("card_payments", "crypto_deposits", "gateway_fee_ledger",
                      "partner_earnings", "btc_remesas", "btc_ves_wallets",
                      "p2p_sales"):
        assert coleccion in borradas, f"{coleccion} sobrevive a un «borrado total»"

    assert "ledger" not in borradas, (
        "el libro NO se borra: se cierra con asientos. Un libro contable es "
        "append-only justamente para que no se pueda borrar.")

    saldos = set(listas["_SALDOS_A_RESETEAR"])
    assert saldos == {"balance_ris", "balance_ris_terceros",
                      "balance_usdt", "balance_usdc"}, (
        "las billeteras cripto sobrevivían al borrado con su plata intacta")


def test_el_soft_delete_muerto_ya_no_esta():
    """`_hide_from_admin` sobre una colección recién vaciada marcaba cero
    documentos, y hacía creer que el usuario conservaba su historial."""
    import ast
    ruta = os.path.join(_BACKEND, "routes", "admin.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and nodo.name == "wipe_all_data":
            llamadas = {
                (c.func.attr if isinstance(c.func, ast.Attribute)
                 else getattr(c.func, "id", ""))
                for c in ast.walk(nodo) if isinstance(c, ast.Call)}
            assert "_hide_from_admin" not in llamadas, (
                "el borrado total vacía la colección antes: esconderla después "
                "no hace nada")
            assert "create_closing_entries" in llamadas, (
                "el borrado tiene que cerrar el libro")
            return
    pytest.fail("no se encontró wipe_all_data")


def test_el_borrado_de_contabilidad_SI_conserva_su_soft_delete():
    """Ahí sí sirve: ese borrado no toca `transactions`, así que esconderlas
    del informe es exactamente lo que hay que hacer."""
    import ast
    ruta = os.path.join(_BACKEND, "routes", "admin.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and nodo.name == "wipe_accounting_data":
            llamadas = {
                (c.func.attr if isinstance(c.func, ast.Attribute)
                 else getattr(c.func, "id", ""))
                for c in ast.walk(nodo) if isinstance(c, ast.Call)}
            assert "_hide_from_admin" in llamadas
            return
    pytest.fail("no se encontró wipe_accounting_data")
