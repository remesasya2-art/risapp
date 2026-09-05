"""
tests/test_migracion_chats_a_casos.py — La historia vieja no se pierde al
mudarla.

POR QUE ESTE ARCHIVO

    Una migración se corre una vez, sobre datos que no se pueden volver a
    generar, y casi siempre de noche. Si se equivoca, no hay segunda toma: los
    `support_chats` quedan intactos, sí, pero un caso creado a medias hace que
    la re-corrida lo SALTEE —la idempotencia va por `origen_chat`— y esa
    conversación no vuelve más.

    Los dos defectos que se prueban acá son de ese tipo: no rompen nada
    visible, dejan casos vacíos.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para correr la migración")


def _correr():
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")
    return _ya(modulo.run())


def _ya(corrutina):
    """Corre una corrutina y devuelve su resultado.

    `asyncio.run` y no `get_event_loop().run_until_complete`: el segundo toma
    el lazo que otro archivo de la suite ya cerró, así que estos tests pasaban
    corriendo el archivo solo y fallaban los tres en la suite completa.
    """
    return asyncio.run(corrutina)


def _base_limpia():
    """Una base propia por test, y `database.db` apuntando a ella.

    `database.db` es un proxy global que apunta el último fixture que corrió:
    sin volver a apuntarlo acá, estos tests leerían la base de otro archivo.
    """
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["ris_migracion"]
    usar_base(base)
    return base


def _cuando(dia):
    return datetime(2026, 1, dia, 12, 0, tzinfo=timezone.utc)


async def _sembrar(base, cuantos_chats=2, con_id=False):
    for n in range(cuantos_chats):
        uid = f"u_{n}"
        await base.support_chats.insert_one({
            "user_id": uid, "user_name": f"Cliente {n}",
            "status": "open", "created_at": _cuando(1),
            "last_message": "Hola", "last_message_at": _cuando(2),
        })
        for i in range(3):
            doc = {
                "user_id": uid, "sender": "user" if i % 2 == 0 else "admin",
                "message": f"mensaje {i} de {uid}", "created_at": _cuando(1 + i),
            }
            if con_id:
                doc["message_id"] = f"m_{uid}_{i}"
            await base.support_messages.insert_one(doc)


def test_dos_chats_sin_identificador_de_mensaje_no_se_pisan():
    """El defecto: el primer mensaje de TODOS los chats se llamaba `msg_0`.

    Con el índice único de `soporte_mensajes`, el segundo chat fallaba entero
    y su conversación no se movía nunca.
    """
    base = _base_limpia()

    async def escenario():
        await _sembrar(base, cuantos_chats=3, con_id=False)

    _ya(escenario())
    resultado = _correr()

    assert resultado["casos_creados"] == 3
    assert resultado["mensajes_movidos"] == 9

    async def revisar():
        ids = await base.soporte_mensajes.distinct("mensaje_id")
        total = await base.soporte_mensajes.count_documents({})
        # Ningún identificador repetido: con `msg_{i}` había tres de cada uno.
        assert len(ids) == total == 9
        for caso in await base.soporte_casos.find({}, {"_id": 0}).to_list(10):
            cuantos = await base.soporte_mensajes.count_documents(
                {"caso_id": caso["caso_id"]})
            assert cuantos == 3, f"{caso['numero']} quedó con {cuantos} mensajes"

    _ya(revisar())


def test_una_corrida_cortada_por_la_mitad_se_termina_en_la_siguiente():
    """Mensajes movidos y caso sin crear: la próxima corrida lo completa.

    Sólo funciona si el identificador del caso sale del chat y no de un
    sorteo. Con uno al azar, los mensajes ya movidos quedarían colgando de un
    caso inexistente y el caso nuevo nacería vacío, porque los reinsertos se
    descartan por repetidos.
    """
    base = _base_limpia()

    _ya(_sembrar(base, cuantos_chats=1))
    _correr()

    async def simular_corte():
        # Se borra el caso y quedan sus mensajes: exactamente el estado en que
        # deja las cosas una corrida que se cae entre los dos pasos.
        await base.soporte_casos.delete_many({})

    _ya(simular_corte())
    _correr()

    async def revisar():
        casos = await base.soporte_casos.find({}, {"_id": 0}).to_list(10)
        assert len(casos) == 1
        cuantos = await base.soporte_mensajes.count_documents(
            {"caso_id": casos[0]["caso_id"]})
        assert cuantos == 3, (
            "el caso no quedó con su conversación entera")
        # Y no quedó ni un mensaje colgado de un caso que no existe: con un
        # identificador sorteado, los tres de la primera corrida se quedarían
        # apuntando a un caso borrado, invisibles para siempre.
        assert await base.soporte_mensajes.count_documents({}) == 3, (
            "quedaron mensajes huérfanos de la corrida anterior")

    _ya(revisar())


def test_correrla_dos_veces_no_duplica_nada():
    base = _base_limpia()

    _ya(_sembrar(base, cuantos_chats=2))
    primera = _correr()
    segunda = _correr()

    assert primera["casos_creados"] == 2
    assert segunda["casos_creados"] == 0
    assert segunda["ya_estaban"] == 2

    async def revisar():
        assert await base.soporte_casos.count_documents({}) == 2
        assert await base.soporte_mensajes.count_documents({}) == 6
        # Y los chats viejos siguen ahí, intactos.
        assert await base.support_chats.count_documents({}) == 2
        assert await base.support_messages.count_documents({}) == 6

    _ya(revisar())
