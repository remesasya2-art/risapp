"""
tests/test_contratos_del_libro.py — Lo que el panel ve del libro de cuentas sale
por un contrato, y ningún contrato se come un campo que su servicio arma.
Ver models/panel_libro.py.

La prueba fuerte es la de HTTP: cada ruta, con datos que llenan TODAS sus
listas (un descuadre, líneas de alguien que ya no existe, líneas mal escritas,
bancos de respaldo y de trabajo, cobros sin acreditar), tiene que contestar lo
mismo que su servicio llamado a mano. Un contrato que se come un campo anidado
se ve ahí, y sólo ahí: con las listas vacías pasaría igual.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves, _claves_de_las_funciones   # noqa: E402
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta    # noqa: E402

L = "routes/ledger_admin.py"
RUTAS = [
    ("POST", "/opening", "AperturaDelLibro"),
    ("GET", "/reconcile", "ReconciliacionVieja"),
    ("GET", "/entries", "LineasDeUnUsuario"),
    ("GET", "/plan-de-cuentas", "PlanDeCuentas"),
    ("GET", "/diario", "LibroDiario"),
    ("GET", "/mayor", "LibroMayor"),
    ("GET", "/balance", "BalanceDeComprobacion"),
    ("GET", "/reconciliacion", "Reconciliacion"),
    ("GET", "/pozo", "ConciliacionDelPozo"),
    ("GET", "/integridad", "IntegridadDelLibro"),
    ("GET", "/cofre", "EstadoDelCofre"),
    ("POST", "/cofre/llave-nueva", "LlaveNuevaDelCofre"),
    ("POST", "/cofre/cotejar", "CotejoDeLaLlave"),
    ("GET", "/cobros-sin-acreditar", "CobrosSinAcreditar"),
]


@pytest.mark.parametrize("metodo,camino,modelo", RUTAS, ids=[f"{m} {c}" for m, c, _ in RUTAS])
def test_CADA_RUTA_DEL_LIBRO_TIENE_SU_CONTRATO(metodo, camino, modelo):
    ruta = _ruta(L, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def test_LAS_DOS_DE_CONTABILIDAD_QUE_USA_EL_PANEL_TIENEN_CONTRATO():
    bancos = _ruta("routes/accounting.py", "router", "GET", "/banks")
    assert bancos.response_model.__args__[0].__name__ == "BancoDeLaContabilidad"
    borrar = _ruta("routes/admin.py", "router", "POST", "/accounting/wipe")
    assert borrar.response_model.__name__ == "ContabilidadBorrada" and borrar.response_model_exclude_unset
    assert _claves("routes/admin.py", "POST", "/accounting/wipe", None) <= set(borrar.response_model.model_fields)


# Lo que arma cada servicio, leído del código: TODOS sus `return {...}`,
# también los de los caminos que los datos de abajo no recorren.
DE_LOS_SERVICIOS = [
    ("services/contabilidad.py", ["reconciliacion"], "Reconciliacion"),
    ("services/contabilidad.py", ["integridad"], "IntegridadDelLibro"),
    ("services/contabilidad.py", ["conciliacion_pozo"], "ConciliacionDelPozo"),
    ("services/contabilidad.py", ["libro_diario"], "LibroDiario"),
    ("services/contabilidad.py", ["libro_mayor"], "LibroMayor"),
    ("services/contabilidad.py", ["balance_de_comprobacion"], "BalanceDeComprobacion"),
    ("services/cobros_sin_acreditar.py", ["revisar"], "CobrosSinAcreditar"),
    ("services/cofre.py", ["cotejar"], "CotejoDeLaLlave"),
    ("services/cofre.py", ["llave_nueva"], "LlaveNuevaDelCofre"),
    ("services/ledger.py", ["create_opening_entries"], "AperturaDelLibro"),
]


@pytest.mark.parametrize("archivo,funciones,modelo", DE_LOS_SERVICIOS, ids=[m for _, _, m in DE_LOS_SERVICIOS])
def test_EL_CONTRATO_TIENE_TODO_LO_QUE_ARMA_SU_SERVICIO(archivo, funciones, modelo):
    from models import panel_libro
    claves = _claves_de_las_funciones(archivo, funciones)
    assert claves, f"no encontré qué devuelve {funciones}: sin claves este test no prueba nada"
    faltan = claves - set(getattr(panel_libro, modelo).model_fields)
    # Las claves de diccionarios internos (una fila, un hallazgo) también se
    # leen del código: se buscan en los modelos anidados, no sólo arriba.
    faltan -= {c for m in _anidados(getattr(panel_libro, modelo)) for c in m.model_fields}
    assert not faltan, f"{funciones} arma {sorted(faltan)} y el contrato {modelo} no los tiene"


def test_EL_ESTADO_DEL_COFRE_TIENE_TODO_LO_QUE_ARMA_REVISAR():
    """`cofre.revisar` no devuelve un diccionario escrito en el `return`:
    arma `estado = {...}` y le agrega claves según el caso (`estado["motivo"]
    = ...`). La lectura de arriba no lo ve, así que acá se leen las dos cosas."""
    import ast
    import pathlib
    from models.panel_libro import EstadoDelCofre
    arbol = ast.parse((pathlib.Path(__file__).resolve().parent.parent / "services/cofre.py").read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == "revisar"]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "estado" \
                and isinstance(n.value, ast.Dict):
            claves |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript) \
                and getattr(n.targets[0].value, "id", "") == "estado":
            claves.add(n.targets[0].slice.value)
    assert len(claves) >= 5, f"la lectura no encontró las claves del estado: {claves}"
    faltan = claves - set(EstadoDelCofre.model_fields)
    assert not faltan, f"cofre.revisar arma {sorted(faltan)} y el contrato no los tiene"


def _anidados(modelo, vistos=None):
    """Los modelos que cuelgan de uno, a cualquier profundidad."""
    from typing import get_args
    from pydantic import BaseModel
    vistos = vistos if vistos is not None else set()
    for campo in modelo.model_fields.values():
        pendientes = [campo.annotation]
        while pendientes:
            t = pendientes.pop()
            if isinstance(t, type) and issubclass(t, BaseModel) and t not in vistos:
                vistos.add(t)
                _anidados(t, vistos)
            pendientes.extend(get_args(t))
    return vistos


# Lo que leen LibroMayor.jsx, ReconciliacionLedger.jsx y CobrosSinAcreditar.jsx.
LO_QUE_LEEN_LAS_PANTALLAS = {
    "AsientoDelDiario": {"numero", "fecha", "glosa", "debe", "haber", "monto", "moneda", "clasificado",
                         "usuario", "referencia"},
    "LibroDiario": {"asientos", "asientos_totales", "suma_debe", "suma_haber", "sin_clasificar", "hay_mas",
                    "truncado"},
    "CuentaDelMayor": {"codigo", "nombre", "tipo", "saldo", "suma_debe", "suma_haber", "movimientos",
                       "hay_mas_movimientos"},
    "MovimientoDelMayor": {"fecha", "glosa", "referencia", "usuario", "debe", "haber", "saldo"},
    "BalanceDeComprobacion": {"cuentas", "total_debe", "total_haber", "cuadra", "por_grupo"},
    "Reconciliacion": {"cuadra", "descuadres", "descuadres_totales", "lineas_leidas", "usuarios_revisados",
                       "lineas_sin_usuario"},
    "DescuadreDeUnUsuario": {"user_id", "email", "nombre", "cuenta_contable", "saldo_guardado",
                             "suma_del_libro", "diferencia"},
    "LineasSinUsuario": {"user_id", "cuenta", "suma_del_libro"},
    "IntegridadDelLibro": {"sano", "hallazgos", "limitaciones", "lineas_revisadas"},
    "HallazgoDelLibro": {"clave", "titulo", "explicacion", "gravedad", "cuantas", "ejemplos"},
    "ReconciliacionVieja": {"checked", "mismatches_count", "ok", "mismatches"},
    "DescuadreViejo": {"user_id", "email", "name", "role", "balance_ris", "ledger_sum", "diff"},
    "LineasDeUnUsuario": {"balance_ris", "ledger_sum", "diff", "entries"},
    "LineaDelLibro": {"entry_id", "created_at", "movement_type", "direction", "amount", "balance_before",
                      "balance_after", "display_id", "reference"},
    "AperturaDelLibro": {"revisados", "aperturas_creadas"},
    "CobrosSinAcreditar": {"cobros", "cuantos", "descuadres", "cuantos_descuadres", "dias", "mirados",
                           "pudo_preguntar", "sin_mirar", "sin_respuesta", "tope", "total_brl",
                           "total_descuadres_brl"},
    "CobroSinAcreditar": {"medio", "pago", "pago_en_mercadopago", "cuenta", "cliente", "estado_en_la_app",
                          "cuando", "monto_en_mercadopago", "monto_en_la_app"},
    "LlaveNuevaDelCofre": {"llave", "huella"},
    "BancoDeLaContabilidad": {"bank_id", "name", "currency"},
}


def test_LO_QUE_LEEN_LAS_PANTALLAS_ESTA_EN_CADA_CONTRATO():
    from models import panel_libro
    for nombre, campos in LO_QUE_LEEN_LAS_PANTALLAS.items():
        faltan = campos - set(getattr(panel_libro, nombre).model_fields)
        assert not faltan, f"la pantalla lee {sorted(faltan)} de {nombre} y su contrato no lo tiene"


def test_LA_LISTA_DE_LO_QUE_LEEN_ESTA_EN_LAS_PANTALLAS():
    from _lote_c_comun import fuente
    texto = "".join(fuente(f) for f in (
        "components/admin/LibroMayor.jsx", "components/admin/ReconciliacionLedger.jsx",
        "components/admin/CobrosSinAcreditar.jsx", "components/admin/SeguridadFinanciera.jsx",
        "components/admin/RecargasVES.jsx", "components/admin/Retiros.jsx"))
    sueltos = sorted({c for campos in LO_QUE_LEEN_LAS_PANTALLAS.values() for c in campos if c not in texto})
    assert not sueltos, f"las pantallas ya no leen {sueltos}"


# ══════════════════════════════════════════════════════════════════════════
# Por HTTP, con un libro que tiene de todo
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


def ya(c):
    return asyncio.run(c)


HOY = datetime.now(timezone.utc)
DESDE, HASTA = (HOY - timedelta(days=30)).strftime("%Y-%m-%d"), (HOY + timedelta(days=1)).strftime("%Y-%m-%d")


class _MercadoPago:
    async def __call__(self, id_de_pago):
        return {"status": "approved", "amount": 150.0, "date_approved": "2026-09-01T10:00:00.000-04:00",
                "status_detail": "accredited"}


@pytest.fixture
def libro(monkeypatch):
    """Un libro con de todo:

    - Uno, que cuadra: recargó 100 y mandó 30, tiene 70.
    - Dos, que NO cuadra: el libro dice 40 y su saldo guardado 55.
    - Líneas de alguien que ya no existe.
    - Una línea mal escrita: monto cero y un movimiento que no está en el plan.
    - Un banco en reales que respalda, una pasarela, y uno en bolívares de trabajo.
    - Un PIX vencido que Mercado Pago cobró, y una tarjeta aprobada sin línea.
    """
    from conftest import ensenarle_decimal128_a_mongomock
    from _lote_c_comun import SUPER, app_con
    from routes import dependencies as deps
    from routes import accounting as rutas_contabilidad
    from routes import ledger_admin as la
    from services import cobros_sin_acreditar, ledger
    from services.money import to_decimal128
    ensenarle_decimal128_a_mongomock()
    c, base = app_con(la.router, deps.get_super_admin, SUPER, "contratos_del_libro")
    c.app.include_router(rutas_contabilidad.router)
    ledger._indexes_ready = False
    monkeypatch.setattr(cobros_sin_acreditar, "_preguntarle_a_mercadopago", _MercadoPago())

    async def sembrar():
        await base.users.insert_many([
            {"user_id": "u1", "email": "uno@example.com", "name": "Uno", "role": "user",
             "balance_ris": to_decimal128("70.00"), "password_hash": "$2b$12$clave", "two_factor_secret": "JBSW"},
            {"user_id": "u2", "email": "dos@example.com", "name": "Dos", "role": "user",
             "balance_ris": to_decimal128("55.00")}])
        for uid, tipo, monto, sentido in (("u1", "recarga_pix", "100", "credit"), ("u1", "envio_ves", "30", "debit"),
                                          ("u2", "recarga_pix", "40", "credit"),
                                          ("u_ya_no_existe", "recarga_pix", "12", "credit")):
            await ledger.record_ris_entry(user_id=uid, movement_type=tipo, amount=monto, direction=sentido,
                                          reference_kind="transaction", reference_id=f"tx_{uid}_{tipo}",
                                          counterparty={"full_name": "Luis Pérez", "bank": "Banesco"},
                                          metadata={"origen": "prueba"})
        await base.ledger.insert_one({
            "entry_id": "led_mal", "created_at": HOY.isoformat(), "book": "RIS", "user_id": "u2",
            "movement_type": "movimiento_raro", "direction": "credit", "amount": to_decimal128("0"),
            "signed_amount": to_decimal128("0"), "currency": "RIS", "account": "balance_ris"})
        await base.bank_accounts.insert_many([
            {"bank_id": "b_brl", "name": "Banco en reales", "currency": "BRL", "balance": to_decimal128("500.00"),
             "created_by": "u_quien_lo_cargo", "created_at": "2026-09-01"},
            {"bank_id": "b_mp", "name": "Pasarela", "currency": "BRL", "balance": to_decimal128("20.00"),
             "is_gateway": True, "created_at": "2026-09-01"},
            {"bank_id": "b_ves", "name": "Banesco", "currency": "VES", "balance": to_decimal128("9000.00"),
             "created_by": "u_quien_lo_cargo", "created_at": "2026-09-01"}])
        await base.gestor_pix_payments.insert_one({
            "payment_id": "gpix_1", "mp_payment_id": "mp_1", "client_name": "Ana", "gestor_id": "u_gestor",
            "amount_ris": to_decimal128("150.00"), "amount_brl": to_decimal128("150.00"), "status": "expired",
            "created_at": HOY - timedelta(days=1)})
        await base.card_payments.insert_one({
            "payment_id": "card_1", "user_id": "u1", "amount_ris": to_decimal128("150.00"),
            "total_charged_brl": to_decimal128("150.00"), "status": "approved", "mp_payment_id": "mp_2",
            "created_at": HOY - timedelta(days=1)})
    ya(sembrar())
    return c, base


def test_LOS_TRES_CONTROLES_SON_SU_SERVICIO_TAL_CUAL(libro):
    from services import contabilidad
    c, _ = libro
    reco = c.get("/admin/ledger/reconciliacion")
    _igual_a_llamarla_directo(reco, ya(contabilidad.reconciliacion(libro="RIS", limite=200)))
    assert reco.json()["descuadres"] and reco.json()["lineas_sin_usuario"], "los datos no llenaron las listas"
    integ = c.get("/admin/ledger/integridad")
    _igual_a_llamarla_directo(integ, ya(contabilidad.integridad(libro=None)))
    assert {h["clave"] for h in integ.json()["hallazgos"]} >= {"monto_cero", "sin_clasificar"}
    pozo = c.get("/admin/ledger/pozo")
    _igual_a_llamarla_directo(pozo, ya(contabilidad.conciliacion_pozo()))
    assert pozo.json()["activo"]["cuentas"] and pozo.json()["capital_de_trabajo"]


def test_EL_DIARIO_EL_MAYOR_Y_EL_BALANCE_SON_SU_SERVICIO_TAL_CUAL(libro):
    from services import contabilidad
    c, _ = libro
    q = f"desde={DESDE}&hasta={HASTA}"
    diario = c.get(f"/admin/ledger/diario?{q}")
    _igual_a_llamarla_directo(diario, ya(contabilidad.libro_diario(
        desde=DESDE, hasta=HASTA, libro=None, user_id=None, movement_type=None, tz_min=0, limite=100, saltear=0)))
    assert diario.json()["asientos"][0]["debe"]["codigo"]
    mayor = c.get(f"/admin/ledger/mayor?{q}")
    _igual_a_llamarla_directo(mayor, ya(contabilidad.libro_mayor(desde=DESDE, hasta=HASTA, libro=None, tz_min=0)))
    assert any(cuenta["movimientos"] for cuenta in mayor.json()["cuentas"])
    balance = c.get(f"/admin/ledger/balance?{q}")
    _igual_a_llamarla_directo(balance, ya(contabilidad.balance_de_comprobacion(
        desde=DESDE, hasta=HASTA, libro=None, tz_min=0)))
    # Con contrato, el CSV sigue saliendo como archivo y no como JSON.
    csv = c.get(f"/admin/ledger/balance?{q}&formato=csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")


def test_EL_PLAN_Y_LAS_RUTAS_VIEJAS(libro):
    from _lote_c_comun import SUPER
    from routes import ledger_admin as la
    c, _ = libro
    _igual_a_llamarla_directo(c.get("/admin/ledger/plan-de-cuentas"), ya(la.plan_de_cuentas(admin=SUPER)))
    viejo = c.get("/admin/ledger/reconcile")
    _igual_a_llamarla_directo(viejo, ya(la.reconcile(admin=SUPER)))
    assert viejo.json()["mismatches"], "Dos no cuadra y tiene que aparecer"
    lineas = c.get("/admin/ledger/entries?user_id=u1")
    _igual_a_llamarla_directo(lineas, ya(la.list_entries(user_id="u1", limit=100, admin=SUPER)))
    (una, *_) = lineas.json()["entries"]
    assert una["counterparty"]["full_name"] == "Luis Pérez" and una["reference"]["kind"] == "transaction"
    assert una["amount"] in (30.0, 100.0), "la plata sale como número"


def test_EL_COFRE_Y_SUS_DOS_BOTONES(libro):
    from services import cofre
    c, base = libro
    _igual_a_llamarla_directo(c.get("/admin/ledger/cofre"), ya(cofre.revisar(base)))
    nueva = c.post("/admin/ledger/cofre/llave-nueva")
    assert nueva.status_code == 200 and set(nueva.json()) == {"llave", "huella"}, "la llave nueva sale, a propósito"
    cotejo = c.post("/admin/ledger/cofre/cotejar", json={"llave": nueva.json()["llave"]})
    _igual_a_llamarla_directo(cotejo, ya(cofre.cotejar(base, nueva.json()["llave"])))


def test_LOS_COBROS_SIN_ACREDITAR_SON_SU_SERVICIO_TAL_CUAL(libro):
    from services import cobros_sin_acreditar
    c, base = libro
    r = c.get("/admin/ledger/cobros-sin-acreditar")
    directo = ya(cobros_sin_acreditar.revisar(base))
    # La ventana se calcula con el reloj: entre las dos llamadas pasan unos
    # milisegundos, y eso no es un campo que el contrato se coma.
    from fastapi.encoders import jsonable_encoder
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    for k in ("desde", "hasta"):
        assert cuerpo.pop(k) and directo.pop(k)
    assert cuerpo == jsonable_encoder(directo)
    assert cuerpo["cobros"] and cuerpo["descuadres"] is not None


def test_LOS_BANCOS_DE_LA_CONTABILIDAD_SIN_QUIEN_LOS_CARGO(libro):
    c, _ = libro
    r = c.get("/admin/accounting/banks")
    assert r.status_code == 200, r.text
    assert "u_quien_lo_cargo" not in r.text
    ves = next(b for b in r.json() if b["bank_id"] == "b_ves")
    assert ves == {"bank_id": "b_ves", "name": "Banesco", "currency": "VES", "balance": 9000.0,
                   "created_at": "2026-09-01"}


def test_NINGUNA_RUTA_DEL_LIBRO_DEJA_SALIR_UN_SECRETO_DEL_USUARIO(libro):
    c, _ = libro
    for u in ("/admin/ledger/reconciliacion", "/admin/ledger/reconcile", "/admin/ledger/entries?user_id=u1",
              f"/admin/ledger/diario?desde={DESDE}&hasta={HASTA}", "/admin/ledger/pozo"):
        r = c.get(u)
        assert r.status_code == 200 and "$2b$12$clave" not in r.text and "JBSW" not in r.text, u


# ══════════════════════════════════════════════════════════════════════════
# El borrado total, lo escondido y el registro de lo que se hizo
# ══════════════════════════════════════════════════════════════════════════

A = "routes/admin.py"
DEL_BORRADO = [
    ("GET", "/wipe-all/preview", "VistaPreviaDelBorrado"),
    ("POST", "/wipe-all", "BorradoTotal"),
    ("GET", "/hidden-transactions", "OperacionesEscondidas"),
    ("POST", "/restore-transactions", "OperacionesRestauradas"),
    ("GET", "/audit-log", "RegistroDeAccionesSensibles"),
]


@pytest.mark.parametrize("metodo,camino,modelo", DEL_BORRADO, ids=[f"{m} {c}" for m, c, _ in DEL_BORRADO])
def test_EL_BORRADO_Y_LO_ESCONDIDO_TIENEN_CONTRATO(metodo, camino, modelo):
    ruta = _ruta(A, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True
    claves = _claves(A, metodo, camino, None)
    assert claves, f"no encontré qué devuelve {camino}"
    faltan = claves - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


def test_LO_QUE_ESCRIBE_EL_REGISTRO_ESTA_EN_SU_CONTRATO():
    """El registro devuelve cada línea como se guardó: sus campos son los que
    escribe `_record_audit`, el único que escribe ahí."""
    import ast
    import pathlib
    from models.panel_libro import AccionSensible
    arbol = ast.parse((pathlib.Path(__file__).resolve().parent.parent / A).read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_record_audit"]
    (d,) = [n for n in ast.walk(f) if isinstance(n, ast.Dict)][:1]
    claves = {k.value for k in d.keys if isinstance(k, ast.Constant)}
    assert len(claves) >= 5 and claves <= set(AccionSensible.model_fields), sorted(claves)


def test_LO_QUE_LEEN_LOS_BOTONES_DE_BORRAR_Y_RESTAURAR():
    from _lote_c_comun import fuente
    from models.panel_libro import BorradoTotal, ContabilidadBorrada, OperacionEscondida, OperacionesRestauradas
    lee_el_boton = {"transaction_id", "display_id", "type", "amount_input", "amount_output", "currency",
                    "created_at", "user_name"}
    assert lee_el_boton <= set(OperacionEscondida.model_fields)
    assert "restored" in OperacionesRestauradas.model_fields
    assert "total_deleted" in BorradoTotal.model_fields and "total_deleted" in ContabilidadBorrada.model_fields
    texto = fuente("components/common/RestoreButton.jsx") + fuente("components/common/WipeButton.jsx")
    assert not [c for c in lee_el_boton | {"restored", "total_deleted"} if c not in texto]


@pytest.fixture
def borrado():
    from conftest import ensenarle_decimal128_a_mongomock
    from _lote_c_comun import SUPER, app_con
    from routes import admin as rutas_admin
    from routes import dependencies as deps
    from services import ledger
    from services.money import to_decimal128
    ensenarle_decimal128_a_mongomock()
    c, base = app_con(rutas_admin.router, deps.get_super_admin, SUPER, "contratos_del_borrado")
    ledger._indexes_ready = False

    async def sembrar():
        await base.users.insert_one({"user_id": "u1", "email": "uno@example.com", "name": "Uno", "role": "user",
                                     "balance_ris": to_decimal128("70.00"), "password_hash": "$2b$12$clave"})
        await base.transactions.insert_many([
            {"transaction_id": "tx_e1", "display_id": "000901", "user_id": "u1", "type": "withdrawal",
             "status": "completed", "amount_input": to_decimal128("60.00"), "amount_output": to_decimal128("6600.00"),
             "currency": "RIS", "created_at": HOY, "hidden_from_admin": True,
             "proof_image": "data:image/jpeg;base64," + "FOTO" * 20, "nota_interna": "revisar"},
            {"transaction_id": "tx_e2", "display_id": "000902", "user_id": "u1", "type": "recharge",
             "status": "completed", "amount_input": to_decimal128("40.00"), "created_at": HOY}])
    ya(sembrar())
    return c, base


def test_ESCONDER_Y_RESTAURAR_POR_HTTP(borrado):
    from _lote_c_comun import SUPER
    from routes import admin as rutas_admin
    c, _ = borrado
    r = c.get("/admin/hidden-transactions")
    _igual_a_llamarla_directo(r, ya(rutas_admin.get_hidden_transactions(limit=500, admin=SUPER)))
    (fila,) = r.json()["transactions"]
    assert fila["amount_input"] == 60.0 and fila["user_name"] == "Uno"
    assert "FOTO" not in r.text and "revisar" not in r.text and "$2b$12$clave" not in r.text
    r = c.post("/admin/restore-transactions", json={"transaction_ids": ["tx_e1"]})
    assert r.json() == {"success": True, "message": "1 transacciones restauradas", "restored": 1}


def test_LA_VISTA_PREVIA_EL_BORRADO_Y_EL_REGISTRO_POR_HTTP(borrado):
    from _lote_c_comun import SUPER
    from routes import admin as rutas_admin
    c, _ = borrado
    previa = c.get("/admin/wipe-all/preview")
    _igual_a_llamarla_directo(previa, ya(rutas_admin.wipe_all_preview(admin=SUPER)))
    assert previa.json()["se_borrarian"] and previa.json()["saldos_que_se_ponen_en_cero"]["balance_ris"] == "70.00"
    r = c.post("/admin/wipe-all", json={"confirmation": "CONFIRMAR"})
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["success"] is True and hecho["total_deleted"] >= 2 and hecho["deleted"]["transactions"] == 2
    assert hecho["libro_conservado"] is True and "revisados" in hecho["cierre_del_libro"]
    registro = c.get("/admin/audit-log")
    (linea,) = registro.json()["entries"]
    assert linea["action"] == "wipe_all" and linea["admin_user_id"] == SUPER.user_id
    assert linea["extra"]["saldos_reseteados"] and linea["deleted"]["transactions"] == 2
