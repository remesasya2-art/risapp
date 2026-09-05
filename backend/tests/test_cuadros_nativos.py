"""
tests/test_cuadros_nativos.py — Nadie vuelve a preguntar con un cuadro del
navegador.

EL DEFECTO QUE ESTE ARCHIVO SOSTIENE CERRADO

    `window.confirm` y `window.prompt` PUEDEN DEJAR DE APARECER, y cuando eso
    pasa devuelven `false` y `null`. O sea: el botón no hace nada. Sin error,
    sin aviso, sin nada en la consola.

    No es teórico. Chrome ofrece «Impedir que esta página cree más diálogos» en
    cuanto una página abre varios seguidos, y la casilla queda puesta para todo
    el sitio. Quien abre varios seguidos es el operador que procesa una cola de
    pagos: aprueba, confirma, aprueba, confirma… y en algún momento la tilda.

    A partir de ahí «Aprobar» deja de aprobar, y nadie sabe por qué.

    El reemplazo está en `frontend/src/components/flujo/confirmar.js`, y sus
    reglas se prueban acá con node, igual que las de las pantallas de envío.
"""
import json
import os
import pathlib
import re
import subprocess

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_FUENTE = _RAIZ / "frontend" / "src"
_MODULO = _FUENTE / "components" / "flujo" / "confirmar.js"

# Los cuadros que bloquean la página y pueden desaparecer sin avisar.
_PROHIBIDOS = ("window.confirm", "window.prompt", "window.alert")

_BLOQUE = re.compile(r"/\*.*?\*/", re.S)
# El `//` de un comentario, pero no el de `https://`: si se cortara ahí, una
# línea con una URL escondería lo que viniera después, que es justo lo que este
# test tiene que ver.
_LINEA = re.compile(r"(?<![:\w])//[^\n]*")


def _sin_comentarios(texto):
    """El código, sin los comentarios.

    Hace falta de verdad: los archivos que arreglaron esto EXPLICAN el defecto
    en su encabezado, y nombran `window.confirm` para hacerlo. Un test que
    buscara la cadena a secas fallaría por la documentación del propio arreglo.
    """
    return _LINEA.sub("", _BLOQUE.sub("", texto))


def _fuentes():
    for ruta in sorted(_FUENTE.rglob("*.js")) + sorted(_FUENTE.rglob("*.jsx")):
        yield ruta


def test_ninguna_pantalla_pregunta_con_un_cuadro_del_navegador():
    culpables = []
    for ruta in _fuentes():
        codigo = _sin_comentarios(ruta.read_text(encoding="utf-8"))
        for prohibido in _PROHIBIDOS:
            if prohibido in codigo:
                culpables.append(f"{ruta.relative_to(_RAIZ)} → {prohibido}")

    assert not culpables, (
        "Volvió a aparecer un cuadro del navegador:\n  "
        + "\n  ".join(culpables)
        + "\n\nSe puede bloquear, y ahí devuelve `false`/`null`: el botón deja "
          "de hacer nada, sin error. Usá `confirmar()` o `pedirTexto()` de "
          "components/flujo/confirmar.js."
    )


def test_el_reemplazo_existe_y_no_arrastra_la_ventana():
    """`confirmar.js` son sólo funciones; la ventana vive aparte.

    Importa: lo llaman pantallas que sólo quieren preguntar. Si acá hubiera
    JSX, cada una arrastraría el componente entero.
    """
    assert _MODULO.exists(), f"Falta {_MODULO.relative_to(_RAIZ)}."
    codigo = _sin_comentarios(_MODULO.read_text(encoding="utf-8"))
    assert "import" not in codigo, (
        "`confirmar.js` empezó a importar algo. Era un módulo sin dependencias "
        "a propósito.")


def test_el_host_se_monta_una_sola_vez_en_la_raiz():
    app = (_FUENTE / "App.jsx").read_text(encoding="utf-8")
    assert app.count("<ConfirmacionHost />") == 1, (
        "El host de las confirmaciones tiene que estar exactamente una vez en "
        "la raíz, al lado del <Toaster />.")


# ══════════════════════════════════════════════════════════════════════════
# Las reglas del módulo
# ══════════════════════════════════════════════════════════════════════════

def _js(cuerpo):
    """Corre una expresión contra el módulo real y devuelve su resultado."""
    guion = (f"import * as m from '{_MODULO}';\n"
             f"const r = await (async () => {{ {cuerpo} }})();\n"
             "console.log(JSON.stringify(r === undefined ? null : r));")
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"El módulo no corre:\n{r.stderr[-1500:]}")
    return json.loads(r.stdout.strip())


def test_sin_host_montado_la_respuesta_es_que_no():
    """Una pregunta que no se pudo hacer NO es un permiso concedido.

    Es el mismo fallo que tenía `window.confirm` bloqueado, pero al revés: acá
    se elige a propósito el lado seguro. Del otro lado de estas preguntas hay
    pagos, baneos y bajas de personal.
    """
    assert _js("return await m.confirmar({ titulo: 'x' });") is False
    assert _js("return await m.pedirTexto({ titulo: 'x' });") is None


def test_con_host_montado_se_le_pasa_la_pregunta():
    assert _js("""
        let visto = null;
        m.registrarHost((op) => { visto = op; return Promise.resolve(true); });
        await m.confirmar({ titulo: '¿Aprobar?', tono: 'peligro' });
        return [visto.titulo, visto.tono, visto.clase];
    """) == ['¿Aprobar?', 'peligro', 'confirmar']


def test_cancelar_es_que_no():
    assert _js("""
        m.registrarHost(() => Promise.resolve(null));
        return await m.confirmar({ titulo: 'x' });
    """) is False


def test_cancelar_y_dejar_vacio_son_cosas_distintas():
    """Y esta diferencia era un bug de verdad, no una sutileza.

    En el baneo del panel de KYC, el motivo se pedía con
    `window.prompt(...) || ''`: el `null` de cancelar se convertía en cadena
    vacía y el baneo salía igual. El operador apretaba Escape creyendo que se
    echaba atrás, y la cuenta quedaba bloqueada.
    """
    assert _js("""
        m.registrarHost(() => Promise.resolve(''));
        return await m.pedirTexto({ titulo: 'x', opcional: true });
    """) == ''
    assert _js("""
        m.registrarHost(() => Promise.resolve(null));
        return await m.pedirTexto({ titulo: 'x', opcional: true });
    """) is None


def test_al_desmontarse_el_host_se_vuelve_a_responder_que_no():
    assert _js("""
        const bajar = m.registrarHost(() => Promise.resolve(true));
        bajar();
        return await m.confirmar({ titulo: 'x' });
    """) is False


def test_un_host_viejo_no_pisa_al_nuevo():
    """Dos montajes seguidos —lo que hace React en modo estricto— y el de
    salida del primero no puede dejar la aplicación sin host."""
    assert _js("""
        const bajarPrimero = m.registrarHost(() => Promise.resolve(null));
        m.registrarHost(() => Promise.resolve(true));
        bajarPrimero();
        return await m.confirmar({ titulo: 'x' });
    """) is True
