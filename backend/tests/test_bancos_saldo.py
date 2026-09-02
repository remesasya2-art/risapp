"""
tests/test_bancos_saldo.py — El saldo de las cuentas bancarias.

EL DEFECTO QUE ESTE ARCHIVO DEFIENDE

    `bank_accounts.balance` se escribía desde trece lugares con dos tipos: unos
    `$inc` con `Decimal128` (el ajuste manual de contabilidad) y otros con
    `float`. Del lado de Python, `Decimal128` no soporta aritmética con `float`
    NI `float(...)`, y seis rutas hacían justamente eso para calcular el saldo
    que anotan en el libro bancario.

    Resultado: **el primer ajuste manual sobre una cuenta la deja en Decimal128
    y a partir de ahí esas seis rutas devuelven 500 sobre esa cuenta.**

    `test_el_ajuste_manual_ya_no_rompe_las_rutas_que_leen_el_saldo` es ese caso,
    y está escrito para fallar con el código viejo.

EL SEGUNDO, MAS SILENCIOSO
    El saldo posterior que se archiva salía de una lectura ANTERIOR al `$inc`.
    Con dos operaciones simultáneas, las dos anotan el mismo saldo y ninguno de
    los dos es el real.
"""

import asyncio
import importlib.util
import os
import sys
import types
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from bson.decimal128 import Decimal128  # noqa: E402

# Mongomock no sabe sumar ni ordenar `Decimal128`: levanta «unsupported operand
# type(s) for +» en cualquier `$inc` sobre un campo de ese tipo. Es una
# limitación del doble, NO del producto —MongoDB lo resuelve sin pestañear— y el
# repo ya la resuelve enseñándole aritmética al propio tipo. No se aplica sola a
# propósito: cada archivo la pide, para que ningún test cambie de comportamiento
# sin haberlo declarado.
from conftest import ensenarle_decimal128_a_mongomock             # noqa: E402
ensenarle_decimal128_a_mongomock()


def _cargar(nombre):
    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    completo = f"services.{nombre}"
    if completo in sys.modules:
        return sys.modules[completo]
    ruta = os.path.join(_BACKEND, "services", f"{nombre}.py")
    spec = importlib.util.spec_from_file_location(completo, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[completo] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_cargar("money")
bancos = _cargar("bancos")


def corre(coro):
    return asyncio.run(coro)


BASE = {}


@pytest.fixture(autouse=True)
def base_limpia():
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    BASE["db"] = base
    yield base
    BASE.clear()


def cuenta(saldo, *, bank_id="bk_1", currency="VES", **extra):
    """Crea una cuenta con el saldo EXACTAMENTE del tipo que se le pase.

    El tipo es el punto de casi todos estos tests, así que no se normaliza.
    """
    doc = {"bank_id": bank_id, "name": "Banesco", "currency": currency,
           "balance": saldo}
    doc.update(extra)
    corre(BASE["db"].bank_accounts.insert_one(doc))
    return doc


def ajustar(**kw):
    return corre(bancos.ajustar(BASE["db"], **kw))


def leer(bank_id="bk_1"):
    return corre(BASE["db"].bank_accounts.find_one({"bank_id": bank_id}))


# ─── 1. El bug que estaba vivo ────────────────────────────────────────────

def test_en_produccion_sumarle_un_float_a_un_Decimal128_REVIENTA():
    """La prueba de que el peligro es real, en un intérprete LIMPIO.

    No se puede comprobar en este proceso: `conftest` le enseña aritmética a
    `Decimal128` para que mongomock pueda hacer `$inc`, y ese mismo parche tapa
    justamente el error que hay que demostrar. En producción nadie parchea el
    tipo, así que la suma revienta — y eso es lo que hacían seis rutas.
    """
    import subprocess
    codigo = (
        "from bson.decimal128 import Decimal128\n"
        "from decimal import Decimal\n"
        "b = Decimal128(Decimal('1000.00'))\n"
        "for f in (lambda: b + 500.0, lambda: float(b)):\n"
        "    try:\n"
        "        f(); print('NO REVIENTA')\n"
        "    except TypeError:\n"
        "        print('TypeError')\n"
    )
    salida = subprocess.run([sys.executable, "-c", codigo],
                            capture_output=True, text=True).stdout.split()
    assert salida == ["TypeError", "TypeError"], (
        f"el hazard cambió: {salida}. Si Decimal128 ya soporta aritmética con "
        f"float, este módulo puede simplificarse.")


def test_el_ajuste_manual_ya_no_rompe_las_rutas_que_leen_el_saldo():
    """EL CASO REAL.

    El ajuste manual de contabilidad hace `$inc` con Decimal128, así que deja el
    campo en Decimal128. Después, la aprobación de una recarga hacía
    `bank["balance"] + amount_ves` con un float: un 500 crudo, sin `try` que lo
    atrape, sobre esa cuenta y para siempre.
    """
    cuenta(Decimal128(Decimal("1000.00")))
    resultado = ajustar(bank_id="bk_1", delta=500.0)
    assert resultado["saldo_nuevo"] == Decimal("1500.00")
    assert resultado["saldo_anterior"] == Decimal("1000.00")


def test_tambien_funciona_sobre_una_cuenta_que_todavia_es_float():
    """Las cuentas que nadie ajustó a mano siguen siendo float."""
    cuenta(1000.0)
    assert ajustar(bank_id="bk_1", delta=500.0)["saldo_nuevo"] == Decimal("1500.00")


def test_leer_el_saldo_no_depende_del_tipo_guardado():
    # `Decimal` a secas no está: BSON no lo sabe codificar, así que en la base
    # sólo pueden existir estos tres.
    for i, guardado in enumerate([1000.0, Decimal128(Decimal("1000.00")),
                                  "1000.00"]):
        cuenta(guardado, bank_id=f"bk_t{i}")
        doc = leer(f"bk_t{i}")
        assert bancos.saldo_de(doc) == Decimal("1000.00"), f"falló con {type(guardado)}"


def test_una_cuenta_sin_campo_de_saldo_vale_cero_y_no_revienta():
    corre(BASE["db"].bank_accounts.insert_one({"bank_id": "bk_v", "name": "X"}))
    assert bancos.saldo_de(leer("bk_v")) == Decimal("0.00")


def test_despues_de_ajustar_el_campo_queda_en_Decimal128():
    """Para que la próxima lectura tampoco tenga que adivinar el tipo."""
    cuenta(1000.0)
    ajustar(bank_id="bk_1", delta=1.0)
    assert isinstance(leer()["balance"], Decimal128)


# ─── 2. El saldo que se archiva es el que ocurrió ─────────────────────────

def test_el_saldo_posterior_sale_de_la_escritura_y_no_de_una_lectura_vieja():
    """Dos entradas seguidas sobre la misma cuenta.

    El código viejo leía el saldo ANTES del `$inc` y le sumaba el monto. Con dos
    operaciones simultáneas las dos leían 1000 y las dos anotaban 1100 en el
    libro bancario, cuando el saldo real había quedado en 1200.
    """
    cuenta(Decimal128(Decimal("1000.00")))
    primero = ajustar(bank_id="bk_1", delta=100.0)
    segundo = ajustar(bank_id="bk_1", delta=100.0)
    assert primero["saldo_nuevo"] == Decimal("1100.00")
    assert segundo["saldo_nuevo"] == Decimal("1200.00"), \
        "el segundo anotó el mismo saldo que el primero"
    assert segundo["saldo_anterior"] == Decimal("1100.00")


def test_el_saldo_anterior_es_coherente_con_el_nuevo():
    cuenta(Decimal128(Decimal("500.00")))
    r = ajustar(bank_id="bk_1", delta=-125.50)
    assert r["saldo_nuevo"] == Decimal("374.50")
    assert r["saldo_anterior"] - r["saldo_nuevo"] == Decimal("125.50")


# ─── 3. Precisión ─────────────────────────────────────────────────────────

def test_sumar_centavos_no_deriva():
    """Con float, sumar 0.10 diez veces no da 1.00."""
    cuenta(Decimal128(Decimal("0.00")))
    for _ in range(10):
        ajustar(bank_id="bk_1", delta=0.10)
    assert bancos.saldo_de(leer()) == Decimal("1.00")


def test_el_clasico_0_1_mas_0_2():
    cuenta(Decimal128(Decimal("0.00")))
    ajustar(bank_id="bk_1", delta=0.1)
    ajustar(bank_id="bk_1", delta=0.2)
    assert bancos.saldo_de(leer()) == Decimal("0.30")


def test_el_delta_se_acepta_venga_como_venga():
    for i, delta in enumerate([100, 100.0, "100", Decimal("100"),
                               Decimal128(Decimal("100"))]):
        cuenta(Decimal128(Decimal("0.00")), bank_id=f"bk_d{i}")
        r = ajustar(bank_id=f"bk_d{i}", delta=delta)
        assert r["saldo_nuevo"] == Decimal("100.00"), f"falló con {type(delta)}"


# ─── 4. El guard de saldo ─────────────────────────────────────────────────

def test_un_debito_sin_saldo_no_escribe_nada():
    cuenta(Decimal128(Decimal("100.00")))
    with pytest.raises(bancos.SaldoInsuficiente):
        ajustar(bank_id="bk_1", delta=-500.0, exigir_saldo=True)
    assert bancos.saldo_de(leer()) == Decimal("100.00"), "descontó igual"


def test_el_debito_exacto_del_saldo_SI_se_permite():
    """`$gte`, no `$gt`: dejar la cuenta en cero es legítimo."""
    cuenta(Decimal128(Decimal("100.00")))
    assert ajustar(bank_id="bk_1", delta=-100.0,
                   exigir_saldo=True)["saldo_nuevo"] == Decimal("0.00")


def test_el_error_de_saldo_dice_cuanto_habia():
    """Sin el disponible, el operador no sabe cuánto le falta poner."""
    cuenta(Decimal128(Decimal("100.00")))
    with pytest.raises(bancos.SaldoInsuficiente) as e:
        ajustar(bank_id="bk_1", delta=-500.0, exigir_saldo=True)
    assert e.value.disponible == Decimal("100.00")
    assert e.value.pedido == Decimal("500.00")


def test_sin_exigir_saldo_la_cuenta_puede_quedar_negativa():
    """La compra de USDT lo permite a propósito; no se cambia ese criterio."""
    cuenta(Decimal128(Decimal("100.00")))
    assert ajustar(bank_id="bk_1", delta=-500.0)["saldo_nuevo"] == Decimal("-400.00")


def test_el_guard_funciona_sobre_una_cuenta_que_todavia_es_float():
    """La comparación es entre Decimal128 y un campo float: Mongo la resuelve
    numéricamente, pero hay que comprobarlo y no suponerlo."""
    cuenta(1000.0)
    assert ajustar(bank_id="bk_1", delta=-400.0,
                   exigir_saldo=True)["saldo_nuevo"] == Decimal("600.00")
    with pytest.raises(bancos.SaldoInsuficiente):
        ajustar(bank_id="bk_1", delta=-5000.0, exigir_saldo=True)


def test_una_cuenta_que_no_existe_se_distingue_de_una_sin_saldo():
    """Confundirlas manda al operador a buscar donde no es."""
    with pytest.raises(bancos.CuentaInexistente):
        ajustar(bank_id="bk_fantasma", delta=100.0)


# ─── 5. Crear la cuenta de una pasarela ───────────────────────────────────

def test_la_cuenta_de_una_pasarela_nace_en_Decimal128():
    """Mercado Pago y la tarjeta la creaban con `"balance": 0.0` y después le
    sumaban floats: el tipo dependía de quién la tocara primero."""
    corre(bancos.asegurar_cuenta(BASE["db"], bank_id="mp_1", name="Mercado Pago",
                                 currency="brl", is_gateway=True))
    doc = leer("mp_1")
    assert isinstance(doc["balance"], Decimal128)
    assert doc["currency"] == "BRL"
    assert doc["is_gateway"] is True


def test_asegurar_una_cuenta_que_ya_existe_NO_le_pisa_el_saldo():
    """Sería devolver el saldo a cero en cada pago que entra."""
    cuenta(Decimal128(Decimal("777.00")), bank_id="mp_1")
    corre(bancos.asegurar_cuenta(BASE["db"], bank_id="mp_1", name="Otro",
                                 currency="BRL"))
    assert bancos.saldo_de(leer("mp_1")) == Decimal("777.00")


# ─── 6. El total real, por moneda ─────────────────────────────────────────

def test_el_total_no_mezcla_monedas():
    """Es la mitad «dinero real» de la conciliación del pozo."""
    cuenta(Decimal128(Decimal("1000.00")), bank_id="b1", currency="VES")
    cuenta(500.0, bank_id="b2", currency="VES")
    cuenta(Decimal128(Decimal("300.00")), bank_id="b3", currency="BRL")
    t = corre(bancos.total_por_moneda(BASE["db"]))
    assert t["VES"]["total"] == Decimal("1500.00")
    assert t["VES"]["cuentas"] == 2
    assert t["BRL"]["total"] == Decimal("300.00")


def test_el_total_suma_bien_aunque_los_tipos_esten_mezclados():
    """Es el caso real de hoy: la mitad de las cuentas migradas y la mitad no."""
    for i in range(10):
        cuenta(0.10 if i % 2 else Decimal128(Decimal("0.10")),
               bank_id=f"b{i}", currency="VES")
    assert corre(bancos.total_por_moneda(BASE["db"]))["VES"]["total"] == Decimal("1.00")


def test_las_cuentas_ocultas_no_entran_en_el_total():
    cuenta(Decimal128(Decimal("100.00")), bank_id="b1", currency="VES")
    cuenta(Decimal128(Decimal("999.00")), bank_id="b2", currency="VES",
           hidden_from_admin=True)
    assert corre(bancos.total_por_moneda(BASE["db"]))["VES"]["total"] == Decimal("100.00")


def test_una_cuenta_sin_moneda_no_desaparece_del_total():
    """Sumarla a otra moneda sería peor, pero perderla del pozo también."""
    cuenta(Decimal128(Decimal("50.00")), bank_id="b1", currency=None)
    t = corre(bancos.total_por_moneda(BASE["db"]))
    assert t["SIN_MONEDA"]["total"] == Decimal("50.00")


# ─── 7. Condiciones que valen en el momento de la escritura ───────────────

def test_una_cuenta_oculta_no_se_puede_debitar():
    """El débito del motor contable excluía las cuentas deshabilitadas dentro
    del propio filtro. Perder esa condición al centralizar habría dejado
    debitar cuentas que el operador dio de baja."""
    cuenta(Decimal128(Decimal("1000.00")), hidden_from_admin=True)
    with pytest.raises(bancos.CuentaNoDisponible):
        ajustar(bank_id="bk_1", delta=-100.0, exigir_saldo=True,
                filtro_extra={"hidden_from_admin": {"$ne": True}})
    assert bancos.saldo_de(leer()) == Decimal("1000.00"), "descontó igual"


def test_una_cuenta_visible_SI_se_debita_con_el_mismo_filtro():
    """El guard tiene que dejar pasar el caso normal."""
    cuenta(Decimal128(Decimal("1000.00")))
    r = ajustar(bank_id="bk_1", delta=-100.0, exigir_saldo=True,
                filtro_extra={"hidden_from_admin": {"$ne": True}})
    assert r["saldo_nuevo"] == Decimal("900.00")


def test_una_cuenta_oculta_SIN_saldo_dice_que_esta_oculta_y_no_que_falta_plata():
    """Confundirlas manda al operador a reponer plata que no arregla nada."""
    cuenta(Decimal128(Decimal("10.00")), hidden_from_admin=True)
    with pytest.raises(bancos.CuentaNoDisponible):
        ajustar(bank_id="bk_1", delta=-500.0, exigir_saldo=True,
                filtro_extra={"hidden_from_admin": {"$ne": True}})
