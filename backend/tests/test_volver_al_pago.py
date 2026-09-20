"""
tests/test_volver_al_pago.py — Retomar un pedido que quedó a medias.

POR QUE EXISTE ESTE ARCHIVO

    El cliente cotiza, le aparece el QR, y cierra la pantalla. Se le corta el
    teléfono, se le vence la sesión, lo llaman.

    Hasta ahora eso era el final: lo que hacía falta para dibujar esa pantalla
    venía en la respuesta de la cotización y no había forma de pedirlo de
    nuevo. El pedido quedaba en el historial y no se podía retomar.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que se pueda volver a ver CON QUE se paga, sea QR, tarjeta o banco.
    2. Que un pedido vencido lo diga, con el texto de SU corredor. Son
       distintos a propósito: en Brasil el cliente pudo haber pagado sin subir
       el comprobante, y decirle sólo «expiró» es decirle que perdió la plata.
    3. Que un pedido YA PAGADO no diga «expirado». Es el peor mensaje posible
       para quien ya pagó.
    4. Que el pedido de OTRO no se pueda mirar.
    5. Que no se filtre nada que el cliente no tenga que ver.
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

from fastapi import HTTPException                             # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from models.user import User                                  # noqa: E402
from services import pago_al_final as paf                     # noqa: E402
from services import volver_al_pago as vap                    # noqa: E402

ensenarle_decimal128_a_mongomock()

# LA HORA SE MIRA AL SEMBRAR, NO AL IMPORTAR.
#
#   Estaba congelada en una constante de módulo. Corriendo este archivo solo
#   no se notaba; en la suite completa pasan minutos entre que se importa y
#   que le toca el turno, así que «vence en 5 minutos» ya era «vence en 1» y
#   el test del reloj fallaba sin que hubiera nada roto.
#
#   Un test que sólo pasa cuando corre primero es un test que un día frena un
#   despliegue por nada.
def ahora():
    return datetime.now(timezone.utc)



def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


CLIENTE = User(user_id="u1", email="c@ejemplo.com", name="Ana", role="user",
               verification_status="verified")


def sembrar(base, *, referencia="venv_1", metodo="pix", minutos=5,
            estado=None, dueno="u1", qr="000201-el-qr", tx="tx_1"):
    corre(base.transactions.insert_one({
        "transaction_id": tx, "display_id": "1001", "user_id": dueno,
        "type": "withdrawal", "status": estado or paf.ESPERANDO_PAGO,
        "payment_order_id": referencia, "payment_amount_brl": 100.0,
        "payment_expires_at": ahora() + timedelta(minutes=minutos),
        "amount_input": 100.0, "amount_output": 11000.0,
        "currency_input": "RIS", "currency_output": "VES", "rate": 110.0,
        "beneficiary_data": {"full_name": "María Pérez"},
        "created_at": ahora()}))
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": referencia, "gestor_id": dueno,
        "proposito": paf.PROPOSITO, "metodo": metodo,
        "qr_code": qr if metodo == "pix" else "",
        "qr_code_base64": "AAA" if metodo == "pix" else "",
        # Un campo que el cliente NO tiene que ver.
        "mp_response": {"payer": {"email": "otro@ejemplo.com"}},
        "status": "pending", "created_at": ahora()}))


def pedir(base, tx="tx_1", usuario=None):
    """Lo que el cliente RECIBE, no el diccionario que arma la ruta.

    LA DIFERENCIA IMPORTA, y la encontró un test que fallaba.

        La ruta devuelve un diccionario y FastAPI lo pasa por
        `ComoPagarEstePedido` antes de mandarlo: ahí se rellenan los campos
        que faltan y —lo que de verdad importa— se RECORTA lo que no esté
        declarado.

        Llamando a la función directa, ese recorte no ocurre. Un test que
        mirara el diccionario crudo daría por bueno un campo que el cliente
        nunca va a ver, y peor: no vería un campo de más que sí se estuviera
        filtrando.
    """
    from routes import transactions
    from routes.transactions import ComoPagarEstePedido
    transactions.db = base
    crudo = corre(transactions.como_pagar_este_pedido(
        tx, current_user=usuario or CLIENTE))
    return ComoPagarEstePedido(**crudo).model_dump()


# ══════════════════════════════════════════════════════════════════════════
# 1. Volver a ver con qué se paga
# ══════════════════════════════════════════════════════════════════════════

def test_CON_PIX_VUELVE_EL_CODIGO(base):
    """El caso por el que existe todo esto: el cliente cerró la pantalla y el
    QR estaba sólo ahí."""
    sembrar(base, metodo="pix")
    r = pedir(base)
    assert r["se_puede_pagar"] is True
    assert r["qr_code"] == "000201-el-qr"
    assert r["copy_paste_code"] == "000201-el-qr", (
        "sin el «copia y pega» queda sólo la imagen, que en una computadora "
        "no se puede escanear")
    assert r["metodo"] == "pix"


def test_CON_TARJETA_VUELVE_EL_DESGLOSE(base):
    """No hay QR que mostrar: lo que hace falta es la referencia para cobrar y
    cuánto sale, que es lo que decide si sigue o se vuelve al PIX."""
    sembrar(base, metodo="tarjeta", qr="")
    r = pedir(base)
    assert r["metodo"] == "tarjeta"
    assert r["qr_code"] == ""
    assert r["payment_order_id"] == "venv_1"
    assert r["credit_card"]["total_brl"] == 104.89
    assert r["debit_card"]["total_brl"] == 102.39


def test_EL_DESGLOSE_DE_LA_TARJETA_ES_EL_MISMO_QUE_AL_COTIZAR(base):
    """Se recalcula, no se guardó. Si diera otro número, el cliente vería un
    precio al cotizar y otro al volver."""
    from services import tarjeta_del_envio
    from services.money import to_decimal
    sembrar(base, metodo="tarjeta", qr="")
    r = pedir(base)
    esperado = tarjeta_del_envio.cuanto_se_le_cobra(
        to_decimal("100"), "credit_card",
        {"credit_pct": 4.49, "debit_pct": 1.99, "flat_brl": 0.40})
    assert r["credit_card"]["total_brl"] == float(esperado["total_brl"])


def test_EN_BRASIL_VUELVEN_LOS_BANCOS(base):
    """Ahí no hay QR ni tarjeta: lo que necesita es a dónde transferir."""
    sembrar(base, referencia="brl_1", metodo="pix")
    r = pedir(base)
    assert r["corredor"] == "brasil"
    assert r["bancos"] is not None, (
        "sin los bancos el cliente no sabe a dónde transferir")


def test_el_reloj_lo_calcula_EL_SERVIDOR(base):
    """El del teléfono puede estar corrido. Un cliente con la hora adelantada
    vería «expirado» sobre un cobro vivo."""
    sembrar(base, minutos=5)
    r = pedir(base)
    assert 250 < r["segundos_restantes"] <= 300


def test_vuelve_a_quien_le_manda_y_cuanto(base):
    """La pantalla lo muestra para que confirme que es el pedido que cree."""
    r = (sembrar(base), pedir(base))[1]
    assert r["beneficiary_data"]["full_name"] == "María Pérez"
    assert r["amount_output"] == 11000.0
    assert r["rate"] == 110.0


# ══════════════════════════════════════════════════════════════════════════
# 2. EL PEDIDO VENCIDO, con el texto de SU corredor
# ══════════════════════════════════════════════════════════════════════════

def test_VENEZUELA_VENCIDO_lo_dice(base):
    sembrar(base, referencia="venv_1", minutos=-1)
    r = pedir(base)
    assert r["se_puede_pagar"] is False
    assert "expiró" in r["motivo"]
    assert r["qr_code"] == "", (
        "se devolvió el código de un cobro vencido: el cliente lo va a pagar")


def test_BRASIL_VENCIDO_NOMBRA_LAS_DOS_SITUACIONES(base):
    """El texto que pidió el dueño, y el motivo de que sea distinto.

    Ahí el cliente transfiere por su cuenta y después sube el comprobante.
    Puede haber pagado y no haber llegado a subirlo — y en ese caso hay plata
    suya dando vueltas. Decirle sólo «expiró» es decirle que la perdió.
    """
    sembrar(base, referencia="brl_1", minutos=-1)
    r = pedir(base)
    assert r["se_puede_pagar"] is False
    assert "soporte" in r["motivo"].lower(), (
        "el mensaje de Brasil no manda a soporte a quien ya transfirió")
    assert "ni vuelvas a transferir" in r["motivo"], (
        "no le dice que NO vuelva a pagar: puede transferir dos veces")


def test_LOS_DOS_MENSAJES_SON_DISTINTOS():
    """Si un día se unifican, el de Brasil pierde la mitad que importa."""
    assert vap.VENCIDO_VENEZUELA != vap.VENCIDO_BRASIL


def test_VENCE_POR_EL_RELOJ_aunque_el_estado_no_haya_cambiado(base):
    """El barrido corre cada minuto. En esa ventana la orden todavía dice
    «esperando pago» y el cobro ya está muerto: guiarse sólo por el estado le
    mostraría un QR que no sirve."""
    sembrar(base, minutos=-1, estado=paf.ESPERANDO_PAGO)
    assert vap.esta_vencido(corre(base.transactions.find_one({}))) is True
    assert pedir(base)["se_puede_pagar"] is False


def test_vence_por_el_ESTADO_aunque_la_fecha_no_haya_llegado(base):
    """Una orden apartada por pago tardío no se vuelve a pagar, tenga la fecha
    que tenga."""
    sembrar(base, minutos=5, estado=paf.PAGO_TARDIO)
    assert pedir(base)["se_puede_pagar"] is False


# ══════════════════════════════════════════════════════════════════════════
# 3. Lo que NO puede decir
# ══════════════════════════════════════════════════════════════════════════

def test_UN_PEDIDO_YA_PAGADO_NO_DICE_EXPIRADO(base):
    """El peor mensaje posible para quien ya pagó."""
    sembrar(base, estado=paf.PENDIENTE)
    r = pedir(base)
    assert r["se_puede_pagar"] is False
    assert "expir" not in (r["motivo"] or "").lower(), (
        f"a quien ya pagó se le dice que su pedido expiró: «{r['motivo']}»")
    assert "historial" in r["motivo"]


def test_un_envio_pagado_con_SALDO_no_tiene_pantalla_de_pago(base):
    """No hay nada que mostrar, y decir «expirado» sería mentira."""
    corre(base.transactions.insert_one({
        "transaction_id": "tx_saldo", "user_id": "u1", "type": "withdrawal",
        "status": "pending", "amount_input": 50.0, "created_at": ahora()}))
    with pytest.raises(HTTPException) as e:
        pedir(base, "tx_saldo")
    assert e.value.status_code == 409
    assert "saldo" in e.value.detail


# ══════════════════════════════════════════════════════════════════════════
# 4. De quién es el pedido, y qué sale de él
# ══════════════════════════════════════════════════════════════════════════

def test_EL_PEDIDO_DE_OTRO_NO_SE_MIRA(base):
    sembrar(base, dueno="otro_usuario")
    with pytest.raises(HTTPException) as e:
        pedir(base)
    assert e.value.status_code == 404


def test_el_cobro_se_busca_TAMBIEN_por_el_dueño(base):
    """Dos filtros y no uno: si la orden se filtrara por dueño y el cobro no,
    bastaría con que coincidiera la referencia."""
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def como_pagar_este_pedido("):]
    cuerpo = cuerpo[:cuerpo.index("\n@router")]
    assert cuerpo.count("current_user.user_id") >= 2


def test_NO_SE_FILTRA_LA_RESPUESTA_DE_MERCADO_PAGO(base):
    """Trae los datos del pagador. Sale por lista de lo permitido justamente
    para que un campo nuevo no se cuele solo."""
    sembrar(base)
    r = pedir(base)
    plano = str(r)
    assert "mp_response" not in plano
    assert "otro@ejemplo.com" not in plano, (
        "se filtró el correo que guarda Mercado Pago en el cobro")


def test_el_contrato_es_por_LISTA_DE_LO_PERMITIDO():
    fuente = (_BACKEND / "routes" / "transactions.py").read_text(encoding="utf-8")
    assert "response_model=ComoPagarEstePedido" in fuente, (
        "la ruta dejó de declarar qué devuelve: cualquier campo nuevo del "
        "documento se le va al cliente")


# ══════════════════════════════════════════════════════════════════════════
# 5. Que la pantalla haga lo mismo que el servidor
#
#   Las guardas del backend pueden estar completas y la pantalla no llamarlas
#   nunca. Pasó con `PuertaCripto` y con los textos que quedaron sueltos al
#   esconder el botón de recargar: las dos veces los tests estaban en verde y
#   el defecto apareció mirando la pantalla.
# ══════════════════════════════════════════════════════════════════════════

_SRC = _BACKEND.parent / "frontend" / "src"


def test_EL_HISTORIAL_DEJA_ABRIR_UN_PEDIDO_EN_CURSO():
    """Sin esto, la ruta existe y no hay cómo llegar a ella."""
    texto = (_SRC / "components" / "dashboard" / "TransactionItem.jsx").read_text(
        encoding="utf-8")
    assert "/envios/${tx.transaction_id}/pagar" in texto, (
        "el historial no deja abrir el pedido: la pantalla existe y nadie "
        "puede llegar")


def test_TAMBIEN_SE_ABRE_UNO_VENCIDO():
    """Es la única forma de que el cliente sepa POR QUE no avanza. Si sólo se
    abriera el que se puede pagar, el vencido quedaría mudo."""
    texto = (_SRC / "components" / "dashboard" / "TransactionItem.jsx").read_text(
        encoding="utf-8")
    cuerpo = texto[texto.index("const sePuedeRetomar"):]
    cuerpo = cuerpo[:cuerpo.index(";")]
    assert "awaiting_payment" in cuerpo and "payment_expired" in cuerpo


@pytest.mark.parametrize("estado", [
    "payment_expired", "awaiting_review", "payment_late"])
def test_LOS_ESTADOS_NUEVOS_TIENEN_SU_ETIQUETA(estado):
    """`StatusBadge` cae a «Pendiente» cuando no encuentra el estado.

    Así que un pedido vencido, uno esperando que alguien mire el comprobante y
    uno con un pago fuera de tiempo se veían los tres igual: como si
    estuvieran en camino. Al primero le decía que espere algo que ya no va a
    pasar; al tercero, que estaba todo bien cuando hay plata suya esperando
    una decisión.
    """
    texto = (_SRC / "components" / "dashboard" / "TransactionItem.jsx").read_text(
        encoding="utf-8")
    catalogo = texto[texto.index("STATUS_CONFIG"):texto.index("export function StatusBadge")]
    assert f"{estado}:" in catalogo, (
        f"«{estado}» no está en el catálogo de estados: el historial lo va a "
        f"mostrar como «Pendiente»")


def test_LA_ETIQUETA_DE_VENCIDO_NO_DICE_PENDIENTE():
    """El defecto entero en una línea."""
    texto = (_SRC / "components" / "dashboard" / "TransactionItem.jsx").read_text(
        encoding="utf-8")
    i = texto.index("payment_expired:")
    linea = texto[i:texto.index("\n", i)]
    assert "Pendiente" not in linea
    assert "Expirado" in linea


def test_LA_PANTALLA_NO_CALCULA_EL_VENCIMIENTO_POR_SU_CUENTA():
    """El reloj del teléfono puede estar corrido. Si la pantalla comparara
    contra su propia hora, un cliente con la hora adelantada vería «expirado»
    sobre un cobro vivo — y uno con la atrasada, al revés."""
    texto = (_SRC / "pages" / "RetomarPago.jsx").read_text(encoding="utf-8")
    cuerpo = texto[texto.index("export default function RetomarPago"):]
    for cuenta in ("Date.now()", "new Date()", "expires_at"):
        assert cuenta not in cuerpo, (
            f"la pantalla calcula el vencimiento con «{cuenta}» en vez de "
            f"usar los segundos que le da el servidor")
    assert "segundos_restantes" in cuerpo


def test_LA_PANTALLA_MUESTRA_EL_MOTIVO_QUE_MANDA_EL_SERVIDOR():
    """Los dos textos son distintos por corredor. Si la pantalla escribiera el
    suyo, el de Brasil perdería la mitad que manda a soporte."""
    texto = (_SRC / "pages" / "RetomarPago.jsx").read_text(encoding="utf-8")
    assert "{pago.motivo}" in texto
    for propio in ("expiró", "soporte", "transferir"):
        cuerpo = texto[texto.index("export default function RetomarPago"):]
        assert propio not in cuerpo, (
            f"la pantalla escribe su propio mensaje de vencido («{propio}»): "
            f"el del servidor cambia por corredor y éste no")


def test_EL_COPIA_Y_PEGA_ESTA():
    """En una computadora el QR no se puede escanear — y ahí es justo donde
    más gente cierra la pantalla y vuelve después."""
    texto = (_SRC / "pages" / "RetomarPago.jsx").read_text(encoding="utf-8")
    assert "copy_paste_code" in texto
    assert "retomar-copiar" in texto


def test_LA_RUTA_DE_PAGAR_VA_ANTES_QUE_LA_DEL_DETALLE():
    """`/envios/:envioId` se comería «tx_xxx/pagar» y abriría el detalle de
    una encomienda que no existe."""
    texto = (_SRC / "App.jsx").read_text(encoding="utf-8")
    assert texto.index("/envios/:transactionId/pagar") < texto.index('"/envios/:envioId"')
