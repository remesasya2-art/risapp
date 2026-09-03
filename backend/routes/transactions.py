"""
Transaction routes - Withdrawals, Recharges, Beneficiaries
"""
import os
import json
import math
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from database import db

from services.money import from_db, to_float, to_decimal, to_decimal128
from services import saldos
from services.rate_engine import apply_rate_adjustment, load_auto_rate_config
from services import nowpayments
from services.min_amount import effective_min_amount
from services.limits import validate_pix_amount, validate_ves_amount
from services import kyc_quota

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://www.risappbr.com")
CRYPTO_NETWORK_TICKER = {"usdt": "usdttrc20", "usdc": "usdc"}

# Campos de dinero de una transaccion (para lectura tolerante float/Decimal128)
_TX_MONEY_2 = (
    "amount_input", "amount_output", "amount_ris", "amount_ves", "amount_brl",
    "balance_before", "balance_after", "balance_after_ris",
    "fee", "commission_amount", "commission",
    "monto_origen", "monto_destino", "monto_input_total", "monto_output_total",
)

def _normalize_tx_money(tx):
    """Normaliza los montos de una transaccion a numeros limpios (tolera float y Decimal128)."""
    if not tx:
        return tx
    for _k in _TX_MONEY_2:
        if _k in tx and tx[_k] is not None:
            tx[_k] = to_float(from_db(tx[_k]))
    if tx.get("rate") is not None:
        tx["rate"] = to_float(from_db(tx["rate"], places=6), places=6)
    return tx
from models.user import User
from models.requests import WithdrawalRequest, BeneficiaryCreate
from routes.dependencies import get_current_user, get_verified_user
from services.idempotency import claim_idempotency, store_idempotency_result
from services.notifications import create_notification
from services.centro_gestion import registrar_evento
from utils.helpers import get_next_withdrawal_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transactions"])

# ============== ENVIO CRIPTO: PAGOS INCOMPLETOS (3 NIVELES) ==============
# Sobre paid_ratio = (lo recibido) / (pay_amount pedido por NOWPayments):
#   ratio >= RATIO_ACEPTA -> se acepta y la orden pasa a 'pending'
#   ratio >= RATIO_TOPUP  -> 'awaiting_topup': se cobra la diferencia
#   ratio <  RATIO_TOPUP  -> 'underpaid_review': revision manual
RATIO_ACEPTA = 0.98
RATIO_TOPUP = 0.80

# Prefijo FIJO del order_id del pago de la diferencia. Es lo unico que distingue
# un IPN de topup de uno del pago original, asi que no debe cambiarse a la ligera.
TOPUP_ORDER_PREFIX = "topup_"

# Ventana para completar la diferencia antes de que la orden caiga a revision.
TOPUP_EXPIRY_HOURS = 48

# Estados desde los que una orden todavia puede pasar a 'pending' al confirmarse
# el pago. Incluye awaiting_topup y underpaid_review porque NOWPayments puede
# mandar un 'finished' tardio despues de un 'partially_paid': si al final entro
# el dinero completo, la orden debe cerrarse igual y no quedarse trabada.
ESTADOS_RECLAMABLES = ["awaiting_payment", "awaiting_topup", "underpaid_review"]


def _ticker_pagable(tx: dict) -> str | None:
    """Ticker de red pagable de la orden (ej. 'usdttrc20').

    OJO: tx['network'] es el nombre de red que devuelve NOWPayments (ej. 'trx'),
    NO un ticker valido para create_payment/min-amount. El ticker es pay_currency;
    si falta, se reconstruye desde la moneda de origen.
    """
    ticker = (tx.get("pay_currency") or "").strip().lower()
    if ticker:
        return ticker
    key = str(tx.get("currency_input") or "").strip().lower()
    return CRYPTO_NETWORK_TICKER.get(key)


ERROR_PAGO_GENERICO = "No se pudo iniciar el pago. Intenta de nuevo."


def _detalle_error_pago(exc: Exception) -> str:
    """Detalle del 502 cuando NOWPayments rechaza el pago.

    La validacion de minimo de mas arriba cubre el caso conocido, pero quedan
    rechazos que no anticipamos (ej. un USDC sobre Algorand rechazado a 10 USD sin
    motivo claro). Si el cuerpo del error trae un "message" — el mismo que PR #36
    dejo en el log via nowpayments._revisar — se le muestra al usuario en vez de
    "no se pudo iniciar el pago" a secas, que no dice nada. Si el cuerpo no se
    puede parsear, queda el mensaje generico de siempre.
    """
    mensaje = nowpayments.mensaje_de_error(exc)
    if not mensaje:
        return ERROR_PAGO_GENERICO
    return f"{ERROR_PAGO_GENERICO} Motivo de la pasarela: {mensaje}"


def _as_utc(dt):
    """Normaliza a datetime timezone-aware en UTC (Mongo puede devolver naive)."""
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _topup_expira_en(topup_created_at):
    base = _as_utc(topup_created_at)
    return base + timedelta(hours=TOPUP_EXPIRY_HOURS) if base else None


def _topup_vencido(topup_created_at) -> bool:
    expira = _topup_expira_en(topup_created_at)
    return bool(expira and datetime.now(timezone.utc) >= expira)


# ============== MERMA REAL DE NOWPAYMENTS (solo medicion) ==============
# `actually_paid` es lo que entro a la direccion de pago; `outcome_amount` es lo
# que NOWPayments acredita de verdad al comercio, ya descontada su comision
# interna de procesamiento. Hasta ahora solo se guardaba el primero, asi que esa
# comision era invisible: el VES prometido al beneficiario (`amount_output`) se
# fija al crear la orden y no se recalcula nunca.
#
# Lo de aca abajo NO cambia ese monto ni el flujo de aprobacion: solo deja
# registrada la diferencia para poder medirla antes de decidir que hacer con ella.


def _leer_outcome_ipn(payload: dict):
    """Extrae outcome_amount / outcome_currency del IPN.

    Devuelve (crudo, moneda, numero):
      - `crudo` y `moneda` se guardan tal como vinieron, sin transformarlos.
      - `numero` es la version usable para calcular, o None si el campo no vino
        o vino ilegible. Nunca 0: un cero seria indistinguible de "sin merma".
    """
    crudo = payload.get("outcome_amount")
    moneda = payload.get("outcome_currency")
    if crudo is None:
        return None, moneda, None
    try:
        return crudo, moneda, float(crudo)
    except (TypeError, ValueError):
        logger.warning(f"crypto-send webhook: outcome_amount ilegible ({crudo!r}), merma sin calcular")
        return crudo, moneda, None


def _outcome_total_con_topup(tx: dict, outcome_topup: Optional[float]) -> Optional[float]:
    """Acreditado total cuando hubo pago original + diferencia (topup).

    Si falta el outcome de cualquiera de los dos tramos devuelve None en vez de
    sumar lo que hay: un total parcial se leeria como una merma enorme y falsa.
    """
    original = tx.get("outcome_amount")
    try:
        original_num = float(original) if original is not None else None
    except (TypeError, ValueError):
        original_num = None
    if original_num is None or outcome_topup is None:
        return None
    return original_num + outcome_topup


def _calcular_merma_ves(tx: dict, outcome_total: Optional[float]) -> Optional[float]:
    """VES prometido menos el VES que respalda lo realmente acreditado.

        esperado_ves = outcome_amount * rate   (el `rate` congelado al crear la orden)
        merma_ves    = amount_output - esperado_ves

    Se usa a proposito el MISMO rate del alta y no la tasa del momento del pago:
    asi este numero mide unicamente la comision interna de NOWPayments y no se
    mezcla con el riesgo cambiario, que se mide aparte.

    Devuelve None -- nunca 0 -- si falta cualquiera de los insumos.
    Puede ser NEGATIVA (entro mas de lo esperado); es un resultado valido, no un
    error, y el reporte la muestra como tal.
    """
    if outcome_total is None:
        return None
    try:
        rate = to_float(from_db(tx.get("rate"), places=6), places=6)
        prometido = to_float(from_db(tx.get("amount_output")))
    except (TypeError, ValueError):
        return None
    if not rate or rate <= 0 or prometido is None:
        return None
    esperado_ves = outcome_total * rate
    return round(prometido - esperado_ves, 2)


async def _notificar_underpaid_review(
    user_id: str,
    title: str = "Tu pago está en revisión",
    message: str = "Tu pago llegó incompleto. Lo estamos revisando y te contactaremos pronto.",
):
    """Aviso de paso a revision manual. Best-effort: nunca rompe el flujo."""
    try:
        await create_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="crypto_send_underpaid_review",
        )
    except Exception as e:
        logger.warning(f"crypto-send: no se pudo notificar revision a {user_id}: {e}")


# ============== BENEFICIARIES ==============

@router.post("/beneficiaries")
async def create_beneficiary(request: BeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Create a new beneficiary"""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"

    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "id_document": request.id_document.strip(),
        "bank": request.bank.strip(),
        "bank_code": request.bank_code,
        "phone_number": request.phone_number,
        "account_number": request.account_number,
        "payment_type": request.payment_type,
        "created_at": datetime.now(timezone.utc)
    }

    await db.beneficiaries.insert_one(beneficiary)

    return {"message": "Beneficiario creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries")
async def get_beneficiaries(current_user: User = Depends(get_current_user)):
    """Get user's beneficiaries"""
    beneficiaries = await db.beneficiaries.find(
        {"user_id": current_user.user_id}
    ).to_list(100)

    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "id_document": b.get("id_document"),
            "bank": b.get("bank"),
            "bank_code": b.get("bank_code"),
            "phone_number": b.get("phone_number"),
            "account_number": b.get("account_number"),
            "payment_type": b.get("payment_type", "transferencia"),
            "created_at": b.get("created_at")
        }
        for b in beneficiaries
    ]

@router.delete("/beneficiaries/{beneficiary_id}")
async def delete_beneficiary(beneficiary_id: str, current_user: User = Depends(get_current_user)):
    """Delete a beneficiary"""
    result = await db.beneficiaries.delete_one({
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    return {"message": "Beneficiario eliminado"}

# ============== WITHDRAWALS ==============

# ---- RIS → Reais (Brasil, pago por PIX) ----

class BrBeneficiaryCreate(BaseModel):
    full_name: str
    cpf: str
    pix_key: str

class ReaisSendRequest(BaseModel):
    beneficiary_id: str
    amount: float   # en RIS (1 RIS = 1 R$)
    idempotency_key: Optional[str] = None

@router.post("/beneficiaries/br")
async def create_br_beneficiary(request: BrBeneficiaryCreate, current_user: User = Depends(get_current_user)):
    """Crea un beneficiario en Brasil (pago por PIX en reais)."""
    beneficiary_id = f"ben_{uuid.uuid4().hex[:12]}"
    beneficiary = {
        "beneficiary_id": beneficiary_id,
        "user_id": current_user.user_id,
        "full_name": request.full_name.strip(),
        "cpf": request.cpf.strip(),
        "pix_key": request.pix_key.strip(),
        "pais": "BR",
        "payment_type": "pix_br",
        "created_at": datetime.now(timezone.utc),
    }
    await db.beneficiaries.insert_one(beneficiary)
    return {"message": "Beneficiario (Brasil) creado", "beneficiary_id": beneficiary_id}

@router.get("/beneficiaries/br")
async def get_br_beneficiaries(current_user: User = Depends(get_current_user)):
    """Lista los beneficiarios en Brasil del usuario."""
    rows = await db.beneficiaries.find(
        {"user_id": current_user.user_id, "pais": "BR"}
    ).to_list(100)
    return [
        {
            "beneficiary_id": b.get("beneficiary_id"),
            "full_name": b.get("full_name"),
            "cpf": b.get("cpf"),
            "pix_key": b.get("pix_key"),
            "payment_type": "pix_br",
            "created_at": b.get("created_at"),
        }
        for b in rows
    ]

@router.post("/reais/send")
async def create_reais_send(request: ReaisSendRequest, current_user: User = Depends(get_current_user)):
    """Crea una orden de envío RIS → Reais (1 RIS = 1 R$, sin comisión: ya viene
    incluida en la recarga). Queda pendiente para que el super_admin la pague
    por PIX en Brasil desde el área de Órdenes por procesar."""
    # Mismo rango que la recarga: el envio sale por PIX y lo paga la misma via.
    error_monto = validate_pix_amount(request.amount)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    # Cupo de la cuenta sin verificar: se comprueba ANTES de crear nada.
    _kq_user = await db.users.find_one({"user_id": current_user.user_id})
    _kq_error = kyc_quota.check_amount(_kq_user, request.amount)
    if _kq_error:
        raise HTTPException(status_code=403, detail=_kq_error)
    # Idempotencia: evita duplicar el envío por doble clic / reintento de red.
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, "reais_send", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")
    # Descuento atómico de saldo RIS
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": to_decimal128(to_decimal(request.amount))}},
        {"$inc": {"balance_ris": to_decimal128(-to_decimal(request.amount))}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id,
        "pais": "BR",
    })
    if not beneficiary:
        # Devolver el saldo si el beneficiario no existe
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        raise HTTPException(status_code=404, detail="Beneficiario de Brasil no encontrado")
    amount_brl = request.amount  # 1 a 1
    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "cpf": beneficiary.get("cpf"),
        "pix_key": beneficiary.get("pix_key"),
        "payment_type": "pix_br",
        "pais": "BR",
    }
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_brl,
        "currency_input": "RIS",
        "currency_output": "BRL",
        "rate": 1.0,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        logger.error(f"Fallo al registrar envío a Brasil {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

    # Libro mayor RIS (append-only). Nunca interrumpe el envío.
    try:
        from services.ledger import record_ris_entry
        # `saldo_de` lee con `from_db`, así que da lo mismo si el campo quedó
        # en `float` o en `Decimal128`. Antes se leía crudo y se le SUMABA el
        # monto para sacar el saldo anterior: con el campo en Decimal128 eso es
        # un TypeError, y como esto va dentro del `try`, la línea del libro se
        # perdía en silencio mientras la plata sí se movía.
        _saldo_despues = saldos.saldo_de(user)
        balance_after_ris = to_float(_saldo_despues)
        balance_before_ris = to_float(_saldo_despues + to_decimal(request.amount))
        await record_ris_entry(
            user_id=current_user.user_id,
            movement_type="envio_reais",
            amount=request.amount,
            direction="debit",
            account="balance_ris",
            balance_before=balance_before_ris,
            balance_after=balance_after_ris,
            reference_kind="transaction",
            reference_id=tx_id,
            transaction_id=tx_id,
            display_id=display_id,
            actor_type="user",
            actor_id=current_user.user_id,
            actor_email=user.get("email"),
            rate=1.0,
            rate_kind="ris_to_brl",
            amount_output=amount_brl,
            currency_output="BRL",
            counterparty=beneficiary_data,
            user_snapshot={"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user.get("role", "user")},
            notes="Envío RIS → Reais (PIX Brasil)",
        )
    except Exception as e:
        logger.warning(f"Ledger envio_reais no registrado: {e}")

    await create_notification(
        user_id=current_user.user_id,
        title="Envío a Brasil solicitado",
        message=f"Tu envío de {request.amount:.2f} RIS (R$ {amount_brl:.2f}) a {beneficiary.get('full_name')} fue recibido y está en cola.",
        notification_type="withdrawal_pending",
    )
    _resp_reais = {"success": True, "transaction_id": tx_id, "display_id": display_id, "amount_brl": amount_brl}
    await store_idempotency_result(current_user.user_id, "reais_send", request.idempotency_key, _resp_reais)
    return _resp_reais

@router.post("/withdraw")
@router.post("/withdrawal/create")
async def create_withdrawal(request: WithdrawalRequest, current_user: User = Depends(get_current_user)):
    """Create a withdrawal request"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")
    # Idempotencia: evita duplicar el envío por doble clic / reintento de red.
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, "withdraw_ves", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")
    # 1) Validar beneficiario ANTES de tocar el saldo (evita débito sin destino)
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) Leer y validar la tasa ANTES de debitar (fail-closed: sin tasa válida no se procesa)
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    _base_rtv = (rate or {}).get("ris_to_ves")
    if not _base_rtv or _base_rtv <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")
    # Aplicar el mismo ajuste de horario que /api/rate para que el envío coincida con la cotización
    _cfg = await load_auto_rate_config(db)
    _eff = apply_rate_adjustment({"ris_to_ves": _base_rtv}, _cfg)
    ris_to_ves = _eff.get("ris_to_ves") or _base_rtv

    amount_ves = round(request.amount * ris_to_ves, 2)

    # Preparar datos de la transacción (antes del débito; no dependen del saldo)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()

    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia")
    }

    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": "RIS",
        "currency_output": "VES",
        "rate": ris_to_ves,
        "status": "pending",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": datetime.now(timezone.utc),
    }

    # 3) Débito atómico (impide sobregiro y condiciones de carrera)
    user = await db.users.find_one_and_update(
        {"user_id": current_user.user_id, "balance_ris": {"$gte": to_decimal128(to_decimal(request.amount))}},
        {"$inc": {"balance_ris": to_decimal128(-to_decimal(request.amount))}},
        return_document=True
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")

    # 4) Crear el registro; si falla, devolver el saldo (compensación) para no perder RIS
    try:
        await db.transactions.insert_one(transaction)
    except Exception as e:
        await db.users.update_one(
            {"user_id": current_user.user_id},
            {"$inc": {"balance_ris": to_decimal128(to_decimal(request.amount))}}
        )
        logger.error(f"Fallo al registrar retiro {tx_id}, saldo devuelto: {e}")
        raise HTTPException(status_code=500, detail="No se pudo registrar el retiro. Tu saldo no fue afectado.")

    # Libro mayor RIS (append-only). Nunca interrumpe el envío.
    try:
        from services.ledger import record_ris_entry
        # `saldo_de` lee con `from_db`, así que da lo mismo si el campo quedó
        # en `float` o en `Decimal128`. Antes se leía crudo y se le SUMABA el
        # monto para sacar el saldo anterior: con el campo en Decimal128 eso es
        # un TypeError, y como esto va dentro del `try`, la línea del libro se
        # perdía en silencio mientras la plata sí se movía.
        _saldo_despues = saldos.saldo_de(user)
        balance_after_ris = to_float(_saldo_despues)
        balance_before_ris = to_float(_saldo_despues + to_decimal(request.amount))
        await record_ris_entry(
            user_id=current_user.user_id,
            movement_type="envio_ves",
            amount=request.amount,
            direction="debit",
            account="balance_ris",
            balance_before=balance_before_ris,
            balance_after=balance_after_ris,
            reference_kind="transaction",
            reference_id=tx_id,
            transaction_id=tx_id,
            display_id=display_id,
            actor_type="user",
            actor_id=current_user.user_id,
            actor_email=user.get("email"),
            rate=ris_to_ves,
            rate_kind="ris_to_ves",
            amount_output=amount_ves,
            currency_output="VES",
            counterparty=beneficiary_data,
            user_snapshot={"email": user.get("email"), "name": user.get("full_name") or user.get("name"), "role": user.get("role", "user")},
            notes="Envío RIS → VES",
        )
    except Exception as e:
        logger.warning(f"Ledger envio_ves no registrado: {e}")

    # Notify user
    await create_notification(
        user_id=current_user.user_id,
        title="Retiro Solicitado",
        message=f"Tu retiro de {request.amount} RIS ({amount_ves:.2f} VES) ha sido recibido y esta en cola.",
        notification_type="withdrawal_pending"
    )

    # Registrar en CentroGestion
    try:
        await registrar_evento(
            tipo="retiro_ves",
            transaction_id=tx_id,
            user_id=current_user.user_id,
            user_email=user.get("email"),
            user_name=user.get("name") or user.get("full_name"),
            amount_input=request.amount,
            amount_output=amount_ves,
            currency_input="RIS",
            currency_output="VES",
            status="pending",
            metadata={
                "display_id": display_id,
                "rate": ris_to_ves,
                "beneficiary": beneficiary_data
            }
        )
    except Exception as e:
        logger.warning(f"registrar_evento fallo: {e}")

    _resp_withdraw = {
        "message": "Retiro solicitado exitosamente",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount,
        "amount_ves": amount_ves,
        "rate": ris_to_ves
    }
    await store_idempotency_result(current_user.user_id, "withdraw_ves", request.idempotency_key, _resp_withdraw)
    return _resp_withdraw

# ---- Saldo cripto (USDT / USDC) → VES ----
# Replica exactamente el mismo patrón de seguridad de create_withdrawal
# (idempotencia, validar beneficiario antes de tocar saldo, tasa fail-closed,
# débito atómico con compensación si falla el registro), pero debitando
# balance_usdt/balance_usdc en vez de balance_ris.

class CryptoSendRequest(BaseModel):
    currency: str            # "usdt" o "usdc"
    amount: float            # monto en USDT/USDC
    beneficiary_id: str
    network: Optional[str] = None
    use_balance: bool = False   # True: descuenta de balance_usdt/usdc (saldo de reembolsos). False (default): pago directo nuevo via NOWPayments.
    idempotency_key: Optional[str] = None

@router.post("/withdraw-crypto")
async def create_crypto_withdrawal(request: CryptoSendRequest, current_user: User = Depends(get_current_user)):
    """Crea un envio de USDT/USDC a un beneficiario en VES.

    Dos caminos:
      - use_balance=True: descuenta de balance_usdt/balance_usdc (saldo que el
        usuario tiene por un reembolso previo). Debito atomico, orden queda
        "pending" de una vez, sin pasar por NOWPayments.
      - use_balance=False (default): sin custodia previa. Genera un pago
        NOWPayments ligado a la orden ("awaiting_payment"); el webhook la pasa
        a "pending" al confirmarse el pago.
    En ambos casos la orden termina en el mismo lugar: "pending", visible en
    Ordenes por procesar, con el mismo pipeline de claim/process/approve/reject.
    """
    from services.credits import normalize_currency

    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    key = normalize_currency(request.currency)
    if key not in CRYPTO_NETWORK_TICKER:
        raise HTTPException(status_code=400, detail="Moneda no soportada")

    idem_scope = f"withdraw_{key}"
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, idem_scope, request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")

    # 1) Validar beneficiario ANTES de tocar saldo o generar el pago
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id
    })
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) Leer y validar la tasa ANTES de tocar saldo o generar el pago (fail-closed)
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    rate_field = "usdtris_to_ves" if key == "usdt" else "usdcris_to_ves"
    crypto_to_ves = (rate_doc or {}).get(rate_field)
    if not crypto_to_ves or crypto_to_ves <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")

    amount_ves = round(request.amount * crypto_to_ves, 2)
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()

    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia")
    }

    # ---- Camino A: usar saldo disponible (reembolsos previos) ----
    if request.use_balance:
        from services.credits import credit_field_for, to_credit_decimal
        from bson.decimal128 import Decimal128

        field = credit_field_for(request.currency)
        amount_dec = to_credit_decimal(request.amount)
        user = await db.users.find_one_and_update(
            {"user_id": current_user.user_id, field: {"$gte": Decimal128(amount_dec)}},
            {"$inc": {field: Decimal128(-amount_dec)}},
            return_document=True
        )
        if user is None:
            raise HTTPException(status_code=400, detail="Saldo insuficiente")

        transaction = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "user_id": current_user.user_id,
            "type": "withdrawal",
            "amount_input": request.amount,
            "amount_output": amount_ves,
            "currency_input": key.upper(),
            "currency_output": "VES",
            "rate": crypto_to_ves,
            "status": "pending",
            "beneficiary_id": request.beneficiary_id,
            "beneficiary_data": beneficiary_data,
            "funded_from": "balance",
            "created_at": datetime.now(timezone.utc),
        }
        try:
            await db.transactions.insert_one(transaction)
        except Exception as e:
            await db.users.update_one(
                {"user_id": current_user.user_id},
                {"$inc": {field: Decimal128(amount_dec)}}
            )
            logger.error(f"Fallo al registrar envío cripto (saldo) {tx_id}, saldo devuelto: {e}")
            raise HTTPException(status_code=500, detail="No se pudo registrar el envío. Tu saldo no fue afectado.")

        try:
            from services.ledger_crypto import record_crypto_entry
            balance_after = user.get(field)
            balance_after_f = float(to_credit_decimal(balance_after)) if balance_after is not None else None
            await record_crypto_entry(
                user_id=current_user.user_id,
                currency=key,
                movement_type="envio_ves",
                amount=float(amount_dec),
                direction="debit",
                balance_before=(balance_after_f + float(amount_dec)) if balance_after_f is not None else None,
                balance_after=balance_after_f,
                reference_kind="transaction",
                reference_id=tx_id,
                actor_type="user",
                actor_id=current_user.user_id,
                actor_email=user.get("email"),
                metadata={"display_id": display_id, "beneficiary": beneficiary_data, "funded_from": "balance"},
                notes=f"Envío {key.upper()} → VES (desde saldo)",
            )
        except Exception as e:
            logger.warning(f"Ledger cripto envio_ves (saldo) no registrado: {e}")

        await create_notification(
            user_id=current_user.user_id,
            title="Envío Solicitado",
            message=f"Tu envío de {request.amount} {key.upper()} ({amount_ves:.2f} VES) ha sido recibido y está en cola.",
            notification_type="withdrawal_pending",
        )
        _resp_balance = {
            "transaction_id": tx_id,
            "display_id": display_id,
            "status": "pending",
            "funded_from": "balance",
            "amount_crypto": request.amount,
            "amount_ves": amount_ves,
            "rate": crypto_to_ves,
            "currency": key.upper(),
        }
        await store_idempotency_result(current_user.user_id, idem_scope, request.idempotency_key, _resp_balance)
        return _resp_balance

    # ---- Camino B: pago directo nuevo (sin custodia), via NOWPayments ----
    pay_currency = (request.network or CRYPTO_NETWORK_TICKER[key]).strip().lower()
    if not pay_currency.startswith(key):
        raise HTTPException(status_code=400, detail="La red elegida no corresponde a la moneda seleccionada.")

    # Validar el monto minimo ANTES de escribir nada en la base.
    # Antes la orden se insertaba primero y el minimo lo terminaba rechazando
    # NOWPayments: cada intento con monto insuficiente dejaba una fila huerfana en
    # `transactions` con status "payment_error", sin ningun envio real detras.
    # Es el mismo minimo (con margen) que devuelve /credits/min-amount y que muestra
    # la pantalla, calculado sobre pay_currency desde el mismo helper.
    min_info = await effective_min_amount(pay_currency, currency_key=key)
    min_amount = min_info["min_amount"]
    if float(request.amount) < float(min_amount):
        raise HTTPException(
            status_code=400,
            detail=f"El monto mínimo para enviar {key.upper()} por esta red es {min_amount:.2f} {key.upper()}.",
        )

    order_id = f"send_{key}_{current_user.user_id}_{uuid.uuid4().hex[:12]}"
    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": key.upper(),
        "currency_output": "VES",
        "rate": crypto_to_ves,
        "status": "awaiting_payment",
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "payment_order_id": order_id,
        "pay_currency": pay_currency,
        "funded_from": "payment",
        "paid_ratio": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    await db.transactions.insert_one(transaction)

    try:
        payment = await nowpayments.create_payment(
            price_amount=float(request.amount),
            price_currency="usd",
            pay_currency=pay_currency,
            order_id=order_id,
            order_description=f"Envío {key.upper()} a {beneficiary_data.get('full_name') or 'beneficiario'}",
            ipn_callback_url=f"{PUBLIC_BASE_URL}/api/crypto-send/webhook",
            is_fee_paid_by_user=True,
        )
    except Exception as e:
        await db.transactions.update_one({"transaction_id": tx_id}, {"$set": {"status": "payment_error"}})
        logger.error(f"NOWPayments create_payment fallo para envío {tx_id}: {e}")
        raise HTTPException(status_code=502, detail=_detalle_error_pago(e))

    pay_address = payment.get("pay_address")
    pay_amount = payment.get("pay_amount")
    if not pay_address or not pay_amount:
        await db.transactions.update_one({"transaction_id": tx_id}, {"$set": {"status": "payment_error"}})
        logger.error(f"NOWPayments sin pay_address/pay_amount para envío {tx_id}: {payment}")
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago. Intenta de nuevo.")

    await db.transactions.update_one(
        {"transaction_id": tx_id},
        {"$set": {
            "payment_id": payment.get("payment_id"),
            "pay_address": pay_address,
            "pay_amount": pay_amount,
            "payin_extra_id": payment.get("payin_extra_id"),
            "network": payment.get("network"),
        }}
    )

    _resp_crypto = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "order_id": order_id,
        "status": "awaiting_payment",
        "funded_from": "payment",
        "pay_address": pay_address,
        "pay_amount": pay_amount,
        "pay_currency": pay_currency,
        "payin_extra_id": payment.get("payin_extra_id"),
        "network": payment.get("network"),
        "network_label": payment.get("network") or pay_currency,
        "amount_crypto": request.amount,
        "amount_ves": amount_ves,
        "rate": crypto_to_ves,
        "currency": key.upper(),
    }
    await store_idempotency_result(current_user.user_id, idem_scope, request.idempotency_key, _resp_crypto)
    return _resp_crypto


@router.get("/withdraw-crypto/{transaction_id}/status")
async def get_crypto_withdrawal_status(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Polling del estado de una orden de envio cripto (para la pantalla de pago).

    Ademas de devolver el estado, aplica el vencimiento del topup: si la orden
    quedo en 'awaiting_topup' y ya pasaron TOPUP_EXPIRY_HOURS desde que se genero
    el pago de la diferencia, se mueve a 'underpaid_review' de forma atomica aqui
    mismo (no se depende de un cron). El admin tiene el mismo barrido en
    /admin/ordenes/revision-pago por si el usuario nunca vuelve a abrir la app.
    """
    tx = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {
            "_id": 0, "status": 1, "amount_output": 1, "paid_ratio": 1,
            "pay_amount": 1, "actually_paid": 1,
            "topup_order_id": 1, "topup_pay_address": 1, "topup_pay_amount": 1,
            "topup_pay_currency": 1, "topup_network": 1, "topup_payin_extra_id": 1,
            "topup_created_at": 1,
        },
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    status = tx.get("status")

    if status == "awaiting_topup" and _topup_vencido(tx.get("topup_created_at")):
        claimed = await db.transactions.find_one_and_update(
            {"transaction_id": transaction_id, "status": "awaiting_topup"},
            {"$set": {"status": "underpaid_review", "topup_expired": True}},
            return_document=True,
        )
        if claimed:
            status = "underpaid_review"
            logger.info(f"crypto-send: topup vencido para {transaction_id}, pasa a underpaid_review")
            await _notificar_underpaid_review(claimed["user_id"])
        else:
            _fresh = await db.transactions.find_one(
                {"transaction_id": transaction_id}, {"_id": 0, "status": 1}
            ) or {}
            status = _fresh.get("status", status)

    resp = {
        "transaction_id": transaction_id,
        "status": status,
        "amount_ves": tx.get("amount_output"),
        "paid_ratio": tx.get("paid_ratio"),
    }

    if status == "awaiting_topup":
        _expires = _topup_expira_en(tx.get("topup_created_at"))
        resp.update({
            "topup_pay_address": tx.get("topup_pay_address"),
            "topup_pay_amount": tx.get("topup_pay_amount"),
            "topup_pay_currency": tx.get("topup_pay_currency"),
            "topup_network": tx.get("topup_network"),
            "topup_payin_extra_id": tx.get("topup_payin_extra_id"),
            "topup_expires_at": _expires.isoformat() if _expires else None,
        })

    return resp


@router.post("/withdraw-crypto/{transaction_id}/cancelar")
async def cancelar_orden_cripto(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Cancela una orden de envio cripto que todavia no recibio ningun pago.

    Solo se permite desde 'awaiting_payment': en ese estado NOWPayments no
    acredito nada todavia, asi que no hay plata del usuario que devolver. Ni
    bien entra un pago (aunque sea parcial) la orden deja de ser cancelable y
    pasa por el circuito normal de topup / revision.

    El claim es atomico (find_one_and_update condicionado al estado) para no
    pisarnos con el webhook: si justo llego un pago en el medio, el webhook ya
    movio el status y aca devolvemos 409 en vez de cancelar una orden que en
    realidad tiene plata adentro. El frontend, ante un 409, refresca el estado
    con el polling que ya tiene en lugar de asumir que se cancelo.
    """
    claimed = await db.transactions.find_one_and_update(
        {
            "transaction_id": transaction_id,
            "user_id": current_user.user_id,
            "status": "awaiting_payment",
        },
        {"$set": {
            "status": "cancelled_by_user",
            "cancelled_at": datetime.now(timezone.utc),
        }},
        return_document=True,
    )

    if claimed:
        logger.info(f"crypto-send: orden {transaction_id} cancelada por el usuario")
        return {
            "ok": True,
            "transaction_id": transaction_id,
            "status": "cancelled_by_user",
        }

    # No se pudo reclamar. O la orden no existe / no es de este usuario, o el
    # estado ya cambio mientras tanto.
    tx = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {"_id": 0, "status": 1},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    estado = tx.get("status")
    logger.info(
        f"crypto-send: cancelacion rechazada para {transaction_id}, estado actual {estado}"
    )
    raise HTTPException(
        status_code=409,
        detail="La orden ya no se puede cancelar porque cambio de estado. "
               "Actualiza la pantalla para ver como quedo.",
    )


async def finalizar_orden_pagada(claimed: dict):
    """Cierre comun cuando una orden de envio queda efectivamente pagada.

    Es exactamente lo que el webhook hacia inline hasta ahora al aceptar un pago;
    se extrae a una funcion porque ahora se llama desde dos lugares: el pago
    original y el pago de la diferencia (topup).

    NO escribe en el ledger cripto a proposito: en el camino funded_from="payment"
    nunca se toca balance_usdt/balance_usdc, asi que un asiento aqui inventaria un
    movimiento de saldo inexistente y romperia la reconciliacion.
    """
    try:
        await create_notification(
            user_id=claimed["user_id"],
            title="Pago recibido",
            message=f"Recibimos tu pago. Tu envío de {claimed.get('amount_output', 0):,.2f} VES será procesado pronto.",
            notification_type="crypto_send_paid",
        )
    except Exception as e:
        logger.warning(f"crypto-send webhook: no se pudo notificar al usuario: {e}")


@router.post("/crypto-send/webhook")
async def webhook_crypto_send(request: Request):
    """IPN de NOWPayments para envios directos (distinto del webhook de depositos
    en /credits/webhook — este busca en 'transactions', no en 'crypto_deposits').

    Sistema de 3 niveles para pagos incompletos, sobre paid_ratio = recibido/pay_amount:
      - ratio >= 0.98  -> se acepta, la orden pasa a 'pending' (underpaid si < 1.0)
      - 0.80 <= ratio  -> 'awaiting_topup': se genera un segundo pago por la
                          diferencia y se le pide al usuario completarlo
      - ratio < 0.80   -> 'underpaid_review': revision manual del admin
    El mismo endpoint atiende el pago original y el topup; se distinguen por el
    prefijo fijo "topup_" del order_id.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig", "")

    try:
        payload = json.loads(raw_body or b"{}") if raw_body else {}
    except Exception:
        payload = {}
    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    logger.info(f"crypto-send webhook: recibido order_id={order_id} status={payment_status}")

    matched = nowpayments.verify_ipn_signature(raw_body, signature)
    if not matched:
        logger.warning(f"crypto-send webhook: firma invalida order_id={order_id} status={payment_status}")
        raise HTTPException(status_code=401, detail="invalid_signature")
    logger.info(f"crypto-send webhook: firma valida (variante={matched}) order_id={order_id}")

    if not order_id:
        return {"received": True, "error": "no_order_id"}

    # --- Identificar si es el pago original o un topup, por el prefijo fijo ---
    is_topup = order_id.startswith(TOPUP_ORDER_PREFIX)
    if is_topup:
        tx = await db.transactions.find_one({"topup_order_id": order_id})
    else:
        tx = await db.transactions.find_one({"payment_order_id": order_id})

    if not tx:
        logger.warning(f"crypto-send webhook: order_id {order_id} no encontrado (topup={is_topup})")
        return {"received": True, "error": "order_not_found"}

    await db.transactions.update_one(
        {"_id": tx["_id"]},
        {"$set": {"payment_status_last": payment_status, "ipn_last_seen": datetime.now(timezone.utc)}},
    )

    # --- Fallo terminal: no llego nada util ---
    if payment_status in ("failed", "expired", "refunded"):
        estado_esperado = "awaiting_topup" if is_topup else "awaiting_payment"
        nuevo_estado = "underpaid_review" if is_topup else "payment_failed"
        claimed = await db.transactions.find_one_and_update(
            {"_id": tx["_id"], "status": estado_esperado},
            {"$set": {"status": nuevo_estado}},
            return_document=True,
        )
        if claimed and is_topup:
            await _notificar_underpaid_review(
                claimed["user_id"],
                message="No pudimos completar el pago de la diferencia. Lo pasamos a revisión y te contactaremos.",
            )
        return {"received": True, "processed": False, "status": payment_status}

    # --- Estados intermedios (waiting/confirming/sending/etc.): no calcular nivel todavia ---
    if payment_status not in ("finished", "partially_paid"):
        return {"received": True, "processed": False, "status": payment_status}

    actually_paid = payload.get("actually_paid")
    if actually_paid is None:
        return {"received": True, "processed": False, "status": payment_status}

    # Solo medicion: no altera el monto prometido ni el flujo de aprobacion.
    outcome_crudo, outcome_moneda, outcome_num = _leer_outcome_ipn(payload)

    try:
        actually_paid = float(actually_paid)
        pay_amount = float(tx.get("pay_amount") or 0)
    except (TypeError, ValueError):
        logger.warning(f"crypto-send webhook: montos ilegibles order_id={order_id}")
        return {"received": True, "processed": False, "status": payment_status}

    if pay_amount <= 0:
        logger.warning(f"crypto-send webhook: pay_amount invalido en {tx.get('transaction_id')}")
        return {"received": True, "processed": False, "status": payment_status}

    if is_topup:
        total_recibido = float(tx.get("actually_paid") or 0) + actually_paid
        paid_ratio = total_recibido / pay_amount
        merma_ves = _calcular_merma_ves(tx, _outcome_total_con_topup(tx, outcome_num))
        await db.transactions.update_one(
            {"_id": tx["_id"]},
            {"$set": {
                "topup_actually_paid": actually_paid,
                "paid_ratio": paid_ratio,
                "topup_outcome_amount": outcome_crudo,
                "topup_outcome_currency": outcome_moneda,
                "merma_ves": merma_ves,
                "merma_calculada_at": datetime.now(timezone.utc),
            }},
        )

        if paid_ratio >= RATIO_ACEPTA:
            claimed = await db.transactions.find_one_and_update(
                {"_id": tx["_id"], "status": {"$in": ESTADOS_RECLAMABLES}},
                {"$set": {
                    "status": "pending",
                    "paid_at": datetime.now(timezone.utc),
                    "underpaid": paid_ratio < 1.0,
                }},
                return_document=True,
            )
            if not claimed:
                logger.info(f"crypto-send webhook: order_id {order_id} ya estaba procesado, ignorando duplicado")
                return {"received": True, "already_processed": True}
            await finalizar_orden_pagada(claimed)
            return {"received": True, "processed": True}

        claimed = await db.transactions.find_one_and_update(
            {"_id": tx["_id"], "status": "awaiting_topup"},
            {"$set": {"status": "underpaid_review"}},
            return_document=True,
        )
        if claimed:
            await _notificar_underpaid_review(
                claimed["user_id"],
                title="Tu pago sigue incompleto",
                message="No pudimos completar tu envío con el pago adicional. Lo pasamos a revisión y te contactaremos.",
            )
        return {"received": True, "processed": False, "status": "underpaid_review"}

    # ---- Pago original ----
    paid_ratio = actually_paid / pay_amount
    merma_ves = _calcular_merma_ves(tx, outcome_num)
    await db.transactions.update_one(
        {"_id": tx["_id"]},
        {"$set": {
            "actually_paid": actually_paid,
            "paid_ratio": paid_ratio,
            "outcome_amount": outcome_crudo,
            "outcome_currency": outcome_moneda,
            "merma_ves": merma_ves,
            "merma_calculada_at": datetime.now(timezone.utc),
        }},
    )

    # --- Nivel 1: alcanza, se acepta ---
    if paid_ratio >= RATIO_ACEPTA:
        claimed = await db.transactions.find_one_and_update(
            {"_id": tx["_id"], "status": {"$in": ESTADOS_RECLAMABLES}},
            {"$set": {
                "status": "pending",
                "paid_at": datetime.now(timezone.utc),
                "underpaid": paid_ratio < 1.0,
            }},
            return_document=True,
        )
        if not claimed:
            logger.info(f"crypto-send webhook: order_id {order_id} ya estaba procesado, ignorando duplicado")
            return {"received": True, "already_processed": True}
        await finalizar_orden_pagada(claimed)
        return {"received": True, "processed": True}

    # --- Nivel 2: falto poco, se pide la diferencia ---
    if paid_ratio >= RATIO_TOPUP:
        faltante = round(pay_amount - actually_paid, 8)
        # OJO - unidades: `faltante` sale de pay_amount/actually_paid, que vienen
        # en unidades de la cripto, y mas abajo se manda como price_amount con
        # price_currency="usd". Vale porque este flujo hoy es solo USDT/USDC y se
        # asume la paridad 1:1 con el dolar. Si alguna vez se acepta otra moneda
        # aca (BTC, ETH, etc.) esta cuenta queda mal y hay que convertir el
        # faltante a USD antes de crear el pago de la diferencia.
        # El ticker pagable es pay_currency (ej. 'usdttrc20'); tx["network"] es el
        # nombre de la red que devuelve NOWPayments (ej. 'trx') y NO sirve como ticker.
        pay_currency = _ticker_pagable(tx)

        min_ok = False
        if pay_currency:
            try:
                min_info = await nowpayments.get_min_amount(pay_currency, fiat_equivalent="usd")
                min_amount = (min_info or {}).get("min_amount")
                min_ok = min_amount is not None and faltante >= float(min_amount)
            except Exception as e:
                logger.warning(f"crypto-send webhook: no se pudo obtener minimo de {pay_currency}: {e}")

        topup_order_id = f"{TOPUP_ORDER_PREFIX}{tx['payment_order_id']}"
        topup_payment = None
        if min_ok:
            try:
                topup_payment = await nowpayments.create_payment(
                    price_amount=faltante,
                    price_currency="usd",
                    pay_currency=pay_currency,
                    order_id=topup_order_id,
                    order_description=f"Diferencia de envio {tx['payment_order_id']}",
                    ipn_callback_url=f"{PUBLIC_BASE_URL}/api/crypto-send/webhook",
                    is_fee_paid_by_user=True,
                )
            except Exception as e:
                logger.warning(f"crypto-send webhook: fallo crear topup para {tx.get('transaction_id')}: {e}")

        if not min_ok or not topup_payment or not topup_payment.get("pay_address"):
            claimed = await db.transactions.find_one_and_update(
                {"_id": tx["_id"], "status": "awaiting_payment"},
                {"$set": {"status": "underpaid_review"}},
                return_document=True,
            )
            if claimed:
                await _notificar_underpaid_review(claimed["user_id"])
            return {"received": True, "processed": False, "status": "underpaid_review"}

        claimed = await db.transactions.find_one_and_update(
            {"_id": tx["_id"], "status": "awaiting_payment"},
            {"$set": {
                "status": "awaiting_topup",
                "topup_order_id": topup_order_id,
                "topup_payment_id": topup_payment.get("payment_id"),
                "topup_pay_address": topup_payment["pay_address"],
                "topup_pay_amount": topup_payment.get("pay_amount"),
                "topup_pay_currency": pay_currency,
                "topup_payin_extra_id": topup_payment.get("payin_extra_id"),
                "topup_network": topup_payment.get("network") or tx.get("network") or pay_currency,
                "topup_created_at": datetime.now(timezone.utc),
            }},
            return_document=True,
        )
        if not claimed:
            logger.info(f"crypto-send webhook: order_id {order_id} ya estaba procesado, ignorando duplicado")
            return {"received": True, "already_processed": True}
        try:
            await create_notification(
                user_id=claimed["user_id"],
                title="Falta completar tu pago",
                message="Tu pago llegó incompleto, probablemente por la comisión de tu wallet. Completá el envío de la diferencia para que se procese.",
                notification_type="crypto_send_awaiting_topup",
                data={"transaction_id": claimed.get("transaction_id")},
            )
        except Exception as e:
            logger.warning(f"crypto-send webhook: no se pudo notificar: {e}")
        return {"received": True, "processed": False, "status": "awaiting_topup"}

    # --- Nivel 3: falto demasiado, revision manual ---
    claimed = await db.transactions.find_one_and_update(
        {"_id": tx["_id"], "status": "awaiting_payment"},
        {"$set": {"status": "underpaid_review"}},
        return_document=True,
    )
    if claimed:
        await _notificar_underpaid_review(claimed["user_id"])
    return {"received": True, "processed": False, "status": "underpaid_review"}


# ============== RECHARGE VES ==============

# ─── El banco destino de una recarga en bolivares ─────────────────────────
#
# El usuario elige un banco en una lista del frontend y manda su clave
# (`banco_venezuela`, `banesco`…). Contabilidad, en cambio, tiene bancos con un
# `bank_id` opaco y un nombre comercial. Traducir de una cosa a la otra es lo
# que hace esta funcion, y es lo que permite que la aprobacion sepa a que
# cuenta entro la plata.
#
# ESTA FUNCION FALTABA. `routes/admin.py` la importaba y la llamaba desde
# siempre, y no existia en ningun archivo del backend: el import reventaba con
# un ImportError. No se notaba porque esa rama solo corre cuando la recarga
# tiene `destination_bank`, y nadie lo escribia — el defecto de mas arriba
# mantenia desarmada la bomba de mas abajo.

_ACENTOS = str.maketrans("áéíóúÁÉÍÓÚàâãêôõçÀÂÃÊÔÕÇ", "aeiouAEIOUaaaeoocAAAEOOC")


def _clave_de_banco(texto) -> str:
    """Un nombre de banco reducido a lo comparable: sin acentos, sin puntuacion.

    'Banco de Venezuela', 'banco_venezuela' y 'BANCO DE VENEZUELA' tienen que
    ser la misma cosa. Sin esto, la traduccion depende de como lo tipeo quien
    cargo el banco en contabilidad, que es una fuente distinta de quien escribio
    la lista del frontend.
    """
    limpio = str(texto or "").translate(_ACENTOS).lower()
    palabras = [p for p in "".join(c if c.isalnum() else " " for c in limpio).split()
                # 'de' y 'del' sobran: "Banco de Venezuela" y "banco_venezuela"
                # tienen que colapsar al mismo valor.
                if p not in ("de", "del", "la", "el", "banco")]
    return " ".join(palabras)


async def resolve_ves_bank(valor):
    """(bank_id, documento) del banco de contabilidad que corresponde, o (None, None).

    Acepta las dos formas que pueden llegar:
      - un `bank_id` ya resuelto, tal como lo guarda el panel;
      - la clave o el nombre que eligio el usuario, que se compara contra el
        nombre de los bancos en VES.

    NUNCA lanza y NUNCA adivina: si no hay una coincidencia clara devuelve
    (None, None) y el que llama decide. Elegir "el mas parecido" seria acreditar
    plata contra una cuenta que nadie eligio, y es exactamente lo que la guarda
    del aprobador viene evitando.

    Una coincidencia AMBIGUA —dos bancos que reducen a la misma clave— tambien
    es (None, None): con dos candidatos no hay respuesta, hay un empate, y un
    empate lo rompe una persona.
    """
    if not valor:
        return None, None
    texto = str(valor).strip()
    if not texto:
        return None, None

    try:
        # 1. Un bank_id explicito. Es lo que manda el panel al resolver a mano.
        #    Se exige `currency: VES` TAMBIEN aca: sin ese filtro, un usuario que
        #    mande el bank_id de una cuenta en reales como `destination_bank`
        #    consigue que la aprobacion sume bolivares a una cuenta en reales.
        #    El aprobador no chequea la moneda —y no lo tocamos—, asi que la
        #    unica forma de que no llegue ahi es no resolverlo nunca.
        directo = await db.bank_accounts.find_one(
            {"bank_id": texto, "currency": "VES"}, {"_id": 0})
        if directo:
            return directo.get("bank_id"), directo

        # 2. La clave o el nombre. Se compara contra los bancos en VES: un banco
        #    en BRL no puede recibir una transferencia en bolivares, y dejarlo
        #    entrar seria un asiento contra la cuenta equivocada.
        bancos = await db.bank_accounts.find(
            {"currency": "VES"}, {"_id": 0}).to_list(200)
    except Exception as e:
        logger.warning(f"resolve_ves_bank: no se pudo leer bank_accounts: {e}")
        return None, None

    buscada = _clave_de_banco(texto)
    if not buscada:
        return None, None
    candidatos = [b for b in bancos if _clave_de_banco(b.get("name")) == buscada]
    if len(candidatos) != 1:
        if len(candidatos) > 1:
            logger.warning(
                f"resolve_ves_bank: {len(candidatos)} bancos VES coinciden con "
                f"{texto!r}; hace falta que alguien elija")
        return None, None
    return candidatos[0].get("bank_id"), candidatos[0]


async def bancos_ves_disponibles() -> list[str]:
    """Los nombres de los bancos en VES, para poder decirlo en un error.

    Un 400 que dice "ese banco no existe" y no dice cuales existen manda a
    alguien a adivinar. Nunca lanza: es para un mensaje, no para una decision.
    """
    try:
        bancos = await db.bank_accounts.find(
            {"currency": "VES"}, {"_id": 0, "name": 1}).sort("name", 1).to_list(200)
        return [b.get("name") for b in bancos if b.get("name")]
    except Exception:                                         # pragma: no cover
        return []


@router.post("/recharge/ves")
async def recharge_ves(request: dict, current_user: User = Depends(get_current_user)):
    """Create a VES recharge request"""
    amount_ves = float(request.get("amount_ves", 0))
    payment_method = request.get("payment_method", "transferencia")

    # Piso de negocio en bolivares. Sin techo, a proposito.
    error_monto = validate_ves_amount(amount_ves)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)

    # ─── El banco y el comprobante, que antes se perdian ──────────────────
    #
    # Los dos llegaban en el `request` y no se leian nunca: el documento se
    # insertaba sin ellos y la aprobacion despues no encontraba nada. Ninguna
    # recarga VES se podia aprobar por el camino normal, y el operador quedaba
    # por acreditar dinero sin poder ver el comprobante que el usuario si habia
    # subido.
    #
    # `bank` y `voucher_image` son los nombres que manda la pantalla vieja. Se
    # aceptan por compatibilidad —hay clientes ya cargados en el navegador de
    # la gente— pero adentro se guarda UN nombre por concepto, el que el panel
    # ya lee: `destination_bank` / `destination_bank_id` y `proof_image`.
    banco_elegido = (request.get("destination_bank") or request.get("bank") or "")
    banco_elegido = str(banco_elegido).strip()
    comprobante = request.get("proof_image") or request.get("voucher_image")

    # SE RECHAZA ACA, NO EN LA APROBACION. Antes el servidor aceptaba una
    # solicitud que el mismo sabia que no iba a poder procesar, y el usuario se
    # enteraba dias despues, por telefono.
    if not banco_elegido:
        raise HTTPException(
            status_code=400,
            detail="Elegí a qué banco transferiste. Sin eso no podemos verificar tu "
                   "pago ni acreditarte el saldo.")

    bank_id, bank_doc = await resolve_ves_bank(banco_elegido)
    if not bank_id:
        # No es culpa del usuario: eligio de la lista que le mostramos. Es que
        # ese banco no esta cargado en contabilidad, o esta con otro nombre.
        disponibles = await bancos_ves_disponibles()
        logger.error(
            f"recharge_ves: el banco {banco_elegido!r} no resuelve contra "
            f"bank_accounts (VES disponibles: {disponibles})")
        raise HTTPException(
            status_code=400,
            detail=("Ese banco no está disponible en este momento. Probá con otro o "
                    "escribinos." + (f" Disponibles: {', '.join(disponibles)}."
                                     if disponibles else "")))

    if not comprobante:
        # Obligatorio: el operador acredita dinero MIRANDOLO. Una recarga sin
        # comprobante es una que alguien va a tener que resolver por telefono.
        raise HTTPException(
            status_code=400,
            detail="Subí el comprobante de la transferencia. Es lo que miramos para "
                   "acreditarte el saldo.")
    # Idempotencia: evita duplicar la solicitud por doble clic / reintento de red.
    _rch_key = request.get("idempotency_key")
    _rch_new, _rch_existing = await claim_idempotency(current_user.user_id, "recharge_ves", _rch_key)
    if not _rch_new:
        if _rch_existing and _rch_existing.get("result"):
            return _rch_existing["result"]
        raise HTTPException(status_code=409, detail="Esta solicitud ya se está procesando. Espera un momento.")
    # Tasa autoritativa del servidor (fail-closed): NO se confía en el monto RIS
    # que envíe el cliente; el servidor recalcula cuánto RIS corresponde.
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    _base_vtr = (rate_doc or {}).get("ves_to_ris_rate")
    if not _base_vtr or _base_vtr <= 0:
        raise HTTPException(status_code=503, detail="La tasa no está disponible en este momento. Intenta más tarde.")
    # Aplicar el mismo ajuste de horario que /api/rate para que la orden coincida con la cotización
    _cfg = await load_auto_rate_config(db)
    _eff = apply_rate_adjustment({"ves_to_ris_rate": _base_vtr}, _cfg)
    ves_to_ris = _eff.get("ves_to_ris_rate") or _base_vtr

    # Fórmula oficial: ves_to_ris_rate = VES por 1 RIS  ->  RIS = VES / tasa
    amount_ris = round(amount_ves / ves_to_ris, 2)
    if amount_ris <= 0:
        raise HTTPException(status_code=400, detail="El monto en VES es demasiado bajo para la tasa actual.")
    # Cupo de la cuenta sin verificar: se comprueba ANTES de crear nada.
    _kq_user = await db.users.find_one({"user_id": current_user.user_id})
    _kq_error = kyc_quota.check_amount(_kq_user, amount_ris)
    if _kq_error:
        raise HTTPException(status_code=403, detail=_kq_error)

    amount_input = amount_ves

    # Aviso si el cliente había calculado un RIS distinto (no bloquea: el servidor manda)
    _client_ris = float(request.get("amount_ris", 0) or 0)
    if _client_ris and abs(_client_ris - amount_ris) > 0.01:
        logger.warning(f"recharge_ves: RIS del cliente ({_client_ris}) != servidor ({amount_ris}) user={current_user.user_id}")

    user = await db.users.find_one({"user_id": current_user.user_id})

    tx_id = f"rech_{uuid.uuid4().hex[:12]}"

    transaction = {
        "transaction_id": tx_id,
        "user_id": current_user.user_id,
        "type": "recharge_ves",
        "amount_input": amount_input,
        "amount_output": amount_ris,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris,
        "rate": ves_to_ris,
        "rate_kind": "ves_to_ris",
        "currency_input": "VES",
        "currency_output": "RIS",
        "payment_method": payment_method,
        # Lo que eligio el usuario, CRUDO, y lo que eso resolvio en
        # contabilidad. Se guardan los dos: el crudo es lo que la persona
        # efectivamente eligio —y es lo que hay que mirar el dia que un banco
        # cambie de nombre— y el resuelto es contra que cuenta va el asiento.
        "destination_bank": banco_elegido,
        "destination_bank_id": bank_id,
        "destination_bank_name": (bank_doc or {}).get("name"),
        "proof_image": comprobante,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    }

    await db.transactions.insert_one(transaction)

    # Registrar en CentroGestion
    await registrar_evento(
        tipo="recarga_ves",
        transaction_id=tx_id,
        user_id=current_user.user_id,
        user_email=user.get("email") if user else None,
        user_name=user.get("name") or user.get("full_name") if user else None,
        amount_input=amount_input,
        amount_output=amount_ris,
        currency_input="VES",
        currency_output="RIS",
        status="pending",
        metadata={"payment_method": payment_method}
    )

    _resp_rch = {
        "message": "Recarga VES registrada, pendiente de verificacion",
        "transaction_id": tx_id,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris
    }
    await store_idempotency_result(current_user.user_id, "recharge_ves", _rch_key, _resp_rch)
    return _resp_rch

# ============== TRANSACTION HISTORY ==============

@router.get("/transactions")
async def get_transactions(
    page: int = 1,
    limit: int = 10,
    filter_type: str = None,
    current_user: User = Depends(get_current_user)
):
    """Get user's transaction history with pagination"""
    query = {"user_id": current_user.user_id}
    if filter_type and filter_type != "all":
        if filter_type == "withdrawals":
            query["type"] = {"$in": ["withdrawal", "send"]}
        elif filter_type == "recharges":
            query["type"] = {"$in": ["recharge", "recharge_ves"]}

    skip = (page - 1) * limit
    total = await db.transactions.count_documents(query)
    transactions = await db.transactions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    for _tx in transactions:
        _normalize_tx_money(_tx)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        # El frontend usa `pages` para habilitar la paginacion; sin este campo
        # se quedaba siempre en la pagina 1.
        "pages": math.ceil(total / limit) if limit else 1,
        "transactions": transactions
    }

@router.get("/transactions/{transaction_id}")
async def get_transaction(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific transaction"""
    transaction = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        {"_id": 0}
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")

    _normalize_tx_money(transaction)

    return transaction

# ============== PENDING WITHDRAWAL CHECK ==============

@router.get("/withdrawal/pending")
async def check_pending_withdrawal(current_user: User = Depends(get_current_user)):
    """Check if user has a pending withdrawal"""
    withdrawal = await db.transactions.find_one(
        {
            "user_id": current_user.user_id,
            "type": {"$in": ["withdrawal", "send"]},
            "status": "pending"
        },
        {"_id": 0},
        sort=[("created_at", -1)]
    )

    if not withdrawal:
        return {"has_pending": False}

    return {
        "has_pending": True,
        "transaction_id": withdrawal.get("transaction_id"),
        "display_id": withdrawal.get("display_id"),
        "amount_input": withdrawal.get("amount_input"),
        "amount_output": withdrawal.get("amount_output"),
        "beneficiary_data": withdrawal.get("beneficiary_data"),
        "created_at": withdrawal.get("created_at")
    }
