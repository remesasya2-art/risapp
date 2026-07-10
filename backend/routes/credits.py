"""
Rutas de creditos cripto (NOWPayments).

Este modulo maneja depositos en cripto (USDT / USDC) usando NOWPayments.
El balance cripto (balance_usdt / balance_usdc) es TOTALMENTE SEPARADO de
balance_ris. El webhook NUNCA toca balance_ris ni la logica de PIX/MercadoPago.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, HTTPException
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

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# Moneda de pago real en NOWPayments segun la cripto elegida
PAY_CURRENCY = {
    "usdt": "usdttrc20",
    "usdc": "usdcerc20",
}


class DepositRequest(BaseModel):
    currency: str            # "usdt" o "usdc"
    amount: float            # cuanto quiere depositar (en esa cripto, 1 a 1)
    declared_not_restricted: bool = False


@router.post("/deposit")
async def create_deposit(
    payload: DepositRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    # 1) Validar jurisdiccion (no toca balance_ris)
    assert_payment_allowed(request, payload.declared_not_restricted)

    # 2) Validar moneda
    currency = normalize_currency(payload.currency)
    if currency not in PAY_CURRENCY:
        raise HTTPException(status_code=400, detail="Moneda no soportada")

    # 3) Validar monto
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Monto invalido")

    # 4) Crear orden pendiente
    order_id = str(uuid.uuid4())
    deposit_doc = {
        "order_id": order_id,
        "user_id": str(current_user.id),
        "currency": currency,
        "amount": float(payload.amount),
        "pay_currency": PAY_CURRENCY[currency],
        "status": "pending",
        "credited": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.crypto_deposits.insert_one(deposit_doc)

    # 5) Crear factura en NOWPayments
    try:
        invoice = await nowpayments.create_invoice(
            order_id=order_id,
            price_amount=float(payload.amount),
            price_currency=currency,
            pay_currency=PAY_CURRENCY[currency],
            ipn_callback_url=f"{PUBLIC_BASE_URL}/credits/webhook",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error creando factura NOWPayments: %s", exc)
        await db.crypto_deposits.update_one(
            {"order_id": order_id},
            {"$set": {"status": "error", "updated_at": datetime.now(timezone.utc)}},
        )
        raise HTTPException(status_code=502, detail="No se pudo crear la factura")

    invoice_url = invoice.get("invoice_url")
    if not invoice_url:
        raise HTTPException(status_code=502, detail="Respuesta invalida de NOWPayments")

    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {"$set": {"invoice_id": invoice.get("id"), "updated_at": datetime.now(timezone.utc)}},
    )

    return {"order_id": order_id, "invoice_url": invoice_url}


TERMINAL_NO_CREDIT_STATUSES = {"failed", "expired", "refunded"}


@router.post("/webhook")
async def nowpayments_webhook(request: Request):
    # 1) Verificar firma HMAC
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")
    if not nowpayments.verify_ipn_signature(raw_body, signature):
        logger.warning("Firma IPN invalida")
        raise HTTPException(status_code=401, detail="Firma invalida")

    # 2) Parsear payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Payload invalido")

    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    if not order_id:
        raise HTTPException(status_code=400, detail="Falta order_id")

    # 3) Buscar deposito
    deposit = await db.crypto_deposits.find_one({"order_id": order_id})
    if not deposit:
        logger.warning("Deposito no encontrado para order_id=%s", order_id)
        raise HTTPException(status_code=404, detail="Deposito no encontrado")

    # 4) Guardar ultimo estado
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {"$set": {"status": payment_status, "updated_at": datetime.now(timezone.utc)}},
    )

    # 5) Estados terminales sin credito
    if payment_status in TERMINAL_NO_CREDIT_STATUSES:
        return {"ok": True}

    # 6) Solo acreditar cuando esta finished/confirmed
    if payment_status not in ("finished", "confirmed"):
        return {"ok": True}

    # 7) Acreditar de forma idempotente (credited=False -> True)
    updated = await db.crypto_deposits.find_one_and_update(
        {"order_id": order_id, "credited": False},
        {"$set": {"credited": True, "credited_at": datetime.now(timezone.utc)}},
    )
    if not updated:
        # Ya fue acreditado antes: idempotente
        return {"ok": True}

    currency = updated["currency"]
    amount = float(updated["amount"])
    user_id = updated["user_id"]

    # 8) Acreditar balance cripto (NUNCA balance_ris)
    try:
        await credit_user(user_id=user_id, currency=currency, amount=amount)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error acreditando usuario: %s", exc)
        # Revertir el flag para reintentar luego
        await db.crypto_deposits.update_one(
            {"order_id": order_id},
            {"$set": {"credited": False}, "$unset": {"credited_at": ""}},
        )
        raise HTTPException(status_code=500, detail="Error acreditando")

    # 9) Notificar (best-effort)
    try:
        label = CREDIT_LABELS.get(currency, currency.upper())
        await create_notification(
            user_id=user_id,
            title="Deposito acreditado",
            body=f"Se acreditaron {amount} {label} a tu balance.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo crear notificacion: %s", exc)

    return {"ok": True, "finished": True}
