"""
routes/credits.py — Endpoints de creditos cripto (deposito via NOWPayments).

Sub-paso 2: crear el deposito.

  POST /api/credits/deposit  -> crea un invoice en NOWPayments y devuelve invoice_url.

Sub-paso 3: confirmar el deposito.

  POST /api/credits/webhook  -> IPN de NOWPayments. Acredita balance_usdt/balance_usdc

  (NUNCA balance_ris — son billeteras totalmente separadas) cuando el pago se confirma.

Guarda cada intento en la coleccion crypto_deposits con estado 'pending'.

Cumplimiento: corre assert_payment_allowed (IP + declaracion) ANTES de crear el cobro.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
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
PAY_CURRENCY = {
    "usdt": "usdttrc20",   # USDT en TRON (TRC20)
    "usdc": "usdcerc20",   # USDC en Ethereum (ERC20)
}


class DepositRequest(BaseModel):
    currency: str            # "usdt" o "usdc" (lo elige el usuario en la app)
    amount: float            # cuanto quiere depositar (en esa cripto, 1 a 1)
    declared_not_restricted: bool = False  # checkbox de declaracion de jurisdiccion


@router.post("/deposit")
async def create_deposit(
    data: DepositRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Crea un deposito de creditos: valida jurisdiccion, crea invoice en NOWPayments,
    guarda el deposito 'pending' y devuelve el invoice_url para redirigir al usuario."""
    # 1) Cumplimiento de jurisdiccion (IP + declaracion). Lanza 403/400 si no pasa.
    assert_payment_allowed(request, declared_not_restricted=data.declared_not_restricted)
    # 2) Validar moneda y monto
    key = normalize_currency(data.currency)
    if key not in PAY_CURRENCY:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    if not data.amount or data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    pay_currency = PAY_CURRENCY[key]
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
    # 4) Crear el invoice en NOWPayments
    try:
        invoice = await nowpayments.create_invoice(
            price_amount=float(data.amount),
            price_currency=key,          # valoramos en la propia cripto (1 a 1)
            pay_currency=pay_currency,
            order_id=order_id,
            order_description=f"Deposito de {CREDIT_LABELS.get(key, key)}",
            ipn_callback_url=f"{PUBLIC_BASE_URL}/api/credits/webhook",
            success_url=f"{PUBLIC_BASE_URL}/credits?status=success",
            cancel_url=f"{PUBLIC_BASE_URL}/credits?status=cancel",
        )
    except Exception as e:
        logger.error(f"NOWPayments create_invoice failed for {order_id}: {e}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id}, {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")
    invoice_url = invoice.get("invoice_url")
    if not invoice_url:
        logger.error(f"NOWPayments sin invoice_url para {order_id}: {invoice}")
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")
    # Guardar el id de invoice para trazabilidad
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {"$set": {"invoice_id": invoice.get("id"), "invoice_url": invoice_url}},
    )
    return {"invoice_url": invoice_url, "order_id": order_id}


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
