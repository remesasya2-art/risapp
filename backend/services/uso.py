"""
services/uso.py — Qué usa la gente, contado en el servidor.

PARA QUE

    El panel sabía cuánta plata se movió y cuántas cuentas hay, pero no qué
    hace la gente adentro de la aplicación: si alguien abre Referidos, si
    cotiza una encomienda y no la confirma, si el historial se mira más que
    el saldo. Las visitas las mide Cloudflare, afuera, por página y sin saber
    quién está logueado. Y una decisión de producto —qué mejorar, qué sacar—
    sin ese número es una adivinanza.

QUE SE CUENTA, Y QUE NO

    Cada pedido de un CLIENTE con sesión, por día y por ruta plantilla
    (`/api/envios/{envio_id}` y no `/api/envios/ENV-123`, para que agrupe).
    Dos números por día y ruta: cuántos pedidos y cuántas cuentas distintas.

    · No se cuenta al personal ni a los administradores: el panel sondea cada
      15, 30 y 60 segundos y taparía a los clientes. Y lo que se quiere saber
      es qué usa la gente, no qué usa el equipo.
    · No se cuentan los latidos: lo que la aplicación pide sola, sin que la
      persona toque nada (`/auth/me`, el contador de avisos, los sondeos de
      estado de un pago). Contarlos convierte «tuvo la pestaña abierta» en la
      función más usada.
    · No se guarda el cuerpo, ni los parámetros, ni las cabeceras. Sólo la
      plantilla de la ruta. Un contador no necesita saber a quién le mandó
      plata cada uno, y lo que no se guarda no se filtra.

COMO, Y POR QUE NO ES UNA ESCRITURA POR PEDIDO

    Se acumula en memoria y se vuelca a la base cada 30 segundos, con `$inc`
    y `$addToSet`: con dos workers, cada uno vuelca lo suyo y la base suma.
    Escribir en cada pedido duplicaría las escrituras de la aplicación para
    un número que nadie mira en tiempo real. Si el volcado falla, lo que no
    se pudo escribir vuelve a la memoria para la próxima vuelta; si el
    proceso muere, se pierden como mucho 30 segundos de estadística. Es un
    contador, no un libro contable: ese trato es el correcto acá.

    Se borra solo a los 90 días (índice TTL): alcanza para comparar un
    trimestre y no acumula sin fin.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

COLECCION = "uso"
DIAS_QUE_SE_GUARDAN = 90
CADA_CUANTO_SE_VUELCA = 30          # segundos
ROL_QUE_SE_CUENTA = "user"          # los clientes, y nadie más

# Tope de lo que una consulta trae de la base. Por encima de esto el número
# sale truncado y queda escrito en el registro; no se rompe la pantalla.
_TOPE = 50_000

# Lo que la aplicación pide sola. La lista es explícita y no una regla sobre
# el nombre, porque `/api/btc/precio` no se llama «status» y se sondea cada
# diez segundos igual.
LATIDOS = frozenset({
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/heartbeat"),
    ("POST", "/api/auth/offline"),
    ("GET", "/api/health"),
    ("GET", "/api/rate"),
    ("GET", "/api/notifications/unread-count"),
    ("GET", "/api/btc/precio"),
    ("GET", "/api/policies/status"),
    ("GET", "/api/pin/status"),
    ("GET", "/api/push/web/status"),
    ("GET", "/api/auth/2fa/status"),
    ("GET", "/api/auth/password-status"),
    ("GET", "/api/limits/me"),
})


def es_latido(metodo: str, ruta: str) -> bool:
    """Un pedido que no dice nada de lo que la persona quiso hacer."""
    if (metodo, ruta) in LATIDOS:
        return True
    # Los sondeos de estado de un pago: `/status/{id}`, `/{id}/status`. Se
    # disparan cada cinco segundos mientras la pantalla espera.
    return metodo == "GET" and ("/status" in ruta)


# El nombre que ve el super administrador. Lo que no está acá se muestra con
# su plantilla cruda, así una ruta nueva aparece igual y se le pone nombre
# después: la lista es para leer, no para filtrar.
NOMBRES = {
    ("GET", "/api/transactions"): "Movimientos (inicio e historial)",
    ("GET", "/api/transactions/{transaction_id}"): "Detalle de un movimiento",
    ("GET", "/api/transactions/export"): "Exportación del historial",
    ("POST", "/api/reais/send"): "Envío a Brasil (reales)",
    ("POST", "/api/withdrawal/create"): "Envío a Venezuela (bolívares)",
    ("POST", "/api/withdraw"): "Envío a Venezuela (bolívares)",
    ("POST", "/api/withdraw-crypto"): "Envío con cripto",
    ("POST", "/api/recharge/ves"): "Recarga desde Venezuela",
    ("POST", "/api/gestor/pix/create"): "Recarga por PIX",
    ("POST", "/api/payments/card/quote"): "Cotización con tarjeta",
    ("POST", "/api/payments/card/process"): "Recarga con tarjeta",
    ("POST", "/api/credits/deposit"): "Depósito cripto",
    ("GET", "/api/credits/history"): "Historial cripto",
    ("POST", "/api/btc/generar-invoice"): "Envío BTC Lightning",
    ("GET", "/api/btc/historial"): "Historial BTC",
    ("POST", "/api/envios/cotizar"): "Cotización de encomienda",
    ("POST", "/api/envios/crear"): "Encomienda confirmada",
    ("GET", "/api/envios/{envio_id}"): "Detalle de una encomienda",
    ("GET", "/api/envios/catalogo"): "Catálogo de encomiendas",
    ("POST", "/api/verification/submit"): "Documentos de verificación enviados",
    ("GET", "/api/verification/status"): "Estado de la verificación",
    ("GET", "/api/referidos/mis-referidos"): "Referidos",
    ("GET", "/api/referidos/mi-codigo"): "Código de invitación",
    ("GET", "/api/soporte/casos"): "Soporte: mis casos",
    ("POST", "/api/soporte/casos"): "Soporte: caso abierto",
    ("POST", "/api/soporte/casos/{caso_id}/mensajes"): "Soporte: mensaje enviado",
    ("GET", "/api/notifications"): "Avisos",
    ("GET", "/api/beneficiaries"): "Beneficiarios (Venezuela)",
    ("POST", "/api/beneficiaries"): "Beneficiario agregado (Venezuela)",
    ("GET", "/api/beneficiaries/br"): "Beneficiarios (Brasil)",
    ("POST", "/api/beneficiaries/br"): "Beneficiario agregado (Brasil)",
    ("GET", "/api/user/balance"): "Saldo",
    ("POST", "/api/pin/set"): "PIN configurado",
    ("POST", "/api/webauthn/register/verify"): "Huella activada",
    ("POST", "/api/auth/change-password"): "Cambio de contraseña",
    ("GET", "/api/gestor/pix/history"): "Historial PIX",
}


def nombre_de(metodo: str, ruta: str):
    return NOMBRES.get((metodo, ruta))


# ══════════════════════════════════════════════════════════════════════════
# Contar, en memoria
# ══════════════════════════════════════════════════════════════════════════

# (día, método, ruta) -> {"pedidos": n, "cuentas": {user_id, ...}}
_pendiente: dict = {}


def _dia(ahora=None) -> str:
    ahora = ahora or datetime.now(timezone.utc)
    return ahora.strftime("%Y-%m-%d")


def contar(*, metodo: str, ruta: str, user_id, rol, ahora=None) -> bool:
    """Anota un pedido. Devuelve si se contó.

    Sin `user_id` no hay cliente; con un rol que no es el de cliente es el
    equipo; y un latido no dice nada. Los tres casos se descartan ACA, en un
    solo lugar, para que el middleware no tenga criterio propio.
    """
    if not user_id or rol != ROL_QUE_SE_CUENTA:
        return False
    if es_latido(metodo, ruta):
        return False
    clave = (_dia(ahora), metodo, ruta)
    entrada = _pendiente.get(clave)
    if entrada is None:
        entrada = _pendiente[clave] = {"pedidos": 0, "cuentas": set()}
    entrada["pedidos"] += 1
    entrada["cuentas"].add(user_id)
    return True


def pendientes() -> int:
    """Cuántos pedidos esperan volcado. Para los tests y el apagado."""
    return sum(e["pedidos"] for e in _pendiente.values())


def _devolver(clave, entrada) -> None:
    """Lo que no se pudo escribir vuelve a la memoria, sumado a lo nuevo."""
    ahora = _pendiente.get(clave)
    if ahora is None:
        _pendiente[clave] = entrada
        return
    ahora["pedidos"] += entrada["pedidos"]
    ahora["cuentas"] |= entrada["cuentas"]


async def volcar(db) -> int:
    """Escribe lo acumulado. Devuelve cuántas filas se escribieron.

    NUNCA LEVANTA. Corre en una tarea de fondo y en el apagado: una excepción
    acá mata la tarea en silencio y el contador deja de volcar para siempre,
    o traba el apagado. Lo que falla se devuelve a la memoria y se reintenta
    en la próxima vuelta.
    """
    global _pendiente
    if not _pendiente:
        return 0
    lote, _pendiente = _pendiente, {}
    escritas = 0
    for clave, entrada in lote.items():
        dia, metodo, ruta = clave
        try:
            await db[COLECCION].update_one(
                {"dia": dia, "metodo": metodo, "ruta": ruta},
                {"$inc": {"pedidos": entrada["pedidos"]},
                 "$addToSet": {"cuentas": {"$each": sorted(entrada["cuentas"])}},
                 # El día como fecha, para que el índice TTL tenga de qué
                 # colgarse: `dia` es texto y un TTL no lee texto.
                 "$setOnInsert": {"cuando": datetime.strptime(dia, "%Y-%m-%d")
                                  .replace(tzinfo=timezone.utc)}},
                upsert=True)
            escritas += 1
        except Exception as e:                            # pragma: no cover
            logger.warning("no se pudo volcar el uso de %s %s: %s", metodo, ruta, e)
            _devolver(clave, entrada)
    return escritas


_tarea = None


async def _bucle(db):
    while True:
        await asyncio.sleep(CADA_CUANTO_SE_VUELCA)
        await volcar(db)


def arrancar(db) -> None:
    """Deja corriendo el volcado periódico. Se llama una vez, al arrancar."""
    global _tarea
    if _tarea is not None and not _tarea.done():
        return
    _tarea = asyncio.create_task(_bucle(db))


async def parar(db) -> None:
    """Corta el volcado periódico y escribe lo que quedó. Para el apagado."""
    global _tarea
    if _tarea is not None:
        _tarea.cancel()
        try:
            await _tarea
        except (asyncio.CancelledError, Exception):
            pass
        _tarea = None
    await volcar(db)


async def preparar_indices(db) -> None:
    await db[COLECCION].create_index(
        "cuando", expireAfterSeconds=DIAS_QUE_SE_GUARDAN * 24 * 3600)
    await db[COLECCION].create_index(
        [("dia", 1), ("metodo", 1), ("ruta", 1)], unique=True)


# ══════════════════════════════════════════════════════════════════════════
# El middleware
# ══════════════════════════════════════════════════════════════════════════

class Contador:
    """Cuenta el pedido DESPUES de que la ruta lo atendió.

    Después y no antes, por dos cosas que sólo existen después: la plantilla
    de la ruta (`scope["route"]`, que pone el enrutador al elegir) y el
    usuario (`scope["state"]`, que cuelga `get_current_user` al autenticar).
    Un pedido que no llegó a ninguna ruta —un 404, uno que cortó el tope de
    cuerpo— no tiene plantilla y no se cuenta.

    Es ASGI pelado, como `rastro.Rastro`, y por el mismo motivo: corre en
    todos los pedidos y no puede permitirse armar un `Request` entero. Y va
    en un `finally`: si la ruta reventó, la persona igual quiso usarla.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            anotar_el_pedido(scope)


def anotar_el_pedido(scope) -> bool:
    """Lo que el middleware sabe del pedido, y nada más: método, plantilla,
    quién. Nunca levanta: un contador no puede tirar abajo una respuesta."""
    try:
        ruta = getattr(scope.get("route"), "path", None)
        if not ruta:
            return False
        estado = scope.get("state") or {}
        return contar(metodo=scope.get("method", ""), ruta=ruta,
                      user_id=estado.get("user_id"), rol=estado.get("rol"))
    except Exception as e:                                # pragma: no cover
        logger.warning("no se pudo contar el pedido: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════
# Leer: lo contado
# ══════════════════════════════════════════════════════════════════════════

def _dias_de_la_ventana(dias: int, hoy=None):
    hoy = (hoy or datetime.now(timezone.utc)).date()
    return [(hoy - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias - 1, -1, -1)]


async def resumen(db, *, dias: int = 30, hoy=None) -> dict:
    """Por función y por día, en la ventana. Las cuentas distintas se cuentan
    de verdad (una persona que usó algo tres días es una, no tres)."""
    ventana = _dias_de_la_ventana(dias, hoy)
    filtro = {"dia": {"$gte": ventana[0], "$lte": ventana[-1]}}
    col = db[COLECCION]

    por_funcion = await col.aggregate([
        {"$match": filtro},
        {"$group": {"_id": {"metodo": "$metodo", "ruta": "$ruta"},
                    "pedidos": {"$sum": "$pedidos"}}},
    ]).to_list(length=_TOPE)
    cuentas_por_funcion = await col.aggregate([
        {"$match": filtro},
        {"$unwind": "$cuentas"},
        {"$group": {"_id": {"metodo": "$metodo", "ruta": "$ruta", "cuenta": "$cuentas"}}},
        {"$group": {"_id": {"metodo": "$_id.metodo", "ruta": "$_id.ruta"},
                    "cuentas": {"$sum": 1}}},
    ]).to_list(length=_TOPE)
    cuentas_de = {(c["_id"]["metodo"], c["_id"]["ruta"]): c["cuentas"]
                  for c in cuentas_por_funcion}
    funciones = []
    for f in por_funcion:
        metodo, ruta = f["_id"]["metodo"], f["_id"]["ruta"]
        funciones.append({
            "metodo": metodo, "ruta": ruta, "nombre": nombre_de(metodo, ruta),
            "pedidos": f["pedidos"], "cuentas": cuentas_de.get((metodo, ruta), 0),
        })
    funciones.sort(key=lambda f: (-f["pedidos"], f["ruta"]))

    pedidos_por_dia = await col.aggregate([
        {"$match": filtro},
        {"$group": {"_id": "$dia", "pedidos": {"$sum": "$pedidos"}}},
    ]).to_list(length=_TOPE)
    cuentas_por_dia = await col.aggregate([
        {"$match": filtro},
        {"$unwind": "$cuentas"},
        {"$group": {"_id": {"dia": "$dia", "cuenta": "$cuentas"}}},
        {"$group": {"_id": "$_id.dia", "cuentas": {"$sum": 1}}},
    ]).to_list(length=_TOPE)
    p_de = {p["_id"]: p["pedidos"] for p in pedidos_por_dia}
    c_de = {c["_id"]: c["cuentas"] for c in cuentas_por_dia}
    por_dia = [{"dia": d, "pedidos": p_de.get(d, 0), "cuentas": c_de.get(d, 0)}
               for d in ventana]

    return {"dias": dias, "desde": ventana[0], "hasta": ventana[-1],
            "funciones": funciones, "por_dia": por_dia}


# ══════════════════════════════════════════════════════════════════════════
# Leer: lo que ya estaba en la base
# ══════════════════════════════════════════════════════════════════════════

# Cada operación vive en su colección, con su campo de fecha y su estado de
# «terminada». La lista está acá, en un solo lugar, con el nombre que ve el
# super administrador al lado.
_OPERACIONES = (
    # (nombre, colección, campo de fecha, filtro de terminada)
    ("Recargas por PIX", "gestor_pix_payments", "created_at",
     {"status": {"$in": ["paid", "approved"]}}),
    ("Recargas con tarjeta", "card_payments", "created_at",
     {"status": "approved"}),
    ("Depósitos cripto", "crypto_deposits", "created_at",
     {"credited": True}),
    ("Envíos BTC Lightning", "btc_remesas", "creado_en",
     {"estado": "enviado"}),
    ("Encomiendas confirmadas", "envios", "confirmado_at", None),
    ("Casos de soporte", "soporte_casos", "creado_en", None),
)


def _nombre_de_la_transaccion(tx: dict) -> str:
    tipo = tx.get("type")
    if tipo == "recharge_ves":
        return "Recargas desde Venezuela"
    if tipo == "withdrawal":
        entra, sale = tx.get("currency_input"), tx.get("currency_output")
        if sale == "BRL":
            return "Envíos a Brasil"
        if entra == "RIS":
            return "Envíos a Venezuela"
        return "Envíos con cripto"
    return str(tipo or "otras")


def _con_zona(d):
    if isinstance(d, datetime) and d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d


def _lunes_de(d: datetime) -> str:
    return (d.date() - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


async def numeros_de_la_base(db, *, dias: int = 30, ahora=None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)
    vivos = {"is_deleted": {"$ne": True}}

    # Altas y embudo, de las cuentas creadas en la ventana. Sólo dos campos
    # por cuenta: es lo único que hace falta para contar.
    altas = await db.users.find(
        {**vivos, "created_at": {"$gte": desde}},
        {"_id": 0, "created_at": 1, "verification_status": 1},
    ).limit(_TOPE).to_list(length=_TOPE)
    if len(altas) >= _TOPE:                               # pragma: no cover
        logger.warning("las altas de la ventana superan el tope %s", _TOPE)

    semanas = {}
    for a in altas:
        creada = _con_zona(a.get("created_at"))
        if isinstance(creada, datetime):
            semanas[_lunes_de(creada)] = semanas.get(_lunes_de(creada), 0) + 1
    # Todas las semanas de la ventana, con cero donde no hubo altas: una
    # semana que falta en el gráfico se lee como un dato roto, no como cero.
    primer_lunes = _lunes_de(desde)
    altas_por_semana = []
    lunes = datetime.strptime(primer_lunes, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    while lunes <= ahora:
        clave = lunes.strftime("%Y-%m-%d")
        altas_por_semana.append({"semana": clave, "cuantos": semanas.get(clave, 0)})
        lunes += timedelta(days=7)

    estados = [a.get("verification_status") for a in altas]
    embudo = {
        "registrados": len(altas),
        "enviaron_documentos": sum(1 for e in estados if e in ("pending", "verified", "rejected")),
        "en_revision": sum(1 for e in estados if e == "pending"),
        "aprobados": sum(1 for e in estados if e == "verified"),
        "rechazados": sum(1 for e in estados if e == "rejected"),
    }

    # El filtro de verificadas se arma en dos pasos y no como un diccionario
    # de dos claves, a propósito: el guardián del bono de bienvenida
    # (tests/test_bono_de_bienvenida.py) toma un diccionario de dos o más
    # claves con el estado «verified» adentro como una ESCRITURA del KYC, y
    # ésta es una lectura. Armado así, ni lo mira.
    filtro_verificadas = dict(vivos)
    filtro_verificadas["verification_status"] = "verified"
    totales = {
        "cuentas": await db.users.count_documents(vivos),
        "verificadas": await db.users.count_documents(filtro_verificadas),
    }
    activos = {
        "7": await db.users.count_documents({**vivos, "last_login": {"$gte": ahora - timedelta(days=7)}}),
        "30": await db.users.count_documents({**vivos, "last_login": {"$gte": ahora - timedelta(days=30)}}),
    }

    # Las operaciones que viven en `transactions` se distinguen por moneda,
    # así que se traen tres campos y se clasifican acá.
    txs = await db.transactions.find(
        {"created_at": {"$gte": desde}},
        {"_id": 0, "type": 1, "currency_input": 1, "currency_output": 1, "status": 1},
    ).limit(_TOPE).to_list(length=_TOPE)
    operaciones = {}
    for tx in txs:
        nombre = _nombre_de_la_transaccion(tx)
        o = operaciones.setdefault(nombre, {"nombre": nombre, "iniciadas": 0, "terminadas": 0})
        o["iniciadas"] += 1
        if tx.get("status") == "completed":
            o["terminadas"] += 1
    for nombre, coleccion, campo, terminada in _OPERACIONES:
        filtro = {campo: {"$gte": desde}}
        iniciadas = await db[coleccion].count_documents(filtro)
        terminadas = (await db[coleccion].count_documents({**filtro, **terminada})
                      if terminada is not None else None)
        operaciones[nombre] = {"nombre": nombre, "iniciadas": iniciadas, "terminadas": terminadas}
    lista = sorted(operaciones.values(), key=lambda o: (-o["iniciadas"], o["nombre"]))

    return {"dias": dias, "altas_por_semana": altas_por_semana, "embudo": embudo,
            "totales": totales, "activos": activos, "operaciones": lista}


async def todo(db, *, dias: int = 30) -> dict:
    """Lo que la pestaña muestra, en una sola respuesta."""
    contado = await resumen(db, dias=dias)
    base = await numeros_de_la_base(db, dias=dias)
    return {"dias": dias, "desde": contado["desde"], "hasta": contado["hasta"],
            "funciones": contado["funciones"], "por_dia": contado["por_dia"],
            "base": base}
