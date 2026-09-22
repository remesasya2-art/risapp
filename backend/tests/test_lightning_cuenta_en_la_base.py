"""
tests/test_lightning_cuenta_en_la_base.py — el tope de facturas Lightning por
cuenta usa el contador compartido, no un diccionario en la memoria del proceso.

POR QUE

    Era el último contador en memoria de la aplicación. Se reiniciaba con cada
    despliegue y con dos procesos eran diez facturas por minuto en vez de cinco.
    Era, además, lo último que trababa prender `--workers` en Railway: los del
    login ya viven en la base cuando LIMITES_EN_LA_BASE=si.
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
from routes import btc_lightning, security_2fa                # noqa: E402
from routes import dependencies as deps                       # noqa: E402


class _HastaAca(Exception):
    """Se levanta justo después del contador: lo que sigue no es de este test."""


@pytest.fixture
def cliente(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    base = mongomock_motor.AsyncMongoMockClient()["lightning_cuenta"]
    usar_base(base)
    security_2fa.reiniciar_la_cuenta()
    quien = {"user_id": "u-1"}

    async def sin_frenos(*a, **k):
        return None

    async def sin_dependencia():
        # Sin parámetros: FastAPI lee la firma de lo que sustituye a una
        # dependencia, y `*a` lo convierte en parámetros de consulta exigidos.
        return None

    async def corte(user_id):
        raise _HastaAca()
    monkeypatch.setattr(btc_lightning.cripto_abierta, "exigir_deposito", sin_frenos)
    monkeypatch.setattr(btc_lightning, "_get_total_enviado_hoy", corte)

    app = FastAPI()
    app.include_router(btc_lightning.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: User(
        user_id=quien["user_id"], name="U", email="u@ejemplo.test", role="user", verification_status="verified")
    app.dependency_overrides[deps.sin_transacciones_personales] = sin_dependencia
    return TestClient(app, raise_server_exceptions=False), quien


def pedir(c):
    return c.post("/api/btc/generar-invoice", json={"usd_cliente": 10, "beneficiario_id": "b-1"})


def test_LA_SEXTA_FACTURA_EN_UN_MINUTO_SE_FRENA_CON_429(cliente):
    c, _ = cliente
    for _ in range(5):
        assert pedir(c).status_code == 500, "pasó el contador y cortó después, como se esperaba"
    r = pedir(c)
    assert r.status_code == 429
    assert "demasiadas operaciones" in r.json()["detail"]


def test_el_tope_es_por_cuenta_y_no_global(cliente):
    c, quien = cliente
    for _ in range(5):
        pedir(c)
    assert pedir(c).status_code == 429
    quien["user_id"] = "u-2"
    assert pedir(c).status_code == 500, "otra cuenta arranca con su propio cupo"


def test_NO_QUEDA_NINGUN_CONTADOR_EN_LA_MEMORIA_DE_LAS_RUTAS():
    """Un diccionario de marcas de tiempo por usuario a nivel de módulo es un
    contador que se reinicia con cada despliegue y se multiplica por proceso.
    Los contadores van por `security_2fa.frenar` o `frenar_por_cuenta`."""
    import ast
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parents[1] / "routes"
    def es_un_recipiente(valor):
        # `{}`, `[]`, `dict()`, `defaultdict(...)`: lo que se llena a mano.
        if isinstance(valor, (ast.Dict, ast.List)):
            return not (valor.keys if isinstance(valor, ast.Dict) else valor.elts)
        return isinstance(valor, ast.Call) and getattr(valor.func, "id", "") in ("dict", "list", "defaultdict")

    culpables = []
    for archivo in sorted(raiz.glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if not isinstance(nodo, ast.Assign) or not es_un_recipiente(nodo.value):
                continue
            for objetivo in nodo.targets:
                nombre = getattr(objetivo, "id", "").lower()
                if any(p in nombre for p in ("rate_limit", "intentos", "attempts", "_reqs", "contador", "limit")):
                    culpables.append(f"{archivo.name}:{nodo.lineno} {nombre}")
    assert not culpables, f"contador en memoria: {culpables}"
    assert not hasattr(btc_lightning, "_rate_limit_invoices")


def test_la_regla_esta_escrita_una_vez_y_es_por_minuto():
    assert btc_lightning.REGLA_DE_FACTURAS == "5/minute"
