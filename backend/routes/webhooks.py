"""
routes/webhooks.py — El webhook entrante de WhatsApp, ya sin flujo detrás.

QUE HABIA
    Un número de WhatsApp autorizado cerraba órdenes sin pasar por el Panel:
    «listo» marcaba el retiro como completado, «cancelar» lo cancelaba y
    reembolsaba el saldo. Esa rama de reembolso acreditaba SIEMPRE `balance_ris`
    sin mirar la moneda de origen, así que un envío pagado en USDT o USDC volvía
    en RIS; y dejaba la orden en «cancelled», un estado que el Panel no produce.

    La Fase 1 cortó la entrada dejando el resto del código en su lugar, detrás
    de un `if`. Esto es la Fase 2: hoy las órdenes se procesan sólo desde el
    Panel, así que ese código se fue —unas 180 líneas—, junto con el emisor de
    salida, `whatsapp_service.py` y las dos rutas de retiros que `admin_routes.py`
    duplicaba.

POR QUE EL ENDPOINT SIGUE EXISTIENDO
    Porque el número puede seguir apuntado acá. Sin la ruta, cada mensaje daría
    404 y Twilio reintentaría; con ella, se valida la firma, queda constancia en
    el log de que alguien escribió, y se contesta 200 sin hacer nada.

    Sigue validando la firma a propósito, aunque no procese: un endpoint público
    que ni siquiera comprueba quién lo llama es una invitación, y el día que se
    conecte algo acá, la validación tiene que estar puesta de antes.

ESTE MODULO NO TOCA LA BASE DE DATOS
    Ni siquiera la importa. Es la propiedad más fuerte que puede tener un
    receptor desactivado, y hay un test que la exige.
"""
import logging
import os

from fastapi import APIRouter, Request, Response
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")

# No se lee de una variable de entorno a propósito: esto es un cierre de
# exposición, no una función con interruptor. Volver a abrirlo tiene que ser un
# cambio de código revisado, no una variable que alguien cambia de madrugada.
WHATSAPP_INBOUND_DISABLED = True


@router.post("/twilio/whatsapp")
async def twilio_whatsapp_webhook(request: Request):
    """Recibe, valida, registra y descarta. No procesa nada.

    Las órdenes se cierran únicamente desde el Panel.
    """
    try:
        form_data = await request.form()

        # Sin token no se puede comprobar quién llama, así que no se contesta
        # 200: se dice que el webhook no está configurado.
        if not TWILIO_AUTH_TOKEN:
            logger.error("TWILIO_AUTH_TOKEN not set - rejecting webhook")
            return Response(status_code=503, content="Webhook not configured")

        # La URL pública que Twilio llamó de verdad. Railway está detrás de un
        # proxy, así que `request.url` trae la interna y la firma no validaría.
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        public_url = f"{proto}://{host}{request.url.path}"
        if request.url.query:
            public_url += f"?{request.url.query}"

        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(public_url, dict(form_data), signature):
            logger.warning(f"Invalid Twilio signature for webhook (url={public_url})")
            return Response(status_code=403, content="Invalid signature")

        from_number = form_data.get("From", "")
        if not ADMIN_WHATSAPP_NUMBER or from_number != ADMIN_WHATSAPP_NUMBER:
            logger.warning(f"Webhook from unauthorized number: {from_number}")
            return Response(content="", media_type="text/xml")

        logger.warning(
            "WhatsApp entrante desactivado: mensaje descartado sin efecto "
            f"(from={from_number}, body={form_data.get('Body', '')!r}, "
            f"media={form_data.get('NumMedia', 0)})"
        )
        return Response(content="", media_type="text/xml")

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return Response(content="", media_type="text/xml")
