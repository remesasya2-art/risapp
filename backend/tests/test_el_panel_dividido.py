"""
tests/test_el_panel_dividido.py — Lo que puede romperse en silencio desde que
`routes/admin.py` se dividió en `routes/admin/`.

Mover el código no cambió ninguna ruta: se comparó la lista entera de la app
antes y después, y quién atiende cada URL. Pero la división abrió tres
maneras nuevas de perder algo sin que nada falle, y cada una tiene su guarda:

    1. Una parte nueva en la carpeta que nadie suma a `__init__.py`: sus rutas
       no existen, y el panel recibe 404 en vez de un error que se vea.
    2. Los barridos de los tests que recorren `routes/` sin bajar a las
       subcarpetas: dejan de mirar el panel y siguen en verde.
    3. El nombre del registro: con `__name__`, cada parte anotaría con un
       nombre propio y una búsqueda por `routes.admin` dejaría de encontrarlas.
"""
import importlib
import logging
import os
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import los_py_de                                       # noqa: E402

_CARPETA = _BACKEND / "routes" / "admin"


def _partes():
    """Los módulos de la carpeta que declaran rutas."""
    salida = []
    for archivo in sorted(_CARPETA.glob("*.py")):
        if archivo.name == "__init__.py":
            continue
        modulo = importlib.import_module(f"routes.admin.{archivo.stem}")
        if getattr(modulo, "router", None) is not None:
            salida.append(modulo)
    return salida


def _firmas(router):
    return {(m, r.path, r.endpoint) for r in router.routes for m in r.methods}


def test_CADA_PARTE_DE_LA_CARPETA_ESTA_SUMADA_AL_PANEL():
    """Si una parte no está en la lista de `__init__.py`, sus rutas no existen
    en la app. Se compara la función que atiende, no sólo el camino: una ruta
    con el mismo camino en otra parte no tapa a la que falta."""
    from routes.admin import router
    del_panel = _firmas(router)
    partes = _partes()
    assert len(partes) >= 11, [p.__name__ for p in partes]
    for parte in partes:
        faltan = _firmas(parte.router) - del_panel
        assert not faltan, (
            f"{parte.__name__} tiene rutas que el panel no registra: "
            f"{sorted((m, p) for m, p, _ in faltan)}. Sumala a la lista de "
            f"routes/admin/__init__.py.")


def test_EL_PANEL_NO_TIENE_RUTAS_DE_MAS():
    """Al revés: todo lo que registra el panel sale de alguna parte. Si el
    agregador empezara a declarar rutas propias, dejaría de ser sólo el punto
    que junta."""
    from routes.admin import router
    de_las_partes = set()
    for parte in _partes():
        de_las_partes |= _firmas(parte.router)
    assert _firmas(router) == de_las_partes


def test_LOS_BARRIDOS_BAJAN_A_LA_CARPETA_DEL_PANEL():
    """`los_py_de` es lo que usan los barridos de `routes/`. Si deja de bajar
    a las subcarpetas, esos tests dejan de mirar el panel y siguen en verde."""
    vistos = set(los_py_de(_BACKEND / "routes"))
    del_panel = {f"admin/{p.name}" for p in _CARPETA.glob("*.py")}
    assert del_panel <= vistos, sorted(del_panel - vistos)
    assert "basic.py" in vistos, "y los de arriba siguen estando"
    assert not any("__pycache__" in v for v in vistos)


def test_EL_REGISTRO_SIGUE_ANOTANDO_COMO_ROUTES_ADMIN():
    from routes.admin import _comun
    assert _comun.logger is logging.getLogger("routes.admin")
    for parte in _partes():
        registro = getattr(parte, "logger", None)
        if registro is not None:
            assert registro.name == "routes.admin", parte.__name__
