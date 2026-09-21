"""
tests/test_la_calculadora_del_inicio.py — la calculadora de la pantalla
principal convierte con la tasa correcta de cada sentido, y no inventa.

POR QUE ESTO ES UN TEST

    La calculadora muestra dinero en la pantalla que todo el mundo ve primero.
    Tiene dos sentidos con dos tasas distintas —Brasil → Venezuela y
    Venezuela → Brasil— y el error obvio es usar la misma para los dos: las
    dos cuentas «funcionan», la pantalla se ve bien, y el número del sentido
    inverso está mal para cada persona que lo mire.

    Las cuentas viven en `utils/calculadora.js`, sin React, y se corren con
    node con números exactos. Lo que no se puede correr —que la pantalla use
    ese módulo y no unas fórmulas propias, y que respete «sin tasa no hay
    cuenta»— se sostiene leyendo el código fuente.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
MODULO = _RAIZ / "frontend" / "src" / "utils" / "calculadora.js"
PANTALLA = _RAIZ / "frontend" / "src" / "components" / "dashboard" / "Calculadora.jsx"
INICIO = _RAIZ / "frontend" / "src" / "pages" / "Dashboard.jsx"

_node = shutil.which("node")

# Las tasas de la captura con la que se decidió esto: 1 R$ = 173 Bs hacia
# Venezuela, el BCV a 849,56 y el USDT a 852. Hacia Brasil se inventa una
# distinta a propósito, para que usar la equivocada se note.
RATES = {"ris_to_ves": 173.0, "ves_to_ris_rate": 181.5,
         "bcv_usd_ves": 849.56, "usdtris_to_ves": 852.0}


def js(expresion):
    if not _node:
        pytest.skip("node no está instalado: las cuentas no se pueden correr")
    codigo = (
        f"import * as m from {json.dumps('file://' + str(MODULO))};\n"
        f"const RATES = {json.dumps(RATES)};\n"
        f"console.log(JSON.stringify(({expresion})));\n"
    )
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"node falló evaluando «{expresion}»:\n{r.stderr}")
    return json.loads(r.stdout)


def _fuente(ruta):
    return ruta.read_text(encoding="utf-8")


def _sin_comentarios(texto):
    fuera, en_bloque = [], False
    for linea in texto.splitlines():
        s = linea.strip()
        if en_bloque:
            if "*/" in s:
                en_bloque = False
            continue
        if s.startswith("/*"):
            en_bloque = "*/" not in s
            continue
        if s.startswith("//") or s.startswith("*"):
            continue
        fuera.append(linea)
    return "\n".join(fuera)


# ─── Cada sentido, su tasa ────────────────────────────────────────────────

def test_hacia_venezuela_usa_la_tasa_de_ir_y_hacia_brasil_la_de_volver():
    assert js("m.tasaDelSentido(RATES, m.A_VENEZUELA)") == 173.0
    assert js("m.tasaDelSentido(RATES, m.A_BRASIL)") == 181.5


def test_LAS_DOS_TASAS_NO_SON_LA_MISMA():
    """Si alguien «simplifica» a una sola tasa, esto se pone en rojo."""
    ida = js("m.tasaDelSentido(RATES, m.A_VENEZUELA)")
    vuelta = js("m.tasaDelSentido(RATES, m.A_BRASIL)")
    assert ida != vuelta


def test_sin_tasa_disponible_no_hay_tasa_aunque_el_contexto_traiga_relleno():
    """`RateContext` deja 110 cuando `/rate` no contesta. Eso no es una tasa."""
    assert js("m.tasaDelSentido({ris_to_ves: 110, ves_to_ris_rate: 140}, m.A_VENEZUELA, false)") == 0
    assert js("m.tasaDelSentido(null, m.A_VENEZUELA)") == 0
    assert js("m.tasaDelSentido({ris_to_ves: 0}, m.A_VENEZUELA)") == 0


# ─── Las cuentas, con números exactos ─────────────────────────────────────

def test_escribiendo_reales_salen_bolivares_y_dolares_al_bcv():
    c = js("m.convertir({origen: m.REALES, monto: 100, tasa: 173, bcv: 849.56, usdt: 852})")
    assert c == {"brl": 100, "ves": 17300, "usd": 20.36, "usdt": 20.31}


def test_escribiendo_dolares_al_bcv_salen_bolivares_y_reales():
    c = js("m.convertir({origen: m.DOLARES_BCV, monto: 50, tasa: 173, bcv: 849.56})")
    assert c["ves"] == 42478
    assert c["brl"] == 245.54
    assert c["usd"] == 50


def test_escribiendo_bolivares_salen_reales_y_dolares():
    c = js("m.convertir({origen: m.BOLIVARES, monto: 17300, tasa: 173, bcv: 849.56})")
    assert c == {"brl": 100, "ves": 17300, "usd": 20.36, "usdt": 0}


def test_la_misma_cuenta_hacia_brasil_da_otro_numero():
    """100 R$ hacia Brasil, con la tasa de volver, no son 17.300 Bs."""
    c = js("m.convertir({origen: m.REALES, monto: 100, tasa: m.tasaDelSentido(RATES, m.A_BRASIL)})")
    assert c["ves"] == 18150


def test_sin_tasa_o_sin_monto_todo_queda_en_cero():
    nada = {"brl": 0, "ves": 0, "usd": 0, "usdt": 0}
    assert js("m.convertir({origen: m.REALES, monto: 100, tasa: 0, bcv: 849.56})") == nada
    assert js("m.convertir({origen: m.REALES, monto: 0, tasa: 173, bcv: 849.56})") == nada
    assert js("m.convertir({origen: 'otra', monto: 100, tasa: 173})") == nada


def test_SIN_BCV_NO_SE_INVENTAN_DOLARES():
    """Sin dato del BCV, la casilla de dólares queda vacía; y escribir en
    ella no puede producir bolívares de la nada."""
    c = js("m.convertir({origen: m.REALES, monto: 100, tasa: 173, bcv: 0})")
    assert c["ves"] == 17300 and c["usd"] == 0
    assert js("m.convertir({origen: m.DOLARES_BCV, monto: 50, tasa: 173, bcv: 0})")["ves"] == 0


def test_lo_escrito_se_lee_como_lo_escribe_la_gente():
    assert js("m.aNumero('1.234,56')") == 1234.56
    assert js("m.aNumero('1234.56')") == 1234.56
    assert js("m.aNumero('100')") == 100
    assert js("m.aNumero('')") == 0
    assert js("m.aNumero('-5')") == 0
    assert js("m.aNumero('abc')") == 0


# ─── La pantalla usa el módulo, y lo usa entero ───────────────────────────

def test_la_pantalla_no_tiene_formulas_propias():
    """La tasa de cada sentido se elige en `tasaDelSentido` y en ningún otro
    lado: la pantalla no nombra `ris_to_ves` ni `ves_to_ris_rate`."""
    codigo = _sin_comentarios(_fuente(PANTALLA))
    assert "from '../../utils/calculadora'" in codigo
    assert "tasaDelSentido(" in codigo
    assert "convertir(" in codigo
    # Con límite de palabra: `usdtris_to_ves` —la del USDT, que la pantalla sí
    # lee— contiene «ris_to_ves» adentro y no es la tasa del envío.
    assert re.search(r"\bris_to_ves\b", codigo) is None
    assert re.search(r"\bves_to_ris_rate\b", codigo) is None


def test_la_pantalla_respeta_que_sin_tasa_no_hay_cuenta():
    codigo = _sin_comentarios(_fuente(PANTALLA))
    assert "tasaDisponible" in codigo
    # Y se lo pasa al módulo, que es quien decide: no alcanza con leerlo.
    assert "tasaDelSentido(rates, sentido, tasaDisponible)" in codigo
    assert 'data-testid="calc-sin-tasa"' in codigo


def test_la_pantalla_ofrece_los_dos_sentidos_con_su_flujo():
    codigo = _sin_comentarios(_fuente(PANTALLA))
    assert "A_VENEZUELA" in codigo and "A_BRASIL" in codigo
    assert "ruta: '/send'" in codigo
    assert "ruta: '/send-reais'" in codigo


def test_el_inicio_dibuja_la_calculadora():
    codigo = _sin_comentarios(_fuente(INICIO))
    assert "import Calculadora from '../components/dashboard/Calculadora'" in codigo
    assert "<Calculadora " in codigo
