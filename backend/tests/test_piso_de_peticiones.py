"""Un techo de pedidos por IP para toda la API, que arranca sólo avisando.

QUE PASABA
    Sólo frenaban las rutas con `frenar(...)` a mano. Todo lo demás —el
    historial, el saldo, el panel entero— no tenía tope.

LO QUE SE PRUEBA
    1. Que sólo se cuente `/api/...`, y que dentro del techo todo pase.
    2. Que en modo reporte (fábrica) pasarse NO corte nada y quede anotado
       en Errores, una vez por IP y minuto, con la IP y el número.
    3. Que en modo exigir el pedido de más reciba un 429 sin llegar a la
       ruta, con el mismo rastro que cualquier error.
    4. Que el panel tenga su techo aparte, más alto y con contador propio.
    5. Que IPs distintas no se mezclen.
    6. Que los tres números salgan del catálogo y se relean cada 30 s.
    7. Que si el contador o el catálogo fallan, se deje pasar.
    8. Que el servidor lo enganche.
"""
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI                                          # noqa: E402
from fastapi.testclient import TestClient                           # noqa: E402

from conftest import usar_base                                       # noqa: E402
from routes import security_2fa                                      # noqa: E402
from services import configuracion, piso_de_peticiones as piso       # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def _lejos_del_cambio_de_minuto(margen=10):
    """Si faltan menos de `margen` segundos para que cambie el minuto, espera
    a que empiece el siguiente.

    El piso cuenta por minuto de reloj: el contador y el aviso «una línea por
    IP y minuto» cambian de ventana cuando cambia el minuto. Un test que manda
    ocho pedidos a las hh:mm:59.9 los reparte en dos minutos, y lo que ve —dos
    líneas, un contador que vuelve a cero— es lo correcto para el producto y
    un rojo para el test. Pasó en CI: el aviso quedó a las 06:55:59.996.
    """
    import time
    resto = 60 - time.time() % 60
    if resto < margen:
        time.sleep(resto + 0.05)


@pytest.fixture
def base():
    _lejos_del_cambio_de_minuto()
    b = mongomock_motor.AsyncMongoMockClient()["ris_piso"]
    usar_base(b)
    security_2fa.reiniciar_la_cuenta()
    piso._olvidar()
    yield b
    security_2fa.reiniciar_la_cuenta()
    piso._olvidar()


def poner(base, clientes=3, panel=6, exigir=0):
    """Techos chicos para poder pasarlos en un test."""
    corre(configuracion.escribir(base, piso.AJUSTE_CLIENTES, clientes))
    corre(configuracion.escribir(base, piso.AJUSTE_PANEL, panel))
    corre(configuracion.escribir(base, piso.AJUSTE_EXIGIR, exigir))
    piso._olvidar()


@pytest.fixture
def app():
    a = FastAPI()
    llegaron = []

    @a.get("/api/cosas")
    async def cosas():
        llegaron.append("cosas")
        return {"ok": True}

    @a.get("/api/admin/pendientes")
    async def pendientes():
        llegaron.append("panel")
        return {"ok": True}

    @a.get("/otra")
    async def otra():
        llegaron.append("otra")
        return {"ok": True}

    a.add_middleware(piso.Piso)
    a.state.llegaron = llegaron
    return a


def cliente(app, ip="10.0.0.1"):
    return TestClient(app, headers={"cf-connecting-ip": ip, "x-forwarded-for": ip})


# ══════════════════════════════════════════════════════════════════════════
# 1 y 2. Sólo la API; en reporte no se corta, se anota
# ══════════════════════════════════════════════════════════════════════════

def test_lo_que_no_es_api_no_se_cuenta(base, app):
    poner(base, clientes=3)
    c = cliente(app)
    for _ in range(10):
        assert c.get("/otra").status_code == 200
    assert corre(base.errores.count_documents({})) == 0
    assert c.get("/api/cosas").status_code == 200


def test_dentro_del_techo_todo_pasa_y_no_se_anota_nada(base, app):
    poner(base, clientes=3)
    c = cliente(app)
    for _ in range(3):
        assert c.get("/api/cosas").status_code == 200
    assert corre(base.errores.count_documents({})) == 0


def test_en_modo_reporte_pasarse_NO_corta_y_queda_anotado_una_vez(base, app):
    poner(base, clientes=3, exigir=0)
    c = cliente(app, ip="10.0.0.7")
    for _ in range(8):
        assert c.get("/api/cosas").status_code == 200, "en reporte no se corta nada"
    assert len(app.state.llegaron) == 8, "los pedidos de más también llegaron a la ruta"
    avisos = corre(base.errores.find({}, {"_id": 0}).to_list(10))
    assert len(avisos) == 1, "una línea por IP y minuto, no una por pedido"
    a = avisos[0]
    assert a["status"] == 429 and a["tipo"] == piso.TIPO_DEL_AVISO
    assert a["ip"] == "10.0.0.7" and "10.0.0.7" in a["mensaje"] and "3" in a["mensaje"]
    assert a["ruta"] == "/api/cosas" and a["metodo"] == "GET"
    assert "no se cortó" in a["mensaje"]


# ══════════════════════════════════════════════════════════════════════════
# 3. En modo exigir, el pedido de más recibe 429
# ══════════════════════════════════════════════════════════════════════════

def test_en_modo_exigir_el_pedido_de_mas_recibe_429_sin_llegar_a_la_ruta(base, app):
    poner(base, clientes=3, exigir=1)
    c = cliente(app)
    for _ in range(3):
        assert c.get("/api/cosas").status_code == 200
    r = c.get("/api/cosas")
    assert r.status_code == 429
    assert r.json()["detail"] == piso.MENSAJE_DEL_429
    assert "request_id" in r.json()
    assert len(app.state.llegaron) == 3, "el cuarto no tenía que llegar a la ruta"
    assert corre(base.errores.count_documents({})) == 0, "cortando no hace falta avisar"


# ══════════════════════════════════════════════════════════════════════════
# 4 y 5. El panel aparte; las IPs aparte
# ══════════════════════════════════════════════════════════════════════════

def test_el_panel_tiene_su_techo_aparte_y_su_contador_aparte(base, app):
    poner(base, clientes=3, panel=6, exigir=1)
    c = cliente(app)
    for _ in range(3):
        assert c.get("/api/cosas").status_code == 200
    assert c.get("/api/cosas").status_code == 429
    # Gastar el cupo de clientes no toca al panel, que además aguanta más.
    for _ in range(6):
        assert c.get("/api/admin/pendientes").status_code == 200
    assert c.get("/api/admin/pendientes").status_code == 429


def test_los_defectos_del_panel_son_mucho_mas_altos_que_los_de_clientes():
    assert configuracion.AJUSTES[piso.AJUSTE_CLIENTES].defecto == 300
    assert configuracion.AJUSTES[piso.AJUSTE_PANEL].defecto >= 4 * 300
    assert configuracion.AJUSTES[piso.AJUSTE_EXIGIR].defecto == 0, "de fábrica sólo avisa"
    assert configuracion.AJUSTES[piso.AJUSTE_EXIGIR].maximo == 1


@pytest.mark.parametrize("camino,del_panel", [
    ("/api/admin", True), ("/api/admin/users", True), ("/api/admin/uso", True),
    ("/api/administracion", False), ("/api/transactions", False), ("/api/auth/me", False),
])
def test_que_es_del_panel(camino, del_panel):
    assert piso.es_del_panel(camino) is del_panel


def test_las_ips_no_se_mezclan(base, app):
    poner(base, clientes=3, exigir=1)
    for _ in range(3):
        assert cliente(app, "10.0.0.1").get("/api/cosas").status_code == 200
    assert cliente(app, "10.0.0.1").get("/api/cosas").status_code == 429
    assert cliente(app, "10.0.0.2").get("/api/cosas").status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 6 y 7. Los números salen del catálogo, con caché corta; nunca levanta
# ══════════════════════════════════════════════════════════════════════════

def test_los_ajustes_se_releen_cada_30_segundos(base):
    async def cuerpo():
        a = await piso.ajustes(base, ahora=1000.0)
        assert a["clientes"] == 300 and a["panel"] == 1500 and a["exigir"] is False
        await configuracion.escribir(base, piso.AJUSTE_CLIENTES, 50)
        await configuracion.escribir(base, piso.AJUSTE_EXIGIR, 1)
        a = await piso.ajustes(base, ahora=1010.0)
        assert a["clientes"] == 300, "antes de los 30 s se sirve lo cacheado"
        a = await piso.ajustes(base, ahora=1031.0)
        assert a["clientes"] == 50 and a["exigir"] is True, "pasados los 30 s se relee"
    corre(cuerpo())


def test_si_el_catalogo_no_responde_se_usan_los_de_fabrica_y_no_levanta():
    class _Rota:
        def __getitem__(self, _):
            raise RuntimeError("base caída")

    async def cuerpo():
        a = await piso.ajustes(_Rota(), ahora=5000.0)
        assert a["clientes"] == 300 and a["exigir"] is False
    piso._olvidar()
    corre(cuerpo())


def test_si_el_contador_se_rompe_se_deja_pasar(base, app, monkeypatch):
    poner(base, clientes=1, exigir=1)

    class _Roto:
        async def hit(self, *a, **k):
            raise RuntimeError("almacén caído")
    monkeypatch.setattr(security_2fa, "el_contador", lambda: _Roto())
    c = cliente(app)
    for _ in range(5):
        assert c.get("/api/cosas").status_code == 200


def test_los_tres_ajustes_estan_en_el_catalogo_y_son_enteros():
    for clave in (piso.AJUSTE_CLIENTES, piso.AJUSTE_PANEL, piso.AJUSTE_EXIGIR):
        assert configuracion.AJUSTES[clave].tipo == configuracion.ENTERO, clave


# ══════════════════════════════════════════════════════════════════════════
# 8. El servidor lo engancha
# ══════════════════════════════════════════════════════════════════════════

def test_el_servidor_engancha_el_piso():
    fuente = pathlib.Path(_BACKEND, "server.py").read_text(encoding="utf-8")
    assert "app.add_middleware(piso_de_peticiones.Piso)" in fuente
    assert "app.add_middleware(uso.Contador)" in fuente
    assert fuente.index("app.add_middleware(uso.Contador)") < fuente.index("app.add_middleware(piso_de_peticiones.Piso)"), \
        "el piso va por fuera del contador de uso: un pedido cortado no es uso de nadie"


def test_el_panel_no_comparte_contador_con_los_clientes_ni_con_el_mismo_techo(base, app):
    """Con techos distintos el contador se separa solo por la regla; con
    techos iguales sólo lo separa el alcance. Esto vigila el alcance."""
    poner(base, clientes=3, panel=3, exigir=1)
    c = cliente(app)
    for _ in range(3):
        assert c.get("/api/cosas").status_code == 200
    assert c.get("/api/cosas").status_code == 429
    for _ in range(3):
        assert c.get("/api/admin/pendientes").status_code == 200, "el panel tiene su propio contador"
