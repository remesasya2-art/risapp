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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# La red que hace que una respuesta con plata adentro no se caiga con un 500.
# Va ANTES de importar las rutas: el traductor a JSON tiene que conocer el tipo
# desde el primer pedido, no desde el primero que le toque un saldo.
from services.json_de_mongo import ensenarle_decimal128_a_fastapi

ensenarle_decimal128_a_fastapi()

# Import modular routers
from routes import api_router as modular_api_router  # noqa: E402

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
# El remitente y la llave de Resend se deciden en `services/correo.py`, que es
# la única puerta por la que sale un correo. Acá había un TERCER valor por
# omisión para el remitente (había uno en config.py y otro en
# email_notifications.py), y los tres eran distintos.

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
        # La mesa de ayuda por casos. La bandeja del asesor filtra por estado y
        # área, y el cliente pide los suyos: sin estos índices, cada apertura
        # del panel recorre la colección entera.
        await db.soporte_casos.create_index("caso_id", unique=True)
        await db.soporte_casos.create_index([("user_id", 1), ("actualizado_en", -1)])
        await db.soporte_casos.create_index([("estado", 1), ("area", 1)])
        await db.soporte_casos.create_index([("asignado_a", 1), ("estado", 1)])
        await db.soporte_mensajes.create_index([("caso_id", 1), ("creado_en", 1)])
        await db.soporte_pedidos.create_index([("area", 1), ("estado", 1)])
        await db.soporte_pedidos.create_index("caso_id")
        await db.quick_replies.create_index([("created_at", 1)])
        await db.blacklist.create_index([("type", 1), ("value", 1)])
        await db.blacklist.create_index("value")
        await db.verifications.create_index([("status", 1), ("created_at", -1)])
        await db.verifications.create_index("user_id")
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")
    try:
        # Los chats viejos pasan a ser casos, solos. Esto se corría a mano
        # (`python3 -m migrations.002_chats_a_casos`) y por eso nunca se corrió:
        # mientras tanto el frontend ya leía únicamente casos, así que el
        # historial de soporte de cada cliente estaba en la base pero no se veía
        # en ninguna pantalla.
        #
        # Va DESPUES de los índices a propósito: la migración escribe en
        # `soporte_casos` y `soporte_mensajes`, que tienen índices únicos, y
        # crearlos después de los datos falla si la migración dejó un repetido.
        #
        # Un problema acá NO tumba la aplicación. La migración no borra nada
        # —`support_chats` y `support_messages` quedan intactas—, así que lo
        # peor que pasa es que el historial siga sin verse y quede el error
        # escrito para mirarlo.
        import importlib
        # `import_module` y no `from migrations.002... import`: el módulo
        # empieza con un número, que no es un nombre válido en un import.
        _chats_a_casos = importlib.import_module("migrations.002_chats_a_casos")
        _movido = await _chats_a_casos.ejecutar_si_hace_falta()
        logger.info("Migracion chats->casos: %s", _movido)
    except Exception as e:
        logger.error(f"Migracion chats->casos: no se pudo completar: {e}")
    try:
        # Los casos asignados a alguien que no puede atenderlos: un cliente o un
        # empleado dado de baja. `transferir` los dejaba entrar y el caso salia
        # de la cola de todos sin que nada avisara. La puerta ya esta cerrada;
        # esto devuelve a la cola los que quedaron atascados antes.
        #
        # Se revisa en CADA arranque a proposito, y no una sola vez: busca una
        # condicion, no ejecuta un paso. Si un caso vuelve a atascarse por un
        # camino que no previmos, el proximo arranque lo suelta.
        import importlib
        _atascados = importlib.import_module("migrations.003_casos_atascados")
        _soltados = await _atascados.ejecutar_si_hace_falta()
        if _soltados.get("liberados"):
            logger.warning("Casos atascados devueltos a la cola: %s", _soltados)
        else:
            logger.info("Casos atascados: %s", _soltados)
    except Exception as e:
        logger.error(f"Casos atascados: no se pudo revisar: {e}")
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
        from config import FRONTEND_URL
        from services import correo
        if not correo.revisar():
            logger.error(
                "ALTA DE PERSONAL A MEDIAS: con el correo así, las cuentas se "
                "van a crear pero el enlace de activación NO va a salir, y el "
                "colaborador no va a poder entrar. El motivo está en la línea "
                "de arriba.")
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
        # El cofre de los documentos del KYC. Se revisa al arrancar para que una
        # llave equivocada se vea en el primer segundo y no dentro de tres meses,
        # cuando alguien necesite abrir un documento y no pueda.
        #
        # Un problema acá NO tumba la aplicación: las remesas siguen andando y
        # lo único que falla es el KYC, con un error claro. Ver services/cofre.py.
        from services import cofre
        await cofre.sellar_testigo(db)
        estado_cofre = await cofre.revisar(db)
        if not estado_cofre["ok"]:
            logger.error("COFRE: %s", estado_cofre["detalle"])
        else:
            logger.info("Cofre en modo «%s» (huella %s): %s",
                        estado_cofre["modo"], estado_cofre["huella"],
                        estado_cofre["detalle"])
    except Exception as e:
        logger.warning(f"Cofre: no se pudo revisar al arrancar: {e}")

    # La puerta del borde. Se dice en el arranque porque su estado por omisión
    # —apagada— es justamente el que deja el agujero abierto, y un agujero que
    # no se anuncia es un agujero que nadie cierra.
    try:
        from services import borde
        estado_borde = borde.revisar()
        if estado_borde["listo"]:
            logger.info("Borde: %s", estado_borde["detalle"])
        else:
            logger.warning("BORDE: %s", estado_borde["detalle"])
    except Exception as e:
        logger.warning(f"Borde: no se pudo revisar al arrancar: {e}")
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


# ============================================================================
# LA DOCUMENTACION AUTOMATICA NO SE PUBLICA
# ============================================================================
#
# FastAPI publica `/docs`, `/redoc` y `/openapi.json` sin pedir nada. Eso es el
# mapa completo de la API: las 337 rutas, con sus parámetros, sus tipos y sus
# nombres — incluidas las de administración, las del puente con adminbrl y las
# de mantenimiento. Ninguna deja de estar protegida por eso, pero saber que
# `/api/admin/fix-media-urls` existe y qué recibe es la mitad del trabajo de
# quien está buscando por dónde entrar, y no hay una sola razón para regalarlo.
#
# En desarrollo hace falta, así que se puede prender con una variable de
# entorno. El valor por defecto es apagado: lo que se olvida de configurar tiene
# que quedar del lado seguro.
_DOCS_ABIERTAS = os.getenv("EXPONER_DOCUMENTACION_API", "").strip().lower() in ("1", "true", "si", "yes")

app = FastAPI(
    title="RIS App API",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _DOCS_ABIERTAS else None,
    redoc_url="/redoc" if _DOCS_ABIERTAS else None,
    openapi_url="/openapi.json" if _DOCS_ABIERTAS else None,
)

# Rate limiter wiring (from routes.security_2fa)
from services import csp
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
    # La política de contenido, incluida `script-src`, sale de services/csp.py.
    # Arranca en modo REPORTE: el navegador no bloquea nada y avisa lo que
    # habría bloqueado, para poder completarla con tráfico real antes de que
    # corte un pago. `CSP_MODO=exigir` la pasa a bloquear.
    cabecera_csp = csp.cabecera()
    if cabecera_csp:
        nombre, valor = cabecera_csp
        response.headers[nombre] = valor
        # Le dice al navegador dónde mandar los avisos de `report-to`.
        response.headers["Reporting-Endpoints"] = f'csp="{csp.RUTA_DE_REPORTE}"'
    return response

# CORS configuration
raworigins = os.getenv("ALLOWED_ORIGINS", "https://risappbr.com,https://www.risappbr.com")
ALLOWED_ORIGINS = [o.strip() for o in raworigins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# LA PUERTA DEL BORDE VA ACA, Y EL ORDEN NO ES CASUAL.
#
# Queda por FUERA de CORS y del limitador de intentos —así un pedido que no
# vino por nuestro Cloudflare se corta antes de que nadie gaste trabajo en
# él— y por DENTRO del tope de cuerpo, para que un cuerpo de varios gigabytes
# lo siga cortando primero quien está para eso.
#
# Arranca en modo aviso: no bloquea nada hasta que se ponga LLAVE_DEL_BORDE y
# LLAVE_DEL_BORDE_MODO=exigir. Ver services/borde.py, que explica las tres
# formas en que esta puerta puede tirar abajo la aplicación entera.
from services.borde import PuertaDelBorde
app.add_middleware(PuertaDelBorde)

# EL TOPE DEL CUERPO VA REGISTRADO ULTIMO, Y ESO ES LO QUE LO PONE PRIMERO.
#
# Starlette envuelve al revés: `add_middleware` inserta al principio de la
# lista, así que el ULTIMO que se registra queda por fuera de todos y es el
# primero que ve el pedido. Registrarlo arriba de este archivo —que es lo que
# parece «primero»— lo dejaba pegado a la ruta, con CORS y el limitador de
# intentos haciendo su trabajo sobre un pedido de varios gigabytes antes de que
# nadie lo cortara.
#
# Ver services/limite_de_cuerpo.py.
from services.limite_de_cuerpo import LimiteDeCuerpo
app.add_middleware(LimiteDeCuerpo)
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

# Lo que cae acá es todo lo que NINGUNA ruta quiso. Ver services/sin_ruta.py:
# el aviso de cada pago de Mercado Pago estuvo meses cayendo justo acá, con un
# 405 suelto por toda señal.
from services import sin_ruta                                     # noqa: E402
from fastapi.responses import JSONResponse                        # noqa: E402

_SIN_RUTA = {"detail": "Not Found"}


def _no_existe(request, full_path: str):
    """El 404, y el grito si lo que rebotó era el aviso de un cobro."""
    sin_ruta.avisar_si_es_un_pago_perdido(
        request.method, request.url.path,
        request.query_params, request.headers.keys())
    return JSONResponse(_SIN_RUTA, status_code=404)


# Los métodos que NO son GET no tienen ninguna pantalla que servir, y por eso
# esta ruta se registra exista o no el build del frontend: quien manda datos a
# una dirección que no existe tiene que enterarse, no recibir una página.
#
# EFECTO LATERAL, A PROPOSITO: un POST a una dirección que sólo acepta GET pasa
# de contestar 405 a contestar 404. Se prefiere: el 405 le confirma a quien
# prueba puertas que esa dirección existe, y eso no se le debe a nadie.
@app.api_route("/{full_path:path}", methods=["POST", "PUT", "PATCH", "DELETE"],
               include_in_schema=False)
async def _sin_ruta_con_datos(request: Request, full_path: str):
    return _no_existe(request, full_path)


if FRONTEND_BUILD_DIR.exists():
    _assets_dir = FRONTEND_BUILD_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(request: Request, full_path: str):
        from fastapi.responses import FileResponse

        # Debajo de /api/ no hay pantalla que servir: lo que no es una ruta es
        # un error. Antes devolvía el index.html con un 200, y entonces un
        # integrador que le pegaba a una dirección inexistente lo veía como si
        # hubiera funcionado. Fuera de /api/ la página sigue saliendo, y tiene
        # que seguir: `/envios/ABC123` lo resuelve el navegador, no el servidor.
        if sin_ruta.es_de_la_api(full_path):
            return _no_existe(request, full_path)

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
