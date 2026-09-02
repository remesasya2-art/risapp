"""
tests/test_recarga_ves.py — La recarga en bolivares, de punta a punta.

POR QUE ESTE ARCHIVO EXISTE
    `POST /recharge/ves` armaba el documento que insertaba en `transactions` con
    el monto, la tasa y el metodo de pago, y NO escribia ni el banco destino ni
    el comprobante. Los dos llegaban en el cuerpo y no se leian nunca.

    Consecuencia: ninguna recarga VES se podia aprobar por el camino normal —el
    aprobador buscaba `destination_bank_id`, no lo encontraba y devolvia un 400
    que ademas culpaba al usuario— y el operador quedaba por acreditar dinero
    sin poder ver el comprobante que el usuario si habia subido.

    NO HABIA UN SOLO TEST DE ESTA RUTA. Uno que solo mirara el 200 de la
    creacion tampoco habria visto nada: la ruta contestaba 200 perfecto mientras
    tiraba los dos campos a la basura. Por eso todos los de aca miran EL
    DOCUMENTO GUARDADO, no la respuesta.

CONTRA MONGOMOCK, NO CONTRA UN DOBLE
    Esto mueve saldo: el circuito completo credita el balance del usuario y deja
    un asiento en `bank_ledger`. Un doble escrito a mano solo falla donde su
    autor penso que podia fallar, y lo que hay que verificar aca es que la plata
    llegue a la cuenta correcta.
"""

import asyncio
import importlib.util
import os
import sys
import types

import pytest
from decimal import Decimal

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)


def _preparar():
    """Carga las dos rutas por ruta directa, sin arrastrar el proyecto entero."""
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

    import routes.transactions as tx
    import routes.admin as adm
    return tx, adm


tx, adm = _preparar()
from fastapi import HTTPException                                    # noqa: E402


# El saldo se guarda como Decimal128 —asi lo guarda toda la app— y mongomock no
# sabe sumarlo. No es un problema del producto: se le ensena al tipo, que es
# exactamente lo que hace el servidor de verdad.
from conftest import ensenarle_decimal128_a_mongomock              # noqa: E402
ensenarle_decimal128_a_mongomock()


def corre(coro):
    return asyncio.run(coro)


class _Usuario:
    user_id = "usr_ana"
    email = "ana@example.com"
    role = "user"
    verification_status = "verified"


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"
    role = "super_admin"


BASE = {}

# Un JPEG diminuto como data URL, que es la forma en que el frontend manda el
# comprobante: `FileReader.readAsDataURL`.
COMPROBANTE = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA=="


@pytest.fixture(autouse=True)
def base_limpia():
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    usar_base(base)
    BASE["db"] = base

    async def sembrar():
        await base.bank_accounts.insert_one({
            "bank_id": "bank_ve01", "name": "Banco de Venezuela",
            "currency": "VES", "balance": 1000.0})
        # Un banco en BRL con un nombre parecido: no puede recibir bolivares, y
        # dejarlo entrar seria un asiento contra la cuenta equivocada.
        await base.bank_accounts.insert_one({
            "bank_id": "bank_br01", "name": "Banesco",
            "currency": "BRL", "balance": 0.0})
        await base.rates.insert_one({"ves_to_ris_rate": 140.0,
                                     "updated_at": "2026-01-01T00:00:00Z"})
        await base.users.insert_one({
            "user_id": "usr_ana", "email": "ana@example.com",
            "full_name": "Ana Pérez", "balance_ris": 0.0,
            "verification_status": "verified"})

    corre(sembrar())
    yield base


def crear(**extra):
    """Crea una recarga con el cuerpo que manda la pantalla vigente."""
    cuerpo = {"amount_ves": 14000.0, "payment_method": "transferencia",
              "bank": "banco_venezuela", "voucher_image": COMPROBANTE}
    cuerpo.update(extra)
    return corre(tx.recharge_ves(cuerpo, _Usuario()))


def guardada(transaction_id):
    return corre(BASE["db"].transactions.find_one({"transaction_id": transaction_id}))


# ─── 1. Un test por cada campo que se perdia ──────────────────────────────

def test_la_pantalla_vigente_guarda_el_banco_y_el_comprobante():
    """`RechargeVES.jsx` manda `bank` y `voucher_image`.

    MIRA EL DOCUMENTO, no la respuesta: la ruta contestaba 200 perfecto mientras
    tiraba los dos campos. Un test del 200 es exactamente como esto llego a
    produccion.
    """
    salida = crear()
    doc = guardada(salida["transaction_id"])

    assert doc["destination_bank"] == "banco_venezuela", "se perdió el banco crudo"
    assert doc["destination_bank_id"] == "bank_ve01", "no se resolvió contra contabilidad"
    assert doc["destination_bank_name"] == "Banco de Venezuela"
    assert doc["proof_image"] == COMPROBANTE, "se perdió el comprobante"


def test_los_nombres_nuevos_tambien_se_aceptan():
    """`destination_bank` y `proof_image` son los nombres unificados, y son los
    que el panel ya leia. Los viejos siguen entrando por compatibilidad: hay
    clientes ya cargados en el navegador de la gente."""
    salida = crear(bank=None, voucher_image=None,
                   destination_bank="Banco de Venezuela", proof_image=COMPROBANTE)
    doc = guardada(salida["transaction_id"])
    assert doc["destination_bank_id"] == "bank_ve01"
    assert doc["proof_image"] == COMPROBANTE


def test_el_nombre_comercial_resuelve_igual_que_la_clave():
    """'Banco de Venezuela' y 'banco_venezuela' son el mismo banco. La lista del
    frontend y el nombre que alguien tipeo en contabilidad son dos fuentes
    distintas, y la traducción no puede depender de cómo se escribió cada una."""
    for valor in ("banco_venezuela", "Banco de Venezuela", "BANCO DE VENEZUELA",
                  "banco venezuela"):
        bank_id, _ = corre(tx.resolve_ves_bank(valor))
        assert bank_id == "bank_ve01", f"no resolvió {valor!r}"


# ─── 2. Se rechaza en la creacion, no en la aprobacion ────────────────────

def test_sin_banco_se_rechaza_al_crear():
    """Antes el servidor aceptaba una solicitud que él mismo sabía que no iba a
    poder procesar, y el usuario se enteraba días después, por teléfono.

    MUTACION: sacar la guarda deja pasar la creación y este test se pone en rojo.
    """
    with pytest.raises(HTTPException) as e:
        crear(bank=None)
    assert e.value.status_code == 400
    # El mensaje EXACTO de esta guarda, no uno que contenga «banco»: el del banco
    # irresoluble también lo contiene, y con esa aserción laxa la mutación pasaba
    # —el test daba verde con la guarda sacada, que es exactamente el defecto que
    # este archivo vino a evitar—.
    assert e.value.detail.startswith("Elegí a qué banco"), e.value.detail
    # Y NO quedó nada creado.
    assert corre(BASE["db"].transactions.count_documents({})) == 0


def test_sin_comprobante_se_rechaza_al_crear():
    """El operador acredita dinero MIRÁNDOLO. Una recarga sin comprobante es una
    que alguien va a tener que resolver por teléfono."""
    with pytest.raises(HTTPException) as e:
        crear(voucher_image=None)
    assert e.value.status_code == 400
    assert "comprobante" in e.value.detail.lower()
    assert corre(BASE["db"].transactions.count_documents({})) == 0


def test_un_banco_que_no_esta_en_contabilidad_se_rechaza_y_dice_cuales_hay():
    """No es culpa del usuario: eligió de la lista que le mostramos. Que el error
    nombre los disponibles evita que alguien tenga que adivinar."""
    with pytest.raises(HTTPException) as e:
        crear(bank="banco_que_no_existe")
    assert e.value.status_code == 400
    assert "Banco de Venezuela" in e.value.detail
    assert corre(BASE["db"].transactions.count_documents({})) == 0


def test_un_banco_en_otra_moneda_no_resuelve():
    """Un banco en BRL no puede recibir una transferencia en bolívares. Dejarlo
    entrar sería un asiento contra la cuenta equivocada.

    MUTACION: sacar el filtro `currency: VES` hace que 'banesco' resuelva contra
    el banco en reales y este test se pone en rojo.
    """
    bank_id, _ = corre(tx.resolve_ves_bank("banesco"))
    assert bank_id is None


def test_el_bank_id_crudo_de_un_banco_en_otra_moneda_tampoco_resuelve():
    """La misma regla, por la otra puerta.

    `resolve_ves_bank` acepta un `bank_id` explicito, y esa rama corta antes de
    llegar al filtro por moneda. Un usuario que mande el bank_id de una cuenta
    en reales como `destination_bank` conseguiria que la aprobacion le sume
    bolivares a una cuenta en reales: el aprobador comprueba que el banco
    exista, no en que moneda esta.

    MUTACION: sacar `"currency": "VES"` del find_one de la rama directa y este
    test se pone en rojo.
    """
    bank_id, doc = corre(tx.resolve_ves_bank("bank_br01"))
    assert bank_id is None and doc is None

    # Y por la ruta de creacion, que es de donde puede venir un valor elegido
    # por el usuario, no se acepta.
    with pytest.raises(HTTPException) as e:
        crear(bank="bank_br01")
    assert e.value.status_code == 400
    assert corre(BASE["db"].transactions.count_documents({})) == 0


def test_dos_bancos_que_colapsan_al_mismo_nombre_no_se_desempatan_solos():
    """Con dos candidatos no hay respuesta, hay un empate — y un empate lo rompe
    una persona. Elegir «el más parecido» sería acreditar plata contra una cuenta
    que nadie eligió."""
    async def caso():
        await BASE["db"].bank_accounts.insert_one({
            "bank_id": "bank_ve02", "name": "Banco Venezuela",
            "currency": "VES", "balance": 0.0})
        return await tx.resolve_ves_bank("banco_venezuela")

    bank_id, doc = corre(caso())
    assert bank_id is None and doc is None


# ─── 3. El circuito entero: crear -> aprobar -> sube el saldo ─────────────

def test_crear_y_aprobar_acredita_el_saldo_contra_el_banco_correcto():
    """Lo que el defecto impedía: que una recarga se pudiera aprobar."""
    salida = crear()
    tx_id = salida["transaction_id"]

    resultado = corre(adm.process_ves_recharge(tx_id, {"action": "approve"}, _Admin()))
    assert "error" not in str(resultado).lower()

    # El saldo del usuario subió por el RIS que calculó el SERVIDOR.
    usuario = corre(BASE["db"].users.find_one({"user_id": "usr_ana"}))
    from services.money import from_db, to_float
    assert to_float(from_db(usuario["balance_ris"])) == pytest.approx(100.0)

    # El banco recibió los bolívares.
    #
    # Se lee con `from_db` y no comparando el valor crudo: el saldo bancario se
    # guarda en `Decimal128` —lo escribe `services/bancos.py`, para que sumar
    # centavos no derive— y `Decimal128('15000.00') == 15000.0` es falso aunque
    # el monto sea exacto. Afirmar sobre el tipo guardado en vez de sobre el
    # monto ata el test a un detalle de almacenamiento.
    banco = corre(BASE["db"].bank_accounts.find_one({"bank_id": "bank_ve01"}))
    from services.money import from_db as _from_db
    assert _from_db(banco["balance"]) == Decimal("15000.00")

    # Y quedó el asiento, contra el banco correcto.
    asiento = corre(BASE["db"].bank_ledger.find_one({"reference": tx_id}))
    assert asiento is not None, "no quedó asiento en bank_ledger"
    assert asiento["bank_id"] == "bank_ve01"
    assert asiento["amount"] == pytest.approx(14000.0)

    doc = guardada(tx_id)
    assert doc["status"] == "approved"


def test_la_aprobacion_ya_no_devuelve_el_400_que_culpaba_al_usuario():
    """El síntoma que se reportó. Con el banco guardado, deja de aparecer.

    MUTACION: dejar de escribir `destination_bank_id` en la creación devuelve el
    400 y este test se pone en rojo.
    """
    salida = crear()
    resultado = corre(adm.process_ves_recharge(
        salida["transaction_id"], {"action": "approve"}, _Admin()))
    assert guardada(salida["transaction_id"])["status"] == "approved"
    assert resultado is not None


# ─── 4. La rama de F4, que nadie ejecutaba nunca ──────────────────────────

def test_la_rama_de_destination_bank_se_ejecuta_de_verdad():
    """La bomba desarmada.

    `routes/admin.py` importaba `resolve_ves_bank` de `routes.transactions` y esa
    función NO EXISTÍA. La rama solo corre cuando la recarga tiene
    `destination_bank` y NO tiene `destination_bank_id` — o sea, exactamente lo
    que pasa con las recargas viejas. Nadie la ejecutaba porque nadie escribía
    `destination_bank`, así que el ImportError llevaba ahí sin que nadie lo note.

    Este test crea a mano una recarga con esa forma —la de las que ya están en
    producción— y la aprueba. Si la función no existiera, esto revienta.
    """
    async def vieja():
        await BASE["db"].transactions.insert_one({
            "transaction_id": "rech_vieja01", "user_id": "usr_ana",
            "type": "recharge_ves", "amount_ves": 14000.0, "amount_ris": 100.0,
            "status": "pending",
            # Con el crudo y SIN el resuelto: la forma que dispara la rama.
            "destination_bank": "banco_venezuela",
        })
        return await adm.process_ves_recharge(
            "rech_vieja01", {"action": "approve"}, _Admin())

    corre(vieja())
    doc = guardada("rech_vieja01")
    assert doc["status"] == "approved"
    assert doc["destination_bank_id"] == "bank_ve01", "la rama no resolvió el banco"


def test_una_recarga_vieja_sin_banco_se_puede_destrabar_a_mano():
    """La red que el aprobador ya aceptaba y que el panel no tenía cómo usar.

    Hay recargas pendientes en producción sin banco: nacieron rotas y el arreglo
    de la creación no las alcanza. Las resuelve una persona, mirando el
    comprobante, pasando el `bank_id` en el cuerpo.
    """
    async def huerfana():
        await BASE["db"].transactions.insert_one({
            "transaction_id": "rech_huerfana", "user_id": "usr_ana",
            "type": "recharge_ves", "amount_ves": 14000.0, "amount_ris": 100.0,
            "status": "pending"})
        return await adm.process_ves_recharge(
            "rech_huerfana", {"action": "approve", "bank_id": "bank_ve01"}, _Admin())

    corre(huerfana())
    doc = guardada("rech_huerfana")
    assert doc["status"] == "approved"
    assert doc["destination_bank_id"] == "bank_ve01"


def test_sin_banco_y_sin_eleccion_manual_la_aprobacion_sigue_frenando():
    """La guarda del aprobador NO se toca: es lo único que evitó que se
    acreditara plata contra un banco desconocido."""
    async def huerfana():
        await BASE["db"].transactions.insert_one({
            "transaction_id": "rech_sinbanco", "user_id": "usr_ana",
            "type": "recharge_ves", "amount_ves": 14000.0, "amount_ris": 100.0,
            "status": "pending"})
        return await adm.process_ves_recharge(
            "rech_sinbanco", {"action": "approve"}, _Admin())

    with pytest.raises(HTTPException) as e:
        corre(huerfana())
    assert e.value.status_code == 400
    # Y el saldo no se movió.
    usuario = corre(BASE["db"].users.find_one({"user_id": "usr_ana"}))
    from services.money import from_db, to_float
    assert to_float(from_db(usuario["balance_ris"])) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# El script de diagnostico: que siga siendo de SOLO LECTURA.
# ---------------------------------------------------------------------------

# Todo lo que en la API de Motor/PyMongo toca el disco. Si alguien agrega una
# de estas al script, este test se pone en rojo: el encargo dice que sobre plata
# de terceros no se escribe sin que una persona lo dispare a mano, y un script
# que hoy solo cuenta es exactamente al que manana alguien le agrega un $set
# "para destrabar las pendientes de una".
ESCRITURAS_DE_MONGO = {
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "bulk_write", "find_one_and_update",
    "find_one_and_replace", "find_one_and_delete", "drop", "drop_database",
    "create_index", "create_indexes", "drop_index", "drop_indexes",
    "rename", "save", "remove", "aggregate",
}

_SCRIPT = os.path.join(_BACKEND, "migrations", "backfill_recargas_ves_sin_banco.py")


def test_el_script_de_diagnostico_no_tiene_una_sola_escritura():
    """El docstring del script promete que no escribe nada. Esto lo verifica
    sobre el arbol sintactico, no sobre la buena fe de quien lo lea.

    `aggregate` esta en la lista negra a proposito: un pipeline con `$merge` o
    `$out` escribe, y desde afuera no se distingue del que solo cuenta.
    """
    import ast

    with open(_SCRIPT, encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename=_SCRIPT)

    encontradas = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr in ESCRITURAS_DE_MONGO:
                encontradas.append(f"linea {nodo.lineno}: .{nodo.func.attr}(")

    assert not encontradas, (
        "El script de diagnostico dejo de ser de solo lectura:\n  "
        + "\n  ".join(encontradas)
        + "\nSi la escritura es intencional, cambiale el nombre al script, "
        "sacale la promesa al docstring y avisale a quien lo va a correr."
    )


def test_el_script_de_diagnostico_compila_y_cuenta_lo_que_dice_contar():
    """Que el archivo sea sintacticamente valido y que las consultas que hace
    sean las que el PR va a citar. Un script de diagnostico que nadie corrio
    puede estar roto y nadie se entera hasta el dia que hace falta."""
    with open(_SCRIPT, encoding="utf-8") as f:
        fuente = f.read()
    compile(fuente, _SCRIPT, "exec")
    # Las cuatro cuentas del PR salen de aca; si alguien renombra un campo, que
    # se note al correr los tests y no al leer el numero equivocado.
    assert '"type": "recharge_ves", "status": "pending"' in fuente
    assert "destination_bank_id" in fuente
    assert "proof_image" in fuente
