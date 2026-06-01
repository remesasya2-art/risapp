"""
In-app notifications service
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

async def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",
    data: dict = None
) -> str:
    """Create an in-app notification for a user"""
    from database import db
    from services.push_notifications import send_push_to_user
    
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"
    
    notification = {
        "notification_id": notification_id,
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.notifications.insert_one(notification)
    
    # Also send push notification
    await send_push_to_user(user_id, title, message, data)
    
    logger.info(f"Notification created for user {user_id}: {title}")
    
    return notification_id
