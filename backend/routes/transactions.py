"""
Transaction routes - Withdrawals, Recharges, Beneficiaries
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.user import User
from models.requests import WithdrawalRequest, BeneficiaryCreate
from routes.dependencies import get_current_user, get_verified_user
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.notifications import create_notification
from utils.helpers import get_next_withdrawal_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transactions"])

# ============== BENEFICIARIES ==============

@router.post("/beneficiaries")
async def create_beneficiary(request: BeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Create a new beneficiary"""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"
    
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "id_document": request.id_document.strip(),
        "bank": request.bank.strip(),
        "bank_code": request.bank_code,
        "phone_number": request.phone_number,
        "account_number": request.account_number,
        "payment_type": request.payment_type,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.beneficiaries.insert_one(beneficiary)
    
    return {"message": "Beneficiario creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries")
async def get_beneficiaries(current_user: User = Depends(get_current_user)):
    """Get user's beneficiaries"""
    beneficiaries = await db.beneficiaries.find(
        {"user_id": current_user.user_id}
    ).to_list(100)
    
    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "id_document": b.get("id_document"),
            "bank": b.get("bank"),
            "bank_code": b.get("bank_code"),
            "phone_number": b.get("phone_number"),
            "account_number": b.get("account_number"),
            "payment_type": b.get("payment_type", "transferencia"),
            "created_at": b.get("created_at")
        }
        for b in beneficiaries
    ]

@router.delete("/beneficiaries/{beneficiary_id}")
async def delete_beneficiary(beneficiary_id: str, current_user: User = Depends(get_current_user)):
    """Delete a beneficiary"""
    result = await db.beneficiaries.delete_one({
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")
    
    return {"message": "Beneficiario eliminado"}

# ============== WITHDRAWALS ==============

@router.post("/withdraw")
@router.post("/withdrawal/create")
async def create_withdrawal(request: WithdrawalRequest, current_user: User = Depends(get_current_user)):
    """Create a withdrawal request"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    if user.get("balance_ris", 0) < request.amount:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")
    
    # Get beneficiary
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")
    
    # Get exchange rate
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    ris_to_ves = rate.get("ris_to_ves", 92.0) if rate else 92.0
    
    amount_ves = request.amount * ris_to_ves
    
    # Create transaction
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    
    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia")
    }
    
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "status": "pending",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "rate": ris_to_ves,
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "payment_type": beneficiary.get("payment_type", "transferencia"),
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(transaction)
    
    # Deduct balance
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$inc": {"balance_ris": -request.amount}}
    )
    
    # Send to WhatsApp queue
    await send_next_pending_withdrawal_whatsapp()
    
    # Notify user
    await create_notification(
        user_id=current_user.user_id,
        title="📤 Retiro Solicitado",
        message=f"Tu retiro de {amount_ves:.2f} VES está siendo procesado.",
        notification_type="withdrawal",
        data={"transaction_id": tx_id, "amount_ves": amount_ves}
    )
    
    logger.info(f"Withdrawal {tx_id} created for user {current_user.user_id}")
    
    return {
        "message": "Retiro solicitado exitosamente",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount,
        "amount_ves": amount_ves,
        "rate": ris_to_ves,
        "beneficiary": beneficiary.get("full_name")
    }

@router.get("/withdrawal/pending")
async def get_pending_withdrawal(current_user: User = Depends(get_current_user)):
    """Get user's pending withdrawal"""
    withdrawal = await db.transactions.find_one({
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "status": "pending"
    })
    
    if not withdrawal:
        return {"has_pending": False}
    
    return {
        "has_pending": True,
        "transaction_id": withdrawal.get("transaction_id"),
        "display_id": withdrawal.get("display_id"),
        "amount_input": withdrawal.get("amount_input"),
        "amount_output": withdrawal.get("amount_output"),
        "beneficiary_data": withdrawal.get("beneficiary_data"),
        "created_at": withdrawal.get("created_at")
    }

# ============== TRANSACTIONS HISTORY ==============

@router.get("/transactions")
async def get_transactions(
    page: int = 1,
    limit: int = 10,
    filter_type: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get user's transaction history with pagination"""
    query = {"user_id": current_user.user_id}
    if filter_type and filter_type != "all":
        if filter_type == "withdrawals":
            query["type"] = {"$in": ["withdrawal", "send"]}
        elif filter_type == "recharges":
            query["type"] = {"$in": ["recharge", "recharge_ves"]}
    
    skip = (page - 1) * limit
    total = await db.transactions.count_documents(query)
    
    transactions = await db.transactions.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "transactions": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "type": t.get("type"),
                "status": t.get("status"),
                "amount_input": t.get("amount_input"),
                "amount_output": t.get("amount_output"),
                "rate": t.get("rate"),
                "beneficiary_data": t.get("beneficiary_data"),
                "payment_type": t.get("payment_type"),
                "proof_image": t.get("proof_image"),
                "proof_images": t.get("proof_images", []),
                "created_at": t.get("created_at"),
                "completed_at": t.get("completed_at")
            }
            for t in transactions
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@router.get("/transaction/{transaction_id}/proof")
async def get_transaction_proof(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get proof images for a transaction"""
    transaction = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "user_id": current_user.user_id
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    return {
        "proof_image": transaction.get("proof_image"),
        "proof_images": transaction.get("proof_images", [])
    }


# ============== VES RECHARGE ==============

# Map of legacy bank codes to canonical bank names (used to find matching bank in accounting)
BANK_CODE_TO_NAME = {
    "banco_venezuela": "Banco de Venezuela",
    "banesco": "Banesco",
    "mercantil": "Mercantil",
    "provincial": "Provincial",
    "bnc": "BNC",
}


async def resolve_ves_bank(code: str):
    """Given a legacy bank code, find the matching VES bank in accounting.
    Returns (bank_id, bank_name) or (None, fallback_name)."""
    if not code:
        return None, None
    expected_name = BANK_CODE_TO_NAME.get(code, code)
    # Try exact match first, then case-insensitive prefix match
    bank = await db.bank_accounts.find_one({
        "currency": "VES",
        "name": {"$regex": f"^{expected_name}", "$options": "i"}
    })
    if bank:
        return bank["bank_id"], bank["name"]
    return None, expected_name


@router.post("/recharge/ves")
async def create_ves_recharge(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Create a VES (Bolívares) recharge request"""
    amount_ves = request.get("amount_ves")
    # Accept both proof_image and voucher_image for compatibility
    proof_image = request.get("proof_image") or request.get("voucher_image")
    destination_bank = request.get("bank")  # Bank code user deposited to (e.g. banco_venezuela)
    
    if not amount_ves or amount_ves <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")
    
    if not proof_image:
        raise HTTPException(status_code=400, detail="Debes adjuntar el comprobante de pago")
    
    if not destination_bank:
        raise HTTPException(status_code=400, detail="Debes seleccionar el banco al que pagaste")
    
    # Resolve to a real bank in accounting (so admin can credit it automatically)
    destination_bank_id, destination_bank_name = await resolve_ves_bank(destination_bank)
    
    # Get current rate (ris_to_ves = cuántos VES por 1 RIS)
    rates = await db.rates.find_one({}, {"_id": 0})
    ris_to_ves = rates.get("ris_to_ves", 140) if rates else 140
    
    # Calculate RIS amount: Si 140 VES = 1 RIS, entonces amount_ris = amount_ves / ris_to_ves
    amount_ris = amount_ves / ris_to_ves if ris_to_ves > 0 else 0
    
    # Generate transaction ID
    transaction_id = f"ves_{uuid.uuid4().hex[:12]}"
    
    # Create recharge request
    recharge = {
        "transaction_id": transaction_id,
        "user_id": current_user.user_id,
        "type": "recharge_ves",
        "amount_ves": amount_ves,
        "amount_ris": round(amount_ris, 2),
        "rate_used": ris_to_ves,
        "proof_image": proof_image,
        "destination_bank": destination_bank,
        "destination_bank_id": destination_bank_id,
        "destination_bank_name": destination_bank_name,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(recharge)
    
    # Notify admins
    await create_notification(
        user_id="admin",
        title="📥 Nueva solicitud de recarga VES",
        message=f"Usuario solicita recarga de {amount_ves:.2f} VES ({amount_ris:.2f} RIS)",
        notification_type="recharge_request",
        data={"transaction_id": transaction_id}
    )
    
    logger.info(f"VES recharge request created: {transaction_id} by {current_user.user_id}")
    
    return {
        "message": "Solicitud de recarga enviada",
        "transaction_id": transaction_id,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris,
        "status": "pending"
    }


@router.get("/recharge/ves/status")
async def get_ves_recharge_status(current_user: User = Depends(get_current_user)):
    """Get all VES recharge requests for the current user"""
    recharges = await db.transactions.find(
        {"user_id": current_user.user_id, "type": "recharge_ves"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    
    return recharges


@router.get("/recharge/ves/{transaction_id}")
async def get_ves_recharge_detail(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get details of a specific VES recharge"""
    recharge = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id, "type": "recharge_ves"},
        {"_id": 0}
    )
    
    if not recharge:
        raise HTTPException(status_code=404, detail="Recarga no encontrada")
    
    return recharge

