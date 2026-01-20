import os
import logging
from twilio.rest import Client
from typing import Optional

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.from_number = os.getenv('TWILIO_WHATSAPP_FROM')
        self.to_number = os.getenv('TWILIO_WHATSAPP_TO')
        
        if not all([self.account_sid, self.auth_token, self.from_number, self.to_number]):
            logger.warning("Twilio WhatsApp credentials not configured")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)
    
    async def send_withdrawal_notification(self, transaction_data: dict, user_data: dict) -> bool:
        """Send WhatsApp notification for new withdrawal request"""
        if not self.client:
            logger.warning("Twilio client not configured, skipping WhatsApp notification")
            return False
        
        try:
            beneficiary = transaction_data.get('beneficiary_data', {})
            amount_ris = transaction_data.get('amount_input', 0)
            amount_ves = transaction_data.get('amount_output', 0)
            transaction_id = transaction_data.get('transaction_id', 'N/A')
            
            # Format message
            message_body = f"""🔔 *NUEVO RETIRO PENDIENTE*

💰 Monto: {amount_ris:.2f} RIS → {amount_ves:.2f} VES
👤 Usuario: {user_data.get('name', 'N/A')}
📧 Email: {user_data.get('email', 'N/A')}

📋 *BENEFICIARIO:*
Nombre: {beneficiary.get('full_name', 'N/A')}
Banco: {beneficiary.get('bank', 'N/A')}
Cuenta: {beneficiary.get('account_number', 'N/A')}
Cédula: {beneficiary.get('id_document', 'N/A')}
Teléfono: {beneficiary.get('phone_number', 'N/A')}

🆔 ID: {transaction_id}

---
Procesa este retiro en el admin panel"""
            
            # Send message
            message = self.client.messages.create(
                from_=self.from_number,
                body=message_body,
                to=self.to_number
            )
            
            logger.info(f"WhatsApp notification sent: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp notification: {e}")
            return False
    
    async def send_completion_notification(self, transaction_id: str, user_phone: Optional[str] = None) -> bool:
        """Send completion notification (optional, if user provides phone)"""
        if not self.client or not user_phone:
            return False
        
        try:
            message_body = f"""✅ *TRANSACCIÓN COMPLETADA*

Tu retiro ha sido procesado exitosamente.

🆔 ID: {transaction_id}

Gracias por usar RIS App 🚀"""
            
            message = self.client.messages.create(
                from_=self.from_number,
                body=message_body,
                to=f"whatsapp:{user_phone}"
            )
            
            logger.info(f"Completion notification sent: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending completion notification: {e}")
            return False

# Global instance
whatsapp_service = WhatsAppService()
