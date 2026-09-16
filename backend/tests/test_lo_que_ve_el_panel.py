"""
tests/test_lo_que_ve_el_panel.py — Lo que el panel ve de OTRA persona.

QUE PASABA

    `/api/admin/users` devolvía cada usuario con `{"_id": 0, "password_hash": 0}`
    —otra lista de lo prohibido— o sea el documento entero menos la contraseña.
    Comprobado corriendo la ruta con un `agent`, que es el rol más bajo con
    acceso al panel:

        jefe@ejemplo.com   super_admin   two_factor_secret, pin_hash,
                                         webauthn_credentials
        ana@ejemplo.com    user          pin_hash, push_token,
                                         web_push_subscription

    Todos en una sola respuesta, sin necesidad de saber ningún identificador.

POR QUE ES PEOR QUE LA FUGA DE `/auth/me`

    Ahí cada persona veía cosas SUYAS. Acá se ve la semilla del segundo factor
    de otro, y la del dueño de la empresa entre ellas. Quien la tenga genera
    los códigos del jefe para siempre: es la diferencia entre ver de más y
    poder entrar como otro.

    El hash del PIN es lo mismo en chico: son cuatro dígitos, diez mil
    combinaciones. Contra un hash que ya se tiene, eso no es una barrera.

    Y la ruta pide `users.view`, que es el permiso de atención al cliente. Ese
    permiso tiene que servir para ver a un cliente, no para quedarse con su
    llave.

QUE PRUEBA ESTE ARCHIVO

    Las dos mitades, como el del dueño: que las llaves no salgan, y que lo que
    el panel necesita para trabajar siga saliendo. Los nombres de la segunda
    mitad salieron de recorrer `AdminPanel.jsx`, que es el único consumidor de
    estas rutas en todo el frontend.
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

from conftest import usar_base, ensenarle_decimal128_a_mongomock  # noqa: E402
from models.user import User                                   # noqa: E402
from routes import admin as rutas_admin                        # noqa: E402
from services import perfil                                    # noqa: E402
from services.money import to_decimal128                       # noqa: E402

ensenarle_decimal128_a_mongomock()

SEMILLA_DEL_JEFE = "JBSWY3DPEHPK3PXP-DEL-JEFE"

# Las llaves de OTRA persona. Que el panel no pueda verlas es lo que separa
# «ver a un cliente» de «poder entrar como él».
LAS_LLAVES_DE_OTRO = [
    "password_hash",
    "two_factor_secret",
    "two_factor_secret_pending",
    "two_factor_backup_hashes",
    "pin_hash",
    "webauthn_credentials",
    "webauthn_auth_challenge",
    "webauthn_reg_challenge",
    # No son llaves, pero tampoco son del panel: son de la persona.
    "web_push_subscription",
    "push_token",
    "original_email",
]

# Lo que `AdminPanel.jsx` lee de verdad de estas rutas.
LO_QUE_EL_PANEL_NECESITA = [
    "user_id", "name", "email", "phone_number", "profile_picture",
    "role", "status", "verification_status", "email_verified",
    "balance_ris", "balance_ris_terceros",
    "cpf_number", "referral_code", "gestor_code",
    "created_at", "last_login",
]


def corre(coro):
    return asyncio.run(coro)


UN_AGENTE = User(user_id="ag_1", email="agente@ejemplo.com", name="Agente",
                 role="agent")


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_panel"]
    usar_base(b)
    corre(b.users.insert_many([
        {
            "user_id": "sa_1", "email": "jefe@ejemplo.com", "name": "Jefe",
            "role": "super_admin", "status": "active",
            "verification_status": "verified", "email_verified": True,
            "phone_number": "+5511900000000", "profile_picture": None,
            "cpf_number": "11111111111", "referral_code": "JEFE",
            "gestor_code": "G1", "created_at": "2026-01-01",
            "last_login": "2026-09-01",
            "balance_ris": to_decimal128(0),
            "balance_ris_terceros": to_decimal128(0),
            "two_factor_enabled": True,
            "two_factor_secret": SEMILLA_DEL_JEFE,
            "two_factor_backup_hashes": ["$2b$12$uno", "$2b$12$dos"],
            "pin_hash": "$2b$12$pin-del-jefe",
            "webauthn_credentials": [{"public_key": "AAA"}],
            "password_hash": "$2b$12$clave-del-jefe",
        },
        {
            "user_id": "u_1", "email": "ana@ejemplo.com", "name": "Ana",
            "role": "user", "status": "active",
            "verification_status": "verified", "email_verified": True,
            "phone_number": "+5511911111111", "profile_picture": None,
            "cpf_number": "22222222222", "referral_code": "ANA",
            "gestor_code": None, "created_at": "2026-02-01",
            "last_login": "2026-09-10",
            "balance_ris": to_decimal128("150.50"),
            "balance_ris_terceros": to_decimal128(0),
            "pin_hash": "$2b$12$pin-de-ana",
            "push_token": "ExponentPushToken[ana]",
            "web_push_subscription": {"keys": {"auth": "s3cr3t"}},
            "original_email": "ana.vieja@ejemplo.com",
            "password_hash": "$2b$12$clave-de-ana",
        },
    ]))
    return b


def la_lista(base):
    return corre(rutas_admin.get_all_users(admin=UN_AGENTE))["users"]


def el_detalle(base):
    return corre(rutas_admin.get_user_detail("sa_1", admin=UN_AGENTE))["user"]


def el_historial(base):
    return corre(
        rutas_admin.get_user_complete_history("sa_1", admin=UN_AGENTE))["profile"]


LAS_RUTAS = {
    "la lista de usuarios": la_lista,
    "el detalle de uno": el_detalle,
    "el historial completo": el_historial,
}


def _documentos(salida):
    return salida if isinstance(salida, list) else [salida]


# ══════════════════════════════════════════════════════════════════════════
# 1. Las llaves de otro no salen
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", LAS_RUTAS)
@pytest.mark.parametrize("campo", LAS_LLAVES_DE_OTRO)
def test_NO_SALE_LA_LLAVE_DE_OTRO(base, ruta, campo):
    """Uno por campo y por ruta: el nombre del test en rojo dice cuál se coló
    y por dónde."""
    for doc in _documentos(LAS_RUTAS[ruta](base)):
        assert campo not in doc, f"{campo} salió por «{ruta}»"


@pytest.mark.parametrize("ruta", LAS_RUTAS)
def test_LA_SEMILLA_DEL_JEFE_NO_SALE_NI_ESCONDIDA(base, ruta):
    """La peor, buscada por su VALOR: si se la renombra o se la mete adentro de
    otro campo, esto la sigue viendo.

    Que la vea quien atiende al cliente es la diferencia entre ver de más y
    poder entrar como el dueño de la empresa.
    """
    import json
    salida = LAS_RUTAS[ruta](base)
    assert SEMILLA_DEL_JEFE not in json.dumps(salida, default=str)


def test_LA_LISTA_ENTERA_NO_TRAE_NI_UNA_LLAVE(base):
    """El caso que se midió: todos los usuarios en una sola respuesta.

    No hacía falta saber ningún identificador — bastaba pedir la lista.
    """
    import json
    texto = json.dumps(la_lista(base), default=str)
    for pedazo in (SEMILLA_DEL_JEFE, "$2b$12$pin-del-jefe", "$2b$12$pin-de-ana",
                   "$2b$12$clave-del-jefe", "s3cr3t", "ExponentPushToken[ana]"):
        assert pedazo not in texto, f"{pedazo!r} viaja en la lista de usuarios"


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que el panel necesita sigue saliendo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("campo", LO_QUE_EL_PANEL_NECESITA)
def test_EL_PANEL_SIGUE_VIENDO_LO_QUE_NECESITA(base, campo):
    """La otra mitad. Una lista de lo permitido que se come un campo no rompe
    ningún test del servidor —la ruta contesta 200 igual— y aparece como una
    columna vacía en el panel, que es donde se atiende a la gente."""
    ana = next(u for u in la_lista(base) if u["user_id"] == "u_1")
    assert campo in ana, (
        f"'{campo}' dejó de salir y AdminPanel.jsx lo lee: revisá "
        "LO_QUE_VE_EL_PANEL en services/perfil.py")


@pytest.mark.parametrize("ruta", LAS_RUTAS)
def test_LA_PESTANA_DE_USUARIOS_NO_DEVUELVE_500(base, ruta):
    """Esta ruta estaba ROTA, y no por el cambio de la proyección.

    Comprobado corriendo la proyección vieja: devolvía los saldos en Decimal128,
    que no se convierte a JSON. O sea que la pestaña «Usuarios» del panel no
    abría para ningún usuario con plata guardada así — que son todos desde que
    la plata se guarda así.

    Es el mismo defecto que tenía la puerta de entrada. Apareció acá porque el
    test de «lo que el panel necesita» exige ver el saldo, y para verlo hay que
    serializarlo.
    """
    from fastapi.encoders import jsonable_encoder
    jsonable_encoder(LAS_RUTAS[ruta](base))


def test_EL_SALDO_LLEGA_COMO_NUMERO_Y_CON_SU_VALOR(base):
    """Que se convierta no alcanza: tiene que llegar el monto correcto.

    Una conversión que devuelva cero serializa perfecto y miente en la pantalla
    donde se atiende a la gente.
    """
    ana = next(u for u in la_lista(base) if u["user_id"] == "u_1")
    assert ana["balance_ris"] == 150.50


def test_UN_SALDO_QUE_TODAVIA_NO_EXISTE_TAMBIEN_SE_CONVIERTE(base):
    """La conversión es por prefijo y no por una lista de nombres.

    Se agrega un saldo que no está en ninguna parte del código. Como está en
    LOS_SALDOS no va a salir por la proyección, así que se prueba la conversión
    directamente, que es donde vive la regla.
    """
    from services import perfil
    salida = perfil.terminar_de_armar(
        {"balance_recien_inventado": to_decimal128("3.50")})
    assert salida["balance_recien_inventado"] == 3.50


# ══════════════════════════════════════════════════════════════════════════
# 3. La forma, no el nombre
# ══════════════════════════════════════════════════════════════════════════

def test_LA_LISTA_DEL_PANEL_ES_DE_LO_PERMITIDO(base):
    """Una proyección de exclusión se reconoce porque lleva ceros en campos que
    no son `_id`. Volver a esa forma deja pasar cada campo nuevo hasta que
    alguien se acuerde — que es exactamente lo que pasó acá."""
    prohibidos = {c: v for c, v in perfil.LO_QUE_VE_EL_PANEL.items()
                  if v == 0 and c != "_id"}
    assert not prohibidos, f"volvió la lista de lo prohibido: {sorted(prohibidos)}"
    assert perfil.LO_QUE_VE_EL_PANEL.get("_id") == 0


def test_NINGUNA_LLAVE_ESTA_EN_LA_LISTA_DEL_PANEL():
    """Por si alguien agrega una a mano sin correr los tests de arriba."""
    colados = [c for c in LAS_LLAVES_DE_OTRO
               if perfil.LO_QUE_VE_EL_PANEL.get(c) == 1]
    assert not colados, f"están permitidos y no deberían: {colados}"


def test_EL_PANEL_VE_MAS_QUE_EL_DUENO_PERO_NINGUNA_LLAVE():
    """Las dos listas existen por separado a propósito, y la relación entre
    ellas es la que tiene que ser.

    El panel ve MAS que el dueño de la cuenta —necesita el estado del KYC y el
    rol de alguien que no es él para poder atenderlo— pero ninguna de las dos
    incluye una forma de entrar. Si algún día se las unifica, esto se pone rojo
    y obliga a pensarlo.
    """
    assert perfil.LO_PERMITIDO_AL_PANEL - perfil.LO_PERMITIDO, (
        "el panel ya no ve nada que el dueño no vea: ¿se unificaron las listas?")
    for lista in (perfil.LO_PERMITIDO, perfil.LO_PERMITIDO_AL_PANEL):
        assert not (set(LAS_LLAVES_DE_OTRO) & lista)
