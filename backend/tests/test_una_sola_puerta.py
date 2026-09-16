"""Una sola puerta de entrada al panel, y que se note si aparece otra.

QUE PASO
    Había dos. La buena en `routes/dependencies.py`, que usan 210 de las 224
    rutas de administración. Otra en `admin_routes.py`, que usaban 14.

    A la segunda le faltaban tres controles que la primera sí tiene: no miraba
    `is_banned`, no miraba `is_deleted`, y no consultaba la tabla de permisos
    de `services/permisos.py`. Entre esas 14 rutas están mover cualquier
    saldo, aprobar recargas, exportar todas las transacciones y crear
    colaboradores nuevos.

    Se comprobó corriéndolo, no leyéndolo: con el mismo colaborador sin
    ningún permiso tildado y la misma ruta de mover saldos, la puerta buena
    contestaba «Te falta el permiso "Ajustar saldos a mano (MUEVE DINERO)"» y
    la otra lo dejaba pasar.

POR QUE EL TEST QUE YA EXISTIA NO LO VIO
    `test_permisos_se_aplican.py` recorre la aplicación armada y reconoce los
    guards POR SU NOMBRE. La copia de `admin_routes.py` se llamaba
    `get_admin_user`, igual que la buena, así que esas 14 rutas contaban como
    protegidas mientras no lo estaban.

    Por eso acá se reconocen por IDENTIDAD: el objeto función que vive en
    `routes/dependencies.py`, no una cadena de texto. Una copia futura con el
    mismo nombre pone este archivo en rojo.
"""
import asyncio
import datetime as dt
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
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock    # noqa: E402
from routes import auth as rutas_auth                               # noqa: E402
from routes import dependencies as deps                             # noqa: E402
from routes.auth import LoginWithPasswordRequest                    # noqa: E402
from utils.security import hash_password                            # noqa: E402

ensenarle_decimal128_a_mongomock()

CLAVE = "Colibri!2026x"
_ips = itertools.count(1)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_una_sola_puerta"]
    usar_base(b)
    yield b


class _AppDeMentira:
    def __init__(self):
        self.state = State()
        self.state.limiter = None


def pedido(metodo="POST", camino="/"):
    """Cada pedido desde una IP distinta: la puerta está limitada por IP y sin
    esto el test número once se comería el 429 que puso el número uno."""
    n = next(_ips)
    ip = f"10.{n // 65536 % 250}.{n // 256 % 256}.{n % 256}"
    r = PedidoReal({
        "type": "http", "method": metodo, "path": camino, "query_string": b"",
        "headers": [(b"x-forwarded-for", ip.encode()), (b"user-agent", b"test")],
        "client": (ip, 0), "app": _AppDeMentira(),
    })

    class _Ruta:
        path = camino
    r.scope["route"] = _Ruta()
    return r


class _RespuestaDeMentira:
    def __init__(self):
        self.headers = {}

    def set_cookie(self, *a, **k):
        pass

    def delete_cookie(self, *a, **k):
        pass


def corre(coro):
    return asyncio.run(coro)


async def _con_sesion(base, **campos):
    """Deja un usuario y una sesión válida suya, y devuelve el token."""
    campos.setdefault("user_id", "u_1")
    campos.setdefault("email", "quien@ejemplo.com")
    campos.setdefault("name", "Quien")
    campos.setdefault("role", "admin")
    await base.users.insert_one(campos)
    token = f"tok_{campos['user_id']}"
    await base.user_sessions.insert_one({
        "session_token": token, "user_id": campos["user_id"],
        "expires_at": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1),
    })
    return token


# ══════════════════════════════════════════════════════════════════════════
# La guarda: que no vuelva a haber una segunda puerta
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def app_armada():
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return app


def _pasa_por_la_puerta_buena(ruta) -> bool:
    """¿La cadena de dependencias de esta ruta incluye `get_current_user`?

    Se compara el OBJETO función, no su nombre. Una copia llamada igual —que
    es lo que hubo— no cuenta.
    """
    visto = []

    def caminar(ds):
        for d in ds or []:
            c = getattr(d, "call", None)
            if c is not None:
                visto.append(c)
            caminar(getattr(d, "dependencies", None))

    caminar(getattr(getattr(ruta, "dependant", None), "dependencies", None))
    return deps.get_current_user in visto


def test_toda_ruta_de_admin_entra_por_la_misma_puerta(app_armada):
    """Si alguien escribe una segunda puerta, acá se pone rojo.

    `get_current_user` es la única que mira `is_deleted` e `is_banned`, y la
    única por la que pasa la tabla de permisos. Una ruta de administración que
    no la tenga en su cadena está sin esos tres controles.
    """
    sueltas, revisadas = [], 0
    for ruta in app_armada.routes:
        camino = getattr(ruta, "path", "")
        # `/api/adminbrl/...` queda afuera a propósito: es el puente entre
        # máquinas, no lo usa ninguna persona y no entra con sesión sino con
        # una clave compartida en la cabecera (`_check_api_key`). Mirarle
        # `is_banned` a una llave no significa nada.
        if not (camino == "/api/admin" or camino.startswith("/api/admin/")):
            continue
        metodos = sorted(m for m in (getattr(ruta, "methods", None) or set())
                         if m not in ("HEAD", "OPTIONS"))
        if not metodos:
            continue
        revisadas += 1
        if not _pasa_por_la_puerta_buena(ruta):
            quien = getattr(getattr(ruta, "endpoint", None), "__module__", "?")
            sueltas.append(f"    {'/'.join(metodos):7s} {camino}   ({quien})")

    # Sin esto el test pasaría igual si el filtro de arriba dejara de
    # encontrar rutas: cero sueltas de cero revisadas es verde y no prueba
    # nada. Hoy son 224; el piso es flojo a propósito, para que agregar o
    # sacar rutas no lo rompa sin motivo.
    assert revisadas >= 200, (
        f"Sólo se revisaron {revisadas} rutas de administración. El filtro se "
        f"rompió: este test no está mirando lo que dice mirar.")

    assert not sueltas, (
        "Estas rutas de administración NO pasan por "
        "routes/dependencies.get_current_user, así que no miran `is_banned`, "
        "no miran `is_deleted` y no consultan la tabla de permisos:\n\n"
        + "\n".join(sueltas)
        + "\n\nUsá los guards de routes/dependencies.py. No escribas otros: "
          "dos puertas se despegan, y ya se despegaron una vez."
    )


def test_las_catorce_rutas_que_estaban_sueltas_siguen_existiendo(app_armada):
    """El test de arriba también pasaría si alguien borrara las rutas.

    Este fija que sigan ahí, atendidas por `admin_routes`, para que el de
    arriba esté diciendo algo sobre ellas y no sobre un archivo vacío.
    """
    de_admin_routes = [
        getattr(r, "path", "") for r in app_armada.routes
        if getattr(getattr(r, "endpoint", None), "__module__", "") == "admin_routes"
        and getattr(r, "path", "").startswith("/api/admin")
    ]
    assert len(de_admin_routes) == 14, (
        f"admin_routes.py atiende {len(de_admin_routes)} rutas, se esperaban "
        f"14. Si el cambio fue a propósito, corregí el número acá:\n"
        + "\n".join(f"    {c}" for c in sorted(de_admin_routes)))


# ══════════════════════════════════════════════════════════════════════════
# Los tres controles, uno por uno, sobre una ruta que mueve dinero
# ══════════════════════════════════════════════════════════════════════════

def _guards_de_admin_routes_son_los_buenos():
    """Lo que hace que los cuatro tests de abajo hablen de `admin_routes.py`.

    Los guards se ejercitan a través de `routes/dependencies.py`, que es de
    donde ahora salen. Esta comprobación es la que ata una cosa con la otra:
    si alguien vuelve a escribir copias locales, los de abajo seguirían verdes
    probando la puerta buena mientras las 14 rutas entran por otra.
    """
    import admin_routes
    assert admin_routes.get_admin_user is deps.get_admin_user
    assert admin_routes.get_super_admin is deps.get_super_admin
    assert admin_routes.get_current_user_from_request is deps.get_current_user


async def _entra_al_panel(token, metodo, camino, super_admin=False):
    """Recorre la cadena completa, como la recorre FastAPI."""
    _guards_de_admin_routes_son_los_buenos()
    p = pedido(metodo, camino)
    usuario = await deps.get_current_user(p, authorization=f"Bearer {token}")
    if super_admin:
        return await deps.get_super_admin(usuario)
    return await deps.get_admin_user(p, usuario)


def test_un_colaborador_sin_el_permiso_no_mueve_saldos(base):
    """El que antes pasaba con cero permisos tildados."""
    async def cuerpo():
        token = await _con_sesion(base, user_id="s1", role="admin", permissions=[])
        with pytest.raises(Exception) as e:
            await _entra_al_panel(token, "PUT", "/api/admin/users/{user_id}/balance")
        assert getattr(e.value, "status_code", None) == 403
        assert "Ajustar saldos" in str(getattr(e.value, "detail", ""))
    corre(cuerpo())


def test_con_el_permiso_puesto_si_pasa(base):
    """La otra mitad: que el arreglo no haya cerrado la puerta a todos."""
    async def cuerpo():
        token = await _con_sesion(base, user_id="s2", role="admin",
                                  permissions=["saldos.ajustar"])
        u = await _entra_al_panel(token, "PUT", "/api/admin/users/{user_id}/balance")
        assert u.user_id == "s2"
    corre(cuerpo())


def test_un_admin_baneado_no_entra_al_panel(base):
    async def cuerpo():
        token = await _con_sesion(base, user_id="s3", role="super_admin",
                                  is_banned=True)
        with pytest.raises(Exception) as e:
            await _entra_al_panel(token, "GET", "/api/admin/sub-admins",
                                  super_admin=True)
        assert getattr(e.value, "status_code", None) == 403
    corre(cuerpo())


def test_un_admin_borrado_no_entra_al_panel(base):
    async def cuerpo():
        token = await _con_sesion(base, user_id="s4", role="super_admin",
                                  is_deleted=True)
        with pytest.raises(Exception) as e:
            await _entra_al_panel(token, "GET", "/api/admin/sub-admins",
                                  super_admin=True)
        assert getattr(e.value, "status_code", None) == 401
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# La otra mitad del agujero: el login
# ══════════════════════════════════════════════════════════════════════════

async def _entrar(base, correo, clave=CLAVE):
    return await rutas_auth.login_with_password(
        pedido(), _RespuestaDeMentira(),
        LoginWithPasswordRequest(email=correo, password=clave))


async def _alta(base, **campos):
    campos.setdefault("user_id", "u_9")
    campos.setdefault("name", "Quien")
    campos.setdefault("role", "user")
    campos.setdefault("email_verified", True)
    campos.setdefault("password_set", True)
    campos["password_hash"] = hash_password(CLAVE)
    await base.users.insert_one(campos)


def test_un_baneado_no_vuelve_a_entrar(base):
    """El botón de banear escribe `is_banned`, y acá se miraba `status`."""
    async def cuerpo():
        await _alta(base, user_id="b1", email="ana@ejemplo.com", is_banned=True)
        with pytest.raises(Exception) as e:
            await _entrar(base, "ana@ejemplo.com")
        assert getattr(e.value, "status_code", None) == 403
        assert await base.user_sessions.count_documents({"user_id": "b1"}) == 0
    corre(cuerpo())


def test_un_borrado_no_vuelve_a_entrar(base):
    async def cuerpo():
        await _alta(base, user_id="b2", email="beto@ejemplo.com", is_deleted=True)
        with pytest.raises(Exception) as e:
            await _entrar(base, "beto@ejemplo.com")
        assert getattr(e.value, "status_code", None) == 401
        assert await base.user_sessions.count_documents({"user_id": "b2"}) == 0
    corre(cuerpo())


def test_un_correo_en_la_lista_negra_no_entra(base):
    """La lista negra se miraba sólo en el registro, y ahí no alcanza a una
    cuenta que ya existe."""
    async def cuerpo():
        await _alta(base, user_id="b3", email="carla@ejemplo.com")
        await base.blacklist.insert_one({"type": "email", "value": "carla@ejemplo.com"})
        with pytest.raises(Exception) as e:
            await _entrar(base, "carla@ejemplo.com")
        assert getattr(e.value, "status_code", None) == 403
        assert await base.user_sessions.count_documents({"user_id": "b3"}) == 0
    corre(cuerpo())


def test_una_cuenta_sana_sigue_entrando(base):
    """Que las cuatro guardas nuevas no hayan cerrado la puerta a todos."""
    async def cuerpo():
        await _alta(base, user_id="b4", email="dani@ejemplo.com")
        r = await _entrar(base, "dani@ejemplo.com")
        assert r.get("session_token")
        assert await base.user_sessions.count_documents({"user_id": "b4"}) == 1
    corre(cuerpo())


def test_lo_baneado_no_se_averigua_sin_la_contraseña(base):
    """Las guardas van DETRAS de la contraseña a propósito.

    Delante, cualquiera con una lista de correos averigua cuáles están
    baneados sin saber ninguna clave. Este test fija ese orden: con la
    contraseña equivocada, un baneado contesta lo mismo que cualquiera.
    """
    async def cuerpo():
        await _alta(base, user_id="b5", email="eva@ejemplo.com", is_banned=True)
        await _alta(base, user_id="b6", email="fran@ejemplo.com")
        with pytest.raises(Exception) as baneado:
            await _entrar(base, "eva@ejemplo.com", clave="NoEsLaClave!9")
        with pytest.raises(Exception) as sano:
            await _entrar(base, "fran@ejemplo.com", clave="NoEsLaClave!9")
        assert (getattr(baneado.value, "status_code", None),
                str(getattr(baneado.value, "detail", ""))) == \
               (getattr(sano.value, "status_code", None),
                str(getattr(sano.value, "detail", "")))
    corre(cuerpo())
