"""
routes/credits.py — Endpoints de creditos cripto (deposito via NOWPayments).
Flujo DENTRO de la app (sin redireccion externa):
  POST /api/credits/deposit               -> crea un pago directo (create_payment) y
                                              devuelve pay_address/pay_amount para
                                              mostrar como QR + copiar, sin salir de la app.
  GET  /api/credits/deposit/{order_id}/status -> polling del estado (lee crypto_deposits,
                                              que el webhook va actualizando).
  POST /api/credits/webhook                -> IPN de NOWPayments. Acredita balance_usdt/
                                              balance_usdc (NUNCA balance_ris) al confirmarse.
Guarda cada intento en la coleccion crypto_deposits con estado 'pending'.
Cumplimiento: corre assert_payment_allowed (IP + declaracion) ANTES de crear el cobro.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from database import db
from routes.dependencies import get_current_user
from models.user import User
from services.geo_restrictions import assert_payment_allowed
from services import nowpayments
from services.credits import normalize_currency, CREDIT_LABELS, credit_user
from services.notifications import create_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credits", tags=["credits"])

# Dominio publico del backend, para las URLs de callback/redireccion.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://www.risappbr.com")

# Mapa de la moneda elegida por el usuario -> pay_currency que espera NOWPayments.
# (red por defecto; se puede ampliar si ofreces mas redes)
# NOTA: "usdcerc20" NO es un codigo valido para NOWPayments ("Currency usdcerc20 was
# not found") -> Ethereum es la red por defecto de USDC en su sistema, se usa "usdc" a secas.
PAY_CURRENCY = {
    "usdt": "usdttrc20",   # USDT en TRON (TRC20)
    "usdc": "usdc",        # USDC en Ethereum (red por defecto en NOWPayments)
}

# Fallback si NOWPayments no responde al consultar el minimo (no debe bloquear el flujo).
MINAMOUNT_FALLBACK = {"usdt": 10.0, "usdc": 10.0}

class DepositRequest(BaseModel):
    currency: str            # "usdt" o "usdc" (lo elige el usuario en la app)
    amount: float            # cuanto quiere depositar (en esa cripto, 1 a 1)
    declared_not_restricted: bool = False  # checkbox de declaracion de jurisdiccion

@router.get("/min-amount")
async def get_min_amount(
    currency: str = Query(..., description="'usdt' o 'usdc'"),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el monto minimo depositable para la moneda pedida (consulta a NOWPayments,
    con fallback fijo si la API no responde). Para mostrarlo en el frontend ANTES de que
    el usuario intente un monto que NOWPayments va a rechazar por AMOUNT_MINIMAL_ERROR."""
    key = normalize_currency(currency)
    if key not in PAY_CURRENCY:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    pay_currency = PAY_CURRENCY[key]
    try:
        info = await nowpayments.get_min_amount(pay_currency, fiat_equivalent="usd")
        min_amount = info.get("min_amount")
        if not min_amount:
            raise ValueError("sin min_amount en la respuesta")
        return {"currency": key, "min_amount": min_amount, "source": "nowpayments"}
    except Exception as e:
        logger.warning(f"No se pudo obtener min-amount de NOWPayments para {pay_currency}: {e}")
        return {
            "currency": key,
            "min_amount": MINAMOUNT_FALLBACK.get(key, 10.0),
            "source": "fallback",
        }

@router.post("/deposit")
async def create_deposit(
    data: DepositRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Crea un deposito de creditos: valida jurisdiccion, crea un PAGO DIRECTO en
    NOWPayments (sin pagina hosteada externa), guarda el deposito 'pending' y devuelve
    la direccion/monto para que el frontend los muestre como QR + copiar, sin que el
    usuario salga de la app."""

    # 1) Cumplimiento de jurisdiccion (IP + declaracion). Lanza 403/400 si no pasa.
    assert_payment_allowed(request, declared_not_restricted=data.declared_not_restricted)

    # 2) Validar moneda y monto
    key = normalize_currency(data.currency)
    if key not in PAY_CURRENCY:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    if not data.amount or data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")

    pay_currency = PAY_CURRENCY[key]

    # 2.5) Validar monto minimo ANTES de crear nada (evita el AMOUNT_MINIMAL_ERROR de
    # NOWPayments con un mensaje generico). Si la consulta a NOWPayments falla, se usa
    # un minimo fijo de respaldo en vez de bloquear el deposito.
    try:
        min_info = await nowpayments.get_min_amount(pay_currency, fiat_equivalent="usd")
        min_amount = min_info.get("min_amount") or MINAMOUNT_FALLBACK.get(key, 10.0)
    except Exception as e:
        logger.warning(f"No se pudo obtener min-amount de NOWPayments para {pay_currency}: {e}")
        min_amount = MINAMOUNT_FALLBACK.get(key, 10.0)

    if float(data.amount) < float(min_amount):
        raise HTTPException(
            status_code=400,
            detail=f"El monto mínimo para depositar {CREDIT_LABELS.get(key, key)} es {min_amount}.",
        )

    order_id = f"credit_{key}_{current_user.user_id}_{uuid.uuid4().hex[:12]}"

    # 3) Registrar el deposito como 'pending' ANTES de llamar a NOWPayments
    deposit_doc = {
        "order_id": order_id,
        "user_id": current_user.user_id,
        "currency": key,                 # 'usdt' | 'usdc'
        "pay_currency": pay_currency,    # 'usdttrc20' | 'usdcerc20'
        "amount": float(data.amount),
        "status": "pending",
        "credited": False,               # se pone True cuando el webhook acredita
        "created_at": datetime.now(timezone.utc),
    }
    await db.crypto_deposits.insert_one(deposit_doc)

    # 4) Crear el pago directo en NOWPayments (sin redireccion externa)
    #    price_currency va en USD (no en 'usdt'/'usdc' pelado, que NOWPayments no acepta
    #    como codigo de moneda valido). Como son stablecoins, el monto en USD es
    #    practicamente 1 a 1 con el monto en USDT/USDC que pidio el usuario.
    try:
        payment = await nowpayments.create_payment(
            price_amount=float(data.amount),
            price_currency="usd",
            pay_currency=pay_currency,
            order_id=order_id,
            order_description=f"Deposito de {CREDIT_LABELS.get(key, key)}",
            ipn_callback_url=f"{PUBLIC_BASE_URL}/api/credits/webhook",
        )
    except Exception as e:
        logger.error(f"NOWPayments create_payment failed for {order_id}: {e}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id}, {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")

    pay_address = payment.get("pay_address")
    pay_amount = payment.get("pay_amount")
    if not pay_address or not pay_amount:
        logger.error(f"NOWPayments sin pay_address/pay_amount para {order_id}: {payment}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id}, {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")

    payin_extra_id = payment.get("payin_extra_id")  # memo/tag, solo si la red lo requiere
    network = payment.get("network")

    # Guardar los datos del pago para trazabilidad y para que /status los pueda devolver
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "payment_id": payment.get("payment_id"),
                "pay_address": pay_address,
                "pay_amount": pay_amount,
                "payin_extra_id": payin_extra_id,
                "network": network,
            }
        },
    )

    return {
        "order_id": order_id,
        "pay_address": pay_address,
        "pay_amount": pay_amount,
        "pay_currency": pay_currency,
        "payin_extra_id": payin_extra_id,
        "network": network,
    }

@router.get("/deposit/{order_id}/status")
async def get_deposit_status(
    order_id: str,
    current_user: User = Depends(get_current_user),
):
    """Polling del estado de un deposito propio, para el flujo dentro de la app
    (sin redireccion). Solo lee crypto_deposits (que el webhook va actualizando) —
    no llama a NOWPayments directamente. Restringido al dueño del deposito."""
    deposit = await db.crypto_deposits.find_one(
        {"order_id": order_id, "user_id": current_user.user_id}, {"_id": 0}
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposito no encontrado")

    return {
        "order_id": order_id,
        "status": deposit.get("status"),
        "credited": deposit.get("credited", False),
        "currency": deposit.get("currency"),
        "amount": deposit.get("amount"),
    }

# Estados de NOWPayments que cierran el deposito sin acreditar (se registran para soporte).
TERMINALNO_CREDIT_STATUSES = {"failed", "expired", "refunded"}

@router.post("/webhook")
async def nowpayments_webhook(request: Request):
    """IPN de NOWPayments — confirma un deposito y acredita creditos (USDT/USDC).
    IMPORTANTE: esto es una billetera de creditos cripto totalmente separada de
    balance_ris. Este webhook NUNCA toca balance_ris ni la logica de PIX/MercadoPago
    (routes/gestor_pix.py) — es un flujo aislado, solo mueve balance_usdt/balance_usdc.
    Seguridad (mismo patron que el webhook de Mercado Pago):
      1. Verifica firma HMAC-SHA512 (header x-nowpayments-sig) contra NOWPAYMENTS_IPN_KEY.
      2. Busca el deposito propio por order_id en crypto_deposits.
      3. Acreditacion atomica y unica vez: find_one_and_update con credited=False,
         asi un IPN reenviado/duplicado nunca acredita dos veces.
      4. Solo se acredita cuando payment_status == 'finished' (confirmado por NOWPayments).
    """
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")

    if not nowpayments.verify_ipn_signature(raw_body, signature):
        logger.warning("NOWPayments webhook: firma invalida o ausente")
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        payload = json.loads(raw_body or b"{}")
    except Exception:
        payload = {}

    logger.info(f"NOWPayments webhook recibido: {payload}")

    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    payment_id = payload.get("payment_id")

    if not order_id:
        logger.warning("NOWPayments webhook sin order_id")
        return {"received": True, "error": "no_order_id"}

    deposit = await db.crypto_deposits.find_one({"order_id": order_id})
    if not deposit:
        logger.warning(f"NOWPayments webhook: order_id {order_id} no encontrado en crypto_deposits")
        return {"received": True, "error": "deposit_not_found"}

    # Trazabilidad: guardamos el ultimo estado visto, independientemente de si acredita.
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "last_payment_status": payment_status,
                "payment_id": payment_id,
                "webhook_last_seen": datetime.now(timezone.utc),
            }
        },
    )

    # Estados terminales sin credito (pago fallo/expiro/fue reembolsado): solo se marca.
    if payment_status in TERMINALNO_CREDIT_STATUSES:
        await db.crypto_deposits.update_one(
            {"order_id": order_id, "credited": False},
            {"$set": {"status": payment_status}},
        )
        return {"received": True, "processed": False, "status": payment_status}

    # Estados intermedios (waiting, confirming, sending, partially_paid, etc.):
    # se registra pero todavia no se acredita.
    if payment_status != "finished":
        return {"received": True, "processed": False, "status": payment_status}

    # Idempotencia + acreditacion atomica: el filtro credited=False garantiza que
    # solo el primer IPN que llegue con 'finished' pasa este punto.
    claimed = await db.crypto_deposits.find_one_and_update(
        {"order_id": order_id, "credited": False},
        {
            "$set": {
                "credited": True,
                "status": "finished",
                "credited_at": datetime.now(timezone.utc),
            }
        },
    )

    if not claimed:
        logger.info(f"NOWPayments webhook: order_id {order_id} ya estaba acreditado, ignorando duplicado")
        return {"received": True, "already_processed": True}

    # Se acredita lo REALMENTE pagado (no lo solicitado), con fallback al monto pedido.
    actually_paid = payload.get("actually_paid")
    credit_amount = actually_paid if actually_paid else claimed.get("amount")

    result = await credit_user(db, claimed["user_id"], claimed["currency"], credit_amount)

    if not result.get("ok"):
        logger.error(f"NOWPayments webhook: fallo al acreditar order_id {order_id}: {result}")
        # Revertimos el flag para permitir que un reintento (manual o del proximo IPN) acredite.
        await db.crypto_deposits.update_one(
            {"order_id": order_id},
            {"$set": {"credited": False, "credit_error": result.get("reason")}},
        )
        return {"received": True, "error": "credit_failed"}

    logger.info(
        f"NOWPayments: acreditado {credit_amount} {claimed['currency']} "
        f"a user {claimed['user_id']} (order {order_id})"
    )

    # Notificacion in-app + push. Best-effort: si falla, no revierte el credito ya aplicado.
    try:
        await create_notification(
            user_id=claimed["user_id"],
            title="Deposito confirmado",
            message=f"Se acreditaron {credit_amount} {CREDIT_LABELS.get(claimed['currency'], claimed['currency'])} a tu cuenta.",
            notification_type="credit_deposit",
            data={"order_id": order_id, "currency": claimed["currency"], "amount": str(credit_amount)},
        )
    except Exception as e:
        logger.warning(f"NOWPayments webhook: no se pudo enviar notificacion: {e}")

    return {"received": True, "processed": True, "status": "finished"}
