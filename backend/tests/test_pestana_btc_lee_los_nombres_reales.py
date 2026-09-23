"""
tests/test_pestana_btc_lee_los_nombres_reales.py — la pestaña «BTC Lightning»
del panel muestra la cédula y el teléfono del beneficiario.

Leía `beneficiario_data.cedula` y `.phone`, que no existen: un beneficiario se
guarda con `id_document` y `phone_number` (`models/requests.BeneficiaryCreate`).
Cada orden salía con «CI: N/A» y, en pago móvil, sin teléfono, y quien pagaba
tenía que ir a buscarlos a otro lado.

El frontend no tiene tests propios, así que esto lee la pantalla. Y comprueba
las otras dos puntas: que esos nombres sean los del formulario, y que la lista
de lo permitido del backend los deje pasar.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PANEL = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "AdminPanel.jsx"


def _tarjeta_de_la_orden():
    fuente = PANEL.read_text(encoding="utf-8")
    inicio = fuente.index(">BENEFICIARIO<")
    return fuente[inicio:inicio + 3000]


def test_LA_TARJETA_LEE_LA_CEDULA_Y_EL_TELEFONO_CON_SUS_NOMBRES_REALES():
    tarjeta = _tarjeta_de_la_orden()
    assert "beneficiario_data?.id_document" in tarjeta, "la cédula se guarda como id_document"
    assert "beneficiario_data?.phone_number" in tarjeta, "el teléfono se guarda como phone_number"


def test_LOS_NOMBRES_QUE_LEE_SON_LOS_DEL_FORMULARIO_DEL_BENEFICIARIO():
    from models.requests import BeneficiaryCreate
    for campo in ("id_document", "phone_number", "bank", "account_number", "payment_type", "full_name"):
        assert campo in BeneficiaryCreate.model_fields, campo


def test_EL_BACKEND_LOS_DEJA_PASAR():
    from models.movimientos import LO_QUE_VE_DEL_BENEFICIARIO
    for campo in ("id_document", "phone_number", "cedula", "phone"):
        assert campo in LO_QUE_VE_DEL_BENEFICIARIO, campo
