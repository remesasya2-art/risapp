"""
routes/admin/retiros.py — Los retiros: la cola de pendientes, el historial y aprobar o rechazar.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from services import las_fotos
from services import quien_es, transacciones
from services.money import from_db, to_float, to_decimal, to_decimal128
from models.user import User
from models.acciones_del_panel import AccionDelPanel
from models.panel_retiros import ColaDeRetiros, RetirosPendientes
from routes.dependencies import get_super_admin
from services.notifications import create_notification
from services import registro_del_pago
from services.imagen_recibida import ImagenInvalida, limpiar_lista
from routes.admin._comun import TOPE_DE_UNA_COLA, logger

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== WITHDRAWALS ==============

@router.get("/withdrawals/pending", response_model=RetirosPendientes, response_model_exclude_unset=True)
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

@router.get("/withdrawals/all", response_model=ColaDeRetiros, response_model_exclude_unset=True)
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

@router.post("/withdrawals/process", response_model=AccionDelPanel, response_model_exclude_unset=True)
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
        # LA DEVOLUCION, SU LINEA Y EL ESTADO, EN UNA TRANSACCION
        #
        #   Con un Mongo de un solo nodo son escrituras separadas: un corte
        #   después de devolver deja la plata devuelta y el retiro pendiente, y
        #   un segundo rechazo la devolvería otra vez. Con réplicas van juntas.
        #   El aviso al cliente va después: una transacción que choca se
        #   reintenta, y un aviso no.
        async def trabajo(session):
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
                    return_document=True,
                    session=session,
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
                        session=session,
                    )
                except Exception as e:
                    if session is not None:
                        raise
                    logger.warning(f"Ledger cripto refund_envio no registrado: {e}")
            else:
                _refunded_user = await db.users.find_one_and_update(
                    {"user_id": transaction["user_id"]},
                    {"$inc": {"balance_ris": to_decimal128(to_decimal(_refund_amount))}},
                    return_document=True,
                    session=session,
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
                        session=session,
                    )
                except Exception as e:
                    # Sin transacción, el libro no interrumpe el rechazo. Con
                    # transacción, sí: tragarse el error confirmaría la devolución
                    # sin su línea.
                    if session is not None:
                        raise
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
                {"$set": _reject_update},
                session=session,
            )

        await transacciones.en_una_transaccion(trabajo)
        
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
