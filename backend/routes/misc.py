"""
Miscellaneous routes - Policies, VES info, Balance, Verification, Export, Dashboard
"""
import uuid
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openpyxl import Workbook

from database import db
from routes.dependencies import get_current_user, get_super_admin
from services.limits import limits_payload
from services.kyc_quota import quota_payload
from models.user import User
from services.imagen_recibida import (ImagenInvalida, limpiar_imagen,
                                      limpiar_imagen_opcional)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["misc"])


# ============== POLICIES ==============

class AcceptPolicy(BaseModel):
    policy_type: str


@router.get("/policies")
async def get_policies():
    """Get all policies"""
    policies = await db.policies.find({}, {"_id": 0}).to_list(10)
    return policies


@router.post("/policies/accept")
async def accept_policy(data: AcceptPolicy, current_user: User = Depends(get_current_user)):
    """Accept a policy"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$addToSet": {"accepted_policies": data.policy_type}}
    )
    return {"success": True}


@router.get("/policies/status")
async def get_policies_status(current_user: User = Depends(get_current_user)):
    """Get user's policy acceptance status"""
    user = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    return {"accepted_policies": user.get("accepted_policies", [])}


# ============== VES PAYMENT INFO ==============

@router.get("/ves-payment-info")
async def get_ves_payment_info():
    """Get VES payment info for manual transfers"""
    info = await db.settings.find_one({"type": "ves_payment_info"}, {"_id": 0})
    return info or {
        "bank": "Banesco",
        "account_type": "Corriente",
        "account_number": "0134-0000-00-0000000000",
        "holder_name": "RIS APP C.A.",
        "holder_id": "J-00000000-0"
    }


# ============== LIMITES DE MONTO ==============

@router.get("/limits")
async def get_limits():
    """Limites de monto por operacion, para que la pantalla no los tenga hardcodeados.

    Publico a proposito: son los mismos para todos los usuarios y la pantalla de
    recarga necesita mostrarlos antes de que el usuario haga nada.
    """
    return limits_payload()


@router.get("/limits/me")
async def get_my_limits(current_user: User = Depends(get_current_user)):
    """Limites por operacion mas el cupo que le queda a ESTE usuario sin verificar.

    La pantalla lo usa para mostrar cuanto le queda y para levantar la ventana
    flotante cuando se agoto. El servidor valida igual: esto es solo para mostrar.
    """
    user_doc = await db.users.find_one({"user_id": current_user.user_id})
    return {**limits_payload(), "cupo_kyc": quota_payload(user_doc)}


# ============== USER BALANCE ==============

@router.get("/user/balance")
async def get_user_balance(current_user: User = Depends(get_current_user)):
    """Get user balance"""
    return {
        "balance_ris": current_user.balance_ris or 0,
        "balance_ris_terceros": current_user.balance_ris_terceros or 0,
        "balance_ves": getattr(current_user, 'balance_ves', 0) or 0
    }


# ============== VERIFICATION ==============

class VerificationSubmit(BaseModel):
    full_name: str
    document_number: str
    cpf_number: str
    phone_number: str
    id_document_image: str
    cpf_image: str
    selfie_image: str
    # NEW: document type + back side (back required for rg/cnh/rnm)
    document_type: Optional[str] = "rg"   # rg | cnh | rnm | passport
    id_document_image_back: Optional[str] = None
    # Keep old fields as optional for backward compatibility
    document_front: Optional[str] = None
    document_back: Optional[str] = None
    selfie: Optional[str] = None


# Document types that physically have a back side and therefore require a second photo.
DOC_TYPES_REQUIRING_BACK = {"rg", "cnh", "rnm"}
ALLOWED_DOC_TYPES = {"rg", "cnh", "rnm", "passport"}


@router.post("/verification/submit")
async def submit_verification(data: VerificationSubmit, current_user: User = Depends(get_current_user)):
    """Submit identity verification.

    For RG, CNH and RNM documents, the back side photo is mandatory.
    For passports, only the front (main page) is needed.
    """
    doc_type = (data.document_type or "rg").lower().strip()
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de documento inválido: {doc_type}")

    if doc_type in DOC_TYPES_REQUIRING_BACK and not (data.id_document_image_back or "").strip():
        raise HTTPException(
            status_code=400,
            detail=f"Para {doc_type.upper()} es obligatorio adjuntar también el reverso del documento."
        )

    # Estos cuatro campos son texto que elige quien sube la foto, y el que los
    # abre después es un administrador. Sin esto, un `javascript:` guardado acá
    # se ejecutaba en la sesión del que estaba revisando el KYC. Ver
    # `services/imagen_recibida.py`.
    try:
        doc_frente = limpiar_imagen(data.id_document_image, campo="El documento")
        doc_dorso = limpiar_imagen_opcional(data.id_document_image_back,
                                            campo="El dorso del documento")
        cpf_img = limpiar_imagen(data.cpf_image, campo="La foto del CPF")
        selfie = limpiar_imagen(data.selfie_image, campo="La selfie")
    except ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))

    verification = {
        "verification_id": f"ver_{uuid.uuid4().hex[:12]}",
        "user_id": current_user.user_id,
        "full_name": data.full_name,
        "document_number": data.document_number,
        "cpf_number": data.cpf_number,
        "phone_number": data.phone_number,
        "document_type": doc_type,
        "id_document_image": doc_frente,
        "id_document_image_back": doc_dorso if doc_type in DOC_TYPES_REQUIRING_BACK else None,
        "cpf_image": cpf_img,
        "selfie_image": selfie,
        "status": "pending",
        "submitted_at": datetime.now(timezone.utc)
    }
    await db.verifications.insert_one(verification)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"verification_status": "pending", "phone_number": data.phone_number}}
    )

    # Notificar a los super administradores que hay un nuevo KYC por revisar.
    # Va en try/except para que un fallo de notificación nunca rompa el envío.
    try:
        from services.notifications import create_notification
        admins = await db.users.find({"role": "super_admin"}, {"user_id": 1}).to_list(50)
        for adm in admins:
            await create_notification(
                user_id=adm["user_id"],
                title="🆔 Nueva verificación KYC",
                message=f"{data.full_name} envió sus documentos para verificación.",
                notification_type="kyc",
                data={
                    "verification_id": verification["verification_id"],
                    "user_id": current_user.user_id,
                }
            )
    except Exception as e:
        logger.warning(f"No se pudo notificar a los admins del nuevo KYC: {e}")

    return {"success": True, "verification_id": verification["verification_id"]}


@router.get("/verification/status")
async def get_verification_status(current_user: User = Depends(get_current_user)):
    """Get verification status"""
    verification = await db.verifications.find_one(
        {"user_id": current_user.user_id},
        {"_id": 0},
        sort=[("submitted_at", -1)],
    )
    return verification or {"status": "none"}


# ============== TRANSACTIONS EXPORT ==============

@router.get("/transactions/export")
async def export_transactions(current_user: User = Depends(get_super_admin)):
    """Export all transactions to Excel"""
    transactions = await db.transactions.find({"hidden_from_admin": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Transacciones"
    
    headers = ["ID", "Usuario", "Tipo", "Monto RIS", "Monto VES", "Estado", "Fecha"]
    ws.append(headers)
    
    for tx in transactions:
        ws.append([
            tx.get("display_id", tx.get("transaction_id", ""))[:15],
            tx.get("user_email", ""),
            tx.get("type", ""),
            tx.get("amount_ris", 0),
            tx.get("amount_ves", 0),
            tx.get("status", ""),
            str(tx.get("created_at", ""))[:19]
        ])
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transacciones.xlsx"}
    )


# ============== ADMIN DASHBOARD ==============

@router.get("/admin/dashboard")
async def get_admin_dashboard(current_user: User = Depends(get_super_admin)):
    """Get admin dashboard stats"""
    # Count users
    total_users = await db.users.count_documents({"is_deleted": {"$ne": True}})
    verified_users = await db.users.count_documents({"verification_status": "verified"})
    
    # Count transactions
    pending_withdrawals = await db.transactions.count_documents({"type": "withdrawal", "status": "pending", "hidden_from_admin": {"$ne": True}})
    completed_today = await db.transactions.count_documents({
        "status": "completed",
        "hidden_from_admin": {"$ne": True},
        "completed_at": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)}
    })
    
    # Calculate volumes
    pipeline = [
        {"$match": {"status": "completed", "hidden_from_admin": {"$ne": True}}},
        {"$group": {"_id": None, "total_ris": {"$sum": "$amount_ris"}, "total_ves": {"$sum": "$amount_ves"}}}
    ]
    volume = await db.transactions.aggregate(pipeline).to_list(1)
    
    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "pending_withdrawals": pending_withdrawals,
        "completed_today": completed_today,
        "total_volume_ris": volume[0]["total_ris"] if volume else 0,
        "total_volume_ves": volume[0]["total_ves"] if volume else 0
    }
