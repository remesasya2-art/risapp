"""
tests/test_los_dos_flujos_se_ven_igual.py — Enviar a Venezuela y enviar con
Bitcoin son la misma tarea, y tienen que verse igual.

POR QUE ESTO ES UN TEST

    `BTCLightning.jsx` tenía su propio sistema visual: fondo con degradado
    violeta y celeste, paleta ámbar, pasos dibujados a mano, emojis como
    iconos. Al lado de `Send.jsx` —el mismo usuario, la misma tarea, el mismo
    dinero— parecía otra aplicación.

    Se unificaron contra `components/flujo`, que es el MISMO módulo y no uno
    parecido. Con estilos copiados, la unificación dura hasta el primer retoque
    en una sola de las dos pantallas, y nadie se entera: las dos compilan, las
    dos andan, y el usuario ve una aplicación cuidada en una pantalla y no en
    la otra.

    Un test no puede juzgar si algo se ve bien. Sí puede sostener lo único que
    hace que se vean igual: que las dos tomen los valores del mismo lugar y no
    definan los suyos.
"""
import os
import pathlib
import re

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

FLUJOS = [
    "frontend/src/pages/Send.jsx",
    "frontend/src/pages/BTCLightning.jsx",
]
COMPARTIDO = "frontend/src/components/flujo"


def _fuente(ruta):
    return (_RAIZ / ruta).read_text(encoding="utf-8")


def _sin_comentarios(texto):
    fuera, en_bloque = [], False
    for linea in texto.splitlines():
        s = linea.strip()
        if en_bloque:
            if "*/" in s:
                en_bloque = False
            continue
        if s.startswith("/*"):
            en_bloque = "*/" not in s
            continue
        if s.startswith("//") or s.startswith("*"):
            continue
        fuera.append(linea)
    return "\n".join(fuera)


# Las dos mitades del módulo compartido. Pedir sólo «que mencione flujo»
# alcanzaba para que una pantalla se llevara las piezas a otro lado y el test
# siguiera verde por el import que quedaba: lo encontró una mutación.
IMPORTS = [
    ("from '../components/flujo'", "las piezas: Boton, Aviso, Progreso, Opcion"),
    ("from '../components/flujo/estilos'", "la paleta y las medidas"),
]


def test_las_dos_pantallas_toman_los_valores_del_modulo_compartido():
    faltan = []
    for ruta in FLUJOS:
        fuente = _fuente(ruta)
        for linea, que in IMPORTS:
            if linea not in fuente:
                faltan.append(f"{ruta}  no trae {que}  ({linea})")

    assert not faltan, (
        "Estas pantallas dejaron de usar el sistema visual compartido:\n  "
        + "\n  ".join(faltan)
        + f"\n\nLos valores viven en {COMPARTIDO}. Una pantalla que define los "
          "suyos se va a separar de la otra en el primer retoque.")


# Los colores del sistema. Escritos a mano en una pantalla, empiezan la deriva.
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")

# El QR se pide con `size=200x200`; no es color. El resto de las excepciones
# tiene que ganarse el lugar acá, con el motivo escrito.
EXCEPCIONES = {
    "frontend/src/pages/BTCLightning.jsx": {
        "#fff": "el blanco del tilde sobre el círculo elegido, igual que en Send",
    },
    "frontend/src/pages/Send.jsx": {
        "#fff": "el blanco de los botones primarios",
        "#4338CA": "el hover del botón primario, que vive en la hoja de estilos",
    },
}


def test_ninguna_de_las_dos_escribe_colores_a_mano():
    """Un `#f59e0b` suelto es el primer paso de vuelta a dos diseños.

    No se prohíbe el blanco: `'#fff'` sobre un fondo de marca es el contraste
    y no una decisión de paleta. Se prohíben los colores de seis dígitos, que
    son los que forman una paleta.
    """
    hallazgos = []
    for ruta in FLUJOS:
        permitidos = EXCEPCIONES.get(ruta, {})
        for n, linea in enumerate(_sin_comentarios(_fuente(ruta)).splitlines(), 1):
            for color in _HEX.findall(linea):
                if color in permitidos:
                    continue
                hallazgos.append(f"{ruta}:{n}  {color}  →  {linea.strip()[:80]}")

    assert not hallazgos, (
        "Hay colores escritos a mano en un flujo de dinero:\n  "
        + "\n  ".join(hallazgos)
        + f"\n\nLa paleta es `C`, en {COMPARTIDO}/estilos.js. Un color suelto "
          "no rompe nada hoy y es el primer paso de vuelta a dos diseños "
          "distintos. Si de verdad hace falta, agregalo a EXCEPCIONES con el "
          "motivo escrito.")


def test_progreso_siempre_recibe_sus_pasos():
    """`Progreso` dejó de traer los pasos de adentro y ahora los recibe.

    Esto pasó de verdad al separarlo: `Send.jsx` quedó llamándolo sin `pasos`.
    El proyecto compiló, el linter no dijo nada, y la pantalla de enviar a
    Venezuela habría reventado al abrirse con «Cannot read properties of
    undefined (reading 'length')». Se descubrió a mano, y por eso está acá.
    """
    sin_pasos = []
    frontend = _RAIZ / "frontend" / "src"
    for archivo in frontend.rglob("*.jsx"):
        if any(p in ("node_modules", "dist", "build") for p in archivo.parts):
            continue
        texto = archivo.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"<Progreso\b([^>]*)>", texto):
            if "pasos=" not in m.group(1):
                linea = texto[:m.start()].count("\n") + 1
                sin_pasos.append(f"{archivo.relative_to(_RAIZ)}:{linea}")

    assert not sin_pasos, (
        "Se está usando <Progreso> sin pasarle `pasos`:\n  "
        + "\n  ".join(sin_pasos)
        + "\n\nLa pantalla revienta al abrirse, y ni el compilador ni el "
          "linter lo ven.")


def test_ninguna_pantalla_convierte_con_una_tasa_inventada():
    """Un valor por defecto para la tasa no se ve roto: se ve bien y miente.

    `BTCLightning.jsx` arrancaba con `useState(680)`. Si el servidor no
    contestaba, la pantalla decía «el beneficiario recibe X VES garantizados»
    con una tasa que nadie confirmó. `Send.jsx` ya había corregido lo mismo.

    Se busca un número en el `useState` de cualquier estado que hable de tasa
    o precio: es la forma que tiene el error.
    """
    sospecha = re.compile(
        r"const\s*\[\s*(\w*(?:tasa|precio|rate)\w*)\s*,[^\]]*\]\s*=\s*useState\(\s*([\d.]+)\s*\)",
        re.IGNORECASE)

    hallazgos = []
    for ruta in FLUJOS:
        for n, linea in enumerate(_sin_comentarios(_fuente(ruta)).splitlines(), 1):
            for nombre, valor in sospecha.findall(linea):
                hallazgos.append(f"{ruta}:{n}  {nombre} arranca en {valor}")

    assert not hallazgos, (
        "Una pantalla que mueve dinero arranca con una tasa escrita a mano:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nSin tasa confirmada por el servidor no se convierte, no se "
          "promete y no se avanza. Un número acá no deja la pantalla rota: la "
          "deja mintiendo, que es peor.")
