"""
tests/test_centro_gestion_quitado.py — Las rutas de centro-gestion se
quitaron, por decisión del dueño del proyecto, y no vuelven solas.

QUE HABIA

    Cuatro rutas (`/api/centro-gestion/*`) que no pedían sesión: entraban con
    una clave compartida en una cabecera, para que un sistema externo leyera
    los retiros y las recargas en bolívares. Las alimentaban dos llamadas
    desde `routes/transactions.py`. Y la puerta de entrada de la API las
    dejaba pasar sin su propia clave, porque traían otra.

POR QUE HAY UN TEST DE ALGO QUE YA NO ESTA

    Una ruta que entra sin sesión es una ruta que se abre a internet. Si
    alguien restaura el archivo desde la historia de git, o copia el router
    de otra rama, tiene que enterarse acá y no en producción.

    Lo que se deja a propósito: la colección `centro_gestion_log`. La sigue
    escribiendo la configuración de encomiendas como su registro de cambios
    (`services/envios_config.py`), y el respaldo la sigue copiando. Es un
    nombre viejo, no una ruta.
"""
import os
import pathlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

_BACKEND = pathlib.Path(__file__).resolve().parent.parent


def test_NINGUNA_RUTA_DE_LA_API_ES_DE_CENTRO_GESTION():
    from routes import api_router
    rutas = [r.path for r in api_router.routes if hasattr(r, "path")]
    assert len(rutas) > 100, "no se leyeron las rutas: este test no mira lo que dice"
    vuelta = [r for r in rutas if "centro-gestion" in r or "centro_gestion" in r]
    assert not vuelta, f"volvieron rutas de centro-gestion: {vuelta}"


def test_LA_PUERTA_DE_LA_API_NO_LE_ABRE_PASO():
    """La puerta del borde deja pasar sin su clave a quien entra con otra.
    Sin las rutas, esa excepción sólo serviría para abrirle paso a lo que
    alguien vuelva a enganchar ahí."""
    from services import borde
    assert not borde.esta_exenta("/api/centro-gestion/log")


def test_NADIE_IMPORTA_LOS_MODULOS_QUITADOS():
    for quitado in ("routes/centro_gestion.py", "services/centro_gestion.py"):
        assert not (_BACKEND / quitado).exists(), f"{quitado} volvió"
    importan = []
    for archivo in _BACKEND.rglob("*.py"):
        if "tests" in archivo.parts:
            continue
        texto = archivo.read_text("utf-8", errors="ignore")
        if "routes.centro_gestion" in texto or "services.centro_gestion" in texto \
                or "import centro_gestion" in texto:
            importan.append(str(archivo.relative_to(_BACKEND)))
    assert not importan, f"estos archivos todavía importan centro_gestion: {importan}"
