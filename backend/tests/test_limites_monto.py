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

El modulo no toca red ni Mongo, asi que se carga por ruta directa para no
arrastrar services/__init__.py (que importa twilio y otras dependencias).
"""
import importlib.util
import os

import pytest

_RUTA = os.path.join(os.path.dirname(__file__), "..", "services", "limits.py")
_spec = importlib.util.spec_from_file_location("limits_bajo_prueba", _RUTA)
limits = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(limits)


# ─── PIX: bordes ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("monto", [10, 10.0, 500, 4999.99, 5000, 5000.0])
def test_pix_acepta_dentro_de_rango(monto):
    assert limits.validate_pix_amount(monto) is None


@pytest.mark.parametrize("monto", [0.01, 1, 9.99])
def test_pix_rechaza_por_debajo_del_minimo(monto):
    error = limits.validate_pix_amount(monto)
    assert error is not None
    assert "mínimo" in error


@pytest.mark.parametrize("monto", [5000.01, 5001, 50000])
def test_pix_rechaza_por_encima_del_maximo(monto):
    """El caso que antes no validaba nadie."""
    error = limits.validate_pix_amount(monto)
    assert error is not None
    assert "máximo" in error


@pytest.mark.parametrize("monto", [0, -1, -5000])
def test_pix_rechaza_cero_y_negativos(monto):
    assert limits.validate_pix_amount(monto) is not None


# ─── Bolivares: piso si, techo no ─────────────────────────────────────────

@pytest.mark.parametrize("monto", [100, 100.0, 5000, 10_000_000])
def test_ves_no_tiene_techo(monto):
    """Decision de negocio: la recarga en bolivares no se limita por arriba."""
    assert limits.validate_ves_amount(monto) is None


@pytest.mark.parametrize("monto", [0.01, 50, 99.99])
def test_ves_rechaza_por_debajo_del_minimo(monto):
    error = limits.validate_ves_amount(monto)
    assert error is not None
    assert "mínimo" in error


def test_ves_rechaza_cero():
    assert limits.validate_ves_amount(0) is not None


# ─── Mensajes ─────────────────────────────────────────────────────────────

def test_el_mensaje_trae_el_numero_como_lo_ve_el_usuario():
    """Miles con punto y decimales con coma, no el 5000.0 crudo de Python."""
    assert "R$ 5.000,00" in limits.validate_pix_amount(999999)
    assert "R$ 10,00" in limits.validate_pix_amount(1)
    assert "100,00 VES" in limits.validate_ves_amount(1)


# ─── Payload para el frontend ─────────────────────────────────────────────

def test_payload_tiene_la_forma_que_consume_la_pantalla():
    payload = limits.limits_payload()
    assert payload["pix"]["min_brl"] == limits.PIX_MIN_BRL
    assert payload["pix"]["max_brl"] == limits.PIX_MAX_BRL
    assert payload["ves"]["min_ves"] == limits.VES_MIN


def test_payload_marca_que_ves_no_tiene_techo():
    """None y no 0: un 0 haria que la pantalla rechace todo."""
    assert limits.limits_payload()["ves"]["max_ves"] is None


def test_los_numeros_son_los_acordados():
    """Guarda contra un cambio accidental: si esto cambia, es una decision de
    negocio y tiene que ser deliberada."""
    assert limits.PIX_MIN_BRL == 10.0
    assert limits.PIX_MAX_BRL == 5000.0
    assert limits.VES_MIN == 100.0
    assert limits.VES_MAX is None


# ─── Entradas basura ──────────────────────────────────────────────────────

@pytest.mark.parametrize("basura", [None, "", "abc", "10,50", [], {}])
def test_entradas_no_numericas_devuelven_mensaje_y_no_revientan(basura):
    assert limits.validate_pix_amount(basura) is not None
    assert limits.validate_ves_amount(basura) is not None


def test_acepta_numeros_como_string():
    """El frontend manda JSON; que llegue "1500" en vez de 1500 no debe romper."""
    assert limits.validate_pix_amount("1500") is None
    assert limits.validate_ves_amount("150") is None
