"""
Gestor PIX routes - PIX payment generation and webhook handling for Gestor flow
Integrates with Mercado Pago for real PIX payments
"""
import uuid
import json
import logging
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from database import db
from services.limits import validate_pix_amount
from services import kyc_quota
from models.user import User
from routes.dependencies import get_current_user
from services.notifications import create_notification
from services.email_notifications import notify_pix_received, notify_recharge_success

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gestor/pix", tags=["gestor-pix"])

# Import Mercado Pago service
try:
    from mercadopago_service import mercadopago_service
    MP_AVAILABLE = mercadopago_service.sdk is not None
except ImportError:
    MP_AVAILABLE = False
    mercadopago_service = None

class CreatePixRequest(BaseModel):
    amount_ris: float
    client_name: Optional[str] = None
    client_email: Optional[str] = "cliente@risapp.com"
    client_cpf: Optional[str] = "00000000000"

class PixPaymentResponse(BaseModel):
    payment_id: str
    qr_code: str
    qr_code_base64: str
    copy_paste_code: str
    amount_ris: float
    amount_brl: float
    expires_at: str
    expires_in_seconds: int

async def require_authenticated_user(current_user: User = Depends(get_current_user)) -> User:
    """Require any authenticated user - PIX recharge available to all users"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=403, detail="Usuario no encontrado")
    return current_user

@router.post("/create")
async def create_pix_payment(request: CreatePixRequest, current_user: User = Depends(require_authenticated_user)):
    """Create a PIX payment for third-party recharge via Mercado Pago"""
    # Limite de monto validado ANTES de crear el pago en Mercado Pago: si no,
    # la pantalla anuncia un techo que el servidor no hace cumplir.
    error_monto = validate_pix_amount(request.amount_ris)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    # Cupo de la cuenta sin verificar: se comprueba ANTES de crear nada.
    _kq_user = await db.users.find_one({"user_id": current_user.user_id})
    _kq_error = kyc_quota.check_amount(_kq_user, request.amount_ris)
    if _kq_error:
        raise HTTPException(status_code=403, detail=_kq_error)
    
    # Get current rate
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    ris_to_ves = rate_doc.get("ris_to_ves", 92.0) if rate_doc else 92.0
    
    # RIS = BRL (1:1)
    amount_brl = request.amount_ris
    amount_ves = request.amount_ris * ris_to_ves
    
    # Generate internal payment ID
    internal_id = f"gpix_{uuid.uuid4().hex[:12]}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=7)
    
    # Get gestor info
    gestor = await db.users.find_one({"user_id": current_user.user_id})
    gestor_name = gestor.get("name", "Gestor") if gestor else "Gestor"
    
    # Try Mercado Pago integration
    mp_payment_id = None
    qr_code_data = ""
    qr_code_base64 = ""
    
    if MP_AVAILABLE and mercadopago_service:
        try:
            mp_result = mercadopago_service.create_pix_payment(
                amount=amount_brl,
                description=f"Recarga Gestor {gestor_name} - {internal_id}",
                payer_email=request.client_email or "cliente@risapp.com",
                payer_first_name=request.client_name.split()[0] if request.client_name else "Cliente",
                payer_last_name=request.client_name.split()[-1] if request.client_name and len(request.client_name.split()) > 1 else "RIS",
                payer_cpf=request.client_cpf or "00000000000",
                external_reference=internal_id
            )
            
            if mp_result and mp_result.get("success"):
                mp_payment_id = mp_result.get("payment_id")
                qr_code_data = mp_result.get("qr_code", "")
                qr_code_base64 = mp_result.get("qr_code_base64", "")
                logger.info(f"Mercado Pago PIX created: {mp_payment_id}, qr_code_len={len(qr_code_data or '')}, has_base64={bool(qr_code_base64)}")
            else:
                logger.warning(f"Mercado Pago PIX failed: {mp_result}")
        except Exception as e:
            logger.error(f"Error creating Mercado Pago PIX: {e}")
    
    # Only use fallback if MP truly didn't return a qr_code
    if not qr_code_data:
        logger.warning(f"No real PIX QR code for {internal_id} - MP not available or failed")
    
    # Create pending PIX payment record
    pix_payment = {
        "payment_id": internal_id,
        "mp_payment_id": mp_payment_id,
        "gestor_id": current_user.user_id,
        "gestor_name": gestor_name,
        "client_name": request.client_name,
        "amount_ris": request.amount_ris,
        "amount_brl": amount_brl,
        "amount_ves": amount_ves,
        "qr_code": qr_code_data,
        "qr_code_base64": qr_code_base64,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
        "is_mp_payment": mp_payment_id is not None
    }
    
    await db.gestor_pix_payments.insert_one(pix_payment)
    
    logger.info(f"PIX payment {internal_id} created for gestor {current_user.user_id}, MP: {mp_payment_id}")
    
    return {
        "payment_id": internal_id,
        "mp_payment_id": mp_payment_id,
        "qr_code": qr_code_data,
        "qr_code_base64": qr_code_base64 or "",
        "copy_paste_code": qr_code_data,
        "amount_ris": request.amount_ris,
        "amount_brl": amount_brl,
        "amount_ves": amount_ves,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": 420
    }


@router.get("/pending")
async def get_pending_pix(current_user: User = Depends(require_authenticated_user)):
    """Get pending PIX payment for current user - allows resuming incomplete payments"""
    # Find pending payment that hasn't expired
    payment = await db.gestor_pix_payments.find_one({
        "gestor_id": current_user.user_id,
        "status": "pending",
        "expires_at": {"$gt": datetime.now(timezone.utc)}
    }, sort=[("created_at", -1)])
    
    if not payment:
        return {"has_pending": False}
    
    # Calculate remaining time
    expires_at = payment.get("expires_at")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    remaining_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    
    if remaining_seconds <= 0:
        # Mark as expired
        await db.gestor_pix_payments.update_one(
            {"payment_id": payment["payment_id"]},
            {"$set": {"status": "expired"}}
        )
        return {"has_pending": False}
    
    return {
        "has_pending": True,
        "payment_id": payment["payment_id"],
        "qr_code": payment.get("qr_code", ""),
        "qr_code_base64": payment.get("qr_code_base64", ""),
        "copy_paste_code": payment.get("qr_code", ""),
        "amount_ris": payment.get("amount_ris"),
        "amount_brl": payment.get("amount_brl"),
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": remaining_seconds,
        "created_at": payment.get("created_at").isoformat() if payment.get("created_at") else None
    }


@router.post("/cancel/{payment_id}")
async def cancel_pix_payment(payment_id: str, current_user: User = Depends(require_authenticated_user)):
    """Cancel a pending PIX payment"""
    result = await db.gestor_pix_payments.update_one(
        {
            "payment_id": payment_id,
            "gestor_id": current_user.user_id,
            "status": "pending"
        },
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pago no encontrado o ya procesado")
    
    return {"success": True, "message": "Pago cancelado"}


@router.get("/status/{payment_id}")
async def get_pix_status(payment_id: str, current_user: User = Depends(require_authenticated_user)):
    """Check PIX payment status - also checks with Mercado Pago if available"""
    payment = await db.gestor_pix_payments.find_one({
        "payment_id": payment_id,
        "gestor_id": current_user.user_id
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    
    current_status = payment.get("status")
    
    # If already paid, return immediately
    if current_status == "paid":
        return {
            "payment_id": payment_id,
            "status": "paid",
            "amount_ris": payment.get("amount_ris"),
            "amount_ves": payment.get("amount_ves"),
            "created_at": payment.get("created_at"),
            "paid_at": payment.get("paid_at")
        }
    
    # Check if expired
    expires_at = payment.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if datetime.now(timezone.utc) > expires_at and current_status == "pending":
            await db.gestor_pix_payments.update_one(
                {"payment_id": payment_id},
                {"$set": {"status": "expired"}}
            )
            return {"status": "expired", "payment_id": payment_id}
    
    # If pending and has MP payment, check status with Mercado Pago
    if current_status == "pending" and payment.get("mp_payment_id") and MP_AVAILABLE:
        try:
            mp_status = mercadopago_service.get_payment_status(payment["mp_payment_id"])
            logger.info(f"MP status check for {payment_id}: {mp_status}")
            
            if mp_status and mp_status.get("status") == "approved":
                # Payment confirmed by MP - update our records
                await process_pix_confirmation(payment_id, payment["gestor_id"])
                return {
                    "payment_id": payment_id,
                    "status": "paid",
                    "amount_ris": payment.get("amount_ris"),
                    "amount_ves": payment.get("amount_ves"),
                    "paid_at": datetime.now(timezone.utc)
                }
        except Exception as e:
            logger.warning(f"Error checking MP status: {e}")
    
    return {
        "payment_id": payment_id,
        "status": current_status,
        "amount_ris": payment.get("amount_ris"),
        "amount_ves": payment.get("amount_ves"),
        "created_at": payment.get("created_at"),
        "paid_at": payment.get("paid_at")
    }


async def process_pix_confirmation(payment_id: str, user_id: str):
    """Process PIX payment confirmation - credit user's balance"""
    # Reclamo atómico: solo UNA ejecución concurrente obtiene el pago pendiente.
    # Si el webhook de Mercado Pago llega duplicado, las demás reciben None y no
    # vuelven a acreditar (evita doble crédito).
    payment = await db.gestor_pix_payments.find_one_and_update(
        {"payment_id": payment_id, "status": "pending"},
        {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc)}}
    )
    if not payment:
        logger.warning(f"Payment {payment_id} not found or already processed")
        return False
    
    # Get user to check role
    user = await db.users.find_one({"user_id": user_id})
    user_role = user.get("role", "user") if user else "user"
    amount_ris = payment.get("amount_ris", 0)
    
    # Determine which balance to credit based on user role
    # For socio_gestor processing third-party payments -> balance_ris_terceros
    # For regular users recharging their own account -> balance_ris (main balance)
    is_gestor_recharge = payment.get("is_gestor_terceros", False)
    
    if user_role == "socio_gestor" and is_gestor_recharge:
        # Gestor receiving third-party payment
        updated = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"balance_ris_terceros": amount_ris, **kyc_quota.consume_inc(amount_ris)}},
            return_document=True
        )
        balance_type = "saldo de terceros"
        ledger_account = "balance_ris_terceros"
        balance_after = (updated or {}).get("balance_ris_terceros")
    else:
        # Regular user or gestor recharging their own account -> main balance
        updated = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"balance_ris": amount_ris, **kyc_quota.consume_inc(amount_ris)}},
            return_document=True
        )
        balance_type = "saldo principal"
        ledger_account = "balance_ris"
        balance_after = (updated or {}).get("balance_ris")

    balance_before = (balance_after - amount_ris) if balance_after is not None else None

    # Si esta recarga le agoto el cupo sin KYC, avisarle. Nunca interrumpe.
    await kyc_quota.notify_if_exhausted(updated)

    # Libro mayor RIS (append-only). Nunca interrumpe la acreditación.
    try:
        from services.ledger import record_ris_entry
        await record_ris_entry(
            user_id=user_id,
            movement_type="recarga_pix",
            amount=amount_ris,
            direction="credit",
            account=ledger_account,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_kind="pix_payment",
            reference_id=payment_id,
            actor_type="webhook",
            actor_id="mercadopago",
            user_snapshot=({"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user_role} if user else None),
            counterparty={"client_name": payment.get("client_name")},
            metadata={
                "amount_brl": payment.get("amount_brl"),
                "amount_ves": payment.get("amount_ves"),
                "mp_payment_id": payment.get("mp_payment_id"),
                "is_gestor_terceros": is_gestor_recharge,
            },
            notes="Recarga por PIX (Mercado Pago)",
        )
    except Exception as e:
        logger.warning(f"Ledger recarga_pix no registrado: {e}")

    # Notify user (in-app)
    await create_notification(
        user_id=user_id,
        title="💰 Pago PIX Confirmado",
        message=f"Se han añadido R$ {amount_ris:.2f} a tu {balance_type}.",
        notification_type="pix_received",
        data={"payment_id": payment_id, "amount": amount_ris}
    )
    
    # Send email notification
    try:
        if user and user.get("email"):
            await notify_pix_received(
                email=user["email"],
                user_name=user.get("name", "Usuario"),
                amount=amount_ris,
                client_name=payment.get("client_name", "Cliente")
            )
    except Exception as e:
        logger.warning(f"Failed to send PIX email notification: {e}")
    
    logger.info(f"PIX payment {payment_id} confirmed, +{amount_ris} RIS to {balance_type} of user {user_id}")

    # Credit MercadoPago accounting bank (BRL)
    try:
        await _credit_mercadopago_bank(payment, amount_ris)
    except Exception as e:
        logger.warning(f"Failed to update MercadoPago accounting bank: {e}")

    return True


async def _credit_mercadopago_bank(payment: dict, amount_brl: float):
    """Ensure a 'Mercado Pago' BRL bank exists in accounting and credit it for this PIX payment."""
    from datetime import datetime, timezone
    import uuid

    bank = await db.bank_accounts.find_one({"name": "Mercado Pago", "currency": "BRL"})
    if not bank:
        bank = {
            "bank_id": f"mp_{uuid.uuid4().hex[:8]}",
            "name": "Mercado Pago",
            "currency": "BRL",
            "balance": 0.0,
            "is_gateway": True,
            "created_at": datetime.now(timezone.utc),
        }
        await db.bank_accounts.insert_one(bank)

    new_balance = round(float(bank.get("balance", 0)) + float(amount_brl), 2)

    await db.bank_accounts.update_one(
        {"bank_id": bank["bank_id"]},
        {"$inc": {"balance": float(amount_brl)}}
    )

    payment_id = payment.get("payment_id")
    client = payment.get("client_name") or payment.get("user_id", "Cliente")

    await db.bank_ledger.insert_one({
        "bank_id": bank["bank_id"],
        "bank_name": "Mercado Pago",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "type": "entrada",
        "concept": f"Recarga PIX: {client} (Payment {payment_id[:12] if payment_id else '-'})",
        "amount": float(amount_brl),
        "balance_after": new_balance,
        "reference": payment_id,
        "notes": "Recarga automática desde Mercado Pago",
        "source": "mercadopago",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

@router.post("/simulate-payment/{payment_id}")
async def simulate_pix_payment(payment_id: str, current_user: User = Depends(require_authenticated_user)):
    """Simulate PIX payment confirmation (for testing when MP not available)"""
    # --- SECURITY: this endpoint credits real balance with no real payment.
    # Fail-closed por defecto: solo se habilita si ENABLE_PIX_SIMULATION=true
    # esta seteado explicitamente (nunca queda abierto por accidente/typo). ---
    if os.environ.get("ENABLE_PIX_SIMULATION", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    payment = await db.gestor_pix_payments.find_one({
        "payment_id": payment_id,
        "gestor_id": current_user.user_id,
        "status": "pending"
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Pago pendiente no encontrado")
    
    # Check if expired
    expires_at = payment.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="El pago ha expirado")
    
    # Process the payment
    success = await process_pix_confirmation(payment_id, current_user.user_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Error al procesar el pago")
    
    # Get updated balance
    user = await db.users.find_one({"user_id": current_user.user_id})
    new_balance = user.get("balance_ris_terceros", 0)
    
    logger.info(f"PIX payment {payment_id} simulated for gestor {current_user.user_id}")
    
    return {
        "status": "paid",
        "payment_id": payment_id,
        "amount_ris": payment.get("amount_ris", 0),
        "new_balance_terceros": new_balance
    }

@router.post("/cancel/{payment_id}")
async def cancel_pix_payment(payment_id: str, current_user: User = Depends(require_authenticated_user)):
    """Cancel a pending PIX payment"""
    result = await db.gestor_pix_payments.update_one(
        {
            "payment_id": payment_id,
            "gestor_id": current_user.user_id,
            "status": "pending"
        },
        {"$set": {"status": "cancelled"}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pago pendiente no encontrado")
    
    return {"message": "Pago cancelado", "payment_id": payment_id}

@router.get("/active")
async def get_active_pix(current_user: User = Depends(require_authenticated_user)):
    """Get active (pending) PIX payment if exists"""
    payment = await db.gestor_pix_payments.find_one({
        "gestor_id": current_user.user_id,
        "status": "pending"
    })
    
    if not payment:
        return {"has_active": False}
    
    # Check if expired
    expires_at = payment.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if datetime.now(timezone.utc) > expires_at:
            await db.gestor_pix_payments.update_one(
                {"payment_id": payment["payment_id"]},
                {"$set": {"status": "expired"}}
            )
            return {"has_active": False}
    
    remaining_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    
    return {
        "has_active": True,
        "payment_id": payment.get("payment_id"),
        "amount_ris": payment.get("amount_ris"),
        "amount_ves": payment.get("amount_ves"),
        "expires_in_seconds": max(0, remaining_seconds)
    }



@router.get("/history")
async def get_pix_history(current_user: User = Depends(require_authenticated_user)):
    """Get PIX payment history for the gestor"""
    payments = await db.gestor_pix_payments.find({
        "gestor_id": current_user.user_id
    }).sort("created_at", -1).limit(50).to_list(50)
    
    result = []
    for p in payments:
        result.append({
            "payment_id": p.get("payment_id"),
            "amount_ris": p.get("amount_ris"),
            "amount_brl": p.get("amount_brl"),
            "client_name": p.get("client_name"),
            "status": p.get("status"),
            "created_at": p.get("created_at"),
            "paid_at": p.get("paid_at")
        })
    
    return result


# Mercado Pago Webhook endpoint (public - no auth required)
webhook_router = APIRouter(prefix="/webhook", tags=["webhooks"])

@webhook_router.post("/mercadopago")
async def mercadopago_webhook(request: Request):
    """
    Webhook endpoint for Mercado Pago payment notifications.
    This is called by MP when a PIX or Card payment status changes.
    
    Security measures:
    1. HMAC-SHA256 signature verification using MERCADOPAGO_WEBHOOK_SECRET.
       Per MP docs: manifest = "id:DATA_ID;request-id:REQUEST_ID;ts:TIMESTAMP;"
       header x-signature = "ts=TIMESTAMP,v1=HEX_HMAC"
       Spec: https://www.mercadopago.com.br/developers/en/docs/your-integrations/notifications/webhooks
    2. Verify the payment exists in our database (PIX or card).
    3. Double-check status with MP API before crediting (anti-spoofing).
    4. Idempotency via processed_webhooks (TTL).
    5. Log all webhook activity for audit.
    """
    import os, hmac, hashlib
    
    try:
        # ── 1. Signature verification ────────────────────────────────────
        webhook_secret = os.environ.get("MERCADOPAGO_WEBHOOK_SECRET")
        raw_body = await request.body()
        
        if webhook_secret:
            x_signature = request.headers.get("x-signature", "")
            x_request_id = request.headers.get("x-request-id", "")
            # Get data.id from query string (MP includes it as ?id=XXX&topic=payment)
            data_id = request.query_params.get("data.id") or request.query_params.get("id", "")
            
            # Parse x-signature: "ts=1234,v1=hexhash"
            parts = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
            ts = parts.get("ts", "")
            v1 = parts.get("v1", "")
            
            # If body has data.id, fall back to that
            if not data_id:
                try:
                    body_json = json.loads(raw_body or b"{}")
                    data_id = str(body_json.get("data", {}).get("id", ""))
                except Exception:
                    pass
            
            if not (ts and v1 and data_id and x_request_id):
                logger.warning(
                    f"MP webhook missing signature headers: "
                    f"ts={bool(ts)} v1={bool(v1)} data_id={bool(data_id)} req_id={bool(x_request_id)}"
                )
                raise HTTPException(status_code=401, detail="missing_signature")
            
            manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                manifest.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            
            if not hmac.compare_digest(expected, v1):
                logger.warning(
                    f"MP webhook signature MISMATCH for data_id={data_id} req_id={x_request_id}"
                )
                raise HTTPException(status_code=401, detail="invalid_signature")
            
            logger.info(f"MP webhook signature OK (data_id={data_id})")
        else:
            logger.error(
                "MERCADOPAGO_WEBHOOK_SECRET not set — rejecting webhook (fail-closed)."
            )
            raise HTTPException(status_code=401, detail="webhook_secret_not_configured")
        
        # ── 2. Parse payload ─────────────────────────────────────────────
        try:
            payload = json.loads(raw_body or b"{}")
        except Exception:
            payload = {}
        
        logger.info(f"Mercado Pago webhook received: {payload}")
        
        # Get the event type and payment ID
        event_type = payload.get("type") or payload.get("action")
        data = payload.get("data", {})
        mp_payment_id = data.get("id")
        
        # Only process payment events
        if event_type not in ["payment.created", "payment.updated", "payment"]:
            logger.info(f"Ignoring non-payment event: {event_type}")
            return {"received": True, "processed": False}
        
        if not mp_payment_id:
            logger.warning("Webhook received without payment ID")
            return {"received": True, "error": "no_payment_id"}
        
        # Find our payment record by MP payment ID — try PIX first, then card
        payment = await db.gestor_pix_payments.find_one({
            "mp_payment_id": mp_payment_id
        })
        
        if not payment:
            # Try card_payments (MP stores its own id as payment_id there)
            card_payment = await db.card_payments.find_one({"payment_id": str(mp_payment_id)})
            if card_payment:
                return await _handle_card_webhook(card_payment, str(mp_payment_id))
            logger.warning(f"Payment {mp_payment_id} not found in our database")
            return {"received": True, "error": "payment_not_found"}
        
        # Skip if already processed
        if payment.get("status") != "pending":
            logger.info(f"Payment {mp_payment_id} already processed with status: {payment.get('status')}")
            return {"received": True, "already_processed": True}
        
        # SECURITY: Double-check status directly with Mercado Pago API
        if not MP_AVAILABLE or not mercadopago_service:
            logger.error("Mercado Pago service not available for verification")
            return {"received": True, "error": "mp_service_unavailable"}
        
        mp_status = mercadopago_service.get_payment_status(mp_payment_id)
        
        if not mp_status:
            logger.error(f"Could not verify payment {mp_payment_id} with MP API")
            return {"received": True, "error": "verification_failed"}
        
        # SECURITY: Verify the amount matches
        expected_amount = payment.get("amount_brl", 0)
        actual_amount = mp_status.get("amount", 0)
        
        if abs(expected_amount - actual_amount) > 0.01:  # Allow 1 cent tolerance
            logger.error(f"Amount mismatch! Expected: {expected_amount}, Actual: {actual_amount}")
            # Mark as suspicious but don't process
            await db.gestor_pix_payments.update_one(
                {"payment_id": payment["payment_id"]},
                {"$set": {"status": "suspicious", "security_note": f"Amount mismatch: expected {expected_amount}, got {actual_amount}"}}
            )
            return {"received": True, "error": "amount_mismatch"}
        
        # Only credit if MP confirms "approved" status
        if mp_status.get("status") == "approved":
            # Process the confirmation - credit user's balance
            success = await process_pix_confirmation(
                payment["payment_id"],
                payment["gestor_id"]
            )
            
            if success:
                logger.info(f"Webhook processed successfully: payment {mp_payment_id} approved and credited")
                return {"received": True, "processed": True, "status": "approved"}
            else:
                logger.error(f"Failed to process payment confirmation for {mp_payment_id}")
                return {"received": True, "error": "processing_failed"}
        else:
            logger.info(f"Payment {mp_payment_id} status is {mp_status.get('status')}, not approved yet")
            return {"received": True, "status": mp_status.get("status")}
        
    except HTTPException:
        # Let signature 401s propagate as-is — don't swallow them.
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Return 200 anyway to prevent MP from retrying
        return {"received": True, "error": str(e)}


# Export both routers
__all__ = ["router", "webhook_router"]


async def _handle_card_webhook(card_payment: dict, mp_payment_id: str) -> dict:
    """Handle MP webhook for a card payment. Idempotent via processed_webhooks.
    
    Most card flows are settled synchronously (binary_mode=true) at /process,
    but this catches: refunds, chargebacks, and edge cases where MP confirms
    asynchronously (e.g. 3DS challenge or pending review).
    """
    from datetime import datetime, timezone
    
    # Idempotency guard — already credited during sync flow?
    existing = await db.processed_webhooks.find_one(
        {"webhook_event_id": f"card_{mp_payment_id}"}
    )
    if existing:
        logger.info(f"Card webhook {mp_payment_id} already processed, skipping")
        return {"received": True, "already_processed": True, "kind": "card"}
    
    # Fetch latest status from MP API for security
    if not MP_AVAILABLE or not mercadopago_service:
        logger.warning(f"MP service unavailable, cannot verify card webhook {mp_payment_id}")
        return {"received": True, "error": "mp_service_unavailable"}
    
    mp_status_data = mercadopago_service.get_payment_status(mp_payment_id)
    if not mp_status_data:
        return {"received": True, "error": "verification_failed"}
    
    mp_status = mp_status_data.get("status")
    
    # Update our record with the latest status
    await db.card_payments.update_one(
        {"payment_id": mp_payment_id},
        {"$set": {
            "status": mp_status,
            "status_detail": mp_status_data.get("status_detail"),
            "webhook_last_seen": datetime.now(timezone.utc),
        }}
    )
    
    # If approved AND not credited yet → credit now
    if mp_status == "approved" and card_payment.get("status") != "approved":
        from routes.payments_card import _credit_mp_bank_card, _register_card_fee
        from services.notifications import create_notification
        
        # Mark as processed to ensure idempotency
        await db.processed_webhooks.insert_one({
            "webhook_event_id": f"card_{mp_payment_id}",
            "provider": "mercadopago_card",
            "processed_at": datetime.now(timezone.utc),
        })
        
        user_id = card_payment.get("user_id")
        amount_ris = card_payment.get("amount_ris", 0)
        fee_brl = card_payment.get("fee_brl", 0)
        total_brl = card_payment.get("total_charged_brl", amount_ris)
        
        # Credit RIS
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"balance_ris": amount_ris}}
        )
        
        # Notify
        user = await db.users.find_one({"user_id": user_id})
        if user:
            await create_notification(
                user_id=user_id,
                title="💳 Pago con Tarjeta Aprobado",
                message=f"Se han añadido R$ {amount_ris:.2f} a tu saldo.",
                notification_type="card_received",
                data={"payment_id": mp_payment_id, "amount": amount_ris},
            )
            # Accounting
            try:
                await _credit_mp_bank_card(
                    payment_id=mp_payment_id,
                    client_name=user.get("name", "Cliente"),
                    amount_brl_net=amount_ris,
                )
                await _register_card_fee(
                    payment_id=mp_payment_id,
                    fee_brl=fee_brl,
                    gross_brl=total_brl,
                )
            except Exception as exc:
                logger.warning(f"Webhook card accounting failed: {exc}")
        
        logger.info(f"Card webhook credited {amount_ris} RIS to {user_id} (MP {mp_payment_id})")
        return {"received": True, "processed": True, "kind": "card", "status": "approved"}
    
    logger.info(f"Card webhook {mp_payment_id} status={mp_status}, no credit needed")
    return {"received": True, "kind": "card", "status": mp_status}
