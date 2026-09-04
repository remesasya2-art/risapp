"""
tests/test_puente_con_llave.py — Que la clave se pida en TODAS, no en casi todas.

DE QUE SE TRATA

    Dos módulos de la aplicación no usan sesión: el puente con adminbrl
    (`/api/adminbrl/*`) y el centro de gestión (`/api/centro-gestion/*`). Entran
    con una clave compartida en una cabecera, y esa clave es lo único que los
    separa de internet.

    `test_puente_adminbrl.py` ya prueba que la clave funciona: sin ella 401, con
    una equivocada 401, sin clave configurada en el servidor 503, y que después
    de varios intentos fallidos se bloquea. Pero lo prueba sobre UNA ruta.

LA FORMA EN QUE ESTO SE ROMPE

    No es que alguien saque el chequeo. Es que alguien agrega la ruta número
    seis y se olvida de las dos líneas:

        x_adminbrl_key: Optional[str] = Header(None)
        _check_api_key(x_adminbrl_key)

    La ruta anda perfecto en las pruebas manuales —contesta lo que tiene que
    contestar— y queda abierta. Ya pasó una vez en esta aplicación, con
    `/withdrawal/create`: la misma función tenía dos decoradores y sólo uno
    llevaba la guardia.

    Por eso este archivo no lista rutas: las recorre TODAS. Una ruta nueva sin
    la clave lo pone en rojo el día que se escribe.

    Se mira el árbol del código y no el texto: un `grep` de `_check_api_key`
    encuentra la línea del comentario que explica por qué hay que llamarla.
"""
import ast
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

PUENTES = [
    ("routes/adminbrl_bridge.py", "_check_api_key", "x_adminbrl_key"),
    ("routes/centro_gestion.py", None, "x_centrogestion_key"),
]


def _guardia_de(archivo):
    """El nombre de la función que valida la clave en ese módulo."""
    texto = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    arbol = ast.parse(texto)
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "key" in nodo.name.lower() and nodo.name.startswith("_"):
                return nodo.name
    return None


def _rutas_de(archivo):
    """Cada handler con decorador `@router.<verbo>` del módulo, ya parseado."""
    texto = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    arbol = ast.parse(texto)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in nodo.decorator_list:
            llamada = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(llamada, ast.Attribute) and \
                    isinstance(llamada.value, ast.Name) and llamada.value.id == "router":
                yield nodo
                break


@pytest.mark.parametrize("archivo", [a for a, _, _ in PUENTES])
def test_hay_una_funcion_que_valida_la_clave(archivo):
    assert _guardia_de(archivo), f"{archivo}: no se encontró la función de la clave"


@pytest.mark.parametrize("archivo, _guardia, cabecera", PUENTES)
def test_TODA_RUTA_DEL_PUENTE_PIDE_LA_CABECERA(archivo, _guardia, cabecera):
    """Sin el parámetro, FastAPI ni siquiera lee la cabecera: la ruta contesta
    igual venga de donde venga."""
    faltan = []
    for fn in _rutas_de(archivo):
        nombres = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
        if cabecera not in nombres:
            faltan.append(f"{fn.name}() línea {fn.lineno}")
    assert not faltan, (
        f"{archivo}: estas rutas no reciben `{cabecera}`, o sea que se pueden "
        f"llamar sin clave:\n  " + "\n  ".join(faltan))


@pytest.mark.parametrize("archivo, _guardia, cabecera", PUENTES)
def test_TODA_RUTA_DEL_PUENTE_LLAMA_A_LA_VALIDACION(archivo, _guardia, cabecera):
    """Recibir la cabecera no alcanza: hay que mirarla. Una ruta que la declara
    y no llama a la validación queda abierta y encima parece protegida."""
    guardia = _guardia_de(archivo)
    faltan = []
    for fn in _rutas_de(archivo):
        llama = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == guardia
            for n in ast.walk(fn))
        if not llama:
            faltan.append(f"{fn.name}() línea {fn.lineno}")
    assert not faltan, (
        f"{archivo}: estas rutas reciben la cabecera pero no llaman a "
        f"`{guardia}()`, así que no la miran:\n  " + "\n  ".join(faltan))


@pytest.mark.parametrize("archivo, _guardia, cabecera", PUENTES)
def test_LA_VALIDACION_ES_LO_PRIMERO_QUE_PASA(archivo, _guardia, cabecera):
    """Si la clave se mira después de leer la base o de escribir algo, la ruta
    ya hizo trabajo —y a veces cambió estado— para alguien que no debía entrar.
    """
    guardia = _guardia_de(archivo)
    tarde = []
    for fn in _rutas_de(archivo):
        # La primera sentencia que no sea el docstring ni un import.
        cuerpo = [s for s in fn.body
                  if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                  and not isinstance(s, (ast.Import, ast.ImportFrom))]
        if not cuerpo:
            continue
        primera = cuerpo[0]
        es_la_guardia = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == guardia
            for n in ast.walk(primera))
        if not es_la_guardia:
            tarde.append(f"{fn.name}() línea {fn.lineno}")
    assert not tarde, (
        f"{archivo}: en estas rutas la clave no se mira en la primera línea:\n  "
        + "\n  ".join(tarde))


@pytest.mark.parametrize("archivo, _guardia, cabecera", PUENTES)
def test_la_clave_se_compara_en_tiempo_constante(archivo, _guardia, cabecera):
    """`clave == esperada` corta en el primer carácter distinto, y el tiempo que
    tarda dice cuántos acertó. `hmac.compare_digest` tarda lo mismo siempre."""
    texto = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert "compare_digest" in texto, (
        f"{archivo}: la clave se compara con ==, que filtra cuánto acertó quien "
        "prueba")


@pytest.mark.parametrize("archivo, _guardia, cabecera", PUENTES)
def test_sin_clave_configurada_el_puente_NO_se_abre(archivo, _guardia, cabecera):
    """El caso peligroso de verdad: si la variable de entorno falta, la
    comparación contra la cadena vacía podría dar por buena una cabecera vacía y
    dejar el puente abierto. Tiene que plantarse, no ceder."""
    texto = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    guardia = _guardia_de(archivo)
    cuerpo = texto[texto.index(f"def {guardia}"):]
    cuerpo = cuerpo[:cuerpo.index("\n@router") if "\n@router" in cuerpo else len(cuerpo)]
    assert "503" in cuerpo, (
        f"{archivo}: sin la clave configurada, {guardia}() no se planta")


def test_ninguno_de_los_dos_puentes_quedo_sin_rutas():
    """Si el barrido no encuentra ninguna ruta, todos los tests de arriba pasan
    sin haber mirado nada. Es la forma en que un test de barrido miente."""
    for archivo, _, _ in PUENTES:
        assert len(list(_rutas_de(archivo))) >= 3, f"{archivo}: el barrido no vio rutas"
