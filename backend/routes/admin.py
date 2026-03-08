"""
Admin routes - User management, Withdrawals, Rates, KYC
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.user import User
from models.requests import UpdateRateRequest, ChangeRoleRequest, ResetPasswordAdminRequest
from routes.dependencies import get_admin_user, get_super_admin
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.notifications import create_notification
from services.email import send_admin_password_reset_email
from utils.security import generate_temp_password, hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# ============== USERS ==============

@router.get("/users")
async def get_all_users(admin: User = Depends(get_super_admin)):
    """Get all users"""
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return {"users": users}

@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: User = Depends(get_super_admin)):
    """Get user details"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Get transactions
    transactions = await db.transactions.find({"user_id": user_id}).sort("created_at", -1).to_list(100)
    
    return {
        "user": user,
        "transactions": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "type": t.get("type"),
                "status": t.get("status"),
                "amount_input": t.get("amount_input"),
                "amount_output": t.get("amount_output"),
                "created_at": t.get("created_at")
            }
            for t in transactions
        ]
    }

@router.post("/change-role")
async def change_user_role(request: ChangeRoleRequest, admin: User = Depends(get_super_admin)):
    """Change user role"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    valid_roles = ["user", "socio", "socio_gestor"]
    if request.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Rol inválido")
    
    update_data = {"role": request.new_role}
    
    if request.new_role == "socio":
        update_data["referral_code"] = request.partner_code or f"REF{uuid.uuid4().hex[:8].upper()}"
        update_data["is_partner"] = True
        update_data["became_partner_at"] = datetime.now(timezone.utc)
    elif request.new_role == "socio_gestor":
        update_data["gestor_code"] = request.gestor_code or f"GES{uuid.uuid4().hex[:6].upper()}"
        update_data["balance_ris_terceros"] = user.get("balance_ris_terceros", 0)
        update_data["became_gestor_at"] = datetime.now(timezone.utc)
    
    await db.users.update_one({"user_id": request.user_id}, {"$set": update_data})
    
    await create_notification(
        user_id=request.user_id,
        title="🎉 Rol Actualizado",
        message=f"Tu rol ha sido actualizado a: {request.new_role}",
        notification_type="role_change"
    )
    
    logger.info(f"User {request.user_id} role changed to {request.new_role} by {admin.user_id}")
    
    return {"message": "Rol actualizado", "new_role": request.new_role}

@router.post("/reset-password")
async def admin_reset_password(request: ResetPasswordAdminRequest, admin: User = Depends(get_super_admin)):
    """Admin reset user password"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    temp_password = generate_temp_password()
    
    await db.users.update_one(
        {"user_id": request.user_id},
        {
            "$set": {
                "password_hash": hash_password(temp_password),
                "password_set": True,
                "must_change_password": True
            }
        }
    )
    
    admin_user = await db.users.find_one({"user_id": admin.user_id})
    await send_admin_password_reset_email(user["email"], temp_password, admin_user.get("name", "Admin"))
    
    logger.info(f"Password reset for {user['email']} by admin {admin.user_id}")
    
    return {"message": "Contraseña restablecida y email enviado"}

# ============== WITHDRAWALS ==============

@router.get("/withdrawals/pending")
async def get_pending_withdrawals(admin: User = Depends(get_super_admin)):
    """Get pending withdrawals"""
    cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending"
    }).sort("created_at", 1)
    
    withdrawals = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "amount_input": tx.get("amount_input", 0),
            "amount_output": tx.get("amount_output", 0),
            "status": tx.get("status"),
            "beneficiary_data": tx.get("beneficiary_data", {}),
            "payment_type": tx.get("payment_type") or tx.get("beneficiary_data", {}).get("payment_type"),
            "is_gestor_transaction": tx.get("is_gestor_transaction", False),
            "client_name": tx.get("client_name"),
            "created_at": tx.get("created_at"),
            "pending_images": tx.get("pending_images", []),
            "whatsapp_active": tx.get("whatsapp_active", False),
        })
    
    return withdrawals

@router.get("/withdrawals/all")
async def get_all_withdrawals(admin: User = Depends(get_super_admin)):
    """Get all withdrawals"""
    cursor = db.transactions.find({"type": "withdrawal"}).sort("created_at", -1).limit(200)
    
    withdrawals = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_input": tx.get("amount_input", 0),
            "amount_output": tx.get("amount_output", 0),
            "rate": tx.get("rate", 0),
            "status": tx.get("status", "pending"),
            "beneficiary_data": tx.get("beneficiary_data", {}),
            "payment_type": tx.get("payment_type") or tx.get("beneficiary_data", {}).get("payment_type"),
            "is_gestor_transaction": tx.get("is_gestor_transaction", False),
            "client_name": tx.get("client_name"),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "proof_image": tx.get("proof_image"),
            "proof_images": tx.get("proof_images", []),
            "pending_images": tx.get("pending_images", []),
            "whatsapp_active": tx.get("whatsapp_active", False),
            "processed_by": tx.get("processed_by"),
        })
    
    return withdrawals

@router.post("/withdrawals/process/{transaction_id}")
async def process_withdrawal(
    transaction_id: str,
    action: str,
    proof_images: list = None,
    admin: User = Depends(get_super_admin)
):
    """Process a withdrawal (approve/reject)"""
    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    if transaction.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Transacción ya procesada")
    
    if action == "approve":
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "processed_by": admin.user_id,
            "whatsapp_active": False
        }
        
        if proof_images:
            update_data["proof_images"] = proof_images
        
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": update_data}
        )
        
        # Notify user
        await create_notification(
            user_id=transaction["user_id"],
            title="✅ Retiro Completado",
            message=f"Tu retiro de {transaction.get('amount_output', 0):.2f} VES ha sido procesado.",
            notification_type="withdrawal_completed"
        )
        
        # Update gestor transaction if applicable
        if transaction.get("gestor_transaction_id"):
            await db.gestor_transactions.update_one(
                {"transaction_id": transaction["gestor_transaction_id"]},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
            )
        
        message = "Retiro aprobado"
        
    elif action == "reject":
        # Refund balance
        await db.users.update_one(
            {"user_id": transaction["user_id"]},
            {"$inc": {"balance_ris": transaction.get("amount_input", 0)}}
        )
        
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {
                "$set": {
                    "status": "rejected",
                    "completed_at": datetime.now(timezone.utc),
                    "processed_by": admin.user_id,
                    "whatsapp_active": False
                }
            }
        )
        
        await create_notification(
            user_id=transaction["user_id"],
            title="❌ Retiro Rechazado",
            message=f"Tu retiro ha sido rechazado. El saldo ha sido devuelto.",
            notification_type="withdrawal_rejected"
        )
        
        message = "Retiro rechazado y saldo devuelto"
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")
    
    # Process next in queue
    await send_next_pending_withdrawal_whatsapp()
    
    logger.info(f"Withdrawal {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}

@router.get("/withdrawals/cleanup-check")
async def check_stuck_withdrawals(admin: User = Depends(get_super_admin)):
    """Check for stuck pending withdrawals"""
    stuck = await db.transactions.find({
        "type": "withdrawal",
        "status": "pending",
        "whatsapp_active": True
    }).to_list(100)
    
    return {
        "count": len(stuck),
        "transactions": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "amount_output": t.get("amount_output"),
                "created_at": t.get("created_at")
            }
            for t in stuck
        ]
    }

@router.post("/withdrawals/cleanup")
async def cleanup_stuck_withdrawals(admin: User = Depends(get_super_admin)):
    """Reset whatsapp_active for stuck withdrawals"""
    result = await db.transactions.update_many(
        {"type": "withdrawal", "status": "pending", "whatsapp_active": True},
        {"$set": {"whatsapp_active": False}}
    )
    
    # Restart queue
    await send_next_pending_withdrawal_whatsapp()
    
    logger.info(f"Cleaned up {result.modified_count} stuck withdrawals by {admin.user_id}")
    
    return {"message": f"Limpiados {result.modified_count} retiros atascados"}

# ============== PARTNERS/GESTORS ==============

@router.get("/partners")
async def get_all_partners(admin: User = Depends(get_super_admin)):
    """Get all partners (socios)"""
    partners = await db.users.find({"role": "socio"}).to_list(500)
    
    result = []
    for p in partners:
        # Get referrals count
        referrals_count = await db.users.count_documents({"referred_by": p.get("referral_code")})
        
        # Get earnings
        earnings = await db.partner_earnings.find({"partner_id": p["user_id"]}).to_list(1000)
        total_earnings = sum(e.get("amount", 0) for e in earnings)
        
        # This month
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_earnings = sum(
            e.get("amount", 0) for e in earnings
            if e.get("created_at") and e["created_at"].replace(tzinfo=timezone.utc) >= month_start
        )
        
        result.append({
            "user_id": p["user_id"],
            "name": p.get("name", ""),
            "email": p.get("email", ""),
            "referral_code": p.get("referral_code", ""),
            "referrals_count": referrals_count,
            "total_earnings": round(total_earnings, 2),
            "month_earnings": round(month_earnings, 2),
            "became_partner_at": p.get("became_partner_at"),
            "created_at": p.get("created_at")
        })
    
    return result

@router.get("/gestors")
async def get_all_gestors(admin: User = Depends(get_super_admin)):
    """Get all gestors with stats"""
    gestors = await db.users.find({"role": "socio_gestor"}).to_list(500)
    
    result = []
    for g in gestors:
        # Count transactions
        tx_count = await db.gestor_transactions.count_documents({"gestor_id": g["user_id"]})
        
        # Total volume
        transactions = await db.gestor_transactions.find({"gestor_id": g["user_id"]}).to_list(1000)
        total_volume = sum(t.get("amount_ris", 0) for t in transactions)
        
        result.append({
            "user_id": g["user_id"],
            "name": g.get("name", ""),
            "email": g.get("email", ""),
            "gestor_code": g.get("gestor_code", ""),
            "total_transactions": tx_count,
            "total_volume": round(total_volume, 2),
            "balance_ris": g.get("balance_ris", 0),
            "balance_ris_terceros": g.get("balance_ris_terceros", 0),
            "became_gestor_at": g.get("became_gestor_at"),
            "created_at": g.get("created_at")
        })
    
    return result

# ============== RATES ==============

@router.get("/rates")
async def get_rates(admin: User = Depends(get_super_admin)):
    """Get exchange rates"""
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    return rate or {"ris_to_ves": 92.0, "ves_to_ris": 0.0109}

@router.post("/rates")
async def update_rates(request: UpdateRateRequest, admin: User = Depends(get_super_admin)):
    """Update exchange rate"""
    await db.rates.update_one(
        {},
        {
            "$set": {
                "ris_to_ves": request.ris_to_ves,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": admin.user_id
            }
        },
        upsert=True
    )
    
    logger.info(f"Rate updated to {request.ris_to_ves} by {admin.user_id}")
    
    return {"message": "Tasa actualizada", "ris_to_ves": request.ris_to_ves}

# ============== KYC ==============

@router.get("/verifications/pending")
async def get_pending_verifications(admin: User = Depends(get_super_admin)):
    """Get pending KYC verifications"""
    users = await db.users.find({"verification_status": "pending"}, {"_id": 0, "password_hash": 0}).to_list(100)
    return users

@router.post("/verifications/process")
async def process_verification(user_id: str, action: str, reason: str = None, admin: User = Depends(get_super_admin)):
    """Process KYC verification"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if action == "approve":
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "verified", "verified_at": datetime.now(timezone.utc)}}
        )
        
        await create_notification(
            user_id=user_id,
            title="✅ Verificación Aprobada",
            message="Tu identidad ha sido verificada exitosamente.",
            notification_type="verification_approved"
        )
    elif action == "reject":
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "rejected", "rejection_reason": reason}}
        )
        
        await create_notification(
            user_id=user_id,
            title="❌ Verificación Rechazada",
            message=f"Tu verificación fue rechazada: {reason}",
            notification_type="verification_rejected"
        )
    
    logger.info(f"Verification {action}d for {user_id} by {admin.user_id}")
    
    return {"message": f"Verificación {action}da"}
