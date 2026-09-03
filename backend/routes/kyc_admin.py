"""
KYC Admin Routes - Enhanced KYC management for admin panel.

Endpoints:
  - GET    /api/admin/kyc/list             List KYC submissions with filters & counts
  - GET    /api/admin/kyc/{id}             Get full KYC detail
  - POST   /api/admin/kyc/{id}/approve     Approve KYC (with audit log)
  - POST   /api/admin/kyc/{id}/reject      Reject KYC (reason required, audit log)
  - PATCH  /api/admin/kyc/{id}/note        Update internal admin note
  - GET    /api/admin/kyc/{id}/history     Get full audit history for a KYC

Audit log is stored in `kyc_audit_log` collection.
Internal notes are stored on the `verifications` document itself (`admin_note`).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin, get_crm_user
from services.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/kyc", tags=["admin-kyc"])


# ============================================================================
# CONSTANTS - Predefined rejection reasons
# ============================================================================

REJECTION_REASONS = {
    "illegible":        "Documento ilegible o borroso",
    "expired":          "Documento vencido",
    "data_mismatch":    "Datos no coinciden con el documento",
    "selfie_mismatch":  "Selfie no coincide con el documento",
    "wrong_doc_type":   "Documento no aceptado (tipo incorrecto)",
    "other":            "Otro motivo",
}

# Catalog of accepted document types.
# `requires_back=True` means the user MUST also upload the back side of the document.
DOCUMENT_TYPES = [
    {"code": "rg",       "label": "RG (Registro Geral)",            "requires_back": True},
    {"code": "cnh",      "label": "CNH (Carteira Nacional de Habilitação)", "requires_back": True},
    {"code": "rnm",      "label": "RNM (Registro Nacional Migratório)", "requires_back": True},
    {"code": "passport", "label": "Pasaporte",                       "requires_back": False},
]
DOCUMENT_TYPE_MAP = {d["code"]: d for d in DOCUMENT_TYPES}


# ============================================================================
# MODELS
# ============================================================================

class RejectRequest(BaseModel):
    reason_code: str = Field(..., description="Code from REJECTION_REASONS")
    reason_text: Optional[str] = Field(None, description="Free text. Required if reason_code = 'other'")


class NoteRequest(BaseModel):
    note: str = Field("", max_length=2000)


# ============================================================================
# HELPERS
# ============================================================================

def _normalize_image(value):
    """Return None for empty/placeholder/invalid image strings."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    # Strip out common bad sentinels
    if v in ("data:", "data:,", "null", "undefined"):
        return None
    # If it's just a data URL prefix with no content, drop it
    if v.startswith("data:") and len(v) < 30:
        return None
    return v


def _serialize_verification(v: dict, user: dict = None, include_images: bool = True) -> dict:
    """Normalize a verification doc for the API response.

    include_images=False omite las imágenes base64 (pesadas) y en su lugar
    devuelve banderas has_* — se usa en el listado para que cargue rápido.
    Las imágenes completas se obtienen en el endpoint de detalle.
    """
    if not v:
        return {}
    base = {
        "verification_id":      v.get("verification_id"),
        "user_id":              v.get("user_id"),
        "full_name":            v.get("full_name") or (user.get("full_name") if user else None),
        "email":                (user.get("email") if user else None),
        "document_type":        v.get("document_type") or "rg",
        "document_type_label":  DOCUMENT_TYPE_MAP.get(v.get("document_type") or "rg", {}).get("label", "Documento"),
        "document_number":      v.get("document_number"),
        "cpf_number":           v.get("cpf_number"),
        "phone_number":         v.get("phone_number") or (user.get("phone_number") if user else None),
        "status":               v.get("status", "pending"),
        "submitted_at":         v.get("submitted_at"),
        "processed_at":         v.get("processed_at"),
        "processed_by":         v.get("processed_by"),
        "processed_by_name":    v.get("processed_by_name"),
        "rejection_reason":     v.get("rejection_reason"),
        "rejection_code":       v.get("rejection_code"),
        "admin_note":           v.get("admin_note", ""),
    }
    id_front = _normalize_image(v.get("id_document_image"))
    id_back  = _normalize_image(v.get("id_document_image_back"))
    cpf_img  = _normalize_image(v.get("cpf_image"))
    selfie   = _normalize_image(v.get("selfie_image"))
    if include_images:
        base.update({
            "id_document_image":      id_front,
            "id_document_image_back": id_back,
            "cpf_image":              cpf_img,
            "selfie_image":           selfie,
        })
    else:
        base.update({
            "has_id_document":      bool(id_front),
            "has_id_document_back": bool(id_back),
            "has_cpf":              bool(cpf_img),
            "has_selfie":           bool(selfie),
        })
    return base


async def _ensure_indexes():
    try:
        await db.kyc_audit_log.create_index([("verification_id", 1), ("created_at", -1)])
        await db.verifications.create_index("verification_id", unique=True, sparse=True)
        await db.verifications.create_index("status")
    except Exception as e:
        logger.warning(f"KYC index warn: {e}")


async def _audit(verification_id: str, user_id: str, action: str,
                 admin: User, details: dict = None):
    """Insert an audit log entry."""
    try:
        await db.kyc_audit_log.insert_one({
            "audit_id": f"aud_{uuid.uuid4().hex[:12]}",
            "verification_id": verification_id,
            "user_id": user_id,
            "action": action,  # 'approved' | 'rejected' | 'note_updated' | 'submitted'
            "admin_id": getattr(admin, "user_id", None),
            "admin_email": getattr(admin, "email", None),
            "admin_name": getattr(admin, "full_name", None) or getattr(admin, "email", None),
            "details": details or {},
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"Failed to record KYC audit: {e}")


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/list")
async def list_kyc(
    status: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
    search: Optional[str] = Query(None, description="Match name, email or document number"),
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(get_crm_user),
):
    """
    Returns:
        {
            counts: { pending, approved, rejected, total },
            items:  [ <serialized verification> ],
        }
    """
    await _ensure_indexes()
    # Counts (always all statuses)
    counts = {
        "pending":  await db.verifications.count_documents({"status": "pending"}),
        "approved": await db.verifications.count_documents({"status": {"$in": ["approved", "verified"]}}),
        "rejected": await db.verifications.count_documents({"status": "rejected"}),
    }
    counts["total"] = counts["pending"] + counts["approved"] + counts["rejected"]
    # Build query
    query = {}
    if status != "all":
        if status == "approved":
            query["status"] = {"$in": ["approved", "verified"]}
        else:
            query["status"] = status
    if search:
        s = search.strip()
        # search across multiple fields case-insensitive
        regex = {"$regex": s, "$options": "i"}
        query["$or"] = [
            {"full_name": regex},
            {"document_number": regex},
            {"cpf_number": regex},
            {"phone_number": regex},
        ]
    cursor = db.verifications.find(query, {"_id": 0}).sort("submitted_at", -1).limit(limit)
    verifications = await cursor.to_list(limit)
    # Optionally also include users matched by email if search is provided
    # (the verifications collection doesn't store email)
    if search:
        user_ids_already = {v.get("user_id") for v in verifications}
        # find matching users
        users_match = await db.users.find(
            {"email": {"$regex": search.strip(), "$options": "i"}},
            {"_id": 0, "user_id": 1}
        ).to_list(100)
        ids_to_add = [u["user_id"] for u in users_match if u["user_id"] not in user_ids_already]
        if ids_to_add:
            extra_query = {"user_id": {"$in": ids_to_add}}
            if status != "all":
                if status == "approved":
                    extra_query["status"] = {"$in": ["approved", "verified"]}
                else:
                    extra_query["status"] = status
            extras = await db.verifications.find(extra_query, {"_id": 0}).to_list(100)
            verifications.extend(extras)
    # Hydrate with user emails (one batch query)
    uids = [v["user_id"] for v in verifications if v.get("user_id")]
    users_by_id = {}
    if uids:
        users_cursor = db.users.find(
            {"user_id": {"$in": uids}},
            {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "phone_number": 1}
        )
        async for u in users_cursor:
            users_by_id[u["user_id"]] = u
    items = [_serialize_verification(v, users_by_id.get(v.get("user_id")), include_images=False) for v in verifications]
    # Marcar coincidencias con la lista negra de identidades (CPF / documento).
    # Se carga la lista negra una sola vez para no consultar por cada item.
    bl_entries = await db.blacklist.find(
        {"type": {"$in": ["cpf", "document"]}}, {"_id": 0, "type": 1, "value": 1}
    ).to_list(5000)
    banned_cpf = {e["value"] for e in bl_entries if e.get("type") == "cpf"}
    banned_doc = {e["value"] for e in bl_entries if e.get("type") == "document"}
    if banned_cpf or banned_doc:
        for item, v in zip(items, verifications):
            cpf_norm = "".join(c for c in (v.get("cpf_number") or "") if c.isdigit())
            doc_norm = "".join(c for c in (v.get("document_number") or "") if c.isalnum()).upper()
            item["blacklist_match"] = bool(
                (cpf_norm and cpf_norm in banned_cpf) or (doc_norm and doc_norm in banned_doc)
            )
    else:
        for item in items:
            item["blacklist_match"] = False

    # Nivel de riesgo: el asignado por el admin (si existe) y una sugerencia
    # automática por reglas simples (coincidencia con lista negra -> alto).
    for item, v in zip(items, verifications):
        item["risk_level"] = v.get("risk_level")
        item["risk_suggested"] = "high" if item.get("blacklist_match") else "low"

    return {"counts": counts, "items": items}


@router.get("/document-types")
async def get_document_types(admin: User = Depends(get_crm_user)):
    """Catalog of accepted ID document types."""
    return DOCUMENT_TYPES


@router.get("/export.csv")
async def export_kyc_csv(
    status: str = Query("all", pattern="^(pending|approved|rejected|all)$"),
    search: Optional[str] = None,
    admin: User = Depends(get_crm_user),
):
    """Export KYC submissions to CSV with current filters applied."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    query = {}
    if status != "all":
        if status == "approved":
            query["status"] = {"$in": ["approved", "verified"]}
        else:
            query["status"] = status

    if search and search.strip():
        s = search.strip()
        regex = {"$regex": s, "$options": "i"}
        query["$or"] = [
            {"full_name": regex}, {"document_number": regex},
            {"cpf_number": regex}, {"phone_number": regex},
        ]

    verifications = await db.verifications.find(query, {"_id": 0}).sort("submitted_at", -1).to_list(5000)
    uids = [v["user_id"] for v in verifications if v.get("user_id")]
    users_by_id = {}
    if uids:
        async for u in db.users.find({"user_id": {"$in": uids}},
                                     {"_id": 0, "user_id": 1, "email": 1}):
            users_by_id[u["user_id"]] = u

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel UTF-8 support
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "verification_id", "user_id", "email", "full_name",
        "document_type", "document_number", "cpf_number", "phone_number",
        "status", "submitted_at", "processed_at",
        "processed_by_name", "rejection_code", "rejection_reason",
        "admin_note", "has_id_front", "has_id_back", "has_cpf", "has_selfie",
    ])
    for v in verifications:
        u = users_by_id.get(v.get("user_id"), {})
        writer.writerow([
            v.get("verification_id", ""), v.get("user_id", ""),
            u.get("email", ""), v.get("full_name", ""),
            v.get("document_type", ""), v.get("document_number", ""),
            v.get("cpf_number", ""), v.get("phone_number", ""),
            v.get("status", ""),
            (v.get("submitted_at").isoformat() if v.get("submitted_at") else ""),
            (v.get("processed_at").isoformat() if v.get("processed_at") else ""),
            v.get("processed_by_name", ""),
            v.get("rejection_code", "") or "",
            (v.get("rejection_reason", "") or "").replace("\n", " ").replace("\r", " "),
            (v.get("admin_note", "") or "").replace("\n", " ").replace("\r", " "),
            "1" if v.get("id_document_image") else "0",
            "1" if v.get("id_document_image_back") else "0",
            "1" if v.get("cpf_image") else "0",
            "1" if v.get("selfie_image") else "0",
        ])

    buf.seek(0)
    filename = f"kyc_{status}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/rejection-reasons")
async def get_rejection_reasons(admin: User = Depends(get_crm_user)):
    """Predefined rejection reason catalog."""
    return [{"code": code, "label": label} for code, label in REJECTION_REASONS.items()]


@router.get("/{verification_id}")
async def get_kyc_detail(verification_id: str, admin: User = Depends(get_crm_user)):
    v = await db.verifications.find_one({"verification_id": verification_id}, {"_id": 0})
    if not v:
        # fallback by user_id
        v = await db.verifications.find_one({"user_id": verification_id}, {"_id": 0}, sort=[("submitted_at", -1)])
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    user = await db.users.find_one(
        {"user_id": v["user_id"]},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "phone_number": 1,
         "role": 1, "balance_ris": 1, "created_at": 1, "verification_status": 1}
    )
    return {
        "verification": _serialize_verification(v, user),
        "user": user,
    }


@router.get("/{verification_id}/history")
async def get_kyc_history(verification_id: str, admin: User = Depends(get_crm_user)):
    """Audit history for a verification."""
    # Resolve real id (allow user_id fallback)
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        {"_id": 0, "verification_id": 1, "user_id": 1, "submitted_at": 1, "status": 1},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    real_id = v["verification_id"]
    entries = await db.kyc_audit_log.find(
        {"verification_id": real_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    # Prepend a synthetic "submitted" event if no audit row for it
    has_submit = any(e["action"] == "submitted" for e in entries)
    if not has_submit and v.get("submitted_at"):
        entries.append({
            "audit_id": "submit_synth",
            "verification_id": real_id,
            "user_id": v["user_id"],
            "action": "submitted",
            "admin_id": None,
            "admin_name": "Usuario",
            "details": {},
            "created_at": v["submitted_at"],
        })

    return {"verification_id": real_id, "history": entries}


@router.post("/{verification_id}/approve")
async def approve_kyc(verification_id: str, payload: dict = Body(default={}), admin: User = Depends(get_crm_user)):
    checklist = (payload or {}).get("checklist") or {}
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    user_id = v["user_id"]
    real_id = v["verification_id"]
    now = datetime.now(timezone.utc)

    await db.verifications.update_one(
        {"verification_id": real_id},
        {"$set": {
            "status": "approved",
            "processed_at": now,
            "processed_by": admin.user_id,
            "processed_by_name": getattr(admin, "full_name", None) or admin.email,
            "rejection_reason": None,
            "rejection_code": None,
            "kyc_checklist": checklist,
        }}
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"verification_status": "verified", "verified_at": now}}
    )

    await create_notification(
        user_id=user_id,
        title="✅ Verificación Aprobada",
        message="Tu identidad ha sido verificada exitosamente. Ya puedes usar todas las funciones de RIS App.",
        notification_type="verification_approved"
    )

    await _audit(real_id, user_id, "approved", admin, {"checklist": checklist})

    logger.info(f"KYC approved: {real_id} by {admin.user_id}")
    return {"success": True, "message": "Verificación aprobada"}


@router.post("/{verification_id}/risk")
async def set_kyc_risk(verification_id: str, payload: dict = Body(default={}), admin: User = Depends(get_crm_user)):
    """Asigna el nivel de riesgo (low/medium/high) a una verificación. No cambia
    el estado; es una clasificación del admin que queda registrada en auditoría."""
    level = (payload or {}).get("level")
    if level not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="Nivel de riesgo inválido")
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    real_id = v["verification_id"]
    user_id = v["user_id"]
    await db.verifications.update_one(
        {"verification_id": real_id},
        {"$set": {
            "risk_level": level,
            "risk_set_by": admin.user_id,
            "risk_set_at": datetime.now(timezone.utc),
        }},
    )
    await _audit(real_id, user_id, "risk_set", admin, {"level": level})
    return {"success": True, "risk_level": level}


@router.post("/{verification_id}/re-review")
async def re_review_kyc(verification_id: str, admin: User = Depends(get_crm_user)):
    """Marca una verificación ya aprobada para re-revisión: vuelve a 'pending'.
    Los documentos existentes se conservan, así que el admin puede re-revisarlos
    y aprobar de nuevo sin que el usuario tenga que reenviar nada.
    """
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    if v.get("status") not in ("approved", "verified"):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede re-verificar una solicitud que ya fue aprobada"
        )

    user_id = v["user_id"]
    real_id = v["verification_id"]
    now = datetime.now(timezone.utc)

    await db.verifications.update_one(
        {"verification_id": real_id},
        {"$set": {
            "status": "pending",
            "re_review": True,
            "re_review_requested_at": now,
            "re_review_by": admin.user_id,
            "re_review_by_name": getattr(admin, "full_name", None) or admin.email,
        }}
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"verification_status": "pending"}}
    )
    await create_notification(
        user_id=user_id,
        title="🔁 Re-verificación de cuenta",
        message="Por seguridad estamos revisando nuevamente tu identidad. Si necesitamos algo más, te avisaremos.",
        notification_type="kyc"
    )
    await _audit(real_id, user_id, "re_review_requested", admin, {})
    logger.info(f"KYC re-review requested: {real_id} by {admin.user_id}")
    return {"success": True, "message": "Usuario enviado a re-verificación"}


@router.post("/{verification_id}/reject")
async def reject_kyc(verification_id: str, payload: RejectRequest,
                     admin: User = Depends(get_crm_user)):
    if payload.reason_code not in REJECTION_REASONS:
        raise HTTPException(status_code=400, detail="Motivo de rechazo inválido")

    reason_label = REJECTION_REASONS[payload.reason_code]
    if payload.reason_code == "other":
        if not payload.reason_text or not payload.reason_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Para 'Otro motivo' debes proveer un texto descriptivo"
            )

    # Build the user-facing reason string
    final_reason = reason_label
    if payload.reason_text and payload.reason_text.strip():
        final_reason = f"{reason_label}: {payload.reason_text.strip()}"

    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    user_id = v["user_id"]
    real_id = v["verification_id"]
    now = datetime.now(timezone.utc)

    await db.verifications.update_one(
        {"verification_id": real_id},
        {"$set": {
            "status": "rejected",
            "processed_at": now,
            "processed_by": admin.user_id,
            "processed_by_name": getattr(admin, "full_name", None) or admin.email,
            "rejection_reason": final_reason,
            "rejection_code": payload.reason_code,
        }}
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"verification_status": "rejected", "rejection_reason": final_reason}}
    )

    await create_notification(
        user_id=user_id,
        title="❌ Verificación Rechazada",
        message=f"Tu verificación fue rechazada. Motivo: {final_reason}",
        notification_type="verification_rejected"
    )

    await _audit(real_id, user_id, "rejected", admin, {
        "reason_code": payload.reason_code,
        "reason_label": reason_label,
        "reason_text": payload.reason_text or "",
        "final_reason": final_reason,
    })

    logger.info(f"KYC rejected: {real_id} by {admin.user_id} ({payload.reason_code})")
    return {"success": True, "message": "Verificación rechazada", "reason": final_reason}


@router.patch("/{verification_id}/note")
async def update_kyc_note(verification_id: str, payload: NoteRequest,
                          admin: User = Depends(get_crm_user)):
    """Update internal admin note (only visible to admins)."""
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": verification_id}, {"user_id": verification_id}]},
        {"_id": 0, "verification_id": 1, "user_id": 1, "admin_note": 1},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    real_id = v["verification_id"]
    previous = v.get("admin_note", "")
    new_note = (payload.note or "").strip()

    await db.verifications.update_one(
        {"verification_id": real_id},
        {"$set": {
            "admin_note": new_note,
            "admin_note_updated_at": datetime.now(timezone.utc),
            "admin_note_updated_by": admin.user_id,
        }}
    )

    if previous != new_note:
        await _audit(real_id, v["user_id"], "note_updated", admin, {
            "previous_value": previous,
            "new_value": new_note,
            "previous_length": len(previous),
            "new_length": len(new_note),
        })

    return {"success": True, "note": new_note}
