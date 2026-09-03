"""
tests/test_saldos_crudos_guarda.py — Que no vuelva a aparecer el mismo error.

LA HISTORIA, EN TRES ACTOS

    El mismo defecto apareció TRES veces seguidas, cada una en un lugar
    distinto, y cada vez lo encontró una persona leyendo código en vez de un
    test:

      1. Seis rutas hacían `bank["balance"] + monto`.        (PR #56)
      2. Cinco sitios hacían `usuario.get("balance_ris") - monto`,
         y tres rutas de auditoría `float(u.get("balance_ris") or 0)`.
                                                             (PR #57 y #58)
      3. `/admin/accounting/balance-check` y el reporte ejecutivo hacían
         `sum(b.get("balance", 0) for b in banks)`.

    Son todos la misma frase: **aritmética sobre un campo de saldo leído crudo
    de la base**. Y todos revientan por lo mismo, ahora que los saldos se
    guardan en `Decimal128`:

        >>> Decimal128(Decimal("1000.00")) + 500.0
        TypeError
        >>> sum(...)                  # arranca en el entero 0
        TypeError: unsupported operand type(s) for +: 'int' and 'Decimal128'
        >>> round(Decimal128(Decimal("1000.00")), 2)
        TypeError: type Decimal128 doesn't define __round__ method
        >>> float(Decimal128(Decimal("1000.00")))
        TypeError

    Este archivo cierra la clase entera. No arregla un sitio: prohíbe la forma.

COMO SE MIRA
    Sobre el AST, nunca sobre el texto. Los docstrings de este proyecto citan
    código de ejemplo a propósito —`services/bancos.py` documenta las seis
    líneas que reventaban, y `kyc_quota.consume_inc` muestra un `$inc` sobre
    `balance_ris`— así que un grep encontraría «errores» dentro de comentarios
    que existen justamente para explicar el error. En el árbol, una cadena es
    una cadena.
"""
import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent

# Los campos donde vive el dinero y que hoy pueden venir en `Decimal128`.
CAMPOS_DE_SALDO = frozenset({
    "balance", "balance_ris", "balance_ris_terceros",
    "balance_usdt", "balance_usdc", "balance_ves",
})

# Las funciones que saben leer cualquiera de las formas. Pasar por una de ellas
# es lo que vuelve seguro el valor.
CONVERSORES = frozenset({
    "from_db", "to_decimal", "to_decimal128", "to_float", "quantize_money",
    "saldo_de", "to_credit_decimal", "_monto",
})

_FUENTES = sorted(
    p for p in (list(_BACKEND.glob("routes/*.py"))
                + list(_BACKEND.glob("services/*.py"))
                + [_BACKEND / "admin_routes.py", _BACKEND / "server.py"])
    if p.is_file())


def _lee_saldo_crudo(nodo):
    """¿Es `x.get("balance_ris")` o `x["balance"]`, sin conversor?"""
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) \
            and nodo.func.attr == "get" and nodo.args:
        primero = nodo.args[0]
        return isinstance(primero, ast.Constant) and primero.value in CAMPOS_DE_SALDO
    if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant):
        return nodo.slice.value in CAMPOS_DE_SALDO
    return False


ESCRITURAS = frozenset({"insert_one", "insert_many"})
OPERADORES_QUE_ESCRIBEN = frozenset({"$set", "$setOnInsert"})


def _dicts_que_se_escriben(arbol):
    """Los diccionarios que terminan guardados en la base.

    Sigue también el patrón habitual, que es el que de verdad usa el código:

        user = {...}                 <- el literal está acá
        await db.users.insert_one(user)

    Mirar sólo los literales pasados directo perdía justo ese caso, que es el
    de `routes/auth.py` creando cada usuario nuevo.
    """
    porNombre = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 \
                and isinstance(nodo.targets[0], ast.Name) \
                and isinstance(nodo.value, ast.Dict):
            porNombre[nodo.targets[0].id] = nodo.value

    def literal(arg):
        if isinstance(arg, ast.Dict):
            return [arg]
        if isinstance(arg, ast.Name) and arg.id in porNombre:
            return [porNombre[arg.id]]
        if isinstance(arg, ast.List):                 # insert_many([...])
            salida = []
            for e in arg.elts:
                salida.extend(literal(e))
            return salida
        return []

    salida = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        if _nombre(nodo) in ESCRITURAS:
            for arg in nodo.args:
                salida.extend(literal(arg))
        # {"$set": {...}} en un update: el dict de adentro es lo que se guarda
        for arg in nodo.args:
            if not isinstance(arg, ast.Dict):
                continue
            for clave, valor in zip(arg.keys, arg.values):
                if isinstance(clave, ast.Constant) \
                        and clave.value in OPERADORES_QUE_ESCRIBEN \
                        and isinstance(valor, ast.Dict):
                    salida.append(valor)
    return salida


def _crea_saldo_crudo(arbol):
    """`{"balance_ris": 0}` — un saldo que NACE en int o float.

    La otra mitad de la misma clase. El guard de arriba prohíbe LEER un saldo
    sin conversor; esto prohíbe ESCRIBIRLO crudo al crear el documento, que es
    por donde volvió a colarse: `routes/auth.py` creaba cada usuario nuevo con
    `"balance_ris": 0.0` y `admin_routes.py` cada sub-admin con
    `"balance_ris": 0`, mientras el resto de la app guarda Decimal128.

    Naciendo crudo, el tipo del saldo depende de quién creó el documento, y
    después hay que adivinar con qué te vas a encontrar en cada lectura. Es
    exactamente lo que `bancos.asegurar_cuenta` documenta desde hace tres PR:
    "naciendo en Decimal128 se evita que el tipo dependa de quién la tocó
    primero".

    Sólo mira los diccionarios que SE ESCRIBEN: el documento de un
    `insert_one`/`insert_many` y el valor de un `$set`/`$setOnInsert`. Un
    `{"balance_ris": 1}` dentro de un `find` es una PROYECCIÓN —el 1 dice
    "traeme este campo", no es un saldo— y marcarlo sería ruido que enseña a
    ignorar la guarda.

    Devuelve [(línea, campo)] de cada literal crudo.
    """
    malos = []
    for nodo in _dicts_que_se_escriben(arbol):
        for clave, valor in zip(nodo.keys, nodo.values):
            if not (isinstance(clave, ast.Constant)
                    and clave.value in CAMPOS_DE_SALDO):
                continue
            # Un número escrito a mano, con o sin signo.
            crudo = valor
            if isinstance(crudo, ast.UnaryOp) and isinstance(crudo.op, ast.USub):
                crudo = crudo.operand
            if isinstance(crudo, ast.Constant) and isinstance(crudo.value, (int, float)) \
                    and not isinstance(crudo.value, bool):
                malos.append((clave.lineno, clave.value))
    return malos


def _nombre(llamada):
    fn = llamada.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def _protegido(cadena_de_padres):
    """¿Algún padre cercano es uno de los conversores?"""
    for padre in cadena_de_padres[:4]:
        if isinstance(padre, ast.Call) and _nombre(padre) in CONVERSORES:
            return True
    return False


def _padres_de(arbol):
    mapa = {}
    for padre in ast.walk(arbol):
        for hijo in ast.iter_child_nodes(padre):
            mapa[hijo] = padre
    return mapa


def _cadena(mapa, nodo):
    salida = []
    while nodo in mapa:
        nodo = mapa[nodo]
        salida.append(nodo)
    return salida


def _recorrer():
    """Devuelve (archivo, línea, forma) por cada uso peligroso."""
    for ruta in _FUENTES:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        mapa = _padres_de(arbol)
        for nodo in ast.walk(arbol):
            # a) sumas y restas: `bank["balance"] + monto`
            if isinstance(nodo, ast.BinOp) and isinstance(
                    nodo.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                for lado in (nodo.left, nodo.right):
                    if _lee_saldo_crudo(lado) and not _protegido(_cadena(mapa, lado)):
                        yield ruta, nodo.lineno, "aritmética"
            # b) comparaciones: `saldo >= monto` sin normalizar los dos lados
            if isinstance(nodo, ast.Compare):
                for lado in [nodo.left, *nodo.comparators]:
                    if _lee_saldo_crudo(lado) and not _protegido(_cadena(mapa, lado)):
                        # `is None` / `is not None` son chequeos de presencia y
                        # no tocan el número: son seguros y muy comunes.
                        if not all(isinstance(op, (ast.Is, ast.IsNot))
                                   for op in nodo.ops):
                            yield ruta, nodo.lineno, "comparación"
            # c) builtins que no saben de Decimal128: sum, round, float, abs
            if isinstance(nodo, ast.Call) and _nombre(nodo) in (
                    "sum", "round", "float", "abs", "min", "max"):
                try:
                    texto = ast.unparse(nodo)
                except Exception:                                # pragma: no cover
                    continue
                toca = any(f'"{c}"' in texto or f"'{c}'" in texto
                           for c in CAMPOS_DE_SALDO)
                if toca and not any(s in texto for s in CONVERSORES):
                    yield ruta, nodo.lineno, f"{_nombre(nodo)}()"


def test_nadie_hace_aritmetica_sobre_un_saldo_crudo():
    """LA GUARDA. Si alguien vuelve a escribir la forma, esto lo grita."""
    hallazgos = sorted(set(_recorrer()))
    detalle = "\n  ".join(
        f"{r.relative_to(_BACKEND)}:{l}  ({k})" for r, l, k in hallazgos)
    assert hallazgos == [], (
        "hay operaciones sobre un campo de saldo leído crudo de la base:\n  "
        + detalle
        + "\n\nLos saldos se guardan en Decimal128 y estas operaciones son un "
          "TypeError. Leelo con `services.bancos.saldo_de`, "
          "`services.saldos.saldo_de` o `services.money.from_db` antes de "
          "operarlo.")


def test_ningun_saldo_NACE_en_int_o_float():
    """La otra mitad: prohibir que un saldo se cree crudo, no sólo leerlo."""
    hallazgos = []
    for archivo in _FUENTES:
        try:
            arbol = ast.parse(archivo.read_text())
        except SyntaxError:                                   # pragma: no cover
            continue
        for linea, campo in _crea_saldo_crudo(arbol):
            hallazgos.append(f"{archivo.name}:{linea}  {campo}")
    assert not hallazgos, (
        "Estos documentos nacen con el saldo en int o float, mientras el resto "
        "de la app lo guarda en Decimal128. Así el tipo del saldo depende de "
        "quién creó el documento.\n  " + "\n  ".join(hallazgos) +
        "\n\nUsá to_decimal128(0).")


def test_LA_GUARDA_DE_NACIMIENTO_SE_PONE_EN_ROJO(tmp_path):
    """Una guarda que no se puede romper no guarda nada."""
    def mira(fuente):
        return _crea_saldo_crudo(ast.parse(textwrap.dedent(fuente)))

    assert mira('db.users.insert_one({"balance_ris": 0, "email": "a@b.c"})') \
        == [(1, "balance_ris")]
    assert mira('db.users.insert_one({"balance_usdt": 0.0})') \
        == [(1, "balance_usdt")]
    assert mira('db.x.insert_one({"balance": -5})') == [(1, "balance")]
    assert mira('db.x.insert_many([{"balance_ris": 0}])') == [(1, "balance_ris")]
    # El patrón habitual: el literal en una variable y el insert más abajo.
    assert mira("""
        user = {"email": "a@b.c", "balance_ris": 0.0}
        db.users.insert_one(user)
    """) == [(2, "balance_ris")]
    assert mira('db.x.update_one(f, {"$set": {"balance_ris": 0}})') \
        == [(1, "balance_ris")]
    assert mira('db.x.update_one(f, {"$setOnInsert": {"balance_ris": 0}})') \
        == [(1, "balance_ris")]

    # Lo que NO tiene que marcar:
    assert mira('db.x.insert_one({"balance_ris": to_decimal128(0)})') == []
    # una proyección: el 1 dice "traeme el campo", no es un saldo
    assert mira('db.x.find({}, {"_id": 0, "balance_ris": 1})') == []
    # un campo que no es de saldo
    assert mira('db.x.insert_one({"intentos": 0})') == []
    # `True` es un int en Python, pero no es un saldo escrito a mano
    assert mira('db.x.insert_one({"balance_ris": True})') == []
    # un `$inc`, que suma sobre lo que ya hay: no crea el tipo
    assert mira('db.x.update_one(f, {"$inc": {"balance_ris": 5}})') == []


def test_la_guarda_de_verdad_encuentra_las_formas_que_reventaban():
    """Que el escáner no esté pasando por vacío.

    Se le da el código EXACTO que había en cada uno de los tres actos y se
    exige que los encuentre. Sin esto, un error en el recorrido dejaría la
    guarda en verde para siempre sin que nadie lo note.
    """
    import os
    import tempfile

    casos = {
        "aritmética": 'def f(bank, monto):\n    return bank["balance"] + monto\n',
        "resta": 'def f(u, m):\n    return u.get("balance_ris") - m\n',
        "sum()": 'def f(banks):\n    return sum(b.get("balance", 0) for b in banks)\n',
        "round()": 'def f(b):\n    return round(b.get("balance", 0), 2)\n',
        "float()": 'def f(u):\n    return float(u.get("balance_ris") or 0)\n',
        "comparación": 'def f(b, m):\n    return b["balance"] >= m\n',
    }
    global _FUENTES
    guardadas = _FUENTES
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            for nombre, codigo in casos.items():
                archivo = Path(carpeta) / "caso.py"
                archivo.write_text(codigo, encoding="utf-8")
                _FUENTES = [archivo]
                encontrado = list(_recorrer())
                assert encontrado, (
                    f"el escáner NO encuentra la forma «{nombre}»:\n{codigo}")
    finally:
        _FUENTES = guardadas
        assert os.path.exists(_BACKEND)


def test_la_guarda_no_marca_el_codigo_ya_arreglado():
    """Y que no sea un escáner que grita con todo: las formas correctas pasan."""
    import tempfile

    seguras = [
        'def f(b):\n    return from_db(b.get("balance")) + 1\n',
        'def f(b):\n    return to_float(from_db(b["balance"]))\n',
        'def f(bs):\n    return sum(saldo_de(b) for b in bs)\n',
        'def f(b):\n    if b.get("balance") is not None:\n        return 1\n',
        'def f(u):\n    return to_decimal(u.get("balance_ris")) - 5\n',
    ]
    global _FUENTES
    guardadas = _FUENTES
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            for codigo in seguras:
                archivo = Path(carpeta) / "seguro.py"
                archivo.write_text(codigo, encoding="utf-8")
                _FUENTES = [archivo]
                assert list(_recorrer()) == [], (
                    f"el escáner marca código correcto:\n{codigo}")
    finally:
        _FUENTES = guardadas


def test_un_docstring_que_cita_el_error_no_cuenta_como_error():
    """`services/bancos.py` documenta las seis líneas que reventaban.

    Un grep las contaría como defectos vivos. El AST no: dentro de un string,
    `bank["balance"] + amount_ves` es texto.
    """
    import tempfile
    codigo = textwrap.dedent('''
        """Documenta el error que se arregló:

            routes/admin.py:1821   bank["balance"] + amount_ves
            sum(b.get("balance", 0) for b in banks)
            float(u.get("balance_ris") or 0)
        """
        def f(b):
            return from_db(b.get("balance"))
    ''')
    global _FUENTES
    guardadas = _FUENTES
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "docstring.py"
            archivo.write_text(codigo, encoding="utf-8")
            _FUENTES = [archivo]
            assert list(_recorrer()) == []
    finally:
        _FUENTES = guardadas


@pytest.mark.parametrize("expresion, error", [
    ('Decimal128(Decimal("1000.00")) + 500.0', "TypeError"),
    ('sum(x for x in [Decimal128(Decimal("1.00"))])', "TypeError"),
    ('round(Decimal128(Decimal("1000.00")), 2)', "TypeError"),
    ('float(Decimal128(Decimal("1000.00")))', "TypeError"),
])
def test_las_formas_prohibidas_revientan_de_verdad(expresion, error):
    """En un intérprete limpio: `conftest` le enseña aritmética a Decimal128
    para que mongomock funcione, y ese parche taparía justo esto.

    Si alguna de estas deja de fallar, el test avisa: puede que la guarda ya no
    haga falta para esa forma.
    """
    guion = textwrap.dedent(f"""
        from decimal import Decimal
        from bson.decimal128 import Decimal128
        try:
            {expresion}
        except {error}:
            print("REVIENTA")
        else:
            raise SystemExit("ya no revienta: revisar la guarda para esta forma")
    """)
    proceso = subprocess.run([sys.executable, "-c", guion],
                             capture_output=True, text=True)
    assert proceso.returncode == 0, proceso.stderr
    assert "REVIENTA" in proceso.stdout


# ══════════════════════════════════════════════════════════════════════════
# Y los dos sitios concretos, ejercitados de verdad
# ══════════════════════════════════════════════════════════════════════════
#
# La guarda de arriba prohíbe la forma; estos comprueban que las dos rutas que
# la tenían devuelven el número correcto con el saldo guardado de las dos
# maneras que conviven hoy en la base.

import asyncio                                                      # noqa: E402
import os                                                           # noqa: E402
import types                                                        # noqa: E402
from decimal import Decimal                                         # noqa: E402

from bson.decimal128 import Decimal128                              # noqa: E402

sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base     # noqa: E402
ensenarle_decimal128_a_mongomock()


def _cargar_accounting():
    """Sin arrastrar el paquete `routes`, que importa el motor contable."""
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(str(_BACKEND), "routes")]
        sys.modules["routes"] = paquete
    if "routes.dependencies" not in sys.modules:
        deps = types.ModuleType("routes.dependencies")
        for nombre in ("get_current_user", "get_admin_user", "get_crm_user",
                       "get_super_admin", "get_verified_user"):
            setattr(deps, nombre, (lambda n: (lambda: None))(nombre))
        sys.modules["routes.dependencies"] = deps
    import routes.accounting as acc
    return acc


class _Super:
    user_id = "usr_super"
    email = "super@risappbr.com"
    role = "super_admin"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


GUARDADO_COMO = [
    pytest.param(lambda x: float(x), id="float"),
    pytest.param(lambda x: Decimal128(Decimal(str(x))), id="Decimal128"),
]


@pytest.mark.parametrize("como", GUARDADO_COMO)
def test_balance_check_suma_bien_y_no_revienta(base, como):
    acc = _cargar_accounting()

    async def caso():
        await base.bank_accounts.insert_many([
            {"bank_id": "b1", "name": "Banco Uno", "currency": "VES",
             "balance": como(1500.50)},
            {"bank_id": "b2", "name": "Banco Dos", "currency": "VES",
             "balance": como(2000)},
            {"bank_id": "b3", "name": "Banco Tres", "currency": "BRL",
             "balance": como(9999)},
        ])
        r = await acc.check_balance(currency="ves", amount=3000, admin=_Super())
        assert r["currency"] == "VES"
        assert r["total_balance"] == 3500.50
        assert r["required"] == 3000.0
        assert r["sufficient"] is True
        assert len(r["banks"]) == 2          # el BRL no entra
        assert {b["balance"] for b in r["banks"]} == {1500.50, 2000.0}
    asyncio.run(caso())


@pytest.mark.parametrize("como", GUARDADO_COMO)
def test_balance_check_dice_que_no_alcanza_cuando_no_alcanza(base, como):
    acc = _cargar_accounting()

    async def caso():
        await base.bank_accounts.insert_one(
            {"bank_id": "b1", "name": "Banco", "currency": "VES",
             "balance": como(100)})
        r = await acc.check_balance(currency="VES", amount=100.01, admin=_Super())
        assert r["sufficient"] is False
    asyncio.run(caso())


def test_balance_check_con_el_monto_justo_alcanza(base):
    """El borde: pedir exactamente lo que hay tiene que alcanzar.

    Comparado en float, 0.1+0.2 >= 0.3 es False. En Decimal es True, y es la
    diferencia entre pagarle a alguien y decirle que no hay plata.
    """
    acc = _cargar_accounting()

    async def caso():
        await base.bank_accounts.insert_many([
            {"bank_id": "b1", "name": "A", "currency": "VES",
             "balance": Decimal128(Decimal("0.10"))},
            {"bank_id": "b2", "name": "B", "currency": "VES",
             "balance": Decimal128(Decimal("0.20"))},
        ])
        r = await acc.check_balance(currency="VES", amount=0.30, admin=_Super())
        assert r["total_balance"] == 0.30
        assert r["sufficient"] is True
    asyncio.run(caso())


def test_balance_check_sin_cuentas_da_cero(base):
    acc = _cargar_accounting()

    async def caso():
        r = await acc.check_balance(currency="VES", amount=10, admin=_Super())
        assert r["total_balance"] == 0.0
        assert r["sufficient"] is False
        assert r["banks"] == []
    asyncio.run(caso())
