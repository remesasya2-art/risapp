"""
tests/test_saldo_y_libro_juntos.py — El saldo del cliente y su línea del libro
se escriben juntos cuando el Mongo tiene transacciones.

POR QUE ESTE ARCHIVO EXISTE

    `saldos.mover` hacía dos escrituras: el `$inc` del saldo y la línea del
    libro. Si la segunda fallaba, la plata ya se había movido y el libro
    quedaba sin su línea —con un grito en Errores, pero descuadrado—. Con
    transacciones, las dos van juntas: o quedan las dos, o ninguna.

    Lo que importa acá sólo se ve contra un Mongo de verdad: con mongomock no
    hay transacciones. CI corre este archivo contra uno con réplicas (ver
    `tests/_mongo_de_verdad.py`). Los tests que no dependen de transacciones
    corren también sobre mongomock.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

from conftest import ensenarle_decimal128_a_mongomock                 # noqa: E402
ensenarle_decimal128_a_mongomock()

from _mongo_de_verdad import MONGO_DE_VERDAD, base_para, corre       # noqa: E402
from services import saldos, transacciones                           # noqa: E402
from services.money import from_db, to_decimal128                    # noqa: E402

solo_con_transacciones = pytest.mark.skipif(
    not MONGO_DE_VERDAD, reason="sin RIS_MONGO_DE_VERDAD no hay transacciones (mongomock no las tiene)")

# Un validador que ninguna línea del libro cumple: la manera de que el asiento
# falle de verdad, en el servidor, y no con un doble que lo simula.
LIBRO_QUE_RECHAZA_TODO = {"$jsonSchema": {"required": ["campo_que_ninguna_linea_tiene"]}}


@pytest.fixture
def base(monkeypatch):
    yield from base_para(monkeypatch, "ris_saldo_y_libro")


def _cliente(base, saldo="100.00", terceros="0.00"):
    corre(base.users.insert_one({
        "user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente", "role": "user",
        "balance_ris": to_decimal128(saldo), "balance_ris_terceros": to_decimal128(terceros)}))


def _saldo(base, cuenta="balance_ris"):
    return from_db(corre(base.users.find_one({"user_id": "u_1"}))[cuenta])


def _lineas(base):
    return corre(base.ledger.find({"user_id": "u_1"}).to_list(100))


def test_UN_CREDITO_DEJA_EL_SALDO_Y_SU_LINEA_CUADRANDO(base):
    _cliente(base)
    r = corre(saldos.mover(base, "u_1", "25.50", movimiento="recarga_pix"))
    assert _saldo(base) == Decimal("125.50")
    (linea,) = _lineas(base)
    assert linea["entry_id"] == r["entry_id"]
    assert from_db(linea["balance_before"]) == Decimal("100.00")
    assert from_db(linea["balance_after"]) == Decimal("125.50")


def test_UN_TRASPASO_MUEVE_LAS_DOS_CUENTAS_Y_DEJA_SUS_DOS_LINEAS(base):
    _cliente(base)
    corre(saldos.transferir(base, "u_1", "40.00", de="balance_ris", a="balance_ris_terceros"))
    assert _saldo(base) == Decimal("60.00") and _saldo(base, "balance_ris_terceros") == Decimal("40.00")
    assert sorted(linea["direction"] for linea in _lineas(base)) == ["credit", "debit"]


def test_SIN_SALDO_NO_SE_ESCRIBE_NADA(base):
    _cliente(base)
    with pytest.raises(saldos.SaldoInsuficiente):
        corre(saldos.mover(base, "u_1", "-500.00", movimiento="envio_ves", exigir_saldo=True))
    assert _saldo(base) == Decimal("100.00") and _lineas(base) == []


@solo_con_transacciones
def test_CON_UN_MONGO_DE_VERDAD_HAY_TRANSACCIONES(base):
    """Si el Mongo de CI arrancara como nodo suelto, los de abajo pasarían por
    el camino sin transacciones y el archivo no probaría nada."""
    assert corre(transacciones.hay_transacciones()) is True


@solo_con_transacciones
def test_SI_LA_LINEA_NO_SE_PUEDE_ESCRIBIR_LA_PLATA_NO_SE_MUEVE(base):
    _cliente(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(saldos.mover(base, "u_1", "25.50", movimiento="recarga_pix"))
    assert _saldo(base) == Decimal("100.00"), "el saldo se movió sin su línea"
    assert _lineas(base) == []


@solo_con_transacciones
def test_UN_ERROR_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_EL_MOVIMIENTO(base):
    """Si la línea no se puede ni armar —acá, un dato que no se puede guardar—
    el error ocurre antes de que el servidor la vea, y el servidor no aborta
    nada por su cuenta. Lo que deshace el movimiento es que el libro deje
    salir el error; si se lo tragara, la transacción confirmaría el saldo
    movido sin su línea."""
    _cliente(base)
    with pytest.raises(Exception):
        corre(saldos.mover(base, "u_1", "25.50", movimiento="recarga_pix",
                           metadata={"no_se_puede_guardar": object()}))
    assert _saldo(base) == Decimal("100.00"), "el saldo se movió sin su línea"
    assert _lineas(base) == []


@solo_con_transacciones
def test_EL_TRASPASO_Y_SUS_DOS_LINEAS_VAN_JUNTOS(base):
    _cliente(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(Exception):
        corre(saldos.transferir(base, "u_1", "40.00", de="balance_ris", a="balance_ris_terceros"))
    assert _saldo(base) == Decimal("100.00") and _saldo(base, "balance_ris_terceros") == Decimal("0.00")


@solo_con_transacciones
def test_VEINTE_PAGOS_A_LA_VEZ_AL_MISMO_CLIENTE_NO_SE_PIERDE_NINGUNO(base):
    """Con transacciones, dos pagos simultáneos al mismo usuario chocan y el
    segundo se reintenta. Si el reintento no estuviera, alguno de estos
    terminaría en error; si se perdiera una escritura, el saldo no daría."""
    _cliente(base)

    async def veinte():
        await asyncio.gather(*[saldos.mover(base, "u_1", "1.00", movimiento="recarga_pix")
                               for _ in range(20)])
    corre(veinte())
    assert _saldo(base) == Decimal("120.00")
    despues = sorted(from_db(linea["balance_after"]) for linea in _lineas(base))
    assert despues == [Decimal(100 + i) for i in range(1, 21)], "cada línea tiene que decir el saldo que dejó"


@solo_con_transacciones
def test_SIN_TRANSACCIONES_ES_LO_DE_SIEMPRE(base, monkeypatch):
    """Con un Mongo de un solo nodo —el de producción hasta que tenga
    réplicas— la plata se mueve igual y la línea que falta queda gritada."""
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", False)
    _cliente(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    r = corre(saldos.mover(base, "u_1", "25.50", movimiento="recarga_pix"))
    assert _saldo(base) == Decimal("125.50") and r["entry_id"] is None
