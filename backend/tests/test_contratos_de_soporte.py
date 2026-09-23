"""
tests/test_contratos_de_soporte.py — lo que el cliente ve de sus casos de
soporte sale por un contrato, y la conversación no le trae el identificador
interno del asesor. Ver models/soporte.py.
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
ASESORA = User(user_id="u_asesora", name="Carla", email="carla@ejemplo.test", role="agent")
AHORA = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)

# Lo que lee la pantalla del cliente (components/soporte/CasosDelCliente.jsx).
LO_QUE_LEE_LA_PANTALLA = {"mensaje_id", "autor", "autor_nombre", "texto", "adjunto", "creado_en"}


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_soporte"]
    usar_base(m)
    ya(m.soporte_casos.insert_one({
        "caso_id": "c1", "numero": 7, "user_id": "u_ana", "motivo": "envio", "estado": "abierto",
        "asignado_a": "u_asesora", "asignado_a_nombre": "Carla",
        "escalado_por_nombre": "Jefe de turno", "escalado_motivo": "cliente sospechoso",
        "creado_en": AHORA, "actualizado_en": AHORA,
    }))
    ya(m.soporte_mensajes.insert_many([
        {"mensaje_id": "m1", "caso_id": "c1", "autor": "cliente", "autor_id": "u_ana",
         "autor_nombre": "Ana", "interno": False, "texto": "¿Dónde está mi envío?",
         "adjunto": None, "creado_en": AHORA},
        {"mensaje_id": "m2", "caso_id": "c1", "autor": "asesor", "autor_id": "u_asesora",
         "autor_nombre": "Carla", "interno": False, "texto": "Ya lo reviso",
         "adjunto": None, "creado_en": AHORA, "ip_del_asesor": "10.0.0.7"},
        {"mensaje_id": "m3", "caso_id": "c1", "autor": "sistema", "autor_id": "u_jefe",
         "autor_nombre": "Jefe de turno", "interno": True, "texto": "Escalado: revisar origen de fondos",
         "adjunto": None, "creado_en": AHORA},
    ]))
    return m


def cliente_como(quien):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.soporte import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    app.dependency_overrides[deps.get_crm_user] = lambda: quien
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. La conversación, como la ve el cliente
# ══════════════════════════════════════════════════════════════════════════

def test_EL_CLIENTE_NO_RECIBE_EL_IDENTIFICADOR_DEL_ASESOR(base):
    r = cliente_como(ANA).get("/api/soporte/casos/c1")
    assert r.status_code == 200
    assert "u_asesora" not in r.text, "el identificador interno del asesor no le sirve al cliente"
    assert "10.0.0.7" not in r.text
    for m in r.json()["mensajes"]:
        assert set(m) == LO_QUE_LEE_LA_PANTALLA, sorted(m)


def test_LAS_NOTAS_INTERNAS_SIGUEN_SIN_LLEGAR(base):
    r = cliente_como(ANA).get("/api/soporte/casos/c1")
    assert [m["mensaje_id"] for m in r.json()["mensajes"]] and "m3" not in r.text
    assert "origen de fondos" not in r.text and "Jefe de turno" not in r.text


def test_LO_QUE_LA_PANTALLA_LEE_SIGUE_LLEGANDO(base):
    mensajes = cliente_como(ANA).get("/api/soporte/casos/c1").json()["mensajes"]
    del_asesor = next(m for m in mensajes if m["mensaje_id"] == "m2")
    assert del_asesor["autor"] == "asesor" and del_asesor["autor_nombre"] == "Carla"
    assert del_asesor["texto"] == "Ya lo reviso" and del_asesor["creado_en"]


class _BaseQueAnota:
    """La base de siempre, anotando qué proyección le piden a `soporte_mensajes`."""
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "soporte_mensajes":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            def find(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return coleccion.find(filtro, proyeccion, *a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_LA_PROYECCION_SOLA_NO_TRAE_DE_LA_BASE_LO_QUE_NO_SE_MUESTRA(base):
    """La primera capa, probada sin la segunda: lo que la consulta le pide a
    Mongo, no lo que sale después del contrato."""
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    cliente_como(ANA).get("/api/soporte/casos/c1")
    (proyeccion,) = anotadas
    assert proyeccion.get("_id") == 0
    assert {c for c, v in proyeccion.items() if c != "_id" and v == 1} == LO_QUE_LEE_LA_PANTALLA
    assert "autor_id" not in proyeccion


def test_EL_CONTRATO_SOLO_CORTA_LO_QUE_LA_PROYECCION_DEJE_PASAR(base, monkeypatch):
    """La segunda capa, probada sin la primera: si alguien ensancha la
    proyección, el contrato corta igual."""
    import routes.soporte as rutas
    monkeypatch.setattr(rutas, "LO_QUE_VE_DE_UN_MENSAJE", {"_id": 0})
    r = cliente_como(ANA).get("/api/soporte/casos/c1")
    assert r.status_code == 200
    assert "u_asesora" not in r.text and "10.0.0.7" not in r.text
    for m in r.json()["mensajes"]:
        assert set(m) <= LO_QUE_LEE_LA_PANTALLA, sorted(m)


def test_EL_PANEL_DEL_EQUIPO_SIGUE_VIENDO_EL_MENSAJE_ENTERO(base):
    """El recorte es sólo para el cliente. El asesor necesita las notas
    internas y quién escribió cada cosa."""
    r = cliente_como(ASESORA).get("/api/admin/soporte/casos/c1")
    assert r.status_code == 200, r.text
    por_id = {m["mensaje_id"]: m for m in r.json()["mensajes"]}
    assert por_id["m3"]["interno"] is True, "las notas internas son del equipo"
    assert por_id["m2"]["autor_id"] == "u_asesora"


# ══════════════════════════════════════════════════════════════════════════
# 2. La ficha del caso y la lista
# ══════════════════════════════════════════════════════════════════════════

def test_LA_FICHA_NO_DICE_QUIEN_LO_ESCALO_NI_POR_QUE(base):
    c = cliente_como(ANA)
    for r in (c.get("/api/soporte/casos/c1"), c.get("/api/soporte/casos")):
        assert r.status_code == 200
        assert "Jefe de turno" not in r.text and "sospechoso" not in r.text
        assert '"asignado_a"' not in r.text
    assert c.get("/api/soporte/casos").json()["casos"][0]["asignado_a_nombre"] == "Carla"


def test_EL_CONTRATO_DE_LA_FICHA_CORTA_SOLO(base, monkeypatch):
    """Sin la lista de `_publico`, el contrato tiene que cortar igual."""
    import routes.soporte as rutas
    monkeypatch.setattr(rutas, "_publico", lambda caso: caso)
    c = cliente_como(ANA)
    for r in (c.get("/api/soporte/casos/c1"), c.get("/api/soporte/casos")):
        assert r.status_code == 200
        assert "Jefe de turno" not in r.text and "sospechoso" not in r.text and "u_asesora" not in r.text


def test_LO_QUE_EL_CASO_NO_TIENE_NO_SALE_COMO_NULL(base):
    """La pantalla distingue «no tiene calificación» de «tiene null». Un caso
    sin `calificacion` tiene que seguir sin esa clave, como antes del contrato."""
    caso = cliente_como(ANA).get("/api/soporte/casos/c1").json()["caso"]
    assert "calificacion" not in caso and "cerrado_en" not in caso
    lista = cliente_como(ANA).get("/api/soporte/casos").json()["casos"][0]
    assert "calificacion" not in lista


def test_UN_CASO_VIEJO_CON_OTRA_FORMA_NO_ROMPE_LA_LISTA(base):
    """Un número guardado como texto y una fecha guardada como texto: el
    contrato recorta, no convierte, y no puede contestar 500."""
    ya(base.soporte_casos.insert_one({
        "caso_id": "c0", "numero": "3", "user_id": "u_ana", "estado": "cerrado",
        "creado_en": "2025-01-02", "actualizado_en": "2025-01-02",
        "calificacion": {"estrellas": 5}}))
    r = cliente_como(ANA).get("/api/soporte/casos")
    assert r.status_code == 200 and {c["caso_id"] for c in r.json()["casos"]} == {"c0", "c1"}


def test_LOS_MOTIVOS(base):
    r = cliente_como(ANA).get("/api/soporte/motivos")
    assert r.status_code == 200 and r.json()["motivos"]
    assert all(set(m) == {"clave", "texto"} for m in r.json()["motivos"])


# ══════════════════════════════════════════════════════════════════════════
# 3. Cada ruta tiene el suyo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("camino,modelo", [
    ("/soporte/motivos", "LosMotivos"),
    ("/soporte/casos", "MisCasos"),
    ("/soporte/casos/{caso_id}", "MiCaso"),
])
def test_CADA_RUTA_DEL_CLIENTE_TIENE_SU_CONTRATO(camino, modelo):
    from routes.soporte import router
    (ruta,) = [r for r in router.routes if r.path == camino and "GET" in r.methods]
    assert getattr(ruta.response_model, "__name__", None) == modelo
