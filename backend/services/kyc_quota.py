"""
services/kyc_quota.py — Cuanto puede operar una cuenta que todavia no verifico.

DE DONDE SALEN LOS DOS NUMEROS
    Del catalogo de `services/configuracion.py`, y se cambian desde el panel del
    super administrador. Estaban escritos a mano aca, y cambiarlos era un commit
    y un despliegue.

    Los valores de fabrica —200 RIS y 2 operaciones— siguen siendo los que rigen
    mientras nadie los toque, y son los que usan los ejemplos de abajo.

    Ojo con una cosa al leerlos: los dos numeros SE PUBLICAN en la pagina de
    "como funciona". Cambiarlos desde el panel cambia una promesa publica.

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
from decimal import Decimal

from services import registro
from services.money import from_db, quantize_money, to_decimal, to_float

logger = logging.getLogger(__name__)

# ─── La regla, en numeros ─────────────────────────────────────────────────
#
# Ya no viven aca: estan en el catalogo de `services/configuracion.py`, bajo
# `cupo_sin_verificar_ris` y `cupo_sin_verificar_operaciones`, para que se
# cambien desde el panel y no con un despliegue.


async def _el_cupo(db):
    """`(maximo en RIS como Decimal, maximo de operaciones como int)`."""
    from services import configuracion
    return (await configuracion.leer(db, "cupo_sin_verificar_ris"),
            await configuracion.leer(db, "cupo_sin_verificar_operaciones"))


# Roles exentos del cupo.
EXEMPT_ROLES = {"super_admin"}

VERIFIED_STATUS = "verified"


def is_exempt(role: str | None, verification_status: str | None) -> bool:
    """Un usuario verificado, o el super_admin, no tienen cupo."""
    if (role or "") in EXEMPT_ROLES:
        return True
    return (verification_status or "") == VERIFIED_STATUS


def quota_used(user_doc: dict | None) -> tuple[int, Decimal]:
    """(operaciones, RIS) ya gastados. Tolera el subdocumento ausente.

    EL ACUMULADO SE GUARDA COMO `float` Y SE LEE COMO `Decimal`

        En la base, `kyc_quota.ris` es un numero comun: se incrementa con el
        mismo `$inc` que mueve el saldo, y pasarlo a `Decimal128` seria mudar
        datos de cuentas reales. Queda pendiente y anotado.

        Pero la comparacion contra el cupo si se hace en `Decimal`, porque el
        cupo ahora es `Decimal` y en Python sumar un `Decimal` con un `float`
        levanta `TypeError`. La conversion pasa aca, en el borde, una sola vez.
    """
    cuota = (user_doc or {}).get("kyc_quota") or {}
    try:
        ops = int(cuota.get("ops") or 0)
    except (TypeError, ValueError):
        ops = 0
    # `from_db` lee por igual un float, un Decimal128 y un texto — que es lo que
    # hace falta para datos ya guardados, y lo que deja abierta la puerta a
    # migrar el acumulado sin tocar esta funcion.
    try:
        ris = from_db(cuota.get("ris") or 0)
    except Exception:
        ris = Decimal("0")
    return max(ops, 0), max(ris, Decimal("0"))


async def check_amount(db, user_doc: dict | None, monto_ris) -> str | None:
    """Puede este usuario crear una operacion por `monto_ris`?

    Devuelve el mensaje de error, o None si puede. No lanza: la ruta decide.
    """
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    if is_exempt(role, estado):
        return None

    monto = to_decimal(monto_ris)
    ops, ris = quota_used(user_doc)
    max_ris, max_ops = await _el_cupo(db)

    if ops >= max_ops:
        return (
            f"Ya usaste las {max_ops} operaciones disponibles sin verificar tu cuenta. "
            "Completá la verificación para seguir operando en RIS App."
        )
    if ris + monto > max_ris:
        restante = max(max_ris - ris, Decimal("0"))
        return (
            f"Sin verificar tu cuenta podés operar hasta {max_ris:.0f} RIS en total, "
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


async def is_exhausted(db, user_doc: dict | None) -> bool:
    """Ya no puede operar mas sin verificar?"""
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    if is_exempt(role, estado):
        return False
    ops, ris = quota_used(user_doc)
    max_ris, max_ops = await _el_cupo(db)
    return ops >= max_ops or ris >= max_ris


async def quota_payload(db, user_doc: dict | None) -> dict:
    """Estado del cupo para el frontend (pantalla y ventana flotante).

    Los montos salen como `float` por el mismo motivo que en
    `services/limits.limits_payload`: la ventana flotante ya los compara con
    `parseFloat`, y pasarlos a texto la romperia en silencio.
    """
    role = (user_doc or {}).get("role")
    estado = (user_doc or {}).get("verification_status")
    exento = is_exempt(role, estado)
    ops, ris = quota_used(user_doc)
    max_ris, max_ops = await _el_cupo(db)
    agotado = (not exento) and (ops >= max_ops or ris >= max_ris)
    return {
        "aplica": not exento,
        "verificado": (estado or "") == VERIFIED_STATUS,
        "max_ris": to_float(max_ris),
        "max_ops": max_ops,
        "ris_usados": to_float(quantize_money(ris)),
        "ops_usadas": ops,
        "ris_restantes": None if exento else to_float(
            quantize_money(max(max_ris - ris, Decimal("0")))),
        "ops_restantes": None if exento else max(max_ops - ops, 0),
        "agotado": agotado,
    }


async def notify_if_exhausted(user_doc_despues: dict | None) -> bool:
    """Avisa al usuario, una sola vez, cuando el cupo se le acaba de agotar.

    Se llama con el documento del usuario DESPUES del $inc (el que devuelve
    find_one_and_update con return_document=True). Manda notificacion en la
    campana —que ya dispara push por dentro— y un mail. Nunca lanza: que falle
    un aviso no puede romper una acreditacion de saldo.

    La marca kyc_quota.avisado evita repetir el aviso en cada operacion
    posterior.

    ESTA SIGUE SIN RECIBIR LA BASE, Y ES LA EXCEPCION

        Las demas funciones de este modulo la piden por parametro desde que los
        numeros salen de la configuracion. Esta no: ya buscaba la base por su
        cuenta para marcar el aviso, la llaman tres rutas, y cambiarle la firma
        seria mover tres llamadas y sus pruebas para no ganar nada. Que quede
        dicho, para que no se lea como un olvido.
    """
    from database import db

    if not await is_exhausted(db, user_doc_despues):
        return False
    cuota = (user_doc_despues or {}).get("kyc_quota") or {}
    if cuota.get("avisado"):
        return False

    user_id = (user_doc_despues or {}).get("user_id")
    if not user_id:
        return False

    max_ris, max_ops = await _el_cupo(db)
    titulo = "Verificá tu cuenta para seguir operando"
    mensaje = (
        f"Alcanzaste el límite de {max_ops} operaciones o {max_ris:.0f} RIS "
        "que permite una cuenta sin verificar. Completá la verificación para seguir usando RIS App."
    )

    try:
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
