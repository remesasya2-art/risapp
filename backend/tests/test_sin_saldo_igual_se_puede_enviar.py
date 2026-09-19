"""
tests/test_sin_saldo_igual_se_puede_enviar.py

POR QUE EXISTE ESTE ARCHIVO

    Corriendo la aplicación con saldo cero y el pago al final prendido, el
    botón «Continuar» del primer paso del envío estaba APAGADO. Y el mismo
    valor que lo apagaba apagaba también «Pagar con PIX» en el último paso —el
    botón que existe justamente para no necesitar saldo.

    O sea: la única forma de enviar sin saldo era inalcanzable para quien no
    tenía saldo. Exactamente al revés de para qué se escribió.

    El servidor nunca tuvo ese problema: la ruta que cotiza no mira
    `balance_ris`. El bloqueo era sólo de la pantalla, y estaba en LAS DOS
    —Venezuela y Brasil—, porque las dos mezclaban las mismas dos preguntas.

    Ningún test lo vio porque todos le pasaban saldo de sobra. Apareció
    mirando la pantalla, igual que las dos puertas de `PuertaCripto`.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que con otra vía de pago prendida, el saldo NO frene el paso del monto.
    2. Que sin otra vía, el saldo SI lo frene — que es lo que le ahorra a
       alguien completar cuatro pantallas para nada.
    3. Que se pueda preguntar por el saldo aparte, para el último paso.
    4. Que nadie pueda olvidarse de decir cuál de los dos casos es.

    La lógica se EJECUTA con node, no se lee buscando texto: eso comprueba que
    algo está escrito, no que funcione.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                # noqa: E402,F401

VENEZUELA = os.path.join(_RAIZ, "frontend", "src", "utils", "envioAVenezuela.js")
BRASIL = os.path.join(_RAIZ, "frontend", "src", "utils", "envioABrasil.js")
PANTALLA_VE = os.path.join(_RAIZ, "frontend", "src", "pages", "Send.jsx")
PANTALLA_BR = os.path.join(_RAIZ, "frontend", "src", "pages", "SendReais.jsx")

_node = shutil.which("node")


def _correr(modulo, expresion):
    if not _node:
        pytest.skip("node no está instalado: la lógica de la pantalla no corre")
    codigo = (f"import * as m from {json.dumps('file://' + modulo)};\n"
              f"console.log(JSON.stringify(({expresion})));\n")
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"node falló:\n{r.stderr}")
    return json.loads(r.stdout.strip())


def _tira(modulo, expresion):
    """¿La expresión lanza un error? Para la guarda del parámetro olvidado."""
    if not _node:
        pytest.skip("node no está instalado")
    codigo = (f"import * as m from {json.dumps('file://' + modulo)};\n"
              f"({expresion});\n")
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    return r.returncode != 0


# ══════════════════════════════════════════════════════════════════════════
# 1. EL DEFECTO. Con otra vía prendida, sin saldo se sigue.
# ══════════════════════════════════════════════════════════════════════════

def test_VENEZUELA_sin_saldo_y_con_pago_al_final_SE_PUEDE_CONTINUAR():
    """El test que no existía cuando el botón quedó apagado."""
    v = _correr(VENEZUELA,
                "m.validarMonto({ris: 50, saldo: 0, tasaDisponible: true,"
                " escribioAlgo: true, saldoEsLaUnicaVia: false})")
    assert v["ok"] is True, (
        "con saldo cero y el pago al final prendido, la pantalla frena en el "
        "paso del monto: el que no tiene saldo no llega nunca al botón que no "
        "le pide saldo.")


def test_BRASIL_sin_saldo_y_con_pago_al_final_SE_PUEDE_CONTINUAR():
    p = _correr(BRASIL,
                "m.validarMonto({monto: 500, saldo: 0,"
                " limites: {pix: {min_brl: 10, max_brl: 5000}}, cupo: null,"
                " saldoEsLaUnicaVia: false})")
    assert p is None, f"frenó con «{p}» habiendo otra vía de pago prendida"


def test_lo_que_NO_es_el_saldo_sigue_frenando_igual():
    """Separar las dos preguntas no es dejar pasar cualquier cosa. El monto
    en cero, el negativo y la falta de tasa frenan con o sin otra vía."""
    casos = [
        ("{ris: 0, saldo: 0, tasaDisponible: true, escribioAlgo: true,"
         " saldoEsLaUnicaVia: false}", "no_positivo"),
        ("{ris: -3, saldo: 0, tasaDisponible: true, escribioAlgo: true,"
         " saldoEsLaUnicaVia: false}", "no_positivo"),
        ("{ris: 50, saldo: 0, tasaDisponible: false, escribioAlgo: true,"
         " saldoEsLaUnicaVia: false}", "sin_tasa"),
        ("{ris: null, saldo: 0, tasaDisponible: true, escribioAlgo: false,"
         " saldoEsLaUnicaVia: false}", "vacio"),
    ]
    for entrada, esperado in casos:
        v = _correr(VENEZUELA, f"m.validarMonto({entrada})")
        assert v["ok"] is False and v["motivo"] == esperado, (
            f"{entrada} dio {v}: separar el saldo se llevó puesta otra guarda")


def test_BRASIL_los_limites_siguen_frenando_sin_saldo():
    """El mínimo y el máximo de la vía no son el saldo: valen igual."""
    lim = "{pix: {min_brl: 10, max_brl: 5000}}"
    bajo = _correr(BRASIL, f"m.validarMonto({{monto: 5, saldo: 0,"
                           f" limites: {lim}, cupo: null,"
                           f" saldoEsLaUnicaVia: false}})")
    alto = _correr(BRASIL, f"m.validarMonto({{monto: 9000, saldo: 0,"
                           f" limites: {lim}, cupo: null,"
                           f" saldoEsLaUnicaVia: false}})")
    assert bajo and "mínimo" in bajo.lower()
    assert alto and "máximo" in alto.lower()


def test_BRASIL_el_cupo_sin_verificar_sigue_frenando_sin_saldo():
    """El cupo de quien no verificó su identidad es una regla de la ley, no
    del saldo. Que se pueda pagar con otra vía no lo levanta."""
    p = _correr(BRASIL,
                "m.validarMonto({monto: 500, saldo: 0,"
                " limites: {pix: {min_brl: 10, max_brl: 5000}},"
                " cupo: {aplica: true, ops_restantes: 0},"
                " saldoEsLaUnicaVia: false})")
    assert p and "operaciones" in p.lower()


# ══════════════════════════════════════════════════════════════════════════
# 2. Sin otra vía, el saldo SIGUE frenando temprano
# ══════════════════════════════════════════════════════════════════════════

def test_VENEZUELA_sin_otra_via_el_saldo_frena_en_el_paso_del_monto():
    """Cuando el saldo es lo único con lo que se puede pagar, frenar temprano
    le ahorra a alguien completar cuatro pantallas para nada. Eso no cambió."""
    v = _correr(VENEZUELA,
                "m.validarMonto({ris: 50, saldo: 0, tasaDisponible: true,"
                " escribioAlgo: true, saldoEsLaUnicaVia: true})")
    assert v["ok"] is False and v["motivo"] == "sin_saldo"


def test_VENEZUELA_sin_otra_via_lo_que_excede_el_saldo_tambien_frena():
    v = _correr(VENEZUELA,
                "m.validarMonto({ris: 500, saldo: 100, tasaDisponible: true,"
                " escribioAlgo: true, saldoEsLaUnicaVia: true})")
    assert v["ok"] is False and v["motivo"] == "excede_saldo"


def test_BRASIL_sin_otra_via_el_saldo_frena_en_el_paso_del_monto():
    p = _correr(BRASIL,
                "m.validarMonto({monto: 500, saldo: 100,"
                " limites: {pix: {min_brl: 10, max_brl: 5000}}, cupo: null,"
                " saldoEsLaUnicaVia: true})")
    assert p and "saldo" in p.lower()


# ══════════════════════════════════════════════════════════════════════════
# 3. La otra mitad, para el último paso
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("modulo, expresion, espera", [
    (VENEZUELA, "m.alcanzaElSaldo({ris: 50, saldo: 250})", True),
    (VENEZUELA, "m.alcanzaElSaldo({ris: 50, saldo: 0})", False),
    (VENEZUELA, "m.alcanzaElSaldo({ris: 100, saldo: 100})", True),   # el justo
    (VENEZUELA, "m.alcanzaElSaldo({ris: null, saldo: 250})", False),
    (BRASIL, "m.alcanzaElSaldo({monto: 100, saldo: 250})", True),
    (BRASIL, "m.alcanzaElSaldo({monto: 100, saldo: 0})", False),
    (BRASIL, "m.alcanzaElSaldo({monto: 100, saldo: 100})", True),
])
def test_se_puede_preguntar_por_el_saldo_aparte(modulo, expresion, espera):
    """El último paso necesita apagar «Usar mi saldo» SIN apagar la otra vía.
    Sin esta función tendría que volver a mezclar las dos preguntas."""
    assert _correr(modulo, expresion) is espera


# ══════════════════════════════════════════════════════════════════════════
# 4. Nadie puede olvidarse de decir cuál de los dos casos es
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("modulo, expresion", [
    (VENEZUELA, "m.validarMonto({ris: 50, saldo: 0, tasaDisponible: true,"
                " escribioAlgo: true})"),
    (BRASIL, "m.validarMonto({monto: 500, saldo: 0, limites: null,"
             " cupo: null})"),
])
def test_olvidarse_del_parametro_ROMPE_en_vez_de_adivinar(modulo, expresion):
    """Un valor por omisión es el que alguien se olvida de pasar en la pantalla
    siguiente, y el olvido no se ve: la pantalla anda, hasta que un usuario sin
    saldo se queda trabado. Es la lección del `tipo` de `PuertaCripto`."""
    assert _tira(modulo, expresion), (
        "`validarMonto` acepta que no le digan si el saldo es la única vía: "
        "la próxima pantalla que se olvide va a trabar a quien no tenga saldo, "
        "y no lo va a ver nadie.")


# ══════════════════════════════════════════════════════════════════════════
# 5. Que las pantallas lo usen de verdad
# ══════════════════════════════════════════════════════════════════════════

def test_LAS_DOS_PANTALLAS_le_dicen_que_hay_otra_via_cuando_la_hay():
    """La lógica separada no sirve de nada si la pantalla sigue mandando
    siempre que el saldo es la única vía."""
    for archivo in (PANTALLA_VE, PANTALLA_BR):
        texto = open(archivo, encoding="utf-8").read()
        assert "saldoEsLaUnicaVia: !pagoAlFinal" in texto, (
            f"{os.path.basename(archivo)} no le pasa el estado del pago al "
            f"final: con el flujo prendido sigue frenando a quien no tiene "
            f"saldo.")


def test_el_boton_del_saldo_se_apaga_SOLO_y_no_apaga_al_de_al_lado():
    """Si el botón de la otra vía volviera a mirar lo mismo que el del saldo,
    vuelve el defecto entero."""
    ve = open(PANTALLA_VE, encoding="utf-8").read()
    br = open(PANTALLA_BR, encoding="utf-8").read()

    # El del saldo mira si alcanza.
    assert "disabled={loading || !validacion.ok || (pagoAlFinal && !elSaldoAlcanza)}" in ve
    assert "disabled={enviando || !montoOk || (pagoAlFinal && !elSaldoAlcanza)}" in br

    # El de la otra vía NO.
    for texto, testid, nombre in ((ve, "pagar-con-pix", "Send.jsx"),
                                  (br, "br-pagar-bolivares", "SendReais.jsx")):
        i = texto.index(testid)
        alrededor = texto[max(0, i - 260):i]
        assert "elSaldoAlcanza" not in alrededor, (
            f"en {nombre} el botón de la vía que NO pide saldo volvió a mirar "
            f"el saldo: es el defecto original, otra vez.")


def test_se_le_dice_al_usuario_que_igual_puede_pagarlo():
    """Un botón apagado sin explicación es alguien mirando la pantalla sin
    saber qué le falta — y creyendo que no puede enviar, cuando sí puede."""
    ve = open(PANTALLA_VE, encoding="utf-8").read()
    br = open(PANTALLA_BR, encoding="utf-8").read()
    assert "saldo-no-alcanza" in ve
    assert "br-saldo-no-alcanza" in br
    # Y el aviso nombra la vía que SI funciona.
    assert "Pagalo con PIX" in ve
    assert "Pagalo en bolívares" in br
