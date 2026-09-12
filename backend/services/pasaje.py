"""
services/pasaje.py — Llenar el comprobante con la operación de verdad.

POR QUE HAY QUE IR A BUSCARLA

    El aviso dice «Tu retiro de 4.500,00 VES ha sido procesado» y nada más:
    ni el número, ni la fecha, ni a quién, ni con qué tasa. Para armar un
    comprobante hace falta la operación, y la operación está en la base.

    La otra opción era meter los ocho campos en el `data` del aviso, en los
    diez lugares que mueven dinero. Es la misma forma que produjo las cinco
    maneras distintas de avisarle al equipo que hubo que desarmar: diez copias
    se desincronizan, y el día que una se olvide de un campo el comprobante
    sale mocho sin que nada lo diga. Acá viaja UN identificador y el resto se
    busca en un solo lugar.

LA PROYECCION ES UNA LISTA DE LO PERMITIDO

    Regla del repositorio, y acá pesa el doble: esto arma un correo, y un
    correo se reenvía. Con una lista de lo prohibido, cada campo nuevo de una
    operación entra solo al comprobante el día que alguien lo agregue —una
    nota interna, el nombre del operador que la aprobó, un motivo de fraude— y
    se va a una casilla que no controlamos.

DEL BENEFICIARIO, LOS ULTIMOS CUATRO

    Ni el documento entero ni la cuenta entera. Alcanzan para reconocer la
    operación y no para usarla. Está explicado en `services/comprobante.py`.

SI NO SE PUEDE ARMAR, EL CORREO SALE IGUAL

    Devuelve `None` y el que llama manda el correo simple. Un movimiento de
    dinero sin aviso es mucho peor que un aviso sin pasaje, y esto corre
    dentro del camino del correo, que a su vez corre dentro del camino de un
    aviso que ya dijo que nunca levanta.
"""
import logging

from services import comprobante as comp

logger = logging.getLogger(__name__)

# De qué se trata, en palabras del usuario. La clave es el `type` guardado.
#
# Lo que no está en esta tabla NO se queda sin comprobante: cae en el nombre
# genérico de abajo. Al revés —sin comprobante— el día que alguien agregue una
# clase nueva de movimiento, sus correos perderían el pasaje en silencio.
DE_QUE_SE_TRATA = {
    "withdrawal": "Retiro",
    "recharge_ves": "Recarga",
    "send": "Envío",
    "entrada": "Entrada de saldo",
    "salida": "Salida de saldo",
}
GENERICO = "Movimiento"

# Cómo se dice cada estado, y de qué color va el sello.
COMO_QUEDO = {
    "pending":           ("En proceso",        comp.ESPERA),
    "awaiting_payment":  ("Esperando el pago", comp.ESPERA),
    "awaiting_topup":    ("Falta completar",   comp.ESPERA),
    "underpaid_review":  ("Pago incompleto",   comp.ESPERA),
    "approved":          ("Aprobada",          comp.VERDE),
    "completed":         ("Completado",        comp.VERDE),
    "finished":          ("Completado",        comp.VERDE),
    "paid":              ("Pagado",            comp.VERDE),
    "resolved":          ("Resuelto",          comp.VERDE),
    "rejected":          ("Rechazado",         comp.ROJO),
    "cancelled":         ("Cancelado",         comp.ROJO),
    "cancelled_by_user": ("Cancelado",         comp.ROJO),
    "expired":           ("Vencido",           comp.ROJO),
    "payment_error":     ("Error en el pago",  comp.ROJO),
    "error":             ("Con un problema",   comp.ROJO),
    "suspicious":        ("En revisión",       comp.ESPERA),
}

# Qué es cada moneda, para el pie de la ruta del pasaje.
MONEDAS = {
    "RIS":  "Tu saldo en RIS App",
    "VES":  "Bolívares, Venezuela",
    "BRL":  "Reales, Brasil",
    "USDT": "Cripto (USDT)",
    "BTC":  "Bitcoin",
    "USD":  "Dólares",
}

# Lo único que se lee de la operación. Lista de lo PERMITIDO.
DE_LA_OPERACION = {
    "_id": 0,
    "display_id": 1, "transaction_id": 1, "remesa_id": 1, "type": 1, "status": 1,
    "amount_input": 1, "amount_output": 1,
    "currency_input": 1, "currency_output": 1,
    "rate": 1, "created_at": 1, "completed_at": 1,
    # Del beneficiario, sólo esto, y los dos números salen recortados a cuatro.
    "beneficiary_data.full_name": 1,
    "beneficiary_data.bank_name": 1,
    "beneficiary_data.account_number": 1,
    "beneficiary_data.document": 1,
    "beneficiary_data.payment_type": 1,
}

# Y lo único que se lee de un envío de paquetería.
DEL_ENVIO = {
    "_id": 0,
    "display_id": 1, "estado": 1, "created_at": 1, "moneda": 1,
    "peso_facturable": 1,
    "origen.ciudad": 1,
    "destino.ciudad": 1, "destino.estado_ve": 1,
}


def _sello(estado: str):
    return COMO_QUEDO.get(estado or "", (estado or "", comp.ESPERA))


async def _base(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def de_la_operacion(identificador: str, *, titulo: str, detalle: str = "",
                          db=None) -> str | None:
    """El pasaje de un movimiento de dinero, o None si no se pudo armar.

    `identificador` puede ser el `transaction_id`, el `display_id` o el
    `remesa_id`, y se busca por los tres. No es pereza: las remesas con
    Bitcoin NO tienen `transaction_id` —su documento en `transactions` se
    encuentra por `remesa_id`—, y los retiros no tienen `remesa_id`. Pedirle a
    los trece lugares que avisan que se pongan de acuerdo en un nombre es
    trabajo que no se hace, y el que se olvida deja el correo sin comprobante.
    """
    if not identificador:
        return None
    try:
        base = await _base(db)
        op = await base.transactions.find_one(
            {"$or": [{"transaction_id": identificador},
                     {"display_id": identificador},
                     {"remesa_id": identificador}]},
            DE_LA_OPERACION)
    except Exception as e:
        logger.warning("no se pudo leer la operación %s para el correo: %s",
                       identificador, e)
        return None
    if not op:
        return None

    quien = op.get("beneficiary_data") or {}
    entra, sale = op.get("currency_input") or "", op.get("currency_output") or ""
    estado, color = _sello(op.get("status"))
    numero = (op.get("display_id") or op.get("remesa_id")
              or op.get("transaction_id") or identificador)
    monto = comp.plata(op.get("amount_output"), sale)
    cuando = op.get("completed_at") or op.get("created_at")

    campos = [("Pusiste", comp.plata(op.get("amount_input"), entra)),
              ("Recibe", monto)]
    if op.get("rate"):
        campos.append(("Tasa", comp.plata(op.get("rate"))))

    filas = [("Beneficiario", quien.get("full_name") or ""),
             ("Banco", quien.get("bank_name") or ""),
             ("Cuenta", comp.ultimos4(quien.get("account_number"))),
             ("Documento", comp.ultimos4(quien.get("document"))),
             ("Forma de pago", (quien.get("payment_type") or "").capitalize())]

    tipo = DE_QUE_SE_TRATA.get(op.get("type"), GENERICO)
    return comp.armar(
        titulo=titulo, detalle=detalle, tipo=tipo,
        desde=entra, desde_pie=MONEDAS.get(entra, ""),
        hasta=sale, hasta_pie=MONEDAS.get(sale, ""),
        monto=monto, campos=campos, filas=filas,
        referencia=numero, cuando=cuando,
        estado=estado, color_estado=color,
        carga_qr=comp.carga_del_qr(referencia=numero, tipo=tipo, monto=monto,
                                   cuando=cuando, estado=estado))


async def del_envio(envio_id: str, *, titulo: str, detalle: str = "",
                    db=None) -> str | None:
    """El pasaje de un paquete. Mismo pasaje, otra ruta.

    Acá la ruta del pasaje es la de verdad: de qué ciudad sale y a qué ciudad
    va. En un movimiento de dinero la ruta son las dos monedas, que es lo más
    parecido que tiene.
    """
    if not envio_id:
        return None
    try:
        base = await _base(db)
        envio = await base.envios.find_one({"envio_id": envio_id}, DEL_ENVIO)
    except Exception as e:
        logger.warning("no se pudo leer el envío %s para el correo: %s",
                       envio_id, e)
        return None
    if not envio:
        return None

    origen = (envio.get("origen") or {}).get("ciudad") or ""
    destino = (envio.get("destino") or {}).get("ciudad") or ""
    provincia = (envio.get("destino") or {}).get("estado_ve") or ""
    numero = envio.get("display_id") or envio_id
    # El estado del paquete ya viene en el título del aviso, que es distinto
    # por estado. Repetirlo en el sello diría lo mismo dos veces a diez
    # centímetros de distancia.
    peso = envio.get("peso_facturable")

    # El número NO va acá: ya está en el talón, grande, dos dedos a la
    # derecha. Estaba, y lo único que hacía era ocupar lugar dos veces.
    campos = []
    if peso:
        campos.append(("Peso", f"{comp.plata(peso)} kg"))
    if provincia:
        campos.append(("Estado", provincia))

    tipo = "Envío de paquete"
    return comp.armar(
        titulo=titulo, detalle=detalle, tipo=tipo,
        desde=(origen[:3] or "").upper(), desde_pie=f"{origen}, Brasil" if origen else "",
        hasta=(destino[:3] or "").upper(),
        hasta_pie=", ".join([p for p in (destino, provincia) if p]),
        campos=campos, filas=(),
        referencia=numero, cuando=envio.get("created_at"),
        carga_qr=comp.carga_del_qr(referencia=numero, tipo=tipo,
                                   cuando=envio.get("created_at"),
                                   estado=envio.get("estado") or ""))


# De qué clase de aviso se saca el identificador, y de qué colección.
#
# `envio` es la única que no mira `db.transactions`.
#
# Y NO TODOS LOS AVISOS DE DINERO TIENEN OPERACION QUE MOSTRAR. El pago por
# PIX, el de tarjeta, el depósito en cripto y el bono de referido viven en
# otras colecciones —`pix_payments`, la de Mercado Pago, `credit_orders`,
# `partner_earnings`— y no tienen documento en `transactions`. Esos siguen
# saliendo como párrafo, que es lo que hace esta función cuando devuelve
# `None`, y está bien: un comprobante con la mitad de los campos vacíos es
# peor que un párrafo que dice la verdad.
#
# A los que sí la tienen se les agregó el número al aviso, al lado de cada
# `create_notification`, en los archivos de rutas.
DONDE_BUSCARLO = ("transaction_id", "remesa_id", "tx_id", "display_id")


async def para_el_aviso(titulo: str, mensaje: str, notification_type: str,
                        data=None, db=None) -> str | None:
    """El pasaje que le corresponde a este aviso, o None si no le corresponde.

    NO LEVANTA NUNCA. Ver el encabezado.
    """
    datos = data if isinstance(data, dict) else {}
    try:
        if notification_type == "envio":
            return await del_envio(datos.get("envio_id"), titulo=titulo,
                                   detalle=mensaje, db=db)
        for clave in DONDE_BUSCARLO:
            if datos.get(clave):
                return await de_la_operacion(datos[clave], titulo=titulo,
                                             detalle=mensaje, db=db)
        return None
    except Exception as e:                                    # pragma: no cover
        logger.warning("no se pudo armar el pasaje de %r: %s",
                       notification_type, e)
        return None
