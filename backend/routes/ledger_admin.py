"""
Endpoints de administración del libro mayor RIS (solo super_admin).
- POST /admin/ledger/opening   -> crea las líneas de apertura (una sola vez).
- GET  /admin/ledger/reconcile -> compara balance_ris vs suma del ledger y lista descuadres.
- GET  /admin/ledger/entries   -> lista las líneas del ledger de un usuario.
"""
import logging

from fastapi import APIRouter, Depends, Query

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services.ledger import sum_ris_balance, create_opening_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ledger", tags=["ledger"])

EPS = 0.01  # tolerancia de redondeo al comparar saldos


@router.post("/opening")
async def run_opening(admin: User = Depends(get_super_admin)):
    """Crea las líneas de saldo de apertura (idempotente: se puede llamar varias
    veces sin duplicar). A partir de aquí el ledger cuadra contra los saldos."""
    result = await create_opening_entries()
    return result


@router.get("/reconcile")
async def reconcile(admin: User = Depends(get_super_admin)):
    """Compara, por usuario, el balance_ris guardado contra la suma del ledger.
    Lista solo los que NO cuadran (diferencia mayor a la tolerancia)."""
    mismatches = []
    checked = 0
    async for u in db.users.find(
        {},
        {"user_id": 1, "email": 1, "full_name": 1, "name": 1,
         "balance_ris": 1, "role": 1},
    ):
        uid = u.get("user_id")
        if not uid:
            continue
        checked += 1
        bal = float(u.get("balance_ris") or 0)
        led = await sum_ris_balance(uid, "balance_ris")
        diff = round(bal - led, 8)
        if abs(diff) > EPS:
            mismatches.append({
                "user_id": uid,
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
                "balance_ris": bal,
                "ledger_sum": led,
                "diff": diff,
            })
    mismatches.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return {
        "checked": checked,
        "mismatches_count": len(mismatches),
        "ok": len(mismatches) == 0,
        "mismatches": mismatches,
    }


@router.get("/entries")
async def list_entries(
    user_id: str = Query(...),
    limit: int = Query(100),
    admin: User = Depends(get_super_admin),
):
    """Lista las líneas del ledger de un usuario (más recientes primero) y
    muestra su saldo guardado vs la suma del ledger."""
    rows = []
    cursor = db.ledger.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(min(max(limit, 1), 500))
    async for r in cursor:
        rows.append(r)
    bal_doc = await db.users.find_one({"user_id": user_id}, {"balance_ris": 1})
    led = await sum_ris_balance(user_id, "balance_ris")
    bal = float((bal_doc or {}).get("balance_ris") or 0)
    return {
        "user_id": user_id,
        "balance_ris": bal,
        "ledger_sum": led,
        "diff": round(bal - led, 8),
        "count": len(rows),
        "entries": rows,
    }
