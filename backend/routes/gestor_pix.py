"""
Gestor PIX routes - PIX payment generation and webhook handling for Gestor flow
Integrates with Mercado Pago for real PIX payments
"""
import uuid
import logging
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from database import db
from models.user import User
from routes.dependencies import get_current_user
from services.notifications import create_notification

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

async def require_gestor(current_user: User = Depends(get_current_user)) -> User:
    """Require socio_gestor role"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    return current_user

@router.post("/create")
async def create_pix_payment(request: CreatePixRequest, current_user: User = Depends(require_gestor)):
    """Create a PIX payment for third-party recharge via Mercado Pago"""
    if request.amount_ris <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
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
                logger.info(f"Mercado Pago PIX created: {mp_payment_id} for {internal_id}")
            else:
                logger.warning(f"Mercado Pago PIX failed: {mp_result}")
        except Exception as e:
            logger.error(f"Error creating Mercado Pago PIX: {e}")
    
    # Fallback to mock QR code if MP not available
    if not qr_code_data:
        qr_code_data = f"00020126580014br.gov.bcb.pix0136{internal_id}5204000053039865406{amount_brl:.2f}5802BR"
        logger.info(f"Using mock PIX QR for {internal_id} (MP not available)")
    
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

@router.get("/status/{payment_id}")
async def get_pix_status(payment_id: str, current_user: User = Depends(require_gestor)):
    """Check PIX payment status - also checks with Mercado Pago if available"""
    payment = await db.gestor_pix_payments.find_one({
        "payment_id": payment_id,
        "gestor_id": current_user.user_id
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    
    # Check if expired
    expires_at = payment.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if datetime.now(timezone.utc) > expires_at and payment.get("status") == "pending":
            await db.gestor_pix_payments.update_one(
                {"payment_id": payment_id},
                {"$set": {"status": "expired"}}
            )
            return {"status": "expired", "payment_id": payment_id}
    
    # If pending and has MP payment, check status with Mercado Pago
    if payment.get("status") == "pending" and payment.get("mp_payment_id") and MP_AVAILABLE:
        try:
            mp_status = mercadopago_service.get_payment_status(payment["mp_payment_id"])
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
        "status": payment.get("status"),
        "amount_ris": payment.get("amount_ris"),
        "amount_ves": payment.get("amount_ves"),
        "created_at": payment.get("created_at"),
        "paid_at": payment.get("paid_at")
    }


async def process_pix_confirmation(payment_id: str, gestor_id: str):
    """Process PIX payment confirmation - credit gestor's terceros balance"""
    payment = await db.gestor_pix_payments.find_one({
        "payment_id": payment_id,
        "status": "pending"
    })
    
    if not payment:
        logger.warning(f"Payment {payment_id} not found or already processed")
        return False
    
    # Mark as paid
    await db.gestor_pix_payments.update_one(
        {"payment_id": payment_id},
        {
            "$set": {
                "status": "paid",
                "paid_at": datetime.now(timezone.utc)
            }
        }
    )
    
    # Add to gestor's terceros balance
    amount_ris = payment.get("amount_ris", 0)
    await db.users.update_one(
        {"user_id": gestor_id},
        {"$inc": {"balance_ris_terceros": amount_ris}}
    )
    
    # Notify gestor
    await create_notification(
        user_id=gestor_id,
        title="💰 Pago PIX Confirmado",
        message=f"Se han añadido R$ {amount_ris:.2f} a tu saldo de terceros.",
        notification_type="pix_received",
        data={"payment_id": payment_id, "amount": amount_ris}
    )
    
    logger.info(f"PIX payment {payment_id} confirmed, +{amount_ris} RIS to gestor {gestor_id}")
    return True

@router.post("/simulate-payment/{payment_id}")
async def simulate_pix_payment(payment_id: str, current_user: User = Depends(require_gestor)):
    """Simulate PIX payment confirmation (for testing when MP not available)"""
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
async def cancel_pix_payment(payment_id: str, current_user: User = Depends(require_gestor)):
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
async def get_active_pix(current_user: User = Depends(require_gestor)):
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
async def get_pix_history(current_user: User = Depends(require_gestor)):
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
    This is called by MP when a PIX payment status changes.
    """
    try:
        payload = await request.json()
        
        logger.info(f"Mercado Pago webhook received: {payload}")
        
        # Get the event type
        event_type = payload.get("type") or payload.get("action")
        data = payload.get("data", {})
        payment_id = data.get("id")
        
        # Handle payment.created or payment.updated events
        if event_type in ["payment.created", "payment.updated", "payment"]:
            if payment_id:
                # Find our payment record by MP payment ID
                payment = await db.gestor_pix_payments.find_one({
                    "mp_payment_id": payment_id
                })
                
                if payment and payment.get("status") == "pending":
                    # Check the actual status with MP
                    if MP_AVAILABLE and mercadopago_service:
                        mp_status = mercadopago_service.get_payment_status(payment_id)
                        
                        if mp_status and mp_status.get("status") == "approved":
                            # Process the confirmation
                            await process_pix_confirmation(
                                payment["payment_id"],
                                payment["gestor_id"]
                            )
                            logger.info(f"Webhook processed: payment {payment_id} approved")
        
        # Always return 200 to acknowledge receipt
        return {"received": True}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Return 200 anyway to prevent retries
        return {"received": True, "error": "processed"}


# Export both routers
__all__ = ["router", "webhook_router"]
