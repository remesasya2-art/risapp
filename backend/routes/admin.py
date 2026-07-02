"""
Admin routes - User management, Withdrawals, Rates, KYC
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from database import db
from services.money import from_db, to_float
from models.user import User
from models.requests import UpdateRateRequest, ChangeRoleRequest, ResetPasswordAdminRequest
from pydantic import BaseModel
from routes.dependencies import get_admin_user, get_super_admin, get_crm_user
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.notifications import create_notification
from services.email import send_admin_password_reset_email
from services.email_notifications import send_email
from utils.security import generate_temp_password, hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# ============== MAINTENANCE ==============

# ============== DANGER ZONE: DATA WIPE ==============

_ALL_DATA_COLLECTIONS = [
    "transactions",
    "usdt_operations",
    "usdt_ledger",
    "usdt_balance",
    "bank_ledger",
    "bank_accounts",
    "accounting_rates",
    "payment_transactions",
    "admin_payment_records",
    "pending_verifications",
    "gestor_pix_payments",
    "gestor_transactions",
    "notifications",
    "support_messages",
    "counters",
]

_ACCOUNTING_COLLECTIONS = [
    "usdt_operations",
    "usdt_ledger",
    "usdt_balance",
    "bank_ledger",
    "bank_accounts",
    "accounting_rates",
]


class WipeRequest(BaseModel):
    confirmation: str = ""


async def _wipe_collections(collections: list[str]) -> dict:
    """Delete all documents from the given collections. Returns count map."""
    result = {}
    for name in collections:
        try:
            existing = await db.list_collection_names()
            if name in existing:
                res = await db[name].delete_many({})
                if res.deleted_count > 0:
                    result[name] = res.deleted_count
        except Exception as e:
            logger.error(f"Error wiping {name}: {e}")
            result[name] = f"error: {e}"
    return result


async def _hide_from_admin(collection_name: str) -> int:
    """Soft-delete: mark docs as hidden from admin views without deleting them.
    Returns count of docs updated."""
    try:
        res = await db[collection_name].update_many(
            {"hidden_from_admin": {"$ne": True}},
            {"$set": {"hidden_from_admin": True}}
        )
        return res.modified_count
    except Exception as e:
        logger.error(f"Error hiding {collection_name}: {e}")
        return 0


async def _record_audit(admin: User, action: str, deleted: dict, total: int, extra: dict = None):
    """Record a sensitive admin action in the audit_log collection."""
    try:
        await db.audit_log.insert_one({
            "admin_email": admin.email,
            "admin_user_id": admin.user_id,
            "action": action,
            "deleted": deleted,
            "total_deleted": total,
            "extra": extra or {},
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"Error recording audit log: {e}")


@router.post("/wipe-all")
async def wipe_all_data(
    request: WipeRequest,
    admin: User = Depends(get_super_admin)
):
    """
    DANGER: Wipes ALL transactional data from the database.
    Resets user balances to 0. Preserves users, rates, and app config.
    Requires confirmation='CONFIRMAR' in body.
    """
    if request.confirmation != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Confirmación requerida: envía 'CONFIRMAR'")

    deleted = await _wipe_collections(_ALL_DATA_COLLECTIONS)
    balance_reset = await db.users.update_many(
        {},
        {"$set": {"balance_ris": 0, "balance_ris_terceros": 0}}
    )

    # Soft-delete: hide user transactions from admin views (users still see their own)
    hidden_tx = await _hide_from_admin("transactions")
    hidden_pay = await _hide_from_admin("payment_transactions")

    logger.warning(f"Super admin {admin.email} wiped ALL data: {deleted}, hidden transactions: {hidden_tx}")

    total = sum(v for v in deleted.values() if isinstance(v, int)) + hidden_tx + hidden_pay
    await _record_audit(admin, "wipe_all", deleted, total, {
        "users_balance_reset": balance_reset.modified_count,
        "hidden_transactions": hidden_tx,
        "hidden_payment_transactions": hidden_pay,
    })

    return {
        "success": True,
        "message": "Datos operacionales eliminados completamente",
        "deleted": deleted,
        "total_deleted": total,
        "hidden_transactions": hidden_tx,
        "users_balance_reset": balance_reset.modified_count
    }


@router.post("/accounting/wipe")
async def wipe_accounting_data(
    request: WipeRequest,
    admin: User = Depends(get_super_admin)
):
    """
    DANGER: Wipes only accounting data (banks, ledgers, USDT operations, rates).
    Does NOT touch transactions or user balances.
    Requires confirmation='CONFIRMAR' in body.
    """
    if request.confirmation != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Confirmación requerida: envía 'CONFIRMAR'")

    deleted = await _wipe_collections(_ACCOUNTING_COLLECTIONS)

    # Also hide transactions from the accounting report
    hidden_tx = await _hide_from_admin("transactions")

    logger.warning(f"Super admin {admin.email} wiped accounting data: {deleted}, hidden transactions: {hidden_tx}")

    total = sum(v for v in deleted.values() if isinstance(v, int)) + hidden_tx
    await _record_audit(admin, "wipe_accounting", deleted, total, {
        "hidden_transactions": hidden_tx,
    })

    return {
        "success": True,
        "message": "Datos de contabilidad eliminados",
        "deleted": deleted,
        "total_deleted": total,
        "hidden_transactions": hidden_tx
    }


@router.get("/hidden-transactions")
async def get_hidden_transactions(
    limit: int = 500,
    admin: User = Depends(get_super_admin)
):
    """List all transactions currently hidden from admin view (for restore UI)."""
    cursor = db.transactions.find(
        {"hidden_from_admin": True},
        {"_id": 0}
    ).sort("created_at", -1).limit(min(limit, 2000))

    items = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")}, {"_id": 0, "name": 1, "email": 1})
        items.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "type": tx.get("type"),
            "status": tx.get("status"),
            "amount_input": tx.get("amount_input") or tx.get("amount_ris", 0),
            "amount_output": tx.get("amount_output") or tx.get("amount_ves", 0),
            "currency": tx.get("currency"),
            "route": tx.get("route"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "created_at": tx.get("created_at").isoformat() if hasattr(tx.get("created_at"), "isoformat") else str(tx.get("created_at")),
        })

    return {"transactions": items, "count": len(items)}


class RestoreRequest(BaseModel):
    transaction_ids: list[str] = []
    restore_all: bool = False


@router.post("/restore-transactions")
async def restore_transactions(
    request: RestoreRequest,
    admin: User = Depends(get_super_admin)
):
    """Restore hidden transactions (set hidden_from_admin=False).
    Either pass transaction_ids=[...] or restore_all=true.
    """
    if request.restore_all:
        res = await db.transactions.update_many(
            {"hidden_from_admin": True},
            {"$set": {"hidden_from_admin": False}}
        )
        restored = res.modified_count
    elif request.transaction_ids:
        res = await db.transactions.update_many(
            {"transaction_id": {"$in": request.transaction_ids}, "hidden_from_admin": True},
            {"$set": {"hidden_from_admin": False}}
        )
        restored = res.modified_count
    else:
        raise HTTPException(status_code=400, detail="Debes pasar transaction_ids o restore_all=true")

    logger.warning(f"Super admin {admin.email} restored {restored} transactions (restore_all={request.restore_all})")

    await _record_audit(admin, "restore_transactions", {}, restored, {
        "restore_all": request.restore_all,
        "requested_ids": len(request.transaction_ids),
    })

    return {
        "success": True,
        "message": f"{restored} transacciones restauradas",
        "restored": restored,
    }


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 100,
    admin: User = Depends(get_super_admin)
):
    """Get the last N entries of the audit log (super admin only)."""
    entries = await db.audit_log.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(min(limit, 500)).to_list(500)

    # Serialize datetimes
    for e in entries:
        ts = e.get("timestamp")
        if ts and hasattr(ts, "isoformat"):
            e["timestamp"] = ts.isoformat()

    return {"entries": entries, "count": len(entries)}


# ============== MAINTENANCE ==============

@router.post("/fix-whatsapp-queue")
async def fix_whatsapp_queue(admin: User = Depends(get_super_admin)):
    """Reset WhatsApp queue - unblock all stuck withdrawals and trigger next notification"""
    # Unblock all stuck withdrawals
    result = await db.transactions.update_many(
        {"whatsapp_active": True},
        {"$set": {"whatsapp_active": False}}
    )
    
    # Trigger next pending withdrawal notification
    await send_next_pending_withdrawal_whatsapp()
    
    logger.info(f"WhatsApp queue fixed by {admin.user_id}. Unblocked: {result.modified_count}")
    
    return {
        "message": "Cola de WhatsApp corregida",
        "unblocked": result.modified_count
    }


@router.post("/fix-media-urls")
async def fix_media_urls(admin: User = Depends(get_super_admin)):
    """Download Twilio images and convert to base64, update in transactions"""
    import re
    import httpx
    import base64
    
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    
    # Find all transactions with non-base64 proof images (Twilio URLs or proxy URLs)
    transactions = await db.transactions.find({
        "$or": [
            {"proof_images": {"$exists": True, "$ne": []}},
            {"proof_image": {"$exists": True, "$ne": None}}
        ]
    }).to_list(1000)
    
    fixed_count = 0
    errors = []
    
    async with httpx.AsyncClient() as client:
        for tx in transactions:
            proof_images = tx.get("proof_images", [])
            proof_image = tx.get("proof_image")
            tx_id = tx.get("transaction_id", "unknown")
            needs_update = False
            update_data = {}
            
            # Handle array of images
            if proof_images:
                new_images = []
                for i, url in enumerate(proof_images):
                    if url and not url.startswith("data:") and ("api.twilio.com" in url or "/api/media/twilio/" in url):
                        # Extract Twilio URL
                        twilio_url = url
                        if "/api/media/twilio/" in url:
                            twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{url.replace('/api/media/twilio/', '')}"
                        
                        try:
                            response = await client.get(
                                twilio_url,
                                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                                follow_redirects=True,
                                timeout=30.0
                            )
                            if response.status_code == 200:
                                content_type = response.headers.get("content-type", "image/jpeg")
                                b64 = base64.b64encode(response.content).decode("utf-8")
                                new_images.append(f"data:{content_type};base64,{b64}")
                                needs_update = True
                            else:
                                new_images.append(url)
                                errors.append(f"{tx_id}[{i}]: HTTP {response.status_code}")
                        except Exception as e:
                            new_images.append(url)
                            errors.append(f"{tx_id}[{i}]: {str(e)[:50]}")
                    else:
                        new_images.append(url)
                
                if needs_update:
                    update_data["proof_images"] = new_images
            
            # Handle single proof_image
            if proof_image and not proof_image.startswith("data:") and ("api.twilio.com" in proof_image or "/api/media/twilio/" in proof_image):
                twilio_url = proof_image
                if "/api/media/twilio/" in proof_image:
                    twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{proof_image.replace('/api/media/twilio/', '')}"
                
                try:
                    response = await client.get(
                        twilio_url,
                        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                        follow_redirects=True,
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        content_type = response.headers.get("content-type", "image/jpeg")
                        b64 = base64.b64encode(response.content).decode("utf-8")
                        update_data["proof_image"] = f"data:{content_type};base64,{b64}"
                        needs_update = True
                    else:
                        errors.append(f"{tx_id}_single: HTTP {response.status_code}")
                except Exception as e:
                    errors.append(f"{tx_id}_single: {str(e)[:50]}")
            
            if update_data:
                await db.transactions.update_one(
                    {"transaction_id": tx_id},
                    {"$set": update_data}
                )
                fixed_count += 1
    
    logger.info(f"Fixed media URLs in {fixed_count} transactions by {admin.user_id}")
    
    return {
        "message": f"Convertidas {fixed_count} transacciones a base64",
        "transactions_fixed": fixed_count,
        "errors": errors[:10]
    }

# ============== USERS ==============

@router.get("/users")
async def get_all_users(admin: User = Depends(get_crm_user)):
    """Get all users"""
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return {"users": users}

@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: User = Depends(get_crm_user)):
    """Get user details"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Get transactions
    transactions = await db.transactions.find({"user_id": user_id, "hidden_from_admin": {"$ne": True}}).sort("created_at", -1).to_list(100)
    
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

@router.get("/users/{user_id}/complete")
async def get_user_complete_history(user_id: str, admin: User = Depends(get_crm_user)):
    """Get complete user history including profile, KYC, stats, transactions, and beneficiaries"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Get KYC/verification data
    kyc = await db.verifications.find_one({"user_id": user_id}, {"_id": 0})
    
    # Merge KYC images into user profile
    if kyc:
        user["id_document_image"] = kyc.get("id_document_image")
        user["cpf_image"] = kyc.get("cpf_image")
        user["selfie_image"] = kyc.get("selfie_image")
    
    # Get all transactions
    all_transactions = await db.transactions.find({"user_id": user_id, "hidden_from_admin": {"$ne": True}}).sort("created_at", -1).to_list(500)
    
    # Separate recharges and withdrawals
    recharges = [t for t in all_transactions if t.get("type") == "recharge"]
    withdrawals = [t for t in all_transactions if t.get("type") in ["withdrawal", "send"]]
    
    # Calculate stats
    total_recharged = sum(t.get("amount_ris", 0) or t.get("amount_output", 0) for t in recharges if t.get("status") == "completed")
    total_withdrawn = sum(t.get("amount_ris", 0) or t.get("amount_input", 0) for t in withdrawals if t.get("status") == "completed")
    total_ves_sent = sum(t.get("amount_ves", 0) or t.get("amount_output", 0) for t in withdrawals if t.get("status") == "completed")
    
    # Get beneficiaries
    beneficiaries = await db.beneficiaries.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    
    return {
        "profile": user,
        "kyc": kyc,
        "stats": {
            "total_recharged_ris": total_recharged,
            "total_withdrawn_ris": total_withdrawn,
            "total_ves_sent": total_ves_sent,
            "total_transactions": len(all_transactions)
        },
        "recharges": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "status": t.get("status"),
                "amount_ris": t.get("amount_ris") or t.get("amount_output"),
                "amount_brl": t.get("amount_brl") or t.get("amount_input"),
                "created_at": t.get("created_at"),
                "completed_at": t.get("completed_at")
            }
            for t in recharges
        ],
        "withdrawals": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "status": t.get("status"),
                "amount_ris": t.get("amount_ris") or t.get("amount_input"),
                "amount_ves": t.get("amount_ves") or t.get("amount_output"),
                "beneficiary": t.get("beneficiary"),
                "created_at": t.get("created_at"),
                "completed_at": t.get("completed_at")
            }
            for t in withdrawals
        ],
        "beneficiaries": beneficiaries
    }

@router.post("/change-role")
async def change_user_role(request: ChangeRoleRequest, admin: User = Depends(get_super_admin)):
    """Change user role"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Protect the original super admin from being modified by others
    if user.get("email") == "marshalljulio46@gmail.com" and admin.user_id != request.user_id:
        raise HTTPException(status_code=403, detail="No puedes modificar al administrador principal")
    
    valid_roles = ["user", "socio", "socio_gestor", "super_admin"]
    if request.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Rol inválido")
    
    update_data = {"role": request.new_role}
    
    if request.new_role == "socio":
        update_data["referral_code"] = request.partner_code or f"REF{uuid.uuid4().hex[:8].upper()}"
        update_data["is_partner"] = True
        update_data["became_partner_at"] = datetime.now(timezone.utc)
    elif request.new_role == "socio_gestor":
        update_data["gestor_code"] = request.gestor_code or f"GES{uuid.uuid4().hex[:6].upper()}"
        update_data["balance_ris_terceros"] = to_float(from_db(user.get("balance_ris_terceros", 0)))
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

class SetAgentRequest(BaseModel):
    is_agent: bool

@router.post("/users/{user_id}/set-agent")
async def set_user_agent(user_id: str, data: SetAgentRequest, admin: User = Depends(get_super_admin)):
    """Promueve a un usuario a agente de soporte, o le quita el rol (solo super admin)."""
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="No se puede cambiar el rol de un super administrador")
    if target.get("email") == "marshalljulio46@gmail.com":
        raise HTTPException(status_code=403, detail="No puedes modificar al administrador principal")
    new_role = "agent" if data.is_agent else "user"
    await db.users.update_one({"user_id": user_id}, {"$set": {"role": new_role}})
    logger.info(f"User {user_id} agent role set to {data.is_agent} by {admin.user_id}")
    return {"success": True, "role": new_role}

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
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
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
    cursor = db.transactions.find({
        "type": "withdrawal",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", -1).limit(200)
    
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

@router.post("/withdrawals/process")
async def process_withdrawal(
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process a withdrawal (approve/reject)"""
    transaction_id = request.get("transaction_id")
    action = request.get("action")
    proof_images = request.get("proof_images")
    bank_id = request.get("bank_id")
    
    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")
    
    if transaction.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Transaccion ya procesada")
    
    if action == "approve":
        # La contabilidad de bancos se lleva en la app externa. Aquí ya NO se
        # descuenta de bancos internos ni se exige seleccionar banco: el admin
        # solo registra el pago y su comprobante. El banco es opcional.
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "processed_by": admin.user_id,
            "whatsapp_active": False,
        }
        if bank_id:
            update_data["paid_from_bank"] = bank_id
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
        _refund_amount = transaction.get("amount_input", 0)
        _refunded_user = await db.users.find_one_and_update(
            {"user_id": transaction["user_id"]},
            {"$inc": {"balance_ris": _refund_amount}},
            return_document=True
        )
        # Libro mayor RIS: crédito de devolución (no interrumpe el rechazo)
        try:
            from services.ledger import record_ris_entry
            _bal_after = (_refunded_user or {}).get("balance_ris")
            _bal_after = to_float(from_db(_bal_after)) if _bal_after is not None else None
            await record_ris_entry(
                user_id=transaction["user_id"],
                movement_type="refund_envio",
                amount=_refund_amount,
                direction="credit",
                account="balance_ris",
                balance_before=(_bal_after - _refund_amount) if _bal_after is not None else None,
                balance_after=_bal_after,
                reference_kind="transaction",
                reference_id=transaction_id,
                transaction_id=transaction_id,
                display_id=transaction.get("display_id"),
                actor_type="admin",
                actor_id=admin.user_id,
                counterparty=transaction.get("beneficiary_data"),
                metadata={"currency_output": transaction.get("currency_output"), "amount_output": transaction.get("amount_output")},
                notes="Devolución por retiro rechazado",
            )
        except Exception as e:
            logger.warning(f"Ledger refund_envio no registrado: {e}")
        
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
        "whatsapp_active": True,
        "hidden_from_admin": {"$ne": True}
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

# ============== VES RECHARGES ADMIN ==============

@router.get("/recharges/ves/pending")
async def get_pending_ves_recharges(admin: User = Depends(get_super_admin)):
    """Get pending VES recharge requests"""
    cursor = db.transactions.find({
        "type": "recharge_ves",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", -1).limit(100)
    
    recharges = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        recharges.append({
            "transaction_id": tx.get("transaction_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_ves": tx.get("amount_ves", 0),
            "amount_ris": tx.get("amount_ris", 0),
            "rate_used": tx.get("rate_used", 0),
            "status": tx.get("status", "pending"),
            "proof_image": tx.get("proof_image"),
            "created_at": tx.get("created_at"),
        })
    
    return {"recharges": recharges}


@router.get("/ordenes/pendientes")
async def get_ordenes_pendientes(admin: User = Depends(get_super_admin)):
    """Área unificada de 'Órdenes por procesar'.

    Junta en una sola lista normalizada todas las órdenes pendientes de los
    distintos flujos (RIS→VES, BTC→VES, VES→RIS) para que el super_admin las
    procese desde un solo lugar. NO descuenta bancos internos: la contabilidad
    se lleva en la app externa. La info completa queda disponible aquí.
    """
    ordenes = []
    user_cache = {}

    async def _user(uid):
        if not uid:
            return {}
        if uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        return user_cache[uid]

    # 1) RIS → VES y RIS → Reais (retiros): el admin paga y sube comprobante.
    #    Se distinguen por currency_output (VES vs BRL).
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "pending", "hidden_from_admin": {"$ne": True}}
    ).sort("created_at", 1):
        u = await _user(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        cur_out = str(tx.get("currency_output") or "VES").upper()
        if cur_out in ("BRL", "REAIS", "REAL"):
            flujo, flujo_label, unidad_dest = "ris_reais", "RIS → Reais", "BRL"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cpf") or b.get("documento", ""),
                "banco": "",
                "telefono": "",
                "cuenta": "",
                "tipo_pago": "pix_br",
                "pix_key": b.get("pix_key", ""),
            }
        else:
            flujo, flujo_label, unidad_dest = "ris_ves", "RIS → VES", "VES"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula") or b.get("id_document", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                "telefono": b.get("phone") or b.get("phone_number", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
                "pix_key": "",
            }
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": flujo,
            "flujo_label": flujo_label,
            "accion": "pagar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_input", 0), "unidad": "RIS"},
            "destino": {"valor": tx.get("amount_output", 0), "unidad": unidad_dest},
            "beneficiario": beneficiario,
            "comprobante_usuario": None,
        })

    # 2) BTC → VES (remesas pagadas): el admin paga VES y sube comprobante
    async for r in db.btc_remesas.find({"estado": "pagado"}, {"_id": 0}).sort("pagado_en", 1):
        u = await _user(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        ordenes.append({
            "orden_id": r.get("remesa_id"),
            "flujo": "btc_ves",
            "flujo_label": "BTC → VES",
            "accion": "pagar",
            "display_id": r.get("display_id") or (r.get("remesa_id") or "")[:8],
            "created_at": r.get("pagado_en") or r.get("creado_en"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": r.get("usd_cliente", 0), "unidad": "USD"},
            "destino": {"valor": r.get("ves_recibe", 0), "unidad": "VES"},
            "beneficiario": {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula", ""),
                "banco": b.get("bank", ""),
                "telefono": b.get("phone", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type", ""),
            },
            "comprobante_usuario": None,
        })

    # 3) VES → RIS (recargas): el admin REVISA el comprobante del usuario y aprueba
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "pending", "hidden_from_admin": {"$ne": True}}
    ).sort("created_at", 1):
        u = await _user(tx.get("user_id"))
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": "ves_ris",
            "flujo_label": "VES → RIS",
            "accion": "aprobar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_ves", 0), "unidad": "VES"},
            "destino": {"valor": tx.get("amount_ris", 0), "unidad": "RIS"},
            "beneficiario": None,
            "comprobante_usuario": tx.get("proof_image"),
        })

    # Más antiguas primero (orden cronológico robusto ante created_at None)
    ordenes.sort(key=lambda o: str(o.get("created_at") or ""))
    return {"ordenes": ordenes, "total": len(ordenes)}

@router.get("/reportes/procesados")
async def reporte_procesados(
    period: str = Query("day", regex="^(day|month|year|range)$"),
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    formato: str = Query("json", regex="^(json|csv)$"),
    admin: User = Depends(get_super_admin),
):
    """Reporte de TODO lo procesado (4 flujos) por día / mes / año o rango.
    Para period="range" usa date_from y date_to (ambos YYYY-MM-DD, inclusivos).
    Devuelve JSON (vista previa + totales) o CSV (descarga para Excel o para la
    app de contabilidad externa). La información completa se genera aquí.
    """
    from datetime import timedelta as _td
    def _parse(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    try:
        if period == "range":
            if not date_from or not date_to:
                raise HTTPException(status_code=400, detail="Indica la fecha desde y hasta (YYYY-MM-DD)")
            start = _parse(date_from).replace(hour=0, minute=0, second=0, microsecond=0)
            end = _parse(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
            if end <= start:
                raise HTTPException(status_code=400, detail="El rango de fechas es inválido (desde debe ser ≤ hasta)")
        else:
            if not date:
                raise HTTPException(status_code=400, detail="Indica la fecha (YYYY-MM-DD)")
            base = _parse(date)
            if period == "day":
                start = base.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + _td(days=1)
            elif period == "month":
                start = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
            else:  # year
                start = base.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (use YYYY-MM-DD)")

    user_cache = {}
    async def _user(uid):
        if not uid:
            return {}
        if uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        return user_cache[uid]

    rows = []
    # Retiros completados (RIS→VES y RIS→Reais)
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "completed", "completed_at": {"$gte": start, "$lt": end}}
    ):
        u = await _user(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        es_brl = str(tx.get("currency_output") or "VES").upper() in ("BRL", "REAIS", "REAL")
        rows.append({
            "fecha_procesado": tx.get("completed_at"),
            "flujo": "RIS → Reais" if es_brl else "RIS → VES",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cpf") or b.get("cedula") or b.get("id_document", ""),
            "pix": b.get("pix_key", ""),
            "banco": "" if es_brl else (b.get("bank") or b.get("bank_code", "")),
            "monto_origen": tx.get("amount_input", 0),
            "unidad_origen": "RIS",
            "monto_destino": tx.get("amount_output", 0),
            "unidad_destino": "BRL" if es_brl else "VES",
            "tasa": tx.get("rate", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if (tx.get("proof_images") or tx.get("proof_image")) else "no",
        })

    # Recargas VES aprobadas (VES→RIS)
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "approved", "processed_at": {"$gte": start, "$lt": end}}
    ):
        u = await _user(tx.get("user_id"))
        rows.append({
            "fecha_procesado": tx.get("processed_at"),
            "flujo": "VES → RIS",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": "",
            "documento": "",
            "pix": "",
            "banco": "",
            "monto_origen": tx.get("amount_ves", 0),
            "unidad_origen": "VES",
            "monto_destino": tx.get("amount_ris", 0),
            "unidad_destino": "RIS",
            "tasa": tx.get("rate_used", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if tx.get("proof_image") else "no",
        })

    # Remesas BTC enviadas (BTC→VES)
    async for r in db.btc_remesas.find(
        {"estado": "enviado", "enviado_en": {"$gte": start, "$lt": end}}, {"_id": 0}
    ):
        u = await _user(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        rows.append({
            "fecha_procesado": r.get("enviado_en"),
            "flujo": "BTC → VES",
            "referencia": r.get("display_id") or r.get("remesa_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cedula", ""),
            "pix": "",
            "banco": b.get("bank", ""),
            "monto_origen": r.get("usd_cliente", 0),
            "unidad_origen": "USD",
            "monto_destino": r.get("ves_recibe", 0),
            "unidad_destino": "VES",
            "tasa": r.get("tasa_ves", ""),
            "procesado_por": r.get("operador_id", ""),
            "comprobante": "sí" if r.get("comprobante_pago") else "no",
        })

    rows.sort(key=lambda x: str(x.get("fecha_procesado") or ""))

    def fmtfecha(d):
        if not d:
            return ""
        try:
            return d.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(d)

    if formato == "csv":
        import csv as _csv
        import io as _io
        from fastapi.responses import StreamingResponse as _SR
        buf = _io.StringIO()
        buf.write("\ufeff")  # BOM para que Excel respete los acentos
        w = _csv.writer(buf)
        w.writerow(["Fecha", "Flujo", "Referencia", "Usuario", "Email",
                    "Beneficiario", "Documento", "Llave PIX", "Banco",
                    "Monto origen", "Unidad", "Monto destino", "Unidad",
                    "Tasa", "Procesado por", "Comprobante"])
        for r in rows:
            w.writerow([
                fmtfecha(r["fecha_procesado"]), r["flujo"], r["referencia"], r["usuario"], r["usuario_email"],
                r["beneficiario"], r["documento"], r["pix"], r["banco"],
                r["monto_origen"], r["unidad_origen"], r["monto_destino"], r["unidad_destino"],
                r["tasa"], r["procesado_por"], r["comprobante"],
            ])
        buf.seek(0)
        etiqueta = f"{date_from}_a_{date_to}" if period == "range" else (date or "")
        filename = f"reporte_{period}_{etiqueta}.csv"
        return _SR(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                   headers={"Content-Disposition": f"attachment; filename={filename}"})

    # JSON: vista previa + totales por flujo
    totales = {}
    for r in rows:
        totales[r["flujo"]] = totales.get(r["flujo"], 0) + 1
        r["fecha_procesado"] = fmtfecha(r["fecha_procesado"])
    return {
        "period": period,
        "date": date,
        "date_from": date_from,
        "date_to": date_to,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": len(rows),
        "totales_por_flujo": totales,
        "rows": rows,
    }


@router.get("/recharges/ves")
async def get_all_ves_recharges(admin: User = Depends(get_super_admin)):
    """Get all VES recharge requests"""
    cursor = db.transactions.find({
        "type": "recharge_ves",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", -1).limit(100)
    
    recharges = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        recharges.append({
            "transaction_id": tx.get("transaction_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_ves": tx.get("amount_ves", 0),
            "amount_ris": tx.get("amount_ris", 0),
            "rate_used": tx.get("rate_used", 0),
            "status": tx.get("status", "pending"),
            "proof_image": tx.get("proof_image"),
            "destination_bank": tx.get("destination_bank"),
            "destination_bank_id": tx.get("destination_bank_id"),
            "destination_bank_name": tx.get("destination_bank_name"),
            "rejection_reason": tx.get("rejection_reason"),
            "created_at": tx.get("created_at"),
            "processed_at": tx.get("processed_at"),
            "processed_by": tx.get("processed_by"),
        })
    
    return recharges


@router.get("/recharges/ves/check-reference")
async def check_ves_reference(
    digits: str,
    exclude_transaction_id: str = "",
    admin: User = Depends(get_super_admin)
):
    """Avisa si esos 3 digitos de referencia ya aparecen en OTRA recarga VES
    (posible pago duplicado/colusion). Solo informa; no aprueba ni rechaza.
    El criterio: el RIS le corresponde a quien la registro primero."""
    digits = str(digits or "").strip()[:3]
    if len(digits) < 3:
        return {"digits": digits, "has_collision": False, "matches": []}
    current = None
    if exclude_transaction_id:
        current = await db.transactions.find_one(
            {"transaction_id": exclude_transaction_id}, {"user_id": 1}
        )
    current_user_id = (current or {}).get("user_id")
    q = {"type": "recharge_ves", "reference_digits": digits}
    if exclude_transaction_id:
        q["transaction_id"] = {"$ne": exclude_transaction_id}
    matches = []
    cursor = db.transactions.find(q).sort("created_at", 1).limit(20)
    async for t in cursor:
        u = await db.users.find_one(
            {"user_id": t.get("user_id")}, {"email": 1, "full_name": 1, "name": 1}
        ) or {}
        matches.append({
            "transaction_id": t.get("transaction_id"),
            "user_id": t.get("user_id"),
            "user_name": u.get("full_name") or u.get("name"),
            "user_email": u.get("email"),
            "amount_ves": t.get("amount_ves") or t.get("amount_input"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "is_other_user": t.get("user_id") != current_user_id,
        })
    other_user = [m for m in matches if m["is_other_user"]]
    return {
        "digits": digits,
        "has_collision": len(other_user) > 0,
        "matches": matches,
        "first_registered": matches[0] if matches else None,
    }


@router.post("/recharges/ves/process/{transaction_id}")
async def process_ves_recharge(
    transaction_id: str, 
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process a VES recharge (approve/reject).
    The bank to credit is taken automatically from the transaction's
    destination_bank_id (set when the user created the recharge)."""
    action = request.get("action")
    rejection_reason = request.get("rejection_reason", "")
    reference_digits = str(request.get("reference_digits", "") or "").strip()[:3]
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Accion invalida")
    
    recharge = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "type": "recharge_ves"
    })
    
    if not recharge:
        raise HTTPException(status_code=404, detail="Recarga no encontrada")
    
    if recharge.get("status") != "pending":
        return {"message": "Esta recarga ya fue procesada", "already_processed": True}
    
    user_id = recharge.get("user_id")
    amount_ris = recharge.get("amount_ris") or recharge.get("amount_output", 0)
    amount_ves = recharge.get("amount_ves") or recharge.get("amount_input", 0)
    
    # Resolve destination bank from the transaction itself.
    # Backwards compatibility: older transactions may only have `destination_bank` (legacy code).
    bank_id = recharge.get("destination_bank_id")
    if not bank_id and recharge.get("destination_bank"):
        from routes.transactions import resolve_ves_bank
        bank_id, _ = await resolve_ves_bank(recharge.get("destination_bank"))
    # Final fallback: optional override from request body
    if not bank_id:
        bank_id = request.get("bank_id")
    
    if action == "approve":
        if not bank_id:
            raise HTTPException(
                status_code=400,
                detail="No se pudo identificar el banco destino. El usuario no eligió un banco válido al crear la recarga."
            )
        bank = await db.bank_accounts.find_one({"bank_id": bank_id})
        if not bank:
            raise HTTPException(status_code=404, detail="Banco destino no encontrado en contabilidad")
        
        # Register in bank ledger (VES received from user)
        new_balance = bank["balance"] + amount_ves
        await db.bank_accounts.update_one({"bank_id": bank_id}, {"$inc": {"balance": amount_ves}})
        
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "full_name": 1, "name": 1, "email": 1})
        user_name = user_doc.get("full_name", user_doc.get("name", user_doc.get("email", ""))) if user_doc else ""
        
        await db.bank_ledger.insert_one({
            "bank_id": bank_id, "bank_name": bank["name"],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "type": "entrada",
            "concept": f"Recarga VES de {user_name} (TX {transaction_id[:8]})",
            "amount": amount_ves, "balance_after": round(new_balance, 2),
            "reference": transaction_id, "notes": "Recarga VES aprobada",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Update recharge status
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {
                "status": "approved",
                "processed_at": datetime.now(timezone.utc),
                "processed_by": admin.user_id,
                "received_in_bank": bank_id,
                "destination_bank_id": bank_id,
                "destination_bank_name": bank["name"],
                "reference_digits": reference_digits,
            }}
        )
        
        # Add balance to user
        _rch_user = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"balance_ris": amount_ris}},
            return_document=True
        )
        # Libro mayor RIS (no interrumpe la aprobación)
        try:
            from services.ledger import record_ris_entry
            _rch_after = (_rch_user or {}).get("balance_ris")
            _rch_after = to_float(from_db(_rch_after)) if _rch_after is not None else None
            await record_ris_entry(
                user_id=user_id,
                movement_type="recarga_ves",
                amount=amount_ris,
                direction="credit",
                account="balance_ris",
                balance_before=(_rch_after - amount_ris) if _rch_after is not None else None,
                balance_after=_rch_after,
                reference_kind="transaction",
                reference_id=transaction_id,
                transaction_id=transaction_id,
                actor_type="admin",
                actor_id=admin.user_id,
                rate=(amount_ves / amount_ris) if amount_ris else None,
                rate_kind="ves_to_ris",
                amount_output=amount_ves,
                currency_output="VES",
                metadata={"destination_bank_id": bank_id},
                notes="Recarga VES → RIS aprobada",
            )
        except Exception as e:
            logger.warning(f"Ledger recarga_ves no registrado: {e}")
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga VES Aprobada",
            message=f"Tu recarga de {amount_ves:.2f} VES ha sido aprobada. Se han añadido {amount_ris:.2f} RIS a tu saldo.",
            notification_type="recharge_approved",
            data={"transaction_id": transaction_id, "amount_ris": amount_ris}
        )
        
        message = f"Recarga aprobada. Se añadieron {amount_ris:.2f} RIS al usuario."
        
    elif action == "reject":
        if not rejection_reason:
            raise HTTPException(status_code=400, detail="Debes proporcionar un motivo de rechazo")
        
        # Update recharge status
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejection_reason": rejection_reason,
                    "processed_at": datetime.now(timezone.utc),
                    "processed_by": admin.user_id
                }
            }
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga VES Rechazada",
            message=f"Tu recarga de {amount_ves:.2f} VES ha sido rechazada. Motivo: {rejection_reason}",
            notification_type="recharge_rejected",
            data={"transaction_id": transaction_id, "reason": rejection_reason}
        )
        
        message = "Recarga rechazada."
    
    logger.info(f"VES recharge {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}


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
            "balance_ris": to_float(from_db(g.get("balance_ris", 0))),
            "balance_ris_terceros": to_float(from_db(g.get("balance_ris_terceros", 0))),
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
    """Update exchange rates - 3 independent rates"""
    update_fields = {"updated_at": datetime.now(timezone.utc), "updated_by": admin.user_id}
    
    if request.ris_to_ves is not None:
        update_fields["ris_to_ves"] = request.ris_to_ves
    
    if request.ves_to_ris_rate is not None:
        update_fields["ves_to_ris_rate"] = request.ves_to_ris_rate
    
    if request.brl_to_ris is not None:
        update_fields["brl_to_ris"] = request.brl_to_ris
    
    if len(update_fields) == 2:  # Only has updated_at and updated_by
        raise HTTPException(status_code=400, detail="Debes proporcionar al menos una tasa")
    
    await db.rates.update_one(
        {},
        {"$set": update_fields},
        upsert=True
    )
    
    logger.info(f"Rates updated by {admin.user_id}: {update_fields}")

    # Log manual rate changes to rate_history
    try:
        from services.rate_history import log_if_changed
        if request.ris_to_ves is not None:
            await log_if_changed(db, "brl_ves", request.ris_to_ves, "manual", admin_email=admin.email)
        if request.ves_to_ris_rate is not None:
            await log_if_changed(db, "ves_brl", request.ves_to_ris_rate, "manual", admin_email=admin.email)
    except Exception as e:
        logger.warning(f"Rate history log failed: {e}")

    return {"message": "Tasa actualizada", **update_fields}


@router.get("/rate-history")
async def get_rate_history(
    limit: int = 200,
    route: str = None,
    admin: User = Depends(get_super_admin)
):
    """Get rate change history (super admin only). Filter by route if provided."""
    query = {}
    if route:
        query["route"] = route
    cursor = db.rate_history.find(query, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 1000))
    entries = await cursor.to_list(1000)
    for e in entries:
        ts = e.get("timestamp")
        if ts and hasattr(ts, "isoformat"):
            e["timestamp"] = ts.isoformat()
    return {"entries": entries, "count": len(entries)}


# ============== AUTO RATE CONFIG ==============

# ============== BCV RATES ==============

@router.get("/bcv-rates")
async def get_bcv_rates(admin: User = Depends(get_admin_user)):
    """Get latest BCV snapshot (USD/EUR/CNY/TRY/RUB to VES)."""
    from services.bcv_scraper import get_latest
    latest = await get_latest(db)
    return latest or {"rates": {}, "value_date": None, "fetched_at": None}


@router.get("/bcv-rates/history")
async def get_bcv_rates_history(limit: int = 50, admin: User = Depends(get_admin_user)):
    """Get BCV rate history."""
    from services.bcv_scraper import get_history
    entries = await get_history(db, limit=limit)
    return {"entries": entries, "count": len(entries)}


@router.post("/bcv-rates/refresh")
async def refresh_bcv_rates(admin: User = Depends(get_admin_user)):
    """Force fetch BCV rates right now."""
    from services.bcv_scraper import fetch_bcv_rates, save_snapshot, get_latest
    try:
        snap = await fetch_bcv_rates()
        saved = await save_snapshot(db, snap)
        latest = await get_latest(db)
        return {"success": True, "saved_new_snapshot": saved, "latest": latest}
    except Exception as e:
        logger.error(f"BCV refresh failed: {e}")
        raise HTTPException(status_code=502, detail=f"No se pudo contactar BCV: {e}")


class AutoRateConfigRequest(BaseModel):
    enabled: bool | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None
    work_days: list[int] | None = None
    delta_brl_ves: float | None = None
    delta_ves_brl: float | None = None


@router.get("/auto-rate")
async def get_auto_rate_config(admin: User = Depends(get_super_admin)):
    """Get current auto-rate configuration and status."""
    from services.rate_engine import load_auto_rate_config, is_off_hours, caracas_now
    config = await load_auto_rate_config(db)
    now = caracas_now()
    return {
        **config,
        "is_off_hours_now": is_off_hours(config, now),
        "current_caracas_time": now.isoformat(),
    }


@router.post("/auto-rate")
async def update_auto_rate_config(
    request: AutoRateConfigRequest,
    admin: User = Depends(get_super_admin)
):
    """Update auto-rate configuration."""
    update_fields = {}
    for field in ["enabled", "work_start_hour", "work_end_hour", "work_days", "delta_brl_ves", "delta_ves_brl"]:
        val = getattr(request, field)
        if val is not None:
            update_fields[field] = val

    if not update_fields:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un campo")

    update_fields["updated_at"] = datetime.now(timezone.utc)
    update_fields["updated_by"] = admin.user_id

    await db.app_settings.update_one(
        {"setting_id": "auto_rate"},
        {"$set": {"setting_id": "auto_rate", **update_fields}},
        upsert=True
    )

    logger.info(f"Auto-rate config updated by {admin.email}: {update_fields}")
    return {"success": True, "message": "Configuración actualizada", **update_fields}

# ============== KYC ==============

@router.get("/verifications/pending")
async def get_pending_verifications(admin: User = Depends(get_super_admin)):
    """Get pending KYC verifications with documents"""
    # Get users with pending verification
    users = await db.users.find(
        {"verification_status": "pending"}, 
        {"_id": 0, "password_hash": 0}
    ).to_list(100)
    
    # Get verification documents for each user
    result = []
    for user in users:
        verification = await db.verifications.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0}
        )
        result.append({
            **user,
            "verification": verification
        })
    
    return result


@router.post("/verifications/decide")
async def decide_verification(
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process KYC verification decision"""
    verification_id = request.get("verification_id")
    approved = request.get("approved", False)
    rejection_reason = request.get("rejection_reason", "")
    
    # Find verification by verification_id or user_id
    verification = await db.verifications.find_one({"verification_id": verification_id})
    if not verification:
        # Try finding by user_id
        verification = await db.verifications.find_one({"user_id": verification_id})
    
    if not verification:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    
    user_id = verification.get("user_id")
    
    if approved:
        # Update verification status
        await db.verifications.update_one(
            {"verification_id": verification.get("verification_id")},
            {"$set": {"status": "approved", "processed_at": datetime.now(timezone.utc), "processed_by": admin.user_id}}
        )
        
        # Update user
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "verified", "verified_at": datetime.now(timezone.utc)}}
        )
        
        await create_notification(
            user_id=user_id,
            title="✅ Verificación Aprobada",
            message="Tu identidad ha sido verificada exitosamente. Ya puedes usar todas las funciones de RIS App.",
            notification_type="verification_approved"
        )
        
        logger.info(f"Verification approved for {user_id} by {admin.user_id}")
        return {"message": "Verificación aprobada"}
    else:
        # Update verification status
        await db.verifications.update_one(
            {"verification_id": verification.get("verification_id")},
            {"$set": {"status": "rejected", "rejection_reason": rejection_reason, "processed_at": datetime.now(timezone.utc), "processed_by": admin.user_id}}
        )
        
        # Update user
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "rejected", "rejection_reason": rejection_reason}}
        )
        
        await create_notification(
            user_id=user_id,
            title="❌ Verificación Rechazada",
            message=f"Tu verificación fue rechazada. Motivo: {rejection_reason}",
            notification_type="verification_rejected"
        )
        
        logger.info(f"Verification rejected for {user_id} by {admin.user_id}: {rejection_reason}")
        return {"message": "Verificación rechazada"}


# Keep old endpoint for backward compatibility
@router.post("/verifications/process")
async def process_verification(user_id: str, action: str, reason: str = None, admin: User = Depends(get_super_admin)):
    """Process KYC verification (legacy endpoint)"""
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



# ============== SUPPORT REQUESTS ==============

@router.get("/support-requests")
async def get_support_requests(admin: User = Depends(get_crm_user)):
    """Get all support requests"""
    requests = await db.support_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"requests": requests}

@router.post("/support-requests/{request_id}/resolve")
async def resolve_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Mark a support request as resolved"""
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc),
            "resolved_by": admin.user_id
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    logger.info(f"Support request {request_id} resolved by {admin.user_id}")
    return {"message": "Solicitud marcada como resuelta"}

class SupportReplyRequest(BaseModel):
    message: str

@router.post("/support-requests/{request_id}/reply")
async def reply_support_request(request_id: str, data: SupportReplyRequest, admin: User = Depends(get_crm_user)):
    """Responde una solicitud de soporte por correo (vía Resend) y guarda la respuesta."""
    text = (data.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    to_email = req.get("email")
    if not to_email:
        raise HTTPException(status_code=400, detail="La solicitud no tiene correo de contacto")
    subject_orig = req.get("subject") or "tu solicitud"
    original_msg = req.get("message") or ""
    safe_reply = text.replace("\n", "<br>")
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Respuesta de soporte - RIS App</h2>
        <p>Hola,</p>
        <p>Gracias por contactarnos. En respuesta a tu solicitud <strong>"{subject_orig}"</strong>:</p>
        <div style="background: #f3f4f6; border-left: 4px solid #6366f1; padding: 14px 16px; border-radius: 8px; margin: 16px 0; color: #1f2937;">
            {safe_reply}
        </div>
        <p style="color: #6b7280; font-size: 13px;">Tu mensaje original: "{original_msg}"</p>
        <div style="background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 12px 14px; margin: 18px 0 8px;">
            <p style="color: #92400e; font-size: 13px; margin: 0; line-height: 1.5;">
                <strong>No respondas este correo</strong>, no podemos leer las respuestas por esta via. El equipo de RisApp se pondra en contacto contigo directamente a traves de los numeros de contacto y el correo que nos dejaste.
            </p>
        </div>
    </div>
    """
    email_sent = await send_email(
        to_email=to_email,
        subject=f"Re: {subject_orig} - Soporte RIS App",
        html_content=html_content,
    )
    reply_doc = {
        "message": text,
        "admin_id": admin.user_id,
        "admin_name": getattr(admin, "name", None) or "Soporte",
        "sent_at": datetime.now(timezone.utc),
        "email_sent": bool(email_sent),
    }
    await db.support_requests.update_one(
        {"support_id": request_id},
        {
            "$push": {"replies": reply_doc},
            "$set": {
                "responded_at": datetime.now(timezone.utc),
                "responded_by": admin.user_id,
            },
        },
    )
    if not email_sent:
        return {"success": False, "email_sent": False, "message": "Respuesta guardada, pero el correo no se pudo enviar (revisa la configuracion de Resend)."}
    return {"success": True, "email_sent": True, "message": "Respuesta enviada por correo"}

@router.post("/support-requests/{request_id}/claim")
async def claim_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Toma (claim) una solicitud de soporte de forma ATÓMICA: solo uno puede tomarla."""
    result = await db.support_requests.update_one(
        {"support_id": request_id, "$or": [{"assigned_to": None}, {"assigned_to": {"$exists": False}}, {"assigned_to": ""}]},
        {"$set": {
            "assigned_to": admin.user_id,
            "assigned_to_name": admin.name or "Operador",
            "assigned_at": datetime.now(timezone.utc),
        }}
    )
    if result.modified_count == 1:
        return {"success": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    existing = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1, "assigned_to_name": 1})
    if existing and existing.get("assigned_to") == admin.user_id:
        return {"success": True, "already_mine": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    return {"success": False, "assigned_to": (existing or {}).get("assigned_to"), "assigned_to_name": (existing or {}).get("assigned_to_name")}

@router.post("/support-requests/{request_id}/release")
async def release_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Suelta una solicitud. Solo el dueño del caso o un super admin."""
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if req.get("assigned_to") and req.get("assigned_to") != admin.user_id and admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo quien atiende el caso o un super admin puede liberarlo")
    await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"assigned_to": None, "assigned_to_name": None, "assigned_at": None}}
    )
    return {"success": True}


class SetPriorityRequest(BaseModel):
    priority: str

@router.post("/support-requests/{request_id}/priority")
async def set_support_priority(request_id: str, data: SetPriorityRequest, admin: User = Depends(get_crm_user)):
    """Cambia la prioridad de una solicitud de soporte."""
    valid = ["baja", "normal", "alta", "urgente"]
    if data.priority not in valid:
        raise HTTPException(status_code=400, detail="Prioridad inválida")
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"priority": data.priority}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {"success": True, "priority": data.priority}

@router.get("/agent-ratings")
async def get_agent_ratings(admin: User = Depends(get_super_admin)):
    """Resumen interno de calificaciones por agente (solo super admin)."""
    ratings = await db.ratings.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    agents = {}
    for r in ratings:
        aid = r.get("agent_id") or "sin_asignar"
        aname = r.get("agent_name") or "Sin asignar"
        if aid not in agents:
            agents[aid] = {"agent_id": aid, "agent_name": aname, "count": 0, "sum_stars": 0, "ratings": []}
        a = agents[aid]
        a["count"] += 1
        a["sum_stars"] += (r.get("stars") or 0)
        a["ratings"].append({
            "stars": r.get("stars"),
            "comment": r.get("comment") or "",
            "channel": r.get("channel"),
            "case_code": r.get("case_code"),
            "created_at": r.get("created_at"),
        })
    result = []
    for a in agents.values():
        avg = round(a["sum_stars"] / a["count"], 2) if a["count"] else 0
        result.append({
            "agent_id": a["agent_id"],
            "agent_name": a["agent_name"],
            "count": a["count"],
            "average": avg,
            "ratings": a["ratings"],
        })
    result.sort(key=lambda x: (-x["average"], -x["count"]))
    return {"agents": result, "total": len(ratings)}



@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, data: dict, admin: User = Depends(get_super_admin)):
    """Suspend or reactivate a user"""
    suspend = data.get("suspend", True)
    
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("role") == "super_admin":
        raise HTTPException(status_code=403, detail="No se puede suspender a un super admin")
    
    new_status = "suspended" if suspend else "active"
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    action = "suspendido" if suspend else "reactivado"
    logger.info(f"User {user_id} {action} by admin {admin.user_id}")
    return {"message": f"Usuario {action} exitosamente"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(get_super_admin)):
    """Borrado lógico: conserva el historial para auditoría y libera el correo.

    No elimina transacciones, beneficiarios ni notificaciones (se conservan para auditoría).
    Marca la cuenta como borrada, cierra sus sesiones y libera el correo (lo mueve a
    original_email) para que pueda reutilizarse en un registro nuevo, salvo que el correo
    esté en la lista negra.
    """
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("role") == "super_admin":
        raise HTTPException(status_code=403, detail="No se puede eliminar a un super admin")

    now = datetime.now(timezone.utc)
    original_email = user.get("email", "")
    # "Lápida" única para liberar el correo original conservando la cuenta/historial
    tombstone_email = f"deleted+{now.strftime('%Y%m%d%H%M%S')}+{uuid.uuid4().hex[:6]}@deleted.local"

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": now,
            "deleted_by": admin.user_id,
            "original_email": original_email,
            "email": tombstone_email,
            "email_verified": False,
        }}
    )

    # Cerrar sus sesiones activas (el resto del historial se conserva)
    await db.user_sessions.delete_many({"user_id": user_id})

    logger.info(f"User {user_id} ({original_email}) soft-deleted by admin {admin.user_id}; email released")
    return {"message": "Usuario eliminado (historial conservado, correo liberado)"}

# ============================================================================
# BLACKLIST (correos / identidades baneadas)
# ============================================================================

ALLOWED_BLACKLIST_TYPES = {"email", "cpf", "document"}

def _normalize_blacklist_value(bl_type: str, value: str) -> str:
    """Normaliza el valor según el tipo para comparaciones consistentes."""
    value = (value or "").strip()
    if bl_type == "email":
        return value.lower()
    if bl_type == "cpf":
        return "".join(c for c in value if c.isdigit())
    if bl_type == "document":
        return "".join(c for c in value if c.isalnum()).upper()
    return value

class BlacklistAddRequest(BaseModel):
    type: str          # "email" | "cpf" | "document"
    value: str
    reason: str = ""

@router.post("/blacklist")
async def add_to_blacklist(data: BlacklistAddRequest, admin: User = Depends(get_crm_user)):
    """Agrega un correo/CPF/documento a la lista negra."""
    bl_type = (data.type or "").lower().strip()
    if bl_type not in ALLOWED_BLACKLIST_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de lista negra inválido")
    norm = _normalize_blacklist_value(bl_type, data.value)
    if not norm:
        raise HTTPException(status_code=400, detail="Valor vacío")
    existing = await db.blacklist.find_one({"type": bl_type, "value": norm})
    if existing:
        return {"success": True, "message": "Ya estaba en la lista negra", "blacklist_id": existing["blacklist_id"]}
    entry = {
        "blacklist_id": f"bl_{uuid.uuid4().hex[:12]}",
        "type": bl_type,
        "value": norm,
        "reason": (data.reason or "").strip(),
        "banned_by": admin.user_id,
        "banned_by_name": getattr(admin, "full_name", None) or admin.email,
        "banned_at": datetime.now(timezone.utc),
    }
    await db.blacklist.insert_one(entry)
    logger.info(f"Blacklist add: {bl_type}={norm} by {admin.user_id}")
    return {"success": True, "message": "Agregado a la lista negra", "blacklist_id": entry["blacklist_id"]}

@router.get("/blacklist")
async def list_blacklist(admin: User = Depends(get_crm_user)):
    """Lista todos los elementos de la lista negra."""
    items = await db.blacklist.find({}, {"_id": 0}).sort("banned_at", -1).to_list(1000)
    return {"items": items, "total": len(items)}

@router.delete("/blacklist/{blacklist_id}")
async def remove_from_blacklist(blacklist_id: str, admin: User = Depends(get_crm_user)):
    """Quita un elemento de la lista negra (des-banear)."""
    result = await db.blacklist.delete_one({"blacklist_id": blacklist_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")
    logger.info(f"Blacklist remove: {blacklist_id} by {admin.user_id}")
    return {"success": True, "message": "Quitado de la lista negra"}

async def _add_bl(bl_type: str, value: str, reason: str, admin: User):
    """Inserta un valor en la lista negra si no existe ya (idempotente)."""
    norm = _normalize_blacklist_value(bl_type, value)
    if not norm:
        return
    if await db.blacklist.find_one({"type": bl_type, "value": norm}):
        return
    await db.blacklist.insert_one({
        "blacklist_id": f"bl_{uuid.uuid4().hex[:12]}",
        "type": bl_type,
        "value": norm,
        "reason": reason,
        "banned_by": admin.user_id,
        "banned_by_name": getattr(admin, "full_name", None) or admin.email,
        "banned_at": datetime.now(timezone.utc),
    })

class BanUserRequest(BaseModel):
    verification_id: str
    scope: str = "full"   # "email" | "full"
    reason: str = ""

@router.post("/ban")
async def ban_from_verification(data: BanUserRequest, admin: User = Depends(get_crm_user)):
    """Banea a un usuario a partir de su verificación.

    scope="email": solo banea el correo (puede abrir cuenta con otro correo).
    scope="full":  banea correo + CPF + documento (su identidad queda en lista negra).
    En ambos casos se bloquea la cuenta actual y se cierran sus sesiones.
    """
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": data.verification_id}, {"user_id": data.verification_id}]}
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    user_id = v["user_id"]
    user = await db.users.find_one({"user_id": user_id})
    email = (user or {}).get("email", "")
    reason = (data.reason or "").strip()
    scope = (data.scope or "full").lower()

    # Siempre se banea el correo
    if email:
        await _add_bl("email", email, reason, admin)

    # El baneo completo también lista la identidad (CPF + documento)
    if scope == "full":
        if v.get("cpf_number"):
            await _add_bl("cpf", v["cpf_number"], reason, admin)
        if v.get("document_number"):
            await _add_bl("document", v["document_number"], reason, admin)

    # Bloquear la cuenta (impide iniciar sesión) y cerrar sus sesiones
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_banned": True,
            "banned_at": datetime.now(timezone.utc),
            "ban_reason": reason,
            "verification_status": "rejected",
        }}
    )
    await db.user_sessions.delete_many({"user_id": user_id})

    logger.info(f"User {user_id} banned (scope={scope}) by {admin.user_id}")
    return {"success": True, "message": "Usuario baneado", "scope": scope}
