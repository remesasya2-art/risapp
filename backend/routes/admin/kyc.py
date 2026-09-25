"""
routes/admin/kyc.py — Las decisiones sobre la verificación de identidad.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from models.user import User
from models.acciones_del_panel import AccionDelPanel
from routes.dependencies import get_super_admin
from services.notifications import create_notification
from services import auditoria
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== KYC ==============

# ACA VIVIA `GET /verifications/pending`, Y SE FUE
#
#   Devolvía cada usuario con la verificación pendiente con la proyección
#   `{"_id": 0, "password_hash": 0}` —una lista de lo PROHIBIDO de un solo
#   nombre—, o sea el documento entero menos la contraseña: la semilla del
#   segundo factor, el hash del PIN y las credenciales de la huella de cada
#   cliente en plena verificación, y al lado el documento entero de su
#   verificación. Comprobado corriéndola. Es el mismo defecto que tuvo
#   `/users`, en otra puerta.
#
#   Ninguna pantalla la usaba: el panel lee las verificaciones de
#   `/kyc/list` y `/kyc/{id}` (routes/kyc_admin.py), que arman la respuesta
#   campo por campo. Una ruta que nadie mira y que sólo sirve para llevarse
#   lo que no hay que mostrar no se arregla: se saca.


@router.post("/verifications/decide", response_model=AccionDelPanel, response_model_exclude_unset=True)
async def decide_verification(
    request: dict,
    peticion: Request,
    admin: User = Depends(get_super_admin)
):
    """Process KYC verification decision"""
    verification_id = request.get("verification_id")
    approved = request.get("approved", False)
    rejection_reason = request.get("rejection_reason", "")
    
    # Find verification by verification_id or user_id
    verification = await db.verifications.find_one({"verification_id": verification_id})
    if not verification:
        # Try finding by user_id
        verification = await db.verifications.find_one({"user_id": verification_id}, sort=[("submitted_at", -1)])
    
    if not verification:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    
    user_id = verification.get("user_id")
    
    if approved:
        # Update verification status
        await db.verifications.update_one(
            {"verification_id": verification.get("verification_id")},
            {"$set": {"status": "approved", "processed_at": datetime.now(timezone.utc), "processed_by": admin.user_id}}
        )
        
        # Update user
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "verified", "verified_at": datetime.now(timezone.utc)}}
        )
        
        await create_notification(
            user_id=user_id,
            title="✅ Verificación Aprobada",
            message="Tu identidad ha sido verificada exitosamente. Ya puedes usar todas las funciones de RISApp.",
            notification_type="verification_approved"
        )

        # El bono: libera el de esta cuenta y le paga al dueño de su código. Las
        # TRES rutas que aprueban un KYC llaman a esta misma función; si colgara de
        # una sola, a los aprobados por las otras el bono les quedaría bloqueado
        # para siempre y en silencio. Nunca levanta.
        from services import bonos
        await bonos.al_aprobarse_el_kyc(db, user_id)
        
        logger.info(f"Verification approved for {user_id} by {admin.user_id}")
        await auditoria.registrar(
            db, "kyc.aprobado", quien=admin, request=peticion,
            objetivo_tipo="usuario", objetivo_id=user_id,
            objetivo_desc=verification.get("full_name"),
            antes={"verification_status": "pending"},
            despues={"verification_status": "verified"},
            detalle={"verification_id": verification.get("verification_id"),
                     "documento": verification.get("document_number"),
                     "cpf": verification.get("cpf_number")})
        return {"message": "Verificación aprobada"}
    else:
        # Update verification status
        await db.verifications.update_one(
            {"verification_id": verification.get("verification_id")},
            {"$set": {"status": "rejected", "rejection_reason": rejection_reason, "processed_at": datetime.now(timezone.utc), "processed_by": admin.user_id}}
        )
        
        # Update user
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "rejected", "rejection_reason": rejection_reason}}
        )
        
        await create_notification(
            user_id=user_id,
            title="❌ Verificación Rechazada",
            message=f"Tu verificación fue rechazada. Motivo: {rejection_reason}",
            notification_type="verification_rejected"
        )
        
        logger.info(f"Verification rejected for {user_id} by {admin.user_id}: {rejection_reason}")
        await auditoria.registrar(
            db, "kyc.rechazado", quien=admin, request=peticion,
            objetivo_tipo="usuario", objetivo_id=user_id,
            objetivo_desc=verification.get("full_name"),
            antes={"verification_status": "pending"},
            despues={"verification_status": "rejected"},
            detalle={"verification_id": verification.get("verification_id"),
                     "motivo": rejection_reason})
        return {"message": "Verificación rechazada"}


# Keep old endpoint for backward compatibility
@router.post("/verifications/process", response_model=AccionDelPanel, response_model_exclude_unset=True)
async def process_verification(user_id: str, action: str, reason: str = None, admin: User = Depends(get_super_admin)):
    """Process KYC verification (legacy endpoint)"""
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if action == "approve":
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "verified", "verified_at": datetime.now(timezone.utc)}}
        )
        
        await create_notification(
            user_id=user_id,
            title="✅ Verificación Aprobada",
            message="Tu identidad ha sido verificada exitosamente.",
            notification_type="verification_approved"
        )

        # El bono: libera el de esta cuenta y le paga al dueño de su código. Las
        # TRES rutas que aprueban un KYC llaman a esta misma función; si colgara de
        # una sola, a los aprobados por las otras el bono les quedaría bloqueado
        # para siempre y en silencio. Nunca levanta.
        from services import bonos
        await bonos.al_aprobarse_el_kyc(db, user_id)
    elif action == "reject":
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"verification_status": "rejected", "rejection_reason": reason}}
        )
        
        await create_notification(
            user_id=user_id,
            title="❌ Verificación Rechazada",
            message=f"Tu verificación fue rechazada: {reason}",
            notification_type="verification_rejected"
        )
    
    logger.info(f"Verification {action}d for {user_id} by {admin.user_id}")
    
    return {"message": f"Verificación {action}da"}
