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
    # Los índices de verdad, con la misma función que corre en el arranque.
    # No es decorado: `run()` se planta si falta el único de `mensaje_id`, y
    # una base de test sin índices no se parece a ninguna base real. Armarlos
    # con el módulo —y no a mano acá— hace que estos tests corran contra la
    # definición que está en producción, no contra una copia que se despega.
    from services.soporte_indices import asegurar_indices
    _ya(asegurar_indices(base))
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


# ─── Lo que pasa cuando los datos viejos no son perfectos ──────────────────


def test_un_mensaje_repetido_no_corta_la_corrida():
    """El defecto: `insert_many(ordered=False)` sigue, pero LEVANTA al final.

    Dos mensajes viejos con el mismo `message_id` en chats DISTINTOS pasan el
    chequeo de `ya_movidos` —que mira sólo los del propio caso— y chocan
    contra el único al insertar. Sin atajar esa excepción, la corrida se
    cortaba ahí y los chats que venían después no se migraban nunca.
    """
    base = _base_limpia()

    async def escenario():
        for n in (0, 1, 2):
            uid = f"u_{n}"
            await base.support_chats.insert_one({
                "user_id": uid, "user_name": f"Cliente {n}",
                "status": "open", "created_at": _cuando(1),
                "last_message": "Hola", "last_message_at": _cuando(2),
            })
            # La misma llave en los tres chats: el caso que el chequeo por
            # caso no puede ver.
            await base.support_messages.insert_one({
                "user_id": uid, "sender": "user", "message_id": "m_repetido",
                "message": f"mensaje de {uid}", "created_at": _cuando(1),
            })
            await base.support_messages.insert_one({
                "user_id": uid, "sender": "user", "message_id": f"m_propio_{n}",
                "message": f"otro de {uid}", "created_at": _cuando(2),
            })

    _ya(escenario())
    resultado = _correr()

    # Los TRES casos se crearon: la corrida no se cortó en el segundo.
    assert resultado["casos_creados"] == 3
    # Cuatro mensajes movidos: los tres propios, más el repetido UNA vez.
    assert resultado["mensajes_movidos"] == 4
    assert resultado["mensajes_repetidos"], (
        "el resultado tiene que decir qué mensajes se descartaron por "
        "repetidos; si no, la pérdida es silenciosa")

    async def revisar():
        casos = await base.soporte_casos.find({}, {"_id": 0}).to_list(10)
        assert len(casos) == 3
        # Ningún caso quedó sin su mensaje propio.
        for caso in casos:
            cuantos = await base.soporte_mensajes.count_documents(
                {"caso_id": caso["caso_id"]})
            assert cuantos >= 1, f"{caso['numero']} quedó vacío"

    _ya(revisar())


def test_un_error_que_no_es_de_llave_repetida_si_frena():
    """Seguir después de un error cualquiera sería migrar a medias y callarlo.

    Sólo el 11000 —llave repetida— es esperable y se descarta. Cualquier otro
    tiene que subir.
    """
    import importlib
    from pymongo.errors import BulkWriteError

    _base_limpia()
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    class BaseQueFalla:
        class soporte_mensajes:
            @staticmethod
            async def insert_many(docs, ordered=True):
                raise BulkWriteError({
                    "nInserted": 0,
                    "writeErrors": [{"code": 121, "errmsg": "documento inválido"}],
                })

    original = modulo.db
    modulo.db = BaseQueFalla
    try:
        with pytest.raises(BulkWriteError):
            _ya(modulo._insertar([{"mensaje_id": "m_1"}]))
    finally:
        modulo.db = original


def test_el_ensayo_no_escribe_nada():
    """Es lo que se corre en producción antes de la corrida de verdad."""
    import importlib
    base = _base_limpia()
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    _ya(_sembrar(base, cuantos_chats=2))
    informe = _ya(modulo.ensayo())

    assert informe["chats"] == 2
    assert informe["casos_a_crear"] == 2
    assert informe["mensajes_a_mover"] == 6
    assert informe["ya_migrados"] == 0

    async def revisar():
        assert await base.soporte_casos.count_documents({}) == 0, (
            "el ensayo escribió casos")
        assert await base.soporte_mensajes.count_documents({}) == 0, (
            "el ensayo escribió mensajes")
        assert await base.contadores.count_documents({}) == 0, (
            "el ensayo movió el contador de números")

    _ya(revisar())


def test_el_ensayo_no_cuenta_dos_veces_lo_ya_migrado():
    """Corrido después de la migración tiene que dar cero para hacer."""
    base = _base_limpia()
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    _ya(_sembrar(base, cuantos_chats=2))
    _correr()
    informe = _ya(modulo.ensayo())

    assert informe["casos_a_crear"] == 0
    assert informe["mensajes_a_mover"] == 0
    assert informe["ya_migrados"] == 2


# ─── La red tiene que estar puesta ────────────────────────────────────────
#
# Toda la idempotencia de esta migración se apoya en el único de `mensaje_id`.
# `asegurar_indices()` lo crea en el arranque pero NO lanza si no pudo —a
# propósito, para no tumbar la aplicación por un índice—, así que «la
# aplicación levantó» no prueba que el índice esté. Y el caso en que falla es
# el peor: falla cuando la colección YA tiene duplicados.


def _base_sin_red():
    """Como `_base_limpia()`, pero sin ningún índice. La base que no debería
    recibir esta migración."""
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["ris_sin_red"]
    usar_base(base)
    return base


def test_sin_el_unico_de_mensaje_id_la_migracion_no_arranca():
    base = _base_sin_red()
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    _ya(_sembrar(base, cuantos_chats=2))

    with pytest.raises(modulo.FaltaLaRed) as e:
        _ya(modulo.run())

    # Y dice qué hacer, no sólo que no.
    assert "asegurar_indices" in str(e.value)


def test_plantarse_es_antes_de_escribir_la_primera_linea():
    """Frenar a mitad de camino dejaría casos creados sin sus mensajes, que es
    peor que no haber corrido: la segunda corrida los saltea por migrados."""
    base = _base_sin_red()
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    _ya(_sembrar(base, cuantos_chats=2))
    with pytest.raises(modulo.FaltaLaRed):
        _ya(modulo.run())

    async def revisar():
        assert await base.soporte_casos.count_documents({}) == 0
        assert await base.soporte_mensajes.count_documents({}) == 0
        assert await base.contadores.count_documents({}) == 0

    _ya(revisar())


def test_el_ensayo_avisa_que_falta_la_red_pero_no_se_planta():
    """El ensayo es el paso previo: tiene que poder decirte que falta, no
    reventar antes de contarte cuánto habría para migrar."""
    base = _base_sin_red()
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    _ya(_sembrar(base, cuantos_chats=2))
    informe = _ya(modulo.ensayo())

    assert informe["indice_unico_de_mensaje_id"].startswith("NO")
    assert informe["casos_a_crear"] == 2


def test_con_la_red_puesta_el_ensayo_lo_dice():
    _base_limpia()   # por el efecto: deja `database.db` apuntando acá
    import importlib
    modulo = importlib.import_module("migrations.002_chats_a_casos")

    informe = _ya(modulo.ensayo())

    assert informe["indice_unico_de_mensaje_id"] == "sí"
