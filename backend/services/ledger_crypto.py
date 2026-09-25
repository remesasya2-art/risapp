"""
services/ledger_crypto.py — Libro mayor (ledger) de creditos cripto USDT/USDC.

Mismo patron que services/ledger.py (libro de RIS), pero para las billeteras de
creditos cripto (balance_usdt / balance_usdc). Usa la MISMA coleccion 'ledger'
(append-only, inmutable), solo que con book='USDT'/'USDC', para que ambos libros
convivan sin duplicar infraestructura de indices/consultas.

IMPORTANTE: esto NUNCA toca balance_ris ni la logica de PIX/MercadoPago/BTC.
Es exclusivamente el rastro auditable de balance_usdt/balance_usdc.
"""

import logging
import uuid
from datetime import datetime, timezone

from database import db
from services.money import quantize_money, to_decimal, to_decimal128

logger = logging.getLogger(__name__)

LEDGER_COLLECTION = "ledger"

_indexes_ready = False


async def _ensure_indexes():
    """Crea indices del ledger una sola vez (idempotente). Comparte indices con
    services/ledger.py (misma coleccion), asi que si ya existen no pasa nada."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db[LEDGER_COLLECTION].create_index([("user_id", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index("entry_id", unique=True)
        await db[LEDGER_COLLECTION].create_index([("movement_type", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("reference.kind", 1), ("reference.id", 1)])
        await db[LEDGER_COLLECTION].create_index([("book", 1), ("created_at", -1)])
        _indexes_ready = True
    except Exception as e:
        logger.warning(f"No se pudieron crear indices del ledger cripto: {e}")


async def record_crypto_entry(
    *,
    user_id: str,
    currency: str,                 # "usdt" | "usdc"
    movement_type: str,            # deposito_cripto | ajuste_admin_cripto
    amount,                        # Decimal, texto o float: se normaliza
    direction: str,                # "credit" (entra saldo) | "debit" (sale saldo)
    balance_before=None,
    balance_after=None,
    decimales: int = 8,
    reference_kind: str = None,    # crypto_deposit | manual
    reference_id: str = None,      # order_id
    actor_type: str = "webhook",   # user | admin | system | webhook
    actor_id: str = None,
    actor_email: str = None,
    user_snapshot: dict = None,
    metadata: dict = None,
    notes: str = None,
    session=None,
):
    """Escribe una linea inmutable en el libro de creditos cripto. Sin
    `session` nunca lanza excepcion (best-effort): si falla, se loguea pero NO
    revierte la acreditacion real que ya se hizo sobre balance_usdt/balance_usdc.

    Con `session` —la transacción del movimiento de saldo— un error SÍ sale,
    por el mismo motivo que en `ledger.record_ris_entry`: tragarlo confirmaría
    el saldo movido sin su línea.

    Devuelve el entry_id si se registro, o None si hubo algun problema.
    """
    try:
        await _ensure_indexes()

        book = currency.upper()  # "USDT" | "USDC"
        account = f"balance_{currency.lower()}"

        if user_snapshot is None:
            u = await db.users.find_one(
                {"user_id": user_id},
                {"email": 1, "name": 1, "full_name": 1, "role": 1},
            ) or {}
            user_snapshot = {
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
            }

        # En Decimal128 con OCHO decimales, como los saldos cripto. El porqué
        # entero está en `ledger.record_ris_entry`.
        amount_abs = quantize_money(abs(to_decimal(amount)), decimales)
        signed = amount_abs if direction == "credit" else -amount_abs

        entry = {
            "entry_id": f"le_{uuid.uuid4().hex[:16]}",
            "created_at": datetime.now(timezone.utc),
            "book": book,
            "user_id": user_id,
            "user_email": user_snapshot.get("email"),
            "user_name": user_snapshot.get("name"),
            "user_role": user_snapshot.get("role"),
            "movement_type": movement_type,
            "direction": direction,
            "amount": to_decimal128(amount_abs, decimales),
            "signed_amount": to_decimal128(signed, decimales),
            "currency": book,
            "account": account,
            "balance_before": None if balance_before is None else to_decimal128(balance_before, decimales),
            "balance_after": None if balance_after is None else to_decimal128(balance_after, decimales),
            "reference": ({"kind": reference_kind, "id": reference_id} if reference_kind else None),
            "actor": {"type": actor_type, "id": actor_id, "email": actor_email},
            "metadata": metadata or {},
            "notes": notes,
        }

        # Sin transacción, la misma llamada de siempre.
        if session is None:
            await db[LEDGER_COLLECTION].insert_one(entry)
        else:
            await db[LEDGER_COLLECTION].insert_one(entry, session=session)
        return entry["entry_id"]
    except Exception as e:
        if session is not None:
            logger.error(
                "El asiento cripto falló adentro de la transacción: el movimiento se "
                f"deshace — user_id={user_id} movimiento={movement_type} monto={amount} error={e!r}")
            raise
        # Igual que en el libro RIS: no se relanza, pero no se calla. Ver
        # services/gritos.py.
        from services import gritos
        await gritos.libro_sin_linea(db, libro=f"cripto/{currency}", user_id=user_id,
                                     movement_type=movement_type, amount=amount, account=account, error=e)
        return None
