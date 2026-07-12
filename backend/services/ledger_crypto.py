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
    amount: float,
    direction: str,                # "credit" (entra saldo) | "debit" (sale saldo)
    balance_before=None,
    balance_after=None,
    reference_kind: str = None,    # crypto_deposit | manual
    reference_id: str = None,      # order_id
    actor_type: str = "webhook",   # user | admin | system | webhook
    actor_id: str = None,
    actor_email: str = None,
    user_snapshot: dict = None,
    metadata: dict = None,
    notes: str = None,
):
    """Escribe una linea inmutable en el libro de creditos cripto. Nunca lanza
    excepcion (best-effort): si falla, se loguea pero NO revierte la acreditacion
    real que ya se hizo sobre balance_usdt/balance_usdc.

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

        amount_abs = abs(float(amount or 0))
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
            "amount": amount_abs,
            "signed_amount": signed,
            "currency": book,
            "account": account,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "reference": ({"kind": reference_kind, "id": reference_id} if reference_kind else None),
            "actor": {"type": actor_type, "id": actor_id, "email": actor_email},
            "metadata": metadata or {},
            "notes": notes,
        }

        await db[LEDGER_COLLECTION].insert_one(entry)
        return entry["entry_id"]
    except Exception as e:
        logger.error(
            f"No se pudo registrar en el ledger cripto (user={user_id}, currency={currency}): {e}"
        )
        return None
