"""
tests/test_cobro_pix_sin_vencimiento.py — un cobro pendiente sin fecha de
vencimiento no tumba la consulta de «¿tengo un cobro abierto?».

POR QUE ESTO ES UN TEST

    `/gestor/pix/active` restaba `expires_at - ahora` sin mirar si
    `expires_at` existía. Los dos lugares que escriben cobros lo ponen, así
    que hoy no pasa; pero un documento a mano o de una versión vieja dejaba a
    la pantalla de recarga sin poder saber si tiene un cobro abierto: 500.
    Ahora ese cobro se cierra como vencido —lo que le pasaría a cualquier
    cobro de más de siete minutos— y la consulta contesta. Lo encontró el
    barrido de rutas de la revisión general.
"""
from datetime import datetime, timedelta, timezone

import pytest

from _lote_c_comun import app_con, ya, User

GESTOR = User(user_id="u_gestor", name="Gestor", email="gestor@ejemplo.test", role="user")


@pytest.fixture
def cliente_y_base():
    from routes import gestor_pix
    return app_con(gestor_pix.router, gestor_pix.require_authenticated_user, GESTOR, "cobros")



def test_un_cobro_pendiente_sin_vencimiento_se_cierra_y_la_consulta_contesta(cliente_y_base):
    cliente, base = cliente_y_base
    ya(base.gestor_pix_payments.insert_one({
        "payment_id": "gpix_sin_fecha", "gestor_id": GESTOR.user_id, "status": "pending",
        "amount_ris": 50.0}))
    r = cliente.get("/gestor/pix/active")
    assert r.status_code == 200, r.text
    assert r.json() == {"has_active": False}
    doc = ya(base.gestor_pix_payments.find_one({"payment_id": "gpix_sin_fecha"}))
    assert doc["status"] == "expired"


def test_UN_COBRO_VIGENTE_SIGUE_SIENDO_ACTIVO(cliente_y_base):
    """Que cerrar el que no tiene fecha no cierre el que sí la tiene."""
    cliente, base = cliente_y_base
    ya(base.gestor_pix_payments.insert_one({
        "payment_id": "gpix_vigente", "gestor_id": GESTOR.user_id, "status": "pending",
        "amount_ris": 50.0, "amount_ves": 5500.0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}))
    r = cliente.get("/gestor/pix/active")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["has_active"] is True and j["payment_id"] == "gpix_vigente"
    assert 0 < j["expires_in_seconds"] <= 300
