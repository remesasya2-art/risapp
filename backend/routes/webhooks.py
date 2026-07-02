"""
Webhooks routes - WhatsApp/Twilio integration for withdrawal processing
"""
import logging
import re
import os
import uuid
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response
from twilio.rest import Client
from twilio.request_validator import RequestValidator

from database import db
from services.money import to_decimal, to_decimal128
from services.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Twilio config
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")

# Directory for storing proof images
PROOF_IMAGES_DIR = "/app/backend/static/comprobantes"
os.makedirs(PROOF_IMAGES_DIR, exist_ok=True)


async def download_twilio_image(media_url: str, display_id: str, index: int) -> str:
    """Download image from Twilio and return as base64 data URI for reliable storage"""
    import base64
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                follow_redirects=True,
                timeout=30.0
            )
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "image/jpeg")
                b64 = base64.b64encode(response.content).decode("utf-8")
                data_uri = f"data:{content_type};base64,{b64}"
                logger.info(f"Image downloaded as base64 for {display_id} ({len(response.content)} bytes)")
                return data_uri
            else:
                logger.error(f"Failed to download image: {response.status_code}")
                return media_url
                
    except Exception as e:
        logger.error(f"Error downloading Twilio image: {e}")
        return media_url


def send_whatsapp_reply(to: str, message: str):
    """Send a WhatsApp reply message"""
    try:
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
            logger.error("Twilio credentials not configured")
            return False
        
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_FROM,
            to=to
        )
        logger.info(f"WhatsApp reply sent to {to}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp reply: {e}")
        return False


@router.post("/twilio/whatsapp")
async def twilio_whatsapp_webhook(request: Request):
    """
    Handle incoming WhatsApp messages from Twilio
    
    Flow:
    1. Admin receives withdrawal notification
    2. Admin sends payment proof image(s)
    3. System responds: "📷 X imagen(es) recibida(s) para ID: XXXXX ✅ Escribe 'listo' para procesar"
    4. Admin writes "listo"
    5. System marks withdrawal as completed and sends next in queue
    """
    try:
        form_data = await request.form()

        # --- SECURITY: verify the request really comes from Twilio ---
        if not TWILIO_AUTH_TOKEN:
            logger.error("TWILIO_AUTH_TOKEN not set - rejecting webhook")
            return Response(status_code=503, content="Webhook not configured")

        # Reconstruct the public URL Twilio actually called (Railway sits behind a proxy,
        # so request.url.scheme/host may be the internal http one).
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        public_url = f"{proto}://{host}{request.url.path}"
        if request.url.query:
            public_url += f"?{request.url.query}"

        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(public_url, dict(form_data), signature):
            logger.warning(f"Invalid Twilio signature for webhook (url={public_url})")
            return Response(status_code=403, content="Invalid signature")

        from_number = form_data.get("From", "")

        # --- SECURITY: only the authorized admin number can act on withdrawals ---
        if not ADMIN_WHATSAPP_NUMBER or from_number != ADMIN_WHATSAPP_NUMBER:
            logger.warning(f"Webhook from unauthorized number: {from_number}")
            return Response(content="", media_type="text/xml")

        body = form_data.get("Body", "").strip().lower()
        num_media = int(form_data.get("NumMedia", 0))
        
        logger.info(f"WhatsApp webhook: from={from_number}, body={body}, media={num_media}")
        
        # Find the active withdrawal being processed
        active_withdrawal = await db.transactions.find_one({
            "type": {"$in": ["withdrawal", "send"]},
            "status": "pending",
            "whatsapp_active": True
        }, sort=[("created_at", 1)])
        
        if not active_withdrawal:
            logger.info("No active withdrawal found for WhatsApp response")
            return Response(content="", media_type="text/xml")
        
        display_id = active_withdrawal.get("display_id", active_withdrawal.get("transaction_id", "")[:8])
        tx_id = active_withdrawal.get("transaction_id")
        user_id = active_withdrawal.get("user_id")
        
        # Handle image uploads
        if num_media > 0:
            # Download images from Twilio and save locally
            image_urls = []
            for i in range(num_media):
                media_url = form_data.get(f"MediaUrl{i}")
                if media_url:
                    # Download and save the image
                    local_url = await download_twilio_image(media_url, display_id, i)
                    image_urls.append(local_url)
            
            # Store images in transaction
            existing_images = active_withdrawal.get("proof_images", [])
            all_images = existing_images + image_urls
            
            await db.transactions.update_one(
                {"transaction_id": tx_id},
                {"$set": {
                    "proof_images": all_images,
                    "last_image_at": datetime.now(timezone.utc)
                }}
            )
            
            # Send confirmation reply
            reply_message = f"""📷 {len(image_urls)} imagen(es) recibida(s) para ID: {display_id}

✅ Escribe "listo" para procesar
📷 O envía más imágenes"""
            
            send_whatsapp_reply(from_number, reply_message)
            logger.info(f"Images received for withdrawal {display_id}: {len(image_urls)} images")
            
            return Response(content="", media_type="text/xml")
        
        # Handle "listo" command to complete withdrawal
        if body in ["listo", "lista", "hecho", "completado", "ok", "done"]:
            # Mark withdrawal as completed
            await db.transactions.update_one(
                {"transaction_id": tx_id},
                {"$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                    "whatsapp_active": False,
                    "whatsapp_completed_by": from_number
                }}
            )
            
            # Get user info
            user = await db.users.find_one({"user_id": user_id})
            user_name = user.get("name", "Usuario") if user else "Usuario"
            amount_ves = active_withdrawal.get("amount_output", 0)
            
            # Create notification for user
            await create_notification(
                user_id=user_id,
                title="✅ Retiro Completado",
                message=f"Tu retiro de {amount_ves:.2f} VES ha sido procesado exitosamente.",
                notification_type="withdrawal_completed"
            )
            
            # Send completion confirmation to admin
            reply_message = f"""✅ RETIRO COMPLETADO

🔢 ID: {display_id}
👤 Usuario: {user_name}
💰 Monto: {amount_ves:.2f} VES

Procesando siguiente retiro..."""
            
            send_whatsapp_reply(from_number, reply_message)
            logger.info(f"Withdrawal {display_id} completed via WhatsApp")
            
            # Send next pending withdrawal
            from services.whatsapp import send_next_pending_withdrawal_whatsapp
            await send_next_pending_withdrawal_whatsapp()
            
            return Response(content="", media_type="text/xml")
        
        # Handle "cancelar" command
        if body in ["cancelar", "cancel", "rechazar"]:
            await db.transactions.update_one(
                {"transaction_id": tx_id},
                {"$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.now(timezone.utc),
                    "whatsapp_active": False,
                    "cancel_reason": "Cancelado por admin via WhatsApp"
                }}
            )
            
            # Refund user balance
            amount_ris = active_withdrawal.get("amount_input", 0)
            await db.users.update_one(
                {"user_id": user_id},
                {"$inc": {"balance_ris": to_decimal128(to_decimal(amount_ris))}}
            )
            
            # Notify user
            await create_notification(
                user_id=user_id,
                title="❌ Retiro Cancelado",
                message=f"Tu retiro ha sido cancelado. El saldo ha sido devuelto a tu cuenta.",
                notification_type="withdrawal_cancelled"
            )
            
            reply_message = f"""❌ RETIRO CANCELADO

🔢 ID: {display_id}
💰 Saldo devuelto al usuario

Procesando siguiente retiro..."""
            
            send_whatsapp_reply(from_number, reply_message)
            logger.info(f"Withdrawal {display_id} cancelled via WhatsApp")
            
            # Send next pending withdrawal
            from services.whatsapp import send_next_pending_withdrawal_whatsapp
            await send_next_pending_withdrawal_whatsapp()
            
            return Response(content="", media_type="text/xml")
        
        # Handle "info" command - show current withdrawal details
        if body in ["info", "datos", "detalles"]:
            beneficiary = active_withdrawal.get("beneficiary_data", {})
            payment_type = beneficiary.get("payment_type", "transferencia")
            amount_ves = active_withdrawal.get("amount_output", 0)
            
            if payment_type == "pago_movil":
                details = f"""📋 DETALLES RETIRO {display_id}

👤 {beneficiary.get('full_name', 'N/A')}
🏦 {beneficiary.get('bank_code', 'N/A')}
📄 {beneficiary.get('id_document', 'N/A')}
📱 {beneficiary.get('phone_number', 'N/A')}
💰 {amount_ves:.2f} VES

📱 PAGO MÓVIL"""
            else:
                details = f"""📋 DETALLES RETIRO {display_id}

👤 {beneficiary.get('full_name', 'N/A')}
🏦 {beneficiary.get('account_number', 'N/A')}
📄 {beneficiary.get('id_document', 'N/A')}
💰 {amount_ves:.2f} VES

🏦 TRANSFERENCIA"""
            
            send_whatsapp_reply(from_number, details)
            return Response(content="", media_type="text/xml")
        
        # Unknown command - show help
        help_message = f"""🔔 Retiro activo: {display_id}

📷 Envía comprobante de pago
✅ Escribe "listo" para completar
❌ Escribe "cancelar" para rechazar
📋 Escribe "info" para ver detalles"""
        
        send_whatsapp_reply(from_number, help_message)
        
        return Response(content="", media_type="text/xml")
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return Response(content="", media_type="text/xml")
