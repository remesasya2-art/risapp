"""
tests/test_cada_orden_tiene_un_numero.py — Que la orden se pueda nombrar.

QUE PASABA ANTES

    El historial del cliente mostraba nombre, fecha y monto. Nada que NOMBRARA
    la operación. Cuando alguien escribía «pagué y no me aparece», ni el
    cliente ni quien lo atendía tenían un número que decirse: había que
    adivinar cuál de los envíos del día era, por el monto y la hora.

    El número existía: el backend lo guarda en `display_id` y lo manda —está
    en `LO_QUE_VE_EL_CLIENTE`—. Lo que faltaba era pintarlo. Y faltaba, además,
    en UNA de las órdenes: la recarga en bolívares era la única que no le pedía
    número al contador.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que toda orden que entra al historial salga con número.
    2. Que la pantalla del cliente lo muestre.
"""
import os
import pathlib
import re
import sys

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_HISTORIAL = (_BACKEND.parent / "frontend" / "src" / "components" /
              "dashboard" / "TransactionItem.jsx")


# ══════════════════════════════════════════════════════════════════════════
# 1. El servidor le pone número a todas
# ══════════════════════════════════════════════════════════════════════════

def _rutas() -> str:
    return (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")


def _cuerpo(nombre: str) -> str:
    """El cuerpo de una función, hasta la siguiente de primer nivel."""
    fuente = _rutas()
    i = fuente.index(f"async def {nombre}(")
    resto = fuente[i:]
    corte = re.search(r"\n@router\.", resto)
    return resto[:corte.start()] if corte else resto


def test_LA_RECARGA_EN_BOLIVARES_TAMBIEN_LLEVA_NUMERO():
    """Era la única orden del historial sin `display_id`. Todas las demás se
    lo piden al mismo contador."""
    cuerpo = _cuerpo("recharge_ves")
    assert "display_id = await get_next_withdrawal_id()" in cuerpo, (
        "la recarga en bolívares volvió a quedarse sin número")
    assert '"display_id": display_id,' in cuerpo, (
        "se pide el número pero no se guarda en la orden")


def test_NINGUNA_ORDEN_QUEDA_SIN_NUMERO():
    """La guarda de verdad: recorre TODOS los diccionarios de este archivo que
    nombran una orden (`"transaction_id": tx_id`) —los que se guardan y los
    que se le contestan al cliente— y exige que cada uno traiga `display_id`.

    Se escribe así, y no nombrando las rutas de a una, porque el modo de
    fallar es agregar una ruta nueva — y una lista de nombres no se entera.
    """
    fuente = _rutas()
    mirados, sin_numero = 0, []
    for m in re.finditer(r"\n(\s*)(\w+) = \{\n(.*?)\n\1\}", fuente, re.S):
        bloque = m.group(0)
        if '"transaction_id": tx_id,' not in bloque:
            continue
        mirados += 1
        if '"display_id"' not in bloque:
            sin_numero.append(fuente[:m.start()].count("\n") + 1)
    # Sin esto la guarda se vuelve muda el día que cambie la forma de escribir
    # un diccionario: no encontraría ninguno y pasaría igual.
    assert mirados >= 13, (
        f"la guarda sólo encontró {mirados} órdenes: dejó de ver el archivo")
    assert not sin_numero, (
        "hay órdenes sin número, en las líneas: "
        + ", ".join(str(n) for n in sin_numero))


# ══════════════════════════════════════════════════════════════════════════
# 2. La pantalla lo muestra
# ══════════════════════════════════════════════════════════════════════════

def test_EL_HISTORIAL_MUESTRA_EL_NUMERO():
    pantalla = _HISTORIAL.read_text(encoding="utf-8")
    assert "tx.display_id" in pantalla, (
        "el historial dejó de leer el número de la orden")
    # Las dos formas de la fila: la corta del panel del cliente y la larga del
    # historial completo. Que una lo muestre y la otra no es el error fácil.
    assert pantalla.count("numero-tx-") == 2, (
        f"el número aparece en {pantalla.count('numero-tx-')} de las dos "
        f"formas de la fila")


def test_el_respaldo_corta_el_identificador_por_el_FINAL():
    """Por el principio salen todas iguales: `tx_`, `rech_` es el tipo, no la
    orden."""
    pantalla = _HISTORIAL.read_text(encoding="utf-8")
    assert ".slice(-8)" in pantalla, (
        "el respaldo del número corta por el principio: todas las órdenes del "
        "mismo tipo quedarían con el mismo «número»")
