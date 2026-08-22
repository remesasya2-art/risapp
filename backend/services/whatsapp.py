"""
WhatsApp notification service via Twilio
"""
import logging
from datetime import datetime, timezone
from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, ADMIN_WHATSAPP_NUMBER

logger = logging.getLogger(__name__)

async def send_whatsapp_notification(message_body: str) -> bool:
    """Send a WhatsApp notification to admin"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, ADMIN_WHATSAPP_NUMBER]):
        logger.warning("WhatsApp not configured - missing Twilio credentials")
        return False
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_FROM,
            to=ADMIN_WHATSAPP_NUMBER
        )
        logger.info(f"WhatsApp notification sent: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp: {e}")
        return False
