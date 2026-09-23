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


# ══════════════════════════════════════════════════════════════════════════
# 2. /auth/me y la seguridad de la cuenta
# ══════════════════════════════════════════════════════════════════════════

from services.money import to_decimal128                      # noqa: E402

SECRETOS_DE_LA_CUENTA = {
    "password_hash": "$2b$12$hash", "two_factor_secret": "JBSWY3DPEHPK3PXP",
    "two_factor_backup_hashes": ["h1", "h2"], "pin_hash": "$2b$pin", "pin_failed_attempts": 2,
    "webauthn_credentials": [{"credential_id": "c1", "public_key": "pk"}],
    "permissions": ["kyc"], "admin_note": "nota interna", "rejection_reason": "doc ilegible",
}


@pytest.fixture
def cuenta(base):
    ya(base.users.insert_one({
        "user_id": "u_ana", "email": "ana@ejemplo.test", "name": "Ana", "role": "user",
        "verification_status": "verified", "cpf_number": "52998224725", "referral_code": "ANA123",
        "balance_ris": to_decimal128("150.25"), "password_set": True, "must_change_password": False,
        "two_factor_enabled": True, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        **SECRETOS_DE_LA_CUENTA}))
    return base


def test_AUTH_ME_SIGUE_DEVOLVIENDO_LO_SUYO_Y_NADA_MAS(cuenta):
    from routes.auth import router
    r = cliente_con(router).get("/api/auth/me")
    assert r.status_code == 200
    j = r.json()
    assert j["user_id"] == "u_ana" and j["email"] == "ana@ejemplo.test" and j["balance_ris"] == 150.25
    assert j["cpf_number"] == "52998224725" and j["referral_code"] == "ANA123" and j["password_set"] is True
    for secreto in SECRETOS_DE_LA_CUENTA:
        assert secreto not in j, secreto


def test_auth_me_no_inventa_campos_que_la_cuenta_no_tiene(cuenta):
    """`exclude_unset`: lo que la cuenta no tiene no sale, ni siquiera como
    `null`. La pantalla distingue «no está» de «está vacío»."""
    from routes.auth import router
    j = cliente_con(router).get("/api/auth/me").json()
    assert "phone" not in j and "gestor_code" not in j and "cep_origen" not in j


def test_EL_CONTRATO_DE_AUTH_ME_SOLO_CORTA_AUNQUE_LA_PROYECCION_TRAIGA_TODO(cuenta, monkeypatch):
    import routes.auth as auth
    monkeypatch.setattr(auth, "LO_QUE_VE_SU_DUENO", {"_id": 0})
    texto = cliente_con(auth.router).get("/api/auth/me").text
    for valor in ("JBSWY3DPEHPK3PXP", "$2b$", "nota interna", "doc ilegible", "public_key"):
        assert valor not in texto, valor


def test_EL_CONTRATO_DE_AUTH_ME_SALE_DE_LA_MISMA_LISTA_QUE_LA_PROYECCION():
    """Generado, no escrito a mano: dos listas de los mismos campos terminan
    distintas, y el campo se pierde en silencio."""
    from models.cuenta import PerfilDelDueno
    from services.perfil import LO_PERMITIDO
    assert set(PerfilDelDueno.model_fields) == set(LO_PERMITIDO)


def test_auth_me_sin_cuenta_devuelve_null_y_no_un_500(base):
    from routes.auth import router
    r = cliente_con(router).get("/api/auth/me")
    assert r.status_code == 200 and r.json() is None


def test_LAS_TRES_RUTAS_DE_SEGURIDAD_DICEN_EL_ESTADO_Y_NINGUN_SECRETO(cuenta):
    from routes.auth import router as auth_router
    from routes.pin import router as pin_router
    from routes.security_2fa import router as dos_pasos_router
    r = cliente_con(auth_router).get("/api/auth/password-status")
    assert r.status_code == 200 and r.json() == {"password_set": True, "must_change_password": False}
    r = cliente_con(dos_pasos_router).get("/api/auth/2fa/status")
    assert r.status_code == 200 and set(r.json()) == {"enabled", "role", "is_required", "backup_codes_remaining"}
    assert r.json()["enabled"] is True and r.json()["backup_codes_remaining"] == 2
    r = cliente_con(pin_router).get("/api/pin/status")
    assert r.status_code == 200 and set(r.json()) == {"has_pin", "must_reset", "locked", "locked_seconds", "is_super_admin"}
    assert r.json()["has_pin"] is True
    for texto in (cliente_con(dos_pasos_router).get("/api/auth/2fa/status").text, cliente_con(pin_router).get("/api/pin/status").text):
        for valor in ("JBSWY3DPEHPK3PXP", "$2b$", "h1"):
            assert valor not in texto


@pytest.mark.parametrize("modelo,campos", [
    ("EstadoDeLaClave", {"password_set", "must_change_password"}),
    ("EstadoDeDosPasos", {"enabled", "role", "is_required", "backup_codes_remaining"}),
    ("EstadoDelPin", {"has_pin", "must_reset", "locked", "locked_seconds", "is_super_admin"}),
])
def test_los_contratos_de_seguridad_declaran_exactamente_lo_que_la_pantalla_lee(modelo, campos):
    import models.cuenta as mc
    assert set(getattr(mc, modelo).model_fields) == campos


# ── Que cada ruta tenga PUESTO su contrato ──────────────────────────────────
#
# Estas rutas ya armaban su respuesta a mano, así que sacarles el contrato no
# filtra nada HOY. Lo que el contrato protege es el día de mañana: el campo
# que alguien agregue al diccionario sin pensar. Por eso se prueba que esté
# puesto, además de lo que devuelve.

@pytest.mark.parametrize("modulo,camino,modelo", [
    ("routes.misc", "/verification/status", "EstadoDeMiVerificacion"),
    ("routes.auth", "/auth/me", "PerfilDelDueno"),
    ("routes.auth", "/auth/password-status", "EstadoDeLaClave"),
    ("routes.security_2fa", "/auth/2fa/status", "EstadoDeDosPasos"),
    ("routes.pin", "/pin/status", "EstadoDelPin"),
])
def test_CADA_RUTA_DE_LA_CUENTA_TIENE_SU_CONTRATO_PUESTO(modulo, camino, modelo):
    import importlib
    import typing
    import models.cuenta as mc
    router = importlib.import_module(modulo).router
    (ruta,) = [r for r in router.routes if getattr(r, "path", None) == camino and "GET" in r.methods]
    declarado = ruta.response_model
    if typing.get_origin(declarado) is typing.Union:
        declarado = next(a for a in typing.get_args(declarado) if a is not type(None))
    assert declarado is getattr(mc, modelo), (camino, declarado)
