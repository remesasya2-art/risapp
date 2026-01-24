import os
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
ROOT_DIR = Path(__file__).parent
FIREBASE_CREDENTIALS_PATH = ROOT_DIR / 'secrets' / 'firebase-service-account.json'

firebase_app = None

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    global firebase_app
    
    if firebase_app is not None:
        return firebase_app
    
    try:
        if FIREBASE_CREDENTIALS_PATH.exists():
            cred = credentials.Certificate(str(FIREBASE_CREDENTIALS_PATH))
            firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
            return firebase_app
        else:
            logger.warning(f"Firebase credentials not found at {FIREBASE_CREDENTIALS_PATH}")
            return None
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")
        return None

# Initialize on module load
initialize_firebase()


class PushNotificationService:
    """Service for sending push notifications via Firebase Cloud Messaging"""
    
    @staticmethod
    async def send_withdrawal_completed_notification(
        fcm_token: str,
        transaction_id: str,
        amount_ris: float,
        amount_ves: float,
        beneficiary_name: str
    ) -> bool:
        """
        Send push notification when a withdrawal is completed
        
        Args:
            fcm_token: User's FCM device token
            transaction_id: Transaction ID
            amount_ris: Amount in RIS
            amount_ves: Amount in VES
            beneficiary_name: Name of the beneficiary
            
        Returns:
            True if notification was sent successfully
        """
        if not firebase_app:
            logger.warning("Firebase not initialized, skipping push notification")
            return False
        
        if not fcm_token:
            logger.warning("No FCM token provided, skipping push notification")
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="✅ Retiro Completado",
                    body=f"Tu retiro de {amount_ris:.2f} RIS ({amount_ves:.2f} VES) a {beneficiary_name} ha sido procesado exitosamente.",
                ),
                data={
                    "type": "withdrawal_completed",
                    "transaction_id": transaction_id,
                    "amount_ris": str(amount_ris),
                    "amount_ves": str(amount_ves),
                    "beneficiary_name": beneficiary_name,
                },
                token=fcm_token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#4CAF50",
                        sound="default",
                        channel_id="withdrawals"
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title="✅ Retiro Completado",
                                body=f"Tu retiro de {amount_ris:.2f} RIS ({amount_ves:.2f} VES) a {beneficiary_name} ha sido procesado exitosamente.",
                            ),
                            sound="default",
                            badge=1,
                        )
                    )
                )
            )
            
            response = messaging.send(message)
            logger.info(f"Push notification sent successfully: {response}")
            return True
            
        except messaging.UnregisteredError:
            logger.warning(f"FCM token is no longer valid: {fcm_token[:20]}...")
            return False
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False
    
    @staticmethod
    async def send_kyc_approved_notification(fcm_token: str, user_name: str) -> bool:
        """Send notification when KYC is approved"""
        if not firebase_app or not fcm_token:
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="🎉 Verificación Aprobada",
                    body=f"¡Felicidades {user_name}! Tu cuenta ha sido verificada. Ya puedes usar todas las funciones de RIS.",
                ),
                data={
                    "type": "kyc_approved",
                },
                token=fcm_token,
            )
            
            response = messaging.send(message)
            logger.info(f"KYC approval notification sent: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending KYC notification: {e}")
            return False
    
    @staticmethod
    async def send_kyc_rejected_notification(fcm_token: str, reason: str = "") -> bool:
        """Send notification when KYC is rejected"""
        if not firebase_app or not fcm_token:
            return False
        
        try:
            body = "Tu verificación no fue aprobada. Por favor, revisa tus documentos y vuelve a intentarlo."
            if reason:
                body = f"Tu verificación no fue aprobada: {reason}"
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title="❌ Verificación Rechazada",
                    body=body,
                ),
                data={
                    "type": "kyc_rejected",
                    "reason": reason,
                },
                token=fcm_token,
            )
            
            response = messaging.send(message)
            logger.info(f"KYC rejection notification sent: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending KYC rejection notification: {e}")
            return False
    
    @staticmethod
    async def send_general_notification(
        fcm_token: str, 
        title: str, 
        body: str,
        data: Optional[dict] = None
    ) -> bool:
        """Send a general notification"""
        if not firebase_app or not fcm_token:
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=fcm_token,
            )
            
            response = messaging.send(message)
            logger.info(f"General notification sent: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending general notification: {e}")
            return False


# Global instance
push_service = PushNotificationService()
