"""
tests/test_lo_que_no_se_publica.py — La página que se decidió no publicar.

QUE PASO

    `ComoFunciona.jsx` describía cómo opera la plataforma por dentro: los
    límites, el cupo que se puede mover sin verificar identidad, y qué queda
    registrado de cada operación. Era material interno y salió a la web.

    Se sacó de circulación: no tiene ruta y no se llega desde ningún lado. El
    archivo se conservó por si algún día se sirve DENTRO de la aplicación, con
    sesión iniciada.

POR QUE HACE FALTA UN TEST

    Un archivo que existe, compila y exporta un componente es una invitación.
    Alcanza con una línea en `App.jsx` para que vuelva a estar en internet, y
    quien la escriba probablemente crea que está arreglando un enlace roto.

    Nada avisaría: la aplicación sigue compilando, el sitio sigue andando, y la
    página vuelve a ser pública sin que nadie lo haya decidido.
"""
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

_FRONT = _RAIZ / "frontend" / "src"

# La página, y la dirección con la que estuvo publicada.
ARCHIVO = "frontend/src/pages/ComoFunciona.jsx"
RUTA = "/como-funciona"


def _fuentes():
    """Todo el frontend, sin lo compilado ni las dependencias."""
    for archivo in _FRONT.rglob("*"):
        if not archivo.is_file() or archivo.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        if any(p in ("node_modules", "dist", "build") for p in archivo.parts):
            continue
        yield archivo, archivo.read_text(encoding="utf-8", errors="ignore")


def test_la_pagina_no_tiene_ruta():
    """Ni pública ni detrás del login: hoy no se sirve de ninguna forma.

    Servirla adentro de la aplicación sería una decisión razonable y este test
    habría que cambiarlo a propósito. Lo que no puede pasar es que vuelva sola.
    """
    app = (_FRONT / "App.jsx").read_text(encoding="utf-8")

    culpables = [f"App.jsx:{n}  {l.strip()[:90]}"
                 for n, l in enumerate(app.splitlines(), 1)
                 if "ComoFunciona" in l or RUTA in l]

    assert not culpables, (
        f"«{ARCHIVO}» volvió a tener ruta:\n  " + "\n  ".join(culpables)
        + f"\n\nEs material interno: describe con detalle cómo opera la "
          "plataforma por dentro, y se decidió que no salga a la web. Si ahora "
          "se quiere servir dentro de la aplicación —con sesión iniciada— "
          "cambiá este test a propósito y dejá dicho por qué.")


def test_nadie_enlaza_a_la_pagina():
    """Un enlace a una ruta que no existe no rompe nada: lleva al 404.

    Por eso el test mira los enlaces aparte de la ruta. Un botón «Cómo
    funciona» que va a ningún lado es la clase de cosa que alguien arregla
    devolviéndole la ruta a la página.
    """
    rotos = []
    for archivo, texto in _fuentes():
        for n, linea in enumerate(texto.splitlines(), 1):
            if linea.lstrip().startswith(("*", "//", "/*", "{/*")):
                continue
            if RUTA in linea:
                rotos.append(f"{archivo.relative_to(_RAIZ)}:{n}  {linea.strip()[:90]}")

    assert not rotos, (
        f"Hay enlaces a «{RUTA}», que ya no se sirve:\n  " + "\n  ".join(rotos)
        + "\n\nO se saca el enlace, o se decide publicar la página de nuevo. "
          "Dejar el enlace apuntando al 404 termina en lo segundo sin que nadie "
          "lo haya decidido.")


def test_el_archivo_sigue_estando_y_dice_que_no_se_publica():
    """Las dos mitades.

    Que el archivo esté: se conservó a propósito, y borrarlo sin decirlo sería
    perder el trabajo en silencio. Que su cabecera lo diga: el que lo abra
    dentro de seis meses tiene que entender por qué no está enganchado antes de
    engancharlo.
    """
    pagina = _RAIZ / ARCHIVO
    if not pagina.exists():
        pytest.fail(
            f"«{ARCHIVO}» ya no está. Se había conservado por si algún día se "
            "sirve dentro de la aplicación. Si se decidió borrarla, borrá "
            "también este test — pero que sea una decisión escrita y no un "
            "archivo que desapareció.")

    cabecera = "\n".join(pagina.read_text(encoding="utf-8").splitlines()[:14]).lower()
    assert "no se publica" in cabecera, (
        f"La cabecera de «{ARCHIVO}» dejó de decir que la página no se "
        "publica. Es lo único que separa a este archivo de un componente "
        "olvidado que alguien vuelve a enganchar de buena fe.")
