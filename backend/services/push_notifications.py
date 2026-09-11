"""
Push notification service (Firebase FCM and Web Push)
"""
import logging
import json
import httpx
from pywebpush import webpush, WebPushException
from config import FIREBASE_SERVER_KEY, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS_EMAIL

logger = logging.getLogger(__name__)

async def send_push_notification(push_token: str, title: str, body: str, data: dict = None) -> bool:
    """Send push notification via Firebase FCM"""
    if not FIREBASE_SERVER_KEY or not push_token:
        return False
    
    try:
        headers = {
            "Authorization": f"key={FIREBASE_SERVER_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "to": push_token,
            "notification": {
                "title": title,
                "body": body,
                "sound": "default",
                "badge": 1
            },
            "data": data or {}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://fcm.googleapis.com/fcm/send",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                logger.info(f"Push notification sent successfully")
                return True
            else:
                logger.error(f"FCM error: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return False

async def send_web_push_notification(subscription: dict, title: str, body: str, data: dict = None) -> bool:
    """Send web push notification via VAPID"""
    if not subscription or not VAPID_PRIVATE_KEY:
        return False
    
    try:
        payload = json.dumps({
            "title": title,
            "body": body,
            "data": data or {},
            "icon": "/icon-192.png",
            "badge": "/icon-192.png"
        })
        
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"}
        )
        
        logger.info(f"Web push notification sent successfully")
        return True
    except WebPushException as e:
        logger.error(f"Web push error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending web push: {e}")
        return False

async def send_push_to_user(user_id: str, title: str, body: str, data: dict = None) -> bool:
    """Send push notification to a specific user"""
    from database import db
    
    # Solo los dos campos que se usan. Sin proyeccion esto traia el usuario
    # ENTERO en cada aviso —documento de identidad, telefono, direcciones— y
    # `avisar_al_personal` dispara uno por destinatario.
    user = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "push_token": 1, "web_push_subscription": 1},
    )
    if not user:
        return False
    
    success = False
    
    # Try FCM first
    if user.get("push_token"):
        success = await send_push_notification(user["push_token"], title, body, data)
    
    # Try web push if FCM failed or not available
    if not success and user.get("web_push_subscription"):
        success = await send_web_push_notification(user["web_push_subscription"], title, body, data)
    
    return success

# `send_push_to_admins` vivia aca y no la llamaba nadie. Era una sexta forma
# de elegir destinatarios —admin + super_admin, tope 100, sin mirar
# `is_active`— esperando a que alguien la usara y repitiera el error. Quien
# avisa al equipo es `services/notifications.avisar_al_personal`, que elige
# por permiso y manda el push por el mismo camino que el aviso guardado.
