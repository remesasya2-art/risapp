# Admin Panel Routes for RIS App
# This module contains all admin-related endpoints for the RIS application

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
from openpyxl import Workbook
from io import BytesIO
from motor.motor_asyncio import AsyncIOMotorClient
import logging
import uuid
import os
from services import saldos
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logger = logging.getLogger(__name__)

# Create admin router
admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Available permissions for sub-admins
ADMIN_PERMISSIONS = {
    "withdrawals.view": "Ver retiros",
    "withdrawals.process": "Procesar retiros",
    "recharges.view": "Ver recargas",
    "recharges.approve": "Aprobar recargas",
    "support.view": "Ver chats de soporte",
    "support.respond": "Responder chats",
    "support.close": "Cerrar chats",
    "users.view": "Ver usuarios",
    "users.edit": "Editar usuarios",
    "kyc.view": "Ver KYC",
    "kyc.approve": "Aprobar/Rechazar KYC",
    "transactions.view": "Ver transacciones",
    "transactions.export": "Exportar transacciones",
    "settings.view": "Ver configuración",
    "settings.edit": "Editar configuración",
    "admins.view": "Ver administradores",
    "admins.create": "Crear sub-administradores",
    "admins.edit": "Editar sub-administradores",
    "dashboard.view": "Ver dashboard",
}

# =======================
# AUTH DEPENDENCIES
# =======================

async def get_current_user_from_request(request: Request, authorization: Optional[str] = Header(None)):
    """Get current user from session token"""
    session_token = None
    
    session_token = request.cookies.get('session_token')
    
    if not session_token and authorization:
        if authorization.startswith('Bearer '):
            session_token = authorization[7:]
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    user_doc = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user_doc

async def get_admin_user(request: Request, authorization: Optional[str] = Header(None)):
    """Check if user is admin or super_admin"""
    user_doc = await get_current_user_from_request(request, authorization)
    role = user_doc.get('role', 'user')
    
    if role not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user_doc

async def get_super_admin(request: Request, authorization: Optional[str] = Header(None)):
    """Check if user is super_admin"""
    user_doc = await get_current_user_from_request(request, authorization)
    role = user_doc.get('role', 'user')
    
    if role != 'super_admin':
        raise HTTPException(status_code=403, detail="Super admin access required")
    
    return user_doc

def has_permission(user: dict, permission: str) -> bool:
    """Check if user has specific permission"""
    role = user.get('role', 'user')
    if role == 'super_admin':
        return True
    if role == 'admin':
        admin_only = ['admins.create', 'admins.edit']
        return permission not in admin_only
    return permission in user.get('permissions', [])

async def create_notification(user_id: str, title: str, message: str, notification_type: str, data: dict = None):
    """Helper function to create a notification"""
    notification = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    await db.notifications.insert_one(notification)
    logger.info(f"Notification created for user {user_id}: {title}")

# =======================
# REQUEST/RESPONSE MODELS
# =======================

class CreateSubAdminRequest(BaseModel):
    email: str
    name: str
    permissions: List[str]

class UpdateSubAdminRequest(BaseModel):
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None

class ProcessWithdrawalAdminRequest(BaseModel):
    transaction_id: str
    action: str  # "approve" or "reject"
    proof_image: Optional[str] = None
    rejection_reason: Optional[str] = None

class ApproveRechargeRequest(BaseModel):
    transaction_id: str
    approved: bool
    rejection_reason: Optional[str] = None

class AdminSupportResponse(BaseModel):
    user_id: str
    message: str

class CloseSupportRequest(BaseModel):
    user_id: str
    closing_message: Optional[str] = None

class VerificationDecision(BaseModel):
    user_id: str
    approved: bool
    rejection_reason: Optional[str] = None

class UpdateRateRequest(BaseModel):
    ris_to_ves: float
    usd_to_ves: Optional[float] = None

class AdjustBalanceRequest(BaseModel):
    amount: float

# =======================
# DASHBOARD
# =======================

@admin_router.get("/dashboard")
async def get_admin_dashboard(admin_user: dict = Depends(get_admin_user)):
    """Get dashboard statistics"""
    if not has_permission(admin_user, "dashboard.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get statistics
    total_users = await db.users.count_documents({"role": {"$nin": ["admin", "super_admin"]}})
    verified_users = await db.users.count_documents({"verification_status": "verified"})
    pending_kyc = await db.users.count_documents({
        "verification_status": "pending", 
        "id_document_image": {"$ne": None}
    })
    
    total_transactions = await db.transactions.count_documents({})
    pending_withdrawals = await db.transactions.count_documents({"type": "withdrawal", "status": "pending"})
    pending_recharges = await db.transactions.count_documents({"type": "recharge", "status": "pending_review"})
    completed_transactions = await db.transactions.count_documents({"status": "completed"})
    
    open_support = await db.support_messages.count_documents({"status": {"$ne": "closed"}})
    
    # Volume calculations
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$type", "total": {"$sum": "$amount_input"}}}
    ]
    volumes = await db.transactions.aggregate(pipeline).to_list(10)
    volume_by_type = {v["_id"]: v["total"] for v in volumes}
    
    # Get exchange rate
    rate_doc = await db.exchange_rates.find_one({})
    current_rate = rate_doc.get("ris_to_ves", 78) if rate_doc else 78
    
    return {
        "users": {
            "total": total_users,
            "verified": verified_users,
            "pending_kyc": pending_kyc
        },
        "transactions": {
            "total": total_transactions,
            "completed": completed_transactions,
            "pending_withdrawals": pending_withdrawals,
            "pending_recharges": pending_recharges
        },
        "support": {
            "open_chats": open_support
        },
        "volume": {
            "withdrawals": volume_by_type.get("withdrawal", 0),
            "recharges": volume_by_type.get("recharge", 0)
        },
        "current_rate": current_rate
    }

# =======================
# PERMISSIONS
# =======================

@admin_router.get("/permissions-list")
async def get_permissions_list(admin_user: dict = Depends(get_admin_user)):
    """Get list of all available permissions"""
    return ADMIN_PERMISSIONS

# =======================
# SUB-ADMIN MANAGEMENT
# =======================

@admin_router.get("/sub-admins")
async def get_sub_admins(admin_user: dict = Depends(get_super_admin)):
    """Get all sub-administrators (super_admin only)"""
    admins = await db.users.find(
        {"role": {"$in": ["admin", "super_admin"]}},
        {"id_document_image": 0, "cpf_image": 0, "selfie_image": 0}
    ).to_list(100)
    
    for a in admins:
        a['_id'] = str(a['_id'])
    
    return admins

@admin_router.post("/sub-admins")
async def create_sub_admin(request: CreateSubAdminRequest, admin_user: dict = Depends(get_super_admin)):
    """Create a new sub-administrator (super_admin only)"""
    
    # Check if user already exists
    existing = await db.users.find_one({"email": request.email})
    
    if existing:
        # Update existing user to admin
        await db.users.update_one(
            {"email": request.email},
            {"$set": {
                "role": "admin",
                "permissions": request.permissions,
                "created_by_admin": admin_user.get('user_id'),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        return {"message": f"Usuario {request.email} promovido a admin", "user_id": existing.get('user_id')}
    else:
        # Create new admin user
        new_admin = {
            "user_id": f"admin_{uuid.uuid4().hex[:12]}",
            "email": request.email,
            "name": request.name,
            "role": "admin",
            "permissions": request.permissions,
            "is_active": True,
            "balance_ris": 0,
            "verification_status": "verified",
            "created_by_admin": admin_user.get('user_id'),
            "created_at": datetime.now(timezone.utc)
        }
        await db.users.insert_one(new_admin)
        return {"message": f"Admin {request.email} creado", "user_id": new_admin['user_id']}

@admin_router.put("/sub-admins/{user_id}")
async def update_sub_admin(user_id: str, request: UpdateSubAdminRequest, admin_user: dict = Depends(get_super_admin)):
    """Update a sub-administrator (super_admin only)"""
    
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    
    if target.get('role') == 'super_admin' and admin_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="No puedes modificar a otro super_admin")
    
    update_data = {"updated_at": datetime.now(timezone.utc)}
    if request.permissions is not None:
        update_data["permissions"] = request.permissions
    if request.is_active is not None:
        update_data["is_active"] = request.is_active
    if request.name is not None:
        update_data["name"] = request.name
    
    await db.users.update_one({"user_id": user_id}, {"$set": update_data})
    return {"message": "Admin actualizado"}

@admin_router.delete("/sub-admins/{user_id}")
async def delete_sub_admin(user_id: str, admin_user: dict = Depends(get_super_admin)):
    """Remove admin role from user (super_admin only)"""
    
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    
    if target.get('role') == 'super_admin':
        raise HTTPException(status_code=403, detail="No puedes eliminar a un super_admin")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": "user", "permissions": []}}
    )
    return {"message": "Rol de admin removido"}

# =======================
# USER MANAGEMENT
# =======================

@admin_router.get("/users")
async def get_all_users(
    admin_user: dict = Depends(get_admin_user),
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all users with pagination"""
    if not has_permission(admin_user, "users.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {"role": {"$nin": ["admin", "super_admin"]}}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    if status:
        query["verification_status"] = status
    
    users = await db.users.find(
        query,
        {"id_document_image": 0, "cpf_image": 0, "selfie_image": 0}
    ).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    total = await db.users.count_documents(query)
    
    for u in users:
        u['_id'] = str(u['_id'])
    
    return {"users": users, "total": total}

@admin_router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin_user: dict = Depends(get_admin_user)):
    """Get detailed user info including KYC documents"""
    if not has_permission(admin_user, "users.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user['_id'] = str(user['_id'])
    
    # Get user's transaction history summary
    tx_count = await db.transactions.count_documents({"user_id": user_id})
    tx_volume = await db.transactions.aggregate([
        {"$match": {"user_id": user_id, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_input"}}}
    ]).to_list(1)
    
    user['transaction_count'] = tx_count
    user['transaction_volume'] = tx_volume[0]['total'] if tx_volume else 0
    
    return user

@admin_router.put("/users/{user_id}/balance")
async def update_user_balance(user_id: str, request: AdjustBalanceRequest, admin_user: dict = Depends(get_admin_user)):
    """Manually adjust user balance"""
    if not has_permission(admin_user, "users.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Un ajuste a mano es el movimiento que MAS necesita quedar asentado: no
    # tiene una operación detrás que lo explique, sólo la decisión de un
    # administrador. Antes movía el saldo con un `$inc` de un float crudo y no
    # dejaba línea en el mayor; el registro en `admin_logs` de acá abajo no es
    # el libro y la conciliación no lo mira.
    try:
        movido = await saldos.mover(
            db, user_id, request.amount,
            movimiento="ajuste_admin",
            reference_kind="manual",
            reference_id=f"ajuste_{user_id}",
            actor_type="admin",
            actor_id=admin_user.get("user_id"),
            actor_email=admin_user.get("email"),
            notes="Ajuste manual de saldo desde el panel",
        )
    except saldos.UsuarioInexistente:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Log the adjustment
    adjustment = {
        "type": "admin_adjustment",
        "user_id": user_id,
        "amount": request.amount,
        "admin_id": admin_user.get('user_id'),
        "balance_before": float(movido["saldo_anterior"]),
        "balance_after": float(movido["saldo_nuevo"]),
        "ledger_entry_id": movido["entry_id"],
        "created_at": datetime.now(timezone.utc)
    }
    await db.admin_logs.insert_one(adjustment)
    
    return {"message": f"Balance ajustado en {request.amount} RIS",
            "balance_after": float(movido["saldo_nuevo"])}

# =======================
# KYC/VERIFICATION MANAGEMENT
# =======================

@admin_router.get("/verifications/pending")
async def get_pending_verifications(admin_user: dict = Depends(get_admin_user)):
    """Get all pending verifications"""
    if not has_permission(admin_user, "kyc.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    users = await db.users.find(
        {"verification_status": "pending", "id_document_image": {"$ne": None}},
        {
            "_id": 0,
            "user_id": 1,
            "name": 1,
            "email": 1,
            "full_name": 1,
            "document_number": 1,
            "cpf_number": 1,
            "id_document_image": 1,
            "cpf_image": 1,
            "selfie_image": 1,
            "created_at": 1
        }
    ).to_list(1000)
    return users

@admin_router.post("/verifications/decide")
async def decide_verification(decision: VerificationDecision, admin_user: dict = Depends(get_admin_user)):
    """Approve or reject verification"""
    if not has_permission(admin_user, "kyc.approve"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    update_data = {
        "verification_status": "verified" if decision.approved else "rejected",
        "verified_at": datetime.now(timezone.utc) if decision.approved else None,
        "verified_by": admin_user.get('user_id') if decision.approved else None,
        "rejection_reason": decision.rejection_reason if not decision.approved else None
    }
    
    result = await db.users.update_one(
        {"user_id": decision.user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Notify user
    if decision.approved:
        await create_notification(
            user_id=decision.user_id,
            title="✅ Cuenta Verificada",
            message="Tu verificación KYC ha sido aprobada. Ya puedes realizar transacciones.",
            notification_type="kyc_approved",
            data={}
        )
    else:
        await create_notification(
            user_id=decision.user_id,
            title="❌ Verificación Rechazada",
            message=f"Tu verificación fue rechazada. Razón: {decision.rejection_reason or 'Documentos inválidos'}",
            notification_type="kyc_rejected",
            data={"reason": decision.rejection_reason}
        )
    
    return {"message": f"Usuario {'aprobado' if decision.approved else 'rechazado'} exitosamente"}

# =======================
# WITHDRAWALS MANAGEMENT
# =======================

# ─── Retiros: las rutas vivían acá y estaban MUERTAS ──────────────────────
#
# `admin_routes.py` registraba `GET /api/admin/withdrawals/pending` y
# `POST /api/admin/withdrawals/process`, que `routes/admin.py` ya registra con
# los mismos caminos. `server.py` monta primero el router modular, así que
# FastAPI resolvía siempre contra `routes/admin.py` y estas dos nunca corrían.
#
# No era código inofensivo. La versión muerta de `process`:
#
#   - acreditaba la devolución con `{"$inc": {"balance_ris": tx['amount_input']}}`
#     —un float crudo, sin `to_decimal128`— cuando el resto de la app usa
#     Decimal;
#   - no dejaba línea en el diario RIS;
#   - devolvía SIEMPRE a `balance_ris`, sin mirar `currency_input`, así que un
#     envío pagado en USDT o USDC volvía en RIS;
#   - no respetaba el candado por operador ni el cupo sin KYC.
#
# Bastaba con que alguien cambiara el orden de los `include_router` en
# `server.py` para que esa versión pasara a atender los retiros, en silencio.
# Se eliminaron: la buena vive en `routes/admin.py`.

# =======================
# RECHARGES MANAGEMENT
# =======================

@admin_router.get("/recharges/pending")
async def get_pending_recharges(admin_user: dict = Depends(get_admin_user)):
    """Get all recharges pending review"""
    if not has_permission(admin_user, "recharges.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    recharges = await db.transactions.find(
        {
            "type": {"$in": ["recharge", "recharge_ves"]},
            "status": {"$in": ["pending", "pending_review"]}
        },
        {"proof_image": 0}
    ).sort("created_at", -1).to_list(1000)
    
    result = []
    for r in recharges:
        user = await db.users.find_one({"user_id": r.get("user_id")})
        r['_id'] = str(r['_id'])
        r['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        r['user_email'] = user.get('email', 'N/A') if user else 'N/A'
        result.append(r)
    
    return {"recharges": result}

@admin_router.get("/recharges/{transaction_id}/proof")
async def get_recharge_proof(transaction_id: str, admin_user: dict = Depends(get_admin_user)):
    """Get proof image for a specific recharge"""
    if not has_permission(admin_user, "recharges.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    return {
        "transaction_id": transaction_id,
        "proof_image": transaction.get("proof_image"),
        "amount_input": transaction.get("amount_input"),
        "status": transaction.get("status")
    }

@admin_router.post("/recharges/approve")
async def approve_recharge(request: ApproveRechargeRequest, admin_user: dict = Depends(get_admin_user)):
    """Approve or reject a recharge with uploaded proof"""
    if not has_permission(admin_user, "recharges.approve"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    transaction = await db.transactions.find_one({
        "transaction_id": request.transaction_id,
        "status": {"$in": ["pending", "pending_review"]}
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    user_id = transaction.get("user_id")
    amount_ris = transaction.get("amount_output", 0)
    
    if request.approved:
        # Acreditar y asentar en la misma operación. Antes era un `$inc` con un
        # float crudo, sin línea de libro y sin consumir el cupo sin KYC: una
        # recarga aprobada por acá no aparecía en el mayor y tampoco contaba
        # para el límite de quien no verificó su cuenta.
        try:
            await saldos.mover(
                db, user_id, amount_ris,
                movimiento="recarga_brl",
                consumir_cupo=True,
                reference_kind="transaction",
                reference_id=request.transaction_id,
                transaction_id=request.transaction_id,
                display_id=transaction.get("display_id"),
                actor_type="admin",
                actor_id=admin_user.get("user_id"),
                actor_email=admin_user.get("email"),
                amount_output=transaction.get("amount_input", 0),
                currency_output="BRL",
                metadata={"verification_method": "admin_manual_approval"},
                notes="Recarga en reales aprobada a mano",
            )
        except saldos.UsuarioInexistente:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Update transaction status
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "approved_by": admin_user.get('user_id'),
                "verification_method": "admin_manual_approval"
            }}
        )
        
        # Save admin record
        user = await db.users.find_one({"user_id": user_id})
        admin_record = {
            "record_type": "recharge_approved",
            "transaction_id": request.transaction_id,
            "user_id": user_id,
            "user_name": user.get('name', 'N/A') if user else 'N/A',
            "user_email": user.get('email', 'N/A') if user else 'N/A',
            "amount_brl": transaction.get("amount_input", 0),
            "amount_ris": amount_ris,
            "proof_image": transaction.get("proof_image"),
            "approved_by": admin_user.get('user_id'),
            "approved_by_email": admin_user.get('email'),
            "processed_via": "admin_panel",
            "created_at": transaction.get("created_at"),
            "completed_at": datetime.now(timezone.utc),
            "recorded_at": datetime.now(timezone.utc)
        }
        
        await db.admin_payment_records.insert_one(admin_record)
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga Confirmada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue confirmada. +{amount_ris:.2f} RIS agregados a tu cuenta.",
            notification_type="recharge_completed",
            data={"transaction_id": request.transaction_id, "amount_ris": amount_ris}
        )
        
        logger.info(f"Recharge {request.transaction_id} approved by admin {admin_user.get('email')}")
        return {"message": "Recarga aprobada y saldo acreditado", "status": "completed"}
    else:
        # Reject recharge
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "rejected",
                "updated_at": datetime.now(timezone.utc),
                "rejected_by": admin_user.get('user_id'),
                "rejection_reason": request.rejection_reason or "Comprobante inválido"
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga Rechazada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue rechazada. Razón: {request.rejection_reason or 'Comprobante inválido'}",
            notification_type="recharge_rejected",
            data={"transaction_id": request.transaction_id}
        )
        
        logger.info(f"Recharge {request.transaction_id} rejected by admin {admin_user.get('email')}")
        return {"message": "Recarga rechazada", "status": "rejected"}

# =======================
# TRANSACTIONS
# =======================

@admin_router.get("/transactions")
async def get_all_transactions(
    admin_user: dict = Depends(get_admin_user),
    skip: int = 0,
    limit: int = 50,
    type: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all transactions with filters"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {}
    if type:
        query["type"] = type
    if status:
        query["status"] = status
    
    transactions = await db.transactions.find(
        query,
        {"proof_image": 0}
    ).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    total = await db.transactions.count_documents(query)
    
    # Get user info for each transaction
    for tx in transactions:
        tx['_id'] = str(tx['_id'])
        user = await db.users.find_one({"user_id": tx.get('user_id')}, {"name": 1, "email": 1})
        tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return {"transactions": transactions, "total": total}

@admin_router.get("/transactions/{transaction_id}")
async def get_transaction_detail(transaction_id: str, admin_user: dict = Depends(get_admin_user)):
    """Get transaction detail including proof image"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    tx = await db.transactions.find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    tx['_id'] = str(tx['_id'])
    
    user = await db.users.find_one({"user_id": tx.get('user_id')}, {"name": 1, "email": 1})
    tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
    tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return tx

@admin_router.get("/transactions/export")
async def export_transactions(admin_user: dict = Depends(get_admin_user)):
    """Export all transactions to Excel"""
    if not has_permission(admin_user, "transactions.export"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    transactions = await db.transactions.find({}, {"_id": 0, "proof_image": 0}).to_list(10000)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ["Transaction ID", "User ID", "Type", "Status", "Amount Input", "Amount Output", 
               "Created At", "Completed At", "Beneficiary"]
    ws.append(headers)
    
    # Data
    for t in transactions:
        beneficiary_name = ""
        if t.get("beneficiary_data"):
            beneficiary_name = t["beneficiary_data"].get("full_name", "")
        
        ws.append([
            t.get("transaction_id", ""),
            t.get("user_id", ""),
            t.get("type", ""),
            t.get("status", ""),
            t.get("amount_input", 0),
            t.get("amount_output", 0),
            str(t.get("created_at", "")),
            str(t.get("completed_at", "")),
            beneficiary_name
        ])
    
    # Save to bytes
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"}
    )

# =======================
# PAYMENT RECORDS
# =======================

@admin_router.get("/payment-records")
async def get_admin_payment_records(admin_user: dict = Depends(get_admin_user)):
    """Get all payment records with proof images"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    records = await db.admin_payment_records.find(
        {},
        {"proof_image": 0}
    ).sort("recorded_at", -1).to_list(1000)
    
    for r in records:
        r['_id'] = str(r['_id'])
    
    return {"records": records}

@admin_router.get("/payment-records/{record_id}")
async def get_admin_payment_record_detail(record_id: str, admin_user: dict = Depends(get_admin_user)):
    """Get a specific payment record with full details including proof image"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    record = await db.admin_payment_records.find_one({"_id": ObjectId(record_id)})
    
    if not record:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    
    record['_id'] = str(record['_id'])
    return record

# =======================
# SUPPORT CHAT MANAGEMENT
# =======================

@admin_router.get("/support/chats")
async def get_support_chats(admin_user: dict = Depends(get_admin_user), status: Optional[str] = None):
    """Get all support chats"""
    if not has_permission(admin_user, "support.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get unique users with support messages
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "last_message": {"$last": "$message"},
            "last_date": {"$max": "$created_at"},
            "message_count": {"$sum": 1},
            "status": {"$last": "$status"}
        }},
        {"$sort": {"last_date": -1}}
    ]
    
    if status:
        pipeline.insert(0, {"$match": {"status": status}})
    
    chats = await db.support_messages.aggregate(pipeline).to_list(100)
    
    # Get user info for each chat
    result = []
    for chat in chats:
        user = await db.users.find_one({"user_id": chat['_id']}, {"name": 1, "email": 1})
        result.append({
            "user_id": chat['_id'],
            "user_name": user.get('name', 'N/A') if user else 'N/A',
            "user_email": user.get('email', 'N/A') if user else 'N/A',
            "last_message": chat['last_message'][:100] + "..." if len(chat.get('last_message', '')) > 100 else chat.get('last_message', ''),
            "last_date": chat['last_date'],
            "message_count": chat['message_count'],
            "status": chat.get('status', 'open')
        })
    
    return result

@admin_router.get("/support/chat/{user_id}")
async def get_support_chat_detail(user_id: str, admin_user: dict = Depends(get_admin_user)):
    """Get full chat history with a user"""
    if not has_permission(admin_user, "support.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Get user messages
    user_messages = await db.support_messages.find({"user_id": user_id}).to_list(100)
    
    # Get admin responses
    admin_responses = await db.support_responses.find({"user_id": user_id}).to_list(100)
    
    # Combine and sort
    conversation = []
    for msg in user_messages:
        conversation.append({
            "id": str(msg['_id']),
            "text": msg.get('message', ''),
            "image": msg.get('image'),
            "sender": "user",
            "timestamp": msg.get('created_at').isoformat() if msg.get('created_at') else None
        })
    
    for resp in admin_responses:
        conversation.append({
            "id": str(resp['_id']),
            "text": resp.get('message', ''),
            "sender": "admin",
            "timestamp": resp.get('created_at').isoformat() if resp.get('created_at') else None
        })
    
    conversation.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '')
    
    # Get user info
    user = await db.users.find_one({"user_id": user_id}, {"name": 1, "email": 1})
    
    return {
        "user_id": user_id,
        "user_name": user.get('name', 'N/A') if user else 'N/A',
        "user_email": user.get('email', 'N/A') if user else 'N/A',
        "messages": conversation
    }

@admin_router.post("/support/respond")
async def admin_respond_support(request: AdminSupportResponse, admin_user: dict = Depends(get_admin_user)):
    """Send a response to user from admin panel"""
    if not has_permission(admin_user, "support.respond"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Save response
    admin_response = {
        "user_id": request.user_id,
        "message": request.message,
        "sender": "admin",
        "admin_id": admin_user.get('user_id'),
        "admin_name": admin_user.get('name'),
        "created_at": datetime.now(timezone.utc)
    }
    await db.support_responses.insert_one(admin_response)
    
    # Create notification
    await create_notification(
        user_id=request.user_id,
        title="💬 Respuesta de Soporte",
        message=request.message[:200] + ("..." if len(request.message) > 200 else ""),
        notification_type="support_response",
        data={"full_message": request.message}
    )
    
    return {"message": "Respuesta enviada"}

@admin_router.post("/support/close")
async def admin_close_support(request: CloseSupportRequest, admin_user: dict = Depends(get_admin_user)):
    """Close a support chat from admin panel"""
    if not has_permission(admin_user, "support.close"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    closing_msg = request.closing_message or "Tu caso de soporte ha sido resuelto. ¡Gracias por contactarnos!"
    
    # Mark as closed
    await db.support_messages.update_many(
        {"user_id": request.user_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc), "closed_by": admin_user.get('user_id')}}
    )
    
    # Save closing message
    admin_response = {
        "user_id": request.user_id,
        "message": f"🔒 Chat cerrado: {closing_msg}",
        "sender": "admin",
        "type": "close",
        "admin_id": admin_user.get('user_id'),
        "created_at": datetime.now(timezone.utc)
    }
    await db.support_responses.insert_one(admin_response)
    
    # Notify user
    await create_notification(
        user_id=request.user_id,
        title="✅ Caso de Soporte Resuelto",
        message=closing_msg,
        notification_type="support_closed",
        data={"closing_message": closing_msg}
    )
    
    return {"message": "Chat cerrado"}

# =======================
# SETTINGS
# =======================

@admin_router.get("/settings/rate")
async def get_exchange_rate(admin_user: dict = Depends(get_admin_user)):
    """Get current exchange rate"""
    if not has_permission(admin_user, "settings.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    rate_doc = await db.exchange_rates.find_one({})
    if not rate_doc:
        return {"ris_to_ves": 78, "updated_at": None, "updated_by": None}
    
    return {
        "ris_to_ves": rate_doc.get("ris_to_ves", 78),
        "updated_at": rate_doc.get("updated_at"),
        "updated_by": rate_doc.get("updated_by")
    }

@admin_router.post("/settings/rate")
async def update_exchange_rate(request: UpdateRateRequest, admin_user: dict = Depends(get_admin_user)):
    """Update exchange rate"""
    if not has_permission(admin_user, "settings.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Build the rate update
    new_rate = {
        "ris_to_ves": request.ris_to_ves,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": admin_user.get("username", "admin")
    }
    if request.usd_to_ves is not None:
        new_rate["usd_to_ves"] = request.usd_to_ves

    await db.exchange_rates.update_one(
        {},
        {"$set": new_rate},
        upsert=True
    )

    return {"message": "Tasa actualizada correctamente", "rate": new_rate}
