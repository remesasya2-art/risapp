"""
Admin routes - User management, Withdrawals, Rates, KYC
"""
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional

from database import db
from services import sesiones
from services import registro
from services import cofre
from services.ledger import create_closing_entries
from services.money import ZERO, from_db, to_float, to_decimal, to_decimal128
from models.user import User
from models.requests import UpdateRateRequest, ChangeRoleRequest, ResetPasswordAdminRequest
from pydantic import BaseModel
from routes.dependencies import get_admin_user, get_super_admin, get_crm_user
from services.notifications import create_notification
from services import auditoria, kyc_quota
from services.email import send_admin_password_reset_email
from services.email_notifications import send_email
from utils.security import generate_temp_password, hash_password
from services.imagen_recibida import ImagenInvalida, limpiar_lista

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# ============== MAINTENANCE ==============

# ============== DANGER ZONE: DATA WIPE ==============

# Lo que el borrado total elimina. La lista dejaba afuera SIETE colecciones que
# guardan plata o historia de plata: un «borrado total» que deja pagos con
# tarjeta, depósitos cripto, comisiones de pasarela, remesas BTC y ganancias de
# socios en la base no es un borrado total, es una base a medio limpiar donde
# nadie sabe qué quedó vivo.
#
# `ledger` NO está acá y no va a estar: el libro se CIERRA con asientos (ver
# `services.ledger.create_closing_entries`), no se borra. Un libro contable es
# append-only justamente para que no se pueda borrar.
_ALL_DATA_COLLECTIONS = [
    "transactions",
    "usdt_operations",
    "usdt_ledger",
    "usdt_balance",
    "bank_ledger",
    "bank_accounts",
    "accounting_rates",
    "payment_transactions",
    "admin_payment_records",
    "pending_verifications",
    "gestor_pix_payments",
    "gestor_transactions",
    "notifications",
    "support_messages",
    "counters",
    # Las siete que faltaban.
    "card_payments",
    "crypto_deposits",
    "gateway_fee_ledger",
    "partner_earnings",
    "btc_remesas",
    "btc_ves_wallets",
    "p2p_sales",
]

# Los saldos que el borrado pone en cero. Estaban sólo los dos de RIS: las
# billeteras cripto sobrevivían al «borrado total» con su plata intacta y sin
# ninguna historia detrás.
_SALDOS_A_RESETEAR = ("balance_ris", "balance_ris_terceros",
                      "balance_usdt", "balance_usdc")

_ACCOUNTING_COLLECTIONS = [
    "usdt_operations",
    "usdt_ledger",
    "usdt_balance",
    "bank_ledger",
    "bank_accounts",
    "accounting_rates",
]


class WipeRequest(BaseModel):
    confirmation: str = ""


async def _wipe_collections(collections: list[str]) -> dict:
    """Delete all documents from the given collections. Returns count map."""
    result = {}
    for name in collections:
        try:
            existing = await db.list_collection_names()
            if name in existing:
                res = await db[name].delete_many({})
                if res.deleted_count > 0:
                    result[name] = res.deleted_count
        except Exception as e:
            logger.error(f"Error wiping {name}: {e}")
            result[name] = f"error: {e}"
    return result


async def _hide_from_admin(collection_name: str) -> int:
    """Soft-delete: mark docs as hidden from admin views without deleting them.
    Returns count of docs updated."""
    try:
        res = await db[collection_name].update_many(
            {"hidden_from_admin": {"$ne": True}},
            {"$set": {"hidden_from_admin": True}}
        )
        return res.modified_count
    except Exception as e:
        logger.error(f"Error hiding {collection_name}: {e}")
        return 0


async def _record_audit(admin: User, action: str, deleted: dict, total: int, extra: dict = None):
    """Record a sensitive admin action in the audit_log collection."""
    try:
        await db.audit_log.insert_one({
            "admin_email": admin.email,
            "admin_user_id": admin.user_id,
            "action": action,
            "deleted": deleted,
            "total_deleted": total,
            "extra": extra or {},
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"Error recording audit log: {e}")


@router.get("/wipe-all/preview")
async def wipe_all_preview(admin: User = Depends(get_super_admin)):
    """Qué haría el borrado total, SIN hacer nada.

    Un botón que borra la base entera y sólo se explica con un texto escrito a
    mano en el frontend es un botón que se aprieta sin saber. Acá el que va a
    apretarlo ve los números reales de SU base: cuántos documentos se van, de
    qué colecciones, cuántos saldos se ponen en cero y cuánta plata suman.

    Es de sólo lectura. No borra, no cierra el libro, no toca un saldo.
    """
    existentes = set(await db.list_collection_names())

    a_borrar, total = [], 0
    for nombre in _ALL_DATA_COLLECTIONS:
        if nombre not in existentes:
            continue
        cuantos = await db[nombre].count_documents({})
        if cuantos:
            a_borrar.append({"coleccion": nombre, "documentos": cuantos})
            total += cuantos
    a_borrar.sort(key=lambda c: c["documentos"], reverse=True)

    # Cuánta plata se pone en cero, por cuenta. Es el número que de verdad
    # importa antes de apretar: si no es el que se espera, hay que parar.
    saldos = {campo: ZERO for campo in _SALDOS_A_RESETEAR}
    con_saldo = 0
    proyeccion = {"_id": 0}
    proyeccion.update({campo: 1 for campo in _SALDOS_A_RESETEAR})
    async for u in db.users.find({}, proyeccion):
        tiene = False
        for campo in _SALDOS_A_RESETEAR:
            monto = from_db(u.get(campo), 8 if campo.endswith(("usdt", "usdc")) else 2)
            saldos[campo] += monto
            tiene = tiene or monto != ZERO
        con_saldo += 1 if tiene else 0

    lineas_libro = await db["ledger"].count_documents({})

    return {
        "es_una_simulacion": True,
        "se_borrarian": a_borrar,
        "documentos_a_borrar": total,
        "saldos_que_se_ponen_en_cero": {
            campo: str(monto) for campo, monto in saldos.items()},
        "usuarios_con_saldo": con_saldo,
        "libro": {
            "lineas": lineas_libro,
            "se_borra": False,
            "que_pasa": ("Se cierra con asientos que lo llevan a cero. No se "
                         "borra ni una línea: la historia queda entera y la "
                         "reconciliación cuadra después del borrado."),
        },
        "no_se_toca": [
            "Los usuarios, sus datos y su verificación.",
            "Las tasas y la configuración de la app.",
            "El libro mayor (`ledger`), que se cierra en vez de borrarse.",
        ],
    }


@router.post("/wipe-all")
async def wipe_all_data(
    request: WipeRequest,
    admin: User = Depends(get_super_admin)
):
    """
    DANGER: Wipes ALL transactional data from the database.
    Resets user balances to 0. Preserves users, rates, and app config.
    Requires confirmation='CONFIRMAR' in body.
    """
    if request.confirmation != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Confirmación requerida: envía 'CONFIRMAR'")

    # 1. El libro se cierra ANTES de tocar nada. Va primero a propósito: si el
    #    cierre falla, todavía no se borró ni se puso en cero nada, y el estado
    #    sigue siendo el de antes. Al revés, un fallo dejaría los saldos en cero
    #    con el libro lleno, que es exactamente el descuadre que hay que evitar.
    cierre = await create_closing_entries(
        actor_id=admin.user_id, actor_email=admin.email, motivo="wipe_all")

    # 2. Los saldos, los CUATRO. Antes se ponían en cero sólo los dos de RIS y
    #    las billeteras cripto sobrevivían con su plata.
    balance_reset = await db.users.update_many(
        {}, {"$set": {campo: to_decimal128(0) for campo in _SALDOS_A_RESETEAR}})

    # 3. Y recién ahora se borra.
    deleted = await _wipe_collections(_ALL_DATA_COLLECTIONS)

    # Lo que había acá era código muerto: `_hide_from_admin("transactions")`
    # corría DESPUES de que `_wipe_collections` vaciara esa misma colección, así
    # que marcaba cero documentos. Venía copiado del borrado de contabilidad
    # —donde sí sirve, porque ese no borra las transacciones— y hacía creer que
    # el usuario conservaba su historial. No lo conservaba: se borraba.

    logger.warning(
        f"Super admin {admin.user_id} wiped ALL data: {deleted}; "
        f"cierre del libro: {cierre}")

    total = sum(v for v in deleted.values() if isinstance(v, int))
    await _record_audit(admin, "wipe_all", deleted, total, {
        "users_balance_reset": balance_reset.modified_count,
        "saldos_reseteados": list(_SALDOS_A_RESETEAR),
        "cierre_del_libro": cierre,
    })

    return {
        "success": True,
        "message": "Datos operacionales eliminados completamente",
        "deleted": deleted,
        "total_deleted": total,
        "users_balance_reset": balance_reset.modified_count,
        "cierre_del_libro": cierre,
        "libro_conservado": True,
    }


@router.post("/accounting/wipe")
async def wipe_accounting_data(
    request: WipeRequest,
    admin: User = Depends(get_super_admin)
):
    """
    DANGER: Wipes only accounting data (banks, ledgers, USDT operations, rates).
    Does NOT touch transactions or user balances.
    Requires confirmation='CONFIRMAR' in body.
    """
    if request.confirmation != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Confirmación requerida: envía 'CONFIRMAR'")

    deleted = await _wipe_collections(_ACCOUNTING_COLLECTIONS)

    # Also hide transactions from the accounting report
    hidden_tx = await _hide_from_admin("transactions")

    logger.warning(f"Super admin {admin.user_id} wiped accounting data: {deleted}, hidden transactions: {hidden_tx}")

    total = sum(v for v in deleted.values() if isinstance(v, int)) + hidden_tx
    await _record_audit(admin, "wipe_accounting", deleted, total, {
        "hidden_transactions": hidden_tx,
    })

    return {
        "success": True,
        "message": "Datos de contabilidad eliminados",
        "deleted": deleted,
        "total_deleted": total,
        "hidden_transactions": hidden_tx
    }


@router.get("/hidden-transactions")
async def get_hidden_transactions(
    limit: int = 500,
    admin: User = Depends(get_super_admin)
):
    """List all transactions currently hidden from admin view (for restore UI)."""
    cursor = db.transactions.find(
        {"hidden_from_admin": True},
        {"_id": 0}
    ).sort("created_at", -1).limit(min(limit, 2000))

    items = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")}, {"_id": 0, "name": 1, "email": 1})
        items.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "type": tx.get("type"),
            "status": tx.get("status"),
            "amount_input": tx.get("amount_input") or tx.get("amount_ris", 0),
            "amount_output": tx.get("amount_output") or tx.get("amount_ves", 0),
            "currency": tx.get("currency"),
            "route": tx.get("route"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "created_at": tx.get("created_at").isoformat() if hasattr(tx.get("created_at"), "isoformat") else str(tx.get("created_at")),
        })

    return {"transactions": items, "count": len(items)}


class RestoreRequest(BaseModel):
    transaction_ids: list[str] = []
    restore_all: bool = False


@router.post("/restore-transactions")
async def restore_transactions(
    request: RestoreRequest,
    admin: User = Depends(get_super_admin)
):
    """Restore hidden transactions (set hidden_from_admin=False).
    Either pass transaction_ids=[...] or restore_all=true.
    """
    if request.restore_all:
        res = await db.transactions.update_many(
            {"hidden_from_admin": True},
            {"$set": {"hidden_from_admin": False}}
        )
        restored = res.modified_count
    elif request.transaction_ids:
        res = await db.transactions.update_many(
            {"transaction_id": {"$in": request.transaction_ids}, "hidden_from_admin": True},
            {"$set": {"hidden_from_admin": False}}
        )
        restored = res.modified_count
    else:
        raise HTTPException(status_code=400, detail="Debes pasar transaction_ids o restore_all=true")

    logger.warning(f"Super admin {admin.user_id} restored {restored} transactions (restore_all={request.restore_all})")

    await _record_audit(admin, "restore_transactions", {}, restored, {
        "restore_all": request.restore_all,
        "requested_ids": len(request.transaction_ids),
    })

    return {
        "success": True,
        "message": f"{restored} transacciones restauradas",
        "restored": restored,
    }


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 100,
    admin: User = Depends(get_super_admin)
):
    """Get the last N entries of the audit log (super admin only)."""
    entries = await db.audit_log.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(min(limit, 500)).to_list(500)

    # Serialize datetimes
    for e in entries:
        ts = e.get("timestamp")
        if ts and hasattr(ts, "isoformat"):
            e["timestamp"] = ts.isoformat()

    return {"entries": entries, "count": len(entries)}


# ============== MAINTENANCE ==============

@router.post("/fix-media-urls")
async def fix_media_urls(admin: User = Depends(get_super_admin)):
    """Baja las fotos que están en Twilio y las guarda como base64.

    ESTA RUTA HACIA UN PEDIDO A LA DIRECCION QUE DIJERA LA BASE

        Decidía a dónde ir con `"api.twilio.com" in url`. Eso es una subcadena,
        no un dominio: `https://cualquier-cosa.example/?x=api.twilio.com` la
        pasa. Y con `follow_redirects=True`, ese pedido salía con nuestro
        usuario y contraseña de Twilio adentro.

        El valor venía de `proof_image`, que hasta ahora era texto libre elegido
        por quien subía el comprobante. O sea: el usuario escribía la dirección
        y un super administrador, al correr la migración, mandaba las
        credenciales ahí.

        Ahora la dirección la arma `routes/media.py`, con la forma exacta de un
        medio y contra NUESTRA cuenta, y el salto al CDN se sigue sin
        credenciales. Lo que no calza se deja como está y se anota en `errors`:
        una migración que además borra lo que no entiende es peor que una que no
        corre.
    """
    import base64

    import httpx

    from routes.media import bajar_medio, url_de_medio

    # Find all transactions with non-base64 proof images (Twilio URLs or proxy URLs)
    transactions = await db.transactions.find({
        "$or": [
            {"proof_images": {"$exists": True, "$ne": []}},
            {"proof_image": {"$exists": True, "$ne": None}}
        ]
    }).to_list(1000)
    
    fixed_count = 0
    errors = []
    
    async with httpx.AsyncClient() as client:
        for tx in transactions:
            proof_images = tx.get("proof_images", [])
            proof_image = tx.get("proof_image")
            tx_id = tx.get("transaction_id", "unknown")
            needs_update = False
            update_data = {}
            
            # Handle array of images
            if proof_images:
                new_images = []
                for i, url in enumerate(proof_images):
                    twilio_url = url_de_medio(url)
                    if twilio_url:
                        try:
                            bajado = await bajar_medio(client, twilio_url)
                            if bajado:
                                contenido, tipo = bajado
                                b64 = base64.b64encode(contenido).decode("utf-8")
                                new_images.append(f"data:{tipo};base64,{b64}")
                                needs_update = True
                            else:
                                new_images.append(url)
                                errors.append(f"{tx_id}[{i}]: no se pudo bajar")
                        except Exception as e:
                            new_images.append(url)
                            errors.append(f"{tx_id}[{i}]: {str(e)[:50]}")
                    else:
                        new_images.append(url)
                
                if needs_update:
                    update_data["proof_images"] = new_images
            
            # Handle single proof_image
            twilio_url = url_de_medio(proof_image)
            if twilio_url:
                try:
                    bajado = await bajar_medio(client, twilio_url)
                    if bajado:
                        contenido, tipo = bajado
                        b64 = base64.b64encode(contenido).decode("utf-8")
                        update_data["proof_image"] = f"data:{tipo};base64,{b64}"
                        needs_update = True
                    else:
                        errors.append(f"{tx_id}_single: no se pudo bajar")
                except Exception as e:
                    errors.append(f"{tx_id}_single: {str(e)[:50]}")
            
            if update_data:
                await db.transactions.update_one(
                    {"transaction_id": tx_id},
                    {"$set": update_data}
                )
                fixed_count += 1
    
    logger.info(f"Fixed media URLs in {fixed_count} transactions by {admin.user_id}")
    
    return {
        "message": f"Convertidas {fixed_count} transacciones a base64",
        "transactions_fixed": fixed_count,
        "errors": errors[:10]
    }

# ============== USERS ==============

@router.get("/users")
async def get_all_users(admin: User = Depends(get_crm_user)):
    """Get all users"""
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return {"users": users}

@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: User = Depends(get_crm_user)):
    """Get user details"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Get transactions
    transactions = await db.transactions.find({"user_id": user_id, "hidden_from_admin": {"$ne": True}}).sort("created_at", -1).to_list(100)
    
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

@router.get("/users/{user_id}/complete")
async def get_user_complete_history(user_id: str, admin: User = Depends(get_crm_user)):
    """Get complete user history including profile, KYC, stats, transactions, and beneficiaries"""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
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
    all_transactions = await db.transactions.find({"user_id": user_id, "hidden_from_admin": {"$ne": True}}).sort("created_at", -1).to_list(500)
    
    # Separate recharges and withdrawals
    recharges = [t for t in all_transactions if t.get("type") == "recharge"]
    withdrawals = [t for t in all_transactions if t.get("type") in ["withdrawal", "send"]]
    
    # Calculate stats
    total_recharged = sum(t.get("amount_ris", 0) or t.get("amount_output", 0) for t in recharges if t.get("status") == "completed")
    total_withdrawn = sum(t.get("amount_ris", 0) or t.get("amount_input", 0) for t in withdrawals if t.get("status") == "completed")
    total_ves_sent = sum(t.get("amount_ves", 0) or t.get("amount_output", 0) for t in withdrawals if t.get("status") == "completed")
    
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

@router.post("/change-role")
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
    
    valid_roles = ["user", "socio", "socio_gestor", "super_admin"]
    if request.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Rol inválido")
    
    update_data = {"role": request.new_role}
    
    if request.new_role == "socio":
        update_data["referral_code"] = request.partner_code or f"REF{uuid.uuid4().hex[:8].upper()}"
        update_data["is_partner"] = True
        update_data["became_partner_at"] = datetime.now(timezone.utc)
    elif request.new_role == "socio_gestor":
        update_data["gestor_code"] = request.gestor_code or f"GES{uuid.uuid4().hex[:6].upper()}"
        update_data["balance_ris_terceros"] = to_float(from_db(user.get("balance_ris_terceros", 0)))
        update_data["became_gestor_at"] = datetime.now(timezone.utc)
    
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

@router.post("/users/{user_id}/set-agent")
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

@router.post("/reset-password")
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
                "password_hash": hash_password(temp_password),
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

# ============== WITHDRAWALS ==============

@router.get("/withdrawals/pending")
async def get_pending_withdrawals(admin: User = Depends(get_super_admin)):
    """Get pending withdrawals"""
    cursor = db.transactions.find({
        "type": "withdrawal",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", 1)
    
    withdrawals = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        withdrawals.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "amount_input": tx.get("amount_input", 0),
            "currency_input": tx.get("currency_input") or "RIS",
            "amount_output": tx.get("amount_output", 0),
            "status": tx.get("status"),
            "beneficiary_data": tx.get("beneficiary_data", {}),
            "payment_type": tx.get("payment_type") or tx.get("beneficiary_data", {}).get("payment_type"),
            "is_gestor_transaction": tx.get("is_gestor_transaction", False),
            "client_name": tx.get("client_name"),
            "created_at": tx.get("created_at"),
            "pending_images": tx.get("pending_images", []),
        })
    
    return withdrawals

@router.get("/withdrawals/all")
async def get_all_withdrawals(
    status: str = "pending",
    q: str = "",
    currency: str = "",
    limit: int = 50,
    skip: int = 0,
    admin: User = Depends(get_super_admin),
):
    """La cola de pagos: una página filtrada, ordenada y contada.

    Antes devolvía **los 200 retiros más nuevos de cualquier estado** y la
    pantalla filtraba en el navegador. Pasados los 200, el pendiente MAS VIEJO
    se caía de la lista, y es gente esperando su plata. Ahora el filtro y el
    conteo van en la base, y las pendientes salen FIFO.
    """
    from services import retiros
    try:
        pagina = await retiros.cola(
            db, estado=status, texto=q, moneda=(currency or None),
            limite=limit, saltear=skip)
    except retiros.ColaInvalida as e:
        raise HTTPException(status_code=e.http, detail=e.mensaje)
    except Exception as e:
        logger.error(f"retiros: no se pudo leer la cola: {e}")
        raise HTTPException(
            status_code=503,
            detail="No se pudo leer la cola de retiros. Reintentá en un momento.")
    pagina["counters"] = await retiros.contadores(db)
    return pagina

@router.post("/withdrawals/process")
async def process_withdrawal(
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process a withdrawal (approve/reject)"""
    transaction_id = request.get("transaction_id")
    action = request.get("action")
    proof_images = request.get("proof_images")
    try:
        proof_images = limpiar_lista(proof_images, campo="Los comprobantes")
    except ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))
    bank_id = request.get("bank_id")
    
    force = bool(request.get("force"))

    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")

    if transaction.get("assigned_to") and transaction.get("assigned_to") != admin.user_id and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Esta orden está siendo procesada por {transaction.get('assigned_to_name') or 'otro operador'}",
        )

    if transaction.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Transaccion ya procesada")
    
    if action == "approve":
        # La contabilidad de bancos se lleva en la app externa. Aquí ya NO se
        # descuenta de bancos internos ni se exige seleccionar banco: el admin
        # solo registra el pago y su comprobante. El banco es opcional.
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "processed_by": admin.user_id,
        }
        if bank_id:
            update_data["paid_from_bank"] = bank_id
        if proof_images:
            update_data["proof_images"] = proof_images
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": update_data}
        )

        # Cupo sin KYC: el saldo de un envio se debita al crearlo, asi que aca no
        # hay ningun $inc de saldo donde colgarse y el consumo va en su propia
        # escritura. Si fallara, el pago igual queda hecho.
        try:
            # amount_input es RIS en los envios de reales y de bolivares, pero USDT
            # o USDC en los de cripto, con el mismo type "withdrawal". Sumar eso al
            # contador mezclaria monedas, asi que del envio en cripto se cuenta la
            # operacion y no el monto.
            _kq_moneda = (transaction.get("currency_input") or "RIS").upper()
            _kq_monto = transaction.get("amount_input", 0) if _kq_moneda == "RIS" else 0
            _kq_after = await db.users.find_one_and_update(
                {"user_id": transaction["user_id"]},
                {"$inc": kyc_quota.consume_inc(_kq_monto)},
                return_document=True,
            )
            await kyc_quota.notify_if_exhausted(_kq_after)
        except Exception as _kq_e:
            logger.warning(f"kyc_quota: no se pudo consumir cupo en {transaction_id}: {_kq_e}")

        # Notify user
        await create_notification(
            user_id=transaction["user_id"],
            title="✅ Retiro Completado",
            message=f"Tu retiro de {transaction.get('amount_output', 0):.2f} VES ha sido procesado.",
            notification_type="withdrawal_completed"
        )
        
        # Update gestor transaction if applicable
        if transaction.get("gestor_transaction_id"):
            await db.gestor_transactions.update_one(
                {"transaction_id": transaction["gestor_transaction_id"]},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
            )
        
        message = "Retiro aprobado"
        
    elif action == "reject":
        # Refund balance — a la moneda de ORIGEN del envío (RIS, o USDT/USDC si
        # el saldo debitado fue cripto). Nunca asumir RIS a ciegas.
        _cur_in = str(transaction.get("currency_input") or "RIS").upper()
        _refund_amount = transaction.get("amount_input", 0)

        if _cur_in in ("USDT", "USDC"):
            from services.credits import to_credit_decimal
            from bson.decimal128 import Decimal128
            _refund_field = "balance_usdt" if _cur_in == "USDT" else "balance_usdc"
            _refund_dec = to_credit_decimal(_refund_amount)
            _refunded_user = await db.users.find_one_and_update(
                {"user_id": transaction["user_id"]},
                {"$inc": {_refund_field: Decimal128(_refund_dec)}},
                return_document=True
            )
            try:
                from services.ledger_crypto import record_crypto_entry
                _bal_after = (_refunded_user or {}).get(_refund_field)
                _bal_after = float(to_credit_decimal(_bal_after)) if _bal_after is not None else None
                await record_crypto_entry(
                    user_id=transaction["user_id"],
                    currency=_cur_in.lower(),
                    movement_type="refund_envio",
                    amount=float(_refund_dec),
                    direction="credit",
                    balance_before=(_bal_after - float(_refund_dec)) if _bal_after is not None else None,
                    balance_after=_bal_after,
                    reference_kind="transaction",
                    reference_id=transaction_id,
                    actor_type="admin",
                    actor_id=admin.user_id,
                    metadata={"currency_output": transaction.get("currency_output"), "amount_output": transaction.get("amount_output")},
                    notes="Devolución por envío rechazado",
                )
            except Exception as e:
                logger.warning(f"Ledger cripto refund_envio no registrado: {e}")
        else:
            _refunded_user = await db.users.find_one_and_update(
                {"user_id": transaction["user_id"]},
                {"$inc": {"balance_ris": to_decimal128(to_decimal(_refund_amount))}},
                return_document=True
            )
            # Libro mayor RIS: crédito de devolución (no interrumpe el rechazo)
            try:
                from services.ledger import record_ris_entry
                _bal_after = (_refunded_user or {}).get("balance_ris")
                _bal_after = to_float(from_db(_bal_after)) if _bal_after is not None else None
                await record_ris_entry(
                    user_id=transaction["user_id"],
                    movement_type="refund_envio",
                    amount=_refund_amount,
                    direction="credit",
                    account="balance_ris",
                    balance_before=(_bal_after - _refund_amount) if _bal_after is not None else None,
                    balance_after=_bal_after,
                    reference_kind="transaction",
                    reference_id=transaction_id,
                    transaction_id=transaction_id,
                    display_id=transaction.get("display_id"),
                    actor_type="admin",
                    actor_id=admin.user_id,
                    counterparty=transaction.get("beneficiary_data"),
                    metadata={"currency_output": transaction.get("currency_output"), "amount_output": transaction.get("amount_output")},
                    notes="Devolución por retiro rechazado",
                )
            except Exception as e:
                logger.warning(f"Ledger refund_envio no registrado: {e}")

        # Marca del reembolso con la MISMA forma que el flujo de pago incompleto
        # (rechazar-y-reembolsar-saldo), para que el historial no tenga que saber
        # cual de los dos caminos lo genero.
        _refunded_amount = float(_refund_amount or 0)
        _reject_update = {
            "status": "rejected",
            "completed_at": datetime.now(timezone.utc),
            "processed_by": admin.user_id,
            "refunded_to_balance": _refunded_amount > 0,
            "refunded_to_balance_field": (
                _refund_field if _cur_in in ("USDT", "USDC") else "balance_ris"
            ),
            "refund_amount": _refunded_amount,
        }
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": _reject_update}
        )
        
        await create_notification(
            user_id=transaction["user_id"],
            title="❌ Retiro Rechazado",
            message=f"Tu retiro ha sido rechazado. El saldo ha sido devuelto.",
            notification_type="withdrawal_rejected"
        )
        
        message = "Retiro rechazado y saldo devuelto"
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")
    
    logger.info(f"Withdrawal {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}

# ============== PARTNERS/GESTORS ==============

# ============== VES RECHARGES ADMIN ==============

@router.get("/recharges/ves/pending")
async def get_pending_ves_recharges(admin: User = Depends(get_super_admin)):
    """Get pending VES recharge requests"""
    cursor = db.transactions.find({
        "type": "recharge_ves",
        "status": "pending",
        "hidden_from_admin": {"$ne": True}
    }).sort("created_at", -1).limit(100)
    
    recharges = []
    async for tx in cursor:
        user = await db.users.find_one({"user_id": tx.get("user_id")})
        recharges.append({
            "transaction_id": tx.get("transaction_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_ves": tx.get("amount_ves", 0),
            "amount_ris": tx.get("amount_ris", 0),
            "rate_used": tx.get("rate_used", 0),
            "status": tx.get("status", "pending"),
            "proof_image": tx.get("proof_image"),
            # Esta proyeccion NO los traia, y son justo los que el panel lee
            # para mostrar el banco y decidir si hace falta elegirlo a mano. Es
            # el mismo defecto de clase que el de la creacion: un campo que
            # existe en la base y se pierde en el camino.
            "destination_bank": tx.get("destination_bank"),
            "destination_bank_id": tx.get("destination_bank_id"),
            "destination_bank_name": tx.get("destination_bank_name"),
            "created_at": tx.get("created_at"),
        })

    # El tamaño del problema, para no tener que contarlo a mano. Son las que
    # nacieron rotas: el arreglo de la creacion no las alcanza y las tiene que
    # resolver una persona, una por una, mirando el comprobante.
    faltantes = {"total_pendientes": len(recharges),
                 "sin_banco": sum(1 for r in recharges if not r["destination_bank_id"]),
                 "sin_comprobante": sum(1 for r in recharges if not r["proof_image"])}

    return {"recharges": recharges, "faltantes": faltantes}


class OrdenClaimRequest(BaseModel):
    orden_id: str
    flujo: str  # ris_ves | ris_reais | ves_ris | btc_ves


def _resolver_coleccion_orden(flujo: str, orden_id: str):
    """Ubica la colección y el filtro correcto para una orden del panel unificado,
    según su flujo. Devuelve (None, None) si el flujo no es válido."""
    if flujo in ("ris_ves", "ris_reais", "usdt_ves", "usdc_ves"):
        return db.transactions, {"transaction_id": orden_id, "type": "withdrawal"}
    if flujo == "ves_ris":
        return db.transactions, {"transaction_id": orden_id, "type": "recharge_ves"}
    if flujo == "btc_ves":
        return db.btc_remesas, {"remesa_id": orden_id}
    return None, None


@router.post("/ordenes/tomar")
async def tomar_orden(data: OrdenClaimRequest, admin: User = Depends(get_super_admin)):
    """El operador 'reclama' una orden pendiente para dejar claro que él la está
    procesando y evitar que otro administrador la trabaje en simultáneo."""
    coleccion, query = _resolver_coleccion_orden(data.flujo, data.orden_id)
    if coleccion is None:
        raise HTTPException(status_code=400, detail="Flujo inválido")

    doc = await coleccion.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    admin_name = getattr(admin, "full_name", None) or getattr(admin, "name", None) or admin.email
    assigned_to = doc.get("assigned_to")

    if assigned_to and assigned_to != admin.user_id:
        return {
            "success": False,
            "assigned_to": assigned_to,
            "assigned_to_name": doc.get("assigned_to_name") or "otro operador",
        }

    await coleccion.update_one(query, {"$set": {
        "assigned_to": admin.user_id,
        "assigned_to_name": admin_name,
        "assigned_at": datetime.now(timezone.utc),
        "estado_admin": "en_proceso",
    }})
    return {"success": True, "assigned_to": admin.user_id, "assigned_to_name": admin_name}


@router.post("/ordenes/liberar")
async def liberar_orden(data: OrdenClaimRequest, admin: User = Depends(get_super_admin)):
    """Libera una orden previamente reclamada, para que cualquier operador
    pueda tomarla de nuevo."""
    coleccion, query = _resolver_coleccion_orden(data.flujo, data.orden_id)
    if coleccion is None:
        raise HTTPException(status_code=400, detail="Flujo inválido")

    doc = await coleccion.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    if doc.get("assigned_to") and doc.get("assigned_to") != admin.user_id:
        raise HTTPException(status_code=403, detail="Esta orden está asignada a otro operador")

    await coleccion.update_one(query, {"$set": {
        "assigned_to": None,
        "assigned_to_name": None,
        "assigned_at": None,
        "estado_admin": "pendiente",
    }})
    return {"success": True}


@router.get("/ordenes/pendientes")
async def get_ordenes_pendientes(admin: User = Depends(get_super_admin)):
    """Área unificada de 'Órdenes por procesar'.

    Junta en una sola lista normalizada todas las órdenes pendientes de los
    distintos flujos (RIS→VES, BTC→VES, VES→RIS) para que el super_admin las
    procese desde un solo lugar. NO descuenta bancos internos: la contabilidad
    se lleva en la app externa. La info completa queda disponible aquí.
    """
    ordenes = []
    user_cache = {}

    async def _user(uid):
        if not uid:
            return {}
        if uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        return user_cache[uid]

    # 1) RIS → VES y RIS → Reais (retiros): el admin paga y sube comprobante.
    #    Se distinguen por currency_output (VES vs BRL).
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "pending", "hidden_from_admin": {"$ne": True}}
    ).sort("created_at", 1):
        u = await _user(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        cur_in = str(tx.get("currency_input") or "RIS").upper()
        cur_out = str(tx.get("currency_output") or "VES").upper()
        if cur_in in ("USDT", "USDC"):
            flujo = "usdt_ves" if cur_in == "USDT" else "usdc_ves"
            flujo_label = f"{cur_in}RIS → VES"
            unidad_dest = "VES"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula") or b.get("id_document", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                "telefono": b.get("phone") or b.get("phone_number", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
                "pix_key": "",
            }
        elif cur_out in ("BRL", "REAIS", "REAL"):
            flujo, flujo_label, unidad_dest = "ris_reais", "RIS → Reais", "BRL"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cpf") or b.get("documento", ""),
                "banco": "",
                "telefono": "",
                "cuenta": "",
                "tipo_pago": "pix_br",
                "pix_key": b.get("pix_key", ""),
            }
        else:
            flujo, flujo_label, unidad_dest = "ris_ves", "RIS → VES", "VES"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula") or b.get("id_document", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                "telefono": b.get("phone") or b.get("phone_number", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
                "pix_key": "",
            }
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": flujo,
            "flujo_label": flujo_label,
            "accion": "pagar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_input", 0), "unidad": cur_in},
            "destino": {"valor": tx.get("amount_output", 0), "unidad": unidad_dest},
            "beneficiario": beneficiario,
            "comprobante_usuario": None,
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "estado_admin": tx.get("estado_admin", "pendiente"),
        })

    # 2) BTC → VES (remesas pagadas): el admin paga VES y sube comprobante
    async for r in db.btc_remesas.find({"estado": "pagado"}, {"_id": 0}).sort("pagado_en", 1):
        u = await _user(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        ordenes.append({
            "orden_id": r.get("remesa_id"),
            "flujo": "btc_ves",
            "flujo_label": "BTC → VES",
            "accion": "pagar",
            "display_id": r.get("display_id") or (r.get("remesa_id") or "")[:8],
            "created_at": r.get("pagado_en") or r.get("creado_en"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": r.get("usd_cliente", 0), "unidad": "USD"},
            "destino": {"valor": r.get("ves_recibe", 0), "unidad": "VES"},
            "beneficiario": {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula", ""),
                "banco": b.get("bank", ""),
                "telefono": b.get("phone", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type", ""),
            },
            "comprobante_usuario": None,
            "assigned_to": r.get("assigned_to"),
            "assigned_to_name": r.get("assigned_to_name"),
            "estado_admin": r.get("estado_admin", "pendiente"),
        })

    # 3) VES → RIS (recargas): el admin REVISA el comprobante del usuario y aprueba
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "pending", "hidden_from_admin": {"$ne": True}}
    ).sort("created_at", 1):
        u = await _user(tx.get("user_id"))
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": "ves_ris",
            "flujo_label": "VES → RIS",
            "accion": "aprobar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_ves", 0), "unidad": "VES"},
            "destino": {"valor": tx.get("amount_ris", 0), "unidad": "RIS"},
            "beneficiario": None,
            "comprobante_usuario": tx.get("proof_image"),
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "estado_admin": tx.get("estado_admin", "pendiente"),
        })

    # Más antiguas primero (orden cronológico robusto ante created_at None)
    ordenes.sort(key=lambda o: str(o.get("created_at") or ""))
    return {"ordenes": ordenes, "total": len(ordenes)}

# ============== ENVIOS CRIPTO CON PAGO INCOMPLETO ==============
# Ordenes que llegaron con menos dinero del pedido y que el sistema no pudo
# resolver solo (o el usuario no completo la diferencia a tiempo). Aqui el admin
# decide: aprobar igual, o cancelar devolviendo lo que si llego como saldo.


async def _barrer_topups_vencidos() -> int:
    """Pasa a 'underpaid_review' los awaiting_topup que ya vencieron.

    Se corre aqui (y no solo en el polling del usuario) para no depender de que
    el usuario vuelva a abrir la app: si nunca vuelve, la orden aparece igual en
    la bandeja del admin.
    """
    from routes.transactions import TOPUP_EXPIRY_HOURS

    limite = datetime.now(timezone.utc) - timedelta(hours=TOPUP_EXPIRY_HOURS)
    res = await db.transactions.update_many(
        {"status": "awaiting_topup", "topup_created_at": {"$lte": limite}},
        {"$set": {"status": "underpaid_review", "topup_expired": True}},
    )
    vencidas = getattr(res, "modified_count", 0) or 0
    if vencidas:
        logger.info(f"revision-pago: {vencidas} orden(es) con topup vencido pasaron a revision")
    return vencidas


@router.get("/ordenes/revision-pago")
async def get_ordenes_revision_pago(admin: User = Depends(get_super_admin)):
    """Bandeja de 'Diferencias de pago': envios cripto que quedaron incompletos."""
    vencidas = await _barrer_topups_vencidos()

    ordenes = []
    user_cache = {}

    async for tx in db.transactions.find(
        {"status": "underpaid_review", "hidden_from_admin": {"$ne": True}}
    ).sort("created_at", 1):
        uid = tx.get("user_id")
        if uid and uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        u = user_cache.get(uid, {})
        b = tx.get("beneficiary_data", {}) or {}

        pagado_original = float(tx.get("actually_paid") or 0)
        pagado_topup = float(tx.get("topup_actually_paid") or 0)
        pedido = float(tx.get("pay_amount") or 0)
        recibido = pagado_original + pagado_topup

        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "beneficiario": {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("id_document") or b.get("cedula", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                "telefono": b.get("phone_number") or b.get("phone", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
            },
            "moneda": str(tx.get("currency_input") or "").upper(),
            "red": tx.get("topup_network") or tx.get("network") or tx.get("pay_currency"),
            "pay_amount": pedido,
            "actually_paid": pagado_original,
            "topup_actually_paid": pagado_topup,
            "recibido_total": round(recibido, 8),
            "faltante": round(pedido - recibido, 8) if pedido else 0,
            "paid_ratio": tx.get("paid_ratio"),
            "topup_expired": bool(tx.get("topup_expired")),
            "amount_input": tx.get("amount_input"),
            "amount_output": tx.get("amount_output"),
            "currency_output": tx.get("currency_output"),
        })

    return {"ordenes": ordenes, "total": len(ordenes), "vencidas_ahora": vencidas}


@router.post("/ordenes/{transaction_id}/aprobar-con-diferencia")
async def aprobar_orden_con_diferencia(transaction_id: str, admin: User = Depends(get_super_admin)):
    """Acepta la orden aunque haya llegado menos dinero: pasa a 'pending' y entra
    al mismo pipeline que un pago completo (nivel 1)."""
    from routes.transactions import finalizar_orden_pagada

    ahora = datetime.now(timezone.utc)
    claimed = await db.transactions.find_one_and_update(
        {"transaction_id": transaction_id, "status": "underpaid_review"},
        {"$set": {
            "status": "pending",
            "underpaid": True,
            "approved_manually": True,
            "approved_manually_by": admin.user_id,
            "approved_manually_at": ahora,
            "paid_at": ahora,
        }},
        return_document=True,
    )
    if not claimed:
        existe = await db.transactions.find_one({"transaction_id": transaction_id}, {"status": 1})
        if not existe:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        raise HTTPException(status_code=409, detail=f"La orden ya no está en revisión (estado: {existe.get('status')})")

    await finalizar_orden_pagada(claimed)
    logger.info(f"Orden {transaction_id} aprobada con diferencia por {admin.user_id}")
    return {"message": "Orden aprobada. Pasó a la cola de procesamiento.", "status": "pending"}


@router.post("/ordenes/{transaction_id}/rechazar-y-reembolsar-saldo")
async def rechazar_orden_y_reembolsar_saldo(transaction_id: str, admin: User = Depends(get_super_admin)):
    """Cancela la orden y acredita al usuario, como saldo cripto, todo lo que si
    llego (pago original + diferencia), para que pueda reusarlo o pedir retiro."""
    from services.credits import to_credit_decimal
    from bson.decimal128 import Decimal128

    ahora = datetime.now(timezone.utc)

    # La moneda se valida ANTES de reclamar el estado. Si no es un envio
    # USDT/USDC no hay saldo cripto que devolver, y en ese caso la orden tiene
    # que quedar como estaba (en revision) en vez de terminar cancelada y sin
    # reembolso, que era lo que pasaba cuando este chequeo iba despues del claim.
    previa = await db.transactions.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0, "status": 1, "currency_input": 1},
    )
    if not previa:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if previa.get("status") != "underpaid_review":
        raise HTTPException(status_code=409, detail=f"La orden ya no está en revisión (estado: {previa.get('status')})")

    cur_in = str(previa.get("currency_input") or "").upper()
    if cur_in not in ("USDT", "USDC"):
        logger.error(f"Orden {transaction_id} en revisión con moneda inesperada {cur_in}; no se cancela")
        raise HTTPException(status_code=400, detail="Esta orden no es un envío USDT/USDC; no hay saldo cripto que devolver.")

    # Recien ahora se reclama el estado, y se sigue reclamando de forma atomica:
    # si dos admins tocan el boton a la vez, solo uno pasa y el reembolso no se
    # duplica. El chequeo de arriba no reemplaza al claim, solo evita cancelar
    # ordenes que despues no vamos a poder reembolsar.
    claimed = await db.transactions.find_one_and_update(
        {"transaction_id": transaction_id, "status": "underpaid_review"},
        {"$set": {
            "status": "rejected",
            "completed_at": ahora,
            "processed_by": admin.user_id,
            "rejected_reason": "pago_incompleto",
        }},
        return_document=True,
    )
    if not claimed:
        existe = await db.transactions.find_one({"transaction_id": transaction_id}, {"status": 1})
        if not existe:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        raise HTTPException(status_code=409, detail=f"La orden ya no está en revisión (estado: {existe.get('status')})")

    monto = float(claimed.get("actually_paid") or 0) + float(claimed.get("topup_actually_paid") or 0)
    monto_dec = to_credit_decimal(monto)
    field = "balance_usdt" if cur_in == "USDT" else "balance_usdc"

    acreditado = 0.0
    if monto > 0:
        user_doc = await db.users.find_one_and_update(
            {"user_id": claimed["user_id"]},
            {"$inc": {field: Decimal128(monto_dec)}},
            return_document=True,
        )
        acreditado = float(monto_dec)
        try:
            from services.ledger_crypto import record_crypto_entry
            bal_after = (user_doc or {}).get(field)
            bal_after = float(to_credit_decimal(bal_after)) if bal_after is not None else None
            await record_crypto_entry(
                user_id=claimed["user_id"],
                currency=cur_in.lower(),
                movement_type="reembolso_pago_incompleto",
                amount=acreditado,
                direction="credit",
                balance_before=(bal_after - acreditado) if bal_after is not None else None,
                balance_after=bal_after,
                reference_kind="transaction",
                reference_id=transaction_id,
                actor_type="admin",
                actor_id=admin.user_id,
                actor_email=getattr(admin, "email", None),
                metadata={
                    "display_id": claimed.get("display_id"),
                    "pay_amount": claimed.get("pay_amount"),
                    "actually_paid": claimed.get("actually_paid"),
                    "topup_actually_paid": claimed.get("topup_actually_paid"),
                    "paid_ratio": claimed.get("paid_ratio"),
                },
                notes="Devolución como saldo por envío con pago incompleto",
            )
        except Exception as e:
            logger.warning(f"Ledger cripto reembolso_pago_incompleto no registrado: {e}")

    # `refunded_to_balance` es un booleano y el monto va en `refund_amount`. Antes
    # el monto se guardaba en `refunded_to_balance`; el historial normaliza los
    # documentos viejos, pero de aca en adelante los dos flujos escriben igual.
    await db.transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {
            "refunded_to_balance": acreditado > 0,
            "refunded_to_balance_field": field,
            "refund_amount": acreditado,
        }},
    )

    try:
        await create_notification(
            user_id=claimed["user_id"],
            title="Envío cancelado, saldo devuelto",
            message=(
                f"Tu envío no pudo completarse porque el pago llegó incompleto. "
                f"Te acreditamos {acreditado:.8f} {cur_in} como saldo disponible."
                if acreditado > 0 else
                "Tu envío no pudo completarse porque el pago llegó incompleto y fue cancelado."
            ),
            notification_type="crypto_send_refunded",
        )
    except Exception as e:
        logger.warning(f"No se pudo notificar el reembolso de {transaction_id}: {e}")

    logger.info(f"Orden {transaction_id} rechazada por {admin.user_id}, {acreditado} {cur_in} devueltos a saldo")
    return {
        "message": f"Orden cancelada. Se devolvieron {acreditado:.8f} {cur_in} al saldo del usuario.",
        "status": "rejected",
        "refunded": acreditado,
        "currency": cur_in,
    }


@router.get("/reportes/merma-nowpayments")
async def reporte_merma_nowpayments(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD, inclusivo"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD, inclusivo"),
    admin: User = Depends(get_super_admin),
):
    """Solo lectura: cuanto VES se prometio de mas frente a lo que NOWPayments
    acredito realmente, ya descontada su comision interna de procesamiento.

    `merma_ves` se calcula en el webhook con el `rate` congelado al crear la
    orden, asi que mide la comision de NOWPayments y NO el movimiento de la tasa.
    Este endpoint no modifica nada: es para ver el tamano real del problema antes
    de decidir que hacer con el.

    El rango filtra por `created_at` de la orden (que es como se listan las
    ordenes en el resto del panel). Ambas fechas son opcionales: sin rango,
    devuelve todo el historico.
    """
    from datetime import timedelta as _td

    def _parse(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    rango = {}
    try:
        if date_from:
            rango["$gte"] = _parse(date_from).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to:
            rango["$lt"] = _parse(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (use YYYY-MM-DD)")
    if "$gte" in rango and "$lt" in rango and rango["$lt"] <= rango["$gte"]:
        raise HTTPException(status_code=400, detail="El rango de fechas es inválido (desde debe ser ≤ hasta)")

    base = {"funded_from": "payment"}
    if rango:
        base["created_at"] = rango

    user_cache = {}

    async def _user(uid):
        if not uid:
            return {}
        if uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        return user_cache[uid]

    ordenes = []
    total_merma = 0.0
    total_merma_positiva = 0.0
    total_merma_negativa = 0.0
    total_prometido = 0.0

    async for tx in db.transactions.find({**base, "merma_ves": {"$ne": None}}).sort("created_at", 1):
        u = await _user(tx.get("user_id"))
        merma = to_float(from_db(tx.get("merma_ves"))) or 0.0
        prometido = to_float(from_db(tx.get("amount_output"))) or 0.0

        total_merma += merma
        total_prometido += prometido
        if merma >= 0:
            total_merma_positiva += merma
        else:
            total_merma_negativa += merma

        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "paid_at": tx.get("paid_at"),
            "merma_calculada_at": tx.get("merma_calculada_at"),
            "status": tx.get("status"),
            "user_email": u.get("email", ""),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "moneda": str(tx.get("currency_input") or "").upper(),
            "red": tx.get("network") or tx.get("pay_currency"),
            "rate": to_float(from_db(tx.get("rate"), places=6), places=6),
            "amount_input": to_float(from_db(tx.get("amount_input"))),
            "amount_output": prometido,
            "pay_amount": tx.get("pay_amount"),
            "actually_paid": tx.get("actually_paid"),
            "outcome_amount": tx.get("outcome_amount"),
            "outcome_currency": tx.get("outcome_currency"),
            "topup_actually_paid": tx.get("topup_actually_paid"),
            "topup_outcome_amount": tx.get("topup_outcome_amount"),
            "paid_ratio": tx.get("paid_ratio"),
            "underpaid": bool(tx.get("underpaid")),
            "merma_ves": merma,
        })

    # Ordenes que si recibieron un IPN de pago pero cuyo IPN no trajo
    # outcome_amount: no se puede medir la merma y quedan fuera del total.
    # Se informa el conteo para que el numero de arriba no se lea como completo.
    sin_outcome = await db.transactions.count_documents(
        {**base, "merma_ves": None, "actually_paid": {"$ne": None}}
    )

    return {
        "desde": date_from,
        "hasta": date_to,
        "total": len(ordenes),
        "sin_outcome": sin_outcome,
        "totales": {
            "merma_ves": round(total_merma, 2),
            "merma_ves_a_favor_del_negocio": round(total_merma_negativa, 2),
            "merma_ves_en_contra": round(total_merma_positiva, 2),
            "ves_prometido": round(total_prometido, 2),
            "merma_pct_sobre_prometido": (
                round(total_merma / total_prometido * 100, 4) if total_prometido else None
            ),
        },
        "ordenes": ordenes,
    }


@router.get("/reportes/fuentes")
async def reportes_fuentes(admin: User = Depends(get_super_admin)):
    """Los flujos de dinero sobre los que se puede pedir un reporte.

    La pantalla NO tiene la lista escrita: la pide. Así, agregar una fuente en
    `services/reportes.py` la hace aparecer en el panel sin tocar el frontend —
    y no puede pasar que el panel ofrezca un flujo que el motor no conoce.
    """
    from services import reportes
    return {"fuentes": [{"clave": k, "etiqueta": v["etiqueta"]}
                        for k, v in reportes.FUENTES.items()]}


@router.get("/reportes")
async def generar_reporte(
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
    flujos: Optional[str] = Query(None, description="claves separadas por coma"),
    buscar: Optional[str] = Query(None, max_length=120),
    operador: Optional[str] = Query(None, max_length=120),
    monto_min: Optional[str] = Query(None, max_length=20),
    monto_max: Optional[str] = Query(None, max_length=20),
    tz_min: int = Query(0, ge=-840, le=840, description="minutos respecto de UTC"),
    limite: int = Query(100, ge=1, le=1000),
    saltear: int = Query(0, ge=0),
    formato: str = Query("json", pattern="^(json|csv|xlsx)$"),
    admin: User = Depends(get_super_admin),
):
    """El reporte de operaciones, ajustable.

    `json` devuelve los totales del periodo entero más una página de filas;
    `csv` y `xlsx` devuelven el archivo con TODAS las filas y el mismo bloque de
    totales, para que sumar la columna dé con el encabezado.

    Los totales se calculan siempre sobre el periodo completo, nunca sobre la
    página: un total que solo suma lo que se ve en pantalla es la forma más
    silenciosa de reportar de menos.
    """
    from fastapi.responses import Response, StreamingResponse
    from services import reportes, reportes_export

    criterios = dict(
        desde=desde, hasta=hasta,
        flujos=[f.strip() for f in flujos.split(",") if f.strip()] if flujos else None,
        buscar=buscar, operador=operador,
        monto_min=monto_min, monto_max=monto_max, tz_min=tz_min,
    )
    try:
        if formato == "json":
            return await reportes.generar(limite=limite, saltear=saltear, **criterios)
        reporte = await reportes.reporte_completo(**criterios)
    except reportes.ReporteInvalido as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:
        logger.error(f"reportes: no se pudo generar: {e}")
        raise HTTPException(503, "No se pudo generar el reporte. Reintentá en un momento.")

    quien = getattr(admin, "email", "") or getattr(admin, "user_id", "")
    nombre = reportes_export.nombre_de_archivo(reporte, formato)
    if formato == "csv":
        return StreamingResponse(
            iter([reportes_export.a_csv(reporte, quien)]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
    return Response(
        content=reportes_export.a_xlsx(reporte, quien),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/reportes/procesados")
async def reporte_procesados(
    period: str = Query("day", pattern="^(day|month|year|range)$"),
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    formato: str = Query("json", pattern="^(json|csv)$"),
    admin: User = Depends(get_super_admin),
):
    """Reporte de TODO lo procesado (4 flujos) por día / mes / año o rango.
    Para period="range" usa date_from y date_to (ambos YYYY-MM-DD, inclusivos).
    Devuelve JSON (vista previa + totales) o CSV (descarga para Excel o para la
    app de contabilidad externa). La información completa se genera aquí.
    """
    from datetime import timedelta as _td
    def _parse(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    try:
        if period == "range":
            if not date_from or not date_to:
                raise HTTPException(status_code=400, detail="Indica la fecha desde y hasta (YYYY-MM-DD)")
            start = _parse(date_from).replace(hour=0, minute=0, second=0, microsecond=0)
            end = _parse(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
            if end <= start:
                raise HTTPException(status_code=400, detail="El rango de fechas es inválido (desde debe ser ≤ hasta)")
        else:
            if not date:
                raise HTTPException(status_code=400, detail="Indica la fecha (YYYY-MM-DD)")
            base = _parse(date)
            if period == "day":
                start = base.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + _td(days=1)
            elif period == "month":
                start = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
            else:  # year
                start = base.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (use YYYY-MM-DD)")

    user_cache = {}
    async def _user(uid):
        if not uid:
            return {}
        if uid not in user_cache:
            user_cache[uid] = await db.users.find_one({"user_id": uid}) or {}
        return user_cache[uid]

    rows = []
    # Retiros completados (RIS→VES y RIS→Reais)
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "completed", "completed_at": {"$gte": start, "$lt": end}}
    ):
        u = await _user(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        es_brl = str(tx.get("currency_output") or "VES").upper() in ("BRL", "REAIS", "REAL")
        rows.append({
            "fecha_procesado": tx.get("completed_at"),
            "flujo": "RIS → Reais" if es_brl else "RIS → VES",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cpf") or b.get("cedula") or b.get("id_document", ""),
            "pix": b.get("pix_key", ""),
            "banco": "" if es_brl else (b.get("bank") or b.get("bank_code", "")),
            "monto_origen": tx.get("amount_input", 0),
            "unidad_origen": "RIS",
            "monto_destino": tx.get("amount_output", 0),
            "unidad_destino": "BRL" if es_brl else "VES",
            "tasa": tx.get("rate", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if (tx.get("proof_images") or tx.get("proof_image")) else "no",
        })

    # Recargas VES aprobadas (VES→RIS)
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "approved", "processed_at": {"$gte": start, "$lt": end}}
    ):
        u = await _user(tx.get("user_id"))
        rows.append({
            "fecha_procesado": tx.get("processed_at"),
            "flujo": "VES → RIS",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": "",
            "documento": "",
            "pix": "",
            "banco": "",
            "monto_origen": tx.get("amount_ves", 0),
            "unidad_origen": "VES",
            "monto_destino": tx.get("amount_ris", 0),
            "unidad_destino": "RIS",
            "tasa": tx.get("rate_used", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if tx.get("proof_image") else "no",
        })

    # Remesas BTC enviadas (BTC→VES)
    async for r in db.btc_remesas.find(
        {"estado": "enviado", "enviado_en": {"$gte": start, "$lt": end}}, {"_id": 0}
    ):
        u = await _user(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        rows.append({
            "fecha_procesado": r.get("enviado_en"),
            "flujo": "BTC → VES",
            "referencia": r.get("display_id") or r.get("remesa_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cedula", ""),
            "pix": "",
            "banco": b.get("bank", ""),
            "monto_origen": r.get("usd_cliente", 0),
            "unidad_origen": "USD",
            "monto_destino": r.get("ves_recibe", 0),
            "unidad_destino": "VES",
            "tasa": r.get("tasa_ves", ""),
            "procesado_por": r.get("operador_id", ""),
            "comprobante": "sí" if r.get("comprobante_pago") else "no",
        })

    rows.sort(key=lambda x: str(x.get("fecha_procesado") or ""))

    def fmtfecha(d):
        if not d:
            return ""
        try:
            return d.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(d)

    if formato == "csv":
        import csv as _csv
        import io as _io
        from fastapi.responses import StreamingResponse as _SR
        buf = _io.StringIO()
        buf.write("\ufeff")  # BOM para que Excel respete los acentos
        w = _csv.writer(buf)
        w.writerow(["Fecha", "Flujo", "Referencia", "Usuario", "Email",
                    "Beneficiario", "Documento", "Llave PIX", "Banco",
                    "Monto origen", "Unidad", "Monto destino", "Unidad",
                    "Tasa", "Procesado por", "Comprobante"])
        for r in rows:
            w.writerow([
                fmtfecha(r["fecha_procesado"]), r["flujo"], r["referencia"], r["usuario"], r["usuario_email"],
                r["beneficiario"], r["documento"], r["pix"], r["banco"],
                r["monto_origen"], r["unidad_origen"], r["monto_destino"], r["unidad_destino"],
                r["tasa"], r["procesado_por"], r["comprobante"],
            ])
        buf.seek(0)
        etiqueta = f"{date_from}_a_{date_to}" if period == "range" else (date or "")
        filename = f"reporte_{period}_{etiqueta}.csv"
        return _SR(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                   headers={"Content-Disposition": f"attachment; filename={filename}"})

    # JSON: vista previa + totales por flujo
    totales = {}
    for r in rows:
        totales[r["flujo"]] = totales.get(r["flujo"], 0) + 1
        r["fecha_procesado"] = fmtfecha(r["fecha_procesado"])
    return {
        "period": period,
        "date": date,
        "date_from": date_from,
        "date_to": date_to,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": len(rows),
        "totales_por_flujo": totales,
        "rows": rows,
    }


@router.get("/recharges/ves")
async def get_all_ves_recharges(
    status: str = "pending",
    q: str = "",
    limit: int = 50,
    skip: int = 0,
    admin: User = Depends(get_super_admin),
):
    """La cola de recargas VES: una página filtrada, ordenada y contada.

    Antes devolvía **las 100 más nuevas de cualquier estado** y la pantalla
    filtraba las pendientes en el navegador. Eso escondía dos defectos:

      - con cien recargas viejas y ninguna pendiente, la pantalla quedaba muda
        (ni lista ni cartel de «no hay nada»);
      - con más de cien recargas, la pendiente MAS VIEJA caía fuera del corte y
        desaparecía de la cola. Plata esperando que nadie veía.

    Ahora el filtro y el conteo van en la base, y las pendientes salen FIFO: la
    que más esperó, primero.
    """
    from services import recargas_ves
    try:
        pagina = await recargas_ves.cola(
            db, estado=status, texto=q, limite=limit, saltear=skip)
    except recargas_ves.ColaInvalida as e:
        raise HTTPException(status_code=e.http, detail=e.mensaje)
    except Exception as e:
        logger.error(f"recargas_ves: no se pudo leer la cola: {e}")
        raise HTTPException(
            status_code=503,
            detail="No se pudo leer la cola de recargas. Reintentá en un momento.")
    pagina["counters"] = await recargas_ves.contadores(db)
    return pagina


@router.get("/recharges/ves/check-reference")
async def check_ves_reference(
    digits: str,
    exclude_transaction_id: str = "",
    admin: User = Depends(get_super_admin)
):
    """Avisa si esos 3 digitos de referencia ya aparecen en OTRA recarga VES
    (posible pago duplicado/colusion). Solo informa; no aprueba ni rechaza.
    El criterio: el RIS le corresponde a quien la registro primero."""
    digits = str(digits or "").strip()[:3]
    if len(digits) < 3:
        return {"digits": digits, "has_collision": False, "matches": []}
    current = None
    if exclude_transaction_id:
        current = await db.transactions.find_one(
            {"transaction_id": exclude_transaction_id}, {"user_id": 1}
        )
    current_user_id = (current or {}).get("user_id")
    q = {"type": "recharge_ves", "reference_digits": digits}
    if exclude_transaction_id:
        q["transaction_id"] = {"$ne": exclude_transaction_id}
    matches = []
    cursor = db.transactions.find(q).sort("created_at", 1).limit(20)
    async for t in cursor:
        u = await db.users.find_one(
            {"user_id": t.get("user_id")}, {"email": 1, "full_name": 1, "name": 1}
        ) or {}
        matches.append({
            "transaction_id": t.get("transaction_id"),
            "user_id": t.get("user_id"),
            "user_name": u.get("full_name") or u.get("name"),
            "user_email": u.get("email"),
            "amount_ves": t.get("amount_ves") or t.get("amount_input"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "is_other_user": t.get("user_id") != current_user_id,
        })
    other_user = [m for m in matches if m["is_other_user"]]
    return {
        "digits": digits,
        "has_collision": len(other_user) > 0,
        "matches": matches,
        "first_registered": matches[0] if matches else None,
    }


@router.post("/recharges/ves/process/{transaction_id}")
async def process_ves_recharge(
    transaction_id: str, 
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process a VES recharge (approve/reject).
    The bank to credit is taken automatically from the transaction's
    destination_bank_id (set when the user created the recharge)."""
    action = request.get("action")
    rejection_reason = request.get("rejection_reason", "")
    reference_digits = str(request.get("reference_digits", "") or "").strip()[:3]
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Accion invalida")
    
    recharge = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "type": "recharge_ves"
    })
    
    if not recharge:
        raise HTTPException(status_code=404, detail="Recarga no encontrada")

    force = bool(request.get("force"))
    if recharge.get("assigned_to") and recharge.get("assigned_to") != admin.user_id and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Esta orden está siendo procesada por {recharge.get('assigned_to_name') or 'otro operador'}",
        )

    if recharge.get("status") != "pending":
        return {"message": "Esta recarga ya fue procesada", "already_processed": True}
    
    user_id = recharge.get("user_id")
    amount_ris = recharge.get("amount_ris") or recharge.get("amount_output", 0)
    amount_ves = recharge.get("amount_ves") or recharge.get("amount_input", 0)
    
    # Resolve destination bank from the transaction itself.
    # Backwards compatibility: older transactions may only have `destination_bank` (legacy code).
    bank_id = recharge.get("destination_bank_id")
    if not bank_id and recharge.get("destination_bank"):
        from routes.transactions import resolve_ves_bank
        bank_id, _ = await resolve_ves_bank(recharge.get("destination_bank"))
    # Final fallback: optional override from request body
    #
    # Es la red para las recargas que ya estan cargadas SIN banco: nacieron
    # rotas y el arreglo de la creacion no las alcanza. Las resuelve una
    # persona, mirando el comprobante. Se anota QUIEN y CUANDO porque es una
    # decision manual sobre plata ajena, y dentro de seis meses la unica forma
    # de entender por que esa recarga entro a ese banco es esto.
    banco_elegido_a_mano = False
    if not bank_id:
        bank_id = request.get("bank_id")
        banco_elegido_a_mano = bool(bank_id)
    
    if action == "approve":
        if not bank_id:
            # El mensaje viejo decia "El usuario no eligio un banco valido al
            # crear la recarga". Era FALSO —la pantalla no lo deja avanzar sin
            # elegirlo; lo perdia el servidor— y le llegaba al operador, que se
            # lo repetia al cliente. Que diga lo que pasa y que hacer.
            raise HTTPException(
                status_code=400,
                detail="Esta solicitud no tiene registrado el banco destino. Elegilo "
                       "abajo mirando el comprobante, o pedile al usuario que confirme "
                       "por dónde pagó."
            )
        bank = await db.bank_accounts.find_one({"bank_id": bank_id})
        if not bank:
            raise HTTPException(status_code=404, detail="Banco destino no encontrado en contabilidad")
        
        # Register in bank ledger (VES received from user)
        #
        # Esta línea hacía `bank["balance"] + amount_ves`. Cuando la cuenta ya
        # había pasado por el ajuste manual de contabilidad, su saldo es
        # `Decimal128`, y sumarle un float levanta TypeError: un 500 crudo, sin
        # `try` que lo atrape, en TODA aprobación sobre esa cuenta. Además el
        # saldo posterior salía de una lectura anterior al `$inc`, así que con
        # dos aprobaciones simultáneas las dos anotaban el mismo número.
        from services import bancos
        _mov = await bancos.ajustar(db, bank_id, amount_ves)
        new_balance = to_float(_mov["saldo_nuevo"])
        
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "full_name": 1, "name": 1, "email": 1})
        user_name = user_doc.get("full_name", user_doc.get("name", user_doc.get("email", ""))) if user_doc else ""
        
        await db.bank_ledger.insert_one({
            "bank_id": bank_id, "bank_name": bank["name"],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "type": "entrada",
            "concept": f"Recarga VES de {user_name} (TX {transaction_id[:8]})",
            "amount": amount_ves, "balance_after": new_balance,
            "reference": transaction_id, "notes": "Recarga VES aprobada",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Update recharge status
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {
                "status": "approved",
                "processed_at": datetime.now(timezone.utc),
                "processed_by": admin.user_id,
                "received_in_bank": bank_id,
                "destination_bank_id": bank_id,
                "destination_bank_name": bank["name"],
                "reference_digits": reference_digits,
                **({"banco_elegido_a_mano": True,
                    "banco_elegido_por": admin.user_id,
                    "banco_elegido_at": datetime.now(timezone.utc)}
                   if banco_elegido_a_mano else {}),
            }}
        )
        
        # Add balance to user
        _rch_user = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(amount_ris)), **kyc_quota.consume_inc(amount_ris)}},
            return_document=True
        )
        # Si esta recarga le agoto el cupo sin KYC, avisarle. Nunca interrumpe.
        await kyc_quota.notify_if_exhausted(_rch_user)
        # Libro mayor RIS (no interrumpe la aprobación)
        try:
            from services.ledger import record_ris_entry
            _rch_after = (_rch_user or {}).get("balance_ris")
            _rch_after = to_float(from_db(_rch_after)) if _rch_after is not None else None
            await record_ris_entry(
                user_id=user_id,
                movement_type="recarga_ves",
                amount=amount_ris,
                direction="credit",
                account="balance_ris",
                balance_before=(_rch_after - amount_ris) if _rch_after is not None else None,
                balance_after=_rch_after,
                reference_kind="transaction",
                reference_id=transaction_id,
                transaction_id=transaction_id,
                actor_type="admin",
                actor_id=admin.user_id,
                rate=(amount_ves / amount_ris) if amount_ris else None,
                rate_kind="ves_to_ris",
                amount_output=amount_ves,
                currency_output="VES",
                metadata={"destination_bank_id": bank_id},
                notes="Recarga VES → RIS aprobada",
            )
        except Exception as e:
            logger.warning(f"Ledger recarga_ves no registrado: {e}")
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga VES Aprobada",
            message=f"Tu recarga de {amount_ves:.2f} VES ha sido aprobada. Se han añadido {amount_ris:.2f} RIS a tu saldo.",
            notification_type="recharge_approved",
            data={"transaction_id": transaction_id, "amount_ris": amount_ris}
        )
        
        message = f"Recarga aprobada. Se añadieron {amount_ris:.2f} RIS al usuario."
        
    elif action == "reject":
        if not rejection_reason:
            raise HTTPException(status_code=400, detail="Debes proporcionar un motivo de rechazo")
        
        # Update recharge status
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejection_reason": rejection_reason,
                    "processed_at": datetime.now(timezone.utc),
                    "processed_by": admin.user_id
                }
            }
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga VES Rechazada",
            message=f"Tu recarga de {amount_ves:.2f} VES ha sido rechazada. Motivo: {rejection_reason}",
            notification_type="recharge_rejected",
            data={"transaction_id": transaction_id, "reason": rejection_reason}
        )
        
        message = "Recarga rechazada."
    
    logger.info(f"VES recharge {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}


@router.get("/partners")
async def get_all_partners(admin: User = Depends(get_super_admin)):
    """Get all partners (socios)"""
    partners = await db.users.find({"role": "socio"}).to_list(500)
    
    result = []
    for p in partners:
        # Get referrals count
        referrals_count = await db.users.count_documents({"referred_by": p.get("referral_code")})
        
        # Get earnings
        earnings = await db.partner_earnings.find({"partner_id": p["user_id"]}).to_list(1000)
        total_earnings = sum(e.get("amount", 0) for e in earnings)
        
        # This month
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_earnings = sum(
            e.get("amount", 0) for e in earnings
            if e.get("created_at") and e["created_at"].replace(tzinfo=timezone.utc) >= month_start
        )
        
        result.append({
            "user_id": p["user_id"],
            "name": p.get("name", ""),
            "email": p.get("email", ""),
            "referral_code": p.get("referral_code", ""),
            "referrals_count": referrals_count,
            "total_earnings": round(total_earnings, 2),
            "month_earnings": round(month_earnings, 2),
            "became_partner_at": p.get("became_partner_at"),
            "created_at": p.get("created_at")
        })
    
    return result

@router.get("/gestors")
async def get_all_gestors(admin: User = Depends(get_super_admin)):
    """Get all gestors with stats"""
    gestors = await db.users.find({"role": "socio_gestor"}).to_list(500)
    
    result = []
    for g in gestors:
        # Count transactions
        tx_count = await db.gestor_transactions.count_documents({"gestor_id": g["user_id"]})
        
        # Total volume
        transactions = await db.gestor_transactions.find({"gestor_id": g["user_id"]}).to_list(1000)
        total_volume = sum(t.get("amount_ris", 0) for t in transactions)
        
        result.append({
            "user_id": g["user_id"],
            "name": g.get("name", ""),
            "email": g.get("email", ""),
            "gestor_code": g.get("gestor_code", ""),
            "total_transactions": tx_count,
            "total_volume": round(total_volume, 2),
            "balance_ris": to_float(from_db(g.get("balance_ris", 0))),
            "balance_ris_terceros": to_float(from_db(g.get("balance_ris_terceros", 0))),
            "became_gestor_at": g.get("became_gestor_at"),
            "created_at": g.get("created_at")
        })
    
    return result

# ============== RATES ==============

@router.get("/rates")
async def get_rates(admin: User = Depends(get_super_admin)):
    """Get exchange rates"""
    rate = await db.rates.find_one({}, {"_id": 0}, sort=[("updated_at", -1)])
    return rate or {"ris_to_ves": 92.0, "ves_to_ris": 0.0109}

@router.post("/rates")
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


@router.get("/rate-history")
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

@router.get("/bcv-rates")
async def get_bcv_rates(admin: User = Depends(get_admin_user)):
    """Get latest BCV snapshot (USD/EUR/CNY/TRY/RUB to VES)."""
    from services.bcv_scraper import get_latest
    latest = await get_latest(db)
    return latest or {"rates": {}, "value_date": None, "fetched_at": None}


@router.get("/bcv-rates/history")
async def get_bcv_rates_history(limit: int = 50, admin: User = Depends(get_admin_user)):
    """Get BCV rate history."""
    from services.bcv_scraper import get_history
    entries = await get_history(db, limit=limit)
    return {"entries": entries, "count": len(entries)}


@router.post("/bcv-rates/refresh")
async def refresh_bcv_rates(admin: User = Depends(get_admin_user)):
    """Force fetch BCV rates right now."""
    from services.bcv_scraper import fetch_bcv_rates, save_snapshot, get_latest
    try:
        snap = await fetch_bcv_rates()
        saved = await save_snapshot(db, snap)
        latest = await get_latest(db)
        return {"success": True, "saved_new_snapshot": saved, "latest": latest}
    except Exception as e:
        logger.error(f"BCV refresh failed: {e}")
        raise HTTPException(status_code=502, detail=f"No se pudo contactar BCV: {e}")


class AutoRateConfigRequest(BaseModel):
    enabled: bool | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None
    work_days: list[int] | None = None
    delta_brl_ves: float | None = None
    delta_ves_brl: float | None = None


@router.get("/auto-rate")
async def get_auto_rate_config(admin: User = Depends(get_super_admin)):
    """Get current auto-rate configuration and status."""
    from services.rate_engine import load_auto_rate_config, is_off_hours, caracas_now
    config = await load_auto_rate_config(db)
    now = caracas_now()
    return {
        **config,
        "is_off_hours_now": is_off_hours(config, now),
        "current_caracas_time": now.isoformat(),
    }


@router.post("/auto-rate")
async def update_auto_rate_config(
    request: AutoRateConfigRequest,
    admin: User = Depends(get_super_admin)
):
    """Update auto-rate configuration."""
    update_fields = {}
    for field in ["enabled", "work_start_hour", "work_end_hour", "work_days", "delta_brl_ves", "delta_ves_brl"]:
        val = getattr(request, field)
        if val is not None:
            update_fields[field] = val

    if not update_fields:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un campo")

    update_fields["updated_at"] = datetime.now(timezone.utc)
    update_fields["updated_by"] = admin.user_id

    await db.app_settings.update_one(
        {"setting_id": "auto_rate"},
        {"$set": {"setting_id": "auto_rate", **update_fields}},
        upsert=True
    )

    logger.info(f"Auto-rate config updated by {admin.user_id}: {update_fields}")
    return {"success": True, "message": "Configuración actualizada", **update_fields}

# ============== KYC ==============

@router.get("/verifications/pending")
async def get_pending_verifications(admin: User = Depends(get_super_admin)):
    """Get pending KYC verifications with documents"""
    # Get users with pending verification
    users = await db.users.find(
        {"verification_status": "pending"}, 
        {"_id": 0, "password_hash": 0}
    ).to_list(100)
    
    # Get verification documents for each user
    result = []
    for user in users:
        verification = await db.verifications.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0},
            sort=[("submitted_at", -1)],
        )
        result.append({
            **user,
            "verification": verification
        })
    
    return result


@router.post("/verifications/decide")
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
            message="Tu identidad ha sido verificada exitosamente. Ya puedes usar todas las funciones de RIS App.",
            notification_type="verification_approved"
        )
        
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
@router.post("/verifications/process")
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



# ============== SUPPORT REQUESTS ==============

@router.get("/support-requests")
async def get_support_requests(admin: User = Depends(get_crm_user)):
    """Get all support requests"""
    requests = await db.support_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"requests": requests}

@router.post("/support-requests/{request_id}/resolve")
async def resolve_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Mark a support request as resolved"""
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc),
            "resolved_by": admin.user_id
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    logger.info(f"Support request {request_id} resolved by {admin.user_id}")
    return {"message": "Solicitud marcada como resuelta"}

class SupportReplyRequest(BaseModel):
    message: str

@router.post("/support-requests/{request_id}/reply")
async def reply_support_request(request_id: str, data: SupportReplyRequest, admin: User = Depends(get_crm_user)):
    """Responde una solicitud de soporte por correo (vía Resend) y guarda la respuesta."""
    text = (data.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    to_email = req.get("email")
    if not to_email:
        raise HTTPException(status_code=400, detail="La solicitud no tiene correo de contacto")
    subject_orig = req.get("subject") or "tu solicitud"
    original_msg = req.get("message") or ""
    safe_reply = text.replace("\n", "<br>")
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Respuesta de soporte - RIS App</h2>
        <p>Hola,</p>
        <p>Gracias por contactarnos. En respuesta a tu solicitud <strong>"{subject_orig}"</strong>:</p>
        <div style="background: #f3f4f6; border-left: 4px solid #6366f1; padding: 14px 16px; border-radius: 8px; margin: 16px 0; color: #1f2937;">
            {safe_reply}
        </div>
        <p style="color: #6b7280; font-size: 13px;">Tu mensaje original: "{original_msg}"</p>
        <div style="background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 12px 14px; margin: 18px 0 8px;">
            <p style="color: #92400e; font-size: 13px; margin: 0; line-height: 1.5;">
                <strong>No respondas este correo</strong>, no podemos leer las respuestas por esta via. El equipo de RisApp se pondra en contacto contigo directamente a traves de los numeros de contacto y el correo que nos dejaste.
            </p>
        </div>
    </div>
    """
    email_sent = await send_email(
        to_email=to_email,
        subject=f"Re: {subject_orig} - Soporte RIS App",
        html_content=html_content,
    )
    reply_doc = {
        "message": text,
        "admin_id": admin.user_id,
        "admin_name": getattr(admin, "name", None) or "Soporte",
        "sent_at": datetime.now(timezone.utc),
        "email_sent": bool(email_sent),
    }
    await db.support_requests.update_one(
        {"support_id": request_id},
        {
            "$push": {"replies": reply_doc},
            "$set": {
                "responded_at": datetime.now(timezone.utc),
                "responded_by": admin.user_id,
            },
        },
    )
    if not email_sent:
        return {"success": False, "email_sent": False, "message": "Respuesta guardada, pero el correo no se pudo enviar (revisa la configuracion de Resend)."}
    return {"success": True, "email_sent": True, "message": "Respuesta enviada por correo"}

@router.post("/support-requests/{request_id}/claim")
async def claim_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Toma (claim) una solicitud de soporte de forma ATÓMICA: solo uno puede tomarla."""
    result = await db.support_requests.update_one(
        {"support_id": request_id, "$or": [{"assigned_to": None}, {"assigned_to": {"$exists": False}}, {"assigned_to": ""}]},
        {"$set": {
            "assigned_to": admin.user_id,
            "assigned_to_name": admin.name or "Operador",
            "assigned_at": datetime.now(timezone.utc),
        }}
    )
    if result.modified_count == 1:
        return {"success": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    existing = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1, "assigned_to_name": 1})
    if existing and existing.get("assigned_to") == admin.user_id:
        return {"success": True, "already_mine": True, "assigned_to": admin.user_id, "assigned_to_name": admin.name or "Operador"}
    return {"success": False, "assigned_to": (existing or {}).get("assigned_to"), "assigned_to_name": (existing or {}).get("assigned_to_name")}

@router.post("/support-requests/{request_id}/release")
async def release_support_request(request_id: str, admin: User = Depends(get_crm_user)):
    """Suelta una solicitud. Solo el dueño del caso o un super admin."""
    req = await db.support_requests.find_one({"support_id": request_id}, {"_id": 0, "assigned_to": 1})
    if not req:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if req.get("assigned_to") and req.get("assigned_to") != admin.user_id and admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo quien atiende el caso o un super admin puede liberarlo")
    await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"assigned_to": None, "assigned_to_name": None, "assigned_at": None}}
    )
    return {"success": True}


class SetPriorityRequest(BaseModel):
    priority: str

@router.post("/support-requests/{request_id}/priority")
async def set_support_priority(request_id: str, data: SetPriorityRequest, admin: User = Depends(get_crm_user)):
    """Cambia la prioridad de una solicitud de soporte."""
    valid = ["baja", "normal", "alta", "urgente"]
    if data.priority not in valid:
        raise HTTPException(status_code=400, detail="Prioridad inválida")
    result = await db.support_requests.update_one(
        {"support_id": request_id},
        {"$set": {"priority": data.priority}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {"success": True, "priority": data.priority}

@router.get("/agent-ratings")
async def get_agent_ratings(admin: User = Depends(get_super_admin)):
    """Resumen interno de calificaciones por agente (solo super admin)."""
    ratings = await db.ratings.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    agents = {}
    for r in ratings:
        aid = r.get("agent_id") or "sin_asignar"
        aname = r.get("agent_name") or "Sin asignar"
        if aid not in agents:
            agents[aid] = {"agent_id": aid, "agent_name": aname, "count": 0, "sum_stars": 0, "ratings": []}
        a = agents[aid]
        a["count"] += 1
        a["sum_stars"] += (r.get("stars") or 0)
        a["ratings"].append({
            "stars": r.get("stars"),
            "comment": r.get("comment") or "",
            "channel": r.get("channel"),
            "case_code": r.get("case_code"),
            "created_at": r.get("created_at"),
        })
    result = []
    for a in agents.values():
        avg = round(a["sum_stars"] / a["count"], 2) if a["count"] else 0
        result.append({
            "agent_id": a["agent_id"],
            "agent_name": a["agent_name"],
            "count": a["count"],
            "average": avg,
            "ratings": a["ratings"],
        })
    result.sort(key=lambda x: (-x["average"], -x["count"]))
    return {"agents": result, "total": len(ratings)}



@router.post("/users/{user_id}/suspend")
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


@router.delete("/users/{user_id}")
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

@router.post("/blacklist")
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

@router.get("/blacklist")
async def list_blacklist(admin: User = Depends(get_crm_user)):
    """Lista todos los elementos de la lista negra."""
    items = await db.blacklist.find({}, {"_id": 0}).sort("banned_at", -1).to_list(1000)
    return {"items": items, "total": len(items)}

@router.delete("/blacklist/{blacklist_id}")
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

@router.post("/ban")
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
