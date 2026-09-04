"""
tests/test_url_de_archivo.py — Que un comprobante no pueda ejecutar código.

QUE PROTEGE

    Los comprobantes, los documentos del KYC y los adjuntos del chat llegan
    como TEXTO. La pantalla los usaba tal cual:

        <a href={usuario.id_document_image} target="_blank">
        onClick={() => window.open(tx.proof_image, '_blank')}

    Un `href` o un `window.open` con `javascript:...` no abre nada: ejecuta ese
    código en el origen de la página, con la sesión de quien hizo click. Y quien
    hace click en estos campos es un administrador — el que aprueba KYCs y mueve
    plata. El que sube el archivo elige el texto; el que lo abre es el que puede
    todo. Es el peor par posible.

    La cookie de sesión es httpOnly, así que ese código no puede robársela. No
    la necesita: ya está corriendo adentro de la sesión y puede pedirle a la API
    lo mismo que puede pedir quien está mirando.

DOS COSAS DISTINTAS SE PRUEBAN ACA

    1. Que el filtro funcione. La lógica vive en
       `frontend/src/utils/urlDeArchivo.js`, sin React y sin red, y acá se
       EJECUTA con node contra los bypass conocidos.

    2. Que se USE en todos lados. Un filtro correcto que la próxima pantalla no
       llama no protege nada, y esa es la forma en que este agujero vuelve. El
       último bloque recorre el código buscando `href={...}` y `window.open(...)`
       sin pasar por el filtro.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RAIZ = os.path.dirname(_BACKEND)
_FRONT = os.path.join(_RAIZ, "frontend", "src")

MODULO = os.path.join(_FRONT, "utils", "urlDeArchivo.js")

_node = shutil.which("node")


def js(expresion):
    if not _node:
        pytest.skip("node no está instalado: el filtro no se puede correr")
    codigo = (
        f"import * as m from {json.dumps('file://' + MODULO)};\n"
        f"console.log(JSON.stringify(({expresion})));\n"
    )
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise AssertionError(f"node falló:\n{r.stderr}")
    return json.loads(r.stdout)


def segura(valor):
    return js(f"m.urlDeArchivoSegura({json.dumps(valor)})")


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que tiene que rechazar
# ══════════════════════════════════════════════════════════════════════════

# Cada uno es un bypass conocido de los filtros que buscan la palabra
# `javascript`. Los navegadores ignoran espacios y caracteres de control antes
# y DENTRO del esquema, así que la palabra completa casi nunca aparece.
BYPASSES = [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "  javascript:alert(1)",
    "\tjavascript:alert(1)",
    "\njavascript:alert(1)",
    "java\tscript:alert(1)",              # tabulador en medio del esquema
    "java\nscript:alert(1)",
    "java\rscript:alert(1)",
    "java\x00script:alert(1)",            # NUL en medio del esquema
    "jav\x09ascript:alert(1)",
    "javascript\x3aalert(1)",             # los dos puntos escapados
    "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "file:///etc/passwd",
    "about:blank",
]


@pytest.mark.parametrize("valor", BYPASSES)
def test_NADA_QUE_EJECUTE_CODIGO_PASA(valor):
    assert segura(valor) is None, f"pasó: {valor!r}"


def test_LO_QUE_PROTEGE_ES_LA_LISTA_no_la_limpieza_de_caracteres():
    """Vale la pena que quede escrito para no confundirse al leer el módulo.

    `normalizar()` saca espacios y caracteres de control, y el comentario que
    tenía sugería que eso era lo que frenaba a «java<TAB>script:». No lo es: se
    reemplazó esa línea por un `trim()` pelado y NINGUN bypass de la lista de
    arriba pasó igual. Caen todos por lo mismo — no empiezan con `/`, ni con
    `https://`, ni con `data:image/`, ni con `blob:`.

    Este test fija esa propiedad directamente: cualquier cosa con un esquema
    que no está en la lista se rechaza, tenga o no caracteres raros.
    """
    for esquema in ["javascript", "vbscript", "file", "about", "chrome",
                    "ms-msdt", "intent", "jar", "livescript", "mocha"]:
        assert segura(f"{esquema}:loquesea") is None, esquema


def test_UN_SVG_NO_PASA_AUNQUE_DIGA_IMAGE():
    """`data:image/svg+xml` es una imagen para el `Content-Type` y un documento
    con scripts adentro para el navegador. En un `<embed>` o abierto en una
    pestaña, ese script corre."""
    assert segura("data:image/svg+xml;base64,PHN2Zz48c2NyaXB0Lz48L3N2Zz4=") is None
    assert segura("data:image/svg+xml,<svg onload=alert(1)>") is None


def test_una_direccion_protocolo_relativa_no_pasa():
    """`//otro-sitio.com/x.png` no es una ruta nuestra: es otro sitio con
    nuestro mismo protocolo. En un `<a href>` manda a quien hace click afuera."""
    assert segura("//evil.example/a.png") is None
    assert segura("\\\\evil.example\\a.png") is None


@pytest.mark.parametrize("valor", [None, "", "   ", "\t\n", 0, 12, [], {}, True])
def test_lo_que_no_es_texto_util_devuelve_nulo(valor):
    assert segura(valor) is None


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que tiene que dejar pasar — un filtro que rompe todo se saca
# ══════════════════════════════════════════════════════════════════════════

LEGITIMAS = [
    "/api/media/twilio/ACxxx/Messages/MMyyy/Media/MEzzz",
    "/api/static/uploads/comprobante.jpg",
    "https://storage.example.com/kyc/abc.jpg",
    "http://localhost:8000/api/static/x.png",
    "https://api.twilio.com/2010-04-01/Accounts/ACxxx/Media/MEzzz",
    "data:image/png;base64,iVBORw0KGgo=",
    "data:image/jpeg;base64,/9j/4AAQ",
    "data:image/webp;base64,UklGRg==",
    "blob:https://risappbr.com/8f2a-4c1d",
]


@pytest.mark.parametrize("valor", LEGITIMAS)
def test_lo_que_la_aplicacion_usa_de_verdad_sigue_funcionando(valor):
    assert segura(valor) == valor


def test_devuelve_el_valor_ORIGINAL_no_el_limpio():
    """La limpieza es para DECIDIR. Si además se devolviera limpio, una URL con
    un espacio codificado legítimo saldría rota."""
    url = "https://storage.example.com/un archivo.jpg"
    assert segura(url) == url


# ══════════════════════════════════════════════════════════════════════════
# 3. La ruta desde la que se pide el medio
# ══════════════════════════════════════════════════════════════════════════

def ruta(valor):
    return js(f"m.rutaDeArchivo({json.dumps(valor)})")


def test_una_url_de_twilio_se_pide_por_el_proxy_propio():
    """Directo a Twilio el navegador no lleva las credenciales y muestra un 401
    adentro del `<img>`."""
    assert ruta("https://api.twilio.com/2010-04-01/Accounts/ACabc/Media/MEdef") \
        == "/api/media/twilio/ACabc/Media/MEdef"


def test_una_url_de_twilio_que_no_calza_no_devuelve_la_cruda():
    assert ruta("https://api.twilio.com/2010-04-01/Otra/cosa") is None


def test_la_ruta_tambien_filtra():
    """Es la que llaman las pantallas, así que tiene que filtrar sola: no puede
    depender de que alguien se acuerde de llamar antes a la otra."""
    for valor in BYPASSES:
        assert ruta(valor) is None, valor


def test_una_ruta_propia_no_se_toca():
    assert ruta("/api/media/x.png") == "/api/media/x.png"
    assert ruta("data:image/png;base64,AAA") == "data:image/png;base64,AAA"


# ══════════════════════════════════════════════════════════════════════════
# 4. Que el filtro se USE — acá es donde el agujero vuelve
# ══════════════════════════════════════════════════════════════════════════

def _fuentes():
    for raiz, _, archivos in os.walk(_FRONT):
        if "node_modules" in raiz:
            continue
        for a in archivos:
            if a.endswith((".jsx", ".js")):
                yield os.path.join(raiz, a)


def _linea(texto, pos):
    return texto.count("\n", 0, pos) + 1


# Lo que se acepta adentro de un `href` o de un `window.open`: una llamada al
# filtro, una constante del propio archivo, o un literal escrito a mano.
_LIMPIO = re.compile(
    r"^\s*(rutaDeArchivo|urlDeArchivoSegura|abrirArchivo|bajarArchivo)\s*\(|"
    r"^\s*['\"`]|"                     # un literal
    r"^\s*[A-Z_][A-Z0-9_]*\s*$|"       # una constante del archivo
    r"^\s*$"
)


def test_NINGUN_HREF_RECIBE_UN_VALOR_SIN_FILTRAR():
    """El agujero no vuelve porque alguien deshaga el filtro: vuelve porque la
    próxima pantalla escribe `href={algo.url}` sin llamarlo.

    Este test recorre el código. Es un poco tosco a propósito: prefiere pedir
    que se escriba `rutaDeArchivo(...)` de más antes que dejar pasar uno.
    """
    sospechosos = []
    patron = re.compile(r"href=\{([^}]*)\}")
    for ruta_archivo in _fuentes():
        if os.path.basename(ruta_archivo) == "urlDeArchivo.js":
            continue                      # el ejemplo del comentario de arriba
        texto = open(ruta_archivo, encoding="utf-8").read()
        for m in patron.finditer(texto):
            dentro = m.group(1)
            if _LIMPIO.match(dentro):
                continue
            # `URL.createObjectURL` lo arma esta misma página con datos propios.
            if "createObjectURL" in dentro or "objectUrl" in dentro:
                continue
            sospechosos.append(
                f"{os.path.relpath(ruta_archivo, _RAIZ)}:{_linea(texto, m.start())}"
                f"  href={{{dentro.strip()[:60]}}}")
    assert not sospechosos, (
        "un href recibe un valor sin pasar por rutaDeArchivo():\n  "
        + "\n  ".join(sospechosos))


def test_NINGUN_WINDOW_OPEN_RECIBE_UN_VALOR_SIN_FILTRAR():
    """Igual que el `href`: `window.open('javascript:...')` ejecuta."""
    sospechosos = []
    patron = re.compile(r"window\.open\(\s*([^,)]*)")
    for ruta_archivo in _fuentes():
        texto = open(ruta_archivo, encoding="utf-8").read()
        if os.path.basename(ruta_archivo) == "urlDeArchivo.js":
            continue                      # es el que lo llama bien
        for m in patron.finditer(texto):
            dentro = m.group(1)
            if _LIMPIO.match(dentro):
                continue
            if "createObjectURL" in dentro or "objectUrl" in dentro:
                continue
            sospechosos.append(
                f"{os.path.relpath(ruta_archivo, _RAIZ)}:{_linea(texto, m.start())}"
                f"  window.open({dentro.strip()[:60]})")
    assert not sospechosos, (
        "un window.open recibe un valor sin pasar por abrirArchivo():\n  "
        + "\n  ".join(sospechosos))


def test_LA_COPIA_DE_convertTwilioUrl_NO_VUELVE():
    """Estaba escrita dos veces, con el mismo cuerpo, en `AdminPanel.jsx` y en
    `History.jsx`. Arreglar una y olvidarse de la otra es exactamente cómo un
    filtro queda a medias."""
    donde = [os.path.relpath(f, _RAIZ) for f in _fuentes()
             if "const convertTwilioUrl" in open(f, encoding="utf-8").read()]
    assert not donde, f"volvió la copia local en: {donde}"
