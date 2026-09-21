"""
tests/test_reporte_ejecutivo_sin_tasa.py — si falta una tasa, el reporte
ejecutivo dice cuál y dónde se configura, en vez de «error inesperado».

POR QUE ESTO ES UN TEST

    `services/accounting_engine.py` ya tenía la excepción que lo dice
    (`TasaSinConfigurar`, con la clave y el motivo). La ruta no la atrapaba:
    llegaba al manejador genérico y el panel mostraba «error inesperado». La
    persona que lo veía iba a buscar un fallo donde había una configuración
    pendiente. Lo encontró el barrido de rutas de la revisión general.
"""
import pytest

from _lote_c_comun import app_con, SUPER


@pytest.fixture
def cliente():
    from routes import accounting_v2
    from routes import dependencies as deps
    c, _ = app_con(accounting_v2.router, deps.get_super_admin, SUPER, "reporte")
    return c


def _que_falte_la_tasa(monkeypatch):
    from routes import accounting_v2
    from services.accounting_engine import TasaSinConfigurar

    async def falta(*a, **k):
        raise TasaSinConfigurar("ris_to_ves", "para valuar la circulación")
    monkeypatch.setattr(accounting_v2.ExecutiveReportService, "generate_report", falta)


def test_sin_tasa_contesta_503_y_dice_cual_falta(cliente, monkeypatch):
    _que_falte_la_tasa(monkeypatch)
    r = cliente.get("/admin/accounting/v2/executive-report")
    assert r.status_code == 503, r.text
    detalle = r.json()["detail"]
    assert "ris_to_ves" in detalle
    assert "Tasas" in detalle, "tiene que decir dónde se configura"


def test_un_rango_invalido_sigue_siendo_400(cliente, monkeypatch):
    """La guarda nueva no se come la que ya estaba."""
    from routes import accounting_v2

    async def mal(*a, **k):
        raise ValueError("rango inválido")
    monkeypatch.setattr(accounting_v2.ExecutiveReportService, "generate_report", mal)
    r = cliente.get("/admin/accounting/v2/executive-report")
    assert r.status_code == 400, r.text
