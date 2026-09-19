"""
tests/test_tarjeta_paga_el_envio.py — La tarjeta paga un envío, no carga saldo.

POR QUE ESTA VIA NO ES UNA RECARGA

    Cargar saldo se cerró: la empresa no custodia dinero de terceros. La
    tarjeta pagando UN ENVIO no es custodia —la plata entra y sale en la misma
    operación, igual que el PIX que cobra al final—, así que esta ruta NO lleva
    la guarda de `recarga_abierta` y las de arriba sí.

LO MAS IMPORTANTE QUE VIGILA ESTE ARCHIVO: EL DOBLE COBRO

    Cotizar un envío deja una orden esperando el pago. Si además de su código
    de PIX se pudiera cobrar con tarjeta, el cliente podría pagar las dos veces
    y sólo una contaría: `pago_al_final.confirmar` es atómico sobre la orden,
    pero eso protege la ORDEN, no la BILLETERA de quien paga.

    Por eso el método se elige ANTES de cotizar, y con tarjeta no se genera
    ningún código. Los tests de la sección 2 son los que no dejan que eso se
    desarme.

LAS OTRAS TRES

    · La comisión la paga el cliente, arriba del envío, y el desglose sale del
      servidor y de un solo lugar.
    · Sólo verificados, por el contracargo a ciento veinte días.
    · Aprobar la tarjeta hace avanzar el envío por el MISMO camino que el PIX,
      y no acredita saldo.
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

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from services import pago_al_final as paf                          # noqa: E402
from services import tarjeta_del_envio as tarjeta                      # noqa: E402
from services.money import to_decimal                              # noqa: E402

ensenarle_decimal128_a_mongomock()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


TARIFAS = {"credit_pct": 4.49, "debit_pct": 1.99, "flat_brl": 0.40}


# ══════════════════════════════════════════════════════════════════════════
# 1. La comisión: la paga el cliente, arriba del envío
# ══════════════════════════════════════════════════════════════════════════

def test_el_envio_no_cambia_y_lo_que_sube_es_lo_que_se_cobra():
    """El beneficiario recibe lo mismo con tarjeta que con PIX. Si la comisión
    se descontara del envío, la familia del otro lado cobraría menos y nadie se
    lo habría avisado."""
    d = tarjeta.cuanto_se_le_cobra(to_decimal("100"), "credit_card", TARIFAS)
    assert d["envio_brl"] == to_decimal("100")
    assert d["total_brl"] == d["envio_brl"] + d["comision_brl"]


@pytest.mark.parametrize("tipo, esperado", [
    ("credit_card", "104.89"),     # 4,49 % + R$ 0,40
    ("debit_card", "102.39"),      # 1,99 % + R$ 0,40
])
def test_la_cuenta_da_lo_que_se_le_dijo_al_dueno(tipo, esperado):
    d = tarjeta.cuanto_se_le_cobra(to_decimal("100"), tipo, TARIFAS)
    assert str(d["total_brl"]) == esperado


def test_el_debito_sale_mas_barato_que_el_credito():
    """Si se invirtieran los porcentajes nadie lo notaría hasta ver la
    liquidación del mes."""
    c = tarjeta.cuanto_se_le_cobra(to_decimal("100"), "credit_card", TARIFAS)
    deb = tarjeta.cuanto_se_le_cobra(to_decimal("100"), "debit_card", TARIFAS)
    assert deb["total_brl"] < c["total_brl"]


def test_la_comision_se_calcula_en_DECIMAL_y_no_en_float():
    """Es plata que se le suma a lo que paga una persona. En float, montos con
    muchos decimales arrastran el error hasta el centavo que se cobra."""
    d = tarjeta.cuanto_se_le_cobra(to_decimal("33.33"), "credit_card", TARIFAS)
    for v in d.values():
        assert not isinstance(v, float), (
            "la cuenta de la tarjeta volvió a float: es dinero")
    # 33,33 · 4,49 % = 1,4965… → 1,50 con el fijo: 1,90
    assert str(d["comision_brl"]) == "1.90"


def test_el_desglose_trae_LAS_TRES_cifras():
    """El total solo no deja comparar con el PIX. Quien ve «R$ 104,89» sin
    saber de dónde salen los 4,89 se cree que le cobran de más."""
    d = tarjeta.cuanto_se_le_cobra(to_decimal("100"), "credit_card", TARIFAS)
    assert set(d) == {"envio_brl", "comision_brl", "total_brl"}


def test_las_tarifas_salen_del_MISMO_lugar_que_las_de_la_recarga():
    """Dos catálogos de tarifas es un cambio que se aplica a una vía y a la
    otra no, y nadie lo ve hasta conciliar."""
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    assert "from routes.payments_card import _get_card_fees" in fuente
    ruta = (_BACKEND / "routes" / "payments_card.py").read_text(encoding="utf-8")
    cuerpo = ruta[ruta.index("async def pagar_envio_con_tarjeta("):]
    assert "await _get_card_fees()" in cuerpo


# ══════════════════════════════════════════════════════════════════════════
# 2. EL DOBLE COBRO. La sección importante.
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_ORDEN_DE_PIX_NO_SE_PUEDE_COBRAR_CON_TARJETA():
    """El test más importante del archivo.

    Una orden cotizada para PIX tiene un código vivo. Cobrarla además con
    tarjeta le saca la plata dos veces al cliente, y sólo una avanza el envío.
    """
    assert tarjeta.es_de_tarjeta({"metodo": "pix", "qr_code": "000201..."}) is False


def test_un_cobro_VIEJO_sin_el_campo_tampoco_pasa():
    """Los cobros de antes de que este campo existiera son todos de PIX, y
    todos tienen código. Fallar abierto acá es el doble cobro."""
    assert tarjeta.es_de_tarjeta({"payment_id": "venv_1", "qr_code": "x"}) is False
    assert tarjeta.es_de_tarjeta({}) is False
    assert tarjeta.es_de_tarjeta(None) is False


def test_solo_lo_que_dice_tarjeta_es_de_tarjeta():
    assert tarjeta.es_de_tarjeta({"metodo": "tarjeta"}) is True
    for otro in ("PIX", "Tarjeta", "credito", "", None):
        assert tarjeta.es_de_tarjeta({"metodo": otro}) is False, otro


def test_LA_SEGUNDA_GUARDA_mira_lo_que_QUEDO_y_no_lo_que_se_pidio():
    """Y por eso no es redundante con la primera.

    Este caso es el que la justifica: una orden que DICE ser de tarjeta y que
    sin embargo tiene un código de PIX guardado. Puede pasar si la cotización
    cambia, o si una migración deja el campo puesto sobre cobros viejos.
    `es_de_tarjeta` la deja pasar —el campo dice tarjeta— y sin la segunda se
    cobraría sobre una orden con un PIX vivo.

    CLAUDE.md prohíbe las guardas redundantes que se tapan entre sí. Ésta no
    se tapa con la otra: cada una ve algo que la otra no.
    """
    mentirosa = {"metodo": "tarjeta", "qr_code": "000201-un-pix-vivo"}
    assert tarjeta.es_de_tarjeta(mentirosa) is True, (
        "cambió la primera guarda: este test ya no prueba lo que dice probar")
    assert tarjeta.tiene_qr(mentirosa) is True, (
        "la segunda guarda dejó de mirar el código: una orden de tarjeta con "
        "un PIX vivo se puede cobrar dos veces")


def test_una_orden_de_tarjeta_limpia_no_tiene_codigo():
    assert tarjeta.tiene_qr({"metodo": "tarjeta", "qr_code": ""}) is False
    assert tarjeta.tiene_qr({"metodo": "tarjeta"}) is False


def test_LA_COTIZACION_NO_PIDE_CODIGO_CUANDO_ES_TARJETA():
    """La raíz de todo: si se pidiera igual, la orden nacería pagable por las
    dos vías y las guardas de arriba serían la única defensa."""
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def cotizar_envio_ves("):]
    cuerpo = cuerpo[:cuerpo.index("\n@router")]
    assert "if (metodo == tarjeta_del_envio.POR_PIX\n" in cuerpo, (
        "la cotización volvió a pedirle un código a Mercado Pago sin mirar el "
        "método: una orden de tarjeta va a nacer con un PIX vivo al lado.")


async def _cotizar(base, metodo, verificado=True):
    """Corre la cotización de verdad contra mongomock y devuelve lo guardado.

    POR QUE SE EJECUTA Y NO SE LEE

        La primera versión de este test buscaba `"metodo": metodo,` en el
        archivo. Borrando esa línea del documento del cobro, los 28 tests
        siguieron en verde: el mismo texto aparece más abajo, en la respuesta
        que se le devuelve a la pantalla, y el test se conformaba con ése.

        O sea que comprobaba que algo estuviera ESCRITO, no que funcionara —
        que es justo lo que este repositorio no acepta.
    """
    from routes import transactions
    from routes.transactions import CotizarEnvioVesRequest, cotizar_envio_ves
    from models.user import User
    from services import configuracion

    # El flujo que cobra al final viene apagado de fábrica: sin esto, la ruta
    # frena antes de llegar a nada de lo que este archivo prueba.
    await configuracion.escribir(base, paf.CLAVE, 1)

    await base.rates.insert_one({"ris_to_ves": 110.0,
                                 "updated_at": datetime.now(timezone.utc)})
    await base.beneficiaries.insert_one({
        "beneficiary_id": "ben_1", "user_id": "u1", "full_name": "María Pérez",
        "id_document": "V123", "bank": "Banco", "bank_code": "0102",
        "payment_type": "pago_movil", "phone_number": "0414"})
    await base.users.insert_one({
        "user_id": "u1", "email": "c@ejemplo.com", "name": "Ana",
        "cpf": "12345678909", "verification_status":
            "verified" if verificado else "pending"})

    usuario = User(user_id="u1", email="c@ejemplo.com", name="Ana", role="user",
                   verification_status="verified" if verificado else "pending")
    transactions.db = base
    return await cotizar_envio_ves(
        CotizarEnvioVesRequest(amount=100.0, beneficiary_id="ben_1",
                               client_cpf="12345678909", metodo=metodo),
        current_user=usuario)


def test_CON_TARJETA_EL_COBRO_GUARDADO_DICE_TARJETA_Y_NO_TIENE_QR(base):
    """El test que corre el flujo entero.

    Es el que no dejó pasar que el método no se guardara: si `es_de_tarjeta`
    no tiene qué mirar, todo cae del lado de PIX y ninguna orden se puede
    pagar con tarjeta. Y si además quedara un código guardado, vuelve el doble
    cobro.
    """
    resp = corre(_cotizar(base, tarjeta.POR_TARJETA))
    assert resp["metodo"] == tarjeta.POR_TARJETA

    cobro = corre(base.gestor_pix_payments.find_one(
        {"payment_id": resp["payment_order_id"]}))
    assert cobro is not None, "la cotización no guardó el cobro"
    assert tarjeta.es_de_tarjeta(cobro) is True, (
        "el cobro guardado no dice que es de tarjeta: la ruta que cobra lo va "
        "a rechazar y la vía entera queda muerta")
    assert tarjeta.tiene_qr(cobro) is False, (
        "la cotización con tarjeta dejó un código de PIX vivo: el cliente "
        "puede pagar dos veces")


def test_CON_PIX_SE_SIGUE_GUARDANDO_COMO_PIX(base):
    """El otro lado: agregar la tarjeta no puede haber cambiado lo de siempre.

    Sin Mercado Pago configurado la cotización con PIX falla —no hay código—,
    y eso mismo es la prueba de que con PIX SI se le pide uno.
    """
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(_cotizar(base, tarjeta.POR_PIX))
    assert e.value.status_code == 503
    assert "PIX" in str(e.value.detail)


def test_el_desglose_de_la_tarjeta_VIENE_en_la_cotizacion(base):
    """La pantalla tiene que poder mostrar los dos precios antes de que la
    persona ponga los datos de la tarjeta."""
    resp = corre(_cotizar(base, tarjeta.POR_TARJETA))
    assert resp["credit_card"]["total_brl"] == 104.89
    assert resp["debit_card"]["total_brl"] == 102.39
    assert resp["credit_card"]["envio_brl"] == 100.0


def test_UN_NO_VERIFICADO_NO_LLEGA_NI_A_COTIZAR_CON_TARJETA(base):
    """Rechazarlo recién en el formulario de la tarjeta es dejarlo completar
    todo para nada."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(_cotizar(base, tarjeta.POR_TARJETA, verificado=False))
    assert e.value.status_code == 403
    assert "PIX" in e.value.detail


def test_el_metodo_QUEDA_ESCRITO_en_el_cobro():
    """La versión estática, acotada AL BLOQUE QUE GUARDA EL COBRO.

    Mirar el archivo entero era lo que dejaba pasar la mutación: el mismo
    texto vive también en la respuesta a la pantalla.
    """
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    i = fuente.index("await db.gestor_pix_payments.insert_one({")
    bloque = fuente[i:fuente.index("})", i)]
    assert '"metodo": metodo,' in bloque, (
        "el documento del cobro dejó de guardar el método: `es_de_tarjeta` no "
        "tiene qué mirar y ninguna orden se puede pagar con tarjeta.")


def test_la_ruta_pregunta_por_LAS_DOS_guardas():
    cuerpo = _cuerpo_de_la_ruta()
    assert "es_de_tarjeta" in cuerpo
    assert "tiene_qr" in cuerpo


def _cuerpo_de_la_ruta():
    fuente = (_BACKEND / "routes" / "payments_card.py").read_text(encoding="utf-8")
    return fuente[fuente.index("async def pagar_envio_con_tarjeta("):]


def test_las_guardas_van_ANTES_de_cobrarle_nada_a_nadie():
    """Preguntar tarde deja al cliente con la tarjeta ya cobrada."""
    cuerpo = _cuerpo_de_la_ruta()
    for guarda in ("es_de_tarjeta", "tiene_qr", "verification_status"):
        assert cuerpo.index(guarda) < cuerpo.index("httpx.AsyncClient"), (
            f"«{guarda}» se comprueba después de cobrarle a la tarjeta")


# ══════════════════════════════════════════════════════════════════════════
# 3. Sólo verificados, y se comprueba en los dos lados
# ══════════════════════════════════════════════════════════════════════════

def test_el_mensaje_nombra_la_via_que_SI_funciona():
    """«Verificá tu identidad» a secas deja el envío parado sin decirle que
    puede pagarlo ahora mismo con PIX."""
    assert "PIX" in tarjeta.SIN_VERIFICAR
    assert "verificar" in tarjeta.SIN_VERIFICAR.lower()


def test_LA_COTIZACION_ya_frena_al_no_verificado():
    """Rechazarlo recién en el formulario de la tarjeta es dejarlo completar
    todo para nada."""
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def cotizar_envio_ves("):]
    cuerpo = cuerpo[:cuerpo.index("\n@router")]
    assert 'current_user.verification_status != "verified"' in cuerpo
    assert "tarjeta_del_envio.SIN_VERIFICAR" in cuerpo


def test_LA_RUTA_QUE_COBRA_lo_comprueba_IGUAL():
    """Una guarda que vive en otra ruta es una guarda hasta que alguien
    reordena las rutas."""
    assert 'verification_status != "verified"' in _cuerpo_de_la_ruta()


# ══════════════════════════════════════════════════════════════════════════
# 4. Aprobar hace avanzar el envío, y no acredita saldo
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TARJETA_HACE_AVANZAR_EL_ENVIO_POR_EL_MISMO_CAMINO_QUE_EL_PIX(base):
    """`confirmar` no pregunta quién le avisó: busca la orden esperando pago y
    la mueve, en UNA escritura. Reusarlo es lo que hace que las dos vías no
    puedan divergir."""
    ahora = datetime.now(timezone.utc)
    corre(base.transactions.insert_one({
        "transaction_id": "tx_1", "user_id": "u1", "type": "withdrawal",
        "status": paf.ESPERANDO_PAGO, "payment_order_id": "venv_abc",
        "payment_expires_at": ahora + timedelta(minutes=7)}))
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": "venv_abc", "proposito": paf.PROPOSITO,
        "metodo": tarjeta.POR_TARJETA, "status": "pending"}))

    assert corre(paf.confirmar(base, {"payment_id": "venv_abc"})) is True
    orden = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert orden["status"] == paf.PENDIENTE


def test_LA_RUTA_NO_ACREDITA_SALDO(base):
    """La diferencia entera con la recarga de arriba, y lo que hace que esto
    no sea custodiar plata de nadie.

    Si esta ruta llamara a `saldos.mover` para el cliente, la tarjeta volvería
    a ser una recarga con otro nombre — justo lo que la empresa no puede
    ofrecer.
    """
    cuerpo = _cuerpo_de_la_ruta()
    assert "saldos.mover" not in cuerpo, (
        "la ruta que paga un envío con tarjeta acredita saldo: eso es una "
        "recarga, y la recarga está cerrada.")
    assert "pago_al_final.confirmar" in cuerpo


def test_lo_que_se_cobra_sale_de_LA_ORDEN_y_no_de_la_pantalla():
    """Si el monto llegara en el cuerpo del pedido, el cliente elegiría cuánto
    pagar por su propio envío."""
    cuerpo = _cuerpo_de_la_ruta()
    entrada = (_BACKEND / "routes" / "payments_card.py").read_text(encoding="utf-8")
    entrada = entrada[entrada.index("class PagarEnvioConTarjetaInput"):]
    entrada = entrada[:entrada.index("\n\nclass ")]
    for prohibido in ("amount", "monto", "total"):
        assert prohibido not in entrada, (
            f"el pedido acepta «{prohibido}»: el cliente estaría eligiendo "
            f"cuánto pagar por su envío")
    assert 'orden.get("payment_amount_brl")' in cuerpo


def test_un_envio_de_OTRO_no_se_puede_pagar():
    """Sin el dueño en el filtro, cualquiera con la referencia paga —o rompe—
    el envío de otra persona."""
    cuerpo = _cuerpo_de_la_ruta()
    assert '"gestor_id": current_user.user_id' in cuerpo
    assert '"user_id": current_user.user_id' in cuerpo


def test_una_orden_VENCIDA_no_se_cobra():
    """Los siete minutos son los que congelan la tasa. Cobrar después es
    cobrarle un precio que ya no existe."""
    cuerpo = _cuerpo_de_la_ruta()
    assert "payment_expires_at" in cuerpo
    assert cuerpo.index("payment_expires_at") < cuerpo.index("httpx.AsyncClient")


def test_una_orden_YA_PAGADA_no_se_cobra_otra_vez():
    cuerpo = _cuerpo_de_la_ruta()
    assert "pago_al_final.ESPERANDO_PAGO" in cuerpo


def test_el_intento_RECHAZADO_tambien_queda_escrito():
    """Un rechazo sin rastro es un cliente diciendo «me lo rechazaron» y nadie
    pudiendo mirar por qué."""
    cuerpo = _cuerpo_de_la_ruta()
    i_insert = cuerpo.index("db.card_payments.insert_one")
    i_aprobado = cuerpo.index('status_mp == "approved"')
    assert i_insert < i_aprobado, (
        "el intento se guarda sólo si aprueba: los rechazos no dejan rastro")


# ══════════════════════════════════════════════════════════════════════════
# 5. Esta vía NO es una recarga
# ══════════════════════════════════════════════════════════════════════════

def test_LA_RUTA_NO_LLEVA_LA_GUARDA_DE_LA_RECARGA():
    """Con la carga de saldo cerrada, ponerle esta guarda mataría la vía
    entera. No carga saldo: paga un envío."""
    assert "recarga_abierta" not in _cuerpo_de_la_ruta(), (
        "la ruta que paga un envío con tarjeta pregunta por la guarda de la "
        "recarga: con la carga cerrada deja de funcionar, y no es una recarga.")


def test_LAS_QUE_SI_CARGAN_SALDO_la_siguen_llevando():
    """El otro lado de lo mismo: agregar esta vía no puede haber abierto las
    que sí cargan saldo."""
    fuente = (_BACKEND / "routes" / "payments_card.py").read_text(encoding="utf-8")
    for funcion in ("quote_card_payment", "process_card_payment"):
        cuerpo = fuente[fuente.index(f"async def {funcion}("):]
        cuerpo = cuerpo[:cuerpo.find("\n@router")]
        assert "recarga_abierta.exigir_abierta" in cuerpo, (
            f"{funcion} dejó de preguntar: la recarga con tarjeta quedó "
            f"abierta por un costado.")


# ══════════════════════════════════════════════════════════════════════════
# 6. Que la pantalla haga lo mismo que el servidor
#
#   Las guardas del backend pueden estar completas y la pantalla ofrecer lo que
#   el servidor va a rechazar. Pasó con `PuertaCripto` y volvió a pasar con los
#   textos que quedaron sueltos al esconder el botón de recargar: las dos veces
#   los tests estaban en verde y el defecto apareció mirando la pantalla.
# ══════════════════════════════════════════════════════════════════════════

_SRC = _BACKEND.parent / "frontend" / "src"
_SEND = _SRC / "pages" / "Send.jsx"
_BRICK = _SRC / "components" / "CardPaymentBrick.jsx"


def test_LA_PANTALLA_LE_DICE_AL_SERVIDOR_CON_QUE_SE_VA_A_PAGAR():
    """Si no lo mandara, el servidor cotizaría como PIX —es lo que vale por
    omisión— y generaría un código. Entonces el botón «Pagar con tarjeta»
    llevaría a una orden que la ruta de la tarjeta rechaza."""
    texto = _SEND.read_text(encoding="utf-8")
    assert "cotizarYPagar('tarjeta')" in texto
    assert "cotizarYPagar('pix')" in texto
    assert "\n        metodo,\n" in texto, (
        "la pantalla dejó de mandar el método: todo se va a cotizar como PIX")


def test_EL_BOTON_DE_LA_TARJETA_SOLO_PARA_VERIFICADOS():
    """El servidor lo rechaza igual. Esconderlo es para que no complete el
    formulario entero de la tarjeta para nada."""
    texto = _SEND.read_text(encoding="utf-8")
    assert "pagoAlFinal && estaVerificado ?" in texto, (
        "el botón de la tarjeta dejó de mirar si la cuenta está verificada: "
        "quien no lo está va a completar todo y comerse un 403 al final.")
    assert "user?.verification_status === 'verified'" in texto


def test_LA_PANTALLA_AVISA_QUE_LA_TARJETA_CUESTA_MAS_ANTES_DE_APRETAR():
    """La única diferencia que importa contra el PIX. Descubrirla recién en el
    resumen es descubrirla tarde: ya eligió."""
    texto = _SEND.read_text(encoding="utf-8")
    assert "tarjeta-cuesta-mas" in texto
    assert "Con PIX no." in texto


def test_EL_PASO_DEL_QR_NO_SE_DIBUJA_CUANDO_ES_TARJETA():
    """Con tarjeta el servidor no genera ningún código, a propósito. Dibujar
    ese paso igual sería un recuadro vacío donde debería estar el QR."""
    texto = _SEND.read_text(encoding="utf-8")
    assert "cobro.metodo === 'tarjeta' ?" in texto
    assert "cobro.metodo !== 'tarjeta' ?" in texto


def test_EL_FORMULARIO_NO_MANDA_EL_MONTO_CUANDO_PAGA_UN_ENVIO():
    """Si lo mandara, el cliente elegiría cuánto pagar por su propio envío."""
    texto = _BRICK.read_text(encoding="utf-8")
    assert "? { ...comun, payment_order_id: envio.payment_order_id }" in texto
    assert "envio ? '/payments/card/envio' : '/payments/card/process'" in texto


def test_LA_PANTALLA_NO_SACA_NINGUNA_CUENTA_DE_DINERO():
    """Dos implementaciones de la misma fórmula es ver un número y que te
    cobren otro. El desglose lo calcula el servidor al cotizar.

    LA PRIMERA VERSION DE ESTE TEST NO SERVIA.

        Buscaba los nombres de las tarifas y el literal `* 0.0449`. Poniendo
        `amountRis * 1.0449 + 0.40` en el total —la misma cuenta, escrita
        distinta— los cuarenta tests siguieron en verde.

        Buscar UNA forma de escribir la cuenta es tan bueno como la
        imaginación de quien escribió el test. Lo que se comprueba ahora es
        que el número salga de donde tiene que salir, y que no haya ninguna
        aritmética sobre montos en el archivo.
    """
    import re
    texto = _BRICK.read_text(encoding="utf-8")
    cuerpo = texto[texto.index("export default function CardPaymentBrick"):]

    # 1. El total sale del desglose del servidor, y de ahí nomás.
    assert ("const totalAPagar = envio ? desglose?.total_brl "
            ": quote?.total_charged_brl;") in cuerpo, (
        "el total que se le cobra a la tarjeta dejó de salir del desglose que "
        "calculó el servidor.")

    # 2. Ninguna cuenta con plata, escrita como sea. Se miran las líneas que
    #    nombran un monto y se exige que no multipliquen, dividan ni sumen.
    PLATA = ("total_brl", "comision_brl", "envio_brl", "amountRis",
             "total_charged_brl", "fee_brl", "totalAPagar")
    for n, linea in enumerate(cuerpo.splitlines(), 1):
        codigo = linea.split("//")[0]
        if not any(m in codigo for m in PLATA):
            continue
        if re.search(r"[)\w\s](\*|/)\s*[\d(]|[\d)]\s*(\*|/)", codigo) \
                or re.search(r"[\w)]\s*\+\s*\d", codigo):
            pytest.fail(
                f"el formulario de la tarjeta hace una cuenta con plata en la "
                f"línea {n}:\n    {linea.strip()}\n"
                f"El día que cambie la tarifa va a mostrar un número y se va a "
                f"cobrar otro. El desglose lo calcula el servidor.")

    # 3. Y nunca las tarifas, que son del servidor.
    for tarifa in ("credit_pct", "debit_pct", "flat_brl"):
        assert tarifa not in cuerpo, (
            f"el formulario lee la tarifa «{tarifa}»: eso es sacar la cuenta")


def test_LA_PANTALLA_DE_APROBADO_NO_PROMETE_UN_SALDO_QUE_NO_EXISTE():
    """Decirle «se acreditaron X a tu saldo» a quien pagó un envío es mandarlo
    a buscar un saldo que nunca existió: la plata entró y salió en la misma
    operación. Es el mismo error que los textos que quedaron sueltos al
    esconder el botón de recargar."""
    texto = _BRICK.read_text(encoding="utf-8")
    assert "card-aprobado-texto" in texto
    assert "tu envío ya está en camino" in texto


def test_SE_LE_DICE_CUANTO_SALDRIA_CON_PIX():
    """El «me cobraron de más» que llega por soporte se evita poniendo el
    número del PIX al lado, no explicando después."""
    texto = _BRICK.read_text(encoding="utf-8")
    assert "card-vs-pix" in texto
    assert "sin\n            comisión" in texto or "sin comisión" in texto


# ══════════════════════════════════════════════════════════════════════════
# 7. La guarda del doble cobro, EJECUTADA contra la ruta de verdad
#
#   Los tests de la sección 2 comprueban la función que decide. Éstos llaman a
#   la ruta entera: es la diferencia entre saber que la regla está escrita y
#   saber que la ruta la aplica.
# ══════════════════════════════════════════════════════════════════════════

def _cuerpo_del_cobro(ref, tipo="credit_card"):
    from routes.payments_card import PagarEnvioConTarjetaInput, PayerIdentification
    return PagarEnvioConTarjetaInput(
        payment_order_id=ref, token="tok_de_prueba", payment_method_id="visa",
        payment_type_id=tipo, payer_email="cliente@ejemplo.com",
        identification=PayerIdentification(type="CPF", number="12345678909"))


async def _sembrar_orden(base, *, metodo, qr="", estado=None, minutos=7,
                         dueno="u1"):
    """Una orden esperando el pago, como la deja la cotización."""
    from services import pago_al_final as p
    ahora = datetime.now(timezone.utc)
    await base.transactions.insert_one({
        "transaction_id": "tx_x", "display_id": "W-1", "user_id": dueno,
        "type": "withdrawal", "status": estado or p.ESPERANDO_PAGO,
        "payment_order_id": "venv_x", "payment_amount_brl": 100.0,
        "payment_expires_at": ahora + timedelta(minutes=minutos),
        "created_at": ahora})
    await base.gestor_pix_payments.insert_one({
        "payment_id": "venv_x", "gestor_id": dueno,
        "proposito": p.PROPOSITO, "metodo": metodo, "qr_code": qr,
        "status": "pending", "created_at": ahora})


def _cobrar(base, **kw):
    """Llama a la ruta y devuelve el HTTPException que levantó, o None."""
    from fastapi import HTTPException
    from models.user import User
    from routes import payments_card

    async def _ir():
        await _sembrar_orden(base, **kw)
        payments_card.db = base
        usuario = User(user_id="u1", email="c@ejemplo.com", name="Ana",
                       role="user", verification_status="verified")
        return await payments_card.pagar_envio_con_tarjeta(
            _cuerpo_del_cobro("venv_x"), current_user=usuario)

    try:
        corre(_ir())
        return None
    except HTTPException as e:
        return e


def test_LA_RUTA_RECHAZA_UNA_ORDEN_COTIZADA_PARA_PIX(base):
    """LA PRUEBA QUE MAS IMPORTA DE TODO EL LOTE.

    Esa orden tiene un código vivo. Cobrarla además con tarjeta le saca la
    plata dos veces al cliente, y sólo una avanza el envío.
    """
    e = _cobrar(base, metodo=tarjeta.POR_PIX, qr="000201-un-pix-vivo")
    assert e is not None, (
        "la ruta cobró con tarjeta una orden que tiene un PIX vivo: el "
        "cliente puede pagar dos veces")
    assert e.status_code == 409
    assert "PIX" in e.detail


def test_LA_RUTA_RECHAZA_LA_ORDEN_QUE_DICE_TARJETA_PERO_TIENE_QR(base):
    """El caso que justifica la segunda guarda. Ver la sección 2."""
    e = _cobrar(base, metodo=tarjeta.POR_TARJETA, qr="000201-un-pix-vivo")
    assert e is not None and e.status_code == 409, (
        "una orden que dice ser de tarjeta y tiene un código guardado se "
        "cobró igual: vuelve el doble cobro")


def test_un_cobro_viejo_SIN_el_campo_tampoco_se_cobra(base):
    e = _cobrar(base, metodo=None, qr="000201")
    assert e is not None and e.status_code == 409


def test_LA_ORDEN_LIMPIA_DE_TARJETA_PASA_LAS_GUARDAS(base):
    """El otro lado: si nada pasara, la vía entera estaría muerta y los tests
    de arriba pasarían igual.

    Llega hasta Mercado Pago y falla ahí por falta de credenciales en el
    entorno de test, que es exactamente lo que tiene que pasar: las guardas la
    dejaron pasar.
    """
    e = _cobrar(base, metodo=tarjeta.POR_TARJETA, qr="")
    assert e is not None, "sin credenciales de Mercado Pago tenía que fallar"
    assert e.status_code == 500 and "MP no configurado" in e.detail, (
        f"la orden limpia de tarjeta se frenó en una guarda ({e.status_code}: "
        f"{e.detail}): la vía entera está muerta")


def test_una_orden_VENCIDA_no_se_cobra_de_verdad(base):
    e = _cobrar(base, metodo=tarjeta.POR_TARJETA, minutos=-1)
    assert e is not None and e.status_code == 409
    assert "venció" in e.detail


def test_una_orden_YA_PAGADA_no_se_cobra_de_verdad(base):
    e = _cobrar(base, metodo=tarjeta.POR_TARJETA, estado=paf.PENDIENTE)
    assert e is not None and e.status_code == 409
    assert "historial" in e.detail


def test_EL_ENVIO_DE_OTRO_no_se_puede_cobrar(base):
    """Sin el dueño en el filtro, cualquiera con la referencia paga el envío
    de otra persona."""
    e = _cobrar(base, metodo=tarjeta.POR_TARJETA, dueno="otro_usuario")
    assert e is not None and e.status_code == 404


def test_UN_NO_VERIFICADO_no_puede_cobrar_aunque_llegue(base):
    """La cotización ya lo frena. Esto comprueba que la ruta no depende de
    eso: una guarda que vive en otra ruta es una guarda hasta que alguien
    reordena las rutas."""
    from fastapi import HTTPException
    from models.user import User
    from routes import payments_card

    async def _ir():
        await _sembrar_orden(base, metodo=tarjeta.POR_TARJETA)
        payments_card.db = base
        return await payments_card.pagar_envio_con_tarjeta(
            _cuerpo_del_cobro("venv_x"),
            current_user=User(user_id="u1", email="c@ejemplo.com", name="Ana",
                              role="user", verification_status="pending"))

    with pytest.raises(HTTPException) as e:
        corre(_ir())
    assert e.value.status_code == 403
    assert "PIX" in e.value.detail
