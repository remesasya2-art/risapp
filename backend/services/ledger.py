"""
Libro mayor (ledger) de saldo RIS — append-only.

Sub-fase A1: modo "solo registra". Este módulo escribe líneas inmutables cada
vez que el saldo RIS de un usuario cambia. NO modifica saldos y NO rompe el
flujo: cualquier error al registrar se captura y se loguea, nunca se propaga.

El saldo se sigue calculando como hoy (campo balance_ris en el usuario); el
ledger es la historia auditable paralela y, en una fase posterior, la base de
la reconciliación.

Cada línea guarda el máximo contexto del negocio: quién, qué, cuánto, saldo
antes/después, a qué operación pertenece, qué tasa se usó, el beneficiario,
quién lo procesó y metadatos libres.

El BTC NO va en este libro: es una orden directa que no toca el saldo RIS y
tendrá su propio libro (ledger_btc) en un paso aparte.
"""

import logging
import uuid
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)

LEDGER_COLLECTION = "ledger"

_indexes_ready = False


async def _ensure_indexes():
    """Crea índices del ledger una sola vez (idempotente)."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db[LEDGER_COLLECTION].create_index([("user_id", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index("entry_id", unique=True)
        await db[LEDGER_COLLECTION].create_index([("movement_type", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("reference.kind", 1), ("reference.id", 1)])
        _indexes_ready = True
    except Exception as e:
        logger.warning(f"No se pudieron crear índices del ledger: {e}")


async def record_ris_entry(
    *,
    user_id: str,
    movement_type: str,            # recarga_pix, envio_ves, envio_reais, refund_envio_ves, refund_envio_reais, bono_referido, pago_tarjeta, ajuste_admin...
    amount: float,                 # SIEMPRE positivo; 'direction' define el signo
    direction: str,                # "credit" (entra saldo) | "debit" (sale saldo)
    account: str = "balance_ris",  # balance_ris | balance_ris_terceros
    balance_before=None,
    balance_after=None,
    reference_kind: str = None,    # transaction | pix_payment | btc_remesa | referral | card_payment | manual
    reference_id: str = None,
    transaction_id: str = None,
    display_id=None,
    actor_type: str = "system",    # user | admin | system | webhook
    actor_id: str = None,
    actor_email: str = None,
    rate=None,
    rate_kind: str = None,         # ris_to_ves | brl_to_ris | ves_to_ris ...
    amount_output=None,            # p.ej. VES o BRL resultantes de la operación
    currency_output: str = None,   # VES | BRL ...
    counterparty: dict = None,     # snapshot del beneficiario u origen
    user_snapshot: dict = None,    # email/name/role del usuario (si ya se tiene a mano)
    metadata: dict = None,         # contexto libre adicional
    notes: str = None,
):
    """Escribe una línea inmutable en el libro de RIS. Nunca lanza excepción.

    Devuelve el entry_id si se registró, o None si hubo algún problema (sin
    afectar el flujo que la invocó).
    """
    try:
        await _ensure_indexes()

        # Snapshot del usuario si no se proporcionó
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
            "book": "RIS",
            # Titular del movimiento
            "user_id": user_id,
            "user_email": user_snapshot.get("email"),
            "user_name": user_snapshot.get("name"),
            "user_role": user_snapshot.get("role"),
            # Naturaleza del movimiento
            "movement_type": movement_type,
            "direction": direction,
            "amount": amount_abs,
            "signed_amount": signed,
            "currency": "RIS",
            "account": account,
            # Saldo antes/después (si el llamador lo provee)
            "balance_before": balance_before,
            "balance_after": balance_after,
            # Enlace al origen
            "reference": ({"kind": reference_kind, "id": reference_id} if reference_kind else None),
            "transaction_id": transaction_id,
            "display_id": display_id,
            # Quién lo ejecutó
            "actor": {"type": actor_type, "id": actor_id, "email": actor_email},
            # Económico de la operación
            "rate": rate,
            "rate_kind": rate_kind,
            "amount_output": amount_output,
            "currency_output": currency_output,
            # Contexto
            "counterparty": counterparty,
            "metadata": metadata or {},
            "notes": notes,
        }

        await db[LEDGER_COLLECTION].insert_one(entry)
        return entry["entry_id"]
    except Exception as e:
        logger.error(
            f"No se pudo registrar en el ledger RIS (user={user_id}, type={movement_type}): {e}"
        )
        return None


async def sum_ris_balance(user_id: str, account: str = "balance_ris") -> float:
    """Suma todas las líneas del ledger de un usuario/cuenta.

    Se usará en la fase de reconciliación para comparar contra balance_ris.
    """
    try:
        cursor = db[LEDGER_COLLECTION].aggregate([
            {"$match": {"user_id": user_id, "account": account}},
            {"$group": {"_id": None, "total": {"$sum": "$signed_amount"}}},
        ])
        async for row in cursor:
            return round(float(row.get("total", 0.0)), 8)
        return 0.0
    except Exception as e:
        logger.warning(f"sum_ris_balance fallo: {e}")
        return 0.0

async def create_opening_entries():
    """Crea, UNA sola vez por usuario y cuenta, una línea 'saldo_apertura' que
    iguala la suma del ledger al saldo actual del usuario.

    Esto resuelve la migración: como el ledger empezó a registrar después de que
    los usuarios ya tenían saldo, la apertura representa ese saldo inicial. Tras
    ejecutarla, sum(ledger) == balance del usuario y la reconciliación cuadra.

    Es idempotente: si un usuario ya tiene apertura en esa cuenta, no la repite.
    El valor de apertura = saldo_actual - suma_ledger_existente, de modo que
    también respeta los movimientos ya registrados desde que el libro arrancó.
    """
    creados = 0
    revisados = 0
    try:
        await _ensure_indexes()
        async for u in db.users.find(
            {},
            {"user_id": 1, "balance_ris": 1, "balance_ris_terceros": 1,
             "email": 1, "name": 1, "full_name": 1, "role": 1},
        ):
            uid = u.get("user_id")
            if not uid:
                continue
            revisados += 1
            snapshot = {
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
            }
            for account, field in (("balance_ris", "balance_ris"),
                                   ("balance_ris_terceros", "balance_ris_terceros")):
                # ¿ya tiene apertura en esta cuenta? (idempotencia)
                existing = await db[LEDGER_COLLECTION].find_one(
                    {"user_id": uid, "movement_type": "saldo_apertura", "account": account}
                )
                if existing:
                    continue
                current = float(u.get(field) or 0)
                led = await sum_ris_balance(uid, account)
                opening = round(current - led, 8)
                if abs(opening) < 1e-9:
                    continue  # nada que abrir
                await record_ris_entry(
                    user_id=uid,
                    movement_type="saldo_apertura",
                    amount=abs(opening),
                    direction="credit" if opening > 0 else "debit",
                    account=account,
                    balance_before=led,
                    balance_after=current,
                    reference_kind="manual",
                    reference_id="opening_migration",
                    actor_type="system",
                    actor_id="ledger_opening",
                    user_snapshot=snapshot,
                    notes="Saldo de apertura (migración al libro mayor)",
                )
                creados += 1
        return {"revisados": revisados, "aperturas_creadas": creados}
    except Exception as e:
        logger.error(f"create_opening_entries fallo: {e}")
        return {"revisados": revisados, "aperturas_creadas": creados, "error": str(e)}
