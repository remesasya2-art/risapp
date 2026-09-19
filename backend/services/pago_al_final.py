"""
Pagar al final: el cliente cotiza, elige beneficiario, y RECIEN AHI paga.

EL FLUJO VIEJO Y EL NUEVO, EN DOS LINEAS

    Viejo   el cliente recarga saldo → después gasta ese saldo en un envío.
    Nuevo   el cliente cotiza el envío → paga ese envío con PIX. Sin saldo
            en el medio.

POR QUE EL NUEVO ES MAS SEGURO, Y NO SOLO MAS CORTO

    Es el motivo principal de este archivo, y conviene que quede escrito.

    En el flujo viejo, la plata cruza DOS documentos en DOS momentos:

        el PIX se confirma  →  el pago pasa a «pagado» Y el saldo sube
        el cliente envía    →  el saldo baja Y nace la orden

    `routes/gestor_pix.process_pix_confirmation` reclama el pago de forma
    atómica y recién después acredita. Entre esas dos líneas hay una ventana:
    si el proceso se muere ahí, el pago queda cobrado y el saldo sin acreditar.
    Cerrarla de verdad pide transacciones de varios documentos, y este
    despliegue puede no tenerlas —`services/accounting_engine.py` detecta si
    Mongo es un conjunto de réplicas y, si no lo es, sigue sin transacciones—.

    Acá no hay saldo en el medio, así que la confirmación es UN cambio de
    estado sobre UN documento:

        find_one_and_update({payment_order_id: X, status: "awaiting_payment"},
                            {$set: {status: "pending"}})

    Una sola operación atómica. No hay ventana que cerrar, y no depende de que
    Mongo sea un conjunto de réplicas. Sacar el saldo del medio no simplifica
    nada más que eso: elimina el problema.

EL ORDEN DE LA CONFIRMACION ES AL REVES QUE EN LA RECARGA, Y ES A PROPOSITO

    La recarga reclama el PAGO y después mueve la plata. Acá se reclama la
    ORDEN y después se anota el pago.

    Si el proceso se muere en el medio:

      · Con este orden: la orden ya está en «pendiente» —el cliente va a
        cobrar— y el documento del pago quedó sin marcar. Un webhook posterior
        vuelve a intentar, encuentra la orden fuera de «awaiting_payment», el
        reclamo devuelve None y no pasa nada dos veces.
      · Con el orden inverso: el pago figura cobrado y la orden nunca avanza.
        El cliente pagó y no existe el envío.

    La idempotencia vive en el estado de la orden, no en el del pago. El
    documento del pago es contabilidad, no candado.

LA TASA SE CONGELA AL COTIZAR

    Decisión del dueño del proyecto. Se guarda en la orden al crearla y se
    respeta al confirmarse, aunque para entonces la tasa haya cambiado.

    Y cambia sola: `services/rate_engine.apply_rate_adjustment` le resta un
    delta fuera del horario laboral. O sea que un envío cotizado a las 21:58 y
    pagado a las 22:01 tiene dos tasas distintas si se releyera. El cliente
    recibe los bolívares que le prometió la pantalla; la diferencia la absorbe
    la empresa, y está acotada a los siete minutos que dura el cobro PIX.

EL BONO DESCUENTA DEL PIX

    El bono de bienvenida es saldo, y acá no hay saldo que gastar. Así que se
    convierte en un descuento: con R$ 15 de bono, el QR cobra R$ 15 menos y el
    beneficiario recibe los mismos bolívares.

    Se asienta como salida de `balance_ris_bono`, nunca de `balance_ris`. Un
    asiento contra la cuenta equivocada haría que el libro mayor no cuadre
    contra los saldos, y el chequeo de integridad lo denunciaría con razón.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLAVE = "pago_al_final"

# La marca que llevan los cobros PIX de este flujo, en `gestor_pix_payments`.
# El webhook de Mercado Pago la mira para saber si tiene que acreditar saldo
# —la recarga de siempre— o hacer avanzar una orden.
#
# Es un campo del documento y no una colección aparte a propósito: el webhook
# ya busca el pago por `mp_payment_id` en esa colección, con su firma, su
# ventana de frescura y su reverificación contra la API de Mercado Pago. Un
# receptor nuevo tendría que repetir todo eso, y la segunda copia es la que
# sale mal.
PROPOSITO = "envio_ves"

# El estado en el que nace la orden. El mismo nombre que usa el envío cripto
# con pago directo (`routes/transactions.create_crypto_withdrawal`, camino B),
# para que el panel y el historial no tengan que aprender un estado nuevo.
ESPERANDO_PAGO = "awaiting_payment"
PENDIENTE = "pending"
PAGO_VENCIDO = "payment_expired"

# Cuánto dura el cobro. Es el mismo número que `routes/gestor_pix.py` le pone
# al PIX de la recarga: si la orden durara más que el QR, quedaría esperando un
# pago que ya no se puede hacer.
MINUTOS_DEL_COBRO = 7


async def esta_activo(db) -> bool:
    """¿El cliente ve el flujo nuevo?

    De fábrica NO. El flujo viejo sigue siendo el que ve todo el mundo hasta
    que se prenda desde el panel: un cambio en el camino del dinero no se
    estrena solo el día que se despliega.
    """
    from services import configuracion
    try:
        return int(await configuracion.leer(db, CLAVE)) == 1
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo leer %s, se asume apagado: %s", CLAVE, e)
        return False


def vence_en(ahora: datetime = None) -> datetime:
    return (ahora or datetime.now(timezone.utc)) + timedelta(minutes=MINUTOS_DEL_COBRO)


def nuevo_id_de_cobro() -> str:
    """El identificador que viaja a Mercado Pago como `external_reference` y
    que queda en la orden como `payment_order_id`. Prefijo propio para que se
    distinga de un `gpix_` de recarga con sólo mirarlo en un registro."""
    return f"venv_{uuid.uuid4().hex[:12]}"


async def confirmar(db, pago: dict) -> bool:
    """El pago se aprobó: hacer avanzar la orden. Devuelve si avanzó.

    Se llama DESDE el webhook de Mercado Pago, después de que éste verificó la
    firma, la frescura, el monto, y le volvió a preguntar a Mercado Pago que el
    pago está aprobado. Acá no se repite ninguna de esas comprobaciones: se
    repiten mal.

    EL RECLAMO ES LO PRIMERO Y ES UNA SOLA ESCRITURA. Ver el encabezado.
    """
    referencia = pago.get("payment_id")
    ahora = datetime.now(timezone.utc)

    orden = await db.transactions.find_one_and_update(
        {"payment_order_id": referencia, "status": ESPERANDO_PAGO},
        {"$set": {"status": PENDIENTE, "paid_at": ahora}},
        return_document=True,
    )
    if not orden:
        # No es un error: es un webhook repetido, o una orden que ya venció y
        # alguien pagó igual. Lo segundo hay que mirarlo, así que se anota con
        # el nivel que corresponde y no se traga.
        existe = await db.transactions.find_one(
            {"payment_order_id": referencia}, {"_id": 0, "status": 1,
                                               "transaction_id": 1})
        if existe and existe.get("status") != PENDIENTE:
            logger.error(
                "pago_al_final: llegó el pago de %s y la orden está en «%s». "
                "Si es «%s», alguien pagó un cobro vencido y hay que "
                "devolverle la plata o despacharle el envío a mano.",
                referencia, existe.get("status"), PAGO_VENCIDO)
        else:
            logger.info("pago_al_final: %s ya estaba confirmada", referencia)
        return False

    # Recién ahora el documento del pago, que es contabilidad y no candado.
    # Si esto falla, la orden ya avanzó y el cliente va a cobrar; queda un
    # ERROR para conciliar a mano, que es el lado barato de equivocarse.
    try:
        await db.gestor_pix_payments.update_one(
            {"payment_id": referencia},
            {"$set": {"status": "paid", "paid_at": ahora,
                      "transaction_id": orden.get("transaction_id")}})
    except Exception as e:                                    # pragma: no cover
        logger.error("pago_al_final: la orden %s avanzó pero el pago %s no se "
                     "pudo marcar: %s", orden.get("transaction_id"),
                     referencia, e)

    logger.info("pago_al_final: orden %s pagada y en cola",
                orden.get("transaction_id"))
    return True


async def vencer_las_viejas(db, ahora: datetime = None) -> int:
    """Marca como vencidas las órdenes que esperan un pago que ya no se puede
    hacer. Devuelve cuántas.

    POR QUE HACE FALTA

        El cobro PIX muere a los siete minutos. Sin esto, cada cotización que
        nadie paga queda para siempre en «esperando pago»: le ensucia el
        historial al cliente, le ensucia el panel al operador, y hace que
        «cuántos envíos hay en curso» deje de significar nada.

        No mueve plata: estas órdenes nunca cobraron. Por eso puede correr
        cuando sea y cuantas veces sea.

    POR QUE EL FILTRO PIDE EL PREFIJO `venv_` ADEMAS DE LA FECHA

        Hoy es redundante, y eso se descubrió rompiéndolo: sacarlo no puso
        ningún test en rojo. El envío cripto con pago directo también deja
        órdenes en «awaiting_payment», pero NO les pone `payment_expires_at`,
        así que la condición de fecha ya las dejaba afuera.

        Se conserva igual, y con un test que lo ejerce de verdad. El motivo es
        que `payment_expires_at` es un nombre genérico: el día que alguien se
        lo agregue al camino cripto —para mostrarle al cliente cuánto le queda,
        por ejemplo— esta función empezaría a vencer órdenes cripto vivas sin
        que nada avise. El prefijo ata la limpieza a las órdenes de ESTE flujo,
        que es lo único que esta función sabe vencer.

        Una guarda redundante y no probada es la que el repositorio prohíbe.
        Una guarda redundante, documentada y con un test que la ejerce es un
        seguro contra un cambio futuro, y eso es otra cosa.
    """
    from services import bonos
    from services.money import to_decimal, to_decimal128

    ahora = ahora or datetime.now(timezone.utc)
    filtro = {"status": ESPERANDO_PAGO, "payment_expires_at": {"$lt": ahora},
              "payment_order_id": {"$regex": "^venv_"}}

    # DE A UNA, Y NO CON UN `update_many`, POR EL BONO.
    #
    #   La primera versión vencía todas de un saque. Pero el bono se debita al
    #   cotizar —ver `routes/transactions.cotizar_envio_ves`, y el motivo está
    #   ahí—, así que una orden que nadie pagó se llevó plata de la cuenta del
    #   bono que hay que devolver. Un `update_many` no deja devolver nada.
    #
    #   El vencimiento se reclama con el estado DENTRO del filtro, igual que la
    #   confirmación. Así dos limpiezas simultáneas no devuelven el bono dos
    #   veces: la segunda no encuentra la orden en «esperando pago».
    vencidas = 0
    async for orden in db.transactions.find(filtro, {"_id": 0,
                                                     "transaction_id": 1,
                                                     "user_id": 1,
                                                     "bono_aplicado": 1}):
        reclamada = await db.transactions.find_one_and_update(
            {"transaction_id": orden["transaction_id"], "status": ESPERANDO_PAGO},
            {"$set": {"status": PAGO_VENCIDO, "expired_at": ahora}})
        if not reclamada:
            continue
        vencidas += 1

        bono = to_decimal(orden.get("bono_aplicado") or 0)
        if bono > 0:
            try:
                await db.users.update_one(
                    {"user_id": orden["user_id"]},
                    {"$inc": {bonos.CUENTA_DEL_BONO: to_decimal128(bono)}})
            except Exception as e:                            # pragma: no cover
                # La orden ya quedó vencida. Que el bono no vuelva es plata de
                # alguien que se quedó sin devolver, así que va como ERROR con
                # todo lo que hace falta para devolverlo a mano.
                logger.error(
                    "pago_al_final: no se le pudo devolver el bono de %s a %s "
                    "al vencer %s: %s", bono, orden["user_id"],
                    orden["transaction_id"], e)
    return vencidas


def exigir_activo(activo: bool) -> None:
    """Frena la ruta si el flujo nuevo está apagado.

    503 y no 404: la ruta existe, lo que no está disponible es el servicio.
    Un 404 le haría pensar a un integrador que se equivocó de dirección.
    """
    if not activo:
        raise HTTPException(
            status_code=503,
            detail="Esta forma de pagar no está disponible por ahora. "
                   "Podés recargar tu saldo y enviar desde ahí.")
