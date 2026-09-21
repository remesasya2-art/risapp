"""Lo que comparten los tests del lote C: la base doble y el cliente de prueba
armado con un solo router y la persona que hace falta suplantada."""
import asyncio
import os
import pathlib
import sys
import types

import pytest

_BACKEND = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
_SRC = _BACKEND.parent / "frontend" / "src"

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402


def sin_webpush():
    """`pywebpush` no compila en este entorno; un doble que no hace nada."""
    try:
        import pywebpush  # noqa: F401
    except Exception:
        falso = types.ModuleType("pywebpush")
        falso.webpush = lambda *a, **k: None
        falso.WebPushException = type("WebPushException", (Exception,), {})
        sys.modules["pywebpush"] = falso


def app_con(router, dependencia, persona, nombre_base):
    """Una app mínima con UN router y la dependencia de identidad suplantada.
    Devuelve (cliente, base)."""
    sin_webpush()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    base = mongomock_motor.AsyncMongoMockClient()[nombre_base]
    usar_base(base)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependencia] = lambda: persona
    return TestClient(app), base


def fuente(relativa):
    return (_SRC / relativa).read_text(encoding="utf-8")


def sin_comentarios(texto):
    fuera, en_bloque = [], False
    for linea in texto.splitlines():
        s = linea.strip()
        if en_bloque:
            if "*/" in s:
                en_bloque = False
            continue
        if s.startswith("/*") or s.startswith("{/*"):
            en_bloque = "*/" not in s
            continue
        if s.startswith("//") or s.startswith("*"):
            continue
        fuera.append(linea)
    return "\n".join(fuera)


def ya(corrutina):
    """Correr una corrutina desde un test sincrónico. `asyncio.run` y no
    `get_event_loop().run_until_complete`: en la suite completa otro archivo
    cierra el bucle por omisión, y pedirlo de nuevo falla. Solos, los tests
    pasaban; en la suite, no. Ya pasó una vez."""
    return asyncio.run(corrutina)


SUPER = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")
