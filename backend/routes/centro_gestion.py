"""
centro_gestion.py (routes) - Endpoints para CentroGestionCont-Byte

Autenticacion: API key via header X-CentroGestion-Key (env: CENTRO_GESTION_API_KEY)
Prefijo: /api/centro-gestion

Endpoints:
  GET  /api/centro-gestion/log              -- Lista de eventos paginada con filtros
  GET  /api/centro-gestion/log/{tx_id}      -- Detalle de un evento por transaction_id
  GET  /api/centro-gestion/stats            -- Totales y resumen por tipo
  GET  /api/centro-gestion/health           -- Health check (verifica conectividad)
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/centro-gestion", tags=["centro-gestion"])

CENTRO_GESTION_API_KEY = os.getenv("CENTRO_GESTION_API_KEY", "")


def _check_key(x_centrogestion_key: Optional[str]) -> None:
    if not CENTRO_GESTION_API_KEY:
        raise HTTPException(status_code=503, detail="CENTRO_GESTION_API_KEY no configurada en el servidor")
    if x_centrogestion_key != CENTRO_GESTION_API_KEY:
        raise HTTPException(status_code=401, detail="API key invalida")


# ===========================================================================
# HEALTH CHECK
# ===========================================================================

@router.get("/health")
async def health(x_centrogestion_key: Optional[str] = Header(None)):
    _check_key(x_centrogestion_key)
    total = await db.centro_gestion_log.count_documents({})
    return {
        "status": "ok",
        "origen": "risappbr",
        "total_eventos": total,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ===========================================================================
# LOG DE TRANSACCIONES
# ===========================================================================

@router.get("/log")
async def get_log(
    x_centrogestion_key: Optional[str] = Header(None),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: retiro_ves, recarga_pix, recarga_ves, pago_tarjeta, remesa_btc, retiro_aprobado, retiro_rechazado"),
    status: Optional[str] = Query(None, description="Filtrar por status: pending, completed, rejected, approved"),
    user_id: Optional[str] = Query(None),
    desde: Optional[str] = Query(None, description="ISO date desde, ej: 2026-01-01"),
    hasta: Optional[str] = Query(None, description="ISO date hasta, ej: 2026-12-31"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200)
):
    _check_key(x_centrogestion_key)

    filtro = {}
    if tipo:
        filtro["tipo"] = tipo
    if status:
        filtro["status"] = status
    if user_id:
        filtro["user_id"] = user_id
    if desde or hasta:
        filtro["registrado_en"] = {}
        if desde:
            filtro["registrado_en"]["$gte"] = datetime.fromisoformat(desde).replace(tzinfo=timezone.utc)
        if hasta:
            filtro["registrado_en"]["$lte"] = datetime.fromisoformat(hasta).replace(tzinfo=timezone.utc)

    skip = (page - 1) * limit
    total = await db.centro_gestion_log.count_documents(filtro)
    docs = await db.centro_gestion_log.find(
        filtro,
        {"_id": 0}
    ).sort("registrado_en", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "eventos": docs
    }


@router.get("/log/{transaction_id}")
async def get_evento(
    transaction_id: str,
    x_centrogestion_key: Optional[str] = Header(None)
):
    _check_key(x_centrogestion_key)
    doc = await db.centro_gestion_log.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return doc


# ===========================================================================
# ESTADISTICAS / RESUMEN
# ===========================================================================

@router.get("/stats")
async def get_stats(
    x_centrogestion_key: Optional[str] = Header(None),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None)
):
    _check_key(x_centrogestion_key)

    fecha_filtro = {}
    if desde or hasta:
        fecha_filtro["registrado_en"] = {}
        if desde:
            fecha_filtro["registrado_en"]["$gte"] = datetime.fromisoformat(desde).replace(tzinfo=timezone.utc)
        if hasta:
            fecha_filtro["registrado_en"]["$lte"] = datetime.fromisoformat(hasta).replace(tzinfo=timezone.utc)

    pipeline = [
        {"$match": fecha_filtro} if fecha_filtro else {"$match": {}},
        {"$group": {
            "_id": "$tipo",
            "total_eventos": {"$sum": 1},
            "monto_input_total": {"$sum": {"$ifNull": ["$amount_input", 0]}},
            "monto_output_total": {"$sum": {"$ifNull": ["$amount_output", 0]}}
        }},
        {"$sort": {"total_eventos": -1}}
    ]

    # Limpiar match vacio
    pipeline = [s for s in pipeline if s != {"$match": {}}]
    if fecha_filtro:
        pipeline = [{"$match": fecha_filtro}] + pipeline[0:]
    else:
        pipeline = pipeline[1:]

    resumen = await db.centro_gestion_log.aggregate(pipeline).to_list(50)
    total_global = await db.centro_gestion_log.count_documents(fecha_filtro)

    return {
        "total_eventos": total_global,
        "por_tipo": resumen,
        "generado_en": datetime.now(timezone.utc).isoformat()
    }
