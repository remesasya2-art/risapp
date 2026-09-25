"""
routes/admin/pagos_incompletos.py — Los envíos cripto que llegaron con menos plata de la pedida: aprobarlos igual
o devolver lo que llegó como saldo.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException

from database import db
from services import las_fotos
from services import quien_es
from services.money import para_mostrar
from models.user import User
from models.acciones_del_panel import (EstadoCambiado, OrdenRechazadaYReembolsada)
from models.panel_ordenes import OrdenesEnRevisionDePago
from routes.dependencies import get_super_admin
from services.notifications import create_notification
from routes.admin._comun import TOPE_DE_UNA_COLA, logger

router = APIRouter(prefix="/admin", tags=["admin"])


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


@router.get("/ordenes/revision-pago", response_model=OrdenesEnRevisionDePago, response_model_exclude_unset=True)
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


@router.post("/ordenes/{transaction_id}/aprobar-con-diferencia", response_model=EstadoCambiado, response_model_exclude_unset=True)
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


@router.post("/ordenes/{transaction_id}/rechazar-y-reembolsar-saldo", response_model=OrdenRechazadaYReembolsada, response_model_exclude_unset=True)
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

    # EL RECHAZO, LA DEVOLUCION Y SU LINEA, EN UNA TRANSACCION
    #
    #   La orden se marca «rejected» ANTES de devolver el saldo: es el reclamo
    #   que impide que dos administradores devuelvan dos veces. Con un Mongo de
    #   un solo nodo son escrituras separadas, y un corte entre las dos dejaba
    #   la orden rechazada y SIN devolución: el botón ya no dejaba reintentar,
    #   porque la orden ya no estaba en revisión. Con réplicas van juntas: si
    #   algo falla, la orden sigue en revisión y el botón se puede volver a usar.
    async def trabajo(session):
        # La sesión se pasa sólo si hay una: sin transacción, las llamadas son
        # las de siempre.
        con = {"session": session} if session is not None else {}
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
            **con,
        )
        if not claimed:
            return None, 0.0, None

        monto = float(claimed.get("actually_paid") or 0) + float(claimed.get("topup_actually_paid") or 0)
        monto_dec = to_credit_decimal(monto)
        field = "balance_usdt" if cur_in == "USDT" else "balance_usdc"

        acreditado = 0.0
        if monto > 0:
            user_doc = await db.users.find_one_and_update(
                {"user_id": claimed["user_id"]},
                {"$inc": {field: Decimal128(monto_dec)}},
                return_document=True,
                **con,
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
                    session=session,
                )
            except Exception as e:
                # Con transacción, tragarse el error confirmaría la devolución
                # sin su línea.
                if session is not None:
                    raise
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
            **con,
        )
        return claimed, acreditado, field

    from services import transacciones
    claimed, acreditado, field = await transacciones.en_una_transaccion(trabajo)
    if not claimed:
        existe = await db.transactions.find_one({"transaction_id": transaction_id}, {"status": 1})
        if not existe:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        raise HTTPException(status_code=409, detail=f"La orden ya no está en revisión (estado: {existe.get('status')})")

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
