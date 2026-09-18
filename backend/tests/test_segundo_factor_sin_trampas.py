"""El segundo factor no se enciende por una puerta que el ingreso no mira.

QUE PASABA

    Había DOS altas del segundo factor en el backend:

      · `enroll-init` / `enroll-confirm`, que corren DURANTE el login con un
        token pendiente. Es el camino del personal, y funciona.
      · `setup-init` / `setup-confirm`, que corrían con la sesión ya abierta
        y sólo exigían estar logueado. O sea que cualquier cliente podía
        encenderlo.

    Y las puertas de entrada NO miran esa marca cuando la cuenta es un
    cliente: la exigen sólo al personal y a los administradores. Así que el
    segundo camino dejaba a una persona con el segundo factor «activado»,
    la ruta de estado se lo confirmaba, el ingreso lo ignoraba, y encima no
    podía apagarlo sin un código del teléfono.

    No lo llamaba ninguna pantalla, así que era una trampa puesta y no un
    agujero abierto. Se retiró.

LO QUE SE PRUEBA, Y POR QUE ASI

    La guarda que importa no es «esas dos rutas no están»: es que NINGUNA
    ruta encienda la marca sin que el ingreso la exija. Eso se vigila por la
    FORMA, recorriendo el árbol: quién escribe `two_factor_enabled: True`.

    El día que alguien quiera ofrecerle el segundo factor al cliente de
    verdad, esto se pone rojo y lo obliga a mirar las tres puertas antes de
    agregar el alta. Es justamente la conversación que no hubo la primera vez.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                      # noqa: E402
from routes import security_2fa                                     # noqa: E402
from services import personal                                       # noqa: E402

# La ÚNICA función que puede encender el segundo factor, y el motivo: corre
# en medio del login, con un token pendiente que el login mismo emitió, así
# que por definición el ingreso ya sabe que esa cuenta lo tiene que usar.
QUIEN_PUEDE_ENCENDERLO = {("security_2fa.py", "twofa_enroll_confirm")}

MARCA = "two_factor_enabled"


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_2fa"]
    usar_base(b)
    yield b


def _quien_enciende_la_marca():
    """`{(archivo, funcion)}` de todo lo que escribe `two_factor_enabled: True`.

    Se usa el árbol y no una búsqueda de texto por dos motivos. Hace falta
    saber en qué FUNCION cae cada escritura, porque un archivo puede tener
    varias. Y hay que distinguir ENCENDERLA de apagarla o de leerla: `disable`
    escribe la misma clave con `False`, y la ruta de estado sólo la lee.
    """
    encontradas = set()
    for ruta in sorted(_BACKEND.rglob("*.py")):
        if set(ruta.relative_to(_BACKEND).parts) & {
                "tests", "scripts", "__pycache__", "venv"}:
            continue
        texto = ruta.read_text(encoding="utf-8")
        if MARCA not in texto:
            continue
        try:
            arbol = ast.parse(texto)
        except SyntaxError:                                  # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for hijo in ast.walk(nodo):
                if not isinstance(hijo, ast.Dict):
                    continue
                for k, v in zip(hijo.keys, hijo.values):
                    if (isinstance(k, ast.Constant) and k.value == MARCA
                            and isinstance(v, ast.Constant) and v.value is True):
                        encontradas.add((ruta.name, nodo.name))
    return encontradas


# ══════════════════════════════════════════════════════════════════════════
# 1. La guarda que importa
# ══════════════════════════════════════════════════════════════════════════

def test_SOLO_EL_ALTA_DEL_LOGIN_PUEDE_ENCENDER_EL_SEGUNDO_FACTOR():
    """LA GUARDA. Quien agregue otra forma de encenderlo se encuentra con
    este rojo y con el motivo."""
    de_mas = _quien_enciende_la_marca() - QUIEN_PUEDE_ENCENDERLO
    assert not de_mas, (
        f"{sorted(de_mas)} enciende(n) {MARCA!r} y no es el alta del login.\n\n"
        "Las puertas de entrada NO exigen el segundo factor a un cliente: lo "
        "exigen sólo al personal y a los administradores. Una cuenta que lo "
        "enciende por otro camino queda con una protección que el ingreso "
        "ignora, y que no puede apagar sin un código del teléfono.\n\n"
        "Si querés ofrecérselo al cliente de verdad, hacen falta tres cosas "
        "ANTES de esto: que las tres puertas respeten la marca, que la regla "
        "siga viviendo sólo en services/personal.py, y que un super "
        "administrador pueda apagárselo a quien perdió el teléfono. Ver la "
        "sección 11 del dossier de seguridad.")


def test_EL_BUSCADOR_DE_QUIEN_LA_ENCIENDE_SIRVE():
    """Un buscador que no encuentra nada deja el test de arriba en verde para
    siempre. Tiene que ver el alta que SI existe."""
    assert _quien_enciende_la_marca() == QUIEN_PUEDE_ENCENDERLO


def test_EL_BUSCADOR_NO_CONFUNDE_APAGARLA_CON_ENCENDERLA():
    """`disable` escribe la misma clave con `False`. Si el buscador la
    contara, habría que poner una excepción falsa, y una lista de excepciones
    con entradas falsas adentro deja de decir nada."""
    quienes = {f for _, f in _quien_enciende_la_marca()}
    assert "twofa_disable" not in quienes
    assert "twofa_status" not in quienes, "leerla no es encenderla"


def test_LAS_DOS_RUTAS_HUERFANAS_NO_VOLVIERON():
    fuente = (_BACKEND / "routes" / "security_2fa.py").read_text(encoding="utf-8")
    assert '"/setup-init"' not in fuente
    assert '"/setup-confirm"' not in fuente
    assert not hasattr(security_2fa, "twofa_setup_init")
    assert not hasattr(security_2fa, "twofa_setup_confirm")
    # Y el motivo queda escrito donde estaban, para que nadie las reponga
    # creyendo que faltaba una pantalla.
    assert "ACA VIVIAN" in fuente and "no protege" in fuente


def test_EL_ALTA_DEL_LOGIN_SIGUE_EN_PIE():
    """Retirar una cosa no puede llevarse la que sí se usa: el personal se da
    de alta por acá y sin esto no entra nadie del equipo."""
    from routes import api_router
    caminos = {getattr(r, "path", "") for r in api_router.routes}
    assert "/api/auth/2fa/enroll-init" in caminos
    assert "/api/auth/2fa/enroll-confirm" in caminos
    assert "/api/auth/2fa/verify" in caminos
    assert "/api/auth/2fa/disable" in caminos, "la salida no se toca"


# ══════════════════════════════════════════════════════════════════════════
# 2. La regla vive en un solo lugar
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta,obligatorio", [
    ({"role": "user"}, False),
    ({"role": "user", "es_personal": True}, True),
    ({"role": "agent"}, True),
    ({"role": "admin"}, True),
    ({"role": "super_admin"}, True),
])
def test_LA_RUTA_DE_ESTADO_CONTESTA_LO_QUE_EXIGE_EL_INGRESO(base, cuenta, obligatorio):
    """Acá decía `role == super_admin` por su cuenta, y a un `admin` o a un
    `agent` le contestaba que no era obligatorio justo antes de que el login
    se lo exigiera. Dos respuestas para la misma pregunta."""
    from models.user import User
    doc = {"user_id": "u1", "email": "a@ejemplo.com", "name": "A", **cuenta}
    corre(base.users.insert_one(dict(doc)))
    r = corre(security_2fa.twofa_status(User(**doc)))
    assert r["is_required"] is obligatorio
    assert r["is_required"] == personal.exige_dos_pasos(doc), \
        "la ruta de estado y la definición única tienen que coincidir siempre"


def test_LA_RUTA_DE_ESTADO_NO_REIMPLEMENTA_LA_REGLA():
    """Por la forma, no por el resultado: coincidir hoy por casualidad no
    impide que se separen mañana."""
    import inspect
    fuente = inspect.getsource(security_2fa.twofa_status)
    assert "exige_dos_pasos" in fuente
    assert "SUPER_ADMIN_ROLE" not in fuente, \
        "volvió a decidir por su cuenta quién necesita dos pasos"


# ══════════════════════════════════════════════════════════════════════════
# 3. Las tres puertas siguen mirando la misma fuente
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo", ["auth.py", "google_ingreso.py", "webauthn_login.py"])
def test_CADA_PUERTA_DECIDE_CON_LA_DEFINICION_UNICA(archivo):
    """Tres puertas emiten sesión mirando si la cuenta necesita dos pasos. Si
    una se escribe su propia regla, se separan sin que nadie lo note: es lo
    que ya pasó con las cinco listas de lo prohibido."""
    fuente = (_BACKEND / "routes" / archivo).read_text(encoding="utf-8")
    assert "exige_dos_pasos" in fuente, f"{archivo} dejó de usar la regla única"
