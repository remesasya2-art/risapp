"""
tests/test_archivos_de_hasta_800_lineas.py — Ningún archivo de código pasa de
800 líneas; si crece más, se divide.

POR QUE ES UN TEST Y NO SOLO UNA REGLA EN CLAUDE.md

    `routes/admin.py` llegó a 3.366 líneas de a poco, un cambio razonable por
    vez, sin que ninguno pareciera el que lo pasaba de la raya. Una regla
    escrita no frena eso: nadie cuenta líneas antes de agregar una función.
    Un test sí.

LOS QUE YA PASABAN

    El día que se escribió, 43 archivos ya pasaban de 800. No se dividieron de
    una: están congelados en `archivos_largos.txt` con el número que tenían, y
    no pueden crecer. La lista sólo se achica (ver su encabezado).

QUÉ SE MIDE

    El código de la aplicación: `backend/` y `frontend/src/`. Las líneas se
    cuentan como las cuenta cualquier editor, comentarios incluidos: un
    archivo difícil de recorrer lo es igual si lo que sobra son comentarios.
"""
import os

import pytest

_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LISTA = os.path.join(os.path.dirname(__file__), "archivos_largos.txt")
TOPE = 800

_CARPETAS = ("backend", "frontend/src")
_EXTENSIONES = (".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".mjs")
# Lo que no escribe nadie a mano: dependencias, compilados y cachés.
_AFUERA = {"__pycache__", "node_modules", "venv", ".venv", ".pytest_cache", "dist", "build"}


def _medir():
    """`{camino desde la raíz del repositorio: líneas}` de cada archivo de código."""
    medidas = {}
    for carpeta in _CARPETAS:
        for base, carpetas, archivos in os.walk(os.path.join(_RAIZ, carpeta)):
            carpetas[:] = [c for c in carpetas if c not in _AFUERA]
            for nombre in archivos:
                if nombre.endswith(_EXTENSIONES):
                    camino = os.path.join(base, nombre)
                    with open(camino, encoding="utf-8") as f:
                        lineas = len(f.read().splitlines())
                    medidas[os.path.relpath(camino, _RAIZ).replace(os.sep, "/")] = lineas
    return medidas


def _congelados():
    congelados = {}
    with open(_LISTA, encoding="utf-8") as f:
        for linea in f:
            if not linea.strip() or linea.startswith("#"):
                continue
            numero, camino = linea.split(None, 1)
            congelados[camino.strip()] = int(numero)
    return congelados


@pytest.fixture(scope="module")
def medidas():
    return _medir()


def test_LA_MEDICION_ENCUENTRA_LOS_ARCHIVOS(medidas):
    """Sin esto, los de abajo pasarían si la medición dejara de encontrar
    archivos: ninguno de cero pasa de 800."""
    assert len(medidas) > 400, len(medidas)
    for conocido in ("backend/routes/admin/__init__.py", "frontend/src/pages/AdminPanel.jsx"):
        assert conocido in medidas, conocido


def test_NINGUN_ARCHIVO_NUEVO_PASA_DE_800_LINEAS(medidas):
    congelados = _congelados()
    largos = sorted(f"{camino} ({n} líneas)" for camino, n in medidas.items()
                    if n > TOPE and camino not in congelados)
    assert not largos, (
        f"pasan de {TOPE} líneas: " + ", ".join(largos) + ". Se dividen en "
        f"archivos más chicos por tema. No se agregan a archivos_largos.txt.")


def test_LOS_QUE_YA_PASABAN_NO_CRECEN(medidas):
    crecieron = sorted(f"{camino}: {medidas[camino]} líneas, tenía {tope}"
                       for camino, tope in _congelados().items()
                       if camino in medidas and medidas[camino] > tope)
    assert not crecieron, (
        "crecieron archivos que ya pasaban de 800: " + "; ".join(crecieron)
        + ". Lo nuevo va en un archivo aparte, o se divide el archivo.")


def test_LA_LISTA_SOLO_SE_ACHICA(medidas):
    """Un archivo que bajó a 800 o se borró sale de la lista. Si se quedara,
    podría volver a crecer hasta el número viejo sin que nada avise."""
    sobran = sorted(camino for camino in _congelados()
                    if camino not in medidas or medidas[camino] <= TOPE)
    assert not sobran, (
        "ya no pasan de 800 (o ya no existen): " + ", ".join(sobran)
        + ". Borralos de archivos_largos.txt.")
