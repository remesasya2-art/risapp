"""
Stripe Payment Routes - Handle USD card payments for RIS balance recharge
Uses official Stripe SDK for production payments
User pays X USD and receives X USD in their wallet (1:1 ratio)
"""
import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
import uuid
import stripe

from database import db
from routes.dependencies import get_current_user
from models.user import User
from services.email_notifications import notify_recharge_success

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/stripe", tags=["stripe-payments"])

# Initialize Stripe
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY
    logger.info("Stripe initialized with API key")

# Minimum and maximum amounts in USD
MIN_AMOUNT_USD = 5.0
MAX_AMOUNT_USD = 1000.0

class CreateCheckoutRequest(BaseModel):
    amount_usd: float  # User chooses the amount
    origin_url: str
    for_terceros: bool = False

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

@router.get("/rate")
async def get_stripe_info():
    """Get Stripe recharge info (min/max amounts)"""
    return {
        "min_amount": MIN_AMOUNT_USD,
        "max_amount": MAX_AMOUNT_USD,
        "currency": "USD",
        "conversion_rate": 1.0,  # 1 USD = 1 USD (no conversion on recharge)
        "note": "Pagas X USD, recibes X USD en tu cartera"
    }

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    data: CreateCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create Stripe checkout session - User pays X USD, receives X USD (1:1)"""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe no configurado")
    
    # Validate amount
    amount_usd = round(data.amount_usd, 2)
    if amount_usd < MIN_AMOUNT_USD:
        raise HTTPException(status_code=400, detail=f"El monto mínimo es ${MIN_AMOUNT_USD} USD")
    if amount_usd > MAX_AMOUNT_USD:
        raise HTTPException(status_code=400, detail=f"El monto máximo es ${MAX_AMOUNT_USD} USD")
    
    # 1:1 conversion - user pays X USD, receives X USD
    total_received = amount_usd
    
    # Create unique transaction ID
    transaction_id = f"stripe_usd_{uuid.uuid4().hex[:12]}"
    
    # Build URLs
    success_url = f"{data.origin_url}/recharge/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{data.origin_url}/recharge/stripe"
    
    try:
        # Create Stripe Checkout Session in USD
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Recarga RIS App - ${amount_usd:.2f} USD",
                        "description": f"Recibirás ${total_received:.2f} USD en tu cartera RIS App"
                    },
                    "unit_amount": int(amount_usd * 100),  # Stripe uses cents
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=current_user.email,
            metadata={
                "user_id": current_user.user_id,
                "transaction_id": transaction_id,
                "amount_usd": str(amount_usd),
                "total_received": str(total_received),
                "for_terceros": str(data.for_terceros).lower()
            }
        )
        
        # Save payment transaction to DB
        payment_record = {
            "transaction_id": transaction_id,
            "stripe_session_id": session.id,
            "user_id": current_user.user_id,
            "user_email": current_user.email,
            "amount_usd": amount_usd,
            "total_received": total_received,  # Same as amount_usd (1:1)
            "currency": "USD",
            "for_terceros": data.for_terceros,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc)
        }
        await db.payment_transactions.insert_one(payment_record)
        
        logger.info(f"Stripe USD checkout created: {transaction_id} for user {current_user.user_id} - ${amount_usd} USD")
        
        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.id
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail=f"Error de Stripe: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating checkout: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear sesión de pago")

@router.get("/status/{session_id}")
async def get_payment_status(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Check payment status and process if completed"""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe no configurado")
    
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
            "amount_usd": transaction.get("amount_usd"),
            "total_received": transaction.get("total_received"),
            "message": "Pago ya procesado"
        }
    
    try:
        # Check with Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == "paid":
            # Check if not already processed
            existing = await db.payment_transactions.find_one({
                "stripe_session_id": session_id,
                "payment_status": "paid"
            })
            
            if not existing:
                total_received = transaction.get("total_received", transaction.get("amount_usd", 0))
                for_terceros = transaction.get("for_terceros", False)
                
                # Update balance (balance_ris stores USD value)
                balance_field = "balance_ris_terceros" if for_terceros else "balance_ris"
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$inc": {balance_field: total_received}}
                )
                
                # Update transaction record
                await db.payment_transactions.update_one(
                    {"stripe_session_id": session_id},
                    {
                        "$set": {
                            "payment_status": "paid",
                            "status": "completed",
                            "stripe_payment_intent": session.payment_intent,
                            "completed_at": datetime.now(timezone.utc)
                        }
                    }
                )
                
                # Create notification
                await db.notifications.insert_one({
                    "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": current_user.user_id,
                    "title": "💳 Recarga USD Exitosa",
                    "message": f"Se han añadido ${total_received:.2f} USD a tu {'saldo de terceros' if for_terceros else 'cartera'}.",
                    "type": "payment_success",
                    "read": False,
                    "created_at": datetime.now(timezone.utc)
                })
                
                # Send email notification
                try:
                    await notify_recharge_success(
                        email=current_user.email,
                        user_name=current_user.name or "Usuario",
                        amount=total_received,
                        method=f"Tarjeta (${transaction.get('amount_usd')} USD)",
                        balance_type="terceros" if for_terceros else "principal"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send recharge email: {e}")
                
                logger.info(f"Stripe USD payment completed: {session_id} - +${total_received} USD to {current_user.user_id}")
            
            return {
                "status": "completed",
                "payment_status": "paid",
                "amount_usd": transaction.get("amount_usd"),
                "total_received": transaction.get("total_received"),
                "message": "¡Pago exitoso! Tu saldo ha sido actualizado."
            }
        
        elif session.status == "expired":
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
                "payment_status": session.payment_status,
                "message": "Pago en proceso..."
            }
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error checking status: {e}")
        return {
            "status": "error",
            "payment_status": "unknown",
            "message": "Error al verificar estado del pago"
        }

@router.get("/history")
async def get_payment_history(current_user: User = Depends(get_current_user)):
    """Get user's USD payment history"""
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
        payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        
        # If webhook secret configured, verify signature
        if webhook_secret and sig_header:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            except stripe.error.SignatureVerificationError:
                logger.warning("Invalid Stripe webhook signature")
                raise HTTPException(status_code=400, detail="Invalid signature")
        else:
            # Parse without verification
            import json
            event = json.loads(payload)
        
        event_type = event.get("type") if isinstance(event, dict) else event.type
        logger.info(f"Stripe webhook received: {event_type}")
        
        # Handle checkout.session.completed
        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event.data.object
            session_id = session.get("id") if isinstance(session, dict) else session.id
            payment_status = session.get("payment_status") if isinstance(session, dict) else session.payment_status
            
            if payment_status == "paid" and session_id:
                transaction = await db.payment_transactions.find_one({
                    "stripe_session_id": session_id,
                    "payment_status": {"$ne": "paid"}
                })
                
                if transaction:
                    total_received = transaction.get("total_received", transaction.get("amount_usd", 0))
                    user_id = transaction.get("user_id")
                    for_terceros = transaction.get("for_terceros", False)
                    
                    # Update balance
                    balance_field = "balance_ris_terceros" if for_terceros else "balance_ris"
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$inc": {balance_field: total_received}}
                    )
                    
                    # Update transaction
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
                    
                    logger.info(f"Webhook: USD Payment {session_id} completed for user {user_id} - +${total_received} USD")
        
        return {"received": True}
        
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"received": True, "error": str(e)}
