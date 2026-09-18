"""La tarjeta «Primeros pasos»: lo que le falta a una cuenta nueva para andar.

QUE PASABA
    El registro deja a la persona logueada y la manda al panel: saldo en
    cero, historial vacío, y nada que diga qué hacer. Los empujones a
    verificarse aparecían recién cuando algo se trababa.

LO QUE SE PRUEBA
    1. Que una cuenta recién creada tenga los tres pasos pendientes, y que
       la respuesta traiga SOLO esos estados: ni saldos ni documentos.
    2. Que «ya recargó» mire las cinco puertas por las que entra plata, y
       sólo las TERMINADAS: un PIX vencido no es una recarga.
    3. Que «ya envió» no cuente lo rechazado ni lo cancelado.
    4. Que mire sólo la cuenta propia.
    5. Que «completo» no dependa de la huella, que es opcional.
    6. Que la ruta exija sesión y use el `user_id` de la sesión.
    7. Que la tarjeta exista, cuelgue del panel y se apoye en el servidor.
"""
import ast
import asyncio
import os
import pathlib
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_PANEL = pathlib.Path(_BACKEND, "..", "frontend", "src", "pages", "Dashboard.jsx").resolve()
_TARJETA = pathlib.Path(_BACKEND, "..", "frontend", "src", "components", "dashboard", "PrimerosPasos.jsx").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                      # noqa: E402
from services import primeros_pasos                                 # noqa: E402
from services.money import to_decimal128                            # noqa: E402

AHORA = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
LO_QUE_DEVUELVE = {"verificacion", "recarga", "envio", "huella", "completo"}


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_primeros_pasos"]
    usar_base(b)
    yield b


async def cuenta(base, uid="u_1", estado="unverified", saldo="0", huella=None):
    doc = {"user_id": uid, "email": f"{uid}@ejemplo.com", "name": "Alguien", "role": "user",
           "verification_status": estado, "balance_ris": to_decimal128(saldo),
           "cpf_number": "12345678909", "password_hash": "no-viaja"}
    if huella is not None:
        doc["webauthn_credentials"] = huella
    await base.users.insert_one(doc)


# ══════════════════════════════════════════════════════════════════════════
# 1. Recién creada
# ══════════════════════════════════════════════════════════════════════════

def test_una_cuenta_recien_creada_tiene_todo_pendiente_y_no_viaja_nada_mas(base):
    async def cuerpo():
        await cuenta(base)
        e = await primeros_pasos.estado(base, "u_1")
        assert e == {"verificacion": "sin_enviar", "recarga": False, "envio": False,
                     "huella": False, "completo": False}
        assert set(e) == LO_QUE_DEVUELVE
        assert "no-viaja" not in repr(e) and "12345678909" not in repr(e)
    corre(cuerpo())


def test_una_cuenta_que_no_existe_no_rompe(base):
    async def cuerpo():
        e = await primeros_pasos.estado(base, "u_fantasma")
        assert e["verificacion"] == "sin_enviar" and not e["completo"]
    corre(cuerpo())


@pytest.mark.parametrize("en_la_base,en_la_tarjeta", [
    ("unverified", "sin_enviar"),
    ("pending", "en_revision"),
    ("verified", "aprobada"),
    ("rejected", "rechazada"),
    ("algo_raro", "sin_enviar"),
    (None, "sin_enviar"),
])
def test_el_estado_de_verificacion_se_traduce(base, en_la_base, en_la_tarjeta):
    async def cuerpo():
        await cuenta(base, estado=en_la_base)
        e = await primeros_pasos.estado(base, "u_1")
        assert e["verificacion"] == en_la_tarjeta
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 2. Ya recargó: las cinco puertas, sólo terminadas
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("coleccion,doc", [
    ("transactions", {"type": "recharge_ves", "status": "completed", "amount_ris": to_decimal128("50")}),
    ("transactions", {"type": "recharge", "status": "completed", "amount_ris": to_decimal128("50")}),
    ("gestor_pix_payments", {"status": "paid", "amount_ris": to_decimal128("50")}),
    ("gestor_pix_payments", {"status": "approved", "amount_ris": to_decimal128("50")}),
    ("card_payments", {"status": "approved", "amount_ris": to_decimal128("50")}),
    ("crypto_deposits", {"credited": True, "amount": to_decimal128("50")}),
])
def test_ya_recargo_por_cada_puerta(base, coleccion, doc):
    async def cuerpo():
        await cuenta(base)
        await base[coleccion].insert_one({"user_id": "u_1", "created_at": AHORA, **doc})
        assert (await primeros_pasos.estado(base, "u_1"))["recarga"] is True
    corre(cuerpo())


def test_ya_recargo_si_el_saldo_esta_en_positivo(base):
    """Un ajuste a mano del panel no pasa por ninguna puerta: se ve en el
    saldo."""
    async def cuerpo():
        await cuenta(base, saldo="12.50")
        assert (await primeros_pasos.estado(base, "u_1"))["recarga"] is True
    corre(cuerpo())


@pytest.mark.parametrize("coleccion,doc", [
    ("transactions", {"type": "recharge_ves", "status": "pending"}),
    ("transactions", {"type": "withdrawal", "status": "completed"}),     # eso es un envío
    ("gestor_pix_payments", {"status": "expired"}),
    ("gestor_pix_payments", {"status": "pending"}),
    ("card_payments", {"status": "rejected"}),
    ("crypto_deposits", {"credited": False}),
])
def test_lo_que_NO_termino_no_es_una_recarga(base, coleccion, doc):
    async def cuerpo():
        await cuenta(base)
        await base[coleccion].insert_one({"user_id": "u_1", "created_at": AHORA, **doc})
        assert (await primeros_pasos.estado(base, "u_1"))["recarga"] is False
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. Ya envió: lo rechazado y lo cancelado no cuentan
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("coleccion,doc", [
    ("transactions", {"type": "withdrawal", "status": "pending"}),
    ("transactions", {"type": "withdrawal", "status": "completed"}),
    ("btc_remesas", {"estado": "enviado"}),
    ("btc_remesas", {"estado": "pendiente"}),
    ("envios", {"estado": "esperando_postagem", "confirmado_at": AHORA}),
])
def test_ya_envio_por_cada_puerta(base, coleccion, doc):
    async def cuerpo():
        await cuenta(base)
        await base[coleccion].insert_one({"user_id": "u_1", **doc})
        assert (await primeros_pasos.estado(base, "u_1"))["envio"] is True
    corre(cuerpo())


@pytest.mark.parametrize("coleccion,doc", [
    ("transactions", {"type": "withdrawal", "status": "rejected"}),
    ("transactions", {"type": "withdrawal", "status": "cancelled"}),
    ("transactions", {"type": "withdrawal", "status": "expired"}),
    ("transactions", {"type": "recharge_ves", "status": "completed"}),   # eso es una recarga
    ("btc_remesas", {"estado": "cancelado"}),
    ("envios", {"estado": "cotizado"}),                                  # nunca la confirmó
])
def test_lo_que_no_fue_no_es_un_envio(base, coleccion, doc):
    async def cuerpo():
        await cuenta(base)
        await base[coleccion].insert_one({"user_id": "u_1", **doc})
        assert (await primeros_pasos.estado(base, "u_1"))["envio"] is False
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. Sólo lo propio
# ══════════════════════════════════════════════════════════════════════════

def test_lo_de_otra_cuenta_no_cuenta(base):
    async def cuerpo():
        await cuenta(base, "u_1")
        await cuenta(base, "u_2", estado="verified", saldo="100", huella=[{"id": "x"}])
        await base.gestor_pix_payments.insert_one({"user_id": "u_2", "status": "paid"})
        await base.transactions.insert_one({"user_id": "u_2", "type": "withdrawal", "status": "completed"})
        e = await primeros_pasos.estado(base, "u_1")
        assert e == {"verificacion": "sin_enviar", "recarga": False, "envio": False,
                     "huella": False, "completo": False}
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 5. La huella y el «completo»
# ══════════════════════════════════════════════════════════════════════════

def test_la_huella_se_ve_si_hay_una_credencial(base):
    async def cuerpo():
        await cuenta(base, "u_1", huella=[{"id": "abc", "public_key": "..."}])
        await cuenta(base, "u_2", huella=[])
        assert (await primeros_pasos.estado(base, "u_1"))["huella"] is True
        assert (await primeros_pasos.estado(base, "u_2"))["huella"] is False
    corre(cuerpo())


def test_completo_con_los_tres_pasos_y_SIN_huella(base):
    """La huella es opcional y depende del dispositivo: una tarjeta que
    nunca se va porque el teléfono no tiene lector se aprende a ignorar."""
    async def cuerpo():
        await cuenta(base, estado="verified", saldo="10")
        await base.transactions.insert_one({"user_id": "u_1", "type": "withdrawal", "status": "pending"})
        e = await primeros_pasos.estado(base, "u_1")
        assert e["huella"] is False
        assert e["completo"] is True
    corre(cuerpo())


@pytest.mark.parametrize("estado,saldo,con_envio", [
    ("pending", "10", True),        # falta la verificación
    ("verified", "0", True),        # falta la recarga
    ("verified", "10", False),      # falta el envío
])
def test_con_un_paso_menos_no_esta_completo(base, estado, saldo, con_envio):
    async def cuerpo():
        await cuenta(base, estado=estado, saldo=saldo)
        if con_envio:
            await base.transactions.insert_one({"user_id": "u_1", "type": "withdrawal", "status": "completed"})
        assert (await primeros_pasos.estado(base, "u_1"))["completo"] is False
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 6. La ruta
# ══════════════════════════════════════════════════════════════════════════

def test_la_ruta_exige_sesion_y_usa_el_user_id_de_la_sesion():
    from routes import primeros_pasos as ruta
    from routes.dependencies import get_current_user
    rutas = [r for r in ruta.router.routes if getattr(r, "path", "") == "/primeros-pasos"]
    assert len(rutas) == 1
    assert get_current_user in [d.call for d in rutas[0].dependant.dependencies]
    fuente = pathlib.Path(_BACKEND, "routes", "primeros_pasos.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "ver")
    assert "primeros_pasos.estado(db, current_user.user_id)" in ast.unparse(fn), \
        "el estado tiene que calcularse con el user_id de la sesión, no con uno del pedido"
    assert not any(a.arg == "user_id" for a in fn.args.args), "la ruta no recibe un user_id ajeno"


def test_la_ruta_esta_colgada_de_la_api():
    from routes import api_router
    assert any(getattr(r, "path", "") == "/api/primeros-pasos" for r in api_router.routes)


# ══════════════════════════════════════════════════════════════════════════
# 7. La tarjeta
# ══════════════════════════════════════════════════════════════════════════

def test_la_tarjeta_cuelga_del_panel_del_cliente():
    panel = _PANEL.read_text(encoding="utf-8")
    assert "import PrimerosPasos from '../components/dashboard/PrimerosPasos';" in panel
    assert "<PrimerosPasos user={user} isMobile={isMobile} />" in panel


def test_la_tarjeta_se_apoya_en_el_servidor_y_se_va_cuando_esta_completo():
    assert _TARJETA.is_file()
    fuente = _TARJETA.read_text(encoding="utf-8")
    assert "api.get('/primeros-pasos')" in fuente
    assert "if (oculto || !estado || estado.completo) return null;" in fuente
    for ruta in ("'/verification'", "'/recharge'", "'/send'", "'/profile'"):
        assert f"ruta: {ruta}" in fuente, ruta
    assert "webauthnSupported()" in fuente
    assert "const CLAVE_OCULTA = 'primeros_pasos_ocultos';" in fuente


def test_la_huella_no_cuenta_para_el_progreso_de_la_tarjeta():
    fuente = _TARJETA.read_text(encoding="utf-8")
    linea = next(l for l in fuente.splitlines() if "clave: 'huella'" in l)
    assert "cuenta: false" in linea
    assert "const queCuentan = pasos.filter((p) => p.cuenta);" in fuente
