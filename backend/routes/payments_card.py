"""
Card Payment routes — Mercado Pago Checkout Bricks integration.

Flow:
  1. Frontend renders Card Payment Brick, tokenizes the card client-side.
  2. Frontend POSTs the token + amount + payer info to /payments/card/process.
  3. Backend validates amount, calls MP /v1/payments with X-Idempotency-Key.
  4. If status="approved":
        - Credit RIS to user (same rule as PIX: 1 BRL = 1 RIS).
        - Credit Mercado Pago bank in accounting (NET, after fee).
        - Register fee in gateway_fee_ledger (accounting v11).
        - Send notification + email.

Business rules (per user spec, 2026-05-22):
  - Single payment only (installments=1).
  - Min/max: configurables desde el panel (`tarjeta_minimo`, `tarjeta_maximo`).
    De fabrica, R$5 y R$5000.
  - Customer pays the fee (added on top of the desired RIS amount).
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from database import db
from services import recarga_abierta
from models.user import User
from models.escalar import Escalar
from routes.dependencies import get_current_user, sin_transacciones_personales
from services.notifications import create_notification
from services import bancos, configuracion, pagos_una_sola_vez, saldos
from services.limits import validate_card_amount
from services.money import para_mostrar, to_float

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/card", tags=["payments-card"])

MP_API_BASE = "https://api.mercadopago.com"

# Default fee config (Mercado Pago Brazil — public rates 2026)
# Stored in app_settings.card_fees so admin can override later (GatewayConfig P3).
DEFAULT_CARD_FEES = {
    "credit_pct": 4.49,   # % over transaction_amount
    "debit_pct": 1.99,
    "flat_brl": 0.40,     # fixed cents per transaction
}

# Los limites de esta via ya no estan escritos aca: viven en el catalogo de
# `services/configuracion.py` (`tarjeta_minimo` y `tarjeta_maximo`) y se cambian
# desde el panel del super administrador, sin desplegar.
#
# La validacion en si la hace `services/limits.validate_card_amount`, para que
# este archivo no tenga su propia copia de la regla — que es como este par de
# numeros termino siendo distinto al de PIX sin que nadie lo decidiera.


# ─── Schemas ──────────────────────────────────────────────────────────────
class PayerIdentification(BaseModel):
    type: str = "CPF"
    number: str


class CardPaymentInput(BaseModel):
    token: str
    amount_ris: float = Field(..., gt=0, description="RIS the user wants to receive (=BRL netto)")
    payment_method_id: str
    payment_type_id: str = Field(default="credit_card", description="credit_card | debit_card")
    payer_email: EmailStr
    identification: PayerIdentification
    issuer_id: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────
async def _get_card_fees() -> dict:
    """Read card fee config from app_settings (with sensible defaults)."""
    doc = await db.app_settings.find_one({"key": "card_fees"})
    if not doc:
        return DEFAULT_CARD_FEES
    return {**DEFAULT_CARD_FEES, **(doc.get("value") or {})}


def _calc_fee(amount_brl_net: float, payment_type_id: str, fees: dict) -> float:
    """Compute total MP fee given the NET amount the user wants to receive."""
    pct = fees["debit_pct"] if payment_type_id == "debit_card" else fees["credit_pct"]
    return round(amount_brl_net * (pct / 100.0) + fees["flat_brl"], 2)


async def _credit_mp_bank_card(payment_id: str, client_name: str, amount_brl_net: float):
    """Same logic as gestor_pix._credit_mercadopago_bank but for cards.
    Imports kept local to avoid circular imports."""
    # Un `upsert`, no un `find_one` seguido de un `insert_one`. Este camino y el
    # de la tarjeta creaban la cuenta por su cuenta, cada uno con su propio
    # `bank_id` al azar: entrando los dos a la vez quedaban DOS filas
    # "Mercado Pago" en BRL con el saldo repartido. Ver services/bancos.py.
    bank = await bancos.asegurar_pasarela(
        db, name="Mercado Pago", currency="BRL", prefijo_id="mp")

    # Igual que en Mercado Pago: `float()` sobre un Decimal128 levanta TypeError.
    from services.money import to_float as _to_float
    _mov = await bancos.ajustar(db, bank["bank_id"], amount_brl_net)
    new_balance = _to_float(_mov["saldo_nuevo"])
    await db.bank_ledger.insert_one({
        "bank_id": bank["bank_id"],
        "bank_name": "Mercado Pago",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "type": "entrada",
        "concept": f"Recarga Tarjeta: {client_name} (MP {payment_id[:12]})",
        "amount": float(amount_brl_net),
        "balance_after": new_balance,
        "reference": str(payment_id),
        "notes": "Recarga automática vía Mercado Pago (Tarjeta)",
        "source": "mercadopago_card",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _register_card_fee(payment_id: str, fee_brl: float, gross_brl: float):
    """Write fee to gateway_fee_ledger (Accounting Engine v11)."""
    await db.gateway_fee_ledger.insert_one({
        "ledger_id": f"gfl_card_{uuid.uuid4().hex[:10]}",
        "gateway": "mercadopago",
        "payment_method": "card",
        "external_payment_id": str(payment_id),
        "currency": "BRL",
        "gross_amount": float(gross_brl),
        "fee_deducted": float(fee_brl),
        "net_amount": round(gross_brl - fee_brl, 2),
        "is_reconciled_with_invoice": False,
        "hidden_from_admin": False,
        "created_at": datetime.now(timezone.utc),
    })


# ─── Endpoints ────────────────────────────────────────────────────────────

class ComisionesDeTarjeta(BaseModel):
    """Las tres comisiones que se le cobran al cliente, y nada más.

    `_get_card_fees` junta las de fábrica con TODO lo que haya guardado en
    `app_settings.card_fees`, y esta ruta lo devolvía tal cual: cualquier
    clave que alguien agregue ahí —una nota sobre lo que se negoció con el
    procesador, por ejemplo— le llegaba a cada cliente que abría el pago con
    tarjeta. Comprobado corriéndolo. El cálculo interno sigue leyendo el
    diccionario entero; lo que sale, sólo esto.
    """
    credit_pct: Escalar = None
    debit_pct: Escalar = None
    flat_brl: Escalar = None


class ConfigDeTarjeta(BaseModel):
    public_key: Escalar = None
    fees: Optional[ComisionesDeTarjeta] = None
    min_amount_brl: Escalar = None
    max_amount_brl: Escalar = None
    locale: Escalar = None
    currency: Escalar = None


@router.get("/config", response_model=ConfigDeTarjeta)
async def get_card_config(current_user: User = Depends(get_current_user)):
    """Frontend bootstrap: public key + fee schedule + limits."""
    fees = await _get_card_fees()
    return {
        "public_key": os.environ.get("MERCADOPAGO_PUBLIC_KEY"),
        # Recortadas acá también, y no sólo en el contrato: una capa por sí
        # sola no se sabe si anda. Ver `ComisionesDeTarjeta`.
        "fees": {k: fees.get(k) for k in DEFAULT_CARD_FEES},
        "min_amount_brl": to_float(await configuracion.leer(db, "tarjeta_minimo")),
        "max_amount_brl": to_float(await configuracion.leer(db, "tarjeta_maximo")),
        "locale": "pt-BR",
        "currency": "BRL",
    }


@router.post("/quote", dependencies=[Depends(sin_transacciones_personales)])
async def quote_card_payment(
    amount_ris: float,
    payment_type_id: str = "credit_card",
    current_user: User = Depends(get_current_user),
):
    """Preview the total amount that will be charged on the card,
    given the desired RIS recharge amount."""
    # También la cotización. Dejarla abierta haría que la pantalla dibuje el
    # total a cobrar y recién al apretar diga que no se puede: el usuario
    # completa todo el formulario de la tarjeta para nada.
    await recarga_abierta.exigir_abierta(db)
    error_monto = await validate_card_amount(db, amount_ris)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    fees = await _get_card_fees()
    fee = _calc_fee(amount_ris, payment_type_id, fees)
    total = round(amount_ris + fee, 2)
    return {
        "amount_ris": amount_ris,
        "amount_brl_net": amount_ris,
        "fee_brl": fee,
        "total_charged_brl": total,
        "payment_type_id": payment_type_id,
    }


@router.post("/process", dependencies=[Depends(sin_transacciones_personales)])
async def process_card_payment(
    body: CardPaymentInput,
    current_user: User = Depends(get_current_user),
):
    """Submit the tokenized card to Mercado Pago and credit RIS on approval."""
    # ── Validation ───────────────────────────────────────────────────────
    # LA CARGA DE SALDO, ANTES DE CUALQUIER OTRA COSA QUE CUESTE.
    #
    #   La empresa no custodia dinero de terceros ni ofrece recarga. La regla
    #   vive en `services/recarga_abierta.py`, no acá: son cuatro puertas, y la
    #   condición copiada en cada una es la que un día se actualiza en tres.
    await recarga_abierta.exigir_abierta(db)
    error_monto = await validate_card_amount(db, body.amount_ris)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    if body.payment_type_id not in ("credit_card", "debit_card"):
        raise HTTPException(status_code=400, detail="Tipo de tarjeta inválido")

    if current_user.verification_status != "verified":
        raise HTTPException(
            status_code=403,
            detail="Debes verificar tu cuenta antes de pagar con tarjeta",
        )

    access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
    if not access_token:
        raise HTTPException(status_code=500, detail="MP no configurado")

    # ── Fee calculation ──────────────────────────────────────────────────
    fees = await _get_card_fees()
    fee_brl = _calc_fee(body.amount_ris, body.payment_type_id, fees)
    total_brl_charged = round(body.amount_ris + fee_brl, 2)

    # ── Call MP Payments API ─────────────────────────────────────────────
    idempotency_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }
    payload = {
        "transaction_amount": total_brl_charged,
        "token": body.token,
        "description": f"Recarga RIS {body.amount_ris:.2f} BRL",
        "installments": 1,
        "payment_method_id": body.payment_method_id,
        "payer": {
            "email": body.payer_email,
            "identification": {
                "type": body.identification.type,
                "number": body.identification.number,
            },
        },
        "capture": True,
        "binary_mode": True,
        "metadata": {
            "user_id": current_user.user_id,
            "origin": "card_brick",
            "amount_ris": body.amount_ris,
            "fee_brl": fee_brl,
        },
        "external_reference": f"user_{current_user.user_id}_{uuid.uuid4().hex[:8]}",
    }
    if body.issuer_id:
        payload["issuer_id"] = body.issuer_id

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            mp_resp = await client.post(
                f"{MP_API_BASE}/v1/payments", json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.error(f"MP API network error: {exc}")
        raise HTTPException(status_code=502, detail="Error conectando con Mercado Pago")

    mp_data = {}
    try:
        mp_data = mp_resp.json()
    except Exception:
        pass

    if mp_resp.status_code >= 400:
        logger.error(f"MP API error {mp_resp.status_code}: {mp_data}")
        raise HTTPException(
            status_code=400,
            detail=mp_data.get("message") or "Error procesando el pago en Mercado Pago",
        )

    payment_id = str(mp_data.get("id") or "")
    status_mp = mp_data.get("status")
    status_detail = mp_data.get("status_detail", "")

    logger.info(
        f"MP card payment created: id={payment_id} status={status_mp} "
        f"detail={status_detail} user={current_user.user_id}"
    )

    # Persist attempt
    await db.card_payments.insert_one({
        "payment_id": payment_id,
        "user_id": current_user.user_id,
        "amount_ris": body.amount_ris,
        "amount_brl_net": body.amount_ris,
        "fee_brl": fee_brl,
        "total_charged_brl": total_brl_charged,
        "payment_method_id": body.payment_method_id,
        "payment_type_id": body.payment_type_id,
        "status": status_mp,
        "status_detail": status_detail,
        "mp_response": mp_data,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc),
    })

    # ── Process side effects on approval ─────────────────────────────────
    if status_mp == "approved" and payment_id:
        # Reclamar el evento ANTES de acreditar. Antes esto era un `find_one`
        # y después un `insert_one`: entre los dos hay una ventana, y el
        # webhook de Mercado Pago entra justo ahí —es el caso para el que este
        # guard fue escrito—, con lo cual los dos leían que no había nada y los
        # dos acreditaban. Ver services/pagos_una_sola_vez.py.
        if await pagos_una_sola_vez.reclamar(
                db, f"card_{payment_id}", proveedor="mercadopago_card"):

            # 1. Credit RIS to user, y asentar en la misma operación.
            _card_mov = await saldos.mover(
                db, current_user.user_id, body.amount_ris,
                movimiento="pago_tarjeta",
                reference_kind="card_payment",
                reference_id=payment_id,
                actor_type="user",
                actor_id=current_user.user_id,
                notes="Recarga con tarjeta",
            )
            _card_user = _card_mov["usuario"]

            # 2. Notification
            await create_notification(
                user_id=current_user.user_id,
                title="Recibimos tu pago con tarjeta",
                message=f"Acreditamos R$ {para_mostrar(body.amount_ris)} en tu saldo.",
                notification_type="card_received",
                data={"payment_id": payment_id, "amount": body.amount_ris},
            )

            # 3. Accounting (Mercado Pago bank + gateway fee ledger)
            try:
                await _credit_mp_bank_card(
                    payment_id=payment_id,
                    client_name=current_user.name or "Cliente",
                    amount_brl_net=body.amount_ris,
                )
                await _register_card_fee(
                    payment_id=payment_id,
                    fee_brl=fee_brl,
                    gross_brl=total_brl_charged,
                )
            except Exception as exc:
                logger.warning(f"Failed to write card payment to accounting: {exc}")

    return {
        "status": status_mp,
        "status_detail": status_detail,
        "payment_id": payment_id,
        "amount_ris_credited": body.amount_ris if status_mp == "approved" else 0,
        "total_charged_brl": total_brl_charged,
        "fee_brl": fee_brl,
    }


# ══════════════════════════════════════════════════════════════════════════
# La tarjeta pagando UN ENVIO, que no es lo mismo que cargar saldo
# ══════════════════════════════════════════════════════════════════════════
#
# Todo lo de arriba carga saldo, y por eso está cerrado: la empresa no custodia
# dinero de terceros. Esto no carga nada — la plata entra y sale en la misma
# operación, igual que el PIX que cobra al final—, así que NO lleva la guarda
# de `recarga_abierta`, y hay un test que exige que no la lleve.
#
# El por qué de cada regla está en `services/tarjeta_del_envio.py`. Acá sólo se
# aplican, en el orden en que le salen más barato al usuario: primero lo que se
# puede saber sin cobrarle nada.

class PagarEnvioConTarjetaInput(BaseModel):
    payment_order_id: str
    token: str
    payment_method_id: str
    payment_type_id: str = Field(default="credit_card",
                                 description="credit_card | debit_card")
    payer_email: EmailStr
    identification: PayerIdentification
    issuer_id: Optional[str] = None


class PagoDeEnvioConTarjeta(BaseModel):
    """Lo que la pantalla necesita saber, y NADA MAS.

    Por lista de lo permitido, como todo lo que ve el usuario: una lista de lo
    prohibido deja pasar cada campo nuevo hasta que alguien se acuerde. Acá lo
    que no puede salir es la respuesta cruda de Mercado Pago, que trae los
    datos del pagador y el detalle interno del emisor.
    """
    status: Optional[str] = None
    status_detail: str = ""
    payment_id: str = ""
    envio_pagado: bool = False
    transaction_id: Optional[str] = None
    total_charged_brl: float = 0.0
    fee_brl: float = 0.0


@router.post("/envio", response_model=PagoDeEnvioConTarjeta,
             dependencies=[Depends(sin_transacciones_personales)])
async def pagar_envio_con_tarjeta(
    body: PagarEnvioConTarjetaInput,
    current_user: User = Depends(get_current_user),
):
    """Cobra con tarjeta un envío ya cotizado y lo hace avanzar si aprueba."""
    from services import pago_al_final, tarjeta_del_envio
    from services.money import to_decimal

    if body.payment_type_id not in ("credit_card", "debit_card"):
        raise HTTPException(status_code=400, detail="Tipo de tarjeta inválido")

    # 1) VERIFICADO. La cotización ya lo comprobó; se repite porque una guarda
    #    que vive en otra ruta es una guarda hasta que alguien reordena las
    #    rutas. El motivo —el contracargo a ciento veinte días— está en
    #    `services/tarjeta_del_envio.py`.
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403,
                            detail=tarjeta_del_envio.SIN_VERIFICAR)

    # 2) El cobro tiene que ser de esta persona y de un envío.
    pago = await db.gestor_pix_payments.find_one({
        "payment_id": body.payment_order_id,
        "gestor_id": current_user.user_id,
        "proposito": pago_al_final.PROPOSITO,
    })
    if not pago:
        raise HTTPException(status_code=404, detail="No encontramos ese envío")

    # 3) LA GUARDA DEL DOBLE COBRO, y es la razón de ser de este bloque.
    #
    #    Una orden cotizada para PIX tiene un código vivo que alguien puede
    #    pagar. Cobrarla ADEMAS con tarjeta le saca la plata dos veces, y sólo
    #    una avanza el envío: `pago_al_final.confirmar` es atómico sobre la
    #    orden, pero eso protege la ORDEN, no la billetera del cliente.
    #
    #    Son dos preguntas y no una, y no se tapan: la primera mira lo que se
    #    PIDIO, la segunda lo que QUEDO. Si una orden de tarjeta terminara con
    #    un QR guardado —una cotización cambiada, una migración a medias— la
    #    primera la dejaría pasar. Cada una tiene su test.
    if not tarjeta_del_envio.es_de_tarjeta(pago):
        raise HTTPException(status_code=409,
                            detail=tarjeta_del_envio.NO_ES_DE_TARJETA)
    if tarjeta_del_envio.tiene_qr(pago):
        logger.error(
            "El envío %s dice ser de tarjeta y tiene un QR guardado: se "
            "rechaza el cobro para no cobrarle dos veces a %s.",
            body.payment_order_id, current_user.user_id)
        raise HTTPException(status_code=409,
                            detail=tarjeta_del_envio.NO_ES_DE_TARJETA)

    # 4) La orden, esperando el pago y sin vencer. Se mira la orden y no el
    #    cobro porque la orden es la que manda: es la que `confirmar` avanza.
    orden = await db.transactions.find_one({
        "payment_order_id": body.payment_order_id,
        "user_id": current_user.user_id,
    })
    if not orden:
        raise HTTPException(status_code=404, detail="No encontramos ese envío")
    if orden.get("status") != pago_al_final.ESPERANDO_PAGO:
        raise HTTPException(
            status_code=409,
            detail="Este envío ya no está esperando el pago. Miralo en tu "
                   "historial.")
    _vence = orden.get("payment_expires_at")
    if _vence:
        if _vence.tzinfo is None:
            _vence = _vence.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= _vence:
            raise HTTPException(
                status_code=409,
                detail="Se venció el tiempo para pagar este envío. Cotizalo de "
                       "nuevo para ver el monto de ahora.")

    # 5) Cuánto se le cobra. Sale del monto guardado en la orden, no de nada
    #    que mande la pantalla: el cliente no elige cuánto pagar.
    tarifas = await _get_card_fees()
    desglose = tarjeta_del_envio.cuanto_se_le_cobra(
        to_decimal(orden.get("payment_amount_brl") or 0),
        body.payment_type_id, tarifas)
    total_brl = to_float(desglose["total_brl"])
    fee_brl = to_float(desglose["comision_brl"])
    if total_brl <= 0:
        raise HTTPException(status_code=400, detail="Monto inválido")

    access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
    if not access_token:
        raise HTTPException(status_code=500, detail="MP no configurado")

    # 6) El cobro. Misma mecánica que la recarga con tarjeta, incluida la
    #    clave de idempotencia que evita que un reintento de red cobre dos.
    idempotency_key = str(uuid.uuid4())
    payload = {
        "transaction_amount": total_brl,
        "token": body.token,
        "description": f"Envio {orden.get('display_id') or ''}".strip(),
        "installments": 1,
        "payment_method_id": body.payment_method_id,
        "payer": {
            "email": body.payer_email,
            "identification": {"type": body.identification.type,
                               "number": body.identification.number},
        },
        "capture": True,
        "binary_mode": True,
        "metadata": {
            "user_id": current_user.user_id,
            "origin": "card_envio",
            "payment_order_id": body.payment_order_id,
            "transaction_id": orden.get("transaction_id"),
            "fee_brl": fee_brl,
        },
        "external_reference": body.payment_order_id,
    }
    if body.issuer_id:
        payload["issuer_id"] = body.issuer_id

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            mp_resp = await client.post(
                f"{MP_API_BASE}/v1/payments", json=payload,
                headers={"Authorization": f"Bearer {access_token}",
                         "Content-Type": "application/json",
                         "X-Idempotency-Key": idempotency_key})
    except httpx.HTTPError as exc:
        logger.error("MP no contestó al cobrar el envío %s: %s",
                     body.payment_order_id, exc)
        raise HTTPException(status_code=502,
                            detail="Error conectando con Mercado Pago")

    try:
        mp_data = mp_resp.json()
    except Exception:
        mp_data = {}

    if mp_resp.status_code >= 400:
        logger.error("MP rechazó el cobro del envío %s (%s): %s",
                     body.payment_order_id, mp_resp.status_code, mp_data)
        raise HTTPException(
            status_code=400,
            detail=mp_data.get("message") or "Error procesando el pago")

    payment_id = str(mp_data.get("id") or "")
    status_mp = mp_data.get("status")
    status_detail = mp_data.get("status_detail", "")

    # 7) Queda escrito el intento, aprobado o no. Un rechazo que no deja
    #    rastro es un cliente diciendo «me lo rechazaron» y nadie pudiendo
    #    mirar por qué.
    await db.card_payments.insert_one({
        "payment_id": payment_id,
        "user_id": current_user.user_id,
        "proposito": pago_al_final.PROPOSITO,
        "payment_order_id": body.payment_order_id,
        "transaction_id": orden.get("transaction_id"),
        "amount_brl_net": to_float(desglose["envio_brl"]),
        "fee_brl": fee_brl,
        "total_charged_brl": total_brl,
        "payment_method_id": body.payment_method_id,
        "payment_type_id": body.payment_type_id,
        "status": status_mp,
        "status_detail": status_detail,
        "mp_response": mp_data,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc),
    })

    # 8) Aprobado: avanza el envío. NO se acredita saldo — ésa es la
    #    diferencia entera con la recarga de arriba, y es lo que hace que esto
    #    no sea custodiar plata de nadie.
    #
    #    `pago_al_final.confirmar` es el MISMO camino que usa el PIX: un solo
    #    `find_one_and_update` con el estado en el filtro. Reusarlo es lo que
    #    hace que las dos vías no puedan divergir.
    avanzo = False
    if status_mp == "approved" and payment_id:
        avanzo = await pago_al_final.confirmar(
            db, {"payment_id": body.payment_order_id})
        if avanzo:
            try:
                await _credit_mp_bank_card(
                    payment_id=payment_id,
                    client_name=current_user.name or "Cliente",
                    amount_brl_net=to_float(desglose["envio_brl"]))
                await _register_card_fee(payment_id=payment_id,
                                         fee_brl=fee_brl, gross_brl=total_brl)
            except Exception as exc:
                logger.warning("El envío %s avanzó pero la contabilidad de la "
                               "tarjeta falló: %s", body.payment_order_id, exc)

    return {
        "status": status_mp,
        "status_detail": status_detail,
        "payment_id": payment_id,
        "envio_pagado": avanzo,
        "transaction_id": orden.get("transaction_id"),
        "total_charged_brl": total_brl,
        "fee_brl": fee_brl,
    }
