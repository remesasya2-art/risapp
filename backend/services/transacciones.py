"""
services/transacciones.py — Si el Mongo tiene transacciones, y cómo abrir una.

POR QUE ESTA EN UN ARCHIVO APARTE

    Vivía adentro de `accounting_engine.py`, que era el único que la usaba.
    Ahora también la usa `services/saldos.py`, para mover el saldo y escribir
    su línea del libro en una sola operación, y ese módulo no tiene por qué
    cargar el motor contable entero para preguntar esto.

QUE PASA SIN REPLICAS

    Un Mongo de un solo nodo no tiene transacciones de varios documentos.
    Esto se detecta una vez, al primer uso, y `sesion_atomica()` entrega
    `None`: el código escribe igual, en escrituras separadas. Es lo que pasa
    en producción mientras Mongo no sea un conjunto de réplicas, y lo que
    muestra la salud de la aplicación en `transacciones`.

    El camino CON transacciones no se ve con `mongomock`, que no las tiene.
    Lo prueba el trabajo «Motor contra un Mongo de verdad» de CI.
"""
import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Optional

from database import client as mongo_client
from pymongo.errors import PyMongoError

# El aviso de «Mongo de un solo nodo» salía con este nombre cuando la
# detección vivía en el motor contable; se conserva para que quien lo busque
# en los registros lo siga encontrando.
logger = logging.getLogger("services.accounting_engine")

# Cached at startup: True if replica set, False if standalone
_SUPPORTS_TRANSACTIONS: Optional[bool] = None


async def _detectar() -> bool:
    """Check once whether the cluster supports multi-document transactions."""
    global _SUPPORTS_TRANSACTIONS
    if _SUPPORTS_TRANSACTIONS is not None:
        return _SUPPORTS_TRANSACTIONS
    try:
        info = await mongo_client.admin.command("hello")
        # Replica sets expose "setName" — standalones don't
        _SUPPORTS_TRANSACTIONS = "setName" in info
    except Exception:
        # Sin respuesta NO se recuerda. Antes se guardaba «no hay» y quedaba
        # así hasta el próximo despliegue: un backend que arrancaba con Mongo
        # caído seguía sin transacciones cuando el conjunto de réplicas volvía.
        # Desde que el servidor atiende aunque la base no conteste (ver
        # services/preparar_la_base.py), arrancar así dejó de ser raro.
        return False
    if not _SUPPORTS_TRANSACTIONS:
        logger.warning(
            "Accounting engine: standalone MongoDB detected — "
            "running WITHOUT multi-document transactions (dev mode)"
        )
    return _SUPPORTS_TRANSACTIONS


async def hay_transacciones() -> bool:
    """Si el Mongo tiene transacciones de varios documentos (un conjunto de
    réplicas) o no (un nodo suelto). Lo pregunta la salud de la aplicación."""
    return await _detectar()


class CorteQueSeGuarda(ValueError):
    """Un corte que tiene que dejar escrito lo que anotó antes de cortar.

    POR QUE EXISTE

        Una transacción deshace TODO lo que pasó adentro si sale un error. Eso
        es lo que se quiere casi siempre, y justo no lo que se quiere cuando el
        error es la conclusión: la conciliación marca «suspended» una operación
        cuyo monto no cuadra y después corta. Con un Mongo de un solo nodo la
        marca queda; con transacciones, el corte la borraba y la operación
        volvía a estar lista para cobrarse con el monto mal. Se vio corriendo
        los tests del motor contra un Mongo con réplicas de verdad.

        Levantar esta excepción adentro de `sesion_atomica` confirma lo
        escrito y recién después deja salir el error. Es un `ValueError`: quien
        llama la sigue atrapando igual que antes.
    """


@asynccontextmanager
async def sesion_atomica():
    """Yield a Motor session inside a transaction, or None if standalone."""
    if await _detectar():
        async with await mongo_client.start_session() as session:
            guardado = None
            async with session.start_transaction():
                try:
                    yield session
                except CorteQueSeGuarda as corte:
                    guardado = corte
            if guardado is not None:
                raise guardado
    else:
        yield None


async def abandonar(session) -> None:
    """Deja la transacción sin confirmar y sale sin error.

    Un `insert_one` que choca con un índice único aborta la transacción EN EL
    SERVIDOR, aunque el código atrape el `DuplicateKeyError`. Si después se
    sale del bloque como si nada, el driver intenta confirmar una transacción
    que ya no existe y revienta con `NoSuchTransaction`: el aviso repetido de
    un proveedor, que tiene que contestar «ya procesado», terminaba en error.
    """
    if session is not None and session.in_transaction:
        await session.abort_transaction()


# Cuántas veces se intenta una transacción que choca con otra.
INTENTOS = 20


async def en_una_transaccion(trabajo):
    """Corre `trabajo(session)` adentro de una transacción, o `trabajo(None)`
    si el Mongo no tiene.

    Es el camino de los movimientos de saldo del cliente. Dos pagos al mismo
    usuario al mismo tiempo chocan: el segundo recibe un «WriteConflict»,
    marcado por el propio Mongo como pasajero, y acá se reintenta el trabajo
    entero. Sin el reintento, ese choque sería un error para el cliente.

    `trabajo` puede correr MÁS DE UNA VEZ: todo lo que escriba tiene que ir
    con la sesión que recibe, para que el intento que se descarta no deje
    nada escrito.

    POR QUE UN REINTENTO PROPIO Y NO `with_transaction` DEL DRIVER

        Se usaba el del driver, y se vieron dos problemas contra un Mongo de
        verdad. Uno: en motor 3.3 no reintenta lo que choca al CONFIRMAR —la
        confirmación ocurre al salir de su propio bloque y su reintento no
        llega a correr—; el primer asiento en un libro que todavía no existía
        chocaba así con la creación de sus índices y el movimiento terminaba
        en error. Dos: reintenta durante 120 SEGUNDOS, y un choque que se
        repite dejaba un pedido HTTP colgado dos minutos; con otro reintento
        encima, diez. Acá se cuentan intentos, no segundos.

        Sólo se reintenta lo que el Mongo marca como pasajero. Nunca una
        confirmación de resultado incierto («UnknownTransactionCommitResult»):
        pudo haberse aplicado, y repetir el trabajo entero la aplicaría dos
        veces.
    """
    if not await _detectar():
        return await trabajo(None)
    for intento in range(INTENTOS):
        async with await mongo_client.start_session() as session:
            try:
                async with session.start_transaction():
                    resultado = await trabajo(session)
                return resultado
            except PyMongoError as error:
                pasajero = (error.has_error_label("TransientTransactionError")
                            and not error.has_error_label("UnknownTransactionCommitResult"))
                if not pasajero or intento == INTENTOS - 1:
                    raise
        # Una espera corta y al azar, para que dos que chocaron no vuelvan a
        # chocar en el mismo instante.
        await asyncio.sleep(random.uniform(0, 0.005 * (intento + 1)))
