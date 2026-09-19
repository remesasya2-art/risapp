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
        corre(paf.exigir_activo(base))
    assert e.value.status_code == 503


def test_apagado_le_dice_por_donde_si(base):
    """Un rechazo que no dice qué hacer manda a soporte a preguntar lo que la
    pantalla podía haber contestado sola.

    Con la carga de saldo abierta —que es lo de fábrica— la salida es cargar
    saldo, igual que antes.
    """
    with pytest.raises(HTTPException) as e:
        corre(paf.exigir_activo(base))
    assert "saldo" in e.value.detail.lower(), (
        "el mensaje no le dice que puede seguir usando el flujo viejo")


def test_APAGADO_Y_CON_LA_CARGA_CERRADA_NO_LO_MANDA_A_RECARGAR(base):
    """El texto que quedó mintiendo, y por lo que existe este bloque.

    El mensaje terminaba en «podés recargar tu saldo y enviar desde ahí»,
    escrito fijo. El día que la carga de saldo se pudo cerrar
    (`services/recarga_abierta.py`), esa frase quedó mandando a recargar a
    alguien que no puede recargar — y la pantalla de recarga, además, lo
    rebota al panel.

    Este caso no se puede llegar por el panel: el seguro de
    `revisar_las_parejas` no deja apagar las dos cosas. Se llega escribiendo
    en la base, que es justo cuando un mensaje honesto más importa.
    """
    from services import recarga_abierta
    corre(cfg_escribir(base, recarga_abierta.CLAVE, recarga_abierta.CERRADA))
    corre(cfg_escribir(base, paf.CLAVE, 0))

    with pytest.raises(HTTPException) as e:
        corre(paf.exigir_activo(base))
    assert "recarg" not in e.value.detail.lower(), (
        f"con la carga de saldo cerrada, el mensaje sigue mandando a "
        f"recargar: «{e.value.detail}»")
    assert "soporte" in e.value.detail.lower(), (
        "sin ninguna vía abierta, el mensaje tiene que mandar a soporte en "
        "vez de inventar una salida")


def cfg_escribir(base, clave, valor):
    """Escribe un ajuste como lo escribe el panel, validación incluida."""
    from services import configuracion
    normalizado, error = configuracion.normalizar(clave, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    return configuracion.escribir(base, clave, normalizado)


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
    pagar, y una fila muerta en la base.

    LA GUARDA AHORA PREGUNTA SI SE PIDIO UN CODIGO, y no si lo hay.

        Desde que el envío se puede pagar con tarjeta, hay un caso en que NO
        tener código es lo correcto: con tarjeta no se le pide ninguno a
        Mercado Pago, a propósito, porque un código vivo al lado de una
        tarjeta es el cliente pagando dos veces
        (`services/tarjeta_del_envio.py`).

        Lo que este test protege no cambió: cuando SI se pidió uno y no vino,
        no se guarda nada.
    """
    cuerpo = _cuerpo_de_la_ruta()
    sin_qr = cuerpo.index("and not qr:")
    inserta = cuerpo.index("db.transactions.insert_one")
    assert sin_qr < inserta, (
        "la orden se guarda antes de comprobar que hay código de cobro")

    # Y la guarda sigue midiendo lo que tiene que medir: que falte el código
    # cuando se pidió uno. Sin la condición del método, la cotización con
    # tarjeta —que nunca tiene código— fallaría siempre.
    linea = cuerpo[cuerpo.rindex("\n", 0, sin_qr) + 1:
                   cuerpo.index(":", sin_qr) + 1]
    assert "POR_PIX" in linea, (
        "la guarda del código dejó de mirar el método: con tarjeta no se pide "
        "ninguno, así que cotizar con tarjeta va a fallar siempre.")


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


# ══════════════════════════════════════════════════════════════════════════
# 9. El corredor inverso: se paga en bolívares y se liquida en reais
# ══════════════════════════════════════════════════════════════════════════
#
# LAS TRES COSAS QUE ESTE BLOQUE NO DEJA QUE SE ROMPAN
#
#   1. QUE SUBIR EL COMPROBANTE NO ACREDITE NADA.
#
#      Decir «pagué» no es haber pagado. Entre el comprobante y la cola de
#      despacho tiene que estar la persona que lo abre. Si alguien conecta el
#      comprobante directo a «pendiente», la aplicación despacha reales contra
#      la palabra del que los pide.
#
#   2. QUE EL ESTADO DEL MEDIO EXISTA.
#
#      Sin él, la orden queda en «esperando pago» —y el cliente ve «pagá»
#      después de haber pagado, y paga dos veces— o en «pendiente», que acá
#      significa «cobrada», sin que nadie haya comprobado nada.
#
#   3. QUE RECHAZAR DEVUELVA A «ESPERANDO PAGO» Y NO A UN ESTADO TERMINAL.
#
#      El cliente no tiene saldo comprometido: si la foto salió mal, lo que
#      necesita es poder mandar la buena, no cotizar de nuevo.

def una_orden_reais(base, estado=None, **extra):
    doc = {
        "transaction_id": "tx_br",
        "display_id": 2001,
        "user_id": "u_1",
        "type": "withdrawal",
        "amount_input": 5500.0,            # bolívares que pone
        "amount_output": 100.0,            # reales que recibe
        "currency_input": "VES",
        "currency_output": "BRL",
        "rate": 55.0,
        "status": estado or paf.ESPERANDO_PAGO,
        "funded_from": "payment",
        "payment_order_id": paf.nuevo_id_de_cobro_reais(),
        "payment_expires_at": paf.vence_en(),
        "created_at": datetime.now(timezone.utc),
    }
    doc.update(extra)
    corre(base.transactions.insert_one(dict(doc)))
    return doc


def _subir(base, **k):
    return corre(paf.recibir_comprobante(
        base, k.pop("tx", "tx_br"), k.pop("uid", "u_1"),
        comprobante=k.pop("comprobante", "data:image/png;base64,AAAA"),
        banco_id=k.pop("banco_id", "bk_1"),
        banco_nombre=k.pop("banco_nombre", "Banesco")))


def test_EL_COMPROBANTE_NO_MANDA_LA_ORDEN_A_LA_COLA(base):
    """El test más importante de este bloque.

    Subir el comprobante deja la orden EN REVISION, no en «pendiente». Decir
    «pagué» no es haber pagado: entre las dos cosas va la persona que abre el
    comprobante. Si esto se pone en verde con «pending», la aplicación
    despacha reales contra la palabra de quien los pide.
    """
    una_orden_reais(base)
    orden = _subir(base)
    assert orden["status"] == paf.REVISANDO
    assert orden["status"] != paf.PENDIENTE
    assert orden.get("proof_image")


def test_el_mismo_comprobante_dos_veces_da_409(base):
    """Doble clic. El reclamo lleva el estado dentro del filtro, así que el
    segundo no encuentra la orden esperando el pago."""
    una_orden_reais(base)
    _subir(base)
    with pytest.raises(HTTPException) as e:
        _subir(base)
    assert e.value.status_code == 409
    assert "revisando" in e.value.detail.lower()


def test_una_cotizacion_vencida_NO_acepta_comprobante(base):
    """Los siete minutos son para pagar. Pasado ese rato la tasa ya no se
    respeta, y aceptar el comprobante en silencio sería despachar con una tasa
    que nadie decidió."""
    una_orden_reais(base,
                    payment_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(HTTPException) as e:
        _subir(base)
    assert e.value.status_code == 409
    assert "venció" in e.value.detail or "vencio" in e.value.detail


def test_la_cotizacion_vencida_le_dice_que_hacer_si_ya_transfirio(base):
    """El caso caro: transfirió y llegó tarde. Si el mensaje sólo dice
    «venció», esa persona pierde la plata sin saber a quién escribirle."""
    una_orden_reais(base,
                    payment_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(HTTPException) as e:
        _subir(base)
    assert "escribinos" in e.value.detail.lower()


def test_no_se_puede_subir_el_comprobante_de_otro(base):
    """El `user_id` va dentro del filtro del reclamo, no comprobado aparte."""
    una_orden_reais(base)
    with pytest.raises(HTTPException) as e:
        _subir(base, uid="otro")
    assert e.value.status_code == 404


# ── La verificación del administrador ────────────────────────────────────

def test_verificar_manda_la_orden_a_la_cola(base):
    una_orden_reais(base, estado=paf.REVISANDO)
    orden = corre(paf.verificar_el_pago(base, "tx_br", "admin_1"))
    assert orden["status"] == paf.PENDIENTE
    assert orden.get("verificado_por") == "admin_1"


def test_DOS_OPERADORES_NO_VERIFICAN_LA_MISMA_ORDEN(base):
    """Dos personas con la misma pantalla abierta. El reclamo lleva
    `REVISANDO` en el filtro, así que el segundo se va con un 409 en vez de
    despachar dos veces."""
    una_orden_reais(base, estado=paf.REVISANDO)
    corre(paf.verificar_el_pago(base, "tx_br", "admin_1"))
    with pytest.raises(HTTPException) as e:
        corre(paf.verificar_el_pago(base, "tx_br", "admin_2"))
    assert e.value.status_code == 409


def test_no_se_puede_verificar_una_orden_que_nadie_pago(base):
    """Una orden en «esperando pago» no tiene comprobante. Verificarla sería
    mandar a despachar algo que nadie dijo siquiera haber pagado."""
    una_orden_reais(base)
    with pytest.raises(HTTPException) as e:
        corre(paf.verificar_el_pago(base, "tx_br", "admin_1"))
    assert e.value.status_code == 409


def test_RECHAZAR_DEVUELVE_A_ESPERANDO_PAGO(base):
    """Y no a un estado terminal: el cliente no tiene saldo comprometido, y si
    la foto salió mal lo que necesita es mandar la buena."""
    una_orden_reais(base, estado=paf.REVISANDO)
    orden = corre(paf.rechazar_el_comprobante(
        base, "tx_br", "admin_1", "La foto está cortada"))
    assert orden["status"] == paf.ESPERANDO_PAGO
    assert orden.get("motivo_del_rechazo") == "La foto está cortada"


def test_al_rechazar_se_borra_el_comprobante_viejo(base):
    """Si quedara, el próximo que abra la orden vería la foto mala y el
    comprobante nuevo al lado, sin saber cuál es cuál."""
    una_orden_reais(base, estado=paf.REVISANDO,
                    proof_image="data:image/png;base64,VIEJA")
    orden = corre(paf.rechazar_el_comprobante(base, "tx_br", "a", "no se lee"))
    assert not orden.get("proof_image")


def test_despues_de_un_rechazo_se_puede_volver_a_subir(base):
    """La vuelta completa: rechazado, corrige la foto, la manda de nuevo."""
    una_orden_reais(base, estado=paf.REVISANDO)
    corre(paf.rechazar_el_comprobante(base, "tx_br", "a", "no se lee"))
    orden = _subir(base, comprobante="data:image/png;base64,BUENA")
    assert orden["status"] == paf.REVISANDO


# ── La forma de las rutas ────────────────────────────────────────────────

def _cuerpo(nombre, archivo="routes/transactions.py"):
    fuente = (_BACKEND / archivo).read_text(encoding="utf-8")
    i = fuente.index(f"async def {nombre}(")
    resto = fuente[i:]
    fin = resto.find("\n@router")
    return resto if fin < 0 else resto[:fin]


def test_el_beneficiario_TIENE_que_ser_de_brasil():
    """Sin esto, un `beneficiary_id` de Venezuela crea una orden que promete
    reales a una cuenta en bolívares, y el operador lo descubre al ir a
    pagarla."""
    cuerpo = _cuerpo("cotizar_envio_reais")
    assert 'beneficiary.get("pais") != "BR"' in cuerpo, (
        "la cotización no comprueba que el beneficiario sea de Brasil")


def test_el_banco_se_resuelve_ANTES_de_aceptar_el_comprobante():
    """Aceptar un banco que no resuelve contra contabilidad deja una orden que
    nadie va a poder procesar, y el cliente se entera días después."""
    cuerpo = _cuerpo("comprobante_del_envio_reais")
    assert "resolve_ves_bank" in cuerpo
    assert cuerpo.index("resolve_ves_bank") < cuerpo.index("recibir_comprobante")


def test_la_cotizacion_inversa_no_toca_ningun_saldo():
    """La propiedad que hace seguro a todo este flujo. Si aparece un débito,
    volvieron las dos escrituras."""
    cuerpo = _cuerpo("cotizar_envio_reais")
    for prohibido in ("balance_ris", "saldos.mover", "$inc"):
        assert prohibido not in cuerpo, (
            f"la cotización inversa toca «{prohibido}»: tiene que ser sin saldo")


def test_rechazar_un_comprobante_EXIGE_un_motivo_escrito():
    """Sin motivo, el cliente recibe un «no» sin saber qué corregir y termina
    en soporte."""
    cuerpo = _cuerpo("verificar_pago_en_bolivares", "routes/admin.py")
    assert "if not motivo:" in cuerpo


def test_las_dos_acciones_estan_declaradas_en_el_libro():
    """`auditoria.registrar` revienta con una acción no declarada, y lo hace a
    propósito: una acción mal escrita es una línea que después nadie encuentra
    al filtrar."""
    from services import auditoria
    assert "envio_brl.verificado" in auditoria.ACCIONES
    assert "envio_brl.rechazado" in auditoria.ACCIONES


# ══════════════════════════════════════════════════════════════════════════
# 10. La pantalla del corredor inverso no promete lo que nadie comprobó
# ══════════════════════════════════════════════════════════════════════════

_SENDREAIS = _REPO / "frontend" / "src" / "pages" / "SendReais.jsx"


def test_la_pantalla_de_brasil_lee_el_estado_del_flujo():
    jsx = _SENDREAIS.read_text(encoding="utf-8")
    assert "r.data?.pago_al_final" in jsx
    assert "{pagoAlFinal ? (" in jsx, (
        "el botón de pagar en bolívares no está condicionado al estado")


def test_los_dos_flujos_conviven_en_la_pantalla_de_brasil():
    jsx = _SENDREAIS.read_text(encoding="utf-8")
    assert "'/enviar-reais/cotizar'" in jsx
    assert "'/reais/send'" in jsx, (
        "se perdió el envío con saldo: los dos flujos tienen que convivir")


def test_LA_PANTALLA_NO_DICE_LISTO_CUANDO_FALTA_VERIFICAR():
    """El error caro de esta pantalla.

    Pagando con saldo, el envío está cobrado y sólo falta despacharlo.
    Pagando en bolívares, NADIE sabe todavía si la plata entró: alguien tiene
    que abrir el comprobante. Decirle «envío registrado» a quien está en el
    segundo caso es prometerle algo que no comprobó nadie, y el día que el
    comprobante se rechace va a decir —con razón— que la aplicación le dijo
    que estaba hecho.
    """
    jsx = _SENDREAIS.read_text(encoding="utf-8")
    assert "hecho.revisando ? 'Recibimos tu comprobante' : 'Envío registrado'" in jsx, (
        "la pantalla de cerrado dejó de distinguir entre «cobrado» y "
        "«esperando que lo verifiquemos»")


def test_la_pantalla_del_comprobante_no_tiene_boton_de_ya_pague():
    """Subir el comprobante ES decir que pagó. Un botón aparte de «ya pagué»
    sería una forma de avanzar la orden sin adjuntar nada que mirar."""
    jsx = _SENDREAIS.read_text(encoding="utf-8")
    i = jsx.index('data-testid="br-comprobante"')
    bloque = jsx[i:i + 4000]
    for prohibido in ("ya pagué", "ya pague", "Ya pagué", "marcar-pagado"):
        assert prohibido not in bloque


def test_la_pantalla_muestra_los_montos_DEL_SERVIDOR():
    """La pantalla convierte a bolívares con la tasa que tiene a mano sólo
    para pedir la cotización. Lo que muestra después son los montos que
    devolvió el servidor: si difieren, gana el servidor."""
    jsx = _SENDREAIS.read_text(encoding="utf-8")
    i = jsx.index('data-testid="br-comprobante"')
    bloque = jsx[i:i + 4000]
    assert "cotizacion.amount_ves" in bloque
    assert "cotizacion.amount_brl" in bloque
    assert "montoNum" not in bloque, (
        "la pantalla del comprobante muestra su propio cálculo en vez del "
        "que devolvió el servidor")
