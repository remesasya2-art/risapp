"""
tests/test_codigo_de_referido_para_cuentas_viejas.py — una cuenta de cliente
sin código de referido lo recibe al pedirlo, y nunca dos.

De donde sale: el dueño del proyecto entró a su perfil y la tarjeta del código
no aparecía. La cuenta había nacido antes de que existiera el código, y la
ruta devolvía vacío a propósito. Ver `routes/referidos.py`.
"""
import asyncio
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

FORMATO = re.compile(r"^REF[0-9A-F]{8}$")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["codigo_referido_viejas"]
    usar_base(m)
    return m


def cliente_como(quien):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.referidos import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


def persona(rol="user"):
    return User(user_id="u_vieja", name="Vieja", email="vieja@ejemplo.test", role=rol)


def codigo_guardado(base):
    return ya(base.users.find_one({"user_id": "u_vieja"}, {"_id": 0, "referral_code": 1})).get("referral_code")


# ══════════════════════════════════════════════════════════════════════════
# 1. La cuenta vieja recibe su código, y es siempre el mismo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("como_no_tiene", ["ausente", None, ""],
                         ids=["campo_ausente", "null_guardado", "cadena_vacia"])
def test_UNA_CUENTA_DE_CLIENTE_SIN_CODIGO_LO_RECIBE_AL_PEDIRLO(base, como_no_tiene):
    doc = {"user_id": "u_vieja", "role": "user"}
    if como_no_tiene != "ausente":
        doc["referral_code"] = como_no_tiene
    ya(base.users.insert_one(doc))

    r = cliente_como(persona()).get("/api/referidos/mi-codigo")

    assert r.status_code == 200
    codigo = r.json()["codigo"]
    assert FORMATO.match(codigo), f"el mismo formato que al nacer, no {codigo!r}"
    assert r.json()["enlace"].endswith(f"/register?ref={codigo}")
    assert codigo_guardado(base) == codigo, "tiene que quedar guardado, no inventarse en cada pedido"


def test_EL_SEGUNDO_PEDIDO_DEVUELVE_EL_MISMO_CODIGO(base):
    ya(base.users.insert_one({"user_id": "u_vieja", "role": "user"}))
    c = cliente_como(persona())
    primero = c.get("/api/referidos/mi-codigo").json()["codigo"]
    segundo = c.get("/api/referidos/mi-codigo").json()["codigo"]
    assert primero and primero == segundo


def test_UN_CODIGO_QUE_YA_EXISTE_NO_SE_TOCA(base):
    ya(base.users.insert_one({"user_id": "u_vieja", "role": "user", "referral_code": "REFAAAA1111"}))
    r = cliente_como(persona()).get("/api/referidos/mi-codigo")
    assert r.json()["codigo"] == "REFAAAA1111"
    assert codigo_guardado(base) == "REFAAAA1111"


# ══════════════════════════════════════════════════════════════════════════
# 2. La carrera: dos pedidos a la vez no dejan dos códigos
# ══════════════════════════════════════════════════════════════════════════

class _BaseConLecturaVieja:
    """La base de siempre, salvo que la PRIMERA lectura de `users` ve la foto
    de antes de que el otro pedido escribiera.

    Es un envoltorio y no un `monkeypatch` sobre `db.users.find_one` porque
    `db.users` devuelve una colección nueva en cada acceso: el parche caía en
    un objeto que la ruta nunca veía, y el test pasaba sin probar nada. Lo
    delató la mutación: quitarle la condición a la escritura lo dejaba verde.
    """
    def __init__(self, base):
        self._base, self._lecturas = base, 0

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "users":
            return coleccion
        envoltorio = self

        class _Col:
            async def find_one(self, *a, **k):
                envoltorio._lecturas += 1
                if envoltorio._lecturas == 1:
                    return {}
                return await coleccion.find_one(*a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_SI_OTRO_PEDIDO_GANO_LA_CARRERA_SE_DEVUELVE_EL_SUYO_Y_NO_SE_PISA(base):
    """El caso por el que esta ruta se negó durante un tiempo a generar códigos.

    Dos pedidos leen «no tiene». El primero escribe el suyo. El segundo llega
    a escribir con la lectura vieja en la mano. Con la forma obvia pisaría el
    código del primero, y el enlace que el primero ya mostró dejaría de
    apuntar a nadie.

    Acá se arma ese momento exacto: la base YA tiene el código del ganador,
    pero la primera lectura de este pedido ve la foto de antes.
    """
    ya(base.users.insert_one({"user_id": "u_vieja", "role": "user", "referral_code": "REFGANADOR"}))

    envuelta = _BaseConLecturaVieja(base)
    usar_base(envuelta)

    r = cliente_como(persona()).get("/api/referidos/mi-codigo")

    assert envuelta._lecturas >= 2, "la ruta tiene que haber visto la lectura vieja y releído"
    assert r.json()["codigo"] == "REFGANADOR", "tiene que devolver el que quedó, no el que generó"
    assert codigo_guardado(base) == "REFGANADOR", "el código del ganador no se pisa"


# ══════════════════════════════════════════════════════════════════════════
# 3. Administradores y personal siguen sin código
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rol", ["admin", "super_admin"])
def test_EL_EQUIPO_NO_RECIBE_CODIGO(base, rol):
    ya(base.users.insert_one({"user_id": "u_vieja", "role": rol}))
    r = cliente_como(persona(rol)).get("/api/referidos/mi-codigo")
    assert r.status_code == 200 and r.json() == {"codigo": "", "enlace": ""}
    assert codigo_guardado(base) is None, "no se escribe nada en la cuenta"


# ══════════════════════════════════════════════════════════════════════════
# 4. Un solo formato
# ══════════════════════════════════════════════════════════════════════════

def test_EL_ALTA_Y_LA_RUTA_USAN_EL_MISMO_GENERADOR():
    """Si alguien vuelve a escribir la fórmula a mano en uno de los dos
    lugares, los códigos terminan con dos formatos."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    alta = (raiz / "services" / "alta_de_cuenta.py").read_text()
    ruta = (raiz / "routes" / "referidos.py").read_text()
    assert "referral_code = nuevo_codigo_de_referido()" in alta
    assert "alta_de_cuenta.nuevo_codigo_de_referido()" in ruta
    assert 'f"REF{' not in ruta
    from services.alta_de_cuenta import nuevo_codigo_de_referido
    assert FORMATO.match(nuevo_codigo_de_referido())
