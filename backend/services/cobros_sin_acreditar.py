"""
services/cobros_sin_acreditar.py — Plata que el cliente pagó y la app no le dio.

POR QUE ESTE MODULO EXISTE

    Un pago de Mercado Pago se acredita por DOS caminos, y ninguno de los dos
    es seguro solo:

      · El aviso del servidor de Mercado Pago (`POST /api/webhook/mercadopago`).
        Si ese aviso no llega —porque el cortafuegos del borde lo bloqueó,
        porque la app estaba caída ese minuto, porque Mercado Pago lo reintentó
        cuatro veces y se rindió— no pasa nada. Nadie se entera.

      · La pantalla del cliente, que mientras espera pregunta cada pocos
        segundos si el pago ya entró (`GET /gestor/pix/status/...`). Ese camino
        tapó el agujero durante mucho tiempo, y por eso el agujero no se vio:
        el cliente que se queda mirando la pantalla cobra igual.

    Quien PAGA Y CIERRA LA PANTALLA —o paga después de que el código QR venció,
    que en PIX se puede— cae en el medio de los dos. Su plata salió de su
    cuenta, Mercado Pago la tiene, y en la app no aparece. Nadie reclama lo que
    no sabe que perdió, así que el defecto es silencioso por diseño.

    No había ninguna pantalla, ninguna consulta y ningún aviso que pudiera
    responder «¿hay alguien esperando plata que ya pagó?». Este módulo responde
    esa pregunta y NADA MAS: no acredita, no corrige, no toca un saldo. Mover
    plata es una decisión de una persona, y va en otro camino con su registro
    en el libro de auditoría.

QUIEN DECIDE SI UN COBRO SE ACREDITO: EL LIBRO, NO EL ESTADO LOCAL

    La tentación es mirar `gestor_pix_payments.status` o `card_payments.status`.
    Es justamente el campo del que se desconfía: si el aviso no llegó, ese
    campo quedó viejo — es el síntoma, no el juez.

    El juez es el LIBRO MAYOR (`ledger`). Acreditar saldo y asentar la línea
    del libro salen de la misma operación de `services/saldos.mover`, y el
    libro es append-only y no caduca. Si existe una línea que apunta al pago,
    la plata entró; si no existe, no entró.

    Se descartó la otra prueba posible —la marca de `processed_webhooks`—
    porque esa colección tiene un TTL de 180 días: pasado ese plazo la marca se
    borra sola y un cobro bien acreditado empezaría a figurar como perdido. Una
    consulta que después de medio año llena la pantalla de falsos positivos es
    una consulta que nadie vuelve a mirar.

POR QUE HAY QUE PREGUNTARLE A MERCADO PAGO, UNO POR UNO

    Que falte la línea del libro no significa que haya plata: la mayoría de los
    códigos QR que se generan no se pagan nunca, y la mayoría de las tarjetas
    rechazadas tampoco. El único que sabe si el dinero salió de la cuenta del
    cliente es Mercado Pago. Así que la falta de línea es el FILTRO —gratis,
    contra la base— y la consulta a Mercado Pago es la CONFIRMACION.

    Esa consulta sale por la red y cuesta. De ahí los dos límites: una ventana
    de días y un tope de consultas. Cuando el tope se alcanza, el resultado
    dice cuántos quedaron sin mirar: un recorte silencioso se lee igual que
    «no hay nada», y son cosas opuestas.

DOS RESPUESTAS DISTINTAS, EN DOS LISTAS

    De los pagos que Mercado Pago da por aprobados y el libro no registra,
    algunos la app tampoco los da por cobrados —ahí hay alguien esperando su
    plata— y otros sí —ahí el cliente ya tiene su saldo y lo que falta es el
    asiento—. Se arreglan distinto: uno se acredita, el otro se asienta. Van
    separados, con su propio total, en `cobros` y en `descuadres`.

NO PODER PREGUNTAR NO ES ESTAR BIEN

    `MercadoPagoService.get_payment_status` devuelve `None` tanto si el pago no
    existe como si la consulta falló, y además se traga la excepción. Si acá se
    contara ese `None` como «no se pagó», una credencial vencida se vería en la
    pantalla como una fila de ceros tranquilizadora.

    Así que se cuentan aparte: `sin_respuesta` son los pagos que no se pudieron
    consultar, y `pudo_preguntar` dice si Mercado Pago está configurado. Un
    informe que no sabe tiene que decir que no sabe.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.money import ZERO, from_db, quantize_money

logger = logging.getLogger(__name__)

# La ventana por defecto. Treinta días cubren de sobra el plazo en el que un
# cliente todavía se acuerda de su pago y reclama, y mantiene la consulta corta.
DIAS_POR_DEFECTO = 30
DIAS_MAXIMO = 365

# Cuántas consultas a Mercado Pago como máximo. Con `EN_PARALELO` de a ocho,
# doscientas consultas tardan unos segundos; mil, cerca de un minuto. El techo
# está para que esta ruta no pueda colgar el panel ni castigar a Mercado Pago.
TOPE_POR_DEFECTO = 200
TOPE_MAXIMO = 1000
EN_PARALELO = 8

# Lo único que Mercado Pago llama «pagado». Cualquier otra palabra —`pending`,
# `in_process`, `rejected`, `refunded`, `charged_back`— no es plata acreditable,
# y una devolución tampoco se le debe al cliente.
APROBADO = "approved"

# Con qué palabra cuenta la app que ese pago ya se acreditó. `paid` es la del
# PIX y `approved` la de la tarjeta: son las dos que el código pone después de
# acreditar, y sirven para separar «falta la plata» de «falta el asiento».
LA_APP_LO_DA_POR_COBRADO = ("paid", "approved")

# De dónde sale cada candidato. Por cada colección: cómo se llama en el libro
# la referencia que la línea deja al acreditar, y con qué campo se le pregunta
# a Mercado Pago.
#
# En PIX los dos identificadores son distintos y eso importa: el libro apunta
# al id INTERNO (`gpix_...`) y Mercado Pago sólo conoce el suyo. Confundirlos
# daba una consulta que nunca encuentra nada y un informe siempre vacío.
ORIGENES = (
    {
        "coleccion": "gestor_pix_payments",
        "referencia": "pix_payment",
        "medio": "PIX",
        "campo_en_mercadopago": "mp_payment_id",
        "campo_de_la_cuenta": "gestor_id",
        "proyeccion": {
            "_id": 0, "payment_id": 1, "mp_payment_id": 1, "client_name": 1,
            "amount_ris": 1, "amount_brl": 1, "status": 1, "created_at": 1,
            "gestor_id": 1, "gestor_name": 1,
        },
    },
    {
        "coleccion": "card_payments",
        "referencia": "card_payment",
        "medio": "Tarjeta",
        "campo_en_mercadopago": "payment_id",
        "campo_de_la_cuenta": "user_id",
        "proyeccion": {
            "_id": 0, "payment_id": 1, "user_id": 1, "amount_ris": 1,
            "total_charged_brl": 1, "status": 1, "status_detail": 1,
            "created_at": 1,
        },
    },
)


def _acotar(valor, *, defecto, minimo, maximo):
    """Un número dentro de su rango, sin confiar en quien llama.

    Los dos límites de esta consulta son la única cosa que impide que una
    llamada pida un año entero y mil consultas a Mercado Pago. Acotar en la
    ruta y confiar acá dejaba el tope a un `?dias=99999` de distancia.
    """
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, valor))


async def _ya_esta_en_el_libro(db, referencias) -> set:
    """Los pagos que YA tienen línea en el libro mayor, como (clase, id).

    QUIEN DECIDE ES LO QUE DICE LA LINEA, NO LO QUE PEDIA LA CONSULTA

        La clase y el identificador salen del documento del libro —de
        `linea["reference"]`— y no de las variables con las que se armó el
        filtro. Es a propósito, y no es lo mismo:

          · Un identificador se puede repetir entre medios sin ser el mismo
            pago: el de la tarjeta lo pone Mercado Pago y el del PIX lo pone
            esta app. Dar por cobrado un PIX porque existe una línea de tarjeta
            con ese número es acreditarle a alguien la plata de otro.
          · Y armar la respuesta con lo que se PIDIO en vez de con lo que
            VOLVIO hace que la corrección dependa del filtro. Un filtro es una
            cosa que alguien afloja para que la consulta sea más rápida, y el
            día que lo aflojen la respuesta tiene que seguir siendo cierta.

        Así, el filtro de acá abajo no decide nada: sólo ACOTA cuánto libro se
        lee. El índice `(reference.kind, reference.id)` lo hace barato, y sin el
        `$in` esto traería el libro entero a la memoria para contestar lo mismo.
    """
    encontrados = set()
    for clase, ids in referencias.items():
        if not ids:
            continue
        cursor = db.ledger.find(
            {"reference.kind": clase, "reference.id": {"$in": sorted(ids)}},
            {"_id": 0, "reference": 1},
        )
        async for linea in cursor:
            referencia = linea.get("reference") or {}
            encontrados.add((referencia.get("kind"), referencia.get("id")))
    return encontrados


async def _preguntarle_a_mercadopago(id_de_pago):
    """Qué dice Mercado Pago de un pago. `None` si no se pudo preguntar.

    `get_payment_status` es SINCRONICA y sale por la red. Llamarla derecho
    desde código asíncrono frena el bucle de eventos entero: mientras espera,
    ninguna otra petición de la app avanza. Con doscientas consultas seguidas
    eso es el servidor parado durante un minuto, así que va a un hilo.
    """
    try:
        from mercadopago_service import mercadopago_service
    except ImportError:                                     # pragma: no cover
        return None
    if mercadopago_service is None or mercadopago_service.sdk is None:
        return None
    return await asyncio.to_thread(mercadopago_service.get_payment_status, id_de_pago)


def _mercadopago_esta_configurado() -> bool:
    try:
        from mercadopago_service import mercadopago_service
    except ImportError:                                     # pragma: no cover
        return False
    return mercadopago_service is not None and mercadopago_service.sdk is not None


def _texto(monto) -> str:
    """Un monto como lo manda la API: «4500.00», punto decimal y sin separadores.

    En el borde de la API el dinero va en texto para que no lo toque un `float`
    en el camino, pero en el texto CANONICO, no en el de la pantalla: quien lo
    recibe tiene que poder volver a convertirlo en número, y el formato de la
    gente —«4.500,00»— no se puede. Ponerlo bonito es tarea del navegador.
    """
    return str(quantize_money(monto))


def _con_zona(valor):
    """Una fecha que se puede comparar y ordenar, o `None`.

    El cliente de Mongo de esta app no es `tz_aware`, así que lo que vuelve de
    la base son fechas SIN zona aunque se hayan guardado con ella. Mezclar una
    de ésas con una fecha con zona —la del principio de la ventana, por ejemplo—
    no da un resultado raro: levanta `TypeError` y tira la consulta abajo. Es la
    misma normalización que hacen una docena de módulos acá, por el mismo motivo.
    """
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def _cuando(valor):
    """Una fecha en texto, o `None`.

    Siempre CON la zona puesta. Sin ella, `new Date(...)` en el navegador la lee
    como hora local y la fila muestra un horario que nunca existió — desplazado
    justo lo que el navegador esté de UTC.
    """
    con_zona = _con_zona(valor)
    return con_zona.isoformat() if con_zona else None


async def _candidatos(db, desde):
    """Los pagos de la ventana que NO tienen línea en el libro.

    Ordenados del más viejo al más nuevo: si el tope recorta, lo que queda sin
    mirar es lo más reciente, que la próxima revisión con una ventana más corta
    alcanza igual. Al revés, lo viejo no se alcanzaría nunca — y un cobro sin
    acreditar sólo empeora con el tiempo, porque es alguien esperando.
    """
    crudos = []
    referencias = {}
    for origen in ORIGENES:
        filtro = {"created_at": {"$gte": desde},
                  origen["campo_en_mercadopago"]: {"$nin": [None, ""]}}
        cursor = db[origen["coleccion"]].find(filtro, origen["proyeccion"])
        async for doc in cursor:
            if not doc.get("payment_id"):
                continue
            crudos.append((origen, doc))
            referencias.setdefault(origen["referencia"], set()).add(doc["payment_id"])

    acreditados = await _ya_esta_en_el_libro(db, referencias)
    sin_linea = [(o, d) for o, d in crudos
                 if (o["referencia"], d["payment_id"]) not in acreditados]
    sin_linea.sort(key=lambda par: _con_zona(par[1].get("created_at")) or desde)
    return sin_linea


def _monto_local(origen, doc):
    """Lo que la app creía que costaba este pago, en reales."""
    if origen["referencia"] == "card_payment":
        crudo = doc.get("total_charged_brl")
        if crudo is None:
            crudo = doc.get("amount_ris")
    else:
        crudo = doc.get("amount_brl")
        if crudo is None:
            crudo = doc.get("amount_ris")
    try:
        return from_db(crudo)
    except Exception:
        return ZERO


async def revisar(db, *, dias=DIAS_POR_DEFECTO, tope=TOPE_POR_DEFECTO,
                  preguntar=None) -> dict:
    """Qué cobros de Mercado Pago están pagados y sin acreditar. SOLO LEE.

    `preguntar` es la costura por la que los tests ponen su propio Mercado Pago:
    una función asíncrona que recibe un identificador de pago y devuelve lo
    mismo que `get_payment_status`, o `None` si no se pudo preguntar.
    """
    dias = _acotar(dias, defecto=DIAS_POR_DEFECTO, minimo=1, maximo=DIAS_MAXIMO)
    tope = _acotar(tope, defecto=TOPE_POR_DEFECTO, minimo=1, maximo=TOPE_MAXIMO)
    preguntar = preguntar or _preguntarle_a_mercadopago

    hasta = datetime.now(timezone.utc)
    desde = hasta - timedelta(days=dias)

    candidatos = await _candidatos(db, desde)
    a_mirar = candidatos[:tope]

    cobros = []
    total = ZERO
    descuadres = []
    total_descuadres = ZERO
    sin_respuesta = 0
    puerta = asyncio.Semaphore(EN_PARALELO)

    async def _uno(origen, doc):
        id_en_mercadopago = doc.get(origen["campo_en_mercadopago"])
        async with puerta:
            try:
                respuesta = await preguntar(id_en_mercadopago)
            except Exception as e:
                # Una consulta que falla no puede tumbar el informe entero: el
                # resto de los pagos se mira igual y éste queda contado como
                # «no se pudo preguntar», que es la verdad.
                logger.warning(
                    "cobros sin acreditar: no se pudo consultar el pago %s en "
                    "Mercado Pago: %s", id_en_mercadopago, e)
                respuesta = None
        return origen, doc, respuesta

    for tanda in await asyncio.gather(*[_uno(o, d) for o, d in a_mirar]):
        origen, doc, respuesta = tanda
        estado = (respuesta or {}).get("status")
        if not estado:
            sin_respuesta += 1
            continue
        if estado != APROBADO:
            continue
        # El total se suma acá, en Decimal, y NO recorriendo después la lista de
        # cobros: los montos de la lista son texto para la pantalla, y volver a
        # leerlos para sumarlos es pedirle a un formato de presentación que
        # aguante aritmética. La primera versión de esto hacía eso y el total
        # daba cero, porque «4.500,00» no es un número en ningún idioma que
        # `Decimal` entienda.
        cobrado = from_db(respuesta.get("amount"))
        fila = {
            "medio": origen["medio"],
            "pago": doc["payment_id"],
            "pago_en_mercadopago": str(doc.get(origen["campo_en_mercadopago"])),
            # DOS COSAS DISTINTAS, Y HACEN FALTA LAS DOS
            #
            #   `cuenta` es de QUIEN es la plata: la cuenta de esta aplicación
            #   que cobra o cobró. En PIX es `gestor_id` —que no es un rol, es
            #   sencillamente la cuenta que generó el cobro y a la que
            #   `process_pix_confirmation` le acredita— y en tarjeta es
            #   `user_id`. Nunca falta, porque sin ella el pago no se habría
            #   podido crear.
            #
            #   `cliente` es el NOMBRE DE QUIEN PAGA, que en PIX puede ser un
            #   tercero. Es texto libre que escribe quien arma el cobro, y en
            #   los pagos viejos está vacío.
            #
            #   La primera versión de esto mostraba una sola columna, con el
            #   nombre del cliente y la cuenta como respaldo. En los tres únicos
            #   descuadres que apareció en producción —todos de pagos viejos—
            #   esa columna salió vacía: justo en las filas donde más falta
            #   hace saber a quién corresponden. Un informe que no se puede
            #   seguir hasta una cuenta no sirve para ir a arreglar nada.
            "cuenta": str(doc.get(origen["campo_de_la_cuenta"]) or ""),
            "cliente": doc.get("client_name") or "",
            "estado_en_la_app": doc.get("status"),
            "cuando": _cuando(doc.get("created_at")),
            "cuando_lo_aprobo_mercadopago": respuesta.get("date_approved"),
            # Dos montos, a propósito. El de Mercado Pago es lo que de verdad
            # salió de la cuenta del cliente; el nuestro, lo que la app pensaba
            # cobrar. Si no coinciden, eso también hay que verlo.
            "monto_en_mercadopago": _texto(cobrado),
            "monto_en_la_app": _texto(_monto_local(origen, doc)),
        }
        # DOS LISTAS, Y NO UNA CON UNA COLUMNA
        #
        #   Las dos son «pago aprobado en Mercado Pago sin línea en el libro»,
        #   y son problemas distintos que se arreglan distinto:
        #
        #     · Si la app TAMPOCO lo da por cobrado, hay alguien esperando su
        #       plata. Eso es lo que hay que ir a acreditar, y es lo que suma el
        #       total.
        #
        #     · Si la app SI lo da por cobrado, el cliente ya tiene su saldo y
        #       lo que falta es la línea del libro. Es un problema de registro:
        #       hay que asentarlo, no acreditarlo.
        #
        #   Mezclarlos en una sola lista da un total que no significa nada —ni
        #   la plata que se debe ni el descuadre del libro—, y un total que no
        #   significa nada es el que alguien usa para decidir.
        if doc.get("status") in LA_APP_LO_DA_POR_COBRADO:
            total_descuadres += cobrado
            descuadres.append(fila)
        else:
            total += cobrado
            cobros.append(fila)

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": dias,
        "tope": tope,
        "candidatos": len(candidatos),
        "mirados": len(a_mirar),
        "sin_mirar": max(0, len(candidatos) - len(a_mirar)),
        "sin_respuesta": sin_respuesta,
        "pudo_preguntar": _mercadopago_esta_configurado(),
        "cuantos": len(cobros),
        "total_brl": _texto(total),
        "cobros": cobros,
        "cuantos_descuadres": len(descuadres),
        "total_descuadres_brl": _texto(total_descuadres),
        "descuadres": descuadres,
    }
