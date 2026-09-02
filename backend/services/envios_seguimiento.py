"""
services/envios_seguimiento.py — El seguimiento publico y los avisos.

DOS COSAS QUE PARECEN UNA
    El SEGUIMIENTO es lo que ve cualquiera con el link: donde esta el paquete.
    Los AVISOS son lo que le llega al usuario cuando algo cambia. Comparten los
    estados y nada mas.

EL SEGUIMIENTO ES PUBLICO Y POR ESO NO LLEVA UN SOLO DATO PERSONAL
    El link se comparte por WhatsApp: al destinatario, a la familia, al grupo. Va
    a terminar en manos que no son la del usuario, y hay que disenarlo asumiendo
    eso desde el principio y no despues del primer incidente.

    Lo que NO sale: el nombre y el telefono del destinatario, el documento, la
    direccion, el `user_id`, el `envio_id`, los montos, y a nombre de quien esta
    rotulada la caja. Nada de eso hace falta para contestar "donde esta mi
    paquete", que es la unica pregunta que esta pantalla responde.

    Lo que si sale: el numero visible, en que estado esta, la ciudad de destino y
    la linea de tiempo. Con eso alcanza, y con eso no se puede identificar a
    nadie.

    Hay un test que toma un envio completo, arma el payload publico y busca cada
    dato sensible adentro. Es la unica forma de que esto siga siendo cierto
    dentro de un ano: una clave nueva en el documento del envio no puede
    aparecer sola en la respuesta publica.

EL TOKEN ES UNA CREDENCIAL, NO UN IDENTIFICADOR
    128 bits de `secrets`, opaco y sin relacion con el numero de envio. Con un
    correlativo, cualquiera que reciba un link puede sumarle uno y ver el paquete
    de otro.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Lo que se le dice al publico de cada estado. Es texto de cara al usuario y no
# el nombre interno: "recibido_pacaraima" no le dice nada a nadie.
PUBLICO = {
    "cotizado": ("Cotizado", "Todavía no se confirmó el envío."),
    "esperando_postagem": (
        "Esperando el despacho",
        "El paquete todavía no se despachó en Brasil."),
    "en_transito_origen": (
        "En camino a la frontera",
        "Despachado en Brasil, viajando hacia Pacaraima."),
    "disponible_retiro": (
        "Esperando en Pacaraima",
        "Llegó a la agencia y nuestro equipo lo va a retirar."),
    "recibido_pacaraima": (
        "Retirado por nuestro equipo",
        "Ya está con nosotros en Pacaraima."),
    "repesado": ("Pesado y listo", "Se pesó y el precio quedó cerrado."),
    "pago_pendiente": (
        "Esperando un pago",
        "Hay un cobro pendiente. El paquete espera hasta que se salde."),
    "en_transito_int": (
        "En camino a Santa Elena",
        "Viajando hacia la oficina del transportista."),
    "entregado_transportista": (
        "Entregado al transportista",
        "Nuestro servicio terminó. El tramo final lo hace el transportista."),
    "retenido": ("Retenido", "El paquete está observado. Estamos resolviéndolo."),
    "devuelto": ("Devuelto", "El paquete volvió al remitente."),
    "cancelado": ("Cancelado", "El envío se canceló."),
    "siniestrado": ("Con un problema", "Estamos gestionando una incidencia."),
}

# Los estados por los que se avisa. No es "todos": un aviso por cada movimiento
# interno entrena al usuario a ignorarlos, y despues el unico que importaba
# —tenes un cobro pendiente— llega a alguien que ya no los lee.
AVISOS = {
    "disponible_retiro": (
        "Tu paquete llegó a Pacaraima",
        "Está en la agencia y nuestro equipo lo va a retirar. Te avisamos cuando "
        "lo tengamos."),
    "recibido_pacaraima": (
        "Ya tenemos tu paquete",
        "Lo retiramos del mostrador. Ahora lo pesamos y cerramos el precio."),
    "pago_pendiente": (
        "Tu paquete espera un pago",
        "Quedó un cobro pendiente del servicio. El paquete espera con nosotros en "
        "Pacaraima hasta que se salde."),
    "en_transito_int": (
        "Tu paquete va hacia Santa Elena",
        "Todo al día. Va camino a la oficina del transportista."),
    "entregado_transportista": (
        "Entregamos tu paquete",
        "Ya está en la oficina del transportista. Desde acá el tramo final lo "
        "hacen ellos, con la guía que te dejamos en el envío."),
    "devuelto": (
        "Tu paquete volvió al remitente",
        "No se pudo completar el traslado. Escribinos y lo vemos."),
    "siniestrado": (
        "Hay un problema con tu paquete",
        "Estamos gestionando una incidencia. Te contamos apenas sepamos más."),
}


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


# ─── El seguimiento público ───────────────────────────────────────────────

async def seguir(token: str, db=None) -> dict | None:
    """Lo que ve cualquiera con el link. Sin un solo dato personal.

    Devuelve None si el token no existe. NO distingue "no existe" de "mal
    formado": las dos cosas son la misma respuesta, porque distinguirlas
    convierte la ruta en un oráculo para adivinar tokens.
    """
    limpio = (token or "").strip()
    if not (32 <= len(limpio) <= 64) or not limpio.isalnum():
        return None
    try:
        base = await _db(db)
        envio = await base.envios.find_one(
            {"tracking_token": limpio},
            # La proyección es una LISTA BLANCA, no una exclusión. Con una
            # exclusión, cada campo nuevo del envío entra solo a la respuesta
            # pública el día que alguien lo agregue.
            # `envio_id` entra porque la bitacora se busca por el, y NO sale en
            # la respuesta: el payload se arma campo por campo mas abajo.
            {"_id": 0, "envio_id": 1, "display_id": 1, "estado": 1,
             "destino.ciudad": 1, "destino.estado_ve": 1, "created_at": 1,
             "entrega.guia": 1},
        )
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el seguimiento: {e}")
        return None
    if not envio:
        return None

    titulo, detalle = PUBLICO.get(envio.get("estado"), ("En proceso", ""))
    return {
        "display_id": envio.get("display_id"),
        "estado": envio.get("estado"),
        "estado_titulo": titulo,
        "estado_detalle": detalle,
        "destino": {"ciudad": (envio.get("destino") or {}).get("ciudad"),
                    "estado": (envio.get("destino") or {}).get("estado_ve")},
        "guia_transportista": (envio.get("entrega") or {}).get("guia"),
        "creado_at": envio.get("created_at"),
        "timeline": await _timeline(envio, db=db),
    }


async def _timeline(envio: dict, db=None) -> list[dict]:
    """La línea de tiempo, del primer movimiento al último.

    Sale de la bitácora y no del estado actual: el estado dice dónde está, la
    bitácora dice cómo llegó. Y se recorta a lo público — el detalle de cada
    evento tiene códigos de objeto, montos y quién lo movió.
    """
    from services.envios_eventos import historial
    try:
        eventos = await historial(envio.get("envio_id") or "", db=db)
    except Exception:                                         # pragma: no cover
        return []
    salida = []
    for evento in eventos or []:
        titulo, detalle = PUBLICO.get(evento.get("a_estado"), (None, None))
        if titulo is None:
            continue
        salida.append({"estado": evento.get("a_estado"), "titulo": titulo,
                       "detalle": detalle, "at": evento.get("created_at")})
    return salida


# ─── Los avisos ───────────────────────────────────────────────────────────

async def avisar(envio: dict, estado: str, db=None) -> str | None:
    """Le avisa al usuario que su envío se movió. Nunca lanza.

    Un aviso que falla no puede deshacer el movimiento que lo produjo: el
    paquete ya está donde está. Se registra y se sigue.
    """
    plantilla = AVISOS.get(estado)
    if not plantilla:
        return None
    titulo, cuerpo = plantilla
    user_id = (envio or {}).get("user_id")
    if not user_id:
        return None

    numero = (envio or {}).get("display_id")
    envio_id = (envio or {}).get("envio_id")

    # CUANTO. Un aviso que dice «quedó un cobro pendiente» y no dice el número
    # obliga a entrar a averiguarlo, y el que no entra no paga. Solo se calcula
    # donde significa algo: en los demás estados no hay ninguna deuda que contar.
    deuda = _deuda_pendiente(envio) if estado == "pago_pendiente" else None
    if deuda:
        cuerpo = f"{cuerpo} Son {deuda} {(envio or {}).get('moneda') or 'RIS'}."

    try:
        from services.notifications import create_notification
        return await create_notification(
            user_id=user_id,
            title=titulo,
            message=f"{cuerpo}" + (f" (envío {numero})" if numero else ""),
            notification_type="envio",
            # El token NO va en el aviso. Un aviso se reenvía y se captura de
            # pantalla; el link de seguimiento es una credencial y vive en la
            # pantalla del envío, detrás de la sesión.
            data={"envio_id": envio_id, "display_id": numero,
                  "estado": estado,
                  **({"a_pagar_ris": deuda} if deuda else {}),
                  # A DONDE LLEVA. Hasta ahora el aviso era un callejón sin
                  # salida: la campana abría un cartel que decía «tu paquete
                  # espera un pago» y no tenía ni un botón. El usuario tenía que
                  # adivinar que la pantalla del envío existe y cómo llegar.
                  #
                  # La acción viaja EN el aviso y no en un `switch` de la
                  # pantalla de notificaciones: ese switch es de otro módulo, no
                  # conoce los envíos, y cada módulo nuevo tendría que ir a
                  # editarlo. La pantalla valida que el destino sea interno.
                  **({"accion": {
                      "label": "Pagar ahora" if deuda else "Ver el envío",
                      "path": f"/envios/{envio_id}"}} if envio_id else {})},
        )
    except Exception as e:
        logger.error(f"envios: no se pudo avisar el cambio a {estado}: {e}")
        return None


def _deuda_pendiente(envio: dict) -> str | None:
    """Lo que falta pagar, como texto listo para un mensaje. None si no hay.

    Nunca lanza: esto corre dentro de `avisar`, y un aviso que revienta por no
    poder sumar un número no puede tumbar el movimiento del paquete.
    """
    try:
        from services.envios_estados import partidas_impagas
        from services.money import quantize_money, to_decimal
        cobros = (envio or {}).get("cobros") or {}
        total = to_decimal(0)
        for partida in partidas_impagas(envio):
            total += to_decimal((cobros.get(partida) or {}).get("monto_ris"))
        if not total.is_finite() or total <= 0:
            return None
        return str(quantize_money(total))
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo calcular la deuda para el aviso: {e}")
        return None


def se_avisa(estado: str) -> bool:
    """Si ese estado le importa al usuario.

    Existe como función y no como un `in` suelto para que la decisión de avisar
    o no esté en un solo lugar: un aviso por cada movimiento interno entrena al
    usuario a ignorarlos, y después el único que importaba llega a alguien que ya
    no los lee.
    """
    return estado in AVISOS
