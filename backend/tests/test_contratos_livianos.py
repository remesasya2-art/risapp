"""
tests/test_contratos_livianos.py — la tasa, los límites, los primeros pasos,
los avisos al celular, el botón de Google y la raíz de la API salen por un
contrato, y ningún contrato se come un campo. Ver models/reglas_publicas.py.

Estas rutas ya armaban la respuesta a mano. El riesgo de ponerles contrato es
que se coma un campo y una pantalla quede con un hueco sin avisar. Por eso
cada ruta se llama DOS veces con los mismos datos —la función directo, y por
HTTP con el contrato puesto— y se exige que salgan las mismas claves.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime.now(timezone.utc)


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_livianos"]
    usar_base(m)
    ya(m.users.insert_one({
        "user_id": "u_ana", "verification_status": "verified", "balance_ris": 10.0,
        "password_hash": "$2b$12$secreto", "pin_hash": "$2b$pin",
        "web_push_subscription": {"endpoint": "https://push.ejemplo.test/abc", "keys": {"p256dh": "CLAVE", "auth": "AUTH"}},
    }))
    ya(m.rates.insert_one({"ris_to_ves": 110.0, "ves_to_ris_rate": 140.0, "brl_to_ris": 1.0,
                           "usd_to_ves": 50.0, "usdtris_to_ves": 36.0, "usdcris_to_ves": 36.1,
                           "updated_at": AHORA}))
    ya(m.bcv_rates.insert_one({"rates": {"dolar": 40.5, "euro": 44.1}, "value_date": "2026-09-22",
                               "fetched_at": AHORA}))
    # Tasa automática prendida: la respuesta suma `is_off_hours` y `auto_rate_enabled`.
    ya(m.app_settings.insert_one({"setting_id": "auto_rate", "enabled": True,
                                  "delta_brl_ves": 2.0, "delta_ves_brl": 3.0}))
    return m


def cliente(*routers):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    for r in routers:
        app.include_router(r, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. La misma respuesta con contrato y sin contrato
# ══════════════════════════════════════════════════════════════════════════

def _claves(d):
    return set(d) if isinstance(d, dict) else set()


def test_LA_TASA_SALE_ENTERA(base):
    import routes.basic as basica
    cruda = ya(basica.get_current_rate())
    r = cliente(basica.router).get("/api/rate")
    assert r.status_code == 200, r.text
    assert "bcv_usd_ves" in cruda and "is_off_hours" in cruda, "los datos tienen que cubrir las ramas"
    assert _claves(r.json()) == _claves(cruda), sorted(_claves(cruda) ^ _claves(r.json()))


@pytest.mark.parametrize("camino,funcion", [("/api/limits", "get_limits"), ("/api/limits/me", "get_my_limits")])
def test_LOS_LIMITES_SALEN_ENTEROS(base, camino, funcion):
    import routes.misc as misc
    f = getattr(misc, funcion)
    cruda = ya(f(current_user=ANA) if funcion == "get_my_limits" else f())
    r = cliente(misc.router).get(camino)
    assert r.status_code == 200, r.text
    assert _claves(r.json()) == _claves(cruda), sorted(_claves(cruda) ^ _claves(r.json()))
    for grupo, valor in cruda.items():
        if isinstance(valor, dict):
            assert _claves(r.json()[grupo]) == _claves(valor), grupo


def test_LOS_PRIMEROS_PASOS_SALEN_ENTEROS(base):
    import routes.primeros_pasos as pp
    cruda = ya(pp.ver(current_user=ANA))
    r = cliente(pp.router).get("/api/primeros-pasos")
    assert r.status_code == 200, r.text
    assert _claves(r.json()) == _claves(cruda)


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que corta: la tasa pública no deja pasar lo que se cuele de la
#    configuración, y los avisos al celular no leen la cuenta entera
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TASA_PUBLICA_CORTA_LO_QUE_SE_COLE_DE_LA_CONFIGURACION(base, monkeypatch):
    """`apply_rate_adjustment` copia lo que le pasen. Si alguien le suma un
    campo de la configuración, la ruta pública no lo publica."""
    import routes.basic as basica
    original = basica.apply_rate_adjustment

    def con_de_mas(base_rates, config, *a, **k):
        return {**original(base_rates, config, *a, **k), "delta_interno": 2.0, "nota_del_panel": "subir el lunes"}
    monkeypatch.setattr(basica, "apply_rate_adjustment", con_de_mas)
    r = cliente(basica.router).get("/api/rate")
    assert r.status_code == 200, r.text
    assert "delta_interno" not in r.text and "subir el lunes" not in r.text


class _BaseQueAnota:
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "users":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            async def find_one(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return await coleccion.find_one(filtro, proyeccion, *a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_LOS_AVISOS_AL_CELULAR_NO_LEEN_LA_CUENTA_ENTERA(base):
    import routes.push as push
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    r = cliente(push.router).get("/api/push/web/status")
    assert r.status_code == 200, r.text
    assert r.json() == {"subscribed": True, "endpoint": "https://push.ejemplo.test/abc"}
    assert anotadas == [{"_id": 0, "web_push_subscription": 1}]
    assert "CLAVE" not in r.text and "AUTH" not in r.text


# ══════════════════════════════════════════════════════════════════════════
# 3. Cada ruta tiene el suyo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("modulo,camino,modelo", [
    ("routes.basic", "/", "RaizDeLaApi"),
    ("routes.basic", "/rate", "LaTasa"),
    ("routes.misc", "/limits", "LosLimites"),
    ("routes.misc", "/limits/me", "MisLimites"),
    ("routes.primeros_pasos", "/primeros-pasos", "MisPrimerosPasos"),
    ("routes.push", "/push/web/status", "EstadoDeMisAvisosAlCelular"),
    ("routes.push", "/push/web/vapid-public-key", "ClavePublicaDeAvisos"),
    ("routes.google_ingreso", "/auth/google/config", "ConfigDelBotonDeGoogle"),
])
def test_CADA_RUTA_TIENE_SU_CONTRATO(modulo, camino, modelo):
    import importlib
    router = importlib.import_module(modulo).router
    (ruta,) = [r for r in router.routes if r.path == camino and "GET" in r.methods]
    assert ruta.response_model.__name__ == modelo
