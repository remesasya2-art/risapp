"""
tests/test_libro_mayor_no_se_edita.py — El libro mayor sólo crece.

QUE PROTEGE

    El libro mayor es la historia auditable del saldo: cada movimiento deja una
    línea con quién, cuánto, saldo antes y saldo después. Su valor entero
    depende de UNA propiedad: que una línea escrita no se pueda cambiar ni
    borrar.

    Esa propiedad no la garantiza la base —Mongo deja actualizar cualquier
    documento— sino el módulo: `services/ledger.py` no ofrece ninguna función
    para modificar ni borrar una línea. Es una garantía por ausencia, y las
    garantías por ausencia son las que se pierden sin que nadie lo note: basta
    que alguien agregue un `corregir_entrada()` "para arreglar un typo" y el
    libro deja de servir como prueba.

    Acá se fija eso, más las tres cosas que hacen que una línea sirva sola:
    que guarde el estado antes y después, que guarde a QUIÉN además de su id, y
    que registrar nunca tumbe la operación que está auditando.

    Es una de las afirmaciones del dossier técnico de seguridad, y hasta ahora
    era la única sin prueba propia.
"""
import asyncio
import inspect
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import ledger                                        # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["libro"]
    usar_base(b)
    ledger._indexes_ready = False
    corre(b.users.insert_one({
        "user_id": "u_1", "email": "cliente@correo.com",
        "full_name": "Cliente Uno", "role": "user",
    }))
    yield b
    # El flag es del módulo, no de la base: si queda encendido, el archivo de
    # test que corra después se salta la creación de índices sin saberlo.
    ledger._indexes_ready = False


def _asentar(**extra):
    datos = dict(
        user_id="u_1", movement_type="recarga_pix", amount=100,
        direction="credit", balance_before=0, balance_after=100,
        actor_type="admin", actor_id="a_1", actor_email="operador@correo.com",
    )
    datos.update(extra)
    return corre(ledger.record_ris_entry(**datos))


# ─── La garantía por ausencia ─────────────────────────────────────────────

def test_el_modulo_no_ofrece_forma_de_editar_ni_borrar():
    """Si alguien agrega una función para tocar una línea, esto se pone rojo.

    Se recorren las funciones públicas del módulo y se rechaza cualquier verbo
    de modificación. No se busca un nombre concreto: se busca la intención.
    """
    prohibidos = (
        "update", "edit", "modify", "delete", "remove", "drop", "fix",
        "actualizar", "editar", "modificar", "borrar", "eliminar", "corregir",
        "anular", "rectificar",
    )
    publicas = [
        n for n, _ in inspect.getmembers(ledger, inspect.isfunction)
        if not n.startswith("_") and _.__module__ == ledger.__name__
    ]
    assert publicas, "no se encontró ninguna función pública: la prueba no está mirando el módulo"

    for nombre in publicas:
        for verbo in prohibidos:
            assert verbo not in nombre.lower(), (
                f"`ledger.{nombre}` parece modificar el libro. El libro mayor se "
                f"escribe y no se toca: un asiento equivocado se corrige con OTRO "
                f"asiento, no editando el anterior.")


def test_el_codigo_del_modulo_no_actualiza_ni_borra_la_coleccion():
    """Y tampoco por la puerta de atrás, escribiendo directo contra Mongo."""
    fuente = inspect.getsource(ledger)
    sin_comentarios = "\n".join(
        l for l in fuente.splitlines() if not l.strip().startswith("#"))
    for operacion in ("update_one", "update_many", "delete_one", "delete_many",
                      "find_one_and_update", "find_one_and_delete", "replace_one"):
        assert operacion not in sin_comentarios, (
            f"`services/ledger.py` usa `{operacion}`. El libro sólo admite inserciones.")


# ─── Lo que hace que una línea sirva sola ─────────────────────────────────

def test_la_linea_guarda_el_saldo_antes_y_despues(base):
    _asentar()
    linea = corre(base[ledger.LEDGER_COLLECTION].find_one({"user_id": "u_1"}))
    assert linea["balance_before"] == 0
    assert linea["balance_after"] == 100
    assert linea["signed_amount"] == 100


def test_un_debito_queda_con_signo_negativo(base):
    _asentar(direction="debit", amount=40, balance_before=100, balance_after=60)
    linea = corre(base[ledger.LEDGER_COLLECTION].find_one({"user_id": "u_1"}))
    assert linea["amount"] == 40, "el monto se guarda siempre positivo"
    assert linea["signed_amount"] == -40, "y el signo lo pone la dirección"


def test_la_linea_dice_quien_fue_y_no_solo_su_id(base):
    """Dentro de un año ese usuario puede no existir, y la línea tiene que
    seguir diciendo de quién se trataba."""
    _asentar()
    linea = corre(base[ledger.LEDGER_COLLECTION].find_one({"user_id": "u_1"}))
    assert linea["user_email"] == "cliente@correo.com"
    assert linea["user_name"] == "Cliente Uno"
    assert linea["actor"]["email"] == "operador@correo.com"
    assert linea["actor"]["type"] == "admin"


def test_cada_linea_tiene_identidad_y_fecha_propias(base):
    primero = _asentar()
    segundo = _asentar()
    assert primero and segundo and primero != segundo
    lineas = corre(base[ledger.LEDGER_COLLECTION].find({"user_id": "u_1"}).to_list(10))
    assert len(lineas) == 2, "el segundo asiento pisó al primero"
    assert all(l.get("created_at") for l in lineas)


# ─── Registrar nunca puede tumbar la operación ────────────────────────────

class _ColeccionCaida:
    async def insert_one(self, *a, **k):
        raise RuntimeError("Mongo caído")


class _BaseCaida:
    def __getitem__(self, _nombre):
        return _ColeccionCaida()


def test_si_el_libro_falla_la_operacion_sigue(base, monkeypatch, caplog):
    """Un libro que tumba una acreditación legítima es peor que un libro con
    un hueco anotado. Devuelve None y deja el ERROR en el registro."""
    import logging

    ledger._indexes_ready = True                 # el fallo va a ser el insert
    monkeypatch.setattr(ledger, "db", _BaseCaida())

    with caplog.at_level(logging.ERROR, logger=ledger.__name__):
        # `user_snapshot` explícito: sin él iría a buscar el usuario a la base
        # caída y el fallo sería otro.
        resultado = _asentar(user_snapshot={
            "email": "cliente@correo.com", "name": "Cliente Uno", "role": "user"})

    assert resultado is None, "un fallo al asentar no puede propagarse"
    assert any("ledger" in r.message.lower() or "Mongo caído" in r.message
               for r in caplog.records), "el fallo tiene que quedar registrado"


def test_el_asiento_devuelve_su_identificador(base):
    entry_id = _asentar()
    assert entry_id and entry_id.startswith("le_")
    assert corre(base[ledger.LEDGER_COLLECTION].find_one({"entry_id": entry_id}))
