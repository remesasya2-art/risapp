"""
services/envios_entrega_final.py — Lo que pasa DESPUES de que terminamos.

EL PROBLEMA QUE RESUELVE
    `entregado_transportista` es un estado TERMINAL: nuestro servicio termina
    cuando la caja queda en la oficina del transportista de destino. Pero el
    usuario no considera que su envio termino ahi — para el termina cuando su
    familiar tiene la caja en la mano, y eso pasa dias despues, en un mostrador
    al que no tenemos acceso.

    El equipo de RIS App SI lo averigua: entra a la pagina del transportista,
    ve que la guia figura retirada y por quien. Hasta ahora esa informacion se
    quedaba en la cabeza de quien la miro. Aca se registra y se le avisa.

ESTO NO ES UN ESTADO NUEVO, Y ES A PROPOSITO
    Seria facil agregar `retirado_destino` a `TRANSICIONES` y mover el envio.
    Estaria mal por dos motivos:

    1. **No lo movimos nosotros.** Un estado del envio dice donde lo pusimos.
       Esto es una OBSERVACION de tercero: alguien de RIS App leyo una pagina
       web. Si manana el transportista corrige su propia pagina, lo que cambia
       es lo que observamos, no lo que hicimos.

    2. **Sacar un estado de `TERMINALES` toca todo.** `es_terminal` gobierna
       desvios, cobros y la pantalla del usuario. Un cambio ahi por una linea
       informativa es desproporcionado y arriesga plata.

    Asi que el envio se queda en `entregado_transportista` y esto vive en un
    bloque aparte, `entrega_final`. La bitacora recibe su linea —con un
    `a_estado` propio que NO existe en la maquina de estados, justamente para
    que nadie lo confunda con una transicion— y el usuario ve un paso mas en su
    seguimiento.

SE PUEDE CORREGIR
    El nombre lo tipea una persona leyendo la web de otra empresa. Se va a
    equivocar. Registrar de nuevo pisa el bloque y deja OTRA linea en la
    bitacora: la correccion es visible, no silenciosa.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# El `a_estado` de la linea de bitacora. NO esta en `TRANSICIONES` ni en
# `TERMINALES`: no es un estado, es una anotacion. Vive como constante para que
# el que la busque la encuentre en un solo lugar.
MARCA_RETIRO = "retiro_final"

# Solo se registra sobre un envio que ya salio de nuestras manos. Anotar que
# «lo retiraron en la oficina» sobre una caja que sigue en Pacaraima no es un
# dato incompleto: es un dato falso, y viaja al usuario como aviso.
ESTADO_EXIGIDO = "entregado_transportista"

LIMITES = {"retirado_por": 120, "documento": 40, "nota": 500, "fuente": 60}


class RetiroInvalido(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def _texto(valor, campo: str) -> str:
    return str(valor or "").strip()[:LIMITES[campo]]


async def registrar(operador, envio_id: str, *, retirado_por: str,
                    retirado_at=None, documento: str = "", nota: str = "",
                    fuente: str = "", db=None, ahora=None) -> dict:
    """Anota que el destinatario retiro la caja en la oficina, y le avisa.

    `retirado_por` es obligatorio: sin el nombre, esto no dice nada que el
    usuario no supiera ya —que la caja llego a la oficina— y el aviso seria
    ruido. Con el nombre responde la pregunta que la gente hace por telefono:
    «¿quien la retiro?».
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)

    nombre = _texto(retirado_por, "retirado_por")
    if len(nombre) < 3:
        raise RetiroInvalido(
            "Poné el nombre de quien retiró el paquete. Es lo que el usuario "
            "va a leer, y sin eso el aviso no le dice nada nuevo.")

    try:
        envio = await base.envios.find_one({"envio_id": envio_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id} para el retiro: {e}")
        raise RetiroInvalido(
            "No se pudo leer el envío. Reintentá en un momento.", http=503) from e
    if not envio:
        raise RetiroInvalido("Ese envío no existe.", http=404)

    if envio.get("estado") != ESTADO_EXIGIDO:
        raise RetiroInvalido(
            "Este envío todavía no está entregado al transportista, así que no "
            "puede estar retirado en su oficina. Registralo cuando lo entreguemos.",
            http=409)

    bloque = {
        "retirado_por": nombre,
        "retirado_at": _fecha(retirado_at) or ahora,
        "documento": _texto(documento, "documento") or None,
        "nota": _texto(nota, "nota") or None,
        # De donde salio el dato. Dentro de seis meses, «lo vi en la web de MRW»
        # y «me lo dijo el destinatario por telefono» no valen lo mismo.
        "fuente": _texto(fuente, "fuente") or None,
        "registrado_por": getattr(operador, "user_id", None),
        "registrado_at": ahora,
    }

    ya_estaba = bool((envio.get("entrega_final") or {}).get("retirado_por"))

    try:
        resultado = await base.envios.update_one(
            {"envio_id": envio_id, "estado": ESTADO_EXIGIDO},
            {"$set": {"entrega_final": bloque}})
    except Exception as e:
        logger.error(f"envios: no se pudo guardar el retiro de {envio_id}: {e}")
        raise RetiroInvalido(
            "No se pudo guardar. Reintentá en un momento.", http=503) from e
    if getattr(resultado, "matched_count", 1) == 0:
        # El estado va en el FILTRO y no solo en el chequeo de arriba: entre que
        # se leyo y que se escribe, otro pudo mover el envio.
        raise RetiroInvalido(
            "El envío cambió mientras trabajabas. Recargá y volvé a intentar.",
            http=409)

    # La bitacora. Una linea POR REGISTRO, no una sola pisada: si alguien
    # corrige el nombre, la correccion tiene que verse.
    try:
        from services import envios_eventos
        await envios_eventos.registrar(
            envio, ESTADO_EXIGIDO, MARCA_RETIRO, "admin",
            actor_id=getattr(operador, "user_id", None),
            detalle={"retirado_por": nombre,
                     "fuente": bloque["fuente"],
                     "correccion": ya_estaba},
            db=base, ahora=ahora)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo registrar el evento de retiro: {e}")

    # Y el aviso. Va al final y no puede deshacer nada: el dato ya esta guardado,
    # y un aviso que falla no lo desguarda.
    await _avisar(envio, nombre, ya_estaba, db=base)

    return {"ok": True, "envio_id": envio_id, "entrega_final": bloque,
            "correccion": ya_estaba}


def _fecha(valor):
    """La fecha que tipeo el operador, o None. Nunca lanza.

    Llega como `YYYY-MM-DD` del input del panel. Una fecha ilegible no puede
    frenar el registro: se cae al momento del registro, que es peor dato pero
    dato al fin, y el operador lo ve en pantalla y lo corrige.
    """
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not valor:
        return None
    try:
        limpio = str(valor).strip().replace("Z", "+00:00")
        fecha = datetime.fromisoformat(limpio)
        return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning(f"envios: fecha de retiro ilegible: {valor!r}")
        return None


async def _avisar(envio: dict, nombre: str, correccion: bool, db=None) -> None:
    """El aviso al usuario. Nunca lanza."""
    user_id = (envio or {}).get("user_id")
    if not user_id:
        return
    numero = (envio or {}).get("display_id")
    try:
        from services.notifications import create_notification
        await create_notification(
            user_id=user_id,
            title=("Corregimos quién retiró tu paquete" if correccion
                   else "Retiraron tu paquete"),
            message=(f"{nombre} lo retiró en la oficina del transportista."
                     + (f" (envío {numero})" if numero else "")
                     + (" Si esto no es correcto, escribinos." if not correccion else "")),
            notification_type="envio",
            data={"envio_id": envio.get("envio_id"), "display_id": numero,
                  "estado": ESTADO_EXIGIDO, "retirado_por": nombre,
                  **({"accion": {"label": "Ver el envío",
                                 "path": f"/envios/{envio.get('envio_id')}"}}
                     if envio.get("envio_id") else {})},
        )
    except Exception as e:
        logger.error(f"envios: no se pudo avisar el retiro final: {e}")


# ─── El historial que mira el equipo ──────────────────────────────────────

TOPE = 50

# Lo que se devuelve por fila. NO va el envio entero: tiene el token de
# seguimiento, los cobros y el codigo de objeto, y esta lista se pinta en una
# pantalla que se deja abierta.
_PROYECCION = {
    "_id": 0, "envio_id": 1, "display_id": 1, "user_id": 1, "estado": 1,
    "created_at": 1, "modalidad_flete": 1,
    "destino.agencia_nombre": 1, "destino.ciudad": 1, "destino.estado_ve": 1,
    "destino.destinatario.nombre": 1,
    "origen.codigo_objeto": 1,
    "entrega": 1, "entrega_final": 1,
    "cotizacion.total_final_ris": 1, "cotizacion.total_estimado_ris": 1,
}


async def historial(*, estado: str = None, buscar: str = None, db=None,
                    limite: int = TOPE, saltear: int = 0) -> dict:
    """Los envíos, del más nuevo al más viejo. Para el panel del equipo.

    La cola muestra UN estado y es para operar. Esto es para buscar: «¿qué pasó
    con el envío de la señora que llamó?».

    LA BUSQUEDA ES POR IDENTIFICADOR EXACTO, no por nombre. `display_id` y
    `origen.codigo_objeto` tienen indice unico, asi que buscar por ahi es una
    lectura. Buscar por nombre del destinatario obligaria a un regex sobre la
    coleccion entera —sin indice que lo cubra— en una pantalla que alguien deja
    abierta y refresca: el dia que haya cien mil envios, eso es un incidente.
    Si hace falta, primero el indice y despues la busqueda.
    """
    base = await _db(db)
    limite = max(1, min(int(limite or TOPE), TOPE))
    saltear = max(0, int(saltear or 0))

    filtro = {}
    texto = str(buscar or "").strip()
    if texto:
        # Un `$or` de dos campos indexados y unicos. El codigo de objeto se
        # normaliza igual que al cargarlo, para que pegarlo con espacios o
        # guiones —como sale de la web del transportista— encuentre algo.
        codigo = texto.replace(" ", "").replace("-", "").replace(".", "").upper()
        filtro = {"$or": [{"display_id": texto.upper()},
                          {"origen.codigo_objeto": codigo}]}
    elif estado:
        filtro = {"estado": estado}

    try:
        filas = await base.envios.find(filtro, _PROYECCION).sort(
            "created_at", -1).skip(saltear).to_list(limite + 1)
    except Exception as e:
        logger.error(f"envios: no se pudo leer el historial: {e}")
        return {"envios": [], "hay_mas": False, "degradado": True}

    filas = filas or []
    hay_mas = len(filas) > limite
    return {"envios": [_fila(f) for f in filas[:limite]],
            "hay_mas": hay_mas, "degradado": False}


def _fila(envio: dict) -> dict:
    destino = envio.get("destino") or {}
    cotizacion = envio.get("cotizacion") or {}
    final = envio.get("entrega_final") or {}
    return {
        "envio_id": envio.get("envio_id"),
        "display_id": envio.get("display_id"),
        "estado": envio.get("estado"),
        "created_at": envio.get("created_at"),
        "codigo_objeto": (envio.get("origen") or {}).get("codigo_objeto"),
        "destinatario": (destino.get("destinatario") or {}).get("nombre"),
        "agencia": destino.get("agencia_nombre"),
        "ciudad": destino.get("ciudad"),
        "estado_ve": destino.get("estado_ve"),
        "guia": (envio.get("entrega") or {}).get("guia"),
        "total_ris": (cotizacion.get("total_final_ris")
                      or cotizacion.get("total_estimado_ris")),
        # Lo que decide si esta fila necesita que alguien la mire: entregada al
        # transportista y todavia sin retirar.
        "retirado_por": final.get("retirado_por"),
        "retirado_at": final.get("retirado_at"),
        "espera_retiro": (envio.get("estado") == ESTADO_EXIGIDO
                          and not final.get("retirado_por")),
    }
