# Admin Panel Routes for RISApp
# This module contains all admin-related endpoints for the RIS application

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from openpyxl import Workbook
from io import BytesIO
from motor.motor_asyncio import AsyncIOMotorClient
from services import perfil
from services import las_fotos
from services import quien_es
from services import auditoria
import logging
import os
from services import saldos
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logger = logging.getLogger(__name__)

# Create admin router
admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Available permissions for sub-admins
# El catálogo vive en services/permisos.py, junto a la tabla que dice qué
# permiso pide cada ruta. Tenerlo acá y la tabla allá garantizaba que se
# separaran: se ofrecían permisos que no gobernaban ninguna ruta.
from services.permisos import CATALOGO as ADMIN_PERMISSIONS

# ─── La puerta de entrada ─────────────────────────────────────────────────
#
# ESTE ARCHIVO TENIA SU PROPIA PUERTA, Y LE FALTABAN TRES CONTROLES
#
#     Acá vivían `get_current_user_from_request`, `get_admin_user` y
#     `get_super_admin`: una copia de las dependencias de
#     `routes/dependencies.py`, escrita antes y nunca vuelta a mirar. Las 14
#     rutas de este archivo entraban por esa copia. Las otras 210 rutas de
#     administración entran por las de `routes/dependencies.py`.
#
#     Con el tiempo la copia se quedó atrás en tres cosas, y las tres se
#     comprobaron corriéndolas:
#
#       1. No miraba `is_banned`. Un `super_admin` baneado entraba igual.
#       2. No miraba `is_deleted`. Una cuenta borrada, también.
#       3. No consultaba la tabla de `services/permisos.py`. Un colaborador
#          con CERO permisos tildados pasaba por `PUT /users/{id}/balance`,
#          que mueve dinero. Por la puerta buena, la misma ruta y el mismo
#          usuario dan: «Te falta el permiso "Ajustar saldos a mano (MUEVE
#          DINERO)"».
#
#     Lo peor no es que faltaran: es que la tabla de permisos SI declara esas
#     14 rutas, con su permiso y todo. Estaban escritas para una comprobación
#     que nunca las alcanzaba.
#
# POR QUE SE BORRA LA COPIA EN VEZ DE EMPAREJARLA
#
#     Emparejarla deja dos puertas que hay que acordarse de mantener iguales,
#     que es exactamente lo que falló. Con una sola, una ruta nueva hereda los
#     controles por usar el guard de siempre, y no hay nada que recordar.
#
# POR QUE EL TEST QUE VIGILA ESTO NO LO VIO
#
#     `test_permisos_se_aplican.py` recorre la aplicación armada y exige que
#     toda ruta de administración tenga permiso declarado. Reconocía los
#     guards POR SU NOMBRE, y la copia de acá se llamaba `get_admin_user`
#     igual que la buena. O sea que contaba estas 14 rutas como protegidas
#     mientras no lo estaban. Ahora se reconocen por identidad —el objeto
#     función, no su nombre—, en `test_una_sola_puerta.py`.
from models.user import User as Usuario   # noqa: E402
from models.acciones_del_panel import EstadoCambiado, SaldoAjustado  # noqa: E402
from models.panel_tablero import DetalleDeOperacion, OperacionesDelPanel  # noqa: E402
from models.panel_personal import Administradores, CatalogoDePermisos  # noqa: E402
from models.panel_recargas import (FotoDeLaRecarga, RecargasPendientes, RegistroDePago,  # noqa: E402
                                   RegistrosDePago)
from routes.dependencies import (        # noqa: E402
    get_admin_user,
    get_current_user as get_current_user_from_request,
    get_super_admin,
)


def has_permission(user: dict, permission: str) -> bool:
    """¿Tiene este permiso? Delega en services/permisos.py.

    LO QUE DECIA ANTES, Y POR QUE IMPORTA

        if role == 'admin':
            admin_only = ['admins.create', 'admins.edit']
            return permission not in admin_only

    O sea: a un `admin` se le daba por concedido CUALQUIER permiso menos dos,
    sin mirar su lista. Esa lista es la que Recursos Humanos deja marcar por
    persona. No se consultaba nunca para el rol `admin`, que es justamente el
    rol con el que se da de alta al personal.

    Marcar permisos era decorativo por partida doble: en las 67 rutas que no
    los verificaban, y también acá, donde se verificaban contra un `True`.
    """
    from services.permisos import tiene
    return tiene(user, permission)

async def create_notification(user_id: str, title: str, message: str, notification_type: str, data: dict = None):
    """Helper function to create a notification"""
    notification = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "data": data or {},
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    await db.notifications.insert_one(notification)
    logger.info(f"Notification created for user {user_id}: {title}")

# =======================
# REQUEST/RESPONSE MODELS
# =======================

class ProcessWithdrawalAdminRequest(BaseModel):
    transaction_id: str
    action: str  # "approve" or "reject"
    proof_image: Optional[str] = None
    rejection_reason: Optional[str] = None

class ApproveRechargeRequest(BaseModel):
    transaction_id: str
    approved: bool
    rejection_reason: Optional[str] = None

class AdminSupportResponse(BaseModel):
    user_id: str
    message: str

class CloseSupportRequest(BaseModel):
    user_id: str
    closing_message: Optional[str] = None

class VerificationDecision(BaseModel):
    user_id: str
    approved: bool
    rejection_reason: Optional[str] = None

class UpdateRateRequest(BaseModel):
    ris_to_ves: float
    usd_to_ves: Optional[float] = None

class AdjustBalanceRequest(BaseModel):
    amount: float

# =======================
# DASHBOARD
# =======================

# ─── LAS NUEVE RUTAS MUERTAS QUE VIVIAN ACA ──────────────────────────────
#
# Este archivo repetía nueve handlers que ya existen en `routes/`:
#
#     GET  /admin/dashboard                 -> routes.misc.get_admin_dashboard
#     GET  /admin/users                     -> routes.admin.get_all_users
#     GET  /admin/users/{user_id}           -> routes.admin.get_user_detail
#     GET  /admin/verifications/pending     -> routes.admin (retirado: devolvía documentos enteros)
#     POST /admin/verifications/decide      -> routes.admin.decide_verification
#     GET  /admin/support/chats             -> routes.support (retirado)
#     GET  /admin/support/chat/{user_id}    -> routes.support (retirado)
#     POST /admin/support/respond           -> routes.support (retirado)
#     POST /admin/support/close             -> routes.support (retirado)
#
# Las cuatro de soporte ya no tienen a dónde apuntar: `routes/support.py` se
# borró al quedar el chat viejo sin uso. Se dejan escritas porque lo que este
# bloque documenta es qué había ACA y por qué no servía, no qué existe hoy.
#
# FastAPI resuelve por ORDEN DE REGISTRO, y `routes/` se incluye antes, así
# que las nueve de acá no atendían un solo pedido. Nunca.
#
# No era deuda cosmética. Este archivo es el ÚNICO del proyecto que verifica
# permisos, y NUEVE de sus veinte verificaciones estaban en estas rutas
# muertas: `dashboard.view`, `users.view` (dos veces), `kyc.view`,
# `kyc.approve`, `support.view` (dos veces), `support.respond` y
# `support.close` no se ejecutaban jamás. Quien leyera este archivo iba a
# concluir que el KYC estaba protegido por `kyc.approve`, y no lo estaba: lo
# atendía `routes.admin`, que no mira permisos.
#
# Se borran. Las que quedan en este archivo SÍ atienden.
# ─────────────────────────────────────────────────────────────────────────


# =======================
# PERMISSIONS
# =======================

@admin_router.get("/permissions-list", response_model=CatalogoDePermisos, response_model_exclude_unset=True)
async def get_permissions_list(admin_user: Usuario = Depends(get_admin_user)):
    """Get list of all available permissions"""
    return ADMIN_PERMISSIONS

# =======================
# SUB-ADMIN MANAGEMENT
# =======================

@admin_router.get("/sub-admins", response_model=Administradores, response_model_exclude_unset=True)
async def get_sub_admins(admin_user: Usuario = Depends(get_super_admin)):
    """Get all sub-administrators (super_admin only)"""
    # Lista de lo permitido. Acá había una de lo PROHIBIDO con tres nombres
    # —las fotos del KYC— y por eso devolvía el resto entero: el hash de la
    # contraseña de cada administrador, su semilla del segundo factor y su hash
    # de PIN. Lo ve sólo el super administrador, pero un hash en el cable es un
    # hash en el cable, y las tres fotos ni siquiera viven en `users`: están en
    # `verifications`, así que esa lista tapaba campos que no estaban.
    #
    # El `_id` sale en la proyección, así que ya no hay que convertirlo.
    admins = await db.users.find(
        {"role": {"$in": ["admin", "super_admin"]}},
        perfil.LO_QUE_VE_EL_PANEL
    ).to_list(100)

    # Los saldos a número: un Decimal128 no se convierte a JSON y la ruta
    # devolvería 500, que es lo que le pasaba a la lista de usuarios.
    return [perfil.terminar_de_armar(a) for a in admins]

# ─── ALTA, CAMBIO Y BAJA DE ADMINISTRADORES: SE FUERON A RRHH ────────────
#
# Acá vivían `POST`, `PUT` y `DELETE /admin/sub-admins`. Eran el camino viejo
# que `routes/recursos_humanos.py` dice haber reemplazado, pero seguían
# vivos, y se saltaban las tres reglas del personal (`services/personal.py`).
# Comprobado corriéndolos:
#
#   - El alta con un correo que ya existía PROMOVIA esa cuenta a `admin`: un
#     cliente con 250 de saldo pasaba a ser administrador con su plata
#     adentro. Y con uno que no existía, creaba la cuenta con
#     `verification_status: "verified"` puesto a mano, sin KYC.
#   - Ninguna de las dos marcaba la cuenta como personal (`es_personal`), así
#     que el candado que le impide al personal mover plata —`saldos.mover`—
#     no la frenaba, y la persona no aparecía en la lista de RRHH: un
#     administrador que la pantalla del personal no ve.
#   - Ninguna dejaba una línea en el libro de auditoría. Tampoco el cambio de
#     permisos, ni la baja, que además no cerraba las sesiones abiertas.
#
# Ninguna pantalla las usaba: el panel da de alta, cambia permisos y da de
# baja por RRHH, que hace todo eso bien. Se sacan; la lista de administradores
# (`GET /admin/sub-admins`) se queda, que sólo lee. Un test comprueba que no
# vuelvan (`tests/test_contratos_del_personal.py`).
# ─────────────────────────────────────────────────────────────────────────

# =======================
# USER MANAGEMENT
# =======================



@admin_router.put("/users/{user_id}/balance", response_model=SaldoAjustado, response_model_exclude_unset=True)
async def update_user_balance(user_id: str, request: AdjustBalanceRequest,
                              peticion: Request,
                              admin_user: Usuario = Depends(get_admin_user)):
    """Manually adjust user balance"""
    if not has_permission(admin_user, "users.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Un ajuste a mano es el movimiento que MAS necesita quedar asentado: no
    # tiene una operación detrás que lo explique, sólo la decisión de un
    # administrador. Antes movía el saldo con un `$inc` de un float crudo y no
    # dejaba línea en el mayor; el registro en `admin_logs` de acá abajo no es
    # el libro y la conciliación no lo mira.
    try:
        movido = await saldos.mover(
            db, user_id, request.amount,
            movimiento="ajuste_admin",
            reference_kind="manual",
            reference_id=f"ajuste_{user_id}",
            actor_type="admin",
            actor_id=admin_user.user_id,
            actor_email=admin_user.email,
            notes="Ajuste manual de saldo desde el panel",
        )
    except saldos.UsuarioInexistente:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Log the adjustment
    adjustment = {
        "type": "admin_adjustment",
        "user_id": user_id,
        "amount": request.amount,
        "admin_id": admin_user.user_id,
        "balance_before": float(movido["saldo_anterior"]),
        "balance_after": float(movido["saldo_nuevo"]),
        "ledger_entry_id": movido["entry_id"],
        "created_at": datetime.now(timezone.utc)
    }
    await db.admin_logs.insert_one(adjustment)
    # También al libro único. `admin_logs` se conserva por ahora —hay datos
    # viejos ahí— pero no tenía ningún endpoint que lo leyera: se escribía y
    # moría. Lo que se consulta de acá en adelante es el libro.
    await auditoria.registrar(
        db, "dinero.ajuste_manual", quien=admin_user, request=peticion,
        objetivo_tipo="usuario", objetivo_id=user_id,
        antes={"saldo": float(movido["saldo_anterior"])},
        despues={"saldo": float(movido["saldo_nuevo"])},
        detalle={"monto": request.amount,
                 "entrada_de_libro": movido["entry_id"]})
    
    return {"message": f"Balance ajustado en {request.amount} RIS",
            "balance_after": float(movido["saldo_nuevo"])}

# =======================
# KYC/VERIFICATION MANAGEMENT
# =======================



# =======================
# WITHDRAWALS MANAGEMENT
# =======================

# ─── Retiros: las rutas vivían acá y estaban MUERTAS ──────────────────────
#
# `admin_routes.py` registraba `GET /api/admin/withdrawals/pending` y
# `POST /api/admin/withdrawals/process`, que `routes/admin/retiros.py` ya registra con
# los mismos caminos. `server.py` monta primero el router modular, así que
# FastAPI resolvía siempre contra `routes/admin/retiros.py` y estas dos nunca corrían.
#
# No era código inofensivo. La versión muerta de `process`:
#
#   - acreditaba la devolución con `{"$inc": {"balance_ris": tx['amount_input']}}`
#     —un float crudo, sin `to_decimal128`— cuando el resto de la app usa
#     Decimal;
#   - no dejaba línea en el diario RIS;
#   - devolvía SIEMPRE a `balance_ris`, sin mirar `currency_input`, así que un
#     envío pagado en USDT o USDC volvía en RIS;
#   - no respetaba el candado por operador ni el cupo sin KYC.
#
# Bastaba con que alguien cambiara el orden de los `include_router` en
# `server.py` para que esa versión pasara a atender los retiros, en silencio.
# Se eliminaron: la buena vive en `routes/admin/retiros.py`.

# =======================
# RECHARGES MANAGEMENT
# =======================

@admin_router.get("/recharges/pending", response_model=RecargasPendientes, response_model_exclude_unset=True)
async def get_pending_recharges(admin_user: Usuario = Depends(get_admin_user)):
    """Get all recharges pending review"""
    if not has_permission(admin_user, "recharges.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    recharges = await db.transactions.find(
        {
            "type": {"$in": ["recharge", "recharge_ves"]},
            "status": {"$in": ["pending", "pending_review"]}
        },
        # Lista de lo prohibido, y se tolera sólo porque el test obliga a que
        # las nombre a TODAS. Acá el documento se le pasa entero a la pantalla.
        las_fotos.sin_las_fotos()
    ).sort("created_at", -1).to_list(1000)
    
    # UNA consulta para los clientes de las mil filas, no una por fila.
    # Y con proyección: antes esto pedía el usuario entero —hash de la
    # contraseña incluido— para leerle el nombre.
    quien = await quien_es.de_las_filas(db, recharges)

    result = []
    for r in recharges:
        user = quien.ya_conocido(r.get("user_id"))
        r['_id'] = str(r['_id'])
        r['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        r['user_email'] = user.get('email', 'N/A') if user else 'N/A'
        result.append(r)
    
    return {"recharges": result}

@admin_router.get("/recharges/{transaction_id}/proof", response_model=FotoDeLaRecarga, response_model_exclude_unset=True)
async def get_recharge_proof(transaction_id: str, admin_user: Usuario = Depends(get_admin_user)):
    """Get proof image for a specific recharge"""
    if not has_permission(admin_user, "recharges.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    transaction = await db.transactions.find_one({"transaction_id": transaction_id})
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    return {
        "transaction_id": transaction_id,
        "proof_image": transaction.get("proof_image"),
        "amount_input": transaction.get("amount_input"),
        "status": transaction.get("status")
    }

@admin_router.post("/recharges/approve", response_model=EstadoCambiado, response_model_exclude_unset=True)
async def approve_recharge(request: ApproveRechargeRequest, peticion: Request,
                           admin_user: Usuario = Depends(get_admin_user)):
    """Approve or reject a recharge with uploaded proof"""
    if not has_permission(admin_user, "recharges.approve"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    transaction = await db.transactions.find_one({
        "transaction_id": request.transaction_id,
        "status": {"$in": ["pending", "pending_review"]}
    })
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada o ya procesada")
    
    user_id = transaction.get("user_id")
    amount_ris = transaction.get("amount_output", 0)
    
    if request.approved:
        # Acreditar y asentar en la misma operación. Antes era un `$inc` con un
        # float crudo, sin línea de libro y sin consumir el cupo sin KYC: una
        # recarga aprobada por acá no aparecía en el mayor y tampoco contaba
        # para el límite de quien no verificó su cuenta.
        try:
            await saldos.mover(
                db, user_id, amount_ris,
                movimiento="recarga_brl",
                consumir_cupo=True,
                reference_kind="transaction",
                reference_id=request.transaction_id,
                transaction_id=request.transaction_id,
                display_id=transaction.get("display_id"),
                actor_type="admin",
                actor_id=admin_user.user_id,
                actor_email=admin_user.email,
                amount_output=transaction.get("amount_input", 0),
                currency_output="BRL",
                metadata={"verification_method": "admin_manual_approval"},
                notes="Recarga en reales aprobada a mano",
            )
        except saldos.UsuarioInexistente:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Update transaction status
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "approved_by": admin_user.user_id,
                "verification_method": "admin_manual_approval"
            }}
        )
        
        # Save admin record
        user = await db.users.find_one({"user_id": user_id})
        admin_record = {
            "record_type": "recharge_approved",
            "transaction_id": request.transaction_id,
            "user_id": user_id,
            "user_name": user.get('name', 'N/A') if user else 'N/A',
            "user_email": user.get('email', 'N/A') if user else 'N/A',
            "amount_brl": transaction.get("amount_input", 0),
            "amount_ris": amount_ris,
            "proof_image": transaction.get("proof_image"),
            "approved_by": admin_user.user_id,
            "approved_by_email": admin_user.email,
            "processed_via": "admin_panel",
            "created_at": transaction.get("created_at"),
            "completed_at": datetime.now(timezone.utc),
            "recorded_at": datetime.now(timezone.utc)
        }
        
        await db.admin_payment_records.insert_one(admin_record)
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="✅ Recarga Confirmada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue confirmada. +{amount_ris:.2f} RIS agregados a tu cuenta.",
            notification_type="recharge_completed",
            data={"transaction_id": request.transaction_id, "amount_ris": amount_ris}
        )
        
        logger.info(f"Recharge {request.transaction_id} approved by admin {admin_user.user_id}")
        await auditoria.registrar(
            db, "dinero.recarga_aprobada", quien=admin_user, request=peticion,
            objetivo_tipo="transaccion", objetivo_id=request.transaction_id,
            objetivo_desc=transaction.get("user_email"),
            antes={"status": transaction.get("status")},
            despues={"status": "completed"},
            detalle={"user_id": transaction.get("user_id"),
                     "monto": str(transaction.get("amount_input")),
                     "moneda": transaction.get("currency_input")})
        return {"message": "Recarga aprobada y saldo acreditado", "status": "completed"}
    else:
        # Reject recharge
        await db.transactions.update_one(
            {"transaction_id": request.transaction_id},
            {"$set": {
                "status": "rejected",
                "updated_at": datetime.now(timezone.utc),
                "rejected_by": admin_user.user_id,
                "rejection_reason": request.rejection_reason or "Comprobante inválido"
            }}
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="❌ Recarga Rechazada",
            message=f"Tu recarga de R$ {transaction.get('amount_input', 0):.2f} fue rechazada. Razón: {request.rejection_reason or 'Comprobante inválido'}",
            notification_type="recharge_rejected",
            data={"transaction_id": request.transaction_id}
        )
        
        logger.info(f"Recharge {request.transaction_id} rejected by admin {admin_user.user_id}")
        await auditoria.registrar(
            db, "dinero.recarga_rechazada", quien=admin_user, request=peticion,
            objetivo_tipo="transaccion", objetivo_id=request.transaction_id,
            objetivo_desc=transaction.get("user_email"),
            antes={"status": transaction.get("status")},
            despues={"status": "rejected"},
            detalle={"user_id": transaction.get("user_id"),
                     "monto": str(transaction.get("amount_input")),
                     "motivo": getattr(request, "rejection_reason", None)})
        return {"message": "Recarga rechazada", "status": "rejected"}

# =======================
# TRANSACTIONS
# =======================

@admin_router.get("/transactions", response_model=OperacionesDelPanel, response_model_exclude_unset=True)
async def get_all_transactions(
    admin_user: Usuario = Depends(get_admin_user),
    skip: int = 0,
    limit: int = 50,
    type: Optional[str] = None,
    status: Optional[str] = None
):
    """Get all transactions with filters"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    query = {}
    if type:
        query["type"] = type
    if status:
        query["status"] = status
    
    transactions = await db.transactions.find(
        query,
        las_fotos.sin_las_fotos()
    ).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    total = await db.transactions.count_documents(query)
    
    # Get user info for each transaction
    quien = await quien_es.de_las_filas(db, transactions)

    for tx in transactions:
        tx['_id'] = str(tx['_id'])
        user = quien.ya_conocido(tx.get('user_id'))
        tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
        tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return {"transactions": transactions, "total": total}

# NOTA — el orden de estos dos importa y no es cosmético.
#
# `/transactions/export` tiene que ir ANTES que `/transactions/{transaction_id}`.
# FastAPI resuelve por orden de registro, así que con el orden anterior un GET
# a /api/admin/transactions/export lo atendía get_transaction_detail buscando
# una transacción con id "export": el endpoint de exportar era inalcanzable.
# Ver tests/test_rutas_alcanzables.py, que falla si vuelve a pasar.
@admin_router.get("/transactions/export")
async def export_transactions(admin_user: Usuario = Depends(get_admin_user)):
    """Export all transactions to Excel"""
    if not has_permission(admin_user, "transactions.export"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # LISTA DE LO PERMITIDO: los nueve campos que este Excel escribe.
    #
    # Acá había `{"_id": 0, "proof_image": 0}`, una lista de lo prohibido que
    # nombraba el campo viejo y no el nuevo (`proof_images`, en plural, que es
    # una LISTA de fotos). Medido corriéndolo: cincuenta filas eran 64 MB en
    # memoria para escribir nueve columnas; al tope de diez mil filas, unos
    # 12 GB. El proceso de Railway muere antes de terminar y se lleva puesta
    # la app para todos mientras se reinicia.
    transactions = await db.transactions.find({}, las_fotos.solo(
        "transaction_id", "user_id", "type", "status",
        "amount_input", "amount_output", "created_at", "completed_at",
        "beneficiary_data",
    )).to_list(10000)
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ["Transaction ID", "User ID", "Type", "Status", "Amount Input", "Amount Output", 
               "Created At", "Completed At", "Beneficiary"]
    ws.append(headers)
    
    # Data
    for t in transactions:
        beneficiary_name = ""
        if t.get("beneficiary_data"):
            beneficiary_name = t["beneficiary_data"].get("full_name", "")
        
        ws.append([
            t.get("transaction_id", ""),
            t.get("user_id", ""),
            t.get("type", ""),
            t.get("status", ""),
            t.get("amount_input", 0),
            t.get("amount_output", 0),
            str(t.get("created_at", "")),
            str(t.get("completed_at", "")),
            beneficiary_name
        ])
    
    # Save to bytes
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"}
    )

@admin_router.get("/transactions/{transaction_id}", response_model=DetalleDeOperacion, response_model_exclude_unset=True)
async def get_transaction_detail(transaction_id: str, admin_user: Usuario = Depends(get_admin_user)):
    """Get transaction detail including proof image"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    tx = await db.transactions.find_one({"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    tx['_id'] = str(tx['_id'])
    
    user = await db.users.find_one({"user_id": tx.get('user_id')}, {"name": 1, "email": 1})
    tx['user_name'] = user.get('name', 'N/A') if user else 'N/A'
    tx['user_email'] = user.get('email', 'N/A') if user else 'N/A'
    
    return tx

# =======================
# PAYMENT RECORDS
# =======================

@admin_router.get("/payment-records", response_model=RegistrosDePago, response_model_exclude_unset=True)
async def get_admin_payment_records(admin_user: Usuario = Depends(get_admin_user)):
    """Get all payment records with proof images"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    records = await db.admin_payment_records.find(
        {},
        las_fotos.sin_las_fotos()
    ).sort("recorded_at", -1).to_list(1000)
    
    for r in records:
        r['_id'] = str(r['_id'])
    
    return {"records": records}

@admin_router.get("/payment-records/{record_id}", response_model=RegistroDePago, response_model_exclude_unset=True)
async def get_admin_payment_record_detail(record_id: str, admin_user: Usuario = Depends(get_admin_user)):
    """Get a specific payment record with full details including proof image"""
    if not has_permission(admin_user, "transactions.view"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Un identificador que no tiene forma de ObjectId no es un error del
    # servidor: es un registro que no existe. Sin esto, `ObjectId(...)` lanzaba
    # y la ruta contestaba 500 con «error inesperado» a quien escribiera la
    # dirección a mano o tuviera un enlace viejo.
    if not ObjectId.is_valid(record_id):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    record = await db.admin_payment_records.find_one({"_id": ObjectId(record_id)})
    
    if not record:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    
    record['_id'] = str(record['_id'])
    return record

# =======================
# SUPPORT CHAT MANAGEMENT
# =======================





# =======================
# SETTINGS
# =======================

# ─── LA TASA QUE NO CAMBIABA LA TASA ─────────────────────────────────────
#
# Acá vivían `GET` y `POST /admin/settings/rate`. Escribían y leían
# `db.exchange_rates`, una colección que NADIE MAS del proyecto lee: la tasa
# real vive en `db.rates`, y de ahí la sacan los envíos, el PIX del gestor,
# el cotizador y `GET /api/rate`.
#
# O sea que un administrador entraba, cambiaba la tasa, recibía "Tasa
# actualizada correctamente"... y no pasaba nada. Y como el GET leía la misma
# colección, al recargar veía su número nuevo y quedaba convencido. Una
# pantalla que confirma un cambio que no ocurrió es peor que una que falla.
#
# La ruta que SI funciona es `POST /admin/rates` (routes/admin/tasas.py): escribe
# `db.rates`, deja historial en `rate_history` y asienta en el libro de
# auditoría con el antes y el después. Es la que usa el panel —se comprobó
# que el frontend no llamaba a ésta ni una vez— y es sólo del super
# administrador, que para mover la tasa a todos los clientes es lo correcto.
# ─────────────────────────────────────────────────────────────────────────


