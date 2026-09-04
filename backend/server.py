"""
RIS App Backend - Clean Server
Main FastAPI application entry point.
All endpoints are now in modular routers under /routes/
"""
from fastapi import FastAPI, Request, Header
from contextlib import asynccontextmanager
from fastapi.security import HTTPBearer
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import Optional
from twilio.rest import Client as TwilioClient
from admin_routes import admin_router
import resend
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Import modular routers
from routes import api_router as modular_api_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_WHATSAPP_FROM = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
TWILIO_WHATSAPP_TO = os.getenv('TWILIO_WHATSAPP_TO')

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Resend Email Configuration
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'noreply@risappbr.com')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Lifespan context manager (replaces @app.on_event startup/shutdown)
@asynccontextmanager
async def lifespan(app):
    # Startup
    try:
        await db.users.create_index("email", unique=True, sparse=True)
        await db.users.create_index("cpf_number", sparse=True)
        await db.user_sessions.create_index("session_token", unique=True)
        # El índice sobre `expires_at` lo crea ensure_security_indexes(), CON
        # expireAfterSeconds. Crearlo acá sin TTL le ganaba de mano —esto corre
        # antes— y dejaba al de allá fallando con IndexOptionsConflict en cada
        # arranque. Resultado: las sesiones vencidas no se borraban nunca y
        # user_sessions crecía sin techo. El vencimiento en sí se comprueba al
        # leer (routes/dependencies.py), así que no era un problema de acceso.
        await db.transactions.create_index("user_id")
        await db.transactions.create_index("status")
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])

        # --- Índices adicionales (rendimiento al escalar) ---
        await db.transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.transactions.create_index([("created_at", -1)])
        await db.transactions.create_index("transaction_id", sparse=True)
        await db.support_requests.create_index([("status", 1), ("created_at", -1)])
        await db.support_requests.create_index("support_id", sparse=True)
        await db.support_messages.create_index([("user_id", 1), ("created_at", 1)])
        await db.support_messages.create_index([("user_id", 1), ("read", 1)])
        await db.support_chats.create_index("user_id")
        await db.support_chats.create_index([("last_message_at", -1)])
        await db.quick_replies.create_index([("created_at", 1)])
        await db.blacklist.create_index([("type", 1), ("value", 1)])
        await db.blacklist.create_index("value")
        await db.verifications.create_index([("status", 1), ("created_at", -1)])
        await db.verifications.create_index("user_id")
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")
    try:
        from routes.security_2fa import ensure_security_indexes
        await ensure_security_indexes()
    except Exception as e:
        logger.warning(f"Security indexes warning: {e}")
    try:
        # El índice único que impide acreditar dos veces el mismo pago. Existía
        # en accounting_engine.ensure_indexes(), pero eso sólo corre si un super
        # admin llama a mano a POST /admin/accounting/v2/bootstrap-indexes: en
        # el arranque no se creaba nunca. Sin él, dos avisos simultáneos del
        # mismo pago con tarjeta entran los dos y acreditan los dos.
        from services.pagos_una_sola_vez import asegurar_indice
        await asegurar_indice(db)
    except Exception as e:
        logger.error(f"Indice de pagos unicos: {e}")
    try:
        # Los índices que impiden tener dos veces la misma cuenta de banco. La
        # de la pasarela la crea el código solo, desde dos caminos que corren a
        # la vez cuando entra un pago.
        from services.bancos import asegurar_indices
        await asegurar_indices(db)
    except Exception as e:
        logger.error(f"Indices de cuentas bancarias: {e}")
    try:
        from services.auditoria import asegurar_indices as indices_auditoria
        await indices_auditoria(db)
    except Exception as e:
        logger.error(f"Indices del libro de auditoria: {e}")
    try:
        # Las invitaciones de primer acceso del personal. El índice único
        # sobre la huella del token es lo que impide que dos invitaciones
        # distintas terminen compartiendo llave.
        from services.invitaciones import asegurar_indices as indices_invitaciones
        await indices_invitaciones(db)
    except Exception as e:
        logger.error(f"Indices de invitaciones del personal: {e}")
    try:
        # Lo que el alta de personal necesita para funcionar de punta a punta.
        # Sin esto, el alta "funciona" —la cuenta queda creada— pero el correo
        # con la llave no sale, y quien la dio de alta se entera cuando el
        # colaborador avisa que nunca le llegó nada. Mejor gritarlo acá.
        from config import RESEND_API_KEY, FRONTEND_URL, FROM_EMAIL
        if not RESEND_API_KEY:
            logger.error(
                "ALTA DE PERSONAL A MEDIAS: falta RESEND_API_KEY. Las cuentas "
                "se van a crear, pero el correo con el enlace de activación NO "
                "va a salir y el colaborador no va a poder entrar.")
        if "example.com" in (FROM_EMAIL or ""):
            logger.error(
                "ALTA DE PERSONAL A MEDIAS: FROM_EMAIL sigue en el valor de "
                "ejemplo (%s). Los correos de activación se van a rechazar.",
                FROM_EMAIL)
        if not (FRONTEND_URL or "").startswith("https://"):
            logger.error(
                "FRONTEND_URL = %r. Con esto se arma el enlace de activación "
                "del personal; si no es la URL pública real, el correo sale "
                "con un link roto.", FRONTEND_URL)
        else:
            logger.info("Alta de personal: los enlaces se arman sobre %s",
                        FRONTEND_URL)
    except Exception as e:
        logger.error(f"No se pudo revisar la configuracion de correo: {e}")
    try:
        # Estructura del módulo de envíos. Crea índices, nunca datos: los
        # transportistas, agencias y tarifas se cargan desde el panel.
        from services.envios_indices import ensure_envios_indexes
        await ensure_envios_indexes()
    except Exception as e:
        logger.warning(f"Envios indexes warning: {e}")
    try:
        from services.bcv_scraper import start_scheduler
        start_scheduler(db, interval_hours=1)
    except Exception as e:
        logger.warning(f"BCV scheduler failed to start: {e}")
    yield
    # Shutdown
    try:
        from services.bcv_scraper import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    client.close()


# Create FastAPI app
app = FastAPI(title="RIS App API", version="2.1.0", lifespan=lifespan)

# Rate limiter wiring (from routes.security_2fa)
from routes.security_2fa import limiter as security_limiter
app.state.limiter = security_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security HTTP headers middleware
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# CORS configuration
raworigins = os.getenv("ALLOWED_ORIGINS", "https://risappbr.com,https://www.risappbr.com")
ALLOWED_ORIGINS = [o.strip() for o in raworigins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# ============================================================================
# STATIC FILES - For serving proof images
# ============================================================================
STATIC_DIR = ROOT_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "comprobantes").mkdir(exist_ok=True)
app.mount("/api/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

# Include modular routers (from routes/)
app.include_router(modular_api_router)

# Include admin router (separate file for backward compatibility)
app.include_router(admin_router)

# ==============================================================================
# FRONTEND - Serve React build (fixes {"detail":"Not Found"} on root path)
# ==============================================================================
FRONTEND_BUILD_DIR = ROOT_DIR.parent / "frontend" / "dist"

if FRONTEND_BUILD_DIR.exists():
    _assets_dir = FRONTEND_BUILD_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        from fastapi.responses import FileResponse
        # Servir archivos reales del build (sw.js, íconos, manifest, etc.) si existen;
        # si no, caer al index.html para las rutas del SPA.
        if full_path:
            candidate = (FRONTEND_BUILD_DIR / full_path).resolve()
            try:
                candidate.relative_to(FRONTEND_BUILD_DIR.resolve())
            except ValueError:
                candidate = None
            if candidate and candidate.is_file():
                return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_BUILD_DIR / "index.html"))

    
# Last update: 2026-03-28 - Complete refactor to modular routers
