"""
tests/test_contratos_de_contabilidad.py — Las rutas de contabilidad que no
tienen pantalla salen por un contrato, y cada una contesta lo mismo que
contestaba, menos quién cargó cada cosa. Ver models/panel_contabilidad.py.

Se recorren como las usaba la pantalla que se borró: se crean bancos, se
cargan movimientos, tasas, compras y ventas de USDT, lotes, una venta P2P, y
se piden los libros, el reporte, el informe ejecutivo y el registro del motor.
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
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta    # noqa: E402

V1, V2 = "routes/accounting.py", "routes/accounting_v2.py"
RUTAS = [
    (V1, "POST", "/banks", "BancoCreado"),
    (V1, "DELETE", "/banks/{bank_id}", "MensajeDeContabilidad"),
    (V1, "GET", "/banks/{bank_id}/ledger", "LibroDeUnBanco"),
    (V1, "POST", "/banks/ledger/manual", "MovimientoManual"),
    (V1, "POST", "/rates", "MensajeDeContabilidad"),
    (V1, "GET", "/rates/latest", "TasaDeUsdt"),
    (V1, "POST", "/operations", "OperacionRegistrada"),
    (V1, "GET", "/usdt-ledger", "LibroDeUsdt"),
    (V1, "GET", "/report", "ReporteDeContabilidad"),
    (V1, "GET", "/balance-check", "AlcanzaElSaldo"),
    (V2, "POST", "/bootstrap-indexes", "MensajeDeContabilidad"),
    (V2, "POST", "/usdt-lots", "LoteDeUsdt"),
    (V2, "GET", "/usdt-lots", "LotesDeUsdt"),
    (V2, "GET", "/usdt-inventory-summary", "InventarioDeUsdt"),
    (V2, "POST", "/p2p-sales", "VentaP2P"),
    (V2, "GET", "/p2p-sales", "VentasP2P"),
    (V2, "GET", "/executive-report", "InformeEjecutivo"),
    (V2, "GET", "/audit-log", "RegistroDelMotor"),
    (V2, "POST", "/webhook-conciliate", "Conciliacion"),
]
# Las que devuelven una lista pelada: el contrato es `List[...]`.
LISTAS = [(V1, "GET", "/rates", "TasaDeUsdt"), (V1, "GET", "/operations", "OperacionConUsdt")]


@pytest.mark.parametrize("archivo,metodo,camino,modelo", RUTAS, ids=[f"{m} {c}" for _, m, c, _ in RUTAS])
def test_CADA_RUTA_DE_CONTABILIDAD_TIENE_SU_CONTRATO(archivo, metodo, camino, modelo):
    ruta = _ruta(archivo, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True
    faltan = _claves(archivo, metodo, camino, None) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


@pytest.mark.parametrize("archivo,metodo,camino,modelo", LISTAS, ids=[c for _, _, c, _ in LISTAS])
def test_LAS_QUE_DEVUELVEN_UNA_LISTA_TIENEN_CONTRATO_DE_LISTA(archivo, metodo, camino, modelo):
    ruta = _ruta(archivo, "router", metodo, camino)
    assert ruta.response_model.__origin__ is list and ruta.response_model.__args__[0].__name__ == modelo


def _claves_de_la_variable(archivo, funcion, variable):
    """Las claves del diccionario `variable = {...}` dentro de `funcion`.

    El motor no devuelve un diccionario escrito en el `return`: arma `doc` o
    `sale_doc`, lo guarda, y devuelve eso. La lectura de `return {...}` no lo
    ve, así que se lee la asignación."""
    import ast
    import pathlib
    arbol = ast.parse((pathlib.Path(__file__).resolve().parent.parent / archivo).read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == funcion]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == variable and isinstance(n.value, ast.Dict):
            claves |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
    assert claves, f"no encontré {variable} en {funcion}"
    return claves


# Lo que el contrato deja afuera A PROPOSITO: el `_id` interno y quién lo hizo.
AFUERA = {"_id", "created_by", "updated_by"}


def test_LO_QUE_ARMA_EL_MOTOR_ESTA_EN_SUS_CONTRATOS():
    from models import panel_contabilidad as m
    motor = "services/accounting_engine.py"
    lote = _claves_de_la_variable(motor, "register_usdt_lot", "doc") | {"lot_id"}
    assert lote - AFUERA <= set(m.LoteDeUsdt.model_fields), sorted(lote - set(m.LoteDeUsdt.model_fields))
    venta = _claves_de_la_variable(motor, "execute_p2p_arbitrage", "sale_doc")
    assert venta - AFUERA <= set(m.VentaP2P.model_fields), sorted(venta - set(m.VentaP2P.model_fields))
    from test_contratos_de_acceso import _claves_de_las_funciones
    informe = _claves_de_las_funciones(motor, ["generate_report"])
    anidados = {c for mod in (m.RangoDelInforme, m.PasivosDelInforme, m.LiquidezDelInforme, m.ArbitrajeDelInforme,
                              m.PasarelasDelInforme, m.BancosDelInforme) for c in mod.model_fields}
    assert informe <= set(m.InformeEjecutivo.model_fields) | anidados
    conciliar = _claves_de_las_funciones(motor, ["process_incoming_payment"])
    assert conciliar <= set(m.Conciliacion.model_fields), sorted(conciliar - set(m.Conciliacion.model_fields))


def test_LAS_LINEAS_DE_LOS_BANCOS_QUE_ESCRIBE_LA_APP_ESTAN_EN_EL_CONTRATO():
    """El libro de cada banco lo escriben cinco lugares, no sólo la
    contabilidad. Un campo nuevo en cualquiera de ellos tiene que estar en el
    contrato, o el libro lo pierde en silencio."""
    import ast
    import pathlib
    from models.panel_contabilidad import LineaDelBanco
    raiz = pathlib.Path(__file__).resolve().parent.parent
    claves = set()
    for archivo in ("routes/accounting.py", "routes/gestor_pix.py", "routes/admin.py", "routes/payments_card.py"):
        for n in ast.walk(ast.parse((raiz / archivo).read_text("utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "insert_one" \
                    and getattr(getattr(n.func, "value", None), "attr", "") == "bank_ledger" \
                    and n.args and isinstance(n.args[0], ast.Dict):
                claves |= {k.value for k in n.args[0].keys if isinstance(k, ast.Constant)}
    assert len(claves) >= 10, claves
    faltan = claves - AFUERA - set(LineaDelBanco.model_fields)
    assert not faltan, f"el libro del banco se escribe con {sorted(faltan)} y su contrato no los tiene"


# ══════════════════════════════════════════════════════════════════════════
# Por HTTP, como las usaba la pantalla
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


def ya(c):
    return asyncio.run(c)


def _sin(directo, *claves):
    """Lo de la función llamada a mano, sin lo que el contrato deja afuera."""
    if isinstance(directo, list):
        return [_sin(x, *claves) for x in directo]
    return {k: v for k, v in directo.items() if k not in claves}


@pytest.fixture
def contabilidad(monkeypatch):
    from _lote_c_comun import SUPER, app_con
    from routes import accounting, accounting_v2
    from routes import dependencies as deps
    from services import accounting_engine as ae
    from conftest import ensenarle_decimal128_a_mongomock
    # Los saldos de los bancos se mueven con `$inc` sobre Decimal128: la base
    # doble no sabe sumarlos si no se le enseña (ver tests/conftest.py).
    ensenarle_decimal128_a_mongomock()
    c, base = app_con(accounting.router, deps.get_super_admin, SUPER, "contratos_de_contabilidad")
    c.app.include_router(accounting_v2.router)
    monkeypatch.setattr(ae, "_SUPPORTS_TRANSACTIONS", None, raising=False)

    async def sembrar():
        await base.processed_webhooks.create_index("webhook_event_id", unique=True)
        await base.usdt_lots.create_index("purchase_id", unique=True, sparse=True)
        await base.rates.insert_one({"brl_to_usd": 5.0, "ris_to_ves": 110, "ves_to_ris_rate": 140, "usd_to_ves": 50})
        await base.bcv_rates.insert_one({"rates": {"dolar": 50}})
        await base.users.insert_one({"user_id": "u1", "name": "Uno", "email": "uno@example.com",
                                     "password_hash": "$2b$12$clave"})
    ya(sembrar())
    return c, base


def test_LOS_BANCOS_Y_SU_LIBRO(contabilidad):
    from _lote_c_comun import SUPER
    from routes import accounting
    c, _ = contabilidad
    creado = c.post("/admin/accounting/banks", json={"name": "Banesco", "currency": "VES", "initial_balance": 1000})
    assert creado.status_code == 200 and set(creado.json()) == {"message", "bank_id"}
    bid = creado.json()["bank_id"]
    mov = c.post("/admin/accounting/banks/ledger/manual",
                 json={"bank_id": bid, "type": "entrada", "amount": 250, "concept": "Depósito", "notes": "n"})
    assert mov.json() == {"message": "Movimiento registrado", "new_balance": 1250.0}
    libro = c.get(f"/admin/accounting/banks/{bid}/ledger")
    directo = ya(accounting.get_bank_ledger(bank_id=bid, page=1, limit=50, admin=SUPER))
    directo["bank"] = _sin(directo["bank"], "created_by")
    directo["entries"] = _sin(directo["entries"], "created_by")
    _igual_a_llamarla_directo(libro, directo)
    assert SUPER.user_id not in libro.text, "quién cargó el banco y el movimiento no sale"
    alcanza = c.get("/admin/accounting/balance-check?currency=VES&amount=500")
    _igual_a_llamarla_directo(alcanza, ya(accounting.check_balance(currency="VES", amount=500, admin=SUPER)))
    assert alcanza.json()["sufficient"] is True
    assert c.delete(f"/admin/accounting/banks/{bid}").json() == {"message": "Banco eliminado"}


def test_LAS_TASAS_LAS_OPERACIONES_Y_EL_LIBRO_DE_USDT(contabilidad):
    from _lote_c_comun import SUPER
    from routes import accounting
    c, base = contabilidad
    bid = c.post("/admin/accounting/banks", json={"name": "Itaú", "currency": "BRL", "initial_balance": 5000}).json()["bank_id"]
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert c.post("/admin/accounting/rates", json={"date": hoy, "buy_rate": 5.2, "sell_rate": 38.5,
                                                   "route": "brl_ves"}).json() == {"message": "Tasas actualizadas"}
    tasas = c.get("/admin/accounting/rates")
    assert tasas.json() == _sin(ya(accounting.get_usdt_rates(route="brl_ves", date=None, admin=SUPER)), "updated_by")
    assert SUPER.user_id not in tasas.text
    ultima = c.get("/admin/accounting/rates/latest")
    _igual_a_llamarla_directo(ultima, _sin(ya(accounting.get_latest_rates(route="brl_ves", admin=SUPER)), "updated_by"))
    for tipo in ("buy", "sell"):
        r = c.post("/admin/accounting/operations", json={
            "date": hoy, "route": "brl_ves", "amount_usdt": 100, "rate": 5.2, "bank_id": bid,
            "operation_type": tipo, "notes": ""})
        assert set(r.json()) == {"message", "operation_id", "total_fiat"}
    ops = c.get("/admin/accounting/operations")
    assert ops.json() == _sin(ya(accounting.get_operations(route="brl_ves", limit=50, admin=SUPER)), "created_by")
    usdt = c.get("/admin/accounting/usdt-ledger")
    _igual_a_llamarla_directo(usdt, ya(accounting.get_usdt_ledger(route="brl_ves", page=1, limit=30, admin=SUPER)))
    assert len(usdt.json()["entries"]) == 2


def test_EL_REPORTE_POR_RUTA(contabilidad):
    from _lote_c_comun import SUPER
    from routes import accounting
    from services.money import to_decimal128
    c, base = contabilidad
    ya(base.transactions.insert_one({
        "transaction_id": "tx_1", "display_id": "001001", "user_id": "u1", "type": "withdrawal",
        "status": "completed", "amount_input": to_decimal128("100.00"), "amount_output": to_decimal128("11000.00"),
        "rate": to_decimal128("110.00"), "created_at": datetime.now(timezone.utc),
        "proof_image": "data:image/jpeg;base64," + "FOTO" * 20}))
    r = c.get("/admin/accounting/report?period=month")
    _igual_a_llamarla_directo(r, ya(accounting.get_accounting_report(
        route="brl_ves", period="month", date=None, admin=SUPER)))
    (fila,) = r.json()["rows"]
    assert fila["cliente"] == "Uno" and fila["valor_transaccion"] == 100.0 and "FOTO" not in r.text


def test_EL_MOTOR_NUEVO_LOTES_VENTAS_INFORME_Y_REGISTRO(contabilidad):
    from _lote_c_comun import SUPER
    from routes import accounting_v2 as v2
    c, base = contabilidad
    bid = c.post("/admin/accounting/banks", json={"name": "Banesco", "currency": "VES", "initial_balance": 0}).json()["bank_id"]
    assert c.post("/admin/accounting/v2/bootstrap-indexes").json()["message"]
    lote = c.post("/admin/accounting/v2/usdt-lots", json={"initial_usdt": 100, "cost_per_usdt_brl": 5.2,
                                                         "purchase_id": "compra_1"})
    assert lote.status_code == 200, lote.text
    assert lote.json()["lot_id"] and lote.json()["remaining_usdt"] == 100.0 and "_id" not in lote.json()
    lotes = c.get("/admin/accounting/v2/usdt-lots")
    _igual_a_llamarla_directo(lotes, ya(v2.list_usdt_lots(only_active=False, admin=SUPER)))
    inventario = c.get("/admin/accounting/v2/usdt-inventory-summary")
    _igual_a_llamarla_directo(inventario, ya(v2.usdt_inventory_summary(admin=SUPER)))
    venta = c.post("/admin/accounting/v2/p2p-sales", json={"amount_usdt_to_sell": 40, "amount_ves_received": 1800,
                                                          "bank_account_id": bid})
    assert venta.status_code == 200, venta.text
    assert venta.json()["sale_id"] and "created_by" not in venta.json() and venta.json()["lots_consumed"]
    ventas = c.get("/admin/accounting/v2/p2p-sales")
    directo = ya(v2.list_p2p_sales(limit=50, admin=SUPER))
    directo["sales"] = _sin(directo["sales"], "created_by")
    _igual_a_llamarla_directo(ventas, directo)
    informe = c.get("/admin/accounting/v2/executive-report")
    _igual_a_llamarla_directo(informe, ya(v2.executive_report(start=None, end=None, range_days=1, admin=SUPER)))
    assert informe.json()["arbitrage_performance"]["volume_usdt_sold"] == 40.0
    registro = c.get("/admin/accounting/v2/audit-log")
    _igual_a_llamarla_directo(registro, ya(v2.get_audit_log(severity=None, action=None, limit=100, admin=SUPER)))
    assert {e["action"] for e in registro.json()["entries"]} >= {"USDT_LOT_REGISTERED", "P2P_ARBITRAGE_COMPLETE"}


def test_LA_CONCILIACION_MANUAL(contabilidad):
    c, base = contabilidad
    ya(base.bank_accounts.insert_one({"bank_id": "bco_1", "name": "Banco", "currency": "BRL", "balance": 1000.0}))
    ya(base.transactions.insert_one({"transaction_id": "tx_c", "status": "pending", "amount_brl": 100.0,
                                     "bank_account_id": "bco_1"}))
    cuerpo = {"webhook_event_id": "evt_1", "provider": "mercadopago", "transaction_id": "tx_c",
              "amount_received": 100.0, "currency": "BRL"}
    r = c.post("/admin/accounting/v2/webhook-conciliate", json=cuerpo)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESSFULLY_CONCILIATED" and set(r.json()) >= {"tx_id", "gross", "fee", "net_to_bank"}
    assert c.post("/admin/accounting/v2/webhook-conciliate", json=cuerpo).json()["status"] == "IGNORED_DUPLICATE"
