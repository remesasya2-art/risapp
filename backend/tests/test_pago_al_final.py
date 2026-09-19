"""
tests/test_pago_al_final.py — Cotizar el envío y pagarlo al final, sin saldo.

QUE SE ESTA PROBANDO

    El flujo nuevo: el cliente cotiza, elige beneficiario y paga con PIX ese
    envío. No hay saldo en el medio. El por qué está en
    `services/pago_al_final.py`.

LAS CINCO COSAS QUE ESTE ARCHIVO NO DEJA QUE SE ROMPAN

    1. QUE LA CONFIRMACION SEA UN SOLO CAMBIO DE ESTADO.

       Es la razón de ser del flujo. Si alguien la parte en dos escrituras
       vuelve la ventana del flujo viejo: el pago cobrado y la orden sin
       avanzar. Hay un test que confirma DOS VECES el mismo pago y exige que
       la orden avance UNA.

    2. QUE LA ORDEN SE RECLAME ANTES QUE EL PAGO.

       Si se marcara el pago primero y el proceso muriera ahí, el pago
       figuraría cobrado y el envío no existiría. El orden importa y está
       probado mirando qué queda cuando la segunda escritura falla.

    3. QUE LA TASA SEA LA DE LA COTIZACION.

       Decisión del dueño: se congela al cotizar. Si alguien la releyera al
       confirmar, el cliente recibiría menos bolívares de los que le mostró la
       pantalla. La tasa se mueve SOLA al cruzar el horario laboral, así que
       esto no es hipotético.

    4. QUE EL BONO DESCUENTE DEL COBRO Y NO DEL ENVIO.

       Con bono, lo que baja es el real que se cobra; los bolívares que recibe
       el beneficiario no cambian. Y el tope de PIX se mide sobre lo que se
       cobra, no sobre el envío: con bono son dos números distintos.

    5. QUE APAGADO NO CAMBIE NADA.

       De fábrica el flujo está apagado y el cliente recarga y gasta como
       siempre. Un camino nuevo para el dinero no se estrena solo.
"""
import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import HTTPException                             # noqa: E402

from conftest import ensenarle_decimal128_a_mongomock, usar_base   # noqa: E402
from services import configuracion as cfg                     # noqa: E402
from services import pago_al_final as paf                     # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    ensenarle_decimal128_a_mongomock()
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def prender(base, valor=1):
    normalizado, error = cfg.normalizar(paf.CLAVE, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, paf.CLAVE, normalizado))


def una_orden(base, referencia="venv_abc", estado=None, **extra):
    """Deja una orden esperando el pago, como la dejaría la ruta."""
    doc = {
        "transaction_id": "tx_1",
        "display_id": 1001,
        "user_id": "u_1",
        "type": "withdrawal",
        "amount_input": 100.0,
        "amount_output": 5500.0,
        "currency_input": "RIS",
        "currency_output": "VES",
        "rate": 55.0,
        "status": estado or paf.ESPERANDO_PAGO,
        "funded_from": "payment",
        "payment_order_id": referencia,
        "payment_expires_at": paf.vence_en(),
        "payment_amount_brl": 100.0,
        "created_at": datetime.now(timezone.utc),
    }
    doc.update(extra)
    corre(base.transactions.insert_one(dict(doc)))
    return doc


def un_cobro(base, referencia="venv_abc", proposito=None):
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": referencia,
        "gestor_id": "u_1",
        "proposito": proposito if proposito is not None else paf.PROPOSITO,
        "amount_brl": 100.0,
        "status": "pending",
    }))
    return {"payment_id": referencia, "gestor_id": "u_1"}


# ══════════════════════════════════════════════════════════════════════════
# 1. El interruptor: apagado de fábrica
# ══════════════════════════════════════════════════════════════════════════

def test_DE_FABRICA_EL_FLUJO_NUEVO_ESTA_APAGADO(base):
    """Un camino nuevo para el dinero no se estrena solo el día que alguien
    fusiona. Al revés que el apagado de la cripto, que tenía que actuar en el
    despliegue."""
    assert corre(paf.esta_activo(base)) is False


def test_prendido_se_activa(base):
    prender(base)
    assert corre(paf.esta_activo(base)) is True


def test_apagado_la_ruta_contesta_503_y_no_404(base):
    """503 y no 404: la ruta existe, lo que no está es el servicio. Un 404 le
    haría pensar a un integrador que se equivocó de dirección."""
    with pytest.raises(HTTPException) as e:
        paf.exigir_activo(False)
    assert e.value.status_code == 503


def test_apagado_le_dice_por_donde_si(base):
    with pytest.raises(HTTPException) as e:
        paf.exigir_activo(False)
    assert "saldo" in e.value.detail.lower(), (
        "el mensaje no le dice que puede seguir usando el flujo viejo")


# ══════════════════════════════════════════════════════════════════════════
# 2. La confirmación: UN documento, UNA vez
# ══════════════════════════════════════════════════════════════════════════

def test_el_pago_hace_avanzar_la_orden(base):
    una_orden(base)
    pago = un_cobro(base)
    assert corre(paf.confirmar(base, pago)) is True
    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["status"] == paf.PENDIENTE
    assert doc.get("paid_at") is not None


def test_EL_MISMO_PAGO_DOS_VECES_AVANZA_UNA_SOLA(base):
    """El test más importante del archivo.

    Mercado Pago reenvía. Si la segunda vuelta también avanzara, un envío
    podría despacharse dos veces por un solo pago.

    La idempotencia no es una marca aparte: es el propio `status` de la orden
    dentro del filtro del `find_one_and_update`. Por eso alcanza con UN
    documento y no hacen falta transacciones de varios.
    """
    una_orden(base)
    pago = un_cobro(base)
    assert corre(paf.confirmar(base, pago)) is True
    assert corre(paf.confirmar(base, pago)) is False


def test_una_orden_que_no_existe_no_rompe_el_webhook(base):
    """Un webhook no puede explotar: Mercado Pago reintenta y llena el
    registro. Devuelve False y sigue."""
    pago = un_cobro(base, referencia="venv_fantasma")
    assert corre(paf.confirmar(base, pago)) is False


def test_un_cobro_vencido_que_se_paga_NO_avanza_solo(base):
    """Si la orden ya venció y alguien pagó igual, esto no puede resolverse
    solo: hay que devolverle la plata o despacharlo a mano. Lo que no puede
    pasar es que avance en silencio con una tasa de hace horas."""
    una_orden(base, estado=paf.PAGO_VENCIDO)
    pago = un_cobro(base)
    assert corre(paf.confirmar(base, pago)) is False
    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["status"] == paf.PAGO_VENCIDO


def test_LA_ORDEN_SE_RECLAMA_ANTES_QUE_EL_PAGO(base):
    """El orden es al revés que en la recarga, y está probado por lo que queda
    cuando la segunda escritura falla.

    Se rompe a propósito la colección de cobros. Si la orden se reclamara
    DESPUES, no habría avanzado y el cliente habría pagado sin envío. Con este
    orden, la orden avanza igual y lo que queda sin marcar es contabilidad.
    """
    una_orden(base)
    pago = un_cobro(base)

    class _CobrosRotos:
        async def update_one(self, *a, **k):
            raise RuntimeError("la base se cayó justo acá")

    original = base.gestor_pix_payments
    try:
        base.gestor_pix_payments = _CobrosRotos()
        assert corre(paf.confirmar(base, pago)) is True
    finally:
        base.gestor_pix_payments = original

    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["status"] == paf.PENDIENTE, (
        "la orden no avanzó: con este orden el cliente tiene que cobrar "
        "aunque la anotación del pago falle")


# ══════════════════════════════════════════════════════════════════════════
# 3. La tasa congelada
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TASA_ES_LA_DE_LA_COTIZACION_Y_NO_LA_DEL_PAGO(base):
    """Se congela al cotizar. Se cambia la tasa del sistema entre la
    cotización y el pago, y la orden tiene que salir con la vieja.

    No es hipotético: `rate_engine.apply_rate_adjustment` le resta un delta al
    cruzar el horario laboral, así que la tasa se mueve sola.
    """
    una_orden(base, rate=55.0, amount_output=5500.0)
    corre(base.rates.insert_one({"ris_to_ves": 40.0,
                                 "updated_at": datetime.now(timezone.utc)}))
    pago = un_cobro(base)
    corre(paf.confirmar(base, pago))

    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["rate"] == 55.0, "la confirmación releyó la tasa"
    assert doc["amount_output"] == 5500.0, (
        "los bolívares cambiaron entre lo que vio el cliente y lo que se "
        "despacha")


def test_confirmar_no_lee_la_tasa_en_ningun_lado():
    """La contracara del anterior, mirando el código.

    El test de arriba pasaría igual si `confirmar` leyera la tasa y guardara
    lo mismo por casualidad. Esto exige que ni la toque.
    """
    fuente = (_BACKEND / "services" / "pago_al_final.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def confirmar("):]
    cuerpo = cuerpo[:cuerpo.index("\nasync def ")]
    for prohibido in ("db.rates", "apply_rate_adjustment", "ris_to_ves"):
        assert prohibido not in cuerpo, (
            f"`confirmar` menciona «{prohibido}»: la tasa se congela al "
            f"cotizar, acá no se relee.")


# ══════════════════════════════════════════════════════════════════════════
# 4. El vencimiento
# ══════════════════════════════════════════════════════════════════════════

def test_la_orden_vence_cuando_vence_el_cobro(base):
    una_orden(base, payment_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert corre(paf.vencer_las_viejas(base)) == 1
    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["status"] == paf.PAGO_VENCIDO


def test_una_orden_todavia_viva_NO_se_vence(base):
    una_orden(base)
    assert corre(paf.vencer_las_viejas(base)) == 0


def test_vencer_NO_toca_las_ordenes_del_flujo_viejo(base):
    """Las del flujo viejo ya cobraron: nacen en «pending» y su plata ya se
    debitó. Vencer una sería borrar un envío pagado.

    El filtro pide `payment_order_id` con el prefijo `venv_`, así que una
    orden del flujo viejo —que no tiene ese campo— no coincide nunca.
    """
    corre(base.transactions.insert_one({
        "transaction_id": "tx_viejo", "user_id": "u_1", "status": "pending",
        "amount_input": 50.0, "created_at": datetime.now(timezone.utc)}))
    assert corre(paf.vencer_las_viejas(base)) == 0
    doc = corre(base.transactions.find_one({"transaction_id": "tx_viejo"}))
    assert doc["status"] == "pending"


def test_vencer_NO_TOCA_UNA_ORDEN_CRIPTO_QUE_TENGA_FECHA(base):
    """La guarda del prefijo, ejercida de verdad.

    La primera versión de este archivo probaba esto con una orden del flujo
    viejo en «pending», y no probaba nada: la condición de estado ya la dejaba
    afuera. Se vio rompiendo el prefijo a propósito — ningún test se puso en
    rojo.

    Acá se simula lo que de verdad pasaría: el envío cripto con pago directo
    deja órdenes en «awaiting_payment», y hoy no les pone `payment_expires_at`.
    El día que alguien se lo agregue —es un nombre genérico, puede pasar— esta
    limpieza empezaría a vencerle órdenes vivas. El prefijo lo impide.
    """
    corre(base.transactions.insert_one({
        "transaction_id": "tx_cripto", "user_id": "u_1",
        "status": paf.ESPERANDO_PAGO,
        "currency_input": "USDT", "funded_from": "payment",
        "payment_order_id": "send_usdt_u_1_abc123",
        "payment_expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "created_at": datetime.now(timezone.utc)}))
    assert corre(paf.vencer_las_viejas(base)) == 0, (
        "la limpieza del flujo PIX venció una orden cripto")
    doc = corre(base.transactions.find_one({"transaction_id": "tx_cripto"}))
    assert doc["status"] == paf.ESPERANDO_PAGO


def test_vencer_no_toca_una_orden_del_flujo_nuevo_YA_PAGADA(base):
    """Vencida quiere decir «nadie la pagó». Una que ya avanzó a «pending»
    cobró de verdad, y vencerla sería borrar un envío que hay que despachar."""
    una_orden(base, estado=paf.PENDIENTE,
              payment_expires_at=datetime.now(timezone.utc) - timedelta(hours=2))
    assert corre(paf.vencer_las_viejas(base)) == 0


# ══════════════════════════════════════════════════════════════════════════
# 5. Que el webhook mande cada cobro a donde va
# ══════════════════════════════════════════════════════════════════════════

def test_el_webhook_distingue_los_dos_propositos():
    """La rama vive en el receptor que ya existe, y no en uno nuevo.

    Es lo importante del diseño: firma HMAC, ventana de frescura,
    reverificación contra la API de Mercado Pago y control de monto valen para
    los dos propósitos. Un receptor aparte tendría que repetirlos, y la
    segunda copia de un control de seguridad es la que sale mal.
    """
    fuente = (_BACKEND / "routes" / "gestor_pix.py").read_text(encoding="utf-8")
    assert 'payment.get("proposito") == pago_al_final.PROPOSITO' in fuente, (
        "el webhook dejó de distinguir el pago de un envío de una recarga: "
        "un envío pagado va a acreditar saldo en vez de despacharse.")
    assert "process_pix_confirmation" in fuente, (
        "se perdió la rama de la recarga de siempre")


def test_confirmar_NO_repite_los_controles_del_webhook():
    """`confirmar` corre DESPUES de que el webhook verificó todo. Repetir un
    control acá no lo hace más seguro: lo hace divergir el día que uno de los
    dos cambie."""
    fuente = (_BACKEND / "services" / "pago_al_final.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def confirmar("):]
    cuerpo = cuerpo[:cuerpo.index("\nasync def ")]
    for prohibido in ("hmac", "signature", "get_payment_status", "amount_brl"):
        assert prohibido not in cuerpo, (
            f"`confirmar` repite «{prohibido}», que el webhook ya comprobó.")


# ══════════════════════════════════════════════════════════════════════════
# 6. La ruta: lo que valida antes de crear nada
# ══════════════════════════════════════════════════════════════════════════

RUTA = "routes/transactions.py"


def _cuerpo_de_la_ruta():
    fuente = (_BACKEND / RUTA).read_text(encoding="utf-8")
    i = fuente.index("async def cotizar_envio_ves(")
    return fuente[i:]


def test_la_ruta_valida_TODO_antes_de_pedirle_el_cobro_a_mercado_pago():
    """Mismo criterio que el envío con saldo, donde las validaciones van antes
    del débito. Acá un rechazo tardío dejaría un QR huérfano que alguien puede
    pagar sin que exista el envío detrás."""
    cuerpo = _cuerpo_de_la_ruta()
    pedido = cuerpo.index("mercadopago_service.create_pix_payment")
    for control in ("exigir_activo", "Beneficiario no encontrado",
                    "validate_pix_amount", "kyc_quota.check_amount",
                    "exigir_para_pagar", "comisiones.campos_de"):
        assert control in cuerpo, f"falta el control «{control}»"
        assert cuerpo.index(control) < pedido, (
            f"«{control}» corre DESPUES de pedirle el cobro a Mercado Pago")


def test_sin_codigo_de_cobro_NO_se_guarda_nada():
    """La lección ya está escrita en `routes/gestor_pix.py`: un cobro sin
    código guardado deja al cliente mirando una pantalla que no se puede
    pagar, y una fila muerta en la base."""
    cuerpo = _cuerpo_de_la_ruta()
    sin_qr = cuerpo.index("if not qr:")
    inserta = cuerpo.index("db.transactions.insert_one")
    assert sin_qr < inserta, (
        "la orden se guarda antes de comprobar que hay código de cobro")


def test_EL_TOPE_DE_PIX_SE_MIDE_SOBRE_LO_QUE_SE_COBRA(base):
    """Con bono, el envío y el cobro son números distintos. El que tiene que
    caber en el tope de la pasarela es el que la pasarela va a cobrar."""
    cuerpo = _cuerpo_de_la_ruta()
    i = cuerpo.index("validate_pix_amount")
    linea = cuerpo[i:cuerpo.index("\n", i)]
    assert "_cobro_float" in linea, (
        "el tope de PIX se está midiendo sobre el envío y no sobre el cobro")


def test_el_bono_descuenta_del_cobro_y_no_cambia_los_bolivares():
    """Lo que baja con el bono es el real que se pone, no lo que recibe el
    beneficiario."""
    cuerpo = _cuerpo_de_la_ruta()
    assert "_a_cobrar = _total - _del_bono" in cuerpo, (
        "el bono dejó de descontar del cobro")
    # Los bolívares salen del monto del envío, nunca del monto cobrado.
    assert "amount_ves = round(request.amount * ris_to_ves, 2)" in cuerpo, (
        "los bolívares se están calculando sobre el cobro y no sobre el "
        "envío: con bono, el beneficiario recibiría de menos.")


def test_el_bono_que_cubre_todo_se_rechaza_con_motivo():
    """Un cobro de cero no lo acepta ninguna pasarela. Se explica en vez de
    pedirle a Mercado Pago un QR imposible."""
    cuerpo = _cuerpo_de_la_ruta()
    assert "if _a_cobrar <= 0:" in cuerpo
    i = cuerpo.index("if _a_cobrar <= 0:")
    pedido = cuerpo.index("mercadopago_service.create_pix_payment")
    assert i < pedido


def test_la_orden_se_guarda_antes_que_el_cobro():
    """Si falla el segundo paso, queda una orden muerta y un QR que no cruza
    con nada. Al revés quedaría un cobro pagable sin envío detrás, que es la
    falla cara."""
    cuerpo = _cuerpo_de_la_ruta()
    assert cuerpo.index("db.transactions.insert_one") < \
        cuerpo.index("db.gestor_pix_payments.insert_one")


# ══════════════════════════════════════════════════════════════════════════
# 7. Que la pantalla no ofrezca lo que el servidor rechaza
# ══════════════════════════════════════════════════════════════════════════
#
# Es la misma guarda que se puso para la vía cripto, y por el mismo motivo:
# ahí un error igual se coló entre 25 tests en verde y sólo apareció corriendo
# la app. Dos lados que se tienen que poner de acuerdo necesitan algo que avise
# cuando dejan de estarlo.

_SEND_JSX = _REPO / "frontend" / "src" / "pages" / "Send.jsx"


def test_limits_publica_si_el_flujo_esta_prendido(base):
    from services.limits import limits_payload
    p = corre(limits_payload(base))
    assert p["pago_al_final"] is False, "de fábrica tiene que venir apagado"
    prender(base)
    assert corre(limits_payload(base))["pago_al_final"] is True


def test_la_pantalla_lee_el_estado_ANTES_de_ofrecer_el_boton():
    """Con el flujo apagado, `/withdraw-ves/cotizar` contesta 503. Un botón
    que lo llamara sin mirar el estado sería un botón que lleva a un error."""
    jsx = _SEND_JSX.read_text(encoding="utf-8")
    assert "r.data?.pago_al_final" in jsx, (
        "la pantalla dejó de leer el estado del flujo desde /limits")
    assert "{pagoAlFinal ? (" in jsx, (
        "el botón de pagar con PIX ya no está condicionado al estado")


def test_el_boton_de_pix_llama_a_la_ruta_que_existe():
    jsx = _SEND_JSX.read_text(encoding="utf-8")
    assert "'/withdraw-ves/cotizar'" in jsx
    # Y la de siempre sigue estando: los dos flujos conviven.
    assert "'/withdraw'" in jsx, (
        "se perdió el envío con saldo: los dos flujos tienen que convivir")


def test_LA_PANTALLA_DEL_COBRO_NO_TIENE_BOTON_DE_YA_PAGUE():
    """Quien dice que pagó no es quien confirma que se pagó.

    La orden avanza cuando Mercado Pago avisa, con su firma verificada. Un
    botón de «ya pagué» sería una forma de decirle a la aplicación algo que no
    puede comprobar, y el día que alguien lo cablee a la ruta de confirmar,
    despacha envíos que nadie pagó.
    """
    jsx = _SEND_JSX.read_text(encoding="utf-8")
    i = jsx.index('data-testid="cobro-pix"')
    bloque = jsx[i:i + 4000]
    for prohibido in ("ya pagué", "ya pague", "Ya pagué", "confirmar-pago",
                      "marcar-pagado"):
        assert prohibido not in bloque, (
            f"apareció «{prohibido}» en la pantalla del cobro")


# ══════════════════════════════════════════════════════════════════════════
# 8. El bono: se debita al cotizar y vuelve si nadie paga
# ══════════════════════════════════════════════════════════════════════════
#
# ESTE BLOQUE EXISTE POR UN ERROR QUE COMETI.
#
#   La primera versión de la ruta descontaba el bono del cobro y NUNCA lo
#   debitaba: el mismo bono habría servido para envíos infinitos. No lo
#   encontró ninguno de los tests de este archivo — lo encontró
#   `test_solo_el_envio_a_venezuela_sabe_gastar_el_bono`, la guarda de otro
#   archivo que vigila quién puede nombrar la cuenta del bono, y que saltó
#   porque el módulo nuevo la mencionaba.
#
#   Un descuento sin débito es plata regalada. Lo que sigue lo vigila.

from services import bonos                                    # noqa: E402
from services.money import from_db, to_decimal128             # noqa: E402


def _con_bono(base, cuanto="15.00"):
    corre(base.users.insert_one({
        "user_id": "u_1", "name": "Ana", "email": "ana@ejemplo.test",
        "role": "user",
        bonos.CUENTA_DEL_BONO: to_decimal128(__import__("decimal").Decimal(cuanto)),
    }))


def _bono_de(base):
    doc = corre(base.users.find_one({"user_id": "u_1"}))
    return from_db(doc.get(bonos.CUENTA_DEL_BONO))


def test_EL_BONO_SE_DEBITA_AL_COTIZAR_Y_NO_AL_CONFIRMAR():
    """Va al cotizar por dos motivos, y los dos están escritos en la ruta.

    Uno: acá todavía se puede fallar sin haberle generado un QR a nadie. Dos:
    la confirmación tiene que seguir siendo UN cambio de estado sobre UN
    documento, y meterle el débito la partiría en dos escrituras — que es la
    ventana que este flujo existe para eliminar.
    """
    ruta = _cuerpo_de_la_ruta()
    assert "bonos.CUENTA_DEL_BONO: {\"$gte\"" in ruta, (
        "el bono se descuenta del cobro pero no se debita con guarda: el "
        "mismo bono sirve para envíos infinitos")
    i = ruta.index("bonos.CUENTA_DEL_BONO")
    pedido = ruta.index("mercadopago_service.create_pix_payment")
    assert i < pedido, "el bono se debita después de generar el cobro"

    confirmar = (_BACKEND / "services" / "pago_al_final.py").read_text(encoding="utf-8")
    cuerpo = confirmar[confirmar.index("async def confirmar("):]
    cuerpo = cuerpo[:cuerpo.index("\nasync def ")]
    assert "CUENTA_DEL_BONO" not in cuerpo, (
        "la confirmación toca el bono: vuelve a ser dos escrituras")


def test_el_debito_del_bono_lleva_guarda_contra_el_doble_gasto():
    """El `$gte` dentro del filtro es lo que impide que dos pedidos
    simultáneos gasten el mismo bono. Es el mismo patrón que el envío con
    saldo, y por el mismo motivo."""
    ruta = _cuerpo_de_la_ruta()
    i = ruta.index("bonos.CUENTA_DEL_BONO: {\"$gte\"")
    bloque = ruta[i:i + 400]
    assert "$inc" in bloque, "no debita"
    assert "find_one_and_update" in ruta[max(0, i - 300):i], (
        "el débito no es una sola escritura atómica")


def test_cada_salida_por_error_DEVUELVE_el_bono():
    """El bono ya salió de su cuenta. Si la ruta se va por un error después de
    eso, sin devolverlo quedaría gastado en un envío que no existe."""
    ruta = _cuerpo_de_la_ruta()
    debito = ruta.index("bonos.CUENTA_DEL_BONO: {\"$gte\"")
    despues = ruta[debito:]
    # Cada `raise HTTPException` posterior al débito tiene que venir precedido
    # por la devolución.
    for trozo in despues.split("raise HTTPException")[1:-1]:
        pass
    assert despues.count("_devolver_el_bono()") >= 3, (
        "hay salidas por error después del débito que no devuelven el bono")


def test_EL_BONO_VUELVE_SI_NADIE_PAGA(base):
    """Comportamiento, no forma. Una orden que vence tiene que devolver lo que
    se llevó."""
    _con_bono(base, "15.00")
    una_orden(base, bono_aplicado=15.0,
              payment_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert _bono_de(base) == __import__("decimal").Decimal("15.00")
    assert corre(paf.vencer_las_viejas(base)) == 1
    assert _bono_de(base) == __import__("decimal").Decimal("30.00"), (
        "el bono de la orden vencida no volvió")


def test_el_bono_NO_vuelve_dos_veces(base):
    """Dos limpiezas simultáneas no pueden devolverlo dos veces. El
    vencimiento se reclama con el estado dentro del filtro, igual que la
    confirmación."""
    _con_bono(base, "0")
    una_orden(base, bono_aplicado=15.0,
              payment_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    corre(paf.vencer_las_viejas(base))
    corre(paf.vencer_las_viejas(base))
    assert _bono_de(base) == __import__("decimal").Decimal("15.00"), (
        "el bono volvió más de una vez")


def test_una_orden_PAGADA_no_devuelve_el_bono(base):
    """Se gastó de verdad: el envío existe y se va a despachar."""
    _con_bono(base, "0")
    una_orden(base, estado=paf.PENDIENTE, bono_aplicado=15.0,
              payment_expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    corre(paf.vencer_las_viejas(base))
    assert _bono_de(base) == __import__("decimal").Decimal("0")
