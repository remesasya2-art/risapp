"""
tests/test_el_boton_de_refrescar.py — Que el botón de refrescar refresque.

QUE PASABA

    El encabezado del panel tenía dos botones con una flecha circular. Uno
    decía «Restaurar» y el otro no decía nada, y los dos parecían lo mismo.

    El de refrescar llamaba a `loadData`, que conoce CINCO pestañas
    —`overview`, `users`, `kyc`, `support`, `ratings`— y el panel tiene
    veintidós. En las otras diecisiete giraba un segundo y no pedía nada.
    Comprobado en el navegador, mirando la red:

        Resumen                  -> 1 pedido:  admin/pendientes
        Órdenes por procesar     -> NINGUNO
        Retiros                  -> NINGUNO
        Recargas VES             -> NINGUNO
        Auditoría                -> NINGUNO
        Libro mayor              -> NINGUNO
        Reportes                 -> NINGUNO

    Y el otro botón ni siquiera era un refrescar: «Restaurar» devuelve las
    transacciones que se ocultaron del panel. Lo que lo disfrazaba era el
    ícono, el mismo dibujo que el de al lado.

POR QUE ESTO ES UN TEST Y NO ALCANZA CON HABERLO ARREGLADO

    El arreglo es UNA LINEA: `key={recarga}` en el `<main>` que envuelve las
    secciones. Es exactamente la clase de línea que alguien saca dentro de seis
    meses por parecerle de más —un `key` en un elemento que no está en una
    lista se lee como un descuido—, y el botón vuelve a mentir en diecisiete
    pestañas sin que nada falle: sigue girando igual.

    Lo mismo con el ícono: volver a poner una flecha circular no rompe nada.
"""
import os
import pathlib
import re

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_FRONT = _RAIZ / "frontend" / "src"

PANEL = _FRONT / "pages" / "AdminPanel.jsx"
RESTAURAR = _FRONT / "components" / "common" / "RestoreButton.jsx"

# Los dos dibujos de flechas circulares de la librería de íconos. Son los que
# hacen que dos botones distintos se lean como el mismo.
FLECHAS_CIRCULARES = ("RotateCcw", "RotateCw", "RefreshCw", "RefreshCcw")


def _solo_el_codigo(texto: str) -> str:
    """El archivo sin sus comentarios.

    HIZO FALTA EN LA PRIMERA CORRIDA, Y VALE ANOTAR POR QUE

        Estos tests se escribieron junto con el arreglo, y los dos fallaron de
        entrada — por los comentarios del propio arreglo. Uno explica por qué
        el ícono ya NO es `RotateCcw`, y nombrarlo alcanzaba para que el test
        lo diera por puesto; otro menciona el `<main>` en prosa y el test se
        quedaba con esa mención en vez de con la etiqueta de verdad.

        Una guarda que lee código con expresiones regulares no distingue lo que
        el archivo HACE de lo que el archivo CUENTA. Y como en este repositorio
        los comentarios explican el porqué —o sea que nombran justo aquello de
        lo que se salió—, la confusión no es un caso raro: es el caso normal.
    """
    sin_bloques = re.sub(r"\{?/\*.*?\*/\}?", "", texto, flags=re.S)
    # El `(?<!:)` deja quietas las direcciones web: `https://` no es un
    # comentario, y borrar de ahí en adelante se comería media línea de código.
    return re.sub(r"(?<!:)//[^\n]*", "", sin_bloques)


def test_el_panel_se_vuelve_a_montar_al_refrescar():
    """La línea que hace que el botón sirva en las veintidós pestañas.

    Sin el `key`, cada sección se queda con los datos que trajo al entrar y el
    botón no tiene forma de pedirle nada: la mayoría de las secciones son
    componentes aparte que `loadData` no conoce.
    """
    panel = _solo_el_codigo(PANEL.read_text(encoding="utf-8"))
    main = re.search(r"<main\b[^>]*>", panel)
    assert main, "no se encontró el <main> del panel"
    assert re.search(r"key=\{[A-Za-z_$][\w$]*\}", main.group(0)), (
        "el <main> del panel perdió su `key`: sin ella el botón de refrescar "
        "vuelve a no pedir nada en las pestañas que son un componente aparte, "
        "y sigue girando igual, así que nadie se entera.\n"
        f"  {main.group(0)[:120]}")


def test_el_boton_de_refrescar_mueve_esa_key():
    """Que el botón llame a lo que refresca todo, y no sólo a `loadData`.

    Volver a engancharlo directo a `loadData` deja la `key` en su lugar y el
    botón inútil igual: es el defecto original, con el arreglo puesto al lado
    sin usarse.
    """
    panel = _solo_el_codigo(PANEL.read_text(encoding="utf-8"))

    boton = re.search(r"<button[^>]*data-testid=\"refresh-button\"", panel)
    assert boton, "no se encontró el botón de refrescar del encabezado"
    manejador = re.search(r"onClick=\{([A-Za-z_$][\w$]*)\}", boton.group(0))
    assert manejador, f"el botón de refrescar no tiene un manejador con nombre:\n  {boton.group(0)[:150]}"

    nombre = manejador.group(1)
    cuerpo = re.search(rf"const {re.escape(nombre)} = \(\) => \{{(.*?)\n  \}};",
                       panel, re.S)
    assert cuerpo, f"no se encontró `{nombre}` en el panel"
    assert "setRecarga" in cuerpo.group(1), (
        f"`{nombre}` ya no cambia la `key` del <main>: el botón vuelve a "
        "refrescar sólo las cinco pestañas que conoce `loadData`.")


def test_restaurar_no_se_disfraza_de_refrescar():
    """Los dos botones están pegados en el encabezado y hacen cosas distintas.

    «Restaurar» devuelve transacciones ocultas del panel; refrescar vuelve a
    pedir los datos. Con el mismo dibujo, el de al lado no se aprieta nunca.
    """
    restaurar = _solo_el_codigo(RESTAURAR.read_text(encoding="utf-8"))
    culpables = [i for i in FLECHAS_CIRCULARES if re.search(rf"\b{i}\b", restaurar)]
    assert not culpables, (
        "«Restaurar» volvió a usar un ícono de flechas circulares "
        f"({', '.join(culpables)}), el mismo que el botón de refrescar que "
        "tiene al lado. No hace lo mismo: devuelve las transacciones que se "
        "ocultaron del panel.")
