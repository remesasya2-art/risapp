"""
Common dependencies for route handlers
"""
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import Request, Header, HTTPException, Depends
from database import db
from models.user import User
from config import SECRET_KEY

logger = logging.getLogger(__name__)

async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Get current user from session token"""
    token = None
    
    # Try Authorization header first
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
    
    # Fall back to X-Session-ID header
    if not token:
        token = request.headers.get("X-Session-ID")
    
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token provided")
    
    # Find session
    session = await db.sessions.find_one({
        "session_token": token,
        "is_active": True
    })
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Check expiration
    if session.get("expires_at") and session["expires_at"] < datetime.now(timezone.utc):
        await db.sessions.update_one(
            {"session_token": token},
            {"$set": {"is_active": False}}
        )
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one({"user_id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if user.get("is_deleted"):
        raise HTTPException(status_code=401, detail="Account has been deleted")
    
    return User(**{k: v for k, v in user.items() if k != "_id"})

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or super_admin role"""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def get_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require super_admin role"""
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user

async def get_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Require verified user"""
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="User verification required")
    return current_user

def has_permission(user: User, permission: str) -> bool:
    """Check if user has a specific permission"""
    if user.role == "super_admin":
        return True
    return permission in (user.permissions or [])

def require_permission(permission: str):
    """Decorator to require a specific permission"""
    async def permission_checker(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
        return current_user
    return permission_checker
