"""
tests/test_primer_acceso_del_personal.py — La primera llave del colaborador.

QUE SE ESTABA ROMPIENDO

    Recursos Humanos daba de alta a una persona: le creaba el usuario, le
    ponía el rol `admin` y sus permisos. Y hasta ahí. Esa cuenta nacía sin
    contraseña y sin el correo verificado, así que su dueño no podía entrar
    por NINGUNA puerta:

      - `/auth/login-password` la frena dos veces, primero por
        `email_verified` y después por `password_set`.
      - `/auth/resend-verification-code` lee `pending_verifications`, una
        colección donde el alta de RRHH no escribe nada.
      - `/auth/request-password-reset` le manda una clave temporal que
        tampoco sirve, porque el login sigue frenando en `email_verified`.

    Y el otro agujero, del lado opuesto: el enrolamiento obligatorio de 2FA
    era sólo para `super_admin`. El personal de RRHH se da de alta con rol
    `admin`, o sea que una cuenta con permisos para aprobar KYC, aprobar
    recargas y mover saldos entraba con contraseña sola.

    Los dos se prueban acá, y se prueban por comportamiento: los tests llaman
    a los handlers de verdad —`dar_de_alta`, `activar_personal`,
    `login_with_password`— contra una base en memoria. No miran el texto del
    código, así que no se los engaña reacomodando líneas.
"""
import asyncio
import hashlib
import itertools
import os
import sys
from datetime import datetime, timedelta, timezone

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

from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from models.requests import LoginWithPasswordRequest                # noqa: E402
from models.user import User                                        # noqa: E402
from routes import auth as rutas_auth                               # noqa: E402
from routes import recursos_humanos as rrhh                         # noqa: E402
from services import auditoria, invitaciones                        # noqa: E402
from utils.security import hash_password                            # noqa: E402


CLAVE_BUENA = "Colibri!2026x"
CLAVE_OTRA = "Guacamayo!2026x"


def corre(coro):
    return asyncio.run(coro)


# Cada pedido llega de una IP distinta. El login y la activación están
# limitados por IP, y sin esto el test número once se comería un 429 puesto
# por el test número uno.
_ips = itertools.count(1)


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido(ip=None):
    """Un Request de starlette de verdad: slowapi rechaza cualquier doble."""
    if ip is None:
        n = next(_ips)
        ip = f"10.{n // 65536 % 250}.{n // 256 % 256}.{n % 256}"
    return PedidoReal({
        "type": "http", "method": "POST", "path": "/", "query_string": b"",
        "headers": [(b"x-forwarded-for", ip.encode()), (b"user-agent", b"test")],
        "client": (ip, 0), "app": _AppDeMentira(),
    })


class _RespuestaDeMentira:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, key=None, value=None, **k):
        self.cookies[key] = value

    def delete_cookie(self, *a, **k):
        pass


EL_SUPER = User(user_id="sa_1", email="jefe@risapp.com", name="Jefe",
                role="super_admin")


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["primer_acceso"]
    usar_base(b)
    return b


@pytest.fixture
def correos(monkeypatch):
    """Intercepta el correo de invitación y guarda el token que viajó.

    Es la única forma honesta de probar el flujo: el token en claro no está
    en la base —ahí sólo vive su hash— así que si el test lo sacara de Mongo
    estaría probando algo que el colaborador real no puede hacer.
    """
    enviados = []

    async def _falso(email, nombre, cargo, token):
        enviados.append({"email": email, "nombre": nombre, "cargo": cargo,
                         "token": token})
        return True

    monkeypatch.setattr(rrhh, "send_staff_invitation_email", _falso)
    return enviados


def alta(datos=None, **extra):
    campos = {"email": "ana@risapp.com", "nombre_completo": "Ana Pérez",
              "cargo": "Analista", "area": "Operaciones",
              "permisos": []}
    campos.update(extra)
    return rrhh.AltaDePersonal(**(datos or campos))


# ══════════════════════════════════════════════════════════════════════════
# El token: lo que se guarda y lo que no
# ══════════════════════════════════════════════════════════════════════════

def test_el_token_en_claro_no_queda_en_la_base(base):
    """Un dump de Mongo no puede contener la llave.

    Si el token se guardara tal cual, cualquiera que lea la colección —un
    backup, un empleado con acceso a la base— podría activar la cuenta de
    otro y quedarse con sus permisos.
    """
    token = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    docs = corre(base[invitaciones.COLECCION].find({}).to_list(10))

    assert len(docs) == 1
    entero = repr(docs[0])
    assert token not in entero, "el token en claro quedó guardado"
    assert docs[0]["huella"] == hashlib.sha256(token.encode()).hexdigest()


def test_la_invitacion_se_consume_una_sola_vez(base):
    token = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))

    doc = corre(invitaciones.consumir(base, token))
    assert doc["user_id"] == "emp_1"

    with pytest.raises(invitaciones.InvitacionInvalida):
        corre(invitaciones.consumir(base, token))


def test_emitir_de_nuevo_anula_la_anterior(base):
    """Reenviar por un correo perdido no puede dejar dos llaves vivas."""
    vieja = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    nueva = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))

    with pytest.raises(invitaciones.InvitacionInvalida):
        corre(invitaciones.mirar(base, vieja))
    assert corre(invitaciones.mirar(base, nueva))["user_id"] == "emp_1"


def test_un_token_inventado_no_sirve(base):
    corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    with pytest.raises(invitaciones.InvitacionInvalida):
        corre(invitaciones.mirar(base, "cualquier-cosa-de-largo-suficiente"))


def test_una_invitacion_vencida_no_sirve(base):
    token = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    corre(base[invitaciones.COLECCION].update_one(
        {"user_id": "emp_1"},
        {"$set": {"expira_en": datetime.now(timezone.utc) - timedelta(minutes=1)}}))

    with pytest.raises(invitaciones.InvitacionInvalida):
        corre(invitaciones.mirar(base, token))
    assert corre(invitaciones.estado(base, "emp_1"))["estado"] == invitaciones.VENCIDA


def test_el_vencimiento_tolera_la_fecha_sin_zona_que_devuelve_mongo(base):
    """Mongo devuelve los datetime SIN zona horaria.

    Compararlos contra un `now(timezone.utc)` con zona levanta TypeError. Sin
    esta tolerancia, una invitación perfectamente válida hace explotar la
    pantalla de activación en producción y anda en los tests, porque
    mongomock guarda lo que uno le da.
    """
    token = corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    ingenua = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    corre(base[invitaciones.COLECCION].update_one(
        {"user_id": "emp_1"}, {"$set": {"expira_en": ingenua}}))

    assert corre(invitaciones.mirar(base, token))["user_id"] == "emp_1"
    assert corre(invitaciones.estado(base, "emp_1"))["estado"] == invitaciones.PENDIENTE


def test_el_estado_de_varios_trae_la_mas_nueva_de_cada_uno(base):
    corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    corre(invitaciones.emitir(base, user_id="emp_1", email="a@b.com"))
    t2 = corre(invitaciones.emitir(base, user_id="emp_2", email="c@d.com"))
    corre(invitaciones.consumir(base, t2))

    varios = corre(invitaciones.estado_de_varios(base, ["emp_1", "emp_2", "emp_3"]))

    assert varios["emp_1"]["estado"] == invitaciones.PENDIENTE
    assert varios["emp_2"]["estado"] == invitaciones.USADA
    assert varios["emp_3"]["estado"] == invitaciones.SIN_INVITACION
    # Y coincide con preguntar de a uno, que es la versión obvia.
    for uid in ("emp_1", "emp_2", "emp_3"):
        assert varios[uid] == corre(invitaciones.estado(base, uid))


def test_el_estado_de_varios_sin_nadie_no_consulta(base):
    assert corre(invitaciones.estado_de_varios(base, [])) == {}


def test_el_consumo_reclama_dentro_del_filtro_y_no_en_un_if():
    """Que `usada: False` viaje en el filtro del find_one_and_update.

    Chequearlo antes con un `if` y actualizar después es una carrera: dos
    pedidos con el mismo token pasan los dos por el `if`. mongomock corre en
    un solo hilo y no reproduce la carrera, así que se verifica la forma.
    """
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(invitaciones.consumir))
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "find_one_and_update"]
    assert len(llamadas) == 1, "se esperaba un solo find_one_and_update"

    filtro = ast.dump(llamadas[0].args[0])
    assert "'usada'" in filtro and "'anulada'" in filtro, (
        "el reclamo del token tiene que ir en el filtro, no en un if previo")


# ══════════════════════════════════════════════════════════════════════════
# El alta: la cuenta nueva sale con llave
# ══════════════════════════════════════════════════════════════════════════

def test_el_alta_manda_la_invitacion(base, correos):
    r = corre(rrhh.dar_de_alta(alta(), pedido(), EL_SUPER))

    assert r["acceso"]["emitida"] is True
    assert r["acceso"]["correo_enviado"] is True
    assert len(correos) == 1
    assert correos[0]["email"] == "ana@risapp.com"
    assert correos[0]["cargo"] == "Analista"
    assert corre(invitaciones.estado(base, r["user_id"]))["estado"] == \
        invitaciones.PENDIENTE


def test_sin_activar_no_se_puede_entrar(base, correos):
    """La cuenta recién dada de alta no entra con nada: es el punto de partida."""
    corre(rrhh.dar_de_alta(alta(), pedido(), EL_SUPER))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rutas_auth.login_with_password(
            pedido(), _RespuestaDeMentira(),
            LoginWithPasswordRequest(email="ana@risapp.com", password=CLAVE_BUENA)))
    assert e.value.status_code == 401


def test_el_alta_no_da_por_verificado_lo_que_nadie_verifico(base, correos):
    r = corre(rrhh.dar_de_alta(alta(), pedido(), EL_SUPER))
    doc = corre(base.users.find_one({"user_id": r["user_id"]}))

    assert doc.get("verification_status") == "unverified"
    assert not doc.get("email_verified")
    assert not doc.get("password_set")
    assert "password_hash" not in doc


def test_convertir_a_alguien_que_ya_entraba_no_le_manda_una_llave(base, correos):
    """Un usuario con clave y correo verificado no necesita invitación.

    Mandársela igual sería poner una segunda llave de su cuenta a viajar por
    correo sin motivo.
    """
    corre(base.users.insert_one({
        "user_id": "u_1", "email": "ana@risapp.com", "name": "Ana",
        "role": "user", "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE_OTRA), "is_active": True,
    }))

    r = corre(rrhh.dar_de_alta(alta(), pedido(), EL_SUPER))

    assert r["convertido_desde_usuario"] is True
    assert r["acceso"]["emitida"] is False
    assert correos == []


# ══════════════════════════════════════════════════════════════════════════
# La activación
# ══════════════════════════════════════════════════════════════════════════

def _dar_de_alta_y_tomar_token(base, correos, **extra):
    r = corre(rrhh.dar_de_alta(alta(**extra) if extra else alta(),
                               pedido(), EL_SUPER))
    return r["user_id"], correos[-1]["token"]


def test_activar_configura_la_clave_y_verifica_el_correo(base, correos):
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)

    r = corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    doc = corre(base.users.find_one({"user_id": user_id}))
    assert doc["password_set"] is True
    assert doc["email_verified"] is True
    assert doc["password_hash"] != CLAVE_BUENA, "la clave se guardó en claro"
    assert r["two_factor_enrollment_required"] is True


def test_activar_no_entrega_sesion_todavia(base, correos):
    """El personal no queda operando con contraseña sola ni por un rato.

    La activación devuelve un token de enrolamiento, no una sesión: la
    sesión la emite `enroll-confirm`, después del primer código.
    """
    _, token = _dar_de_alta_y_tomar_token(base, correos)

    r = corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    assert "session_token" not in r
    assert r["pending_token"]


def test_despues_de_activar_la_clave_sirve_para_entrar(base, correos):
    _, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="ana@risapp.com", password=CLAVE_BUENA)))

    assert r["two_factor_enrollment_required"] is True


def test_la_invitacion_no_sirve_dos_veces(base, correos):
    _, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rutas_auth.activar_personal(
            pedido(), rutas_auth.ActivarPersonalRequest(
                token=token, password=CLAVE_OTRA, confirm_password=CLAVE_OTRA)))
    assert e.value.status_code == 400


def test_una_clave_mal_tipeada_no_quema_la_invitacion(base, correos):
    """Si un error de tipeo gastara el token habría que pedir otro por correo."""
    _, token = _dar_de_alta_y_tomar_token(base, correos)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        corre(rutas_auth.activar_personal(
            pedido(), rutas_auth.ActivarPersonalRequest(
                token=token, password=CLAVE_BUENA, confirm_password=CLAVE_OTRA)))
    with pytest.raises(HTTPException):
        corre(rutas_auth.activar_personal(
            pedido(), rutas_auth.ActivarPersonalRequest(
                token=token, password="123", confirm_password="123")))

    r = corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))
    assert r["two_factor_enrollment_required"] is True


def test_alguien_dado_de_baja_no_puede_activar(base, correos):
    """Entre el correo y el click pueden haberla dado de baja."""
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rrhh.dar_de_baja(user_id, rrhh.Baja(motivo="renunció"),
                           pedido(), EL_SUPER))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rutas_auth.activar_personal(
            pedido(), rutas_auth.ActivarPersonalRequest(
                token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))
    assert e.value.status_code in (400, 403)


def test_verificar_no_gasta_la_invitacion(base, correos):
    """La pantalla saluda por nombre antes de pedir la clave, sin consumirla."""
    _, token = _dar_de_alta_y_tomar_token(base, correos)

    r = corre(rutas_auth.verificar_invitacion(
        pedido(), rutas_auth.VerificarInvitacionRequest(token=token)))

    assert r["valido"] is True
    assert r["email"] == "ana@risapp.com"
    assert r["cargo"] == "Analista"
    # Y sigue sirviendo.
    assert corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA,
            confirm_password=CLAVE_BUENA)))["two_factor_enrollment_required"]


# ══════════════════════════════════════════════════════════════════════════
# El reenvío
# ══════════════════════════════════════════════════════════════════════════

def test_reenviar_anula_el_link_viejo(base, correos):
    user_id, viejo = _dar_de_alta_y_tomar_token(base, correos)

    corre(rrhh.reenviar_invitacion(user_id, pedido(), EL_SUPER))
    nuevo = correos[-1]["token"]

    assert nuevo != viejo
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        corre(rutas_auth.activar_personal(
            pedido(), rutas_auth.ActivarPersonalRequest(
                token=viejo, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))
    assert corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=nuevo, password=CLAVE_BUENA,
            confirm_password=CLAVE_BUENA)))["two_factor_enrollment_required"]


def test_no_se_reenvia_a_quien_ya_tiene_su_acceso(base, correos):
    """Si ya configuró su clave, el camino es 'olvidé mi contraseña'.

    Reenviar ahí sería fabricar una llave nueva de una cuenta con permisos
    desde el panel, sin que su dueño se entere.
    """
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rrhh.reenviar_invitacion(user_id, pedido(), EL_SUPER))
    assert e.value.status_code == 409


def test_no_se_reenvia_a_quien_esta_de_baja(base, correos):
    user_id, _ = _dar_de_alta_y_tomar_token(base, correos)
    corre(rrhh.dar_de_baja(user_id, rrhh.Baja(motivo="renunció"),
                           pedido(), EL_SUPER))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rrhh.reenviar_invitacion(user_id, pedido(), EL_SUPER))
    assert e.value.status_code == 409


# ══════════════════════════════════════════════════════════════════════════
# 2FA obligatorio para todo el personal, no sólo para el super
# ══════════════════════════════════════════════════════════════════════════

def _usuario(base, **campos):
    doc = {"user_id": "x", "email": "x@x.com", "name": "X", "role": "user",
           "email_verified": True, "password_set": True,
           "password_hash": hash_password(CLAVE_BUENA), "is_active": True}
    doc.update(campos)
    corre(base.users.insert_one(doc))
    return doc


def test_un_admin_sin_2fa_no_recibe_sesion(base):
    """El agujero grande: `admin` es el rol del personal de RRHH.

    Antes el enrolamiento obligatorio miraba sólo `super_admin`, así que una
    cuenta con permisos para aprobar KYC y mover saldos entraba con
    contraseña sola.
    """
    _usuario(base, user_id="emp_9", email="ana@risapp.com", role="admin")

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="ana@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_enrollment_required") is True
    assert "session_token" not in r


def test_un_admin_con_2fa_recibe_el_desafio_y_no_el_enrolamiento(base):
    _usuario(base, user_id="emp_9", email="ana@risapp.com", role="admin",
             two_factor_enabled=True)

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="ana@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_required") is True
    assert not r.get("two_factor_enrollment_required")
    assert "session_token" not in r


def test_el_super_admin_sigue_obligado(base):
    _usuario(base, user_id="sa_9", email="jefe@risapp.com", role="super_admin")

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="jefe@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_enrollment_required") is True


def test_el_super_admin_que_YA_tiene_su_autenticador_entra_como_siempre(base):
    """La cuenta del dueño de la aplicación, que ya tiene 2FA puesto.

    Este es el test que existe para que endurecer el acceso del personal no
    le toque el ingreso a quien ya lo tenía andando: sigue yendo al desafío
    del código de siempre, NO a un enrolamiento nuevo, y NO se le pide volver
    a configurar el autenticador.
    """
    _usuario(base, user_id="sa_9", email="jefe@risapp.com", role="super_admin",
             two_factor_enabled=True, two_factor_secret="EL-SECRETO-DE-SIEMPRE")

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="jefe@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_required") is True
    assert not r.get("two_factor_enrollment_required"), \
        "se le está pidiendo enrolar un autenticador que ya tiene"
    # Y su secreto sigue siendo el mismo: nada lo tocó.
    doc = corre(base.users.find_one({"user_id": "sa_9"}))
    assert doc["two_factor_secret"] == "EL-SECRETO-DE-SIEMPRE"
    assert doc["two_factor_enabled"] is True


def test_un_agent_sin_2fa_tampoco_recibe_sesion(base):
    """`agent` es colaborador: llega a 59 rutas con datos de clientes.

    No mueve plata, pero lee los datos personales de todos los clientes. Eso
    no puede quedar detrás de una sola contraseña.
    """
    _usuario(base, user_id="col_1", email="mesa@risapp.com", role="agent")

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="mesa@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_enrollment_required") is True
    assert "session_token" not in r


def test_un_agent_con_2fa_recibe_el_desafio(base):
    _usuario(base, user_id="col_1", email="mesa@risapp.com", role="agent",
             two_factor_enabled=True)

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="mesa@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_required") is True
    assert "session_token" not in r


def test_a_quien_RRHH_marco_como_personal_no_lo_salva_bajarle_el_rol(base):
    """La obligación no se esquiva degradando el rol.

    Si alguien le pone `role: user` a una cuenta de personal —a mano en la
    base, o por un camino que todavía no revisamos— la marca de RRHH sigue
    exigiendo los dos pasos.
    """
    _usuario(base, user_id="emp_x", email="ana@risapp.com", role="user",
             es_personal=True)

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="ana@risapp.com", password=CLAVE_BUENA)))

    assert r.get("two_factor_enrollment_required") is True


def test_al_usuario_comun_no_se_le_pide_2fa(base):
    """El endurecimiento no puede alcanzar a los clientes de la app."""
    _usuario(base, user_id="u_9", email="cliente@correo.com", role="user")

    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="cliente@correo.com", password=CLAVE_BUENA)))

    assert r.get("session_token")
    assert not r.get("two_factor_enrollment_required")
    assert not r.get("two_factor_required")


# ══════════════════════════════════════════════════════════════════════════
# El rastro
# ══════════════════════════════════════════════════════════════════════════

def test_el_libro_asienta_la_invitacion_y_la_activacion(base, correos):
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    libro = corre(auditoria.buscar(base, objetivo_id=user_id, limite=50))
    acciones = [l["accion"] for l in libro["lineas"]]

    assert "personal.alta" in acciones
    assert "personal.invitacion" in acciones
    assert "personal.activacion" in acciones


def test_el_token_no_aparece_en_ninguna_linea_del_libro(base, correos):
    """El libro lo lee más gente que la casilla de correo del colaborador."""
    _, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    lineas = corre(base[auditoria.COLECCION].find({}).to_list(100))
    assert token not in repr(lineas)
    assert CLAVE_BUENA not in repr(lineas), "la clave nueva quedó en el libro"


def test_la_activacion_queda_a_nombre_del_colaborador_no_del_super(base, correos):
    """Quien activó fue la persona, no quien la dio de alta."""
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    linea = corre(base[auditoria.COLECCION].find_one({"accion": "personal.activacion"}))
    assert linea["actor"]["user_id"] == user_id
    assert linea["actor"]["email"] == "ana@risapp.com"


# ══════════════════════════════════════════════════════════════════════════
# La pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_la_ficha_muestra_como_esta_el_acceso(base, correos):
    """De un vistazo: quién con permisos todavía no aseguró su cuenta."""
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)

    lista = corre(rrhh.listar_personal(False, EL_SUPER))
    acceso = lista["personal"][0]["acceso"]
    assert acceso["clave_configurada"] is False
    assert acceso["dos_pasos"] is False
    assert acceso["invitacion"]["estado"] == invitaciones.PENDIENTE

    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    ficha = corre(rrhh.ver_legajo(user_id, EL_SUPER))["ficha"]
    assert ficha["acceso"]["clave_configurada"] is True
    assert ficha["acceso"]["correo_verificado"] is True
    assert ficha["acceso"]["invitacion"]["estado"] == invitaciones.USADA


def test_la_lista_no_filtra_el_hash_de_la_contrasena(base, correos):
    """Se sacó la proyección `{_id: 0}` para poder leer password_set.

    Traer el documento entero y devolverlo tal cual habría publicado el hash
    de la contraseña y el secreto de 2FA en la pantalla de RRHH.
    """
    user_id, token = _dar_de_alta_y_tomar_token(base, correos)
    corre(rutas_auth.activar_personal(
        pedido(), rutas_auth.ActivarPersonalRequest(
            token=token, password=CLAVE_BUENA, confirm_password=CLAVE_BUENA)))

    def claves(x):
        """Todas las claves del árbol. Buscar el texto '_id' no sirve: lo
        contiene 'user_id', que sí tiene que estar."""
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from claves(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                yield from claves(v)

    salida = [corre(rrhh.listar_personal(False, EL_SUPER)),
              corre(rrhh.ver_legajo(user_id, EL_SUPER))]
    presentes = set(claves(salida))

    for prohibido in ("_id", "password_hash", "password_reset_token",
                      "two_factor_secret", "two_factor_secret_pending",
                      "two_factor_backup_hashes"):
        assert prohibido not in presentes, f"la pantalla de RRHH publica {prohibido}"
    # Y que el hash tampoco viaje como valor bajo otro nombre.
    assert corre(base.users.find_one({"user_id": user_id}))["password_hash"] \
        not in repr(salida)


# ══════════════════════════════════════════════════════════════════════════
# El alta no puede sacarte a vos
# ══════════════════════════════════════════════════════════════════════════

def test_no_se_da_de_alta_al_super_administrador(base, correos):
    """El alta CONVIERTE la cuenta: le pone `role: "admin"`.

    Hecho sobre el super administrador, lo degrada. Y si es el único —que es
    el caso de esta aplicación— no queda nadie que pueda devolverle el rol,
    porque la pantalla que lo haría es la que acaba de perder. Se arregla
    editando Mongo a mano.

    `dar_de_baja` ya frenaba esto. El alta no, y es el mismo daño por el otro
    lado: el aviso de saldo lo tapaba de casualidad, porque con la cuenta en
    cero seguía derecho.
    """
    # Un super administrador DISTINTO del que hace el alta. Con el mismo, el
    # freno de "no a vos mismo" lo atajaría igual y este quedaría sin probar:
    # así fue como sobrevivió a la primera ronda de mutación.
    corre(base.users.insert_one({
        "user_id": "sa_2", "email": "socia@risapp.com", "name": "Socia",
        "role": "super_admin", "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE_OTRA), "is_active": True,
        # En cero a propósito: sin plata que encerrar, el único freno posible
        # es este.
        "balance_ris": 0, "balance_ris_terceros": 0,
    }))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rrhh.dar_de_alta(alta(email="socia@risapp.com"), pedido(), EL_SUPER))

    assert e.value.status_code == 409
    doc = corre(base.users.find_one({"user_id": "sa_2"}))
    assert doc["role"] == "super_admin", "se degradó al super administrador"
    assert not doc.get("es_personal")
    assert correos == [], "se mandó una invitación a un alta que se rechazó"


def test_nadie_se_da_de_alta_a_si_mismo(base, correos):
    """Convertir la cuenta propia es sacarse el acceso uno mismo."""
    corre(base.users.insert_one({
        "user_id": EL_SUPER.user_id, "email": EL_SUPER.email, "name": "Jefe",
        "role": "admin", "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE_OTRA), "is_active": True,
        "balance_ris": 0, "balance_ris_terceros": 0,
    }))

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rrhh.dar_de_alta(alta(email=EL_SUPER.email), pedido(), EL_SUPER))

    assert e.value.status_code == 409
    doc = corre(base.users.find_one({"user_id": EL_SUPER.user_id}))
    assert not doc.get("es_personal")


def test_a_otra_persona_sin_saldo_si_se_le_da_de_alta(base, correos):
    """La contracara: los frenos nuevos no pueden trabar el caso normal."""
    corre(base.users.insert_one({
        "user_id": "u_9", "email": "ana@risapp.com", "name": "Ana",
        "role": "user", "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE_OTRA), "is_active": True,
        "balance_ris": 0, "balance_ris_terceros": 0,
    }))

    r = corre(rrhh.dar_de_alta(alta(), pedido(), EL_SUPER))

    assert r["convertido_desde_usuario"] is True
    doc = corre(base.users.find_one({"user_id": "u_9"}))
    assert doc["es_personal"] is True
    assert doc["role"] == "admin"
