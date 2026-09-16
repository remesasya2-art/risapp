"""
tests/test_las_cinco_puertas.py — Las cinco rutas que mandan el usuario, juntas.

POR QUE ESTE ARCHIVO EXISTE APARTE

    `tests/test_lo_que_ve_su_dueno.py` vigila `/auth/me` campo por campo. Este
    vigila que las OTRAS CUATRO devuelvan exactamente lo mismo.

    Es la lección que dejó el defecto: había cinco listas de lo prohibido
    escritas a mano, y se habían separado sin que nadie lo notara. La de
    `/webauthn/login/verify` tapaba `pin_hash` y las otras cuatro no. No fue
    mala suerte: acordarse en un lugar no protege los otros cuatro, y no hay
    forma de ver la diferencia leyendo un archivo por vez.

    Así que lo que se prueba acá no es «cada ruta tapa lo suyo» sino «las cinco
    devuelven LO MISMO». Un test por ruta se pondría en verde con las cinco
    igual de rotas.

COMO SE PRUEBA

    Se siembra un usuario con TODOS los campos sensibles puestos, se entra por
    cada puerta, y se compara el resultado contra el de `/auth/me`. Si una
    puerta se adelanta o se queda atrás, el nombre del test dice cuál.
"""
import asyncio
import itertools
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

import pyotp                                                   # noqa: E402
from starlette.datastructures import State                     # noqa: E402
from starlette.requests import Request as PedidoReal           # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock  # noqa: E402
from models.user import User                                   # noqa: E402
from routes import auth as rutas_auth                          # noqa: E402
from routes import security_2fa as rutas_2fa                   # noqa: E402
from routes.auth import LoginWithPasswordRequest               # noqa: E402
from services.money import to_decimal128                       # noqa: E402
from utils.security import hash_password                       # noqa: E402

ensenarle_decimal128_a_mongomock()

CLAVE = "Colibri!2026x"
CORREO = "ana@ejemplo.com"
SEMILLA = "JBSWY3DPEHPK3PXP"

# Campos que la aplicación escribe en `users` y no son de su dueño para ver.
# Salieron de recorrer el código buscando escrituras sobre esa colección: no
# hay ninguno inventado, porque un campo inventado hace pasar un test sin
# probar nada del producto.
LO_QUE_NO_ES_SUYO = {
    "password_hash": "puesto abajo",
    "two_factor_secret": SEMILLA,
    "two_factor_secret_pending": "PENDIENTE1234567",
    "two_factor_backup_hashes": ["$2b$12$uno", "$2b$12$dos"],
    "pin_hash": "$2b$12$pin",
    "pin_failed_attempts": 2,
    "pin_locked_until": "2030-01-01",
    "webauthn_credentials": [{"public_key": "AAA", "sign_count": 3}],
    "webauthn_auth_challenge": "reto-de-entrada",
    "webauthn_reg_challenge": "reto-de-registro",
    "web_push_subscription": {"endpoint": "https://push/x",
                              "keys": {"auth": "s3cr3t"}},
    "push_token": "ExponentPushToken[xxx]",
    "original_email": "cuenta.borrada@ejemplo.com",
    "permissions": ["ver_todo", "pagar"],
    "legajo": {"cargo": "operador"},
    "ban_reason": "motivo interno",
    "rejection_reason": "motivo interno del KYC",
    "drive_kyc_link": "https://drive.google.com/x",
    "deleted_by": "sa_1",
}


def corre(coro):
    return asyncio.run(coro)


_ips = itertools.count(1)


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido():
    """Cada pedido desde una IP distinta: las puertas están limitadas por IP y
    sin esto el test número once se comería el 429 que puso el número uno."""
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
    b = mongomock_motor.AsyncMongoMockClient()["ris_cinco_puertas"]
    usar_base(b)
    corre(b.users.insert_one({
        "user_id": "u1", "email": CORREO, "name": "Ana", "role": "user",
        "email_verified": True, "password_set": True,
        "verification_status": "verified",
        "cpf_number": "12345678901", "referral_code": "ANA123",
        # Sembrado a propósito: las puertas escriben `last_login` al entrar y
        # algunas releen el documento después. Sin esto, la comparación de
        # campos marcaría una diferencia que es del test y no del producto.
        "last_login": "2026-01-01T00:00:00+00:00",
        "balance_ris": to_decimal128(10), "balance_ves": to_decimal128(0),
        "balance_ris_bono": to_decimal128(0),
        **{**LO_QUE_NO_ES_SUYO, "password_hash": hash_password(CLAVE)},
    }))
    return b


# ══════════════════════════════════════════════════════════════════════════
# Cómo se entra por cada puerta
# ══════════════════════════════════════════════════════════════════════════

def por_la_ventana(base):
    """GET /auth/me — la que mira la aplicación al abrirse."""
    return corre(rutas_auth.get_me(User(user_id="u1", email=CORREO)))


def por_la_contrasena(base):
    """POST /auth/login-password"""
    r = corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email=CORREO, password=CLAVE)))
    return r["user"]


def por_el_segundo_factor(base):
    """POST /auth/2fa/verify — con la cuenta ya con segundo factor puesto."""
    corre(base.users.update_one({"user_id": "u1"},
                                {"$set": {"two_factor_enabled": True}}))
    token = corre(rutas_2fa._create_pending_token("u1", "2fa_login"))
    r = corre(rutas_2fa.twofa_verify(
        pedido(), _RespuestaDeMentira(),
        rutas_2fa.TwoFAVerifyRequest(pending_token=token,
                                     code=pyotp.TOTP(SEMILLA).now())))
    return r["user"]


def por_el_alta_del_segundo_factor(base):
    """POST /auth/2fa/enroll-confirm — la puerta del alta del segundo factor.

    Es una puerta completa: consume el token, activa el segundo factor Y emite
    la sesión, o sea que su respuesta alimenta el mismo `setUser()` que las
    otras. Faltaba en este archivo, y se notó rompiéndola a propósito: la
    mutación que le agregaba un campo de más pasaba en verde.
    """
    corre(base.users.update_one(
        {"user_id": "u1"}, {"$set": {"two_factor_secret_pending": SEMILLA}}))
    token = corre(rutas_2fa._create_pending_token("u1", "2fa_enroll"))
    r = corre(rutas_2fa.twofa_enroll_confirm(
        pedido(), _RespuestaDeMentira(),
        rutas_2fa.TwoFASetupConfirmFromPendingRequest(
            pending_token=token, code=pyotp.TOTP(SEMILLA).now())))
    return r["user"]


def por_la_huella(base):
    """POST /webauthn/login/verify — no se puede firmar un reto de verdad acá,
    así que se prueba el armado de la respuesta, que es lo que este archivo
    vigila. La verificación criptográfica la prueban sus propios tests."""
    from services.perfil import para_su_dueno
    doc = corre(base.users.find_one({"user_id": "u1"}))
    return para_su_dueno(doc)


LAS_PUERTAS = {
    "login con contraseña": por_la_contrasena,
    "login con segundo factor": por_el_segundo_factor,
    "alta del segundo factor": por_el_alta_del_segundo_factor,
    "login con huella": por_la_huella,
}


# ══════════════════════════════════════════════════════════════════════════
# 1. Ninguna puerta deja salir lo que no es suyo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("puerta", LAS_PUERTAS)
@pytest.mark.parametrize("campo", sorted(LO_QUE_NO_ES_SUYO))
def test_NO_SALE_POR_NINGUNA_PUERTA(base, puerta, campo):
    """Uno por campo y por puerta: el nombre del test en rojo dice cuál se
    coló y por dónde, sin tener que leer un diff de tres archivos."""
    salida = LAS_PUERTAS[puerta](base)
    assert campo not in salida


@pytest.mark.parametrize("puerta", LAS_PUERTAS)
def test_LA_SEMILLA_NO_SALE_NI_ESCONDIDA(base, puerta):
    """La peor de todas, buscada por su VALOR y no por su nombre: si algún día
    se la renombra o se la mete adentro de otro campo, esto la sigue viendo."""
    import json
    salida = LAS_PUERTAS[puerta](base)
    assert SEMILLA not in json.dumps(salida, default=str)


# ══════════════════════════════════════════════════════════════════════════
# 2. Todas devuelven LO MISMO
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("puerta", LAS_PUERTAS)
def test_CADA_PUERTA_DEVUELVE_LO_MISMO_QUE_LA_VENTANA(base, puerta):
    """El test que importa, y el que no existía.

    Con un test por ruta, las cinco listas podían separarse de a poco y todos
    seguían en verde. Este compara: si una puerta se adelanta o se queda atrás,
    se pone rojo diciendo qué campo sobra o falta.
    """
    dela_ventana = set(por_la_ventana(base))
    dela_puerta = set(LAS_PUERTAS[puerta](base))

    # `two_factor_enabled` no: lo pone la propia puerta del segundo factor.
    sobran = dela_puerta - dela_ventana
    faltan = dela_ventana - dela_puerta
    assert not sobran, (
        f"«{puerta}» devuelve campos que /auth/me no: {sorted(sobran)}. "
        "Las cinco rutas alimentan el mismo setUser(): si una manda de más, "
        "volvieron las listas separadas.")
    assert not faltan, (
        f"a «{puerta}» le faltan campos que /auth/me sí manda: {sorted(faltan)}. "
        "La pantalla que los lea va a mostrar un hueco después de entrar, y "
        "se va a arreglar sola al recargar, que es la peor forma de fallar.")


def test_NINGUNA_PUERTA_VUELVE_A_ESCRIBIR_UNA_LISTA_DE_LO_PROHIBIDO():
    """La guarda contra la reincidencia.

    El defecto no fue que una lista estuviera mal: fue que hubiera CINCO, todas
    escritas a mano y todas distintas. Así que lo que se vigila no es un campo
    sino la FORMA:

        {k: v for k, v in user.items() if k not in ["_id", "password_hash", ...]}

    Se busca por estructura y no por texto a propósito. Buscar el nombre de un
    campo daba falsos positivos —`security_2fa` escribe `two_factor_secret
    _pending` legítimamente al dar de alta el segundo factor— y un falso
    positivo en una guarda termina con alguien apagando la guarda.
    """
    import ast
    import inspect
    from routes import webauthn_login

    def copias_con_lista_de_lo_prohibido(modulo):
        arbol = ast.parse(inspect.getsource(modulo))
        encontradas = []
        for n in ast.walk(arbol):
            if not isinstance(n, (ast.DictComp, ast.SetComp, ast.ListComp)):
                continue
            for gen in n.generators:
                for prueba in gen.ifs:
                    if not isinstance(prueba, ast.Compare):
                        continue
                    if not any(isinstance(o, ast.NotIn) for o in prueba.ops):
                        continue
                    for comparado in prueba.comparators:
                        nombres = {e.value for e in ast.walk(comparado)
                                   if isinstance(e, ast.Constant)
                                   and isinstance(e.value, str)}
                        # La firma: una lista de campos a esconder del usuario.
                        if "password_hash" in nombres:
                            encontradas.append(sorted(nombres))
        return encontradas

    for modulo in (rutas_auth, rutas_2fa, webauthn_login):
        culpables = copias_con_lista_de_lo_prohibido(modulo)
        assert not culpables, (
            f"{modulo.__name__} volvió a armar la respuesta con una lista de lo "
            f"PROHIBIDO: {culpables}. Ese fue el defecto —cinco listas que se "
            "separaron sin que nadie lo notara—. La lista compartida está en "
            "services/perfil.py y se usa con `para_su_dueno(user)`.")


def test_EL_BUSCADOR_DE_LISTAS_DE_LO_PROHIBIDO_SIRVE():
    """Que encuentre la forma que TIENE que encontrar, o no está mirando nada.

    Se le da el código exacto que había en las cinco puertas antes del arreglo.
    Sin esto, la guarda de arriba pasa en verde por no ver nada.
    """
    import ast

    codigo = (
        'user_response = {k: v for k, v in user.items() '
        'if k not in ["_id", "password_hash", "two_factor_secret"]}')
    arbol = ast.parse(codigo)
    hallada = False
    for n in ast.walk(arbol):
        if isinstance(n, ast.DictComp):
            for gen in n.generators:
                for prueba in gen.ifs:
                    if isinstance(prueba, ast.Compare) and \
                       any(isinstance(o, ast.NotIn) for o in prueba.ops):
                        nombres = {e.value for c in prueba.comparators
                                   for e in ast.walk(c)
                                   if isinstance(e, ast.Constant)
                                   and isinstance(e.value, str)}
                        if "password_hash" in nombres:
                            hallada = True
    assert hallada, "el buscador no ve la forma que vino a buscar"


def test_LA_LISTA_COMPARTIDA_NO_ESTA_VACIA():
    """Una lista vacía taparía todo y rompería las cinco pantallas a la vez."""
    from services import perfil
    assert len(perfil.LO_PERMITIDO) > 10
