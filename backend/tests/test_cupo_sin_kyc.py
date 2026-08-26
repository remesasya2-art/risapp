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

Modulo puro: no toca red ni Mongo, se carga por ruta directa para no arrastrar
services/__init__.py.
"""
import importlib.util
import os

import pytest

_RUTA = os.path.join(os.path.dirname(__file__), "..", "services", "kyc_quota.py")
_spec = importlib.util.spec_from_file_location("kyc_quota_bajo_prueba", _RUTA)
kq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kq)


def usuario(ops=0, ris=0.0, role="user", estado="unverified"):
    return {
        "user_id": "u1",
        "role": role,
        "verification_status": estado,
        "kyc_quota": {"ops": ops, "ris": ris},
    }


# ─── Los escenarios acordados ─────────────────────────────────────────────

def test_dos_operaciones_de_50_agotan_aunque_sobre_monto():
    """Gasto 100 de 200, pero uso las 2 operaciones: no puede operar mas."""
    assert kq.check_amount(usuario(ops=2, ris=100.0), 10) is not None


def test_una_sola_operacion_de_200_agota_el_cupo():
    assert kq.check_amount(usuario(), 200) is None
    assert kq.is_exhausted(usuario(ops=1, ris=200.0)) is True


def test_120_y_despues_100_se_rechaza_porque_lo_llevaria_a_220():
    assert kq.check_amount(usuario(ops=1, ris=120.0), 100) is not None


def test_120_y_despues_80_pasa_y_queda_justo_en_200():
    assert kq.check_amount(usuario(ops=1, ris=120.0), 80) is None


def test_una_primera_operacion_de_500_se_rechaza():
    """Ninguna operacion puede superar el techo total, ni siendo la primera."""
    assert kq.check_amount(usuario(), 500) is not None


@pytest.mark.parametrize("monto", [200.01, 201, 500, 5000])
def test_cualquier_monto_mayor_a_200_exige_kyc(monto):
    assert kq.check_amount(usuario(), monto) is not None


@pytest.mark.parametrize("monto", [0.01, 10, 199.99, 200])
def test_hasta_200_pasa_en_la_primera(monto):
    assert kq.check_amount(usuario(), monto) is None


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


# ─── Exenciones ───────────────────────────────────────────────────────────

def test_usuario_verificado_no_tiene_cupo():
    assert kq.check_amount(usuario(ops=99, ris=99999.0, estado="verified"), 5000) is None
    assert kq.is_exhausted(usuario(ops=99, ris=99999.0, estado="verified")) is False


def test_super_admin_esta_exento():
    assert kq.check_amount(usuario(ops=99, ris=99999.0, role="super_admin"), 5000) is None


def test_pending_no_es_verificado():
    """Mandar el KYC no alcanza: tiene que estar aprobado."""
    assert kq.check_amount(usuario(estado="pending"), 500) is not None


# ─── Documentos incompletos ───────────────────────────────────────────────

@pytest.mark.parametrize("doc", [None, {}, {"role": "user"}, {"kyc_quota": None}, {"kyc_quota": {"ops": "x", "ris": "y"}}])
def test_documentos_raros_no_revientan(doc):
    assert kq.quota_used(doc) == (0, 0.0)
    kq.check_amount(doc, 10)  # no debe lanzar


def test_contadores_negativos_se_tratan_como_cero():
    assert kq.quota_used(usuario(ops=-5, ris=-100.0)) == (0, 0.0)


# ─── Payload para la pantalla ─────────────────────────────────────────────

def test_payload_sin_kyc_dice_cuanto_queda():
    p = kq.quota_payload(usuario(ops=1, ris=120.0))
    assert p["aplica"] is True and p["agotado"] is False
    assert p["ris_restantes"] == 80.0 and p["ops_restantes"] == 1


def test_payload_verificado_no_muestra_limite():
    p = kq.quota_payload(usuario(estado="verified"))
    assert p["aplica"] is False and p["ris_restantes"] is None and p["agotado"] is False


def test_payload_marca_agotado_por_operaciones():
    assert kq.quota_payload(usuario(ops=2, ris=10.0))["agotado"] is True


def test_payload_marca_agotado_por_monto():
    assert kq.quota_payload(usuario(ops=1, ris=200.0))["agotado"] is True


def test_los_numeros_son_los_acordados():
    """Guarda contra un cambio accidental: son reglas de negocio."""
    assert kq.UNVERIFIED_MAX_RIS == 200.0
    assert kq.UNVERIFIED_MAX_OPS == 2
    assert kq.EXEMPT_ROLES == {"super_admin"}
