"""
tests/test_archivo_de_pagos.py — Que el texto que se pega en el banco sea el correcto.

POR QUE ESTE ARCHIVO IMPORTA MAS QUE OTROS

    Lo que sale de acá no lo revisa nadie: se baja, se copia y se pega en la
    banca en línea. No hay una pantalla intermedia donde el error se vea. Un
    monto con el separador equivocado, una cuenta a la que le falta un dígito o
    una orden que no aparece en el archivo son plata que sale mal, o que no
    sale y nadie nota.

    Por eso varios de estos tests comparan el texto LETRA POR LETRA contra el
    formato que se usa hoy a mano, en vez de comprobar que «contenga» algo.
"""
import os
import sys
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import archivo_de_pagos as ap                       # noqa: E402
from services import bancos_venezuela as bancos                   # noqa: E402
from services.money import to_decimal128                          # noqa: E402

BDV = "0102"
BANESCO = "0134"


def _orden(nombre="ANA PEREZ", documento="V-12345678", cuenta=None, telefono=None,
           banco=None, tipo="transferencia", monto="1000.00", display_id="#000001",
           decimal128=False):
    return {
        "orden_id": "tx_" + display_id,
        "display_id": display_id,
        # El monto se puede escribir como lo escribe la aplicación (Decimal128)
        # o como quedó en los datos viejos (float). Las dos formas tienen que
        # dar el mismo texto: si no, el archivo depende de cuándo se cargó la
        # orden.
        "destino": {"valor": to_decimal128(monto) if decimal128 else float(monto),
                    "unidad": "VES"},
        "beneficiario": {"nombre": nombre, "documento": documento, "cuenta": cuenta,
                         "telefono": telefono, "bank": banco, "tipo_pago": tipo},
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. Los tres formatos, letra por letra
# ══════════════════════════════════════════════════════════════════════════

def test_LA_LINEA_DE_OTROS_BANCOS_SALE_EXACTA():
    """Copiada del archivo que se usa hoy: dos espacios entre campos, «BS»
    suelto, y el monto sin separador de miles."""
    r = ap.armar([_orden("Yoan Patricia Andrés Pabón", "V-17144009",
                         cuenta="01380026080260010870", monto="30660.00")],
                 banco_pagador=BDV)
    assert ("1  Yoan Patricia Andrés Pabón  V-17144009  "
            "01380026080260010870  BS  30660,00") in r["texto"], r["texto"]


def test_LA_LINEA_DE_MISMO_BANCO_SALE_EXACTA():
    """El formato de mismo banco usa UN espacio, no dos. No es un detalle
    estético: quien paga lo lee todos los días y lo reconoce por la forma."""
    r = ap.armar([_orden("MARIA MAGDALENA MUNOZ MELENDEZ", "V-14852171",
                         cuenta="01020121710106529080", monto="51932.50")],
                 banco_pagador=BDV)
    assert ("1 MARIA MAGDALENA MUNOZ MELENDEZ V-14852171 "
            "01020121710106529080 BS 51932,50") in r["texto"], r["texto"]


def test_EL_BLOQUE_DE_PAGO_MOVIL_SALE_EXACTO():
    """Cuatro líneas y sin número: el bloque se copia entero en el formulario
    del banco, y un número al principio sería un dato que hay que saltear."""
    r = ap.armar([_orden(documento="12345678", telefono="04141234567",
                         banco="0102", tipo="pago_movil", monto="93478.50")],
                 banco_pagador=BANESCO)
    assert "12345678\n04141234567\n0102\nBS 93478,50" in r["texto"], r["texto"]


# ══════════════════════════════════════════════════════════════════════════
# 2. El banco pagador, que es de lo que se trata todo esto
# ══════════════════════════════════════════════════════════════════════════

def test_LA_MISMA_ORDEN_CAMBIA_DE_SECCION_SEGUN_DESDE_DONDE_SE_PAGUE():
    """Es la razón por la que el banco pagador es un dato del lote y no una
    constante: el mismo beneficiario es «mismo banco» un día y «otros bancos»
    al siguiente, según desde dónde se pague."""
    orden = _orden(cuenta="01020121710106529080", monto="100.00")
    desde_bdv = ap.armar([orden], banco_pagador=BDV)["por_seccion"]
    desde_banesco = ap.armar([orden], banco_pagador=BANESCO)["por_seccion"]
    assert desde_bdv[ap.MISMO_BANCO] == 1 and desde_bdv[ap.OTROS_BANCOS] == 0
    assert desde_banesco[ap.MISMO_BANCO] == 0 and desde_banesco[ap.OTROS_BANCOS] == 1


# ══════════════════════════════════════════════════════════════════════════
# 3. Lo que no se puede pagar no desaparece
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("roto,por_que", [
    ({"cuenta": "123"}, "cuenta corta"),
    ({"cuenta": None}, "sin cuenta"),
    # Diecinueve dígitos, y empiezan con un banco de verdad. Es el caso que
    # SOLO agarra el largo: el banco se reconoce, así que sin esa comprobación
    # la orden saldría en el archivo con una cuenta a la que le falta un
    # dígito, y ese pago se rechaza o cae en otro lado.
    ({"cuenta": "0134021911219104651", "banco": "Banesco"}, "cuenta de 19"),
    ({"cuenta": "013402191121910465166", "banco": "Banesco"}, "cuenta de 21"),
    ({"cuenta": "01020121710106529080", "banco": "banco que no existe"}, "banco desconocido"),
])
def test_UNA_ORDEN_QUE_NO_SE_PUEDE_PAGAR_NO_SE_SALTEA(roto, por_que):
    """Un archivo con diez líneas cuando el lote tenía once es un pago que no
    se hizo y que nadie nota hasta que el cliente reclama."""
    datos = {"cuenta": "01020121710106529080", "monto": "500.00", "display_id": "#000099"}
    datos.update(roto)
    r = ap.armar([_orden(**datos)], banco_pagador=BANESCO)
    if por_que == "banco desconocido":
        # La cuenta empieza con el código: se usa ésa antes de rendirse.
        assert r["por_seccion"][ap.SIN_DATOS] == 0, "la cuenta traía el código"
        return
    assert r["por_seccion"][ap.SIN_DATOS] == 1, r
    assert "#000099" in r["sin_datos"], r["sin_datos"]
    assert "#000099" in r["texto"], "no aparece en el archivo que ve el operador"


@pytest.mark.parametrize("falta", ["telefono", "documento", "banco"])
def test_UN_PAGO_MOVIL_INCOMPLETO_TAMPOCO_SE_SALTEA(falta):
    datos = {"documento": "12345678", "telefono": "04141234567", "banco": "0102",
             "tipo": "pago_movil", "monto": "300.00"}
    datos[falta] = None
    r = ap.armar([_orden(**datos)], banco_pagador=BANESCO)
    assert r["por_seccion"][ap.SIN_DATOS] == 1, f"sin {falta} igual salió como pagable"


def test_la_cuenta_cuando_el_campo_del_banco_no_dice_nada():
    """Los veinte dígitos empiezan con el código del banco. Usarlo no es
    adivinar: está en el mismo número que se va a pegar."""
    r = ap.armar([_orden(cuenta="01340219112191046516", banco="", monto="10.00")],
                 banco_pagador=BDV)
    assert r["por_seccion"][ap.OTROS_BANCOS] == 1, r
    assert "Banesco" in r["texto"]


# ══════════════════════════════════════════════════════════════════════════
# 4. El dinero
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("valor,texto", [
    ("30660.00", "30660,00"),
    ("177028.00", "177028,00"),
    ("114552.10", "114552,10"),
    ("413600.00", "413600,00"),
    ("0.50", "0,50"),
])
def test_EL_MONTO_VA_SIN_SEPARADOR_DE_MILES(valor, texto):
    """Un punto de miles metido en el campo de un formulario bancario lo
    rechaza, o peor, lo interpreta."""
    assert ap.monto(Decimal(valor)) == texto


def test_da_igual_como_este_guardado_el_monto():
    """`Decimal128`, como lo escribe la aplicación, y `float`, como quedó en
    los datos viejos. El archivo no puede depender de eso."""
    viejo = ap.armar([_orden(cuenta="01020121710106529080", monto="51932.50",
                             decimal128=False)], banco_pagador=BDV)["texto"]
    nuevo = ap.armar([_orden(cuenta="01020121710106529080", monto="51932.50",
                             decimal128=True)], banco_pagador=BDV)["texto"]
    assert viejo == nuevo, "el mismo monto sale distinto según cómo se guardó"
    assert "51932,50" in nuevo


def test_el_monto_no_se_redondea_a_menos_de_dos_decimales():
    assert ap.monto(Decimal("42065.333")) == "42065,33"


# ══════════════════════════════════════════════════════════════════════════
# 5. La cédula
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("guardado", ["V-17144009", "17144009", "v17144009", "V 17.144.009"])
def test_la_cedula_sale_igual_sin_importar_como_se_guardo(guardado):
    assert ap.documento(guardado, con_prefijo=True) == "V-17144009"
    assert ap.documento(guardado, con_prefijo=False) == "17144009"


def test_una_cedula_que_no_es_V_conserva_su_letra():
    """Hay beneficiarios con E, J, G o P. Ponerles «V-» a todos es un dato
    equivocado en un formulario bancario."""
    assert ap.documento("E-81234567", con_prefijo=True) == "E-81234567"
    assert ap.documento("J-309876543", con_prefijo=True) == "J-309876543"


# ══════════════════════════════════════════════════════════════════════════
# 6. El orden y los nombres
# ══════════════════════════════════════════════════════════════════════════

def test_LA_NUMERACION_ARRANCA_DE_NUEVO_EN_CADA_BANCO():
    """En la banca en línea se carga un banco por vez: el número es la
    posición dentro de ESA carga, no dentro del lote."""
    r = ap.armar([
        _orden("UNO", cuenta="01340219112191046516", monto="1.00"),
        _orden("DOS", cuenta="01340384833843094170", monto="2.00"),
        _orden("TRES", cuenta="01080340380200079549", monto="3.00"),
    ], banco_pagador=BDV)
    assert "1  UNO  " in r["texto"] and "2  DOS  " in r["texto"], r["texto"]
    assert "1  TRES  " in r["texto"], "el tercero, de otro banco, no volvió a 1"


def test_los_bancos_salen_siempre_en_el_mismo_orden():
    """Si el orden cambiara de lote en lote, quien paga tendría que buscar el
    suyo cada vez en vez de saber dónde está."""
    ordenes = [
        _orden("Z", cuenta="01910199132100033592", monto="1.00"),
        _orden("A", cuenta="01080340380200079549", monto="2.00"),
        _orden("M", cuenta="01340219112191046516", monto="3.00"),
    ]
    texto = ap.armar(ordenes, banco_pagador=BDV)["texto"]
    al_reves = ap.armar(list(reversed(ordenes)), banco_pagador=BDV)["texto"]
    assert texto == al_reves, "el archivo cambia según el orden en que entraron"
    assert texto.index("Provincial") < texto.index("Banesco") < texto.index("Nacional")


def test_EL_APODO_PISA_EL_NOMBRE_DEL_CATALOGO():
    """«BNC» es como lo tiene anotado quien paga. Obligar a editar código para
    cambiar un rótulo sería justo lo que este repositorio no hace."""
    ordenes = [_orden(cuenta="01910199132100033592", monto="1.00")]
    sin = ap.armar(ordenes, banco_pagador=BDV)["texto"]
    con = ap.armar(ordenes, banco_pagador=BDV, apodos={"0191": "BNC"})["texto"]
    assert "Banco Nacional de Crédito" in sin
    assert "— BNC (1) —" in con and "Banco Nacional de Crédito" not in con


# ══════════════════════════════════════════════════════════════════════════
# 7. La tabla de bancos
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("guardado,codigo", [
    ({"bank_code": "0134"}, "0134"),
    ({"bank": "0102"}, "0102"),
    ({"bank": "Banesco"}, "0134"),
    # Los nombres largos son los que escriben los propios comprobantes del banco.
    ({"bank": "BANESCO BANCO UNIVERSAL S.A.C.A."}, "0134"),
    ({"bank": "BANCO DIGITAL DE LOS TRABAJADORES"}, "0175"),
    ({"bank": "Banco Provincial"}, "0108"),
])
def test_el_banco_se_reconoce_venga_como_venga(guardado, codigo):
    assert bancos.codigo_de(guardado) == codigo


@pytest.mark.parametrize("escrito,codigo", [
    ("Banco Caroni", "0128"),      # sin la tilde de «Caroní»
    ("Banco Agricola", "0166"),    # sin la tilde de «Agrícola»
    ("BANESCO, C.A.", "0134"),     # con puntuación de más
    ("  banesco  ", "0134"),       # con espacios y en minúscula
])
def test_UN_BANCO_ESCRITO_CON_OTRA_ORTOGRAFIA_SE_RECONOCE_IGUAL(escrito, codigo):
    """La gente carga el banco a mano y los comprobantes lo escriben a su
    manera. Un beneficiario que quedó sin banco reconocido es una orden que no
    entra al archivo, y eso es un pago que no se hace."""
    assert bancos.codigo_de({"bank": escrito}) == codigo


def test_UN_BANCO_QUE_NO_SE_RECONOCE_NO_SE_ADIVINA():
    """Un banco adivinado mal es un pago que sale hacia otro lado."""
    assert bancos.codigo_de({"bank": "Cooperativa La Esperanza"}) == ""
    assert bancos.codigo_de({}) == ""


def test_UN_NOMBRE_CORTO_DEL_CATALOGO_NO_EMPAREJA_POR_ESTAR_ADENTRO_DE_OTRO():
    """El catálogo tiene «ONT», de tres letras. Sin un mínimo, cualquier banco
    con esas tres letras seguidas —«Banco MONTe Carlo»— se resolvería a él, y
    el pago saldría hacia otro banco.

    Es el único nombre del catálogo con menos de cinco letras, y por eso este
    test lo nombra: si mañana entra otro corto, hay que volver a pensar acá.
    """
    assert bancos.codigo_de({"bank": "Banco Monte Carlo"}) == ""
    assert bancos.codigo_de({"bank": "Banco"}) == ""
