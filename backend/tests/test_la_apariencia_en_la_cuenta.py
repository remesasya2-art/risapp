"""
tests/test_la_apariencia_en_la_cuenta.py — claro, oscuro o automático,
guardado en la cuenta.

QUE SE PIDIO

    Que la persona elija cómo se ve la app y que la elección la siga a
    cualquier aparato donde entre. Por eso vive en la cuenta y no sólo en el
    navegador.

LO QUE ESTE ARCHIVO CUIDA

    - Que se guarde y que vuelva: por `/auth/me` y por cada puerta de entrada,
      porque la pantalla se pinta con lo que trae la puerta.
    - Que la ruta no sirva para otra cosa: un solo campo, tres valores, y
      siempre sobre la cuenta de la sesión.
    - Que una cuenta que nunca eligió no reciba un `null` inventado: la
      pantalla distingue «no eligió» (y entonces adopta lo del aparato) de
      «eligió».
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services.money import to_decimal128                      # noqa: E402

ANA = User(user_id="usr_ana", name="Ana", email="ana@ejemplo.test", role="user")


def ya(c):
    import asyncio
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["apariencia"]
    usar_base(m)
    ya(m.users.insert_many([
        {"user_id": "usr_ana", "email": "ana@ejemplo.test", "name": "Ana", "role": "user",
         "balance_ris": to_decimal128("12.50")},
        {"user_id": "usr_beto", "email": "beto@ejemplo.test", "name": "Beto", "role": "user",
         "apariencia": "claro", "balance_ris": to_decimal128("3.00")},
    ]))
    return m


def cliente(quien=ANA):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.auth import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. Se guarda y vuelve
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("eleccion", ["auto", "claro", "oscuro"])
def test_SE_GUARDA_Y_VUELVE_POR_AUTH_ME(base, eleccion):
    c = cliente()
    r = c.put("/api/auth/me/apariencia", json={"apariencia": eleccion})
    assert r.status_code == 200, r.text
    assert r.json() == {"apariencia": eleccion}
    assert c.get("/api/auth/me").json()["apariencia"] == eleccion


def test_QUIEN_NUNCA_ELIGIO_NO_RECIBE_UN_NULL_INVENTADO(base):
    """Sin elección guardada, la pantalla adopta la del aparato y la sube.
    Si le llegara `apariencia: null` no podría distinguir ese caso."""
    assert "apariencia" not in cliente().get("/api/auth/me").json()


def test_SALE_POR_LAS_PUERTAS_DE_ENTRADA():
    """Al entrar, la pantalla se pinta con lo que trae la puerta: si la
    preferencia llegara recién después, quien eligió oscuro vería un destello
    blanco cada vez. Las cinco puertas arman su respuesta con esta lista."""
    from services.perfil import LO_PERMITIDO
    assert "apariencia" in LO_PERMITIDO


def test_LA_PUERTA_DE_LA_CONTRASENA_LA_DEVUELVE():
    """Y no alcanza con estar en la lista: se entra de verdad y se mira."""
    import test_las_cinco_puertas as puertas
    from utils.security import hash_password
    m = mongomock_motor.AsyncMongoMockClient()["apariencia_puerta"]
    usar_base(m)
    ya(m.users.insert_one({
        "user_id": "u1", "email": puertas.CORREO, "name": "Ana", "role": "user",
        "email_verified": True, "password_set": True,
        "password_hash": hash_password(puertas.CLAVE),
        "balance_ris": to_decimal128(10), "apariencia": "oscuro"}))
    assert puertas.por_la_contrasena(m)["apariencia"] == "oscuro"


# ══════════════════════════════════════════════════════════════════════════
# 2. La ruta no sirve para otra cosa
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuerpo", [
    {"apariencia": "rosa"},
    {"apariencia": ""},
    {"apariencia": None},
    {"apariencia": "OSCURO"},
    {},
])
def test_SOLO_ACEPTA_LOS_TRES_VALORES(base, cuerpo):
    assert cliente().put("/api/auth/me/apariencia", json=cuerpo).status_code == 422
    assert "apariencia" not in ya(base.users.find_one({"user_id": "usr_ana"}))


def test_NO_ESCRIBE_NADA_MAS_QUE_LA_APARIENCIA(base):
    """Un campo de más en el cuerpo no llega a la cuenta: si llegara, esta
    ruta serviría para cambiarse el rol o el saldo."""
    antes = ya(base.users.find_one({"user_id": "usr_ana"}, {"_id": 0}))
    r = cliente().put("/api/auth/me/apariencia",
                      json={"apariencia": "oscuro", "role": "super_admin",
                            "balance_ris": "999999"})
    assert r.status_code == 200
    despues = ya(base.users.find_one({"user_id": "usr_ana"}, {"_id": 0}))
    assert despues == {**antes, "apariencia": "oscuro"}


def test_SOLO_TOCA_LA_CUENTA_DE_LA_SESION(base):
    """La sesión es la de Beto, que es la SEGUNDA cuenta de la colección: si
    el filtro por `user_id` se perdiera, `update_one` tocaría la primera que
    encuentra —la de Ana— y este test lo vería. Con la sesión de Ana, un
    filtro vacío le caería justo a ella y el defecto pasaría inadvertido."""
    beto = User(user_id="usr_beto", name="Beto", email="beto@ejemplo.test", role="user")
    assert cliente(beto).put("/api/auth/me/apariencia", json={"apariencia": "oscuro"}).status_code == 200
    assert ya(base.users.find_one({"user_id": "usr_beto"}))["apariencia"] == "oscuro"
    assert "apariencia" not in ya(base.users.find_one({"user_id": "usr_ana"}))


def test_SIN_SESION_NO_ENTRA(base):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.auth import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    r = TestClient(app).put("/api/auth/me/apariencia", json={"apariencia": "oscuro"})
    assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 3. Las pantallas
# ══════════════════════════════════════════════════════════════════════════
#
# Se lee el fuente porque no hay navegador en la suite. Lo que se vigila son
# las dos decisiones que impiden que el modo oscuro rompa algo.

from pathlib import Path                                      # noqa: E402

_FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_LA_PANTALLA_GUARDA_EN_LA_RUTA_QUE_EXISTE():
    """Si la pantalla llamara a otra dirección, la elección quedaría sólo en
    el aparato sin que nada avise: el cambio de color se ve igual."""
    fuente = (_FRONT / "contexts" / "TemaContext.jsx").read_text(encoding="utf-8")
    assert fuente.count("api.put('/auth/me/apariencia', { apariencia:") == 2
    from routes.auth import router
    assert any(r.path == "/auth/me/apariencia" and "PUT" in r.methods for r in router.routes)


def test_LO_OSCURO_NO_SE_ESCAPA_A_LAS_PANTALLAS_QUE_NO_PASARON():
    """Las pantallas que todavía no pasaron al estilo nuevo tienen sus colores
    escritos a mano. Si los colores oscuros o `color-scheme: dark` colgaran
    del documento entero, el pie de página saldría negro al fondo de una
    pantalla blanca, y los campos sin color propio quedarían oscuros con letra
    oscura. Se comprobó comparando capturas: con la regla así, el registro y
    el marco legal en modo oscuro son idénticos píxel a píxel a los de antes."""
    import re
    css = (_FRONT / "index.css").read_text(encoding="utf-8")
    sin_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    reglas = re.findall(r"([^{}]+)\{([^{}]*)\}", sin_comentarios)
    for selector, cuerpo in reglas:
        selector = " ".join(selector.split())
        if 'data-tema="oscuro"' in selector or "color-scheme: dark" in cuerpo:
            assert selector.endswith(".con-tema"), (
                f"«{selector}» pinta de oscuro fuera de las pantallas preparadas")
    assert any('data-tema="oscuro"' in s for s, _ in reglas), "no hay modo oscuro"


def test_EL_TEMA_SE_PONE_ANTES_DE_DIBUJAR():
    """Si se pusiera cuando monta React, quien eligió oscuro vería un destello
    blanco cada vez que abre la app."""
    fuente = (_FRONT / "main.jsx").read_text(encoding="utf-8")
    assert fuente.index("aplicar(leerDelAparato())") < fuente.index("createRoot(")
