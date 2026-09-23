"""
tests/test_sin_tasa_nocturna.py — la tasa nocturna (la «tasa automática») ya
no existe: la tasa es la que carga el super administrador, a cualquier hora,
en la pantalla y en la plata.

QUE ERA

    Fuera del horario laboral —de noche, los domingos y los feriados— el
    servidor le restaba un delta a BRL→VES y le sumaba otro a VES→BRL. Se
    aplicaba en cinco lugares a la vez: `/rate`, que es lo que muestra la
    pantalla, y cuatro de `routes/transactions.py` que convierten plata (el
    envío con saldo, la recarga en bolívares y las dos cotizaciones de pagar
    al final). Se configuraba desde una tarjeta del panel.

    Se eliminó entera, por decisión del dueño del proyecto: la tarjeta, sus
    dos rutas (`GET` y `POST /admin/auto-rate`), el módulo que hacía la cuenta
    (`services/rate_engine.py`) y el ajuste en los cinco lugares.

POR QUE ESTE ARCHIVO

    La configuración vieja puede seguir guardada en la base
    (`app_settings`, `setting_id: auto_rate`), incluso prendida. Si algo la
    volviera a leer —en uno solo de los cinco lugares—, la pantalla mostraría
    una tasa y la orden cobraría otra. Eso es lo que se vigila.
"""
import asyncio
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

JEFA = User(user_id="u_jefa", name="Jefa", email="jefa@ejemplo.test", role="super_admin")
TASA_BRL_VES, TASA_VES_BRL = 111.25, 141.75
_BACKEND = Path(__file__).resolve().parents[1]
_FRONT = _BACKEND.parent / "frontend" / "src"


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["sin_tasa_nocturna"]
    usar_base(m)
    ya(m.rates.insert_one({"ris_to_ves": TASA_BRL_VES, "ves_to_ris_rate": TASA_VES_BRL,
                           "brl_to_ris": 1.0, "usd_to_ves": 50.0}))
    # La configuración vieja, PRENDIDA y sin ningún día laboral: con la tasa
    # nocturna viva, esto ajustaba la tasa a toda hora.
    ya(m.app_settings.insert_one({"setting_id": "auto_rate", "enabled": True,
                                  "delta_brl_ves": 9.92, "delta_ves_brl": 5.0,
                                  "work_days": [], "work_start_hour": 8, "work_end_hour": 22}))
    return m


def como(quien, router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. La tasa pública es la cargada, con la configuración vieja prendida
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TASA_PUBLICA_ES_LA_CARGADA(base):
    from routes.basic import router
    r = como(None, router).get("/api/rate")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ris_to_ves"] == TASA_BRL_VES and d["ves_to_ris_rate"] == TASA_VES_BRL


def test_NO_QUEDA_RASTRO_DE_LA_TASA_NOCTURNA_EN_LA_RESPUESTA(base):
    from routes.basic import router
    d = como(None, router).get("/api/rate").json()
    for campo in ("is_off_hours", "auto_rate_enabled", "base_ris_to_ves", "base_ves_to_ris_rate"):
        assert campo not in d, campo


def test_EL_CONTRATO_PUBLICO_NO_DEJA_PASAR_LO_QUE_NO_NOMBRA():
    """La segunda capa, sola: si alguien vuelve a sumarle a la respuesta un
    campo de la tasa nocturna, el contrato no lo publica."""
    from models.reglas_publicas import LaTasa
    salida = LaTasa.model_validate({"ris_to_ves": 1.0, "is_off_hours": True,
                                    "auto_rate_enabled": True, "base_ris_to_ves": 2.0,
                                    "delta_interno": 9.92}).model_dump(exclude_unset=True)
    assert salida == {"ris_to_ves": 1.0}


# ══════════════════════════════════════════════════════════════════════════
# 2. Las rutas del panel ya no están
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("metodo", ["get", "post"])
def test_LAS_RUTAS_DE_LA_TASA_AUTOMATICA_NO_EXISTEN(base, metodo):
    from routes.admin import router
    r = getattr(como(JEFA, router), metodo)("/api/admin/auto-rate", **({"json": {"enabled": True}} if metodo == "post" else {}))
    assert r.status_code in (404, 405), r.text


# ══════════════════════════════════════════════════════════════════════════
# 3. Nada del código la vuelve a leer
# ══════════════════════════════════════════════════════════════════════════

def _codigo_del_servidor():
    for archivo in sorted(_BACKEND.rglob("*.py")):
        partes = archivo.relative_to(_BACKEND).parts
        if partes[0] in ("tests", "venv", ".venv") or "__pycache__" in partes:
            continue
        yield archivo, archivo.read_text(encoding="utf-8", errors="ignore")


def test_NADIE_LEE_LA_CONFIGURACION_VIEJA():
    """Leer `app_settings` con `setting_id: auto_rate` es la única forma de que
    la tasa nocturna vuelva sin que se note: la configuración sigue guardada."""
    lectores = []
    for archivo, fuente in _codigo_del_servidor():
        for n, linea in enumerate(fuente.splitlines(), 1):
            if linea.lstrip().startswith("#"):
                continue
            if re.search(r"""["']auto_rate["']""", linea):
                lectores.append(f"{archivo.relative_to(_BACKEND)}:{n}")
    assert not lectores, "algo vuelve a leer la configuración de la tasa nocturna: " + ", ".join(lectores)


def test_LA_GUARDA_DE_ARRIBA_NO_ESTA_CIEGA(tmp_path):
    """Que la búsqueda encuentre una lectura de verdad si la hubiera."""
    muestra = '    doc = await db.app_settings.find_one({"setting_id": "auto_rate"})\n'
    assert re.search(r"""["']auto_rate["']""", muestra)
    assert any(True for _ in _codigo_del_servidor()), "la guarda no está recorriendo ningún archivo"


def test_LOS_CUATRO_CALCULOS_DE_PLATA_USAN_LA_TASA_CARGADA():
    """El envío con saldo, la recarga en bolívares y las dos cotizaciones de
    pagar al final: la tasa que multiplican es la que leyeron de `db.rates`."""
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    assert "ris_to_ves = _base_rtv\n" in fuente           # envío con saldo
    assert "ves_to_ris = _base_vtr\n" in fuente           # recarga en bolívares
    assert "ris_to_ves = _base    # la de /api/rate" in fuente   # cotizar envío a Venezuela
    assert "ves_to_ris = _base\n" in fuente               # cotizar envío a Brasil


def test_EL_MODULO_DE_LA_TASA_NOCTURNA_NO_EXISTE():
    assert not (_BACKEND / "services" / "rate_engine.py").exists()


# ══════════════════════════════════════════════════════════════════════════
# 4. Las pantallas
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TARJETA_NO_ESTA_Y_EL_HISTORIAL_SIGUE():
    assert not (_FRONT / "components" / "common" / "AutoRateCard.jsx").exists()
    panel = (_FRONT / "pages" / "AdminPanel.jsx").read_text(encoding="utf-8")
    assert "AutoRateCard" not in panel
    assert "<RateHistoryButton userRole={user?.role} />" in panel, "el historial de la tasa se perdió del panel"


@pytest.mark.parametrize("archivo", ["contexts/RateContext.jsx", "pages/AdminPanel.jsx"])
def test_NINGUNA_PANTALLA_BUSCA_LA_TASA_NOCTURNA(archivo):
    fuente = (_FRONT / archivo).read_text(encoding="utf-8")
    for campo in ("is_off_hours", "auto_rate_enabled", "base_ris_to_ves", "auto-rate"):
        assert campo not in fuente, (archivo, campo)
