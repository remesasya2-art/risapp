"""
routes/admin/usuarios.py — La lista y la ficha de cada usuario, el rol, la clave, suspender, borrar, la
lista negra y el veto desde la verificación.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from services import sesiones
from services import registro
from services import cofre
from services import perfil
from services import estado_de_la_cuenta
from services import las_fotos
from services.money import money_add, to_float
from models.user import User
from models.acciones_del_panel import (AccionDelPanel, AgenteAsignado, ClaveReiniciada,
                                       CuentaVetada, RolCambiado)
from models.panel_usuarios import DetalleDeUsuario, FichaCompletaDelUsuario, ListaDeUsuariosDelPanel
from models.panel_tablero import (AccionEnLaListaNegra, ListaNegra)
from models.requests import ChangeRoleRequest, ResetPasswordAdminRequest
from pydantic import BaseModel
from routes.dependencies import (get_super_admin, get_crm_user)
from services.notifications import create_notification
from services import auditoria
from services.email import send_admin_password_reset_email
from utils.security import generate_temp_password, hash_password_async
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== USERS ==============

@router.get("/users", response_model=ListaDeUsuariosDelPanel, response_model_exclude_unset=True)
async def get_all_users(admin: User = Depends(get_crm_user)):
    """Get all users"""
    # Lista de lo permitido. Acá había `{"_id": 0, "password_hash": 0}`, o sea
    # el documento entero de CADA usuario: la semilla del segundo factor del
    # jefe y el hash del PIN de cada cliente, todos en una sola respuesta, a
    # quien tuviera el permiso de atención al cliente. El motivo largo está en
    # `services/perfil.py`.
    users = await db.users.find({}, perfil.LO_QUE_VE_EL_PANEL).to_list(1000)

    # EL ESTADO DE CADA CUENTA, Y EL RESUMEN, DECIDIDOS EN UN SOLO LUGAR.
    #
    # Esta ruta devolvía la lista y nada más, así que la pantalla tenía que
    # deducir sola quién estaba vetado — y lo hacía escondiéndolo. El resumen
    # viaja con la lista para que el número de la pantalla y las filas que se
    # ven salgan de la misma consulta y no puedan discrepar.
    vetados = await estado_de_la_cuenta.los_correos_vetados(db)
    for u in users:
        u["estado"] = estado_de_la_cuenta.de(u, vetados)

    # Los saldos a número. ESTA RUTA DEVOLVIA 500 —comprobado corriéndola— para
    # cualquier usuario con el saldo en Decimal128, que son todos desde que la
    # plata se guarda así. O sea que la pestaña «Usuarios» del panel no abría.
    #
    # Es el mismo defecto que tenía la puerta de entrada, y por el mismo motivo:
    # un Decimal128 no se convierte a JSON y nadie lo convirtió. Se recorre por
    # prefijo, no por una lista de nombres, para que el próximo saldo que se
    # invente no repita la historia.
    return {
        "users": [perfil.terminar_de_armar(u) for u in users],
        "resumen": await estado_de_la_cuenta.resumen(db),
    }

@router.get("/users/{user_id}/ficha")
async def descargar_ficha_del_cliente(
    user_id: str,
    peticion: Request,
    admin: User = Depends(get_crm_user),
):
    """La ficha del cliente en PDF, para descargar.

    ANTES ESTO SUBIA EL PDF A GOOGLE DRIVE

        Había un botón que armaba esta misma ficha y la subía a la cuenta de
        Google del administrador que lo apretaba —con un `refresh_token` que
        no vence guardado en la base, y con la primera cuenta que se conectó
        como destino por omisión de todo el equipo—. Los datos de los clientes
        de una app financiera no tienen por qué vivir ahí.

        Ahora el PDF se arma acá, se devuelve como descarga y no se guarda en
        ningún lado. En Railway el disco del contenedor se borra en cada
        despliegue, así que guardarlo sería, además, inútil.

    Y QUEDA ASENTADO QUIEN SE LO LLEVO

        Es lo que más cambia respecto de antes. Subir la ficha a Drive no
        dejaba rastro en ningún lado: no había forma de saber quién se llevó
        los datos de quién, ni cuándo. Acá cada descarga escribe una línea en
        el libro de auditoría, con el actor, el cliente y la IP.

        La línea se escribe ANTES de devolver el archivo. Al revés —asentar
        después de mandarlo— una descarga que se corta a la mitad se lleva los
        datos igual y no queda anotada.
    """
    usuario = await db.users.find_one({"user_id": user_id}, perfil.LO_QUE_VE_EL_PANEL)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await auditoria.registrar(
        db, "kyc.ficha_descargada", quien=admin, request=peticion,
        objetivo_tipo="usuario", objetivo_id=user_id,
        objetivo_desc=usuario.get("full_name") or usuario.get("name") or usuario.get("email"),
    )

    from fastapi.responses import Response as _Respuesta
    from services import ficha_del_cliente

    crudo = ficha_del_cliente.armar(usuario)
    nombre = (usuario.get("full_name") or usuario.get("name") or "cliente").replace(" ", "_")
    documento = usuario.get("cpf_number") or usuario.get("document_number") or "sin_id"
    return _Respuesta(
        content=crudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Ficha_{nombre}_{documento}.pdf"'},
    )


@router.get("/users/{user_id}", response_model=DetalleDeUsuario, response_model_exclude_unset=True)
async def get_user_detail(user_id: str, admin: User = Depends(get_crm_user)):
    """Get user details"""
    user = await db.users.find_one({"user_id": user_id}, perfil.LO_QUE_VE_EL_PANEL)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    perfil.terminar_de_armar(user)
    
    # Get transactions
    transactions = await db.transactions.find(
        {"user_id": user_id, "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "display_id", "type", "status",
                       "amount_input", "amount_output", "created_at"),
    ).sort("created_at", -1).to_list(100)
    
    return {
        "user": user,
        "transactions": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "type": t.get("type"),
                "status": t.get("status"),
                "amount_input": t.get("amount_input"),
                "amount_output": t.get("amount_output"),
                "created_at": t.get("created_at")
            }
            for t in transactions
        ]
    }

@router.get("/users/{user_id}/complete", response_model=FichaCompletaDelUsuario, response_model_exclude_unset=True)
async def get_user_complete_history(user_id: str, admin: User = Depends(get_crm_user)):
    """Get complete user history including profile, KYC, stats, transactions, and beneficiaries"""
    user = await db.users.find_one({"user_id": user_id}, perfil.LO_QUE_VE_EL_PANEL)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    perfil.terminar_de_armar(user)
    
    # Get KYC/verification data
    kyc = await db.verifications.find_one({"user_id": user_id}, {"_id": 0}, sort=[("submitted_at", -1)])
    
    # Merge KYC images into user profile
    if kyc:
        # `abrir_varios` deja en claro lo que esté cifrado y no toca lo demás.
        kyc = cofre.abrir_varios(kyc, cofre.CAMPOS_KYC)
        user["id_document_image"] = kyc.get("id_document_image")
        user["cpf_image"] = kyc.get("cpf_image")
        user["selfie_image"] = kyc.get("selfie_image")
    
    # Get all transactions
    all_transactions = await db.transactions.find(
        {"user_id": user_id, "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "display_id", "type", "status",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "amount_brl", "beneficiary", "created_at", "completed_at"),
    ).sort("created_at", -1).to_list(500)
    
    # Separate recharges and withdrawals
    recharges = [t for t in all_transactions if t.get("type") == "recharge"]
    withdrawals = [t for t in all_transactions if t.get("type") in ["withdrawal", "send"]]
    
    # Los totales, con la suma de la plata del proyecto. Con `sum()` a secas
    # esto daba 500 para cualquier cliente con una operación completada cuyo
    # monto estuviera guardado en Decimal128: `0 + Decimal128` no existe
    # fuera de los tests. Los tests no lo veían porque `mongomock` necesita
    # que se le enseñe aritmética a ese tipo (tests/conftest.py), y esa
    # lección vale para todo el proceso de pruebas.
    completadas = lambda filas: [t for t in filas if t.get("status") == "completed"]    # noqa: E731
    total_recharged = to_float(money_add(*(t.get("amount_ris") or t.get("amount_output") for t in completadas(recharges))))
    total_withdrawn = to_float(money_add(*(t.get("amount_ris") or t.get("amount_input") for t in completadas(withdrawals))))
    total_ves_sent = to_float(money_add(*(t.get("amount_ves") or t.get("amount_output") for t in completadas(withdrawals))))
    
    # Get beneficiaries
    beneficiaries = await db.beneficiaries.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    
    return {
        "profile": user,
        "kyc": kyc,
        "stats": {
            "total_recharged_ris": total_recharged,
            "total_withdrawn_ris": total_withdrawn,
            "total_ves_sent": total_ves_sent,
            "total_transactions": len(all_transactions)
        },
        "recharges": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "status": t.get("status"),
                "amount_ris": t.get("amount_ris") or t.get("amount_output"),
                "amount_brl": t.get("amount_brl") or t.get("amount_input"),
                "created_at": t.get("created_at"),
                "completed_at": t.get("completed_at")
            }
            for t in recharges
        ],
        "withdrawals": [
            {
                "transaction_id": t.get("transaction_id"),
                "display_id": t.get("display_id"),
                "status": t.get("status"),
                "amount_ris": t.get("amount_ris") or t.get("amount_input"),
                "amount_ves": t.get("amount_ves") or t.get("amount_output"),
                "beneficiary": t.get("beneficiary"),
                "created_at": t.get("created_at"),
                "completed_at": t.get("completed_at")
            }
            for t in withdrawals
        ],
        "beneficiaries": beneficiaries
    }

@router.post("/change-role", response_model=RolCambiado, response_model_exclude_unset=True)
async def change_user_role(request: ChangeRoleRequest, admin: User = Depends(get_super_admin)):
    """Change user role"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # A un super administrador sólo lo puede tocar él mismo.
    #
    # Antes esto comparaba contra una dirección de correo escrita en el
    # código: una cuenta concreta protegida por su nombre. Mirar el ROL dice
    # lo mismo sin publicar a nadie, y además cubre a cualquier otro super
    # administrador que exista mañana, que con el correo a mano quedaba
    # desprotegido.
    if user.get("role") == "super_admin" and admin.user_id != request.user_id:
        raise HTTPException(status_code=403, detail="No puedes modificar al administrador principal")
    
    # `socio` y `socio_gestor` ya no existen.
    #
    # Y el código de referido NO se toca acá. Antes, ascender a alguien a socio
    # le asignaba —o le PISABA— su código. Ahora lo recibe todo el mundo al
    # registrarse, una sola vez: pisarlo dejaría huérfano a cada referido que
    # ya hubiera usado el anterior.
    valid_roles = ["user", "agent", "admin", "super_admin"]
    if request.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Rol inválido")

    update_data = {"role": request.new_role}

    await db.users.update_one({"user_id": request.user_id}, {"$set": update_data})
    
    await create_notification(
        user_id=request.user_id,
        title="🎉 Rol Actualizado",
        message=f"Tu rol ha sido actualizado a: {request.new_role}",
        notification_type="role_change"
    )
    
    logger.info(f"User {request.user_id} role changed to {request.new_role} by {admin.user_id}")
    
    return {"message": "Rol actualizado", "new_role": request.new_role}

class SetAgentRequest(BaseModel):
    is_agent: bool

@router.post("/users/{user_id}/set-agent", response_model=AgenteAsignado, response_model_exclude_unset=True)
async def set_user_agent(user_id: str, data: SetAgentRequest, admin: User = Depends(get_super_admin)):
    """Promueve a un usuario a agente de soporte, o le quita el rol (solo super admin)."""
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # La comprobación por correo que estaba acá abajo sobraba: sólo podía
    # dispararse para una cuenta con ese correo que NO fuera super
    # administrador, y la línea de arriba ya frena a los que sí lo son.
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="No se puede cambiar el rol de un super administrador")
    new_role = "agent" if data.is_agent else "user"
    await db.users.update_one({"user_id": user_id}, {"$set": {"role": new_role}})
    logger.info(f"User {user_id} agent role set to {data.is_agent} by {admin.user_id}")
    return {"success": True, "role": new_role}

@router.post("/reset-password", response_model=ClaveReiniciada, response_model_exclude_unset=True)
async def admin_reset_password(request: ResetPasswordAdminRequest, admin: User = Depends(get_super_admin)):
    """Admin reset user password"""
    user = await db.users.find_one({"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    temp_password = generate_temp_password()
    
    await db.users.update_one(
        {"user_id": request.user_id},
        {
            "$set": {
                "password_hash": await hash_password_async(temp_password),
                "password_set": True,
                "must_change_password": True
            }
        }
    )
    
    # Este es el camino que se usa cuando alguien avisa que le tomaron la
    # cuenta. Sin cerrar las sesiones, el reseteo no echaba a nadie y la
    # respuesta «ya está» era una certeza falsa. Se cierran TODAS: el
    # administrador no es el dueño de ninguna de ellas.
    cerradas = await sesiones.cerrar_todas(
        db, request.user_id, motivo=f"reseteo hecho por el admin {admin.user_id}")

    admin_user = await db.users.find_one({"user_id": admin.user_id})
    await send_admin_password_reset_email(user["email"], temp_password, admin_user.get("name", "Admin"))

    logger.info("Contraseña reseteada para %s por el admin %s; %d sesión(es) cerradas",
                user.get("user_id"), admin.user_id, cerradas)

    return {"message": "Contraseña restablecida y email enviado",
            "sesiones_cerradas": cerradas}


@router.post("/users/{user_id}/suspend", response_model=AccionDelPanel, response_model_exclude_unset=True)
async def suspend_user(user_id: str, data: dict, peticion: Request,
                       admin: User = Depends(get_super_admin)):
    """Suspend or reactivate a user"""
    suspend = data.get("suspend", True)
    
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("role") == "super_admin":
        raise HTTPException(status_code=403, detail="No se puede suspender a un super admin")
    
    new_status = "suspended" if suspend else "active"
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    action = "suspendido" if suspend else "reactivado"
    logger.info(f"User {user_id} {action} by admin {admin.user_id}")
    await auditoria.registrar(
        db, "usuario.suspendido" if suspend else "usuario.reactivado",
        quien=admin, request=peticion,
        objetivo_tipo="usuario", objetivo_id=user_id,
        objetivo_desc=user.get("email"),
        antes={"status": user.get("status")}, despues={"status": new_status},
        detalle={"motivo": data.get("motivo") or data.get("reason")})
    return {"message": f"Usuario {action} exitosamente"}


@router.delete("/users/{user_id}", response_model=AccionDelPanel, response_model_exclude_unset=True)
async def delete_user(user_id: str, admin: User = Depends(get_super_admin)):
    """Borrado lógico: conserva el historial para auditoría y libera el correo.

    No elimina transacciones, beneficiarios ni notificaciones (se conservan para auditoría).
    Marca la cuenta como borrada, cierra sus sesiones y libera el correo (lo mueve a
    original_email) para que pueda reutilizarse en un registro nuevo, salvo que el correo
    esté en la lista negra.
    """
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.get("role") == "super_admin":
        raise HTTPException(status_code=403, detail="No se puede eliminar a un super admin")

    now = datetime.now(timezone.utc)
    original_email = user.get("email", "")
    # "Lápida" única para liberar el correo original conservando la cuenta/historial
    tombstone_email = f"deleted+{now.strftime('%Y%m%d%H%M%S')}+{uuid.uuid4().hex[:6]}@deleted.local"

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": now,
            "deleted_by": admin.user_id,
            "original_email": original_email,
            "email": tombstone_email,
            "email_verified": False,
        }}
    )

    # Cerrar sus sesiones activas (el resto del historial se conserva)
    await db.user_sessions.delete_many({"user_id": user_id})

    logger.info("Usuario %s soft-deleted por el admin %s; correo %s liberado",
                user_id, admin.user_id, registro.correo(original_email))
    return {"message": "Usuario eliminado (historial conservado, correo liberado)"}

# ============================================================================
# BLACKLIST (correos / identidades baneadas)
# ============================================================================

ALLOWED_BLACKLIST_TYPES = {"email", "cpf", "document"}

def _normalize_blacklist_value(bl_type: str, value: str) -> str:
    """Normaliza el valor según el tipo para comparaciones consistentes."""
    value = (value or "").strip()
    if bl_type == "email":
        return value.lower()
    if bl_type == "cpf":
        return "".join(c for c in value if c.isdigit())
    if bl_type == "document":
        return "".join(c for c in value if c.isalnum()).upper()
    return value

class BlacklistAddRequest(BaseModel):
    type: str          # "email" | "cpf" | "document"
    value: str
    reason: str = ""

@router.post("/blacklist", response_model=AccionEnLaListaNegra, response_model_exclude_unset=True)
async def add_to_blacklist(data: BlacklistAddRequest, admin: User = Depends(get_crm_user)):
    """Agrega un correo/CPF/documento a la lista negra."""
    bl_type = (data.type or "").lower().strip()
    if bl_type not in ALLOWED_BLACKLIST_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de lista negra inválido")
    norm = _normalize_blacklist_value(bl_type, data.value)
    if not norm:
        raise HTTPException(status_code=400, detail="Valor vacío")
    existing = await db.blacklist.find_one({"type": bl_type, "value": norm})
    if existing:
        return {"success": True, "message": "Ya estaba en la lista negra", "blacklist_id": existing["blacklist_id"]}
    entry = {
        "blacklist_id": f"bl_{uuid.uuid4().hex[:12]}",
        "type": bl_type,
        "value": norm,
        "reason": (data.reason or "").strip(),
        "banned_by": admin.user_id,
        "banned_by_name": getattr(admin, "full_name", None) or admin.email,
        "banned_at": datetime.now(timezone.utc),
    }
    await db.blacklist.insert_one(entry)
    logger.info(f"Blacklist add: {bl_type}={norm} by {admin.user_id}")
    return {"success": True, "message": "Agregado a la lista negra", "blacklist_id": entry["blacklist_id"]}

@router.get("/blacklist", response_model=ListaNegra, response_model_exclude_unset=True)
async def list_blacklist(admin: User = Depends(get_crm_user)):
    """Lista todos los elementos de la lista negra."""
    items = await db.blacklist.find({}, {"_id": 0}).sort("banned_at", -1).to_list(1000)
    return {"items": items, "total": len(items)}

@router.delete("/blacklist/{blacklist_id}", response_model=AccionEnLaListaNegra, response_model_exclude_unset=True)
async def remove_from_blacklist(blacklist_id: str, admin: User = Depends(get_crm_user)):
    """Quita un elemento de la lista negra (des-banear)."""
    result = await db.blacklist.delete_one({"blacklist_id": blacklist_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")
    logger.info(f"Blacklist remove: {blacklist_id} by {admin.user_id}")
    return {"success": True, "message": "Quitado de la lista negra"}

async def _add_bl(bl_type: str, value: str, reason: str, admin: User):
    """Inserta un valor en la lista negra si no existe ya (idempotente)."""
    norm = _normalize_blacklist_value(bl_type, value)
    if not norm:
        return
    if await db.blacklist.find_one({"type": bl_type, "value": norm}):
        return
    await db.blacklist.insert_one({
        "blacklist_id": f"bl_{uuid.uuid4().hex[:12]}",
        "type": bl_type,
        "value": norm,
        "reason": reason,
        "banned_by": admin.user_id,
        "banned_by_name": getattr(admin, "full_name", None) or admin.email,
        "banned_at": datetime.now(timezone.utc),
    })

class BanUserRequest(BaseModel):
    verification_id: str
    scope: str = "full"   # "email" | "full"
    reason: str = ""

@router.post("/ban", response_model=CuentaVetada, response_model_exclude_unset=True)
async def ban_from_verification(data: BanUserRequest, admin: User = Depends(get_crm_user)):
    """Banea a un usuario a partir de su verificación.

    scope="email": solo banea el correo (puede abrir cuenta con otro correo).
    scope="full":  banea correo + CPF + documento (su identidad queda en lista negra).
    En ambos casos se bloquea la cuenta actual y se cierran sus sesiones.
    """
    v = await db.verifications.find_one(
        {"$or": [{"verification_id": data.verification_id}, {"user_id": data.verification_id}]},
        sort=[("submitted_at", -1)],
    )
    if not v:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")
    user_id = v["user_id"]
    user = await db.users.find_one({"user_id": user_id})
    email = (user or {}).get("email", "")
    reason = (data.reason or "").strip()
    scope = (data.scope or "full").lower()

    # Siempre se banea el correo
    if email:
        await _add_bl("email", email, reason, admin)

    # El baneo completo también lista la identidad (CPF + documento)
    if scope == "full":
        if v.get("cpf_number"):
            await _add_bl("cpf", v["cpf_number"], reason, admin)
        if v.get("document_number"):
            await _add_bl("document", v["document_number"], reason, admin)

    # Bloquear la cuenta (impide iniciar sesión) y cerrar sus sesiones
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_banned": True,
            "banned_at": datetime.now(timezone.utc),
            "ban_reason": reason,
            "verification_status": "rejected",
        }}
    )
    await db.user_sessions.delete_many({"user_id": user_id})

    logger.info(f"User {user_id} banned (scope={scope}) by {admin.user_id}")
    return {"success": True, "message": "Usuario baneado", "scope": scope}
