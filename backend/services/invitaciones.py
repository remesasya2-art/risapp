"""
Invitaciones de acceso del personal — la primera llave.

EL PROBLEMA QUE RESUELVE

    Recursos Humanos da de alta a una persona: le crea el usuario, le pone
    el rol, le pone los permisos. Y hasta acá llegaba. Esa cuenta nacía sin
    contraseña y sin el correo verificado, o sea que su dueño no podía
    entrar por ninguna puerta:

      - `/auth/login-password` la rechaza dos veces: primero por
        `email_verified`, después por `password_set`.
      - `/auth/resend-verification-code` lee `pending_verifications`, una
        colección donde el alta de RRHH no escribe nada.
      - `/auth/request-password-reset` le manda una contraseña temporal que
        no sirve, porque el login sigue frenando en `email_verified`.

    No había ningún momento en que el colaborador configurara su clave.
    Este módulo es ese momento.

COMO FUNCIONA

    El alta emite un token de un solo uso, con vencimiento, que se manda por
    correo a la dirección del legajo. Quien lo presenta demuestra dos cosas
    a la vez: que tiene acceso a esa casilla —por eso la activación da el
    correo por verificado, y no hay que mandar un código aparte— y que fue
    el super administrador quien lo puso ahí.

LO QUE SE GUARDA Y LO QUE NO

    En la base queda el SHA-256 del token, nunca el token. Quien lea la
    colección —un backup, un dump, un empleado con acceso a Mongo— ve
    hashes, y un hash no abre nada. El token en claro existe una sola vez:
    en el cuerpo del correo.

    Emitir una invitación anula las anteriores de esa persona. Si el super
    administrador reenvía porque el correo se perdió, el link viejo deja de
    servir en el mismo instante, no queda una segunda llave dando vueltas.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

COLECCION = "invitaciones_personal"

# Cuánto vive una invitación. Corto a propósito: es una llave a una cuenta
# con permisos de administración viajando por correo. Si vence, el super
# administrador reenvía —lo que además deja otra línea en el libro.
HORAS_DE_VIDA = 72

# Estados que devuelve `estado()`. Se declaran para que la pantalla no
# invente strings y para que un cambio de nombre rompa un test, no la vista.
SIN_INVITACION = "sin_invitacion"
PENDIENTE = "pendiente"
VENCIDA = "vencida"
USADA = "usada"


class InvitacionInvalida(Exception):
    """El token no existe, ya se usó, se anuló, o venció.

    Es un solo error a propósito: distinguir "no existe" de "vencida" le
    diría a quien prueba tokens al voleo cuáles acertó a medias.
    """


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def asegurar_indices(db):
    """Índices de la colección. Se llama en el arranque."""
    try:
        await db[COLECCION].create_index("huella", unique=True, name="huella_unica")
        await db[COLECCION].create_index([("user_id", 1), ("creada_en", -1)],
                                         name="por_persona")
        logger.info("INDICE ok: %s (huella única, por persona)", COLECCION)
    except Exception as e:
        logger.error("No se pudieron crear los índices de %s: %s", COLECCION, e)


async def emitir(db, *, user_id: str, email: str, emitida_por: Optional[str] = None) -> str:
    """Emite una invitación y devuelve el token EN CLARO.

    El token en claro no se guarda ni se loguea: es el valor de retorno, y
    el único destino legítimo es el correo. Las invitaciones anteriores de
    esta persona quedan anuladas.
    """
    ahora = datetime.now(timezone.utc)

    # Primero anular las viejas. Si lo hiciéramos después, entre el insert y
    # el update habría un instante con dos llaves vivas.
    await db[COLECCION].update_many(
        {"user_id": user_id, "usada": False, "anulada": False},
        {"$set": {"anulada": True, "anulada_en": ahora}},
    )

    token = secrets.token_urlsafe(32)
    await db[COLECCION].insert_one({
        "_id": uuid.uuid4().hex,
        "huella": _huella(token),
        "user_id": user_id,
        "email": email,
        "creada_en": ahora,
        "expira_en": ahora + timedelta(hours=HORAS_DE_VIDA),
        "emitida_por": emitida_por,
        "usada": False,
        "usada_en": None,
        "anulada": False,
    })
    return token


async def mirar(db, token: str) -> dict:
    """Valida el token SIN consumirlo, para que la pantalla salude por
    nombre antes de pedir la contraseña. Levanta InvitacionInvalida."""
    doc = await db[COLECCION].find_one({"huella": _huella(token)})
    if not doc or doc.get("usada") or doc.get("anulada"):
        raise InvitacionInvalida()
    if _vencida(doc):
        raise InvitacionInvalida()
    return doc


async def consumir(db, token: str) -> dict:
    """Consume el token de forma atómica y devuelve la invitación.

    El `usada: False` va dentro del filtro, no en un `if` previo: dos
    pedidos simultáneos con el mismo token entran los dos al `if`, pero al
    `find_one_and_update` gana uno solo. El otro se lleva un None y termina
    en InvitacionInvalida, que es exactamente lo correcto.
    """
    ahora = datetime.now(timezone.utc)
    doc = await db[COLECCION].find_one_and_update(
        {"huella": _huella(token), "usada": False, "anulada": False},
        {"$set": {"usada": True, "usada_en": ahora}},
    )
    if not doc:
        raise InvitacionInvalida()
    # El vencimiento se mira después de ganar la carrera: dejarlo en el
    # filtro hace que Mongo compare fechas con zonas horarias que puede
    # haber guardado ingenuas. Ya quedó consumida, así que igual no sirve.
    if _vencida(doc):
        raise InvitacionInvalida()
    return doc


def _vencida(doc: dict) -> bool:
    expira = doc.get("expira_en")
    if expira is None:
        return True
    if expira.tzinfo is None:
        # Mongo devuelve las fechas sin zona. Son UTC; sin esto la
        # comparación de abajo revienta con TypeError.
        expira = expira.replace(tzinfo=timezone.utc)
    return expira <= datetime.now(timezone.utc)


def _clasificar(doc: Optional[dict]) -> dict:
    """De un documento de invitación al estado que mira la pantalla."""
    if not doc or doc.get("anulada"):
        return {"estado": SIN_INVITACION, "expira_en": None, "usada_en": None}
    if doc.get("usada"):
        return {"estado": USADA, "expira_en": None,
                "usada_en": _iso(doc.get("usada_en"))}
    if _vencida(doc):
        return {"estado": VENCIDA, "expira_en": _iso(doc.get("expira_en")),
                "usada_en": None}
    return {"estado": PENDIENTE, "expira_en": _iso(doc.get("expira_en")),
            "usada_en": None}


async def estado(db, user_id: str) -> dict:
    """En qué anda la invitación de esta persona, para la pantalla de RRHH.

    Nunca levanta: es información de apoyo en una lista, y no vale la pena
    voltear la pantalla entera porque no se pudo leer una fecha.
    """
    try:
        # Sólo las vigentes. Emitir anula las anteriores, así que una
        # anulada siempre tiene una más nueva detrás; ordenar por fecha y
        # confiar en el desempate es frágil, porque dos emisiones seguidas
        # pueden caer en el mismo microsegundo.
        doc = await db[COLECCION].find_one({"user_id": user_id, "anulada": False},
                                           sort=[("creada_en", -1)])
    except Exception as e:
        logger.warning("No se pudo leer la invitación de %s: %s", user_id, e)
        return _clasificar(None)
    return _clasificar(doc)


async def estado_de_varios(db, user_ids) -> dict:
    """Lo mismo para una lista, en una sola consulta.

    La pantalla de RRHH muestra a todo el personal junto; una consulta por
    fila convierte una lista de veinte en veinte viajes a la base.
    """
    ids = list(user_ids)
    if not ids:
        return {}
    ultima: dict = {}
    try:
        cursor = db[COLECCION].find(
            {"user_id": {"$in": ids}, "anulada": False}).sort("creada_en", -1)
        async for doc in cursor:
            # Vienen de la más nueva a la más vieja: la primera de cada
            # persona es la que vale, las siguientes se descartan.
            ultima.setdefault(doc["user_id"], doc)
    except Exception as e:
        logger.warning("No se pudieron leer las invitaciones: %s", e)
        return {uid: _clasificar(None) for uid in ids}
    return {uid: _clasificar(ultima.get(uid)) for uid in ids}


def _iso(cuando) -> Optional[str]:
    if cuando is None:
        return None
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    return cuando.isoformat()
