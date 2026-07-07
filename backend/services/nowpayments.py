"""
services/nowpayments.py — Cliente de la API de NOWPayments (FD Transfers LLC).

Solo cubre lo necesario para el deposito de creditos:
  - status: comprobar que la API responde.
  - create_invoice: crear una factura hosteada (POST /v1/invoice) y obtener invoice_url.
  - verify_ipn_signature: verificar la firma HMAC-SHA512 del webhook (IPN).

SEGURIDAD
    Las claves se leen de variables de entorno, NUNCA van en el codigo:
      NOWPAYMENTS_API_KEY  -> header x-api-key para crear invoices
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


def verify_ipn_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verifica la firma HMAC-SHA512 del webhook IPN.

    NOWPayments firma el JSON ORDENADO POR CLAVES con el IPN secret.
    raw_body: cuerpo crudo del request (bytes) tal cual llego.
    signature_header: valor del header 'x-nowpayments-sig'.
    """
    if not IPN_KEY or not signature_header:
        return False
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False

    # Reordenar por claves (sorted) y serializar de forma estable
    sorted_body = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(
        IPN_KEY.encode("utf-8"),
        sorted_body.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()

    # Comparacion en tiempo constante (evita ataques de temporizacion)
    return hmac.compare_digest(digest, signature_header.strip())
