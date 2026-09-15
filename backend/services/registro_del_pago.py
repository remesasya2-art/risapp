"""
services/registro_del_pago.py — Asentar un pago que YA SE HIZO.

QUE ES «REGISTRAR», Y QUE NO ES

    En este flujo la aplicación NO PAGA. El pago lo hace una persona en la
    banca en línea del banco venezolano, con el archivo que bajó del panel.
    Acá se asienta que se hizo: la orden pasa a completada, queda su
    comprobante, se le avisa al cliente y se le consume el cupo.

    Por eso no hay ningún movimiento de saldo acá. El saldo del cliente se
    debitó cuando creó el envío; lo que faltaba era la constancia.

POR QUE ESTO ES UN MODULO Y NO VIVE ADENTRO DE LA RUTA

    Hay dos caminos que asientan un pago: el botón «Procesar pago» de una
    orden suelta, y «Cerrar el lote», que asienta de una vez todas las del
    lote que tienen su comprobante.

    Si cada uno tuviera su propia versión, la primera corrección que alguien
    hiciera en uno no llegaría al otro, y lo que se perdería no se nota: el
    aviso al cliente, o el cupo. Nadie se entera hasta que alguien pregunta
    por qué a él no le llegó nada.

    Así que el trabajo está escrito una sola vez y los dos caminos lo llaman.

LA CARRERA, Y POR QUE LA CONDICION VA ADENTRO DE LA ESCRITURA

    Dos agentes pueden tener la misma orden abierta. Mirar el estado y
    después escribir deja una ventana entre las dos cosas, y en esa ventana
    caben dos avisos al mismo cliente por el mismo pago y dos consumos de su
    cupo.

    `status: "pending"` va DENTRO del filtro del `update_one`: la base
    resuelve quién llegó primero, y el segundo se entera porque no modificó
    nada. Es la misma forma que usa `services/pagos_una_sola_vez`.
"""
import logging

from datetime import datetime, timezone

from services import auditoria, kyc_quota
from services.money import para_mostrar
from services.notifications import create_notification

logger = logging.getLogger(__name__)


async def _consumir_cupo(db, transaccion):
    """El cupo sin verificación, que se gasta al completarse el envío.

    Va en su propia escritura y no puede tumbar el registro: si fallara, el
    pago igual quedó asentado y lo que se pierde es un contador.

    `amount_input` son RIS en los envíos de bolívares y de reales, pero USDT o
    USDC en los de cripto, con el mismo `type: "withdrawal"`. Sumar eso al
    contador mezclaría monedas, así que del envío en cripto se cuenta la
    OPERACION y no el monto.
    """
    try:
        moneda = (transaccion.get("currency_input") or "RIS").upper()
        monto = transaccion.get("amount_input", 0) if moneda == "RIS" else 0
        despues = await db.users.find_one_and_update(
            {"user_id": transaccion["user_id"]},
            {"$inc": kyc_quota.consume_inc(monto)},
            return_document=True,
        )
        await kyc_quota.notify_if_exhausted(despues)
    except Exception as e:
        logger.warning("kyc_quota: no se pudo consumir cupo en %s: %s",
                       transaccion.get("transaction_id"), e)


async def registrar(db, transaccion: dict, *, quien=None, banco: str = None,
                    comprobantes: list = None, request=None) -> bool:
    """Asienta el pago de un envío. Devuelve si esta llamada fue la que lo hizo.

    `False` no es un error: quiere decir que la orden ya no estaba pendiente
    —otro agente la asentó, o se rechazó— y que acá no se tocó nada.

    `comprobantes` sólo se escribe si viene. En el camino del lote las fotos
    ya se colgaron de la orden cuando se adjudicaron, y pisarlas con una lista
    vacía borraría la prueba del pago.
    """
    orden_id = transaccion.get("transaction_id")
    cambios = {
        "status": "completed",
        "completed_at": datetime.now(timezone.utc),
        "processed_by": getattr(quien, "user_id", None),
    }
    if banco:
        cambios["paid_from_bank"] = banco
    if comprobantes:
        cambios["proof_images"] = comprobantes

    resultado = await db.transactions.update_one(
        {"transaction_id": orden_id, "status": "pending"}, {"$set": cambios})
    if getattr(resultado, "modified_count", 0) != 1:
        logger.info("registro_del_pago: %s ya no estaba pendiente", orden_id)
        return False

    await _consumir_cupo(db, transaccion)

    await create_notification(
        user_id=transaccion["user_id"],
        title="Tu retiro se completó",
        message=f"Ya enviamos {para_mostrar(transaccion.get('amount_output'), 'VES')} "
                "a tu beneficiario.",
        notification_type="withdrawal_completed",
        # El número de la operación viaja en el aviso para que el correo pueda
        # armar el comprobante con forma de pasaje, en vez de mandar un
        # párrafo. Ver `services/pasaje.py`.
        data={"transaction_id": orden_id},
    )

    if transaccion.get("gestor_transaction_id"):
        await db.gestor_transactions.update_one(
            {"transaction_id": transaccion["gestor_transaction_id"]},
            {"$set": {"status": "completed",
                      "completed_at": datetime.now(timezone.utc)}})

    # LA LINEA DE AUDITORIA, QUE HASTA ACA NO SE ESCRIBIA
    #
    #     `dinero.retiro_aprobado` estaba declarada en `services/auditoria.py`
    #     desde siempre y NO LA LLAMABA NADIE. O sea que armar un lote,
    #     cancelarlo y subirle comprobantes quedaban asentados, y mandar la
    #     plata —la única de las cuatro que saca dinero— no.
    await auditoria.registrar(
        db, "dinero.retiro_aprobado", quien=quien, request=request,
        objetivo_tipo="transaccion", objetivo_id=orden_id,
        objetivo_desc=f"{transaccion.get('display_id') or orden_id}: "
                      f"{para_mostrar(transaccion.get('amount_output'), 'VES')}",
        detalle={"display_id": transaccion.get("display_id"),
                 "banco_pagador": banco,
                 "user_id": transaccion.get("user_id")})

    return True
