"""
tests/test_la_contrasena_obligada.py — Que quien entra con una temporal pueda salir.

EL DEFECTO QUE ESTE ARCHIVO CIERRA

    Cuando un administrador resetea la contraseña de alguien, la cuenta queda
    con `must_change_password` y la aplicación la manda a
    `/force-change-password` desde cualquier lado. Esa pantalla llamaba a
    `POST /auth/set-new-password`.

    Esa ruta NO EXISTIA. Nunca existió: hay un test suelto que la describe, en
    un archivo que no corre en esta suite, y nada más.

    O sea que cada persona a la que le resetearon la contraseña quedó
    encerrada. El único botón que le funcionaba era «Cerrar sesión», y el
    cartel decía «Not Found» —el `detail` de una dirección que no existe—, que
    no se parece en nada a «esta función no está hecha».

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que la marca sea lo ÚNICO que autoriza. Sin ella, esta ruta cambia la
       contraseña sin pedir la actual y sin el código del correo: sería
       quedarse para siempre con cualquier cuenta cuya sesión alguien haya
       conseguido.
    2. Que se cierren las demás sesiones. Este camino existe porque alguien
       avisó que le tomaron la cuenta.
    3. Que la nueva no pueda ser la temporal, que es la que el administrador
       conoce.
    4. Que la ruta exista y funcione, que es por lo que empezó todo.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI                                 # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

from conftest import usar_base                              # noqa: E402
from models.user import User                                # noqa: E402
from routes import auth as rutas_auth                       # noqa: E402
from routes import dependencies as deps                     # noqa: E402
from routes import security_2fa                             # noqa: E402
from utils.security import hash_password, verify_password   # noqa: E402

TEMPORAL = "Temporal.9xK!"
NUEVA = "MiClave.Propia1!"

QUIEN = User(user_id="u1", name="Jhose", email="jhose@ejemplo.com", role="user")


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_obligada"]
    usar_base(b)
    return b


@pytest.fixture
def cliente(base, monkeypatch):
    """La ruta sola, sin correo y sin limitador.

    El correo se sustituye porque mandarlo de verdad desde la suite le
    escribiría a una casilla ajena; ya pasó en este repositorio.
    """
    async def sin_correo(*a, **k):
        return True
    monkeypatch.setattr(rutas_auth, "notify_password_change", sin_correo)
    try:
        security_2fa.limiter.limiter.storage.reset()
    except Exception:
        pass

    app = FastAPI()
    app.include_router(rutas_auth.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: QUIEN
    return TestClient(app)


async def _sembrar(base, *, obligado=True, clave=TEMPORAL):
    await base.users.delete_many({"user_id": "u1"})
    await base.users.insert_one({
        "user_id": "u1", "email": "jhose@ejemplo.com", "name": "Jhose",
        "role": "user", "password_hash": hash_password(clave),
        "password_set": True, "must_change_password": obligado,
    })


def _poner(cliente, nueva=NUEVA, confirmar=None):
    return cliente.post("/api/auth/set-new-password", json={
        "new_password": nueva,
        "confirm_password": nueva if confirmar is None else confirmar,
    })


# ══════════════════════════════════════════════════════════════════════════
# 1. La ruta existe y hace lo suyo
# ══════════════════════════════════════════════════════════════════════════

def test_LA_RUTA_EXISTE(base, cliente):
    """LA REPRODUCCION DEL DEFECTO.

    Si esto devuelve 404, la pantalla del cambio obligado está rota otra vez y
    la gente a la que le resetearon la contraseña queda encerrada.
    """
    asyncio.run(_sembrar(base))
    r = _poner(cliente)
    assert r.status_code == 200, r.text


def test_LA_CONTRASENA_QUEDA_CAMBIADA_DE_VERDAD(base, cliente):
    """No alcanza con que conteste 200: tiene que poder entrar con la nueva."""
    asyncio.run(_sembrar(base))
    assert _poner(cliente).status_code == 200

    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert verify_password(NUEVA, guardado["password_hash"]), "no se guardó"
    assert not verify_password(TEMPORAL, guardado["password_hash"]), \
        "la temporal sigue sirviendo"


def test_LA_MARCA_SE_BAJA(base, cliente):
    """Si no se bajara, la aplicación lo seguiría mandando a la misma pantalla
    para siempre, que es justo el encierro que esto viene a abrir."""
    asyncio.run(_sembrar(base))
    assert _poner(cliente).status_code == 200
    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert guardado["must_change_password"] is False


# ══════════════════════════════════════════════════════════════════════════
# 2. La marca es lo único que autoriza
# ══════════════════════════════════════════════════════════════════════════

def test_SIN_LA_MARCA_NO_SE_PUEDE_CAMBIAR_NADA(base, cliente):
    """LA GUARDA QUE MAS IMPORTA.

    Esta ruta no pide la contraseña actual ni el código del correo. Sin la
    marca, sería la forma de quedarse para siempre con cualquier cuenta cuya
    sesión alguien haya conseguido.
    """
    asyncio.run(_sembrar(base, obligado=False))
    r = _poner(cliente)
    assert r.status_code == 403, r.text

    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert verify_password(TEMPORAL, guardado["password_hash"]), \
        "cambió la contraseña de una cuenta que no tenía cambio pendiente"


def test_NO_SE_PUEDE_USAR_DOS_VECES(base, cliente):
    """La segunda llamada ya no tiene la marca: no puede volver a escribir."""
    asyncio.run(_sembrar(base))
    assert _poner(cliente).status_code == 200
    assert _poner(cliente, nueva="OtraMas.Distinta2!").status_code == 403

    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert verify_password(NUEVA, guardado["password_hash"]), \
        "la segunda llamada pisó la contraseña"


class _UsuariosQueSePierdenLaMarca:
    """`users`, pero a la primera lectura le baja la marca al usuario.

    Es la ventana entre la lectura y la escritura, abierta a propósito. Se
    envuelve la COLECCION y no se parchea con `monkeypatch.setattr` porque
    `base.users` devuelve un objeto nuevo en cada acceso: el parche caería en
    uno descartable y el test pasaría sin probar nada. Ya pasó al escribirlo.
    """

    def __init__(self, real, ya_paso):
        self._real = real
        self._ya_paso = ya_paso

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    async def find_one(self, filtro, *a, **k):
        doc = await self._real.find_one(filtro, *a, **k)
        if doc and doc.get("must_change_password") and not self._ya_paso:
            self._ya_paso.append(True)
            await self._real.update_one(
                {"user_id": doc["user_id"]},
                {"$set": {"must_change_password": False}})
        return doc


class _BaseConLaVentanaAbierta:
    """Deja pasar todo tal cual, salvo `users`."""

    def __init__(self, real):
        self._real = real
        self._ya_paso = []

    def __getattr__(self, nombre):
        col = getattr(self._real, nombre)
        if nombre != "users":
            return col
        return _UsuariosQueSePierdenLaMarca(col, self._ya_paso)

    def __getitem__(self, nombre):
        return getattr(self, nombre)


def test_SI_LA_MARCA_SE_CAE_ENTRE_LA_LECTURA_Y_LA_ESCRITURA_NO_SE_ESCRIBE(
        base, cliente, monkeypatch):
    """La carrera que cubre tener la marca DENTRO del filtro del update.

    La ruta lee el usuario, decide, y después escribe. Entre esas dos cosas
    hay una ventana: otra pestaña que termina el trámite, un administrador que
    toca la cuenta. Si la escritura no volviera a exigir la marca, la llamada
    tardía pisaría la contraseña que se acaba de poner — y quien la eligió se
    quedaría afuera con una que nunca escribió.

    Acá esa ventana se abre a propósito: se baja la marca justo DESPUES de que
    la ruta leyó el usuario. Es la única forma de probar una carrera sin
    depender de que dos pedidos caigan en el orden justo.
    """
    asyncio.run(_sembrar(base))
    monkeypatch.setattr(rutas_auth, "db", _BaseConLaVentanaAbierta(base))

    r = _poner(cliente)
    assert r.status_code == 409, r.text

    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert verify_password(TEMPORAL, guardado["password_hash"]), \
        "escribió la contraseña aunque la marca ya no estaba"


# ══════════════════════════════════════════════════════════════════════════
# 3. Lo que no se acepta como contraseña nueva
# ══════════════════════════════════════════════════════════════════════════

def test_LA_NUEVA_NO_PUEDE_SER_LA_TEMPORAL(base, cliente):
    """Sería dar el trámite por hecho con la contraseña que el administrador
    conoce, que es exactamente lo que este paso viene a deshacer."""
    asyncio.run(_sembrar(base))
    r = _poner(cliente, nueva=TEMPORAL)
    assert r.status_code == 400, r.text

    guardado = asyncio.run(base.users.find_one({"user_id": "u1"}))
    assert guardado["must_change_password"] is True, \
        "se dio por hecho el cambio sin cambiar nada"


def test_LAS_DOS_TIENEN_QUE_COINCIDIR(base, cliente):
    asyncio.run(_sembrar(base))
    r = _poner(cliente, nueva=NUEVA, confirmar="Otra.Cosa1!")
    assert r.status_code == 400, r.text
    assert "coinciden" in r.json()["detail"].lower()


@pytest.mark.parametrize("floja", ["corta1!", "todaminuscula1!", "SINNUMEROS!!aa"])
def test_UNA_CONTRASENA_FLOJA_NO_ENTRA(base, cliente, floja):
    """La misma política que el resto de la aplicación. Que este camino sea el
    de una emergencia no lo hace el camino de las contraseñas malas."""
    asyncio.run(_sembrar(base))
    assert _poner(cliente, nueva=floja).status_code == 400


# ══════════════════════════════════════════════════════════════════════════
# 4. Las otras sesiones
# ══════════════════════════════════════════════════════════════════════════

def test_SE_CIERRAN_LAS_OTRAS_SESIONES(base, cliente):
    """Este camino existe porque alguien avisó que le tomaron la cuenta. Si las
    sesiones del intruso sobrevivieran, el cambio no serviría de nada."""
    async def sembrar_sesiones():
        await _sembrar(base)
        await base.user_sessions.insert_many([
            {"session_id": "s_intruso", "session_token": "tok_intruso",
             "user_id": "u1", "is_active": True},
            {"session_id": "s_otra", "session_token": "tok_otra",
             "user_id": "u1", "is_active": True},
        ])
    asyncio.run(sembrar_sesiones())

    assert _poner(cliente).status_code == 200

    vivas = asyncio.run(base.user_sessions.count_documents(
        {"user_id": "u1", "is_active": True}))
    assert vivas == 0, "quedó viva una sesión de antes del cambio"
