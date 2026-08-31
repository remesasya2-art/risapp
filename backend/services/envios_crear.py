"""
services/envios_crear.py — Confirmar una cotizacion. NO cobra.

QUE CAMBIO Y POR QUE IMPORTA
    En el diseno original, confirmar era cobrar: se debitaba el saldo y si no
    alcanzaba, el envio no se creaba. Ya no. El usuario paga el tramo 1
    directamente al transportista de origen, y RIS App recien cobra cuando puede
    verificar contra una medicion ajena: el peso que figura en el comprobante de
    despacho.

    Eso cambia el manejo del error de raiz. Antes, sin saldo, no habia envio y un
    402 era la respuesta correcta. Ahora el paquete existe y esta viajando:
    quedarse sin saldo no cancela nada, solo deja una partida pendiente. El unico
    lugar donde la falta de saldo detiene algo es la salida de Pacaraima.

    Por eso este archivo no importa nada que mueva plata, y hay un test que lo
    verifica leyendo el fuente.

LAS DOS ACEPTACIONES SON DOS
    Una para el contenido —la lista de prohibidos— y otra, aparte, para el precio
    estimado. Juntarlas en un solo checkbox esconde la del precio detras de la
    del contenido, que es justo lo que no se quiere el dia que haya que defender
    el cobro de un ajuste: "aceptaste que podia variar" no se sostiene si esa
    frase estaba adentro de un checkbox que decia otra cosa.

    Ninguna viene tildada por defecto. Eso lo garantiza la pantalla; lo que
    garantiza este modulo es que sin las dos no hay envio.

IDEMPOTENTE
    Un doble clic no puede partir el flujo en dos envios. Se usa el mismo
    `claim_idempotency` que ya usa `/reais/send`, con la misma degradacion: si la
    idempotencia falla, se deja pasar. Es preferible arriesgar un duplicado raro
    que impedir una operacion real — y aca el duplicado ni siquiera cuesta plata.
"""

import logging
import secrets
from datetime import datetime, timezone

from services.envios_cotizador import esta_vencida
from services.envios_estados import puede_transicionar
from services.envios_policy import limites_efectivos, validar_paquete

logger = logging.getLogger(__name__)

# La accion INCLUYE el envio, no es una constante. `claim_idempotency` reclama
# por (user_id, action, key), asi que con una accion fija dos confirmaciones de
# envios DISTINTOS con la misma clave colisionan: la segunda devuelve el
# resultado de la primera —otro envio_id, otro display_id, otro token— con un
# 200 y `success: true`.
#
# No es un cliente malicioso: es un `useRef(uuid())` creado al montar la app, o
# una clave por sesion en vez de por envio. Y el dano no queda ahi. El segundo
# envio se queda en `cotizado`, el TTL parcial lo borra a las 48 h, y el usuario
# —que recibio un 200— despacha esa caja y despues carga el comprobante contra
# el display_id que le dieron, que es el del PRIMER envio. Ahi si se mueve plata
# mal: el cobro inicial de uno se calcula con el peso del despacho del otro.
def accion_idempotencia(envio_id: str) -> str:
    return f"envio_crear:{envio_id}"


ACCION_IDEMPOTENCIA = "envio_crear"      # el prefijo, para poder buscar en el log
ESTADO_DESTINO = "esperando_postagem"

# El contador de la numeracion visible. Es el mismo patron que
# `utils/helpers.get_next_withdrawal_id`, con su propia clave: los envios y los
# retiros no comparten numeracion.
CONTADOR_DISPLAY = "envio_display_id"


class NoSePuedeCrear(Exception):
    """Un motivo que el usuario puede leer, con su codigo HTTP."""

    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def nuevo_tracking_token() -> str:
    """El token del seguimiento publico. Opaco y aleatorio, NUNCA secuencial.

    Con un numero correlativo, cualquiera que reciba un link de seguimiento puede
    sumarle uno y ver el paquete de otra persona: a donde va, a nombre de quien y
    con que telefono. `secrets` y no `uuid4` porque esto es una credencial de
    lectura, no un identificador.
    """
    return secrets.token_hex(16)


async def siguiente_display_id(db=None) -> str | None:
    """El numero visible, con el contador atomico de Mongo.

    Nunca lanza: si el contador falla, el envio se crea igual y se queda sin
    numero visible. Un envio sin `display_id` es incomodo de nombrar por
    telefono; un envio que no se creo porque un contador fallo es un usuario que
    no puede despachar.
    """
    try:
        base = await _db(db)
        doc = await base.counters.find_one_and_update(
            {"_id": CONTADOR_DISPLAY}, {"$inc": {"seq": 1}},
            upsert=True, return_document=True)
        return f"E{int(doc['seq']):06d}"
    except Exception as e:
        logger.error(f"envios: no se pudo asignar el display_id: {e}")
        return None


# ─── Confirmar ────────────────────────────────────────────────────────────

async def crear(usuario, envio_id: str, declaracion: dict, idempotency_key: str = None,
                db=None, ahora=None, ip: str = None) -> dict:
    """Confirma la cotizacion y entrega los datos de despacho. Lanza NoSePuedeCrear.

    NO mueve un centavo y no toca ningun saldo.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    declaracion = declaracion or {}

    envio = await _envio_del_usuario(base, usuario, envio_id)

    # 1. Las dos aceptaciones, antes que nada de lo que dependa del sistema: es
    #    lo unico que el usuario puede arreglar sin ayuda.
    faltan = [etiqueta for clave, etiqueta in (
        ("contenido_aceptado", "que el contenido no está en la lista de prohibidos"),
        ("estimado_aceptado", "que el precio es estimado y puede cambiar al repesar"),
    ) if declaracion.get(clave) is not True]
    if faltan:
        raise NoSePuedeCrear(
            "Falta aceptar " + " y ".join(faltan) + ". Son dos confirmaciones "
            "separadas y las dos hacen falta.")

    # 1b. La versión de términos que vio la pantalla tiene que ser la que el
    #     envío congeló. Si no, el usuario aceptó un texto distinto del que el
    #     envío dice que aceptó — y "aceptaste las condiciones" deja de
    #     sostenerse justo cuando hace falta que se sostenga.
    congelada = (envio.get("cotizacion") or {}).get("terminos_version")
    mostrada = declaracion.get("terminos_version")
    if mostrada and congelada and str(mostrada) != str(congelada):
        raise NoSePuedeCrear(
            "Las condiciones cambiaron mientras completabas el formulario. Recargá la "
            "pantalla y volvé a leerlas antes de confirmar.", http=409)

    # 2. El estado. Un envío ya confirmado no se vuelve a confirmar.
    if envio.get("estado") != "cotizado":
        if envio.get("estado") == ESTADO_DESTINO:
            # Ya estaba confirmado: se devuelve lo mismo en vez de un error. Un
            # reintento de red no puede parecer un fallo cuando salió bien.
            #
            # Pasa por `_numerar` igual, porque la transición y la numeración son
            # dos escrituras: entre una y otra hay una ventana en la que el
            # documento ya está confirmado y todavía no tiene número. Sin esto, el
            # segundo clic devolvía `display_id: null` con `success: true`, y la
            # pantalla se quedaba sin número de envío ni link de seguimiento.
            return _resultado(await _numerar(base, envio, envio_id))
        raise NoSePuedeCrear(
            "Este envío ya no se puede confirmar: su estado cambió. Abrilo para ver "
            "en qué punto está.", http=409)

    # `puede_transicionar` devuelve el MENSAJE del problema, o None si se puede.
    # Leerlo como un booleano invierte la condición y rechaza justo las
    # transiciones válidas — que es lo que hacía esta línea hasta que el primer
    # test la corrió.
    problema = puede_transicionar("cotizado", ESTADO_DESTINO, "user")
    if problema:
        raise NoSePuedeCrear(problema, http=409)

    # 3. La cotización tiene que estar vigente. Confirmar dentro de seis meses un
    #    precio de hoy es cobrarle al usuario un número que ya no existe.
    if esta_vencida(envio, ahora=ahora):
        raise NoSePuedeCrear(
            "La cotización venció. Pedí una nueva: los precios y los límites pueden "
            "haber cambiado.", http=409)

    # 4. Los límites, otra vez. Entre cotizar y confirmar pueden haber cambiado
    #    —un transportista que baja su máximo, otro que entra al catálogo— y
    #    despachar algo que el mostrador va a rechazar es peor que un 409 acá.
    await _limites_siguen_dando(base, envio)

    # 5. Idempotencia. Recién acá, con todo validado: reclamar antes convierte un
    #    400 por un checkbox sin tildar en una clave quemada que devuelve el
    #    mismo error para siempre.
    from services.idempotency import claim_idempotency, store_idempotency_result
    accion = accion_idempotencia(envio_id)
    es_nueva, previo = await claim_idempotency(
        getattr(usuario, "user_id", None), accion, idempotency_key)
    if not es_nueva:
        if previo and previo.get("result"):
            return previo["result"]
        raise NoSePuedeCrear(
            "Esta confirmación ya se está procesando. Esperá un momento.", http=409)

    # 6. El envío pasa a esperando_postagem, con su numeración y su token.
    parche = {
        "estado": ESTADO_DESTINO,
        "confirmado_at": ahora,
        "declaracion": {
            "contenido_aceptado": True,
            "estimado_aceptado": True,
            "terminos_version": (envio.get("cotizacion") or {}).get("terminos_version"),
            "at": ahora,
            "ip": ip,
        },
    }
    try:
        actualizado = await base.envios.find_one_and_update(
            # El estado va EN EL FILTRO y no solo en el chequeo de arriba: entre
            # que se leyó y que se escribe, otra petición pudo confirmar el mismo
            # envío. Es la misma guardia atómica que usa el débito de saldo.
            {"envio_id": envio_id, "user_id": getattr(usuario, "user_id", None),
             "estado": "cotizado"},
            {"$set": parche}, return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo confirmar {envio_id}: {e}")
        # La clave se LIBERA. Si no, un timeout de Mongo la deja en
        # `processing` para siempre —no hay TTL en `idempotency_keys` ni nada que
        # barra las colgadas— y el reintento que el propio mensaje invita a hacer
        # devuelve 409 hasta que el envío vence. Nada ocurrió: la clave no tiene
        # por qué quedar reclamada.
        await _liberar(usuario, accion, idempotency_key)
        raise NoSePuedeCrear(
            "No se pudo confirmar el envío. Probá de nuevo en un momento.",
            http=503) from e

    if actualizado is None:
        # Otra petición ganó la carrera. No es un error del usuario.
        actual = await _envio_del_usuario(base, usuario, envio_id)
        if actual.get("estado") == ESTADO_DESTINO:
            return _resultado(await _numerar(base, actual, envio_id))
        raise NoSePuedeCrear(
            "Este envío ya no se puede confirmar: su estado cambió.", http=409)

    # 7. La numeración y el token, DESPUÉS de haber ganado la carrera. Al revés
    #    —reservando el número antes del update— la petición que pierde igual
    #    consume un número del contador, y la numeración visible queda con
    #    huecos que nadie sabe explicar. El que gana la transición es el único
    #    que tiene derecho a un número.
    actualizado = await _numerar(base, actualizado, envio_id)

    from services import envios_eventos
    await envios_eventos.registrar(
        actualizado, "cotizado", ESTADO_DESTINO, "user",
        actor_id=getattr(usuario, "user_id", None),
        detalle={"terminos_version": parche["declaracion"]["terminos_version"]},
        db=base, ahora=ahora)

    resultado = _resultado(actualizado)
    await store_idempotency_result(
        getattr(usuario, "user_id", None), accion, idempotency_key, resultado)
    return resultado


async def _liberar(usuario, accion: str, key: str) -> None:
    """Suelta una clave reclamada cuya operación no llegó a ocurrir. Nunca lanza."""
    if not key:
        return
    try:
        from database import db as real
        await real["idempotency_keys"].delete_one(
            {"user_id": getattr(usuario, "user_id", None), "action": accion,
             "key": key, "result": None})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo liberar la clave {accion}/{key}: {e}")


async def _numerar(base, envio: dict, envio_id: str) -> dict:
    """Le pone número visible y token de seguimiento. Nunca lanza.

    Un fallo acá deja el envío confirmado y sin número, que es incómodo de
    nombrar por teléfono y nada más. Deshacer la confirmación por eso sería
    cambiar un problema cosmético por uno real.
    """
    parche = {}
    if not envio.get("display_id"):
        numero = await siguiente_display_id(base)
        if numero:
            parche["display_id"] = numero
    if not envio.get("tracking_token"):
        parche["tracking_token"] = nuevo_tracking_token()
    if not parche:
        return envio
    try:
        await base.envios.update_one({"envio_id": envio_id}, {"$set": parche})
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo numerar {envio_id}: {e}")
        return envio
    return {**envio, **parche}


async def _envio_del_usuario(base, usuario, envio_id: str) -> dict:
    """El envío, si es de quien lo pide.

    El mismo 404 para "no existe" y para "es de otro": distinguirlos convierte la
    ruta en un oráculo que confirma qué identificadores existen.
    """
    user_id = getattr(usuario, "user_id", None)
    try:
        envio = await base.envios.find_one(
            {"envio_id": envio_id, "user_id": user_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        raise NoSePuedeCrear(
            "No se pudo leer el envío. Probá de nuevo en un momento.", http=503) from e
    if not envio:
        raise NoSePuedeCrear("No encontramos ese envío.", http=404)
    return envio


TIMEOUT_RELECTURA_S = 6.0


async def _limites_siguen_dando(base, envio: dict) -> None:
    """Que lo que se cotizó siga siendo despachable. Nunca es un 500.

    Revalida DOS cosas, y las dos por la misma razón: despachar algo que el
    mostrador va a rechazar es peor que un 409 acá, porque para cuando se
    descubre el usuario ya pagó el tramo 1 de su bolsillo.

      - Las medidas contra la intersección de límites.
      - Que el destino siga existiendo: el transportista activo y de rol destino,
        y la agencia recibiendo. Sin esto, dar de baja una agencia dejaba
        confirmar igual —y peor, `limites_efectivos` descarta las fichas
        inactivas, así que dar de baja un transportista SACABA sus límites de la
        intersección y la revalidación se volvía más laxa justo cuando algo se
        había roto.
    """
    from services.envios_catalogo import tarifa_vigente
    from services.referencias import _activo, _catalogo

    declarado = (envio.get("paquete") or {}).get("declarado") or {}
    try:
        # En paralelo y con tope, como el cotizador. Tres lecturas en serie sin
        # cota son, con un failover, tres veces el server-selection timeout
        # reteniendo un worker.
        import asyncio
        tarifa, (brasil, br_ok), (venezuela, ve_ok) = await asyncio.wait_for(
            asyncio.gather(tarifa_vigente(db=base), _catalogo("brasil", db=base),
                           _catalogo("venezuela", db=base)),
            timeout=TIMEOUT_RELECTURA_S)
    except asyncio.TimeoutError:
        logger.warning("envios: la relectura de límites no llegó a tiempo")
        return
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudieron releer los límites: {e}")
        return

    await _destino_sigue_recibiendo(base, envio, venezuela, ve_ok)
    if not (br_ok and ve_ok):
        # No se pudo leer un rol. NO se afloja el chequeo ni se bloquea la
        # confirmación: el paquete ya fue validado al cotizar contra la
        # intersección completa, y bloquear acá por un fallo nuestro le impide
        # despachar a alguien que hizo todo bien.
        logger.warning("envios: catálogo incompleto al confirmar; no se revalidan límites")
        return

    limites = limites_efectivos((brasil or []) + (venezuela or []),
                                (tarifa or {}).get("limites_propios"))
    problema = validar_paquete(
        declarado.get("peso_kg"), declarado.get("largo_cm"),
        declarado.get("ancho_cm"), declarado.get("alto_cm"),
        declarado.get("valor_declarado"), limites)
    if problema:
        raise NoSePuedeCrear(
            f"{problema} Los límites cambiaron desde que cotizaste: pedí una "
            f"cotización nueva.", http=409)


async def _destino_sigue_recibiendo(base, envio: dict, venezuela, ve_ok) -> None:
    from services.referencias import _activo

    if not ve_ok:
        return                    # no se pudo leer; no se castiga al usuario
    destino = envio.get("destino") or {}
    transportista_id = destino.get("transportista_id")
    if transportista_id and not any(
            t.get("transportista_id") == transportista_id for t in (venezuela or [])):
        raise NoSePuedeCrear(
            "El transportista de destino que elegiste ya no está disponible. Pedí una "
            "cotización nueva y elegí otro.", http=409)

    codigo = destino.get("agencia_codigo")
    if not (transportista_id and codigo):
        return
    try:
        agencia = await base.agencias.find_one(
            {"transportista_id": transportista_id, "codigo": codigo}, {"_id": 0})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo releer la agencia {codigo}: {e}")
        return
    if not agencia or not _activo({"activo": agencia.get("activa")}):
        raise NoSePuedeCrear(
            "La agencia de destino que elegiste ya no está recibiendo paquetes. Pedí "
            "una cotización nueva y elegí otra.", http=409)


def _resultado(envio: dict) -> dict:
    """Lo que la pantalla necesita para que el usuario vaya a despachar.

    Trae el bloque de despacho CONGELADO del envío, no el vigente: entre cotizar
    y confirmar pueden haber cambiado el turno de la nómina, y la etiqueta tiene
    que decir lo mismo que dijo cuando el usuario la leyó.
    """
    cotizacion = envio.get("cotizacion") or {}
    despacho = envio.get("destino_brasil") or {}
    return {
        "success": True,
        "envio_id": envio.get("envio_id"),
        "display_id": envio.get("display_id"),
        "tracking_token": envio.get("tracking_token"),
        "estado": envio.get("estado"),
        "es_estimado": True,
        "total_estimado_ris": cotizacion.get("total_estimado_ris"),
        "moneda": cotizacion.get("moneda") or "RIS",
        # NO se cobró nada. Se dice explícitamente porque el usuario acaba de
        # apretar un botón que en cualquier otra app de este rubro le habría
        # sacado plata.
        "cobrado_ahora_ris": "0.00",
        "retiro": {k: v for k, v in despacho.items()
                   if k not in ("retirador_id", "retirador_motivo", "congelado_at")},
        "proximo_paso": (
            "Despachá el paquete a esa dirección y después cargá el comprobante acá. "
            "Recién con el comprobante te vamos a cobrar el servicio, calculado sobre "
            "el peso que midió el transportista."
        ),
    }
