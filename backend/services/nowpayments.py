"""
services/nowpayments.py — Cliente de la API de NOWPayments (FD Transfers LLC).

Cubre lo necesario para el deposito de creditos:
  - status: comprobar que la API responde.
  - create_invoice: crear una factura hosteada (POST /v1/invoice), REDIRIGE fuera de la app.
    (ya no se usa en el flujo de deposito, se deja por si se necesita como respaldo)
  - create_payment: crear un pago directo (POST /v1/payment) — devuelve direccion + monto
    para mostrar como QR/copiar DENTRO de la app, sin redirigir a ninguna pagina externa.
  - verify_ipn_signature: verificar la firma HMAC-SHA512 del webhook (IPN).

SEGURIDAD
    Las claves se leen de variables de entorno, NUNCA van en el codigo:
      NOWPAYMENTS_API_KEY  -> header x-api-key para crear pagos/invoices
      NOWPAYMENTS_IPN_KEY  -> secreto para verificar la firma del webhook
"""

import os
import json
import hmac
import hashlib
import httpx

API_BASE = "https://api.nowpayments.io/v1"
API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
IPN_KEY = os.environ.get("NOWPAYMENTS_IPN_KEY", "")


def _headers() -> dict:
    return {"x-api-key": API_KEY, "Content-Type": "application/json"}


async def get_status() -> dict:
    """GET /v1/status — comprueba que la API responde."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_BASE}/status", headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_min_amount(currency: str, fiat_equivalent: str = "usd") -> dict:
    """GET /v1/min-amount — monto minimo pagable en currency (cubre la comision de red).
    Devuelve el JSON de NOWPayments, que incluye 'min_amount' (en la propia currency)
    y, si se pide fiat_equivalent, tambien el equivalente en esa moneda fiat.
    Se usa para avisarle al usuario el minimo ANTES de que NOWPayments rechace el pago
    con AMOUNT_MINIMAL_ERROR.
    """
    params = {
        "currency_from": currency,
        "currency_to": currency,
        "fiat_equivalent": fiat_equivalent,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_BASE}/min-amount", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


async def get_merchant_coins() -> list[str]:
    """GET /v1/merchant/coins — monedas/redes habilitadas en el dashboard de NOWPayments
    para este comercio (Coin Settings). Se usa para ofrecerle al usuario solo las redes
    que realmente estan activas en la cuenta, evitando ofrecer una red que despues falle
    al crear el pago."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API_BASE}/merchant/coins", headers=_headers())
        r.raise_for_status()
        data = r.json()
        return data.get("selectedCurrencies", []) or []


async def create_invoice(
    *,
    price_amount: float,
    price_currency: str,
    pay_currency: str,
    order_id: str,
    order_description: str,
    ipn_callback_url: str | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict:
    """Crea una factura hosteada. Devuelve el JSON de NOWPayments (incluye invoice_url).

    price_amount/price_currency: cuanto y en que moneda se valora el deposito.
    pay_currency: la cripto en que pagara el usuario (ej. 'usdttrc20', 'usdcerc20').
    order_id: identificador unico nuestro (para casar el webhook con el deposito).
    """
    payload = {
        "price_amount": price_amount,
        "price_currency": price_currency,
        "pay_currency": pay_currency,
        "order_id": order_id,
        "order_description": order_description,
    }
    if ipn_callback_url:
        payload["ipn_callback_url"] = ipn_callback_url
    if success_url:
        payload["success_url"] = success_url
    if cancel_url:
        payload["cancel_url"] = cancel_url

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}/invoice", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


async def create_payment(
    *,
    price_amount: float,
    price_currency: str,
    pay_currency: str,
    order_id: str,
    order_description: str,
    ipn_callback_url: str | None = None,
    is_fee_paid_by_user: bool = False,
) -> dict:
    """Crea un pago directo (POST /v1/payment) — SIN pagina hosteada externa.

    Para el flujo dentro de la app: el JSON de respuesta trae 'pay_address' (direccion
    a la que el usuario debe enviar la cripto) y 'pay_amount' (monto exacto), que se
    muestran como QR + texto para copiar. El usuario nunca sale de la app.

    is_fee_paid_by_user=True: la comision de servicio de NOWPayments se suma al
    pay_amount (el usuario la paga), en vez de descontarse de lo que se acredita al
    comercio. NOWPayments exige que el pago sea a tasa fija (fixed_rate) cuando se usa
    esta opcion, por eso se envia siempre junto con ella.

    Puede incluir 'payin_extra_id' (memo/tag) para redes que lo requieran, y 'network'
    (nombre de la red). El pago se confirma por el mismo webhook IPN que ya tenemos
    (mismos campos: order_id, payment_status, actually_paid).
    """
    payload = {
        "price_amount": price_amount,
        "price_currency": price_currency,
        "pay_currency": pay_currency,
        "order_id": order_id,
        "order_description": order_description,
    }
    if ipn_callback_url:
        payload["ipn_callback_url"] = ipn_callback_url
    if is_fee_paid_by_user:
        payload["is_fee_paid_by_user"] = True
        payload["fixed_rate"] = True

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}/payment", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


def verify_ipn_signature(raw_body: bytes, signature_header: str) -> str | None:
    """Verifica la firma HMAC-SHA512 del webhook (IPN).

    NOWPayments firma el body, pero el formato exacto de serializacion que
    usan internamente no esta garantizado igual al que reconstruimos nosotros
    con json.loads + json.dumps (numeros, acentos, orden de claves anidadas
    pueden variar entre su backend y Python). En vez de asumir un formato,
    probamos varias representaciones candidatas del mismo payload y aceptamos
    si el HMAC de alguna coincide con la firma recibida.

    Devuelve el nombre de la variante que coincidio ("raw", "sorted_ascii",
    "sorted_unicode") para que el caller pueda loguear cual es, o None si
    ninguna calzo (firma invalida o ausente).
    """
    if not IPN_KEY or not signature_header:
        return None
    sig = signature_header.strip()

    candidates: dict[str, bytes] = {"raw": raw_body}
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
        candidates["sorted_ascii"] = json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        candidates["sorted_unicode"] = json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except Exception:
        pass

    for name, body in candidates.items():
        digest = hmac.new(IPN_KEY.encode("utf-8"), body, hashlib.sha512).hexdigest()
        if hmac.compare_digest(digest, sig):
            return name
    return None
