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

# Quién puede encender el segundo factor, y por qué cada uno.
#
# LA LISTA CRECIO, Y ESTA VEZ CON LAS PUERTAS DE SU LADO. Cuando este archivo
# se escribió, el alta desde el perfil estaba retirada: encendía la marca y el
# ingreso no la miraba, así que dejaba a la persona con una protección falsa y
# sin forma de apagarla. Volvió recién cuando las puertas empezaron a mirarla,
# que es lo que vigila la segunda guarda de más abajo. Una sin la otra es
# exactamente el agujero anterior.
QUIEN_PUEDE_ENCENDERLO = {
    # Corre en medio del login, con un token pendiente que el login mismo
    # emitió: por definición el ingreso ya sabe que esa cuenta lo va a usar.
    ("routes/security_2fa.py", "twofa_enroll_confirm"),
    # El camino del perfil, para quien lo activa porque quiere. Vale porque
    # `personal.pide_dos_pasos` hace que las puertas se lo pidan, y porque
    # Recursos Humanos puede reiniciárselo si pierde el teléfono.
    ("routes/security_2fa.py", "activar_dos_pasos_confirm"),
}

# Las puertas que emiten sesión SIN preguntar `pide_dos_pasos`, con el motivo.
#
# No alcanza con que el motivo exista: tiene que ser verdad. Cada una está
# comprobada, y si mañana deja de serlo, la puerta tiene que salir de acá y
# empezar a preguntar.
PUERTAS_EXENTAS = {
    ("routes/auth.py", "verify_email_code"):
        "Crea la cuenta en ese mismo pedido y rechaza un correo repetido, así "
        "que la sesión que emite es siempre de una cuenta nacida hace "
        "segundos: no pudo activar nada todavía.",
    ("routes/google_ingreso.py", "completar"):
        "Igual que el registro por correo: crea la cuenta en ese mismo pedido, "
        "así que la sesión que emite es de una cuenta nacida hace segundos y "
        "sin nada activado. Entrar con una cuenta de Google que YA EXISTE es "
        "otra función, `_entrar_a_la_cuenta`, y ésa sí pregunta la regla.",
    ("routes/security_2fa.py", "twofa_enroll_confirm"):
        "Es el alta misma: la persona acaba de escribir su primer código "
        "correcto. Pedírselo otra vez sería pedir dos.",
    ("routes/security_2fa.py", "twofa_verify"):
        "Es la puerta donde se escribe el código. Preguntar ahí si hay que "
        "pedirlo sería preguntarlo después de haberlo pedido.",
    ("routes/webauthn_login.py", "login_verify"):
        "La huella es posesión más biometría: ya son dos factores. Sumarle el "
        "código de seis dígitos es tres, y el costo es que la gente deje de "
        "usar la huella y vuelva a la contraseña sola, que es peor. Decisión "
        "tomada a propósito; si algún día se quiere revisar, se revisa acá.",
}

REGLA = "pide_dos_pasos"

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
                        encontradas.add((ruta.relative_to(_BACKEND).as_posix(), nodo.name))
    return encontradas


def _puertas_que_emiten_sesion():
    """`{(archivo, funcion)}` de todo lo que deja a alguien adentro.

    Dos formas, y hay que mirar las dos: llamar a `issue_session_token`, o
    insertar a mano en `user_sessions`. La segunda existe —el alta de cuenta
    arma la sesión ella misma— y una guarda que sólo mirara la primera la
    dejaría pasar.
    """
    emiten = set()
    for ruta in sorted(_BACKEND.rglob("*.py")):
        if set(ruta.relative_to(_BACKEND).parts) & {
                "tests", "scripts", "__pycache__", "venv"}:
            continue
        texto = ruta.read_text(encoding="utf-8")
        if "issue_session_token" not in texto and "user_sessions.insert_one" not in texto:
            continue
        try:
            arbol = ast.parse(texto)
        except SyntaxError:                                  # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # `issue_session_token` es la función que EMITE, no una puerta:
            # es el ayudante que todas las puertas llaman. Contarla sería
            # pedirle que se pregunte a sí misma si hay que pedir el código.
            if nodo.name == "issue_session_token":
                continue
            for hijo in ast.walk(nodo):
                if not isinstance(hijo, ast.Call):
                    continue
                f = hijo.func
                nombre = getattr(f, "id", None) or getattr(f, "attr", None)
                if nombre == "issue_session_token":
                    emiten.add((ruta.relative_to(_BACKEND).as_posix(), nodo.name))
                if (nombre == "insert_one" and isinstance(f, ast.Attribute)
                        and getattr(f.value, "attr", None) == "user_sessions"):
                    emiten.add((ruta.relative_to(_BACKEND).as_posix(), nodo.name))
    return emiten


def _pregunta_la_regla(archivo: str, funcion: str) -> bool:
    """Si esa función llama a `personal.pide_dos_pasos`.

    `archivo` es la ruta relativa —`routes/google_ingreso.py`— y no el nombre
    a secas. HAY DOS `google_ingreso.py` en el repositorio, uno en `routes` y
    otro en `services`, y buscar por nombre encontraba el que no era: el test
    daba rojo diciendo que la puerta no preguntaba la regla cuando sí lo
    hacía. Lo encontró esta misma guarda al estrenarse.
    """
    ruta = _BACKEND / archivo
    if not ruta.is_file():                                   # pragma: no cover
        return False
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and nodo.name == funcion):
            for hijo in ast.walk(nodo):
                if isinstance(hijo, ast.Call):
                    f = hijo.func
                    if (getattr(f, "id", None) or getattr(f, "attr", None)) == REGLA:
                        return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# 1. La guarda que importa
# ══════════════════════════════════════════════════════════════════════════

def test_TODA_PUERTA_QUE_EMITE_SESION_MIRA_LA_REGLA_O_DICE_POR_QUE_NO():
    """LA OTRA MITAD, y la que hace que encender el segundo factor sirva.

    Encenderlo no protege nada si la puerta por la que se entra no lo mira.
    Eso es exactamente lo que pasó la primera vez: había alta, no había
    puertas, y quedaba una protección que el ingreso ignoraba.

    Por eso esta guarda no pregunta «¿está bien?» sino «¿alguien lo pensó?».
    Una puerta nueva que emita sesión tiene dos salidas: preguntar la regla, o
    entrar en `PUERTAS_EXENTAS` con un motivo escrito. Las dos obligan a mirar
    el problema; ninguna se cumple sola.
    """
    sin_declarar = sorted(
        p for p in _puertas_que_emiten_sesion()
        if p not in PUERTAS_EXENTAS and not _pregunta_la_regla(*p))
    assert not sin_declarar, (
        f"{sin_declarar} emite(n) sesión sin preguntar `personal.{REGLA}` y sin "
        "motivo escrito.\n\n"
        "Una cuenta que activó el segundo factor y entra por ahí lo saltea: la "
        "protección queda de adorno. Si esa puerta de verdad no tiene que "
        "pedirlo, agregala a PUERTAS_EXENTAS con el motivo, y que el motivo "
        "sea cierto.")


def test_LOS_MOTIVOS_DE_LAS_EXENTAS_NO_PUEDEN_ESTAR_VACIOS():
    """Una exención sin motivo es una exención que nadie pensó."""
    for puerta, motivo in PUERTAS_EXENTAS.items():
        assert motivo and len(motivo) > 40, puerta


def test_LAS_PUERTAS_EXENTAS_EXISTEN_DE_VERDAD():
    """Una exención sobre una función que se renombró no exime nada, y encima
    tapa que la función nueva quedó sin declarar."""
    emiten = _puertas_que_emiten_sesion()
    fantasmas = sorted(p for p in PUERTAS_EXENTAS if p not in emiten)
    assert not fantasmas, f"{fantasmas} ya no emite(n) sesión: sacalas de PUERTAS_EXENTAS."



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
