"""
tests/test_la_billetera_btc_se_calcula.py — La billetera BTC-VES que ve el
cliente son los bolívares en camino: las órdenes pagadas con Bitcoin que
todavía no se le enviaron al beneficiario.

Antes se mostraba `btc_ves_wallets.saldo`, un contador que el aviso de Blink
sumaba al cobrar y que marcar la orden como enviada desde el panel no
descontaba. El número sólo crecía, y mostraba como «disponibles» bolívares
ya entregados.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

from conftest import ensenarle_decimal128_a_mongomock, usar_base      # noqa: E402
ensenarle_decimal128_a_mongomock()

from models.user import User                                         # noqa: E402

CLIENTE = User(user_id="u_1", name="Cliente", email="cliente@ejemplo.test", role="user")
OTRO = User(user_id="u_2", name="Otro", email="otro@ejemplo.test", role="user")


@pytest.fixture
def base():
    import mongomock_motor
    b = mongomock_motor.AsyncMongoMockClient()["ris_billetera_btc"]
    usar_base(b)
    return b


def corre(coro):
    return asyncio.run(coro)


def _orden(base, remesa_id, ves, estado="pagado", user_id="u_1", pagado_en=None):
    corre(base.btc_remesas.insert_one({
        "remesa_id": remesa_id, "user_id": user_id, "estado": estado, "ves_recibe": ves,
        "pagado_en": pagado_en or datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)}))


def _billetera(usuario=CLIENTE):
    from routes import btc_lightning
    return corre(btc_lightning.get_btc_wallet(current_user=usuario))


def test_SIN_ORDENES_ES_CERO(base):
    assert _billetera()["saldo"] == 0.0


def test_SUMA_SOLO_LO_PAGADO_Y_TODAVIA_NO_ENVIADO(base):
    _orden(base, "r_1", 1000.0)
    _orden(base, "r_2", 250.5)
    _orden(base, "r_3", 700.0, estado="enviado")
    _orden(base, "r_4", 300.0, estado="pendiente")
    _orden(base, "r_5", 400.0, estado="revision_manual")
    _orden(base, "r_6", 500.0, estado="cancelado")
    assert _billetera()["saldo"] == 1250.5


def test_EL_CONTADOR_VIEJO_NO_SE_MUESTRA(base):
    """El contador acumulado de más —bolívares ya enviados— no cuenta."""
    corre(base.btc_ves_wallets.insert_one({"user_id": "u_1", "saldo": 99999.0, "moneda": "BTC-VES"}))
    _orden(base, "r_1", 1000.0)
    assert _billetera()["saldo"] == 1000.0


def test_AL_MARCAR_ENVIADO_DESDE_EL_PANEL_BAJA(base):
    """El defecto de origen: el panel marcaba la orden enviada y el número
    que veía el cliente no bajaba."""
    from routes import btc_admin
    _orden(base, "r_1", 1000.0)
    _orden(base, "r_2", 200.0)
    corre(btc_admin.completar_remesa_btc("r_1", via="panel", operador_id="adm_1"))
    assert _billetera()["saldo"] == 200.0


def test_LEE_LOS_MONTOS_GUARDADOS_EN_DECIMAL128(base):
    """Hoy `ves_recibe` se guarda como `float`, pero la regla del proyecto es
    guardar la plata en `Decimal128`. El día que las órdenes se guarden así,
    sumar con `float()` revienta con TypeError; `to_decimal` lee los dos."""
    from services.money import to_decimal128
    _orden(base, "r_1", to_decimal128("1000.10"))
    _orden(base, "r_2", 250.25)
    assert _billetera()["saldo"] == 1250.35


def test_NO_SUMA_LAS_ORDENES_DE_OTRO(base):
    _orden(base, "r_1", 1000.0, user_id="u_2")
    assert _billetera()["saldo"] == 0.0
    assert _billetera(OTRO)["saldo"] == 1000.0


def test_LA_FECHA_ES_LA_DEL_ULTIMO_PAGO_EN_CAMINO(base):
    _orden(base, "r_1", 10.0, pagado_en=datetime(2026, 9, 20, tzinfo=timezone.utc))
    _orden(base, "r_2", 10.0, pagado_en=datetime(2026, 9, 24, tzinfo=timezone.utc))
    assert _billetera()["actualizado_en"].day == 24
