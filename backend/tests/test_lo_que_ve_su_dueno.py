"""
tests/test_lo_que_ve_su_dueno.py — Lo que `/auth/me` le manda al navegador.

LO QUE HABIA

    La proyección era `{"_id": 0, "password_hash": 0}` —una lista de lo
    PROHIBIDO— y el comentario de al lado lo decía: «el documento ya sale
    entero». Así que cada campo que la aplicación le fue escribiendo al usuario
    viajaba al navegador, y ésta es LA RUTA MAS LLAMADA DE LA APLICACION.

    Comprobado corriendo la ruta, salían la semilla del segundo factor, los
    códigos de respaldo cifrados, un token de reseteo vivo, el código de
    verificación de seis dígitos, la suscripción de avisos con su secreto, el
    correo de una cuenta borrada y el token de notificaciones.

POR QUE LA SEMILLA ES LA PEOR

    No vence. Quien la tenga genera códigos válidos PARA SIEMPRE. Una sesión
    robada se revoca; una semilla filtrada obliga a darse de alta de nuevo. En
    una cuenta de administrador es la diferencia entre «entraron un rato» y
    «tienen la cuenta».

    Y no hace falta un atacante remoto: cualquier XSS, o una extensión del
    navegador —que ya vimos inyectando scripts en esta misma aplicación— pasa
    de robar una sesión a quedarse con el segundo factor.

POR QUE ESTE ARCHIVO PRUEBA LAS DOS MITADES

    Una lista de lo permitido falla de dos formas opuestas: deja pasar algo que
    no debía, o se come algo que la pantalla necesita. La segunda no se nota en
    los tests del servidor —la ruta contesta 200 igual— y aparece como una
    pantalla rota.
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

from conftest import usar_base                              # noqa: E402
from models.user import User                                # noqa: E402
from routes import auth                                     # noqa: E402

# Lo que la aplicación le escribe de verdad a un usuario, y nunca es suyo para
# ver. Cada nombre está porque alguna parte del código lo escribe en `users`.
NUNCA_SALE = [
    "password_hash",
    "two_factor_secret",
    "two_factor_backup_hashes",
    "password_reset_token",
    "password_reset_expires",
    "email_verification_code",
    "email_verification_expires",
    "web_push_subscription",
    "push_token",
    "push_token_web",
    "original_email",
    "google_id",
]

# Lo que el frontend lee de esta respuesta. Salió de recorrer los archivos que
# usan `useAuth()`, que es donde vive: `AuthContext` hace `setUser(data)`.
TIENE_QUE_SALIR = [
    "user_id", "email", "name", "role", "status",
    "verification_status", "email_verified", "password_set",
    "must_change_password",
    "balance_ris", "balance_ves", "balance_ris_terceros",
    "cpf_number", "referral_code", "gestor_code",
    "cep_origen", "created_at", "last_login", "profile_picture",
]


def correr(corrutina):
    return asyncio.run(corrutina)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_su_dueno"]
    usar_base(b)
    return b


def _un_usuario_como_los_de_verdad():
    doc = {c: f"valor-de-{c}" for c in NUNCA_SALE + TIENE_QUE_SALIR}
    doc.update({
        "user_id": "u1", "email": "ana@ejemplo.com", "role": "user",
        "two_factor_backup_hashes": ["$2b$12$uno", "$2b$12$dos"],
        "web_push_subscription": {"endpoint": "https://push/x",
                                  "keys": {"auth": "s3cr3t"}},
        "email_verified": True, "password_set": True,
        "must_change_password": True,
        "balance_ris": 10.0, "balance_ves": 0.0, "balance_ris_terceros": 0.0,
    })
    return doc


def _pedirla(base, extra=None):
    doc = _un_usuario_como_los_de_verdad()
    doc.update(extra or {})
    correr(base.users.insert_one(dict(doc)))
    return correr(auth.get_me(User(user_id="u1", email="ana@ejemplo.com"))), doc


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que no tiene que salir
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("campo", NUNCA_SALE)
def test_NO_SALE(base, campo):
    """Uno por campo a propósito: si alguno vuelve a colarse, el nombre del
    test en rojo dice CUAL, sin tener que leer un diff."""
    salida, _ = _pedirla(base)
    assert campo not in salida


def test_LA_SEMILLA_DEL_SEGUNDO_FACTOR_NO_SALE_NI_ESCONDIDA(base):
    """La peor de todas, buscada por su VALOR y no por su nombre: si algún día
    se la renombra o se la mete adentro de otro campo, esto la sigue viendo."""
    import json

    semilla = "JBSWY3DPEHPK3PXPSECRETO"
    salida, _ = _pedirla(base, {"two_factor_secret": semilla})
    assert semilla not in json.dumps(salida, default=str)


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que sí tiene que salir
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("campo", TIENE_QUE_SALIR)
def test_SIGUE_SALIENDO(base, campo):
    """La otra mitad. Una lista de lo permitido que se come un campo no rompe
    ningún test del servidor —la ruta contesta 200 igual— y aparece como una
    pantalla rota en producción."""
    salida, _ = _pedirla(base)
    assert campo in salida, (
        f"'{campo}' dejó de salir y el frontend lo lee: revisá "
        "LO_QUE_VE_SU_DUENO en routes/auth.py")


def test_LA_LISTA_ES_DE_LO_PERMITIDO_Y_NO_DE_LO_PROHIBIDO():
    """La regla del proyecto, escrita donde se puede romper.

    Una proyección de exclusión se reconoce porque lleva ceros en campos que no
    son `_id`. Volver a esa forma deja pasar cada campo nuevo hasta que alguien
    se acuerde — que es exactamente lo que pasó con la semilla del 2FA.
    """
    prohibidos = {c: v for c, v in auth.LO_QUE_VE_SU_DUENO.items()
                  if v == 0 and c != "_id"}
    assert not prohibidos, (
        f"volvió la lista de lo prohibido: {sorted(prohibidos)}")
    assert auth.LO_QUE_VE_SU_DUENO.get("_id") == 0


def test_NINGUN_CAMPO_PROHIBIDO_ESTA_EN_LA_LISTA():
    """Por si alguien agrega uno a mano sin correr los tests de arriba."""
    colados = [c for c in NUNCA_SALE if auth.LO_QUE_VE_SU_DUENO.get(c) == 1]
    assert not colados, f"están permitidos y no deberían: {colados}"
