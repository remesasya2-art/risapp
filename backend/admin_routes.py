# Admin Panel Routes for RIS App
# This module contains all admin-related endpoints

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId

# Admin permission checker
def check_permission(user_permissions: List[str], user_role: str, required_permission: str) -> bool:
    """Check if user has the required permission"""
    # Super admin has all permissions
    if user_role == "super_admin":
        return True
    
    # Admin has most permissions except admin management
    if user_role == "admin":
        admin_only_perms = ["admins.create", "admins.edit"]
        if required_permission not in admin_only_perms:
            return True
    
    # Check specific permissions
    return required_permission in user_permissions

# Request/Response Models
class CreateSubAdminRequest(BaseModel):
    email: str
    name: str
    permissions: List[str]

class UpdateSubAdminRequest(BaseModel):
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None

class ProcessWithdrawalRequest(BaseModel):
    transaction_id: str
    action: str  # "approve" or "reject"
    proof_image: Optional[str] = None  # base64 for approve
    rejection_reason: Optional[str] = None  # for reject

class ApproveKYCRequest(BaseModel):
    user_id: str
    action: str  # "approve" or "reject"
    rejection_reason: Optional[str] = None

class UpdateRateRequest(BaseModel):
    ris_to_ves: float

class AdminSupportResponse(BaseModel):
    user_id: str
    message: str

class CloseSupportRequest(BaseModel):
    user_id: str
    closing_message: Optional[str] = None
