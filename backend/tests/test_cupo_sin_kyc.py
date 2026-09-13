"""
El cupo de una cuenta sin KYC: 200 RIS o 2 operaciones, lo que pase primero.

CONTEXTO
    Antes de esto, ninguna de las tres vias de dinero miraba el KYC en el servidor.
    /gestor/pix/create usaba una dependencia con el comentario "PIX recharge
    available to all users", /reais/send tomaba get_current_user en vez de
    get_verified_user (que existe en el repo y hace ese chequeo), y /recharge/ves
    igual. El unico bloqueo vivia en Recharge.jsx, o sea que por API un usuario sin
    verificar podia recargar y enviar cualquier monto, las veces que quisiera.

LA REGLA QUE SE PRUEBA
    Sin KYC aprobado: hasta 200 RIS acumulados Y hasta 2 operaciones completadas.
    Se agota con lo que pase primero, y no se renueva. Por eso cualquier monto
    mayor a 200 exige verificar: no hay forma de que entre en el cupo.
    El super_admin y los usuarios verificados estan exentos.

QUE SE CUBRE
    1. Los cinco escenarios acordados, uno por uno.
    2. Que el consumo sea el $inc que se mergea en el update del saldo — es lo que
       garantiza que contador y saldo no se puedan desincronizar.
    3. Exenciones: verificado y super_admin.
    4. Documentos incompletos o corruptos no revientan el chequeo.
    5. El payload que consume la pantalla.
    6. Y LO NUEVO: que cambiar los dos numeros desde el panel cambie de verdad
       lo que el servidor hace cumplir.

POR QUE AHORA HACE FALTA UNA BASE DE DATOS
    Los dos numeros salian de constantes en el .py. Ahora salen del catalogo de
    `services/configuracion.py`, para que se cambien desde el panel sin
    desplegar, y leerlos es una consulta.

    Este archivo antes cargaba el modulo por ruta directa para no arrastrar
    `services/__init__.py`. Ahora usa la base de mentira, igual que el resto.

EL ACUMULADO SIGUE SIENDO UN `float` EN LA BASE
    `kyc_quota.ris` se incrementa con el mismo $inc que mueve el saldo, y
    pasarlo a Decimal128 seria mudar datos de cuentas reales. Queda pendiente.
    Lo que si es Decimal es la COMPARACION, y por eso `quota_used` devuelve
    Decimal: sumar un Decimal con un float levanta TypeError en Python.
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
from services import configuracion                                  # noqa: E402
from services import kyc_quota as kq                                # noqa: E402


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


def usuario(ops=0, ris=0.0, role="user", estado="unverified"):
    return {
        "user_id": "u1",
        "role": role,
        "verification_status": estado,
        "kyc_quota": {"ops": ops, "ris": ris},
    }


# ─── Los escenarios acordados ─────────────────────────────────────────────

def test_dos_operaciones_de_50_agotan_aunque_sobre_monto(base):
    """Gasto 100 de 200, pero uso las 2 operaciones: no puede operar mas."""
    assert corre(kq.check_amount(base, usuario(ops=2, ris=100.0), 10)) is not None


def test_una_sola_operacion_de_200_agota_el_cupo(base):
    assert corre(kq.check_amount(base, usuario(), 200)) is None
    assert corre(kq.is_exhausted(base, usuario(ops=1, ris=200.0))) is True


def test_120_y_despues_100_se_rechaza_porque_lo_llevaria_a_220(base):
    assert corre(kq.check_amount(base, usuario(ops=1, ris=120.0), 100)) is not None


def test_120_y_despues_80_pasa_y_queda_justo_en_200(base):
    assert corre(kq.check_amount(base, usuario(ops=1, ris=120.0), 80)) is None


def test_una_primera_operacion_de_500_se_rechaza(base):
    """Ninguna operacion puede superar el techo total, ni siendo la primera."""
    assert corre(kq.check_amount(base, usuario(), 500)) is not None


@pytest.mark.parametrize("monto", [200.01, 201, 500, 5000])
def test_cualquier_monto_mayor_a_200_exige_kyc(base, monto):
    assert corre(kq.check_amount(base, usuario(), monto)) is not None


@pytest.mark.parametrize("monto", [0.01, 10, 199.99, 200])
def test_hasta_200_pasa_en_la_primera(base, monto):
    assert corre(kq.check_amount(base, usuario(), monto)) is None


# ─── El consumo va pegado al saldo ────────────────────────────────────────

def test_consume_inc_es_un_inc_mergeable():
    """La forma tiene que servir para {"$inc": {"balance_ris": m, **consume_inc(m)}}."""
    inc = kq.consume_inc(120.5)
    assert inc == {"kyc_quota.ops": 1, "kyc_quota.ris": 120.5}
    combinado = {"balance_ris": 120.5, **inc}
    assert set(combinado) == {"balance_ris", "kyc_quota.ops", "kyc_quota.ris"}


def test_consume_inc_tolera_basura():
    assert kq.consume_inc(None)["kyc_quota.ris"] == 0.0
    assert kq.consume_inc("abc")["kyc_quota.ops"] == 1


def test_EL_ACUMULADO_SE_SIGUE_ESCRIBIENDO_COMO_NUMERO_COMUN():
    """A propósito, y anotado: pasarlo a Decimal128 es mudar datos guardados.

    Y hay un motivo más para no hacerlo de a poco: `mongomock` no sabe sumar con
    Decimal128, así que la mitad de la suite del dinero se apagaría el día que
    alguien lo cambie sin más. Si esto se rompe, es porque alguien empezó esa
    migración — y entonces hace falta mirar también el `$inc`.
    """
    assert isinstance(kq.consume_inc(10)["kyc_quota.ris"], float)


# ─── Exenciones ───────────────────────────────────────────────────────────

def test_usuario_verificado_no_tiene_cupo(base):
    assert corre(kq.check_amount(
        base, usuario(ops=99, ris=99999.0, estado="verified"), 5000)) is None
    assert corre(kq.is_exhausted(
        base, usuario(ops=99, ris=99999.0, estado="verified"))) is False


def test_super_admin_esta_exento(base):
    assert corre(kq.check_amount(
        base, usuario(ops=99, ris=99999.0, role="super_admin"), 5000)) is None


def test_pending_no_es_verificado(base):
    """Mandar el KYC no alcanza: tiene que estar aprobado."""
    assert corre(kq.check_amount(base, usuario(estado="pending"), 500)) is not None


# ─── Documentos incompletos ───────────────────────────────────────────────

@pytest.mark.parametrize("doc", [
    None, {}, {"role": "user"}, {"kyc_quota": None},
    {"kyc_quota": {"ops": "x", "ris": "y"}},
])
def test_documentos_raros_no_revientan(base, doc):
    assert kq.quota_used(doc) == (0, Decimal("0"))
    corre(kq.check_amount(base, doc, 10))  # no debe lanzar


def test_contadores_negativos_se_tratan_como_cero():
    assert kq.quota_used(usuario(ops=-5, ris=-100.0)) == (0, Decimal("0"))


def test_EL_ACUMULADO_SE_LEE_COMO_DECIMAL(base):
    """Lo guardado es un `float` y lo que sale de acá es un `Decimal`.

    Es lo que hace posible comparar contra el cupo, que ahora es `Decimal`:
    sumar un `Decimal` con un `float` levanta `TypeError` en Python. Si esta
    conversión se cayera, la primera operación de cualquier cuenta sin verificar
    reventaría con un error del servidor.
    """
    ops, ris = kq.quota_used(usuario(ops=1, ris=120.5))
    assert isinstance(ris, Decimal) and ris == Decimal("120.50")
    assert isinstance(ops, int)
    # Y la suma que sin la conversión explotaría:
    assert corre(kq.check_amount(base, usuario(ops=1, ris=120.5), 79.5)) is None


# ─── Payload para la pantalla ─────────────────────────────────────────────

def test_payload_sin_kyc_dice_cuanto_queda(base):
    p = corre(kq.quota_payload(base, usuario(ops=1, ris=120.0)))
    assert p["aplica"] is True and p["agotado"] is False
    assert p["ris_restantes"] == 80.0 and p["ops_restantes"] == 1


def test_payload_verificado_no_muestra_limite(base):
    p = corre(kq.quota_payload(base, usuario(estado="verified")))
    assert p["aplica"] is False and p["ris_restantes"] is None and p["agotado"] is False


def test_payload_marca_agotado_por_operaciones(base):
    assert corre(kq.quota_payload(base, usuario(ops=2, ris=10.0)))["agotado"] is True


def test_payload_marca_agotado_por_monto(base):
    assert corre(kq.quota_payload(base, usuario(ops=1, ris=200.0)))["agotado"] is True


def test_los_montos_del_payload_salen_como_numero_y_no_como_texto(base):
    """La ventana flotante los compara con `parseFloat`. Mismo motivo que en
    `services/limits.limits_payload`."""
    p = corre(kq.quota_payload(base, usuario(ops=1, ris=120.0)))
    for campo in ("max_ris", "ris_usados", "ris_restantes"):
        assert isinstance(p[campo], (int, float)), \
            f"{campo} salió como {type(p[campo]).__name__}"
    assert isinstance(p["max_ops"], int)


# ─── Que el panel de verdad mande ─────────────────────────────────────────

def test_los_numeros_de_fabrica_son_los_acordados(base):
    """Guarda contra un cambio accidental: son reglas de negocio, y además
    están PUBLICADAS en la página de «cómo funciona»."""
    assert corre(configuracion.leer(base, "cupo_sin_verificar_ris")) == Decimal("200.00")
    assert corre(configuracion.leer(base, "cupo_sin_verificar_operaciones")) == 2
    assert kq.EXEMPT_ROLES == {"super_admin"}


def test_CAMBIAR_EL_CUPO_EN_RIS_DESDE_EL_PANEL_CAMBIA_LO_QUE_SE_VALIDA(base):
    assert corre(kq.check_amount(base, usuario(), 300)) is not None
    poner(base, "cupo_sin_verificar_ris", "500")
    assert corre(kq.check_amount(base, usuario(), 300)) is None
    assert corre(kq.check_amount(base, usuario(), 500.01)) is not None


def test_cambiar_el_cupo_de_operaciones_desde_el_panel_cambia_lo_que_se_valida(base):
    assert corre(kq.check_amount(base, usuario(ops=2, ris=0.0), 10)) is not None
    poner(base, "cupo_sin_verificar_operaciones", 5)
    assert corre(kq.check_amount(base, usuario(ops=2, ris=0.0), 10)) is None


def test_el_mensaje_de_rechazo_cita_el_numero_configurado(base):
    """Y no el de fábrica. Un mensaje que dice «200 RIS» cuando el cupo está en
    500 manda a la persona a verificar su cuenta sin necesidad."""
    poner(base, "cupo_sin_verificar_ris", "500")
    error = corre(kq.check_amount(base, usuario(), 600))
    assert "500" in error and "200" not in error


def test_el_payload_tambien_sigue_al_panel(base):
    poner(base, "cupo_sin_verificar_ris", "350")
    p = corre(kq.quota_payload(base, usuario(ops=1, ris=100.0)))
    assert p["max_ris"] == 350.0
    assert p["ris_restantes"] == 250.0
