"""
tests/test_el_menu_del_panel.py — Que ninguna sección del panel desaparezca.

QUE PASABA ANTES

    El panel era una tira plana de dieciocho pestañas que envolvía en tres
    filas, ordenadas por el momento en que se fueron agregando. En un teléfono
    esas pestañas se apilaban en unas diez filas: antes de llegar al contenido
    había que pasar toda la pared.

    Ahora las secciones viven agrupadas en un menú lateral —seis grupos que se
    despliegan—, que en pantalla angosta se pliega detrás de un botón. Es el
    mismo patrón que `pages/Dashboard.jsx` ya usaba para el cliente.

POR QUE HACE FALTA UN TEST, Y CUAL ES EL PELIGRO DE VERDAD

    Agrupar mueve las secciones de una lista plana a una lista de listas. A
    partir de ahora **una sección existe en el panel sólo si algún grupo la
    nombra**, y ése es un modo de fallar nuevo y silencioso:

        Alguien agrega la sección veintiuno a `TABS`, escribe su pantalla, la
        prueba entrando por `?tab=`, y se olvida de agregarla a `GRUPOS`. La
        aplicación compila, no hay error, no hay advertencia — y la sección
        simplemente NO APARECE EN EL MENU. Nadie la encuentra, y quien la
        escribió cree que está publicada.

    Este archivo cierra ese agujero por los dos lados: ninguna sección queda
    sin grupo, y ningún grupo nombra una sección que no existe.
"""
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
PANEL = _RAIZ / "frontend" / "src" / "pages" / "AdminPanel.jsx"

# `crm` era el contenedor de las subpestañas de clientes y ese trabajo ahora lo
# hace el grupo. Sigue aceptándose en la dirección (`?tab=crm`) por los enlaces
# viejos, pero no es una sección que el menú tenga que mostrar.
NO_ES_UNA_SECCION = {"crm"}


def _bloque(texto: str, nombre: str) -> str:
    """El contenido de `const NOMBRE = [ ... ];`, contando corchetes."""
    i = texto.index(f"const {nombre} = [")
    i = texto.index("[", i)
    hondo, j = 0, i
    while j < len(texto):
        if texto[j] == "[":
            hondo += 1
        elif texto[j] == "]":
            hondo -= 1
            if hondo == 0:
                return texto[i:j + 1]
        j += 1
    raise AssertionError(f"no se pudo cerrar el bloque de {nombre}")


@pytest.fixture(scope="module")
def panel():
    return PANEL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def secciones(panel):
    """Todas las claves de sección que el panel sabe dibujar."""
    claves = set()
    for nombre in ("TABS", "CRM_SUBTABS"):
        claves |= set(re.findall(r"key: '([\w]+)'", _bloque(panel, nombre)))
    return claves - NO_ES_UNA_SECCION


@pytest.fixture(scope="module")
def por_grupo(panel):
    """`{clave del grupo: [secciones que nombra]}`."""
    bloque = _bloque(panel, "GRUPOS")
    grupos = {}
    for grupo, hijas in re.findall(
            r"key: '(g_\w+)'.*?hijas: \[([^\]]*)\]", bloque, re.S):
        grupos[grupo] = re.findall(r"'([\w]+)'", hijas)
    assert grupos, "no se encontró ningún grupo en GRUPOS"
    return grupos


# ══════════════════════════════════════════════════════════════════════════
# 1. El agujero nuevo: una sección sin grupo no existe para nadie.
# ══════════════════════════════════════════════════════════════════════════

def test_ninguna_seccion_queda_sin_grupo(secciones, por_grupo):
    """El modo de fallar que trajo el menú agrupado.

    Una sección que ningún grupo nombra no sale en el menú, y no da error:
    compila, anda por `?tab=`, y nadie la encuentra nunca.
    """
    agrupadas = {c for hijas in por_grupo.values() for c in hijas}
    huerfanas = sorted(secciones - agrupadas)
    assert not huerfanas, (
        "estas secciones existen en el panel y NINGUN grupo del menú las "
        f"nombra, así que no hay forma de llegar a ellas: {', '.join(huerfanas)}.\n"
        "Se agregan a `GRUPOS` en frontend/src/pages/AdminPanel.jsx.")


def test_ningun_grupo_nombra_una_seccion_que_no_existe(secciones, por_grupo):
    """El error del otro lado: un renglón del menú que no lleva a ningún lado.

    Pasa al renombrar o quitar una sección y olvidarse del menú. La pantalla
    no rompe: el renglón se dibuja y no hace nada.
    """
    inventadas = sorted(
        {c for hijas in por_grupo.values() for c in hijas} - secciones)
    assert not inventadas, (
        "el menú nombra secciones que el panel no sabe dibujar, así que son "
        f"renglones que no llevan a ninguna parte: {', '.join(inventadas)}")


def test_ninguna_seccion_esta_en_dos_grupos(por_grupo):
    """Repetida, aparece dos veces en el menú y se pisan los estados de abierto."""
    vistas, repetidas = set(), set()
    for hijas in por_grupo.values():
        for clave in hijas:
            if clave in vistas:
                repetidas.add(clave)
            vistas.add(clave)
    assert not repetidas, f"están en más de un grupo: {', '.join(sorted(repetidas))}"


# ══════════════════════════════════════════════════════════════════════════
# 2. Que el menú siga siendo desplegable, que es lo que se pidió.
# ══════════════════════════════════════════════════════════════════════════

def test_los_grupos_arrancan_cerrados(panel):
    """Se pidió que se desplieguen, no que estén desplegados.

    La primera versión los abría todos y el menú quedaba en veinte renglones
    —el problema que vino a resolver—. Cerrados, son seis y entran juntos en
    cualquier pantalla.
    """
    # Anclado al nombre del estado, y no a «hay un `new Set()` en el archivo».
    # La primera versión buscaba el `new Set()` suelto y encontraba el de
    # `bannedEmails`, que está a treinta líneas: arrancar con grupos abiertos
    # dejaba el test en verde. Lo agarró la mutación.
    assert re.search(
        r"const \[desplegados, setDesplegados\] = useState\(\(\) => new Set\(\)\)",
        panel), (
        "el estado de los grupos desplegados ya no arranca vacío: si arranca "
        "con grupos adentro, el menú vuelve a abrirse todo de entrada.")
    # La condición se compara ENTERA, y no por «contiene `desplegados.has`».
    # La primera versión de este test buscaba ese trozo de texto, y
    # `!desplegados.has(...)` también lo contiene: invertir la condición dejaba
    # el menú abriéndose todo y los seis tests en verde. Lo agarró la mutación.
    assert re.search(
        r"const abierto = tieneLoAbierto \|\| desplegados\.has\(grupo\.key\);",
        panel), (
        "el grupo ya no se abre por estar EN la lista de desplegados. Si la "
        "condición se invirtió (`!...has`), están todos abiertos otra vez.")


def test_el_grupo_de_la_seccion_abierta_se_despliega_solo(panel):
    """Si no, el menú no puede indicar dónde estás parada."""
    assert re.search(r"const abierto = tieneLoAbierto \|\|", panel), (
        "el grupo de la sección activa dejó de abrirse solo: el menú puede "
        "quedar cerrado sobre la sección que se está mirando.")


def test_en_pantalla_angosta_el_menu_se_pliega(panel):
    """El teléfono es la mitad del cambio: sin esto, el menú tapa el contenido."""
    assert 'data-testid="boton-menu"' in panel, (
        "desapareció el botón que abre el menú en el teléfono")
    assert re.search(r"if \(!esAncho\) setMenuAbierto\(false\)", panel), (
        "elegir una sección ya no cierra el menú del teléfono: queda tapando "
        "justo lo que la persona acaba de pedir.")
