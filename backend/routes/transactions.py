"""
Transaction routes - Withdrawals, Recharges, Beneficiaries
"""
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from database import db

from services.money import from_db, to_float, to_decimal, to_decimal128
from services.rate_engine import apply_rate_adjustment, load_auto_rate_config
from services import nowpayments

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://www.risappbr.com")
CRYPTO_NETWORK_TICKER = {"usdt": "usdttrc20", "usdc": "usdc"}

# Campos de dinero de una transaccion (para lectura tolerante float/Decimal128)
_TX_MONEY_2 = (
    "amount_input", "amount_output", "amount_ris", "amount_ves", "amount_brl",
    "balance_before", "balance_after", "balance_after_ris",
    "fee", "commission_amount", "commission",
    "monto_origen", "monto_destino", "monto_input_total", "monto_output_total",
)

def _normalize_tx_money(tx):
    """Normaliza los montos de una transaccion a numeros limpios (tolera float y Decimal128)."""
    if not tx:
        return tx
    for _k in _TX_MONEY_2:
        if _k in tx and tx[_k] is not None:
            tx[_k] = to_float(from_db(tx[_k]))
    if tx.get("rate") is not None:
        tx["rate"] = to_float(from_db(tx["rate"], places=6), places=6)
    return tx
from models.user import User
from models.requests import WithdrawalRequest, BeneficiaryCreate
from routes.dependencies import get_current_user, get_verified_user
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.idempotency import claim_idempotency, store_idempotency_result
from services.notifications import create_notification
from services.centro_gestion import registrar_evento
from utils.helpers import get_next_withdrawal_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transactions"])

# ============== BENEFICIARIES ==============

@router.post("/beneficiaries")
async def create_beneficiary(request: BeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Create a new beneficiary"""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"

    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "id_document": request.id_document.strip(),
        "bank": request.bank.strip(),
        "bank_code": request.bank_code,
        "phone_number": request.phone_number,
        "account_number": request.account_number,
        "payment_type": request.payment_type,
        "created_at": datetime.now(timezone.utc)
    }

    await db.beneficiaries.insert_one(beneficiary)

    return {"message": "Beneficiario creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries")
async def get_beneficiaries(current_user: User = Depends(get_current_user)):
    """Get user's beneficiaries"""
    beneficiaries = await db.beneficiaries.find(
        {"user_id": current_user.user_id}
    ).to_list(100)

    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "id_document": b.get("id_document"),
            "bank": b.get("bank"),
            "bank_code": b.get("bank_code"),
            "phone_number": b.get("phone_number"),
            "account_number": b.get("account_number"),
            "payment_type": b.get("payment_type", "transferencia"),
            "created_at": b.get("created_at")
        }
        for b in beneficiaries
    ]

@router.delete("/beneficiaries/{beneficiary_id}")
async def delete_beneficiary(beneficiary_id: str, current_user: User = Depends(get_current_user)):
    """Delete a beneficiary"""
    result = await db.beneficiaries.delete_one({
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    return {"message": "Beneficiario eliminado"}

# ============== WITHDRAWALS ==============

# ---- RIS → Reais (Brasil, pago por PIX) ----

class BrBeneficiaryCreate(BaseModel):
    full_name: str
    cpf: str
    pix_key: str

class ReaisSendRequest(BaseModel):
    beneficiary_id: str
    amount: float   # en RIS (1 RIS = 1 R$)
    idempotency_key: Optional[str] = None

@router.post("/beneficiaries/br")
async def create_br_beneficiary(request: BrBeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Crea un beneficiario en Brasil (pago por PIX en reais)."""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "cpf": request.cpf.strip(),
        "pix_key": request.pix_key.strip(),
        "pais": "BR",
        "payment_type": "pix_br",
        "created_at": datetime.now(timezone.utc),
    }
    await db.beneficiaries.insert_one(beneficiary)
    return {"message": "Beneficiario (Brasil) creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries/br")
async def get_br_beneficiaries(current_user: User = Depends(get_current_user)):
    """Lista los beneficiarios en Brasil del usuario."""
    rows = await db.beneficiaries.find(
        {"user_id": current_user.user_id, "pais": "BR"}
    ).to_list(100)
    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "cpf": b.get("cpf"),
            "pix_key": b.get("pix_key"),
            "payment_type": "pix_br",
            "created_at": b.get("created_at"),
        }
        for b in rows
    ]

@router.post("/reais/send")
async def create_reais_send(request: ReaisSendRequest, current_user: User = Depends(get_current_user)):
    """Crea una orden de envío RIS → Reais (1 RIS = 1 R$, sin comisión: ya viene
    incluida en la recarga). Queda pendiente para que el super_admin la pague
    por PIX en Brasil desde el área de Órdenes por procesar."""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    # Idempotencia: evita duplicar el envío por doble clic / reintento de red.
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, "reais_send", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")
    # Descuento atómico de saldo RIS
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": to_decimal128(to_decimal(request.amount))}},
        {"$inc": {"balance_ris": to_decimal128(-to_decimal(request.amount))}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id,
        "pais": "BR",
    })
    if not beneficiary:
        # Devolver el saldo si el beneficiario no existe
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        raise HTTPException(status_code=404, detail="Beneficiario de Brasil no encontrado")
    amount_brl = request.amount  # 1 a 1
    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "cpf": beneficiary.get("cpf"),
        "pix_key": beneficiary.get("pix_key"),
        "payment_type": "pix_br",
        "pais": "BR",
    }
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_brl,
        "currency_input": "RIS",
        "currency_output": "BRL",
        "rate": 1.0,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
        "whatsapp_active": False,
    }
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        logger.error(f"Fallo al registrar envío a Brasil {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

    # Libro mayor RIS (append-only). Nunca interrumpe el envío.
    try:
        from services.ledger import record_ris_entry
        balance_after_ris = user.get("balance_ris")
        await record_ris_entry(
            user_id=current_user.user_id,
            movement_type="envio_reais",
            amount=request.amount,
            direction="debit",
            account="balance_ris",
            balance_before=(balance_after_ris + request.amount) if balance_after_ris is not None else None,
            balance_after=balance_after_ris,
            reference_kind="transaction",
            reference_id=tx_id,
            transaction_id=tx_id,
            display_id=display_id,
            actor_type="user",
            actor_id=current_user.user_id,
            actor_email=user.get("email"),
            rate=1.0,
            rate_kind="ris_to_brl",
            amount_output=amount_brl,
            currency_output="BRL",
            counterparty=beneficiary_data,
            user_snapshot={"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user.get("role", "user")},
            notes="Envío RIS → Reais (PIX Brasil)",
        )
    except Exception as e:
        logger.warning(f"Ledger envio_reais no registrado: {e}")

    await create_notification(
        user_id=current_user.user_id,
        title="Envío a Brasil solicitado",
        message=f"Tu envío de {request.amount:.2f} RIS (R$ {amount_brl:.2f}) a {beneficiary.get('full_name')} fue recibido y está en cola.",
        notification_type="withdrawal_pending",
    )
    _resp_reais = {"success": True, "transaction_id": tx_id, "display_id": display_id, "amount_brl": amount_brl}
    await store_idempotency_result(current_user.user_id, "reais_send", request.idempotency_key, _resp_reais)
    return _resp_reais

@router.post("/withdraw")
@router.post("/withdrawal/create")
async def create_withdrawal(request: WithdrawalRequest, current_user: User = Depends(get_current_user)):
    """Create a withdrawal request"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    # Idempotencia: evita duplicar el envío por doble clic / reintento de red.
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, "withdraw_ves", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")
    # 1) Validar beneficiario ANTES de tocar el saldo (evita débito sin destino)
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) Leer y validar la tasa ANTES de debitar (fail-closed: sin tasa válida no se procesa)
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    _base_rtv = (rate or {}).get("ris_to_ves")
    if not _base_rtv or _base_rtv <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")
    # Aplicar el mismo ajuste de horario que /api/rate para que el envío coincida con la cotización
    _cfg = await load_auto_rate_config(db)
    _eff = apply_rate_adjustment({"ris_to_ves": _base_rtv}, _cfg)
    ris_to_ves = _eff.get("ris_to_ves") or _base_rtv

    amount_ves = round(request.amount * ris_to_ves, 2)

    # Preparar datos de la transacción (antes del débito; no dependen del saldo)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()

    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia")
    }

    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": "RIS",
        "currency_output": "VES",
        "rate": ris_to_ves,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
        "whatsapp_active": False
    }

    # 3) Débito atómico (impide sobregiro y condiciones de carrera)
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": to_decimal128(to_decimal(request.amount))}},
        {"$inc": {"balance_ris": to_decimal128(-to_decimal(request.amount))}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")

    # 4) Crear el registro; si falla, devolver el saldo (compensación) para no perder RIS
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        logger.error(f"Fallo al registrar retiro {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el retiro. Tu saldo no fue afectado.")

    # Libro mayor RIS (append-only). Nunca interrumpe el envío.
    try:
        from services.ledger import record_ris_entry
        balance_after_ris = user.get("balance_ris")
        await record_ris_entry(
            user_id=current_user.user_id,
            movement_type="envio_ves",
            amount=request.amount,
            direction="debit",
            account="balance_ris",
            balance_before=(balance_after_ris + request.amount) if balance_after_ris is not None else None,
            balance_after=balance_after_ris,
            reference_kind="transaction",
            reference_id=tx_id,
            transaction_id=tx_id,
            display_id=display_id,
            actor_type="user",
            actor_id=current_user.user_id,
            actor_email=user.get("email"),
            rate=ris_to_ves,
            rate_kind="ris_to_ves",
            amount_output=amount_ves,
            currency_output="VES",
            counterparty=beneficiary_data,
            user_snapshot={"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user.get("role", "user")},
            notes="Envío RIS → VES",
        )
    except Exception as e:
        logger.warning(f"Ledger envio_ves no registrado: {e}")

    # Notify user
    await create_notification(
        user_id=current_user.user_id,
        title="Retiro Solicitado",
        message=f"Tu retiro de {request.amount} RIS ({amount_ves:.2f} VES) ha sido recibido y esta en cola.",
        notification_type="withdrawal_pending"
    )

    # Send to WhatsApp queue
    try:
        await send_next_pending_withdrawal_whatsapp()
    except Exception as e:
        logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

    # Registrar en CentroGestion
    try:
        await registrar_evento(
            tipo="retiro_ves",
            transaction_id=tx_id,
            user_id=current_user.user_id,
            user_email=user.get("email"),
            user_name=user.get("name") or user.get("full_name"),
            amount_input=request.amount,
            amount_output=amount_ves,
            currency_input="RIS",
            currency_output="VES",
            status="pending",
            metadata={
                "display_id": display_id,
                "rate": ris_to_ves,
                "beneficiary": beneficiary_data
            }
        )
    except Exception as e:
        logger.warning(f"registrar_evento fallo: {e}")

    _resp_withdraw = {
        "message": "Retiro solicitado exitosamente",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount,
        "amount_ves": amount_ves,
        "rate": ris_to_ves
    }
    await store_idempotency_result(current_user.user_id, "withdraw_ves", request.idempotency_key, _resp_withdraw)
    return _resp_withdraw

# ---- Saldo cripto (USDT / USDC) → VES ----
# Replica exactamente el mismo patrón de seguridad de create_withdrawal
# (idempotencia, validar beneficiario antes de tocar saldo, tasa fail-closed,
# débito atómico con compensación si falla el registro), pero debitando
# balance_usdt/balance_usdc en vez de balance_ris.

class CryptoSendRequest(BaseModel):
    currency: str            # "usdt" o "usdc"
    amount: float            # monto en USDT/USDC
    beneficiary_id: str
    network: Optional[str] = None
    use_balance: bool = False   # True: descuenta de balance_usdt/usdc (saldo de reembolsos). False (default): pago directo nuevo via NOWPayments.
    idempotency_key: Optional[str] = None

@router.post("/withdraw-crypto")
async def create_crypto_withdrawal(request: CryptoSendRequest, current_user: User = Depends(get_current_user)):
    """Crea un envio de USDT/USDC a un beneficiario en VES.

    Dos caminos:
      - use_balance=True: descuenta de balance_usdt/balance_usdc (saldo que el
        usuario tiene por un reembolso previo). Debito atomico, orden queda
        "pending" de una vez, sin pasar por NOWPayments.
      - use_balance=False (default): sin custodia previa. Genera un pago
        NOWPayments ligado a la orden ("awaiting_payment"); el webhook la pasa
        a "pending" al confirmarse el pago.
    En ambos casos la orden termina en el mismo lugar: "pending", visible en
    Ordenes por procesar, con el mismo pipeline de claim/process/approve/reject.
    """
    from services.credits import normalize_currency

    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    key = normalize_currency(request.currency)
    if key not in CRYPTO_NETWORK_TICKER:
        raise HTTPException(status_code=400, detail="Moneda no soportada")

    idem_scope = f"withdraw_{key}"
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, idem_scope, request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")

    # 1) Validar beneficiario ANTES de tocar saldo o generar el pago
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) Leer y validar la tasa ANTES de tocar saldo o generar el pago (fail-closed)
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    rate_field = "usdtris_to_ves" if key == "usdt" else "usdcris_to_ves"
    crypto_to_ves = (rate_doc or {}).get(rate_field)
    if not crypto_to_ves or crypto_to_ves <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")

    amount_ves = round(request.amount * crypto_to_ves, 2)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()

    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia")
    }

    # ---- Camino A: usar saldo disponible (reembolsos previos) ----
    if request.use_balance:
        from services.credits import credit_field_for, to_credit_decimal
        from bson.decimal128 import Decimal128

        field = credit_field_for(request.currency)
        amount_dec = to_credit_decimal(request.amount)
        user = await db.users.find_one_and_update(
            {"user_id": current_user.user_id, field: {"$gte": Decimal128(amount_dec)}},
            {"$inc": {field: Decimal128(-amount_dec)}},
            return_document=True
        )
        if user is None:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")

        transaction = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "user_id": current_user.user_id,
            "type": "withdrawal",
            "amount_input": request.amount,
            "amount_output": amount_ves,
            "currency_input": key.upper(),
            "currency_output": "VES",
            "rate": crypto_to_ves,
            "status": "pending",
            "beneficiary_id": request.beneficiary_id,
            "beneficiary_data": beneficiary_data,
            "funded_from": "balance",
            "created_at": datetime.now(timezone.utc),
            "whatsapp_active": False,
        }
        try:
            await db.transactions.insert_one(transaction)
        except Exception as e:
            await db.users.update_one(
                {"user_id": current_user.user_id},
                {"$inc": {field: Decimal128(amount_dec)}}
            )
            logger.error(f"Fallo al registrar envío cripto (saldo) {tx_id}, saldo devuelto: {e}")
            raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

        try:
            from services.ledger_crypto import record_crypto_entry
            balance_after = user.get(field)
            balance_after_f = float(to_credit_decimal(balance_after)) if balance_after is not None else None
            await record_crypto_entry(
                user_id=current_user.user_id,
                currency=key,
                movement_type="envio_ves",
                amount=float(amount_dec),
                direction="debit",
                balance_before=(balance_after_f + float(amount_dec)) if balance_after_f is not None else None,
                balance_after=balance_after_f,
                reference_kind="transaction",
                reference_id=tx_id,
                actor_type="user",
                actor_id=current_user.user_id,
                actor_email=user.get("email"),
                metadata={"display_id": display_id, "beneficiary": beneficiary_data, "funded_from": "balance"},
                notes=f"Envío {key.upper()} → VES (desde saldo)",
            )
        except Exception as e:
            logger.warning(f"Ledger cripto envio_ves (saldo) no registrado: {e}")

        await create_notification(
            user_id=current_user.user_id,
            title="Envío Solicitado",
            message=f"Tu envío de {request.amount} {key.upper()} ({amount_ves:.2f} VES) ha sido recibido y está en cola.",
            notification_type="withdrawal_pending",
        )
        try:
            await send_next_pending_withdrawal_whatsapp()
        except Exception as e:
            logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

        _resp_balance = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "status": "pending",
            "funded_from": "balance",
            "amount_crypto": request.amount,
            "amount_ves": amount_ves,
            "rate": crypto_to_ves,
            "currency": key.upper(),
        }
        await store_idempotency_result(current_user.user_id, idem_scope, request.idempotency_key, _resp_balance)
        return _resp_balance

    # ---- Camino B: pago directo nuevo (sin custodia), via NOWPayments ----
    pay_currency = (request.network or CRYPTO_NETWORK_TICKER[key]).strip().lower()
    if not pay_currency.startswith(key):
        raise HTTPException(status_code=400, detail="La red elegida no corresponde a la moneda seleccionada.")

    order_id = f"send_{key}_{current_user.user_id}_{uuid.uuid4().hex[:12]}"
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": key.upper(),
        "currency_output": "VES",
        "rate": crypto_to_ves,
        "status": "awaiting_payment",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "payment_order_id": order_id,
        "pay_currency": pay_currency,
        "funded_from": "payment",
        "created_at": datetime.now(timezone.utc),
        "whatsapp_active": False,
    }
    await db.transactions.insert_one(transaction)

    try:
        payment = await nowpayments.create_payment(
            price_amount=float(request.amount),
            price_currency="usd",
            pay_currency=pay_currency,
            order_id=order_id,
            order_description=f"Envío {key.upper()} a {beneficiary_data.get('full_name') or 'beneficiario'}",
            ipn_callback_url=f"{PUBLIC_BASE_URL}/api/crypto-send/webhook",
            is_fee_paid_by_user=True,
        )
    except Exception as e:
        await db.transactions.update_one({"transaction_id": tx_id}, {"$set": {"status": "payment_error"}})
        logger.error(f"NOWPayments create_payment fallo para envío {tx_id}: {e}")
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")

    pay_address = payment.get("pay_address")
    pay_amount = payment.get("pay_amount")
    if not pay_address or not pay_amount:
        await db.transactions.update_one({"transaction_id": tx_id}, {"$set": {"status": "payment_error"}})
        logger.error(f"NOWPayments sin pay_address/pay_amount para envío {tx_id}: {payment}")
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")

    await db.transactions.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "payment_id": payment.get("payment_id"),
            "pay_address": pay_address,
            "pay_amount": pay_amount,
            "payin_extra_id": payment.get("payin_extra_id"),
            "network": payment.get("network"),
        }}
    )

    _resp_crypto = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "order_id": order_id,
        "status": "awaiting_payment",
        "funded_from": "payment",
        "pay_address": pay_address,
        "pay_amount": pay_amount,
        "pay_currency": pay_currency,
        "payin_extra_id": payment.get("payin_extra_id"),
        "network": payment.get("network"),
        "network_label": payment.get("network") or pay_currency,
        "amount_crypto": request.amount,
        "amount_ves": amount_ves,
        "rate": crypto_to_ves,
        "currency": key.upper(),
    }
    await store_idempotency_result(current_user.user_id, idem_scope, request.idempotency_key, _resp_crypto)
    return _resp_crypto


@router.get("/withdraw-crypto/{transaction_id}/status")
async def get_crypto_withdrawal_status(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Polling del estado de una orden de envío cripto (para la pantalla de pago)."""
    tx = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {"_id": 0, "status": 1, "amount_output": 1}
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return {"transaction_id": transaction_id, "status": tx.get("status"), "amount_ves": tx.get("amount_output")}


@router.post("/crypto-send/webhook")
async def webhook_crypto_send(request: Request):
    """IPN de NOWPayments para envíos directos (distinto del webhook de depósitos
    en /credits/webhook — este busca en 'transactions', no en 'crypto_deposits')."""
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")

    try:
        payload = json.loads(raw_body or b"{}")
    except Exception:
        payload = {}
    preview_order_id = payload.get("order_id")
    preview_status = payload.get("payment_status")
    logger.info(f"crypto-send webhook: intento recibido order_id={preview_order_id} status={preview_status}")

    matched = nowpayments.verify_ipn_signature(raw_body, signature)
    if not matched:
        logger.warning(f"crypto-send webhook: firma invalida order_id={preview_order_id} status={preview_status}")
        raise HTTPException(status_code=401, detail="invalid_signature")
    logger.info(f"crypto-send webhook: firma valida (variante={matched}) order_id={preview_order_id}")

    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    if not order_id:
        return {"received": True, "error": "no_order_id"}

    tx = await db.transactions.find_one({"payment_order_id": order_id})
    if not tx:
        logger.warning(f"crypto-send webhook: order_id {order_id} no encontrado")
        return {"received": True, "error": "order_not_found"}

    await db.transactions.update_one(
        {"payment_order_id": order_id},
        {"$set": {"payment_status_last": payment_status, "ipn_last_seen": datetime.now(timezone.utc)}}
    )

    if payment_status in ("failed", "expired", "refunded"):
        await db.transactions.update_one(
            {"payment_order_id": order_id, "status": "awaiting_payment"},
            {"$set": {"status": "payment_failed"}}
        )
        return {"received": True, "processed": False, "status": payment_status}

    actually_paid = payload.get("actually_paid")
    pay_amount = tx.get("pay_amount")
    is_finished = payment_status == "finished"
    is_acceptable_partial = False
    if payment_status == "partially_paid" and actually_paid and pay_amount:
        try:
            is_acceptable_partial = (float(actually_paid) / float(pay_amount)) >= 0.99
        except (TypeError, ValueError, ZeroDivisionError):
            is_acceptable_partial = False

    if not is_finished and not is_acceptable_partial:
        return {"received": True, "processed": False, "status": payment_status}

    claimed = await db.transactions.find_one_and_update(
        {"payment_order_id": order_id, "status": "awaiting_payment"},
        {"$set": {
            "status": "pending",
            "paid_at": datetime.now(timezone.utc),
            "actually_paid": actually_paid,
            "underpaid": bool(is_acceptable_partial and not is_finished),
        }},
        return_document=True,
    )
    if not claimed:
        logger.info(f"crypto-send webhook: order_id {order_id} ya estaba procesado, ignorando duplicado")
        return {"received": True, "already_processed": True}

    try:
        await create_notification(
            user_id=claimed["user_id"],
            title="Pago recibido",
            message=f"Recibimos tu pago. Tu envío de {claimed.get('amount_output', 0):,.2f} VES será procesado pronto.",
            notification_type="crypto_send_paid",
        )
    except Exception as e:
        logger.warning(f"crypto-send webhook: no se pudo notificar al usuario: {e}")

    try:
        await send_next_pending_withdrawal_whatsapp()
    except Exception as e:
        logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

    return {"received": True, "processed": True}

# ============== RECHARGE VES ==============

@router.post("/recharge/ves")
async def recharge_ves(request: dict, current_user: User = Depends(get_current_user)):
    """Create a VES recharge request"""
    amount_ves = float(request.get("amount_ves", 0))
    payment_method = request.get("payment_method", "transferencia")

    if amount_ves <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")
    # Idempotencia: evita duplicar la solicitud por doble clic / reintento de red.
    _rch_key = request.get("idempotency_key")
    _rch_new, _rch_existing = await claim_idempotency(current_user.user_id, "recharge_ves", _rch_key)
    if not _rch_new:
        if _rch_existing and _rch_existing.get("result"):
            return _rch_existing["result"]
        raise HTTPException(status_code=409, detail="Esta solicitud ya se está procesando. Espera un momento.")
    # Tasa autoritativa del servidor (fail-closed): NO se confía en el monto RIS
    # que envíe el cliente; el servidor recalcula cuánto RIS corresponde.
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    _base_vtr = (rate_doc or {}).get("ves_to_ris_rate")
    if not _base_vtr or _base_vtr <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")
    # Aplicar el mismo ajuste de horario que /api/rate para que la orden coincida con la cotización
    _cfg = await load_auto_rate_config(db)
    _eff = apply_rate_adjustment({"ves_to_ris_rate": _base_vtr}, _cfg)
    ves_to_ris = _eff.get("ves_to_ris_rate") or _base_vtr

    # Fórmula oficial: ves_to_ris_rate = VES por 1 RIS  ->  RIS = VES / tasa
    amount_ris = round(amount_ves / ves_to_ris, 2)
    if amount_ris <= 0:
        raise HTTPException(status_code=400, detail="El monto en VES es demasiado bajo para la tasa actual.")

    amount_input = amount_ves

    # Aviso si el cliente había calculado un RIS distinto (no bloquea: el servidor manda)
    _client_ris = float(request.get("amount_ris", 0) or 0)
    if _client_ris and abs(_client_ris - amount_ris) > 0.01:
        logger.warning(f"recharge_ves: RIS del cliente ({_client_ris}) != servidor ({amount_ris}) user={current_user.user_id}")

    user = await db.users.find_one({"user_id": current_user.user_id})

    tx_id = f"rech_{uuid.uuid4().hex[:12]}"

    transaction = {
        "transaction_id": tx_id,
        "user_id": current_user.user_id,
        "type": "recharge_ves",
        "amount_input": amount_input,
        "amount_output": amount_ris,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris,
        "rate": ves_to_ris,
        "rate_kind": "ves_to_ris",
        "currency_input": "VES",
        "currency_output": "RIS",
        "payment_method": payment_method,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }

    await db.transactions.insert_one(transaction)

    # Registrar en CentroGestion
    await registrar_evento(
        tipo="recarga_ves",
        transaction_id=tx_id,
        user_id=current_user.user_id,
        user_email=user.get("email") if user else None,
        user_name=user.get("name") or user.get("full_name") if user else None,
        amount_input=amount_input,
        amount_output=amount_ris,
        currency_input="VES",
        currency_output="RIS",
        status="pending",
        metadata={"payment_method": payment_method}
    )

    _resp_rch = {
        "message": "Recarga VES registrada, pendiente de verificacion",
        "transaction_id": tx_id,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris
    }
    await store_idempotency_result(current_user.user_id, "recharge_ves", _rch_key, _resp_rch)
    return _resp_rch

# ============== TRANSACTION HISTORY ==============

@router.get("/transactions")
async def get_transactions(
    page: int = 1,
    limit: int = 10,
    filter_type: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get user's transaction history with pagination"""
    query = {"user_id": current_user.user_id}
    if filter_type and filter_type != "all":
        if filter_type == "withdrawals":
            query["type"] = {"$in": ["withdrawal", "send"]}
        elif filter_type == "recharges":
            query["type"] = {"$in": ["recharge", "recharge_ves"]}

    skip = (page - 1) * limit
    total = await db.transactions.count_documents(query)
    transactions = await db.transactions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    for _tx in transactions:
        _normalize_tx_money(_tx)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "transactions": transactions
    }

@router.get("/transactions/{transaction_id}")
async def get_transaction(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific transaction"""
    transaction = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {"_id": 0}
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")

    _normalize_tx_money(transaction)

    return transaction

# ============== PENDING WITHDRAWAL CHECK ==============

@router.get("/withdrawal/pending")
async def check_pending_withdrawal(current_user: User = Depends(get_current_user)):
    """Check if user has a pending withdrawal"""
    withdrawal = await db.transactions.find_one(
        {
            "user_id": current_user.user_id,
            "type": {"$in": ["withdrawal", "send"]},
            "status": "pending"
        },
        {"_id": 0},
        sort=[("created_at", -1)]
    )

    if not withdrawal:
        return {"has_pending": False}

    return {
        "has_pending": True,
        "transaction_id": withdrawal.get("transaction_id"),
        "display_id": withdrawal.get("display_id"),
        "amount_input": withdrawal.get("amount_input"),
        "amount_output": withdrawal.get("amount_output"),
        "beneficiary_data": withdrawal.get("beneficiary_data"),
        "created_at": withdrawal.get("created_at")
    }
