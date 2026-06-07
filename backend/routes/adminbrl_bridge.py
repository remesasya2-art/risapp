"""
adminbrl_bridge.py - Bridge API para comunicacion entre adminbrl y risapp.

Autenticacion: API key via header X-AdminBRL-Key (env: ADMINBRL_API_KEY).
No requiere sesion de usuario. Solo para uso interno entre sistemas.

Endpoints:
  GET  /api/adminbrl/withdrawals/pending   -- Retiros VES pendientes
  POST /api/adminbrl/withdrawals/process   -- Aprobar/rechazar retiro VES
  GET  /api/adminbrl/btc/pending           -- Retiros BTC pendientes (estado=pagado)
  POST /api/adminbrl/btc/process           -- Marcar retiro BTC como enviado
  POST /api/adminbrl/rates/sync            -- Sincronizar tasa del dia
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from database import db
from services.notifications import create_notification
from services.whatsapp import send_next_pending_withdrawal_whatsapp

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/adminbrl", tags=["adminbrl-bridge"])

# ============================================================================
# AUTH HELPER
# ============================================================================

ADMINBRL_API_KEY = os.getenv("ADMINBRL_API_KEY", "")


def _check_api_key(x_adminbrl_key: Optional[str]) -> None:
    if not ADMINBRL_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ADMINBRL_API_KEY no configurada en el servidor."
        )
    if x_adminbrl_key != ADMINBRL_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API key invalida o ausente."
        )


# ============================================================================
# MODELS
# ============================================================================

class ProcessWithdrawalRequest(BaseModel):
    transaction_id: str
    action: str
    bank_id: Optional[str] = None
    proof_images: Optional[List[str]] = None
    rejection_reason: Optional[str] = None


class ProcessBtcRequest(BaseModel):
    remesa_id: str
    proof_images: Optional[List[str]] = None


class SyncRateRequest(BaseModel):
    tasa_ves: float
    source: Optional[str] = "adminbrl"


# ============================================================================
# HELPERS
# ============================================================================

def _serialize_withdrawal(tx: dict, user: dict = None) -> dict:
    benef = tx.get("beneficiary_data", {}) or {}
    return {
        "transaction_id": tx.get("transaction_id"),
        "display_id": tx.get("display_id"),
        "user_id": tx.get("user_id"),
        "user_name": (user.get("name") or user.get("full_name")) if user else "Unknown",
        "user_email": user.get("email") if user else None,
        "amount_input": float(tx.get("amount_input", 0) or 0),
        "amount_output": float(tx.get("amount_output", 0) or 0),
        "status": tx.get("status"),
        "beneficiary": {
            "full_name": benef.get("full_name") or benef.get("name"),
            "id_document": benef.get("id_document") or benef.get("cedula"),
            "phone": benef.get("phone") or benef.get("phone_number"),
            "bank_name": benef.get("bank_name"),
            "account_number": benef.get("account_number"),
        },
        "created_at": tx.get("created_at").isoformat() if tx.get("created_at") else None,
        "proof_images": tx.get("proof_images", []),
    }


def _serialize_btc_remesa(r: dict, user: dict = None) -> dict:
    benef = r.get("beneficiario_data", {}) or {}
    return {
        "remesa_id": r.get("remesa_id"),
        "user_id": r.get("user_id"),
        "user_email": user.get("email") if user else None,
        "user_name": user.get("full_name") if user else None,
        "estado": r.get("estado", "pendiente"),
        "usd_cliente": float(r.get("usd_cliente", 0) or 0),
        "ves_recibe": float(r.get("ves_recibe", 0) or 0),
        "btc_pagar": float(r.get("btc_pagar", 0) or 0),
        "sats": int(r.get("sats", 0) or 0),
        "memo": r.get("memo"),
        "beneficiario": {
            "full_name": benef.get("full_name"),
            "id_document": benef.get("id_document") or benef.get("cedula"),
            "phone": benef.get("phone") or benef.get("phone_number"),
        },
        "pagado_en": r.get("pagado_en").isoformat() if r.get("pagado_en") else None,
        "proof_images": r.get("proof_images", []),
    }


# ============================================================================
# ENDPOINTS -- RETIROS VES
# ============================================================================

@router.get("/withdrawals/pending")
async def get_pending_withdrawals(
    x_adminbrl_key: Optional[str] = Header(None)
):
    _check_api_key(x_adminbrl_key)

    cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", 1)

    withdrawals = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append(_serialize_withdrawal(tx, user))

    return {"withdrawals": withdrawals, "total": len(withdrawals)}


@router.post("/withdrawals/process")
async def process_withdrawal(
    request: ProcessWithdrawalRequest,
    x_adminbrl_key: Optional[str] = Header(None)
):
    _check_api_key(x_adminbrl_key)

    transaction = await db.transactions.find_one({"transaction_id": request.transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada.")

    if transaction.get("status") != "pending":
        raise HTTPException(status_code=400, detail="La transaccion ya fue procesada.")

    action = request.action

    if action == "approve":
        amount_output = transaction.get("amount_output", 0)
        bank_id = request.bank_id

        if not bank_id:
            raise HTTPException(status_code=400, detail="Debes indicar bank_id para aprobar.")

        bank = await db.bank_accounts.find_one({"bank_id": bank_id})
        if not bank:
            raise HTTPException(status_code=400, detail="Banco no encontrado.")

        new_balance = bank["balance"] - amount_output
        transaction_id = request.transaction_id

        await db.bank_accounts.update_one(
            {"bank_id": bank_id},
            {"$inc": {"balance": -amount_output}}
        )

        beneficiary = transaction.get("beneficiary_data", {})
        beneficiary_name = beneficiary.get("full_name", beneficiary.get("name", ""))
        await db.bank_ledger.insert_one({
            "bank_id": bank_id,
            "bank_name": bank["name"],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "type": "salida",
            "concept": f"Pago beneficiario: {beneficiary_name} (TX {transaction.get('display_id', transaction_id[:8])})",
            "amount": amount_output,
            "balance_after": round(new_balance, 2),
            "reference": transaction_id,
            "notes": "Procesado via adminbrl bridge",
            "created_at": datetime.now(timezone.utc),
        })

        update_data = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "bank_id": bank_id,
            "whatsapp_active": False,
        }
        if request.proof_images:
            update_data["proof_images"] = request.proof_images

        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": update_data}
        )

        await create_notification(
            user_id=transaction["user_id"],
            title="Retiro Completado",
            message=f"Tu retiro de {transaction.get('amount_output', 0):.2f} VES ha sido procesado.",
            notification_type="withdrawal_completed"
        )

        if transaction.get("gestor_transaction_id"):
            await db.gestor_transactions.update_one(
                {"transaction_id": transaction["gestor_transaction_id"]},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
            )

        try:
            await send_next_pending_withdrawal_whatsapp()
        except Exception as e:
            logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

        logger.info(f"[adminbrl] Retiro {transaction_id} APROBADO -- banco {bank_id}")
        return {"message": "Retiro aprobado", "transaction_id": transaction_id}

    elif action == "reject":
        transaction_id = request.transaction_id

        await db.users.update_one(
            {"user_id": transaction["user_id"]},
            {"$inc": {"balance_ris": transaction.get("amount_input", 0)}}
        )

        rejection_reason = request.rejection_reason or "Rechazado por el operador."

        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {
                "status": "rejected",
                "rejected_at": datetime.now(timezone.utc),
                "rejection_reason": rejection_reason,
                "whatsapp_active": False,
            }}
        )

        await create_notification(
            user_id=transaction["user_id"],
            title="Retiro Rechazado",
            message="Tu retiro ha sido rechazado. El saldo ha sido devuelto.",
            notification_type="withdrawal_rejected"
        )

        try:
            await send_next_pending_withdrawal_whatsapp()
        except Exception as e:
            logger.warning(f"send_next_pending_withdrawal_whatsapp fallo: {e}")

        logger.info(f"[adminbrl] Retiro {transaction_id} RECHAZADO")
        return {"message": "Retiro rechazado y saldo devuelto", "transaction_id": transaction_id}

    else:
        raise HTTPException(status_code=400, detail=f"Accion invalida: '{action}'. Usa 'approve' o 'reject'.")


# ============================================================================
# ENDPOINTS -- RETIROS BTC
# ============================================================================

@router.get("/btc/pending")
async def get_pending_btc(
    x_adminbrl_key: Optional[str] = Header(None)
):
    _check_api_key(x_adminbrl_key)

    remesas = await db.btc_remesas.find(
        {"estado": "pagado"},
        {"_id": 0}
    ).sort("pagado_en", 1).to_list(100)

    result = []
    for r in remesas:
        user = await db.users.find_one({"user_id": r.get("user_id")})
        result.append(_serialize_btc_remesa(r, user))

    return {"ordenes": result, "total": len(result)}


@router.post("/btc/process")
async def process_btc(
    request: ProcessBtcRequest,
    x_adminbrl_key: Optional[str] = Header(None)
):
    _check_api_key(x_adminbrl_key)

    remesa = await db.btc_remesas.find_one({"remesa_id": request.remesa_id})
    if not remesa:
        raise HTTPException(status_code=404, detail="Orden BTC no encontrada.")
    if remesa["estado"] != "pagado":
        raise HTTPException(status_code=400, detail=f"Estado actual: {remesa['estado']}. Solo se puede marcar como enviada si esta en 'pagado'.")

    wallet = await db.btc_ves_wallets.find_one({"user_id": remesa["user_id"]})
    saldo_actual = wallet["saldo"] if wallet else 0.0
    ves_recibe = remesa.get("ves_recibe", 0)

    if saldo_actual < ves_recibe:
        raise HTTPException(status_code=400, detail=f"Saldo BTC-VES insuficiente ({saldo_actual:.2f} < {ves_recibe:.2f}).")

    await db.btc_ves_wallets.update_one(
        {"user_id": remesa["user_id"]},
        {"$inc": {"saldo": -ves_recibe}}
    )

    update_data = {
        "estado": "enviado",
        "enviado_en": datetime.now(timezone.utc),
    }
    if request.proof_images:
        update_data["proof_images"] = request.proof_images

    await db.btc_remesas.update_one(
        {"remesa_id": request.remesa_id},
        {"$set": update_data}
    )

    await create_notification(
        user_id=remesa["user_id"],
        title="Remesa BTC Enviada",
        message=f"Tu remesa de {ves_recibe:.2f} VES ha sido enviada al beneficiario.",
        notification_type="btc_remesa_enviada"
    )

    logger.info(f"[adminbrl] Remesa BTC {request.remesa_id} marcada como enviada.")
    return {"ok": True, "msg": "Orden marcada como enviada.", "remesa_id": request.remesa_id}


# ============================================================================
# ENDPOINT -- SINCRONIZAR TASA
# ============================================================================

@router.post("/rates/sync")
async def sync_rate(
    request: SyncRateRequest,
    x_adminbrl_key: Optional[str] = Header(None)
):
    _check_api_key(x_adminbrl_key)

    if request.tasa_ves <= 0:
        raise HTTPException(status_code=400, detail="La tasa debe ser mayor que 0.")

    now = datetime.now(timezone.utc)

    await db.config.update_one(
        {"clave": "tasa_usd_ves"},
        {"$set": {
            "clave": "tasa_usd_ves",
            "valor": request.tasa_ves,
            "updated_at": now,
            "source": request.source or "adminbrl",
        }},
        upsert=True,
    )

    await db.accounting_rates.update_one(
        {"date": now.strftime("%Y-%m-%d")},
        {"$set": {
            "date": now.strftime("%Y-%m-%d"),
            "rate": request.tasa_ves,
            "source": request.source or "adminbrl",
            "updated_at": now,
        }},
        upsert=True,
    )

    logger.info(f"[adminbrl] Tasa sync: {request.tasa_ves} VES/USD (fuente: {request.source})")
    return {
        "ok": True,
        "tasa_ves": request.tasa_ves,
        "updated_at": now.isoformat(),
        "source": request.source,
    }
