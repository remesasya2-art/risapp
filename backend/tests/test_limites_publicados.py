"""
tests/test_limites_publicados.py — Lo que se publica y lo que se hace cumplir
tienen que ser el mismo número.

POR QUE ESTE ARCHIVO EXISTE

    La página pública de "cómo funciona" muestra los límites de operación y el
    cupo de quien todavía no verificó su identidad. Esos números son una
    promesa: quien los lee decide en base a ellos, y una revisión de
    cumplimiento los compara contra lo que el sistema hace de verdad.

    Si la página los tuviera escritos a mano, el día que alguien cambie
    `PIX_MAX_BRL` la página seguiría diciendo lo viejo. Y nadie se entera:
    no falla nada, sólo queda publicado un número que no es.

    Por eso salen del MISMO módulo que valida, por `GET /api/limits`, y por eso
    estos tests: comprueban que lo publicado es exactamente lo que se hace
    cumplir, no que sea un valor en particular.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import kyc_quota, limits                             # noqa: E402


def test_lo_publicado_es_lo_que_se_valida_en_pix():
    publicado = limits.limits_payload()["pix"]
    assert publicado["min_brl"] == limits.PIX_MIN_BRL
    assert publicado["max_brl"] == limits.PIX_MAX_BRL

    # Y que de verdad se haga cumplir, en los dos bordes.
    assert limits.validate_pix_amount(publicado["min_brl"]) is None
    assert limits.validate_pix_amount(publicado["max_brl"]) is None
    assert limits.validate_pix_amount(publicado["min_brl"] - 0.01) is not None
    assert limits.validate_pix_amount(publicado["max_brl"] + 0.01) is not None


def test_lo_publicado_es_lo_que_se_valida_en_ves():
    publicado = limits.limits_payload()["ves"]
    assert publicado["min_ves"] == limits.VES_MIN
    assert publicado["max_ves"] == limits.VES_MAX

    assert limits.validate_ves_amount(publicado["min_ves"]) is None
    assert limits.validate_ves_amount(publicado["min_ves"] - 0.01) is not None


def test_EL_CUPO_PUBLICADO_ES_EL_QUE_SE_HACE_CUMPLIR():
    """El número que ve quien todavía no verificó su identidad."""
    publicado = limits.limits_payload()["sin_verificar"]
    assert publicado["max_ris"] == kyc_quota.UNVERIFIED_MAX_RIS
    assert publicado["max_operaciones"] == kyc_quota.UNVERIFIED_MAX_OPS


def test_el_cupo_publicado_coincide_con_el_que_ve_el_usuario():
    """`/limits` (público) y `/limits/me` (con sesión) no pueden discrepar.

    Uno lo lee quien todavía no se registró; el otro, quien ya está adentro.
    Si dijeran distinto, alguien tomaría una decisión con el número
    equivocado.
    """
    publico = limits.limits_payload()["sin_verificar"]
    del_usuario = kyc_quota.quota_payload({"verification_status": "unverified"})
    assert publico["max_ris"] == del_usuario["max_ris"]
    assert publico["max_operaciones"] == del_usuario["max_ops"]


def test_el_pago_publicado_no_tiene_agujeros():
    """Las tres claves tienen que estar: la página las lee sin preguntar."""
    p = limits.limits_payload()
    assert set(p) == {"pix", "ves", "sin_verificar"}, p
    assert set(p["pix"]) == {"min_brl", "max_brl"}
    assert set(p["ves"]) == {"min_ves", "max_ves"}
    assert set(p["sin_verificar"]) == {"max_ris", "max_operaciones"}


@pytest.mark.parametrize("campo", ["min_brl", "max_brl"])
def test_ningun_limite_de_pix_queda_en_nulo(campo):
    """Un `null` acá se muestra como 'sin límite' y sería falso."""
    assert limits.limits_payload()["pix"][campo] is not None


def test_el_techo_de_ves_es_nulo_a_proposito():
    """Y la página tiene que poder distinguir 'sin techo' de 'no lo sé'.

    `VES_MAX = None` está puesto a propósito —lo dice el comentario del
    módulo— así que publicarlo como `null` es correcto. Este test existe para
    que si algún día se le pone un techo, alguien se acuerde de que hay una
    página que dice 'sin límite'.
    """
    assert limits.limits_payload()["ves"]["max_ves"] is None, (
        "Se le puso techo a las recargas en VES. La página pública dice 'sin "
        "límite': hay que actualizarla y cambiar este test.")
