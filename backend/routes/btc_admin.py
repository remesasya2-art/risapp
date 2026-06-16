"""
BTC Lightning Admin Routes - Historial completo, configuración dinámica, export CSV.

Endpoints:
  - GET    /api/admin/btc/transacciones        Lista paginada con filtros + counts
  - GET    /api/admin/btc/transacciones.csv    Export CSV con filtros aplicados
  - GET    /api/admin/btc/config               Lee configuración BTC (margen, comisión, tasa)
  - PATCH  /api/admin/btc/config               Actualiza configuración
  - GET    /api/admin/btc/stats                Métricas agregadas (totales por estado, USD recibido, etc.)

Las configuraciones se persisten en la colección `config` con claves:
  - btc_margen        (default 0.99)
  - btc_comision      (default 1.02)
  - tasa_usd_ves_btc  (default 680.0)   ← reutiliza la clave ya existente
"""
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/btc", tags=["admin-btc"])


# ============================================================================
# CONSTANTS / DEFAULTS
# ============================================================================

DEFAULT_MARGEN = 0.99
DEFAULT_COMISION = 1.02
DEFAULT_TASA_USD_VES = 680.0

# Status labels for UI consistency
STATUS_LABELS = {
    "pendiente": "Pendiente",
    "pagado":    "Pagado",
    "enviado":   "Enviado",
    "cancelado": "Cancelado",
    "expirado":  "Expirado",
    "fallido":   "Fallido",
}


# ============================================================================
# MODELS
# ============================================================================

class BtcConfigUpdate(BaseModel):
    margen: Optional[float] = Field(None, gt=0, le=1.0, description="0 < margen <= 1.0 (1 = sin margen)")
    comision: Optional[float] = Field(None, ge=1.0, le=2.0, description="1.0 <= comision <= 2.0 (1 = sin comisión)")
    tasa_usd_ves: Optional[float] = Field(None, gt=0, description="Tasa USD a VES para conversión final")


class MarcarEnviadoBtcRequest(BaseModel):
    remesa_id: str


# ============================================================================
# HELPERS
# ============================================================================

async def _read_config_value(clave: str, default):
    doc = await db.config.find_one({"clave": clave})
    if not doc:
        return default
    try:
        return type(default)(doc.get("valor", default))
    except (ValueError, TypeError):
        return default


async def _write_config_value(clave: str, valor):
    await db.config.update_one(
        {"clave": clave},
        {"$set": {"clave": clave, "valor": valor, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def _fetch_current_btc_price():
    """Fetches current BTC price in USD from blockchain.info; soft-fails."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://blockchain.info/ticker")
            data = resp.json()
            return float(data["USD"]["last"])
    except Exception as e:
        logger.warning(f"Error precio BTC: {e}")
        return None


def _serialize_remesa(r: dict, user: dict = None) -> dict:
    """Normalize a btc_remesas doc for the API response."""
    benef = r.get("beneficiario_data", {}) or {}
    return {
        "remesa_id":       r.get("remesa_id"),
        "user_id":         r.get("user_id"),
        "user_email":      (user.get("email") if user else None),
        "user_name":       (user.get("full_name") if user else None),
        "estado":          r.get("estado", "pendiente"),
        "estado_label":    STATUS_LABELS.get(r.get("estado", ""), r.get("estado", "")),
        "usd_cliente":     float(r.get("usd_cliente", 0) or 0),
        "ves_recibe":      float(r.get("ves_recibe", 0) or 0),
        "btc_pagar":       float(r.get("btc_pagar", 0) or 0),
        "sats":            int(r.get("sats", 0) or 0),
        "precio_btc_usado": float(r.get("precio_btc_usado", 0) or 0),
        "precio_con_margen": float(r.get("precio_con_margen", 0) or 0),
        "tasa_ves":        float(r.get("tasa_ves", 0) or 0),
        "memo":            r.get("memo"),
        "payment_hash":    r.get("payment_hash"),
        "beneficiario": {
            "full_name":      benef.get("full_name"),
            "id_document":    benef.get("id_document") or benef.get("cedula"),
            "phone":          benef.get("phone") or benef.get("phone_number"),
            "bank":           benef.get("bank") or benef.get("bank_code"),
            "account_number": benef.get("account_number"),
            "payment_type":   benef.get("payment_type"),
        },
        "operador_id":     r.get("operador_id"),
        "creado_en":       r.get("creado_en"),
        "pagado_en":       r.get("pagado_en"),
        "enviado_en":      r.get("enviado_en"),
        "cancelado_en":    r.get("cancelado_en"),
        "expira_en":       r.get("expira_en"),
    }


async def _build_query(status: str, search: Optional[str], date_from: Optional[str],
                       date_to: Optional[str]):
    query = {"tipo": "btc_remesa"}
    if status and status != "all":
        query["estado"] = status

    # Date range on creado_en
    if date_from or date_to:
        rng = {}
        if date_from:
            try:
                rng["$gte"] = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            except Exception:
                pass
        if date_to:
            try:
                rng["$lte"] = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            except Exception:
                pass
        if rng:
            query["creado_en"] = rng

    # Search across remesa_id, user_id, beneficiary name/CI/phone
    if search and search.strip():
        s = search.strip()
        regex = {"$regex": s, "$options": "i"}
        query["$or"] = [
            {"remesa_id": regex},
            {"user_id": regex},
            {"memo": regex},
            {"beneficiario_data.full_name": regex},
            {"beneficiario_data.id_document": regex},
            {"beneficiario_data.cedula": regex},
            {"beneficiario_data.phone": regex},
            {"beneficiario_data.phone_number": regex},
            {"beneficiario_data.account_number": regex},
        ]

        # Allow searching by user email too: resolve user ids and OR them in
        matched_users = await db.users.find(
            {"email": {"$regex": s, "$options": "i"}},
            {"_id": 0, "user_id": 1}
        ).to_list(100)
        extra_user_ids = [u["user_id"] for u in matched_users if u.get("user_id")]
        if extra_user_ids:
            query["$or"].append({"user_id": {"$in": extra_user_ids}})

    return query


async def _hydrate_users(remesas):
    uids = list({r.get("user_id") for r in remesas if r.get("user_id")})
    if not uids:
        return {}
    users_by_id = {}
    async for u in db.users.find(
        {"user_id": {"$in": uids}},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1}
    ):
        users_by_id[u["user_id"]] = u
    return users_by_id


# ============================================================================
# CONFIG ENDPOINTS
# ============================================================================

@router.get("/config")
async def get_btc_config(admin: User = Depends(get_super_admin)):
    margen = await _read_config_value("btc_margen", DEFAULT_MARGEN)
    comision = await _read_config_value("btc_comision", DEFAULT_COMISION)
    tasa_usd_ves = await _read_config_value("tasa_usd_ves_btc", DEFAULT_TASA_USD_VES)
    btc_price = await _fetch_current_btc_price()

    # Compute representative example: 1 USD client → ? BTC, ? VES
    example = {}
    if btc_price:
        precio_con_margen = btc_price * margen
        ejemplo_usd = 1.0
        ejemplo_btc = (ejemplo_usd * comision) / precio_con_margen
        ejemplo_sats = int(round(ejemplo_btc * 100_000_000))
        ejemplo_ves = ejemplo_usd * tasa_usd_ves
        example = {
            "usd": ejemplo_usd,
            "btc": ejemplo_btc,
            "sats": ejemplo_sats,
            "ves": ejemplo_ves,
            "precio_con_margen": precio_con_margen,
        }

    return {
        "margen": margen,
        "comision": comision,
        "tasa_usd_ves": tasa_usd_ves,
        "btc_price_usd": btc_price,
        "btc_price_source": "blockchain.info/ticker",
        "example": example,
        "defaults": {
            "margen": DEFAULT_MARGEN,
            "comision": DEFAULT_COMISION,
            "tasa_usd_ves": DEFAULT_TASA_USD_VES,
        },
    }


@router.patch("/config")
async def update_btc_config(payload: BtcConfigUpdate, admin: User = Depends(get_super_admin)):
    changes = {}
    if payload.margen is not None:
        await _write_config_value("btc_margen", float(payload.margen))
        changes["margen"] = float(payload.margen)
    if payload.comision is not None:
        await _write_config_value("btc_comision", float(payload.comision))
        changes["comision"] = float(payload.comision)
    if payload.tasa_usd_ves is not None:
        await _write_config_value("tasa_usd_ves_btc", float(payload.tasa_usd_ves))
        changes["tasa_usd_ves"] = float(payload.tasa_usd_ves)

    if not changes:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún cambio.")

    # Audit log (best effort)
    try:
        await db.btc_config_audit.insert_one({
            "admin_id":   admin.user_id,
            "admin_email": admin.email,
            "changes":    changes,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning(f"Audit log BTC config failed: {e}")

    return {"success": True, "changes": changes}


# ============================================================================
# STATS / LIST / EXPORT
# ============================================================================

@router.get("/stats")
async def get_btc_stats(admin: User = Depends(get_super_admin)):
    """Aggregated counts and totals by status."""
    pipeline = [
        {"$match": {"tipo": "btc_remesa"}},
        {"$group": {
            "_id": "$estado",
            "count": {"$sum": 1},
            "total_usd": {"$sum": "$usd_cliente"},
            "total_ves": {"$sum": "$ves_recibe"},
        }},
    ]
    by_estado = {}
    async for row in db.btc_remesas.aggregate(pipeline):
        by_estado[row["_id"] or "desconocido"] = {
            "count":     row["count"],
            "total_usd": float(row.get("total_usd", 0) or 0),
            "total_ves": float(row.get("total_ves", 0) or 0),
        }

    grand_total_count = sum(v["count"] for v in by_estado.values())
    grand_total_usd = sum(v["total_usd"] for v in by_estado.values())
    grand_total_ves = sum(v["total_ves"] for v in by_estado.values())

    return {
        "by_estado": by_estado,
        "totals": {
            "count":     grand_total_count,
            "total_usd": grand_total_usd,
            "total_ves": grand_total_ves,
        },
    }


@router.get("/transacciones")
async def list_btc_transacciones(
    status: str = Query("all", regex="^(pendiente|pagado|enviado|cancelado|expirado|fallido|all)$"),
    search: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="ISO date (e.g. 2026-06-01T00:00:00Z)"),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: User = Depends(get_super_admin),
):
    """List BTC remesas with filters, pagination, and per-status counts."""
    query = await _build_query(status, search, date_from, date_to)

    # Counts (independent of pagination, by status)
    counts_pipeline = [
        {"$match": {"tipo": "btc_remesa"}},
        {"$group": {"_id": "$estado", "count": {"$sum": 1}}},
    ]
    counts = {k: 0 for k in ["pendiente", "pagado", "enviado", "cancelado", "expirado", "fallido"]}
    async for row in db.btc_remesas.aggregate(counts_pipeline):
        if row["_id"] in counts:
            counts[row["_id"]] = row["count"]
    counts["total"] = sum(counts.values())

    # Total matching the query (for pagination)
    total = await db.btc_remesas.count_documents(query)
    total_pages = max(1, (total + page_size - 1) // page_size)

    skip = (page - 1) * page_size
    cursor = db.btc_remesas.find(query, {"_id": 0}).sort("creado_en", -1).skip(skip).limit(page_size)
    remesas = await cursor.to_list(page_size)

    users_by_id = await _hydrate_users(remesas)
    items = [_serialize_remesa(r, users_by_id.get(r.get("user_id"))) for r in remesas]

    return {
        "items": items,
        "counts": counts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@router.get("/transacciones.csv")
async def export_btc_csv(
    status: str = Query("all", regex="^(pendiente|pagado|enviado|cancelado|expirado|fallido|all)$"),
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin: User = Depends(get_super_admin),
):
    """Export filtered BTC transactions to CSV."""
    query = await _build_query(status, search, date_from, date_to)
    remesas = await db.btc_remesas.find(query, {"_id": 0}).sort("creado_en", -1).to_list(5000)
    users_by_id = await _hydrate_users(remesas)

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM so Excel reads UTF-8 properly
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "remesa_id", "user_id", "user_email", "user_name",
        "estado", "creado_en", "pagado_en", "enviado_en", "cancelado_en",
        "usd_cliente", "ves_recibe", "btc_pagar", "sats",
        "precio_btc_usado", "precio_con_margen", "tasa_ves",
        "beneficiario_nombre", "beneficiario_cedula", "beneficiario_telefono",
        "beneficiario_banco", "beneficiario_cuenta", "beneficiario_tipo_pago",
        "operador_id", "memo", "payment_hash",
    ])
    for r in remesas:
        u = users_by_id.get(r.get("user_id"), {})
        benef = r.get("beneficiario_data", {}) or {}
        def iso(d):
            return d.isoformat() if isinstance(d, datetime) else (d or "")
        writer.writerow([
            r.get("remesa_id", ""), r.get("user_id", ""),
            u.get("email", ""), u.get("full_name", ""),
            r.get("estado", ""),
            iso(r.get("creado_en")), iso(r.get("pagado_en")),
            iso(r.get("enviado_en")), iso(r.get("cancelado_en")),
            r.get("usd_cliente", 0), r.get("ves_recibe", 0),
            r.get("btc_pagar", 0), r.get("sats", 0),
            r.get("precio_btc_usado", 0), r.get("precio_con_margen", 0),
            r.get("tasa_ves", 0),
            benef.get("full_name", ""),
            benef.get("id_document", "") or benef.get("cedula", ""),
            benef.get("phone", "") or benef.get("phone_number", ""),
            benef.get("bank", "") or benef.get("bank_code", ""),
            benef.get("account_number", ""),
            benef.get("payment_type", ""),
            r.get("operador_id", "") or "",
            (r.get("memo") or "").replace("\n", " "),
            r.get("payment_hash", "") or "",
        ])

    buf.seek(0)
    filename = f"btc_{status}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Cont