"""
routes/admin/mantenimiento.py — El borrado total, las operaciones escondidas y su restauración, el registro
de acciones sensibles y el arreglo de las fotos viejas.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from services import las_fotos
from services import quien_es
from services.ledger import create_closing_entries
from services.money import ZERO, from_db, to_decimal128
from models.user import User
from models.panel_libro import (BorradoTotal, ContabilidadBorrada, OperacionesEscondidas,
                                 OperacionesRestauradas, RegistroDeAccionesSensibles, VistaPreviaDelBorrado)
from models.panel_tablero import FotosConvertidas
from pydantic import BaseModel
from routes.dependencies import get_super_admin
from routes.admin._comun import logger

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


@router.get("/wipe-all/preview", response_model=VistaPreviaDelBorrado, response_model_exclude_unset=True)
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


@router.post("/wipe-all", response_model=BorradoTotal, response_model_exclude_unset=True)
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


@router.post("/accounting/wipe", response_model=ContabilidadBorrada, response_model_exclude_unset=True)
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


@router.get("/hidden-transactions", response_model=OperacionesEscondidas, response_model_exclude_unset=True)
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


@router.post("/restore-transactions", response_model=OperacionesRestauradas, response_model_exclude_unset=True)
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


@router.get("/audit-log", response_model=RegistroDeAccionesSensibles, response_model_exclude_unset=True)
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

@router.post("/fix-media-urls", response_model=FotosConvertidas, response_model_exclude_unset=True)
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
