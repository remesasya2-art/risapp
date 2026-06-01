import os
import logging
from typing import Optional
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
)

logger = logging.getLogger(__name__)

class PushNotificationService:
    """Service for sending push notifications via Expo"""
    
    def __init__(self):
        self.push_client = PushClient()
    
    async def send_notification(
        self,
        push_token: str,
        title: str,
        body: str,
        data: Optional[dict] = None
    ) -> bool:
        """Send a push notification"""
        try:
            if not push_token:
                logger.warning("No push token provided")
                return False
            
            # Check if it's an Expo push token
            if not push_token.startswith('ExponentPushToken') and not push_token.startswith('e-'):
                logger.warning(f"Invalid Expo push token format: {push_token[:20]}...")
                return False
            
            message = PushMessage(
                to=push_token,
                title=title,
                body=body,
                data=data or {},
                sound="default",
                badge=1,
            )
            
            response = self.push_client.publish(message)
            
            # Check for errors
            if response.status == "ok":
                logger.info(f"Push notification sent successfully to {push_token[:30]}...")
                return True
            else:
                logger.error(f"Push notification failed: {response.message}")
                return False
                
        except DeviceNotRegisteredError:
            logger.warning(f"Device not registered: {push_token[:30]}...")
            return False
        except PushServerError as e:
            logger.error(f"Push server error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False
    
    async def send_withdrawal_completed_notification(
        self,
        push_token: str,
        transaction_id: str,
        amount_ris: float,
        amount_ves: float,
        beneficiary_name: str
    ) -> bool:
        """Send notification when withdrawal is completed"""
        return await self.send_notification(
            push_token=push_token,
            title="✅ Retiro Completado",
            body=f"Tu retiro de {amount_ris:.2f} RIS ({amount_ves:.2f} VES) a {beneficiary_name} fue procesado.",
            data={
                "type": "withdrawal_completed",
                "transaction_id": transaction_id,
                "amount_ris": str(amount_ris),
                "amount_ves": str(amount_ves),
            }
        )
    
    async def send_kyc_approved_notification(self, push_token: str, user_name: str) -> bool:
        """Send notification when KYC is approved"""
        return await self.send_notification(
            push_token=push_token,
            title="🎉 Verificación Aprobada",
            body=f"¡Felicidades {user_name}! Tu cuenta ha sido verificada.",
            data={"type": "kyc_approved"}
        )
    
    async def send_kyc_rejected_notification(self, push_token: str, reason: str = "") -> bool:
        """Send notification when KYC is rejected"""
        body = "Tu verificación no fue aprobada. Revisa tus documentos."
        if reason:
            body = f"Tu verificación no fue aprobada: {reason}"
        
        return await self.send_notification(
            push_token=push_token,
            title="❌ Verificación Rechazada",
            body=body,
            data={"type": "kyc_rejected", "reason": reason}
        )
    
    async def send_recharge_completed_notification(
        self,
        push_token: str,
        amount_ris: float
    ) -> bool:
        """Send notification when recharge is completed"""
        return await self.send_notification(
            push_token=push_token,
            title="💰 Recarga Exitosa",
            body=f"Se han acreditado {amount_ris:.2f} RIS a tu cuenta.",
            data={"type": "recharge_completed", "amount": str(amount_ris)}
        )


# Global instance
push_service = PushNotificationService()
