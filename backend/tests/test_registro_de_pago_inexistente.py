"""
tests/test_registro_de_pago_inexistente.py — pedir la ficha de un registro de
pago con un identificador que no existe es un 404, no un «error inesperado».

POR QUE ESTO ES UN TEST

    La ruta armaba `ObjectId(record_id)` a secas. Con un identificador que no
    tiene esa forma —una dirección escrita a mano, un enlace viejo— la
    conversión lanzaba y el panel mostraba «error inesperado», que manda a
    quien lo ve a buscar un fallo donde sólo hay un registro que no existe.
    Lo encontró el barrido de rutas de la revisión general.
"""
import pytest

from _lote_c_comun import app_con, ya, SUPER


@pytest.fixture
def cliente(monkeypatch):
    import admin_routes
    from routes import dependencies as deps
    c, base = app_con(admin_routes.admin_router, deps.get_admin_user, SUPER, "registros")
    # `admin_routes` abre su propia conexión y no pasa por el proxy de la base.
    monkeypatch.setattr(admin_routes, "db", base)
    return c


def test_un_identificador_sin_forma_de_objectid_es_404(cliente):
    r = cliente.get("/api/admin/payment-records/esto-no-es-un-id")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Registro no encontrado"


def test_un_identificador_bien_formado_que_no_existe_tambien_es_404(cliente):
    r = cliente.get("/api/admin/payment-records/64b7f0c2a1b2c3d4e5f60718")
    assert r.status_code == 404, r.text


def test_LA_GUARDA_NO_TAPA_UN_REGISTRO_QUE_SI_EXISTE(cliente, monkeypatch):
    """Que rechazar lo inválido no rechace lo válido."""
    import admin_routes
    from bson import ObjectId
    _id = ObjectId()
    ya(admin_routes.db.admin_payment_records.insert_one({"_id": _id, "nota": "hola"}))
    r = cliente.get(f"/api/admin/payment-records/{_id}")
    assert r.status_code == 200, r.text
    assert r.json()["nota"] == "hola"
