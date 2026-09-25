"""
tests/test_datos_de_cobro.py — A qué cuenta le decimos al cliente que
transfiera: se carga en el panel, se revisa antes de guardarse, y el cliente
ve sólo lo publicado y sólo lo necesario. Ver `services/bancos.py`
(`normalizar_cobro`, `para_el_cliente`), `routes/accounting.guardar_datos_de_cobro`
y `routes/transactions.bancos_para_transferir`.

Los datos de prueba son inventados: ni el titular ni la cédula ni las cuentas
existen.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

BIEN = {"codigo": "0134", "titular": "Empresa de Ejemplo C.A.", "documento": "j-12345678-9",
        "numero_cuenta": "0134 0000 11 2222333344", "tipo_cuenta": "corriente", "telefono": "+58 414 555 0000"}


def ya(c):
    return asyncio.run(c)


# ══════════════════════════════════════════════════════════════════════════
# Lo que se revisa antes de guardar
# ══════════════════════════════════════════════════════════════════════════

def test_LO_QUE_SE_ESCRIBE_A_MANO_QUEDA_EN_UNA_SOLA_FORMA():
    from services.bancos import normalizar_cobro
    assert normalizar_cobro(BIEN) == {
        "codigo": "0134", "titular": "Empresa de Ejemplo C.A.", "documento": "J-12345678-9",
        "numero_cuenta": "01340000112222333344", "tipo_cuenta": "Corriente", "telefono": "04145550000"}


@pytest.mark.parametrize("cambio,dice", [
    ({"codigo": "134"}, "4 dígitos"),
    ({"titular": "  "}, "titular"),
    ({"documento": "12345678"}, "letra"),
    ({"numero_cuenta": "0134000011222233334"}, "tiene 19"),
    ({"numero_cuenta": "01020000112222333344"}, "¿Es la cuenta de otro banco?"),
    ({"tipo_cuenta": "plazo fijo"}, "corriente o de ahorro"),
    ({"telefono": "02125550000"}, "celular"),
    ({"numero_cuenta": "", "telefono": ""}, "al menos una forma de pago"),
], ids=["codigo", "titular", "documento-sin-letra", "cuenta-corta", "cuenta-de-otro-banco", "tipo",
        "telefono-fijo", "sin-forma-de-pago"])
def test_UN_DATO_QUE_MANDARIA_LA_PLATA_A_OTRO_LADO_SE_RECHAZA(cambio, dice):
    from services.bancos import DatosDeCobroInvalidos, normalizar_cobro
    with pytest.raises(DatosDeCobroInvalidos, match=dice):
        normalizar_cobro({**BIEN, **cambio})


def test_ALCANZA_CON_UNA_DE_LAS_DOS_FORMAS_DE_PAGO():
    from services.bancos import normalizar_cobro
    solo_movil = normalizar_cobro({**BIEN, "numero_cuenta": ""})
    assert solo_movil["numero_cuenta"] == "" and solo_movil["tipo_cuenta"] == "" and solo_movil["telefono"]
    solo_cuenta = normalizar_cobro({**BIEN, "telefono": ""})
    assert solo_cuenta["telefono"] == "" and solo_cuenta["numero_cuenta"]


# ══════════════════════════════════════════════════════════════════════════
# El panel y el cliente, por HTTP
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


@pytest.fixture
def app():
    from _lote_c_comun import SUPER, app_con
    from routes import accounting, transactions
    from routes import dependencies as deps
    from services.money import to_decimal128
    c, base = app_con(accounting.router, deps.get_super_admin, SUPER, "datos_de_cobro")
    c.app.include_router(transactions.router)
    c.app.dependency_overrides[deps.get_current_user] = lambda: SUPER
    ya(base.bank_accounts.insert_many([
        {"bank_id": "b_ves", "name": "Banesco", "currency": "VES", "balance": to_decimal128("9000"),
         "created_by": "u_ID_INTERNO"},
        {"bank_id": "b_ves2", "name": "Mercantil", "currency": "VES", "balance": to_decimal128("0")},
        {"bank_id": "b_brl", "name": "Itaú", "currency": "BRL", "balance": to_decimal128("10")},
        {"bank_id": "b_pasarela", "name": "Pasarela", "currency": "VES", "balance": to_decimal128("0"),
         "is_gateway": True},
    ]))
    return c, base


def test_GUARDAR_DEJA_LOS_DATOS_LIMPIOS_Y_QUEDA_EN_LA_AUDITORIA(app):
    c, base = app
    r = c.put("/admin/accounting/banks/b_ves/cobro", json={**BIEN, "publicado": True})
    assert r.status_code == 200, r.text
    assert r.json()["cobro"]["numero_cuenta"] == "01340000112222333344" and r.json()["cobro"]["publicado"] is True
    guardado = ya(base.bank_accounts.find_one({"bank_id": "b_ves"}))["cobro"]
    assert guardado["documento"] == "J-12345678-9" and guardado["telefono"] == "04145550000"
    (linea,) = ya(base.auditoria.find({"accion": "contabilidad.banco_cobro"}).to_list(5))
    assert linea["objetivo"]["id"] == "b_ves" and linea["despues"]["numero_cuenta"] == "01340000112222333344"
    lista = c.get("/admin/accounting/banks").json()
    assert next(b for b in lista if b["bank_id"] == "b_ves")["cobro"]["publicado"] is True, \
        "el panel necesita ver los datos para editarlos"


def test_UN_DATO_MALO_NO_SE_GUARDA(app):
    c, base = app
    r = c.put("/admin/accounting/banks/b_ves/cobro", json={**BIEN, "numero_cuenta": "01020000112222333344"})
    assert r.status_code == 400 and "otro banco" in r.json()["detail"]
    assert "cobro" not in ya(base.bank_accounts.find_one({"bank_id": "b_ves"}))


@pytest.mark.parametrize("bank_id,codigo,dice", [
    ("b_brl", 400, "bolívares"), ("b_pasarela", 400, "pasarela"), ("b_nada", 404, "no encontrado"),
], ids=["en-reales", "pasarela", "no-existe"])
def test_SOLO_SE_CARGAN_EN_BANCOS_EN_BOLIVARES_QUE_NO_SON_PASARELA(app, bank_id, codigo, dice):
    c, _ = app
    r = c.put(f"/admin/accounting/banks/{bank_id}/cobro", json={**BIEN, "publicado": True})
    assert r.status_code == codigo and dice in r.json()["detail"].lower()


def test_EL_CLIENTE_VE_SOLO_LO_PUBLICADO_Y_SOLO_LO_NECESARIO(app):
    c, base = app
    c.put("/admin/accounting/banks/b_ves/cobro", json={**BIEN, "publicado": True})
    c.put("/admin/accounting/banks/b_ves2/cobro", json={**BIEN, "codigo": "0105",
                                                       "numero_cuenta": "01050000112222333344", "publicado": False})
    r = c.get("/bancos-para-transferir")
    assert r.status_code == 200, r.text
    assert r.json() == [{
        "bank_id": "b_ves", "name": "Banesco", "codigo": "0134",
        "transferencia": {"titular": "Empresa de Ejemplo C.A.", "documento": "J-12345678-9",
                          "numero_cuenta": "01340000112222333344", "tipo_cuenta": "Corriente"},
        "pago_movil": {"telefono": "04145550000", "documento": "J-12345678-9"},
    }]
    for nada in ("9000", "balance", "u_ID_INTERNO", "Mercantil"):
        assert nada not in r.text, f"{nada} le llegó al cliente"


def test_SIN_TELEFONO_NO_SE_OFRECE_PAGO_MOVIL(app):
    c, _ = app
    c.put("/admin/accounting/banks/b_ves/cobro", json={**BIEN, "telefono": "", "publicado": True})
    (banco,) = c.get("/bancos-para-transferir").json()
    assert banco["pago_movil"] is None and banco["transferencia"]["numero_cuenta"]


def test_LO_TOCADO_A_MANO_EN_LA_BASE_NO_LE_LLEGA_AL_CLIENTE(app):
    """Se revisa también al servir: un documento editado en la base sin pasar
    por el panel —una cuenta de 19 dígitos, una pasarela publicada— no se
    muestra."""
    c, base = app
    ya(base.bank_accounts.update_one({"bank_id": "b_ves"}, {"$set": {"cobro": {
        **BIEN, "numero_cuenta": "0134000011222233334", "publicado": True}}}))
    ya(base.bank_accounts.update_one({"bank_id": "b_pasarela"}, {"$set": {"cobro": {
        **BIEN, "publicado": True}}}))
    assert c.get("/bancos-para-transferir").json() == []


def test_LA_PANTALLA_DE_BANCOS_CARGA_LOS_DATOS_Y_AVISA_SI_NINGUNO_ESTA_PUBLICADO():
    from _lote_c_comun import fuente, sin_comentarios
    pantalla = sin_comentarios(fuente("components/admin/Bancos.jsx"))
    assert "api.put(`/admin/accounting/banks/${banco.bank_id}/cobro`, datos)" in pantalla
    assert 'data-testid="bancos-sin-publicar"' in pantalla
    assert "b.currency === 'VES' && b.cobro?.publicado" in pantalla
