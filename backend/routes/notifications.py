"""
Notification routes - User notifications management
"""
import logging
from fastapi import APIRouter, Depends

from database import db
from routes.dependencies import get_current_user
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user)):
    """Get user notifications"""
    notifications = await db.notifications.find(
        {"user_id": current_user.user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return notifications


@router.get("/notifications/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get unread notification count"""
    count = await db.notifications.count_documents({
        "user_id": current_user.user_id,
        "read": False
    })
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: User = Depends(get_current_user)):
    """Mark notification as read"""
    await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user.user_id},
        {"$set": {"read": True}}
    )
    return {"success": True}


@router.post("/notifications/mark-all-read")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    await db.notifications.update_many(
        {"user_id": current_user.user_id, "read": False},
        {"$set": {"read": True}}
    )
    return {"success": True}
