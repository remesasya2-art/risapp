"""
tests/test_politicas_sin_puerta_publica.py — `GET /policies` no vuelve, y
`/policies/status` lee y devuelve sólo lo que aceptó quien pregunta.

`GET /policies` era pública y devolvía los documentos enteros de `policies`
con `{"_id": 0}`. Ningún código escribe esa colección y ninguna pantalla la
pedía: lo que alguien guardara ahí a mano salía para cualquiera.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["politicas"]
    usar_base(m)
    ya(m.users.insert_one({"user_id": "u_ana", "accepted_policies": ["terminos"],
                           "password_hash": "$2b$12$secreto", "pin_hash": "$2b$pin"}))
    return m


def cliente(quien=ANA):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.misc import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


def test_LA_RUTA_PUBLICA_YA_NO_EXISTE():
    from routes.misc import router
    assert not [r for r in router.routes if getattr(r, "path", "") == "/policies"
                and "GET" in getattr(r, "methods", ())]


def test_EL_ESTADO_DEVUELVE_LO_ACEPTADO(base):
    r = cliente().get("/api/policies/status")
    assert r.status_code == 200 and r.json() == {"accepted_policies": ["terminos"]}


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


def test_NO_TRAE_LA_CUENTA_ENTERA_PARA_LEER_UNA_LISTA(base):
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    cliente().get("/api/policies/status")
    assert anotadas == [{"_id": 0, "accepted_policies": 1}]


def test_UNA_CUENTA_QUE_YA_NO_EXISTE_NO_DA_500(base):
    otra = User(user_id="u_borrada", name="X", email="x@ejemplo.test", role="user")
    r = cliente(otra).get("/api/policies/status")
    assert r.status_code == 200 and r.json() == {"accepted_policies": []}
