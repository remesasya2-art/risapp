"""Una consulta por pantalla, no una por fila.

QUE PASABA
    Las listas del panel muestran transacciones, y la transacción guarda el
    `user_id`, no el nombre. Para poner «Ana Ribeiro» al lado de cada fila se
    iba a buscar el usuario FILA POR FILA: diez pantallas hacían 1 + N
    consultas. Las recargas pendientes traen hasta mil filas.

    Y cinco de esas consultas pedían el usuario ENTERO para leerle el nombre:
    con el hash de la contraseña, la semilla del segundo factor, las
    credenciales de la huella y la suscripción de avisos adentro. No se
    filtraban a la pantalla —el código elige qué campos poner— pero viajaban
    por la red y quedaban en memoria del proceso.

    Tres pantallas más se habían escrito su propio diccionario de caché, las
    tres iguales y las tres sin proyección.

LO QUE SE PRUEBA ACA
    1. Que no quede ninguna consulta de usuarios adentro de un bucle.
    2. Que la lista de lo permitido sea una lista de lo PERMITIDO, y que no
       deje pasar nada de lo que no es de nadie más.
    3. Que el ayudante haga UNA consulta para muchas filas, contándolas.
    4. Que las dos colas sin tope ahora lo tengan.
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

from conftest import usar_base                                      # noqa: E402
from services import quien_es                                       # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_una_consulta"]
    usar_base(b)
    yield b


# ══════════════════════════════════════════════════════════════════════════
# 1. Que no vuelva a aparecer una consulta por fila
# ══════════════════════════════════════════════════════════════════════════

# Vacío, y así tiene que quedar. Acá estuvo `routes/adminbrl_bridge.py`, que
# era el único con el problema sin arreglar; ese puente se quitó del todo.
# Agregar un archivo a esta lista es decir «esta pantalla puede consultar fila
# por fila», y eso hay que justificarlo al lado.
FUERA: set[str] = set()


def _consultas_de_usuarios_en_bucles():
    hallazgos = []
    raiz = pathlib.Path(_BACKEND)
    for p in sorted(raiz.rglob("*.py")):
        rel = p.relative_to(raiz).as_posix()
        if rel.startswith(("tests/", "venv/", "migrations/", "scripts/")):
            continue
        if rel in FUERA:
            continue
        try:
            arbol = ast.parse(p.read_text())
        except SyntaxError:                                  # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.For, ast.AsyncFor)):
                continue
            for dentro in ast.walk(nodo):
                if not isinstance(dentro, ast.Await):
                    continue
                llamada = dentro.value
                if not isinstance(llamada, ast.Call):
                    continue
                f = llamada.func
                if not isinstance(f, ast.Attribute) or f.attr not in ("find", "find_one"):
                    continue
                if ast.unparse(f.value).endswith("users"):
                    hallazgos.append(f"{rel}:{dentro.lineno}  {ast.unparse(llamada)[:80]}")
    return hallazgos


def test_ninguna_pantalla_consulta_usuarios_fila_por_fila():
    """El test que hace que esto no se degrade solo.

    Recorre el código de verdad. Si alguien escribe una pantalla nueva y
    resuelve el nombre del cliente adentro del bucle, acá se pone rojo.
    """
    sueltas = _consultas_de_usuarios_en_bucles()
    assert not sueltas, (
        "Estas consultas a `users` están adentro de un bucle: una ida y "
        "vuelta a la base por cada fila de la pantalla.\n\n"
        + "\n".join(f"    {x}" for x in sueltas)
        + "\n\nUsá services/quien_es.py: junta los user_id y los trae en UNA "
          "consulta, con lista de lo permitido."
    )


def test_el_recorrido_no_esta_mirando_al_vacio():
    """Sin esto, el de arriba pasaría igual si el recorrido dejara de
    encontrar archivos: cero de cero es verde y no prueba nada."""
    raiz = pathlib.Path(_BACKEND)
    cuantos = sum(1 for p in raiz.rglob("*.py")
                  if not p.relative_to(raiz).as_posix().startswith(
                      ("tests/", "venv/", "migrations/", "scripts/")))
    assert cuantos >= 100, (
        f"El recorrido sólo vio {cuantos} archivos. Se rompió: el test de "
        f"arriba no está mirando lo que dice mirar.")


# ══════════════════════════════════════════════════════════════════════════
# 2. La lista de lo permitido
# ══════════════════════════════════════════════════════════════════════════

# Lo que la aplicación escribe en `users` y no tiene nada que hacer en una
# fila de una tabla. Salieron de recorrer las escrituras sobre esa colección:
# ninguno está inventado, porque un campo inventado hace pasar un test sin
# probar nada del producto.
LO_QUE_NO_VA_EN_UNA_FILA = [
    "password_hash", "two_factor_secret", "two_factor_secret_pending",
    "two_factor_backup_hashes", "pin_hash", "webauthn_credentials",
    "webauthn_auth_challenge", "webauthn_reg_challenge",
    "web_push_subscription", "push_token", "permissions", "legajo",
    "ban_reason", "rejection_reason", "drive_kyc_link", "original_email",
]


def test_la_lista_es_de_lo_permitido_y_no_de_lo_prohibido():
    """Un `0` en la proyección es una lista de lo prohibido disfrazada: deja
    pasar cada campo nuevo del usuario hasta que alguien se acuerde."""
    permitidos = {c: v for c, v in quien_es.LO_QUE_MUESTRA_UNA_FILA.items()
                  if c != "_id"}
    assert permitidos, "la lista quedó vacía"
    assert all(v == 1 for v in permitidos.values()), (
        "services/quien_es.py: LO_QUE_MUESTRA_UNA_FILA tiene un campo en 0. "
        "Tiene que decir qué SE muestra, no qué no.")


def test_nada_de_lo_que_no_es_de_nadie_mas_pasa_por_la_lista():
    for campo in LO_QUE_NO_VA_EN_UNA_FILA:
        assert campo not in quien_es.LO_QUE_MUESTRA_UNA_FILA, (
            f"«{campo}» entró en la lista de lo que muestra una fila. No es "
            f"algo que el panel necesite para escribir el nombre de alguien.")


def test_lo_que_llega_a_la_pantalla_son_solo_esos_campos(base):
    """Y que la proyección se aplique de verdad, no que sólo esté escrita."""
    async def cuerpo():
        await base.users.insert_one({
            "user_id": "u1", "name": "Ana", "email": "ana@ejemplo.com",
            "password_hash": "$2b$12$secreto",
            "two_factor_secret": "JBSWY3DPEHPK3PXP",
            "webauthn_credentials": [{"public_key": "AAA"}],
        })
        d = await quien_es.de_las_filas(base, [{"user_id": "u1"}])
        trajo = d.ya_conocido("u1")
        assert trajo.get("name") == "Ana"
        for campo in ("password_hash", "two_factor_secret", "webauthn_credentials"):
            assert campo not in trajo, f"«{campo}» llegó igual"
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. Que de verdad sea UNA consulta
# ══════════════════════════════════════════════════════════════════════════

class _BaseQueCuenta:
    """Envuelve la base y cuenta cuántas veces se le pregunta por usuarios."""

    def __init__(self, real):
        self._real = real
        self.consultas = 0

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    @property
    def users(self):
        cuenta = self

        class _Coleccion:
            def find(_, *a, **k):
                cuenta.consultas += 1
                return cuenta._real.users.find(*a, **k)

            def find_one(_, *a, **k):
                cuenta.consultas += 1
                return cuenta._real.users.find_one(*a, **k)

        return _Coleccion()


def test_cincuenta_filas_se_resuelven_con_una_sola_consulta(base):
    async def cuerpo():
        for i in range(50):
            await base.users.insert_one(
                {"user_id": f"u{i}", "name": f"Cliente {i}",
                 "email": f"c{i}@ejemplo.com"})
        filas = [{"user_id": f"u{i}"} for i in range(50)]

        contada = _BaseQueCuenta(base)
        d = await quien_es.de_las_filas(contada, filas)

        assert contada.consultas == 1, (
            f"cincuenta filas costaron {contada.consultas} consultas")
        assert d.ya_conocido("u7")["name"] == "Cliente 7"
        assert d.ya_conocido("u49")["email"] == "c49@ejemplo.com"
    corre(cuerpo())


def test_el_mismo_cliente_repetido_no_se_pregunta_dos_veces(base):
    async def cuerpo():
        await base.users.insert_one({"user_id": "u1", "name": "Ana"})
        contada = _BaseQueCuenta(base)
        d = quien_es.Directorio(contada)
        for _ in range(10):
            await d.de("u1")
        assert contada.consultas == 1, (
            f"el mismo cliente costó {contada.consultas} consultas")
    corre(cuerpo())


def test_un_cliente_que_ya_no_existe_tampoco_se_pregunta_dos_veces(base):
    """El caso que el diccionario a mano no cubría: si la consulta no lo trae,
    hay que ANOTAR que no está. Si no, se lo busca de nuevo cada vez."""
    async def cuerpo():
        contada = _BaseQueCuenta(base)
        d = quien_es.Directorio(contada)
        for _ in range(5):
            assert await d.de("borrado") == {}
        assert contada.consultas == 1, (
            f"un cliente inexistente costó {contada.consultas} consultas")
    corre(cuerpo())


def test_sin_filas_no_toca_la_base(base):
    async def cuerpo():
        contada = _BaseQueCuenta(base)
        await quien_es.de_las_filas(contada, [])
        assert contada.consultas == 0
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. Los dos topes que faltaban
# ══════════════════════════════════════════════════════════════════════════

def test_las_dos_colas_de_trabajo_tienen_tope():
    """Retiros pendientes y Diferencias de pago traían TODAS las filas.

    No las acota el historial sino el trabajo sin procesar: chicas mientras el
    equipo esté al día, sin techo el día que no lo esté.
    """
    from routes import admin as rutas_admin
    fuente = pathlib.Path(_BACKEND, "routes", "admin.py").read_text()

    assert rutas_admin.TOPE_DE_UNA_COLA > 0
    arbol = ast.parse(fuente)
    por_nombre = {n.name: n for n in ast.walk(arbol)
                  if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}

    for nombre in ("get_pending_withdrawals", "get_ordenes_revision_pago"):
        # Que exista se comprueba, no se asume: un `if no está: seguí` haría
        # pasar este test el día que alguien le cambie el nombre a la función,
        # que es justo cuando hay que mirarlo.
        assert nombre in por_nombre, (
            f"«{nombre}» ya no existe en routes/admin.py. Si se renombró, "
            f"corregí el nombre acá; si se borró, sacá esta línea a mano.")
        cuerpo = ast.unparse(por_nombre[nombre])
        assert "TOPE_DE_UNA_COLA" in cuerpo, (
            f"«{nombre}» perdió el tope: vuelve a traer todas las filas.")
