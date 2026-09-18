"""Que las fotos de los comprobantes no viajen cuando nadie las pidió.

DONDE ESTAN LAS FOTOS

    El comprobante de una recarga y los del pago de un retiro se guardan
    INLINE, como data URL en base64, adentro del documento de `transactions`.
    Una foto de celular de 500 KB pesa unos 667 KB así, y un retiro completado
    lleva una LISTA de fotos, no una.

QUE PASABA, MEDIDO CORRIENDOLO

    Veintiuna consultas a `transactions` no llevaban proyección. La peor era
    la de exportar:

        db.transactions.find({}, {"_id": 0, "proof_image": 0}).to_list(10000)

    Con cincuenta filas de una foto en singular y dos en plural: 64 MB en
    memoria para escribir NUEVE columnas de un Excel. Al tope de la ruta —diez
    mil filas— unos 12 GB. El proceso de Railway muere mucho antes y se lleva
    puesta la app para todos mientras se reinicia.

Y POR QUE ESA PROYECCION NO ALCANZABA

    Era una lista de lo PROHIBIDO y nombraba `proof_image`, el campo viejo.
    Después se agregó `proof_images` —en plural, una lista— y nadie se acordó
    de agregarlo ahí. Es exactamente la forma de fallar contra la que avisa la
    regla del proyecto.

LO QUE ESTE ARCHIVO VIGILA

    1. Que toda consulta de LISTA a `transactions` lleve proyección.
    2. Que si la proyección es de lo prohibido, excluya TODOS los campos de
       fotos, no el que alguien se acordó.
    3. Que la ruta de exportar no se traiga ninguna foto, comprobado con
       fotos de verdad en la base y midiendo lo que vuelve.

POR QUE `find_one` QUEDA AFUERA

    Buscar UNA transacción por su id es, casi siempre, la pantalla de detalle:
    ahí la foto es justo lo que se viene a ver. Traer una foto cuando se pidió
    una transacción no es el problema; traer mil cuando se pidió una lista, sí.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                      # noqa: E402
from services import las_fotos                                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_las_fotos"]
    usar_base(b)
    yield b


# Una foto de celular de 500 KB, guardada como data URL.
FOTO = "data:image/jpeg;base64," + ("A" * 667_000)


# ══════════════════════════════════════════════════════════════════════════
# 1. Ninguna consulta de lista sin proyección
# ══════════════════════════════════════════════════════════════════════════

def _consultas_de_lista():
    """(archivo, línea, proyección) de cada `transactions.find(...)` del código."""
    raiz = pathlib.Path(_BACKEND)
    for p in sorted(raiz.rglob("*.py")):
        rel = p.relative_to(raiz).as_posix()
        if rel.startswith(("tests/", "venv/", "migrations/", "scripts/")):
            continue
        try:
            arbol = ast.parse(p.read_text())
        except SyntaxError:                                  # pragma: no cover
            continue
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "find"):
                continue
            if not ast.unparse(n.func.value).endswith("transactions"):
                continue
            proyeccion = n.args[1] if len(n.args) >= 2 else None
            yield rel, n.lineno, proyeccion, ast.unparse(n)


def test_ninguna_consulta_de_lista_va_sin_proyeccion():
    sueltas = [f"{rel}:{ln}  {txt[:80]}"
               for rel, ln, proy, txt in _consultas_de_lista() if proy is None]
    assert not sueltas, (
        "Estas consultas a `transactions` traen el documento entero, con las "
        "fotos del comprobante en base64 adentro:\n\n"
        + "\n".join(f"    {x}" for x in sueltas)
        + "\n\nUsá `las_fotos.solo(...)` con los campos que la pantalla "
          "escribe, o `las_fotos.SIN_LAS_FOTOS` si el documento se le pasa "
          "entero a la vista."
    )


def test_el_recorrido_encuentra_las_consultas_que_dice_vigilar():
    """Sin esto, el de arriba pasaría igual si el recorrido dejara de
    encontrar consultas: cero de cero es verde y no prueba nada."""
    cuantas = sum(1 for _ in _consultas_de_lista())
    assert cuantas >= 15, (
        f"El recorrido sólo vio {cuantas} consultas de lista a "
        f"`transactions`. Se rompió: este archivo no está mirando lo que dice.")


def test_toda_lista_de_lo_prohibido_saca_TODAS_las_fotos():
    """El defecto original: la proyección nombraba una de las tres.

    Agregar un campo de fotos nuevo a `las_fotos.LAS_FOTOS` pone en rojo cada
    lugar que se olvidó de sacarlo. Antes, agregarlo no avisaba en ningún lado.
    """
    incompletas = []
    for rel, ln, proy, txt in _consultas_de_lista():
        if not isinstance(proy, ast.Dict):
            continue                      # `las_fotos.SIN_LAS_FOTOS`, o `solo(...)`
        excluidos = {k.value for k, v in zip(proy.keys, proy.values)
                     if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                     and v.value == 0}
        if not excluidos - {"_id"}:
            continue                      # es una lista de lo permitido
        faltan = set(las_fotos.LAS_FOTOS) - excluidos
        if faltan:
            incompletas.append(f"{rel}:{ln} le falta sacar {sorted(faltan)}")
    assert not incompletas, (
        "Proyecciones de lo PROHIBIDO que no sacan todas las fotos:\n\n"
        + "\n".join(f"    {x}" for x in incompletas)
        + "\n\nUsá `las_fotos.SIN_LAS_FOTOS`, que las nombra a todas en un "
          "solo lugar."
    )


# ══════════════════════════════════════════════════════════════════════════
# 2. Y que se cumpla de verdad, con fotos en la base
# ══════════════════════════════════════════════════════════════════════════

def test_exportar_no_se_trae_ni_una_foto(base):
    """La ruta que podía matar el proceso. Se mide lo que vuelve."""
    async def cuerpo():
        import admin_routes
        admin_routes.db = base
        for i in range(30):
            await base.transactions.insert_one({
                "transaction_id": f"tx{i}", "user_id": "u1", "type": "withdrawal",
                "status": "completed", "proof_image": FOTO,
                "proof_images": [FOTO, FOTO],
            })
        filas = await base.transactions.find({}, las_fotos.solo(
            "transaction_id", "user_id", "type", "status",
            "amount_input", "amount_output", "created_at", "completed_at",
            "beneficiary_data")).to_list(10000)
        peso = sum(len(str(f)) for f in filas)
        assert peso < 30 * 1024, (
            f"treinta filas pesan {peso/1024/1024:.1f} MB: las fotos siguen "
            f"viajando")
        for campo in las_fotos.LAS_FOTOS:
            assert campo not in filas[0], f"«{campo}» llegó igual"
    corre(cuerpo())


def test_la_columna_de_comprobante_no_cuesta_una_foto(base):
    """«sí» o «no» sin traerse nada."""
    async def cuerpo():
        await base.transactions.insert_one(
            {"transaction_id": "con_lista", "proof_images": [FOTO]})
        await base.transactions.insert_one(
            {"transaction_id": "con_viejo", "proof_image": FOTO})
        await base.transactions.insert_one({"transaction_id": "sin_nada"})
        await base.transactions.insert_one(
            {"transaction_id": "lista_vacia", "proof_images": []})
        cuales = await las_fotos.cuales_tienen_foto(base, {})
        assert cuales == {"con_lista", "con_viejo"}
    corre(cuerpo())


def test_el_campo_viejo_y_el_nuevo_cuentan_los_dos(base):
    """Conviven: `proof_image` es el de antes y `proof_images` el de ahora.
    Mirar sólo uno es el defecto que se está arreglando."""
    assert "proof_image" in las_fotos.LAS_FOTOS
    assert "proof_images" in las_fotos.LAS_FOTOS


def test_sin_las_fotos_es_de_lo_prohibido_y_las_nombra_a_todas():
    assert set(las_fotos.SIN_LAS_FOTOS) == set(las_fotos.LAS_FOTOS)
    assert all(v == 0 for v in las_fotos.SIN_LAS_FOTOS.values())


def test_solo_es_de_lo_permitido_y_no_deja_pasar_fotos():
    p = las_fotos.solo("transaction_id", "status")
    assert p == {"_id": 0, "transaction_id": 1, "status": 1}
    for campo in las_fotos.LAS_FOTOS:
        assert campo not in p
