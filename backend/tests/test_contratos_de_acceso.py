"""
tests/test_contratos_de_acceso.py — Las puertas de entrada a la cuenta salen
por un contrato, y ningún contrato se come un campo que su ruta devuelve.

Tercera tanda de los contratos de las acciones (las otras dos en
`test_contratos_de_acciones_de_dinero.py` y
`test_contratos_de_acciones_del_cliente.py`).

Lo que más importa es la sección 2: se entra con contraseña DE VERDAD, por
HTTP, con la primera capa rota a propósito —la puerta devuelve el documento
crudo del usuario, con el hash de la contraseña, la semilla del segundo
factor y el hash del PIN— y no sale nada de eso. Es exactamente el error que
ya pasó en estas rutas, cinco veces, con cinco listas de lo prohibido.
"""
import ast
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

_BACKEND = Path(__file__).resolve().parents[1]

# (archivo de la ruta, método, camino, contrato, dónde se arma la respuesta)
# El último es (archivo, funciones) cuando la ruta devuelve lo que arma otra
# función del módulo; si no, las claves se leen de la ruta misma (incluidas
# las funciones que define adentro, como `_do_login`).
RUTAS = [
    ("routes/auth.py", "POST", "/logout", "MiMensaje", None),
    ("routes/auth.py", "POST", "/register", "MiRegistroEmpezado", None),
    ("routes/auth.py", "POST", "/verify-email", "MiEntrada", None),
    ("routes/auth.py", "POST", "/resend-verification-code", "MiCodigoReenviado", None),
    ("routes/auth.py", "POST", "/login-password", "MiEntrada", None),
    ("routes/auth.py", "POST", "/heartbeat", "MiLatido", None),
    ("routes/auth.py", "POST", "/offline", "MiLatido", None),
    ("routes/auth.py", "POST", "/personal/invitacion", "MiInvitacion", None),
    ("routes/auth.py", "POST", "/personal/activar", "MiEntrada", None),
    ("routes/google_ingreso.py", "POST", "", "MiEntrada",
     ("routes/google_ingreso.py", ("_entrar_a_la_cuenta", "_empezar_el_registro"))),
    ("routes/google_ingreso.py", "POST", "/completar", "MiEntrada", None),
    ("routes/security_2fa.py", "POST", "/enroll-init", "MiAltaDeDosPasos", None),
    ("routes/security_2fa.py", "POST", "/enroll-confirm", "MiEntradaConDosPasos", None),
    ("routes/security_2fa.py", "POST", "/verify", "MiEntradaConDosPasos", None),
    ("routes/webauthn_login.py", "POST", "/login/verify", "MiEntrada", None),
]
_IDS = [f"{m} {a.split('/')[-1][:-3]}{c}" for a, m, c, _, _ in RUTAS]


def _ruta(archivo, metodo, camino):
    import importlib
    router = importlib.import_module(archivo[:-3].replace("/", ".")).router
    (r,) = [r for r in router.routes
            if r.path == (router.prefix or "") + camino and metodo in r.methods]
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Cada puerta tiene su contrato, y el contrato no se come nada
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_CADA_PUERTA_TIENE_SU_CONTRATO(archivo, metodo, camino, modelo, fuente):
    ruta = _ruta(archivo, metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def _de(d):
    return {k.value for k in d.keys if isinstance(k, ast.Constant)}


def _claves_de_las_funciones(archivo, nombres):
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    claves, encontradas = set(), set()
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name in nombres:
            encontradas.add(f.name)
            for r in ast.walk(f):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                    claves |= _de(r.value)
    assert encontradas == set(nombres), f"no encontré {set(nombres) - encontradas} en {archivo}"
    return claves


def _claves_de_la_ruta(archivo, metodo, camino):
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == metodo.lower()
                and d.args and isinstance(d.args[0], ast.Constant) and d.args[0].value == camino
                for d in f.decorator_list):
            return {k for r in ast.walk(f) if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict)
                    for k in _de(r.value)}
    raise AssertionError(f"no encontré {metodo} {camino} en {archivo}")    # pragma: no cover


def _claves(archivo, metodo, camino, fuente):
    return _claves_de_las_funciones(*fuente) if fuente else _claves_de_la_ruta(archivo, metodo, camino)


@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_PUERTA_DEVUELVE(archivo, metodo, camino, modelo, fuente):
    """Un contrato que se come un campo deja la entrada rota EN SILENCIO: la
    ruta contesta 200 y la pantalla no ve, por ejemplo, que falta el código
    del segundo factor. Es peor que no tener contrato."""
    ruta = _ruta(archivo, metodo, camino)
    faltan = _claves(archivo, metodo, camino, fuente) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino or '/'} devuelve {sorted(faltan)} y su contrato no los tiene"


def test_LA_LECTURA_DEL_CODIGO_ENCUENTRA_CLAVES():
    """Sin esto, el de arriba pasaría igual si la lectura dejara de encontrar
    diccionarios: cero claves de cero es verde y no prueba nada."""
    vacias = [c for a, m, c, _, f in RUTAS if not _claves(a, m, c, f)]
    assert vacias == [], vacias


def test_EL_USUARIO_DE_CADA_PUERTA_ES_EL_MISMO_QUE_EL_DEL_PERFIL():
    """El campo `user` de las puertas usa el contrato de `/auth/me`, que se
    genera de la lista de lo permitido. Si una puerta tuviera su propio
    contrato del usuario, volveríamos a tener dos listas que se separan."""
    from models.acciones_de_acceso import MiEntrada, MiEntradaConDosPasos
    from models.cuenta import PerfilDelDueno
    from routes.auth import get_me
    for modelo in (MiEntrada, MiEntradaConDosPasos):
        assert modelo.model_fields["user"].annotation.__args__[0] is PerfilDelDueno
    perfil = [r for r in __import__("routes.auth", fromlist=["router"]).router.routes
              if getattr(r, "endpoint", None) is get_me][0]
    assert perfil.response_model.__args__[0] is PerfilDelDueno


# ══════════════════════════════════════════════════════════════════════════
# 2. Entrar de verdad, con la primera capa rota
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")

CLAVE = "Colibri!2026x"

# Lo que la aplicación escribe en `users` y NO es de su dueño para ver. Los
# nombres salen de `tests/test_las_cinco_puertas.py`, que los buscó en el
# código: ninguno está inventado.
LO_QUE_NO_ES_SUYO = {
    "two_factor_secret": "JBSWY3DPEHPK3PXP",
    "two_factor_backup_hashes": ["$2b$12$uno"],
    "pin_hash": "$2b$12$pindelcliente",
    "webauthn_credentials": [{"public_key": "CLAVE-PUBLICA", "sign_count": 3}],
    "push_token": "ExponentPushToken[xxx]",
    "ban_reason": "motivo interno",
    "rejection_reason": "motivo interno del KYC",
}


@pytest.fixture
def cliente(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base, ensenarle_decimal128_a_mongomock
    from routes import auth as rutas_auth
    from services.money import to_decimal128
    from services.perfil import terminar_de_armar
    from utils.security import hash_password

    ensenarle_decimal128_a_mongomock()
    base = mongomock_motor.AsyncMongoMockClient()["contratos_de_acceso"]
    usar_base(base)
    asyncio.run(base.users.insert_one({
        "user_id": "u_ana", "email": "ana@ejemplo.com", "name": "Ana", "role": "user",
        "email_verified": True, "password_set": True, "verification_status": "verified",
        "balance_ris": to_decimal128("10.00"),
        "password_hash": hash_password(CLAVE), **LO_QUE_NO_ES_SUYO,
    }))
    # LA PRIMERA CAPA, ROTA A PROPOSITO: la puerta devuelve el documento
    # entero, sólo con los saldos convertidos para que no dé 500. Es el
    # `return user` de una tarde apurada.
    monkeypatch.setattr(rutas_auth, "para_su_dueno",
                        lambda d: terminar_de_armar({k: v for k, v in d.items() if k != "_id"}))
    app = FastAPI()
    app.include_router(rutas_auth.router, prefix="/api")
    return TestClient(app)


def test_AUNQUE_LA_PUERTA_DEVUELVA_EL_DOCUMENTO_CRUDO_NO_SALE_NADA_QUE_NO_SEA_SUYO(cliente):
    r = cliente.post("/api/auth/login-password", json={"email": "ana@ejemplo.com", "password": CLAVE})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["session_token"] and cuerpo["user"]["user_id"] == "u_ana"
    assert cuerpo["user"]["email"] == "ana@ejemplo.com" and cuerpo["user"]["balance_ris"] == 10.0
    for campo in ("password_hash", *LO_QUE_NO_ES_SUYO):
        assert campo not in r.text, f"el login dejó salir «{campo}»"
    for valor in ("$2b$", "JBSWY3DPEHPK3PXP", "CLAVE-PUBLICA", "motivo interno"):
        assert valor not in r.text, f"el login dejó salir «{valor}»"


def test_LO_QUE_LA_PUERTA_NO_PONE_NO_SALE_COMO_NULL(cliente):
    """`exclude_unset`: la pantalla de entrada decide qué hacer según qué
    claves vinieron. Un `two_factor_required: null` en una entrada sin
    segundo factor es una clave que antes no estaba."""
    r = cliente.post("/api/auth/login-password", json={"email": "ana@ejemplo.com", "password": CLAVE})
    assert set(r.json()) == {"message", "session_token", "user", "must_change_password"}
