"""
tests/test_duracion_de_la_sesion.py — La sesión de un administrador dura menos.

QUE PROTEGE

    Una sesión de administrador vale muchísimo más que una de un usuario
    común: desde ella se aprueban recargas, se mueven saldos y se otorgan
    permisos. Por eso caduca a los 30 minutos, mientras que la de un usuario
    común dura 7 días.

    El número vive en `routes/security_2fa.py` (`ADMIN_SESSION_MINUTES`,
    `USER_SESSION_DAYS`) y lo aplica `_session_duration_for(role)`, que usa
    `issue_session_token` para todas las sesiones que emite la aplicación.

    Hasta ahora no había ninguna prueba sobre esto. La caducidad diferenciada
    es una afirmación del dossier técnico de seguridad, y una afirmación de
    seguridad sin prueba es una afirmación que alguien puede borrar sin
    enterarse: cambiar `_session_duration_for` para que devuelva siempre
    `timedelta(days=7)` no rompía nada, y le regalaba una semana de sesión a
    cada administrador.

    Lo que se comprueba es el `expires_at` que QUEDA EN LA BASE, no la
    constante. Una prueba que lee la constante y la compara consigo misma no
    comprueba nada.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from routes import security_2fa                                     # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["duracion"]
    usar_base(b)
    return b


def _minutos_de_sesion(base, role):
    """Emite una sesión para ese rol y devuelve cuánto dura, en minutos."""
    usuario = {"user_id": f"u_{role}", "email": f"{role}@correo.com", "role": role}
    antes = datetime.now(timezone.utc)
    token = corre(security_2fa.issue_session_token(usuario))
    sesion = corre(base.user_sessions.find_one({"session_token": token}))
    assert sesion is not None, "no se guardó la sesión"

    vence = sesion["expires_at"]
    if vence.tzinfo is None:                 # Mongo devuelve naive, en UTC
        vence = vence.replace(tzinfo=timezone.utc)
    return (vence - antes).total_seconds() / 60


def test_el_administrador_tiene_media_hora(base):
    for role in ("admin", "super_admin"):
        minutos = _minutos_de_sesion(base, role)
        assert 29 <= minutos <= 31, f"la sesión de {role} duró {minutos:.1f} minutos"


def test_el_usuario_comun_tiene_siete_dias(base):
    minutos = _minutos_de_sesion(base, "user")
    esperados = 7 * 24 * 60
    assert esperados - 2 <= minutos <= esperados + 2, (
        f"la sesión del usuario duró {minutos:.1f} minutos, se esperaban {esperados}")


def test_el_agente_hoy_dura_como_un_cliente_y_eso_esta_a_la_vista(base):
    """UNA DIFERENCIA QUE CONVIENE MIRAR, NO UN ERROR DE ESTA PRUEBA.

    `agent` entra al panel —está en `personal.ROLES_CON_PANEL` y por eso se le
    exige segundo factor— pero NO está en `security_2fa.ADMIN_ROLES`, así que
    su sesión dura siete días, como la de un cliente.

    Esta prueba fija el comportamiento de hoy en vez de disimularlo. Si se
    decide acortarla, la prueba se pone roja y hay que venir acá a cambiar el
    número a propósito: es exactamente lo que se quiere de un cambio así.
    """
    from services.personal import ROLES_CON_PANEL

    assert "agent" in ROLES_CON_PANEL, "el agente entra al panel"
    assert "agent" not in security_2fa.ADMIN_ROLES, "y sin embargo no acorta su sesión"

    minutos = _minutos_de_sesion(base, "agent")
    esperados = 7 * 24 * 60
    assert esperados - 2 <= minutos <= esperados + 2, (
        f"la sesión del agente duró {minutos:.1f} minutos. Si es a propósito, "
        f"actualizá esta prueba y el dossier de seguridad.")


def test_los_roles_que_acortan_la_sesion_estan_declarados():
    """La lista de roles con sesión corta es explícita, no inferida."""
    assert security_2fa.ADMIN_ROLES == {"admin", "super_admin"}
    assert security_2fa.ADMIN_SESSION_MINUTES == 30
    assert security_2fa.USER_SESSION_DAYS == 7


def test_el_ingreso_de_un_administrador_queda_asentado(base):
    """Cada sesión de administrador deja línea en `admin_access_log`: sin eso
    no hay forma de reconstruir quién entró al panel y desde dónde."""
    corre(security_2fa.issue_session_token(
        {"user_id": "u_a", "email": "a@correo.com", "role": "admin"},
        None, True))
    linea = corre(base.admin_access_log.find_one({"user_id": "u_a"}))
    assert linea is not None, "un ingreso de administrador no dejó rastro"
    assert linea["two_factor_used"] is True
    assert linea["session_minutes"] == 30


def test_el_ingreso_de_un_usuario_comun_no_ensucia_el_libro_de_admins(base):
    corre(security_2fa.issue_session_token(
        {"user_id": "u_c", "email": "c@correo.com", "role": "user"}))
    assert corre(base.admin_access_log.find_one({"user_id": "u_c"})) is None
