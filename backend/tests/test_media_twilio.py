"""
tests/test_media_twilio.py — El proxy que va a Twilio con nuestras credenciales.

QUE PROTEGE

    Las fotos que llegan por WhatsApp viven en Twilio y hay que autenticarse
    para bajarlas. El navegador no puede, así que el servidor va a buscarlas.
    Eso convierte a esta ruta en la única de la aplicación que hace un pedido
    saliente CON NUESTRO USUARIO Y CONTRASEÑA de Twilio, hacia una dirección que
    arma con lo que le mandan.

    La versión anterior pegaba el path recibido a la URL sin mirarlo:

        twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{path}"

    `path:path` de FastAPI se traga las barras, así que el pedido lo escribía
    entero quien llamaba. Cualquiera con sesión podía pedir

        /api/media/twilio/AC…/Messages.json

    y recibir los cuerpos de TODOS los SMS de la cuenta — que es donde viajan
    los códigos de verificación que la aplicación le manda a la gente.

    La segunda copia del mismo pedido, en la migración de `admin.py`, decidía a
    dónde ir con `"api.twilio.com" in url`: una subcadena, no un dominio. Y el
    valor salía de `proof_image`, que era texto libre elegido por el usuario.

LO QUE SE PRUEBA

    Que sólo pase la forma exacta de un medio, de NUESTRA cuenta; que un salto
    no lleve las credenciales a otro dominio; y que las dos entradas —la ruta y
    la migración— usen el mismo criterio, porque tener dos era el problema.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

AC = "AC" + "a" * 32
MM = "MM" + "b" * 32
ME = "ME" + "c" * 32
MEDIO = f"{AC}/Messages/{MM}/Media/{ME}"


@pytest.fixture
def media(monkeypatch):
    """El módulo con una cuenta puesta. El SID se lee al importar, así que se
    pisa el atributo del módulo, no la variable de entorno."""
    import routes.media as m
    monkeypatch.setattr(m, "TWILIO_ACCOUNT_SID", AC)
    monkeypatch.setattr(m, "TWILIO_AUTH_TOKEN", "token-secreto")
    return m


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que no se puede pedir
# ══════════════════════════════════════════════════════════════════════════

# Cada uno es una parte distinta de la API de Twilio, alcanzable con la ruta
# vieja porque el path se pegaba entero.
ABUSOS = [
    f"{AC}/Messages.json",
    f"{AC}/Recordings.json",
    f"{AC}/IncomingPhoneNumbers.json",
    f"{AC}/Calls.json",
    f"{AC}.json",
    f"{AC}/Messages/{MM}/Media/{ME}/../../../Messages.json",
    f"{AC}/Messages/{MM}/Media/{ME}.json",
    f"{AC}/Messages/{MM}/Media/{ME}?PageSize=1000",
    "",
    "/",
    "../../Accounts.json",
]


@pytest.mark.parametrize("path", ABUSOS)
def test_NO_SE_PUEDE_PEDIR_OTRA_COSA_QUE_UN_MEDIO(media, path):
    """El ancla del final del patrón es la mitad importante: sin ella,
    «…/Media/ME…/../../Messages.json» empieza igual que un medio válido."""
    assert media.FORMA_DEL_MEDIO.match(path) is None, path


def test_un_medio_de_OTRA_cuenta_de_twilio_no_se_pide(media):
    """Aunque la forma calce. Si no es nuestra cuenta, no tenemos por qué
    ponerle nuestras credenciales al pedido."""
    otra = "AC" + "9" * 32
    assert media.url_de_medio(f"/api/media/twilio/{otra}/Messages/{MM}/Media/{ME}") is None


def test_el_medio_valido_si_se_pide(media):
    assert media.url_de_medio(f"/api/media/twilio/{MEDIO}") == \
        f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"
    assert media.url_de_medio(
        f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}") == \
        f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"


# ══════════════════════════════════════════════════════════════════════════
# 2. La subcadena que dejaba salir las credenciales
# ══════════════════════════════════════════════════════════════════════════

# La migración de `admin.py` decidía con `"api.twilio.com" in url`. Estas URLs
# la pasan todas, y ese pedido salía con nuestro usuario y contraseña adentro.
DISFRACES = [
    "https://cualquier-cosa.example/?x=api.twilio.com",
    "https://api.twilio.com.evil.example/2010-04-01/Accounts/" + MEDIO,
    "https://evil.example/api.twilio.com/2010-04-01/Accounts/" + MEDIO,
    "http://api.twilio.com/2010-04-01/Accounts/" + MEDIO,       # sin TLS
    "https://api.twilio.com@evil.example/x",
    "//api.twilio.com/2010-04-01/Accounts/" + MEDIO,
]


@pytest.mark.parametrize("url", DISFRACES)
def test_UNA_URL_QUE_SOLO_CONTIENE_EL_DOMINIO_NO_ALCANZA(media, url):
    assert "api.twilio.com" in url            # pasaba el chequeo viejo
    assert media.url_de_medio(url) is None    # no pasa el nuevo


@pytest.mark.parametrize("valor", [None, "", 12, [], "data:image/png;base64,AAA",
                                   "javascript:alert(1)", "/api/media/twilio/"])
def test_lo_que_no_es_un_medio_no_dispara_ningun_pedido(media, valor):
    assert media.url_de_medio(valor) is None


# ══════════════════════════════════════════════════════════════════════════
# 3. El salto al CDN
# ══════════════════════════════════════════════════════════════════════════

class _Respuesta:
    def __init__(self, status_code=200, headers=None, content=b"bytes"):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


class _Cliente:
    """Anota cada pedido: a dónde fue y con qué credenciales."""
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.pedidos = []

    async def get(self, url, auth=None, follow_redirects=None, timeout=None):
        self.pedidos.append({"url": url, "auth": auth,
                             "follow_redirects": follow_redirects})
        return self._respuestas.pop(0)


def corre(coro):
    import asyncio
    return asyncio.run(coro)


def test_EL_SALTO_NO_SE_SIGUE_CON_LAS_CREDENCIALES_PUESTAS(media):
    """Twilio contesta con un salto al CDN. Seguirlo con la cabecera puesta es
    entregarle nuestro usuario y contraseña a donde apunte el `Location`."""
    cliente = _Cliente([
        _Respuesta(307, {"location": "https://media.twiliocdn.com/x.jpg"}),
        _Respuesta(200, {"content-type": "image/jpeg"}, b"foto"),
    ])
    resultado = corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"))

    assert resultado == (b"foto", "image/jpeg")
    assert cliente.pedidos[0]["auth"] == (AC, "token-secreto")
    assert cliente.pedidos[1]["auth"] is None, \
        "el segundo pedido salió con las credenciales de Twilio adentro"


def test_httpx_nunca_sigue_saltos_por_su_cuenta(media):
    """`follow_redirects=True` deja la decisión en manos de la respuesta del
    otro lado. Los dos pedidos tienen que salir con eso apagado."""
    cliente = _Cliente([
        _Respuesta(302, {"location": "https://media.twiliocdn.com/x.jpg"}),
        _Respuesta(200, {"content-type": "image/jpeg"}, b"foto"),
    ])
    corre(media.bajar_medio(cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"))
    assert all(p["follow_redirects"] is False for p in cliente.pedidos)


SALTOS_MALOS = [
    "https://evil.example/x.jpg",
    "http://media.twiliocdn.com/x.jpg",              # sin TLS
    "https://evil-twiliocdn.com/x.jpg",              # el sufijo sin el punto
    "https://twiliocdn.com.evil.example/x.jpg",
    "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/",      # metadatos de la nube
    "",
]


@pytest.mark.parametrize("destino", SALTOS_MALOS)
def test_un_salto_a_otro_lado_corta_el_pedido(media, destino):
    cliente = _Cliente([_Respuesta(307, {"location": destino})])
    assert corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}")) is None
    assert len(cliente.pedidos) == 1, "siguió el salto igual"


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que vuelve
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_RESPUESTA_ENORME_NO_ENTRA(media):
    """Sin tope, la respuesta de un tercero decide cuánta memoria usa este
    proceso."""
    cliente = _Cliente([_Respuesta(200, {"content-type": "image/jpeg"},
                                   b"x" * (media.TOPE_BYTES + 1))])
    assert corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}")) is None


@pytest.mark.parametrize("tipo", ["text/html", "image/svg+xml", "application/javascript",
                                  "text/html; charset=utf-8", ""])
def test_UN_TIPO_QUE_EJECUTA_SE_MANDA_COMO_DESCARGA(media, tipo):
    """El `content-type` lo elige el otro lado, y con él el navegador decide
    cómo interpretar estos bytes. Un `text/html` servido desde nuestra ruta es
    una página que corre en NUESTRO origen."""
    cliente = _Cliente([_Respuesta(200, {"content-type": tipo}, b"<script>")])
    contenido, devuelto = corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"))
    assert devuelto == "application/octet-stream", tipo


def test_una_imagen_de_verdad_conserva_su_tipo(media):
    cliente = _Cliente([_Respuesta(200, {"content-type": "image/png"}, b"\x89PNG")])
    assert corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}"))[1] == "image/png"


def test_un_error_de_twilio_no_devuelve_la_respuesta_de_error(media):
    cliente = _Cliente([_Respuesta(404, {"content-type": "application/json"},
                                   b'{"message":"not found"}')])
    assert corre(media.bajar_medio(
        cliente, f"https://api.twilio.com/2010-04-01/Accounts/{MEDIO}")) is None


# ══════════════════════════════════════════════════════════════════════════
# 5. Que no vuelva a haber dos criterios
# ══════════════════════════════════════════════════════════════════════════

# Los tres barridos de abajo miran el ARBOL del código, no el texto. Un grep
# encuentra `follow_redirects=True` adentro del comentario que explica por qué
# ya no se usa, y ahí el test empieza a pedir que no se escriba la explicación.


def _arboles():
    """Cada archivo de `routes/`, ya parseado."""
    import ast
    rutas = os.path.join(_BACKEND, "routes")
    for archivo in sorted(os.listdir(rutas)):
        if not archivo.endswith(".py"):
            continue
        texto = open(os.path.join(rutas, archivo), encoding="utf-8").read()
        yield f"routes/{archivo}", texto, ast.parse(texto)


def test_LA_MIGRACION_USA_EL_MISMO_CRITERIO_QUE_LA_RUTA():
    """El agujero de `admin.py` no fue un descuido puntual: fue tener el mismo
    pedido escrito dos veces, y arreglar sólo uno."""
    fuente = open(os.path.join(_BACKEND, "routes", "admin.py"), encoding="utf-8").read()
    assert "url_de_medio" in fuente and "bajar_medio" in fuente


def test_NADIE_DECIDE_A_DONDE_IR_CON_UNA_SUBCADENA():
    """`"api.twilio.com" in url` acepta `https://evil.example/?x=api.twilio.com`.
    Un dominio se compara como dominio, no como pedazo de texto."""
    import ast
    sospechosos = []
    for nombre, _, arbol in _arboles():
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Compare):
                continue
            if not any(isinstance(op, ast.In) for op in nodo.ops):
                continue
            izq = nodo.left
            if isinstance(izq, ast.Constant) and isinstance(izq.value, str) \
                    and "twilio.com" in izq.value:
                sospechosos.append(f"{nombre}:{nodo.lineno}  {izq.value!r} in …")
    assert not sospechosos, (
        "se decide un destino por subcadena. Usá routes/media.py:\n  "
        + "\n  ".join(sospechosos))


def test_NADIE_MAS_ARMA_UNA_URL_DE_TWILIO_A_MANO():
    """Si aparece un tercer lugar que pega un valor a la URL de Twilio, este
    test lo muestra antes de que salga a producción."""
    import ast
    sospechosos = []
    for nombre, _, arbol in _arboles():
        if nombre == "routes/media.py":
            continue
        for nodo in ast.walk(arbol):
            # Un f-string o una suma cuyo texto fijo nombra a Twilio.
            if isinstance(nodo, ast.JoinedStr):
                fijo = "".join(v.value for v in nodo.values
                               if isinstance(v, ast.Constant) and isinstance(v.value, str))
            elif isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
                fijo = "".join(x.value for x in (nodo.left, nodo.right)
                               if isinstance(x, ast.Constant) and isinstance(x.value, str))
            else:
                continue
            if "api.twilio.com" in fijo:
                sospechosos.append(f"{nombre}:{nodo.lineno}")
    assert not sospechosos, (
        "una ruta arma la URL de Twilio a mano. Usá routes/media.py: "
        + ", ".join(sospechosos))


def test_ningun_pedido_a_twilio_sale_siguiendo_saltos_solo():
    """`follow_redirects=True` en un pedido autenticado deja que la respuesta
    del otro lado decida a dónde va nuestra cabecera de credenciales."""
    import ast
    sospechosos = []
    for nombre, texto, arbol in _arboles():
        if "TWILIO_AUTH_TOKEN" not in texto:
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            for kw in nodo.keywords:
                if kw.arg == "follow_redirects" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value is True:
                    sospechosos.append(f"{nombre}:{nodo.lineno}")
    assert not sospechosos, (
        "un archivo que tiene las credenciales de Twilio sigue saltos solo: "
        + ", ".join(sospechosos))
