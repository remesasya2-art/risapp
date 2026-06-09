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
                    await db.user_sessions.create_index("expires_at")
                    await db.transactions.create_index("user_id")
                    await db.transactions.create_index("status")
                    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
                    logger.info("Database indexes created successfully")
        except Exception as e:
                    logger.warning(f"Index creation warning: {e}")
                try:
                            from routes.security_2fa import ensure_security_indexes
                            await ensure_security_indexes()
                except Exception as e:
        logger.warning(f"Security indexes warning: {e}")
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
        return FileResponse(str(FRONTEND_BUILD_DIR / "index.html"))

    
# Last update: 2026-03-28 - Complete refactor to modular routers
