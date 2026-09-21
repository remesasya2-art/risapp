"""
tests/test_el_monto_viaja_de_la_calculadora_al_envio.py — el monto escrito en
la calculadora del inicio llega a la pantalla de envío, y sólo si es un número.

POR QUE ESTO ES UN TEST

    La calculadora lleva al flujo con un botón. Si el monto no viaja, la
    persona lo tipea dos veces. Y viaja por la dirección (`?monto=`), que la
    escribe cualquiera: un texto, un negativo o un cero no pueden arrancar la
    pantalla con basura en la casilla del monto.
"""
import json
import shutil
import subprocess

import pytest

from _lote_c_comun import _SRC, fuente, sin_comentarios

MODULO = _SRC / "utils" / "montoDeLaUrl.js"
_node = shutil.which("node")


def js(expresion):
    if not _node:
        pytest.skip("node no está instalado")
    codigo = (f"import * as m from {json.dumps('file://' + str(MODULO))};\n"
              f"const P = (o) => new URLSearchParams(o);\n"
              f"console.log(JSON.stringify(({expresion})));\n")
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"node falló evaluando «{expresion}»:\n{r.stderr}")
    return json.loads(r.stdout)


def test_un_monto_valido_arranca_la_casilla():
    assert js("m.montoDeLaUrl(P('monto=245.54'))") == "245.54"
    assert js("m.montoDeLaUrl(P('monto=100'))") == "100"
    assert js("m.montoDeLaUrl(P('monto=12,5'))") == "12.5"


def test_LO_QUE_NO_ES_UN_MONTO_ARRANCA_VACIO():
    for crudo in ("abc", "-5", "0", "", "1e999x"):
        assert js(f"m.montoDeLaUrl(P('monto={crudo}'))") == "", crudo
    assert js("m.montoDeLaUrl(P(''))") == ""
    assert js("m.montoDeLaUrl(null)") == ""


def test_la_calculadora_manda_el_monto_en_reales_solo_cuando_hay_cuenta():
    codigo = sin_comentarios(fuente("components/dashboard/Calculadora.jsx"))
    assert "?monto=${cuenta.brl}" in codigo
    assert "hayCuenta ?" in codigo


def test_las_dos_pantallas_de_envio_arrancan_con_el_monto_de_la_url():
    for pantalla, estado in (("pages/Send.jsx", "setRisEscrito"), ("pages/SendReais.jsx", "setMonto")):
        codigo = sin_comentarios(fuente(pantalla))
        assert "useSearchParams" in codigo, pantalla
        assert "from '../utils/montoDeLaUrl'" in codigo, pantalla
        assert f"{estado}] = useState(() => montoDeLaUrl(parametros))" in codigo, pantalla
