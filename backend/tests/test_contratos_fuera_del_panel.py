"""
tests/test_contratos_fuera_del_panel.py — Las últimas rutas de datos que no
tenían contrato: la cola de pagos, el registro de accesos al panel, la marca
de enviado del operador de Bitcoin y las tres del PIX de la recarga. Ver
models/fuera_del_panel.py.

Dos guardas: la lectura del código de lo que arma cada ruta (ve también las
ramas que los datos no recorren), y por HTTP con datos, la misma respuesta que
la función llamada a mano.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves                     # noqa: E402
from test_contratos_de_encomiendas import _campos                # noqa: E402
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta    # noqa: E402

PIX = "routes/gestor_pix.py"
# (archivo, método, camino, contrato)
RUTAS = [
    ("routes/basic.py", "GET", "/withdrawal/queue-stats", "ColaDePagos"),
    ("routes/security_2fa.py", "GET", "/admin-access-log", "RegistroDeAccesos"),
    ("routes/btc_lightning.py", "POST", "/operador/marcar-enviado", "EnvioMarcadoPorElOperador"),
    (PIX, "POST", "/create", "PixCreado"),
    (PIX, "POST", "/cancel/{payment_id}", "PixCancelado"),
    (PIX, "POST", "/simulate-payment/{payment_id}", "PagoSimulado"),
]
_IDS = [f"{m} {c}" for _, m, c, _ in RUTAS]


@pytest.mark.parametrize("archivo,metodo,camino,modelo", RUTAS, ids=_IDS)
def test_CADA_RUTA_TIENE_SU_CONTRATO(archivo, metodo, camino, modelo):
    ruta = _ruta(archivo, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True


@pytest.mark.parametrize("archivo,metodo,camino,modelo", RUTAS, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_RUTA_ARMA(archivo, metodo, camino, modelo):
    ruta = _ruta(archivo, "router", metodo, camino)
    claves = _claves(archivo, metodo, camino, None)
    assert claves, f"no encontré qué devuelve {camino}: sin claves este test no prueba nada"
    faltan = claves - _campos(ruta.response_model)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


def test_LO_QUE_SE_ANOTA_AL_ENTRAR_AL_PANEL_ESTA_EN_EL_CONTRATO():
    """El registro se lee de la base tal cual: lo que escribe el único lugar
    que escribe ahí tiene que estar en el contrato, menos el `_id`."""
    from models.fuera_del_panel import AccesoAlPanel
    claves = _escritura_del_registro()
    faltan = claves - {"_id"} - set(AccesoAlPanel.model_fields)
    assert len(claves) >= 8 and not faltan, f"el registro de accesos anota {sorted(faltan)} y el contrato no"



def _escritura_del_registro():
    """Las claves del `db.admin_access_log.insert_one({...})`, esté en la
    función que esté."""
    import ast
    import pathlib
    arbol = ast.parse((pathlib.Path(__file__).resolve().parent.parent / "routes/security_2fa.py").read_text("utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "insert_one" \
                and getattr(getattr(n.func, "value", None), "attr", "") == "admin_access_log":
            return {k.value for k in n.args[0].keys if isinstance(k, ast.Constant)}
    raise AssertionError("no encontré dónde se escribe el registro de accesos")


def test_LAS_CAJAS_POR_MONEDA_DE_LA_COLA_ESTAN_EN_EL_CONTRATO():
    """`por_moneda` y `por_origen` los arma `services/retiros.contadores`."""
    from models.fuera_del_panel import TotalPorMoneda
    import ast
    import pathlib
    arbol = ast.parse((pathlib.Path(__file__).resolve().parent.parent / "services/retiros.py").read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == "contadores"]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Dict):
            claves |= {k.value for k in n.keys if isinstance(k, ast.Constant)}
    cajas = {"moneda", "total", "ordenes"} & claves
    assert cajas == {"moneda", "total", "ordenes"}, f"la lectura no encontró las cajas: {claves}"
    assert cajas <= set(TotalPorMoneda.model_fields)


# ══════════════════════════════════════════════════════════════════════════
# Por HTTP, con datos
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def app():
    from _lote_c_comun import SUPER, app_con
    from routes import basic, btc_lightning, gestor_pix, security_2fa
    from routes import dependencies as deps
    c, base = app_con(basic.router, deps.get_super_admin, SUPER, "fuera_del_panel")
    for r in (security_2fa.router, btc_lightning.router, gestor_pix.router):
        c.app.include_router(r)
    c.app.dependency_overrides[deps.get_current_user] = lambda: SUPER
    return c, base


def test_LA_COLA_DE_PAGOS(app):
    from _lote_c_comun import SUPER
    from routes import basic
    from services.money import to_decimal128
    c, base = app
    ahora = datetime(2026, 9, 20, tzinfo=timezone.utc)
    ya(base.transactions.insert_many([
        {"transaction_id": "tx_1", "type": "withdrawal", "status": "pending", "currency_input": "RIS",
         "amount_input": to_decimal128("100.00"), "currency_output": "VES", "amount_output": to_decimal128("11000.00"),
         "beneficiary_data": {"full_name": "Carla"}, "created_at": ahora},
        {"transaction_id": "tx_2", "type": "withdrawal", "status": "pending", "currency_input": "RIS",
         "amount_input": to_decimal128("20.00"), "currency_output": "BRL", "amount_output": to_decimal128("20.00"),
         "beneficiary_data": {"full_name": "Dani"}, "created_at": ahora},
    ]))
    r = c.get("/withdrawal/queue-stats")
    _igual_a_llamarla_directo(r, ya(basic.get_withdrawal_queue_stats(admin=SUPER)))
    assert r.json()["total_ves_pending"] == 11000.0
    assert {m["moneda"]: m["ordenes"] for m in r.json()["por_moneda"]} == {"VES": 1, "BRL": 1}


def test_EL_REGISTRO_DE_ACCESOS_AL_PANEL(app):
    from _lote_c_comun import SUPER
    from routes import security_2fa
    c, base = app
    ya(base.admin_access_log.insert_one({
        "_id": "a" * 32, "user_id": "u_jefa", "email": "jefa@ejemplo.test", "role": "super_admin",
        "ip": "10.0.0.1", "country": "VE", "user_agent": "Navegador", "two_factor_used": True,
        "session_minutes": 30, "created_at": datetime(2026, 9, 20, tzinfo=timezone.utc)}))
    r = c.get("/auth/2fa/admin-access-log")
    _igual_a_llamarla_directo(r, ya(security_2fa.admin_access_log(limit=50, current_user=SUPER)))
    (acceso,) = r.json()["entries"]
    assert acceso["ip"] == "10.0.0.1" and acceso["two_factor_used"] is True


def test_LA_MARCA_DE_ENVIADO_DEL_OPERADOR(app):
    c, base = app
    # La billetera BTC-VES se guarda como float (ver btc_lightning.py): así se escribe acá.
    ya(base.btc_remesas.insert_one({"remesa_id": "r1", "user_id": "u_cli", "estado": "pagado",
                                    "ves_recibe": 100.0, "beneficiario_data": {"full_name": "José"}}))
    ya(base.btc_ves_wallets.insert_one({"user_id": "u_cli", "saldo": 150.0}))
    r = c.post("/btc/operador/marcar-enviado", json={"remesa_id": "r1", "operador_id": "u_op"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "msg": "Orden marcada como enviada.", "remesa_id": "r1"}


def test_CANCELAR_UN_PIX(app):
    from _lote_c_comun import SUPER
    c, base = app
    # La ruta busca a quien cancela en la base antes de dejarlo pasar.
    ya(base.users.insert_one({"user_id": SUPER.user_id, "email": SUPER.email}))
    ya(base.gestor_pix_payments.insert_one({"payment_id": "pix_1", "gestor_id": SUPER.user_id, "status": "pending"}))
    r = c.post("/gestor/pix/cancel/pix_1")
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "message": "Pago cancelado"}
