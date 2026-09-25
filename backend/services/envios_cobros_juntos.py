"""
services/envios_cobros_juntos.py — El cobro y la devolución de una encomienda,
en una sola transacción cuando el Mongo la tiene.

POR QUE ESTA EN UN ARCHIVO APARTE

    `envios_cobros.py` estaba congelado en 814 líneas (ver
    `tests/archivos_largos.txt`) y lo que se agregaba no entraba. `devolver`
    se mudó acá entero, tal cual estaba; `envios_cobros.devolver` sigue
    existiendo y llama a éste, así que nadie que lo use tuvo que cambiar.

LO QUE CAMBIA CON TRANSACCIONES

    Sin réplicas, cobrar es una cadena de escrituras separadas con su propio
    protocolo para cuando algo se corta: la reserva, el débito, la línea del
    libro como evidencia de que el débito ocurrió, el marcado, y una
    devolución si el marcado falla. Ese camino NO cambia: sigue en
    `envios_cobros._intentar_pagar`, y es el que corre hoy en producción.

    Con réplicas, el débito, la línea y el marcado van en una transacción:
    quedan los tres o ninguno. Ya no hace falta devolver nada cuando algo
    falla a la mitad, porque a la mitad no queda nada escrito.

    La RESERVA queda afuera, antes, igual que siempre. Es la que resuelve una
    petición que murió sin terminar (`_resolver_reserva_vencida`), y esa
    resolución mira el libro: con la transacción, la línea y el marcado van
    juntos, así que la evidencia es todavía más confiable que antes.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from services import transacciones
from services.money import ZERO, quantize_money, to_decimal, to_decimal128

logger = logging.getLogger("services.envios_cobros")


class _LaReservaYaNoEsDeEsteIntento(Exception):
    """El marcado no encontró la reserva de este intento. Se levanta ADENTRO de
    la transacción para deshacer el débito y la línea que ya se escribieron:
    sin marcado, esa plata saldría sin que el envío se entere."""


async def pagar_reservada(base, envio: dict, partida: str, importe: Decimal,
                          intento_id: str, ahora, actor_type: str, actor_id: str) -> dict:
    """Débito, línea del libro y marcado, en una transacción. La reserva ya está
    tomada por `intento_id`. Mismas respuestas que `_intentar_pagar`."""
    from services import envios_cobros as cobros
    envio_id, user_id = cobros._identidad(envio)

    async def trabajo(session):
        usuario = await base.users.find_one_and_update(
            {"user_id": user_id, "balance_ris": {"$gte": to_decimal128(importe)}},
            {"$inc": {"balance_ris": to_decimal128(-importe)}},
            return_document=True, session=session)
        if usuario is None:
            return None
        saldo_despues = to_decimal(usuario.get("balance_ris"))
        entry_id = await cobros._asentar(
            user_id, importe, envio, partida, saldo_despues,
            intento_id, actor_type, actor_id, session=session)
        # El mismo filtro que `_marcar_pagada`, y por lo mismo: con el
        # `intento_id` adentro, marcar la reserva de otra petición sería marcar
        # un pago que no es éste.
        marcada = await base.envios.find_one_and_update(
            {"envio_id": envio_id, f"cobros.{partida}.estado": "pagando",
             f"cobros.{partida}.intento_id": intento_id},
            {"$set": {f"cobros.{partida}.estado": "pagado",
                      f"cobros.{partida}.pagado_at": ahora}},
            return_document=True, session=session)
        if marcada is None:
            raise _LaReservaYaNoEsDeEsteIntento()
        return saldo_despues, entry_id, marcada

    try:
        hecho = await transacciones.en_una_transaccion(trabajo)
    except Exception as e:
        # No quedó nada escrito, salvo en un caso: que la confirmación haya
        # llegado al Mongo y la respuesta no. Por eso se suelta la reserva
        # PRIMERO y se relee DESPUÉS. Si la transacción se confirmó, la partida
        # ya está `pagado`, soltar no la toca —el filtro pide `pagando`— y la
        # relectura lo dice. Al revés, releer primero podía ver la partida
        # todavía sin marcar y contestar «pendiente» por un pago hecho.
        logger.error(f"envios: el cobro de {partida} de {envio_id} no se completó: {e}")
        await cobros._soltar_reserva(base, envio_id, partida)
        doc = cobros._partida_existente(await cobros._releer(base, envio_id), partida) or {}
        if doc.get("estado") == "pagado":
            return cobros._resultado(partida, doc, saldo=None)
        return cobros._pendiente(partida, importe, motivo="error")

    if hecho is None:
        logger.info(f"envios: {envio_id} deja la partida {partida} pendiente por saldo")
        await cobros._soltar_reserva(base, envio_id, partida)
        return cobros._pendiente(partida, importe, motivo="saldo")

    saldo_despues, entry_id, marcada = hecho
    # Afuera de la transacción: es un campo de conveniencia que no puede
    # tumbar un cobro, y adentro cualquier error la deshace entera.
    await cobros._refrescar_total(base, envio_id, marcada)
    return {
        "partida": partida,
        "estado": "pagado",
        "monto_ris": str(importe),
        "saldo_restante": str(quantize_money(saldo_despues)),
        "entry_id": entry_id,
        "motivo": None,
    }


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
    from services.envios_cobros import (
        MOVIMIENTO_REEMBOLSO, CobroImposible, _db, _identidad, _releer)
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio_id, user_id = _identidad(envio)

    importe = quantize_money(to_decimal(monto)).copy_abs()
    if not importe.is_finite() or importe <= ZERO:
        raise CobroImposible(
            "Una devolución de cero no se emite: si no hay nada que devolver, no hay "
            "devolución.", http=500)

    if await transacciones.hay_transacciones():
        return await _devolver_junto(base, envio, envio_id, user_id, importe, ahora,
                                     motivo, actor_type, actor_id)

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


async def _devolver_junto(base, envio: dict, envio_id: str, user_id: str,
                          importe: Decimal, ahora, motivo: str,
                          actor_type: str, actor_id: str) -> dict:
    """La marca, el crédito, la línea y el cierre, en una transacción.

    Sin transacciones la marca pasa por `acreditando` y se cierra al final,
    porque entre medio el proceso puede morir. Adentro de una transacción no
    hay «entre medio» que alguien pueda ver: se escribe ya cerrada. Si algo
    falla, no queda ni la marca, y reintentar la devolución funciona.
    """
    from services.envios_cobros import MOVIMIENTO_REEMBOLSO, CobroImposible, _releer
    from services.ledger import record_ris_entry

    async def trabajo(session):
        # La marca sigue siendo la guardia: dos devoluciones simultáneas chocan
        # en este documento, la segunda se reintenta y ya la encuentra.
        escrito = await base.envios.find_one_and_update(
            {"envio_id": envio_id, "cobros.devolucion": None},
            {"$set": {"cobros.devolucion": {
                "monto_ris": str(importe), "motivo": motivo, "emitido_at": ahora,
                "estado": "acreditado", "acreditado_at": ahora},
                "cobros.reembolsado_ris": str(importe)}},
            return_document=True, session=session)
        if escrito is None:
            return None
        usuario = await base.users.find_one_and_update(
            {"user_id": user_id}, {"$inc": {"balance_ris": to_decimal128(importe)}},
            return_document=True, session=session)
        saldo = to_decimal((usuario or {}).get("balance_ris"))
        entry_id = await record_ris_entry(
            user_id=user_id, movement_type=MOVIMIENTO_REEMBOLSO,
            amount=float(importe), direction="credit", balance_after=float(saldo),
            reference_kind="envio", reference_id=envio_id,
            display_id=envio.get("display_id"),
            actor_type=actor_type, actor_id=actor_id,
            metadata={"partida": "devolucion", "motivo": motivo},
            notes="Devolución del servicio de traslado transfronterizo",
            session=session)
        return saldo, entry_id

    try:
        hecho = await transacciones.en_una_transaccion(trabajo)
    except Exception as e:
        logger.error(f"envios: la devolución de {envio_id} no se completó: {e}")
        raise CobroImposible(
            "No se pudo procesar la devolución. Reintentá en un momento.",
            http=503) from e

    if hecho is None:
        ya = ((await _releer(base, envio_id)).get("cobros") or {}).get("devolucion") or {}
        return {"estado": ya.get("estado") or "acreditado",
                "monto_ris": str(to_decimal(ya.get("monto_ris"))),
                "saldo_restante": None, "entry_id": None}

    saldo, entry_id = hecho
    return {"estado": "acreditado", "monto_ris": str(importe),
            "saldo_restante": str(quantize_money(saldo)), "entry_id": entry_id}
