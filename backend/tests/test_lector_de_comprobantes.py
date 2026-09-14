"""
tests/test_lector_de_comprobantes.py — Qué se saca del texto de un comprobante.

QUE SE PRUEBA ACA Y QUE NO

    Acá se prueba la parte que no necesita a `tesseract`: de un texto ya
    leído, qué candidatos salen. Es la mitad que decide si una foto se puede
    adjudicar, y la que se puede romper sin darse cuenta.

    Lo otro —que `tesseract` LEA la foto— no se prueba en la suite: depende de
    un programa del sistema que puede no estar, y una prueba que se saltea en
    silencio cuando falta es peor que ninguna. Eso se midió a mano contra los
    cuatro formatos de comprobante que usa el negocio.

POR QUE LAS SEÑALES SON LISTAS Y NO VALORES

    Un comprobante tiene varios números con forma de monto: el que se
    transfirió, la comisión, el saldo. Elegir «el primero» es elegir al azar.
    Se devuelven todos, y quien adjudica pregunta si el de la orden está entre
    ellos.
"""
import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import lector_de_comprobantes as lector    # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Las cuentas
# ══════════════════════════════════════════════════════════════════════════

def test_LA_CUENTA_SE_ENCUENTRA_ESCRITA_CON_GUIONES():
    """Banesco la escribe 0134-0046-60-0463065183."""
    s = lector.senales_del_texto("Cuenta 0134-0046-60-0463065183")
    assert s["cuentas"] == ["01340046600463065183"]


def test_LA_CUENTA_SE_ENCUENTRA_ESCRITA_CON_ESPACIOS():
    s = lector.senales_del_texto("0102 0121 71 0106529080")
    assert s["cuentas"] == ["01020121710106529080"]


def test_UN_NUMERO_DE_DIECINUEVE_DIGITOS_NO_ES_UNA_CUENTA():
    assert lector.senales_del_texto("0134004660046306518")["cuentas"] == []


# ══════════════════════════════════════════════════════════════════════════
# Los teléfonos y las cédulas
# ══════════════════════════════════════════════════════════════════════════

def test_EL_TELEFONO_SE_ENCUENTRA_CON_Y_SIN_GUION():
    assert lector.senales_del_texto("0426-4672100")["telefonos"] == ["04264672100"]
    assert lector.senales_del_texto("04261917808")["telefonos"] == ["04261917808"]


def test_UN_NUMERO_QUE_NO_ES_DE_UNA_OPERADORA_NO_ES_UN_TELEFONO():
    """0212 es un fijo de Caracas: no recibe pago móvil."""
    assert lector.senales_del_texto("0212-1234567")["telefonos"] == []


def test_LA_CEDULA_SE_ENCUENTRA_CON_LETRA_Y_SIN_ELLA():
    assert "26138745" in lector.senales_del_texto("V-26138745")["cedulas"]
    assert "26138745" in lector.senales_del_texto("Cédula 26138745")["cedulas"]


def test_UN_NUMERO_DE_CINCO_DIGITOS_NO_ES_UNA_CEDULA():
    """Por debajo de seis es cualquier número suelto de la pantalla."""
    assert lector.senales_del_texto("Ref 12345")["cedulas"] == []


# ══════════════════════════════════════════════════════════════════════════
# Los montos
# ══════════════════════════════════════════════════════════════════════════

def test_SE_DEVUELVEN_TODOS_LOS_MONTOS_NO_EL_PRIMERO():
    """Es la decisión de diseño del módulo: acá no se elige nada."""
    s = lector.senales_del_texto("Monto 114.552,10  Comisión 0,30  Saldo 9.000,00")
    assert s["montos"] == ["0,30", "114.552,10", "9.000,00"]


def test_UN_ENTERO_SIN_DECIMALES_NO_ES_UN_MONTO():
    """Cualquier número de referencia lo imita, y un monto de más que no
    coincide con nada es ruido; uno que coincide por casualidad, un error."""
    assert lector.senales_del_texto("Operación 007324237255")["montos"] == []


# ══════════════════════════════════════════════════════════════════════════
# Comparar nombres escritos de dos maneras
# ══════════════════════════════════════════════════════════════════════════

def test_EL_NOMBRE_SE_COMPARA_SIN_TILDES_NI_ENE():
    """El lector devuelve MUNOZ donde el panel guarda MUÑOZ."""
    assert lector.sin_adornos("María Muñoz") == lector.sin_adornos("MARIA MUNOZ")


def test_LA_PUNTUACION_NO_IMPIDE_QUE_DOS_NOMBRES_COINCIDAN():
    assert "BANESCO" in lector.sin_adornos("BANESCO, C.A.")


def test_SOLO_DIGITOS_DEJA_COMPARABLES_DOS_ESCRITURAS_DEL_MISMO_NUMERO():
    assert lector.solo_digitos("V-26.138.745") == lector.solo_digitos("26138745")


# ══════════════════════════════════════════════════════════════════════════
# Que no se rompa
# ══════════════════════════════════════════════════════════════════════════

def test_UN_TEXTO_VACIO_NO_DEVUELVE_NINGUNA_SEÑAL():
    s = lector.senales_del_texto("")
    assert s["cuentas"] == s["telefonos"] == s["cedulas"] == s["montos"] == []


def test_VACIO_TIENE_LA_MISMA_FORMA_QUE_UNA_LECTURA_DE_VERDAD():
    """Quien adjudica no puede tener que preguntar si hubo lector o no."""
    assert set(lector.vacio()) == set(lector.senales_del_texto("algo"))
