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

import pytest

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


# ══════════════════════════════════════════════════════════════════════════
# Encontrar el programa, y decir por qué no se encontró
# ══════════════════════════════════════════════════════════════════════════
#
# El lector no quedó instalado en el primer despliegue y la pantalla decía «el
# servidor no tiene el lector» pasara lo que pasara. Ese mensaje era una
# conjetura: podía ser que no estuviera, que estuviera en otro lado, o que le
# faltara el idioma. Sin saber cuál, arreglarlo son vueltas de despliegue a
# ciegas — y eso costó una entera.

def test_LA_VARIABLE_DEL_AMBIENTE_MANDA_SOBRE_TODO_LO_DEMAS(monkeypatch):
    """Es la salida cuando el programa aterriza donde la lista no mira.

    Tiene que poder arreglarse desde el panel del servidor: acá configurar
    nunca puede exigir editar código y volver a desplegar.
    """
    monkeypatch.setenv(lector.VARIABLE_DEL_PROGRAMA, "/un/lugar/raro/tesseract")
    assert lector._donde_esta_el_programa() == "/un/lugar/raro/tesseract"


def test_SIN_VARIABLE_SE_BUSCA_EN_EL_PATH(monkeypatch):
    """La ruta que devuelve tiene que venir del PATH y de ningún otro lado.

    La primera versión de este test esperaba «/usr/bin/tesseract», que es
    también lo que devuelve la lista de respaldo en una máquina donde el
    programa está ahí. O sea que pasaba sin el PATH, y una mutación que borra
    esa búsqueda entera lo dejaba en verde.

    Ahora la ruta es una que SOLO puede salir del PATH, y la lista de respaldo
    se vacía para que no haya de dónde sacarla.
    """
    monkeypatch.delenv(lector.VARIABLE_DEL_PROGRAMA, raising=False)
    monkeypatch.setattr(lector, "DONDE_SUELE_ESTAR", ())
    monkeypatch.setattr("shutil.which", lambda _: "/solo/desde/el/path/tesseract")
    assert lector._donde_esta_el_programa() == "/solo/desde/el/path/tesseract"


def test_SI_NO_ESTA_EN_EL_PATH_SE_MIRA_DONDE_SUELE_ESTAR(monkeypatch, tmp_path):
    """La lista de respaldo es la que cubre el caso que pasó: instalado por el
    despliegue en un lugar que el PATH del proceso no tenía."""
    falso = tmp_path / "tesseract"
    falso.write_text("#!/bin/sh\n")
    falso.chmod(0o755)

    monkeypatch.delenv(lector.VARIABLE_DEL_PROGRAMA, raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(lector, "DONDE_SUELE_ESTAR", (str(falso),))
    assert lector._donde_esta_el_programa() == str(falso)


def test_SI_NO_ESTA_EN_NINGUN_LADO_SE_DICE_QUE_FALTA_EL_PROGRAMA(monkeypatch):
    """El caso que pasó de verdad: instalado en el despliegue y no encontrado
    por el proceso, que se ve igual que no instalado."""
    monkeypatch.delenv(lector.VARIABLE_DEL_PROGRAMA, raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(lector, "DONDE_SUELE_ESTAR", ())

    motivo = lector.por_que_no_hay_lector()
    assert "tesseract" in motivo
    assert lector.VARIABLE_DEL_PROGRAMA in motivo, (
        "el mensaje tiene que decir CÓMO arreglarlo, no sólo que está mal")
    assert not lector.hay_lector()


def test_SI_EL_PROGRAMA_ESTA_PERO_NO_CORRE_SE_DICE_DONDE_ESTABA(monkeypatch):
    """«Está en /usr/bin pero no se pudo ejecutar» y «no está» se arreglan de
    formas distintas. Un mensaje que los junta no sirve para ninguna."""
    import pytesseract
    monkeypatch.setenv(lector.VARIABLE_DEL_PROGRAMA, "/opt/raro/tesseract")

    def no_corre(*a, **k):
        raise OSError("permiso denegado")
    monkeypatch.setattr(pytesseract, "get_tesseract_version", no_corre)

    motivo = lector.por_que_no_hay_lector()
    assert "/opt/raro/tesseract" in motivo
    assert "permiso denegado" in motivo


def test_CUANDO_EL_LECTOR_ANDA_NO_HAY_MOTIVO_QUE_MOSTRAR():
    """Si devolviera un texto con el lector funcionando, la pantalla mostraría
    una advertencia permanente que nadie volvería a leer."""
    if not lector.hay_lector():
        pytest.skip("este entorno no tiene tesseract; el caso se prueba en el otro")
    assert lector.por_que_no_hay_lector() == ""


def test_LOS_IDIOMAS_SE_PUEDEN_PREGUNTAR_SIN_ROMPER(monkeypatch):
    """Distinguir «no hay lector» de «hay lector sin español» es lo que evita
    la siguiente vuelta de despliegue a ciegas."""
    import pytesseract
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "spa"])
    assert lector.idiomas_instalados() == ["eng", "spa"]


def test_SI_NO_SE_PUEDEN_PREGUNTAR_LOS_IDIOMAS_NO_SE_LEVANTA(monkeypatch):
    """Es un dato de diagnóstico: que falte no puede tumbar la pantalla."""
    import pytesseract

    def revienta(*a, **k):
        raise OSError("no está")
    monkeypatch.setattr(pytesseract, "get_languages", revienta)
    assert lector.idiomas_instalados() == []


# ══════════════════════════════════════════════════════════════════════════
#
# LO QUE FALLABA DE VERDAD NO ERA EL LECTOR
#
# Puesto el diagnóstico, el servidor contestó otra cosa: faltaba
# `libstdc++.so.6`, una pieza de C++ del sistema. Sin ella no carga `numpy`, y
# `pytesseract` importa `numpy` al cargarse — así que `import pytesseract`
# reventaba y el lector nunca llegaba ni a buscar el programa.
#
# El mensaje de entonces decía «falta la librería pytesseract», que era FALSO:
# estaba instalada. Mandar a alguien a revisar requirements.txt cuando lo que
# falta es una pieza del sistema son horas buscando donde no está.

# El sermón tal como lo escupe numpy cuando no encuentra la pieza de C++.
# Se guarda entero, con su media página de consejos, porque el largo es parte
# de lo que hay que probar.
ERROR_DE_NUMPY = ImportError("""

IMPORTANT: PLEASE READ THIS FOR ADVICE ON HOW TO SOLVE THIS ISSUE!

Importing the numpy C-extensions failed. This error can happen for
many reasons, often due to issues with your setup or how NumPy was
installed. We have compiled some common reasons and troubleshooting tips at:

    https://numpy.org/devdocs/user/troubleshooting-importerror.html

Please note and check the following:

  * The Python version is: Python3.11 from "/app/venv/bin/python"
  * The NumPy version is: "2.4.0"

and make sure that they are the versions you expect.

Original error was: libstdc++.so.6: cannot open shared object file: No such file or directory
""")


def _pytesseract_no_carga(monkeypatch, error):
    """Hace que `import pytesseract` falle con ese error, como en el servidor.

    Se toca el import y no `sys.modules` porque lo que hay que reproducir es
    justamente que la librería ESTA y aun así no carga.
    """
    import builtins
    de_verdad = builtins.__import__

    def falla(nombre, *a, **k):
        if nombre == "pytesseract":
            raise error
        return de_verdad(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", falla)


def test_SI_FALTA_UNA_PIEZA_DEL_SISTEMA_SE_DICE_CUAL_Y_NO_QUE_FALTE_PYTESSERACT(monkeypatch):
    """El caso que pasó en producción, entero y por el camino de verdad."""
    _pytesseract_no_carga(monkeypatch, ERROR_DE_NUMPY)

    motivo = lector.por_que_no_hay_lector()
    assert "libstdc++.so.6" in motivo, (
        "sin el nombre del archivo que falta no hay nada accionable")
    assert "Falta la librería pytesseract" not in motivo, (
        "pytesseract ESTA instalada: decir que falta manda a buscar donde no está")
    assert not lector.hay_lector()


def _el_programa_no_corre(monkeypatch, texto):
    """El único camino cuyo mensaje PEGA adentro el texto de una excepción.

    La primera versión de estos dos tests usaba el camino de numpy, cuyo
    mensaje lo escribe este archivo y ya sale corto. Así que pasaban con el
    recorte borrado: probaban que un texto corto es corto.
    """
    import pytesseract
    monkeypatch.setenv(lector.VARIABLE_DEL_PROGRAMA, "/opt/raro/tesseract")

    def no_corre(*a, **k):
        raise OSError(texto)
    monkeypatch.setattr(pytesseract, "get_tesseract_version", no_corre)


def test_EL_MOTIVO_NO_PUEDE_SER_UNA_PARED_DE_TEXTO(monkeypatch):
    """El sermón de numpy tapó el encabezado del panel y no se entendía nada.

    Un motivo que no se puede leer no sirve más que el sí/no que había antes.
    """
    _el_programa_no_corre(monkeypatch, str(ERROR_DE_NUMPY))
    assert len(lector.por_que_no_hay_lector()) <= lector.LARGO_MAXIMO_DEL_MOTIVO


def test_EL_MOTIVO_ES_UN_RENGLON_Y_NO_UN_PARRAFO(monkeypatch):
    """Recortar sin juntar los renglones deja un pedazo de párrafo torcido.

    Son dos cosas distintas y por eso son dos tests: un texto de tres
    renglones cortos entra en el tope y aun así desarma el encabezado.
    """
    _el_programa_no_corre(monkeypatch, "se cayó\n   por\n   algo")

    motivo = lector.por_que_no_hay_lector()
    assert "\n" not in motivo
    assert "se cayó por algo" in motivo, "juntar no puede perder lo que decía"


def test_SI_LA_LIBRERIA_FALTA_DE_VERDAD_SE_MANDA_A_REQUIREMENTS(monkeypatch):
    """«No está instalada» y «está pero no carga» se arreglan en dos lugares
    distintos. Un mensaje que los junta no sirve para ninguno."""
    _pytesseract_no_carga(
        monkeypatch,
        ModuleNotFoundError("No module named 'pytesseract'", name="pytesseract"))

    motivo = lector.por_que_no_hay_lector()
    assert "requirements.txt" in motivo


def test_SI_NO_CARGA_POR_OTRA_COSA_SE_MANDA_AL_REGISTRO(monkeypatch):
    """Ningún mensaje adivina: lo que no se sabe explicar se dice que está en
    el registro, donde sí entra un texto largo."""
    _pytesseract_no_carga(monkeypatch, RuntimeError("algo que nadie previó"))

    motivo = lector.por_que_no_hay_lector()
    assert motivo, "quedarse callado deja la pantalla sin explicación"
    assert "registro" in motivo
    assert len(motivo) <= lector.LARGO_MAXIMO_DEL_MOTIVO
