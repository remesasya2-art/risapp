"""
tests/test_bono_referido.py — El bono que se le paga a un socio.

POR QUE ESTE ARCHIVO EXISTE

    `services/referrals.py` acredita saldo a un socio cada vez que alguien que
    él refirió recarga. Es plata que sale de la empresa, y no tenía un solo test
    que lo importara. Es el quinto de los seis módulos que mueven plata y
    estaban sin cubrir, y otro que reescribí en el PR #57.

LO QUE MAS IMPORTA ACA
    Que el bono se le pague a QUIEN corresponde, UNA vez y por el monto justo.
    Un bono de más sale del bolsillo de la empresa; uno de menos, del socio. Y
    el bono nunca puede tumbar la recarga del usuario referido: él no tiene nada
    que ver con que su socio siga existiendo.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import ledger, referrals, saldos                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def d(x):
    return Decimal128(Decimal(str(x)).quantize(Decimal("0.01")))


@pytest.fixture
def base(monkeypatch):
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    ledger._indexes_ready = True

    import services.notifications as notif

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(notif, "create_notification", _nada)
    return b


async def _mundo(base, rol_socio="socio", referido_por="COD-1",
                 saldo_socio=0, recargas_completadas=1):
    await base.users.insert_many([
        {"user_id": "usr_socio", "email": "socio@x.com", "name": "Socio",
         "role": rol_socio, "referral_code": "COD-1", "balance_ris": d(saldo_socio)},
        # Con su propio código: en la vida real todos lo tienen, y sin él es
        # ELLA la que matchea `{"referral_code": None}` y el guard de rol tapa
        # el caso que se quiere probar.
        {"user_id": "usr_ana", "email": "ana@x.com", "name": "Ana", "role": "user",
         "referral_code": "COD-ANA", "referred_by": referido_por,
         "balance_ris": d(0)},
    ])
    for i in range(recargas_completadas):
        await base.transactions.insert_one({
            "transaction_id": f"tx_{i}", "user_id": "usr_ana",
            "type": "recharge_ves", "status": "completed"})


async def _saldo_socio(base):
    doc = await base.users.find_one({"user_id": "usr_socio"})
    return saldos.saldo_de(doc)


async def _lineas(base):
    return await base.ledger.find({"user_id": "usr_socio"}).to_list(50)


# ══════════════════════════════════════════════════════════════════════════
# 1. El monto: de más sale de la empresa, de menos sale del socio
# ══════════════════════════════════════════════════════════════════════════

def test_la_primera_recarga_paga_hito_MAS_comision(base):
    """Por defecto: 5 de hito + 2% de 1000 = 25."""
    async def caso():
        await _mundo(base, recargas_completadas=1)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("25.00")
    corre(caso())


def test_las_recargas_siguientes_pagan_SOLO_comision(base):
    """El hito es una vez sola. Si se paga siempre, la empresa regala plata en
    cada recarga."""
    async def caso():
        await _mundo(base, recargas_completadas=2)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("20.00")
    corre(caso())


def test_la_comision_sale_de_la_configuracion_y_no_de_un_numero_fijo(base):
    async def caso():
        await _mundo(base, recargas_completadas=2)
        await base.app_settings.insert_one({
            "setting_id": "partner_settings",
            "commission_rate": 5.0, "milestone_bonus": 50.0})
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("50.00")   # 5% de 1000
    corre(caso())


def test_el_hito_configurado_tambien_se_respeta(base):
    async def caso():
        await _mundo(base, recargas_completadas=1)
        await base.app_settings.insert_one({
            "setting_id": "partner_settings",
            "commission_rate": 5.0, "milestone_bonus": 50.0})
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("100.00")  # 50 + 5%
    corre(caso())


def test_el_bono_se_suma_al_saldo_que_el_socio_ya_tenia(base):
    async def caso():
        await _mundo(base, saldo_socio=500, recargas_completadas=2)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("520.00")
        linea, = await _lineas(base)
        assert (linea["balance_before"], linea["balance_after"]) == (500.0, 520.0)
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. A quién: el bono no puede caer en la cuenta equivocada
# ══════════════════════════════════════════════════════════════════════════

def test_un_usuario_sin_referente_no_genera_bono(base):
    async def caso():
        await _mundo(base, referido_por=None)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("0.00")
        assert await _lineas(base) == []
    corre(caso())


def test_sin_referente_el_bono_NO_cae_en_un_socio_sin_codigo(base):
    """El caso que hace falta el guard, y que un test ingenuo no ve.

    Sin `referred_by`, la búsqueda del socio sería
    `find_one({"referral_code": None})`. En Mongo eso NO devuelve vacío: matchea
    los documentos donde el campo es null **o donde no existe**. Cualquier socio
    que nunca recibió código cobraría el bono de un usuario que no refirió nadie.

    Lo descubrí por mutación: quitar la mitad `not user.get("referred_by")` de
    la guarda no ponía ningún test en rojo, porque en mi escenario no había
    ningún socio sin código.
    """
    async def caso():
        await _mundo(base, referido_por=None)
        # Un socio de verdad, sin código de referido: el que se llevaría el bono.
        await base.users.insert_one({
            "user_id": "usr_socio_sin_codigo", "email": "s2@x.com",
            "name": "Socio Sin Código", "role": "socio", "balance_ris": d(0)})
        await referrals.process_referral_bonus("usr_ana", 1000.0)

        doc = await base.users.find_one({"user_id": "usr_socio_sin_codigo"})
        assert saldos.saldo_de(doc) == Decimal("0.00"), (
            "el bono cayó en un socio que no refirió a nadie")
        assert await base.ledger.count_documents({}) == 0
    corre(caso())


def test_un_codigo_de_referido_que_no_existe_no_genera_bono(base):
    async def caso():
        await _mundo(base, referido_por="COD-INVENTADO")
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("0.00")
    corre(caso())


@pytest.mark.parametrize("rol", ["user", "admin", "agent"])
def test_solo_los_socios_cobran_bono(base, rol):
    """Si cualquiera cobrara, alcanzaría con auto-referirse para sacar plata."""
    async def caso():
        await _mundo(base, rol_socio=rol)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("0.00")
        assert await _lineas(base) == []
    corre(caso())


@pytest.mark.parametrize("rol", ["socio", "socio_gestor"])
def test_los_dos_roles_de_socio_SI_cobran(base, rol):
    async def caso():
        await _mundo(base, rol_socio=rol, recargas_completadas=2)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        assert await _saldo_socio(base) == Decimal("20.00")
    corre(caso())


def test_un_usuario_que_no_existe_no_genera_bono(base):
    async def caso():
        await _mundo(base)
        await referrals.process_referral_bonus("usr_fantasma", 1000.0)
        assert await _saldo_socio(base) == Decimal("0.00")
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La línea del libro, y que el bono nunca tumbe la recarga
# ══════════════════════════════════════════════════════════════════════════

def test_el_bono_deja_su_linea_con_el_contexto(base):
    async def caso():
        await _mundo(base, recargas_completadas=1)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        linea, = await _lineas(base)
        assert linea["movement_type"] == "bono_referido"
        assert linea["direction"] == "credit"
        assert linea["amount"] == 25.0
        assert linea["reference"] == {"kind": "referral", "id": "usr_ana"}
        assert linea["actor"]["type"] == "system"
        assert linea["metadata"]["referred_user_id"] == "usr_ana"
        assert linea["metadata"]["first_recharge"] is True
        assert linea["metadata"]["recharge_amount"] == 1000.0
    corre(caso())


def test_si_el_socio_desaparece_a_mitad_de_camino_el_bono_no_revienta(base, monkeypatch):
    """El bono no puede tumbar la recarga del usuario referido: él no tiene nada
    que ver con que su socio siga existiendo.

    Para que el manejador se ejecute, `saldos.mover` tiene que LLEGAR a llamarse
    y fallar — es la carrera en que el socio se borra entre que se lo busca por
    su código y que se le acredita. Con el socio simplemente borrado de entrada,
    la búsqueda no lo encuentra y la función sale mucho antes: la mutación que
    cambiaba el `except` pasaba en verde porque ese camino nunca se ejecutaba.
    """
    async def caso():
        await _mundo(base, recargas_completadas=1)

        import services.saldos as saldos_mod
        llamadas = []

        async def _desaparecio(db, user_id, monto, **k):
            llamadas.append(user_id)
            raise saldos_mod.UsuarioInexistente(user_id)

        monkeypatch.setattr(saldos_mod, "mover", _desaparecio)

        # No tiene que levantar excepción: la recarga del usuario sigue su curso.
        await referrals.process_referral_bonus("usr_ana", 1000.0)

        assert llamadas == ["usr_socio"], "el bono ni siquiera se intentó"
        assert await base.ledger.count_documents({}) == 0
    corre(caso())


def test_el_saldo_del_socio_y_su_libro_cuadran(base):
    from services import contabilidad

    async def caso():
        await _mundo(base, saldo_socio=0, recargas_completadas=1)
        await referrals.process_referral_bonus("usr_ana", 1000.0)
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())


def test_dos_recargas_pagan_dos_bonos_distintos_y_el_libro_sigue_cuadrado(base):
    from services import contabilidad

    async def caso():
        await _mundo(base, recargas_completadas=1)
        await referrals.process_referral_bonus("usr_ana", 1000.0)   # hito + 2%
        await base.transactions.insert_one({
            "transaction_id": "tx_9", "user_id": "usr_ana",
            "type": "recharge_ves", "status": "completed"})
        await referrals.process_referral_bonus("usr_ana", 500.0)    # sólo 2%
        assert await _saldo_socio(base) == Decimal("35.00")         # 25 + 10
        assert len(await _lineas(base)) == 2
        r = await contabilidad.reconciliacion(db=base)
        assert r["cuadra"] is True, r["descuadres"]
    corre(caso())
