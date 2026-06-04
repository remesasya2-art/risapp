import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
import os

import httpx
from database import db
from fastapi import APIRouter, Depends, HTTPException, Request
from models.user import User
from pydantic import BaseModel
from routes.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/btc", tags=["btc-lightning"])

BLINK_API_KEY = os.getenv("BLINK_API_KEY", "")
BLINK_WEBHOOK_SECRET = os.getenv("BLINK_WEBHOOK_SECRET" , "" )
BLINK_WALLET_ID = os.getenv("BLINK_WALLET_ID", "81812448-e78e-47fb-b6cd-d827fc952536")
BLINK_GRAPHQL_URL = "https://api.blink.sv/graphql"

_btc_price_cache = {"price": 58500.0, "updated_at": None}

MARGEN = 0.99
COMISION = 1.02
LIMITE_DIARIO_USD = 500.0


async def _get_tasa_ves():
    config = await db.config.find_one({"clave": "tasa_usd_ves_btc"})
    return float(config["valor"]) if config and config.get("valor") else 680.0


async def _get_btc_price():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://blockchain.info/ticker")
            data = resp.json()
            price = float(data["USD"]["last"])
            _btc_price_cache["price"] = price
            _btc_price_cache["updated_at"] = datetime.now(timezone.utc)
            return price
    except Exception as e:
        logger.warning(f"Error precio BTC: {e}")
        return _btc_price_cache["price"]


async def _get_total_enviado_hoy(user_id):
    hace_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    pipeline = [
        {"$match": {"user_id": user_id, "tipo": "btc_remesa", "estado": {"$in": ["pendiente", "pagado", "enviado"]}, "creado_en": {"$gte": hace_24h}}},
        {"$group": {"_id": None, "total_usd": {"$sum": "$usd_cliente"}}}
    ]
    result = await db.btc_remesas.aggregate(pipeline).to_list(1)
    return result[0]["total_usd"] if result else 0.0


def _verify_blink_signature(svix_id, svix_timestamp, body, signature_header):
    if not BLINK_WEBHOOK_SECRET or not svix_id or not svix_timestamp:
        return False
    try:
        secret_bytes = base64.b64decode(BLINK_WEBHOOK_SECRET.split("_", 1)[1])
    except Exception:
        return False
    signed_content = svix_id.encode() + b"." + svix_timestamp.encode() + b"." + body
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()
    for passed_sig in (signature_header or "").split(" "):
        parts = passed_sig.split(",", 1)
        if len(parts) < 2:
            continue
        if hmac.compare_digest(expected, parts[1]):
            return True
    return False


class GenerarInvoiceRequest(BaseModel):
    usd_cliente: float
    beneficiario_id: str


class MarcarEnviadoRequest(BaseModel):
    remesa_id: str
    operador_id: str


@router.get("/precio")
async def get_precio_btc():
    precio = await _get_btc_price()
    tasa_ves = await _get_tasa_ves()
    return {"precio_btc": precio, "tasa_btc_ves": tasa_ves, "updated_at": _btc_price_cache.get("updated_at")}


@router.post("/generar-invoice")
async def generar_invoice(body: GenerarInvoiceRequest, current_user: User = Depends(get_current_user)):
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Debes completar la verificacion KYC para realizar envios con BTC Lightning.")
    if body.usd_cliente <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
        
    enviado_hoy = await _get_total_enviado_hoy(current_user.user_id)
    if enviado_hoy + body.usd_cliente > LIMITE_DIARIO_USD:
        disponible = max(0.0, LIMITE_DIARIO_USD - enviado_hoy)
        raise HTTPException(status_code=429, detail=f"Limite diario alcanzado. Disponible: ${disponible:.2f} USD.")
        
    beneficiario = await db.beneficiaries.find_one({"beneficiary_id": body.beneficiario_id, "user_id": current_user.user_id})
    if not beneficiario:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado.")
        
    precio_btc = await _get_btc_price()
    tasa_ves = await _get_tasa_ves()
    precio_con_margen = precio_btc * MARGEN
    btc_pagar = (body.usd_cliente * COMISION) / precio_con_margen
    
    # Aseguramos que sats sea un entero (int)
    sats = int(round(btc_pagar * 100_000_000))
    ves_recibe = body.usd_cliente * tasa_ves
    memo = f"RIS-{current_user.user_id[:8]}-{uuid.uuid4().hex[:8]}"
    
    mutation = """
    mutation LnInvoiceCreate($input: LnInvoiceCreateInput!) {
      lnInvoiceCreate(input: $input) {
        invoice {
          paymentRequest
          paymentHash
        }
        errors {
          message
        }
      }
    }
    """
    
    if not BLINK_API_KEY:
        raise HTTPException(status_code=503, detail="El proveedor de pagos BTC no esta configurado.")
        
    try:
        # Headers corregidos usando la cabecera estándar de Blink (Bearer)
        headers = {
            "X-API-KEY": BLINK_API_KEY,
            "Content-Type": "application/json"
        }
            
        payload = {
            "query": mutation,
            "variables": {
                "input": {
                    "amount": sats,
                    "memo": memo,
                    "walletId": BLINK_WALLET_ID
                }
            }
        }
            
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(BLINK_GRAPHQL_URL, headers=headers, json=payload)
            result = resp.json()
            logger.error(f"Blink lnInvoiceCreate response: {resp.status_code} body={resp.text}")
            
    except Exception as e:
        logger.error(f"Blink except: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="Error al conectar con el proveedor de pagos.")
        
    ln_data = result.get("data", {}).get("lnInvoiceCreate", {})
    errors = ln_data.get("errors", [])
    if errors:
        raise HTTPException(status_code=502, detail=f"Error Blink: {errors[0].get('message')}")
        
    invoice = ln_data.get("invoice", {})
    payment_request = invoice.get("paymentRequest")
    payment_hash = invoice.get("paymentHash")
    
    if not payment_request:
        raise HTTPException(status_code=502, detail=f"No se pudo generar el invoice. BLINK={result}.")
        
    remesa_id = str(uuid.uuid4())
    await db.btc_remesas.insert_one({
        "remesa_id": remesa_id, 
        "user_id": current_user.user_id, 
        "beneficiario_id": body.beneficiario_id, 
        "beneficiario_data": {k: v for k, v in beneficiario.items() if k != "_id"}, 
        "usd_cliente": body.usd_cliente, 
        "ves_recibe": ves_recibe, 
        "btc_pagar": btc_pagar, 
        "sats": sats, 
        "precio_btc_usado": precio_btc, 
        "precio_con_margen": precio_con_margen, 
        "tasa_ves": tasa_ves, 
        "payment_request": payment_request, 
        "payment_hash": payment_hash, 
        "memo": memo, 
        "tipo": "btc_remesa", 
        "estado": "pendiente", 
        "no_reembolsable": True, 
        "creado_en": datetime.now(timezone.utc), 
        "expira_en": datetime.now(timezone.utc) + timedelta(minutes=30)
    })
    
    return {
        "remesa_id": remesa_id, 
        "qr": f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={payment_request}",
        "payment_request": payment_request, 
        "btc": f"{btc_pagar:.8f}", 
        "sats": sats, 
        "usd": body.usd_cliente, 
        "ves_recibe": ves_recibe, 
        "precio_btc_usado": precio_btc, 
        "tasa_ves": tasa_ves, 
        "expira_en": 1800, 
        "aviso": "Los pagos en BTC no son reembolsables bajo ningun motivo."
    }


@router.get("/limite-diario")
async def get_limite_diario(current_user: User = Depends(get_current_user)):
    enviado_hoy = await _get_total_enviado_hoy(current_user.user_id)
    return {"limite_diario_usd": LIMITE_DIARIO_USD, "enviado_hoy_usd": enviado_hoy, "disponible_usd": max(0.0, LIMITE_DIARIO_USD - enviado_hoy)}


@router.post("/webhook/blink")
async def webhook_blink(request: Request):
    body = await request.body()
    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    signature = request.headers.get("svix-signature", "")
    try:
        if abs(time.time() - int(svix_timestamp)) > 300:
            raise HTTPException(status_code=401, detail="Timestamp fuera de rango")
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Timestamp invalido")
    if not _verify_blink_signature(svix_id, svix_timestamp, body, signature):
        raise HTTPException(status_code=401, detail="Firma invalida")
    payload = await request.json()
    transaction = payload.get("transaction", {})
    payment_hash = transaction.get("initiationVia", {}).get("paymentHash") or payload.get("payment_hash") or payload.get("invoice_id")
    status = str(transaction.get("status", payload.get("status", ""))).upper()
    if status not in ("PAID", "SUCCESS"):
        return {"ok": True, "msg": "Evento ignorado"}
    remesa = await db.btc_remesas.find_one({"$or": [{"payment_hash": payment_hash}, {"remesa_id": payment_hash}], "estado": "pendiente"})
    if not remesa:
        return {"ok": True, "msg": "Orden no encontrada o ya procesada"}
    ves_recibe = remesa["ves_recibe"]
    user_id = remesa["user_id"]
    await db.btc_ves_wallets.update_one({"user_id": user_id}, {"$inc": {"saldo": ves_recibe}, "$set": {"moneda": "BTC-VES", "user_id": user_id}, "$setOnInsert": {"creado_en": datetime.now(timezone.utc)}}, upsert=True)
    await db.btc_remesas.update_one({"remesa_id": remesa["remesa_id"]}, {"$set": {"estado": "pagado", "pagado_en": datetime.now(timezone.utc)}})
    try:
        from services.notifications import create_notification
        await create_notification(user_id=user_id, title="Pago BTC recibido", message=f"Recibimos tu pago. Tu envío de {ves_recibe:,.2f} BTC-VES sera procesado en maximo 15 minutos.", notification_type="btc_payment")
    except Exception as e:
        logger.warning(f"Error notificacion usuario: {e}")
    try:
        from services.whatsapp import send_whatsapp_notification
        beneficiario_data = remesa.get("beneficiario_data", {})
        nombre_benef = beneficiario_data.get("full_name", "N/A")
        cedula_benef = beneficiario_data.get("id_document", "N/A")
        banco_benef = beneficiario_data.get("bank_code", "") or beneficiario_data.get("bank", "N/A")
        telefono_benef = beneficiario_data.get("phone_number", "N/A")
        tipo_pago = beneficiario_data.get("payment_type", "transferencia")
        remesa_id_corto = remesa.get("remesa_id", "N/A")[:8].upper()
        usd_cliente = remesa.get("usd_cliente", 0)
        admin_msg = (
            f"🔔 NUEVA ORDEN BTC PAGADA\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: {remesa_id_corto}\n"
            f"💵 USD: ${usd_cliente:,.2f}\n"
            f"💵 VES a enviar: {ves_recibe:,.2f} Bs\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Beneficiario: {nombre_benef}\n"
            f"🪪 Cédula: {cedula_benef}\n"
            f"🏦 Banco: {banco_benef}\n"
            f"📱 Teléfono: {telefono_benef}\n"
            f"💳 Tipo: {tipo_pago.upper()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Por favor procesar en max 15 min."
        )
        await send_whatsapp_notification(admin_msg)
    except Exception as e:
        logger.warning(f"Error notificacion admin WhatsApp: {e}")
    try:
        from services.notifications import create_notification
        beneficiario_data = remesa.get("beneficiario_data", {})
        nombre_benef = beneficiario_data.get("full_name", "N/A")
        cedula_benef = beneficiario_data.get("id_document", "N/A")
        banco_benef = beneficiario_data.get("bank_code", "") or beneficiario_data.get("bank", "N/A")
        telefono_benef = beneficiario_data.get("phone_number", "N/A")
        tipo_pago = beneficiario_data.get("payment_type", "transferencia").upper()
        remesa_id_corto = remesa.get("remesa_id", "N/A")[:8].upper()
        usd_cliente = remesa.get("usd_cliente", 0)
        admin_title = f"💸 Nueva orden BTC pagada - ID {remesa_id_corto}"
        admin_message = (f"${usd_cliente:,.2f} USD | {ves_recibe:,.2f} Bs | {tipo_pago}\n"
                        f"Beneficiario: {nombre_benef} | CI: {cedula_benef}\n"
                        f"Banco: {banco_benef} | Tel: {telefono_benef}")
        admins = await db.users.find({"role": {"$in": ["admin", "super_admin"]}}, {"user_id": 1}).to_list(50)
        for admin in admins:
            try:
                await create_notification(user_id=admin["user_id"], title=admin_title, message=admin_message, notification_type="btc_remesa_pagada")
            except Exception as ea:
                logger.warning(f"Error notif admin {admin.get('user_id')}: {ea}")
    except Exception as e:
        logger.warning(f"Error notificacion in-app admins: {e}")
    return {"ok": True}


@router.post("/operador/marcar-enviado")
async def marcar_enviado(body: MarcarEnviadoRequest, current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Solo operadores pueden marcar envíos como completados.")
    remesa = await db.btc_remesas.find_one({"remesa_id": body.remesa_id})
    if not remesa:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    if remesa["estado"] != "pagado":
        raise HTTPException(status_code=400, detail=f"Estado actual: {remesa['estado']}")
    wallet = await db.btc_ves_wallets.find_one({"user_id": remesa["user_id"]})
    saldo_actual = wallet["saldo"] if wallet else 0.0
    if saldo_actual < remesa["ves_recibe"]:
        raise HTTPException(status_code=400, detail="Saldo BTC-VES insuficiente.")
    await db.btc_ves_wallets.update_one({"user_id": remesa["user_id"]}, {"$inc": {"saldo": -remesa["ves_recibe"]}})
    await db.btc_remesas.update_one({"remesa_id": body.remesa_id}, {"$set": {"estado": "enviado", "enviado_en": datetime.now(timezone.utc), "operador_id": body.operador_id}})
    try:
        from services.notifications import create_notification
        nombre = remesa.get("beneficiario_data", {}).get("full_name", "tu beneficiario")
        await create_notification(user_id=remesa["user_id"], title="Envío completado", message=f"Tu envío de {remesa['ves_recibe']:,.2f} Bs fue completado a {nombre}.", notification_type="btc_enviado")
    except Exception as e:
        logger.warning(f"Error notificacion: {e}")
    return {"ok": True, "msg": "Orden marcada como enviada.", "remesa_id": body.remesa_id}


@router.get("/operador/pendientes")
async def get_remesas_pendientes(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Solo operadores pueden ver esta lista.")
    remesas = await db.btc_remesas.find({"estado": "pagado"}, {"_id": 0}).sort("pagado_en", 1).to_list(100)
    return {"ordenes": remesas, "remesas": remesas, "total": len(remesas)}

@router.get("/status/{remesa_id}")
async def get_remesa_status(remesa_id: str, current_user: User = Depends(get_current_user)):
    """Permite al frontend verificar el estado de pago de una orden."""
    remesa = await db.btc_remesas.find_one(
        {"remesa_id": remesa_id, "user_id": current_user.user_id},
        {"_id": 0, "remesa_id": 1, "estado": 1, "sats": 1, "usd_cliente": 1, "ves_recibe": 1, "creado_en": 1, "expira_en": 1}
    )
    if not remesa:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    # Convert datetime to string for JSON
    if remesa.get("creado_en"):
        remesa["creado_en"] = remesa["creado_en"].isoformat()
    if remesa.get("expira_en"):
        remesa["expira_en"] = remesa["expira_en"].isoformat()
    return remesa


@router.post("/cancelar/{remesa_id}")
async def cancelar_remesa(remesa_id: str, current_user: User = Depends(get_current_user)):
    """Permite al usuario cancelar un envío pendiente."""
    remesa = await db.btc_remesas.find_one(
        {"remesa_id": remesa_id, "user_id": current_user.user_id, "estado": "pendiente"}
    )
    if not remesa:
        raise HTTPException(status_code=404, detail="Orden no encontrada o no cancelable.")
    await db.btc_remesas.update_one(
        {"remesa_id": remesa_id},
        {"$set": {"estado": "cancelado", "cancelado_en": datetime.now(timezone.utc)}}
    )
    return {"ok": True, "msg": "Envío cancelado."}

@router.get("/wallet")
async def get_btc_wallet(current_user: User = Depends(get_current_user)):
    """Retorna el saldo de la billetera BTC-VES del usuario autenticado."""
    wallet = await db.btc_ves_wallets.find_one(
        {"user_id": current_user.user_id},
        {"_id": 0}
    )
    if not wallet:
        return {"saldo": 0.0, "moneda": "BTC-VES", "user_id": current_user.user_id}
    return {
        "saldo": float(wallet.get("saldo", 0)),
        "moneda": wallet.get("moneda", "BTC-VES"),
        "user_id": current_user.user_id,
        "actualizado_en": wallet.get("actualizado_en", None)
    }


@router.get("/historial")
async def get_historial_usuario(current_user: User = Depends(get_current_user)):
    """Retorna el historial de envíos BTC del usuario autenticado."""
    remesas = await db.btc_remesas.find(
        {"user_id": current_user.user_id},
        {"_id": 0, "remesa_id": 1, "estado": 1, "sats": 1, "usd_cliente": 1,
         "ves_recibe": 1, "tasa_ves": 1, "creado_en": 1, "pagado_en": 1,
         "beneficiario_data": 1}
    ).sort("creado_en", -1).to_list(50)
    for r in remesas:
        if r.get("creado_en"):
            r["creado_en"] = r["creado_en"].isoformat()
        if r.get("pagado_en"):
            r["pagado_en"] = r["pagado_en"].isoformat()
    return {"remesas": remesas, "total": len(remesas)}
