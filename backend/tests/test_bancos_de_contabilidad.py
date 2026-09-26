"""
tests/test_bancos_de_contabilidad.py — Crear y borrar bancos desde la pantalla
de Bancos, con las reglas que antes no hacían falta porque nadie llegaba ahí
sin saber programar. Ver `routes/accounting.py` (`create_bank`,
`_por_que_no_se_puede_borrar`) y `frontend/src/components/admin/Bancos.jsx`.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def bancos():
    from _lote_c_comun import SUPER, app_con
    from routes import accounting
    from routes import dependencies as deps
    from conftest import ensenarle_decimal128_a_mongomock
    ensenarle_decimal128_a_mongomock()
    c, base = app_con(accounting.router, deps.get_super_admin, SUPER, "bancos_de_contabilidad")
    return c, base


def _crear(c, **cuerpo):
    return c.post("/admin/accounting/banks", json={"currency": "VES", **cuerpo})


# ══════════════════════════════════════════════════════════════════════════
# Crear
# ══════════════════════════════════════════════════════════════════════════

def test_EL_SALDO_INICIAL_SE_GUARDA_EXACTO_COMO_DECIMAL(bancos):
    from bson.decimal128 import Decimal128
    c, base = bancos
    r = _crear(c, name="  Banco   de Venezuela ", initial_balance="1234.56")
    assert r.status_code == 200, r.text
    doc = ya(base.bank_accounts.find_one({"bank_id": r.json()["bank_id"]}))
    assert isinstance(doc["balance"], Decimal128) and doc["balance"].to_decimal() == Decimal("1234.56")
    assert doc["name"] == "Banco de Venezuela", "los espacios de más no quedan en el nombre"
    assert doc["currency"] == "VES"


def test_TAMBIEN_ACEPTA_EL_NUMERO_COMO_ANTES_DE_LA_PANTALLA(bancos):
    c, base = bancos
    r = c.post("/admin/accounting/banks", json={"name": "Itaú", "currency": "brl", "initial_balance": 500})
    assert r.status_code == 200, r.text
    doc = ya(base.bank_accounts.find_one({"bank_id": r.json()["bank_id"]}))
    assert doc["currency"] == "BRL" and doc["balance"].to_decimal() == Decimal("500.00")


@pytest.mark.parametrize("cuerpo,dice", [
    ({"name": " ", "initial_balance": "0"}, "nombre"),
    ({"name": "X" * 61}, "nombre"),
    ({"name": "Banco", "currency": "USD"}, "VES o BRL"),
    ({"name": "Banco", "initial_balance": "-10"}, "negativo"),
    ({"name": "Banco", "initial_balance": "1.500,00"}, "no es un monto"),
    ({"name": "Banco", "initial_balance": "NaN"}, "negativo"),
], ids=["sin-nombre", "nombre-largo", "moneda", "negativo", "con-miles", "nan"])
def test_LO_QUE_NO_TIENE_SENTIDO_SE_RECHAZA_DICIENDO_POR_QUE(bancos, cuerpo, dice):
    """`to_decimal` convierte en cero lo que no entiende: «1.500,00» mal
    escrito habría creado el banco en cero sin avisar."""
    c, base = bancos
    r = _crear(c, **cuerpo)
    assert r.status_code == 400, r.text
    assert dice in r.json()["detail"]
    assert ya(base.bank_accounts.count_documents({})) == 0


def test_DOS_BANCOS_EN_BOLIVARES_QUE_SE_CONFUNDEN_POR_EL_NOMBRE_NO(bancos):
    """La recarga encuentra el banco por el nombre: con dos que reducen igual,
    no sabría a cuál ir."""
    c, _ = bancos
    assert _crear(c, name="Banesco").status_code == 200
    r = _crear(c, name="BANCO BANESCO")
    assert r.status_code == 409 and "Banesco" in r.json()["detail"]
    # En reales nadie los busca por el nombre: se puede repetir.
    assert c.post("/admin/accounting/banks", json={"name": "Banesco", "currency": "BRL"}).status_code == 200


def test_LA_RECARGA_Y_LA_PANTALLA_REDUCEN_EL_NOMBRE_CON_LA_MISMA_FUNCION():
    """Si cada una tuviera su copia, podrían separarse: la pantalla dejaría
    cargar un nombre que la recarga después confunde."""
    import ast
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    for archivo in ("routes/transactions.py", "routes/accounting.py"):
        arbol = ast.parse((raiz / archivo).read_text("utf-8"))
        propias = [n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and "clave" in n.name]
        assert not propias, f"{archivo} tiene su propia función para comparar nombres: {propias}"
    from services import bancos as servicio
    assert servicio.clave_del_nombre("Banco de Venezuela") == servicio.clave_del_nombre("banco_venezuela")


def test_CREAR_QUEDA_EN_LA_AUDITORIA(bancos):
    c, base = bancos
    bid = _crear(c, name="Mercantil", initial_balance="10").json()["bank_id"]
    (linea,) = ya(base.auditoria.find({"accion": "contabilidad.banco_creado"}).to_list(10))
    assert linea["objetivo"]["id"] == bid


# ══════════════════════════════════════════════════════════════════════════
# Borrar
# ══════════════════════════════════════════════════════════════════════════

def test_UN_BANCO_QUE_NUNCA_SE_USO_SE_BORRA_Y_QUEDA_ANOTADO(bancos):
    c, base = bancos
    bid = _crear(c, name="Cargado por error").json()["bank_id"]
    assert c.delete(f"/admin/accounting/banks/{bid}").json() == {"message": "Banco eliminado"}
    assert ya(base.bank_accounts.count_documents({})) == 0
    assert ya(base.auditoria.count_documents({"accion": "contabilidad.banco_borrado", "objetivo.id": bid})) == 1


def _no_se_borra(c, base, bid, dice):
    r = c.delete(f"/admin/accounting/banks/{bid}")
    assert r.status_code == 409, r.text
    assert dice in r.json()["detail"]
    assert ya(base.bank_accounts.count_documents({"bank_id": bid})) == 1, "el banco sigue ahí"


def test_CON_MOVIMIENTOS_NO_SE_BORRA(bancos):
    c, base = bancos
    bid = _crear(c, name="Con historia").json()["bank_id"]
    ya(base.bank_ledger.insert_one({"bank_id": bid, "type": "entrada", "concept": "x"}))
    _no_se_borra(c, base, bid, "1 movimiento anotado")


def test_CON_SALDO_NO_SE_BORRA(bancos):
    c, base = bancos
    bid = _crear(c, name="Con plata", initial_balance="1500.5").json()["bank_id"]
    _no_se_borra(c, base, bid, "Tiene saldo (1.500,50 VES)")


def test_CON_RECARGAS_ESPERANDO_NO_SE_BORRA(bancos):
    c, base = bancos
    bid = _crear(c, name="Esperando").json()["bank_id"]
    ya(base.transactions.insert_one({"transaction_id": "tx_1", "type": "recharge_ves", "status": "pending",
                                     "destination_bank_id": bid}))
    _no_se_borra(c, base, bid, "1 recarga esperando")


def test_LA_CUENTA_DE_UNA_PASARELA_NO_SE_BORRA(bancos):
    from services.money import to_decimal128
    c, base = bancos
    ya(base.bank_accounts.insert_one({"bank_id": "bank_pasarela", "name": "Mercado Pago", "currency": "BRL",
                                      "balance": to_decimal128("0"), "is_gateway": True}))
    _no_se_borra(c, base, "bank_pasarela", "pasarela")
    lista = c.get("/admin/accounting/banks").json()
    assert lista[0]["is_gateway"] is True, "la pantalla necesita saberlo para no ofrecer el botón"


def test_UN_BANCO_QUE_NO_EXISTE_ES_404(bancos):
    c, _ = bancos
    assert c.delete("/admin/accounting/banks/bank_nada").status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# La pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_LA_PANTALLA_ESTA_EN_CONTABILIDAD_Y_PREGUNTA_SIN_CUADROS_DEL_NAVEGADOR():
    from _lote_c_comun import fuente, sin_comentarios
    # Las secciones y sus grupos viven en seccionesDelPanel.js desde que el
    # panel llegó a su tope de líneas; el dibujo sigue en AdminPanel.jsx.
    panel = sin_comentarios(fuente("pages/AdminPanel.jsx") + "\n"
                            + fuente("components/admin/seccionesDelPanel.js"))
    assert "{ key: 'bancos'" in panel and "superAdminOnly: true" in panel.split("{ key: 'bancos'")[1].split("\n")[0]
    # Desde que el panel se separó por servicio, Bancos vive en la Tesorería
    # de Remesas: son las cuentas de donde salen sus retiros y a donde entran
    # sus recargas. Ver GRUPOS en seccionesDelPanel.js.
    assert "hijas: ['bancos', 'cobros']" in panel, "la pestaña tiene que estar en la Tesorería de Remesas"
    assert "<Bancos onCambio={cargarBancos} />" in panel, \
        "sin avisarle al panel, Retiros y Recargas no ven el banco nuevo hasta recargar"
    pantalla = sin_comentarios(fuente("components/admin/Bancos.jsx"))
    assert "confirmar(" in pantalla and "window.confirm" not in pantalla and "window.prompt" not in pantalla
    assert "initial_balance: inicial" in pantalla and "parseFloat" not in pantalla, \
        "el saldo inicial viaja como texto, sin pasar por un float"
    assert "limpio.includes(',') ? limpio.replace(/\\./g, '')" in pantalla, \
        "con coma decimal, los puntos son de miles: «1.500,00» tiene que llegar como 1500.00"
