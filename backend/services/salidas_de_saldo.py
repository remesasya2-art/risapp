"""
services/salidas_de_saldo.py — Los envíos que el cliente paga con su saldo: lo
que se escribe en la base, adentro de una transacción cuando el Mongo la tiene.

POR QUE ESTA ACA Y NO EN LA RUTA

    Cada envío descuenta el saldo, crea la orden y escribe su línea del libro:
    tres escrituras. Con un Mongo de un solo nodo son separadas, y si algo
    falla a la mitad la ruta devuelve el saldo a mano. Con transacciones van
    juntas: si una falla, no queda ninguna.

    Vivía en `routes/transactions.py`, que ya pasaba las 800 líneas y no puede
    crecer (ver `tests/archivos_largos.txt`). Envolverlo en una transacción
    ahí lo hacía crecer; acá, la ruta queda más corta.

    Lo que NO es una escritura en la base —el aviso al cliente, la respuesta,
    la idempotencia— queda en la ruta: una transacción que choca se reintenta
    entera, y un aviso no se puede reintentar sin mandarlo dos veces.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services import saldos, transacciones
from services.money import to_decimal, to_decimal128, to_float
from utils.helpers import get_next_withdrawal_id

logger = logging.getLogger("routes.transactions")


async def cobrar_envio_a_brasil(current_user, request):
    """Descuenta el saldo, crea la orden y asienta la línea del envío a Brasil.

    Devuelve `(user, beneficiary, tx_id, display_id, amount_brl)`. Levanta las
    mismas `HTTPException` que la ruta levantaba: saldo insuficiente,
    beneficiario que no existe, orden que no se pudo registrar.
    """
    async def trabajo(session):
        # Descuento atómico de saldo RIS
        user = await db.users.find_one_and_update(
            {"user_id": current_user.user_id, "balance_ris": {"$gte": to_decimal128(to_decimal(request.amount))}},
            {"$inc": {"balance_ris": to_decimal128(-to_decimal(request.amount))}},
            return_document=True,
            session=session,
        )
        if user is None:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")
        beneficiary = await db.beneficiaries.find_one({
            "beneficiary_id": request.beneficiary_id,
            "user_id": current_user.user_id,
            "pais": "BR",
        }, session=session)
        if not beneficiary:
            # Devolver el saldo si el beneficiario no existe. Con transacción no
            # hace falta: el error la deshace entera, débito incluido.
            if session is None:
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
                )
            raise HTTPException(status_code=404, detail="Beneficiario de Brasil no encontrado")
        amount_brl = request.amount  # 1 a 1
        beneficiary_data = {
            "full_name": beneficiary.get("full_name"),
            "cpf": beneficiary.get("cpf"),
            "pix_key": beneficiary.get("pix_key"),
            "payment_type": "pix_br",
            "pais": "BR",
        }
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        display_id = await get_next_withdrawal_id()
        transaction = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "user_id": current_user.user_id,
            "type": "withdrawal",
            "amount_input": request.amount,
            "amount_output": amount_brl,
            "currency_input": "RIS",
            "currency_output": "BRL",
            "rate": 1.0,
            "status": "pending",
            "beneficiary_id": request.beneficiary_id,
            "beneficiary_data": beneficiary_data,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            await db.transactions.insert_one(transaction, session=session)
        except Exception as e:
            # Con transacción, el error la deshace entera: devolver a mano sería
            # escribir sobre una transacción que el servidor ya abortó.
            if session is None:
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
                )
            logger.error(f"Fallo al registrar envío a Brasil {tx_id}, saldo devuelto: {e}")
            raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

        # Libro mayor RIS (append-only). Nunca interrumpe el envío.
        try:
            from services.ledger import record_ris_entry
            # `saldo_de` lee con `from_db`, así que da lo mismo si el campo quedó
            # en `float` o en `Decimal128`. Antes se leía crudo y se le SUMABA el
            # monto para sacar el saldo anterior: con el campo en Decimal128 eso es
            # un TypeError, y como esto va dentro del `try`, la línea del libro se
            # perdía en silencio mientras la plata sí se movía.
            _saldo_despues = saldos.saldo_de(user)
            balance_after_ris = to_float(_saldo_despues)
            balance_before_ris = to_float(_saldo_despues + to_decimal(request.amount))
            await record_ris_entry(
                user_id=current_user.user_id,
                movement_type="envio_reais",
                amount=request.amount,
                direction="debit",
                account="balance_ris",
                balance_before=balance_before_ris,
                balance_after=balance_after_ris,
                reference_kind="transaction",
                reference_id=tx_id,
                transaction_id=tx_id,
                display_id=display_id,
                actor_type="user",
                actor_id=current_user.user_id,
                actor_email=user.get("email"),
                rate=1.0,
                rate_kind="ris_to_brl",
                amount_output=amount_brl,
                currency_output="BRL",
                counterparty=beneficiary_data,
                user_snapshot={"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user.get("role", "user")},
                notes="Envío RIS → Reais (PIX Brasil)",
                session=session,
            )
        except Exception as e:
            # Sin transacción, el libro nunca interrumpe el envío. Con
            # transacción, sí: tragarse el error confirmaría el débito sin su línea.
            if session is not None:
                raise
            logger.warning(f"Ledger envio_reais no registrado: {e}")
        return user, beneficiary, tx_id, display_id, amount_brl

    return await transacciones.en_una_transaccion(trabajo)
