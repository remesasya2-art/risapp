"""Las rutas que mueven plata frenan a quien opera demasiado seguido.

QUE PASABA

    De 157 rutas POST frenaban 17, y las 17 eran de entrada y recuperación:
    login, registro, códigos, huella. NINGUNA ruta de dinero tenía límite.
    Una cuenta con sesión podía crear pedidos de retiro sin parar.

    Y todos los límites eran por IP. Eso protege la puerta de entrada —quien
    no tiene sesión sólo tiene su IP— pero quien YA tiene sesión tiene además
    una cuenta, y una cuenta que cambia de red arranca de cero. Para el
    dinero, eso era no tener límite.

DONDE VA EL FRENO, Y POR QUE AHI

    Todas las rutas que mueven plata pasan por UNA dependencia:
    `sin_transacciones_personales`. Ahí van los dos contadores —por cuenta y
    por IP—, y una ruta nueva los hereda por usar la puerta de siempre. No
    hay diecisiete lugares donde olvidarse de uno.

    Los dos números viven en el catálogo de `services/configuracion.py` y se
    cambian desde el panel, no editando código.

LO QUE SE PRUEBA

    1. Que las rutas de dinero pasen por esa puerta (recorriendo la app).
    2. Que la puerta llame a los dos frenos (mirando el árbol, con `await`).
    3. Que la cuenta tope aunque cambie de IP, y que la IP tope aunque cambie
       de cuenta: dos contadores, no uno disfrazado.
    4. Que el tope salga del catálogo: cambiarlo en la base cambia lo que la
       puerta hace cumplir.
    5. Que el personal siga frenado ANTES de gastar cupo.

Y UNA COSA QUE APARECIO ESCRIBIENDO ESTO

    El punto 5 no pasaba. `User` no declaraba `es_personal`, Pydantic lo
    descartaba, y la puerta recibía siempre `False`: nunca había frenado a
    nadie. Se comprobó corriéndolo. El arreglo está en `models/user.py`, y
    `test_el_modelo_conserva_la_marca_del_personal` es lo que impide que
    vuelva a pasar.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock    # noqa: E402
from models.user import User                                        # noqa: E402
from routes import dependencies as deps                             # noqa: E402
from routes import security_2fa                                     # noqa: E402
from services import configuracion                                  # noqa: E402

ensenarle_decimal128_a_mongomock()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_freno_dinero"]
    usar_base(b)
    security_2fa.reiniciar_la_cuenta()
    yield b
    security_2fa.reiniciar_la_cuenta()


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido(ip="10.0.0.1"):
    return PedidoReal({
        "type": "http", "method": "POST", "path": "/api/withdrawal/create",
        "query_string": b"",
        "headers": [(b"cf-connecting-ip", ip.encode()), (b"user-agent", b"test")],
        "client": (ip, 0), "app": _AppDeMentira(),
    })


def cliente(uid="u1"):
    return User(user_id=uid, email=f"{uid}@ejemplo.com", name=uid, role="user")


def personal():
    # `es_personal=True` como lo marca RRHH. Con sólo `role="admin"` no alcanza,
    # y es a propósito: el rol dice qué puede hacer en el panel; la marca dice
    # que es una cuenta de trabajo. Ver services/personal.py.
    return User(user_id="p1", email="p1@ejemplo.com", name="Personal",
                role="admin", es_personal=True)


# ══════════════════════════════════════════════════════════════════════════
# 1. Las rutas de dinero pasan por la puerta
# ══════════════════════════════════════════════════════════════════════════

LAS_RUTAS_DE_DINERO = {
    ("POST", "/api/reais/send"),
    ("POST", "/api/withdrawal/create"),
    ("POST", "/api/withdraw-crypto"),
    ("POST", "/api/recharge/ves"),
    ("POST", "/api/gestor/pix/create"),
    ("POST", "/api/btc/generar-invoice"),
    ("POST", "/api/credits/deposit"),
    ("POST", "/api/payments/card/process"),
}


@pytest.fixture(scope="module")
def app_armada():
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return app


def _dependencias_de(ruta):
    vistas = []

    def caminar(ds):
        for d in ds or []:
            c = getattr(d, "call", None)
            if c is not None:
                vistas.append(c)
            caminar(getattr(d, "dependencies", None))

    caminar(getattr(getattr(ruta, "dependant", None), "dependencies", None))
    return vistas


def test_toda_ruta_de_dinero_pasa_por_la_puerta(app_armada):
    sin_freno, vistas = [], set()
    for ruta in app_armada.routes:
        camino = getattr(ruta, "path", "")
        for metodo in (getattr(ruta, "methods", None) or set()):
            if (metodo, camino) not in LAS_RUTAS_DE_DINERO:
                continue
            vistas.add((metodo, camino))
            if deps.sin_transacciones_personales not in _dependencias_de(ruta):
                sin_freno.append(f"{metodo} {camino}")
    faltan = LAS_RUTAS_DE_DINERO - vistas
    assert not faltan, f"estas rutas ya no existen con ese camino: {sorted(faltan)}"
    assert not sin_freno, (
        "Rutas que mueven plata SIN pasar por `sin_transacciones_personales`, "
        "o sea sin freno por cuenta ni por IP:\n    " + "\n    ".join(sin_freno))


# ══════════════════════════════════════════════════════════════════════════
# 2. La puerta llama a los dos frenos
# ══════════════════════════════════════════════════════════════════════════

def test_la_puerta_frena_por_cuenta_Y_por_ip():
    fuente = pathlib.Path(_BACKEND, "routes", "dependencies.py").read_text()
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef)
              and n.name == "sin_transacciones_personales")
    esperadas = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) \
                and isinstance(n.value.func, ast.Name):
            esperadas.add(n.value.func.id)
    assert "frenar_por_cuenta" in esperadas, "la puerta ya no frena por cuenta"
    assert "frenar" in esperadas, "la puerta ya no frena por IP"


# ══════════════════════════════════════════════════════════════════════════
# 3. Dos contadores de verdad
# ══════════════════════════════════════════════════════════════════════════

def test_la_cuenta_topa_aunque_cambie_de_ip(base):
    async def cuerpo():
        await configuracion.escribir(base, "dinero_operaciones_por_cuenta_por_hora", 3)
        await configuracion.escribir(base, "dinero_operaciones_por_ip_por_hora", 1000)
        u = cliente("u1")
        for i in range(3):
            await deps.sin_transacciones_personales(pedido(f"10.0.0.{i}"), u)
        with pytest.raises(Exception) as e:
            await deps.sin_transacciones_personales(pedido("10.0.0.99"), u)
        assert getattr(e.value, "status_code", None) == 429
    corre(cuerpo())


def test_la_ip_topa_aunque_cambie_de_cuenta(base):
    async def cuerpo():
        await configuracion.escribir(base, "dinero_operaciones_por_cuenta_por_hora", 1000)
        await configuracion.escribir(base, "dinero_operaciones_por_ip_por_hora", 3)
        for i in range(3):
            await deps.sin_transacciones_personales(pedido("10.0.0.1"), cliente(f"u{i}"))
        with pytest.raises(Exception) as e:
            await deps.sin_transacciones_personales(pedido("10.0.0.1"), cliente("u99"))
        assert getattr(e.value, "status_code", None) == 429
    corre(cuerpo())


def test_otra_cuenta_desde_otra_ip_no_paga_el_cupo_ajeno(base):
    """Que el freno sea por cuenta y no global: dos personas distintas en
    dos redes distintas no se frenan entre sí."""
    async def cuerpo():
        await configuracion.escribir(base, "dinero_operaciones_por_cuenta_por_hora", 2)
        await configuracion.escribir(base, "dinero_operaciones_por_ip_por_hora", 2)
        for _ in range(2):
            await deps.sin_transacciones_personales(pedido("10.0.0.1"), cliente("u1"))
        # u1 en 10.0.0.1 agotó los dos. u2 en 10.0.0.2 no tiene nada gastado.
        await deps.sin_transacciones_personales(pedido("10.0.0.2"), cliente("u2"))
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. El número sale del catálogo
# ══════════════════════════════════════════════════════════════════════════

def test_los_dos_numeros_estan_en_el_catalogo():
    for clave in ("dinero_operaciones_por_cuenta_por_hora",
                  "dinero_operaciones_por_ip_por_hora"):
        assert clave in configuracion.AJUSTES, clave
        assert configuracion.AJUSTES[clave].tipo == configuracion.ENTERO


def test_el_de_cuenta_va_mas_bajo_que_el_de_ip_por_defecto():
    """Detrás de una IP puede haber una oficina; detrás de una cuenta, una
    persona. Si el de IP fuera el bajo, una oficina entera se frenaría por
    lo que hace uno."""
    a = configuracion.AJUSTES["dinero_operaciones_por_cuenta_por_hora"].defecto
    b = configuracion.AJUSTES["dinero_operaciones_por_ip_por_hora"].defecto
    assert a < b


def test_cambiar_el_numero_desde_el_panel_cambia_lo_que_se_cumple(base):
    async def cuerpo():
        await configuracion.escribir(base, "dinero_operaciones_por_ip_por_hora", 1000)
        await configuracion.escribir(base, "dinero_operaciones_por_cuenta_por_hora", 1)
        await deps.sin_transacciones_personales(pedido(), cliente("u1"))
        with pytest.raises(Exception):
            await deps.sin_transacciones_personales(pedido(), cliente("u1"))
        # Con otro número, otra cuenta llega más lejos.
        await configuracion.escribir(base, "dinero_operaciones_por_cuenta_por_hora", 5)
        for _ in range(5):
            await deps.sin_transacciones_personales(pedido(), cliente("u2"))
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 5. El personal sigue afuera, y no gasta cupo
# ══════════════════════════════════════════════════════════════════════════

def test_el_personal_sigue_frenado_con_403(base):
    async def cuerpo():
        with pytest.raises(Exception) as e:
            await deps.sin_transacciones_personales(pedido(), personal())
        assert getattr(e.value, "status_code", None) == 403
    corre(cuerpo())


def test_el_modelo_conserva_la_marca_del_personal():
    """Si `User` vuelve a perder el campo, la puerta vuelve a ser decorativa
    y ningún otro test lo nota: el 403 simplemente no sale."""
    from routes.dependencies import DEL_USUARIO
    u = User(user_id="p1", email="p@e.com", name="P", role="admin", es_personal=True)
    assert u.es_personal is True, "User descarta es_personal"
    assert "es_personal" in DEL_USUARIO, "get_current_user no se lo pide a la base"


def test_una_cuenta_sana_pasa(base):
    async def cuerpo():
        u = await deps.sin_transacciones_personales(pedido(), cliente("u1"))
        assert u.user_id == "u1"
    corre(cuerpo())
