"""
tests/test_entrar_con_el_bono_puesto.py — La puerta principal, con plata nueva.

QUE SE ESTABA ROMPIENDO

    `/auth/login-password` devolvía 500 a toda persona registrada desde que
    existe el bono de bienvenida. O sea: no podían entrar. Es la puerta
    principal de la aplicación y es la que usa `AuthContext.login()`.

POR QUE

    La ruta convertía los saldos a número con una lista de nombres escrita a
    mano —siete— y le faltaba `balance_ris_bono`. El registro escribe ese campo
    en Decimal128 desde el primer día del bono, y un Decimal128 NO SE PUEDE
    CONVERTIR A JSON: FastAPI se caía al armar la respuesta, después de haber
    verificado la contraseña y creado la sesión.

POR QUE NADIE LO VIO

    Porque una lista de nombres no avisa cuando le falta uno. Seguía andando
    perfecto para los seis saldos que sí estaban, y para toda cuenta anterior
    al bono, que no tiene el campo. El único síntoma era un 500 en cuentas
    nuevas, que es justo donde menos se mira.

    Y el test que existía miraba la otra ruta. `/auth/me` ya recorría por
    prefijo —no por lista— y tenía una guarda que lo exigía; el login hacía lo
    mismo de la forma frágil, a treinta líneas de distancia, sin guarda.

QUE PRUEBA ESTE ARCHIVO

    Que se puede entrar con cualquier saldo guardado como Decimal128, incluido
    uno que todavía no exista. Es la misma guarda que `/auth/me` ya tenía,
    puesta ahora sobre la puerta por la que se entra.
"""
import asyncio
import itertools
import os
import sys
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi.encoders import jsonable_encoder                 # noqa: E402
from starlette.datastructures import State                    # noqa: E402
from starlette.requests import Request as PedidoReal          # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from routes import auth as rutas_auth                         # noqa: E402
from routes.auth import LoginWithPasswordRequest            # noqa: E402
from services.money import to_decimal128                      # noqa: E402
from utils.security import hash_password                      # noqa: E402

ensenarle_decimal128_a_mongomock()

# Los saldos que la aplicación escribe hoy en `users`. Esta lista está acá
# ESCRITA A MANO A PROPOSITO, y no importada del código que se está probando:
# un test que lee la misma lista que la ruta pasa en verde aunque a las dos les
# falte el mismo nombre, que es exactamente lo que acababa de pasar. La guarda
# que cubre los saldos que todavía no existen es la de más abajo.
LOS_SALDOS = (
    "balance_ris", "balance_ves", "balance_ris_terceros",
    "balance_usdt", "balance_usdc", "balance_ris_bono",
    # Nombres viejos: una cuenta de hace tiempo puede tener la plata así.
    "balance_terceros", "balance_personal",
)

CLAVE = "Colibri!2026x"
CORREO = "ana@ejemplo.com"


def corre(coro):
    return asyncio.run(coro)


# Cada pedido desde una IP distinta: el login está limitado por IP y sin esto
# el test número once se comería el 429 que puso el test número uno.
_ips = itertools.count(1)


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido():
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
    b = mongomock_motor.AsyncMongoMockClient()["ris_entrar_con_bono"]
    usar_base(b)
    return b


def _entrar(base, saldos):
    """Crea la cuenta con esos saldos y entra, como entra la gente."""
    doc = {
        "user_id": "u1", "email": CORREO, "name": "Ana", "role": "user",
        "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE),
    }
    doc.update(saldos)
    corre(base.users.insert_one(doc))
    return corre(rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email=CORREO, password=CLAVE)))


def test_se_puede_entrar_con_el_bono_recien_registrado(base):
    """El caso exacto que estaba roto, escrito como lo escribe el registro.

    `routes/auth.py` guarda `balance_ris_bono` con `to_decimal128(0)` al dar de
    alta. O sea que CADA cuenta nueva traía el campo que tumbaba la respuesta,
    y el cero no salva: un Decimal128 en cero tampoco se convierte a JSON.
    """
    r = _entrar(base, {
        "balance_ris": to_decimal128(0),
        "balance_ves": to_decimal128(0),
        "balance_ris_bono": to_decimal128(0),
    })
    # `jsonable_encoder` es lo que hace FastAPI al devolver un dict. Si esto
    # levanta, en producción es un 500 con la sesión ya creada.
    jsonable_encoder(r)
    assert r["user"]["balance_ris_bono"] == 0.0


@pytest.mark.parametrize("campo", LOS_SALDOS)
def test_CADA_SALDO_SALE_CONVERTIDO(base, campo):
    """Uno por saldo a propósito: si alguno vuelve a quedar sin convertir, el
    nombre del test en rojo dice CUAL, sin tener que leer un diff."""
    r = _entrar(base, {campo: to_decimal128(Decimal("12.34"))})
    jsonable_encoder(r)
    assert r["user"][campo] == 12.34, (
        f"'{campo}' salió sin convertir y el login devuelve 500")


def test_LA_CONVERSION_ES_POR_PREFIJO_Y_NO_UNA_LISTA_DE_NOMBRES():
    """La guarda de fondo, probada donde vive: en la funcion que convierte.

    Se le pasa un saldo inventado que no esta en ninguna parte del codigo y se
    exige que salga convertido igual. Si alguien vuelve a escribir una lista de
    nombres, al proximo saldo nuevo le va a pasar lo mismo que le paso al bono
    —un 500 en la puerta de entrada— y este test se pone rojo primero.

    NO se prueba a traves del login a proposito. El login recorta antes por
    lista de lo permitido, asi que un saldo inventado no llega hasta la
    conversion: el test pasaria en verde con la conversion rota, que es peor
    que no tenerlo.
    """
    from services import perfil

    salida = perfil.terminar_de_armar(
        {"balance_de_algo_que_todavia_no_existe": to_decimal128(Decimal("7"))})
    assert salida["balance_de_algo_que_todavia_no_existe"] == 7.0


def test_UN_SALDO_QUE_NADIE_AGREGO_A_LA_LISTA_NO_SALE(base):
    """El precio de la lista de lo permitido, escrito donde se lee.

    Es su modo de fallar silencioso: la ruta contesta 200, nadie ve un error, y
    la pantalla muestra un hueco. Este test existe para que el dia que alguien
    agregue `balance_loquesea` y no lo vea, busque «LOS_SALDOS» y lo encuentre
    en un minuto en vez de en una tarde.
    """
    r = _entrar(base, {"balance_de_algo_que_todavia_no_existe":
                       to_decimal128(Decimal("7"))})
    jsonable_encoder(r)
    assert "balance_de_algo_que_todavia_no_existe" not in r["user"], (
        "salio un saldo que no esta en LOS_SALDOS: la puerta volvio a devolver "
        "el documento entero")


def test_UN_SALDO_VIEJO_EN_FLOAT_SIGUE_ENTRANDO(base):
    """Lectura tolerante: las cuentas de antes tienen los saldos en float y no
    se migraron. Convertirlas no las puede romper."""
    r = _entrar(base, {"balance_ris": 1234.56})
    jsonable_encoder(r)
    assert r["user"]["balance_ris"] == 1234.56


def test_UN_SALDO_VACIO_NO_TUMBA_EL_LOGIN(base):
    """Un `None` en un saldo no puede dejar a nadie afuera: se deja como está."""
    r = _entrar(base, {"balance_ris": to_decimal128(0), "balance_ves": None})
    jsonable_encoder(r)
    assert r["user"]["balance_ves"] is None
