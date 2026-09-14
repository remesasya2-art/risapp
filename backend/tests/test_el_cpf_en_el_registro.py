"""
tests/test_el_cpf_en_el_registro.py — Que la cuenta nazca atada a una persona.

POR QUE EL CPF SE PIDE AL REGISTRARSE

    Es lo que ata una cuenta a alguien, y es el dato que la recarga necesita
    igual —PIX exige identificar al pagador—. Pidiéndolo una sola vez, la
    persona no lo tipea dos veces y el número que va al banco es el mismo que
    declaró el primer día.

    Y hace posible la regla que sostiene el cupo inicial: UN CPF, UNA CUENTA.
    Sin ella, 200 R$ sin verificar por cuenta es 200 R$ por cada correo que
    alguien se moleste en crear.

LO QUE SE VIGILA ACA

    Que la ruta lo exija, que compruebe los dígitos verificadores, que respete
    la lista negra y que no deje abrir dos cuentas con el mismo. Las cuatro
    cosas EN EL SERVIDOR: en el navegador se apagan con la consola abierta.
"""
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
from routes import auth as rutas_auth                       # noqa: E402
from routes import security_2fa                             # noqa: E402

UNO = "52998224725"
OTRO = "11144477735"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_cpf_registro"]
    usar_base(b)
    return b


@pytest.fixture
def cliente(base, monkeypatch):
    """La ruta de registro sola, sin correo y sin limitador.

    El correo se sustituye porque mandarlo de verdad desde la suite le
    escribiría a una casilla ajena; ya pasó en este repositorio. El limitador
    se vacía porque el registro admite diez por hora y por IP, y con
    `TestClient` todos los pedidos vienen de la misma.
    """
    async def sin_correo(*a, **k):
        return True
    monkeypatch.setattr(rutas_auth, "send_verification_email", sin_correo)
    try:
        security_2fa.limiter.limiter.storage.reset()
    except Exception:
        pass

    app = FastAPI()
    app.include_router(rutas_auth.router, prefix="/api")
    return TestClient(app)


def _registrar(cliente, correo="ana@ejemplo.com", cpf=UNO, **extra):
    cuerpo = {"name": "Ana", "email": correo,
              "password": "Clave.larga1!", "confirm_password": "Clave.larga1!",
              **extra}
    if cpf is not None:
        cuerpo["cpf_number"] = cpf
    return cliente.post("/api/auth/register", json=cuerpo)


# ══════════════════════════════════════════════════════════════════════════
# 1. Es obligatorio, y se comprueba de verdad
# ══════════════════════════════════════════════════════════════════════════

def test_SIN_CPF_NO_SE_PUEDE_REGISTRAR(cliente):
    """Si fuera opcional, la cuenta nacería sin atadura y la recarga se
    trabaría más adelante — que es de dónde vino todo esto."""
    assert _registrar(cliente, cpf=None).status_code == 422


def test_UN_CPF_INVENTADO_NO_ABRE_CUENTA(cliente):
    """Once dígitos no son un CPF. Es lo que la aplicación aceptaba antes."""
    r = _registrar(cliente, cpf="12345678900")
    assert r.status_code == 400, r.text
    assert "cpf" in r.json()["detail"].lower()


def test_UN_DIGITO_CAMBIADO_NO_ABRE_CUENTA(cliente):
    """El error que más pasa. Si entra, queda guardado y el pago no cuadra."""
    roto = UNO[:-1] + str((int(UNO[-1]) + 1) % 10)
    assert _registrar(cliente, cpf=roto).status_code == 400


def test_UN_CPF_DE_VERDAD_ABRE_CUENTA(cliente, base):
    import asyncio
    assert _registrar(cliente).status_code == 200

    pendiente = asyncio.run(
        base.pending_verifications.find_one({"email": "ana@ejemplo.com"}))
    assert pendiente["cpf_number"] == UNO


def test_SE_GUARDA_NORMALIZADO_AUNQUE_SE_ESCRIBA_CON_PUNTOS(cliente, base):
    """Si se guardaran las dos formas, la comparación de la recarga fallaría
    según cómo lo hubiera tipeado la persona ese día."""
    import asyncio
    assert _registrar(cliente, cpf="529.982.247-25").status_code == 200

    pendiente = asyncio.run(
        base.pending_verifications.find_one({"email": "ana@ejemplo.com"}))
    assert pendiente["cpf_number"] == UNO


# ══════════════════════════════════════════════════════════════════════════
# 2. Un CPF, una cuenta
# ══════════════════════════════════════════════════════════════════════════

def test_UN_CPF_QUE_YA_TIENE_CUENTA_NO_ABRE_OTRA(cliente, base):
    """La regla que sostiene el cupo. Sin ella, 200 R$ por cada correo."""
    import asyncio
    asyncio.run(base.users.insert_one(
        {"user_id": "u_vieja", "email": "vieja@ejemplo.com", "cpf_number": UNO}))

    r = _registrar(cliente, correo="nueva@ejemplo.com", cpf=UNO)
    assert r.status_code == 400, r.text
    assert "cuenta" in r.json()["detail"].lower()


def test_OTRO_CPF_SI_ABRE_CUENTA(cliente, base):
    import asyncio
    asyncio.run(base.users.insert_one(
        {"user_id": "u_vieja", "email": "vieja@ejemplo.com", "cpf_number": UNO}))
    assert _registrar(cliente, correo="nueva@ejemplo.com",
                      cpf=OTRO).status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 3. La lista negra
# ══════════════════════════════════════════════════════════════════════════

def test_UN_CPF_VETADO_NO_ABRE_CUENTA(cliente, base):
    """Cortarle el paso antes de que invierta tiempo en el flujo es la mitad
    del motivo por el que el CPF se pide acá y no más adelante."""
    import asyncio
    asyncio.run(base.blacklist.insert_one({"type": "cpf", "value": UNO}))
    assert _registrar(cliente).status_code == 400


def test_EL_MENSAJE_DEL_VETO_NO_CONFIRMA_QUE_ESTE_VETADO(cliente, base):
    """Si lo dijera, el registro sería una forma de averiguar quién está en la
    lista: se prueba un CPF y el mensaje contesta."""
    import asyncio
    asyncio.run(base.blacklist.insert_one({"type": "cpf", "value": UNO}))
    detalle = _registrar(cliente).json()["detail"].lower()
    assert "lista" not in detalle and "veta" not in detalle, detalle
