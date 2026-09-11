"""
tests/test_soporte_indices.py — Que los índices de la mesa de ayuda existan
de verdad, y que el chat viejo ya no tenga puerta.

POR QUE ESTE ARCHIVO

    Los índices de la mesa de ayuda estaban escritos dos veces —`database.py`
    y el `lifespan` de `server.py`— con listas distintas, y de las dos sólo
    corría la del `lifespan`, que era la que NO tenía ninguno de los tres
    únicos. Un índice escrito y no creado es peor que uno que falta: el que
    lee el archivo cree que está.

    Nada lo avisaba porque un índice ausente no rompe nada visible. Sólo
    deja la base sin red y las consultas sin plan. Por eso es un test.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Los dos últimos tests arman la app entera para mirar sus rutas, y `config`
# lee estas dos al importarse. Sin ellas el import falla y los tests se
# SALTEAN —que es justo lo que no queremos del test que vigila una puerta.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor")

from services import soporte_indices                            # noqa: E402


def _ya(corrutina):
    return asyncio.run(corrutina)


def _base():
    return mongomock_motor.AsyncMongoMockClient()["ris_indices"]


# ─── Los tres únicos, que son los que faltaban ────────────────────────────


def test_el_unico_de_mensaje_id_esta_declarado():
    """Es la red de la migración del historial. Sin él, una corrida cortada y
    vuelta a correr duplica mensajes y nadie se entera."""
    declarados = [(c, k) for c, k, o in soporte_indices.INDICES if o.get("unique")]
    assert ("soporte_mensajes", "mensaje_id") in declarados


def test_los_identificadores_de_caso_y_pedido_son_unicos():
    unicos = {(c, k) for c, k, o in soporte_indices.INDICES if o.get("unique")}
    assert ("soporte_casos", "caso_id") in unicos
    assert ("soporte_pedidos", "pedido_id") in unicos


def test_el_numero_del_caso_NO_es_unico():
    """A propósito: la migración y las altas nuevas comparten contador y
    pueden repetir uno. Un único ahí haría fallar la creación del índice y,
    en una lista dentro de un try, se llevaría puestos los que siguen."""
    for coleccion, claves, opciones in soporte_indices.INDICES:
        if coleccion == "soporte_casos" and claves == "numero":
            assert not opciones.get("unique")
            return
    pytest.fail("no está declarado el índice sobre `numero`")


def test_la_bandeja_tiene_su_indice_con_el_orden_adentro():
    """La consulta del asesor filtra por estado y ORDENA por actualizado_en.

    El índice que corría en producción era `[estado, area]`: sirve para el
    filtro y no para el orden, así que el sort quedaba en memoria sobre toda
    la colección. Se consulta cada doce segundos por cada asesor conectado.
    """
    claves = [k for c, k, _ in soporte_indices.INDICES if c == "soporte_casos"]
    assert [("estado", 1), ("actualizado_en", -1)] in claves


# ─── Que se creen de verdad, y que nada de esto tumbe el arranque ─────────


def test_se_crean_todos_sobre_una_base_limpia():
    base = _base()
    resultado = _ya(soporte_indices.asegurar_indices(base))

    assert resultado["fallidos"] == []
    assert resultado["creados"] == len(soporte_indices.INDICES)


def test_correrla_dos_veces_no_se_queja():
    """Crear un índice en Mongo es idempotente, y esto corre en cada arranque."""
    base = _base()
    _ya(soporte_indices.asegurar_indices(base))
    segunda = _ya(soporte_indices.asegurar_indices(base))

    assert segunda["fallidos"] == []


def test_el_unico_de_mensaje_id_ataja_un_duplicado():
    """Que esté declarado no alcanza: tiene que estar aplicado."""
    from pymongo.errors import DuplicateKeyError

    base = _base()
    _ya(soporte_indices.asegurar_indices(base))

    async def escenario():
        await base.soporte_mensajes.insert_one({"mensaje_id": "m_1"})
        with pytest.raises(DuplicateKeyError):
            await base.soporte_mensajes.insert_one({"mensaje_id": "m_1"})

    _ya(escenario())


def test_un_indice_que_falla_no_frena_a_los_demas():
    """Un índice es rendimiento, no corrección. Tumbar el arranque de toda la
    aplicación por uno sería cambiar un problema chico por uno grave."""
    class UnaColeccionRota:
        async def create_index(self, claves, **opciones):
            raise RuntimeError("no se pudo")

    class BaseAMedias:
        def __getitem__(self, nombre):
            if nombre == "soporte_casos":
                return UnaColeccionRota()
            return _ColeccionQueAnda()

    class _ColeccionQueAnda:
        async def create_index(self, claves, **opciones):
            return "ok"

    resultado = _ya(soporte_indices.asegurar_indices(BaseAMedias()))

    rotos = sum(1 for c, _, _ in soporte_indices.INDICES if c == "soporte_casos")
    assert len(resultado["fallidos"]) == rotos
    assert resultado["creados"] == len(soporte_indices.INDICES) - rotos
    # Y el que falló dice cuál es, para poder ir a buscar los duplicados.
    assert resultado["fallidos"][0]["coleccion"] == "soporte_casos"


def test_una_base_que_no_responde_no_cuelga_el_arranque():
    """Con Mongo inalcanzable, cada create_index espera su propio timeout de
    selección de servidor. Once en serie son minutos de arranque colgado, que
    en Railway es un healthcheck que falla y un crash-loop."""
    class BaseQueNoContesta:
        def __getitem__(self, nombre):
            return self

        async def create_index(self, claves, **opciones):
            await asyncio.sleep(30)

    resultado = _ya(soporte_indices.asegurar_indices(
        BaseQueNoContesta(), timeout_s=0.2))

    assert resultado["timeout"] is True


# ─── Bases que ya venían con los índices viejos ───────────────────────────
#
# Todos los tests de arriba arrancan de una base limpia, y por eso ninguno veía
# el problema: en producción la base NO está limpia. El `lifespan` viejo de
# server.py ya creó ahí unos cuantos índices, y son esos los que chocan.


def _como_estaba_en_produccion(base):
    """Los índices de la mesa de ayuda tal como los dejó el `lifespan` viejo.

    Copiados de server.py antes de este cambio. Es el estado real de cualquier
    base donde la aplicación arrancó alguna vez.
    """
    async def sembrar():
        await base.soporte_casos.create_index("caso_id", unique=True)
        await base.soporte_casos.create_index([("user_id", 1), ("actualizado_en", -1)])
        await base.soporte_casos.create_index([("estado", 1), ("area", 1)])
        await base.soporte_casos.create_index([("asignado_a", 1), ("estado", 1)])
        await base.soporte_mensajes.create_index([("caso_id", 1), ("creado_en", 1)])
        await base.soporte_pedidos.create_index([("area", 1), ("estado", 1)])
        await base.soporte_pedidos.create_index("caso_id")
        await base.quick_replies.create_index([("created_at", 1)])
    _ya(sembrar())


def test_sobre_una_base_que_ya_arranco_no_falla_ninguno():
    """El caso que importa, y el que ninguna base limpia podía mostrar.

    `caso_id` ya está creado como `unique` a secas. Si acá se lo declarara
    `unique + sparse`, Mongo rechazaría la creación con IndexOptionsConflict
    —«ya existe con otras opciones»— en CADA arranque, para siempre.
    """
    base = _base()
    _como_estaba_en_produccion(base)

    resultado = _ya(soporte_indices.asegurar_indices(base))

    assert resultado["fallidos"] == []
    assert resultado["conflictos"] == []


def test_el_unico_de_caso_id_sigue_atajando_duplicados():
    """Sacarle `sparse` no puede haberle sacado el único."""
    from pymongo.errors import DuplicateKeyError

    base = _base()
    _como_estaba_en_produccion(base)
    _ya(soporte_indices.asegurar_indices(base))

    async def escenario():
        await base.soporte_casos.insert_one({"caso_id": "c_1"})
        with pytest.raises(DuplicateKeyError):
            await base.soporte_casos.insert_one({"caso_id": "c_1"})

    _ya(escenario())


def test_un_choque_de_opciones_no_se_cuenta_como_dato_sucio():
    """`fallidos` significa «hay duplicados en la base» y alguien tiene que ir
    a mirar. Un índice que ya está con otras opciones no es eso: si cayera en
    la misma lista, el aviso que importa quedaría enterrado bajo un warning
    que sale en todos los arranques."""
    base = _base()
    # Con otras opciones que las declaradas: acá `mensaje_id` va sin `sparse`.
    _ya(base.soporte_mensajes.create_index("mensaje_id", unique=True))

    resultado = _ya(soporte_indices.asegurar_indices(base))

    assert resultado["fallidos"] == []
    assert [c["coleccion"] for c in resultado["conflictos"]] == ["soporte_mensajes"]


# ─── Los índices que quedaron sin trabajo ─────────────────────────────────


def test_los_viejos_que_ya_no_sirven_se_borran():
    """Un índice de más no da respuestas equivocadas: cuesta una escritura en
    cada alta para responder algo que ya responde otro."""
    base = _base()
    _como_estaba_en_produccion(base)

    resultado = _ya(soporte_indices.asegurar_indices(base))

    assert set(resultado["sobrantes"]) == {"soporte_casos/estado_1_area_1",
                                           "soporte_pedidos/caso_id_1"}
    assert "estado_1_area_1" not in _ya(base.soporte_casos.index_information())
    assert "caso_id_1" not in _ya(base.soporte_pedidos.index_information())


def test_borrar_los_viejos_no_se_queja_si_no_estan():
    """Base nueva, o segundo arranque. Es el caso normal, no un error."""
    base = _base()
    primera = _ya(soporte_indices.asegurar_indices(base))
    segunda = _ya(soporte_indices.asegurar_indices(base))

    assert primera["sobrantes"] == []
    assert segunda["sobrantes"] == []
    assert segunda["fallidos"] == []


def test_no_se_borra_ninguno_de_los_que_si_se_declaran():
    """Una lista de borrados y otra de creados se despegan calladas. Si un
    nombre cayera en las dos, el arranque crearía y borraría lo mismo cada vez
    y la consulta se quedaría sin índice."""
    declarados = set()
    for coleccion, claves, _ in soporte_indices.INDICES:
        if isinstance(claves, str):
            nombre = f"{claves}_1"
        else:
            nombre = "_".join(f"{c}_{d}" for c, d in claves)
        declarados.add((coleccion, nombre))

    assert declarados.isdisjoint(set(soporte_indices.SOBRANTES))


# ─── La puerta del chat viejo ─────────────────────────────────────────────


def test_el_chat_viejo_ya_no_tiene_rutas():
    """`support_chats` es una colección que ninguna pantalla lee ya.

    Mientras `routes/support.py` estuvo montado, cualquier cliente
    autenticado podía escribir ahí —un buzón mudo— y, peor, un mensaje que
    entrara DESPUES de migrar ese chat no lo rescataba una segunda corrida:
    la idempotencia de la migración va por chat, no por mensaje.
    """
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    caminos = {getattr(r, "path", "") for r in app.routes}
    muertas = sorted(p for p in caminos
                     if p.startswith("/api/admin/support/")
                     or p in ("/api/support/send", "/api/support/history",
                              "/api/support/conversation", "/api/support/rate"))
    assert not muertas, (
        "volvieron a montarse rutas del chat viejo; escriben en "
        "`support_chats`, que ya no lee nadie:\n  " + "\n  ".join(muertas))


def test_las_respuestas_rapidas_siguen_estando():
    """Era lo único vivo del router viejo: la mesa de ayuda las pide al abrir.
    Apagar el chat no tenía que llevárselas puestas."""
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    caminos = {getattr(r, "path", "") for r in app.routes}
    assert "/api/admin/quick-replies" in caminos
    assert "/api/admin/quick-replies/{qr_id}" in caminos
