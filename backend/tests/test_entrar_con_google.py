"""Entrar y registrarse con Google: la misma puerta con otra llave.

QUE PASABA
    Nadie quiere crear una contraseña más. El registro pedía contraseña,
    confirmación y un código de seis dígitos por correo; y la única otra
    forma de entrar —la huella— recién se activa después de tener cuenta.

LO QUE SE PRUEBA
    1. Que sin id de cliente no hay puerta (503) y la configuración viene
       vacía: nada se rompe, sólo falta la función.
    2. Que la credencial se comprueba de verdad: emisor, audiencia, y sobre
       todo `email_verified`, que la librería no mira.
    3. Que una cuenta que existe entra con las MISMAS guardas y respuestas
       que la contraseña (borrada, suspendida, lista negra) y el MISMO
       segundo factor obligatorio para el personal. Google no lo saltea.
    4. Que una cuenta nueva no nace en el primer paso: queda una invitación
       corta, y la cuenta nace en el segundo por `alta_de_cuenta`, sin
       contraseña, con el CPF anclado y el bono liberado.
    5. Que la invitación se consume recién cuando todo lo demás pasó, y una
       sola vez.
    6. Que el correo de la cuenta nueva sale de la invitación (lo que Google
       confirmó) y nunca del pedido.
    7. Que la política de contenido deja pasar a Google, y que las pantallas
       sólo dibujan el botón si hay id de cliente.
"""
import ast
import asyncio
import inspect
import itertools
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_FRONT = pathlib.Path(_BACKEND, "..", "frontend", "src").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import HTTPException                                   # noqa: E402
from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from routes import google_ingreso as rutas                          # noqa: E402
from services import google_ingreso as servicio                     # noqa: E402
from services import csp                                            # noqa: E402
from services.money import to_decimal128                            # noqa: E402
from services.perfil import LO_PERMITIDO                            # noqa: E402

ensenarle_decimal128_a_mongomock()

CLIENTE = "cliente-de-prueba.apps.googleusercontent.com"
CORREO = "ana@ejemplo.com"
CPF_VALIDO = "529.982.247-25"          # con sus dos dígitos verificadores bien
SEMILLA = "JBSWY3DPEHPK3PXP"


def corre(coro):
    return asyncio.run(coro)


_ips = itertools.count(1)


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido():
    """Cada pedido desde una IP distinta: las puertas están frenadas por IP."""
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


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_google"]
    usar_base(b)
    yield b


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENTE)


def afirmaciones(email=CORREO, **cambios):
    base = {"iss": "https://accounts.google.com", "aud": CLIENTE, "email": email,
            "email_verified": True, "sub": "sub-ana-1", "name": "Ana Google"}
    base.update(cambios)
    return base


@pytest.fixture
def google_dice(monkeypatch):
    """Reemplaza SOLO la lectura del token (lo único que habla con Google)."""
    def _poner(**cambios):
        monkeypatch.setattr(servicio, "leer_las_afirmaciones", lambda cred: afirmaciones(**cambios))
    return _poner


LO_QUE_NO_ES_SUYO = {
    "password_hash": "$2b$12$no-sale",
    "two_factor_secret": SEMILLA,
    "pin_hash": "$2b$12$pin",
    "webauthn_credentials": [{"public_key": "AAA"}],
}


async def cuenta(base, **extra):
    doc = {"user_id": "u1", "email": CORREO, "name": "Ana", "role": "user",
           "email_verified": True, "password_set": True, "verification_status": "verified",
           "cpf_number": "12345678901", "referral_code": "ANA123",
           "balance_ris": to_decimal128(10), "balance_ves": to_decimal128(0),
           "balance_ris_bono": to_decimal128(0), **LO_QUE_NO_ES_SUYO, **extra}
    await base.users.insert_one(doc)
    return doc


def entrar(credencial="una-credencial"):
    respuesta = _RespuestaDeMentira()
    r = corre(rutas.entrar(pedido(), respuesta, rutas.EntrarConGoogleRequest(credential=credencial)))
    return r, respuesta


def completar(pending_token, cpf=CPF_VALIDO, acepta=True, referido=None, nombre="Ana Completa"):
    respuesta = _RespuestaDeMentira()
    r = corre(rutas.completar(pedido(), respuesta, rutas.CompletarRegistroGoogleRequest(
        pending_token=pending_token, name=nombre, cpf_number=cpf, referred_by=referido,
        accept_terms=acepta)))
    return r, respuesta


def levanta(fn, status):
    with pytest.raises(HTTPException) as e:
        fn()
    assert e.value.status_code == status, e.value.detail
    return e.value.detail


# ══════════════════════════════════════════════════════════════════════════
# 1. Sin id de cliente no hay puerta, y nada se rompe
# ══════════════════════════════════════════════════════════════════════════

def test_sin_id_de_cliente_la_config_viene_vacia_y_la_puerta_dice_503(base, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert corre(rutas.config()) == {"client_id": ""}
    assert not servicio.configurado()
    levanta(lambda: entrar(), 503)


def test_la_config_trae_el_id_y_nada_mas(base, configurado):
    assert corre(rutas.config()) == {"client_id": CLIENTE}


# ══════════════════════════════════════════════════════════════════════════
# 2. La credencial se comprueba de verdad
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cambio", [
    {"email_verified": False},
    {"email_verified": "true"},          # un texto no es True
    {"iss": "https://cuentas.malas.example"},
    {"aud": "otra-aplicacion"},
    {"email": ""},
    {"email": "sin-arroba"},
    {"sub": ""},
])
def test_una_afirmacion_que_falta_o_miente_no_entra(configurado, google_dice, cambio):
    google_dice(**cambio)
    with pytest.raises(servicio.CredencialInvalida):
        servicio.verificar_credencial("una-credencial")


def test_si_la_libreria_rechaza_el_token_tampoco_entra(configurado, monkeypatch):
    def _revienta(cred):
        raise ValueError("Token expired")
    monkeypatch.setattr(servicio, "leer_las_afirmaciones", _revienta)
    with pytest.raises(servicio.CredencialInvalida):
        servicio.verificar_credencial("una-credencial")


@pytest.mark.parametrize("credencial", ["", None, "x" * (servicio.TOPE_DE_LA_CREDENCIAL + 1), 123])
def test_una_credencial_vacia_o_rara_no_llega_a_google(configurado, monkeypatch, credencial):
    def _no_deberia_llamarse(cred):
        raise AssertionError("no tenía que hablar con Google")
    monkeypatch.setattr(servicio, "leer_las_afirmaciones", _no_deberia_llamarse)
    with pytest.raises(servicio.CredencialInvalida):
        servicio.verificar_credencial(credencial)


def test_una_credencial_buena_deja_el_correo_en_minusculas(configurado, google_dice):
    google_dice(email="  Ana@Ejemplo.COM ", name="  Ana Google  ")
    assert servicio.verificar_credencial("una-credencial") == {
        "email": "ana@ejemplo.com", "sub": "sub-ana-1", "nombre": "Ana Google"}


def test_una_credencial_mala_da_401_y_no_toca_nada(base, configurado, google_dice):
    google_dice(email_verified=False)
    detalle = levanta(lambda: entrar(), 401)
    assert detalle == rutas.NO_SE_PUDO_VERIFICAR
    assert corre(base.users.count_documents({})) == 0
    assert corre(base.twofa_pending.count_documents({})) == 0


# ══════════════════════════════════════════════════════════════════════════
# 3. La cuenta que existe entra como con la contraseña
# ══════════════════════════════════════════════════════════════════════════

def test_una_cuenta_que_existe_entra_con_sesion_y_sin_lo_que_no_es_suyo(base, configurado, google_dice):
    corre(cuenta(base))
    google_dice()
    r, respuesta = entrar()
    assert r["message"] == "Login exitoso" and r["session_token"]
    assert respuesta.cookies.get("session_token") == r["session_token"]
    assert set(r["user"]) <= LO_PERMITIDO
    crudo = repr(r)
    for valor in ("$2b$12$no-sale", SEMILLA, "$2b$12$pin", "AAA"):
        assert valor not in crudo
    assert corre(base.user_sessions.count_documents({"user_id": "u1"})) == 1
    doc = corre(base.users.find_one({"user_id": "u1"}))
    assert doc["google_sub"] == "sub-ana-1"
    assert isinstance(doc.get("last_login"), datetime)


def test_el_identificador_de_google_no_se_pisa(base, configurado, google_dice):
    corre(cuenta(base, google_sub="sub-viejo"))
    google_dice(sub="sub-nuevo")
    entrar()
    assert corre(base.users.find_one({"user_id": "u1"}))["google_sub"] == "sub-viejo"


@pytest.mark.parametrize("estado,status,detalle", [
    ({"is_deleted": True}, 401, rutas.CREDENCIALES_INVALIDAS),
    ({"is_banned": True}, 403, rutas.CUENTA_SUSPENDIDA),
    ({"status": "suspended"}, 403, rutas.CUENTA_SUSPENDIDA),
    ({"_lista_negra": True}, 403, rutas.CUENTA_SUSPENDIDA),
])
def test_las_tres_guardas_de_la_contrasena_tambien_cierran_esta_puerta(base, configurado, google_dice, estado, status, detalle):
    if estado.pop("_lista_negra", False):
        corre(base.blacklist.insert_one({"type": "email", "value": CORREO}))
    corre(cuenta(base, **estado))
    google_dice()
    assert levanta(lambda: entrar(), status) == detalle
    assert corre(base.user_sessions.count_documents({})) == 0


def test_las_frases_son_las_mismas_que_en_la_puerta_de_la_contrasena():
    """Lo borrado contesta como una contraseña equivocada, y lo vetado como
    lo suspendido: si una frase cambia en una puerta y no en la otra, se
    puede distinguir por cuál se entró."""
    fuente = pathlib.Path(_BACKEND, "routes", "auth.py").read_text(encoding="utf-8")
    assert f'detail="{rutas.CREDENCIALES_INVALIDAS}"' in fuente
    assert f'detail="{rutas.CUENTA_SUSPENDIDA}"' in fuente


@pytest.mark.parametrize("quien,con_2fa,espera", [
    ({"role": "admin"}, False, "two_factor_enrollment_required"),
    ({"role": "super_admin"}, False, "two_factor_enrollment_required"),
    ({"role": "agent"}, True, "two_factor_required"),
    ({"role": "admin"}, True, "two_factor_required"),
    ({"role": "user", "es_personal": True}, False, "two_factor_enrollment_required"),
])
def test_el_personal_no_se_saltea_el_segundo_factor_con_google(base, configurado, google_dice, quien, con_2fa, espera):
    """Google confirma quién es; no reemplaza el segundo paso."""
    corre(cuenta(base, two_factor_enabled=con_2fa, **quien))
    google_dice()
    r, respuesta = entrar()
    assert r.get(espera) is True
    assert r["pending_token"] and "session_token" not in r and "user" not in r
    assert respuesta.cookies == {}, "no puede haber cookie de sesión antes del segundo factor"
    assert corre(base.user_sessions.count_documents({})) == 0
    proposito = "2fa_login" if con_2fa else "2fa_enroll"
    assert corre(base.twofa_pending.find_one({"token": r["pending_token"]}))["purpose"] == proposito


# ══════════════════════════════════════════════════════════════════════════
# 4 y 5. La cuenta nueva: invitación primero, cuenta después
# ══════════════════════════════════════════════════════════════════════════

def test_un_correo_sin_cuenta_recibe_una_invitacion_y_todavia_no_hay_cuenta(base, configurado, google_dice):
    google_dice(email="nueva@ejemplo.com")
    r, respuesta = entrar()
    assert r["registro_incompleto"] is True
    assert r["email"] == "nueva@ejemplo.com" and r["nombre"] == "Ana Google"
    assert "session_token" not in r and respuesta.cookies == {}
    assert corre(base.users.count_documents({})) == 0
    inv = corre(base.twofa_pending.find_one({"token": r["pending_token"]}))
    assert inv["purpose"] == rutas.PROPOSITO_DEL_REGISTRO
    assert inv["email"] == "nueva@ejemplo.com" and inv["google_sub"] == "sub-ana-1"
    assert inv["consumed"] is False and inv["user_id"] is None
    vence_en = inv["expires_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(minutes=10) < vence_en <= timedelta(minutes=rutas.MINUTOS_PARA_COMPLETAR)


def test_un_correo_vetado_no_recibe_invitacion(base, configurado, google_dice):
    corre(base.blacklist.insert_one({"type": "email", "value": "vetado@ejemplo.com"}))
    google_dice(email="vetado@ejemplo.com")
    levanta(lambda: entrar(), 400)
    assert corre(base.twofa_pending.count_documents({})) == 0


@pytest.fixture
def invitacion(base, configurado, google_dice):
    google_dice(email="nueva@ejemplo.com")
    r, _ = entrar()
    return r["pending_token"]


def test_completar_crea_la_cuenta_sin_contrasena_con_el_cpf_anclado_y_el_bono(base, invitacion, monkeypatch):
    corre(base.users.insert_one({"user_id": "u_dueno", "email": "dueno@ejemplo.com",
                                 "referral_code": "REFDUENO001", "balance_ris": to_decimal128(0)}))
    from services import bonos
    llamadas = []

    async def _al_registrarse(db, user_id, codigo):
        llamadas.append((user_id, codigo))
        return {"ok": True}
    monkeypatch.setattr(bonos, "al_registrarse", _al_registrarse)

    r, respuesta = completar(invitacion, referido="ref dueno 001")
    assert r["message"] == "Registro completado exitosamente" and r["session_token"]
    assert respuesta.cookies.get("session_token") == r["session_token"]
    assert set(r["user"]) <= LO_PERMITIDO
    assert r["user"]["email"] == "nueva@ejemplo.com" and r["user"]["password_set"] is False

    doc = corre(base.users.find_one({"email": "nueva@ejemplo.com"}))
    assert doc["password_hash"] is None and doc["password_set"] is False
    assert doc["email_verified"] is True
    assert doc["name"] == "Ana Completa"
    assert doc["cpf_number"] == "52998224725"
    assert doc["google_sub"] == "sub-ana-1" and doc["registrada_via"] == "google"
    assert doc["referred_by"] == "REFDUENO001"
    assert doc["terms_accepted"] is True and doc["terms_version"]
    assert doc["role"] == "user" and doc["verification_status"] == "unverified"
    assert llamadas == [(doc["user_id"], "REFDUENO001")], "el bono no se liberó"
    assert corre(base.user_sessions.count_documents({"user_id": doc["user_id"]})) == 1
    # El CPF quedó anclado a ESTA cuenta: la reserva tiene dueño. Mirar la
    # reserva y no `revisar_para_registrar`, que también rechaza por el
    # documento del usuario y no distingue si el ancla se puso.
    from services import cpf_de_la_cuenta
    ancla = corre(base[cpf_de_la_cuenta.COLECCION_TOMADOS].find_one({"user_id": doc["user_id"]}))
    assert ancla is not None, "el CPF no quedó anclado a la cuenta"


def test_la_invitacion_se_consume_una_sola_vez(base, invitacion):
    completar(invitacion)
    assert levanta(lambda: completar(invitacion, cpf="111.444.777-35"), 400) == rutas.INVITACION_VENCIDA
    assert corre(base.users.count_documents({"email": "nueva@ejemplo.com"})) == 1


def test_sin_aceptar_los_terminos_no_nace_nada_y_la_invitacion_sigue_viva(base, invitacion):
    levanta(lambda: completar(invitacion, acepta=False), 400)
    assert corre(base.users.count_documents({})) == 0
    assert corre(base.twofa_pending.find_one({"token": invitacion}))["consumed"] is False


def test_un_cpf_mal_tipeado_se_corrige_sin_volver_a_google(base, invitacion):
    """La invitación se consume RECIEN cuando todo lo demás pasó."""
    levanta(lambda: completar(invitacion, cpf="123.456.789-00"), 400)
    assert corre(base.users.count_documents({})) == 0
    assert corre(base.twofa_pending.find_one({"token": invitacion}))["consumed"] is False
    r, _ = completar(invitacion)
    assert r["session_token"]


def test_un_codigo_de_invitacion_que_no_existe_se_rechaza(base, invitacion):
    detalle = levanta(lambda: completar(invitacion, referido="REFFANTASMA"), 400)
    assert "no existe" in detalle
    assert corre(base.users.count_documents({})) == 0


def test_una_invitacion_vencida_no_sirve(base, invitacion):
    corre(base.twofa_pending.update_one({"token": invitacion}, {"$set": {
        "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}}))
    assert levanta(lambda: completar(invitacion), 400) == rutas.INVITACION_VENCIDA


def test_un_token_del_segundo_factor_no_sirve_para_registrarse(base, configurado):
    """Distinto propósito, distinta puerta: un token de 2FA no crea cuentas."""
    from routes.security_2fa import _create_pending_token
    token = corre(_create_pending_token("u_alguien", purpose="2fa_login"))
    assert levanta(lambda: completar(token), 400) == rutas.INVITACION_VENCIDA
    assert corre(base.users.count_documents({})) == 0


def test_si_el_correo_ya_tiene_cuenta_al_completar_no_se_duplica(base, invitacion):
    corre(cuenta(base, email="nueva@ejemplo.com"))
    detalle = levanta(lambda: completar(invitacion), 400)
    assert "ya tiene una cuenta" in detalle
    assert corre(base.users.count_documents({"email": "nueva@ejemplo.com"})) == 1


def test_el_nombre_sale_de_google_si_la_persona_no_lo_escribe(base, invitacion):
    r, _ = completar(invitacion, nombre="")
    assert r["user"]["name"] == "Ana Google"


def test_sin_nombre_por_ningun_lado_se_pide(base, configurado, google_dice):
    google_dice(email="anonima@ejemplo.com", name="")
    r, _ = entrar()
    assert levanta(lambda: completar(r["pending_token"], nombre="  "), 400) == "Decinos tu nombre."


def test_el_correo_de_la_cuenta_nueva_es_el_que_google_confirmo():
    """El modelo del segundo paso NO tiene campo de correo: no hay forma de
    mandar uno. Si algún día se agrega, esto se pone rojo y hay que explicar
    por qué un correo que no confirmó Google puede nacer como cuenta."""
    assert "email" not in rutas.CompletarRegistroGoogleRequest.model_fields
    fn = next(n for n in ast.walk(ast.parse(inspect.getsource(rutas)))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "completar")
    assert "email = pendiente['email']" in ast.unparse(fn)


def test_la_cuenta_nacida_con_google_no_entra_con_contrasena(base, invitacion):
    from routes import auth as rutas_auth
    completar(invitacion)
    with pytest.raises(HTTPException) as e:
        corre(rutas_auth.login_with_password(
            pedido(), _RespuestaDeMentira(),
            rutas_auth.LoginWithPasswordRequest(email="nueva@ejemplo.com", password="lo-que-sea")))
    assert e.value.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 6. Forma: una sola cuna, topes, política de contenido, pantallas
# ══════════════════════════════════════════════════════════════════════════

def test_las_dos_puertas_nacen_por_alta_de_cuenta_y_ninguna_inserta_por_su_cuenta():
    auth = pathlib.Path(_BACKEND, "routes", "auth.py").read_text(encoding="utf-8")
    google = pathlib.Path(_BACKEND, "routes", "google_ingreso.py").read_text(encoding="utf-8")
    assert "alta_de_cuenta.crear(" in auth and "alta_de_cuenta.crear(" in google
    assert "db.users.insert_one" not in auth, "verify-email volvió a crear la cuenta por su cuenta"
    assert "db.users.insert_one" not in google


def test_las_dos_puertas_tienen_tope_y_contadores_distintos():
    fuente = inspect.getsource(rutas)
    assert 'frenar(request, "auth.google", ' in fuente
    assert 'frenar(request, "auth.google.completar", ' in fuente


def test_la_politica_de_contenido_deja_pasar_a_google():
    assert csp.GOOGLE_INGRESO_SCRIPT in csp.DIRECTIVAS["script-src"].split()
    assert csp.GOOGLE_INGRESO in csp.DIRECTIVAS["frame-src"].split()
    assert csp.GOOGLE_INGRESO in csp.DIRECTIVAS["connect-src"].split()
    assert csp.GOOGLE_INGRESO_ESTILO in csp.DIRECTIVAS["style-src"].split()


def test_lo_de_google_no_sale_por_ninguna_puerta():
    assert "google_sub" not in LO_PERMITIDO
    assert "registrada_via" not in LO_PERMITIDO


def test_las_rutas_estan_colgadas_de_la_api():
    from routes import api_router
    caminos = {getattr(r, "path", "") for r in api_router.routes}
    assert {"/api/auth/google/config", "/api/auth/google", "/api/auth/google/completar"} <= caminos


def test_el_boton_se_dibuja_solo_si_hay_id_de_cliente_y_carga_el_script_permitido():
    util = (_FRONT / "utils" / "google.js").read_text(encoding="utf-8")
    assert f"export const URL_DEL_SCRIPT = '{csp.GOOGLE_INGRESO_SCRIPT}';" in util
    assert "api.get('/auth/google/config')" in util
    boton = (_FRONT / "components" / "auth" / "EntrarConGoogle.jsx").read_text(encoding="utf-8")
    assert "if (!clientId) return null;" in boton
    assert "api.post('/auth/google', { credential })" in boton


def test_el_segundo_paso_manda_la_invitacion_y_los_terminos_y_no_un_correo():
    fuente = (_FRONT / "components" / "auth" / "CompletarRegistroGoogle.jsx").read_text(encoding="utf-8")
    assert "api.post('/auth/google/completar', {" in fuente
    assert "pending_token: pendiente.pending_token," in fuente
    assert "accept_terms: true," in fuente
    assert "readOnly" in fuente, "el correo se muestra pero no se edita"


@pytest.mark.parametrize("pantalla", ["Login.jsx", "Register.jsx"])
def test_las_dos_pantallas_ofrecen_google_y_saben_completar(pantalla):
    fuente = (_FRONT / "pages" / pantalla).read_text(encoding="utf-8")
    assert "<EntrarConGoogle " in fuente
    assert "onDosPasos={pedirDosPasos}" in fuente, "el personal tiene que pasar por el segundo factor"
    assert "onRegistroIncompleto={setGooglePendiente}" in fuente
    assert "<CompletarRegistroGoogle " in fuente
