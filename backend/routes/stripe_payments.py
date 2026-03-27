"""
Stripe Payment Routes - Handle USD card payments for RIS balance recharge
Uses official Stripe SDK for production payments
Targeted at US customers paying in USD
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

# USD Recharge packages - amounts in USD
# RIS amount calculated dynamically based on usd_to_ris rate from database
USD_RECHARGE_PACKAGES = {
    "usd_10": {"amount_usd": 10.0, "bonus": 0, "name": "$10 USD"},
    "usd_25": {"amount_usd": 25.0, "bonus": 5, "name": "$25 USD (+5% bonus)"},
    "usd_50": {"amount_usd": 50.0, "bonus": 10, "name": "$50 USD (+10% bonus)"},
    "usd_100": {"amount_usd": 100.0, "bonus": 15, "name": "$100 USD (+15% bonus)"}
}

class CreateCheckoutRequest(BaseModel):
    package_id: str
    origin_url: str
    for_terceros: bool = False

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

async def get_usd_to_ris_rate() -> float:
    """Get current USD to RIS exchange rate from database"""
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    if rate and rate.get("usd_to_ris"):
        return rate.get("usd_to_ris")
    return 5.5  # Default rate

@router.get("/packages")
async def get_recharge_packages():
    """Get available USD recharge packages with dynamic RIS calculation"""
    usd_to_ris = await get_usd_to_ris_rate()
    
    packages = []
    for key, pkg in USD_RECHARGE_PACKAGES.items():
        base_ris = pkg["amount_usd"] * usd_to_ris
        bonus_ris = base_ris * (pkg["bonus"] / 100)
        total_ris = base_ris + bonus_ris
        
        packages.append({
            "id": key,
            "name": pkg["name"],
            "amount_usd": pkg["amount_usd"],
            "bonus_percent": pkg["bonus"],
            "base_ris": round(base_ris, 2),
            "bonus_ris": round(bonus_ris, 2),
            "total_ris": round(total_ris, 2),
            "exchange_rate": usd_to_ris
        })
    
    return {
        "packages": packages,
        "current_rate": usd_to_ris,
        "currency": "USD"
    }

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    data: CreateCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Create Stripe checkout session for USD recharge"""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe no configurado")
    
    # Validate package
    if data.package_id not in USD_RECHARGE_PACKAGES:
        raise HTTPException(status_code=400, detail="Paquete inválido")
    
    package = USD_RECHARGE_PACKAGES[data.package_id]
    amount_usd = package["amount_usd"]
    bonus_percent = package["bonus"]
    
    # Get current exchange rate
    usd_to_ris = await get_usd_to_ris_rate()
    
    # Calculate RIS amount
    base_ris = amount_usd * usd_to_ris
    bonus_ris = base_ris * (bonus_percent / 100)
    total_ris = base_ris + bonus_ris
    
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
                    "currency": "usd",  # Changed from BRL to USD
                    "product_data": {
                        "name": f"Recarga RIS - {package['name']}",
                        "description": f"Recarga desde USA. Recibirás {total_ris:.2f} RIS (tasa: 1 USD = {usd_to_ris} RIS)"
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
                "package_id": data.package_id,
                "amount_usd": str(amount_usd),
                "bonus_percent": str(bonus_percent),
                "total_ris": str(total_ris),
                "usd_to_ris_rate": str(usd_to_ris),
                "for_terceros": str(data.for_terceros).lower()
            }
        )
        
        # Save payment transaction to DB
        payment_record = {
            "transaction_id": transaction_id,
            "stripe_session_id": session.id,
            "user_id": current_user.user_id,
            "user_email": current_user.email,
            "package_id": data.package_id,
            "amount_usd": amount_usd,
            "bonus_percent": bonus_percent,
            "base_ris": base_ris,
            "bonus_ris": bonus_ris,
            "total_ris": total_ris,
            "usd_to_ris_rate": usd_to_ris,
            "currency": "USD",
            "for_terceros": data.for_terceros,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc)
        }
        await db.payment_transactions.insert_one(payment_record)
        
        logger.info(f"Stripe USD checkout created: {transaction_id} for user {current_user.user_id} - ${amount_usd} USD -> {total_ris} RIS")
        
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
            "amount_ris": transaction.get("total_ris"),
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
                total_ris = transaction.get("total_ris", 0)
                for_terceros = transaction.get("for_terceros", False)
                
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
                    "message": f"Se han añadido {total_ris:.2f} RIS a tu {'saldo de terceros' if for_terceros else 'saldo'}. Pago de ${transaction.get('amount_usd')} USD.",
                    "type": "payment_success",
                    "read": False,
                    "created_at": datetime.now(timezone.utc)
                })
                
                # Send email notification
                try:
                    await notify_recharge_success(
                        email=current_user.email,
                        user_name=current_user.name or "Usuario",
                        amount=total_ris,
                        method=f"Tarjeta USD (${transaction.get('amount_usd')} USD)",
                        balance_type="terceros" if for_terceros else "principal"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send recharge email: {e}")
                
                logger.info(f"Stripe USD payment completed: {session_id} - +{total_ris} RIS to {current_user.user_id}")
            
            return {
                "status": "completed",
                "payment_status": "paid",
                "amount_usd": transaction.get("amount_usd"),
                "amount_ris": transaction.get("total_ris"),
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
                        {"stripe_session_id": session_id},
                        {
                            "$set": {
                                "payment_status": "paid",
                                "status": "completed",
                                "completed_at": datetime.now(timezone.utc)
                            }
                        }
                    )
                    
                    logger.info(f"Webhook: USD Payment {session_id} completed for user {user_id} - +{total_ris} RIS")
        
        return {"received": True}
        
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"received": True, "error": str(e)}
