"""
Los limites de monto que anuncia la pantalla tienen que ser los que valida el servidor.

CONTEXTO
    La pantalla de recarga decia "Minimo: R$ 10 - Maximo: R$ 2.000" y validaba
    solo el minimo. El maximo era un atributo max="2000" en el input, que el
    navegador nunca llegaba a aplicar porque el envio va por onClick y no por
    submit nativo. Del lado del servidor, /gestor/pix/create y /reais/send solo
    comprobaban amount > 0. O sea: el techo anunciado no existia en ningun lado
    y se podia recargar o enviar cualquier monto por API.

    En bolivares pasaba lo mismo pero peor: Recharge.jsx exigia 100 VES y
    RechargeVES.jsx —que postea al MISMO endpoint— no exigia nada.

QUE SE CUBRE
    1. Los bordes exactos de PIX: 9,99 y 5.000,01 se rechazan; 10 y 5.000 pasan.
    2. Bolivares tiene piso pero NO techo, a proposito.
    3. Los mensajes salen con el numero formateado como lo ve el usuario.
    4. limits_payload devuelve la forma que el frontend consume, con max_ves en
       None para que la pantalla sepa que ahi no hay techo que mostrar.
    5. Entradas basura (None, texto, vacio) no revientan: devuelven mensaje.
    6. Y LO NUEVO: que cambiar el numero desde el panel cambie de verdad lo que
       el servidor hace cumplir. Antes los limites eran constantes en un .py y
       "cambiar el maximo" era un despliegue.

POR QUE AHORA HACE FALTA UNA BASE DE DATOS
    Porque los numeros salen del catalogo de `services/configuracion.py`, y eso
    es una consulta. Este archivo antes cargaba `limits.py` por ruta directa
    para no arrastrar nada; ahora usa la base de mentira, igual que el resto.
"""
import os
import sys
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                      # noqa: E402
from services import configuracion, limits                          # noqa: E402


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


# ─── PIX: bordes ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("monto", [10, 10.0, 500, 4999.99, 5000, 5000.0])
def test_pix_acepta_dentro_de_rango(base, monto):
    assert corre(limits.validate_pix_amount(base, monto)) is None


@pytest.mark.parametrize("monto", [0.01, 1, 9.99])
def test_pix_rechaza_por_debajo_del_minimo(base, monto):
    error = corre(limits.validate_pix_amount(base, monto))
    assert error is not None
    assert "mínimo" in error


@pytest.mark.parametrize("monto", [5000.01, 5001, 50000])
def test_pix_rechaza_por_encima_del_maximo(base, monto):
    """El caso que antes no validaba nadie."""
    error = corre(limits.validate_pix_amount(base, monto))
    assert error is not None
    assert "máximo" in error


@pytest.mark.parametrize("monto", [0, -1, -5000])
def test_pix_rechaza_cero_y_negativos(base, monto):
    assert corre(limits.validate_pix_amount(base, monto)) is not None


# ─── Tarjeta: su propio par de numeros ────────────────────────────────────

@pytest.mark.parametrize("monto", [5, 5.0, 100, 5000])
def test_la_tarjeta_acepta_dentro_de_su_rango(base, monto):
    assert corre(limits.validate_card_amount(base, monto)) is None


@pytest.mark.parametrize("monto", [4.99, 1, 0.01, 5000.01, 99999])
def test_la_tarjeta_rechaza_fuera_de_su_rango(base, monto):
    assert corre(limits.validate_card_amount(base, monto)) is not None


def test_LA_TARJETA_TIENE_SU_PROPIO_MINIMO_Y_NO_EL_DE_PIX(base):
    """R$ 5 pasa por tarjeta y no pasa por PIX, de fábrica.

    Son dos vías con costos distintos —la tarjeta cobra una comisión fija además
    del porcentaje— y por eso son dos ajustes y no uno. Si alguien los uniera
    "para simplificar", este test se pone rojo antes de que nadie lo note en
    producción.
    """
    assert corre(limits.validate_card_amount(base, 5)) is None
    assert corre(limits.validate_pix_amount(base, 5)) is not None


# ─── Bolivares: piso si, techo no ─────────────────────────────────────────

@pytest.mark.parametrize("monto", [100, 100.0, 5000, 10_000_000])
def test_ves_no_tiene_techo(base, monto):
    """Decision de negocio: la recarga en bolivares no se limita por arriba."""
    assert corre(limits.validate_ves_amount(base, monto)) is None


@pytest.mark.parametrize("monto", [0.01, 50, 99.99])
def test_ves_rechaza_por_debajo_del_minimo(base, monto):
    error = corre(limits.validate_ves_amount(base, monto))
    assert error is not None
    assert "mínimo" in error


def test_ves_rechaza_cero(base):
    assert corre(limits.validate_ves_amount(base, 0)) is not None


# ─── Mensajes ─────────────────────────────────────────────────────────────

def test_el_mensaje_trae_el_numero_como_lo_ve_el_usuario(base):
    """Miles con punto y decimales con coma, no el 5000.0 crudo de Python."""
    assert "R$ 5.000,00" in corre(limits.validate_pix_amount(base, 999999))
    assert "R$ 10,00" in corre(limits.validate_pix_amount(base, 1))
    assert "100,00 VES" in corre(limits.validate_ves_amount(base, 1))


# ─── Payload para el frontend ─────────────────────────────────────────────

def test_payload_tiene_la_forma_que_consume_la_pantalla(base):
    payload = corre(limits.limits_payload(base))
    assert payload["pix"]["min_brl"] == 10.0
    assert payload["pix"]["max_brl"] == 5000.0
    assert payload["tarjeta"]["min_brl"] == 5.0
    assert payload["tarjeta"]["max_brl"] == 5000.0
    assert payload["ves"]["min_ves"] == 100.0


def test_LOS_MONTOS_DEL_PAYLOAD_SALEN_COMO_NUMERO_Y_NO_COMO_TEXTO(base):
    """Seis pantallas los comparan con `parseFloat`.

    El resto del proyecto manda la plata como texto por el borde del API, y con
    razón. Acá no, y es una excepción deliberada: `"10.00" > 5` es verdadero en
    JavaScript, pero `"10.00" > "5"` es FALSO —compara letra por letra— y la
    pantalla dejaría pasar montos fuera de rango sin un solo error en consola.

    Son topes de tres cifras, no saldos: no hay nada que redondear mal.
    """
    payload = corre(limits.limits_payload(base))
    for via, campos in (("pix", ("min_brl", "max_brl")),
                        ("tarjeta", ("min_brl", "max_brl")),
                        ("ves", ("min_ves",))):
        for campo in campos:
            valor = payload[via][campo]
            assert isinstance(valor, (int, float)), \
                f"{via}.{campo} salió como {type(valor).__name__}"
    assert isinstance(payload["sin_verificar"]["max_ris"], (int, float))
    assert isinstance(payload["sin_verificar"]["max_operaciones"], int)


def test_payload_marca_que_ves_no_tiene_techo(base):
    """None y no 0: un 0 haria que la pantalla rechace todo."""
    assert corre(limits.limits_payload(base))["ves"]["max_ves"] is None


def test_los_numeros_de_fabrica_son_los_acordados(base):
    """Guarda contra un cambio accidental: si esto cambia, es una decision de
    negocio y tiene que ser deliberada.

    Ahora mira los valores POR OMISION del catálogo, que es donde viven desde
    que se pueden cambiar desde el panel."""
    assert corre(configuracion.leer(base, "pix_minimo")) == Decimal("10.00")
    assert corre(configuracion.leer(base, "pix_maximo")) == Decimal("5000.00")
    assert corre(configuracion.leer(base, "tarjeta_minimo")) == Decimal("5.00")
    assert corre(configuracion.leer(base, "tarjeta_maximo")) == Decimal("5000.00")
    assert corre(configuracion.leer(base, "ves_minimo")) == Decimal("100.00")
    assert limits.VES_MAX is None


# ─── Que el panel de verdad mande ─────────────────────────────────────────
#
# Es la razón por la que existe todo este cambio. Sin estos tests, los números
# podrían estar leyéndose del catálogo y no cambiar nada, y nadie se enteraría
# hasta que alguien los mueva desde el panel y no pase nada.

def test_CAMBIAR_EL_MAXIMO_DE_PIX_DESDE_EL_PANEL_CAMBIA_LO_QUE_SE_VALIDA(base):
    assert corre(limits.validate_pix_amount(base, 6000)) is not None
    poner(base, "pix_maximo", "8000")
    assert corre(limits.validate_pix_amount(base, 6000)) is None
    assert corre(limits.validate_pix_amount(base, 8000.01)) is not None


def test_cambiar_el_minimo_de_pix_desde_el_panel_cambia_lo_que_se_valida(base):
    assert corre(limits.validate_pix_amount(base, 5)) is not None
    poner(base, "pix_minimo", "1")
    assert corre(limits.validate_pix_amount(base, 5)) is None


def test_cambiar_el_minimo_de_bolivares_desde_el_panel_cambia_lo_que_se_valida(base):
    assert corre(limits.validate_ves_amount(base, 50)) is not None
    poner(base, "ves_minimo", "20")
    assert corre(limits.validate_ves_amount(base, 50)) is None


def test_cambiar_los_limites_de_la_tarjeta_desde_el_panel_cambia_lo_que_se_valida(base):
    assert corre(limits.validate_card_amount(base, 3)) is not None
    poner(base, "tarjeta_minimo", "1")
    assert corre(limits.validate_card_amount(base, 3)) is None


def test_LO_QUE_SE_PUBLICA_SIGUE_AL_PANEL(base):
    """Y el payload también, no sólo la validación.

    Es la mitad que se olvida: si `/limits` siguiera devolviendo el número viejo,
    la pantalla anunciaría un techo distinto del que el servidor hace cumplir —
    que es exactamente el defecto que este módulo existe para haber arreglado.
    """
    poner(base, "pix_maximo", "1234.50")
    payload = corre(limits.limits_payload(base))
    assert payload["pix"]["max_brl"] == 1234.5


def test_un_ajuste_guardado_raro_no_deja_la_via_muerta(base):
    """El catálogo cae al valor de fábrica y lo anota en los registros.

    Un número ilegible en la base no puede dejar a nadie sin poder operar: eso
    convertiría un dedo mal puesto en una caída total de la vía."""
    corre(base[configuracion.COLECCION].update_one(
        {"clave": "pix_maximo"},
        {"$set": {"clave": "pix_maximo", "valor": "no soy un numero"}},
        upsert=True))
    assert corre(limits.validate_pix_amount(base, 100)) is None


# ─── Entradas basura ──────────────────────────────────────────────────────

@pytest.mark.parametrize("basura", [None, "", "abc", "10,50", [], {}])
def test_entradas_no_numericas_devuelven_mensaje_y_no_revientan(base, basura):
    assert corre(limits.validate_pix_amount(base, basura)) is not None
    assert corre(limits.validate_ves_amount(base, basura)) is not None
    assert corre(limits.validate_card_amount(base, basura)) is not None


def test_LA_COMA_DECIMAL_SE_RECHAZA_AUNQUE_EL_PANEL_LA_ACEPTE(base):
    """«1,050» no se sabe si es mil cincuenta o uno coma cero cinco.

    En el panel la coma se normaliza, porque ahí la escribe una persona y así se
    escribe un monto en Brasil. Acá esto llega de un navegador, y leerla mal es
    equivocarse por mil veces. Las dos decisiones son opuestas a propósito.
    """
    for texto in ("10,50", "1,050", "5.000,00"):
        assert corre(limits.validate_pix_amount(base, texto)) is not None


def test_acepta_numeros_como_string(base):
    """El frontend manda JSON; que llegue "1500" en vez de 1500 no debe romper."""
    assert corre(limits.validate_pix_amount(base, "1500")) is None
    assert corre(limits.validate_ves_amount(base, "150")) is None
