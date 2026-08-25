"""
services/min_amount.py — Monto minimo real exigido por NOWPayments, en UN solo lugar.

POR QUE EXISTE ESTE MODULO
    El minimo que la app le muestra al usuario y el minimo contra el que el backend
    valida tienen que ser EL MISMO numero. Antes cada endpoint lo calculaba por su
    cuenta (o directamente no lo validaba) y era facil que se desincronizaran: el
    usuario veia un piso, mandaba ese monto y NOWPayments lo rechazaba igual.

    Todo el que necesite un minimo llama a `effective_min_amount()`. Nadie vuelve a
    aplicar el margen por afuera.

COMO SE ARMA EL MINIMO
    1. `nowpayments.get_min_amount()` da el minimo crudo del par (ver el docstring de
       esa funcion: se consulta contra `usd` porque nuestros pagos pasan por el
       exchange interno de NOWPayments).
    2. Se le suma un margen de seguridad del 10%. El minimo crudo se mueve con la
       comision de red del momento, asi que un valor consultado hace un minuto puede
       quedar corto cuando el pago se crea de verdad.
    3. Se toma el mayor entre eso y el piso de negocio (no aceptamos depositos ni
       envios ridiculamente chicos aunque la pasarela los permita).

CACHE
    El resultado se guarda unos minutos en memoria por (moneda+red). `/credits/networks`
    consulta el minimo de TODAS las redes habilitadas en cada carga de pantalla; sin
    cache eso serian N llamadas a NOWPayments por cada vez que alguien abre la
    pantalla de deposito. Los resultados de respaldo (cuando la API fallo) NO se
    cachean, para que una caida pasajera no quede pegada varios minutos.

    Es una cache de proceso: con varias instancias cada una tiene la suya, y se
    pierde en cada deploy. Alcanza de sobra para lo que hace.
"""

import math
import time
import logging

from services import nowpayments

logger = logging.getLogger(__name__)

# Margen de seguridad sobre el minimo crudo de NOWPayments (10%).
MIN_AMOUNT_SAFETY_MARGIN = 0.10

# Piso de negocio por moneda: por debajo de esto no aceptamos la operacion aunque
# NOWPayments la acepte. Tambien es el valor de respaldo si la API no responde.
BUSINESS_MIN_AMOUNT = {"usdt": 10.0, "usdc": 10.0}
DEFAULT_BUSINESS_MIN = 10.0

# Cuanto vive un minimo en cache (segundos).
CACHE_TTL_SECONDS = 300

# clave (moneda_key|pay_currency|fiat) -> (vence_en_epoch, resultado)
_cache: dict[str, tuple[float, dict]] = {}


def business_min_for(currency_key: str | None) -> float:
    """Piso de negocio de la moneda ('usdt' / 'usdc')."""
    if not currency_key:
        return DEFAULT_BUSINESS_MIN
    return BUSINESS_MIN_AMOUNT.get(currency_key.strip().lower(), DEFAULT_BUSINESS_MIN)


def with_margin(raw_min: float) -> float:
    """Aplica el margen de seguridad y redondea HACIA ARRIBA a 2 decimales.

    Hacia arriba a proposito: redondear hacia abajo se comeria parte del margen y
    volveriamos a mostrar un minimo que la pasarela puede rechazar.
    Ej.: 12.363435 -> 13.60
    """
    con_margen = float(raw_min) * (1.0 + MIN_AMOUNT_SAFETY_MARGIN)
    return math.ceil(con_margen * 100.0) / 100.0


def clear_cache() -> None:
    """Vacia la cache. Pensado para los tests."""
    _cache.clear()


async def effective_min_amount(
    pay_currency: str,
    *,
    currency_key: str | None = None,
    fiat_equivalent: str = "usd",
    use_cache: bool = True,
) -> dict:
    """Minimo efectivo para pagar en `pay_currency` (ticker de red, ej. 'usdttrc20').

    Devuelve siempre:
      {
        "min_amount":     float,  # CON margen — el unico que se muestra y se valida
        "min_amount_raw": float | None,  # lo que dijo NOWPayments, sin margen
        "source":         "nowpayments" | "fallback",
      }

    Nunca lanza: si NOWPayments no responde cae al piso de negocio, porque dejar al
    usuario sin poder operar es peor que exigirle un minimo aproximado.
    """
    ticker = (pay_currency or "").strip().lower()
    if currency_key is None:
        # 'usdttrc20' -> 'usdt', 'usdcerc20' -> 'usdc'
        currency_key = "usdt" if ticker.startswith("usdt") else ("usdc" if ticker.startswith("usdc") else None)
    piso = business_min_for(currency_key)

    clave = f"{currency_key}|{ticker}|{fiat_equivalent}"
    ahora = time.monotonic()
    if use_cache:
        entrada = _cache.get(clave)
        if entrada and entrada[0] > ahora:
            return dict(entrada[1])

    try:
        info = await nowpayments.get_min_amount(ticker, fiat_equivalent=fiat_equivalent)
        crudo = (info or {}).get("min_amount")
        if crudo is None:
            raise ValueError("sin min_amount en la respuesta")
        crudo = float(crudo)
        resultado = {
            "min_amount": max(with_margin(crudo), piso),
            "min_amount_raw": crudo,
            "source": "nowpayments",
        }
    except Exception as e:
        logger.warning(f"No se pudo obtener min-amount de NOWPayments para {ticker}: {e}")
        # No se cachea el respaldo: la proxima consulta vuelve a intentar contra la API.
        return {"min_amount": piso, "min_amount_raw": None, "source": "fallback"}

    _cache[clave] = (ahora + CACHE_TTL_SECONDS, dict(resultado))
    return resultado
