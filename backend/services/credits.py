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

ESTADO
    Modulo aislado. Se conecta al webhook de NOWPayments cuando se construya.
    No cambia el comportamiento actual de la app.
"""

from decimal import Decimal
from bson.decimal128 import Decimal128

# Monedas de credito soportadas y su campo de saldo en el documento de usuario.
CREDIT_FIELDS = {
    "usdt": "balance_usdt",
    "usdc": "balance_usdc",
}

# Etiqueta de cara al usuario
CREDIT_LABELS = {
    "usdt": "Creditos USDT",
    "usdc": "Creditos USDC",
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


async def credit_user(db, user_id: str, currency: str, amount) -> dict:
    """Acredita amount de creditos (USDT/USDC) al usuario, de forma atomica.

    Devuelve {"ok": True, "field": ..., "amount": ...} si acredito,
    o {"ok": False, "reason": ...} si la moneda no es soportada.

    NOTA: la idempotencia (no acreditar dos veces el mismo pago) se controla
    en el webhook via la coleccion crypto_deposits, ANTES de llamar aqui.
    """
    field = credit_field_for(currency)
    if not field:
        return {"ok": False, "reason": f"moneda no soportada: {currency}"}

    inc_value = Decimal128(to_credit_decimal(amount))
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {field: inc_value}},
    )
    return {"ok": True, "field": field, "amount": str(to_credit_decimal(amount))}
