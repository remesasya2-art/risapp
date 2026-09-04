"""
tests/test_sesiones_al_cambiar_clave.py — Que cambiar la contraseña eche al intruso.

EL DEFECTO QUE ESTE ARCHIVO FIJA

    Hay cuatro formas de cambiar una contraseña en esta aplicación:

        /auth/change-password      el usuario, desde adentro
        /auth/reset-password       con la contraseña temporal del correo
        /recovery/reset-password   con el código de recuperación
        /admin/reset-password      un administrador se la resetea a alguien

    Las cuatro escribían el `password_hash` nuevo y no tocaban nada más. Las
    sesiones abiertas seguían abiertas.

    Eso rompe la única defensa que una persona sabe usar sola. Alguien entra a
    una cuenta ajena, la dueña lo sospecha y hace lo que todo el mundo sabe
    hacer: cambia la contraseña. Y no pasa nada. El intruso sigue adentro, con
    la sesión que ya tenía, leyendo movimientos, beneficiarios y documentos.

    El caso del administrador era peor: nos avisan que una cuenta está tomada,
    la reseteamos, contestamos «listo, ya está» — y no estaba. Le dábamos a la
    persona una certeza falsa, que es peor que no darle ninguna.

POR QUE ESTO SE PRUEBA EN DOS NIVELES

    El comportamiento de una sesión no se ve mirando el código: la cookie
    sigue siendo la misma cadena, la pantalla sigue dibujando igual, y lo único
    que cambia es si una fila de `user_sessions` está o no está. Así que se
    prueba la función que la borra Y se barre el código para que ninguna forma
    nueva de cambiar una contraseña se olvide de llamarla.
"""
import ast
import asyncio
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

from conftest import usar_base                                      # noqa: E402
from services import sesiones                                       # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def con_sesiones(base, *usuarios):
    """Deja tres sesiones abiertas por usuario, como quien entró del teléfono,
    de la computadora, y del navegador que alguien más está usando."""
    async def cargar():
        for u in usuarios:
            for n in range(3):
                await base.user_sessions.insert_one(
                    {"user_id": u, "session_token": f"tok-{u}-{n}"})
    corre(cargar())


async def cuantas(base, user_id):
    return await base.user_sessions.count_documents({"user_id": user_id})


# ══════════════════════════════════════════════════════════════════════════
# 1. La función que cierra
# ══════════════════════════════════════════════════════════════════════════

def test_SE_CIERRAN_TODAS_LAS_SESIONES_DEL_USUARIO(base):
    con_sesiones(base, "ana", "beto")

    async def caso():
        cerradas = await sesiones.cerrar_todas(base, "ana", motivo="prueba")
        assert cerradas == 3
        assert await cuantas(base, "ana") == 0
    corre(caso())


def test_no_se_tocan_las_sesiones_de_otra_persona(base):
    """Una función que cierra de más deja a gente afuera sin motivo, y eso se
    lee como «la aplicación me echa sola»."""
    con_sesiones(base, "ana", "beto")

    async def caso():
        await sesiones.cerrar_todas(base, "ana")
        assert await cuantas(base, "beto") == 3
    corre(caso())


def test_LA_SESION_ACTUAL_SE_CONSERVA_CUANDO_SE_PIDE(base):
    """Cuando la persona cambia su propia contraseña estando adentro, echarla de
    la pantalla en la que está —justo después de hacer las cosas bien— se lee
    como un error de la aplicación."""
    con_sesiones(base, "ana")

    async def caso():
        cerradas = await sesiones.cerrar_todas(base, "ana", excepto="tok-ana-1")
        assert cerradas == 2
        quedan = await base.user_sessions.find({"user_id": "ana"}).to_list(10)
        assert [s["session_token"] for s in quedan] == ["tok-ana-1"]
    corre(caso())


def test_sin_excepto_no_sobrevive_ninguna(base):
    """El caso del administrador y el del reseteo por correo: no hay «sesión
    actual» que conservar, porque quien dispara el cambio no es quien tiene las
    sesiones abiertas."""
    con_sesiones(base, "ana")

    async def caso():
        await sesiones.cerrar_todas(base, "ana", excepto="")
        assert await cuantas(base, "ana") == 0
    corre(caso())


def test_un_usuario_sin_sesiones_no_es_un_error(base):
    async def caso():
        assert await sesiones.cerrar_todas(base, "nadie") == 0
    corre(caso())


@pytest.mark.parametrize("vacio", ["", None])
def test_sin_user_id_no_borra_nada(base, vacio):
    """Un `user_id` vacío con un filtro mal armado borraría sesiones ajenas. Se
    corta antes de llegar a la base."""
    con_sesiones(base, "ana", "beto")

    async def caso():
        assert await sesiones.cerrar_todas(base, vacio) == 0
        assert await cuantas(base, "ana") == 3
        assert await cuantas(base, "beto") == 3
    corre(caso())


def test_UN_USER_ID_NULO_NO_BARRE_LAS_SESIONES_HUERFANAS(base):
    """El caso que hace falta la guardia, y que este test no cubría al principio.

    Con la cadena vacía el filtro `{"user_id": ""}` no calza con nada, así que
    sacar la guardia no cambiaba nada y el mutante sobrevivía. Con `None` es
    distinto: en Mongo, `{"user_id": None}` calza también con los documentos que
    NO TIENEN el campo. Una fila de sesión vieja o a medio escribir se borraría
    sin que nadie lo haya pedido — y con ella, alguien se queda afuera sin
    entender por qué.
    """
    async def caso():
        await base.user_sessions.insert_one({"session_token": "sin-dueno"})
        await base.user_sessions.insert_one({"user_id": "ana", "session_token": "t"})

        assert await sesiones.cerrar_todas(base, None) == 0
        quedan = await base.user_sessions.find({}).to_list(10)
        assert {d["session_token"] for d in quedan} == {"sin-dueno", "t"}
    corre(caso())


def test_SI_LA_BASE_FALLA_NO_SE_CAE_EL_CAMBIO_DE_CONTRASENA(base):
    """Esto se llama justo después de guardar la contraseña nueva. Una excepción
    acá deja a la persona sin saber si el cambio se aplicó. Fallar cerrando
    sesiones es malo; fallar de una forma que hace dudar de si la contraseña
    cambió es peor."""
    class _Rota:
        async def delete_many(self, *a, **k):
            raise RuntimeError("la base no responde")

    class _Base(dict):
        def __getitem__(self, nombre):
            return _Rota()

    async def caso():
        assert await sesiones.cerrar_todas(_Base(), "ana") == 0
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. De dónde sale el identificador de la sesión actual
# ══════════════════════════════════════════════════════════════════════════

def _pedido(cookies=None, headers=None):
    class Req:
        pass
    Req.cookies = cookies or {}
    Req.headers = headers or {}
    return Req()


def test_el_token_se_busca_en_los_tres_lados_y_en_ese_orden():
    """El mismo orden que usa `get_current_user`. Si acá se buscara distinto, la
    sesión que se conserva no sería la de esta pantalla — se conservaría otra, y
    a la persona se la echaría igual."""
    assert sesiones.token_del_pedido(
        _pedido(cookies={"session_token": "de-la-cookie"},
                headers={"Authorization": "Bearer del-header"})) == "de-la-cookie"
    assert sesiones.token_del_pedido(
        _pedido(headers={"Authorization": "Bearer del-header",
                         "X-Session-ID": "del-otro"})) == "del-header"
    assert sesiones.token_del_pedido(
        _pedido(headers={"X-Session-ID": "del-otro"})) == "del-otro"


def test_sin_token_en_ningun_lado_devuelve_vacio():
    """Y vacío significa «cerrá todas», que es el lado seguro: ante la duda de
    cuál es la sesión actual, no se conserva ninguna."""
    assert sesiones.token_del_pedido(_pedido()) == ""
    assert sesiones.token_del_pedido(object()) == ""


def test_un_authorization_que_no_es_bearer_no_se_toma_como_token():
    assert sesiones.token_del_pedido(
        _pedido(headers={"Authorization": "Basic abc123"})) == ""


# ══════════════════════════════════════════════════════════════════════════
# 3. Que las CUATRO rutas la llamen — acá es donde esto vuelve
# ══════════════════════════════════════════════════════════════════════════

# Cada entrada: el archivo, la función que cambia la contraseña, y si tiene que
# conservar la sesión de quien la llama.
CAMINOS = [
    ("routes/auth.py", "reset_password", False),
    ("routes/auth.py", "change_password", True),
    ("routes/recovery.py", "reset_password", False),
    ("routes/admin.py", "admin_reset_password", False),
]


def _funcion(archivo, nombre):
    texto = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    arbol = ast.parse(texto)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre:
            return n, texto
    raise AssertionError(f"{archivo}: no se encontró {nombre}()")


@pytest.mark.parametrize("archivo, nombre, conserva", CAMINOS)
def test_CADA_CAMINO_CIERRA_LAS_SESIONES(archivo, nombre, conserva):
    fn, texto = _funcion(archivo, nombre)
    cuerpo = ast.get_source_segment(texto, fn) or ""
    assert "cerrar_todas" in cuerpo, (
        f"{archivo}:{nombre}() cambia la contraseña y deja las sesiones "
        "abiertas: cambiarla no echa a quien ya está adentro")


@pytest.mark.parametrize("archivo, nombre, conserva", CAMINOS)
def test_solo_el_cambio_propio_conserva_una_sesion(archivo, nombre, conserva):
    """Los tres caminos de reseteo NO pueden conservar ninguna: quien resetea
    desde el correo no está adentro, y el administrador no es el dueño de esas
    sesiones. Pasarles un `excepto` cerraría todas menos la del intruso."""
    fn, texto = _funcion(archivo, nombre)
    cuerpo = ast.get_source_segment(texto, fn) or ""
    usa_excepto = "excepto=" in cuerpo
    assert usa_excepto == conserva, (
        f"{archivo}:{nombre}() " +
        ("tendría que conservar la sesión de quien hace el cambio"
         if conserva else
         "no puede conservar ninguna sesión: quien dispara el cambio no es "
         "quien las tiene abiertas"))


def test_NINGUNA_RUTA_NUEVA_CAMBIA_UNA_CONTRASENA_SIN_CERRAR_SESIONES():
    """El barrido. No enumera las cuatro de arriba: busca CUALQUIER función que
    escriba un `password_hash` y exige que cierre sesiones.

    El alta de una cuenta queda afuera —no hay sesiones previas que cerrar— y se
    reconoce porque el usuario todavía no existe.
    """
    permitidas = {
        # Alta de una cuenta nueva: el usuario todavía no existe, no hay
        # sesiones anteriores que cerrar.
        ("routes/auth.py", "register_user"),
        ("routes/auth.py", "verify_email_code"),
    }
    # El alta del personal (`_activar`) NO está permitida, y vale contar por qué:
    # este barrido la encontró y la lista escrita a mano no la tenía. Lo normal
    # es que no haya sesiones —la cuenta existía como invitación y sin
    # contraseña no se podía entrar— pero si a alguien del personal le REINVITAN
    # la cuenta porque se la tomaron, ahí sí hay una sesión viva, y es una con
    # permisos de administración. Cierra sesiones como las otras cuatro.
    huerfanas = []
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for archivo in sorted(os.listdir(raiz)):
            if not archivo.endswith(".py"):
                continue
            rel = f"{carpeta}/{archivo}"
            texto = open(os.path.join(raiz, archivo), encoding="utf-8").read()
            try:
                arbol = ast.parse(texto)
            except SyntaxError:                           # pragma: no cover
                continue
            for fn in ast.walk(arbol):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                cuerpo = ast.get_source_segment(texto, fn) or ""
                # ¿Escribe una contraseña? `hash_password(...)` o bcrypt directo
                # asignados a la clave `password_hash`.
                escribe = ('"password_hash":' in cuerpo
                           and ("hash_password(" in cuerpo or "bcrypt.hashpw" in cuerpo
                                or "hashed" in cuerpo))
                if not escribe:
                    continue
                if (rel, fn.name) in permitidas:
                    continue
                if "cerrar_todas" not in cuerpo:
                    huerfanas.append(f"{rel}:{fn.lineno} {fn.name}()")

    assert not huerfanas, (
        "estas funciones cambian una contraseña y no cierran las sesiones "
        "abiertas, así que cambiarla no echa a quien ya está adentro:\n  "
        + "\n  ".join(huerfanas)
        + "\n\nLlamá a services/sesiones.cerrar_todas(), o agregala a la lista "
          "de permitidas con el motivo.")


def test_el_barrido_encuentra_algo():
    """Si el barrido de arriba no ve ninguna función que escriba contraseñas,
    pasa sin haber mirado nada. Es la forma en que un test de barrido miente."""
    encontradas = 0
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for archivo in sorted(os.listdir(raiz)):
            if not archivo.endswith(".py"):
                continue
            texto = open(os.path.join(raiz, archivo), encoding="utf-8").read()
            encontradas += texto.count('"password_hash":')
    assert encontradas >= 6, f"el barrido sólo vio {encontradas} escrituras"
