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
from services.aviso_de_tasa import avisar_si_hace_falta
from routes.dependencies import get_current_user, sin_transacciones_personales

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/btc", tags=["btc-lightning"])

BLINK_API_KEY = os.getenv("BLINK_API_KEY", "")
BLINK_WEBHOOK_SECRET = os.getenv("BLINK_WEBHOOK_SECRET" , "" )
BLINK_WALLET_ID = os.getenv("BLINK_WALLET_ID", "81812448-e78e-47fb-b6cd-d827fc952536")
BLINK_GRAPHQL_URL = "https://api.blink.sv/graphql"

# El caché arranca VACIO. Antes arrancaba en 58 500 USD escritos a mano: si el
# primer pedido al proveedor de precio fallaba, esa cifra se usaba para cobrar
# una remesa real. Con el bitcoin cerca de 79 000, el cliente habría pagado un
# 36 % de más en bitcoin sin que nada fallara ni nadie se enterara.
_btc_price_cache = {"price": None, "updated_at": None}

# Cuánto se acepta un precio guardado CUANDO EL PROVEEDOR NO CONTESTA.
#
#   No es un intervalo de actualización: no hay ninguno. Cada consulta va en
#   vivo a blockchain.info y devuelve lo que contesta, y la pantalla del envío
#   consulta cada diez segundos. Este número sólo entra en juego si el
#   proveedor se cae.
#
#   Treinta segundos, por decisión del operador y por lo que es el bitcoin: es
#   una moneda que se mueve, y cobrar con el precio de hace un minuto es cobrar
#   mal, para un lado o para el otro.
#
#   Lo que cuesta: con la pantalla consultando cada diez segundos, esto tolera
#   unos tres intentos fallidos seguidos. Un hipo del proveedor más largo que
#   eso deja de cotizar. Es una falla suave y se cura sola —la pantalla dice
#   que no hay cotización y sigue reintentando— pero va a pasar más seguido que
#   con diez minutos.
#
#   Bajarlo de ~15 segundos no tendría sentido: sería menos que el intervalo
#   con que se consulta, o sea no tolerar nada.
EDAD_MAXIMA_DEL_PRECIO = timedelta(seconds=30)

# Cuánto vale la tasa USDI → VES desde que se guardó.
#
#   El precio de Bitcoin se pide en vivo en cada consulta, así que no envejece.
#   La tasa NO: se escribe a mano desde el panel (`btc_admin.py`), y el
#   raspador del BCV escribe otra colección —`bcv_rates`— que nadie conecta con
#   esta clave. Si nadie la toca, el valor de hace un mes sigue ahí y el
#   sistema sigue prometiendo bolívares con él.
#
#   Un día es una elección conservadora para una tasa que se mueve todos los
#   días. Es UN número y está acá para cambiarlo: si el operador la fija una
#   vez por semana, subilo; si la mueve dos veces por día, bajalo.
EDAD_MAXIMA_DE_LA_TASA = timedelta(hours=24)

# Cuánto dura el cobro, desde que se genera hasta que vence.
#
#   Es LA ventana de exposición a la volatilidad del bitcoin: en ese rato el
#   precio queda clavado —los sats que paga el cliente y los bolívares que
#   recibe el beneficiario ya están fijos— y el movimiento lo absorbe el
#   operador, con el colchón del margen y la comisión (~3 %).
#
#   Diez minutos, por decisión del operador: menos ventana y más apuro en
#   pagar. Antes eran treinta.
#
#   Escrito UNA vez. Estaba en cuatro lugares —dos en el servidor y dos en la
#   pantalla— y cambiarlo era acordarse de los cuatro.
DURACION_DEL_COBRO = timedelta(minutes=10)

MARGEN = 0.99
COMISION = 1.02
LIMITE_DIARIO_USD = 500.0
LIMITE_MAXIMO_USD = 200.0
_rate_limit_invoices = {}  # {user_id: [timestamps]}


async def _get_margen_dinamico():
    """Lee margen desde DB con fallback al default."""
    config = await db.config.find_one({"clave": "btc_margen"})
    try:
        return float(config["valor"]) if config and config.get("valor") is not None else MARGEN
    except (ValueError, TypeError):
        return MARGEN


async def _get_comision_dinamica():
    """Lee comisión desde DB con fallback al default."""
    config = await db.config.find_one({"clave": "btc_comision"})
    try:
        return float(config["valor"]) if config and config.get("valor") is not None else COMISION
    except (ValueError, TypeError):
        return COMISION


async def _get_tasa_ves():
    """La tasa USDI → VES, o None si no está configurada.

    Antes devolvía 680.0 cuando faltaba. Eso no dejaba el sistema roto: lo
    dejaba emitiendo remesas a una tasa que nadie fijó. Si la real fuera 270,
    a cada beneficiario se le prometían dos veces y media los bolívares que
    corresponden, y la diferencia la pone el operador.

    Devolver None obliga a decidir en cada lugar que la use. Los dos lugares
    están decididos: la pantalla no convierte, y el cobro no se emite.
    """
    config = await db.config.find_one({"clave": "tasa_usd_ves_btc"})
    if not config or not config.get("valor"):
        return None
    try:
        tasa = float(config["valor"])
    except (TypeError, ValueError):
        logger.error("tasa_usd_ves_btc guardada con un valor que no es un número")
        return None
    if tasa <= 0:
        return None

    cuando = config.get("updated_at")
    if cuando is None:
        # Concesión, y con fecha de vencimiento: las tasas guardadas antes de
        # que `_write_config_value` sellara la hora no la tienen. Cortar acá
        # dejaría los envíos parados en el momento de desplegar esto, por un
        # dato viejo y no por una tasa mala. Se acepta una vez y se grita: con
        # que el operador vuelva a guardar la tasa desde el panel, queda
        # sellada y este camino no se usa nunca más.
        logger.error("La tasa USDI→VES no tiene fecha de actualización: "
                     "volvé a guardarla desde el panel para poder controlar "
                     "su antigüedad.")
        return tasa

    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    edad = datetime.now(timezone.utc) - cuando
    if edad > EDAD_MAXIMA_DE_LA_TASA:
        logger.error(f"La tasa USDI→VES tiene {edad.days} día(s) y "
                     f"{edad.seconds // 3600} hora(s): no se cotiza con ella.")
        # El corte ya está decidido arriba: se devuelve None pase lo que pase
        # con el aviso. Avisar es lo que evita que el operador se entere por un
        # cliente que no pudo enviar, y el propio servicio se ocupa de que sea
        # UN aviso por vencimiento y no uno por consulta.
        await avisar_si_hace_falta(db, cuando, edad)
        return None
    return tasa


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
        # Se acepta el último precio conocido sólo si es reciente. Si no hay
        # ninguno, o el que hay ya envejeció, se devuelve None: es preferible
        # no poder cotizar a cotizar con un número de hace horas.
        guardado = _btc_price_cache.get("price")
        cuando = _btc_price_cache.get("updated_at")
        if guardado is None or cuando is None:
            return None
        if datetime.now(timezone.utc) - cuando > EDAD_MAXIMA_DEL_PRECIO:
            logger.error("El precio BTC guardado quedó viejo y el proveedor no contesta")
            return None
        return guardado


async def _cotizacion_o_error():
    """Las dos cifras con las que se cobra, o un error que se entiende.

    Existe para que ningún camino que mueve dinero pueda seguir sin ellas por
    olvido. Devuelve una tupla; si falta cualquiera de las dos, corta.
    """
    precio = await _get_btc_price()
    tasa = await _get_tasa_ves()
    if precio is None or tasa is None:
        falta = "el precio de Bitcoin" if precio is None else "la tasa del día"
        if precio is None and tasa is None:
            falta = "el precio de Bitcoin ni la tasa del día"
        logger.error(f"No se emite el cobro: no se pudo obtener {falta}")
        raise HTTPException(
            status_code=503,
            detail=("En este momento no podemos calcular la cotización. No "
                    "emitimos el cobro con una tasa estimada: el monto que "
                    "recibe el beneficiario tiene que ser exacto. Probá de "
                    "nuevo en unos minutos."),
        )
    return precio, tasa


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
    # Puede devolver nulos, y es a propósito. La pantalla sabe qué hacer con
    # eso: no convierte, no promete y no deja avanzar. Un número inventado acá
    # se vería bien y sería mentira.
    # La fecha de la tasa viaja para que el panel pueda mostrarla. Un control
    # que corta sin decir desde cuándo obliga a adivinar qué pasó.
    doc = await db.config.find_one({"clave": "tasa_usd_ves_btc"})
    return {
        "precio_btc": precio,
        "tasa_btc_ves": tasa_ves,
        "disponible": precio is not None and tasa_ves is not None,
        "updated_at": _btc_price_cache.get("updated_at"),
        "tasa_actualizada_en": (doc or {}).get("updated_at"),
    }


def _blink_rechazo_el_vencimiento(respuesta):
    """¿El proveedor rechazó la petición por no conocer `expiresIn`?

    Se mira sólo el error de GraphQL de nivel superior —el que se devuelve
    cuando la consulta no valida contra el esquema— y no los errores de
    negocio, que vienen adentro de `lnInvoiceCreate.errors`. Confundirlos haría
    reintentar un cobro que el proveedor rechazó por un motivo real, como un
    monto fuera de rango.
    """
    for e in (respuesta or {}).get("errors") or []:
        mensaje = str(e.get("message", "")).lower()
        if "expiresin" in mensaje:
            return True
    return False


@router.post("/generar-invoice", dependencies=[Depends(sin_transacciones_personales)])
async def generar_invoice(body: GenerarInvoiceRequest, current_user: User = Depends(get_current_user)):
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Debes completar la verificacion KYC para realizar envios con BTC Lightning.")
    if body.usd_cliente <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0.")
    if body.usd_cliente > LIMITE_MAXIMO_USD:
        raise HTTPException(status_code=400, detail="El monto maximo por operacion es $200 USD.")
    # Rate limiting: max 5 invoices por usuario por minuto
    now = time.time()
    _user_reqs = _rate_limit_invoices.get(current_user.user_id, [])
    _user_reqs = [t for t in _user_reqs if now - t < 60]
    if len(_user_reqs) >= 5:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta de nuevo en 1 minuto.")
    _user_reqs.append(now)
    _rate_limit_invoices[current_user.user_id] = _user_reqs
        
    enviado_hoy = await _get_total_enviado_hoy(current_user.user_id)
    if enviado_hoy + body.usd_cliente > LIMITE_DIARIO_USD:
        disponible = max(0.0, LIMITE_DIARIO_USD - enviado_hoy)
        raise HTTPException(status_code=429, detail=f"Limite diario alcanzado. Disponible: ${disponible:.2f} USD.")
        
    beneficiario = await db.beneficiaries.find_one({"beneficiary_id": body.beneficiario_id, "user_id": current_user.user_id})
    if not beneficiario:
        raise HTTPException(status_code=404, detail="Beneficiario no encontrado.")
        
    precio_btc, tasa_ves = await _cotizacion_o_error()
    margen_dinamico = await _get_margen_dinamico()
    comision_dinamica = await _get_comision_dinamica()
    precio_con_margen = precio_btc * margen_dinamico
    btc_pagar = (body.usd_cliente * comision_dinamica) / precio_con_margen
    
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
            
        # EL INVOICE VENCE CUANDO VENCE NUESTRA VENTANA, no después.
        #
        #   Hasta acá el invoice se pedía sin vencimiento y quedaba con el que
        #   pone el proveedor por omisión, que es mucho más largo. O sea que la
        #   ventana de diez minutos era sólo del lado nuestro: un cliente podía
        #   pagar a los cuarenta y la red aceptaba el pago igual.
        #
        #   Dos formas de terminar mal, y las dos con plata de por medio:
        #   procesar el envío a un precio de hace cuarenta minutos, o —si el
        #   cliente había cancelado— cobrarle sin que el envío exista.
        #
        #   Acortar la ventana sin esto habría hecho las dos más probables.
        entrada = {"amount": sats, "memo": memo, "walletId": BLINK_WALLET_ID}
        minutos = max(1, int(DURACION_DEL_COBRO.total_seconds() // 60))

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                BLINK_GRAPHQL_URL, headers=headers,
                json={"query": mutation,
                      "variables": {"input": {**entrada, "expiresIn": minutos}}})
            result = resp.json()
            logger.debug(f"Blink lnInvoiceCreate status: {resp.status_code}")

            # Si el proveedor no conoce ese campo, se reintenta sin él en vez
            # de dejar al cliente sin poder pagar. Adivinar el nombre de un
            # campo y equivocarse no puede costar que no se emita ningún
            # cobro; queda registrado para que se note y se corrija.
            if _blink_rechazo_el_vencimiento(result):
                logger.error(
                    "El proveedor no aceptó `expiresIn`: el invoice queda con "
                    "su vencimiento por omisión, más largo que nuestra "
                    "ventana. Revisar el nombre del campo en su API.")
                resp = await client.post(
                    BLINK_GRAPHQL_URL, headers=headers,
                    json={"query": mutation, "variables": {"input": entrada}})
                result = resp.json()
            
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
        "expira_en": datetime.now(timezone.utc) + DURACION_DEL_COBRO
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
        # `expira_en_segundos` y no `expira_en`.
        #
        #   Acá se devolvían segundos y en `/mi-remesa-activa` una fecha ISO,
        #   las dos con el MISMO nombre. La pantalla lo resolvía sin querer:
        #   hacía `new Date(600)`, le daba 1970, lo descartaba por estar en el
        #   pasado y caía en un 1800 escrito a mano que resultaba ser el valor
        #   correcto. Funcionaba de casualidad, y dejó de funcionar en cuanto
        #   la duración cambió.
        "expira_en_segundos": int(DURACION_DEL_COBRO.total_seconds()),
        "expira_en": (datetime.now(timezone.utc) + DURACION_DEL_COBRO).isoformat(),
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
    # Se busca sin filtrar por estado a propósito. Filtrar por «pendiente»
    # hacía que un pago de una orden cancelada no encontrara nada y el webhook
    # contestara «ya procesada»: el cliente pagaba y no quedaba rastro de que
    # su plata había llegado.
    remesa = await db.btc_remesas.find_one(
        {"$or": [{"payment_hash": payment_hash}, {"remesa_id": payment_hash}]})
    if not remesa:
        logger.error(f"Pago recibido sin orden que lo explique: {payment_hash}")
        return {"ok": True, "msg": "Orden no encontrada"}
    if remesa.get("estado") == "pagado":
        return {"ok": True, "msg": "Ya procesada"}

    # UN PAGO QUE LLEGA TARDE NO SE ACREDITA SOLO.
    #
    #   El precio quedó fijo al generar el cobro. Acreditarlo después de que
    #   venció es enviar bolívares calculados con un bitcoin de otro momento, y
    #   la diferencia la pone alguien sin haberlo decidido.
    #
    #   Tampoco se ignora: la plata llegó. Queda marcado para que una persona
    #   lo mire, que es la única forma de resolverlo bien —devolver o completar
    #   a la cotización de hoy— y es una decisión de negocio, no de código.
    vencida = remesa.get("expira_en") and remesa["expira_en"].replace(
        tzinfo=remesa["expira_en"].tzinfo or timezone.utc) < datetime.now(timezone.utc)
    if vencida or remesa.get("estado") == "cancelado":
        motivo = "vencida" if vencida else "cancelada"
        logger.error(f"Pago de una orden {motivo}: {remesa['remesa_id']}. "
                     "Queda para revisión manual.")
        await db.btc_remesas.update_one(
            {"remesa_id": remesa["remesa_id"]},
            {"$set": {"estado": "revision_manual",
                      "motivo_revision": f"pago recibido con la orden {motivo}",
                      "pagado_en": datetime.now(timezone.utc)}})
        try:
            from services.notifications import create_notification
            async for admin in db.users.find({"role": "super_admin"}):
                await create_notification(
                    user_id=admin["user_id"],
                    title="Un pago con Bitcoin llegó tarde",
                    message=(f"Llegó el pago de una orden {motivo}. No se "
                             "acreditó solo, porque el precio con el que se "
                             "calculó ya no es el de ahora. Hay que revisarla "
                             "en el panel."),
                    notification_type="warning",
                    data={"remesa_id": remesa["remesa_id"], "motivo": motivo})
        except Exception as e:
            logger.error(f"No se pudo avisar del pago tardío: {type(e).__name__}")
        return {"ok": True, "msg": "Orden vencida: queda para revisión"}

    if remesa.get("estado") != "pendiente":
        return {"ok": True, "msg": "Orden en un estado que no admite el pago"}

    ves_recibe = remesa["ves_recibe"]
    user_id = remesa["user_id"]
    await db.btc_ves_wallets.update_one({"user_id": user_id}, {"$inc": {"saldo": ves_recibe}, "$set": {"moneda": "BTC-VES", "user_id": user_id}, "$setOnInsert": {"creado_en": datetime.now(timezone.utc)}}, upsert=True)
    await db.btc_remesas.update_one({"remesa_id": remesa["remesa_id"]}, {"$set": {"estado": "pagado", "pagado_en": datetime.now(timezone.utc)}})
    # Registrar transaccion en historial del usuario con estado pendiente
    try:
        beneficiario_data_hist = remesa.get("beneficiario_data", {})
        tx_hist_id = f"tx_{str(uuid.uuid4())[:12]}"
        await db.transactions.insert_one({
            "tx_id": tx_hist_id,
            "user_id": user_id,
            "tipo": "envio",
            "subtipo": "btc_lightning",
            "estado": "procesando",
            "amount": -remesa.get("usd_cliente", 0),
            "amount_ves": remesa.get("ves_recibe", 0),
            "monto_btc": remesa.get("btc_pagar", 0),
            "usd_cliente": remesa.get("usd_cliente", 0),
            "beneficiario": beneficiario_data_hist.get("full_name", "N/A"),
            "beneficiario_data": beneficiario_data_hist,
            "banco": beneficiario_data_hist.get("bank_code", ""),
            "metodo": beneficiario_data_hist.get("payment_type", "pago_movil"),
            "remesa_id": remesa.get("remesa_id"),
            "created_at": datetime.now(timezone.utc),
            "display_id": remesa.get("remesa_id", "")[:8].upper(),
            "moneda": "BTC-VES",
            "description": f"Procesando envio de ${remesa.get('usd_cliente', 0):,.2f} USD ({remesa.get('ves_recibe', 0):,.2f} Bs)",
        })
        logger.info(f"Transaccion historial creada para remesa {remesa.get('remesa_id')}")
    except Exception as e_hist:
        logger.warning(f"Error al registrar transaccion en historial: {e_hist}")
    try:
        from services.notifications import create_notification
        await create_notification(user_id=user_id, title="Pago BTC recibido", message=f"Recibimos tu pago. Tu envío de {ves_recibe:,.2f} BTC-VES sera procesado en maximo 15 minutos.", notification_type="btc_payment")
    except Exception as e:
        logger.warning(f"Error notificacion usuario: {e}")
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
    # Transición de estado atómica: solo una petición puede pasar de "pagado" a "enviado"
    claimed = await db.btc_remesas.find_one_and_update(
        {"remesa_id": body.remesa_id, "estado": "pagado"},
        {"$set": {"estado": "enviado", "enviado_en": datetime.now(timezone.utc), "operador_id": current_user.user_id}}
    )
    if not claimed:
        raise HTTPException(status_code=400, detail="La orden ya fue procesada o no está en estado pagado.")
    # Débito atómico del monedero BTC-VES con guardia
    wdec = await db.btc_ves_wallets.find_one_and_update(
        {"user_id": remesa["user_id"], "saldo": {"$gte": remesa["ves_recibe"]}},
        {"$inc": {"saldo": -remesa["ves_recibe"]}}
    )
    if not wdec:
        # No había saldo suficiente: revertimos el estado para no dejar la orden "enviada" sin debitar
        await db.btc_remesas.update_one({"remesa_id": body.remesa_id}, {"$set": {"estado": "pagado"}})
        raise HTTPException(status_code=400, detail="Saldo BTC-VES insuficiente.")
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

@router.get("/mi-remesa-activa")
async def mi_remesa_activa(current_user: User = Depends(get_current_user)):
    """Devuelve la remesa BTC más reciente y relevante del usuario (de las últimas
    48h, no cancelada), para que al volver a la app vea su estado: el invoice si
    sigue vigente, o la pantalla de éxito si ya pagó. Evita que pierda el hilo
    tras salir a pagar en su billetera."""
    from datetime import timedelta
    limite = datetime.now(timezone.utc) - timedelta(hours=48)
    remesa = await db.btc_remesas.find_one(
        {
            "user_id": current_user.user_id,
            "estado": {"$in": ["pendiente", "pagado", "enviado", "completado"]},
            "creado_en": {"$gte": limite},
        },
        {
            "_id": 0, "remesa_id": 1, "estado": 1, "sats": 1, "usd_cliente": 1,
            "ves_recibe": 1, "btc_pagar": 1, "payment_request": 1,
            "beneficiario_data": 1, "creado_en": 1, "expira_en": 1,
        },
        sort=[("creado_en", -1)],
    )
    if not remesa:
        return {"activa": False}
    if remesa.get("creado_en"):
        remesa["creado_en"] = remesa["creado_en"].isoformat()
    if remesa.get("expira_en"):
        remesa["expira_en"] = remesa["expira_en"].isoformat()
    return {"activa": True, "remesa": remesa}


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
    ).sort("creado_en", -1).to_list(100)
    # Convertir fechas a texto ISO para que el JSON no falle
    for r in remesas:
        if r.get("creado_en"):
            r["creado_en"] = r["creado_en"].isoformat()
        if r.get("pagado_en"):
            r["pagado_en"] = r["pagado_en"].isoformat()
    return {"remesas": remesas, "total": len(remesas)}
