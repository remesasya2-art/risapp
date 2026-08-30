"""
services/envios_cobros.py — El unico lugar del modulo que mueve plata.

QUE COBRA RIS APP Y CUANDO
    Un solo servicio —retiro en Pacaraima, repesaje y traslado hasta la oficina
    del transportista en Santa Elena— en dos partidas:

      INICIAL, al verificar el comprobante de despacho. Se calcula con el peso
      que midio el transportista de origen: una medicion ajena, hecha por alguien
      sin ningun interes en que sea baja, y disponible antes de que el paquete
      cruce nada. No es el precio absoluto, pero es infinitamente mejor que
      cobrar contra lo que el usuario declaro.

      AJUSTE, al repesar con balanza propia en Pacaraima. Puede cobrar, devolver
      o no hacer nada.

    Nadie paga por adelantado. Cotizar es gratis y confirmar tampoco cobra.

QUE UNA PARTIDA QUEDE IMPAGA NO ES UN ERROR
    Es un estado del negocio. Cuando se emite el cobro inicial el paquete ya esta
    viajando y no depende de nosotros: quedarse sin saldo no puede cancelar nada
    ni devolver un 402. La partida queda `pendiente` y la unica palanca de cobro
    real —la posesion fisica del paquete— se ejerce en un solo lugar: el paquete
    no sale de Pacaraima con una partida impaga.

    Por eso `cobrar()` NUNCA lanza por falta de saldo. Devuelve como quedo.

EL ORDEN, Y POR QUE ES ASI
    1. Reclamar la idempotencia. Un doble clic no cobra dos veces.
    2. Registrar la partida como `pendiente`. ANTES de tocar el saldo: si se
       debita y despues no se puede escribir que se debito, el usuario pago y el
       envio no lo sabe — y el cobro se vuelve a emitir manana.
    3. Debitar con `find_one_and_update` condicional al saldo. Es la unica forma
       de que dos peticiones simultaneas no sobregiren: leer el saldo y despues
       restar es una carrera con la plata de alguien.
    4. Marcar la partida como pagada. SI ESTO FALLA, SE DEVUELVE EL SALDO. Es el
       mismo patron de compensacion que `/reais/send` ya usa cuando el
       beneficiario no existe; no se invento uno nuevo.
    5. Asiento en el ledger. Nunca interrumpe: el libro es un registro, no la
       fuente de verdad del saldo.
    6. Guardar el resultado idempotente.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from services.envios_estados import PARTIDAS
from services.money import ZERO, quantize_money, to_decimal, to_decimal128

logger = logging.getLogger(__name__)

# Los tipos de movimiento del libro. Se nombran por lo que son y no por el
# estado del envio: el libro se lee dentro de dos anos, cuando los estados de
# este modulo pueden llamarse de otra forma.
# `_paquete` en los dos: `pago_envio` y `refund_envio` ya significan otra cosa en
# esta aplicacion —el envio de una REMESA a VES o BRL, ver routes/admin.py— y una
# consulta del libro por movement_type mezclaria dos negocios distintos.
MOVIMIENTO_COBRO = "pago_envio_paquete"
MOVIMIENTO_REEMBOLSO = "refund_envio_paquete"

# Cuanto puede durar una reserva antes de considerarse abandonada. Es el tiempo
# de una peticion, no de una decision: si algo la dejo asi, el proceso murio.
RESERVA_VENCE_S = 120

# `pagando` es una reserva de milisegundos, no un estado del negocio: existe solo
# para que dos pagos simultaneos de la misma partida no debiten dos veces. Si
# algo la deja trabada —el proceso murio entre la reserva y el marcado— la
# resuelve `_resolver_reserva_vencida`, que mira el LIBRO para saber si el debito
# llego a ocurrir. Sin eso, una partida en `pagando` es una deuda incobrable: no
# figura pendiente, no esta pagada, y el paquete no sale de Pacaraima.
ESTADOS_PARTIDA = ("pendiente", "pagando", "pagado")
IMPAGAS = ("pendiente", "pagando")


class CobroImposible(Exception):
    """Algo impide siquiera intentar el cobro. NO es falta de saldo."""

    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def accion_idempotencia(envio_id: str, partida: str) -> str:
    """La accion INCLUYE el envio y la partida.

    Con una accion fija, una clave reusada entre dos envios devuelve el resultado
    del primero y el segundo nunca se cobra. Ya paso una vez en este modulo, en
    la confirmacion; aca costaria plata.
    """
    return f"envio_cobro:{envio_id}:{partida}"


# ─── Cobrar ───────────────────────────────────────────────────────────────

async def cobrar(envio: dict, partida: str, monto, *, db=None, ahora=None,
                 idempotency_key: str = None, base_calculo: str = None,
                 peso_base_kg=None, detalle: dict = None,
                 actor_type: str = "system", actor_id: str = None) -> dict:
    """Emite una partida y trata de cobrarla. NUNCA lanza por falta de saldo.

    Devuelve `{"partida", "estado", "monto_ris", "saldo_restante", "entry_id"}`.
    `estado` es "pagado" o "pendiente"; las dos son respuestas válidas.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)

    envio_id, user_id = _identidad(envio)
    _partida_valida(partida)
    _cobrable(envio)

    importe = quantize_money(to_decimal(monto))
    if not importe.is_finite() or importe <= ZERO:
        raise CobroImposible(
            f"El monto a cobrar es {importe}. Un cobro de cero o negativo no se emite: "
            f"si no hay nada que cobrar, la partida no existe.", http=500)

    ya = _partida_existente(envio, partida)
    if ya is not None:
        # La partida ya se emitió. Reemitirla es cobrar dos veces lo mismo.
        return _resultado(partida, ya, saldo=None)

    from services.idempotency import claim_idempotency, store_idempotency_result
    accion = accion_idempotencia(envio_id, partida)
    es_nueva, previo = await claim_idempotency(user_id, accion, idempotency_key)
    if not es_nueva:
        if previo and previo.get("result"):
            return previo["result"]
        raise CobroImposible(
            "Este cobro ya se está procesando. Esperá un momento.", http=409)

    # 2. La partida se registra PENDIENTE antes de tocar el saldo.
    partida_doc = {
        "monto_ris": str(importe),
        "base": base_calculo,
        "peso_base_kg": None if peso_base_kg is None else str(to_decimal(peso_base_kg)),
        "emitido_at": ahora,
        "estado": "pendiente",
        "pagado_at": None,
        "detalle": detalle or {},
    }
    try:
        escrito = await base.envios.find_one_and_update(
            # `$exists: False` en el filtro: si otra petición emitió la misma
            # partida entre el chequeo de arriba y esta línea, esta no escribe.
            {"envio_id": envio_id, f"cobros.{partida}": None},
            {"$set": {f"cobros.{partida}": partida_doc}}, return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo emitir el cobro {partida} de {envio_id}: {e}")
        await _liberar(user_id, accion, idempotency_key)
        raise CobroImposible(
            "No se pudo emitir el cobro. Reintentá en un momento.", http=503) from e

    if escrito is None:
        actual = await _releer(base, envio_id)
        ya = _partida_existente(actual, partida)
        if ya is not None:
            return _resultado(partida, ya, saldo=None)
        await _liberar(user_id, accion, idempotency_key)   # pragma: no cover
        raise CobroImposible(                              # pragma: no cover
            "No se pudo emitir el cobro. Reintentá en un momento.", http=503)

    resultado = await _intentar_pagar(
        base, escrito, partida, importe, ahora,
        actor_type=actor_type, actor_id=actor_id)

    await store_idempotency_result(user_id, accion, idempotency_key, resultado)
    return resultado


async def pagar_pendiente(envio: dict, partida: str, *, db=None, ahora=None,
                          actor_type: str = "user", actor_id: str = None) -> dict:
    """Salda una partida que quedó pendiente. Idempotente por el estado.

    No reclama idempotencia por clave: la guardia es el propio estado de la
    partida, que se cambia con un update condicional. Dos peticiones simultáneas
    debitan una sola vez porque solo una gana ese update.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio_id, _ = _identidad(envio)

    _partida_valida(partida)
    _cobrable(envio)

    doc = _partida_existente(envio, partida)
    if doc is None:
        raise CobroImposible("Ese cobro no existe en este envío.", http=404)
    if doc.get("estado") == "pagado":
        return _resultado(partida, doc, saldo=None)

    try:
        importe = quantize_money(to_decimal(doc.get("monto_ris")))
    except Exception:
        importe = ZERO
    if not importe.is_finite() or importe <= ZERO:
        # Un "Infinity" o un texto ilegible escrito por una migración: se
        # responde con un motivo, no con un 503 en bucle.
        raise CobroImposible(
            "El cobro pendiente no tiene un monto legible. Escribinos y lo resolvemos.",
            http=409)

    return await _intentar_pagar(base, envio, partida, importe, ahora,
                                 actor_type=actor_type, actor_id=actor_id)


async def _intentar_pagar(base, envio: dict, partida: str, importe: Decimal,
                          ahora, actor_type: str, actor_id: str) -> dict:
    """Reserva, débito, marcado y libro. La única función que saca plata."""
    envio_id, user_id = _identidad(envio)

    # 3a. RESERVAR LA PARTIDA antes de tocar el saldo. Es lo que impide el doble
    #     cobro, y no lo impide el débito: el débito es atómico contra el SALDO,
    #     no contra la deuda. Dos peticiones simultáneas de pago de la misma
    #     partida ven las dos `pendiente`, las dos encuentran saldo suficiente, y
    #     las dos debitan. El usuario paga dos veces lo mismo y solo una marca.
    #
    #     La reserva lleva `intento_id` y `reservado_at`: son lo que permite
    #     resolver una reserva abandonada sin adivinar si el débito ocurrió.
    intento_id = f"int_{uuid.uuid4().hex[:16]}"
    reservada = await _reservar(base, envio_id, partida, intento_id, ahora)
    if reservada is None:
        actual = await _releer(base, envio_id)
        doc = _partida_existente(actual, partida) or {}
        if doc.get("estado") == "pagado":
            return _resultado(partida, doc, saldo=None)
        # Está en curso: la tomó otra petición hace un instante, o quedó
        # abandonada y `_reservar` no pudo resolverla todavía.
        return _pendiente(partida, importe, motivo="en_curso")

    # El importe sale del DOCUMENTO que devolvió la reserva, no del argumento. Un
    # dict del llamador puede venir de una lectura anterior —el propio módulo
    # trata los dicts rancios como entrada esperada— y cobrar por él es cobrar un
    # monto que no es el que figura como deuda.
    persistido = quantize_money(to_decimal(
        (_partida_existente(reservada, partida) or {}).get("monto_ris")))
    if persistido.is_finite() and persistido > ZERO:
        importe = persistido

    # 3b. El débito. Condicional al saldo, en una sola operación: leer el saldo y
    #     después restar es una carrera con la plata de alguien.
    try:
        usuario = await base.users.find_one_and_update(
            {"user_id": user_id, "balance_ris": {"$gte": to_decimal128(importe)}},
            {"$inc": {"balance_ris": to_decimal128(-importe)}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: falló el débito de {importe} a {user_id}: {e}")
        await _soltar_reserva(base, envio_id, partida)
        return _pendiente(partida, importe, motivo="error")

    if usuario is None:
        # Sin saldo. NO es un 402: el paquete ya existe y está viajando. Queda
        # pendiente, y la única palanca real —que no salga de Pacaraima— se
        # ejerce en otro lado.
        logger.info(f"envios: {envio_id} deja la partida {partida} pendiente por saldo")
        await _soltar_reserva(base, envio_id, partida)
        return _pendiente(partida, importe, motivo="saldo")

    saldo_despues = to_decimal(usuario.get("balance_ris"))

    # 4. El LIBRO va antes de marcar, y no después. Es la evidencia de que el
    #    débito ocurrió, y es lo único que permite resolver una reserva
    #    abandonada sin adivinar: si el proceso muere entre el débito y el
    #    marcado, el asiento con este `intento_id` dice que la plata salió.
    #    Marcar primero y asentar después dejaba el caso opuesto —plata debitada
    #    sin ninguna línea que lo diga— que es el que no tiene arreglo.
    entry_id = await _asentar(user_id, importe, envio, partida, saldo_despues,
                              intento_id, actor_type, actor_id)

    # 5. Marcar la partida pagada.
    marcada = await _marcar_pagada(base, envio_id, partida, intento_id, importe, ahora)
    if marcada is not None:
        # El total se recalcula del documento ya marcado, no del dict que trajo
        # el llamador. Es un campo derivado y su fuente es la base.
        await _refrescar_total(base, envio_id, marcada)
    if marcada is None:
        # No se pudo marcar. Antes de devolver nada se RELEE: una excepción de
        # red no significa "la escritura no ocurrió", significa "no sé si
        # ocurrió", y devolver el saldo sobre una partida que quedó pagada
        # regala el traslado y libera Pacaraima.
        actual = await _releer(base, envio_id)
        doc = _partida_existente(actual, partida) or {}
        if doc.get("estado") == "pagado":
            return {"partida": partida, "estado": "pagado",
                    "monto_ris": str(importe),
                    "saldo_restante": str(quantize_money(saldo_despues)),
                    "entry_id": entry_id, "motivo": None}

        logger.error(
            f"envios: se debitó {importe} a {user_id} y no se pudo marcar la partida "
            f"{partida} de {envio_id}; se devuelve el saldo")
        devuelto = await _devolver(base, user_id, importe, entry_id, envio, partida)
        await _soltar_reserva(base, envio_id, partida)
        raise CobroImposible(
            "No se pudo registrar el pago. Tu saldo no fue afectado."
            if devuelto else
            "No se pudo registrar el pago y tampoco devolver el saldo. Ya estamos "
            "revisándolo: escribinos con el número de tu envío.", http=503)

    return {
        "partida": partida,
        "estado": "pagado",
        "monto_ris": str(importe),
        "saldo_restante": str(quantize_money(saldo_despues)),
        "entry_id": entry_id,
        "motivo": None,
    }


async def _reservar(base, envio_id: str, partida: str, intento_id: str, ahora):
    """`pendiente -> pagando`, o None si otra petición la tiene. Nunca lanza.

    Antes de rendirse intenta resolver una reserva ABANDONADA: si el proceso
    murió entre la reserva y el marcado, la partida queda en `pagando` para
    siempre, no figura pendiente, no está pagada, y el paquete no sale de
    Pacaraima. Ninguna ruta la destrabaría.
    """
    marca = {f"cobros.{partida}.estado": "pagando",
             f"cobros.{partida}.intento_id": intento_id,
             f"cobros.{partida}.reservado_at": ahora}
    try:
        tomada = await base.envios.find_one_and_update(
            {"envio_id": envio_id, f"cobros.{partida}.estado": "pendiente"},
            {"$set": marca}, return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo reservar {partida} de {envio_id}: {e}")
        return None
    if tomada is not None:
        return tomada

    if await _resolver_reserva_vencida(base, envio_id, partida, ahora):
        try:
            return await base.envios.find_one_and_update(
                {"envio_id": envio_id, f"cobros.{partida}.estado": "pendiente"},
                {"$set": marca}, return_document=True)
        except Exception as e:                                # pragma: no cover
            logger.error(f"envios: no se pudo reservar {partida}: {e}")
    return None


async def _resolver_reserva_vencida(base, envio_id: str, partida: str, ahora) -> bool:
    """Una reserva abandonada, resuelta con la evidencia del libro. Nunca lanza.

    Devuelve True si la dejó en `pendiente` (el débito NO había ocurrido) y False
    si no había nada que resolver o si la cerró como pagada.

    El libro es la evidencia porque se escribe ANTES de marcar: un asiento con
    ese `intento_id` significa que la plata salió, y entonces lo correcto es
    terminar de marcar la partida, no devolver nada. Sin asiento, el débito no
    llegó a ocurrir y la partida vuelve a `pendiente`.
    """
    actual = await _releer(base, envio_id)
    doc = _partida_existente(actual, partida) or {}
    if doc.get("estado") != "pagando":
        return False

    reservado = _fecha(doc.get("reservado_at"))
    if reservado is not None and (ahora - reservado).total_seconds() < RESERVA_VENCE_S:
        return False                      # es de hace un instante, no está abandonada

    intento = doc.get("intento_id")
    asiento = await _asiento_del_intento(base, intento) if intento else None
    if asiento is not None:
        logger.warning(
            f"envios: la partida {partida} de {envio_id} quedó reservada con el débito "
            f"ya hecho ({intento}); se cierra como pagada")
        await _marcar_pagada(base, envio_id, partida, intento,
                             to_decimal(asiento.get("amount")), ahora)
        return False

    logger.warning(
        f"envios: la partida {partida} de {envio_id} quedó reservada sin débito "
        f"({intento}); vuelve a pendiente")
    await _soltar_reserva(base, envio_id, partida)
    return True


async def _asiento_del_intento(base, intento_id: str):
    try:
        return await base.ledger.find_one({"metadata.intento_id": intento_id}, {"_id": 0})
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo consultar el libro por {intento_id}: {e}")
        return None


async def _marcar_pagada(base, envio_id: str, partida: str, intento_id: str,
                         importe: Decimal, ahora):
    """`pagando -> pagado`. Devuelve el documento, o None si no se pudo.

    Un `update_one` que no matchea NO lanza, y tratarlo como éxito dejaba el
    débito hecho, la partida en `pendiente` y la respuesta diciendo `pagado` — y
    el siguiente intento cobraba de nuevo. Por eso `find_one_and_update`, que
    devuelve None cuando no matcheó, y por eso el filtro incluye el `intento_id`:
    marcar la reserva de otra petición sería marcar un pago que no es este.
    """
    try:
        return await base.envios.find_one_and_update(
            {"envio_id": envio_id, f"cobros.{partida}.estado": "pagando",
             f"cobros.{partida}.intento_id": intento_id},
            {"$set": {f"cobros.{partida}.estado": "pagado",
                      f"cobros.{partida}.pagado_at": ahora}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo marcar {partida} de {envio_id}: {e}")
        return None


async def _refrescar_total(base, envio_id: str, envio: dict) -> None:
    """Deja `total_cobrado_ris` al día. Nunca lanza: es un campo de conveniencia,
    y la verdad se puede volver a derivar de las partidas en cualquier momento."""
    try:
        await base.envios.update_one(
            {"envio_id": envio_id},
            {"$set": {"cobros.total_cobrado_ris": str(total_cobrado(envio))}})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo refrescar el total de {envio_id}: {e}")


def _fecha(valor):
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


async def _soltar_reserva(base, envio_id: str, partida: str) -> None:
    """Vuelve la partida a `pendiente`. Nunca lanza.

    Una partida que queda en `pagando` para siempre es una deuda que nadie puede
    saldar: no figura como pendiente y no está pagada, así que el paquete no sale
    de Pacaraima y ninguna ruta la destraba.
    """
    try:
        await base.envios.update_one(
            {"envio_id": envio_id, f"cobros.{partida}.estado": "pagando"},
            {"$set": {f"cobros.{partida}.estado": "pendiente"}})
    except Exception as e:                                    # pragma: no cover
        logger.critical(
            f"envios: la partida {partida} de {envio_id} quedó trabada en 'pagando' y "
            f"no se pudo soltar. Requiere corrección manual: {e}")


async def _devolver(base, user_id: str, importe: Decimal, entry_id,
                    envio: dict, partida: str) -> bool:
    """La compensación. Devuelve si se pudo. Nunca lanza.

    Deja su propia línea en el libro: una devolución que no se asienta convierte
    el saldo en un número que el libro no explica, y reconciliar eso seis meses
    después no se puede.
    """
    try:
        await base.users.update_one(
            {"user_id": user_id}, {"$inc": {"balance_ris": to_decimal128(importe)}})
    except Exception as e:
        logger.critical(
            f"envios: NO SE PUDO DEVOLVER {importe} RIS a {user_id} tras un cobro "
            f"fallido. Requiere corrección manual: {e}")
        return False
    try:
        from services.ledger import record_ris_entry
        await record_ris_entry(
            user_id=user_id, movement_type=MOVIMIENTO_REEMBOLSO,
            amount=float(importe), direction="credit",
            reference_kind="envio", reference_id=envio.get("envio_id"),
            display_id=envio.get("display_id"), actor_type="system",
            metadata={"partida": partida, "compensa_asiento": entry_id},
            notes="Devolución: el cobro no se pudo registrar en el envío")
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo asentar la devolución: {e}")
    return True


async def _asentar(user_id, importe, envio, partida, saldo_despues,
                   intento_id, actor_type, actor_id) -> str | None:
    try:
        from services.ledger import record_ris_entry
        return await record_ris_entry(
            user_id=user_id,
            movement_type=MOVIMIENTO_COBRO,
            # `float` acá y no en el cálculo: la firma del libro es float y
            # cambiarla tocaría todos los flujos de dinero de la app. El monto ya
            # está redondeado a dos decimales, así que el float no puede
            # introducir un centavo que el débito no haya movido — y el débito,
            # que es lo que importa, se hizo en Decimal128.
            amount=float(importe),
            direction="debit",
            balance_after=float(saldo_despues),
            reference_kind="envio",
            reference_id=envio.get("envio_id"),
            display_id=envio.get("display_id"),
            actor_type=actor_type,
            actor_id=actor_id,
            metadata={"partida": partida,
                      # La evidencia de que el débito ocurrió. Es lo que permite
                      # resolver una reserva abandonada sin adivinar.
                      "intento_id": intento_id,
                      "tarifa_version": (envio.get("cotizacion") or {}).get(
                          "tarifa_version")},
            notes=f"Servicio de traslado transfronterizo, partida {partida}",
        )
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo asentar el cobro en el libro: {e}")
        return None


# ─── Piezas ───────────────────────────────────────────────────────────────

def _partida_valida(partida: str) -> None:
    """`PARTIDAS` existe para que nadie invente una tercera sin que se note.

    Sin este chequeo, cualquier clave con forma de dict dentro de `cobros` era
    cobrable desde la ruta: `POST /envios/{id}/cobros/reembolso/pagar` debitaba
    el monto de una DEVOLUCIÓN.
    """
    if partida not in PARTIDAS:
        raise CobroImposible(f"No existe una partida {partida!r} en este envío.",
                             http=404)


def _cobrable(envio: dict) -> None:
    """No se cobra sobre un envío terminado.

    `cancelado` es, por definición, "cancelado antes de que hubiera nada que
    cobrar"; `siniestrado` abre indemnización. Un reproceso de comprobantes
    atrasados le cobraba el traslado a paquetes que nunca se trasladaron.
    """
    from services.envios_estados import es_terminal
    estado = (envio or {}).get("estado")
    if estado and es_terminal(estado):
        raise CobroImposible(
            f"Este envío está {estado} y no se le puede cobrar el servicio.", http=409)


def _identidad(envio: dict) -> tuple[str, str]:
    envio_id = (envio or {}).get("envio_id")
    user_id = (envio or {}).get("user_id")
    if not envio_id or not user_id:
        raise CobroImposible(
            "El envío no tiene identidad completa; no se puede cobrar contra él.",
            http=500)
    return envio_id, user_id


def _partida_existente(envio: dict, partida: str) -> dict | None:
    """La partida, o None si no se emitió.

    Un dict VACÍO cuenta como emitida, no como ausente. Es la lectura que hace
    `envios_estados.partidas_impagas`, y discrepar dejaba un envío bloqueado sin
    salida: la deuda figuraba impaga, emitirla devolvía 503 en bucle porque el
    filtro `cobros.X: None` no matchea `{}`, y pagarla devolvía 404.
    """
    cobros = (envio or {}).get("cobros") or {}
    doc = cobros.get(partida)
    return doc if isinstance(doc, dict) else None


def total_cobrado(envio: dict) -> Decimal:
    """Lo efectivamente cobrado, SUMANDO las partidas pagadas.

    Se deriva en vez de acumularse. Un `$set` de un total calculado en Python
    sobre el dict del llamador pierde actualizaciones: se cobra el ajuste, se
    paga después la inicial desde una pantalla que leyó el envío antes, y el
    total queda diciendo 132,00 cuando el saldo bajó 138,70. El campo que se usa
    para saber si el envío está al día no puede depender de quién leyó primero.
    """
    cobros = (envio or {}).get("cobros") or {}
    total = ZERO
    for partida in PARTIDAS:
        doc = cobros.get(partida)
        if isinstance(doc, dict) and doc.get("estado") == "pagado":
            total += to_decimal(doc.get("monto_ris"))
    return quantize_money(total)


def _pendiente(partida: str, importe: Decimal, motivo: str) -> dict:
    return {
        "partida": partida,
        "estado": "pendiente",
        "monto_ris": str(importe),
        "saldo_restante": None,
        "entry_id": None,
        "motivo": motivo,
    }


def _resultado(partida: str, doc: dict, saldo) -> dict:
    # `pagando` es una reserva interna de milisegundos. Hacia afuera hay dos
    # estados y solo dos: pagado o pendiente. Filtrar el tercero le entrega a la
    # pantalla un valor que no sabe mostrar.
    estado = doc.get("estado")
    return {
        "partida": partida,
        "estado": "pagado" if estado == "pagado" else "pendiente",
        "monto_ris": str(to_decimal(doc.get("monto_ris"))),
        "saldo_restante": None if saldo is None else str(quantize_money(saldo)),
        "entry_id": None,
        "motivo": "en_curso" if estado == "pagando" else None,
    }


async def _releer(base, envio_id: str) -> dict:
    try:
        return await base.envios.find_one({"envio_id": envio_id}, {"_id": 0}) or {}
    except Exception:                                         # pragma: no cover
        return {}


async def _liberar(user_id, accion: str, key: str) -> None:
    """Suelta una clave reclamada cuya operación no llegó a ocurrir."""
    if not key:
        return
    try:
        from database import db as real
        await real["idempotency_keys"].delete_one(
            {"user_id": user_id, "action": accion, "key": key, "result": None})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo liberar la clave {accion}/{key}: {e}")


async def envio_del_usuario(usuario, envio_id: str, db=None) -> dict:
    """El envío, si es de quien lo pide. Mismo 404 para "no existe" y "es de otro".

    Distinguirlos convierte la ruta en un oráculo que confirma qué
    identificadores existen — y acá, además, cuáles tienen deuda.
    """
    base = await _db(db)
    user_id = getattr(usuario, "user_id", None)
    try:
        envio = await base.envios.find_one(
            {"envio_id": envio_id, "user_id": user_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        raise CobroImposible(
            "No se pudo leer el envío. Probá de nuevo en un momento.", http=503) from e
    if not envio:
        raise CobroImposible("No encontramos ese envío.", http=404)
    return envio


# ─── El cobro inicial, contra el comprobante ──────────────────────────────

async def emitir_inicial(envio: dict, peso_comprobante_kg, largo_cm, ancho_cm,
                         alto_cm, *, db=None, ahora=None,
                         idempotency_key: str = None, actor_id: str = None) -> dict:
    """El primer cobro, calculado con el peso que midió el transportista de origen.

    La tarifa NO la recibe de quien llama: la busca por la versión CONGELADA en
    el envío. Dejar que el llamador la pase abre la puerta a cobrar con una
    tarifa distinta de la que el usuario aceptó, y `envios_estados` ya se niega a
    calcular si las dos no coinciden — pero negarse tarde es negarse después de
    haber elegido mal.
    """
    from services.envios_estados import EnvioIncompleto, TarifaEquivocada, cobro_inicial

    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    tarifa = await _tarifa_congelada(base, envio)

    try:
        calculo = cobro_inicial(envio, tarifa, peso_comprobante_kg,
                                largo_cm, ancho_cm, alto_cm)
    except (EnvioIncompleto, TarifaEquivocada) as e:
        logger.error(f"envios: no se puede cobrar {envio.get('envio_id')}: {e}")
        raise CobroImposible(
            "No se puede calcular el cobro de este envío. Escribinos y lo resolvemos.",
            http=409) from e
    except Exception as e:
        logger.error(f"envios: el cálculo del cobro inicial falló: {e}")
        raise CobroImposible(
            "No se pudo calcular el cobro. Revisá los datos del comprobante.",
            http=400) from e

    return await cobrar(
        envio, "inicial", calculo["monto"], db=base, ahora=ahora,
        idempotency_key=idempotency_key,
        base_calculo="comprobante",
        peso_base_kg=calculo["peso_base_kg"],
        detalle={"tarifa_version": calculo["tarifa_version"],
                 "peso_facturable_kg": str(
                     calculo["desglose"]["comprobante"]["peso_facturable_kg"])},
        actor_type="system", actor_id=actor_id)


async def _tarifa_congelada(base, envio: dict) -> dict:
    """La versión de tarifa con la que se cotizó. No la vigente.

    Es lo que impide cobrarle a alguien un aumento posterior a lo que aceptó, y
    por eso se busca por `version_id` en el histórico y no se toma la que rige
    hoy: son dos documentos distintos y confundirlos es cobrar de más sin que
    nada chille.
    """
    version = ((envio or {}).get("cotizacion") or {}).get("tarifa_version")
    if not version:
        raise CobroImposible(
            "El envío no registra con qué versión de tarifa se cotizó, así que no hay "
            "forma de cobrarlo sin arriesgarse a cobrar precios que no aceptó.",
            http=409)
    try:
        tarifa = await base.tarifas_envio.find_one({"version_id": version}, {"_id": 0})
    except Exception as e:
        logger.error(f"envios: no se pudo leer la tarifa {version}: {e}")
        raise CobroImposible(
            "No se pudo leer la tarifa del envío. Reintentá en un momento.",
            http=503) from e
    if not tarifa:
        raise CobroImposible(
            "No encontramos la versión de tarifa con la que se cotizó este envío. "
            "Escribinos y lo resolvemos.", http=409)
    return tarifa


# ─── Devolver ─────────────────────────────────────────────────────────────

async def devolver(envio: dict, monto, *, db=None, ahora=None, motivo: str = "ajuste",
                   actor_type: str = "system", actor_id: str = None) -> dict:
    """Le acredita saldo al usuario. La otra mitad del ajuste.

    Existe porque el ajuste por repesaje tiene tres ramas y una es DEVOLVER: si
    la balanza propia da menos que el comprobante, el usuario pagó de más. Sin
    esta función el cobro inicial sería un anticipo que solo sube, que es
    exactamente lo que el diseño del ajuste dice que no puede pasar.

    Acreditar es más simple que cobrar y por una razón: no puede fallar por falta
    de fondos, así que no hay reserva, no hay carrera con el saldo y no hay
    compensación. Lo único que hay que garantizar es que no se acredite dos
    veces, y eso lo hace el registro en el envío.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio_id, user_id = _identidad(envio)

    importe = quantize_money(to_decimal(monto)).copy_abs()
    if not importe.is_finite() or importe <= ZERO:
        raise CobroImposible(
            "Una devolución de cero no se emite: si no hay nada que devolver, no hay "
            "devolución.", http=500)

    # La marca va primero y es la guardia: si ya está, no se acredita de nuevo.
    try:
        escrito = await base.envios.find_one_and_update(
            {"envio_id": envio_id, "cobros.devolucion": None},
            {"$set": {"cobros.devolucion": {
                "monto_ris": str(importe), "motivo": motivo,
                "emitido_at": ahora, "estado": "acreditando"}}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo emitir la devolución de {envio_id}: {e}")
        raise CobroImposible(
            "No se pudo emitir la devolución. Reintentá en un momento.", http=503) from e

    if escrito is None:
        ya = ((await _releer(base, envio_id)).get("cobros") or {}).get("devolucion") or {}
        return {"estado": ya.get("estado") or "acreditado",
                "monto_ris": str(to_decimal(ya.get("monto_ris"))),
                "saldo_restante": None, "entry_id": None}

    try:
        usuario = await base.users.find_one_and_update(
            {"user_id": user_id}, {"$inc": {"balance_ris": to_decimal128(importe)}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo acreditar {importe} a {user_id}: {e}")
        try:
            await base.envios.update_one({"envio_id": envio_id},
                                         {"$set": {"cobros.devolucion": None}})
        except Exception:                                     # pragma: no cover
            logger.critical(f"envios: devolución trabada en {envio_id}")
        raise CobroImposible(
            "No se pudo procesar la devolución. Reintentá en un momento.",
            http=503) from e

    saldo = to_decimal((usuario or {}).get("balance_ris"))
    entry_id = None
    try:
        from services.ledger import record_ris_entry
        entry_id = await record_ris_entry(
            user_id=user_id, movement_type=MOVIMIENTO_REEMBOLSO,
            amount=float(importe), direction="credit", balance_after=float(saldo),
            reference_kind="envio", reference_id=envio_id,
            display_id=envio.get("display_id"),
            actor_type=actor_type, actor_id=actor_id,
            metadata={"partida": "devolucion", "motivo": motivo},
            notes="Devolución del servicio de traslado transfronterizo")
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo asentar la devolución: {e}")

    try:
        await base.envios.update_one(
            {"envio_id": envio_id},
            {"$set": {"cobros.devolucion.estado": "acreditado",
                      "cobros.devolucion.acreditado_at": ahora,
                      "cobros.reembolsado_ris": str(importe)}})
    except Exception as e:                                    # pragma: no cover
        # La plata ya está en la cuenta del usuario. NO se revierte: quitarle un
        # saldo que ya vio, por un fallo nuestro de registro, es peor que un
        # campo desactualizado que se puede recalcular del libro.
        logger.error(f"envios: no se pudo cerrar la devolución de {envio_id}: {e}")

    return {"estado": "acreditado", "monto_ris": str(importe),
            "saldo_restante": str(quantize_money(saldo)), "entry_id": entry_id}
