"""
tests/test_limite_por_ip.py — El límite de intentos cuenta por IP, no en bloque.

EL BUG QUE ESTE ARCHIVO CONGELA

    `routes/auth.py` limitaba así:

        async def login_with_password(request, response, body):
            from routes.security_2fa import limiter

            @limiter.limit("20/15minutes")
            async def _do_login(request, body):
                ...
            return await _do_login(request, body)

    El decorador se aplica sobre una función definida ADENTRO del handler, o
    sea que se vuelve a aplicar EN CADA PEDIDO. Y aplicar `@limiter.limit`
    agrega una entrada a `limiter._route_limits["routes.auth._do_login"]`,
    una lista que no se limpia nunca.

    `_check_request_limit` recorre esa lista entera y descuenta una unidad
    del cupo por cada entrada. Así que:

      - Después de 20 ingresos el proceso tenía 20 entradas acumuladas, y un
        solo pedido consumía 20 del cupo de 20. Medido: el ingreso número 21,
        DESDE UNA IP QUE NUNCA HABÍA ENTRADO, se rechazaba con 429.
      - A partir de ahí nadie más podía entrar. No se recuperaba solo: había
        que reiniciar el proceso, y a los 20 ingresos volvía a pasar.
      - La lista crecía sin techo mientras el servidor viviera.

    Estaba en cinco endpoints: login, reenvío del código de verificación,
    pedido de reseteo de contraseña, verificación de identidad de
    recuperación, y —hasta que se arregló— los dos del primer acceso del
    personal.

    Los dos tests que importan son los dos extremos: que veinte IPs distintas
    puedan entrar, y que UNA sola IP siga topando a los veinte intentos. Si
    alguien "arregla" el primero sacando el límite, el segundo se pone rojo.
"""
import asyncio
import itertools
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
from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from models.requests import LoginWithPasswordRequest                # noqa: E402
from routes import auth as rutas_auth                               # noqa: E402
from routes import security_2fa                                     # noqa: E402
from utils.security import hash_password                            # noqa: E402


CLAVE = "Turpial!2026x"

# Este archivo usa un rango de IPs propio para no cruzarse con el de
# test_primer_acceso_del_personal.py: los contadores del limitador son del
# proceso, no de la base, así que sobreviven al fixture.
_ips = itertools.count(1)


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = security_2fa.limiter


def pedido(ip=None):
    if ip is None:
        n = next(_ips)
        ip = f"172.{n // 65536 % 250}.{n // 256 % 256}.{n % 256}"
    return PedidoReal({
        "type": "http", "method": "POST", "path": "/", "query_string": b"",
        "headers": [(b"x-forwarded-for", ip.encode()), (b"user-agent", b"test")],
        "client": (ip, 0), "app": _AppDeMentira(),
    })


class _RespuestaDeMentira:
    def set_cookie(self, *a, **k):
        pass


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["limite"]
    usar_base(b)
    corre(b.users.insert_one({
        "user_id": "u_1", "email": "cliente@correo.com", "name": "Cliente",
        "role": "user", "email_verified": True, "password_set": True,
        "password_hash": hash_password(CLAVE), "is_active": True,
    }))
    return b


def _entrar(ip=None):
    return corre(rutas_auth.login_with_password(
        pedido(ip), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email="cliente@correo.com", password=CLAVE)))


def test_treinta_ips_distintas_pueden_entrar(base):
    """El caso que estaba roto: la IP 21 se comía un 429 que no era suyo."""
    for i in range(30):
        r = _entrar()
        assert r.get("session_token"), f"el ingreso {i + 1} desde una IP nueva falló"


def test_una_sola_ip_sigue_topando(base):
    """Y el límite tiene que seguir existiendo: 20 en 15 minutos, por IP."""
    fija = "172.31.31.31"
    for i in range(20):
        assert _entrar(fija).get("session_token"), f"el intento {i + 1} falló antes de tiempo"

    with pytest.raises(HTTPException) as e:
        _entrar(fija)
    assert e.value.status_code == 429


def test_gastar_el_cupo_de_un_endpoint_no_afecta_al_otro(base):
    """Los contadores van separados por alcance.

    Sin eso, alguien que se pasa pidiendo "olvidé mi contraseña" se queda
    también sin poder iniciar sesión, que es su único camino de vuelta.
    """
    fija = "172.30.30.30"
    for _ in range(5):
        security_2fa.frenar(pedido(fija), "prueba.uno", "5/15minutes")

    with pytest.raises(HTTPException):
        security_2fa.frenar(pedido(fija), "prueba.uno", "5/15minutes")

    # El otro alcance sigue intacto.
    security_2fa.frenar(pedido(fija), "prueba.dos", "5/15minutes")


def test_ningun_handler_vuelve_a_decorar_por_pedido():
    """Que nadie reintroduzca el patrón, en este archivo ni en otro.

    Se busca `@limiter.limit` con sangría: en el margen izquierdo está bien
    —FastAPI decora una sola vez, al importar— y adentro de una función es
    el bug.
    """
    import pathlib
    import re

    raiz = pathlib.Path(_BACKEND)
    culpables = []
    for archivo in list(raiz.glob("routes/*.py")) + list(raiz.glob("*.py")):
        for n, linea in enumerate(archivo.read_text().splitlines(), 1):
            if re.match(r"\s+@\w*limiter\.limit\(", linea):
                culpables.append(f"{archivo.relative_to(raiz)}:{n}")

    assert not culpables, (
        "@limiter.limit adentro de una función se re-aplica en cada pedido y "
        "acumula límites. Usá security_2fa.frenar(request, alcance, regla). "
        f"Sitios: {culpables}")
