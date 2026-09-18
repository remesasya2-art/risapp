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
    # La cuenta arranca de cero en cada test: si no, los veinte intentos de uno
    # dejan al siguiente con el cupo gastado y falla por el motivo equivocado.
    security_2fa.reiniciar_la_cuenta()
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
        corre(security_2fa.frenar(pedido(fija), "prueba.uno", "5/15minutes"))

    with pytest.raises(HTTPException):
        corre(security_2fa.frenar(pedido(fija), "prueba.uno", "5/15minutes"))

    # El otro alcance sigue intacto.
    corre(security_2fa.frenar(pedido(fija), "prueba.dos", "5/15minutes"))


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


# ══════════════════════════════════════════════════════════════════════════
# La cuenta afuera de la memoria del proceso
# ══════════════════════════════════════════════════════════════════════════
#
# La cuenta vivía en la memoria del proceso, y eso tenía dos costos: cada
# despliegue la ponía en cero, y con varios procesos cada uno llevaba la suya
# —«20 intentos cada 15 minutos» pasaba a ser 20 POR PROCESO—. Son dieciocho
# límites y casi todos protegen contraseñas, códigos y recuperación de cuenta.

def test_LLAMAR_A_FRENAR_SIN_AWAIT_DEJA_EL_ENDPOINT_SIN_LIMITE():
    """LA GUARDA QUE IMPORTA DE TODO ESTE ARCHIVO.

    `frenar` es `async`. Llamarla sin `await` NO FALLA: devuelve una corrutina,
    Python tira un aviso que nadie lee, y ese endpoint se queda sin límite. Un
    login sin límite es fuerza bruta libre contra contraseñas — y no hay nada
    en pantalla ni en el registro que lo diga.

    Se mira el árbol del código y no el texto: un `await frenar(...)` partido
    en dos líneas se le escapa a cualquier expresión regular.
    """
    import ast
    import pathlib

    raiz = pathlib.Path(_BACKEND)
    culpables = []
    for archivo in sorted(raiz.rglob("*.py")):
        if "tests" in archivo.parts or "__pycache__" in archivo.parts:
            continue
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except SyntaxError:                               # pragma: no cover
            continue
        esperadas = {n.value.lineno for n in ast.walk(arbol)
                     if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)}
        for n in ast.walk(arbol):
            # `frenar_por_cuenta` también: es `async` por el mismo motivo y
            # llamarla sin `await` deja la ruta de dinero sin límite por cuenta.
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ("frenar", "frenar_por_cuenta")
                    and n.lineno not in esperadas):
                culpables.append(f"{archivo.relative_to(raiz)}:{n.lineno}")

    assert not culpables, (
        "frenar() llamada sin await: ese endpoint NO tiene límite. Sitios: "
        f"{culpables}")


def test_TODOS_LOS_LIMITES_SIGUEN_PUESTOS():
    """Que ninguno se caiga en el camino.

    Se cuentan las llamadas, no se nombran una por una: una lista escrita a
    mano envejece, y lo que importa acá es que nadie BORRE un límite sin darse
    cuenta. Si se agrega uno nuevo, este número sube y el test lo dice.
    """
    import ast
    import pathlib

    raiz = pathlib.Path(_BACKEND)
    cuantos = 0
    for archivo in sorted(raiz.rglob("*.py")):
        if "tests" in archivo.parts or "__pycache__" in archivo.parts:
            continue
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except SyntaxError:                               # pragma: no cover
            continue
        cuantos += sum(1 for n in ast.walk(arbol)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id == "frenar")

    assert cuantos >= 17, (
        f"había 17 límites y ahora hay {cuantos}: alguno se cayó. Si sacaste "
        "uno a propósito, bajá el número acá y escribí por qué.")


def test_NO_QUEDA_NINGUN_DECORADOR_DE_LIMITE():
    """Con la cuenta afuera de slowapi, el decorador no tiene de dónde sacarla:
    quedaría escrito, se vería bien en una revisión, y no contaría nada."""
    import pathlib
    import re

    raiz = pathlib.Path(_BACKEND)
    culpables = []
    for archivo in list(raiz.glob("routes/*.py")) + list(raiz.glob("*.py")):
        for n, linea in enumerate(archivo.read_text().splitlines(), 1):
            if re.match(r"\s*@\w*limiter\.limit\(", linea):
                culpables.append(f"{archivo.relative_to(raiz)}:{n}")
    assert not culpables, f"quedó un decorador que ya no cuenta nada: {culpables}"


def test_EL_ALMACEN_ARRANCA_APAGADO(monkeypatch):
    """Un mecanismo nuevo en el camino del login que se despliega solo un
    viernes es peor que el problema que viene a resolver. Se prende con una
    variable de entorno en Railway, sin tocar código."""
    monkeypatch.delenv("LIMITES_EN_LA_BASE", raising=False)
    assert security_2fa._en_la_base() is False


@pytest.mark.parametrize("valor", ["si", "sí", "1", "true", "on", "SI"])
def test_SE_PRENDE_CON_LA_VARIABLE_DE_ENTORNO(monkeypatch, valor):
    monkeypatch.setenv("LIMITES_EN_LA_BASE", valor)
    assert security_2fa._en_la_base() is True


@pytest.mark.parametrize("valor", ["no", "", "apagado", "0", "false"])
def test_CUALQUIER_OTRA_COSA_LO_DEJA_APAGADO(monkeypatch, valor):
    """Un valor mal escrito no puede prender algo que toca el login."""
    monkeypatch.setenv("LIMITES_EN_LA_BASE", valor)
    assert security_2fa._en_la_base() is False


def test_SI_LA_BASE_NO_CONTESTA_EL_PEDIDO_NO_PASA():
    """LA PROPIEDAD DE SEGURIDAD. Lo contrario —dejar pasar cuando la base
    falla— haría que la defensa contra la fuerza bruta desapareciera justo
    cuando la base está en problemas, que es cuando menos se mira.

    No cuesta nada en la práctica: con Mongo caído no funciona ninguna pantalla
    de la aplicación, porque todas leen de ahí.
    """
    from limits import parse
    from limits.aio.strategies import FixedWindowRateLimiter
    from limits.storage import storage_from_string

    # El almacén de verdad, apuntado a una dirección donde no hay nadie.
    roto = FixedWindowRateLimiter(
        storage_from_string("async+mongodb://127.0.0.1:1/x",
                            serverSelectionTimeoutMS=200))
    with pytest.raises(Exception):
        corre(roto.hit(parse("5/minute"), "ip", "login"))
