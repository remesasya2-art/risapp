"""
tests/test_contrato_de_salida.py — Que toda ruta NUEVA diga qué devuelve.

QUE ES UN CONTRATO DE SALIDA

    El `response_model` de FastAPI: un modelo que declara qué campos devuelve
    una ruta. No es documentación — FastAPI RECORTA la respuesta a esos campos.
    O sea que es una lista de lo permitido que no se puede olvidar, porque vive
    al lado del nombre de la función.

POR QUE ESTE ARCHIVO EXISTE

    El día que se escribió, de las 364 rutas de la aplicación, NINGUNA declaraba
    contrato. Y en la misma semana aparecieron tres fugas del mismo tipo, todas
    por devolver un documento de Mongo con una lista de lo prohibido:

        /auth/me                  la semilla del segundo factor de su dueño
        las cuatro puertas        lo mismo, cada una con su propia lista
        /api/admin/users          la semilla del JEFE, a quien atienda clientes

    Un contrato en esas rutas las habría cortado de raíz.

POR QUE NO SE PUSIERON LOS 364 DE UNA

    Porque un modelo mal escrito se come campos EN SILENCIO: la ruta contesta
    200 y la pantalla queda vacía. Trescientos sesenta y cuatro modelos escritos
    de un tirón, sobre una aplicación con gente usándola, es cambiar una fuga
    conocida por un montón de pantallas rotas desconocidas.

    Así que esto es un trinquete: `rutas_sin_contrato.txt` congela lo que había
    y el test exige contrato sólo en lo NUEVO. El número no puede crecer.

COMO SE DESTRABA CUANDO SE PONE ROJO

    Lo dice el mensaje del assert, con el nombre de la ruta. En resumen:
    ruta nueva, ponele `response_model`; ruta vieja a la que se lo pusiste,
    borrala de la lista; ruta que borraste, borrala de la lista.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                # noqa: E402,F401

LISTA = os.path.join(os.path.dirname(__file__), "rutas_sin_contrato.txt")


def _congeladas():
    with open(LISTA, encoding="utf-8") as f:
        return {l.strip() for l in f
                if l.strip() and not l.lstrip().startswith("#")}


@pytest.fixture(scope="module")
def rutas():
    """(método, path, tiene_contrato) de cada ruta de la aplicación."""
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    from fastapi.routing import APIRoute

    salida = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            salida.append((f"{m} {r.path}", r.response_model is not None))
    return salida


def test_TODA_RUTA_NUEVA_DECLARA_QUE_DEVUELVE(rutas):
    """El trinquete. Esto es lo que impide que el número vuelva a crecer."""
    congeladas = _congeladas()
    nuevas = sorted(nombre for nombre, tiene in rutas
                    if not tiene and nombre not in congeladas)
    assert not nuevas, (
        "estas rutas no declaran `response_model`:\n\n    "
        + "\n    ".join(nuevas)
        + "\n\nUna ruta sin contrato devuelve lo que le pongan, y así se "
          "filtraron la semilla del segundo factor y el hash del PIN. Declarale "
          "un modelo con lo que de verdad devuelve.\n\n"
          "Si es una ruta interna sin respuesta que le importe a nadie, "
          "`response_model=dict` no sirve —no recorta nada—: escribí el modelo.")


def test_LA_LISTA_SOLO_SE_ACHICA(rutas):
    """Que a una ruta congelada se le ponga contrato es una buena noticia, y
    hay que anotarla: si no se la saca de la lista, el trinquete deja de
    apretar sobre ella y puede volver a quedar sin contrato sin que nadie se
    entere."""
    congeladas = _congeladas()
    ya_tienen = sorted(nombre for nombre, tiene in rutas
                       if tiene and nombre in congeladas)
    assert not ya_tienen, (
        "estas rutas YA declaran contrato pero siguen en "
        "tests/rutas_sin_contrato.txt:\n\n    "
        + "\n    ".join(ya_tienen)
        + "\n\nBorralas de esa lista. Es una menos.")


def test_LA_LISTA_NO_NOMBRA_RUTAS_QUE_NO_EXISTEN(rutas):
    """Una lista con nombres viejos adentro se va llenando de ruido hasta que
    nadie la lee, y entonces deja de ser una guarda."""
    vivas = {nombre for nombre, _ in rutas}
    fantasmas = sorted(_congeladas() - vivas)
    assert not fantasmas, (
        "tests/rutas_sin_contrato.txt nombra rutas que ya no existen:\n\n    "
        + "\n    ".join(fantasmas)
        + "\n\nBorralas de esa lista.")


def test_EL_TRINQUETE_APRIETA_DE_VERDAD(rutas):
    """Que la guarda vea la forma que vino a buscar, o no está mirando nada.

    Sin esto, una lista mal leída —vacía, o con todo adentro— dejaría los tres
    tests de arriba en verde para siempre.
    """
    congeladas = _congeladas()
    assert congeladas, "la lista quedó vacía: el trinquete no aprieta sobre nada"
    assert len(congeladas) < 1000, "la lista se llenó de ruido"

    # Una ruta inventada tiene que ser detectada como nueva.
    inventada = "GET /api/una-ruta-que-no-existe"
    assert inventada not in congeladas
    nuevas = [n for n, tiene in [(inventada, False)]
              if not tiene and n not in congeladas]
    assert nuevas == [inventada], "el trinquete no ve una ruta nueva sin contrato"
