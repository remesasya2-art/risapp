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


# `services/notifications.create_notification` importa `push_notifications`, que
# importa `pywebpush`. En este entorno esa dependencia no compila, y sin el stub
# TODO aviso falla — con lo cual un test de avisos verificaria el except y no el
# aviso. En produccion la libreria esta instalada.
if "pywebpush" not in sys.modules:
    _push = types.ModuleType("pywebpush")

    class _WebPushException(Exception):
        pass

    _push.WebPushException = _WebPushException
    _push.webpush = lambda *a, **k: None
    sys.modules["pywebpush"] = _push


# ─── Los archivos cuyo orden ES el test ───────────────────────────────────

def pytest_collection_modifyitems(items):
    """Devuelve al orden de definición los módulos que declaran `ORDEN_IMPORTA`.

    Casi todo el repositorio es independiente del orden, y así tiene que ser: un
    test que necesita que otro haya corrido antes es un test que miente cuando
    corre solo. Pero un recorrido end-to-end no es eso. Cotizar, confirmar,
    despachar y entregar SON un orden: es lo único que prueban. Partirlo en
    pasos independientes obligaría a rearmar el envío entero en cada uno, y ahí
    el circuito de verdad —el que junta los nueve pasos— deja de probarse.

    La alternativa era un solo test gigante. Se prefiere esto: el reporte dice
    cuál de los nueve pasos se rompió, en vez de un `assert` a mitad de camino.

    Se aplica a cualquier módulo que ponga `ORDEN_IMPORTA = True` arriba de todo,
    y no hace nada con el resto. Con `pytest-randomly` instalado, sin este gancho
    el end-to-end se desintegra: veintiún tests en rojo por `KeyError`.
    """
    fijos = {}
    for posicion, item in enumerate(items):
        modulo = getattr(item, "module", None)
        if getattr(modulo, "ORDEN_IMPORTA", False):
            fijos.setdefault(modulo.__name__, []).append((posicion, item))

    for grupo in fijos.values():
        posiciones = sorted(p for p, _ in grupo)
        # Por número de línea de la función, que es el orden en que están
        # escritos: es lo que el autor quiso decir con "en orden".
        en_orden = sorted((i for _, i in grupo),
                          key=lambda i: getattr(i.function, "__code__",
                                                None).co_firstlineno
                          if getattr(i, "function", None) else 0)
        for posicion, item in zip(posiciones, en_orden):
            items[posicion] = item
