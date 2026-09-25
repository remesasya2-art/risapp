"""
tests/_mongo_de_verdad.py — Correr un archivo de tests contra un Mongo con
réplicas de verdad, en vez de mongomock.

POR QUE EXISTE

    mongomock no tiene transacciones de varios documentos. Todo lo que la
    aplicación hace ADENTRO de una transacción no se prueba con él: los tests
    pasan por el camino sin transacciones, que es el de un Mongo de un solo
    nodo. El día que se probó el motor contable contra un Mongo con réplicas,
    dos tests se pusieron en rojo; con mongomock los dos pasaban.

COMO SE USA

    Con la variable `RIS_MONGO_DE_VERDAD` apuntando a un Mongo con réplicas, el
    fixture `base` de los archivos que usan esto abre ahí una base limpia por
    test. Sin la variable, usa mongomock como siempre. El trabajo «Suite del
    backend» de CI levanta el Mongo y corre esos archivos con la variable.

    El cliente de un Mongo de verdad queda atado al lazo de eventos donde
    nació: con `asyncio.run` cada llamada abre uno nuevo y la segunda revienta
    con «attached to a different loop». Por eso, con Mongo de verdad, `corre`
    usa un solo lazo por test.
"""
import asyncio
import os

MONGO_DE_VERDAD = os.environ.get("RIS_MONGO_DE_VERDAD")

_lazo = None


def corre(coro):
    return _lazo.run_until_complete(coro) if _lazo else asyncio.run(coro)


def base_para(monkeypatch, nombre):
    """Generador para un fixture: `yield from base_para(monkeypatch, "x")`.

    Reinicia además lo que `services/transacciones.py` recuerda de la base
    anterior: sin eso, el primer test decide por todos los demás si hay
    transacciones y el orden de los tests pasa a importar.
    """
    global _lazo
    from conftest import usar_base
    from services import transacciones
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", None)
    if not MONGO_DE_VERDAD:
        import mongomock_motor
        b = mongomock_motor.AsyncMongoMockClient()[nombre]
        usar_base(b)
        yield b
        return
    from motor.motor_asyncio import AsyncIOMotorClient
    _lazo = asyncio.new_event_loop()
    asyncio.set_event_loop(_lazo)
    cliente = AsyncIOMotorClient(MONGO_DE_VERDAD)
    corre(cliente.drop_database(nombre))
    b = cliente[nombre]
    usar_base(b)
    monkeypatch.setattr(transacciones, "mongo_client", cliente)
    try:
        yield b
    finally:
        cliente.close()
        _lazo.close()
        _lazo = None
        asyncio.set_event_loop(None)
