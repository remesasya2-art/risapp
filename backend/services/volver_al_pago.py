"""
Volver a ver cómo pagar un pedido que quedó a medias.

POR QUE ESTO EXISTE

    El cliente cotiza, le aparece el QR (o el formulario de la tarjeta, o los
    datos del banco) y… cierra la pantalla. Se le corta el teléfono, se le
    vence la sesión, lo llaman.

    Hasta ahora eso era el final: la pantalla de pago se dibujaba una sola vez,
    con lo que devolvía la cotización, y no se guardaba en ningún lado al que
    el cliente pudiera volver. El pedido quedaba en el historial diciendo
    «Pendiente» —ni siquiera «esperando pago»— y no había forma de retomarlo.

    Acá se junta lo que hace falta para volver a dibujar esa pantalla.

DE DONDE SALE CADA COSA, Y POR QUE HACE FALTA JUNTARLAS

    La orden vive en `transactions` y el cobro en `gestor_pix_payments`. El QR
    está en el segundo; el monto, el vencimiento y el estado, en el primero.
    Ninguno de los dos alcanza solo.

LO QUE SE DEVUELVE ES UNA LISTA DE LO PERMITIDO

    Como todo lo que ve el usuario. Una lista de lo prohibido deja pasar cada
    campo nuevo hasta que alguien se acuerde — y acá al lado hay una respuesta
    cruda de Mercado Pago con los datos del pagador.

EL VENCIMIENTO SE DECIDE ACA, MIRANDO EL RELOJ

    Y no sólo el estado guardado. El barrido corre cada minuto
    (`services/pago_al_final.py`), así que entre que el cobro muere y que el
    estado cambia hay hasta un minuto en el que la orden todavía dice
    «esperando pago». Si esta pantalla se guiara sólo por el estado, en ese
    minuto le mostraría al cliente un QR que ya no sirve.

    Es la misma razón por la que `confirmar` mira la fecha: entre el reloj y
    el barrido hay una ventana, y las dos puntas tienen que mirar el reloj.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Los textos, uno por corredor ─────────────────────────────────────────
#
# Los escribió el dueño del proyecto y dicen cosas distintas a propósito.
#
#   En Venezuela el pago es instantáneo: si no entró, no se pagó. No hay
#   ambigüedad posible, así que el mensaje es corto.
#
#   En Brasil el cliente transfiere por su cuenta y después sube el
#   comprobante. Puede perfectamente haber pagado y no haber llegado a
#   subirlo — y en ese caso hay plata suya dando vueltas. Por eso ese mensaje
#   tiene que nombrar las dos situaciones y mandar a soporte en la segunda:
#   decirle sólo «expiró» a alguien que ya transfirió es decirle que perdió
#   la plata.
VENCIDO_VENEZUELA = (
    "Este pedido expiró y no se pagó. La tasa que te habíamos reservado ya no "
    "vale, así que hacé un pedido nuevo para ver el precio de ahora.")

VENCIDO_BRASIL = (
    "Pasados los 7 minutos este pedido expiró. Si no llegaste a pagarlo, hacé "
    "uno nuevo. Si ya transferiste y no alcanzaste a subir el comprobante, "
    "escribinos por el chat de soporte: no hagas otro pedido ni vuelvas a "
    "transferir.")


def esta_vencido(orden: dict, ahora: datetime = None) -> bool:
    """¿Este pedido ya no se puede pagar?

    Mira el reloj Y el estado, porque cualquiera de los dos puede ir adelante:
    el reloj cuando el barrido todavía no pasó, el estado cuando la orden se
    apartó por otro motivo.
    """
    from services import pago_al_final

    if orden.get("status") in (pago_al_final.PAGO_VENCIDO,
                               pago_al_final.PAGO_TARDIO):
        return True
    vence = orden.get("payment_expires_at")
    if not vence:
        return False
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    return (ahora or datetime.now(timezone.utc)) >= vence


def es_de_venezuela(orden: dict) -> bool:
    """¿De qué corredor es? Decide qué mensaje se muestra al vencer.

    Se mira el prefijo de la referencia del cobro y no el tipo de la orden:
    el tipo es `withdrawal` en los dos corredores, así que no distingue nada.
    """
    from services import pago_al_final
    referencia = str(orden.get("payment_order_id") or "")
    return referencia.startswith(pago_al_final.PREFIJO_VENEZUELA)


def por_que_no_se_puede_pagar(orden: dict) -> str:
    """El texto que va en la pantalla cuando el pedido ya venció."""
    return VENCIDO_VENEZUELA if es_de_venezuela(orden) else VENCIDO_BRASIL


def segundos_que_quedan(orden: dict, ahora: datetime = None) -> int:
    """Cuánto le queda para pagar. Nunca negativo.

    La pantalla lo usa para el reloj. Se calcula en el servidor y no en el
    navegador porque el reloj del teléfono puede estar corrido: un cliente con
    la hora adelantada vería «expirado» sobre un cobro vivo.
    """
    vence = orden.get("payment_expires_at")
    if not vence:
        return 0
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    quedan = (vence - (ahora or datetime.now(timezone.utc))).total_seconds()
    return max(0, int(quedan))
