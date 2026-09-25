"""
Transaction routes - Withdrawals, Recharges, Beneficiaries
"""
import asyncio
import os
import json
import math
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from database import db
from services import cripto_abierta, recarga_abierta

from services.money import from_db, para_mostrar, to_float, to_decimal, to_decimal128
from services import bonos, comisiones, salidas_de_saldo
from services import nowpayments
from services.min_amount import effective_min_amount
from services.limits import validate_pix_amount, validate_ves_amount
from services import kyc_quota
from services.bancos import clave_del_nombre, para_el_cliente

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
from routes.dependencies import get_current_user, get_verified_user, sin_transacciones_personales
from services.idempotency import claim_idempotency, store_idempotency_result
from services.notifications import create_notification
from utils.helpers import get_next_withdrawal_id
from services.imagen_recibida import ImagenInvalida, limpiar_imagen_opcional

logger = logging.getLogger(__name__)
from models.cuenta import MiBeneficiario, MiBeneficiarioEnBrasil
from models.movimientos import LO_QUE_VE_EL_CLIENTE, LO_QUE_VE_EN_LA_LISTA, MisMovimientos, MovimientoQueVeElCliente
from services.las_fotos import cuales_tienen_comprobante
from models.dinero_en_transito import EstadoDeMiEnvioCripto, MiRetiroPendiente
from models.acciones_de_dinero import (
    BancosParaTransferir,
    MiComprobanteRecibido,
    MiCotizacionReais,
    MiCotizacionVes,
    MiEnvioCripto,
    MiEnvioDeReais,
    MiOrdenCriptoCancelada,
    MiRecargaVes,
    MiRetiroPedido,
)
from models.acciones_del_cliente import (MiBeneficiarioCreado, MiBeneficiarioEliminado,
                                        MiBeneficiarioEnBrasilCreado)
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
    transaction_id: str | None = None,
):
    """Aviso de paso a revision manual. Best-effort: nunca rompe el flujo.

    `transaction_id` es opcional a proposito: este ayudante lo llaman varios
    caminos y no todos tienen la operacion a mano. Sin el, el correo sale como
    parrafo en vez de comprobante, que es peor pero no es nada.
    """
    try:
        await create_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="crypto_send_underpaid_review",
            data={"transaction_id": transaction_id} if transaction_id else None,
        )
    except Exception as e:
        logger.warning(f"crypto-send: no se pudo notificar revision a {user_id}: {e}")


# ============== BENEFICIARIES ==============

@router.post("/beneficiaries", response_model=MiBeneficiarioCreado, response_model_exclude_unset=True)
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

    # El beneficiario va entero, igual que sale en la lista. Antes volvía sólo
    # el identificador, y la pantalla de envío tomaba ESTA respuesta como el
    # beneficiario elegido: la confirmación —justo el paso que dice «revisá el
    # nombre y los datos»— salía con un «?» y sin banco, cédula ni teléfono.
    return {"message": "Beneficiario creado", "beneficiary_id": beneficiary_id,
            "beneficiario": _como_se_lista(beneficiary)}

@router.get("/beneficiaries", response_model=List[MiBeneficiario])
async def get_beneficiaries(current_user: User = Depends(get_current_user)):
    """Get user's beneficiaries"""
    beneficiaries = await db.beneficiaries.find(
        {"user_id": current_user.user_id}
    ).to_list(100)

    return [_como_se_lista(b) for b in beneficiaries]


def _como_se_lista(b: dict) -> dict:
    """Un beneficiario de Venezuela tal como lo ve su dueño. UNA sola forma
    para la lista y para la respuesta de guardarlo: si fueran dos, la pantalla
    mostraría distinto al mismo beneficiario según de dónde lo sacó."""
    return {
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

@router.delete("/beneficiaries/{beneficiary_id}", response_model=MiBeneficiarioEliminado, response_model_exclude_unset=True)
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

@router.post("/beneficiaries/br", response_model=MiBeneficiarioEnBrasilCreado, response_model_exclude_unset=True)
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
    # Entero, por lo mismo que el de Venezuela: la pantalla lo elige con esta
    # respuesta, y sin los datos la confirmación salía sin nombre, CPF ni llave.
    return {"message": "Beneficiario (Brasil) creado", "beneficiary_id": beneficiary_id,
            "beneficiario": _como_se_lista_en_brasil(beneficiary)}

@router.get("/beneficiaries/br", response_model=List[MiBeneficiarioEnBrasil])
async def get_br_beneficiaries(current_user: User = Depends(get_current_user)):
    """Lista los beneficiarios en Brasil del usuario."""
    rows = await db.beneficiaries.find(
        {"user_id": current_user.user_id, "pais": "BR"}
    ).to_list(100)
    return [_como_se_lista_en_brasil(b) for b in rows]


def _como_se_lista_en_brasil(b: dict) -> dict:
    """Un beneficiario de Brasil tal como lo ve su dueño: la misma forma en la
    lista y al guardarlo (ver `_como_se_lista`)."""
    return {
        "beneficiary_id": b.get("beneficiary_id"),
        "full_name": b.get("full_name"),
        "cpf": b.get("cpf"),
        "pix_key": b.get("pix_key"),
        "payment_type": "pix_br",
        "created_at": b.get("created_at"),
    }

@router.post("/reais/send", response_model=MiEnvioDeReais, response_model_exclude_unset=True, dependencies=[Depends(sin_transacciones_personales)])
async def create_reais_send(request: ReaisSendRequest, current_user: User = Depends(get_current_user)):
    """Crea una orden de envío RIS → Reais (1 RIS = 1 R$, sin comisión: ya viene
    incluida en la recarga). Queda pendiente para que el super_admin la pague
    por PIX en Brasil desde el área de Órdenes por procesar."""
    # Mismo rango que la recarga: el envio sale por PIX y lo paga la misma via.
    error_monto = await validate_pix_amount(db, request.amount)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    # Cupo de la cuenta sin verificar: se comprueba ANTES de crear nada.
    _kq_user = await db.users.find_one({"user_id": current_user.user_id})
    _kq_error = await kyc_quota.check_amount(db, _kq_user, request.amount)
    if _kq_error:
        raise HTTPException(status_code=403, detail=_kq_error)
    # Idempotencia: evita duplicar el envío por doble clic / reintento de red.
    _idem_new, _idem_existing = await claim_idempotency(current_user.user_id, "reais_send", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409, detail="Esta operación ya se está procesando. Espera un momento.")
    user, beneficiary, tx_id, display_id, amount_brl = await salidas_de_saldo.cobrar_envio_a_brasil(
        current_user, request)

    await create_notification(
        user_id=current_user.user_id,
        title="Tu envío a Brasil está en cola",
        message=f"Recibimos tu envío de {para_mostrar(request.amount, 'RIS')} (R$ {para_mostrar(amount_brl)}) a {beneficiary.get('full_name')}. Te avisamos cuando salga.",
        notification_type="withdrawal_pending",
        # El número de la operación viaja en el aviso para que el correo pueda
        # armar el comprobante con forma de pasaje. Ver `services/pasaje.py`.
        data={"transaction_id": tx_id},
    )
    _resp_reais = {"success": True, "transaction_id": tx_id, "display_id": display_id, "amount_brl": amount_brl}
    await store_idempotency_result(current_user.user_id, "reais_send", request.idempotency_key, _resp_reais)
    return _resp_reais

# EL CANDADO VA EN LAS DOS PUERTAS, Y ANTES NO ERA ASI.
#
#   Esta función estaba registrada dos veces —`/withdraw` y `/withdrawal/create`—
#   y la dependencia `sin_transacciones_personales` colgaba SOLO del primer
#   decorador. FastAPI registra una ruta por decorador, con las dependencias de
#   ese decorador y nada más: `/withdrawal/create` quedaba abierta.
#
#   O sea que la regla «el personal no hace transacciones a título personal» se
#   saltaba escribiendo otra URL. Y el segundo candado tampoco lo ataja: esta
#   función debita con un `find_one_and_update` directo sobre `db.users`, no
#   pasa por `services/saldos.mover`.
#
#   El alias no lo usa nadie —el frontend no lo llama— pero se
#   conserva por si algún cliente viejo lo llama, ahora con el mismo candado.
#   Hay un test que recorre la aplicación armada y falla si una ruta de envío
#   queda sin él.
@router.post("/withdraw", response_model=MiRetiroPedido, response_model_exclude_unset=True, dependencies=[Depends(sin_transacciones_personales)])
@router.post("/withdrawal/create", response_model=MiRetiroPedido, response_model_exclude_unset=True, dependencies=[Depends(sin_transacciones_personales)])
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
    # La misma tasa que muestra /api/rate: la cargada, sin ajuste nocturno
    # (se eliminó; ver `routes/basic.py`).
    ris_to_ves = _base_rtv

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

    # ─── 2 bis) Lo que te queda a vos ────────────────────────────────────
    #
    # VA ANTES DEL DEBITO, y ése es todo el punto. Si la tasa de costo falta,
    # la operación se rechaza acá, con el saldo intacto. Calculado después del
    # débito, un rechazo dejaría plata movida y habría que devolverla.
    #
    # De fábrica esto devuelve `{}` y no cambia absolutamente nada: el registro
    # de comisiones viene apagado. Ver `services/comisiones.py`.
    try:
        transaction.update(await comisiones.campos_de(
            db, via="ris_to_ves", monto_cliente=request.amount,
            tasa_cliente=ris_to_ves))
    except comisiones.FaltaLaTasaDeCosto:
        raise HTTPException(
            status_code=503,
            detail="El envío no está disponible en este momento. Intenta más tarde.")

    await salidas_de_saldo.cobrar_retiro_en_bolivares(
        current_user, request, transaction=transaction, tx_id=tx_id, display_id=display_id,
        ris_to_ves=ris_to_ves, amount_ves=amount_ves, beneficiary_data=beneficiary_data)

    # El bono del dueño del código, para los referidos que pasaron el tope: de
    # la cuenta número once en adelante cobra recién cuando su referido hace
    # este envío. Va DESPUES de que la operación quedó registrada, y nunca
    # levanta: que un bono no se pague no puede hacer fallar una remesa que ya
    # se cobró.
    await bonos.al_enviar_a_venezuela(db, current_user.user_id, request.amount)

    # Notify user
    await create_notification(
        user_id=current_user.user_id,
        title="Tu retiro está en cola",
        message=f"Recibimos tu retiro de {para_mostrar(request.amount, 'RIS')} ({para_mostrar(amount_ves, 'VES')}). Te avisamos cuando salga.",
        notification_type="withdrawal_pending",
        data={"transaction_id": tx_id},
    )

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

@router.post("/withdraw-crypto", response_model=MiEnvioCripto, response_model_exclude_unset=True, dependencies=[Depends(sin_transacciones_personales)])
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

    # ESTA RUTA ES LAS DOS COSAS SEGUN `use_balance`, Y POR ESO SON DOS GUARDAS.
    #
    #   use_balance=True  gasta saldo que ya existe. Es SALIDA, y en el estado
    #                     de apagado (1) tiene que seguir funcionando: es
    #                     justamente por donde la plata de alguien puede salir.
    #   use_balance=False genera un pago cripto NUEVO por NOWPayments. Eso es
    #                     ENTRADA, aunque el nombre de la ruta diga «withdraw»:
    #                     entra cripto que antes no estaba.
    #
    # Mirar sólo el nombre de la ruta y ponerle una sola guarda dejaría abierta
    # la mitad que crea custodia nueva.
    await cripto_abierta.exigir_envio(db)
    if not request.use_balance:
        await cripto_abierta.exigir_deposito(db)

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
        # El débito, la orden y su línea del libro: ver services/salidas_de_saldo.py.
        from services.salidas_de_saldo import cobrar_envio_con_saldo_cripto
        await cobrar_envio_con_saldo_cripto(
            current_user, request, key=key, tx_id=tx_id, display_id=display_id,
            crypto_to_ves=crypto_to_ves, amount_ves=amount_ves,
            beneficiary_data=beneficiary_data)

        await create_notification(
            user_id=current_user.user_id,
            title="Tu envío está en cola",
            message=f"Recibimos tu envío de {request.amount} {key.upper()} ({para_mostrar(amount_ves, 'VES')}). Te avisamos cuando salga.",
            notification_type="withdrawal_pending",
            data={"transaction_id": tx_id},
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


@router.get("/withdraw-crypto/{transaction_id}/status", response_model=EstadoDeMiEnvioCripto, response_model_exclude_unset=True)
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
            await _notificar_underpaid_review(
                claimed["user_id"],
                transaction_id=claimed.get("transaction_id"))
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


@router.post("/withdraw-crypto/{transaction_id}/cancelar", response_model=MiOrdenCriptoCancelada, response_model_exclude_unset=True)
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
            title="Recibimos tu pago",
            message=f"Tu envío de {para_mostrar(claimed.get('amount_output'), 'VES')} se procesa en breve.",
            notification_type="crypto_send_paid",
            data={"transaction_id": claimed.get("transaction_id")},
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
                transaction_id=claimed.get("transaction_id"),
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
                transaction_id=claimed.get("transaction_id"),
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
                await _notificar_underpaid_review(
                    claimed["user_id"],
                    transaction_id=claimed.get("transaction_id"))
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
        await _notificar_underpaid_review(
            claimed["user_id"],
            transaction_id=claimed.get("transaction_id"))
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

    buscada = clave_del_nombre(texto)
    if not buscada:
        return None, None
    candidatos = [b for b in bancos if clave_del_nombre(b.get("name")) == buscada]
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


@router.get("/bancos-para-transferir", response_model=BancosParaTransferir, response_model_exclude_unset=True)
async def bancos_para_transferir(current_user: User = Depends(get_current_user)):
    """A qué cuentas puede transferir el cliente en bolívares.

    Las usan la recarga y el envío a Brasil pagado en bolívares. Antes la
    recarga las tenía escritas en su código —titular, cédula, teléfono y
    cuentas, servidos a cualquier visitante— y el envío a Brasil no las
    mostraba en ningún lado. Se cargan y se publican desde Contabilidad →
    Bancos. Ver `services/bancos.para_el_cliente`.
    """
    salida = []
    async for banco in db.bank_accounts.find(
            {"currency": "VES", "cobro.publicado": True},
            {"_id": 0, "bank_id": 1, "name": 1, "currency": 1, "is_gateway": 1, "cobro": 1}).sort("name", 1):
        visto = para_el_cliente(banco)
        if visto:
            salida.append(visto)
    return salida


@router.post("/recharge/ves", response_model=MiRecargaVes, response_model_exclude_unset=True, dependencies=[Depends(sin_transacciones_personales)])
async def recharge_ves(request: dict, current_user: User = Depends(get_current_user)):
    """Create a VES recharge request"""
    # LA CARGA DE SALDO, ANTES DE CUALQUIER OTRA COSA.
    #
    #   La empresa no custodia dinero de terceros ni ofrece recarga. La regla
    #   vive en `services/recarga_abierta.py`, no acá.
    #
    #   Ojo con no confundir esta ruta con `/enviar-reais/comprobante`: las dos
    #   reciben una transferencia en bolívares con su comprobante, pero aquélla
    #   paga UN ENVIO y ésta carga saldo. La primera sigue funcionando.
    await recarga_abierta.exigir_abierta(db)

    amount_ves = float(request.get("amount_ves", 0))
    payment_method = request.get("payment_method", "transferencia")

    # Piso de negocio en bolivares. Sin techo, a proposito.
    error_monto = await validate_ves_amount(db, amount_ves)
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
    # El comprobante lo abre después un administrador desde el panel. Sin
    # mirarlo acá, el campo es texto libre elegido por quien recarga.
    try:
        comprobante = limpiar_imagen_opcional(comprobante, campo="El comprobante")
    except ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    # La misma tasa que muestra /api/rate: la cargada, sin ajuste nocturno
    # (se eliminó; ver `routes/basic.py`).
    ves_to_ris = _base_vtr

    # Fórmula oficial: ves_to_ris_rate = VES por 1 RIS  ->  RIS = VES / tasa
    amount_ris = round(amount_ves / ves_to_ris, 2)
    if amount_ris <= 0:
        raise HTTPException(status_code=400, detail="El monto en VES es demasiado bajo para la tasa actual.")
    # Cupo de la cuenta sin verificar: se comprueba ANTES de crear nada.
    _kq_user = await db.users.find_one({"user_id": current_user.user_id})
    _kq_error = await kyc_quota.check_amount(db, _kq_user, amount_ris)
    if _kq_error:
        raise HTTPException(status_code=403, detail=_kq_error)

    amount_input = amount_ves

    # Aviso si el cliente había calculado un RIS distinto (no bloquea: el servidor manda)
    _client_ris = float(request.get("amount_ris", 0) or 0)
    if _client_ris and abs(_client_ris - amount_ris) > 0.01:
        logger.warning(f"recharge_ves: RIS del cliente ({_client_ris}) != servidor ({amount_ris}) user={current_user.user_id}")

    tx_id = f"rech_{uuid.uuid4().hex[:12]}"
    # EL NUMERO CORTO, TAMBIEN ACA
    #
    #   Era la unica orden del historial que no llevaba `display_id`: todas
    #   las demas lo piden al mismo contador. Sin el, el historial mostraba
    #   nombre, fecha y monto y nada mas, y un cliente que escribia «pagué y
    #   no me aparece» no tenia numero que dar.
    display_id = await get_next_withdrawal_id()

    transaction = {
        "transaction_id": tx_id,
        "display_id": display_id,
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

    _resp_rch = {
        "message": "Recarga VES registrada, pendiente de verificacion",
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ves": amount_ves,
        "amount_ris": amount_ris
    }
    await store_idempotency_result(current_user.user_id, "recharge_ves", _rch_key, _resp_rch)
    return _resp_rch

# ══════════════════════════════════════════════════════════════════════════
# Mis recargas en bolívares
# ══════════════════════════════════════════════════════════════════════════
#
# La pantalla «Recargar con VES» muestra las recargas que el cliente ya pidió
# —en revisión, aprobadas, rechazadas con su motivo—. Pide esta ruta desde
# siempre; la ruta existió hasta junio de 2026 y se fue en una limpieza. Desde
# entonces la lista quedaba vacía en silencio y cada visita dejaba un 404.
# Apareció en la revisión general del 21 de septiembre.
#
# Vuelve POR LISTA DE LO PERMITIDO, que la versión vieja no tenía: al
# documento de una recarga el panel le escribe `processed_by` —el
# identificador del administrador que la aprobó o rechazó—, y eso no tiene
# por qué viajar al navegador del cliente.

class UnaRecargaEnBolivares(BaseModel):
    transaction_id: str
    display_id: Optional[str] = None
    amount_ves: Optional[float] = None
    amount_ris: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    destination_bank: Optional[str] = None
    payment_method: Optional[str] = None


@router.get("/recharge/ves/status", response_model=list[UnaRecargaEnBolivares])
async def mis_recargas_en_bolivares(current_user: User = Depends(get_current_user)):
    """Las recargas en bolívares del propio usuario, de la más nueva a la más
    vieja. Veinte alcanzan: es lo que la pantalla lista debajo del formulario."""
    filas = await db.transactions.find(
        {"user_id": current_user.user_id, "type": "recharge_ves"},
        {"_id": 0, "transaction_id": 1, "display_id": 1, "amount_ves": 1,
         "amount_ris": 1, "status": 1, "created_at": 1, "processed_at": 1,
         "rejection_reason": 1, "destination_bank": 1, "payment_method": 1},
    ).sort("created_at", -1).to_list(20)
    for fila in filas:
        _normalize_tx_money(fila)
    return filas


# ============== TRANSACTION HISTORY ==============

# Lo que el cliente ve de su propia operación: la lista y su contrato viven en
# `models/movimientos.py`, juntos, para que no puedan decir cosas distintas.


@router.get("/transactions", response_model=MisMovimientos, response_model_exclude_unset=True)
async def get_transactions(
    # EL TOPE DE `limit`
    #
    #   No tenía. La lista viajaba con las fotos adentro (unos 667 KB cada una),
    #   y un cliente con sesión podía pedir `?limit=100000`: el servidor cargaba
    #   en memoria su historial entero con todas las fotos. Medido: 60 MB con
    #   sesenta operaciones. Las pantallas piden 10; 50 deja margen.
    #
    #   `page` empieza en 1 porque con 0 el `skip` sale negativo, el driver de
    #   Mongo lo rechaza (`ValueError: skip must be >= 0`) y nadie lo atajaba:
    #   llegaba como un 500. Y `limit=0`, para Mongo, no es «ninguna» sino
    #   «sin tope».
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
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
    # Sin las fotos: se piden al tocar «Ver comprobante», por el detalle de
    # esa operación. El porqué, en `models/movimientos.py`.
    transactions = await db.transactions.find(
        query,
        LO_QUE_VE_EN_LA_LISTA
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    con_comprobante = await cuales_tienen_comprobante(db, {
        "user_id": current_user.user_id,
        "transaction_id": {"$in": [t.get("transaction_id") for t in transactions]},
    })
    for _tx in transactions:
        _normalize_tx_money(_tx)
        _tx["tiene_comprobante"] = _tx.get("transaction_id") in con_comprobante

    return {
        "total": total,
        "page": page,
        "limit": limit,
        # El frontend usa `pages` para habilitar la paginacion; sin este campo
        # se quedaba siempre en la pagina 1.
        "pages": math.ceil(total / limit) if limit else 1,
        "transactions": transactions
    }

# ══════════════════════════════════════════════════════════════════════════
# Volver a la pantalla de pago de un pedido que quedó a medias
# ══════════════════════════════════════════════════════════════════════════
#
# El cliente cotizó, vio el QR, y cerró la pantalla. Hasta ahora eso era el
# final: lo que hacía falta para dibujar esa pantalla venía en la respuesta de
# la cotización y no había forma de pedirlo de nuevo.
#
# El por qué de cada regla está en `services/volver_al_pago.py`.

class ComoPagarEstePedido(BaseModel):
    """Lo que la pantalla necesita, y NADA MAS.

    Por lista de lo permitido, como todo lo que ve el usuario. Acá al lado hay
    una respuesta cruda de Mercado Pago con los datos del pagador, y una lista
    de lo prohibido la dejaría salir el día que alguien agregue un campo.
    """
    transaction_id: str
    display_id: Optional[str] = None
    corredor: str                       # "venezuela" | "brasil"
    metodo: Optional[str] = None        # "pix" | "tarjeta" | None (bolívares)
    se_puede_pagar: bool
    motivo: Optional[str] = None        # por qué no, cuando no se puede
    segundos_restantes: int = 0
    # Cuánto es
    amount_input: Optional[float] = None
    amount_output: Optional[float] = None
    currency_input: Optional[str] = None
    currency_output: Optional[str] = None
    rate: Optional[float] = None
    monto_a_pagar: Optional[float] = None
    # Con qué se paga
    payment_order_id: Optional[str] = None
    qr_code: str = ""
    qr_code_base64: str = ""
    copy_paste_code: str = ""
    credit_card: Optional[dict] = None
    debit_card: Optional[dict] = None
    bancos: Optional[list] = None
    # A quién
    beneficiary_data: Optional[dict] = None


@router.get("/envios/{transaction_id}/como-pagar",
            response_model=ComoPagarEstePedido)
async def como_pagar_este_pedido(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
):
    """Todo lo que hace falta para volver a dibujar la pantalla de pago."""
    from services import pago_al_final, tarjeta_del_envio, volver_al_pago

    orden = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id})
    if not orden:
        raise HTTPException(status_code=404, detail="No encontramos ese envío")

    if not orden.get("payment_order_id"):
        # Un envío pagado con saldo no tiene pantalla de pago que mostrar.
        raise HTTPException(
            status_code=409,
            detail="Este envío no se paga por separado: se descontó de tu saldo.")

    de_venezuela = volver_al_pago.es_de_venezuela(orden)
    vencido = volver_al_pago.esta_vencido(orden)
    # Un pedido que ya avanzó tampoco se paga de nuevo, y eso NO es «vencido»:
    # decirle «expiró» a quien ya pagó es el peor mensaje posible.
    ya_avanzo = orden.get("status") not in (pago_al_final.ESPERANDO_PAGO,
                                            pago_al_final.PAGO_VENCIDO,
                                            pago_al_final.PAGO_TARDIO)

    _resp = {
        "transaction_id": transaction_id,
        "display_id": orden.get("display_id"),
        "corredor": "venezuela" if de_venezuela else "brasil",
        "se_puede_pagar": not (vencido or ya_avanzo),
        "segundos_restantes": volver_al_pago.segundos_que_quedan(orden),
        "amount_input": to_float(orden.get("amount_input")),
        "amount_output": to_float(orden.get("amount_output")),
        "currency_input": orden.get("currency_input"),
        "currency_output": orden.get("currency_output"),
        "rate": to_float(orden.get("rate")),
        "monto_a_pagar": to_float(orden.get("payment_amount_brl")
                                  or orden.get("amount_input")),
        "payment_order_id": orden.get("payment_order_id"),
        "beneficiary_data": orden.get("beneficiary_data"),
    }

    if ya_avanzo:
        _resp["motivo"] = ("Este envío ya no está esperando el pago. "
                           "Miralo en tu historial.")
        return _resp
    if vencido:
        _resp["motivo"] = volver_al_pago.por_que_no_se_puede_pagar(orden)
        return _resp

    # ── Todavía se puede pagar: con qué ──────────────────────────────────
    if de_venezuela:
        cobro = await db.gestor_pix_payments.find_one(
            {"payment_id": orden["payment_order_id"],
             "gestor_id": current_user.user_id},
            {"_id": 0, "metodo": 1, "qr_code": 1, "qr_code_base64": 1})
        metodo = tarjeta_del_envio.normalizar_metodo((cobro or {}).get("metodo"))
        _resp["metodo"] = metodo
        if metodo == tarjeta_del_envio.POR_TARJETA:
            # El desglose se RECALCULA, no se guardó. Sale del mismo lugar que
            # cuando se cotizó, así que no puede dar otro número.
            from routes.payments_card import _get_card_fees
            _tarifas = await _get_card_fees()
            for _tipo in ("credit_card", "debit_card"):
                _d = tarjeta_del_envio.cuanto_se_le_cobra(
                    to_decimal(orden.get("payment_amount_brl") or 0),
                    _tipo, _tarifas)
                _resp[_tipo] = {k: to_float(v) for k, v in _d.items()}
        else:
            _resp["qr_code"] = (cobro or {}).get("qr_code") or ""
            _resp["qr_code_base64"] = (cobro or {}).get("qr_code_base64") or ""
            _resp["copy_paste_code"] = _resp["qr_code"]
    else:
        # Brasil: los bancos a los que puede transferir. Se piden de nuevo
        # porque la lista se administra y puede haber cambiado desde que
        # cotizó.
        _resp["bancos"] = await bancos_ves_disponibles()

    return _resp


@router.get("/transactions/{transaction_id}", response_model=MovimientoQueVeElCliente,
            response_model_exclude_unset=True)
async def get_transaction(transaction_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific transaction"""
    transaction = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": current_user.user_id},
        LO_QUE_VE_EL_CLIENTE
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaccion no encontrada")

    _normalize_tx_money(transaction)

    return transaction

# ============== PENDING WITHDRAWAL CHECK ==============

@router.get("/withdrawal/pending", response_model=MiRetiroPendiente, response_model_exclude_unset=True)
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


# ══════════════════════════════════════════════════════════════════════════
# Pagar al final: cotizar el envío y pagarlo con PIX, sin saldo en el medio
# ══════════════════════════════════════════════════════════════════════════
#
# El por qué entero está en `services/pago_al_final.py`. En una línea: sin
# saldo en el medio, la confirmación del pago es UN cambio de estado sobre UN
# documento, y desaparece la ventana en la que el flujo viejo puede cobrar sin
# acreditar.
#
# De fábrica está apagado y convive con el flujo de siempre. Prenderlo no
# apaga nada.

class CotizarEnvioVesRequest(BaseModel):
    amount: float                      # en RIS, que es 1:1 con el real
    beneficiary_id: str
    client_cpf: Optional[str] = None   # el CPF de quien paga el PIX
    idempotency_key: Optional[str] = None
    # CON QUE SE VA A PAGAR, Y POR QUE SE DECIDE ACA Y NO DESPUES.
    #
    #   Con «tarjeta» no se genera ningún QR. Si se generara, la orden quedaría
    #   pagable por las dos vías y el cliente podría pagarla dos veces: sólo
    #   una avanzaría el envío, y para entonces ya le sacaron la plata dos
    #   veces. Está contado en `services/tarjeta_del_envio.py`.
    #
    #   Si no lo mandan, PIX: es lo que había antes de este campo, y un cliente
    #   viejo tiene que seguir recibiendo su código.
    metodo: Optional[str] = None


@router.post("/withdraw-ves/cotizar", response_model=MiCotizacionVes, response_model_exclude_unset=True,
             dependencies=[Depends(sin_transacciones_personales)])
async def cotizar_envio_ves(request: CotizarEnvioVesRequest,
                            current_user: User = Depends(get_current_user)):
    """Deja una orden esperando el pago, y devuelve el QR para pagarla.

    TODO LO QUE PUEDE FALLAR, FALLA ANTES DE CREAR NADA.

        Es el mismo criterio del envío con saldo: allá las validaciones van
        antes del débito para que un rechazo no deje plata movida. Acá van
        antes de pedirle el cobro a Mercado Pago, para que un rechazo no deje
        un QR huérfano que alguien puede pagar sin que exista el envío.
    """
    from services import cpf_de_la_cuenta, pago_al_final, tarjeta_del_envio
    from services.notifications import create_notification

    await pago_al_final.exigir_activo(db)

    metodo = tarjeta_del_envio.normalizar_metodo(request.metodo)

    # CON TARJETA, SOLO VERIFICADOS, Y SE COMPRUEBA ACA.
    #
    #   Un contracargo se puede pedir hasta ciento veinte días después del
    #   cobro, cosa que con PIX no pasa. Si para entonces el envío ya salió,
    #   la pérdida es de la empresa, así que la plata tiene que estar atada a
    #   una persona identificada.
    #
    #   Va acá, antes de crear nada, y no al cobrar: rechazarlo recién en el
    #   formulario de la tarjeta es dejarlo completar todo para nada. La ruta
    #   que cobra lo comprueba igual, porque una guarda que vive en otra ruta
    #   es una guarda hasta que alguien reordena las rutas.
    if (metodo == tarjeta_del_envio.POR_TARJETA
            and current_user.verification_status != "verified"):
        raise HTTPException(status_code=403,
                            detail=tarjeta_del_envio.SIN_VERIFICAR)

    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    # Idempotencia, igual que el envío con saldo: dos clics no cotizan dos
    # veces ni dejan dos cobros abiertos por el mismo envío.
    _idem_new, _idem_existing = await claim_idempotency(
        current_user.user_id, "cotizar_ves", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409,
                            detail="Esta operación ya se está procesando. Espera un momento.")

    # 1) El beneficiario, antes que nada: un cobro sin destino no sirve.
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id})
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")

    # 2) La tasa, con el mismo ajuste de horario que `/api/rate`, para que lo
    #    que ve en la pantalla y lo que se guarda sean el mismo número.
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    _base = (rate or {}).get("ris_to_ves")
    if not _base or _base <= 0:
        raise HTTPException(status_code=503,
                            detail="La tasa no está disponible en este momento. Intenta más tarde.")
    ris_to_ves = _base    # la de /api/rate, sin ajuste nocturno
    amount_ves = round(request.amount * ris_to_ves, 2)

    # 3) EL BONO DESCUENTA DEL COBRO, no del saldo.
    #
    #    Acá no hay saldo que debitar, así que el bono se convierte en lo que
    #    de verdad era: menos plata a poner. El beneficiario recibe los mismos
    #    bolívares; lo que baja es el real que se cobra por PIX.
    #
    #    `disponible_para_enviar` es la única función que decide si el bono se
    #    puede gastar —mira que esté liberado y no bloqueado—, así que acá no
    #    se repite ninguna de esas reglas.
    _usuario = await db.users.find_one({"user_id": current_user.user_id})
    _total = to_decimal(request.amount)
    _del_bono = min(_total, await bonos.disponible_para_enviar(db, _usuario or {}))
    _a_cobrar = _total - _del_bono

    if _a_cobrar <= 0:
        # El bono cubre el envío entero. No hay nada que cobrar, y un cobro de
        # cero no lo acepta ninguna pasarela. Se rechaza con el motivo, en vez
        # de pedirle a Mercado Pago un QR imposible.
        raise HTTPException(
            status_code=400,
            detail="Tu bono cubre este envío entero. Por ahora, para usarlo "
                   "solo, hacé el envío desde tu saldo.")

    # 4) Tope de PIX y cupo, sobre LO QUE SE VA A COBRAR y no sobre el envío.
    #    Con bono, esos dos números son distintos, y el que tiene que caber en
    #    el tope de la pasarela es el que la pasarela va a cobrar.
    _cobro_float = to_float(_a_cobrar)
    error_monto = await validate_pix_amount(db, _cobro_float)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)
    _cupo = await kyc_quota.check_amount(db, _usuario, _cobro_float)
    if _cupo:
        raise HTTPException(status_code=403, detail=_cupo)

    # 5) El CPF de quien paga tiene que ser el titular de la cuenta. Es el
    #    control que ata cada real que entra a una persona, y es el mismo que
    #    aplica la recarga: se llama a la misma función, no se copia la regla.
    try:
        cpf_del_pago = await cpf_de_la_cuenta.exigir_para_pagar(
            db, _usuario or {}, request.client_cpf)
    except cpf_de_la_cuenta.CpfInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (cpf_de_la_cuenta.CpfDeOtro, cpf_de_la_cuenta.CpfVetado,
            cpf_de_la_cuenta.CpfEnUso) as e:
        raise HTTPException(status_code=403, detail=str(e))

    # 5 bis) EL BONO SE DEBITA ACA, NO AL CONFIRMARSE EL PAGO.
    #
    #   La primera versión de esta ruta descontaba el bono del cobro y NUNCA lo
    #   debitaba: el mismo bono habría servido para envíos infinitos. Lo
    #   encontró `test_solo_el_envio_a_venezuela_sabe_gastar_el_bono`, la
    #   guarda que vigila quién puede nombrar esa cuenta.
    #
    #   Va acá y no en la confirmación por dos motivos:
    #
    #     · Acá se puede fallar. Si el bono ya no está —otra pestaña lo gastó
    #       hace un segundo— todavía no se le generó un QR a nadie. En la
    #       confirmación el cliente YA PAGO, y no hay nada que rechazar.
    #     · La confirmación tiene que seguir siendo UN cambio de estado sobre
    #       UN documento. Meterle el débito del bono la volvería a partir en
    #       dos escrituras, que es justo la ventana que este flujo elimina.
    #
    #   El `$gte` dentro del filtro es lo que impide gastarlo dos veces: dos
    #   pedidos simultáneos no pueden pasar los dos. Mismo patrón que el envío
    #   con saldo.
    #
    #   Si nadie paga, `pago_al_final.vencer_las_viejas` lo devuelve.
    if _del_bono > 0:
        _con_bono = await db.users.find_one_and_update(
            {"user_id": current_user.user_id,
             bonos.CUENTA_DEL_BONO: {"$gte": to_decimal128(_del_bono)}},
            {"$inc": {bonos.CUENTA_DEL_BONO: to_decimal128(-_del_bono)}})
        if _con_bono is None:
            raise HTTPException(
                status_code=409,
                detail="Tu bono cambió mientras completabas el envío. "
                       "Volvé a empezar para ver el monto correcto.")

    async def _devolver_el_bono():
        """Para cualquier salida por error de acá en adelante. El bono ya salió
        de su cuenta y el envío no va a existir."""
        if _del_bono > 0:
            await db.users.update_one(
                {"user_id": current_user.user_id},
                {"$inc": {bonos.CUENTA_DEL_BONO: to_decimal128(_del_bono)}})

    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    referencia = pago_al_final.nuevo_id_de_cobro()
    ahora = datetime.now(timezone.utc)
    vence = pago_al_final.vence_en(ahora)

    beneficiary_data = {
        "full_name": beneficiary.get("full_name"),
        "id_document": beneficiary.get("id_document"),
        "bank": beneficiary.get("bank"),
        "bank_code": beneficiary.get("bank_code"),
        "phone_number": beneficiary.get("phone_number"),
        "account_number": beneficiary.get("account_number"),
        "payment_type": beneficiary.get("payment_type", "transferencia"),
    }

    orden = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount,
        "amount_output": amount_ves,
        "currency_input": "RIS",
        "currency_output": "VES",
        "rate": ris_to_ves,
        "status": pago_al_final.ESPERANDO_PAGO,
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": beneficiary_data,
        "created_at": ahora,
        # Lo que distingue a esta orden de una del flujo viejo.
        "funded_from": "payment",
        "payment_order_id": referencia,
        "payment_expires_at": vence,
        "payment_amount_brl": _cobro_float,
        "bono_aplicado": to_float(_del_bono),
    }

    # 6) Lo que te queda a vos, ANTES de pedir el cobro. Si falta la tasa de
    #    costo la operación se rechaza acá, sin haberle generado un QR a nadie.
    try:
        orden.update(await comisiones.campos_de(
            db, via="ris_to_ves", monto_cliente=request.amount,
            tasa_cliente=ris_to_ves))
    except comisiones.FaltaLaTasaDeCosto:
        await _devolver_el_bono()
        raise HTTPException(status_code=503,
                            detail="El envío no está disponible en este momento. Intenta más tarde.")

    # 7) El cobro. Si Mercado Pago no devuelve un código, NO SE GUARDA NADA:
    #    es la lección escrita en `routes/gestor_pix.py`, donde un cobro sin
    #    código quedaba guardado y la persona veía una pantalla rota.
    from routes.gestor_pix import MP_AVAILABLE, mercadopago_service
    qr = ""
    qr_b64 = ""
    mp_id = None
    # CON TARJETA NO SE PIDE NINGUN QR. Ver el comentario del campo `metodo`:
    # un QR vivo al lado de una tarjeta es el doble cobro.
    if (metodo == tarjeta_del_envio.POR_PIX
            and MP_AVAILABLE and mercadopago_service):
        try:
            _nombre = (_usuario or {}).get("name") or "Cliente"
            _partes = _nombre.split()
            mp = await asyncio.to_thread(
                mercadopago_service.create_pix_payment,
                amount=_cobro_float,
                description=f"Envio {display_id}",
                payer_email=(_usuario or {}).get("email") or "cliente@risapp.com",
                payer_first_name=_partes[0],
                payer_last_name=_partes[-1] if len(_partes) > 1 else "RIS",
                payer_cpf=cpf_del_pago,
                external_reference=referencia)
            if mp and mp.get("success"):
                mp_id = mp.get("payment_id")
                qr = mp.get("qr_code", "")
                qr_b64 = mp.get("qr_code_base64", "")
        except Exception as e:
            logger.error("cotizar_envio_ves: Mercado Pago falló para %s: %s",
                         referencia, e)

    # El código que falta sólo es un problema cuando se pidió uno.
    if metodo == tarjeta_del_envio.POR_PIX and not qr:
        await _devolver_el_bono()
        logger.error("COBRO SIN CODIGO para el envío %s: no se guarda nada.",
                     referencia)
        raise HTTPException(
            status_code=503,
            detail="No pudimos generar el cobro con PIX en este momento. "
                   "Probá de nuevo en unos minutos.")

    # 8) La orden PRIMERO y el cobro después.
    #
    #    Si falla el segundo, se vence la orden en el acto: queda una orden
    #    muerta y un QR que nadie va a poder cruzar con nada, y el cliente ve
    #    un error en vez de un código que no sirve. Al revés —el cobro primero—
    #    dejaría un cobro pagable sin envío detrás, que es la falla cara.
    await db.transactions.insert_one(orden)
    try:
        await db.gestor_pix_payments.insert_one({
            "payment_id": referencia,
            "mp_payment_id": mp_id,
            "gestor_id": current_user.user_id,
            "proposito": pago_al_final.PROPOSITO,
            # Con qué se cotizó. Es lo que mira `tarjeta_del_envio.es_de_tarjeta`
            # para no dejar que una orden de PIX se cobre además con tarjeta.
            "metodo": metodo,
            "transaction_id": tx_id,
            "amount_ris": _cobro_float,
            "amount_brl": _cobro_float,
            "amount_ves": amount_ves,
            "qr_code": qr,
            "qr_code_base64": qr_b64,
            "status": "pending",
            "created_at": ahora,
            "expires_at": vence,
            "is_mp_payment": mp_id is not None,
        })
    except Exception as e:
        await db.transactions.update_one(
            {"transaction_id": tx_id},
            {"$set": {"status": pago_al_final.PAGO_VENCIDO, "expired_at": ahora}})
        await _devolver_el_bono()
        logger.error("cotizar_envio_ves: no se pudo guardar el cobro %s, la "
                     "orden %s queda vencida: %s", referencia, tx_id, e)
        raise HTTPException(status_code=503,
                            detail="No pudimos generar el cobro en este momento. "
                                   "Probá de nuevo en unos minutos.")

    await create_notification(
        user_id=current_user.user_id,
        title="Tu envío espera el pago",
        message=f"Pagá {para_mostrar(_cobro_float, 'BRL')} con PIX y salimos a "
                f"despachar {para_mostrar(amount_ves, 'VES')}.",
        notification_type="withdrawal_awaiting_payment",
        data={"transaction_id": tx_id})

    _resp = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ris": request.amount,
        "amount_ves": amount_ves,
        "rate": ris_to_ves,
        "bono_aplicado": to_float(_del_bono),
        "amount_brl": _cobro_float,
        "qr_code": qr,
        "qr_code_base64": qr_b64 or "",
        "copy_paste_code": qr,
        "expires_at": vence.isoformat(),
        "expires_in_seconds": pago_al_final.MINUTOS_DEL_COBRO * 60,
        "metodo": metodo,
        # LA REFERENCIA DEL COBRO VA SIEMPRE, TAMBIEN CON PIX.
        #
        #   Antes iba sólo con tarjeta —abajo—, con el argumento de que con
        #   PIX «el código ya lo identifica». Es cierto para pagar, pero no
        #   para PREGUNTAR si se pagó: la pantalla le pregunta al servidor por
        #   `/gestor/pix/status/{referencia}`, y sin la referencia no tenía
        #   por qué preguntar. Ese fue el motivo exacto por el que el cliente
        #   pagaba con PIX y la pantalla del QR se quedaba igual.
        "payment_order_id": referencia,
    }

    # EL DESGLOSE DE LA TARJETA LO CALCULA EL SERVIDOR, Y SOLO EL SERVIDOR.
    #
    #   La pantalla podría sacar la cuenta sola: `/payments/card/config` le
    #   publica las tarifas. Pero entonces habría dos implementaciones de la
    #   misma fórmula, y el día que una cambie el cliente vería un número y se
    #   le cobraría otro. Acá sale UNA vez, del mismo lugar del que sale lo que
    #   se le va a cobrar de verdad.
    #
    #   Van las tres cifras y no sólo el total: quien ve «R$ 104,89» sin saber
    #   de dónde salen los 4,89 se cree que le están cobrando de más.
    if metodo == tarjeta_del_envio.POR_TARJETA:
        # La referencia ya va arriba para las dos vías. Con tarjeta es además
        # lo único que ata el formulario de la tarjeta a esta orden. Conocerla
        # no alcanza para pagar el envío de otro: la ruta que cobra filtra
        # también por el dueño.

        from routes.payments_card import _get_card_fees
        _tarifas = await _get_card_fees()
        for _tipo in ("credit_card", "debit_card"):
            _d = tarjeta_del_envio.cuanto_se_le_cobra(
                _a_cobrar, _tipo, _tarifas)
            _resp[_tipo] = {k: to_float(v) for k, v in _d.items()}

    await store_idempotency_result(current_user.user_id, "cotizar_ves",
                                   request.idempotency_key, _resp)
    return _resp


# ══════════════════════════════════════════════════════════════════════════
# El corredor inverso: se cotiza en bolívares y se liquida en reais
# ══════════════════════════════════════════════════════════════════════════
#
# Mismo flujo que el envío a Venezuela, en el otro sentido y con otra forma de
# pagar: el cliente transfiere en bolívares y sube el comprobante, y un
# administrador verifica que la plata entró antes de que la orden entre en la
# cola de despacho. El por qué de cada estado está en
# `services/pago_al_final.py`.
#
# SIN SALDO EN EL MEDIO, igual que el otro corredor. Esa es la propiedad que
# hace que cada paso sea un solo cambio de estado sobre un solo documento.

class CotizarEnvioReaisRequest(BaseModel):
    amount_ves: float                  # lo que el cliente pone, en bolívares
    beneficiary_id: str                # un beneficiario en Brasil
    idempotency_key: Optional[str] = None


class ComprobanteDelEnvioRequest(BaseModel):
    transaction_id: str
    destination_bank: str              # a qué banco transfirió
    proof_image: str                   # el comprobante


@router.post("/enviar-reais/cotizar", response_model=MiCotizacionReais, response_model_exclude_unset=True,
             dependencies=[Depends(sin_transacciones_personales)])
async def cotizar_envio_reais(request: CotizarEnvioReaisRequest,
                              current_user: User = Depends(get_current_user)):
    """Deja una orden esperando que el cliente pague en bolívares.

    No genera ningún cobro contra una pasarela: acá el cliente transfiere por
    su cuenta y después sube el comprobante. Así que esta ruta sólo cotiza y
    reserva la tasa.
    """
    from services import pago_al_final

    await pago_al_final.exigir_activo(db)

    if request.amount_ves <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    # El piso en bolívares, el mismo que la recarga: es la misma plata
    # entrando por el mismo lugar.
    error_monto = await validate_ves_amount(db, request.amount_ves)
    if error_monto:
        raise HTTPException(status_code=400, detail=error_monto)

    _idem_new, _idem_existing = await claim_idempotency(
        current_user.user_id, "cotizar_reais", request.idempotency_key)
    if not _idem_new:
        if _idem_existing and _idem_existing.get("result"):
            return _idem_existing["result"]
        raise HTTPException(status_code=409,
                            detail="Esta operación ya se está procesando. Espera un momento.")

    # EL BENEFICIARIO TIENE QUE SER DE BRASIL, y se comprueba.
    #
    #   Sin esto, mandar un `beneficiary_id` de Venezuela crearía una orden que
    #   promete reales a una cuenta en bolívares. El operador lo descubriría
    #   recién al ir a pagarla.
    beneficiary = await db.beneficiaries.find_one({
        "beneficiary_id": request.beneficiary_id,
        "user_id": current_user.user_id})
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado")
    if beneficiary.get("pais") != "BR":
        raise HTTPException(
            status_code=400,
            detail="Ese beneficiario no es de Brasil. Elegí uno con clave PIX.")

    # La tasa del sentido inverso, la misma que muestra /api/rate.
    rate_doc = await db.rates.find_one(sort=[("updated_at", -1)])
    _base = (rate_doc or {}).get("ves_to_ris_rate")
    if not _base or _base <= 0:
        raise HTTPException(status_code=503,
                            detail="La tasa no está disponible en este momento. Intenta más tarde.")
    ves_to_ris = _base

    # La fórmula oficial, la misma que la recarga en bolívares:
    # `ves_to_ris_rate` son los bolívares que vale 1 RIS, así que se divide.
    amount_ris = round(request.amount_ves / ves_to_ris, 2)
    if amount_ris <= 0:
        raise HTTPException(status_code=400,
                            detail="Ese monto queda en cero reales. Probá con uno mayor.")

    # El cupo de la cuenta sin verificar se mide sobre los REALES, que es la
    # moneda en la que están escritos los topes de esta aplicación.
    _usuario = await db.users.find_one({"user_id": current_user.user_id})
    _cupo = await kyc_quota.check_amount(db, _usuario, amount_ris)
    if _cupo:
        raise HTTPException(status_code=403, detail=_cupo)

    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    display_id = await get_next_withdrawal_id()
    ahora = datetime.now(timezone.utc)
    vence = pago_al_final.vence_en(ahora)

    orden = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "user_id": current_user.user_id,
        "type": "withdrawal",
        "amount_input": request.amount_ves,
        "amount_output": amount_ris,
        "currency_input": "VES",
        "currency_output": "BRL",
        "rate": ves_to_ris,
        "status": pago_al_final.ESPERANDO_PAGO,
        "beneficiary_id": request.beneficiary_id,
        "beneficiary_data": {
            "full_name": beneficiary.get("full_name"),
            "cpf": beneficiary.get("cpf"),
            "pix_key": beneficiary.get("pix_key"),
            "pais": "BR",
            "payment_type": "pix_br",
        },
        "created_at": ahora,
        "funded_from": "payment",
        "payment_order_id": pago_al_final.nuevo_id_de_cobro_reais(),
        "payment_expires_at": vence,
    }
    await db.transactions.insert_one(orden)

    _resp = {
        "transaction_id": tx_id,
        "display_id": display_id,
        "amount_ves": request.amount_ves,
        "amount_brl": amount_ris,
        "rate": ves_to_ris,
        "bancos": await bancos_ves_disponibles(),
        "expires_at": vence.isoformat(),
        "expires_in_seconds": pago_al_final.MINUTOS_DEL_COBRO * 60,
    }
    await store_idempotency_result(current_user.user_id, "cotizar_reais",
                                   request.idempotency_key, _resp)
    return _resp


@router.post("/enviar-reais/comprobante", response_model=MiComprobanteRecibido, response_model_exclude_unset=True,
             dependencies=[Depends(sin_transacciones_personales)])
async def comprobante_del_envio_reais(request: ComprobanteDelEnvioRequest,
                                      current_user: User = Depends(get_current_user)):
    """El cliente transfirió en bolívares y sube el comprobante.

    NO ACREDITA NADA. Deja la orden esperando que un administrador mire el
    comprobante. Quien decide si esa plata entró es la persona que lo abre.
    """
    from services import pago_al_final

    await pago_al_final.exigir_activo(db)

    # El comprobante, con la misma limpieza que la recarga en bolívares: es
    # texto libre elegido por quien paga, y el panel lo va a abrir.
    try:
        comprobante = limpiar_imagen_opcional(request.proof_image,
                                              campo="El comprobante")
    except ImagenInvalida as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not comprobante:
        raise HTTPException(
            status_code=400,
            detail="Subí el comprobante de la transferencia. Es lo que miramos "
                   "para despachar tu envío.")

    # El banco tiene que resolver contra contabilidad, y se rechaza ACA.
    # Aceptar uno que no resuelve deja una orden que nadie va a poder procesar,
    # y el cliente se entera días después.
    banco_id, banco_doc = await resolve_ves_bank((request.destination_bank or "").strip())
    if not banco_id:
        disponibles = await bancos_ves_disponibles()
        raise HTTPException(
            status_code=400,
            detail=("Ese banco no está disponible en este momento. Probá con otro."
                    + (f" Disponibles: {', '.join(disponibles)}." if disponibles else "")))

    orden = await pago_al_final.recibir_comprobante(
        db, request.transaction_id, current_user.user_id,
        comprobante=comprobante, banco_id=banco_id,
        # El nombre del banco que se encontró, no lo que mandó la pantalla: la
        # pantalla manda el `bank_id`, y el panel mostraría ese código en vez
        # del nombre.
        banco_nombre=(banco_doc or {}).get("name") or (request.destination_bank or "").strip())

    await create_notification(
        user_id=current_user.user_id,
        title="Recibimos tu comprobante",
        message=f"Lo estamos revisando. En cuanto confirmemos el pago "
                f"despachamos {para_mostrar(orden.get('amount_output'), 'BRL')}.",
        notification_type="withdrawal_awaiting_review",
        data={"transaction_id": orden.get("transaction_id")})

    return {
        "message": "Recibimos tu comprobante. Lo estamos revisando.",
        "transaction_id": orden.get("transaction_id"),
        "status": orden.get("status"),
    }
