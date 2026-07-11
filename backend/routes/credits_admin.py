"""
routes/credits_admin.py — Panel de superadmin para creditos cripto (USDT/USDC).

Endpoints:
  GET  /api/admin/credits/deposits        Lista paginada de crypto_deposits con filtros + counts.
  POST /api/admin/credits/manual-credit   Acredita balance_usdt/balance_usdc manualmente
                                           (soporte, pruebas). Requiere super_admin.

IMPORTANTE: esto es la billetera de creditos cripto, TOTALMENTE SEPARADA de balance_ris.
Ninguno de estos endpoints toca balance_ris ni la logica de PIX/MercadoPago/BTC.
Toda acreditacion manual pasa por credit_user() (mismo camino que el webhook de NOWPayments)
y queda registrada en crypto_deposits con source="admin_manual", credited=True desde el
inicio, y el user_id del admin que la hizo — asi aparece en el mismo historial que los
depositos reales y queda trazabilidad completa para auditoria.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services.credits import normalize_currency, credit_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/credits", tags=["admin-credits"])


@router.get("/deposits")
async def list_credit_deposits(
    status: Optional[str] = Query(None, description="pending | finished | failed | expired | refunded | manual | error | all"),
    search: Optional[str] = Query(None, description="Busca por email, nombre, order_id o user_id"),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    admin: User = Depends(get_super_admin),
):
    """Historial de depositos de creditos cripto (reales via NOWPayments + acreditaciones
    manuales del admin), con filtros por estado y busqueda, y contadores por estado."""
    query: dict = {}
    if status and status != "all":
        query["status"] = status
    if search:
        s = search.strip()
        user_matches = await db.users.find(
            {
                "$or": [
                    {"email": {"$regex": s, "$options": "i"}},
                    {"full_name": {"$regex": s, "$options": "i"}},
                    {"name": {"$regex": s, "$options": "i"}},
                ]
            },
            {"_id": 0, "user_id": 1},
        ).to_list(200)
        matched_user_ids = [u["user_id"] for u in user_matches]
        search_or = [{"order_id": {"$regex": s, "$options": "i"}}]
        if matched_user_ids:
            search_or.append({"user_id": {"$in": matched_user_ids}})
        else:
            search_or.append({"user_id": s})
        query["$or"] = search_or
    total = await db.crypto_deposits.count_documents(query)
    counts: dict = {}
    async for c in db.crypto_deposits.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
        counts[c["_id"] or "unknown"] = c["count"]
    items = (
        await db.crypto_deposits.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    user_ids = list({it.get("user_id") for it in items if it.get("user_id")})
    users_map: dict = {}
    if user_ids:
        async for u in db.users.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "name": 1},
        ):
            users_map[u["user_id"]] = u
    for it in items:
        u = users_map.get(it.get("user_id"), {})
        it["user_email"] = u.get("email")
        it["user_name"] = u.get("full_name") or u.get("name")
    return {"total": total, "counts": counts, "items": items}


class ManualCreditRequest(BaseModel):
    email: str
    currency: str  # "usdt" | "usdc"
    amount: float
    note: Optional[str] = Field(None, max_length=300)


@router.post("/manual-credit")
async def manual_credit(data: ManualCreditRequest, admin: User = Depends(get_super_admin)):
    """Acredita balance_usdt/balance_usdc manualmente a un usuario (soporte/pruebas).
    Usa el mismo credit_user() atomico que el webhook. NUNCA toca balance_ris.
    Queda registrado en crypto_deposits (source=admin_manual) con el admin que lo hizo.
    """
    currency = normalize_currency(data.currency)
    if not currency:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    if not data.amount or data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    user = await db.users.find_one(
        {"email": data.email.strip().lower()}, {"_id": 0, "user_id": 1, "email": 1}
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado con ese email.")
    order_id = f"admin_{currency}_{user['user_id']}_{uuid.uuid4().hex[:12]}"
    result = await credit_user(db, user["user_id"], currency, data.amount)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "No se pudo acreditar."))
    await db.crypto_deposits.insert_one(
        {
            "order_id": order_id,
            "user_id": user["user_id"],
            "currency": currency,
            "amount": float(data.amount),
            "status": "manual",
            "credited": True,
            "credited_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "source": "admin_manual",
            "admin_id": admin.user_id,
            "admin_note": data.note or "",
        }
    )
    logger.info(
        f"Admin {admin.user_id} acredito manualmente {data.amount} {currency} "
        f"a {user['email']} (order {order_id})"
    )
    return {
        "ok": True,
        "order_id": order_id,
        "user_email": user["email"],
        "currency": currency,
        "amount": data.amount,
        "field": result.get("field"),
    }
