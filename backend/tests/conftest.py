"""
Infraestructura compartida de los tests del modulo de envios.

EL PROBLEMA QUE RESUELVE
    Varios modulos del proyecto hacen `from database import db` al importarse:
    `services/idempotency.py` y `routes/envios_admin.py`, entre otros. Eso captura
    el objeto en el momento del import, asi que un test que instala su propio
    doble de Mongo en `sys.modules["database"]` se lo impone a todos los archivos
    de test que se carguen despues — y el que corre segundo trabaja contra la
    base del primero.

    Corriendo cada archivo por separado los dos pasan; juntos, quince fallan. Es
    la peor forma de este bug: aparece solo en la suite completa, que es donde
    nadie mira el detalle.

LA SOLUCION
    Un unico `database.db` que es un PROXY: no tiene datos propios, delega todo
    en el doble que el archivo de test en curso haya declarado como actual. Cada
    archivo apunta el proxy a su base en un fixture, y ninguno pisa al otro.
"""
import sys
import types


class _ProxyDeBase:
    """Delega en la base actual. Se apunta con `usar()`."""

    def __init__(self):
        self._actual = None

    def usar(self, base):
        self._actual = base
        return base

    def _requerida(self):
        if self._actual is None:
            raise RuntimeError(
                "Ningún test declaró su base. Llamá a conftest.usar_base(base) en "
                "un fixture antes de tocar código que use el `db` global.")
        return self._actual

    def __getattr__(self, nombre):
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        return getattr(self._requerida(), nombre)

    def __getitem__(self, nombre):
        return self._requerida()[nombre]


PROXY = _ProxyDeBase()


def usar_base(base):
    """Apunta el `db` global a esta base. Se llama desde un fixture."""
    return PROXY.usar(base)


if "database" not in sys.modules:
    _modulo = types.ModuleType("database")
    _modulo.db = PROXY
    sys.modules["database"] = _modulo
elif getattr(sys.modules["database"], "db", None) is None:  # pragma: no cover
    sys.modules["database"].db = PROXY
