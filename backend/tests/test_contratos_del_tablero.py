"""
tests/test_contratos_del_tablero.py — Lo que queda del panel sale por un
contrato, y ningún contrato se come un campo que su ruta o su servicio arma.
Ver models/panel_tablero.py.

TRES GUARDAS

    1. Cada ruta declara su contrato (la tabla de abajo).
    2. La lectura del código: las claves que arma cada ruta o cada servicio
       están en su contrato. Ve también las ramas que los datos de prueba no
       recorren.
    3. Por HTTP con datos sembrados: cada lectura contesta lo mismo que su
       función llamada a mano, menos lo que el contrato deja afuera a
       propósito. Ve lo que la lectura del código no ve: lo que sale de la
       base tal cual o se arma con `{**otro}`.
"""
import ast
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves, _claves_de_las_funciones   # noqa: E402
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta     # noqa: E402
from test_contratos_de_encomiendas import _campos                        # noqa: E402

_BACKEND = pathlib.Path(__file__).resolve().parent.parent

BTC, CONF = "routes/btc_admin.py", "routes/configuracion.py"
# (archivo, router, método, camino, contrato)
RUTAS = [
    ("routes/misc.py", "router", "GET", "/admin/dashboard", "TableroDelPanel"),
    ("routes/admin/pendientes.py", "router", "GET", "/pendientes", "PendientesDelPanel"),
    ("routes/admin/mantenimiento.py", "router", "POST", "/fix-media-urls", "FotosConvertidas"),
    ("routes/admin/lotes.py", "router", "GET", "/lector/desempeno", "DesempenoDelLector"),
    ("routes/admin/reportes.py", "router", "GET", "/reportes/merma-nowpayments", "MermaDeNowpayments"),
    ("routes/admin/reportes.py", "router", "GET", "/reportes/fuentes", "FuentesDeReporte"),
    ("routes/admin/reportes.py", "router", "GET", "/reportes", "ReporteGenerado"),
    ("routes/admin/tasas.py", "router", "GET", "/rates", "TasasDelSistema"),
    ("routes/admin/tasas.py", "router", "POST", "/rates", "TasaActualizada"),
    ("routes/admin/tasas.py", "router", "GET", "/rate-history", "HistorialDeTasas"),
    ("routes/admin/tasas.py", "router", "GET", "/bcv-rates", "LecturaDelBcv"),
    ("routes/admin/tasas.py", "router", "GET", "/bcv-rates/history", "HistorialDelBcv"),
    ("routes/admin/tasas.py", "router", "POST", "/bcv-rates/refresh", "BcvActualizado"),
    ("routes/admin/usuarios.py", "router", "POST", "/blacklist", "AccionEnLaListaNegra"),
    ("routes/admin/usuarios.py", "router", "GET", "/blacklist", "ListaNegra"),
    ("routes/admin/usuarios.py", "router", "DELETE", "/blacklist/{blacklist_id}", "AccionEnLaListaNegra"),
    (CONF, "router", "GET", "", "ConfiguracionDelPanel"),
    (CONF, "router", "PUT", "", "ConfiguracionDelPanel"),
    (BTC, "router", "GET", "/config", "ConfiguracionBtc"),
    (BTC, "router", "PATCH", "/config", "ConfiguracionBtcGuardada"),
    (BTC, "router", "GET", "/stats", "EstadisticasBtc"),
    (BTC, "router", "GET", "/transacciones", "RemesasBtc"),
    (BTC, "router", "POST", "/marcar-enviado", "RemesaBtcEnviada"),
    ("routes/errores_admin.py", "router", "GET", "", "ErroresRegistrados"),
    ("routes/errores_admin.py", "router", "GET", "/resumen", "ResumenDeErrores"),
    ("routes/uso_admin.py", "router", "GET", "", "UsoDeLaApp"),
    ("admin_routes.py", "admin_router", "GET", "/transactions", "OperacionesDelPanel"),
    ("admin_routes.py", "admin_router", "GET", "/transactions/{transaction_id}", "DetalleDeOperacion"),
]
_IDS = [f"{m} {a.split('/')[-1][:-3]}{c}" for a, _, m, c, _ in RUTAS]


@pytest.mark.parametrize("archivo,nombre,metodo,camino,modelo", RUTAS, ids=_IDS)
def test_CADA_RUTA_QUE_QUEDABA_DEL_PANEL_TIENE_SU_CONTRATO(archivo, nombre, metodo, camino, modelo):
    ruta = _ruta(archivo, nombre, metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


# Las que devuelven lo que arma un servicio, o el documento de la base con
# algo agregado: no hay un diccionario a la vista en la ruta. Se leen más
# abajo, en su servicio o en lo que se guarda.
NO_ARMAN_AHI = {
    ("routes/admin/lotes.py", "GET", "/lector/desempeno"), ("routes/admin/reportes.py", "GET", "/reportes"),
    ("routes/admin/tasas.py", "GET", "/bcv-rates/history"), ("routes/configuracion.py", "GET", ""),
    # Estas dos devuelven `lo_de_la_base or {...por omisión}`.
    ("routes/admin/tasas.py", "GET", "/rates"), ("routes/admin/tasas.py", "GET", "/bcv-rates"),
    ("routes/errores_admin.py", "GET", ""), ("routes/errores_admin.py", "GET", "/resumen"),
    ("routes/uso_admin.py", "GET", ""), ("routes/btc_admin.py", "POST", "/marcar-enviado"),
    ("admin_routes.py", "GET", "/transactions/{transaction_id}"),
}
ARMAN_AHI = [r for r in RUTAS if (r[0], r[2], r[3]) not in NO_ARMAN_AHI]


@pytest.mark.parametrize("archivo,nombre,metodo,camino,modelo", ARMAN_AHI,
                         ids=[f"{m} {c}" for _, _, m, c, _ in ARMAN_AHI])
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_RUTA_ARMA(archivo, nombre, metodo, camino, modelo):
    ruta = _ruta(archivo, nombre, metodo, camino)
    claves = _claves(archivo, metodo, camino, None)
    assert claves, f"no encontré qué devuelve {camino}: sin claves este test no prueba nada"
    faltan = claves - _campos(ruta.response_model)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


def _claves_de_la_variable(archivo, funcion, variable):
    """Las claves de `variable = {...}` y de `variable["x"] = ...` dentro de
    `funcion`: lo que se arma de a poco y se devuelve al final."""
    arbol = ast.parse((_BACKEND / archivo).read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcion]
    claves = set()
    for n in ast.walk(f):
        if not isinstance(n, ast.Assign):
            continue
        destino = n.targets[0]
        if getattr(destino, "id", "") == variable and isinstance(n.value, ast.Dict):
            claves |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
        if isinstance(destino, ast.Subscript) and getattr(destino.value, "id", "") == variable \
                and isinstance(destino.slice, ast.Constant):
            claves.add(destino.slice.value)
    assert claves, f"no encontré {variable} en {funcion}"
    return claves


def _claves_de_los_diccionarios_pasados_a(archivo, funcion, llamada):
    """Las claves de cada `algo.llamada({...})` dentro de `funcion`, como el
    `ordenes.append({...})` del reporte de merma o el `insert_one({...})` de
    la lista negra."""
    arbol = ast.parse((_BACKEND / archivo).read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcion]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == llamada and n.args \
                and isinstance(n.args[0], ast.Dict):
            claves |= {k.value for k in n.args[0].keys if isinstance(k, ast.Constant)}
    assert claves, f"no encontré {llamada}({{...}}) en {funcion}"
    return claves


def _en(modelo, claves, afuera=()):
    faltan = set(claves) - set(afuera) - _campos(modelo)
    assert not faltan, f"se arma {sorted(faltan)} y el contrato {modelo.__name__} no lo tiene"


def test_LO_QUE_ARMAN_LOS_SERVICIOS_ESTA_EN_SU_CONTRATO():
    from models import panel_tablero as m
    _en(m.ReporteGenerado, _claves_de_las_funciones("services/reportes.py", ["generar"]))
    _en(m.DesempenoDelLector, _claves_de_las_funciones("services/desempeno_del_lector.py", ["_vacio"])
        | _claves_de_la_variable("services/desempeno_del_lector.py", "_medir", "informe"))
    _en(m.ErroresRegistrados, _claves_de_las_funciones("services/errores.py", ["buscar"]))
    _en(m.ResumenDeErrores, _claves_de_las_funciones("services/errores.py", ["resumen"]))
    _en(m.UsoDeLaApp, _claves_de_las_funciones("services/uso.py", ["todo"]))
    _en(m.RemesaBtc, _claves_de_las_funciones(BTC, ["_serialize_remesa"]))
    _en(m.RemesaBtcEnviada, _claves_de_las_funciones(BTC, ["completar_remesa_btc"]))
    _en(m.OrdenConMerma, _claves_de_los_diccionarios_pasados_a("routes/admin/reportes.py", "reporte_merma_nowpayments", "append"))


def test_LO_QUE_SE_GUARDA_Y_SE_LEE_TAL_CUAL_ESTA_EN_SU_CONTRATO():
    """Las tasas, su historial, el BCV, la lista negra y los errores se leen
    de la base sin armar nada. Lo que el único lugar que escribe cada
    colección guarda tiene que estar en el contrato, menos lo que se deja
    afuera a propósito."""
    from models import panel_tablero as m
    _en(m.ErrorRegistrado, _claves_de_la_variable("services/errores.py", "anotar", "linea"))
    _en(m.EntradaDeLaListaNegra, _claves_de_la_variable("routes/admin/usuarios.py", "add_to_blacklist", "entry"), afuera={"banned_by"})
    _en(m.CambioDeTasa, _claves_de_la_variable("services/rate_history.py", "log_if_changed", "entry"))
    _en(m.LecturaDelBcv, _claves_de_las_funciones("services/bcv_scraper.py", ["fetch_bcv_rates"])
        | _claves_de_la_variable("services/bcv_scraper.py", "get_latest", "doc"))
    tasa = _claves_de_la_variable("routes/admin/tasas.py", "update_rates", "update_fields") \
        | _claves_de_los_diccionarios_pasados_a("database.py", "init_db", "insert_one")
    _en(m.TasasDelSistema, tasa, afuera={"updated_by"})
    assert "updated_by" in tasa, "la lectura dejó de ver quién cambió la tasa: este test no mira lo que dice"


# ══════════════════════════════════════════════════════════════════════════
# Por HTTP, con datos
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


def ya(c):
    import asyncio
    return asyncio.run(c)


def _sin(directo, *claves):
    if isinstance(directo, list):
        return [_sin(x, *claves) for x in directo]
    return {k: v for k, v in directo.items() if k not in claves}


AHORA = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def panel(monkeypatch):
    from _lote_c_comun import SUPER, app_con
    from routes import admin, btc_admin, configuracion, errores_admin, misc, uso_admin
    from routes import dependencies as deps
    import admin_routes
    from services.money import to_decimal128
    c, base = app_con(admin.router, deps.get_super_admin, SUPER, "contratos_del_tablero")
    for r in (misc.router, configuracion.router, btc_admin.router, errores_admin.router, uso_admin.router,
              admin_routes.admin_router):
        c.app.include_router(r)
    # `admin_routes.py` abre su propia conexión.
    monkeypatch.setattr(admin_routes, "db", base)
    for d in (deps.get_admin_user, deps.get_crm_user, deps.get_current_user):
        c.app.dependency_overrides[d] = lambda: SUPER

    async def sembrar():
        await base.users.insert_many([
            {"user_id": "u_ana", "name": "Ana", "full_name": "Ana Pérez", "email": "ana@ejemplo.test",
             "verification_status": "verified", "password_hash": "$2b$12$clave"},
            {"user_id": "u_beto", "name": "Beto", "email": "beto@ejemplo.test", "password_hash": "$2b$12$clave"},
        ])
        await base.transactions.insert_many([
            {"transaction_id": "tx_1", "display_id": "000101", "user_id": "u_ana", "type": "withdrawal",
             "status": "completed", "amount_input": to_decimal128("100.00"),
             "amount_output": to_decimal128("11000.00"), "currency_input": "RIS", "currency_output": "VES",
             "rate": to_decimal128("110.00"), "created_at": AHORA, "completed_at": AHORA,
             "beneficiary_data": {"full_name": "Carla", "id_document": "V123", "bank": "0102",
                                  "account_number": "0102000", "user_id": "u_ana", "beneficiary_id": "b_1"},
             "proof_image": "data:image/jpeg;base64," + "FOTO" * 20,
             "notas_internas": "no mostrar", "ipn_crudo": {"secreto": "x"}},
            {"transaction_id": "tx_2", "display_id": "000102", "user_id": "u_beto", "type": "recharge_ves",
             "status": "completed", "funded_from": "payment", "amount_input": to_decimal128("50.00"),
             "amount_output": to_decimal128("5000.00"), "currency_input": "usdttrc20",
             "rate": to_decimal128("100.00"), "merma_ves": to_decimal128("12.50"),
             "merma_calculada_at": AHORA, "created_at": AHORA, "paid_at": AHORA, "actually_paid": 49.5,
             "outcome_amount": 49.0, "outcome_currency": "usdttrc20"},
        ])
        await base.rates.insert_one({"rate_id": "default", "ris_to_ves": 110.0, "ves_to_ris": 0.009,
                                     "ves_to_ris_rate": 140.0, "updated_at": AHORA, "updated_by": "u_jefa"})
        await base.rate_history.insert_many([
            {"route": "brl_ves", "old_rate": 100.0, "new_rate": 110.0, "change_type": "manual",
             "admin_email": "jefa@ejemplo.test", "reason": None, "timestamp": AHORA},
        ])
        await base.bcv_rates.insert_many([
            {"rates": {"dolar": 50.1, "euro": 55.2}, "value_date": "Lunes, 21 Septiembre 2026",
             "fetched_at": AHORA - timedelta(hours=30)},
            {"rates": {"dolar": 51.3, "euro": 56.0}, "value_date": "Martes, 22 Septiembre 2026",
             "fetched_at": AHORA},
        ])
        await base.btc_remesas.insert_one({
            "remesa_id": "r_1", "user_id": "u_ana", "beneficiario_id": "b_9",
            "beneficiario_data": {"full_name": "Dani", "cedula": "V9", "phone_number": "+58 412",
                                  "bank": "0102", "account_number": "0102999", "payment_type": "pago_movil"},
            "usd_cliente": 20.0, "ves_recibe": 1000.0, "btc_pagar": 0.0002, "sats": 20000,
            "precio_btc_usado": 100000.0, "precio_con_margen": 98000.0, "tasa_ves": 50.0,
            "payment_request": "lnbc1factura", "payment_hash": "hash_1", "memo": "memo", "tipo": "btc_remesa",
            "estado": "pagado", "no_reembolsable": True, "creado_en": AHORA, "expira_en": AHORA})
    ya(sembrar())
    return c, base


def test_EL_TABLERO_Y_LOS_PENDIENTES(panel):
    from _lote_c_comun import SUPER
    from routes import misc
    from routes.admin import pendientes as admin
    c, _ = panel
    tablero = c.get("/admin/dashboard")
    _igual_a_llamarla_directo(tablero, ya(misc.get_admin_dashboard(current_user=SUPER)))
    assert tablero.json()["total_users"] == 2
    _igual_a_llamarla_directo(c.get("/admin/pendientes"), ya(admin.get_pendientes(current_user=SUPER)))


def test_LAS_TASAS_NO_DICEN_QUIEN_LAS_CAMBIO(panel):
    from _lote_c_comun import SUPER
    from routes.admin import tasas as admin
    c, _ = panel
    tasas = c.get("/admin/rates")
    _igual_a_llamarla_directo(tasas, _sin(ya(admin.get_rates(admin=SUPER)), "updated_by"))
    assert tasas.json()["ris_to_ves"] == 110.0 and SUPER.user_id not in tasas.text
    nueva = c.post("/admin/rates", json={"ris_to_ves": 112.5})
    assert nueva.status_code == 200, nueva.text
    assert nueva.json()["ris_to_ves"] == 112.5 and nueva.json()["message"] == "Tasa actualizada"
    assert "updated_by" not in nueva.json() and SUPER.user_id not in nueva.text
    historial = c.get("/admin/rate-history")
    _igual_a_llamarla_directo(historial, ya(admin.get_rate_history(limit=200, route=None, admin=SUPER)))
    assert historial.json()["count"] == 2, "el cambio manual quedó en el historial"


def test_LAS_TASAS_DEL_BCV(panel, monkeypatch):
    from _lote_c_comun import SUPER
    from routes.admin import tasas as admin
    from services import bcv_scraper
    c, _ = panel
    ultima = c.get("/admin/bcv-rates")
    _igual_a_llamarla_directo(ultima, ya(admin.get_bcv_rates(admin=SUPER)))
    assert ultima.json()["rates"] == {"dolar": 51.3, "euro": 56.0} and "vencida" in ultima.json()
    _igual_a_llamarla_directo(c.get("/admin/bcv-rates/history"),
                              ya(admin.get_bcv_rates_history(limit=50, admin=SUPER)))

    async def raspar():
        return {"rates": {"dolar": 52.0}, "value_date": "Jueves", "fetched_at": datetime.now(timezone.utc)}
    monkeypatch.setattr(bcv_scraper, "fetch_bcv_rates", raspar)
    nueva = c.post("/admin/bcv-rates/refresh")
    assert nueva.status_code == 200, nueva.text
    assert nueva.json()["saved_new_snapshot"] is True and nueva.json()["latest"]["rates"] == {"dolar": 52.0}
    assert set(nueva.json()["latest"]) >= {"value_date", "fetched_at", "vencida", "edad_horas", "horas_de_vigencia"}


def test_LA_LISTA_NEGRA(panel):
    from _lote_c_comun import SUPER
    from routes.admin import usuarios as admin
    c, _ = panel
    alta = c.post("/admin/blacklist", json={"type": "email", "value": "Malo@Ejemplo.test", "reason": "fraude"})
    assert alta.status_code == 200, alta.text
    assert set(alta.json()) == {"success", "message", "blacklist_id"}
    lista = c.get("/admin/blacklist")
    directo = ya(admin.list_blacklist(admin=SUPER))
    directo["items"] = _sin(directo["items"], "banned_by")
    _igual_a_llamarla_directo(lista, directo)
    assert SUPER.user_id not in lista.text, "quién bloqueó sale por su nombre, no por su identificador"
    (item,) = lista.json()["items"]
    assert item["value"] == "malo@ejemplo.test" and item["banned_by_name"] == SUPER.email
    baja = c.delete(f"/admin/blacklist/{alta.json()['blacklist_id']}")
    assert baja.json() == {"success": True, "message": "Quitado de la lista negra"}


def test_LA_CONFIGURACION(panel):
    from _lote_c_comun import SUPER
    from routes import configuracion
    c, _ = panel
    ver = c.get("/admin/configuracion")
    _igual_a_llamarla_directo(ver, ya(configuracion.ver_configuracion(SUPER)))
    assert len(ver.json()["ajustes"]) >= 20 and {"clave", "valor"} <= set(ver.json()["ajustes"][0])
    guardado = c.put("/admin/configuracion", json={"valores": {"bcv_horas_de_vigencia": 36}})
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["cambiados"] == ["bcv_horas_de_vigencia"]
    assert [a["valor"] for a in guardado.json()["ajustes"] if a["clave"] == "bcv_horas_de_vigencia"] == [36]


def test_EL_BITCOIN(panel, monkeypatch):
    from _lote_c_comun import SUPER
    from routes import btc_admin
    c, _ = panel

    async def precio():
        return 100000.0
    monkeypatch.setattr(btc_admin, "_fetch_current_btc_price", precio)
    config = c.get("/admin/btc/config")
    _igual_a_llamarla_directo(config, ya(btc_admin.get_btc_config(admin=SUPER)))
    assert config.json()["example"]["sats"] > 0 and config.json()["defaults"]
    cambio = c.patch("/admin/btc/config", json={"margen": 0.97})
    assert cambio.json() == {"success": True, "changes": {"margen": 0.97}}
    _igual_a_llamarla_directo(c.get("/admin/btc/stats"), ya(btc_admin.get_btc_stats(admin=SUPER)))
    lista = c.get("/admin/btc/transacciones")
    _igual_a_llamarla_directo(lista, ya(btc_admin.list_btc_transacciones(
        status="all", search=None, date_from=None, date_to=None, page=1, page_size=50, admin=SUPER)))
    (remesa,) = lista.json()["items"]
    assert remesa["beneficiario"] == {"full_name": "Dani", "id_document": "V9", "phone": "+58 412",
                                      "bank": "0102", "account_number": "0102999", "payment_type": "pago_movil"}
    assert remesa["user_email"] == "ana@ejemplo.test"
    assert "lnbc1factura" not in lista.text, "la factura Lightning no sale en la lista del panel"


def test_LOS_ERRORES_Y_EL_USO(panel):
    from _lote_c_comun import SUPER  # noqa: F401
    from services import errores, uso
    c, base = panel
    ya(errores.anotar(base, rastro="r1", metodo="GET", ruta="/api/algo", status=500, tipo="KeyError",
                      mensaje="falta x", traza="Traceback...", user_id="u_ana", ip="10.0.0.1"))
    lista = c.get("/admin/errores")
    _igual_a_llamarla_directo(lista, ya(errores.buscar(base)))
    assert lista.json()["lineas"][0]["traza"] == "Traceback..."
    resumen = c.get("/admin/errores/resumen")
    _igual_a_llamarla_directo(resumen, ya(errores.resumen(base, horas=24)))
    assert resumen.json()["rutas"] == [{"ruta": "/api/algo", "cuantos": 1}]
    _igual_a_llamarla_directo(c.get("/admin/uso"), ya(uso.todo(base, dias=30)))


def test_LOS_REPORTES_Y_EL_LECTOR(panel):
    from _lote_c_comun import SUPER
    from routes.admin import lotes, reportes as admin
    from services import reportes
    c, base = panel
    _igual_a_llamarla_directo(c.get("/admin/reportes/fuentes"), ya(admin.reportes_fuentes(admin=SUPER)))
    merma = c.get("/admin/reportes/merma-nowpayments")
    _igual_a_llamarla_directo(merma, ya(admin.reporte_merma_nowpayments(date_from=None, date_to=None, admin=SUPER)))
    (orden,) = merma.json()["ordenes"]
    assert orden["merma_ves"] == 12.5 and orden["user_email"] == "beto@ejemplo.test"
    criterios = dict(desde="2026-09-01", hasta="2026-09-30", flujos=None, buscar=None, operador=None,
                     monto_min=None, monto_max=None, tz_min=0)
    r = c.get("/admin/reportes?desde=2026-09-01&hasta=2026-09-30")
    # `generado_at` es la hora de cada llamada: difiere entre las dos.
    directo = ya(reportes.generar(limite=100, saltear=0, **criterios))
    assert r.status_code == 200, r.text
    from fastapi.encoders import jsonable_encoder
    assert _sin(r.json(), "generado_at") == _sin(jsonable_encoder(directo), "generado_at")
    assert r.json()["operaciones"] >= 1 and r.json()["filas"]
    _igual_a_llamarla_directo(c.get("/admin/lector/desempeno"),
                              ya(lotes.desempeno_del_lector_de_comprobantes(admin=SUPER)))
    fotos = c.post("/admin/fix-media-urls").json()
    assert fotos["transactions_fixed"] == 0 and fotos["errors"] == [] and fotos["message"]


def test_LAS_DOS_RUTAS_VIEJAS_DE_OPERACIONES_YA_NO_DEVUELVEN_EL_DOCUMENTO_ENTERO(panel):
    """Antes salía la operación tal cual está en la base: el `_id`, las notas
    internas, lo que cada medio de pago le anotó y el beneficiario copiado con
    los identificadores de su dueño."""
    c, _ = panel
    lista = c.get("/api/admin/transactions")
    assert lista.status_code == 200, lista.text
    assert lista.json()["total"] == 2
    fila = next(t for t in lista.json()["transactions"] if t["transaction_id"] == "tx_1")
    assert fila["user_email"] == "ana@ejemplo.test" and fila["amount_input"] == 100.0
    assert fila["beneficiary_data"]["full_name"] == "Carla"
    detalle = c.get("/api/admin/transactions/tx_1")
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["proof_image"].startswith("data:image/jpeg"), "el detalle es donde se ven las fotos"
    for respuesta in (lista, detalle):
        for adentro in ('"_id"', "notas_internas", "no mostrar", "ipn_crudo", "beneficiary_id", "b_1"):
            assert adentro not in respuesta.text, f"{adentro} salió en {respuesta.url}"
    assert "FOTO" not in lista.text, "la lista sigue sin las fotos"


def test_SIN_PRECIO_DEL_BTC_LA_PANTALLA_NO_DIBUJA_UNA_VISTA_PREVIA_CON_NAN(panel, monkeypatch):
    """Sin precio del BTC el backend manda `example: {}`, y la pantalla de
    tasas lo tomaba como un ejemplo de verdad: «NaN Bs» y «$NaN». Se ve en la
    vista previa del 25 de septiembre de 2026, con el precio bloqueado."""
    import re
    from _lote_c_comun import fuente, sin_comentarios
    from routes import btc_admin
    c, _ = panel

    async def sin_precio():
        return None
    monkeypatch.setattr(btc_admin, "_fetch_current_btc_price", sin_precio)
    assert c.get("/admin/btc/config").json()["example"] == {}, "el caso que este test cubre dejó de existir"
    codigo = sin_comentarios(fuente("components/admin/TasasBtcSection.jsx"))
    (ej,) = re.findall(r"const ej = (.+);", codigo)
    assert "precio_con_margen" in ej and "null" in ej, \
        f"la vista previa se dibuja con cualquier `example`, también el vacío: `{ej}`"
