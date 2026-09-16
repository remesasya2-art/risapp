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



_RECARGA = os.path.join(_BACKEND, "..", "frontend", "src", "pages", "Recharge.jsx")

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
    codigo = _solo_el_codigo(open(_RECARGA, encoding="utf-8").read())
    bloque = re.search(r"const RITMO = \[(.*?)\];", codigo, re.S)
    assert bloque, "no se encontró el RITMO en la pantalla de recarga"
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
    codigo = _solo_el_codigo(open(_RECARGA, encoding="utf-8").read())
    assert not re.search(r"pollRef\.current\s*=\s*setInterval", codigo), (
        "volvió el reloj fijo para consultar el pago")
    assert "cadaCuanto(" in codigo, "nadie usa el ritmo"


def test_AL_CORTAR_SE_DEJA_LA_REFERENCIA_EN_NULL():
    """Sin eso, la pregunta que estaba en vuelo cuando el pago se confirmó se
    vuelve a programar, y la cadena sigue viva para siempre sobre un pago que
    ya terminó."""
    codigo = _solo_el_codigo(open(_RECARGA, encoding="utf-8").read())
    parar = re.search(r"const pararDePreguntar = \(\) => \{(.*?)\};", codigo, re.S)
    assert parar, "no está `pararDePreguntar`"
    assert "clearTimeout" in parar.group(1), "no corta el reloj"
    assert re.search(r"pollRef\.current\s*=\s*null", parar.group(1)), (
        "no deja la referencia en null: la cadena se vuelve a programar sola")
