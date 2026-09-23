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

    La tasa la cambia el super administrador cuando quiere, y antes también
    cambiaba sola de noche (la tasa automática, ya eliminada). O sea que un
    envío cotizado y pagado siete minutos después puede tener dos tasas
    distintas si se releyera. El cliente recibe los bolívares que le prometió
    la pantalla; la diferencia la absorbe la empresa, y está acotada a los
    siete minutos que dura el cobro PIX.

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

# El prefijo de la referencia de cobro de este corredor. Tenía el texto suelto
# dentro del filtro de `vencer_las_viejas` y dentro de `nuevo_id_de_cobro`;
# dos copias del mismo dato es una que un día se cambia sola.
PREFIJO_VENEZUELA = "venv_"

# El estado en el que nace la orden. El mismo nombre que usa el envío cripto
# con pago directo (`routes/transactions.create_crypto_withdrawal`, camino B),
# para que el panel y el historial no tengan que aprender un estado nuevo.
ESPERANDO_PAGO = "awaiting_payment"
PENDIENTE = "pending"
PAGO_VENCIDO = "payment_expired"

# EL ESTADO DEL MEDIO, Y POR QUE HACE FALTA UNO NUEVO.
#
#   El corredor Venezuela → Brasil se paga por transferencia en bolívares, y eso
#   no lo confirma ninguna pasarela: lo mira un administrador. Entre que el
#   cliente sube el comprobante y que alguien lo abre pueden pasar horas.
#
#   Sin un estado propio, esa orden quedaría o en «esperando pago» —y el
#   cliente vería «pagá», después de haber pagado— o en «pendiente», que en
#   este sistema significa «cobrada, lista para despachar», y nadie habría
#   comprobado nada todavía. Las dos mentiras son caras: la primera hace que
#   pague dos veces, la segunda despacha plata que quizá no entró.
REVISANDO = "awaiting_review"

# PAGO QUE LLEGO TARDE, Y QUE NADIE PUEDE DECIDIR SOLO.
#
#   Los siete minutos congelan la tasa. Si el pago entra después, el envío
#   saldría a un precio que ya no existe, y esa diferencia la paga la empresa.
#
#   Pero la plata YA SALIO de la cuenta del cliente. Devolverla sola puede
#   salir peor que despachar: hay comisiones de por medio y una persona que
#   cree que su familia va a cobrar. Así que la orden no avanza NI se devuelve:
#   queda apartada para que alguien la mire y decida. Decisión del dueño del
#   proyecto.
#
#   Es un estado terminal para la máquina y de entrada para una persona.
PAGO_TARDIO = "payment_late"

# El propósito del corredor inverso. El de Venezuela es `envio_ves`.
PROPOSITO_REAIS = "envio_brl"

# El prefijo de sus cobros, para distinguirlos de un vistazo en un registro.
PREFIJO_REAIS = "brl_"

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
    return f"{PREFIJO_VENEZUELA}{uuid.uuid4().hex[:12]}"


async def confirmar(db, pago: dict) -> bool:
    """El pago se aprobó: hacer avanzar la orden. Devuelve si avanzó.

    Se llama DESDE el webhook de Mercado Pago —y desde la ruta que cobra con
    tarjeta—, después de que ésos verificaron la firma, la frescura, el monto,
    y le volvieron a preguntar a Mercado Pago que el pago está aprobado. Acá no
    se repite ninguna de esas comprobaciones: se repiten mal.

    EL RECLAMO ES LO PRIMERO Y ES UNA SOLA ESCRITURA. Ver el encabezado.

    EL VENCIMIENTO ESTA EN EL FILTRO, Y ANTES NO ESTABA.

        El filtro pedía sólo el estado. Eso dejaba pasar un pago que entra
        después de los siete minutos: la orden seguía en «esperando pago»
        —porque nadie la vencía— y avanzaba a la cola con la tasa congelada
        hace horas. El envío salía a un precio que ya no existía y la
        diferencia la pagaba la empresa, sin que nada lo dijera.

        El código de acá abajo ya contemplaba ese caso: si la orden estaba en
        «vencida», anotaba un ERROR pidiendo mirarla a mano. Pero esa rama
        NUNCA SE ALCANZABA, porque `vencer_las_viejas` no corría en ningún
        lado y ninguna orden llegaba a estar «vencida».

        Ahora el vencimiento se mira acá, y no se depende de que el barrido
        haya llegado a tiempo: entre que el cobro muere y que el barrido pasa
        hay una ventana, y el pago puede entrar justo ahí.
    """
    referencia = pago.get("payment_id")
    ahora = datetime.now(timezone.utc)

    orden = await db.transactions.find_one_and_update(
        {"payment_order_id": referencia, "status": ESPERANDO_PAGO,
         "payment_expires_at": {"$gt": ahora}},
        {"$set": {"status": PENDIENTE, "paid_at": ahora}},
        return_document=True,
    )
    if not orden:
        return await _pago_que_no_avanzo(db, referencia, ahora)

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


async def _pago_que_no_avanzo(db, referencia, ahora) -> bool:
    """El pago entró y la orden no estaba lista para avanzar. ¿Por qué?

    Tres motivos posibles, y sólo uno de ellos es un problema:

      · Webhook repetido sobre una orden que ya avanzó. Normal, se ignora.
      · La orden no existe. Tampoco es de este flujo; se ignora.
      · LLEGO TARDE. La plata salió de la cuenta de alguien por un cobro que
        ya no valía. Eso no se decide solo.

    NO AVANZA NI DEVUELVE. Queda apartada en `PAGO_TARDIO` para que una
    persona mire y decida: despachar al precio viejo, o devolver. Es la
    decisión que tomó el dueño del proyecto, y el motivo está donde se declara
    ese estado.
    """
    existe = await db.transactions.find_one(
        {"payment_order_id": referencia},
        {"_id": 0, "status": 1, "transaction_id": 1, "display_id": 1,
         "user_id": 1, "payment_expires_at": 1, "bono_aplicado": 1})

    if not existe:
        logger.info("pago_al_final: %s no es una orden de este flujo",
                    referencia)
        return False

    if existe.get("status") == PENDIENTE:
        logger.info("pago_al_final: %s ya estaba confirmada", referencia)
        return False

    # Sólo queda tarde, si la orden todavía estaba esperando o ya se venció.
    if existe.get("status") not in (ESPERANDO_PAGO, PAGO_VENCIDO):
        logger.warning(
            "pago_al_final: llegó el pago de %s y la orden %s está en «%s». "
            "No se toca: hay que mirarla a mano.",
            referencia, existe.get("transaction_id"), existe.get("status"))
        return False

    # EL ESTADO DE PARTIDA VA EN EL FILTRO, igual que todo en este módulo: dos
    # webhooks del mismo pago no pueden apartar la orden dos veces ni avisar
    # dos veces al equipo.
    apartada = await db.transactions.find_one_and_update(
        {"transaction_id": existe.get("transaction_id"),
         "status": existe.get("status")},
        {"$set": {"status": PAGO_TARDIO, "late_payment_at": ahora,
                  "late_payment_ref": referencia}},
        return_document=True)
    if not apartada:
        logger.info("pago_al_final: %s ya estaba apartada", referencia)
        return False

    # SI EL BONO YA SE DEVOLVIO, QUIEN DECIDA TIENE QUE SABERLO.
    #
    #   `vencer_las_viejas` devuelve el bono al vencer la orden. Si el pago
    #   llega después de eso, el cliente tiene el bono de vuelta EN LA MANO y
    #   además pagó. Despachar sin descontarlo otra vez es regalarlo.
    bono_devuelto = (existe.get("status") == PAGO_VENCIDO
                     and float(existe.get("bono_aplicado") or 0) > 0)

    logger.error(
        "PAGO FUERA DE TIEMPO en el envío %s (%s): entró %s cuando el cobro "
        "ya había vencido%s. La orden quedó en «%s» y NO se despachó. Hay que "
        "decidir a mano: despachar a la tasa vieja, o devolver.%s",
        existe.get("display_id"), existe.get("transaction_id"), referencia,
        f" el {existe.get('payment_expires_at')}"
        if existe.get("payment_expires_at") else "",
        PAGO_TARDIO,
        f" OJO: el bono de {existe.get('bono_aplicado')} ya se le devolvió al "
        f"vencer, así que si se despacha hay que volver a descontarlo."
        if bono_devuelto else "")

    # Y que alguien se entere sin tener que mirar el registro.
    try:
        from services.notifications import avisar_al_personal
        await avisar_al_personal(
            title="Un pago entró fuera de tiempo",
            message=(f"El envío {existe.get('display_id')} se pagó después de "
                     f"que venciera el cobro. No se despachó: hay que decidir "
                     f"si sale a la tasa vieja o se devuelve."
                     + (" El bono ya se le devolvió al cliente."
                        if bono_devuelto else "")),
            notification_type="pago_tardio",
            solo_super_admin=True,
            data={"transaction_id": existe.get("transaction_id"),
                  "payment_order_id": referencia,
                  "bono_ya_devuelto": bono_devuelto})
    except Exception as e:                                    # pragma: no cover
        # La orden ya quedó apartada, que es lo que protege la plata. Que el
        # aviso no salga se anota y no se devuelve.
        logger.error("pago_al_final: no se pudo avisar del pago tardío de "
                     "%s: %s", referencia, e)
    return False


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
    # LOS DOS CORREDORES, y antes era uno solo.
    #
    #   El filtro pedía `^venv_`, o sea sólo los envíos a Venezuela. Las
    #   órdenes del corredor inverso —`brl_`, las que se pagan en bolívares—
    #   se quedaban en «esperando pago» para siempre aunque su cobro hubiera
    #   muerto: `recibir_comprobante` las rechaza por vencidas, pero nadie las
    #   movía de estado, así que el cliente veía «en curso» un pedido que ya
    #   no podía pagar.
    #
    #   Se agrega el prefijo del otro corredor en vez de sacar la condición.
    #   El motivo de que el prefijo exista sigue en pie y está abajo: ata la
    #   limpieza a los flujos que esta función sabe vencer, y deja afuera el
    #   camino cripto, que también usa «awaiting_payment».
    filtro = {"status": ESPERANDO_PAGO, "payment_expires_at": {"$lt": ahora},
              "payment_order_id": {"$regex": f"^({PREFIJO_VENEZUELA}|{PREFIJO_REAIS})"}}

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



# ══════════════════════════════════════════════════════════════════════════
# El barrido, que es lo que hace que «vencida» signifique algo
# ══════════════════════════════════════════════════════════════════════════
#
# POR QUE ESTO EXISTE, Y QUE PASABA SIN ESTO
#
#   `vencer_las_viejas` estaba escrita, probada y COMPLETA. Lo único que le
#   faltaba era que alguien la llamara: sólo la llamaban los tests.
#
#   Tres cosas pasaban por eso, todas en producción:
#
#     1. Una orden que nadie pagó se quedaba en «esperando pago» PARA SIEMPRE.
#        El cliente veía «en curso» un pedido que ya no podía pagar.
#     2. El bono descontado al cotizar NUNCA VOLVIA. Es plata de alguien.
#     3. Y la cara: un pago que entraba tarde avanzaba igual, porque la orden
#        nunca llegaba a estar «vencida». El envío salía a la tasa congelada
#        hacía horas.
#
#   El tercero ya no depende de esto —`confirmar` mira la fecha por su
#   cuenta—, pero los dos primeros sí.
#
# CADA CUANTO, Y POR QUE ESE NUMERO
#
#   El cobro dura siete minutos. Un minuto de barrido significa que, en el
#   peor caso, el cliente ve «en curso» sesenta segundos de más. Bajarlo no
#   compra nada; subirlo empieza a notarse en la pantalla.
#
#   Es barato: una consulta sobre estado y fecha, y en el caso normal no
#   devuelve nada.

import asyncio                                               # noqa: E402

CADA_CUANTO_SE_BARRE = 60

_tarea = None


async def _bucle(db):
    while True:
        await asyncio.sleep(CADA_CUANTO_SE_BARRE)
        try:
            cuantas = await vencer_las_viejas(db)
            if cuantas:
                logger.info("pago_al_final: vencieron %d órdenes", cuantas)
        except Exception as e:                                # pragma: no cover
            # NO SE CORTA EL BUCLE. Un error de base en una vuelta no puede
            # dejar la aplicación sin barrido hasta el próximo despliegue: eso
            # es exactamente el estado del que este bloque saca al sistema.
            logger.error("pago_al_final: falló el barrido: %s", e)


def arrancar(db) -> None:
    """Deja corriendo el barrido. Se llama una vez, al arrancar."""
    global _tarea
    if _tarea is not None and not _tarea.done():
        return
    _tarea = asyncio.create_task(_bucle(db))


async def parar() -> None:
    """Corta el barrido. Para el apagado."""
    global _tarea
    if _tarea is not None:
        _tarea.cancel()
        try:
            await _tarea
        except (asyncio.CancelledError, Exception):
            pass
        _tarea = None


# Lo que no se puede. La segunda mitad —qué SI se puede— la pone
# `services/la_via_que_funciona.py`, que la calcula mirando la configuración.
# Acá terminaba en «podés recargar tu saldo y enviar desde ahí», y quedó
# mintiendo el día que la carga de saldo se pudo cerrar.
SIN_PAGO_AL_FINAL = "Esta forma de pagar no está disponible por ahora."


async def exigir_activo(db) -> None:
    """Frena la ruta si el flujo nuevo está apagado.

    503 y no 404: la ruta existe, lo que no está disponible es el servicio.
    Un 404 le haría pensar a un integrador que se equivocó de dirección.

    RECIBE LA BASE Y NO UN BOOLEANO, que es como era antes.

        El mensaje tiene que nombrar la vía que SI funciona, y eso depende de
        la configuración: sin la base no se puede saber, y por eso la versión
        anterior tenía la frase escrita fija — la frase que terminó mintiendo.
    """
    if not await esta_activo(db):
        from services import la_via_que_funciona
        raise HTTPException(
            status_code=503,
            detail=await la_via_que_funciona.con(db, SIN_PAGO_AL_FINAL))


# ══════════════════════════════════════════════════════════════════════════
# El corredor inverso: se paga en bolívares y se liquida en reais
# ══════════════════════════════════════════════════════════════════════════
#
# MISMO FLUJO, OTRA FORMA DE CONFIRMAR
#
#   El cliente cotiza, elige beneficiario en Brasil, transfiere en bolívares y
#   sube el comprobante. Un administrador lo verifica y recién ahí la orden
#   entra en la cola de despacho, para pagarse por PIX en reais.
#
#   Lo que NO cambia respecto del corredor de Venezuela, y es lo importante:
#   no hay saldo en el medio, así que cada paso sigue siendo UN cambio de
#   estado sobre UN documento, reclamado con el estado dentro del filtro.
#
# LOS SIETE MINUTOS SON PARA PAGAR, NO PARA CONFIRMAR
#
#   Decisión del dueño del proyecto, y hay que entenderla bien porque es la
#   diferencia con el corredor de Venezuela.
#
#   La cotización vence a los siete minutos: pasado ese rato, el cliente ya no
#   puede subir el comprobante contra esa tasa. Pero si lo sube a tiempo, la
#   tasa que vio se le respeta AUNQUE EL ADMINISTRADOR LO VERIFIQUE HORAS
#   DESPUES.
#
#   La exposición de la empresa, entonces, no dura siete minutos: dura hasta
#   que alguien mire el comprobante. Está escrito acá para que quien lea este
#   código sepa que el número depende de la rapidez de la mesa, no del reloj
#   del cobro.


def nuevo_id_de_cobro_reais() -> str:
    return f"{PREFIJO_REAIS}{uuid.uuid4().hex[:12]}"


async def recibir_comprobante(db, transaction_id: str, user_id: str,
                              comprobante: str, banco_id: str,
                              banco_nombre: str) -> dict:
    """El cliente dice que pagó y sube el comprobante. Devuelve la orden.

    EL RECLAMO ES CON EL ESTADO DENTRO DEL FILTRO, como todo en este módulo:
    dos envíos del mismo comprobante no pueden pasar los dos. El segundo
    encuentra la orden fuera de «esperando pago» y se va con un 409.

    NO SE ACREDITA NADA. Esto sólo dice «hay algo para mirar». Quien decide si
    esa plata entró es la persona que abre el comprobante.
    """
    ahora = datetime.now(timezone.utc)
    orden = await db.transactions.find_one_and_update(
        {"transaction_id": transaction_id, "user_id": user_id,
         "status": ESPERANDO_PAGO,
         "payment_expires_at": {"$gt": ahora}},
        {"$set": {"status": REVISANDO,
                  "proof_image": comprobante,
                  "destination_bank_id": banco_id,
                  "destination_bank": banco_nombre,
                  "proof_sent_at": ahora}},
        return_document=True,
    )
    if not orden:
        # Se distingue el motivo: vencida y ya enviada no son lo mismo para
        # quien está del otro lado.
        actual = await db.transactions.find_one(
            {"transaction_id": transaction_id, "user_id": user_id},
            {"_id": 0, "status": 1, "payment_expires_at": 1})
        if not actual:
            raise HTTPException(status_code=404, detail="Ese envío no existe.")
        if actual.get("status") == REVISANDO:
            raise HTTPException(
                status_code=409,
                detail="Ya recibimos tu comprobante. Lo estamos revisando.")
        if actual.get("status") == ESPERANDO_PAGO:
            raise HTTPException(
                status_code=409,
                detail="La cotización venció. Volvé a cotizar para ver la tasa "
                       "de ahora; si ya transferiste, escribinos y lo "
                       "resolvemos a mano.")
        raise HTTPException(
            status_code=409,
            detail="Ese envío ya no está esperando el pago.")
    return orden


async def verificar_el_pago(db, transaction_id: str, admin_id: str) -> dict:
    """El administrador confirma que la plata entró. La orden pasa a la cola.

    Devuelve la orden, o levanta si ya no estaba para revisar. El reclamo va
    con `REVISANDO` en el filtro para que dos operadores mirando la misma
    pantalla no la aprueben dos veces.
    """
    ahora = datetime.now(timezone.utc)
    orden = await db.transactions.find_one_and_update(
        {"transaction_id": transaction_id, "status": REVISANDO},
        {"$set": {"status": PENDIENTE, "paid_at": ahora,
                  "verificado_por": admin_id, "verificado_en": ahora}},
        return_document=True,
    )
    if not orden:
        raise HTTPException(
            status_code=409,
            detail="Esa orden ya no está esperando verificación. Actualizá la "
                   "pantalla para ver cómo quedó.")
    return orden


async def rechazar_el_comprobante(db, transaction_id: str, admin_id: str,
                                  motivo: str) -> dict:
    """El comprobante no sirve: la orden vuelve a esperar el pago.

    POR QUE VUELVE A «ESPERANDO PAGO» Y NO A UN ESTADO DE RECHAZO

        Porque no hay nada que devolver: en este flujo el cliente no tiene
        saldo comprometido, y si su comprobante no servía, lo que necesita es
        poder subir el bueno. Un estado terminal lo obligaría a cotizar de
        nuevo, con otra tasa, por un error de foto.

        La cotización sigue siendo la misma y su vencimiento también: si ya
        pasó, va a tener que cotizar de nuevo igual, y eso es correcto.
    """
    ahora = datetime.now(timezone.utc)
    orden = await db.transactions.find_one_and_update(
        {"transaction_id": transaction_id, "status": REVISANDO},
        {"$set": {"status": ESPERANDO_PAGO, "proof_image": None,
                  "rechazado_por": admin_id, "rechazado_en": ahora,
                  "motivo_del_rechazo": (motivo or "").strip()[:500]}},
        return_document=True,
    )
    if not orden:
        raise HTTPException(
            status_code=409,
            detail="Esa orden ya no está esperando verificación.")
    return orden
