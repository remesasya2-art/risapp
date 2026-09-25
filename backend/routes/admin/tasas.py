"""
routes/admin/tasas.py — Las tasas del sistema, su historial y la lectura del BCV.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from models.user import User
from models.panel_tablero import (BcvActualizado, HistorialDeTasas, HistorialDelBcv,
                                   LecturaDelBcv, TasaActualizada, TasasDelSistema)
from models.requests import UpdateRateRequest
from routes.dependencies import (get_admin_user, get_super_admin)
from services import auditoria
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/rates", response_model=TasasDelSistema, response_model_exclude_unset=True)
async def get_rates(admin: User = Depends(get_super_admin)):
    """Get exchange rates"""
    rate = await db.rates.find_one({}, {"_id": 0}, sort=[("updated_at", -1)])
    return rate or {"ris_to_ves": 92.0, "ves_to_ris": 0.0109}

@router.post("/rates", response_model=TasaActualizada, response_model_exclude_unset=True)
async def update_rates(request: UpdateRateRequest, peticion: Request,
                       admin: User = Depends(get_super_admin)):
    """Update exchange rates - 3 independent rates"""
    update_fields = {"updated_at": datetime.now(timezone.utc), "updated_by": admin.user_id}
    
    if request.ris_to_ves is not None:
        update_fields["ris_to_ves"] = request.ris_to_ves
    
    if request.ves_to_ris_rate is not None:
        update_fields["ves_to_ris_rate"] = request.ves_to_ris_rate
    
    if request.brl_to_ris is not None:
        update_fields["brl_to_ris"] = request.brl_to_ris

    if request.usdtris_to_ves is not None:
        update_fields["usdtris_to_ves"] = request.usdtris_to_ves

    if request.usdcris_to_ves is not None:
        update_fields["usdcris_to_ves"] = request.usdcris_to_ves
    
    if len(update_fields) == 2:  # Only has updated_at and updated_by
        raise HTTPException(status_code=400, detail="Debes proporcionar al menos una tasa")
    
    # Se lee ANTES de escribir: un registro que dice "se cambió la tasa" sin
    # decir de cuánto a cuánto no sirve para investigar nada.
    antes_de_la_tasa = await db.rates.find_one(
        {}, {"_id": 0}, sort=[("updated_at", -1)]) or {}
    antes_de_la_tasa = {k: antes_de_la_tasa.get(k) for k in update_fields}

    await db.rates.update_one(
        {},
        {"$set": update_fields},
        upsert=True
    )
    
    logger.info(f"Rates updated by {admin.user_id}: {update_fields}")

    # Log manual rate changes to rate_history
    try:
        from services.rate_history import log_if_changed
        if request.ris_to_ves is not None:
            await log_if_changed(db, "brl_ves", request.ris_to_ves, "manual", admin_email=admin.email)
        if request.ves_to_ris_rate is not None:
            await log_if_changed(db, "ves_brl", request.ves_to_ris_rate, "manual", admin_email=admin.email)
    except Exception as e:
        logger.warning(f"Rate history log failed: {e}")

    await auditoria.registrar(
        db, "config.tasa", quien=admin, request=peticion,
        objetivo_tipo="tasas", objetivo_id="rates",
        objetivo_desc="Tasas de cambio",
        antes=antes_de_la_tasa, despues=update_fields)

    return {"message": "Tasa actualizada", **update_fields}


@router.get("/rate-history", response_model=HistorialDeTasas, response_model_exclude_unset=True)
async def get_rate_history(
    limit: int = 200,
    route: str = None,
    admin: User = Depends(get_super_admin)
):
    """Get rate change history (super admin only). Filter by route if provided."""
    query = {}
    if route:
        query["route"] = route
    cursor = db.rate_history.find(query, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 1000))
    entries = await cursor.to_list(1000)
    for e in entries:
        ts = e.get("timestamp")
        if ts and hasattr(ts, "isoformat"):
            e["timestamp"] = ts.isoformat()
    return {"entries": entries, "count": len(entries)}


# ============== AUTO RATE CONFIG ==============

# ============== BCV RATES ==============

@router.get("/bcv-rates", response_model=LecturaDelBcv, response_model_exclude_unset=True)
async def get_bcv_rates(admin: User = Depends(get_admin_user)):
    """Get latest BCV snapshot (USD/EUR/CNY/TRY/RUB to VES)."""
    from services.bcv_scraper import get_latest
    latest = await get_latest(db)
    return latest or {"rates": {}, "value_date": None, "fetched_at": None}


@router.get("/bcv-rates/history", response_model=HistorialDelBcv, response_model_exclude_unset=True)
async def get_bcv_rates_history(limit: int = 50, admin: User = Depends(get_admin_user)):
    """Get BCV rate history."""
    from services.bcv_scraper import get_history
    entries = await get_history(db, limit=limit)
    return {"entries": entries, "count": len(entries)}


@router.post("/bcv-rates/refresh", response_model=BcvActualizado, response_model_exclude_unset=True)
async def refresh_bcv_rates(admin: User = Depends(get_admin_user)):
    """Force fetch BCV rates right now.

    PIDE EL MISMO TURNO QUE EL RELOJ DE FONDO

        Son los dos únicos que raspan, y `save_snapshot` mira la última fila y
        DESPUES escribe: si este botón se aprieta justo cuando el reloj de la
        hora está corriendo, los dos leen lo mismo y entran dos filas iguales
        al historial. No hace falta que haya varios procesos para que pase —
        alcanza con el reloj y una persona apretando el botón.

        Si el turno no está libre es porque se está raspando AHORA, o sea que
        el dato que esta persona quiere va a estar en unos segundos.
    """
    from services import turnos
    from services.bcv_scraper import (SEGUNDOS_DEL_TURNO, TURNO,
                                      fetch_bcv_rates, get_latest, save_snapshot)

    if not await turnos.me_toca(db, TURNO, segundos=SEGUNDOS_DEL_TURNO):
        raise HTTPException(
            status_code=409,
            detail="La tasa se está actualizando en este momento. Probá de "
                   "nuevo en unos segundos.")
    try:
        snap = await fetch_bcv_rates()
        saved = await save_snapshot(db, snap)
        latest = await get_latest(db)
        return {"success": True, "saved_new_snapshot": saved, "latest": latest}
    except Exception as e:
        logger.error(f"BCV refresh failed: {e}")
        raise HTTPException(status_code=502, detail=f"No se pudo contactar BCV: {e}")
    finally:
        # Se suelta enseguida: el turno dura dos minutos por si la raspada
        # tarda, pero ésta ya terminó y no hay motivo para hacer esperar al
        # reloj de fondo ni a quien vuelva a apretar el botón.
        await turnos.soltar(db, TURNO)


# `GET` y `POST /admin/auto-rate` vivían acá: la configuración de la «tasa
# automática», el ajuste nocturno de la tasa. Se eliminó entera por decisión del
# dueño del proyecto —ver el comentario en `routes/basic.py`, en `/rate`—. El
# documento `app_settings.auto_rate` puede seguir en la base; ya nadie lo lee.
