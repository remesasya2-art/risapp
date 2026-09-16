"""
tests/test_el_cupo_inicial_se_puede_usar.py — Que el cliente nuevo pueda empezar.

EL DEFECTO QUE ESTE ARCHIVO CIERRA

    El servidor le da a toda cuenta sin verificar un cupo inicial —200 R$ y 2
    operaciones, configurables desde el panel— y la página «Cómo funciona» se lo
    promete al visitante, con esos números sacados de la configuración.

    `/gestor/pix/create` lo respetaba: no exigía KYC, sólo preguntaba al cupo.
    Pero la PANTALLA de recarga mandaba a verificarse antes de dejar intentar:

        if (user?.verification_status !== 'verified') {
          navigate('/verification');

    Así que ese cupo no lo podía usar NADIE. El cliente nuevo se registraba,
    entraba a recargar, y salía a la pantalla de verificación sin haber podido
    hacer su primera operación. El servidor lo permitía, la web lo prometía, y
    la pantalla no lo dejaba.

    Un portón que contradice al servidor no se ve en ninguna prueba del
    servidor: por eso este archivo prueba LA RUTA, que es donde la decisión
    tiene que vivir, y la pantalla quedó sin el portón.

LO QUE TAMBIEN SE VIGILA ACA

    Que el CPF del pago sea el de la cuenta, comprobado EN EL SERVIDOR. Antes
    el control vivía sólo en el navegador y `client_cpf` traía «00000000000»
    por omisión: se saltaba con la consola abierta.
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

from conftest import ensenarle_decimal128_a_mongomock, usar_base   # noqa: E402
ensenarle_decimal128_a_mongomock()

from models.user import User                                # noqa: E402
from routes import dependencies as deps                     # noqa: E402
from routes import gestor_pix                               # noqa: E402

UNO = "52998224725"
OTRO = "11144477735"

SIN_VERIFICAR = User(user_id="u_nuevo", name="Ana", email="ana@ejemplo.com",
                     role="user")


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_cupo"]
    usar_base(b)
    return b


class _MercadoPagoDeMentira:
    """Contesta como Mercado Pago cuando todo sale bien, sin red ni credencial."""

    def create_pix_payment(self, **kwargs):
        return {
            "success": True,
            "payment_id": 178336825747,
            "qr_code": "00020126580014BR.GOV.BCB.PIX-DE-MENTIRA",
            "qr_code_base64": "iVBORw0KGgo=",
        }


@pytest.fixture
def cliente(base, monkeypatch):
    """La ruta de PIX montada sola, con un Mercado Pago de mentira.

    ACA SE APAGABA MERCADO PAGO (`MP_AVAILABLE = False`), con este motivo:
    «no se prueba que el QR salga, se prueba QUIEN puede pedirlo y con qué
    CPF». El motivo sigue siendo bueno —no queremos depender de la red ni de
    una credencial— pero apagarlo dejó de servir.

    Desde que un cobro sin código devuelve 503 en vez de guardarse vacío, con
    Mercado Pago apagado la ruta falla SIEMPRE, y estos tests pasaban a probar
    el fallo en vez del cupo.

    Y mirándolo bien, apagarlo nunca fue lo correcto: hacía que estos tests
    recorrieran un camino que producción no recorre nunca. Un doble que
    contesta bien prueba lo mismo, sin red, y por el camino de verdad.
    """
    monkeypatch.setattr(gestor_pix, "MP_AVAILABLE", True)
    monkeypatch.setattr(gestor_pix, "mercadopago_service", _MercadoPagoDeMentira())

    app = FastAPI()
    app.include_router(gestor_pix.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: SIN_VERIFICAR
    return TestClient(app)


async def _sembrar(base, *, cpf=None, verificado=False, usado_ris="0", usadas=0):
    doc = {
        "user_id": "u_nuevo", "email": "ana@ejemplo.com", "role": "user",
        "verification_status": "verified" if verificado else "unverified",
        "kyc_quota": {"ops": usadas, "ris": usado_ris},
    }
    if cpf:
        doc["cpf_number"] = cpf
    await base.users.delete_many({"user_id": "u_nuevo"})
    await base.users.insert_one(doc)


def _pedir(cliente, monto=50, cpf=UNO):
    return cliente.post("/api/gestor/pix/create",
                        json={"amount_ris": monto, "client_cpf": cpf})


# ══════════════════════════════════════════════════════════════════════════
# 1. El cupo inicial, que es lo que estaba trabado
# ══════════════════════════════════════════════════════════════════════════

def test_EL_CUPO_INICIAL_DEJA_RECARGAR_SIN_VERIFICAR(base, cliente):
    """LA REPRODUCCION DEL DEFECTO.

    Si esto se pone rojo, el cliente nuevo no puede hacer su primera recarga y
    la promesa de la página «Cómo funciona» es mentira.
    """
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO))
    r = _pedir(cliente, monto=50)
    assert r.status_code == 200, r.text


def test_pasarse_del_cupo_se_rechaza_con_el_motivo(base, cliente):
    """El cupo sigue existiendo: lo que se sacó fue el portón, no el límite."""
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO))
    r = _pedir(cliente, monto=5000)
    assert r.status_code == 403, r.text
    assert "verific" in r.json()["detail"].lower(), r.text


def test_agotadas_las_operaciones_no_se_puede_seguir(base, cliente):
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO, usadas=2))
    r = _pedir(cliente, monto=10)
    assert r.status_code == 403, r.text


def test_una_cuenta_verificada_no_tiene_ese_techo(base, cliente):
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO, verificado=True, usadas=99))
    r = _pedir(cliente, monto=500)
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
# 2. El CPF, comprobado en el servidor
# ══════════════════════════════════════════════════════════════════════════

def test_NO_SE_PUEDE_PAGAR_CON_EL_CPF_DE_OTRO(base, cliente):
    """La atadura entera. Antes esto lo miraba sólo el navegador."""
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO))
    r = _pedir(cliente, cpf=OTRO)
    assert r.status_code == 403, r.text


def test_EL_CPF_ES_OBLIGATORIO(base, cliente):
    """Tenía «00000000000» por omisión: el campo se podía omitir y el pago salía."""
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO))
    r = cliente.post("/api/gestor/pix/create", json={"amount_ris": 50})
    assert r.status_code == 422, r.text


def test_UN_CPF_INVENTADO_NO_SIRVE(base, cliente):
    import asyncio
    asyncio.run(_sembrar(base, cpf=UNO))
    r = _pedir(cliente, cpf="12345678900")
    assert r.status_code == 400, r.text


def test_LA_CUENTA_VIEJA_SIN_CPF_LO_ATA_EN_SU_PRIMERA_RECARGA(base, cliente):
    """Son todas las que ya existían antes de que el registro lo pidiera.
    Sin esto, el cambio las rompe a todas."""
    import asyncio
    asyncio.run(_sembrar(base))
    r = _pedir(cliente, cpf=UNO)
    assert r.status_code == 200, r.text

    guardado = asyncio.run(base.users.find_one({"user_id": "u_nuevo"}))
    assert guardado["cpf_number"] == UNO

    # Y de ahí en adelante rige: con otro, no.
    r2 = _pedir(cliente, cpf=OTRO)
    assert r2.status_code == 403, r2.text
