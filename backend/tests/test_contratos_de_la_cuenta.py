"""
tests/test_contratos_de_la_cuenta.py — lo que una persona ve de su propia
cuenta sale por un contrato de salida, y nada de lo que escribió el equipo
sobre ella llega a su pantalla. Ver models/cuenta.py.
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


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_cuenta"]
    usar_base(m)
    return m


def cliente_con(router):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. /verification/status
# ══════════════════════════════════════════════════════════════════════════

LO_QUE_ESCRIBE_EL_EQUIPO = {
    "admin_note": "sospechosa, revisar origen de fondos",
    "admin_note_updated_by": "u_agente",
    "risk_level": "alto", "risk_set_by": "u_agente",
    "processed_by": "u_agente", "processed_by_name": "Carla Agente",
    "re_review_by_name": "Otro Agente", "rejection_code": "doc_ilegible",
}
SUS_DOCUMENTOS = {
    "full_name": "Ana Souza", "document_number": "123456", "cpf_number": "52998224725",
    "phone_number": "+5511999999999",
    "id_document_image": "data:image/jpeg;base64,AAAA", "cpf_image": "data:image/jpeg;base64,BBBB",
    "selfie_image": "data:image/jpeg;base64,CCCC",
}


@pytest.fixture
def verificacion(base):
    ya(base.verifications.insert_one({
        "verification_id": "ver_1", "user_id": "u_ana", "status": "approved", "document_type": "rg",
        "submitted_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "verified_at": datetime(2026, 9, 2, tzinfo=timezone.utc),
        **LO_QUE_ESCRIBE_EL_EQUIPO, **SUS_DOCUMENTOS}))
    return base


def test_LO_QUE_ESCRIBIO_EL_EQUIPO_SOBRE_EL_CLIENTE_NO_LE_LLEGA(verificacion):
    """La nota interna, el nivel de riesgo y quién lo revisó salían enteros.
    Avisarle a alguien que está bajo sospecha es justamente lo que las normas
    de prevención de lavado prohíben."""
    from routes.misc import router
    r = cliente_con(router).get("/api/verification/status")
    assert r.status_code == 200
    assert set(r.json()) == {"status", "submitted_at", "verified_at", "document_type"}
    assert r.json()["status"] == "approved" and r.json()["document_type"] == "rg"
    texto = r.text
    for valor in ("sospechosa", "alto", "Carla Agente", "u_agente", "doc_ilegible"):
        assert valor not in texto, valor


def test_SUS_FOTOS_Y_SUS_DATOS_TAMPOCO_VUELVEN(verificacion):
    from routes.misc import router
    texto = cliente_con(router).get("/api/verification/status").text
    for valor in ("base64", "123456", "52998224725", "Ana Souza", "+5511"):
        assert valor not in texto, valor


def test_la_proyeccion_ya_no_trae_de_la_base_lo_que_no_se_muestra():
    """Dos capas: la proyección es de lo permitido, no sólo el contrato. Así el
    día que alguien toque el modelo, la base igual no trae la nota."""
    from models.cuenta import LO_QUE_VE_DE_SU_VERIFICACION
    assert LO_QUE_VE_DE_SU_VERIFICACION["_id"] == 0
    permitidos = {c for c, v in LO_QUE_VE_DE_SU_VERIFICACION.items() if v == 1}
    assert permitidos == {"status", "submitted_at", "verified_at", "document_type"}
    assert not any(v == 0 for c, v in LO_QUE_VE_DE_SU_VERIFICACION.items() if c != "_id"), "es de lo permitido"


def test_sin_verificacion_dice_none_y_nada_mas(base):
    from routes.misc import router
    r = cliente_con(router).get("/api/verification/status")
    assert r.status_code == 200 and r.json() == {"status": "none"}


def test_solo_ve_la_suya(verificacion):
    ya(verificacion.verifications.insert_one({"user_id": "u_otro", "status": "rejected",
                                              "submitted_at": datetime(2026, 9, 5, tzinfo=timezone.utc)}))
    from routes.misc import router
    assert cliente_con(router).get("/api/verification/status").json()["status"] == "approved"


# ── Cada capa, sola ─────────────────────────────────────────────────────────
#
# La proyección y el contrato se tapan entre sí: con cualquiera de las dos
# puesta, el test de arriba pasa. Estos prueban cada una por separado, porque
# una guarda que sólo pasa gracias a la otra no se sabe si anda.

def test_EL_CONTRATO_SOLO_CORTA_AUNQUE_LA_PROYECCION_TRAIGA_TODO(verificacion, monkeypatch):
    import routes.misc as misc
    monkeypatch.setattr(misc, "LO_QUE_VE_DE_SU_VERIFICACION", {"_id": 0})     # la proyección vieja
    texto = cliente_con(misc.router).get("/api/verification/status").text
    for valor in ("sospechosa", "alto", "Carla Agente", "base64", "52998224725"):
        assert valor not in texto, valor


def test_el_contrato_declara_exactamente_los_cuatro_campos():
    from models.cuenta import EstadoDeMiVerificacion
    assert set(EstadoDeMiVerificacion.model_fields) == {"status", "submitted_at", "verified_at", "document_type"}


class _BaseQueAnota:
    """La base de siempre, anotando qué proyección le piden a `verifications`."""
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "verifications":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            async def find_one(self, filtro, proyeccion=None, **k):
                anotadas.append(proyeccion)
                return await coleccion.find_one(filtro, proyeccion, **k)
        return _Col()


def test_LA_PROYECCION_SOLA_NO_TRAE_DE_LA_BASE_LO_QUE_NO_SE_MUESTRA(verificacion):
    import routes.misc as misc
    anotadas = []
    usar_base(_BaseQueAnota(verificacion, anotadas))
    cliente_con(misc.router).get("/api/verification/status")
    (proyeccion,) = anotadas
    assert proyeccion.get("_id") == 0 and all(v == 1 for c, v in proyeccion.items() if c != "_id"), proyeccion
    assert set(c for c in proyeccion if c != "_id") == {"status", "submitted_at", "verified_at", "document_type"}
