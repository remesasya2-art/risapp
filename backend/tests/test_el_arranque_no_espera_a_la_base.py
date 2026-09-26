"""
tests/test_el_arranque_no_espera_a_la_base.py — El servidor empieza a atender
aunque Mongo no conteste, y prepara la base cuando vuelve.

El 25 de septiembre de 2026 Mongo se quedó sin primario. El backend creaba sus
índices antes de atender, cada uno esperaba 30 segundos a la base, no contestó
`/api/health` en los cinco minutos de Railway y la página quedó en «Not Found».
Ver services/preparar_la_base.py.
"""
import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

pytest.importorskip("mongomock_motor")

if "pywebpush" not in sys.modules:
    _stub = types.ModuleType("pywebpush")
    _stub.WebPushException = type("WebPushException", (Exception,), {})
    _stub.webpush = lambda *a, **k: None
    sys.modules["pywebpush"] = _stub


def corre(coro):
    return asyncio.run(coro)


class _BaseQueNoContesta:
    """Un `ping` que falla las primeras `n` veces, como un Mongo sin primario."""

    def __init__(self, fallas):
        self.fallas = fallas
        self.pings = 0

    async def command(self, nombre):
        assert nombre == "ping"
        self.pings += 1
        if self.pings <= self.fallas:
            raise RuntimeError("No primary exists currently")
        return {"ok": 1}


# ══════════════════════════════════════════════════════════════════════════
# Esperar a la base
# ══════════════════════════════════════════════════════════════════════════

def test_ESPERA_A_QUE_LA_BASE_CONTESTE_Y_ESPACIA_LOS_INTENTOS():
    from services import preparar_la_base
    esperas = []

    async def dormir(s):
        esperas.append(s)
    base = _BaseQueNoContesta(fallas=7)
    fallidos = corre(preparar_la_base.esperar_la_base(base, dormir=dormir))
    assert fallidos == 7 and base.pings == 8
    assert esperas == [1, 2, 4, 8, 16, 30, 30], "sin tope, a la hora espera días entre intentos"


def test_CON_LA_BASE_SANA_NO_ESPERA_NADA():
    from services import preparar_la_base
    esperas = []

    async def dormir(s):
        esperas.append(s)
    assert corre(preparar_la_base.esperar_la_base(_BaseQueNoContesta(0), dormir=dormir)) == 0
    assert esperas == []


def test_PREPARA_RECIEN_CUANDO_LA_BASE_CONTESTA(monkeypatch):
    """Corrido directo con la base caída, cada paso fallaba y no se reintentaba
    hasta el próximo despliegue."""
    from services import preparar_la_base
    monkeypatch.setattr(preparar_la_base, "ESPERA_INICIAL_S", 0)
    base = _BaseQueNoContesta(fallas=3)
    visto = []

    async def preparar():
        visto.append(base.pings)

    async def todo():
        await preparar_la_base.arrancar(base, preparar)
    corre(todo())
    assert visto == [4], "preparó antes de que la base contestara"


def test_UN_ERROR_AL_PREPARAR_QUEDA_ESCRITO_Y_NO_SE_ESCAPA(monkeypatch, caplog):
    from services import preparar_la_base

    async def preparar():
        raise ValueError("un índice que no se pudo crear")

    async def todo():
        await preparar_la_base.arrancar(_BaseQueNoContesta(0), preparar)
    corre(todo())
    assert "la preparación de la base se cortó" in caplog.text


# ══════════════════════════════════════════════════════════════════════════
# El arranque del servidor
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def servidor(monkeypatch):
    """El servidor de verdad, con una base de mongomock y los relojes de fondo
    apagados: acá se mira sólo qué espera el arranque."""
    import mongomock_motor
    import server
    base = mongomock_motor.AsyncMongoMockClient()["ris_arranque"]
    monkeypatch.setattr(server, "db", base)
    for modulo, funcion in [("services.bcv_scraper", "start_scheduler"),
                            ("services.salud_de_la_app", "arrancar"),
                            ("services.respaldo_automatico", "arrancar"),
                            ("services.pago_al_final", "arrancar"),
                            ("nucleo.trabajador", "arrancar")]:
        monkeypatch.setattr(__import__(modulo, fromlist=[funcion]), funcion, lambda *a, **k: None)
    monkeypatch.setattr(server.uso, "arrancar", lambda *a, **k: None)
    return server, base


def test_EL_SERVIDOR_ATIENDE_AUNQUE_LA_BASE_NO_CONTESTE(servidor, monkeypatch):
    """Lo que tumbó la página: el arranque no terminaba mientras la base no
    contestara."""
    server, base = servidor
    from services import preparar_la_base

    async def nunca_contesta(db, dormir=None):
        await asyncio.Event().wait()
    monkeypatch.setattr(preparar_la_base, "esperar_la_base", nunca_contesta)

    async def arrancar_y_mirar():
        async with server.lifespan(server.app):
            indices = await base.users.index_information()
            tarea = preparar_la_base._tarea
        # Se mira acá, recién apagado: al terminar, `asyncio.run` cancela por
        # su cuenta lo que quede, y mirado afuera daría bien aunque el apagado
        # no la cortara.
        return "email_1" in indices, tarea.cancelled()
    ya_preparo, cortada = corre(asyncio.wait_for(arrancar_y_mirar(), timeout=10))
    assert ya_preparo is False, "preparó la base antes de que contestara"
    assert cortada, "al apagar, la espera quedó colgada"


def test_CUANDO_LA_BASE_CONTESTA_EL_ARRANQUE_LA_PREPARA(servidor):
    """Los índices se siguen creando: sólo cambia cuándo. El único que impide
    acreditar dos veces el mismo aviso de pago incluido."""
    server, base = servidor
    from services import preparar_la_base

    async def arrancar_y_esperar():
        async with server.lifespan(server.app):
            await asyncio.wait_for(asyncio.shield(preparar_la_base._tarea), timeout=20)
            return (await base.users.index_information(),
                    await base.processed_webhooks.index_information())
    usuarios, avisos = corre(arrancar_y_esperar())
    assert "email_1" in usuarios
    assert any(i.get("unique") for n, i in avisos.items() if n != "_id_")


# ══════════════════════════════════════════════════════════════════════════
# Si hay transacciones
# ══════════════════════════════════════════════════════════════════════════

class _ClienteQueVuelve:
    """Un Mongo con réplicas que la primera vez no contesta."""

    def __init__(self):
        self.veces = 0
        self.admin = self

    async def command(self, nombre):
        self.veces += 1
        if self.veces == 1:
            raise RuntimeError("No primary exists currently")
        return {"setName": "rs0", "ok": 1}


def test_SI_MONGO_NO_CONTESTA_NO_SE_QUEDA_CON_QUE_NO_HAY_TRANSACCIONES(monkeypatch):
    """Antes se guardaba «no hay» para siempre: un backend que arrancaba con el
    conjunto de réplicas caído seguía sin transacciones cuando volvía."""
    from services import transacciones
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", None)
    monkeypatch.setattr(transacciones, "mongo_client", _ClienteQueVuelve())
    assert corre(transacciones.hay_transacciones()) is False
    assert corre(transacciones.hay_transacciones()) is True


def test_UN_MONGO_SUELTO_SE_RECUERDA_Y_NO_SE_VUELVE_A_PREGUNTAR(monkeypatch):
    from services import transacciones

    class _Suelto:
        veces = 0

        def __init__(self):
            self.admin = self

        async def command(self, nombre):
            _Suelto.veces += 1
            return {"ok": 1}
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", None)
    monkeypatch.setattr(transacciones, "mongo_client", _Suelto())
    assert corre(transacciones.hay_transacciones()) is False
    assert corre(transacciones.hay_transacciones()) is False
    assert _Suelto.veces == 1
