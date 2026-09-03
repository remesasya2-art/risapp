"""
tests/test_libro_mayor_pantalla.py — Que el Libro Mayor no se ponga en blanco.

QUE PASO

    Al abrir la sección «Integridad», la página quedaba en blanco.

    En React, una excepción durante el render desmonta el árbol entero: el que
    lo ve no recibe un error, recibe una pantalla vacía. Y la app no tenía UN
    SOLO `ErrorBoundary`, así que cualquier fallo de dibujo de cualquier sección
    se llevaba puesta la pantalla completa.

    La cadena era ésta, y tiene tres eslabones:

    1. LA CAUSA — una respuesta vieja aterrizaba en la vista nueva.
       `cargar()` se protegía con `const vivo = useRef(true)`: el efecto lo
       ponía en `true` al entrar y en `false` al salir. Al cambiar de vista con
       una petición en vuelo, la limpieza lo ponía en `false` y el efecto nuevo
       lo volvía a poner en `true` un instante después. Cuando llegaba la
       respuesta VIEJA, el chequeo `if (!vivo.current) return` la dejaba pasar y
       `setDatos` escribía los datos de la vista anterior.

    2. EL SINTOMA — `Integridad` recibía la respuesta de `Reconciliación`, que
       no trae `hallazgos`, y hacía `datos.hallazgos.length` sin proteger. Era
       el ÚNICO acceso crudo del archivo: todos los demás usan `(datos.x || [])`.
       TypeError.

    3. LA FALTA DE RED — sin `ErrorBoundary`, ese TypeError no quedaba contenido
       en la sección: mataba la página.

    Los tres se arreglaron, y este archivo fija los tres. En el repo no hay
    runner de tests de JavaScript, así que la comprobación es sobre el código
    fuente. No es tan fuerte como renderizar el componente, y se dice acá para
    que nadie lea de más en un test en verde.
"""
import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parent.parent.parent
_LIBRO = _RAIZ / "frontend" / "src" / "components" / "admin" / "LibroMayor.jsx"
_BOUNDARY = _RAIZ / "frontend" / "src" / "components" / "common" / "ErrorBoundary.jsx"


def _sin_comentarios(texto: str) -> str:
    """Saca comentarios sin romperse con lo que sólo LOS PARECE.

    Un `re.sub(r"/\\*.*?\\*/", ...)` sobre este proyecto se come código: en JSX
    hay `accept="image/*"`, y ese `/*` abre un comentario que nunca cierra. Un
    test que afirma que algo NO está pasaría en verde porque el stripper borró
    justo el pedazo que buscaba. Por eso se recorre carácter por carácter,
    respetando comillas simples, dobles y backticks.
    """
    salida = []
    i, n = 0, len(texto)
    cita = None
    while i < n:
        c = texto[i]
        if cita:
            salida.append(c)
            if c == "\\" and i + 1 < n:
                salida.append(texto[i + 1])
                i += 2
                continue
            if c == cita:
                cita = None
            i += 1
            continue
        if c in "'\"`":
            cita = c
            salida.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "/":
            j = texto.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and texto[i + 1] == "*":
            j = texto.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        salida.append(c)
        i += 1
    return "".join(salida)


@pytest.fixture(scope="module")
def codigo():
    assert _LIBRO.is_file(), f"no está {_LIBRO}"
    return _sin_comentarios(_LIBRO.read_text(encoding="utf-8"))


def test_el_stripper_no_se_come_el_codigo():
    """La guarda de la guarda. Sin esto, todo lo de abajo puede pasar en falso."""
    entrada = 'const a = "image/*"; /* fuera */ const b = 1; // fuera\nconst c = 2;'
    salida = _sin_comentarios(entrada)
    assert '"image/*"' in salida, "se comió una cadena que parecía comentario"
    assert "const b = 1;" in salida
    assert "const c = 2;" in salida
    assert "fuera" not in salida


# ══════════════════════════════════════════════════════════════════════════
# 1. La causa: ninguna respuesta puede aterrizar en la vista equivocada
# ══════════════════════════════════════════════════════════════════════════

def test_no_queda_la_bandera_de_montado_compartida(codigo):
    """`vivo.current = true` en el efecto es exactamente lo que dejaba pasar la
    respuesta vieja: la limpieza lo bajaba y el efecto siguiente lo subía."""
    assert "vivo.current = true" not in codigo, (
        "volvió la bandera compartida: una respuesta de la vista anterior puede "
        "aterrizar en la vista actual")


def test_cada_carga_lleva_su_numero_y_se_descarta_si_no_es_la_ultima(codigo):
    assert re.search(r"const\s+mia\s*=\s*\+\+\s*peticion\.current", codigo), (
        "cada carga tiene que quedarse con su número de petición")
    assert re.search(r"peticion\.current\s*!==\s*mia", codigo), (
        "hay que descartar la respuesta que llega tarde antes de escribirla")


def test_setDatos_nunca_se_llama_sin_comprobar_antes(codigo):
    """Lo que de verdad importa: que no se pueda escribir el estado con una
    respuesta que ya no corresponde a la vista abierta."""
    for m in re.finditer(r"setDatos\(data\)", codigo):
        previo = codigo[max(0, m.start() - 400):m.start()]
        assert "peticion.current !== mia" in previo, (
            "hay un setDatos(data) sin el chequeo de petición delante")


# ══════════════════════════════════════════════════════════════════════════
# 2. El síntoma: ningún campo de la respuesta se lee crudo
# ══════════════════════════════════════════════════════════════════════════

def test_ningun_campo_de_datos_se_lee_sin_proteger(codigo):
    """`datos.hallazgos.length` era el único acceso crudo del archivo.

    Se permiten los que van DENTRO de un `(datos.x || []).length > 0 ?`, porque
    ahí la propia condición garantiza que el campo existe. El escáner los
    reconoce por el guard que aparece antes en el mismo bloque.
    """
    crudos = []
    for m in re.finditer(r"datos\.([a-z_]+)\.(length|map|filter|slice|reduce)\b", codigo):
        campo = m.group(1)
        anterior = codigo[max(0, m.start() - 600):m.start()]
        if f"(datos.{campo} || [])" in anterior:
            continue          # protegido por la condición que lo envuelve
        crudos.append(f"datos.{campo}.{m.group(2)}()")
    assert crudos == [], (
        "estos campos se leen crudos de la respuesta y rompen el render si no "
        f"vienen: {crudos}. Usá `(datos.x || [])`.")


# ══════════════════════════════════════════════════════════════════════════
# 3. La red: un error de dibujo no puede llevarse la página
# ══════════════════════════════════════════════════════════════════════════

def test_existe_un_error_boundary_de_verdad():
    assert _BOUNDARY.is_file(), "falta el componente ErrorBoundary"
    fuente = _sin_comentarios(_BOUNDARY.read_text(encoding="utf-8"))
    assert "getDerivedStateFromError" in fuente, (
        "sin `getDerivedStateFromError` no atrapa nada")
    assert "componentDidCatch" in fuente, (
        "hay que dejar el error en la consola: es lo único que permite "
        "encontrar la línea cuando alguien reporta «se puso en blanco»")


def test_las_vistas_se_dibujan_dentro_del_error_boundary(codigo):
    assert "ErrorBoundary" in codigo, (
        "las vistas del libro tienen que ir dentro de un ErrorBoundary")
    dentro = codigo[codigo.index("<ErrorBoundary"):codigo.index("</ErrorBoundary>")]
    for vista in ("Balance", "Diario", "Mayor", "Reconciliacion", "Integridad"):
        assert f"<{vista} datos=" in dentro, (
            f"la vista {vista} quedó fuera del ErrorBoundary")


def test_el_boundary_se_limpia_al_cambiar_de_vista():
    """Si el error se quedara pegado, una sección rota dejaría inservibles a
    todas las demás."""
    fuente = _sin_comentarios(_BOUNDARY.read_text(encoding="utf-8"))
    assert "componentDidUpdate" in fuente
    assert "prevProps.clave !== this.props.clave" in fuente
