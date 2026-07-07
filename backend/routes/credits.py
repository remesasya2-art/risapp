"""
routes/credits.py — Endpoints de creditos cripto (deposito via NOWPayments).

Sub-paso 2: crear el deposito.
  POST /api/credits/deposit  -> crea un invoice en NOWPayments y devuelve invoice_url.

Guarda cada intento en la coleccion crypto_deposits con estado 'pending'.
NO acredita saldo aqui — eso lo hace el webhook (sub-paso 3) al confirmarse el pago.

Cumplimiento: corre assert_payment_allowed (IP + declaracion) ANTES de crear el cobro.
"""

import os
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
from services.credits import normalize_currency, CREDIT_LABELS

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
