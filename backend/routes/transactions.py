"""
Transaction routes - Withdrawals, Recharges, Beneficiaries
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from models.user import User
from models.requests import WithdrawalRequest, BeneficiaryCreate
from routes.dependencies import get_current_user, get_verified_user
from services.whatsapp import send_next_pending_withdrawal_whatsapp
from services.notifications import create_notification
from services.centro_gestion import registrar_evento
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

# ---- RIS → Reais (Brasil, pago por PIX) ----

class BrBeneficiaryCreate(BaseModel):
    full_name: str
    cpf: str
    pix_key: str

class ReaisSendRequest(BaseModel):
    beneficiary_id: str
    amount: float   # en RIS (1 RIS = 1 R$)

@router.post("/beneficiaries/br")
async def create_br_beneficiary(request: BrBeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Crea un beneficiario en Brasil (pago por PIX en reais)."""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "cpf": request.cpf.strip(),
        "pix_key": request.pix_key.strip(),
        "pais": "BR",
        "payment_type": "pix_br",
        "created_at": datetime.now(timezone.utc),
    }
    await db.beneficiaries.insert_one(beneficiary)
    return {"message": "Beneficiario (Brasil) creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries/br")
async def get_br_beneficiaries(current_user: User = Depends(get_current_user)):
    """Lista los beneficiarios en Brasil del usuario."""
    rows = await db.beneficiaries.find(
        {"user_id": current_user.user_id, "pais": "BR"}
    ).to_list(100)
    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "cpf": b.get("cpf"),
            "pix_key": b.get("pix_key"),
            "payment_type": "pix_br",
            "created_at": b.get("created_at"),
        }
        for b in rows
    ]

@router.post("/reais/send")
async def create_reais_send(request: ReaisSendRequest, current_user: User = Depends(get_current_user)):
    """Crea una orden de envío RIS → Reais (1 RIS = 1 R$, sin comisión: ya viene
    incluida en la recarga). Queda pendiente para que el super_admin la pague
    por PIX en Brasil desde el área de Órdenes por procesar."""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    # Descuento atómico de saldo RIS
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": request.amount}},
        {"$inc": {"balance_ris": -request.amount}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id,
        "pais": "BR",
    })
    if not beneficiary:
        # Devolver el saldo si el beneficiario no existe
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": request.amount}}
        )
        raise HTTPException(status_code=404, detail="Beneficiario de Brasil no encontrado")
    amount_brl = request.amount  # 1 a 1
    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "cpf": beneficiary.get("cpf"),
        "pix_key": beneficiary.get("pix_key"),
        "payment_type": "pix_br",
        "pais": "BR",
    }
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_brl,
        "currency_input": "RIS",
        "currency_output": "BRL",
        "rate": 1.0,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
        "whatsapp_active": False,
    }
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": request.amount}}
        )
        logger.error(f"Fallo al registrar envío a Brasil {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

    await create_notification(
        user_id=current_user.user_id,
        title="Envío a Brasil solicitado",
        message=f"Tu envío de {request.amount:.2f} RIS (R$ {amount_brl:.2f}) a {beneficiary.get('full_name')} fue recibido y está en cola.",
        notification_type="withdrawal_pending",
    )
    return {"success": True, "transaction_id": tx_id, "display_id": display_id, "amount_brl": amount_brl}

@router.post("/withdraw")
@router.post("/withdrawal/create")
async def create_withdrawal(request: WithdrawalRequest, current_user: User = Depends(get_current_user)):
    """Create a withdrawal request"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    # 1) Validar beneficiario ANTES de tocar el saldo (evita débito sin destino)
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) Leer y validar la tasa ANTES de debitar (fail-closed: sin tasa válida no se procesa)
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    ris_to_ves = (rate or {}).get("ris_to_ves")
    if not ris_to_ves or ris_to_ves <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")

    amount_ves = request.amount * ris_to_ves

    # Preparar datos de la transacción (antes del débito; no dependen del saldo)
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
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": "RIS",
        "currency_output": "VES",
        "rate": ris_to_ves,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
        "whatsapp_active": False
    }

    # 3) Débito atómico (impide sobregiro y condiciones de carrera)
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": request.amount}},
        {"$inc": {"balance_ris": -request.amount}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")

    # 4) Crear el registro; si falla, devolver el saldo (compensación) para no perder RIS
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": request.amount}}
        )
        logger.error(f"Fallo al registrar retiro {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el retiro. Tu saldo no fue afectado.")

    # Notify user
    await create_notification(
        user_id=current_user.user_id,
        title="Retiro Solicitado",
        message=f"Tu retiro de {request.amount} RIS ({amount_ves:.2f} VES) ha sido recibido y esta en cola.",
        notification_type="withdrawal_pending"
    )

    # Send to WhatsApp queue
    try:
        await send_next_pending_withdrawal_whatsapp()
    except Exception as e:
        logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

    # Registrar en CentroGestion
    try:
        await registrar_evento(
            tipo="retiro_ves",
            transaction_id=tx_id,
            user_id=current_user.user_id,
            user_email=user.get("email"),
            user_name=user.get("name") or user.get("full_name"),
            amount_input=request.amount,
            amount_output=amount_ves,
            currency_input="RIS",
            currency_output="VES",
            status="pending",
            metadata={
                "display_id": display_id,
                "rate": ris_to_ves,
                "beneficiary": beneficiary_data
            }
        )
    except Exception as e:
        logger.warning(f"registrar_evento fallo: {e}")

    return {
        "message": "Retiro solicitado exitosamente",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount,
        "amount_ves": amount_ves,
        "rate": ris_to_ves
    }

# ============== RECHARGE VES ==============

@router.post("/recharge/ves")
async def recharge_ves(request: dict, current_user: User = Depends(get_current_user)):
    """Create a VES recharge request"""
    amount_ves = float(request.get("amount_ves", 0))
    amount_ris = float(request.get("amount_ris", 0))
    payment_method = request.get("payment_method", "transferencia")
    amount_input = float(request.get("amount_input", amount_ves))

    if amount_ves <= 0 or amount_ris <= 0:
        raise HTTPException(status_code=400, detail="Montos invalidos")

    user = await db.users.find_one({"user_id": current_user.user_id})

    tx_id = f"rech_{uuid.uuid4().hex[:12]}"

    transaction = {
        "transaction_id": tx_id,
        "user_id": current_user.user_id,
        "type": "recharge_ves",
        "amount_input": amount_input,
        "amount_output": amount_ris,
        "currency_input": "VES",
        "currency_output": "RIS",
        "payment_method": payment_method,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }

    await db.transactions.insert_one(transaction)

    # Registrar en CentroGestion
    await registrar_evento(
        tipo="recarga_ves",
        transaction_id=tx_id,
        user_id=current_user.user_id,
        user_email=user.get("email") if user else None,
        user_name=user.get("name") or user.get("full_name") if user else None,
        amount_input=amount_input,
        amount_output=amount_ris,
        currency_input="VES",
        currency_output="RIS",
        status="pending",
        metadata={"payment_method": payment_method}
    )

    return {
        "message": "Recarga VES registrada, pendiente de verificacion",
        "transaction_id": tx_id,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris
    }

# ============== TRANSACTION HISTORY ==============

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
    transactions = await db.transactions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "transactions": transactions
    }

@router.get("/transactions/{transaction_id}")
async def get_transaction(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific transaction"""
    transaction = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {"_id": 0}
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")

    return transaction

# ============== PENDING WITHDRAWAL CHECK ==============

@router.get("/withdrawal/pending")
async def check_pending_withdrawal(current_user: User = Depends(get_current_user)):
    """Check if user has a pending withdrawal"""
    withdrawal = await db.transactions.find_one(
        {
            "user_id": current_user.user_id,
            "type": {"$in": ["withdrawal", "send"]},
            "status": "pending"
        },
        {"_id": 0},
        sort=[("created_at", -1)]
    )

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
