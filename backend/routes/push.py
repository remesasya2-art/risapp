"""
Web Push notification routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from routes.dependencies import get_current_user
from web_push_service import web_push_service
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push/web", tags=["push"])


class WebPushSubscription(BaseModel):
    endpoint: str
    keys: dict


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Get VAPID public key for web push"""
    return {"public_key": web_push_service.get_public_key()}


@router.post("/subscribe")
async def subscribe_web_push(subscription: WebPushSubscription, current_user: User = Depends(get_current_user)):
    """Subscribe to web push notifications"""
    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": subscription.keys
    }
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"web_push_subscription": sub_info}}
    )
    return {"success": True}


@router.post("/unsubscribe")
async def unsubscribe_web_push(current_user: User = Depends(get_current_user)):
    """Unsubscribe from web push notifications"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$unset": {"web_push_subscription": ""}}
    )
    return {"success": True}


@router.get("/status")
async def get_web_push_status(current_user: User = Depends(get_current_user)):
    """Check if user has web push subscription"""
    user = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    return {"subscribed": "web_push_subscription" in user}


@router.post("/test")
async def test_web_push(current_user: User = Depends(get_current_user)):
    """Test web push notification"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    sub = user.get("web_push_subscription")
    if not sub:
        raise HTTPException(status_code=400, detail="No web push subscription")
    
    try:
        web_push_service.send_notification(sub, "Test", "Esta es una notificacion de prueba")
        return {"success": True}
    except Exception as e:
        logger.error(f"Web push error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
