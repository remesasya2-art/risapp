"""
tests/test_nucleo_apagado_de_fabrica.py — el núcleo de cuentas no existe
hasta que alguien lo prenda, y aun prendido los clientes no lo ven.

POR QUE ESTO ES UN TEST

    Decisión del dueño: la arquitectura de fintech se construye ahora y se
    prende cuando haya licencia. Lo que sostiene esa decisión no es una
    promesa sino esto: de fábrica las rutas contestan 404 a todo el mundo, el
    interruptor falla cerrado, ninguna pantalla de cliente nombra el núcleo,
    y `/limits` no publica nada sobre él.
"""
import os
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
_SRC = _BACKEND.parent / "frontend" / "src"

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from nucleo import base as nucleo_base, modo                  # noqa: E402

SUPER = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")
ADMIN = User(user_id="u_admin", name="Admin", email="admin@ejemplo.test", role="admin")


def _ya(c):
    import asyncio
    return asyncio.run(c)


@pytest.fixture
def app_y_base():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nucleo.rutas import router
    from routes import dependencies as deps
    base = mongomock_motor.AsyncMongoMockClient()["nucleo_modo"]
    usar_base(base)
    nucleo_base.usar("sqlite+aiosqlite://")
    _ya(nucleo_base.crear_todo())
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, base, TestClient, deps


def _como(app, deps, quien):
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    app.dependency_overrides[deps.get_super_admin] = lambda: quien


def _poner_modo(base, valor):
    _ya(base.config.update_one({"clave": modo.CLAVE}, {"$set": {"clave": modo.CLAVE, "valor": str(valor)}}, upsert=True))


# ─── el interruptor ───────────────────────────────────────────────────────

def test_de_fabrica_esta_apagado():
    from services import configuracion
    assert configuracion.AJUSTES[modo.CLAVE].defecto == modo.APAGADO


def test_el_interruptor_FALLA_CERRADO(monkeypatch):
    """Si la configuración no se puede leer, apagado. Al revés que la recarga,
    y el motivo está en nucleo/modo.py."""
    from services import configuracion

    async def rota(*a, **k):
        raise RuntimeError("la base no contesta")
    monkeypatch.setattr(configuracion, "leer", rota)
    assert _ya(modo.leer(object())) == modo.APAGADO


def test_un_valor_fuera_del_catalogo_es_apagado(app_y_base):
    _, base, _, _ = app_y_base
    _poner_modo(base, 7)
    assert _ya(modo.leer(base)) == modo.APAGADO


def test_ACTIVO_HOY_SE_COMPORTA_IGUAL_QUE_LABORATORIO():
    """Nadie prende el núcleo de verdad cambiando un número. El día que haya
    licencia, ACTIVO va a exigir otra cosa; hasta entonces es laboratorio."""
    assert modo.se_puede_usar(modo.LABORATORIO) is True
    assert modo.se_puede_usar(modo.ACTIVO) is True
    assert modo.se_puede_usar(modo.APAGADO) is False


# ─── las rutas ────────────────────────────────────────────────────────────

def test_APAGADO_EL_SUPER_ADMINISTRADOR_RECIBE_404(app_y_base):
    app, base, TestClient, deps = app_y_base
    _como(app, deps, SUPER)
    c = TestClient(app)
    for ruta in ("/api/nucleo/estado", "/api/nucleo/laboratorio/cuentas", "/api/nucleo/laboratorio/libro",
                 "/api/nucleo/laboratorio/balance", "/api/nucleo/laboratorio/cadena", "/api/nucleo/laboratorio/cierres"):
        r = c.get(ruta)
        assert r.status_code == 404, (ruta, r.status_code, r.text)
    r = c.post("/api/nucleo/laboratorio/cuentas", json={"titular_ref": "u_1"})
    assert r.status_code == 404


def test_en_laboratorio_el_super_administrador_entra(app_y_base):
    app, base, TestClient, deps = app_y_base
    _poner_modo(base, modo.LABORATORIO)
    _como(app, deps, SUPER)
    r = TestClient(app).get("/api/nucleo/estado")
    assert r.status_code == 200, r.text
    assert r.json()["modo_nombre"] == "laboratorio"
    assert r.json()["conectada"] is True


def test_toda_ruta_del_nucleo_lleva_la_puerta_del_super_administrador_y_el_interruptor():
    """No alcanza con que las rutas de hoy lo lleven: cada ruta que se agregue
    tiene que llevarlo. Se recorre el router de verdad."""
    from nucleo.rutas import router
    from routes.dependencies import get_super_admin
    for ruta in router.routes:
        deps = {d.call for d in ruta.dependant.dependencies}
        assert get_super_admin in deps, f"{ruta.path} sin get_super_admin"
        assert modo.exigir_encendido in deps, f"{ruta.path} sin el interruptor"
        assert ruta.response_model is not None, f"{ruta.path} sin contrato de salida"


# ─── los clientes no lo ven ───────────────────────────────────────────────

def _fuentes_del_cliente():
    for carpeta in ("pages", "components", "hooks", "contexts", "utils"):
        for archivo in (_SRC / carpeta).rglob("*.js*"):
            if archivo.name.startswith("Nucleo"):
                continue
            if "admin" in archivo.parts[len(_SRC.parts):]:
                continue
            yield archivo


def test_NINGUNA_PANTALLA_DE_CLIENTE_NOMBRA_EL_NUCLEO():
    culpables = [str(a.relative_to(_SRC)) for a in _fuentes_del_cliente()
                 if re.search(r"/nucleo\b", a.read_text(encoding="utf-8"))]
    assert not culpables, culpables


def test_limits_no_publica_nada_del_nucleo():
    from services import limits
    base = mongomock_motor.AsyncMongoMockClient()["nucleo_limits"]
    usar_base(base)
    _poner_modo(base, modo.LABORATORIO)
    p = _ya(limits.limits_payload(base))
    assert "nucleo" not in str(p).lower()
