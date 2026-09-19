"""
Admin routes - User management, Withdrawals, Rates, KYC
"""
import asyncio
import os
import re
import uuid
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Optional

from database import db
from services import sesiones
from services import registro
from services import cofre
from services import perfil
from services import estado_de_la_cuenta
from services import las_fotos
from services import quien_es
from services.ledger import create_closing_entries
from services.money import ZERO, from_db, para_mostrar, to_float, to_decimal, to_decimal128
from models.user import User
from models.requests import UpdateRateRequest, ChangeRoleRequest, ResetPasswordAdminRequest
from pydantic import BaseModel, Field
from routes.dependencies import (get_admin_user, get_current_user,
                                 get_super_admin, get_crm_user)
from services.notifications import create_notification, ROLES_DEL_PERSONAL
from services import pendientes as pendientes_svc
from services import (auditoria, comprobantes_del_lote,
                      desempeno_del_lector, kyc_quota, lotes_de_pago,
                      registro_del_pago)
from services.email import send_admin_password_reset_email
from services.email_notifications import send_email
from utils.security import generate_temp_password, hash_password_async
from services.imagen_recibida import ImagenInvalida, limpiar_lista

logger = logging.getLogger(__name__)
# ─── El tope de las colas de trabajo ───────────────────────────────────────
#
# Dos bandejas —retiros pendientes y diferencias de pago— traían TODAS las
# filas, sin tope. No las acota el historial sino el trabajo sin procesar, así
# que mientras el equipo esté al día son chicas y nadie lo nota. El día que se
# atrase, la pantalla tarda proporcionalmente y no avisa antes de hacerlo.
#
# Mil es alto a propósito: una bandeja que de verdad tenga mil pendientes ya
# es un problema de operación, y recortarla a cien escondería ese problema
# justo en la pantalla donde hay que verlo.
TOPE_DE_UNA_COLA = 1000


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
    tope = min(limit, 2000)
    filas = await db.transactions.find(
        {"hidden_from_admin": True},
        las_fotos.solo("transaction_id", "display_id", "type", "status",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "currency", "route", "user_id", "created_at"),
    ).sort("created_at", -1).limit(tope).to_list(tope)

    # UNA consulta para los clientes de las 2000 filas, no una por fila.
    quien = await quien_es.de_las_filas(db, filas)

    items = []
    for tx in filas:
        user = quien.ya_conocido(tx.get("user_id"))
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
    # EL UNICO LUGAR DONDE LAS FOTOS TIENEN QUE VIAJAR, porque este trabajo
    # las reescribe. Aun así va con lista de lo permitido: tres campos y no el
    # documento entero. Lo que acota el peso es el tope de mil, que se deja
    # como estaba: es un trabajo que se corre a mano, no una pantalla.
    transactions = await db.transactions.find(
        {"$or": [
            {"proof_images": {"$exists": True, "$ne": []}},
            {"proof_image": {"$exists": True, "$ne": None}},
        ]},
        las_fotos.solo("transaction_id", "proof_image", "proof_images"),
    ).to_list(1000)
    
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


@router.get("/users/{user_id}")
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

@router.get("/users/{user_id}/complete")
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

# ============== WITHDRAWALS ==============

@router.get("/withdrawals/pending")
async def get_pending_withdrawals(admin: User = Depends(get_super_admin)):
    """Get pending withdrawals"""
    # EL TOPE, que no estaba.
    #
    # Esta cola la acota el trabajo sin procesar, no el historial, así que
    # mientras el equipo esté al día son pocas filas. El día que se atrase
    # —o que alguien meta mil pedidos de retiro— la pantalla tarda
    # proporcionalmente y no avisa antes de hacerlo.
    filas = await db.transactions.find(
        {"type": "withdrawal", "status": "pending",
         "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "display_id", "user_id", "status",
                       "amount_input", "amount_output", "currency_input",
                       "beneficiary_data", "payment_type", "client_name",
                       "is_gestor_transaction", "pending_images", "created_at"),
    ).sort("created_at", 1).limit(TOPE_DE_UNA_COLA).to_list(TOPE_DE_UNA_COLA)

    quien = await quien_es.de_las_filas(db, filas)

    withdrawals = []
    for tx in filas:
        user = quien.ya_conocido(tx.get("user_id"))
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
    peticion: Request,
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
        #
        # Todo el trabajo vive en `services/registro_del_pago.py` y no acá,
        # porque ahora hay DOS caminos que asientan un pago: este botón y
        # «Cerrar el lote». Escrito dos veces, la primera corrección en uno no
        # llegaría al otro y lo que se pierde no se nota: el aviso al cliente,
        # o el cupo.
        asentado = await registro_del_pago.registrar(
            db, transaction, quien=admin, banco=bank_id,
            comprobantes=proof_images, request=peticion)
        if not asentado:
            raise HTTPException(
                status_code=409,
                detail="Esa orden ya se procesó desde otro lado. Actualizá la "
                       "pantalla para ver cómo quedó.")

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
            title="Tu retiro fue rechazado",
            message="No pudimos procesarlo. Te devolvimos el saldo a tu cuenta.",
            notification_type="withdrawal_rejected",
            data={"transaction_id": transaction_id},
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
    # `proof_image` SI se pide acá: es la foto que el operador viene a mirar
    # para aprobar la recarga. Lo que no se pide es `proof_images`, que en esta
    # cola no existe —se escribe al completar un retiro— y venía igual.
    filas = await db.transactions.find(
        {"type": "recharge_ves", "status": "pending",
         "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "user_id", "status",
                       "amount_ves", "amount_ris", "rate_used",
                       "destination_bank", "destination_bank_id",
                       "destination_bank_name", "proof_image", "created_at"),
    ).sort("created_at", -1).limit(100).to_list(100)

    quien = await quien_es.de_las_filas(db, filas)

    recharges = []
    for tx in filas:
        user = quien.ya_conocido(tx.get("user_id"))
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
    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    # 1) RIS → VES y RIS → Reais (retiros): el admin paga y sube comprobante.
    #    Se distinguen por currency_output (VES vs BRL).
    # Las que están en un lote salen de la cola: ya las tomó alguien para
    # pagarlas. Se las ve en el panel de lotes abiertos, no acá — si no
    # estuvieran en ningún lado, para el operador habrían desaparecido.
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "pending", "hidden_from_admin": {"$ne": True},
         "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "currency_input", "currency_output", "beneficiary_data",
                       "payment_type", "estado_admin", "assigned_to",
                       "assigned_to_name", "created_at"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
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
                # El CODIGO aparte del nombre. El campo `banco` de arriba se
                # queda con lo primero que encuentre, y en una transferencia eso
                # es el nombre: el código se perdía. Para agrupar pagos por banco
                # y para el formulario de pago móvil hace falta el código.
                "banco_codigo": b.get("bank_code") or "",
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
                "banco_codigo": b.get("bank_code") or "",
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
    async for r in db.btc_remesas.find(
        {"estado": "pagado", "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        {"_id": 0}).sort("pagado_en", 1):
        u = await quien.de(r.get("user_id"))
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
                "banco_codigo": b.get("bank_code") or "",
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
    # `proof_image` SI se pide acá: es la foto que el operador viene a mirar
    # para aprobar la recarga. Lo que no viaja es `proof_images`, que en esta
    # cola no existe —se escribe al completar un retiro— y venía igual.
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "pending", "hidden_from_admin": {"$ne": True},
         "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "currency_input", "currency_output", "payment_type",
                       "estado_admin", "assigned_to", "assigned_to_name",
                       "proof_image", "created_at"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
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

# ============== EL ARCHIVO DE PAGOS DE UN LOTE ==============
#
# Para pagar un grupo de órdenes en bolívares hay que pasar los datos de cada
# beneficiario a la banca en línea. Hoy eso se hace copiando de la pantalla, de
# a un campo por vez: con once órdenes son cuarenta y cuatro copiados, y cada
# uno es una chance de pegar el monto de una fila en la cuenta de otra.
#
# Esta ruta arma ese texto de una sola vez, agrupado por banco y numerado.
# SOLO LEE: no cambia el estado de ninguna orden, no toca plata, no marca nada
# como pagado. Bajar el archivo y pagar son dos cosas distintas, y quien baja
# el archivo todavía no pagó nada.

class ArmarLoteRequest(BaseModel):
    orden_ids: List[str] = Field(..., min_length=1, max_length=lotes_de_pago.MAXIMO)
    # El código de cuatro dígitos del banco desde el que se paga ESTE lote.
    # Es un dato del lote y no una constante: la misma orden va a «mismo banco»
    # o a «otros bancos» según desde dónde se pague ese día.
    banco_pagador: str


@router.post("/lotes")
async def armar_lote(
    cuerpo: ArmarLoteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Arma un lote con estas órdenes y devuelve su archivo.

    Las órdenes salen de la MISMA consulta que alimenta la pantalla, filtradas
    por los identificadores que mandó el operador. Que sea la misma fuente no
    es comodidad: si el lote armara su propia lista, podría incluir una orden
    que en la pantalla ya no está —porque otro operador la tomó hace diez
    segundos— y esa orden se pagaría dos veces.

    Armar un lote NO mueve plata ni marca nada como pagado: reserva las
    órdenes y guarda el papel que se va a pegar en el banco.
    """
    disponibles = (await get_ordenes_pendientes(admin=admin)).get("ordenes", [])
    por_id = {o.get("orden_id"): o for o in disponibles}

    elegidas, ya_no_estan = [], []
    for oid in cuerpo.orden_ids:
        if oid in por_id:
            elegidas.append(por_id[oid])
        else:
            ya_no_estan.append(oid)

    try:
        lote = await lotes_de_pago.armar(
            db, elegidas, banco_pagador=cuerpo.banco_pagador,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))

    # Las que se cayeron entre que la pantalla cargó y el operador pulsó el
    # botón vuelven nombradas. Sacarlas en silencio sería entregar un archivo
    # con menos pagos de los que la persona creyó pedir.
    lote["ya_no_estan"] = ya_no_estan
    return lote


@router.get("/lotes")
async def listar_lotes_abiertos(admin: User = Depends(get_super_admin)):
    """Los lotes que todavía están en la calle, con sus órdenes reservadas."""
    return {"lotes": await lotes_de_pago.abiertos(db)}


# NO CUELGA DE `/lotes/...`, Y ES A PROPOSITO
#
#   El informe es de TODOS los lotes cerrados, no de uno. Colgarlo de
#   `/lotes/algo` lo pondría a competir por el orden de registro con
#   `/lotes/{lote_id}/...`, que es el choque que ya pasó dos veces en este
#   repositorio y que vigila `tests/test_rutas_alcanzables.py`.
@router.get("/lector/desempeno")
async def desempeno_del_lector_de_comprobantes(
        admin: User = Depends(get_super_admin)):
    """Cómo viene adjudicando el lector, sobre los últimos lotes cerrados."""
    return await desempeno_del_lector.medir(db)


@router.get("/lotes/{lote_id}/archivo")
async def archivo_del_lote(lote_id: str, admin: User = Depends(get_super_admin)):
    """El archivo GUARDADO de un lote, para volver a bajarlo idéntico.

    No se vuelve a generar: entre que se bajó y ahora pudo cambiar la tasa o
    corregirse la cuenta de un beneficiario, y entonces el segundo archivo no
    sería el que la persona ya pegó en el banco.
    """
    try:
        return await lotes_de_pago.archivo(db, lote_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


class DevolverOrdenRequest(BaseModel):
    # El motivo se valida en el servicio, donde viven el mínimo y el tope.
    motivo: str


@router.get("/lotes/cerrados")
async def listar_lotes_cerrados(admin: User = Depends(get_super_admin)):
    """Los últimos lotes cerrados. Adentro viven el archivo y las fotos."""
    return {"lotes": await lotes_de_pago.cerrados(db)}


@router.post("/lotes/{lote_id}/cerrar")
async def cerrar_lote(lote_id: str, request: Request,
                      admin: User = Depends(get_super_admin)):
    """Asienta de una vez el pago de todas las órdenes del lote y lo cierra."""
    try:
        return await lotes_de_pago.cerrar(db, lote_id, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/ordenes/{orden_id}/devolver")
async def devolver_orden_del_lote(lote_id: str, orden_id: str,
                                  cuerpo: DevolverOrdenRequest,
                                  request: Request,
                                  admin: User = Depends(get_super_admin)):
    """Saca una orden del lote y la manda de vuelta a la cola de pendientes."""
    try:
        return await lotes_de_pago.devolver_una(
            db, lote_id, orden_id, cuerpo.motivo, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/cancelar")
async def cancelar_lote(lote_id: str, request: Request,
                        admin: User = Depends(get_super_admin)):
    """Deshace un lote: sus órdenes vuelven a la cola de pendientes."""
    try:
        return await lotes_de_pago.cancelar(db, lote_id, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ============== LOS COMPROBANTES DEL LOTE, DE UNA SOLA CARGA ==============
#
# El agente paga las once órdenes en la banca en línea y vuelve con once
# capturas en el teléfono. Antes tenía que abrir orden por orden y buscar cuál
# de las once era la de ésa — y el único dato a mano para distinguirlas era el
# monto, que es justo el que se repite cuando dos personas cobran lo mismo.
#
# Acá se suben todas juntas y el sistema dice de quién es cada una. Lo que no
# puede decir con certeza queda marcado y lo resuelve una persona: ver
# `services/comprobantes_del_lote.py`, que explica por qué el monto nunca
# adjudica y por qué ante la duda no se elige.
#
# Esto NO aprueba ni acredita nada. Colgar la foto y dar la orden por pagada
# son dos decisiones distintas.

class ComprobantesRequest(BaseModel):
    imagenes: List[str] = Field(
        ..., min_length=1, max_length=comprobantes_del_lote.MAXIMO_POR_CARGA)


class AsignarComprobanteRequest(BaseModel):
    # `None` suelta la foto: la saca de la orden que la tenía y la deja sin
    # dueño, para volver a asignarla.
    orden_id: Optional[str] = None


class DescartarComprobanteRequest(BaseModel):
    # El motivo es obligatorio y se valida en el servicio, no acá: el mínimo de
    # letras y el tope viven al lado de la regla que los usa.
    motivo: str


@router.post("/lotes/{lote_id}/comprobantes")
async def cargar_comprobantes_del_lote(
    lote_id: str,
    cuerpo: ComprobantesRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Sube varias fotos de una vez y las reparte entre las órdenes del lote."""
    try:
        return await comprobantes_del_lote.cargar(
            db, lote_id, cuerpo.imagenes, quien=admin, request=request)
    except ImagenInvalida as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/lotes/{lote_id}/comprobantes")
async def ver_comprobantes_del_lote(lote_id: str,
                                    admin: User = Depends(get_super_admin)):
    """La tabla de fotos del lote y las órdenes a las que se pueden asignar."""
    try:
        return await comprobantes_del_lote.listar(db, lote_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/lotes/{lote_id}/comprobantes/{comprobante_id}/imagen")
async def ver_una_foto_del_lote(lote_id: str, comprobante_id: str,
                                admin: User = Depends(get_super_admin)):
    """Una foto concreta. Se pide de a una: once en base64 son decenas de megas."""
    try:
        return {"imagen": await comprobantes_del_lote.imagen(
            db, lote_id, comprobante_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/lotes/{lote_id}/comprobantes/{comprobante_id}/asignar")
async def asignar_comprobante_del_lote(
    lote_id: str, comprobante_id: str,
    cuerpo: AsignarComprobanteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Cambia a mano de qué orden es una foto, o la suelta."""
    try:
        return await comprobantes_del_lote.asignar(
            db, lote_id, comprobante_id, cuerpo.orden_id,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/comprobantes/{comprobante_id}/descartar")
async def descartar_comprobante_del_lote(
    lote_id: str, comprobante_id: str,
    cuerpo: DescartarComprobanteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Saca una foto de la pantalla, con el motivo escrito."""
    try:
        return await comprobantes_del_lote.descartar(
            db, lote_id, comprobante_id, cuerpo.motivo,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/ordenes/bancos-para-pagar")
async def bancos_para_pagar(admin: User = Depends(get_super_admin)):
    """La lista de bancos, para elegir desde cuál se paga el lote."""
    from services import bancos_venezuela
    return {"bancos": [{"codigo": c, "nombre": n}
                       for c, n in sorted(bancos_venezuela.BANCOS.items())]}


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

    # El tope no estaba. Como la cola de retiros, la acota el trabajo sin
    # procesar y no el historial: chica mientras el equipo esté al día, y sin
    # techo el día que no lo esté.
    filas = await db.transactions.find(
        {"status": "underpaid_review", "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "currency_input",
                       "currency_output", "beneficiary_data", "payment_type",
                       "actually_paid", "paid_ratio", "pay_amount", "pay_currency",
                       "network", "topup_actually_paid", "topup_expired",
                       "topup_network", "created_at"),
    ).sort("created_at", 1).limit(TOPE_DE_UNA_COLA).to_list(TOPE_DE_UNA_COLA)

    quien = await quien_es.de_las_filas(db, filas)

    for tx in filas:
        u = quien.ya_conocido(tx.get("user_id"))
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
            title="Tu envío se canceló y te devolvimos el saldo",
            message=(
                f"Tu envío no pudo completarse porque el pago llegó incompleto. "
                # Ocho decimales: es cripto, y redondear a dos le borraría el
                # monto entero a una devolución chica.
                f"Te acreditamos {para_mostrar(acreditado, cur_in, 8)} como saldo disponible."
                if acreditado > 0 else
                "Tu envío no pudo completarse porque el pago llegó incompleto y fue cancelado."
            ),
            data={"transaction_id": claimed.get("transaction_id")},
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

    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    ordenes = []
    total_merma = 0.0
    total_merma_positiva = 0.0
    total_merma_negativa = 0.0
    total_prometido = 0.0

    async for tx in db.transactions.find(
        {**base, "merma_ves": {"$ne": None}},
        las_fotos.solo("transaction_id", "display_id", "user_id", "status",
                       "amount_input", "amount_output", "currency_input", "rate",
                       "merma_ves", "merma_calculada_at", "paid_at", "created_at",
                       "actually_paid", "outcome_amount", "outcome_currency",
                       "paid_ratio", "pay_amount", "pay_currency", "network",
                       "topup_actually_paid", "topup_outcome_amount", "underpaid"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
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

    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    rows = []

    # LA COLUMNA «comprobante» DICE «sí» O «no», Y ESO COSTABA MEGABYTES.
    #
    # Para escribir esas dos letras, este reporte se traía el documento entero
    # de cada fila —con la lista de fotos del comprobante en base64 adentro— y
    # después preguntaba si estaba vacía. Ahora la pregunta la contesta la
    # base y lo que vuelve es un booleano por fila. Es el problema que
    # `services/reportes.py` ya documenta en su encabezado, punto 1.
    filtro_retiros = {"type": "withdrawal", "status": "completed", "completed_at": {"$gte": start, "$lt": end}}
    filtro_recargas = {"type": "recharge_ves", "status": "approved", "processed_at": {"$gte": start, "$lt": end}}
    con_foto = await las_fotos.cuales_tienen_foto(db, filtro_retiros)
    con_foto |= await las_fotos.cuales_tienen_foto(db, filtro_recargas)

    # Retiros completados (RIS→VES y RIS→Reais)
    async for tx in db.transactions.find(
        filtro_retiros,
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "currency_output",
                       "beneficiary_data", "rate", "processed_by", "completed_at"),
    ):
        u = await quien.de(tx.get("user_id"))
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
            "comprobante": "sí" if tx.get("transaction_id") in con_foto else "no",
        })

    # Recargas VES aprobadas (VES→RIS)
    async for tx in db.transactions.find(
        filtro_recargas,
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_ves", "amount_ris", "rate_used",
                       "processed_by", "processed_at"),
    ):
        u = await quien.de(tx.get("user_id"))
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
            "comprobante": "sí" if tx.get("transaction_id") in con_foto else "no",
        })

    # Remesas BTC enviadas (BTC→VES)
    async for r in db.btc_remesas.find(
        {"estado": "enviado", "enviado_en": {"$gte": start, "$lt": end}}, {"_id": 0}
    ):
        u = await quien.de(r.get("user_id"))
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
    filas = await db.transactions.find(
        q, las_fotos.solo("transaction_id", "user_id", "status",
                          "amount_input", "amount_ves", "created_at"),
    ).sort("created_at", 1).limit(20).to_list(20)
    quien = await quien_es.de_las_filas(db, filas)
    for t in filas:
        u = quien.ya_conocido(t.get("user_id"))
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
            title="Tu recarga se acreditó",
            message=f"Acreditamos {para_mostrar(amount_ris, 'RIS')} en tu saldo por tu recarga de {para_mostrar(amount_ves, 'VES')}.",
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
            title="Tu recarga fue rechazada",
            message=f"No pudimos aprobar tu recarga de {para_mostrar(amount_ves, 'VES')}. Motivo: {rejection_reason}",
            notification_type="recharge_rejected",
            data={"transaction_id": transaction_id, "reason": rejection_reason}
        )
        
        message = "Recarga rechazada."
    
    logger.info(f"VES recharge {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}


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
            # `case_ref` de respaldo, y no por prolijidad: las calificaciones
            # que ya están guardadas se escribieron sólo con ese campo, así que
            # sin el respaldo el panel seguiría sin decir de qué caso habla
            # hasta que llegue una calificación nueva. Para un caso `case_ref`
            # es el identificador interno; para un chat viejo es el usuario,
            # que es justo con lo que se abría esa conversación.
            "case_code": r.get("case_code") or r.get("case_ref"),
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


# ============== LOS PENDIENTES DE CADA SECCION ==============
#
# POR QUE NO PASA POR `get_crm_user`
#
#   Los dos guardas con permiso exigen UN permiso por ruta, y esta ruta no
#   tiene uno: es un resumen que cruza nueve secciones con nueve guardianes
#   distintos. Declararla bajo cualquiera de ellos sería mentir sobre lo que
#   protege; inventar un permiso nuevo dejaría sin números a todo el personal
#   que ya existe, hasta que alguien se lo marcara a mano.
#
#   El filtro está adentro y es por sección: `services/pendientes.contar_para`
#   devuelve sólo los contadores de las secciones que ESTE usuario puede abrir.
#   Un cliente no recibe ninguno; un agente recibe los suyos y no se entera de
#   cuántos retiros hay esperando.

@router.get("/pendientes")
async def get_pendientes(current_user: User = Depends(get_current_user)):
    """Cuánto trabajo espera en cada pestaña, para quien pregunta."""
    if current_user.role not in ROLES_DEL_PERSONAL:
        raise HTTPException(status_code=403, detail="CRM access required")

    pendientes, usuarios = await asyncio.gather(
        pendientes_svc.contar_para(current_user),
        pendientes_svc.total_de_usuarios(),
    )
    return {"pendientes": pendientes, "usuarios": usuarios}


# ══════════════════════════════════════════════════════════════════════════
# Verificar el pago en bolívares de un envío a Brasil
# ══════════════════════════════════════════════════════════════════════════
#
# El cliente cotizó, transfirió en bolívares y subió el comprobante. Acá
# alguien lo abre y dice si esa plata entró.
#
# POR QUE NO REUSA `process_ves_recharge`
#
#   Aquélla acredita SALDO y trabaja sobre `type: "recharge_ves"`. Esto no
#   acredita nada: hace avanzar una orden que ya existe hacia la cola de
#   despacho. Meterlas en la misma función obligaría a un `if` que decide si
#   mueve plata o no, en el único lugar donde eso no se puede confundir.

class VerificarPagoEnBolivares(BaseModel):
    action: str                          # "approve" o "reject"
    motivo: Optional[str] = None         # obligatorio al rechazar


@router.post("/envios-reais/{transaction_id}/verificar")
async def verificar_pago_en_bolivares(
    transaction_id: str,
    body: VerificarPagoEnBolivares,
    admin: User = Depends(get_super_admin),
):
    """Confirma o rechaza el comprobante de un envío pagado en bolívares."""
    from services import pago_al_final
    from services.notifications import create_notification

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Acción inválida")

    if body.action == "approve":
        orden = await pago_al_final.verificar_el_pago(
            db, transaction_id, admin.user_id)
        await auditoria.registrar(
            db, "envio_brl.verificado", quien=admin,
            objetivo_tipo="transaction", objetivo_id=transaction_id,
            objetivo_desc=f"Envío {orden.get('display_id')}",
            detalle={"amount_ves": orden.get("amount_input"),
                     "amount_brl": orden.get("amount_output"),
                     "banco": orden.get("destination_bank")})
        await create_notification(
            user_id=orden.get("user_id"),
            title="Confirmamos tu pago",
            message="Tu envío ya está en la cola para despacharse.",
            notification_type="withdrawal_pending",
            data={"transaction_id": transaction_id})
        return {"message": "Pago verificado. La orden pasó a la cola.",
                "status": orden.get("status")}

    # RECHAZAR EXIGE UN MOTIVO ESCRITO.
    #
    #   Sin él, el cliente recibe un «no» sin saber qué corregir y termina en
    #   soporte. Y queda en el libro de auditoría: rechazar el comprobante de
    #   alguien que sí pagó es el error caro de esta pantalla.
    motivo = (body.motivo or "").strip()
    if not motivo:
        raise HTTPException(
            status_code=400,
            detail="Escribí por qué no sirve el comprobante. El cliente lo va a "
                   "leer para mandarte el correcto.")

    orden = await pago_al_final.rechazar_el_comprobante(
        db, transaction_id, admin.user_id, motivo)
    await auditoria.registrar(
        db, "envio_brl.rechazado", quien=admin,
        objetivo_tipo="transaction", objetivo_id=transaction_id,
        objetivo_desc=f"Envío {orden.get('display_id')}",
        detalle={"motivo": motivo})
    await create_notification(
        user_id=orden.get("user_id"),
        title="Necesitamos otro comprobante",
        message=motivo,
        notification_type="warning",
        data={"transaction_id": transaction_id})
    return {"message": "Comprobante rechazado.", "status": orden.get("status")}
