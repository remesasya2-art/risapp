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


# ─── Decimal128 para los tests que mueven saldo ───────────────────────────

def ensenarle_decimal128_a_mongomock():
    """Compartida: la usan el e2e de envios y los tests de recarga VES.

    Vive aca y no en un archivo de test porque el saldo en `Decimal128` es una
    propiedad de TODA la app, no del modulo de envios: cualquier test que
    acredite o debite plata contra mongomock la necesita. Es idempotente y NO se
    aplica sola — cada archivo la llama, para que ningun test cambie de
    comportamiento sin haberlo pedido.

    ES UNA LIMITACION DE MONGOMOCK, NO DEL PRODUCTO, y por eso se arregla acá y
    no allá. El saldo
    se guarda como `Decimal128` —así lo guarda el resto de la app— y el débito
    atómico hace dos cosas con él que el servidor de verdad resuelve sin
    pestañear:

        {"balance_ris": {"$gte": Decimal128(monto)}}     comparar
        {"$inc": {"balance_ris": Decimal128(-monto)}}    sumar

    Mongomock levanta "'>=' not supported" en la primera y "unsupported operand
    type(s) for +" en la segunda. Sin esto el guard del débito falla SIEMPRE, y
    el E2E daría por bueno un mundo donde ningún cobro se puede pagar — que es
    peor que no probarlo.

    Se le enseña al TIPO, no a mongomock: `bson.Decimal128` es Python puro, y
    darle aritmética y orden es exactamente lo que hace el servidor. Sale una
    línea por operación en vez de tres parches contra los internos de una
    librería de tests.

    Y que quede escrito, porque es lo que este archivo vino a hacer visible:
    **el cobro del módulo depende de que la base sume y ordene `Decimal128`.**
    Es un requisito real sobre MongoDB, y no había un solo test que lo dijera.
    """
    from decimal import Decimal
    from bson.decimal128 import Decimal128

    def valor(x):
        if isinstance(x, Decimal128):
            return x.to_decimal()
        if isinstance(x, float):
            return Decimal(str(x))
        if isinstance(x, (int, Decimal)):
            return Decimal(x)
        return None

    def binaria(nombre, operacion, invertida=False):
        def metodo(self, otro):
            a, b = valor(self), valor(otro)
            if a is None or b is None:
                return NotImplemented
            resultado = operacion(b, a) if invertida else operacion(a, b)
            return (Decimal128(resultado) if isinstance(resultado, Decimal)
                    else resultado)
        metodo.__name__ = nombre
        return metodo

    # Se aplica UNA vez. pytest importa todos los módulos de test en la
    # colección, así que sin esta guarda una segunda importación anidaría
    # lambdas sobre `_get_compare_type`.
    if getattr(Decimal128, "_ris_app_parchado", False):
        return
    Decimal128._ris_app_parchado = True

    import operator as op
    for nombre, fn in (("__add__", op.add), ("__sub__", op.sub),
                       ("__mul__", op.mul), ("__truediv__", op.truediv),
                       ("__lt__", op.lt), ("__le__", op.le),
                       ("__gt__", op.gt), ("__ge__", op.ge)):
        setattr(Decimal128, nombre, binaria(nombre, fn))
    for nombre, fn in (("__radd__", op.add), ("__rsub__", op.sub),
                       ("__rmul__", op.mul)):
        setattr(Decimal128, nombre, binaria(nombre, fn, invertida=True))

    # Y el orden de tipos: `Decimal128` es un número y va en el mismo grupo, que
    # es lo que hace que el type bracketing de Mongo no lo descarte contra un int.
    import mongomock.filtering as filtrado
    original_tipo = filtrado._get_compare_type
    filtrado._get_compare_type = (
        lambda val: 10 if isinstance(val, Decimal128) else original_tipo(val))

    # LO QUE ESTE PARCHE NO HACE, a propósito: `__eq__`. El que trae `bson`
    # compara la representación binaria, así que `Decimal128("2.00")` no es
    # igual a `Decimal128("2.0")` aunque ahora `<=` y `>=` digan que sí. MongoDB
    # resuelve las dos numéricamente. Se deja como está porque ninguna query del
    # módulo hace `$eq` ni `$in` sobre un monto —el débito compara con `$gte` y
    # suma con `$inc`, y todo lo demás pasa por `services/money.py`, que
    # convierte a `Decimal` antes de tocar nada—. Si alguien escribe esa query,
    # que la escriba con este comentario a la vista: acá el E2E daría verde
    # sobre un comportamiento que producción no tiene.
