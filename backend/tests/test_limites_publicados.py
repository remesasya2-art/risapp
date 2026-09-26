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

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                     # noqa: E402
from services import configuracion, kyc_quota, limits              # noqa: E402


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def corre(coro):
    import asyncio
    return asyncio.run(coro)


def poner(b, clave, valor):
    """Cambia un ajuste como lo haría el panel, pasando por `normalizar`."""
    limpio, motivo = configuracion.normalizar(clave, valor)
    assert motivo is None, motivo
    corre(configuracion.escribir(b, clave, limpio))


def test_lo_publicado_es_lo_que_se_valida_en_pix(base):
    publicado = corre(limits.limits_payload(base))["pix"]

    # Y que de verdad se haga cumplir, en los dos bordes.
    assert corre(limits.validate_pix_amount(base, publicado["min_brl"])) is None
    assert corre(limits.validate_pix_amount(base, publicado["max_brl"])) is None
    assert corre(limits.validate_pix_amount(base, publicado["min_brl"] - 0.01)) is not None
    assert corre(limits.validate_pix_amount(base, publicado["max_brl"] + 0.01)) is not None


def test_LO_PUBLICADO_SIGUE_AL_PANEL_Y_LO_VALIDADO_TAMBIEN(base):
    """La guarda de verdad, ahora que el número se puede cambiar sin desplegar.

    Antes bastaba con comparar el payload contra una constante: los dos salían
    del mismo archivo y era casi una tautología. Ahora el número viaja desde la
    base hasta dos lugares distintos —lo que se anuncia y lo que se hace
    cumplir— y lo que este test prueba es que llegue a los dos.
    """
    poner(base, "pix_maximo", "3000")
    publicado = corre(limits.limits_payload(base))["pix"]
    assert publicado["max_brl"] == 3000.0
    assert corre(limits.validate_pix_amount(base, 3000)) is None
    assert corre(limits.validate_pix_amount(base, 3000.01)) is not None


def test_lo_publicado_es_lo_que_se_valida_en_ves(base):
    publicado = corre(limits.limits_payload(base))["ves"]
    assert publicado["max_ves"] == limits.VES_MAX

    assert corre(limits.validate_ves_amount(base, publicado["min_ves"])) is None
    assert corre(limits.validate_ves_amount(base, publicado["min_ves"] - 0.01)) is not None


def test_lo_publicado_es_lo_que_se_valida_en_la_tarjeta(base):
    publicado = corre(limits.limits_payload(base))["tarjeta"]
    assert corre(limits.validate_card_amount(base, publicado["min_brl"])) is None
    assert corre(limits.validate_card_amount(base, publicado["max_brl"])) is None
    assert corre(limits.validate_card_amount(base, publicado["min_brl"] - 0.01)) is not None
    assert corre(limits.validate_card_amount(base, publicado["max_brl"] + 0.01)) is not None


def test_EL_CUPO_PUBLICADO_ES_EL_QUE_SE_HACE_CUMPLIR(base):
    """El número que ve quien todavía no verificó su identidad.

    Se comprueba contra la validación de verdad y no contra una constante: el
    cupo se cambia desde el panel, y lo que importa es que el cartel y el
    rechazo digan lo mismo DESPUES de cambiarlo.
    """
    poner(base, "cupo_sin_verificar_ris", "350")
    publicado = corre(limits.limits_payload(base))["sin_verificar"]
    assert publicado["max_ris"] == 350.0

    sin_verificar = {"verification_status": "unverified"}
    assert corre(kyc_quota.check_amount(base, sin_verificar, 350)) is None
    assert corre(kyc_quota.check_amount(base, sin_verificar, 350.01)) is not None


def test_el_cupo_publicado_coincide_con_el_que_ve_el_usuario(base):
    """`/limits` (público) y `/limits/me` (con sesión) no pueden discrepar.

    Uno lo lee quien todavía no se registró; el otro, quien ya está adentro.
    Si dijeran distinto, alguien tomaría una decisión con el número
    equivocado.
    """
    publico = corre(limits.limits_payload(base))["sin_verificar"]
    del_usuario = corre(kyc_quota.quota_payload(
        base, {"verification_status": "unverified"}))
    assert publico["max_ris"] == del_usuario["max_ris"]
    assert publico["max_operaciones"] == del_usuario["max_ops"]


def test_el_pago_publicado_no_tiene_agujeros(base):
    """Las cinco claves tienen que estar: la página las lee sin preguntar.

    Se comparan CONJUNTOS EXACTOS y no «que estén»: una lista de lo permitido.
    Por eso agregar `cripto` puso este test en rojo, que es lo que tenía que
    pasar — esta ruta es el contrato entre la pantalla y el servidor, y crecerlo
    sin que nadie mire es cómo se cuelan campos que ninguna pantalla lee.
    """
    p = corre(limits.limits_payload(base))
    assert set(p) == {"pix", "tarjeta", "ves", "sin_verificar", "cripto",
                      "pago_al_final", "recarga", "encomiendas", "remesas"}, p
    assert set(p["pix"]) == {"min_brl", "max_brl"}
    assert set(p["tarjeta"]) == {"min_brl", "max_brl"}
    assert set(p["ves"]) == {"min_ves", "max_ves"}
    assert set(p["sin_verificar"]) == {"max_ris", "max_operaciones"}
    # `estado` viaja además de las tres respuestas resueltas: es lo que el
    # panel muestra y lo que hace falta para entender un registro viejo.
    assert set(p["cripto"]) == {"estado", "deposito", "envio", "visible"}
    # Un booleano pelado y no un objeto: acá no hay tres estados que resolver,
    # es «se ofrece o no se ofrece».
    assert isinstance(p["pago_al_final"], bool)
    assert isinstance(p["recarga"], bool)
    # Lo mismo para las encomiendas: se pueden mandar o no. Lo que ya está en
    # camino no depende de esto, así que no hay más estados que resolver.
    assert isinstance(p["encomiendas"], bool)


@pytest.mark.parametrize("campo", ["min_brl", "max_brl"])
def test_ningun_limite_de_pix_queda_en_nulo(base, campo):
    """Un `null` acá se muestra como 'sin límite' y sería falso."""
    assert corre(limits.limits_payload(base))["pix"][campo] is not None


def test_el_techo_de_ves_es_nulo_a_proposito(base):
    """Y la página tiene que poder distinguir 'sin techo' de 'no lo sé'.

    `VES_MAX = None` está puesto a propósito —lo dice el comentario del
    módulo— así que publicarlo como `null` es correcto. Este test existe para
    que si algún día se le pone un techo, alguien se acuerde de que hay una
    página que dice 'sin límite'.
    """
    assert corre(limits.limits_payload(base))["ves"]["max_ves"] is None, (
        "Se le puso techo a las recargas en VES. La página pública dice 'sin "
        "límite': hay que actualizarla y cambiar este test.")
