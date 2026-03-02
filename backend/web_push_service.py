"""
Web Push Notifications Service
Uses pywebpush library with VAPID authentication for browser push notifications
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from pywebpush import webpush, WebPushException
import time

logger = logging.getLogger(__name__)

class WebPushService:
    """Service for sending web push notifications to browsers"""
    
    def __init__(self):
        self.vapid_public_key = os.getenv('VAPID_PUBLIC_KEY')
        self.vapid_private_key = os.getenv('VAPID_PRIVATE_KEY')
        self.vapid_subject = os.getenv('VAPID_SUBJECT', 'mailto:admin@ris-app.com')
        
        if self.vapid_public_key and self.vapid_private_key:
            logger.info("Web Push Notification Service initialized with VAPID keys")
        else:
            logger.warning("VAPID keys not found - web push notifications disabled")
    
    def get_public_key(self) -> Optional[str]:
        """Get the VAPID public key for frontend subscription"""
        return self.vapid_public_key
    
    def send_notification(
        self,
        subscription: Dict[str, Any],
        title: str,
        body: str,
        icon: str = "/logo-ris.jpeg",
        badge: str = "/logo-ris.jpeg",
        url: str = "/",
        tag: str = None,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        Send a push notification to a single subscription
        
        Args:
            subscription: Push subscription object from browser
            title: Notification title
            body: Notification body text
            icon: URL to notification icon
            badge: URL to notification badge
            url: URL to open when notification is clicked
            tag: Tag for notification grouping
            data: Additional data to send with notification
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.vapid_public_key or not self.vapid_private_key:
            logger.error("Cannot send notification - VAPID keys not configured")
            return False
        
        try:
            payload = json.dumps({
                "title": title,
                "body": body,
                "icon": icon,
                "badge": badge,
                "url": url,
                "tag": tag or f"ris-notification-{int(time.time())}",
                "data": data or {},
                "timestamp": int(time.time() * 1000)
            })
            
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=self.vapid_private_key,
                vapid_claims={
                    "sub": self.vapid_subject
                }
            )
            
            logger.info(f"Web push notification sent: {title}")
            return True
            
        except WebPushException as e:
            logger.error(f"Web push notification failed: {e}")
            if e.response and e.response.status_code == 410:
                logger.info("Subscription expired - should be removed from database")
            return False
        except Exception as e:
            logger.error(f"Error sending web push notification: {e}")
            return False
    
    def send_to_multiple(
        self,
        subscriptions: List[Dict[str, Any]],
        title: str,
        body: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Send notification to multiple subscriptions"""
        success = 0
        failed = 0
        expired = []
        
        for sub in subscriptions:
            try:
                if self.send_notification(sub, title, body, **kwargs):
                    success += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        
        return {
            "success": success,
            "failed": failed,
            "expired_endpoints": expired
        }
    
    # Notification templates
    def notify_transaction_completed(self, subscription: Dict, amount: float, tx_type: str) -> bool:
        """Notify user that a transaction was completed"""
        if tx_type == "recharge":
            title = "💰 Recarga Completada"
            body = f"Tu recarga de {amount:.2f} RIS ha sido acreditada a tu cuenta."
        elif tx_type == "withdrawal":
            title = "✅ Envío Completado"
            body = f"Tu envío de {amount:.2f} RIS ha sido procesado exitosamente."
        else:
            title = "✅ Transacción Completada"
            body = f"Tu transacción de {amount:.2f} RIS ha sido completada."
        
        return self.send_notification(subscription, title, body, url="/history")
    
    def notify_transaction_rejected(self, subscription: Dict, tx_type: str, reason: str = "") -> bool:
        """Notify user that a transaction was rejected"""
        if tx_type == "recharge":
            title = "❌ Recarga Rechazada"
            body = f"Tu recarga ha sido rechazada. {reason}".strip()
        else:
            title = "❌ Transacción Rechazada"
            body = f"Tu transacción ha sido rechazada. {reason}".strip()
        
        return self.send_notification(subscription, title, body, url="/history")
    
    def notify_kyc_approved(self, subscription: Dict) -> bool:
        """Notify user that KYC verification was approved"""
        return self.send_notification(
            subscription,
            title="🎉 Cuenta Verificada",
            body="¡Tu identidad ha sido verificada! Ya puedes usar todas las funciones de RIS.",
            url="/profile"
        )
    
    def notify_kyc_rejected(self, subscription: Dict, reason: str = "") -> bool:
        """Notify user that KYC verification was rejected"""
        return self.send_notification(
            subscription,
            title="⚠️ Verificación Rechazada",
            body=f"Tu verificación fue rechazada. {reason}".strip(),
            url="/verification"
        )
    
    def notify_rate_change(self, subscription: Dict, old_rate: float, new_rate: float) -> bool:
        """Notify user about exchange rate change"""
        direction = "📈" if new_rate > old_rate else "📉"
        return self.send_notification(
            subscription,
            title=f"{direction} Cambio de Tasa",
            body=f"La tasa cambió de {old_rate:.2f} a {new_rate:.2f} VES por RIS.",
            url="/"
        )
    
    def notify_payment_received(self, subscription: Dict, amount: float) -> bool:
        """Notify user that a payment was received"""
        return self.send_notification(
            subscription,
            title="💵 Pago Recibido",
            body=f"Has recibido un pago de {amount:.2f} RIS.",
            url="/history"
        )


# Global instance
web_push_service = WebPushService()
