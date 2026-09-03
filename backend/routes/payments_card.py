"""
Card Payment routes — Mercado Pago Checkout Bricks integration.

Flow:
  1. Frontend renders Card Payment Brick, tokenizes the card client-side.
  2. Frontend POSTs the token + amount + payer info to /payments/card/process.
  3. Backend validates amount, calls MP /v1/payments with X-Idempotency-Key.
  4. If status="approved":
        - Credit RIS to user (same rule as PIX: 1 BRL = 1 RIS).
        - Credit Mercado Pago bank in accounting (NET, after fee).
        - Register fee in gateway_fee_ledger (accounting v11).
        - Send notification + email.

Business rules (per user spec, 2026-05-22):
  - Single payment only (installments=1).
  - Min R$5, max R$5000.
  - Customer pays the fee (added on top of the desired RIS amount).
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from database import db
from models.user import User
from routes.dependencies import get_current_user
from services.notifications import create_notification
from services import bancos, pagos_una_sola_vez, saldos

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/card", tags=["payments-card"])

MP_API_BASE = "https://api.mercadopago.com"

# Default fee config (Mercado Pago Brazil — public rates 2026)
# Stored in app_settings.card_fees so admin can override later (GatewayConfig P3).
DEFAULT_CARD_FEES = {
    "credit_pct": 4.49,   # % over transaction_amount
    "debit_pct": 1.99,
    "flat_brl": 0.40,     # fixed cents per transaction
}

MIN_AMOUNT_BRL = 5.0
MAX_AMOUNT_BRL = 5000.0


# ─── Schemas ──────────────────────────────────────────────────────────────
class PayerIdentification(BaseModel):
    type: str = "CPF"
    number: str


class CardPaymentInput(BaseModel):
    token: str
    amount_ris: float = Field(..., gt=0, description="RIS the user wants to receive (=BRL netto)")
    payment_method_id: str
    payment_type_id: str = Field(default="credit_card", description="credit_card | debit_card")
    payer_email: EmailStr
    identification: PayerIdentification
    issuer_id: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────
async def _get_card_fees() -> dict:
    """Read card fee config from app_settings (with sensible defaults)."""
    doc = await db.app_settings.find_one({"key": "card_fees"})
    if not doc:
        return DEFAULT_CARD_FEES
    return {**DEFAULT_CARD_FEES, **(doc.get("value") or {})}


def _calc_fee(amount_brl_net: float, payment_type_id: str, fees: dict) -> float:
    """Compute total MP fee given the NET amount the user wants to receive."""
    pct = fees["debit_pct"] if payment_type_id == "debit_card" else fees["credit_pct"]
    return round(amount_brl_net * (pct / 100.0) + fees["flat_brl"], 2)


async def _credit_mp_bank_card(payment_id: str, client_name: str, amount_brl_net: float):
    """Same logic as gestor_pix._credit_mercadopago_bank but for cards.
    Imports kept local to avoid circular imports."""
    # Un `upsert`, no un `find_one` seguido de un `insert_one`. Este camino y el
    # de la tarjeta creaban la cuenta por su cuenta, cada uno con su propio
    # `bank_id` al azar: entrando los dos a la vez quedaban DOS filas
    # "Mercado Pago" en BRL con el saldo repartido. Ver services/bancos.py.
    bank = await bancos.asegurar_pasarela(
        db, name="Mercado Pago", currency="BRL", prefijo_id="mp")

    # Igual que en Mercado Pago: `float()` sobre un Decimal128 levanta TypeError.
    from services.money import to_float as _to_float
    _mov = await bancos.ajustar(db, bank["bank_id"], amount_brl_net)
    new_balance = _to_float(_mov["saldo_nuevo"])
    await db.bank_ledger.insert_one({
        "bank_id": bank["bank_id"],
        "bank_name": "Mercado Pago",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "type": "entrada",
        "concept": f"Recarga Tarjeta: {client_name} (MP {payment_id[:12]})",
        "amount": float(amount_brl_net),
        "balance_after": new_balance,
        "reference": str(payment_id),
        "notes": "Recarga automática vía Mercado Pago (Tarjeta)",
        "source": "mercadopago_card",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _register_card_fee(payment_id: str, fee_brl: float, gross_brl: float):
    """Write fee to gateway_fee_ledger (Accounting Engine v11)."""
    await db.gateway_fee_ledger.insert_one({
        "ledger_id": f"gfl_card_{uuid.uuid4().hex[:10]}",
        "gateway": "mercadopago",
        "payment_method": "card",
        "external_payment_id": str(payment_id),
        "currency": "BRL",
        "gross_amount": float(gross_brl),
        "fee_deducted": float(fee_brl),
        "net_amount": round(gross_brl - fee_brl, 2),
        "is_reconciled_with_invoice": False,
        "hidden_from_admin": False,
        "created_at": datetime.now(timezone.utc),
    })


# ─── Endpoints ────────────────────────────────────────────────────────────
@router.get("/config")
async def get_card_config(current_user: User = Depends(get_current_user)):
    """Frontend bootstrap: public key + fee schedule + limits."""
    fees = await _get_card_fees()
    return {
        "public_key": os.environ.get("MERCADOPAGO_PUBLIC_KEY"),
        "fees": fees,
        "min_amount_brl": MIN_AMOUNT_BRL,
        "max_amount_brl": MAX_AMOUNT_BRL,
        "locale": "pt-BR",
        "currency": "BRL",
    }


@router.post("/quote")
async def quote_card_payment(
    amount_ris: float,
    payment_type_id: str = "credit_card",
    current_user: User = Depends(get_current_user),
):
    """Preview the total amount that will be charged on the card,
    given the desired RIS recharge amount."""
    if amount_ris < MIN_AMOUNT_BRL or amount_ris > MAX_AMOUNT_BRL:
        raise HTTPException(
            status_code=400,
            detail=f"Monto debe estar entre R$ {MIN_AMOUNT_BRL:.2f} y R$ {MAX_AMOUNT_BRL:.2f}",
        )
    fees = await _get_card_fees()
    fee = _calc_fee(amount_ris, payment_type_id, fees)
    total = round(amount_ris + fee, 2)
    return {
        "amount_ris": amount_ris,
        "amount_brl_net": amount_ris,
        "fee_brl": fee,
        "total_charged_brl": total,
        "payment_type_id": payment_type_id,
    }


@router.post("/process")
async def process_card_payment(
    body: CardPaymentInput,
    current_user: User = Depends(get_current_user),
):
    """Submit the tokenized card to Mercado Pago and credit RIS on approval."""
    # ── Validation ───────────────────────────────────────────────────────
    if body.amount_ris < MIN_AMOUNT_BRL or body.amount_ris > MAX_AMOUNT_BRL:
        raise HTTPException(
            status_code=400,
            detail=f"Monto debe estar entre R$ {MIN_AMOUNT_BRL:.2f} y R$ {MAX_AMOUNT_BRL:.2f}",
        )
    if body.payment_type_id not in ("credit_card", "debit_card"):
        raise HTTPException(status_code=400, detail="Tipo de tarjeta inválido")

    if current_user.verification_status != "verified":
        raise HTTPException(
            status_code=403,
            detail="Debes verificar tu cuenta antes de pagar con tarjeta",
        )

    access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
    if not access_token:
        raise HTTPException(status_code=500, detail="MP no configurado")

    # ── Fee calculation ──────────────────────────────────────────────────
    fees = await _get_card_fees()
    fee_brl = _calc_fee(body.amount_ris, body.payment_type_id, fees)
    total_brl_charged = round(body.amount_ris + fee_brl, 2)

    # ── Call MP Payments API ─────────────────────────────────────────────
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }
    payload = {
        "transaction_amount": total_brl_charged,
        "token": body.token,
        "description": f"Recarga RIS {body.amount_ris:.2f} BRL",
        "installments": 1,
        "payment_method_id": body.payment_method_id,
        "payer": {
            "email": body.payer_email,
            "identification": {
                "type": body.identification.type,
                "number": body.identification.number,
            },
        },
        "capture": True,
        "binary_mode": True,
        "metadata": {
            "user_id": current_user.user_id,
            "origin": "card_brick",
            "amount_ris": body.amount_ris,
            "fee_brl": fee_brl,
        },
        "external_reference": f"user_{current_user.user_id}_{uuid.uuid4().hex[:8]}",
    }
    if body.issuer_id:
        payload["issuer_id"] = body.issuer_id

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            mp_resp = await client.post(
                f"{MP_API_BASE}/v1/payments", json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.error(f"MP API network error: {exc}")
        raise HTTPException(status_code=502, detail="Error conectando con Mercado Pago")

    mp_data = {}
    try:
        mp_data = mp_resp.json()
    except Exception:
        pass

    if mp_resp.status_code >= 400:
        logger.error(f"MP API error {mp_resp.status_code}: {mp_data}")
        raise HTTPException(
            status_code=400,
            detail=mp_data.get("message") or "Error procesando el pago en Mercado Pago",
        )

    payment_id = str(mp_data.get("id") or "")
    status_mp = mp_data.get("status")
    status_detail = mp_data.get("status_detail", "")

    logger.info(
        f"MP card payment created: id={payment_id} status={status_mp} "
        f"detail={status_detail} user={current_user.user_id}"
    )

    # Persist attempt
    await db.card_payments.insert_one({
        "payment_id": payment_id,
        "user_id": current_user.user_id,
        "amount_ris": body.amount_ris,
        "amount_brl_net": body.amount_ris,
        "fee_brl": fee_brl,
        "total_charged_brl": total_brl_charged,
        "payment_method_id": body.payment_method_id,
        "payment_type_id": body.payment_type_id,
        "status": status_mp,
        "status_detail": status_detail,
        "mp_response": mp_data,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc),
    })

    # ── Process side effects on approval ─────────────────────────────────
    if status_mp == "approved" and payment_id:
        # Reclamar el evento ANTES de acreditar. Antes esto era un `find_one`
        # y después un `insert_one`: entre los dos hay una ventana, y el
        # webhook de Mercado Pago entra justo ahí —es el caso para el que este
        # guard fue escrito—, con lo cual los dos leían que no había nada y los
        # dos acreditaban. Ver services/pagos_una_sola_vez.py.
        if await pagos_una_sola_vez.reclamar(
                db, f"card_{payment_id}", proveedor="mercadopago_card"):

            # 1. Credit RIS to user, y asentar en la misma operación.
            _card_mov = await saldos.mover(
                db, current_user.user_id, body.amount_ris,
                movimiento="pago_tarjeta",
                reference_kind="card_payment",
                reference_id=payment_id,
                actor_type="user",
                actor_id=current_user.user_id,
                notes="Recarga con tarjeta",
            )
            _card_user = _card_mov["usuario"]

            # 2. Notification
            await create_notification(
                user_id=current_user.user_id,
                title="💳 Pago con Tarjeta Aprobado",
                message=f"Se han añadido R$ {body.amount_ris:.2f} a tu saldo.",
                notification_type="card_received",
                data={"payment_id": payment_id, "amount": body.amount_ris},
            )

            # 3. Accounting (Mercado Pago bank + gateway fee ledger)
            try:
                await _credit_mp_bank_card(
                    payment_id=payment_id,
                    client_name=current_user.name or "Cliente",
                    amount_brl_net=body.amount_ris,
                )
                await _register_card_fee(
                    payment_id=payment_id,
                    fee_brl=fee_brl,
                    gross_brl=total_brl_charged,
                )
            except Exception as exc:
                logger.warning(f"Failed to write card payment to accounting: {exc}")

    return {
        "status": status_mp,
        "status_detail": status_detail,
        "payment_id": payment_id,
        "amount_ris_credited": body.amount_ris if status_mp == "approved" else 0,
        "total_charged_brl": total_brl_charged,
        "fee_brl": fee_brl,
    }
