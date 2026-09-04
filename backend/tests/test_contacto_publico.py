"""
tests/test_contacto_publico.py — El canal de contacto sale de la configuración.

QUE PASABA

    La dirección de contacto de la empresa estaba escrita a mano en seis
    lugares del frontend: el pie de página y cinco párrafos de la página
    legal. El frontend se compila y se le sirve al navegador de CADA
    visitante, así que esa dirección viajaba dentro del bundle —se comprobó
    que estaba en el JS publicado—, lista para que la levante cualquier robot
    que lea el archivo, y sin forma de cambiarla que no fuera un despliegue.

    Peor que la exposición: cinco de esos seis lugares eran los que declaran
    CÓMO se ejerce un derecho. Los de la LGPD, la disputa de una operación y
    la baja de la cuenta. Cambiar de dirección obligaba a tocar cinco
    párrafos legales a mano, y olvidarse de uno dejaba a un usuario
    escribiéndole a una casilla muerta para pedir que le borren los datos.

QUE HAY AHORA

    `GET /api/contacto` la lee de `CONTACTO_PUBLICO`, del entorno. Se cambia
    en Railway y los seis lugares se actualizan juntos. Vacía = no se publica
    ninguna, y el frontend manda al centro de ayuda en vez de mostrar un
    "escriba a" sin destinatario.
"""
import asyncio
import importlib
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

from routes import misc                                             # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def configurar(monkeypatch):
    """Pone CONTACTO_PUBLICO y recarga `config`, como en un arranque real."""
    def _poner(valor):
        if valor is None:
            monkeypatch.delenv("CONTACTO_PUBLICO", raising=False)
        else:
            monkeypatch.setenv("CONTACTO_PUBLICO", valor)
        import config
        importlib.reload(config)
        return config
    yield _poner
    monkeypatch.delenv("CONTACTO_PUBLICO", raising=False)
    import config
    importlib.reload(config)


def test_publica_la_direccion_configurada(configurar):
    configurar("contacto@risappbr.com")

    r = corre(misc.canal_de_contacto())

    assert r["correo"] == "contacto@risappbr.com"
    assert r["hay_correo"] is True


def test_sin_configurar_no_inventa_ninguna(configurar):
    """Devolver algo por defecto sería volver a escribir una dirección en el
    código, que es exactamente lo que se sacó."""
    configurar(None)

    r = corre(misc.canal_de_contacto())

    assert r["correo"] is None
    assert r["hay_correo"] is False


def test_una_variable_vacia_cuenta_como_no_configurada(configurar):
    """Una variable puesta en blanco en Railway no puede publicarse como si
    fuera una dirección: el pie de página quedaría con un mailto: vacío."""
    configurar("   ")

    r = corre(misc.canal_de_contacto())

    assert r["correo"] is None
    assert r["hay_correo"] is False


def test_la_ruta_es_publica():
    """La lee el pie de página, que se muestra sin sesión iniciada.

    Si colgara de `get_current_user`, un visitante sin cuenta vería la página
    legal sin ninguna vía de contacto — justo el caso en que más falta hace.
    """
    from server import app

    ruta = next((r for r in app.routes
                 if getattr(r, "path", None) == "/api/contacto"), None)
    assert ruta is not None, "la ruta no quedó registrada"

    nombres = set()

    def caminar(ds):
        for d in ds or []:
            c = getattr(d, "call", None)
            if c is not None:
                nombres.add(getattr(c, "__name__", ""))
            caminar(getattr(d, "dependencies", None))

    caminar(getattr(getattr(ruta, "dependant", None), "dependencies", None))
    guards = {"get_current_user", "get_admin_user", "get_crm_user",
              "get_super_admin", "get_verified_user"}
    assert not (nombres & guards), (
        f"la ruta pide sesión ({nombres & guards}) y el pie de página se "
        f"muestra sin ella")
