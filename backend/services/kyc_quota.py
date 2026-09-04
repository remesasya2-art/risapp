"""
services/kyc_quota.py — Cuanto puede operar una cuenta que todavia no verifico.

LA REGLA
    Una cuenta sin KYC aprobado tiene un cupo de 200 RIS acumulados Y 2 operaciones
    completadas. Se agota con lo que pase primero:

        2 operaciones de 50   -> quedan 100 de cupo pero ya no puede operar
        1 operacion de 200    -> cupo agotado de una, aunque le sobre la segunda
        1 de 120 y luego 100  -> la segunda se rechaza: lo llevaria a 220
        una primera de 500    -> se rechaza: ninguna operacion puede pasar el techo

    Por eso cualquier monto mayor a 200 exige KYC aprobado: no hay forma de que
    entre en el cupo.

    No se renueva por mes. Una vez agotado, la unica salida es verificar la cuenta.
    El super_admin esta exento, y un usuario ya verificado no tiene ninguno de los
    dos limites (solo el tope por operacion de services/limits.py).

QUE CUENTA COMO OPERACION
    Las que efectivamente movieron plata: una recarga PIX acreditada, una recarga
    en bolivares aprobada por el admin, un envio de reales pagado. Un QR de PIX
    generado y nunca pagado no gasta cupo, y una operacion cancelada o rechazada
    tampoco.

COMO SE CUENTA — y por que asi
    El contador vive en el documento del usuario, en el subdocumento kyc_quota, y
    se incrementa DENTRO DEL MISMO update_one que mueve el saldo. Es la parte
    importante del diseno: si el saldo se movio, el contador se movio, porque son
    la misma escritura de Mongo. No hay dos registros que puedan desincronizarse.

    La alternativa era contar leyendo db.transactions, y no es viable: hay 15 tipos
    de operacion repartidos en 6 colecciones, unas con `type` y otras con `tipo`,
    unas con `status` y otras con `estado`, "completada" es `completed` en un lado,
    `approved` en otro y `paid` en otro, y amount_input es RIS en un envio de reales
    pero USDT en uno de cripto. Ya hay un bug vivo por eso mismo en
    services/referrals.py, que busca recharge_ves con status "completed" cuando el
    valor real es "approved": ese contador da 0 siempre y nadie se entero.

LO QUE ESTE MODULO TODAVIA NO CUBRE
    Las vias en cripto. Un deposito de USDT acredita balance_usdt y nunca toca RIS,
    asi que sumarlo al cupo exigiria una conversion USDT->RIS que hoy no existe en
    el codigo. Quedan fuera a proposito y esta anotado como pendiente, en vez de
    inventar una tasa para un control de cumplimiento.
"""

import logging

from services import registro

logger = logging.getLogger(__name__)

# ─── La regla, en numeros ─────────────────────────────────────────────────
UNVERIFIED_MAX_RIS = 200.0
UNVERIFIED_MAX_OPS = 2

# Roles exentos del cupo.
EXEMPT_ROLES = {"super_admin"}

VERIFIED_STATUS = "verified"


def is_exempt(role: str | None, verification_status: str | None) -> bool:
    """Un usuario verificado, o el super_admin, no tienen cupo."""
    if (role or "") in EXEMPT_ROLES:
        return True
    return (verification_status or "") == VERIFIED_STATUS


def quota_used(user_doc: dict | None) -> tuple[int, float]:
    """(operaciones, RIS) ya gastados. Tolera el subdocumento ausente."""
    cuota = (user_doc or {}).get("kyc_quota") or {}
    try:
        ops = int(cuota.get("ops") or 0)
    except (TypeError, ValueError):
        ops = 0
    try:
        ris = float(cuota.get("ris") or 0.0)
    except (TypeError, ValueError):
        ris = 0.0
    return max(ops, 0), max(ris, 0.0)


def check_amount(user_doc: dict | None, monto_ris) -> str | None:
    """Puede este usuario crear una operacion por `monto_ris`?

    Devuelve el mensaje de error, o None si puede. No lanza: la ruta decide.
    """
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    if is_exempt(role, estado):
        return None

    try:
        monto = float(monto_ris)
    except (TypeError, ValueError):
        monto = 0.0

    ops, ris = quota_used(user_doc)

    if ops >= UNVERIFIED_MAX_OPS:
        return (
            f"Ya usaste las {UNVERIFIED_MAX_OPS} operaciones disponibles sin verificar tu cuenta. "
            "Completá la verificación para seguir operando en RIS App."
        )
    if ris + monto > UNVERIFIED_MAX_RIS:
        restante = max(UNVERIFIED_MAX_RIS - ris, 0.0)
        return (
            f"Sin verificar tu cuenta podés operar hasta {UNVERIFIED_MAX_RIS:.0f} RIS en total, "
            f"y te quedan {restante:.2f}. Completá la verificación para operar por este monto."
        )
    return None


def consume_inc(monto_ris) -> dict:
    """El $inc que hay que mergear en el update que mueve el saldo.

    Se usa asi, para que contador y saldo sean la misma escritura:

        {"$inc": {"balance_ris": monto, **consume_inc(monto)}}
    """
    try:
        monto = float(monto_ris)
    except (TypeError, ValueError):
        monto = 0.0
    return {"kyc_quota.ops": 1, "kyc_quota.ris": monto}


def is_exhausted(user_doc: dict | None) -> bool:
    """Ya no puede operar mas sin verificar?"""
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    if is_exempt(role, estado):
        return False
    ops, ris = quota_used(user_doc)
    return ops >= UNVERIFIED_MAX_OPS or ris >= UNVERIFIED_MAX_RIS


def quota_payload(user_doc: dict | None) -> dict:
    """Estado del cupo para el frontend (pantalla y ventana flotante)."""
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    exento = is_exempt(role, estado)
    ops, ris = quota_used(user_doc)
    return {
        "aplica": not exento,
        "verificado": (estado or "") == VERIFIED_STATUS,
        "max_ris": UNVERIFIED_MAX_RIS,
        "max_ops": UNVERIFIED_MAX_OPS,
        "ris_usados": round(ris, 2),
        "ops_usadas": ops,
        "ris_restantes": None if exento else round(max(UNVERIFIED_MAX_RIS - ris, 0.0), 2),
        "ops_restantes": None if exento else max(UNVERIFIED_MAX_OPS - ops, 0),
        "agotado": (not exento) and (ops >= UNVERIFIED_MAX_OPS or ris >= UNVERIFIED_MAX_RIS),
    }


async def notify_if_exhausted(user_doc_despues: dict | None) -> bool:
    """Avisa al usuario, una sola vez, cuando el cupo se le acaba de agotar.

    Se llama con el documento del usuario DESPUES del $inc (el que devuelve
    find_one_and_update con return_document=True). Manda notificacion en la
    campana —que ya dispara push por dentro— y un mail. Nunca lanza: que falle
    un aviso no puede romper una acreditacion de saldo.

    La marca kyc_quota.avisado evita repetir el aviso en cada operacion
    posterior.
    """
    if not is_exhausted(user_doc_despues):
        return False
    cuota = (user_doc_despues or {}).get("kyc_quota") or {}
    if cuota.get("avisado"):
        return False

    user_id = (user_doc_despues or {}).get("user_id")
    if not user_id:
        return False

    titulo = "Verificá tu cuenta para seguir operando"
    mensaje = (
        f"Alcanzaste el límite de {UNVERIFIED_MAX_OPS} operaciones o {UNVERIFIED_MAX_RIS:.0f} RIS "
        "que permite una cuenta sin verificar. Completá la verificación para seguir usando RIS App."
    )

    try:
        from database import db
        await db.users.update_one({"user_id": user_id}, {"$set": {"kyc_quota.avisado": True}})
    except Exception as e:
        logger.warning(f"kyc_quota: no se pudo marcar el aviso para {user_id}: {e}")

    try:
        from services.notifications import create_notification
        await create_notification(
            user_id=user_id,
            title=titulo,
            message=mensaje,
            notification_type="kyc_required",
            data={"motivo": "cupo_agotado", "accion": "/verification"},
        )
    except Exception as e:
        logger.warning(f"kyc_quota: no se pudo crear la notificacion para {user_id}: {e}")

    email = (user_doc_despues or {}).get("email")
    if email:
        try:
            from services.email_notifications import send_email, get_email_template
            html = get_email_template(
                titulo,
                f"<p>{mensaje}</p><p>Ingresá a tu cuenta y completá la verificación para "
                "levantar el límite.</p>",
                "Este aviso se envía una sola vez.",
            )
            await send_email(email, titulo, html)
        except Exception as e:
            logger.warning("kyc_quota: no se pudo enviar el mail a %s: %s",
                           registro.correo(email), e)

    return True
