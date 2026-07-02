"""
Gestor (Agent) routes - Third-party transaction management
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from services.money import from_db, to_float, to_decimal, to_decimal128
from models.user import User
from models.requests import GestorBeneficiaryRequest, GestorTransactionRequest, GestorRechargeTercerosRequest
from routes.dependencies import get_current_user
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.notifications import create_notification
from utils.helpers import get_next_withdrawal_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gestor", tags=["gestor"])

async def require_gestor(current_user: User = Depends(get_current_user)) -> User:
    """Require socio_gestor role"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user or user.get("role") != "socio_gestor":
        raise HTTPException(status_code=403, detail="Acceso solo para socios gestores")
    return current_user

@router.get("/dashboard")
async def get_gestor_dashboard(current_user: User = Depends(require_gestor)):
    """Get gestor dashboard with stats and data"""
    gestor_id = current_user.user_id
    user = await db.users.find_one({"user_id": gestor_id})
    
    # Get commission setting
    settings = await db.app_settings.find_one({"setting_id": "gestor_commission"})
    commission = settings.get("value", 5.0) if settings else 5.0
    
    # Stats
    all_tx = await db.gestor_transactions.find({"gestor_id": gestor_id}).to_list(1000)
    total_volume = sum(t.get("amount_ris", 0) for t in all_tx)
    
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_tx = []
    for t in all_tx:
        created = t.get("created_at")
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= month_start:
                month_tx.append(t)
    month_volume = sum(t.get("amount_ris", 0) for t in month_tx)
    
    # Get beneficiaries
    beneficiaries = await db.gestor_beneficiaries.find({"gestor_id": gestor_id}).to_list(100)
    beneficiaries_list = []
    for b in beneficiaries:
        beneficiaries_list.append({
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "id_document": b.get("id_document") or b.get("cedula"),
            "bank": b.get("bank") or b.get("bank_name"),
            "bank_code": b.get("bank_code"),
            "phone_number": b.get("phone_number") or b.get("phone"),
            "account_number": b.get("account_number"),
            "payment_type": b.get("payment_type", "transferencia")
        })
    
    # Get recent transactions
    transactions = await db.gestor_transactions.find({"gestor_id": gestor_id}).sort("created_at", -1).limit(20).to_list(20)
    transactions_list = []
    for t in transactions:
        transactions_list.append({
            "transaction_id": t.get("transaction_id"),
            "display_id": t.get("display_id"),
            "client_name": t.get("client_name"),
            "beneficiary_name": t.get("beneficiary_name"),
            "payment_type": t.get("payment_type"),
            "amount_ris": t.get("amount_ris"),
            "amount_ves": t.get("amount_ves"),
            "status": t.get("status"),
            "created_at": t.get("created_at")
        })
    
    return {
        "gestor_code": user.get("gestor_code", ""),
        "balance_ris": to_float(from_db(user.get("balance_ris", 0))),
        "balance_ris_terceros": to_float(from_db(user.get("balance_ris_terceros", 0))),
        "commission_rate": commission,
        "stats": {
            "total_transactions": len(all_tx),
            "total_volume": round(total_volume, 2),
            "month_transactions": len(month_tx),
            "month_volume": round(month_volume, 2)
        },
        "beneficiaries": beneficiaries_list,
        "recent_transactions": transactions_list
    }

@router.post("/beneficiaries")
async def add_gestor_beneficiary(request: GestorBeneficiaryRequest, current_user: User = Depends(require_gestor)):
    """Add a new beneficiary"""
    beneficiary_id = f"gben_{uuid.uuid4().hex[:12]}"
    
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "gestor_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "id_document": request.id_document.strip(),
        "bank": request.bank.strip(),
        "bank_code": request.bank_code,
        "phone_number": request.phone_number,
        "account_number": request.account_number,
        "payment_type": request.payment_type,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.gestor_beneficiaries.insert_one(beneficiary)
    
    logger.info(f"Gestor {current_user.user_id} added beneficiary {beneficiary_id}")
    return {"message": "Beneficiario agregado exitosamente", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries")
async def get_gestor_beneficiaries(current_user: User = Depends(require_gestor)):
    """Get all beneficiaries"""
    beneficiaries = await db.gestor_beneficiaries.find({"gestor_id": current_user.user_id}).to_list(100)
    
    result = []
    for b in beneficiaries:
        result.append({
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "id_document": b.get("id_document") or b.get("cedula"),
            "bank": b.get("bank") or b.get("bank_name"),
            "bank_code": b.get("bank_code"),
            "phone_number": b.get("phone_number") or b.get("phone"),
            "account_number": b.get("account_number"),
            "payment_type": b.get("payment_type", "transferencia"),
            "created_at": b.get("created_at")
        })
    
    return result

@router.post("/process-transaction")
async def process_gestor_transaction(request: GestorTransactionRequest, current_user: User = Depends(require_gestor)):
    """Process a third-party transaction using balance_ris_terceros"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    # Check balance
    balance_terceros = to_float(from_db(user.get("balance_ris_terceros", 0)))
    if balance_terceros < request.amount_ris:
        raise HTTPException(status_code=400, detail=f"Saldo de terceros insuficiente. Disponible: {balance_terceros:.2f} RIS")
    
    # Verify beneficiary
    beneficiary = await db.gestor_beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "gestor_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")
    
    # Get exchange rate
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    ris_to_ves = rate_doc.get("ris_to_ves", 92.0) if rate_doc else 92.0
    amount_ves = request.amount_ris * ris_to_ves
    
    # Get commission
    settings = await db.app_settings.find_one({"setting_id": "gestor_commission"})
    commission_rate = settings.get("value", 5.0) / 100 if settings else 0.05
    commission_amount = request.amount_ris * commission_rate
    
    # Create gestor transaction
    tx_id = f"gtx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    
    gestor_transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "gestor_id": current_user.user_id,
        "gestor_name": user.get("name", ""),
        "gestor_code": user.get("gestor_code", ""),
        "client_name": request.client_name,
        "client_phone": request.client_phone or "",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_name": beneficiary.get("full_name", ""),
        "beneficiary_data": {
            "full_name": beneficiary.get("full_name"),
            "id_document": beneficiary.get("id_document"),
            "bank": beneficiary.get("bank"),
            "bank_code": beneficiary.get("bank_code"),
            "phone_number": beneficiary.get("phone_number"),
            "account_number": beneficiary.get("account_number"),
            "payment_type": request.payment_type
        },
        "payment_type": request.payment_type,
        "amount_ris": request.amount_ris,
        "amount_ves": amount_ves,
        "rate_used": ris_to_ves,
        "commission_rate": commission_rate * 100,
        "commission_amount": commission_amount,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.gestor_transactions.insert_one(gestor_transaction)
    
    # Débito atómico con guardia (evita condición de carrera / saldo negativo)
    debited = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris_terceros": {"$gte": to_decimal128(to_decimal(request.amount_ris))}},
        {"$inc": {"balance_ris_terceros": to_decimal128(-to_decimal(request.amount_ris))}}
    )
    if not debited:
        # El saldo cambió entre la comprobación y el débito (carrera): deshacemos el registro.
        await db.gestor_transactions.delete_one({"transaction_id": tx_id})
        raise HTTPException(status_code=400, detail="Saldo de terceros insuficiente.")
    
    # Create withdrawal for admin processing
    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": request.payment_type
    }
    
    withdrawal = {
        "transaction_id": f"tx_{uuid.uuid4().hex[:12]}",
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "status": "pending",
        "amount_input": request.amount_ris,
        "amount_output": amount_ves,
        "beneficiary_data": beneficiary_data,
        "beneficiary_id": request.beneficiary_id,
        "gestor_transaction_id": tx_id,
        "is_gestor_transaction": True,
        "client_name": request.client_name,
        "client_phone": request.client_phone,
        "payment_type": request.payment_type,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.transactions.insert_one(withdrawal)
    
    # Send to WhatsApp queue
    await send_next_pending_withdrawal_whatsapp()
    
    # Notify gestor
    await create_notification(
        user_id=current_user.user_id,
        title="📤 Transacción Registrada",
        message=f"Envío de {amount_ves:.2f} VES a {beneficiary.get('full_name')} para cliente {request.client_name}. Pendiente de procesamiento.",
        notification_type="gestor_transaction",
        data={"transaction_id": tx_id, "amount_ves": amount_ves}
    )
    
    logger.info(f"Gestor transaction {tx_id} created by {current_user.user_id} for client {request.client_name}")
    
    return {
        "message": "Transacción registrada exitosamente",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount_ris,
        "amount_ves": amount_ves,
        "commission": commission_amount,
        "beneficiary": beneficiary.get("full_name"),
        "client": request.client_name
    }

@router.get("/transactions")
async def get_gestor_transactions(current_user: User = Depends(require_gestor)):
    """Get all transactions"""
    transactions = await db.gestor_transactions.find({"gestor_id": current_user.user_id}).sort("created_at", -1).to_list(100)
    
    result = []
    for t in transactions:
        result.append({
            "transaction_id": t.get("transaction_id"),
            "display_id": t.get("display_id"),
            "client_name": t.get("client_name"),
            "beneficiary_name": t.get("beneficiary_name"),
            "payment_type": t.get("payment_type"),
            "amount_ris": t.get("amount_ris"),
            "amount_ves": t.get("amount_ves"),
            "amount_output": t.get("amount_ves"),
            "commission_amount": t.get("commission_amount"),
            "status": t.get("status"),
            "voucher_url": t.get("voucher_url"),
            "created_at": t.get("created_at"),
            "completed_at": t.get("completed_at")
        })
    
    return result

@router.post("/recharge-terceros")
async def gestor_recharge_terceros(request: GestorRechargeTercerosRequest, current_user: User = Depends(require_gestor)):
    """Transfer balance from personal to terceros account"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    
    balance_personal = to_float(from_db(user.get("balance_ris", 0)))
    if balance_personal < request.amount:
        raise HTTPException(status_code=400, detail=f"Saldo personal insuficiente. Disponible: {balance_personal:.2f} RIS")
    
    # Transfer
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {
            "$inc": {
                "balance_ris": to_decimal128(-to_decimal(request.amount)),
                "balance_ris_terceros": to_decimal128(to_decimal(request.amount))
            }
        }
    )
    
    logger.info(f"Gestor {current_user.user_id} transferred {request.amount} RIS from personal to terceros")
    
    updated_user = await db.users.find_one({"user_id": current_user.user_id})
    
    return {
        "message": f"Transferido {request.amount:.2f} RIS a saldo de terceros",
        "balance_ris": to_float(from_db(updated_user.get("balance_ris", 0))),
        "balance_ris_terceros": to_float(from_db(updated_user.get("balance_ris_terceros", 0)))
    }
