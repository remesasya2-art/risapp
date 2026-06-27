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
    """Get current user from session token (cookie or header)"""
    session_token = None
    
    # Check cookie first
    session_token = request.cookies.get('session_token')
    
    # Fallback to Authorization header
    if not session_token and authorization:
        if authorization.startswith('Bearer '):
            session_token = authorization[7:]
    
    # Fall back to X-Session-ID header
    if not session_token:
        session_token = request.headers.get("X-Session-ID")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Find session (use user_sessions collection like server.py)
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Check expiration
    expires_at = session.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if user.get("is_deleted"):
        raise HTTPException(status_code=401, detail="Account has been deleted")
    if user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Esta cuenta ha sido suspendida")

    return User(**user)

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or super_admin role"""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def get_crm_user(current_user: User = Depends(get_current_user)) -> User:
    """Require CRM access: agent, admin or super_admin"""
    if current_user.role not in ["agent", "admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="CRM access required")
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
