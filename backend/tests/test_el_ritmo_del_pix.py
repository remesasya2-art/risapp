"""
tests/test_el_ritmo_del_pix.py — Cada cuánto se pregunta si el pago entró.

DE DONDE SALE

    De la revisión de capacidad para dos mil usuarios activos, punto 6.

    La pantalla de recarga preguntaba cada CINCO SEGUNDOS FIJOS durante los
    quince minutos que dura el código PIX: 180 preguntas por persona, y cada
    una cruza desde el servidor hasta Mercado Pago.

POR QUE UNA ESCALERA Y NO UN NUMERO MAS GRANDE

    La gente paga en el primer minuto: abre la app del banco, escanea y
    confirma. Ahí los cinco segundos valen, porque es cuando el aviso de
    «listo» tiene que llegar rápido. El que a los diez minutos no pagó no es
    alguien a punto de pagar: es alguien que dejó la pantalla abierta.

    Medido contra la aplicación corriendo, mirando 95 segundos seguidos:
    5, 5, 5, 5, 15, 15, 15, 15.
"""
import os
import re
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)



_SRC = os.path.join(_BACKEND, "..", "frontend", "src")
# El ritmo vivió primero en la pantalla de recarga. Cuando el envío pasó a
# pagarse al final se generalizó en `hooks/useEsperarElPago.js`, y la recarga
# pasó a usar el hook: UNA copia de la pregunta, no dos. Estos tests leen el
# ritmo de donde está, y uno comprueba que la recarga no tenga el suyo propio.
_HOOK = os.path.join(_SRC, "hooks", "useEsperarElPago.js")
_RECARGA = os.path.join(_SRC, "pages", "Recharge.jsx")

# Cuánto dura el código PIX. Es lo que hay que cubrir preguntando.
_MINUTOS_DEL_CODIGO = 15


def _solo_el_codigo(texto: str) -> str:
    """El archivo sin sus comentarios.

    Los comentarios de este repositorio explican el porqué, o sea que nombran
    justo aquello de lo que se salió: el de al lado del ritmo nuevo menciona
    los cinco segundos fijos de antes. Una guarda que lee con expresiones
    regulares no distingue lo que el archivo HACE de lo que CUENTA.
    """
    sin_bloques = re.sub(r"\{?/\*.*?\*/\}?", "", texto, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", sin_bloques)


def _el_ritmo():
    """Los tramos del ritmo, leídos del archivo de verdad."""
    codigo = _solo_el_codigo(open(_HOOK, encoding="utf-8").read())
    bloque = re.search(r"export const RITMO = \[(.*?)\];", codigo, re.S)
    assert bloque, "no se encontró el RITMO en el hook"
    tramos = []
    for hasta, cada in re.findall(r"\{\s*(?:hasta:\s*(\d+),\s*)?cada:\s*(\d+)",
                                  bloque.group(1)):
        tramos.append((int(hasta) if hasta else None, int(cada)))
    return tramos


def _cuantas_preguntas(tramos, segundos):
    """Las preguntas que se harían en `segundos`, con este ritmo."""
    cuantas, reloj = 0, 0.0
    while reloj < segundos:
        cada = next((c for h, c in tramos if h is None or reloj < h), tramos[-1][1])
        reloj += cada / 1000
        cuantas += 1
    return cuantas


def test_EL_PRIMER_MINUTO_SIGUE_PREGUNTANDO_RAPIDO():
    """Espaciar de entrada sería peor que no tocar nada: la gente paga en el
    primer minuto, y ahí el aviso de «listo» tiene que llegar rápido."""
    tramos = _el_ritmo()
    primero = tramos[0]
    assert primero[0] is not None and primero[0] >= 60, tramos
    assert primero[1] <= 5000, f"el primer tramo pregunta cada {primero[1]} ms"


def test_EL_RITMO_SE_VA_ESPACIANDO_Y_NUNCA_SE_APURA():
    """Un tramo más rápido que el anterior sería un ritmo que no ahorra nada y
    que además nadie escribió a propósito."""
    tramos = _el_ritmo()
    assert len(tramos) >= 2, "no hay escalera: es un número fijo"
    esperas = [cada for _, cada in tramos]
    assert esperas == sorted(esperas), f"el ritmo se apura en algún tramo: {esperas}"


def test_SE_PREGUNTA_MUCHO_MENOS_EN_LOS_QUINCE_MINUTOS():
    """El número que motivó el cambio. Cada pregunta cruza a Mercado Pago desde
    el servidor, así que son 180 idas y vueltas por persona esperando."""
    cuantas = _cuantas_preguntas(_el_ritmo(), _MINUTOS_DEL_CODIGO * 60)
    assert cuantas <= 60, f"{cuantas} preguntas en {_MINUTOS_DEL_CODIGO} minutos"


def test_NO_QUEDO_UN_RELOJ_FIJO_PREGUNTANDO_POR_EL_PAGO():
    """Si volviera el `setInterval`, el ritmo quedaría de adorno."""
    codigo = _solo_el_codigo(open(_HOOK, encoding="utf-8").read())
    assert not re.search(r"programada\.current\s*=\s*setInterval", codigo), (
        "volvió el reloj fijo para consultar el pago")
    assert "cadaCuanto(" in codigo, "nadie usa el ritmo"


def test_AL_CORTAR_NO_SE_VUELVE_A_PROGRAMAR():
    """Sin eso, la pregunta que estaba en vuelo cuando el pago se confirmó se
    vuelve a programar, y la cadena sigue viva para siempre sobre un pago que
    ya terminó. En el hook la bandera es `parado`: la limpieza del efecto la
    levanta y la cadena la mira antes de reprogramarse."""
    codigo = _solo_el_codigo(open(_HOOK, encoding="utf-8").read())
    assert re.search(r"parado\s*=\s*true", codigo), "la limpieza no levanta la bandera"
    assert re.search(r"if \(parado \|\| como !== ESPERANDO\) return;", codigo), (
        "la cadena no mira la bandera antes de reprogramarse")
    assert "clearTimeout(programada.current)" in codigo, "no corta el reloj"


def test_LA_RECARGA_USA_EL_HOOK_Y_NO_TIENE_UN_RITMO_PROPIO():
    """Dos copias de la pregunta son la que un día se arregla en una y no en
    la otra. La recarga tuvo la suya; ahora usa la compartida."""
    codigo = _solo_el_codigo(open(_RECARGA, encoding="utf-8").read())
    assert "useEsperarElPago(" in codigo, "la recarga no usa el hook"
    assert "const RITMO" not in codigo, "la recarga volvió a tener su propio ritmo"
    assert "/gestor/pix/status/" not in codigo, "la recarga vuelve a preguntar por su cuenta"
    # Y sólo pregunta mientras hay un QR esperando: con otro estado, `null`.
    assert re.search(r"useEsperarElPago\(\s*step === 2 && paymentStatus === 'pending' && pixData\?\.payment_id \? pixData\.payment_id : null", codigo), (
        "la recarga pregunta aunque no haya un QR esperando")
