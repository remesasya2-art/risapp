"""
tests/test_la_paleta_de_los_flujos.py — la paleta compartida aprende el modo
oscuro sin cambiar nada en claro.

COMO FUNCIONA

    `components/flujo/estilos.js` escribe cada color como
    `var(--en-oscuro-texto, #101828)`: vale el color de siempre en todas
    partes, salvo dentro de una pantalla marcada `.con-tema` en modo oscuro,
    donde index.css define la variable. Lo usan quince pantallas; en claro
    quedaron idénticas píxel a píxel (comparado con capturas).

LO QUE ESTE ARCHIVO CUIDA

    Las dos cosas que con una variable adentro se rompen EN SILENCIO —la
    pantalla compila, no hay error, y el color simplemente no aparece—:

    1. Pegarle texto a un color (`C.marca + '22'`, `${C.marca}33`): queda un
       valor inválido y el navegador lo descarta.
    2. Darle el color a un ícono como atributo (`<Check color={C.exito} />`):
       la variable dentro de un atributo de SVG la resuelve Chrome, pero no
       hay garantía de que lo haga el Safari del iPhone, y el ícono quedaría
       sin trazo, invisible. Va por `style={{ color: ... }}`.
"""
import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
_ESTILOS = _SRC / "components" / "flujo" / "estilos.js"


def _los_que_usan_la_paleta():
    """Los que importan la paleta, y también los que escriben sus colores
    «en oscuro» a mano (`var(--en-oscuro-...)`, como el inicio del cliente):
    las dos reglas valen igual para ellos, y así una pantalla que se convierta
    mañana queda vigilada sin que nadie tenga que agregarla a una lista."""
    usan = []
    for f in _SRC.rglob("*.js*"):
        if f == _ESTILOS or "node_modules" in f.parts:
            continue
        texto = f.read_text(encoding="utf-8")
        if "flujo/estilos" in texto or "from './estilos'" in texto or "var(--en-oscuro-" in texto:
            usan.append((f, texto))
    assert len(usan) >= 25, "la búsqueda de quién usa la paleta dejó de encontrarlos"
    return usan


def _la_paleta():
    fuente = _ESTILOS.read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("const C = {"):]
    return cuerpo[:cuerpo.index("};")]


def test_CADA_COLOR_ES_EL_DE_SIEMPRE_SALVO_EN_OSCURO():
    paleta = _la_paleta()
    pares = re.findall(r"(\w+): (.+?)(?:,\s*(?=\w+:)|,?\s*$)", paleta.replace("\n", " "))
    assert len(pares) == 20, pares
    for nombre, valor in pares:
        assert re.fullmatch(r"oscuro\('[a-z0-9-]+', '#[0-9A-Fa-f]{6}'\)", valor.strip()), (nombre, valor)
    fuente = _ESTILOS.read_text(encoding="utf-8")
    assert "const oscuro = (nombre, deSiempre) => `var(--en-oscuro-${nombre}, ${deSiempre})`;" in fuente


def test_LOS_COLORES_DE_SIEMPRE_NO_CAMBIARON():
    """Lo que garantiza que en claro nada se mueva: los valores de antes,
    escritos acá una vez, tal como estaban."""
    de_antes = {
        "tinta": "#101828", "texto": "#344054", "suave": "#667085", "tenue": "#98A2B3",
        "linea": "#E4E7EC", "lineaFuerte": "#D0D5DD", "lienzo": "#FFFFFF", "fondo": "#F7F8FA",
        "marca": "#4F46E5", "marcaSuave": "#EEF0FF", "marcaBorde": "#C7CDFF",
        "exito": "#067647", "exitoSuave": "#ECFDF3", "exitoBorde": "#A9EFC5",
        "alerta": "#B54708", "alertaSuave": "#FFFAEB", "alertaBorde": "#FEDF89",
        "error": "#B42318", "errorSuave": "#FEF3F2", "errorBorde": "#FECDCA",
    }
    paleta = _la_paleta()
    for nombre, color in de_antes.items():
        assert re.search(rf"\b{nombre}: oscuro\('[a-z0-9-]+', '{color}'\)", paleta), nombre


def test_CADA_VARIABLE_DE_LA_PALETA_TIENE_SU_VALOR_OSCURO():
    """Una variable sin valor oscuro no rompe nada —gana el color de siempre—
    pero deja un pedazo claro en medio de la pantalla oscura."""
    usadas = set(re.findall(r"oscuro\('([a-z0-9-]+)'", _la_paleta()))
    css = (_SRC / "index.css").read_text(encoding="utf-8")
    definidas = set(re.findall(r"--en-oscuro-([a-z0-9-]+):", css))
    assert usadas <= definidas, usadas - definidas


def test_NADIE_LE_PEGA_TEXTO_A_UN_COLOR_DE_LA_PALETA():
    malos = []
    for f, texto in _los_que_usan_la_paleta():
        # Cualquier cosa + dos cifras hexadecimales es agregarle transparencia
        # a un color; con una variable adentro queda inválido. No sólo los de
        # la paleta: una constante local (`acento`) puede valer una variable.
        for m in re.finditer(r"\bC\.\w+\s*\+|\+\s*C\.\w+\b|[\w.\])]\s*\+\s*['\"][0-9A-Fa-f]{2}['\"]|\$\{[^}]+\}[0-9A-Fa-f]{2}\b", texto):
            malos.append(f"{f.relative_to(_SRC)}: {m.group(0)}")
    assert not malos, malos


def test_NINGUN_ICONO_RECIBE_EL_COLOR_COMO_ATRIBUTO():
    malos = []
    for f, texto in _los_que_usan_la_paleta():
        for m in re.finditer(r"<([A-Z][\w.]*)\b[^<>]*?\s(color|fill|stroke)=\{", texto):
            malos.append(f"{f.relative_to(_SRC)}: <{m.group(1)} {m.group(2)}={{...}}>")
    assert not malos, (
        "un ícono recibe el color como atributo; con la paleta de variables "
        "puede quedar invisible en Safari. Pasalo por style={{ color: ... }}:\n  "
        + "\n  ".join(malos))
