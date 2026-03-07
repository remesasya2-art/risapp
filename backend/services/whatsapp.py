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

async def send_next_pending_withdrawal_whatsapp():
    """Send WhatsApp notification for the next pending withdrawal in FIFO order"""
    # Import here to avoid circular imports
    from database import db
    
    # Check if there's already an active WhatsApp withdrawal
    active = await db.transactions.find_one({
        "type": "withdrawal",
        "status": "pending",
        "whatsapp_active": True
    })
    
    if active:
        logger.info(f"FIFO: El retiro {active.get('display_id')} ya está activo")
        return
    
    # Get the next pending withdrawal (oldest first - FIFO)
    next_withdrawal = await db.transactions.find_one(
        {
            "type": "withdrawal",
            "status": "pending",
            "whatsapp_active": {"$ne": True}
        },
        sort=[("created_at", 1)]
    )
    
    if not next_withdrawal:
        logger.info("FIFO: No hay retiros pendientes en cola")
        return
    
    # Mark as active
    await db.transactions.update_one(
        {"transaction_id": next_withdrawal["transaction_id"]},
        {"$set": {"whatsapp_active": True}}
    )
    
    # Get user info
    user = await db.users.find_one({"user_id": next_withdrawal.get("user_id")})
    if not user:
        logger.error(f"User not found for withdrawal {next_withdrawal.get('transaction_id')}")
        return
    
    # Build message based on transaction type
    beneficiary = next_withdrawal.get('beneficiary_data', {})
    full_name = beneficiary.get('full_name', 'N/A')
    id_document = beneficiary.get('id_document', 'N/A')
    amount_ves = next_withdrawal.get('amount_output', 0)
    display_id = next_withdrawal.get('display_id', next_withdrawal.get('transaction_id', 'N/A')[:8])
    payment_type = beneficiary.get('payment_type', 'transferencia')
    is_gestor = next_withdrawal.get('is_gestor_transaction', False)
    client_name = next_withdrawal.get('client_name', '')
    
    # User info line
    user_info = f"👤 Cliente: {client_name}\n🏢 Gestor: {user.get('name', 'N/A')}" if is_gestor and client_name else f"👤 Usuario: {user.get('name', 'N/A')}"
    
    if payment_type == 'pago_movil':
        bank_code = beneficiary.get('bank_code', '') or beneficiary.get('bank', '')
        phone_number = beneficiary.get('phone_number', 'N/A')
        message = f"""{full_name}
{bank_code}
{id_document}
{phone_number}
{amount_ves:.2f} Bs

📱 PAGO MÓVIL
{user_info}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""
    else:
        account_number = beneficiary.get('account_number', 'N/A')
        bank_name = beneficiary.get('bank', '')
        message = f"""{full_name}
{account_number}
{id_document}
{amount_ves:.2f} Bs

🏦 TRANSFERENCIA ({bank_name})
{user_info}
🔢 ID: R{display_id}
🔔 NUEVO RETIRO PENDIENTE"""
    
    # Send WhatsApp
    success = await send_whatsapp_notification(message)
    if success:
        logger.info(f"FIFO: Notificación enviada para retiro {display_id}")
    else:
        logger.warning(f"FIFO: No se pudo enviar notificación para retiro {display_id}")
