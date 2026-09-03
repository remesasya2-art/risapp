"""
tests/test_ttl_de_sesiones.py — Las sesiones vencidas tienen que borrarse solas.

POR QUE ESTE ARCHIVO EXISTE

    En los logs de arranque de producción aparecía, en cada deploy:

        WARNING:routes.security_2fa:user_sessions TTL index: An equivalent
        index already exists with the same name but different options.
        Requested: { expires_at: 1, expireAfterSeconds: 2592000 }
        Existing:  { expires_at: 1 }
        code: 85, codeName: IndexOptionsConflict

    Dos lugares creaban el MISMO índice con el mismo nombre y distintas
    opciones: `server.py` sin TTL y `ensure_security_indexes()` con TTL de 30
    días. Como server.py corre antes, ganaba el suyo, y el de allá fallaba
    siempre. Resultado: las sesiones vencidas nunca se borraban y
    `user_sessions` crecía sin techo.

    NO era un problema de acceso: el vencimiento se comprueba al leer la
    sesión, en routes/dependencies.py, comparando `expires_at` en cada
    request. Una sesión vencida no entra aunque su documento siga ahí. Lo que
    crecía era la colección, no el riesgo.

    Y Mongo no cambia las opciones de un índice que ya existe: hay que tirarlo
    y rehacerlo. Por eso el arreglo no es sólo sacar la línea de server.py —
    eso deja el índice malo en la base para siempre— sino detectar el
    conflicto y rehacer el índice.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def _modulo():
    import routes.security_2fa as s2fa
    return s2fa


def test_sobre_una_base_limpia_el_indice_nace_con_TTL(base):
    async def caso():
        s2fa = _modulo()
        await s2fa._asegurar_ttl_de_sesiones()
        info = await base.user_sessions.index_information()
        assert "expires_at_1" in info, info
    corre(caso())


def test_SI_EL_INDICE_YA_EXISTE_SIN_TTL_SE_REHACE(base):
    """El caso de producción: el índice está, pero sin expireAfterSeconds."""
    async def caso():
        s2fa = _modulo()
        # El estado en el que quedó la base: mismo nombre, sin TTL.
        await base.user_sessions.create_index("expires_at", name="expires_at_1")

        llamadas = {"drop": 0}
        real_drop = base.user_sessions.drop_index

        # mongomock no levanta IndexOptionsConflict, así que se simula la
        # respuesta del servidor de verdad: es el error exacto que apareció en
        # los logs, con su código 85.
        from pymongo.errors import OperationFailure
        creados = []
        real_create = base.user_sessions.create_index

        # El estado va AFUERA del wrapper: mongomock devuelve un objeto de
        # colección nuevo en cada acceso a `base.user_sessions`, así que un
        # atributo de instancia se reinicia en cada llamada.
        estado = {"ya_fallo": False}

        class _Sesiones:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def create_index(s, clave, **kw):
                if not estado["ya_fallo"] and "expireAfterSeconds" in kw:
                    estado["ya_fallo"] = True
                    raise OperationFailure(
                        "An equivalent index already exists with the same name "
                        "but different options.", 85)
                creados.append(kw)
                return await real_create(clave, **kw)

            async def drop_index(s, nombre):
                llamadas["drop"] += 1
                return await real_drop(nombre)

        class _Base:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                real = getattr(s._real, n)
                return _Sesiones(real) if n == "user_sessions" else real

            def __getitem__(s, n):
                real = s._real[n]
                return _Sesiones(real) if n == "user_sessions" else real

        import database
        original = database.db
        try:
            s2fa.db = _Base(base)
            await s2fa._asegurar_ttl_de_sesiones()
        finally:
            s2fa.db = original

        assert llamadas["drop"] == 1, "no tiró el índice viejo"
        assert creados and creados[-1].get("expireAfterSeconds") == \
            s2fa.TTL_SESIONES_VENCIDAS, \
            f"lo rehizo sin TTL o con otro: {creados}"
    corre(caso())


def test_server_py_ya_no_crea_ese_indice_sin_TTL():
    """La causa raíz: dos lugares creando el mismo nombre con otras opciones.

    Si vuelve a aparecer en server.py, corre ANTES que
    ensure_security_indexes() y el conflicto vuelve.
    """
    import pathlib
    fuente = pathlib.Path(_BACKEND, "server.py").read_text()
    sin_comentarios = "\n".join(
        linea for linea in fuente.splitlines()
        if not linea.strip().startswith("#"))
    assert 'user_sessions.create_index("expires_at")' not in sin_comentarios, (
        "server.py volvió a crear user_sessions.expires_at sin TTL. Corre "
        "antes que ensure_security_indexes(), así que le gana el nombre y "
        "las sesiones vencidas dejan de borrarse.")


def test_el_vencimiento_no_depende_del_TTL():
    """Que se entienda por qué esto no era un agujero de seguridad.

    `get_current_user` compara `expires_at` en cada request. El TTL es
    limpieza; el control de acceso está en el código.
    """
    import ast
    import pathlib
    fuente = pathlib.Path(_BACKEND, "routes/dependencies.py").read_text()
    arbol = ast.parse(fuente)
    fn = next(n for n in arbol.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "get_current_user")
    cuerpo = ast.unparse(fn)
    # Que LEA el campo de la sesión, no que exista una variable con ese
    # nombre: `expires_at = None` deja la palabra en el cuerpo y no comprueba
    # nada. Y que además lo COMPARE contra la hora actual.
    assert "session.get('expires_at')" in cuerpo, \
        "get_current_user dejó de leer expires_at de la sesión: ahora el TTL " \
        "SÍ sería el único control, y una sesión vencida entraría hasta que " \
        "Mongo la borre"
    assert "datetime.now" in cuerpo, \
        "get_current_user lee expires_at pero ya no lo compara contra la hora"


def test_UN_ERROR_QUE_NO_SEA_EL_CONFLICTO_NO_TIRA_EL_INDICE(base):
    """Sólo el código 85 justifica rehacer el índice.

    Ante cualquier otro fallo —permisos, la base caída— tirar el índice sería
    empeorar las cosas: se pierde el que había y no se puede crear el nuevo.
    """
    async def caso():
        s2fa = _modulo()
        from pymongo.errors import OperationFailure

        llamadas = {"drop": 0}

        class _Sesiones:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def create_index(s, clave, **kw):
                raise OperationFailure("no autorizado", 13)   # Unauthorized

            async def drop_index(s, nombre):
                llamadas["drop"] += 1

        class _Base:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                real = getattr(s._real, n)
                return _Sesiones(real) if n == "user_sessions" else real

            def __getitem__(s, n):
                real = s._real[n]
                return _Sesiones(real) if n == "user_sessions" else real

        original = s2fa.db
        try:
            s2fa.db = _Base(base)
            await s2fa._asegurar_ttl_de_sesiones()     # no levanta
        finally:
            s2fa.db = original

        assert llamadas["drop"] == 0, \
            "tiró el índice por un error que no era el conflicto de opciones"
    corre(caso())
