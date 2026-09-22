"""
RIS App Backend - Clean Server
Main FastAPI application entry point.
All endpoints are now in modular routers under /routes/
"""
from fastapi import FastAPI, Request, Header
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
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

# Cada línea del registro sale con el rastro del pedido que la produjo. Sin
# esto, «me dio error a las tres» no se puede buscar. Ver services/rastro.py.
from services import rastro                                           # noqa: E402
rastro.configurar_el_registro()
# El contador de uso. Se importa ACA arriba porque el middleware se registra
# a mitad del archivo, antes de los otros imports de servicios: importarlo
# abajo dejaba `uso.Contador` sin definir y el servidor no arrancaba.
from services import uso                                              # noqa: E402
from services import piso_de_peticiones                               # noqa: E402
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
        # ÚNICO: un CPF, una cuenta. El motivo y la trampa de reemplazar un
        # índice que ya existe con otras opciones están en el módulo.
        from services import cpf_de_la_cuenta
        await cpf_de_la_cuenta.asegurar_el_indice(db)
        # La reserva del CPF: tomado desde que se escribe, no quince minutos
        # después. La caducidad suelta sola las reservas sin confirmar, y la
        # siembra le da su reserva a cada cuenta que ya existe —y deja escrito
        # en el registro cuáles son los CPF repetidos, con su `user_id`, que
        # son los que impiden crear el índice único de arriba.
        await cpf_de_la_cuenta.asegurar_la_caducidad(db)
        await cpf_de_la_cuenta.sembrar(db)
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
        # El registro de errores del panel: se borra solo a los 30 días.
        await errores.preparar_indices(db)
        # El contador de uso: una fila por día y ruta, 90 días.
        await uso.preparar_indices(db)
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

    # El núcleo de cuentas. Se anuncia porque su estado de fábrica es
    # «apagado» y conviene que el registro lo diga: si un día aparece
    # «laboratorio» sin que nadie lo haya prendido, hay que mirar.
    try:
        from nucleo import base as nucleo_base, modo as nucleo_modo
        modo_nucleo = await nucleo_modo.leer(db)
        logger.info("Núcleo de cuentas: modo «%s», base %s",
                    nucleo_modo.NOMBRES[modo_nucleo],
                    "configurada" if nucleo_base.url_configurada() else "sin configurar")
    except Exception as e:
        logger.warning(f"Núcleo: no se pudo revisar al arrancar: {e}")
    try:
        from services.bcv_scraper import start_scheduler
        start_scheduler(db, interval_hours=1)
    except Exception as e:
        logger.warning(f"BCV scheduler failed to start: {e}")
    # El contador de uso vuelca a la base cada 30 segundos, en una tarea de
    # fondo. Si no arranca, la aplicación sigue: es estadística, no operación.
    try:
        uso.arrancar(db)
    except Exception as e:
        logger.warning(f"Uso: no se pudo arrancar el volcado: {e}")
    # EL BARRIDO DE COBROS VENCIDOS. Sin esto, las órdenes que nadie paga se
    # quedan en «esperando pago» para siempre y el bono descontado no vuelve.
    # El por qué completo está en `services/pago_al_final.py`.
    #
    # Va como WARNING y no como ERROR si no arranca, igual que los otros dos:
    # la aplicación funciona sin barrido —lo hizo hasta ahora—, sólo que deja
    # basura. Tirar el arranque entero por esto sería peor.
    try:
        from services import pago_al_final as _paf
        _paf.arrancar(db)
    except Exception as e:
        logger.warning(f"Pago al final: no se pudo arrancar el barrido: {e}")
    # EL TRABAJADOR DEL NUCLEO. Con el núcleo apagado (lo de fábrica) mira
    # el interruptor cada medio minuto y no toca nada; prendido, despacha
    # los eventos y corre la cola. Ver nucleo/trabajador.py.
    try:
        from nucleo import trabajador as _nucleo_trabajador
        _nucleo_trabajador.arrancar(db)
    except Exception as e:
        logger.warning(f"Núcleo: no se pudo arrancar el trabajador: {e}")
    yield
    # Shutdown
    # Lo que el contador tiene en memoria, a la base antes de cerrarla. No
    # levanta: ver services/uso.py.
    await uso.parar(db)
    try:
        from services import pago_al_final as _paf
        await _paf.parar()
    except Exception:
        pass
    try:
        from nucleo import trabajador as _nucleo_trabajador
        await _nucleo_trabajador.parar()
    except Exception:
        pass
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
# nombres — incluidas las de administración, las del centro de gestión y las
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
# El manejador del 429 se registra más abajo, junto a los otros dos, y no
# acá: envuelve al de `slowapi` para anotar el rechazo en «Errores» antes de
# devolver la misma respuesta de siempre. Registrarlo también acá dejaría una
# línea muerta —la de abajo la pisa— y la próxima persona no sabría cuál manda.
app.add_middleware(SlowAPIMiddleware)

# Security HTTP headers middleware
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    # OJO: ESTA LINEA NO ES LO QUE RECIBE EL VISITANTE. CLOUDFLARE LA PISA.
    #
    # Cloudflare tiene su propia función de HSTS y gana. Medido sobre la
    # respuesta real de https://risappbr.com el 18/09/2026, lo que llega es:
    #
    #     strict-transport-security: max-age=15552000
    #
    # Ciento ochenta días, SIN `includeSubDomains`. O sea que los subdominios
    # no están cubiertos, por más que acá diga que sí.
    #
    # La línea se deja igual, y a propósito: es lo que corresponde mandar
    # desde el origen, y es lo que valdría si un día se sirviera sin
    # Cloudflare en el medio. Lo que NO se puede hacer es leerla y creerle.
    # Para cambiar lo que llega de verdad hay que tocar el panel de
    # Cloudflare (SSL/TLS → Edge Certificates → HSTS), y antes de prender
    # `includeSubDomains` hay que saber qué subdominios existen: obliga a
    # HTTPS en todos, y se rompe para quien ya visitó durante lo que dure el
    # `max-age`. Ver la sección 8.2 del dossier.
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # La política de contenido, incluida `script-src`, sale de services/csp.py.
    # Arranca en modo REPORTE: el navegador no bloquea nada y avisa lo que
    # habría bloqueado, para poder completarla con tráfico real antes de que
    # corte un pago. `CSP_MODO=exigir` la pasa a bloquear.
    # UN NONCE NUEVO POR RESPUESTA.
    #
    # Es lo que deja que Cloudflare firme el script en línea que inyecta para
    # su detección de bots: lee esta cabecera y le copia el nonce. Sin esto, el
    # día que la política pase a bloquear, la aplicación frenaría ese script.
    # El motivo largo está en `services/csp.py`.
    #
    # Se genera ACA y no adentro de `csp.cabecera()` sin argumento, para que
    # quede a la vista que hay uno por respuesta y no uno por proceso. Un nonce
    # que se repite no protege nada.
    cabecera_csp = csp.cabecera(csp.nuevo_nonce())
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

# El contador de uso (services/uso.py). Cuenta DESPUES de que la ruta atendió,
# así que su lugar en la cadena no cambia lo que cuenta; va acá, pegado a la
# aplicación, para no correr sobre lo que el tope de cuerpo o la puerta del
# borde ya rechazaron: esos ni llegan a tener ruta.
app.add_middleware(uso.Contador)

# El piso de pedidos por IP para toda la API (services/piso_de_peticiones.py).
# Por fuera del contador de uso: un pedido cortado por el piso no es uso de
# nadie. Arranca en modo reporte: no corta hasta que Configuración lo diga.
app.add_middleware(piso_de_peticiones.Piso)

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
from services import errores, rechazos
from services.ip_cliente import ip_del_cliente
from services.limite_de_cuerpo import LimiteDeCuerpo
app.add_middleware(LimiteDeCuerpo)

# Y EL RASTRO VA DESPUES DE TODOS, que es lo que lo deja por fuera de todos.
#
# Tiene que ver el pedido antes que nadie para que hasta el que rechaza el tope
# de cuerpo, o la puerta del borde, salga con su rastro. Justamente los
# rechazados son los que después hay que poder encontrar en el registro.
app.add_middleware(rastro.Rastro)


@app.exception_handler(Exception)
async def _error_no_previsto(request, exc):
    """Lo que ve el usuario cuando algo se rompe de verdad.

    Se registra el error ENTERO —con su traza— y se le devuelve al usuario el
    rastro y nada más. El texto de una excepción nombra tablas, rutas y a veces
    cadenas de conexión: no es para el cliente. El rastro sí, porque es lo
    único que le sirve a soporte para encontrar esta línea.
    """
    logger.exception("error no previsto en %s %s", request.method,
                     request.url.path)
    # Y AL REGISTRO QUE EL PANEL MUESTRA. Antes esto iba al log de Railway y
    # ahí se quedaba: el super administrador no sabía que algo fallaba hasta
    # que un cliente escribía. Ver services/errores.py. Nunca levanta.
    import traceback as _tb
    await errores.anotar(
        db, rastro=rastro.actual(), metodo=request.method,
        ruta=_plantilla_de(request), status=500,
        tipo=type(exc).__name__, mensaje=str(exc),
        traza="".join(_tb.format_exception(type(exc), exc, exc.__traceback__)),
        user_id=getattr(request.state, "user_id", None),
        ip=ip_del_cliente(request))
    return JSONResponse(
        status_code=500,
        content={"detail": "Hubo un error inesperado. Si escribís a soporte, "
                           f"pasales este código: {rastro.actual()}",
                 "request_id": rastro.actual()},
    )


def _plantilla_de(request) -> str:
    """`/api/admin/users/{user_id}` y no `/api/admin/users/u_123`: la
    pantalla agrupa por ruta, y con el id adentro cada error sería su propia
    ruta y no se agruparía nada."""
    ruta = request.scope.get("route")
    return getattr(ruta, "path", None) or request.url.path


@app.exception_handler(StarletteHTTPException)
async def _error_levantado_a_proposito(request, exc):
    """Los 5xx que el código levanta con intención —el 503 de «no pudimos
    generar el cobro», por ejemplo— también son errores que el panel tiene
    que mostrar: son justo los que un cliente sufre antes de quejarse.

    Los 4xx, casi ninguno: un 404 o un 403 de cliente es el sistema diciendo
    que no, no algo roto. Los cuatro que sí cuentan una historia los elige
    `services/rechazos.py`, con su umbral y su ventana para que un solo
    programa no llene el registro. Se delega en el manejador de siempre para
    que la respuesta sea idéntica.
    """
    ruta = _plantilla_de(request)
    user_id = getattr(request.state, "user_id", None)
    ip = ip_del_cliente(request)
    if exc.status_code >= 500:
        await errores.anotar(
            db, rastro=rastro.actual(), metodo=request.method,
            ruta=ruta, status=exc.status_code,
            tipo="HTTPException", mensaje=str(exc.detail),
            user_id=user_id, ip=ip)
    else:
        situacion = rechazos.que_situacion(exc.status_code, ruta)
        if situacion:
            # La clave del freno es la cuenta cuando la hay, y la conexión
            # cuando no: en las puertas de ingreso todavía no hay sesión, así
            # que agrupar por cuenta no agruparía nada.
            await rechazos.anotar_si_importa(
                db, situacion=situacion, clave=user_id or ip,
                rastro=rastro.actual(), metodo=request.method, ruta=ruta,
                status=exc.status_code, detalle=str(exc.detail),
                user_id=user_id, ip=ip)
    return await http_exception_handler(request, exc)


@app.exception_handler(RateLimitExceeded)
async def _paso_del_limite(request, exc):
    """El 429 de los límites de dinero, que antes no se veía en ningún lado.

    `RateLimitExceeded` ES una excepción HTTP, pero Starlette elige siempre
    el manejador MAS ESPECIFICO, así que el de `slowapi` se lo llevaba y el
    de arriba no lo veía pasar nunca. Quedaban dos limitadores en la misma
    aplicación, el piso de peticiones visible en «Errores» y éste invisible.

    La respuesta la sigue armando `slowapi`: acá sólo se anota.
    """
    await rechazos.anotar_si_importa(
        db, situacion="limite_de_dinero",
        clave=getattr(request.state, "user_id", None) or ip_del_cliente(request),
        rastro=rastro.actual(), metodo=request.method,
        ruta=_plantilla_de(request), status=429, detalle=str(exc.detail),
        user_id=getattr(request.state, "user_id", None),
        ip=ip_del_cliente(request))
    return _rate_limit_exceeded_handler(request, exc)
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

# El núcleo de cuentas (backend/nucleo). Se registra ACA y no en
# routes/__init__.py a propósito: nucleo.rutas importa la puerta del super
# administrador de routes.dependencies, y si el paquete routes lo importara a
# él habría un ciclo cada vez que un test importe el núcleo primero. Apagado
# de fábrica: con `nucleo_modo` en 0 todas sus rutas contestan 404.
from nucleo.rutas import router as nucleo_router  # noqa: E402
app.include_router(nucleo_router, prefix="/api")

# Y la guarda de cuatro ojos sobre la configuración del núcleo: con el núcleo
# prendido, `nucleo_modo` y los umbrales se cambian pidiendo y aprobando desde
# la pestaña, no desde Configuración. Se engancha ACA, único puente entre la
# aplicación y el núcleo. Ver nucleo/operacion/aprobaciones.py.
from nucleo.operacion import aprobaciones as _nucleo_aprobaciones  # noqa: E402
from services import configuracion as _configuracion  # noqa: E402
if _nucleo_aprobaciones.guarda_de_configuracion not in _configuracion.GUARDAS:
    _configuracion.GUARDAS.append(_nucleo_aprobaciones.guarda_de_configuracion)

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


# El comodín de GET se registra SIEMPRE, haya build o no.
#
#   Antes vivía dentro del `if` de arriba, y eso estaba bien mientras fuera el
#   único comodín: sin build no había ninguno y una dirección desconocida daba
#   404. Al agregar el de POST/PUT/PATCH/DELETE eso dejó de ser cierto: sin
#   build, el camino `/{full_path:path}` pasaba a existir SOLO para esos cuatro
#   métodos, y entonces un GET a CUALQUIER dirección —incluida la raíz— se
#   encontraba con una ruta que no acepta su método y contestaba 405.
#
#   O sea: el sitio entero contestaba «método no permitido» en cualquier
#   despliegue sin build. Lo agarró la suite en CI, que corre justo así porque
#   `frontend/dist` no está versionado.
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(request: Request, full_path: str):
    from fastapi.responses import FileResponse

    # Debajo de /api/ no hay pantalla que servir: lo que no es una ruta es un
    # error. Antes devolvía el index.html con un 200, y entonces un integrador
    # que le pegaba a una dirección inexistente lo veía como si hubiera
    # funcionado.
    if sin_ruta.es_de_la_api(full_path):
        return _no_existe(request, full_path)

    # Sin build no hay ninguna aplicación que servir, así que lo honesto es
    # decir que eso no está — nunca un 405, que hablaría del método cuando el
    # problema es que no hay nada ahí.
    if not FRONTEND_BUILD_DIR.exists():
        return _no_existe(request, full_path)

    # Con build: los archivos reales (sw.js, íconos, manifest…) si existen; si
    # no, el index.html, porque `/envios/ABC123` lo resuelve el navegador y no
    # el servidor.
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
