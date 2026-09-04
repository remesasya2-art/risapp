"""
tests/test_huella_del_personal.py — La huella tiene que verificar a su dueño.

EL AGUJERO QUE CIERRA

    `/webauthn/login/verify` emite una sesión marcada `two_factor_used=True`
    SIN pedir contraseña ni código. Y lo hacía con:

        require_user_verification=False

    o sea que el autenticador podía responder sin pedir nada. Para una cuenta
    de personal —que desde el cambio anterior tiene 2FA obligatorio— eso
    convertía la obligación en decorativa: alcanzaba con tener el dispositivo
    en la mano y el 2FA quedaba esquivado por esta puerta.

    Además esta ruta no miraba la suspensión. `/auth/login-password` frena a
    quien tiene `status: "suspended"`, y `get_current_user` mira `is_banned`
    pero NO `status`. Resultado: una cuenta suspendida seguía entrando con la
    huella, y su sesión funcionaba.

LO QUE EL ESTANDAR NO PERMITE, Y POR ESO NO SE PRUEBA

    WebAuthn informa SI el autenticador verificó al usuario, no CON QUE. Una
    huella y un PIN llegan igual (`user_verified = True`). No hay test posible
    de "fue biometría", porque el dato no existe en el protocolo. Lo que sí se
    prueba es que se exige verificación, y que al registrar se pide un
    autenticador de plataforma, que es donde la biometría es el camino normal.

COMO SE PRUEBA

    La verificación criptográfica de WebAuthn se sustituye por un doble que
    anota con qué argumentos la llamaron. Lo que importa acá no es que la
    firma valide —eso lo hace la librería— sino QUE POLITICA se le pidió que
    aplicara, y en qué orden se miran las puertas.
"""
import asyncio
import os
import sys

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

from fastapi import HTTPException                                   # noqa: E402
from webauthn.helpers.structs import UserVerificationRequirement    # noqa: E402

from routes import webauthn_login as wa                             # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Verificado:
    """Lo que devuelve la librería cuando la firma valida."""
    def __init__(self, user_verified=True):
        self.new_sign_count = 7
        self.user_verified = user_verified


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["huella"]
    usar_base(b)
    return b


@pytest.fixture
def libreria(monkeypatch):
    """Doble de la verificación criptográfica: anota cómo la llamaron."""
    llamadas = []

    def _verificar(**kw):
        llamadas.append(kw)
        if kw.get("require_user_verification") and not _verificar.verifica:
            raise ValueError("User verification required but not received")
        return _Verificado(user_verified=_verificar.verifica)

    _verificar.verifica = True
    monkeypatch.setattr(wa, "verify_authentication_response", _verificar)
    monkeypatch.setattr(wa, "base64url_to_bytes", lambda x: b"x")
    return llamadas, _verificar


def _cuenta(base, *, rol="user", es_personal=False, uv_registrada=True, **extra):
    doc = {
        "user_id": "u_1", "email": "quien@risapp.com", "name": "Quien",
        "role": rol, "es_personal": es_personal, "is_active": True,
        "webauthn_auth_challenge": "reto",
        "webauthn_auth_challenge_at": wa._now(),
        "webauthn_credentials": [{
            "credential_id": "cred-1", "public_key": "pk", "sign_count": 3,
            "label": "Mi teléfono", "user_verified": uv_registrada,
        }],
    }
    doc.update(extra)
    corre(base.users.insert_one(doc))
    return doc


def _entrar(base):
    class Req:
        class client:
            host = "1.2.3.4"
        headers = {}
    return corre(wa.login_verify(
        wa.LoginVerifyBody(email="quien@risapp.com",
                           credential={"id": "cred-1"}),
        Req()))


# ══════════════════════════════════════════════════════════════════════════
# La política que se le pide a la librería
# ══════════════════════════════════════════════════════════════════════════

def test_al_personal_se_le_exige_verificacion(base, libreria):
    """El caso que motiva todo: sin esto, el 2FA obligatorio se esquiva acá."""
    llamadas, _ = libreria
    _cuenta(base, rol="admin")

    _entrar(base)

    assert llamadas[0]["require_user_verification"] is True


def test_al_agent_tambien(base, libreria):
    llamadas, _ = libreria
    _cuenta(base, rol="agent")

    _entrar(base)

    assert llamadas[0]["require_user_verification"] is True


def test_a_quien_RRHH_marco_como_personal_tambien(base, libreria):
    """No se esquiva bajándole el rol."""
    llamadas, _ = libreria
    _cuenta(base, rol="user", es_personal=True)

    _entrar(base)

    assert llamadas[0]["require_user_verification"] is True


def test_una_credencial_nacida_verificando_sigue_verificando(base, libreria):
    """Aflojarlo después sería una degradación silenciosa."""
    llamadas, _ = libreria
    _cuenta(base, rol="user", uv_registrada=True)

    _entrar(base)

    assert llamadas[0]["require_user_verification"] is True


def test_al_usuario_comun_con_una_huella_vieja_no_se_le_rompe_el_acceso(base, libreria):
    """El endurecimiento no puede dejar afuera a quien no pidió nada.

    Una credencial registrada antes de este cambio no tiene `user_verified`.
    Para un usuario común eso NO se convierte en un rechazo: entra como
    siempre, y la próxima que registre ya nace verificando.
    """
    llamadas, _ = libreria
    _cuenta(base, rol="user", uv_registrada=False)

    r = _entrar(base)

    assert llamadas[0]["require_user_verification"] is False
    assert r.get("session_token")


def test_el_personal_con_una_huella_vieja_recibe_una_salida(base, libreria):
    """Para el personal la vieja SÍ se rechaza, pero diciendo qué hacer."""
    _, doble = libreria
    doble.verifica = False
    _cuenta(base, rol="admin", uv_registrada=False)

    with pytest.raises(HTTPException) as e:
        _entrar(base)

    assert e.value.status_code == 401
    assert "contraseña" in e.value.detail, "el mensaje no dice cómo salir"


def test_el_reto_ya_pide_la_verificacion_y_no_recien_la_respuesta(base, libreria):
    """Pedirla sólo al verificar deja a la persona entrar y ser rechazada
    después, que se lee como 'no funciona' en vez de 'poné tu huella'."""
    _cuenta(base, rol="admin")

    opciones = corre(wa.login_options(wa.LoginOptionsBody(email="quien@risapp.com")))

    assert opciones["userVerification"] == UserVerificationRequirement.REQUIRED.value


def test_al_usuario_comun_con_huella_vieja_el_reto_no_se_la_exige(base, libreria):
    _cuenta(base, rol="user", uv_registrada=False)

    opciones = corre(wa.login_options(wa.LoginOptionsBody(email="quien@risapp.com")))

    assert opciones["userVerification"] == UserVerificationRequirement.PREFERRED.value


# ══════════════════════════════════════════════════════════════════════════
# Las puertas que esta ruta no tenía
# ══════════════════════════════════════════════════════════════════════════

def test_una_cuenta_suspendida_no_entra_con_la_huella(base, libreria):
    """`/auth/login-password` la frena; acá pasaba de largo."""
    _cuenta(base, rol="user", status="suspended")

    with pytest.raises(HTTPException) as e:
        _entrar(base)
    assert e.value.status_code == 403


def test_una_cuenta_bloqueada_no_entra_con_la_huella(base, libreria):
    _cuenta(base, rol="user", is_banned=True)

    with pytest.raises(HTTPException) as e:
        _entrar(base)
    assert e.value.status_code == 403


def test_una_cuenta_borrada_no_entra_con_la_huella(base, libreria):
    _cuenta(base, rol="user", is_deleted=True)

    with pytest.raises(HTTPException) as e:
        _entrar(base)
    assert e.value.status_code == 401


def test_la_suspension_se_mira_ANTES_de_verificar_la_firma(base, libreria):
    """Que no se gaste el reto de una cuenta suspendida."""
    llamadas, _ = libreria
    _cuenta(base, rol="user", status="suspended")

    with pytest.raises(HTTPException):
        _entrar(base)

    assert llamadas == [], "se verificó la firma de una cuenta suspendida"


# ══════════════════════════════════════════════════════════════════════════
# Lo que queda anotado
# ══════════════════════════════════════════════════════════════════════════

def test_la_sesion_dice_la_verdad_sobre_los_dos_factores(base, libreria):
    """Antes era True fija: el registro de accesos decía que hubo dos
    factores donde hubo uno solo."""
    _, doble = libreria
    doble.verifica = False
    _cuenta(base, rol="user", uv_registrada=False)

    r = _entrar(base)
    sesion = corre(base.user_sessions.find_one({"session_token": r["session_token"]}))

    assert sesion["two_factor_used"] is False


def test_con_verificacion_la_sesion_cuenta_como_dos_factores(base, libreria):
    _cuenta(base, rol="admin")

    r = _entrar(base)
    sesion = corre(base.user_sessions.find_one({"session_token": r["session_token"]}))

    assert sesion["two_factor_used"] is True


def test_queda_anotado_que_la_credencial_verifico(base, libreria):
    _cuenta(base, rol="user", uv_registrada=False)
    _, doble = libreria
    doble.verifica = True

    _entrar(base)

    doc = corre(base.users.find_one({"user_id": "u_1"}))
    assert doc["webauthn_credentials"][0]["user_verified"] is True
    assert doc["webauthn_credentials"][0]["sign_count"] == 7


# ══════════════════════════════════════════════════════════════════════════
# El registro
# ══════════════════════════════════════════════════════════════════════════

def test_al_registrar_se_pide_plataforma_y_verificacion(base):
    """Lo más cerca que deja el estándar de pedir biometría.

    `platform` es el autenticador integrado al equipo —Touch ID, Face ID,
    Windows Hello, el lector del teléfono—, donde el dedo es el camino normal
    y el PIN el respaldo. Una llave USB no entra.

    Se mira lo que sale por la ruta, no el texto del código: buscar la palabra
    "PLATFORM" en la fuente también la encuentra dentro de "CROSS_PLATFORM",
    que es exactamente lo contrario de lo que se quiere.
    """
    from models.user import User as UserModel

    corre(base.users.insert_one({
        "user_id": "u_1", "email": "quien@risapp.com", "name": "Quien",
        "role": "admin",
    }))

    opciones = corre(wa.register_options(
        UserModel(user_id="u_1", email="quien@risapp.com", name="Quien")))
    seleccion = opciones["authenticatorSelection"]

    assert seleccion["authenticatorAttachment"] == "platform", (
        "se está aceptando una llave USB: en esas no hay biometría")
    assert seleccion["userVerification"] == "required", (
        "la verificación de usuario quedó en 'preferred': con eso el navegador "
        "la pide 'si puede', y nace una credencial que después no sirve")


def test_al_registrar_no_se_acepta_una_credencial_que_no_verifico(base, monkeypatch):
    """Las opciones son un PEDIDO al navegador; esto es la comprobación.

    Pedir `userVerification: required` en las opciones no garantiza nada por
    sí solo: un cliente hostil —o uno con un bug— puede devolver una
    credencial que no verificó a nadie. Si el servidor no lo comprueba al
    validar, esa credencial queda guardada y sirve para entrar.
    """
    llamadas = []

    class _RegVerificado:
        credential_id = b"cred"
        credential_public_key = b"pk"
        sign_count = 0
        user_verified = False

    def _verificar(**kw):
        llamadas.append(kw)
        if kw.get("require_user_verification") and not _RegVerificado.user_verified:
            raise ValueError("User verification required but not received")
        return _RegVerificado()

    monkeypatch.setattr(wa, "verify_registration_response", _verificar)
    monkeypatch.setattr(wa, "base64url_to_bytes", lambda x: b"x")
    monkeypatch.setattr(wa, "bytes_to_base64url", lambda x: "cred-1")

    from models.user import User as UserModel
    corre(base.users.insert_one({
        "user_id": "u_1", "email": "quien@risapp.com", "name": "Quien",
        "role": "admin", "webauthn_reg_challenge": "reto",
        "webauthn_reg_challenge_at": wa._now(),
    }))

    with pytest.raises(HTTPException) as e:
        corre(wa.register_verify(
            wa.RegisterVerifyBody(credential={"id": "cred-1"}, label="Tel"),
            UserModel(user_id="u_1", email="quien@risapp.com", name="Quien")))

    assert llamadas[0]["require_user_verification"] is True
    assert e.value.status_code == 400
    doc = corre(base.users.find_one({"user_id": "u_1"}))
    assert not doc.get("webauthn_credentials"), \
        "quedó guardada una credencial que no verifica a su dueño"
