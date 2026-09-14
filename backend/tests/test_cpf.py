"""
tests/test_cpf.py — Que un CPF inventado no entre.

POR QUE ESTO IMPORTA MAS DE LO QUE PARECE

    El CPF es lo que ata una cuenta a una persona y lo que ata cada recarga a
    quien la pagó. Si el validador acepta once dígitos cualesquiera, esa
    atadura no ata nada: «12345678900» pasa, y un teléfono tipeado en el campo
    equivocado también.

    Hasta que esto existió, la aplicación contaba once dígitos y nada más.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import cpf                                   # noqa: E402


# CPF válidos que se publican como ejemplo. Los dos, y no uno, porque un
# validador roto de una forma particular puede acertarle a uno por casualidad.
VALIDOS = ["52998224725", "11144477735"]


@pytest.mark.parametrize("numero", VALIDOS)
def test_UN_CPF_DE_VERDAD_ENTRA(numero):
    assert cpf.es_valido(numero)


@pytest.mark.parametrize("numero", VALIDOS)
def test_ENTRA_IGUAL_ESCRITO_CON_PUNTOS_Y_GUION(numero):
    """La gente lo copia de su documento, con los puntos puestos."""
    con_formato = cpf.para_mostrar(numero)
    assert "." in con_formato and "-" in con_formato
    assert cpf.es_valido(con_formato)
    assert cpf.normalizar(con_formato) == numero


def test_UN_DIGITO_CAMBIADO_NO_ENTRA():
    """Es el error que más pasa: un dedo que se equivoca en una cifra.

    Y es el más caro, porque queda guardado y nadie lo mira hasta que hay que
    reclamar un pago.
    """
    for i in range(11):
        roto = list(VALIDOS[0])
        roto[i] = str((int(roto[i]) + 1) % 10)
        assert not cpf.es_valido("".join(roto)), f"pasó con el dígito {i} cambiado"


@pytest.mark.parametrize("numero,cual", [
    ("00000000604", "el primero"),
    ("00000001830", "el segundo"),
])
def test_UN_CPF_CUYO_VERIFICADOR_SALE_DE_UN_RESTO_DE_DIEZ_ENTRA(numero, cual):
    """La rama de la fórmula que nadie prueba y que rechazaría CPF de verdad.

    Cuando el resto de la cuenta da 10 u 11, el dígito verificador es CERO: no
    es «10». Si alguien «simplifica» esa línea a devolver el resto tal cual, el
    dígito calculado sería «10» —dos caracteres— y no coincidiría nunca con el
    del documento. El resultado no sería un agujero de seguridad sino algo casi
    peor de encontrar: un puñado de personas con un CPF perfectamente válido a
    las que la aplicación les dice que se equivocaron, y nadie más.

    Estos dos números son los más chicos que tienen esa propiedad, uno en cada
    dígito verificador.
    """
    assert cpf.es_valido(numero), f"se rechaza un CPF válido: {cual} verificador"


def test_ONCE_DIGITOS_CUALESQUIERA_NO_SON_UN_CPF():
    """Lo que aceptaba la aplicación antes de que esto existiera."""
    assert not cpf.es_valido("12345678900")


@pytest.mark.parametrize("numero", [str(d) * 11 for d in range(10)])
def test_LOS_ONCE_DIGITOS_REPETIDOS_NO_ENTRAN(numero):
    """Pasan la cuenta de los verificadores pero no son de nadie.

    Son los que aparecen cuando alguien quiere sacarse de encima un campo
    obligatorio. Y «00000000000» era, literalmente, el valor con el que el
    código mandaba los pagos a Mercado Pago cuando el campo venía vacío.
    """
    assert not cpf.es_valido(numero)


@pytest.mark.parametrize("numero", ["", None, "5299822472", "529982247255", "abc"])
def test_LO_QUE_NO_TIENE_ONCE_DIGITOS_NO_ENTRA(numero):
    assert not cpf.es_valido(numero)


def test_UN_TELEFONO_EN_EL_CAMPO_EQUIVOCADO_NO_PASA():
    """Once dígitos y forma de CPF, pero es un celular brasileño."""
    assert not cpf.es_valido("11987654321")


def test_NORMALIZAR_DEJA_COMPARABLES_LAS_DOS_ESCRITURAS():
    """Si se guardaran las dos formas, la comparación de la recarga fallaría
    según cómo lo hubiera tipeado la persona ese día."""
    assert cpf.normalizar("529.982.247-25") == cpf.normalizar("52998224725")


def test_TAPADO_NO_MUESTRA_EL_DOCUMENTO_ENTERO():
    tapado = cpf.tapado(VALIDOS[0])
    assert VALIDOS[0] not in cpf.normalizar(tapado)
    assert "982" in tapado, "no deja reconocer cuál es"


def test_TAPADO_NO_INVENTA_NADA_CON_UN_NUMERO_INCOMPLETO():
    assert cpf.tapado("123") == ""
