"""
routes/credits_admin.py — Panel de superadmin para creditos cripto (USDT/USDC).

Endpoints:
  GET  /api/admin/credits/deposits        Lista paginada de crypto_deposits con filtros
                                           (estado, busqueda, rango de fechas) + counts.
  GET  /api/admin/credits/report          Reporte (diario o por rango de fechas) de
                                           operaciones acreditadas, en JSON o CSV.
  POST /api/admin/credits/manual-credit   Acredita balance_usdt/balance_usdc manualmente
                                           (soporte, pruebas). Requiere super_admin.

IMPORTANTE: esto es la billetera de creditos cripto, TOTALMENTE SEPARADA de balance_ris.
Ninguno de estos endpoints toca balance_ris ni la logica de PIX/MercadoPago/BTC.

Toda acreditacion manual pasa por credit_user() (mismo camino que el webhook de NOWPayments)
y queda registrada en crypto_deposits con source="admin_manual", credited=True desde el
inicio, y el user_id del admin que la hizo — asi aparece en el mismo historial que los
depositos reales y queda trazabilidad completa para auditoria (incluye el ledger cripto).
"""
import csv
import io
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services.credits import normalize_currency, credit_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/credits", tags=["admin-credits"])


def _parse_date_range(date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Convierte 'YYYY-MM-DD' a un filtro Mongo {'$gte':..., '$lte':...} en UTC.
    Si solo viene una punta, arma el rango solo con esa punta."""
    date_range: dict = {}
    try:
        if date_from:
            date_range["$gte"] = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if date_to:
            date_range["$lte"] = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha invalido. Usa YYYY-MM-DD.")
    return date_range


@router.get("/deposits")
async def list_credit_deposits(
    status: Optional[str] = Query(None, description="pending | finished | failed | expired | refunded | manual | error | all"),
    search: Optional[str] = Query(None, description="Busca por email, nombre, order_id o user_id"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD, filtra por fecha de creacion"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD, filtra por fecha de creacion"),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
    admin: User = Depends(get_super_admin),
):
    """Historial de depositos de creditos cripto (reales via NOWPayments + acreditaciones
    manuales del admin), con filtros por estado, busqueda y rango de fechas, y contadores
    por estado."""
    query: dict = {}
    if status and status != "all":
        query["status"] = status

    if date_from or date_to:
        date_range = _parse_date_range(date_from, date_to)
        if date_range:
            query["created_at"] = date_range

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


@router.get("/report")
async def credits_report(
    date_from: str = Query(..., description="YYYY-MM-DD (usa la misma fecha en date_to para reporte diario)"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    currency: str = Query("all", description="usdt | usdc | all"),
    format: str = Query("json", description="json | csv"),
    admin: User = Depends(get_super_admin),
):
    """Reporte de operaciones cripto EFECTIVAMENTE ACREDITADAS (depositos confirmados
    via NOWPayments + acreditaciones manuales) en un rango de fechas. Si date_from ==
    date_to, es un reporte diario. Devuelve totales por moneda, desglose por dia, y el
    detalle de cada operacion. format=csv descarga el detalle como archivo CSV."""
    date_range = _parse_date_range(date_from, date_to)
    if not date_range:
        raise HTTPException(status_code=400, detail="date_from y date_to son requeridos.")
    if date_range.get("$gte") and date_range.get("$lte") and date_range["$lte"] < date_range["$gte"]:
        raise HTTPException(status_code=400, detail="date_to no puede ser anterior a date_from.")

    query: dict = {"credited": True, "credited_at": date_range}
    if currency in ("usdt", "usdc"):
        query["currency"] = currency

    items = await db.crypto_deposits.find(query, {"_id": 0}).sort("credited_at", 1).to_list(10000)

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

    totals = {"usdt": 0.0, "usdc": 0.0, "count": len(items)}
    by_day: dict = {}
    for it in items:
        c = it.get("currency")
        amt = float(it.get("credit_amount") or it.get("amount") or 0)
        if c in totals:
            totals[c] += amt
        day = it.get("credited_at") or it.get("created_at")
        day_key = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]
        row = by_day.setdefault(day_key, {"date": day_key, "usdt": 0.0, "usdc": 0.0, "count": 0})
        if c in ("usdt", "usdc"):
            row[c] += amt
        row["count"] += 1

    totals["usdt"] = round(totals["usdt"], 8)
    totals["usdc"] = round(totals["usdc"], 8)
    for row in by_day.values():
        row["usdt"] = round(row["usdt"], 8)
        row["usdc"] = round(row["usdc"], 8)
    by_day_list = sorted(by_day.values(), key=lambda r: r["date"])

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["fecha", "order_id", "usuario_email", "moneda", "monto_acreditado", "fuente", "estado"])
        for it in items:
            created = it.get("credited_at") or it.get("created_at")
            fecha = created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else str(created)
            writer.writerow([
                fecha,
                it.get("order_id", ""),
                it.get("user_email", ""),
                it.get("currency", ""),
                it.get("credit_amount") or it.get("amount") or 0,
                it.get("source", "nowpayments"),
                it.get("status", ""),
            ])
        buf.seek(0)
        filename = f"reporte_cripto_{date_from}_a_{date_to}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return {
        "range": {"date_from": date_from, "date_to": date_to},
        "currency": currency,
        "totals": totals,
        "by_day": by_day_list,
        "items": items,
    }


class ManualCreditRequest(BaseModel):
    email: str
    currency: str  # "usdt" | "usdc"
    amount: float
    note: Optional[str] = Field(None, max_length=300)


@router.post("/manual-credit")
async def manual_credit(data: ManualCreditRequest, admin: User = Depends(get_super_admin)):
    """Acredita balance_usdt/balance_usdc manualmente a un usuario (soporte/pruebas).

    Usa el mismo credit_user() atomico que el webhook. NUNCA toca balance_ris.
    Queda registrado en crypto_deposits (source=admin_manual) con el admin que lo hizo,
    y como linea de auditoria en el ledger cripto.
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

    result = await credit_user(
        db, user["user_id"], currency, data.amount,
        movement_type="ajuste_admin_cripto",
        reference_kind="manual",
        reference_id=order_id,
        actor_type="admin",
        actor_id=admin.user_id,
        actor_email=getattr(admin, "email", None),
        notes=data.note or "Acreditacion manual desde panel de superadmin",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "No se pudo acreditar."))

    await db.crypto_deposits.insert_one(
        {
            "order_id": order_id,
            "user_id": user["user_id"],
            "currency": currency,
            "amount": float(data.amount),
            "credit_amount": float(data.amount),
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
        f"a {user.get('user_id')} (order {order_id})"
    )

    return {
        "ok": True,
        "order_id": order_id,
        "user_email": user["email"],
        "currency": currency,
        "amount": data.amount,
        "field": result.get("field"),
    }
