"""
tests/test_saldo_en_bolivares.py — El saldo del usuario, convertido a bolivares.

QUE PASO
    La tarjeta de saldo del panel principal mostraba «Equivalente BCV de tu
    saldo» calculado como `saldo x bcvUsdVes` — o sea, multiplicando un saldo en
    RIS por la tasa del DOLAR. Trataba 1 RIS como 1 USD.

    El RIS esta denominado en REALES: `services/rate_engine.py` documenta
    `ris_to_ves` como la tasa BRL->VES, y `accounting_engine` valua la
    circulacion de RIS con esa misma tasa. Asi que el numero salia inflado por
    el factor BRL/USD, unas 5,8 veces:

        206,85 RIS x 801,18 (USD/VES) = Bs 165.723   <- lo que mostraba
        206,85 RIS x 138,00 (RIS/VES) = Bs  28.545   <- lo que vale

    No era un redondeo: era una unidad equivocada, en el numero mas grande de la
    pantalla principal, sobre el saldo de una persona.

POR QUE ESTE TEST LEE EL FUENTE
    El frontend no tiene runner de tests. Y este defecto es invisible en una
    revision —las dos variables existen, las dos son tasas, las dos son numeros
    positivos— asi que lo unico que lo distingue es CUAL de las dos se usa.

QUE NO CUBRE
    Que `ris_to_ves` valga lo correcto: eso lo fija el panel de tasas y es una
    decision de negocio. Lo que se fija aca es la UNIDAD.
"""

import os
import re

import pytest

_FRONT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend", "src"))

_TARJETA = os.path.join(_FRONT, "components", "dashboard", "BalanceCard.jsx")


def _sin_comentarios(texto: str) -> str:
    """El codigo, sin la prosa.

    Sin esto, el asterisco de una linea de JSDoc —` *   bcvUsdVes: 1 USD = X Bs`—
    parece una multiplicacion por `bcvUsdVes` y el test se dispara con su propia
    documentacion. El repo ya aprendio esto una vez, en `_cuerpo_de` de
    test_envios_config.py: un test que lee fuente tiene que leer CODIGO.
    """
    lineas = []
    for linea in texto.split("\n"):
        limpia = linea.lstrip()
        if limpia.startswith(("*", "//", "/*", "*/")):
            lineas.append("")
            continue
        # Un comentario al final de una linea de codigo.
        lineas.append(linea.split("//")[0])
    return "\n".join(lineas)


def _fuente(ruta):
    if not os.path.isfile(ruta):                              # pragma: no cover
        pytest.skip("el frontend no esta en este arbol")
    with open(ruta, encoding="utf-8") as f:
        return _sin_comentarios(f.read())


def test_el_saldo_se_convierte_con_la_tasa_RIS_y_no_con_la_del_dolar():
    """MUTACION: cambiar `animated * risToVes` por `animated * bcvUsdVes` y esto
    se pone en rojo. Es exactamente el defecto que estuvo en produccion."""
    fuente = _fuente(_TARJETA)

    # Toda multiplicacion del saldo tiene que ser por la tasa RIS.
    productos = re.findall(r"(?:animated|balance)\s*\*\s*(\w+)", fuente)
    assert productos, "cambio la forma de calcular el saldo en bolivares"
    for factor in productos:
        assert factor == "risToVes", (
            f"El saldo se esta multiplicando por `{factor}`. El saldo esta en RIS "
            f"y el RIS esta denominado en reales: la unica tasa que lo lleva a "
            f"bolivares es `risToVes` (`ris_to_ves`, que rate_engine documenta "
            f"como BRL->VES). Multiplicar por la tasa del dolar infla el numero "
            f"por el factor BRL/USD, unas 5,8 veces.")


def test_la_tasa_del_dolar_solo_se_usa_para_DIVIDIR_bolivares():
    """`bcv_usd_ves` es 1 USD = X Bs. La unica operacion valida con ella es
    dividir un monto EN BOLIVARES para obtener dolares — que es lo que hacen el
    resto de las pantallas. Multiplicar por ella algo que no esta en dolares es
    un error de unidad."""
    fuente = _fuente(_TARJETA)
    assert not re.search(r"\*\s*bcvUsdVes", fuente), (
        "Nada se multiplica por la tasa del dólar en esta tarjeta: el saldo "
        "está en RIS, no en USD.")


def test_las_demas_pantallas_dividen_bolivares_para_dar_dolares():
    """El barrido que evita que el mismo error de unidad aparezca en otra parte.

    En el resto de la app `bcv_usd_ves` aparece SIEMPRE como divisor de un monto
    en bolivares (`amount_output / rates.bcv_usd_ves`), que es correcto. Este
    test falla si alguna pantalla empieza a multiplicar por ella.
    """
    sospechosas = []
    for base, _, archivos in os.walk(_FRONT):
        for nombre in archivos:
            if not nombre.endswith((".jsx", ".js")):
                continue
            ruta = os.path.join(base, nombre)
            with open(ruta, encoding="utf-8") as f:
                texto = _sin_comentarios(f.read())
            for m in re.finditer(r"\*\s*(?:rates\??\.)?bcv_?[uU]sd_?[vV]es", texto):
                linea = texto[:m.start()].count("\n") + 1
                sospechosas.append(f"{os.path.relpath(ruta, _FRONT)}:{linea}")

    assert not sospechosas, (
        "Estas líneas MULTIPLICAN por la tasa del dólar:\n  "
        + "\n  ".join(sospechosas)
        + "\nEsa tasa es 1 USD = X Bs: solo sirve para DIVIDIR un monto en "
        "bolívares y obtener dólares. Multiplicar por ella algo que no está en "
        "dólares es el defecto que mostraba el saldo inflado 5,8 veces.")
