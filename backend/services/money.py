"""
services/money.py — Utilidades de dinero con precisión exacta (Decimal).

OBJETIVO
    Centralizar la conversión y el redondeo de montos de dinero usando
    decimal.Decimal (precisión exacta) y bson.Decimal128 (para guardar en Mongo),
    evitando los errores de redondeo del tipo float (ej. 0.1 + 0.2 = 0.30000000000000004).

ESTADO (Fase 1)
    Este módulo está AISLADO: define las funciones pero todavía NO se usa en
    ninguna ruta ni servicio. No cambia el comportamiento de la aplicación.
    Las siguientes fases lo irán conectando, un flujo de dinero a la vez.

NOTA SOBRE DECIMALES
    - Monedas fiat (RIS, VES, BRL, USD): por defecto 2 decimales.
    - BTC: 8 decimales. USDT: usar los decimales que corresponda.
    Por eso casi todas las funciones aceptan un parámetro places.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from bson.decimal128 import Decimal128

# Cero reutilizable
ZERO = Decimal("0")


def to_decimal(value) -> Decimal:
    """Convierte cualquier valor (float, int, str, Decimal, Decimal128, None) a Decimal.

    - None  -> Decimal('0')
    - float -> se convierte vía str() para NO arrastrar el ruido binario del float.
    - Decimal128 (lo que devuelve Mongo) -> su Decimal interno.
    - Valores inválidos -> Decimal('0') (seguro, no lanza excepción).
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip() or "0")
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def quantize_money(value, places: int = 2) -> Decimal:
    """Redondea un monto a places decimales con redondeo bancario estándar (HALF_UP)."""
    exp = Decimal(1).scaleb(-places)  # places=2 -> Decimal('0.01')
    return to_decimal(value).quantize(exp, rounding=ROUND_HALF_UP)


def to_decimal128(value, places: int = 2) -> Decimal128:
    """Convierte un monto a Decimal128 para GUARDAR en MongoDB (ya redondeado)."""
    return Decimal128(quantize_money(value, places))


def from_db(value, places: int = 2) -> Decimal:
    """Lee un monto que puede venir como float (datos viejos) o Decimal128 (datos nuevos)
    y devuelve siempre un Decimal redondeado. Es la base de la "lectura tolerante" (Fase 2)."""
    return quantize_money(value, places)


def to_float(value, places: int = 2) -> float:
    """Convierte un monto a float redondeado, para respuestas JSON / compatibilidad con el frontend.
    El cálculo interno se mantiene en Decimal; esto es solo para mostrar."""
    return float(quantize_money(value, places))


# --- Aritmética segura (siempre en Decimal) ---

def money_add(*values, places: int = 2) -> Decimal:
    """Suma varios montos en Decimal y redondea el resultado."""
    total = ZERO
    for v in values:
        total += to_decimal(v)
    return quantize_money(total, places)


def money_sub(a, b, places: int = 2) -> Decimal:
    """Resta b de a en Decimal y redondea el resultado."""
    return quantize_money(to_decimal(a) - to_decimal(b), places)


def money_mul(value, factor, places: int = 2) -> Decimal:
    """Multiplica un monto por un factor (ej. una tasa) en Decimal y redondea."""
    return quantize_money(to_decimal(value) * to_decimal(factor), places)


def is_gte(a, b) -> bool:
    """Compara dos montos como Decimal: ¿a >= b? (útil para validar saldo suficiente)."""
    return to_decimal(a) >= to_decimal(b)
