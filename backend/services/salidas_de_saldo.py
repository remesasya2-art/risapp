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
from services import bonos, saldos, transacciones
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


async def cobrar_retiro_en_bolivares(current_user, request, *, transaction, tx_id, display_id,
                                     ris_to_ves, amount_ves, beneficiary_data):
    """Descuenta el saldo (y el bono, si alcanza), crea la orden y asienta sus
    líneas del retiro en bolívares.

    La orden ya viene armada: la ruta la completa con las comisiones antes de
    cobrar. Devuelve el usuario después del débito. Levanta las mismas
    `HTTPException` que la ruta levantaba: saldo insuficiente, orden que no se
    pudo registrar.
    """
    async def trabajo(session):
        # ─── 3) El débito, que ahora puede salir de DOS cuentas ──────────────
        #
        # Esta es la única ruta de la aplicación que sabe gastar el bono de
        # bienvenida, y es a propósito: la regla del producto es que ese bono se
        # usa sólo en envíos a Venezuela. Si al liberarse se mezclara con
        # `balance_ris`, habría que enseñarle la restricción a las veinte funciones
        # que debitan ese campo, y la primera que se olvidara la dejaría sin
        # efecto. Ver `services/bonos.py`.
        #
        # EL ORDEN: primero el bono, después el saldo normal. Porque el bono sólo
        # sirve para esto y el saldo sirve para todo: gastar primero el que menos
        # sirve le deja a la persona la mayor libertad con lo que le queda.
        #
        # UNA SOLA ESCRITURA, con las dos comprobaciones DENTRO del filtro. Partirlo
        # en dos —debitar el bono y después el saldo— abriría la ventana en la que
        # el bono ya salió y el saldo todavía no, y dos envíos simultáneos pasarían
        # los dos la comprobación. Es el mismo motivo por el que
        # `saldos.transferir` toca los dos campos en un solo `$inc`.
        _monto_total = to_decimal(request.amount)
        _antes = await db.users.find_one(
            {"user_id": current_user.user_id},
            {"_id": 0, "bono": 1, "balance_ris_bono": 1})
        _del_bono = min(_monto_total,
                        await bonos.disponible_para_enviar(db, _antes or {}))
        _del_saldo = _monto_total - _del_bono

        _filtro = {"user_id": current_user.user_id,
                   "balance_ris": {"$gte": to_decimal128(_del_saldo)}}
        _resta = {"balance_ris": to_decimal128(-_del_saldo)}
        if _del_bono > 0:
            # Sólo se nombra la cuenta del bono si de verdad se va a usar. Las
            # cuentas viejas no tienen ese campo, y un `$gte: 0` contra un campo
            # ausente no coincide: el filtro rechazaría el envío de todo el que se
            # registró antes de que el bono existiera.
            _filtro[bonos.CUENTA_DEL_BONO] = {"$gte": to_decimal128(_del_bono)}
            _resta[bonos.CUENTA_DEL_BONO] = to_decimal128(-_del_bono)

        user = await db.users.find_one_and_update(
            _filtro, {"$inc": _resta}, return_document=True, session=session)
        if user is None:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")

        # 4) Crear el registro; si falla, devolver el saldo (compensación) para no perder RIS
        try:
            await db.transactions.insert_one(transaction, session=session)
        except Exception as e:
            # Se devuelve a CADA cuenta lo que salió de ella. Devolverlo todo a
            # `balance_ris` convertiría un bono —que sólo sirve para Venezuela— en
            # saldo libre, y un fallo de registro terminaría regalando plata.
            # Con transacción no hace falta: el error la deshace entera.
            if session is None:
                await db.users.update_one({"user_id": current_user.user_id},
                                          {"$inc": {k: to_decimal128(-v.to_decimal())
                                                    for k, v in _resta.items()}})
            logger.error(f"Fallo al registrar retiro {tx_id}, saldo devuelto: {e}")
            raise HTTPException(status_code=500, detail="No se pudo registrar el retiro. Tu saldo no fue afectado.")

        # Libro mayor RIS (append-only). Nunca interrumpe el envío.
        try:
            from services.ledger import record_ris_entry
            # `saldo_de` lee con `from_db`, así que da lo mismo si el campo quedó
            # en `float` o en `Decimal128`. Antes se leía crudo y se le SUMABA el
            # monto para sacar el saldo anterior: con el campo en Decimal128 eso es
            # un TypeError, y como esto va dentro del `try`, la línea del libro se
            # perdía en silencio mientras la plata sí se movía.
            # UNA LINEA POR CUENTA DE LA QUE SALIO PLATA, y no una sola por el
            # total. Antes de que el bono existiera había una sola cuenta y daba lo
            # mismo; ahora una línea que dijera «salieron 50 de balance_ris» cuando
            # 15 salieron del bono haría que el libro no cuadre contra los saldos, y
            # el chequeo de integridad lo denunciaría —con razón—.
            _snapshot = {"email": user.get("email"),
                         "name": user.get("full_name") or user.get("name"),
                         "role": user.get("role", "user")}
            _comun = dict(
                user_id=current_user.user_id,
                movement_type="envio_ves",
                direction="debit",
                reference_kind="transaction",
                reference_id=tx_id,
                transaction_id=tx_id,
                display_id=display_id,
                actor_type="user",
                actor_id=current_user.user_id,
                actor_email=user.get("email"),
                rate=ris_to_ves,
                rate_kind="ris_to_ves",
                amount_output=amount_ves,
                currency_output="VES",
                counterparty=beneficiary_data,
                user_snapshot=_snapshot,
            )
            for _cuenta, _parte, _nota in (
                    ("balance_ris", _del_saldo, "Envío RIS → VES"),
                    (bonos.CUENTA_DEL_BONO, _del_bono,
                     "Envío RIS → VES pagado con el bono de bienvenida")):
                if _parte <= 0:
                    # Un asiento de cero es ruido en el mayor, y `saldos.mover` ya
                    # se niega a escribirlo por el mismo motivo.
                    continue
                _despues = saldos.saldo_de(user, _cuenta)
                await record_ris_entry(
                    amount=to_float(_parte),
                    account=_cuenta,
                    balance_before=to_float(_despues + _parte),
                    balance_after=to_float(_despues),
                    notes=_nota,
                    session=session,
                    **_comun,
                )
        except Exception as e:
            # Sin transacción, el libro nunca interrumpe el envío. Con
            # transacción, sí: tragarse el error confirmaría el débito sin su línea.
            if session is not None:
                raise
            logger.warning(f"Ledger envio_ves no registrado: {e}")
        return user

    return await transacciones.en_una_transaccion(trabajo)


async def cobrar_envio_con_saldo_cripto(current_user, request, *, key, tx_id, display_id,
                                        crypto_to_ves, amount_ves, beneficiary_data):
    """Descuenta el saldo en USDT o USDC, crea la orden y asienta su línea en el
    libro cripto. Es el envío a Venezuela que el cliente paga con su saldo.

    Devuelve el documento del usuario después del débito. Levanta las mismas
    `HTTPException` que la ruta levantaba: saldo insuficiente y orden que no
    se pudo registrar.
    """
    from bson.decimal128 import Decimal128
    from services.credits import credit_field_for, to_credit_decimal

    field = credit_field_for(request.currency)
    amount_dec = to_credit_decimal(request.amount)

    async def trabajo(session):
        # La sesión se pasa sólo si hay una: sin transacción, las llamadas son
        # las de siempre.
        con = {"session": session} if session is not None else {}
        user = await db.users.find_one_and_update(
            {"user_id": current_user.user_id, field: {"$gte": Decimal128(amount_dec)}},
            {"$inc": {field: Decimal128(-amount_dec)}},
            return_document=True,
            **con,
        )
        if user is None:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")

        transaction = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "user_id": current_user.user_id,
            "type": "withdrawal",
            "amount_input": request.amount,
            "amount_output": amount_ves,
            "currency_input": key.upper(),
            "currency_output": "VES",
            "rate": crypto_to_ves,
            "status": "pending",
            "beneficiary_id": request.beneficiary_id,
            "beneficiary_data": beneficiary_data,
            "funded_from": "balance",
            "created_at": datetime.now(timezone.utc),
        }
        try:
            await db.transactions.insert_one(transaction, **con)
        except Exception as e:
            # Con transacción, el error la deshace entera: devolver a mano sería
            # escribir sobre una transacción que el servidor ya abortó.
            if session is None:
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$inc": {field: Decimal128(amount_dec)}}
                )
            logger.error(f"Fallo al registrar envío cripto (saldo) {tx_id}, saldo devuelto: {e}")
            raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

        try:
            from services.ledger_crypto import record_crypto_entry
            balance_after = user.get(field)
            balance_after_f = float(to_credit_decimal(balance_after)) if balance_after is not None else None
            await record_crypto_entry(
                user_id=current_user.user_id,
                currency=key,
                movement_type="envio_ves",
                amount=float(amount_dec),
                direction="debit",
                balance_before=(balance_after_f + float(amount_dec)) if balance_after_f is not None else None,
                balance_after=balance_after_f,
                reference_kind="transaction",
                reference_id=tx_id,
                actor_type="user",
                actor_id=current_user.user_id,
                actor_email=user.get("email"),
                metadata={"display_id": display_id, "beneficiary": beneficiary_data, "funded_from": "balance"},
                notes=f"Envío {key.upper()} → VES (desde saldo)",
                session=session,
            )
        except Exception as e:
            # Sin transacción, el libro nunca interrumpe el envío. Con
            # transacción, sí: tragarse el error confirmaría el débito sin su línea.
            if session is not None:
                raise
            logger.warning(f"Ledger cripto envio_ves (saldo) no registrado: {e}")
        return user

    return await transacciones.en_una_transaccion(trabajo)
