"""
tests/test_confirmar_envio_a_brasil_dice_como_se_paga.py — al confirmar un
envío a Brasil, «se descuentan de tu saldo» sólo se dice cuando es verdad.

POR QUE ESTO ES UN TEST

    Con el pago al final prendido, la pantalla ofrece dos botones: «Pagar en
    bolívares» y «Usar mi saldo». La frase de arriba decía «Se descuentan RI$
    40,00 de tu saldo» para los dos, y pagando en bolívares el saldo no se
    toca. `Send.jsx` ya tenía esta corrección en su paso de confirmar; la
    pantalla de Brasil no. Se vio en una captura de la app corriendo con la
    recarga cerrada.
"""
import re

from _lote_c_comun import fuente, sin_comentarios

PANTALLA = "pages/SendReais.jsx"


def _bloque():
    codigo = sin_comentarios(fuente(PANTALLA))
    m = re.search(r'data-testid="br-como-se-paga".*?</p>', codigo, re.S)
    assert m, "falta la frase de cómo se paga en el paso de confirmar"
    return m.group(0)


def test_la_frase_depende_de_si_el_pago_al_final_esta_prendido():
    bloque = _bloque()
    assert "pagoAlFinal" in bloque
    assert "?" in bloque and ":" in bloque, "tiene que elegir entre dos frases"


def test_con_el_pago_al_final_prendido_aclara_que_en_bolivares_no_se_toca_el_saldo():
    bloque = _bloque()
    assert "Usar mi saldo" in bloque
    assert "tu saldo no se toca" in bloque


def test_con_el_pago_al_final_apagado_sigue_diciendo_lo_de_siempre():
    assert "de tu saldo." in _bloque()
