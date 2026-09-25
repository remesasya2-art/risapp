"""
tests/test_las_encomiendas_cobran_en_una_transaccion.py — El cobro y la
devolución de una encomienda van en una sola transacción cuando el Mongo la
tiene.

Ver `services/envios_cobros_juntos.py`. Sin réplicas, cobrar son escrituras
separadas —el débito, la línea del libro, el marcado— con una devolución si
el marcado falla; con réplicas, van juntas. Lo que importa sólo se ve contra
un Mongo de verdad; CI corre este archivo contra uno con réplicas. Los casos
que no dependen de transacciones corren también sobre mongomock, y prueban
que el camino de un solo nodo sigue siendo el de siempre.
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

from conftest import ensenarle_decimal128_a_mongomock                 # noqa: E402
ensenarle_decimal128_a_mongomock()

from _mongo_de_verdad import MONGO_DE_VERDAD, base_para, corre       # noqa: E402
from services import envios_cobros, envios_cobros_juntos             # noqa: E402
from services.money import from_db, to_decimal128                    # noqa: E402

solo_con_transacciones = pytest.mark.skipif(
    not MONGO_DE_VERDAD, reason="sin RIS_MONGO_DE_VERDAD no hay transacciones (mongomock no las tiene)")

LIBRO_QUE_RECHAZA_TODO = {"$jsonSchema": {"required": ["campo_que_ninguna_linea_tiene"]}}
AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def base(monkeypatch):
    yield from base_para(monkeypatch, "ris_encomiendas_juntas")


def _preparar(base, saldo="100.00", cobros=None):
    corre(base.users.insert_one({"user_id": "u_1", "email": "cliente@ejemplo.test", "name": "Cliente",
                                 "role": "user", "balance_ris": to_decimal128(saldo)}))
    corre(base.envios.insert_one({
        "envio_id": "env_1", "display_id": "E000001", "user_id": "u_1", "estado": "en_transito_origen",
        "cotizacion": {"tarifa_version": "tar_1"},
        "cobros": cobros or {"inicial": None, "ajuste": None,
                             "reembolsado_ris": "0.00", "total_cobrado_ris": "0.00"}}))


def _envio(base):
    return corre(base.envios.find_one({"envio_id": "env_1"}, {"_id": 0}))


def _saldo(base):
    return from_db(corre(base.users.find_one({"user_id": "u_1"}))["balance_ris"])


def _lineas(base):
    return corre(base.ledger.find({"reference.id": "env_1"}).to_list(10))


def _cobrar(base, monto="30.00"):
    return envios_cobros.cobrar(_envio(base), "inicial", monto, db=base, ahora=AHORA)


def _el_libro_no_se_puede_armar(monkeypatch):
    """Un error de este lado: la línea ni llega a la base. El servidor no se
    entera y no aborta nada por su cuenta; lo único que deshace el débito es
    que el error salga del `try` del libro."""
    from services import ledger

    def no_se_puede(*a, **k):
        raise ValueError("la línea no se pudo armar")
    monkeypatch.setattr(ledger, "quantize_money", no_se_puede)


# ══════════════════════════════════════════════════════════════════════════
# Cobrar
# ══════════════════════════════════════════════════════════════════════════

def test_COBRAR_DESCUENTA_ASIENTA_Y_MARCA_PAGADA(base):
    _preparar(base)
    r = corre(_cobrar(base))
    assert r["estado"] == "pagado" and r["saldo_restante"] == "70.00"
    assert _saldo(base) == Decimal("70.00")
    envio = _envio(base)
    assert envio["cobros"]["inicial"]["estado"] == "pagado"
    assert envio["cobros"]["total_cobrado_ris"] == "30.00"
    (linea,) = _lineas(base)
    assert linea["movement_type"] == envios_cobros.MOVIMIENTO_COBRO
    assert linea["metadata"]["intento_id"] == envio["cobros"]["inicial"]["intento_id"]


def test_COBRAR_SIN_SALDO_QUEDA_PENDIENTE_Y_SUELTA_LA_RESERVA(base):
    _preparar(base, saldo="10.00")
    r = corre(_cobrar(base))
    assert r["estado"] == "pendiente" and r["motivo"] == "saldo"
    assert _saldo(base) == Decimal("10.00") and _lineas(base) == []
    assert _envio(base)["cobros"]["inicial"]["estado"] == "pendiente"


@solo_con_transacciones
def test_COBRAR_SI_LA_LINEA_FALLA_NI_DEBITO_NI_MARCA(base):
    """Sin transacciones, el libro no interrumpía el cobro: la plata salía y la
    partida quedaba pagada sin la línea que es la evidencia del débito."""
    _preparar(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    r = corre(_cobrar(base))
    assert r["estado"] == "pendiente" and r["motivo"] == "error"
    assert _saldo(base) == Decimal("100.00"), "se descontó sin su línea"
    assert _envio(base)["cobros"]["inicial"]["estado"] == "pendiente", "la reserva quedó trabada"


@solo_con_transacciones
def test_COBRAR_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    _el_libro_no_se_puede_armar(monkeypatch)
    _preparar(base)
    r = corre(_cobrar(base))
    assert r["estado"] == "pendiente" and r["motivo"] == "error"
    assert _saldo(base) == Decimal("100.00") and _lineas(base) == []
    assert _envio(base)["cobros"]["inicial"]["estado"] == "pendiente"


@solo_con_transacciones
def test_COBRAR_SI_LA_RESERVA_YA_NO_ES_DE_ESTE_INTENTO_NO_QUEDA_NI_DEBITO_NI_LINEA(base):
    """La reserva la tiene otro intento —la de éste venció y alguien la
    resolvió—. El marcado no la encuentra, y el débito y la línea que ya se
    escribieron adentro de la transacción tienen que irse con ella."""
    _preparar(base, cobros={"inicial": {"monto_ris": "30.00", "estado": "pagando",
                                        "intento_id": "int_otro", "reservado_at": AHORA},
                            "ajuste": None})
    corre(envios_cobros_juntos.pagar_reservada(
        base, _envio(base), "inicial", Decimal("30.00"), "int_este", AHORA, "system", None))
    assert _saldo(base) == Decimal("100.00"), "se descontó un cobro que no quedó marcado"
    assert _lineas(base) == []


@solo_con_transacciones
def test_COBRAR_SI_SE_CONFIRMO_PERO_LA_RESPUESTA_NO_LLEGO_CONTESTA_PAGADO(base, monkeypatch):
    """La confirmación llega al Mongo y la respuesta se pierde en el camino.
    El cobro ocurrió: contestar «pendiente» invita a pagarlo otra vez."""
    from pymongo.errors import PyMongoError
    from services import transacciones
    original = transacciones.en_una_transaccion

    async def confirma_y_se_corta(trabajo):
        await original(trabajo)
        raise PyMongoError("se cortó la respuesta de la confirmación")
    monkeypatch.setattr(transacciones, "en_una_transaccion", confirma_y_se_corta)
    _preparar(base)
    r = corre(_cobrar(base))
    assert r["estado"] == "pagado"
    assert _saldo(base) == Decimal("70.00") and len(_lineas(base)) == 1
    assert _envio(base)["cobros"]["inicial"]["estado"] == "pagado"


# ══════════════════════════════════════════════════════════════════════════
# Devolver
# ══════════════════════════════════════════════════════════════════════════

def _devolver(base, monto="6.70"):
    return envios_cobros.devolver(_envio(base), monto, db=base, ahora=AHORA)


def test_DEVOLVER_ACREDITA_ASIENTA_Y_CIERRA(base):
    _preparar(base)
    r = corre(_devolver(base))
    assert r["estado"] == "acreditado" and r["saldo_restante"] == "106.70"
    assert _saldo(base) == Decimal("106.70")
    cobros = _envio(base)["cobros"]
    assert cobros["devolucion"]["estado"] == "acreditado" and cobros["reembolsado_ris"] == "6.70"
    (linea,) = _lineas(base)
    assert linea["movement_type"] == envios_cobros.MOVIMIENTO_REEMBOLSO


def test_DEVOLVER_DOS_VECES_ACREDITA_UNA(base):
    _preparar(base)
    corre(_devolver(base))
    r = corre(_devolver(base))
    assert r["estado"] == "acreditado" and r["entry_id"] is None
    assert _saldo(base) == Decimal("106.70") and len(_lineas(base)) == 1


@solo_con_transacciones
def test_DEVOLVER_SI_LA_LINEA_FALLA_NI_CREDITO_NI_MARCA_Y_SE_PUEDE_REINTENTAR(base):
    """Sin transacciones, la plata quedaba acreditada sin su línea."""
    _preparar(base)
    corre(base.create_collection("ledger", validator=LIBRO_QUE_RECHAZA_TODO))
    with pytest.raises(envios_cobros.CobroImposible):
        corre(_devolver(base))
    assert _saldo(base) == Decimal("100.00"), "se acreditó sin su línea"
    assert _envio(base)["cobros"].get("devolucion") is None, "la marca impide reintentar"


@solo_con_transacciones
def test_DEVOLVER_UN_ERROR_DEL_LIBRO_ANTES_DE_LLEGAR_A_LA_BASE_TAMBIEN_DESHACE_TODO(base, monkeypatch):
    _el_libro_no_se_puede_armar(monkeypatch)
    _preparar(base)
    with pytest.raises(envios_cobros.CobroImposible):
        corre(_devolver(base))
    assert _saldo(base) == Decimal("100.00") and _envio(base)["cobros"].get("devolucion") is None


@solo_con_transacciones
def test_DEVOLVER_SI_ALGO_FALLA_DESPUES_DE_LA_LINEA_LA_LINEA_TAMBIEN_SE_VA(base, monkeypatch):
    """La línea es lo último que se escribe: sólo se ve que va adentro de la
    transacción si algo falla después de ella. Escrita afuera, quedaría una
    devolución en el libro que nunca llegó al saldo."""
    from services import ledger
    original = ledger.record_ris_entry

    async def escribe_y_se_corta(*a, **k):
        await original(*a, **k)
        raise RuntimeError("se cortó después de la línea")
    monkeypatch.setattr(ledger, "record_ris_entry", escribe_y_se_corta)
    _preparar(base)
    with pytest.raises(envios_cobros.CobroImposible):
        corre(_devolver(base))
    assert _lineas(base) == [] and _saldo(base) == Decimal("100.00")
