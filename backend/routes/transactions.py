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
async def get_transactions(current_user: User = Depends(get_current_user)):
    """Get user's transaction history"""
    transactions = await db.transactions.find(
        {"user_id": current_user.user_id}
    ).sort("created_at", -1).to_list(100)
    
    return [
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
    ]

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
