"""
tests/test_la_tasa_base_no_es_publica.py — la tasa de antes del ajuste fuera
de horario ya no sale por la ruta pública `/rate`; la tarjeta de tasa
automática del panel la lee de `GET /admin/auto-rate`, que es sólo del super
administrador.

QUE PASABA

    `/rate` la ve cualquiera, sin sesión. Mandaba `base_ris_to_ves` y
    `base_ves_to_ris_rate` al lado de la tasa ajustada, así que fuera de
    horario cualquiera podía restar y saber cuánto se le suma a la tasa de
    noche. Las leía una sola pantalla: la tarjeta de tasa automática del panel.
"""
import asyncio
import os
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
# Un colaborador con TODOS los permisos del catálogo: ni así lee la base. Con
# un permiso cualquiera, la prueba pasaría aunque la ruta se abriera a los
# colaboradores —la tabla de permisos lo frenaría por otro lado— y no
# probaría lo que dice.
from services.permisos import CATALOGO                        # noqa: E402
AGENTE = User(user_id="u_agente", name="Agente", email="agente@ejemplo.test",
              role="admin", permissions=sorted(CATALOGO))
CLIENTA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")

# Valores que no se confunden con nada más de la respuesta.
BASE_RIS_VES, BASE_VES_RIS = 111.25, 141.75


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["tasa_base"]
    usar_base(m)
    ya(m.rates.insert_one({"ris_to_ves": BASE_RIS_VES, "ves_to_ris_rate": BASE_VES_RIS,
                           "brl_to_ris": 1.0, "usd_to_ves": 50.0}))
    ya(m.app_settings.insert_one({"setting_id": "auto_rate", "enabled": True,
                                  "delta_brl_ves": 2.0, "delta_ves_brl": 3.0}))
    return m


@pytest.fixture
def fuera_de_horario(monkeypatch):
    """Que la tasa ajustada difiera de la base, pase lo que pase con el reloj."""
    import services.rate_engine as motor
    monkeypatch.setattr(motor, "is_off_hours", lambda config, now=None: True)


def como(quien, router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


def publica():
    from routes.basic import router
    return como(None, router)


def panel(quien):
    from routes.admin import router
    return como(quien, router)


# ══════════════════════════════════════════════════════════════════════════
# 1. La ruta pública
# ══════════════════════════════════════════════════════════════════════════

def test_LA_RUTA_PUBLICA_NO_MANDA_LA_TASA_BASE(base, fuera_de_horario):
    r = publica().get("/api/rate")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "base_ris_to_ves" not in d and "base_ves_to_ris_rate" not in d
    # Fuera de horario la ajustada es otra, y la base no aparece en ningún lado.
    assert d["ris_to_ves"] != BASE_RIS_VES
    assert str(BASE_RIS_VES) not in r.text and str(BASE_VES_RIS) not in r.text


def test_EL_CONTRATO_PUBLICO_LA_CORTA_SI_VUELVE_A_COLARSE(base, fuera_de_horario, monkeypatch):
    """Si alguien vuelve a escribir las dos líneas en la función, el contrato
    de la ruta pública no las deja salir."""
    import routes.basic as basica
    original = basica.apply_rate_adjustment

    def con_la_base(base_rates, config, *a, **k):
        return {**original(base_rates, config, *a, **k),
                "base_ris_to_ves": base_rates["ris_to_ves"],
                "base_ves_to_ris_rate": base_rates["ves_to_ris_rate"]}
    monkeypatch.setattr(basica, "apply_rate_adjustment", con_la_base)
    r = publica().get("/api/rate")
    assert r.status_code == 200, r.text
    assert "base_ris_to_ves" not in r.text and str(BASE_RIS_VES) not in r.text


def test_LA_FUNCION_DE_LA_RUTA_PUBLICA_YA_NO_LA_ARMA(base, fuera_de_horario):
    """La primera capa: la función misma, sin el contrato."""
    import routes.basic as basica
    cruda = ya(basica.get_current_rate())
    assert "base_ris_to_ves" not in cruda and "base_ves_to_ris_rate" not in cruda


# ══════════════════════════════════════════════════════════════════════════
# 2. La ruta del panel
# ══════════════════════════════════════════════════════════════════════════

def test_EL_SUPER_ADMIN_LA_LEE_DE_SU_RUTA(base, fuera_de_horario):
    r = panel(JEFA).get("/api/admin/auto-rate")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["base_ris_to_ves"] == BASE_RIS_VES and d["base_ves_to_ris_rate"] == BASE_VES_RIS
    assert d["enabled"] is True and d["delta_brl_ves"] == 2.0 and d["is_off_hours_now"] is True


def test_LA_BASE_ES_LA_MISMA_QUE_AJUSTA_LA_RUTA_PUBLICA(base, fuera_de_horario):
    """«base → ajustada» en la tarjeta tiene que ser la cuenta que hace el
    servidor: base menos el delta es lo que publica `/rate`."""
    d = panel(JEFA).get("/api/admin/auto-rate").json()
    publicada = publica().get("/api/rate").json()
    assert publicada["ris_to_ves"] == pytest.approx(d["base_ris_to_ves"] - d["delta_brl_ves"])
    assert publicada["ves_to_ris_rate"] == pytest.approx(d["base_ves_to_ris_rate"] + d["delta_ves_brl"])


@pytest.mark.parametrize("quien", [AGENTE, CLIENTA], ids=["admin_con_permisos", "cliente"])
def test_NADIE_MAS_LA_LEE(base, quien):
    assert panel(quien).get("/api/admin/auto-rate").status_code == 403


def test_NI_DECLARANDOLA_EN_LA_TABLA_DE_PERMISOS_LA_LEE_UN_COLABORADOR(base, monkeypatch):
    """La tabla de permisos falla cerrado: una ruta que no está en ella se le
    niega a cualquier colaborador. Por eso el test de arriba pasaría aunque la
    ruta pidiera `get_admin_user` en vez de `get_super_admin` —las dos guardas
    se tapan entre sí—. Acá se la declara, como haría quien quiera abrirla, y
    lo único que queda frenando es que sea del super administrador."""
    import services.permisos as permisos
    monkeypatch.setitem(permisos.MAPA, ("GET", "/api/admin/auto-rate"), "settings.view")
    assert panel(AGENTE).get("/api/admin/auto-rate").status_code == 403


def test_SIN_TASA_CARGADA_USA_LOS_MISMOS_RESPALDOS_QUE_LA_PUBLICA(base):
    ya(base.rates.delete_many({}))
    d = panel(JEFA).get("/api/admin/auto-rate").json()
    assert d["base_ris_to_ves"] == 110.0 and d["base_ves_to_ris_rate"] == 140.0


def test_EL_CONTRATO_DEL_PANEL_NO_SE_COME_NADA(base, fuera_de_horario):
    import routes.admin as admin
    cruda = ya(admin.get_auto_rate_config(admin=JEFA))
    r = panel(JEFA).get("/api/admin/auto-rate")
    assert set(r.json()) == set(cruda), sorted(set(r.json()) ^ set(cruda))


def test_LA_RUTA_DEL_PANEL_TIENE_SU_CONTRATO():
    from routes.admin import router
    (ruta,) = [r for r in router.routes if r.path == "/admin/auto-rate" and "GET" in r.methods]
    assert ruta.response_model.__name__ == "ConfigDeTasaAutomatica"


# ══════════════════════════════════════════════════════════════════════════
# 3. Las pantallas
# ══════════════════════════════════════════════════════════════════════════

_FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_LA_TARJETA_LA_LEE_DE_SU_CONFIGURACION():
    fuente = (_FRONT / "components" / "common" / "AutoRateCard.jsx").read_text(encoding="utf-8")
    assert "const baseRisToVes = config.base_ris_to_ves;" in fuente
    assert "const baseVesToRis = config.base_ves_to_ris_rate;" in fuente


@pytest.mark.parametrize("archivo", ["contexts/RateContext.jsx", "pages/AdminPanel.jsx"])
def test_NINGUNA_PANTALLA_LA_BUSCA_EN_LA_TASA_PUBLICA(archivo):
    """Si una pantalla la sigue buscando en `/rate`, muestra un hueco sin avisar."""
    fuente = (_FRONT / archivo).read_text(encoding="utf-8")
    assert "base_ris_to_ves" not in fuente and "base_ves_to_ris_rate" not in fuente, archivo
