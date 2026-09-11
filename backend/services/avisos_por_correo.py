"""
services/avisos_por_correo.py — Qué avisos salen TAMBIEN por correo.

POR QUE UNA TABLA Y NO DIECIOCHO COPIAS

    Antes ningún movimiento de dinero mandaba correo. Dieciocho eventos
    —retiros, recargas, envíos, reembolsos, bonos— avisaban dentro de la
    aplicación y nada más. Quien no abría la aplicación no se enteraba de que
    su plata se había movido, y no le quedaba constancia de nada.

    La forma obvia de arreglarlo era agregar una línea de correo en los
    dieciocho lugares. Eso es exactamente lo que produjo las cinco formas
    distintas de avisarle al equipo que tuvimos que desarmar: dieciocho copias
    se desincronizan, y la diecinueve se olvida.

    Acá la regla vive en un lugar: una tabla que dice, por CLASE de aviso, si
    también sale por correo. El que agrega un evento de dinero agrega una
    línea, y si se olvida, hay un test que se pone rojo.

POR QUE SE ENGANCHA AL AVISO Y NO AL MOVIMIENTO

    Lo natural sería engancharlo donde se mueve la plata, en
    `services/saldos.mover`. Su comentario dice que por ahí «pasan todas».

    No es cierto: hay nueve lugares que le suman al saldo directamente, sin
    pasar por ahí —los retiros y los envíos en reales, entre ellos, que son los
    movimientos más grandes—. Enganchar el correo ahí dejaría afuera justo a
    los que más importan, y arreglarlo significaría tocar nueve lugares que
    mueven dinero.

    El AVISO, en cambio, ya está en los dieciocho, y ya dice lo que hay que
    decir. Enganchándolo ahí no se toca ni una línea de código que mueve plata.

SOLO LO PERSONAL

    Un aviso de trabajo —«hay un KYC nuevo»— no sale por correo. El equipo lo
    ve en el panel, y llenarle la casilla de trabajo a cada operador es la
    forma más rápida de que deje de mirar los correos de la aplicación.
"""
import logging

logger = logging.getLogger(__name__)

# Las clases de aviso que TAMBIEN salen por correo, y con qué asunto.
#
# El cuerpo se arma con el título y el mensaje del aviso: son los mismos que ya
# se le muestran a la persona adentro de la aplicación, y decirle dos cosas
# distintas por dos vías sobre el mismo hecho es cómo se pierde la confianza en
# las dos.
POR_CORREO = {
    # ── Retiros ──────────────────────────────────────────────────────────
    "withdrawal_pending":            "Tu retiro está en proceso",
    "withdrawal_completed":          "Tu retiro se completó",
    "withdrawal_rejected":           "Tu retiro fue rechazado",
    # ── Recargas y pagos que entran ──────────────────────────────────────
    "recharge_approved":             "Tu recarga se acreditó",
    "recharge_rejected":             "Tu recarga fue rechazada",
    "pix_received":                  "Recibimos tu pago por PIX",
    "card_received":                 "Recibimos tu pago con tarjeta",
    "credit_deposit":                "Tu depósito en cripto se acreditó",
    "btc_payment":                   "Recibimos tu pago con Bitcoin",
    # ── Envíos de dinero que salen ───────────────────────────────────────
    "crypto_send_paid":              "Tu envío en cripto se pagó",
    "crypto_send_refunded":          "Te devolvimos tu envío en cripto",
    "crypto_send_awaiting_topup":    "Falta completar el pago de tu envío",
    "crypto_send_underpaid_review":  "Tu pago quedó incompleto",
    "btc_enviado":                   "Tu envío con Bitcoin se completó",
    "btc_remesa_enviada":            "Tu remesa con Bitcoin se envió",
    "gestor_transaction":            "Se registró un movimiento en tu cuenta",
    # ── Lo demás que mueve el saldo ──────────────────────────────────────
    "partner_bonus":                 "Te acreditamos un bono por referido",
    # ── Los paquetes ─────────────────────────────────────────────────────
    #
    # Pedido expreso: el usuario quiere enterarse por correo de CADA
    # actualización de su paquete. El estado concreto va en el título del
    # aviso, que es el que se usa de asunto.
    "envio":                         None,
}


def asunto_de(notification_type: str, titulo: str) -> str | None:
    """El asunto del correo para esta clase de aviso, o `None` si no sale.

    Cuando la tabla dice `None`, el asunto es el título del aviso: los envíos
    tienen un título distinto por estado y repetir «Novedades de tu paquete»
    en los diez haría diez correos indistinguibles en la bandeja.
    """
    if notification_type not in POR_CORREO:
        return None
    return POR_CORREO[notification_type] or titulo


def _cuerpo(titulo: str, mensaje: str, pie: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1; margin-bottom: 6px;">{titulo}</h2>
        <p style="font-size: 16px; color: #374151; line-height: 1.5; white-space: pre-line;">{mensaje}</p>
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
        <p style="color: #6b7280; font-size: 13px;">{pie}</p>
    </div>
    """


async def acompanar(user_id: str, titulo: str, mensaje: str,
                    notification_type: str) -> bool:
    """Manda el correo que acompaña a un aviso, si a esa clase le corresponde.

    NO LEVANTA NUNCA, y no espera. El aviso ya quedó guardado dentro de la
    aplicación y el trabajo que lo produjo ya está hecho: que el correo tarde o
    falle no puede ser un segundo más de ruedita ni un error para quien acaba
    de operar.

    Devuelve si se encoló, que no es lo mismo que si salió. Lo que salió o no
    queda en el registro de `services/correo.py`.
    """
    asunto = asunto_de(notification_type, titulo)
    if asunto is None:
        return False

    try:
        from database import db
        from services import correo

        # Sólo la casilla. Sin proyección esto traería el usuario entero
        # —documento, teléfono, direcciones— en cada movimiento de dinero.
        persona = await db.users.find_one({"user_id": user_id},
                                          {"_id": 0, "email": 1, "is_active": 1})
        if not persona or not persona.get("email"):
            logger.warning("no hay a qué casilla mandar el aviso %r de %s",
                           notification_type, user_id)
            return False

        correo.en_segundo_plano(
            persona["email"], asunto,
            _cuerpo(titulo, mensaje,
                    "Este es un aviso automático de RIS App. Podés ver el "
                    "detalle en la aplicación."),
            que_es=f"aviso de {notification_type}")
        return True
    except Exception as e:                                    # pragma: no cover
        logger.warning("no se pudo acompañar el aviso %r con un correo: %s",
                       notification_type, e)
        return False
