"""
routes/credits.py — Endpoints de creditos cripto (deposito via NOWPayments).

Flujo DENTRO de la app (sin redireccion externa):
  GET  /api/credits/networks               -> redes disponibles para depositar una moneda,
                                                cada una con su monto minimo real.
  GET  /api/credits/min-amount              -> monto minimo real para moneda+red elegidas.
  POST /api/credits/deposit                 -> crea un pago directo (create_payment) y
                                                devuelve pay_address/pay_amount para
                                                mostrar como QR + copiar, sin salir de la app.
  GET  /api/credits/deposit/{order_id}/status -> polling del estado (lee crypto_deposits,
                                                que el webhook va actualizando).
  POST /api/credits/webhook                 -> IPN de NOWPayments. Acredita balance_usdt/
                                                balance_usdc (NUNCA balance_ris) al confirmarse.

Guarda cada intento en la coleccion crypto_deposits con estado 'pending'.
Cumplimiento: corre assert_payment_allowed (IP + declaracion) ANTES de crear el cobro.
"""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from database import db
from routes.dependencies import get_current_user, sin_transacciones_personales
from models.user import User
from services.geo_restrictions import assert_payment_allowed
from services import nowpayments
from services.credits import normalize_currency, CREDIT_LABELS, credit_user
from services.min_amount import effective_min_amount
from services.notifications import create_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credits", tags=["credits"])

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://www.risappbr.com")

DEFAULT_NETWORK_TICKER = {
    "usdt": "usdttrc20",
    "usdc": "usdc",
}

# El piso de negocio (antes MINAMOUNT_FALLBACK aca) y el calculo del minimo real
# —margen de seguridad incluido— viven ahora en services/min_amount.py, para que el
# deposito, el envio y el frontend usen exactamente el mismo numero y no se puedan
# desincronizar.

NETWORK_LABELS = {
    "trc20": "Tron (TRC20)",
    "erc20": "Ethereum (ERC20)",
    "bsc":   "BNB Smart Chain (BEP20)",
    "sol":   "Solana",
    "matic": "Polygon",
    "arb":   "Arbitrum",
    "base":  "Base",
    "ton":   "TON",
    "op":    "Optimism",
    "avax":  "Avalanche",
}

def networklabel(ticker: str, currency_key: str) -> str:
    suffix = ticker[len(currency_key):] if ticker.lower().startswith(currency_key) else ticker
    if not suffix:
        return "Ethereum (ERC20)"
    return NETWORK_LABELS.get(suffix.lower(), suffix.upper())


ERROR_PAGO_GENERICO = "No se pudo iniciar el pago. Intenta de nuevo."


def _detalle_error_pago(exc: Exception) -> str:
    """Detalle del 502 cuando NOWPayments rechaza el pago.

    Si el cuerpo del error trae un "message" (ej. "amountTo is too small"), se
    incluye: sin eso el usuario solo veia "no se pudo iniciar el pago" y no habia
    forma de saber por que, ni siquiera mirando la pantalla. Si no se puede
    parsear, queda el mensaje generico de siempre.
    """
    mensaje = nowpayments.mensaje_de_error(exc)
    if not mensaje:
        return ERROR_PAGO_GENERICO
    return f"{ERROR_PAGO_GENERICO} Motivo de la pasarela: {mensaje}"


class DepositRequest(BaseModel):
    currency: str
    amount: float
    declared_not_restricted: bool = False
    network: str | None = None


@router.get("/networks")
async def list_networks(
    currency: str = Query(..., description="'usdt' o 'usdc'"),
    current_user: User = Depends(get_current_user),
):
    key = normalize_currency(currency)
    if key not in DEFAULT_NETWORK_TICKER:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    default_ticker = DEFAULT_NETWORK_TICKER[key]
    try:
        coins = await nowpayments.get_merchant_coins()
        matches = [c for c in coins if c.lower().startswith(key)]
        if not matches:
            raise ValueError("el comercio no tiene ninguna red habilitada para esta moneda")
    except Exception as e:
        logger.warning(f"No se pudo obtener redes habilitadas de NOWPayments para {key}: {e}")
        matches = [default_ticker]
    if default_ticker not in matches:
        matches.append(default_ticker)

    # Minimo real de cada red, en paralelo (una consulta por red, todas a la vez) y
    # cacheado unos minutos en services/min_amount.py: si no, cada vez que alguien
    # abre la pantalla de deposito le pegariamos N veces seguidas a NOWPayments.
    minimos = await asyncio.gather(
        *[effective_min_amount(t, currency_key=key) for t in matches]
    )

    networks = [
        {
            "ticker": t,
            "label": networklabel(t, key),
            "is_default": t == default_ticker,
            "min_amount": m["min_amount"],
            "min_amount_raw": m["min_amount_raw"],
            "min_amount_source": m["source"],
        }
        for t, m in zip(matches, minimos)
    ]
    # De menor a mayor minimo: la red mas barata de usar aparece primero, asi el
    # usuario elige viendo el minimo de todas y no se entera despues de elegir.
    networks.sort(key=lambda n: (n["min_amount"], n["label"]))
    return {"currency": key, "networks": networks, "default_ticker": default_ticker}


@router.get("/min-amount")
async def get_min_amount(
    currency: str = Query(..., description="'usdt' o 'usdc'"),
    network: str | None = Query(None, description="ticker de red, ej. 'usdttrc20'"),
    current_user: User = Depends(get_current_user),
):
    key = normalize_currency(currency)
    if key not in DEFAULT_NETWORK_TICKER:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    pay_currency = (network or DEFAULT_NETWORK_TICKER[key]).strip().lower()
    if not pay_currency.startswith(key):
        raise HTTPException(status_code=400, detail="La red elegida no corresponde a la moneda seleccionada.")
    # `min_amount` ya viene con el margen de seguridad aplicado: es el unico valor
    # que el frontend debe mostrar y contra el que el backend valida. `min_amount_raw`
    # es informativo (lo que dijo NOWPayments), NUNCA se le vuelve a aplicar margen.
    info = await effective_min_amount(pay_currency, currency_key=key)
    return {
        "currency": key,
        "network": pay_currency,
        "min_amount": info["min_amount"],
        "min_amount_raw": info["min_amount_raw"],
        "source": info["source"],
    }


@router.post("/deposit", dependencies=[Depends(sin_transacciones_personales)])
async def create_deposit(
    data: DepositRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    assert_payment_allowed(request, declared_not_restricted=data.declared_not_restricted)
    key = normalize_currency(data.currency)
    if key not in DEFAULT_NETWORK_TICKER:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa USDT o USDC.")
    if not data.amount or data.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    pay_currency = (data.network or DEFAULT_NETWORK_TICKER[key]).strip().lower()
    if not pay_currency.startswith(key):
        raise HTTPException(status_code=400, detail="La red elegida no corresponde a la moneda seleccionada.")
    # Mismo minimo (con margen) que devuelve /credits/min-amount y que muestra la
    # pantalla: se consulta desde el mismo helper para que no puedan desincronizarse.
    min_info = await effective_min_amount(pay_currency, currency_key=key)
    min_amount = min_info["min_amount"]
    if float(data.amount) < float(min_amount):
        raise HTTPException(
            status_code=400,
            detail=f"El monto mínimo para depositar {CREDIT_LABELS.get(key, key)} es {min_amount:.2f}.",
        )
    order_id = f"credit_{key}_{current_user.user_id}_{uuid.uuid4().hex[:12]}"
    deposit_doc = {
        "order_id": order_id,
        "user_id": current_user.user_id,
        "currency": key,
        "pay_currency": pay_currency,
        "amount": float(data.amount),
        "status": "pending",
        "credited": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.crypto_deposits.insert_one(deposit_doc)
    try:
        payment = await nowpayments.create_payment(
            price_amount=float(data.amount),
            price_currency="usd",
            pay_currency=pay_currency,
            order_id=order_id,
            order_description=f"Deposito de {CREDIT_LABELS.get(key, key)}",
            ipn_callback_url=f"{PUBLIC_BASE_URL}/api/credits/webhook",
            is_fee_paid_by_user=True,
        )
    except Exception as e:
        logger.error(f"NOWPayments create_payment failed for {order_id}: {e}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id}, {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=502, detail=_detalle_error_pago(e))
    pay_address = payment.get("pay_address")
    pay_amount = payment.get("pay_amount")
    if not pay_address or not pay_amount:
        logger.error(f"NOWPayments sin pay_address/pay_amount para {order_id}: {payment}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id}, {"$set": {"status": "error"}}
        )
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")
    payin_extra_id = payment.get("payin_extra_id")
    network_name = payment.get("network")
    pay_amount_float = float(pay_amount)
    credit_amount = float(data.amount)
    fee_amount = round(pay_amount_float - credit_amount, 8)
    if fee_amount < 0:
        fee_amount = 0.0
    fee_percentage = round((fee_amount / credit_amount) * 100, 2) if credit_amount else 0.0
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "payment_id": payment.get("payment_id"),
                "pay_address": pay_address,
                "pay_amount": pay_amount,
                "payin_extra_id": payin_extra_id,
                "network": network_name,
                "fee_amount": fee_amount,
                "credit_amount": credit_amount,
            }
        },
    )
    return {
        "order_id": order_id,
        "pay_address": pay_address,
        "pay_amount": pay_amount,
        "pay_currency": pay_currency,
        "payin_extra_id": payin_extra_id,
        "network": network_name,
        "network_label": networklabel(pay_currency, key),
        "credit_amount": credit_amount,
        "fee_amount": fee_amount,
        "fee_percentage": fee_percentage,
    }


@router.get("/deposit/{order_id}/status")
async def get_deposit_status(
    order_id: str,
    current_user: User = Depends(get_current_user),
):
    deposit = await db.crypto_deposits.find_one(
        {"order_id": order_id, "user_id": current_user.user_id}, {"_id": 0}
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposito no encontrado")
    return {
        "order_id": order_id,
        "status": deposit.get("status"),
        "credited": deposit.get("credited", False),
        "currency": deposit.get("currency"),
        "amount": deposit.get("amount"),
    }


TERMINALNO_CREDIT_STATUSES = {"failed", "expired", "refunded"}


@router.post("/webhook")
async def nowpayments_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")
    if not nowpayments.verify_ipn_signature(raw_body, signature):
        logger.warning("NOWPayments webhook: firma invalida o ausente")
        raise HTTPException(status_code=401, detail="invalid_signature")
    try:
        payload = json.loads(raw_body or b"{}")
    except Exception:
        payload = {}
    logger.info(f"NOWPayments webhook recibido: {payload}")
    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    payment_id = payload.get("payment_id")
    if not order_id:
        logger.warning("NOWPayments webhook sin order_id")
        return {"received": True, "error": "no_order_id"}
    deposit = await db.crypto_deposits.find_one({"order_id": order_id})
    if not deposit:
        logger.warning(f"NOWPayments webhook: order_id {order_id} no encontrado en crypto_deposits")
        return {"received": True, "error": "deposit_not_found"}
    await db.crypto_deposits.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "last_payment_status": payment_status,
                "payment_id": payment_id,
                "webhook_last_seen": datetime.now(timezone.utc),
            }
        },
    )
    if payment_status in TERMINALNO_CREDIT_STATUSES:
        await db.crypto_deposits.update_one(
            {"order_id": order_id, "credited": False},
            {"$set": {"status": payment_status}},
        )
        return {"received": True, "processed": False, "status": payment_status}
    if payment_status != "finished":
        return {"received": True, "processed": False, "status": payment_status}
    claimed = await db.crypto_deposits.find_one_and_update(
        {"order_id": order_id, "credited": False},
        {
            "$set": {
                "credited": True,
                "status": "finished",
                "credited_at": datetime.now(timezone.utc),
            }
        },
    )
    if not claimed:
        logger.info(f"NOWPayments webhook: order_id {order_id} ya estaba acreditado, ignorando duplicado")
        return {"received": True, "already_processed": True}
    actually_paid = payload.get("actually_paid")
    credit_amount = actually_paid if actually_paid else claimed.get("amount")
    result = await credit_user(
        db, claimed["user_id"], claimed["currency"], credit_amount,
        movement_type="deposito_cripto",
        reference_kind="crypto_deposit",
        reference_id=order_id,
        actor_type="webhook",
        notes="Acreditado via webhook NOWPayments",
    )
    if not result.get("ok"):
        logger.error(f"NOWPayments webhook: fallo al acreditar order_id {order_id}: {result}")
        await db.crypto_deposits.update_one(
            {"order_id": order_id},
            {"$set": {"credited": False, "credit_error": result.get("reason")}},
        )
        return {"received": True, "error": "credit_failed"}
    logger.info(
        f"NOWPayments: acreditado {credit_amount} {claimed['currency']} "
        f"a user {claimed['user_id']} (order {order_id})"
    )
    try:
        await create_notification(
            user_id=claimed["user_id"],
            title="Deposito confirmado",
            message=f"Se acreditaron {credit_amount} {CREDIT_LABELS.get(claimed['currency'], claimed['currency'])} a tu cuenta.",
            notification_type="credit_deposit",
            data={"order_id": order_id, "currency": claimed["currency"], "amount": str(credit_amount)},
        )
    except Exception as e:
        logger.warning(f"NOWPayments webhook: no se pudo enviar notificacion: {e}")
    return {"received": True, "processed": True, "status": "finished"}



# Monedas de credito soportadas, en el orden en que se muestran.
CREDIT_KEYS = ("usdt", "usdc")


def _currency_input_variants(keys) -> list:
    """Tickers tal como pueden estar guardados en `transactions.currency_input`.

    El codigo actual guarda siempre mayuscula (`key.upper()`), pero hay envios
    viejos y datos migrados que quedaron en minuscula, asi que el $match acepta
    las dos formas en vez de asumir una."""
    variants = []
    for k in keys:
        variants.extend([k.upper(), k.lower()])
    return variants


def build_history_pipeline(user_id: str, key, skip: int, limit: int) -> list:
    """Pipeline del historial cripto unificado (depositos + envios).

    Se construye aparte del handler para poder testearlo sin Mongo. Arranca en
    `crypto_deposits`, le suma `transactions` (envios USDT/USDC) con $unionWith,
    ordena todo junto por fecha descendente y usa $facet para devolver, en una
    sola vuelta, la pagina pedida y el total combinado. Asi el frontend sigue
    recibiendo {total, items} sin tener que reconciliar dos paginaciones.

    Requiere MongoDB >= 4.4 ($unionWith).
    """
    keys = [key] if key else list(CREDIT_KEYS)

    deposit_match = {"user_id": user_id}
    if key:
        deposit_match["currency"] = key
    else:
        deposit_match["currency"] = {"$in": list(CREDIT_KEYS)}

    send_match = {
        "user_id": user_id,
        "type": "withdrawal",
        "currency_input": {"$in": _currency_input_variants(keys)},
    }

    # Forma comun de un item de deposito.
    deposit_projection = {
        "_id": 0,
        "kind": {"$literal": "deposit"},
        "order_id": 1,
        "currency": 1,
        "date": "$created_at",
        "created_at": 1,
        "amount": 1,
        "credit_amount": 1,
        "credited": 1,
        "credited_at": 1,
        "status": 1,
        "network": 1,
        "pay_currency": 1,
        "fee_amount": 1,
        "source": 1,
    }

    # Forma comun de un item de envio. `refunded_to_balance` se normaliza a
    # booleano y el monto devuelto sale siempre por `refund_amount`, porque los
    # documentos viejos guardaban el monto (float) directamente en
    # `refunded_to_balance` y el frontend no tiene por que conocer esa historia.
    send_projection = {
        "_id": 0,
        "kind": {"$literal": "send"},
        "transaction_id": 1,
        "display_id": 1,
        "currency": {"$toLower": "$currency_input"},
        "date": "$created_at",
        "created_at": 1,
        "completed_at": 1,
        "amount": "$amount_input",
        "amount_output": 1,
        "currency_output": 1,
        "rate": 1,
        "status": 1,
        "funded_from": 1,
        "network": "$pay_currency",
        "beneficiary_data": 1,
        "rejected_reason": 1,
        "refund_amount": {"$ifNull": ["$refund_amount", "$_legacy_refund_amount"]},
        "refunded_to_balance": {
            "$gt": [
                {"$ifNull": [{"$ifNull": ["$refund_amount", "$_legacy_refund_amount"]}, 0]},
                0,
            ]
        },
        "refunded_to_balance_field": 1,
    }

    return [
        {"$match": deposit_match},
        {"$project": deposit_projection},
        {
            "$unionWith": {
                "coll": "transactions",
                "pipeline": [
                    {"$match": send_match},
                    # Compatibilidad hacia atras: antes el monto devuelto vivia
                    # en `refunded_to_balance` como numero.
                    {
                        "$addFields": {
                            "_legacy_refund_amount": {
                                "$cond": [
                                    {
                                        "$in": [
                                            {"$type": "$refunded_to_balance"},
                                            ["double", "int", "long", "decimal"],
                                        ]
                                    },
                                    "$refunded_to_balance",
                                    None,
                                ]
                            }
                        }
                    },
                    {"$project": send_projection},
                ],
            }
        },
        {"$sort": {"date": -1}},
        {
            "$facet": {
                "items": [{"$skip": skip}, {"$limit": limit}],
                "total": [{"$count": "count"}],
            }
        },
    ]


@router.get("/history")
async def get_credit_history(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    currency: str = Query("all", description="usdt | usdc | all"),
    current_user: User = Depends(get_current_user),
):
    """Historial cripto unificado (USDT/USDC) del usuario autenticado.

    Trae en una sola lista, ordenada por fecha descendente:
      - depositos (`crypto_deposits`): NOWPayments + acreditaciones manuales de
        soporte, con kind="deposit";
      - envios (`transactions` type=withdrawal en USDT/USDC), con kind="send",
        incluyendo si el envio termino devuelto a saldo.

    Nunca mezcla con balance_ris ni con /transactions — sigue siendo el
    historial de la billetera cripto, ahora completo en vez de solo depositos.
    """
    key = normalize_currency(currency) if currency and currency != "all" else None
    if currency and currency != "all" and key is None:
        raise HTTPException(status_code=400, detail="Moneda no soportada. Usa usdt, usdc o all.")

    skip = (page - 1) * limit
    pipeline = build_history_pipeline(current_user.user_id, key, skip, limit)

    result = await db.crypto_deposits.aggregate(pipeline).to_list(1)
    faceted = result[0] if result else {}
    items = faceted.get("items") or []
    total_bucket = faceted.get("total") or []
    total = total_bucket[0].get("count", 0) if total_bucket else 0

    for it in items:
        it["currency_label"] = CREDIT_LABELS.get(it.get("currency"), it.get("currency"))

    return {"total": total, "page": page, "limit": limit, "items": items}
