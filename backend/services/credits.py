"""
services/credits.py — Logica de creditos cripto (USDT / USDC) via NOWPayments.

MODELO
    Los "creditos" son saldos en cripto que el usuario deposita a traves de NOWPayments.
    Internamente se guardan como balance_usdt y balance_usdc (uno a uno con la cripto).
    De cara al usuario se muestran como "Creditos USDT" / "Creditos USDC".
    Son TOTALMENTE SEPARADOS de balance_ris (que es en reales) — nunca se mezclan.

SEGURIDAD
    La acreditacion usa $inc atomico con Decimal128, igual que los saldos RIS,
    para evitar condiciones de carrera. Cada deposito se acredita UNA sola vez
    (idempotencia por payment_id, controlada en la coleccion crypto_deposits).

AUDITORIA
    Cada acreditacion (via webhook o manual desde el panel de superadmin) queda
    registrada como una linea inmutable en el libro mayor de creditos cripto
    (services/ledger_crypto.py), con saldo antes/despues, quien la hizo y a que
    operacion pertenece. Si el registro del ledger falla, NUNCA revierte ni
    bloquea la acreditacion real — es solo el rastro auditable.
"""

import logging
from decimal import Decimal
from bson.decimal128 import Decimal128

logger = logging.getLogger(__name__)

# Monedas de credito soportadas y su campo de saldo en el documento de usuario.
CREDIT_FIELDS = {
    "usdt": "balance_usdt",
    "usdc": "balance_usdc",
}

# Etiqueta de cara al usuario (nombre de marca de la billetera, NO el ticker real
# de la cripto: el deposito/red siguen siendo USDT/USDC reales en la blockchain,
# esto es solo como se llama el saldo dentro de la app).
CREDIT_LABELS = {
    "usdt": "USDT",
    "usdc": "USDC",
}


def normalize_currency(currency: str) -> str | None:
    """Normaliza el codigo de moneda de NOWPayments a 'usdt' o 'usdc'.

    NOWPayments puede enviar 'usdttrc20', 'usdcerc20', etc. segun la red.
    Devuelve 'usdt', 'usdc', o None si no es una moneda de credito soportada."""
    if not currency:
        return None
    c = currency.strip().lower()
    if c.startswith("usdt"):
        return "usdt"
    if c.startswith("usdc"):
        return "usdc"
    return None


def credit_field_for(currency: str) -> str | None:
    """Devuelve el nombre del campo de saldo (balance_usdt / balance_usdc)."""
    key = normalize_currency(currency)
    return CREDIT_FIELDS.get(key) if key else None


def to_credit_decimal(amount) -> Decimal:
    """Convierte a Decimal con 8 decimales (precision cripto)."""
    if isinstance(amount, Decimal128):
        d = amount.to_decimal()
    elif isinstance(amount, Decimal):
        d = amount
    else:
        d = Decimal(str(amount))
    return d.quantize(Decimal("0.00000001"))


async def credit_user(
    db,
    user_id: str,
    currency: str,
    amount,
    *,
    movement_type: str = "deposito_cripto",
    reference_kind: str | None = None,
    reference_id: str | None = None,
    actor_type: str = "webhook",
    actor_id: str | None = None,
    actor_email: str | None = None,
    notes: str | None = None,
) -> dict:
    """Acredita amount de creditos (USDT/USDC) al usuario, de forma atomica.

    Devuelve {"ok": True, "field": ..., "amount": ...} si acredito,
    o {"ok": False, "reason": ...} si la moneda no es soportada.

    NOTA: la idempotencia (no acreditar dos veces el mismo pago) se controla
    en el webhook via la coleccion crypto_deposits, ANTES de llamar aqui.

    Ademas de acreditar, escribe una linea inmutable en el libro mayor de
    creditos cripto (services/ledger_crypto.py) para auditoria — igual que el
    libro de RIS. Esto nunca bloquea ni revierte la acreditacion si falla.
    """
    field = credit_field_for(currency)
    if not field:
        return {"ok": False, "reason": f"moneda no soportada: {currency}"}

    key = normalize_currency(currency)
    amount_dec = to_credit_decimal(amount)

    # Saldo antes (best-effort, solo para el registro del ledger; el $inc de abajo
    # es la operacion atomica real que determina el saldo).
    user_before = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, field: 1, "email": 1, "name": 1, "full_name": 1, "role": 1},
    )
    balance_before = float(to_credit_decimal(user_before.get(field, 0))) if user_before else None

    inc_value = Decimal128(amount_dec)
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {field: inc_value}},
    )

    balance_after = (balance_before + float(amount_dec)) if balance_before is not None else None

    try:
        from services.ledger_crypto import record_crypto_entry
        await record_crypto_entry(
            user_id=user_id,
            currency=key,
            movement_type=movement_type,
            amount=float(amount_dec),
            direction="credit",
            balance_before=balance_before,
            balance_after=balance_after,
            reference_kind=reference_kind,
            reference_id=reference_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_email=actor_email,
            user_snapshot=(
                {
                    "email": user_before.get("email"),
                    "name": user_before.get("full_name") or user_before.get("name"),
                    "role": user_before.get("role", "user"),
                } if user_before else None
            ),
            notes=notes,
        )
    except Exception as e:
        logger.warning(f"No se pudo registrar en ledger_crypto (user={user_id}): {e}")

    return {"ok": True, "field": field, "amount": str(amount_dec)}
