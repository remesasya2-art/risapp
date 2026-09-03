"""
tests/test_gestor_plata_de_terceros.py — La plata que un gestor tiene de otros.

POR QUE ESTE MODULO IMPORTA MAS QUE LOS OTROS

    `balance_ris_terceros` no es plata del gestor: es plata de SUS CLIENTES, que
    él administra. Un error acá no le cuesta a la empresa ni al gestor — le
    cuesta a alguien que ni siquiera tiene cuenta en la app.

    Y `routes/gestor.py` no tenía un solo test que lo importara. Es el tercero
    de los seis módulos que mueven plata y estaban sin cubrir, y otro que yo
    reescribí en el PR #57 sin nada que ejercitara el sitio de la llamada.

LAS DOS OPERACIONES

    · `process_gestor_transaction` — el gestor paga una remesa con plata de
      terceros. Debita `balance_ris_terceros` y crea el retiro que el Panel
      después procesa.

    · `gestor_recharge_terceros` — el gestor pasa plata de su saldo personal al
      de terceros. Antes comprobaba el saldo en Python y después escribía sin
      condición: dos traspasos simultáneos pasaban los dos y el saldo personal
      quedaba EN NEGATIVO. El #57 lo metió en una sola escritura con el guard
      dentro del filtro; acá se prueba el sitio de la llamada.
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

from services import ledger, saldos                                 # noqa: E402


def _cargar_gestor():
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
    import routes.gestor as g
    return g


g = _cargar_gestor()
from fastapi import HTTPException                                   # noqa: E402
from models.requests import (GestorTransactionRequest,               # noqa: E402
                             GestorRechargeTercerosRequest)


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


class _Gestor:
    user_id = "usr_gestor"
    email = "gestor@x.com"
    name = "Gestor Test"
    role = "socio_gestor"


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(g, "create_notification", _nada)
    return b


async def _mundo(base, personal=1000, terceros=2000):
    await base.users.insert_one({
        "user_id": "usr_gestor", "email": "gestor@x.com", "name": "Gestor Test",
        "role": "socio_gestor", "gestor_code": "G-01",
        "balance_ris": d(personal), "balance_ris_terceros": d(terceros)})
    await base.gestor_beneficiaries.insert_one({
        "beneficiary_id": "ben_1", "gestor_id": "usr_gestor",
        "full_name": "María Pérez", "id_document": "V-12345678",
        "bank": "Banesco", "bank_code": "0134", "phone_number": "04141234567",
        "account_number": "01340000000000000000"})
    await base.rates.insert_one({"ris_to_ves": 92.0, "updated_at": 1})


def _envio(monto=300.0):
    return GestorTransactionRequest(
        beneficiary_id="ben_1", amount_ris=monto, client_name="Cliente Uno",
        client_phone="04141112233", payment_type="pago_movil")


async def _lineas(base):
    return await base.ledger.find({"user_id": "usr_gestor"}).to_list(50)


async def _saldos(base):
    doc = await base.users.find_one({"user_id": "usr_gestor"})
    return (saldos.saldo_de(doc, "balance_ris"),
            saldos.saldo_de(doc, "balance_ris_terceros"))


# ══════════════════════════════════════════════════════════════════════════
# 1. El envío: sale de la cuenta de TERCEROS, no de la del gestor
# ══════════════════════════════════════════════════════════════════════════

def test_el_envio_debita_la_cuenta_de_terceros_y_no_la_personal(base):
    """Si sale de la cuenta equivocada, el gestor paga de su bolsillo una
    remesa de un cliente — o al revés, gasta plata ajena."""
    async def caso():
        await _mundo(base, personal=1000, terceros=2000)
        await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        personal, terceros = await _saldos(base)
        assert terceros == Decimal("1700.00")
        assert personal == Decimal("1000.00"), "no se toca el saldo del gestor"
    corre(caso())


def test_el_envio_deja_su_linea_en_la_cuenta_correcta(base):
    async def caso():
        await _mundo(base)
        await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        linea, = await _lineas(base)
        assert linea["account"] == "balance_ris_terceros"
        assert linea["direction"] == "debit"
        assert linea["amount"] == 300.0
        assert linea["movement_type"] == "envio_ves"
        assert linea["currency_output"] == "VES"
        assert linea["metadata"]["is_gestor_transaction"] is True
        assert linea["metadata"]["client_name"] == "Cliente Uno"
        assert linea["counterparty"]["full_name"] == "María Pérez"
    corre(caso())


def test_sin_saldo_de_terceros_no_se_debita_ni_queda_la_transaccion(base):
    """Y la transacción que se había creado antes del débito tiene que
    deshacerse: si no, queda un envío fantasma que el Panel va a intentar pagar."""
    async def caso():
        await _mundo(base, personal=99999, terceros=100)
        with pytest.raises(HTTPException) as e:
            await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        assert e.value.status_code == 400
        personal, terceros = await _saldos(base)
        assert terceros == Decimal("100.00")
        assert personal == Decimal("99999.00"), (
            "no puede caer sobre el saldo personal del gestor")
        assert await base.gestor_transactions.count_documents({}) == 0, (
            "quedó una transacción fantasma")
        assert await _lineas(base) == []
    corre(caso())


def test_LA_CARRERA_el_guard_atomico_ataja_lo_que_la_comprobacion_previa_no(base, monkeypatch):
    """El test que faltaba, y la razón por la que faltaba.

    `process_gestor_transaction` comprueba el saldo DOS veces:

      1. En Python, leyendo el usuario (`if balance_terceros < amount: 400`).
      2. Dentro del filtro de la escritura, con `exigir_saldo=True`.

    Un test que simplemente pide más plata de la que hay sólo ejercita la
    primera. Lo descubrí por mutación: poner `exigir_saldo=False` NO ponía
    ningún test en rojo, porque la comprobación de Python atajaba el caso antes.

    Pero la que importa es la SEGUNDA. La primera lee y después escribe, y entre
    esas dos cosas otra petición puede llevarse la plata: es justo la carrera que
    deja el saldo de terceros en negativo, con dinero de clientes.

    Acá se reproduce esa ventana: la lectura previa devuelve un saldo que ya no
    existe. Si el guard atómico no está, el débito pasa igual y la cuenta queda
    negativa.
    """
    async def caso():
        await _mundo(base, personal=0, terceros=100)

        # La lectura del chequeo previo ve 5000; la base sigue teniendo 100.
        #
        # Se envuelve el `db` DEL MODULO, no la base: la ruta usa su propio
        # `db`, y mongomock devuelve un objeto de colección nuevo en cada
        # acceso, así que parchear `base.users.find_one` no alcanza —lo aprendí
        # a la mala: el test pasaba igual con el guard quitado—.
        estado = {"primera": True}

        class _UsuariosConLecturaRancia:
            def __init__(self, real):
                self._real = real

            async def find_one(self, consulta, *a, **k):
                doc = await self._real.find_one(consulta, *a, **k)
                if estado["primera"] and doc and "balance_ris_terceros" in doc:
                    estado["primera"] = False
                    doc = dict(doc)
                    doc["balance_ris_terceros"] = d(5000)
                return doc

            def __getattr__(self, nombre):
                return getattr(self._real, nombre)

        class _BaseConLecturaRancia:
            def __init__(self, real):
                self._real = real

            @property
            def users(self):
                return _UsuariosConLecturaRancia(self._real.users)

            def __getattr__(self, nombre):
                return getattr(self._real, nombre)

            def __getitem__(self, nombre):
                if nombre == "users":
                    return self.users
                return self._real[nombre]

        trucada = _BaseConLecturaRancia(base)
        monkeypatch.setattr(g, "db", trucada)
        with pytest.raises(HTTPException) as e:
            await g.process_gestor_transaction(_envio(300), current_user=_Gestor())

        assert e.value.status_code == 400
        personal, terceros = await _saldos(base)
        assert terceros == Decimal("100.00"), (
            "el débito pasó pese a no haber saldo: falta el guard en la escritura")
        assert personal == Decimal("0.00")
        assert await _lineas(base) == []
        assert await base.gestor_transactions.count_documents({}) == 0, (
            "quedó una transacción fantasma que el Panel va a intentar pagar")
    corre(caso())


def test_con_el_saldo_justo_el_envio_pasa(base):
    async def caso():
        await _mundo(base, terceros=300)
        await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        _, terceros = await _saldos(base)
        assert terceros == Decimal("0.00")
    corre(caso())


@pytest.mark.parametrize("monto", [0, -50])
def test_un_monto_que_no_es_positivo_se_rechaza(base, monto):
    async def caso():
        await _mundo(base)
        with pytest.raises(HTTPException) as e:
            await g.process_gestor_transaction(_envio(monto), current_user=_Gestor())
        assert e.value.status_code == 400
        assert await _lineas(base) == []
    corre(caso())


def test_un_beneficiario_de_otro_gestor_no_se_puede_usar(base):
    """El beneficiario se busca por `gestor_id`: un gestor no puede mandar
    plata a la lista de otro."""
    async def caso():
        await _mundo(base)
        await base.gestor_beneficiaries.update_one(
            {"beneficiary_id": "ben_1"}, {"$set": {"gestor_id": "otro_gestor"}})
        with pytest.raises(HTTPException) as e:
            await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        assert e.value.status_code == 404
        _, terceros = await _saldos(base)
        assert terceros == Decimal("2000.00")
    corre(caso())


def test_el_envio_crea_el_retiro_que_el_panel_va_a_procesar(base):
    async def caso():
        await _mundo(base)
        await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        retiro = await base.transactions.find_one({"type": "withdrawal"})
        assert retiro is not None, "sin el retiro, la plata salió y nadie la paga"
        assert retiro["status"] == "pending"
        assert retiro["amount_input"] == 300.0
        assert retiro["user_id"] == "usr_gestor"
        gtx = await base.gestor_transactions.find_one({})
        assert gtx["display_id"] == retiro["display_id"], (
            "las dos puntas tienen que compartir el mismo número")
    corre(caso())


def test_el_saldo_y_el_libro_cuadran_despues_del_envio(base):
    from services import contabilidad

    async def caso():
        await _mundo(base, personal=0, terceros=2000)
        # Apertura, para que el libro arranque igualado al saldo.
        await ledger.create_opening_entries()
        await g.process_gestor_transaction(_envio(300), current_user=_Gestor())
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. El traspaso: la carrera que dejaba el saldo en negativo
# ══════════════════════════════════════════════════════════════════════════

def test_el_traspaso_mueve_las_dos_cuentas(base):
    async def caso():
        await _mundo(base, personal=1000, terceros=200)
        r = await g.gestor_recharge_terceros(
            GestorRechargeTercerosRequest(amount=300), current_user=_Gestor())
        assert r["balance_ris"] == 700.0
        assert r["balance_ris_terceros"] == 500.0
        personal, terceros = await _saldos(base)
        assert (personal, terceros) == (Decimal("700.00"), Decimal("500.00"))
    corre(caso())


def test_el_traspaso_deja_SUS_DOS_patas_en_el_libro(base):
    """Un traspaso es dos movimientos: sale de una cuenta y entra en la otra."""
    async def caso():
        await _mundo(base, personal=1000, terceros=0)
        await g.gestor_recharge_terceros(
            GestorRechargeTercerosRequest(amount=300), current_user=_Gestor())
        lineas = await _lineas(base)
        assert len(lineas) == 2
        salida = next(x for x in lineas if x["account"] == "balance_ris")
        entrada = next(x for x in lineas if x["account"] == "balance_ris_terceros")
        assert (salida["direction"], salida["amount"]) == ("debit", 300.0)
        assert (entrada["direction"], entrada["amount"]) == ("credit", 300.0)
        assert {x["movement_type"] for x in lineas} == {"traspaso_interno"}
    corre(caso())


def test_el_traspaso_sin_saldo_no_deja_el_personal_en_negativo(base):
    """LA CARRERA. Antes se comprobaba el saldo en Python y después se escribía
    sin condición; ahora el guard va dentro del filtro de la escritura."""
    async def caso():
        await _mundo(base, personal=100, terceros=0)
        with pytest.raises(HTTPException) as e:
            await g.gestor_recharge_terceros(
                GestorRechargeTercerosRequest(amount=300), current_user=_Gestor())
        assert e.value.status_code == 400
        assert "insuficiente" in str(e.value.detail).lower()
        personal, terceros = await _saldos(base)
        assert personal == Decimal("100.00"), "el saldo personal quedó tocado"
        assert terceros == Decimal("0.00")
        assert await _lineas(base) == []
    corre(caso())


def test_el_traspaso_con_el_saldo_justo_pasa(base):
    async def caso():
        await _mundo(base, personal=300, terceros=0)
        r = await g.gestor_recharge_terceros(
            GestorRechargeTercerosRequest(amount=300), current_user=_Gestor())
        assert r["balance_ris"] == 0.0
        assert r["balance_ris_terceros"] == 300.0
    corre(caso())


@pytest.mark.parametrize("monto", [0, -50])
def test_un_traspaso_que_no_es_positivo_se_rechaza(base, monto):
    async def caso():
        await _mundo(base, personal=1000, terceros=0)
        with pytest.raises(HTTPException) as e:
            await g.gestor_recharge_terceros(
                GestorRechargeTercerosRequest(amount=monto), current_user=_Gestor())
        assert e.value.status_code == 400
        assert await _saldos(base) == (Decimal("1000.00"), Decimal("0.00"))
    corre(caso())


def test_el_traspaso_no_cambia_el_total_que_el_gestor_tiene(base):
    """No entra ni sale plata: sólo cambia de bolsillo. Si el total se mueve,
    el traspaso está creando o destruyendo dinero."""
    async def caso():
        await _mundo(base, personal=1000, terceros=200)
        antes = sum(await _saldos(base))
        await g.gestor_recharge_terceros(
            GestorRechargeTercerosRequest(amount=350), current_user=_Gestor())
        assert sum(await _saldos(base)) == antes
    corre(caso())


def test_el_traspaso_deja_el_libro_cuadrado(base):
    from services import contabilidad

    async def caso():
        await _mundo(base, personal=1000, terceros=0)
        await ledger.create_opening_entries()
        await g.gestor_recharge_terceros(
            GestorRechargeTercerosRequest(amount=300), current_user=_Gestor())
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())
