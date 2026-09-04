"""
El libro de auditoría: quién hizo qué, sobre quién, cuándo y desde dónde.

POR QUE EXISTE

    De las 96 rutas de administración que escriben en la base, sólo cuatro
    dejaban rastro: los tres borrados catastróficos y el ajuste manual de
    saldo. Aprobar un KYC, aprobar una recarga, suspender a un usuario, mover
    la tasa de cambio u OTORGAR PERMISOS no quedaban registrados en ningún
    lado.

    Ese último es el que ordena todo lo demás: `update_user_balance` asienta
    cuando alguien mueve plata, pero entregarle a una persona el PODER de
    mover plata no se asentaba. Si alguien entrara y se diera permisos, no
    habría forma de enterarse ni de reconstruir cuándo pasó.

    Y había cuatro registros distintos —`audit_log`, `admin_access_log`,
    `admin_logs`, `accounting_audit_log`— cada uno escrito por un solo módulo,
    uno de ellos SIN NINGÚN endpoint que lo leyera, y ninguno visible en el
    panel. Cuatro libros a medio hacer no son una auditoría.

QUE GARANTIZA

    - Se escribe, nunca se edita ni se borra. No hay función para modificar
      una línea: el módulo no la ofrece.
    - Cada línea se basta sola. Guarda el nombre y el correo del actor, no
      sólo su id, porque dentro de un año ese usuario puede no existir y la
      línea tiene que seguir diciendo quién fue.
    - Guarda el estado ANTES y DESPUÉS. Un registro que dice "se cambiaron
      los permisos" sin decir de qué a qué no sirve para investigar nada.
    - Fecha y hora en UTC y también en la hora de Caracas, que es la que usa
      quien lee el panel. Guardar sólo UTC obliga a hacer la cuenta a mano;
      guardar sólo Caracas pierde la referencia absoluta.
    - Nunca rompe la operación que audita. Si el libro falla, la línea se
      pierde y queda un ERROR en el log, pero el KYC se aprueba igual. Un
      libro que puede tumbar una operación es un libro que alguien va a
      terminar sacando.

LO QUE NO HACE
    No reemplaza al mayor contable (`services/ledger.py`). Ahí va el
    movimiento de dinero, peso por peso. Acá va el movimiento de PODER y de
    ESTADO: quién decidió, sobre quién, y qué había antes.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLECCION = "auditoria"

# La hora que lee quien mira el panel. El resto de la app ya usa esta zona
# (services/accounting_engine.CARACAS_TZ).
CARACAS = timezone(timedelta(hours=-4))


# ─── Las acciones. Añadir una es agregarla acá, no inventar una cadena ────
#
# Se declaran para que el panel pueda ofrecer un filtro cerrado y para que un
# error de tipeo en el nombre de una acción se vea en los tests, no en el
# momento de buscar algo que no aparece.

class Cat:
    """Categorías, para agrupar en el panel."""
    PERSONAL = "personal"        # altas, bajas y permisos del personal
    KYC = "kyc"
    DINERO = "dinero"
    USUARIOS = "usuarios"
    CONFIG = "configuracion"
    SESION = "sesion"
    PELIGRO = "peligro"          # borrados masivos


ACCIONES = {
    # Personal y permisos — el motivo por el que este libro existe
    "personal.alta":            (Cat.PERSONAL, "Alta de personal"),
    "personal.baja":            (Cat.PERSONAL, "Baja de personal"),
    "personal.permisos":        (Cat.PERSONAL, "Cambio de permisos"),
    "personal.reactivacion":    (Cat.PERSONAL, "Reactivación de personal"),
    "personal.datos":           (Cat.PERSONAL, "Cambio de datos del legajo"),
    "personal.invitacion":      (Cat.PERSONAL, "Invitación de acceso enviada"),
    "personal.activacion":      (Cat.PERSONAL, "Personal activó su acceso"),
    # KYC
    "kyc.aprobado":             (Cat.KYC, "Verificación aprobada"),
    "kyc.rechazado":            (Cat.KYC, "Verificación rechazada"),
    "kyc.re_revision":          (Cat.KYC, "Verificación devuelta a revisión"),
    "kyc.riesgo":               (Cat.KYC, "Nivel de riesgo asignado"),
    # Dinero
    "dinero.ajuste_manual":     (Cat.DINERO, "Ajuste manual de saldo"),
    "dinero.recarga_aprobada":  (Cat.DINERO, "Recarga aprobada"),
    "dinero.recarga_rechazada": (Cat.DINERO, "Recarga rechazada"),
    "dinero.retiro_aprobado":   (Cat.DINERO, "Retiro aprobado"),
    "dinero.retiro_rechazado":  (Cat.DINERO, "Retiro rechazado"),
    # Usuarios
    "usuario.suspendido":       (Cat.USUARIOS, "Usuario suspendido"),
    "usuario.reactivado":       (Cat.USUARIOS, "Usuario reactivado"),
    "usuario.lista_negra":      (Cat.USUARIOS, "Usuario a lista negra"),
    # Configuración
    "config.tasa":              (Cat.CONFIG, "Cambio de tasa de cambio"),
    "config.limites":           (Cat.CONFIG, "Cambio de límites"),
    # Sesión
    "sesion.ingreso_admin":     (Cat.SESION, "Ingreso de administrador"),
    "sesion.cerradas":          (Cat.SESION, "Sesiones cerradas"),
    # Peligro
    "peligro.borrado_total":    (Cat.PELIGRO, "Borrado total de datos"),
    "peligro.borrado_contable": (Cat.PELIGRO, "Borrado de datos contables"),
    "peligro.restauracion":     (Cat.PELIGRO, "Restauración de transacciones"),
}


class AccionDesconocida(ValueError):
    """Una acción que no está declarada arriba."""


def _actor(quien) -> dict:
    """Quién hizo la acción, con lo suficiente para identificarlo dentro de
    un año, cuando ese usuario capaz ya no exista."""
    if quien is None:
        return {"user_id": None, "email": None, "nombre": None, "rol": None}
    leer = quien.get if isinstance(quien, dict) else lambda k, d=None: getattr(quien, k, d)
    return {
        "user_id": leer("user_id"),
        "email": leer("email"),
        "nombre": leer("name") or leer("nombre"),
        "rol": leer("role") or leer("rol"),
    }


def _origen(request) -> dict:
    """Desde dónde. Sin request queda en None, no se inventa."""
    if request is None:
        return {"ip": None, "pais": None, "navegador": None}
    cabeceras = getattr(request, "headers", {}) or {}
    reenviada = cabeceras.get("x-forwarded-for")
    ip = (reenviada.split(",")[0].strip() if reenviada
          else (getattr(getattr(request, "client", None), "host", None)))
    return {
        "ip": ip,
        "pais": cabeceras.get("cf-ipcountry"),
        "navegador": (cabeceras.get("user-agent") or "")[:200] or None,
    }


async def registrar(
    db,
    accion: str,
    *,
    quien=None,
    request=None,
    objetivo_tipo: Optional[str] = None,
    objetivo_id: Optional[str] = None,
    objetivo_desc: Optional[str] = None,
    antes: Any = None,
    despues: Any = None,
    detalle: Optional[dict] = None,
    exito: bool = True,
) -> Optional[str]:
    """Asienta una línea. Devuelve su id, o None si no se pudo escribir.

    NUNCA levanta: la operación auditada no se cae porque el libro falle. Si
    falla, queda un ERROR en el log con todo lo que se iba a escribir, para
    que se pueda reconstruir a mano.
    """
    if accion not in ACCIONES:
        # Esto sí revienta, y a propósito: una acción mal escrita es una línea
        # que después nadie encuentra al filtrar. Se ve en los tests, no en
        # medio de una investigación.
        raise AccionDesconocida(
            f"Acción no declarada: {accion!r}. Agregala a ACCIONES en "
            f"services/auditoria.py.")

    categoria, etiqueta = ACCIONES[accion]
    ahora = datetime.now(timezone.utc)
    linea = {
        "_id": uuid.uuid4().hex,
        "accion": accion,
        "categoria": categoria,
        "etiqueta": etiqueta,
        "actor": _actor(quien),
        "objetivo": {
            "tipo": objetivo_tipo,
            "id": objetivo_id,
            "descripcion": objetivo_desc,
        },
        "antes": antes,
        "despues": despues,
        "detalle": detalle or {},
        "exito": bool(exito),
        "origen": _origen(request),
        # Las dos horas: la absoluta y la que lee quien mira el panel.
        "cuando": ahora,
        "cuando_caracas": ahora.astimezone(CARACAS).isoformat(),
    }
    try:
        await db[COLECCION].insert_one(linea)
        return linea["_id"]
    except Exception as e:
        logger.error(
            "AUDITORIA PERDIDA: no se pudo asentar %s por %s sobre %s/%s: %s. "
            "Línea completa: %s",
            accion, linea["actor"].get("email"), objetivo_tipo, objetivo_id, e,
            linea)
        return None


async def asegurar_indices(db) -> None:
    """Los índices para poder buscar. Se llaman al arrancar."""
    try:
        await db[COLECCION].create_index([("cuando", -1)], name="ix_cuando")
        await db[COLECCION].create_index(
            [("actor.user_id", 1), ("cuando", -1)], name="ix_actor")
        await db[COLECCION].create_index(
            [("categoria", 1), ("cuando", -1)], name="ix_categoria")
        await db[COLECCION].create_index(
            [("accion", 1), ("cuando", -1)], name="ix_accion")
        await db[COLECCION].create_index(
            [("objetivo.id", 1), ("cuando", -1)], name="ix_objetivo")
        logger.info("Índices del libro de auditoría verificados")
    except Exception as e:
        logger.error("Índices de auditoría: %s", e)


async def buscar(db, *, categoria=None, accion=None, actor_id=None,
                 objetivo_id=None, desde=None, hasta=None,
                 limite=100, saltar=0) -> dict:
    """Lee el libro. Sólo lee: acá no se modifica nada."""
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    if accion:
        filtro["accion"] = accion
    if actor_id:
        filtro["actor.user_id"] = actor_id
    if objetivo_id:
        filtro["objetivo.id"] = objetivo_id
    if desde or hasta:
        rango = {}
        if desde:
            rango["$gte"] = desde
        if hasta:
            rango["$lte"] = hasta
        filtro["cuando"] = rango

    limite = max(1, min(int(limite), 500))
    cursor = db[COLECCION].find(filtro, {"_id": 0}).sort(
        "cuando", -1).skip(max(0, int(saltar))).limit(limite)
    lineas = [x async for x in cursor]
    for linea in lineas:
        cuando = linea.get("cuando")
        if isinstance(cuando, datetime):
            # Mongo devuelve las fechas SIN zona: se guardan como UTC y
            # vuelven naive. Un isoformat sin offset es ambiguo —quien lo lea
            # puede tomarlo por hora local— así que se le vuelve a poner el
            # UTC que siempre tuvo antes de emitirlo.
            if cuando.tzinfo is None:
                cuando = cuando.replace(tzinfo=timezone.utc)
            linea["cuando"] = cuando.isoformat()
    return {
        "lineas": lineas,
        "total": await db[COLECCION].count_documents(filtro),
        "limite": limite,
        "saltar": int(saltar),
    }
