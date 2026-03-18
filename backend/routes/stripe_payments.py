"""
Stripe Payment Routes - Handle card payments for RIS balance recharge
Uses emergentintegrations for Stripe Checkout
"""
import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
import uuid

from database import db
from routes.dependencies import get_current_user
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/stripe", tags=["stripe-payments"])

# Import Stripe Checkout from emergentintegrations
try:
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout, 
        CheckoutSessionRequest, 
        CheckoutSessionResponse,
        CheckoutStatusResponse
    )
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("emergentintegrations not available - Stripe disabled")

# Fixed recharge packages (amounts in BRL - same as RIS)
RECHARGE_PACKAGES = {
    "small": {"amount": 50.0, "bonus": 0, "name": "R$ 50"},
    "medium": {"amount": 100.0, "bonus": 5, "name": "R$ 100 (+5% bonus)"},
    "large": {"amount": 200.0, "bonus": 10, "name": "R$ 200 (+10% bonus)"},
    "xlarge": {"amount": 500.0, "bonus": 15, "name": "R$ 500 (+15% bonus)"}
}

class CreateCheckoutRequest(BaseModel):
    package_id: str
    origin_url: str
    for_terceros: bool = False  # If true, add to balance_ris_terceros

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

def get_stripe_checkout(request: Request) -> StripeCheckout:
    """Get Stripe Checkout instance"""
    if not STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Stripe not available")
    
    api_key = os.getenv("STRIPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    
    return StripeCheckout(api_key=api_key, webhook_url=webhook_url)

@router.get("/packages")
async def get_recharge_packages():
    """Get available recharge packages"""
    return {
        "packages": [
            {
                "id": key,
                "name": pkg["name"],
                "amount": pkg["amount"],
                "bonus_percent": pkg["bonus"],
                "total_ris": pkg["amount"] * (1 + pkg["bonus"] / 100)
            }
            for key, pkg in RECHARGE_PACKAGES.items()
        ]
    }

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    data: CreateCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create Stripe checkout session for recharge"""
    # Validate package
    if data.package_id not in RECHARGE_PACKAGES:
        raise HTTPException(status_code=400, detail="Paquete inválido")
    
    package = RECHARGE_PACKAGES[data.package_id]
    amount = package["amount"]
    bonus_percent = package["bonus"]
    total_ris = amount * (1 + bonus_percent / 100)
    
    # Get Stripe checkout
    stripe_checkout = get_stripe_checkout(request)
    
    # Build URLs from origin
    success_url = f"{data.origin_url}/recharge/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{data.origin_url}/recharge"
    
    # Create unique transaction ID
    transaction_id = f"stripe_{uuid.uuid4().hex[:12]}"
    
    # Metadata for tracking
    metadata = {
        "user_id": current_user.user_id,
        "transaction_id": transaction_id,
        "package_id": data.package_id,
        "amount_brl": str(amount),
        "bonus_percent": str(bonus_percent),
        "total_ris": str(total_ris),
        "for_terceros": str(data.for_terceros).lower()
    }
    
    try:
        # Create checkout session request
        checkout_request = CheckoutSessionRequest(
            amount=float(amount),
            currency="brl",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata
        )
        
        # Create session
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        
        # Save payment transaction to DB (PENDING status)
        payment_record = {
            "transaction_id": transaction_id,
            "stripe_session_id": session.session_id,
            "user_id": current_user.user_id,
            "user_email": current_user.email,
            "package_id": data.package_id,
            "amount_brl": amount,
            "bonus_percent": bonus_percent,
            "total_ris": total_ris,
            "for_terceros": data.for_terceros,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc)
        }
        await db.payment_transactions.insert_one(payment_record)
        
        logger.info(f"Stripe checkout created: {transaction_id} for user {current_user.user_id}")
        
        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.session_id
        )
        
    except Exception as e:
        logger.error(f"Error creating Stripe checkout: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear sesión de pago: {str(e)}")

@router.get("/status/{session_id}")
async def get_payment_status(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Check payment status and process if completed"""
    # Find the transaction
    transaction = await db.payment_transactions.find_one({
        "stripe_session_id": session_id,
        "user_id": current_user.user_id
    }, {"_id": 0})
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    # If already processed, return status
    if transaction.get("payment_status") == "paid":
        return {
            "status": "completed",
            "payment_status": "paid",
            "amount_ris": transaction.get("total_ris"),
            "message": "Pago ya procesado"
        }
    
    # Check with Stripe
    stripe_checkout = get_stripe_checkout(request)
    
    try:
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        
        if status.payment_status == "paid":
            # Process the payment - add balance
            total_ris = transaction.get("total_ris", 0)
            for_terceros = transaction.get("for_terceros", False)
            
            # Update user balance (only if not already processed)
            existing = await db.payment_transactions.find_one({
                "stripe_session_id": session_id,
                "payment_status": "paid"
            })
            
            if not existing:
                # Update balance
                balance_field = "balance_ris_terceros" if for_terceros else "balance_ris"
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$inc": {balance_field: total_ris}}
                )
                
                # Update transaction record
                await db.payment_transactions.update_one(
                    {"stripe_session_id": session_id},
                    {
                        "$set": {
                            "payment_status": "paid",
                            "status": "completed",
                            "completed_at": datetime.now(timezone.utc)
                        }
                    }
                )
                
                # Create notification
                await db.notifications.insert_one({
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": current_user.user_id,
                    "title": "💳 Recarga Exitosa",
                    "message": f"Se han añadido R$ {total_ris:.2f} a tu {'saldo de terceros' if for_terceros else 'saldo'}.",
                    "type": "payment_success",
                    "read": False,
                    "created_at": datetime.now(timezone.utc)
                })
                
                logger.info(f"Stripe payment completed: {session_id} - +{total_ris} RIS to {current_user.user_id}")
            
            return {
                "status": "completed",
                "payment_status": "paid",
                "amount_ris": total_ris,
                "message": "¡Pago exitoso! Tu saldo ha sido actualizado."
            }
        
        elif status.status == "expired":
            await db.payment_transactions.update_one(
                {"stripe_session_id": session_id},
                {"$set": {"status": "expired", "payment_status": "expired"}}
            )
            return {
                "status": "expired",
                "payment_status": "expired",
                "message": "La sesión de pago ha expirado"
            }
        
        else:
            return {
                "status": "pending",
                "payment_status": status.payment_status,
                "message": "Pago en proceso..."
            }
            
    except Exception as e:
        logger.error(f"Error checking Stripe status: {e}")
        return {
            "status": "error",
            "payment_status": "unknown",
            "message": "Error al verificar estado del pago"
        }

@router.get("/history")
async def get_payment_history(current_user: User = Depends(get_current_user)):
    """Get user's payment history"""
    payments = await db.payment_transactions.find(
        {"user_id": current_user.user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    
    return payments


# Webhook router (public - no auth)
webhook_router = APIRouter(prefix="/webhook", tags=["webhooks"])

@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        
        api_key = os.getenv("STRIPE_API_KEY")
        if not api_key:
            return {"received": True}
        
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
        
        event = await stripe_checkout.handle_webhook(body, signature)
        
        logger.info(f"Stripe webhook received: {event.event_type}")
        
        # Process payment success
        if event.payment_status == "paid" and event.session_id:
            transaction = await db.payment_transactions.find_one({
                "stripe_session_id": event.session_id,
                "payment_status": {"$ne": "paid"}
            })
            
            if transaction:
                total_ris = transaction.get("total_ris", 0)
                user_id = transaction.get("user_id")
                for_terceros = transaction.get("for_terceros", False)
                
                # Update balance
                balance_field = "balance_ris_terceros" if for_terceros else "balance_ris"
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$inc": {balance_field: total_ris}}
                )
                
                # Update transaction
                await db.payment_transactions.update_one(
                    {"stripe_session_id": event.session_id},
                    {
                        "$set": {
                            "payment_status": "paid",
                            "status": "completed",
                            "completed_at": datetime.now(timezone.utc)
                        }
                    }
                )
                
                logger.info(f"Webhook processed payment: {event.session_id}")
        
        return {"received": True}
        
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"received": True, "error": str(e)}
