"""Qué usa la gente: contado en el servidor y a la vista del super administrador.

QUE PASABA
    El panel sabía cuánta plata se movió y cuántas cuentas hay, pero no qué
    hace la gente adentro. Cloudflare mide visitas por página, afuera, sin
    saber quién está logueado. Una decisión de producto sin ese número es
    una adivinanza.

LO QUE SE PRUEBA
    1. Que se cuente a los clientes con sesión, y a nadie más: ni anónimos,
       ni personal, ni los latidos que la aplicación pide sola.
    2. Que el volcado sume (`$inc`) y no pise, que las cuentas distintas no
       se dupliquen, y que lo que no se pudo escribir vuelva a la memoria.
    3. Que el middleware cuente por PLANTILLA y no por la URL con el id.
    4. Que se guarde sólo la lista de lo permitido: jamás cuerpo, consulta
       ni cabeceras.
    5. Que se borre solo (TTL) y que el servidor lo arranque y lo pare.
    6. Que el resumen cuente cuentas distintas de verdad, que las funciones
       que nadie usó salgan agrupadas por nombre, y que los números de la
       base (altas, embudo, activos, operaciones) salgan bien.
    7. Que la ruta sea sólo del super administrador y la pantalla exista.
    8. Que cada nombre y cada latido apunten a una ruta que existe.
"""
import ast
import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_PANEL = pathlib.Path(_BACKEND, "..", "frontend", "src", "pages", "AdminPanel.jsx").resolve()
_COMPONENTE = pathlib.Path(_BACKEND, "..", "frontend", "src", "components", "admin", "Uso.jsx").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI, Request                                # noqa: E402
from fastapi.testclient import TestClient                          # noqa: E402

from conftest import usar_base                                      # noqa: E402
from services import uso                                            # noqa: E402
from services.money import to_decimal128                            # noqa: E402

HOY = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
LO_PERMITIDO = {"dia", "metodo", "ruta", "pedidos", "cuentas", "cuando"}


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_uso"]
    usar_base(b)
    yield b


@pytest.fixture(autouse=True)
def memoria_limpia():
    """El contador es global a propósito (lo comparten todos los pedidos del
    proceso); entre tests se vacía para que uno no cuente lo del anterior."""
    uso._pendiente.clear()
    yield
    uso._pendiente.clear()


def cliente(ruta="/api/transactions", metodo="GET", user_id="u_1", ahora=HOY):
    return uso.contar(metodo=metodo, ruta=ruta, user_id=user_id, rol="user", ahora=ahora)


# ══════════════════════════════════════════════════════════════════════════
# 1. A quién se cuenta
# ══════════════════════════════════════════════════════════════════════════

def test_se_cuenta_a_los_clientes_por_dia_y_por_ruta():
    assert cliente(user_id="u_1")
    assert cliente(user_id="u_1")
    assert cliente(user_id="u_2")
    assert cliente(user_id="u_1", ahora=HOY - timedelta(days=1))
    assert uso.pendientes() == 4
    hoy = uso._pendiente[("2026-09-18", "GET", "/api/transactions")]
    assert hoy["pedidos"] == 3
    assert hoy["cuentas"] == {"u_1", "u_2"}
    ayer = uso._pendiente[("2026-09-17", "GET", "/api/transactions")]
    assert ayer["pedidos"] == 1


def test_NO_se_cuenta_a_los_anonimos():
    assert not uso.contar(metodo="GET", ruta="/api/rate", user_id=None, rol=None)
    assert not uso.contar(metodo="GET", ruta="/api/transactions", user_id="", rol="user")
    assert uso.pendientes() == 0


@pytest.mark.parametrize("rol", ["admin", "super_admin", "agent", "colaborador", None])
def test_NO_se_cuenta_al_personal(rol):
    """El panel sondea cada 15, 30 y 60 segundos: contado, tapa a los
    clientes. Y lo que se quiere saber es qué usa la gente."""
    assert not uso.contar(metodo="GET", ruta="/api/transactions", user_id="a_1", rol=rol)
    assert uso.pendientes() == 0


@pytest.mark.parametrize("metodo,ruta", [
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/heartbeat"),
    ("GET", "/api/notifications/unread-count"),
    ("GET", "/api/btc/precio"),
    ("GET", "/api/gestor/pix/status/{payment_id}"),
    ("GET", "/api/withdraw-crypto/{transaction_id}/status"),
    ("GET", "/api/credits/deposit/{order_id}/status"),
])
def test_NO_se_cuentan_los_latidos(metodo, ruta):
    """Lo que la aplicación pide sola. Contado, «tuvo la pestaña abierta» se
    vuelve la función más usada."""
    assert uso.es_latido(metodo, ruta)
    assert not cliente(ruta=ruta, metodo=metodo)
    assert uso.pendientes() == 0


def test_lo_que_la_persona_hace_NO_es_latido():
    for metodo, ruta in [("GET", "/api/transactions"), ("POST", "/api/reais/send"),
                         ("POST", "/api/gestor/pix/create"), ("GET", "/api/referidos/mis-referidos")]:
        assert not uso.es_latido(metodo, ruta), ruta


# ══════════════════════════════════════════════════════════════════════════
# 2. El volcado
# ══════════════════════════════════════════════════════════════════════════

def test_volcar_suma_y_no_pisa_y_las_cuentas_no_se_duplican(base):
    async def cuerpo():
        cliente(user_id="u_1"); cliente(user_id="u_2")
        assert await uso.volcar(base) == 1
        assert uso.pendientes() == 0
        # Segunda vuelta: la misma cuenta y una nueva. Con `$set` en vez de
        # `$inc` esto daría 2 y no 4; con `$push` daría cuatro cuentas.
        cliente(user_id="u_1"); cliente(user_id="u_3")
        assert await uso.volcar(base) == 1
        d = await base.uso.find_one({"dia": "2026-09-18", "ruta": "/api/transactions"}, {"_id": 0})
        assert d["pedidos"] == 4
        assert sorted(d["cuentas"]) == ["u_1", "u_2", "u_3"]
        assert d["metodo"] == "GET"
    corre(cuerpo())


def test_se_guarda_solo_lo_permitido_y_el_dia_como_fecha(base):
    async def cuerpo():
        cliente()
        await uso.volcar(base)
        d = await base.uso.find_one({}, {"_id": 0})
        assert set(d.keys()) == LO_PERMITIDO, sorted(set(d.keys()) ^ LO_PERMITIDO)
        assert d["cuando"] == datetime(2026, 9, 18)
    corre(cuerpo())


def test_volcar_sin_nada_pendiente_no_escribe(base):
    async def cuerpo():
        assert await uso.volcar(base) == 0
        assert await base.uso.count_documents({}) == 0
    corre(cuerpo())


def test_si_la_base_falla_no_levanta_y_lo_pendiente_vuelve_a_la_memoria():
    class _Rota:
        def __getitem__(self, _):
            class _C:
                async def update_one(self, *a, **k):
                    raise RuntimeError("base caída")
            return _C()

    async def cuerpo():
        cliente(user_id="u_1"); cliente(user_id="u_2")
        cliente(user_id="u_1", ahora=HOY - timedelta(days=1))
        assert await uso.volcar(_Rota()) == 0            # no levanta
        assert uso.pendientes() == 3, "lo que no se escribió se perdió"
        assert uso._pendiente[("2026-09-18", "GET", "/api/transactions")]["cuentas"] == {"u_1", "u_2"}
    corre(cuerpo())


def test_lo_que_vuelve_a_la_memoria_se_suma_a_lo_nuevo():
    """Entre que el volcado falla y devuelve, pudo entrar un pedido más."""
    uso._pendiente[("2026-09-18", "GET", "/api/x")] = {"pedidos": 2, "cuentas": {"u_9"}}
    uso._devolver(("2026-09-18", "GET", "/api/x"), {"pedidos": 3, "cuentas": {"u_1", "u_9"}})
    e = uso._pendiente[("2026-09-18", "GET", "/api/x")]
    assert e["pedidos"] == 5 and e["cuentas"] == {"u_1", "u_9"}


# ══════════════════════════════════════════════════════════════════════════
# 3. El middleware: por plantilla, y sólo lo que llegó a una ruta
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def app_de_prueba():
    app = FastAPI()

    @app.get("/api/cosas/{cosa_id}")
    async def una_cosa(cosa_id: str, request: Request):
        # Lo que hace `get_current_user` cuando autentica.
        request.state.user_id = "u_1"
        request.state.rol = "user"
        return {"ok": cosa_id}

    @app.get("/api/publica")
    async def publica():
        return {"ok": True}

    @app.get("/api/rompe")
    async def rompe(request: Request):
        request.state.user_id = "u_1"
        request.state.rol = "user"
        raise RuntimeError("se rompió")

    app.add_middleware(uso.Contador)
    return TestClient(app, raise_server_exceptions=False)


def test_el_middleware_cuenta_por_plantilla_y_no_por_la_url(app_de_prueba):
    assert app_de_prueba.get("/api/cosas/ENV-123?q=secreto").status_code == 200
    assert app_de_prueba.get("/api/cosas/ENV-456").status_code == 200
    assert list(uso._pendiente) == [(uso._dia(), "GET", "/api/cosas/{cosa_id}")]
    e = uso._pendiente[(uso._dia(), "GET", "/api/cosas/{cosa_id}")]
    assert e["pedidos"] == 2 and e["cuentas"] == {"u_1"}
    assert "secreto" not in repr(uso._pendiente)


def test_el_middleware_NO_cuenta_sin_sesion_ni_sin_ruta(app_de_prueba):
    assert app_de_prueba.get("/api/publica").status_code == 200       # sin usuario
    assert app_de_prueba.get("/api/no-existe").status_code == 404     # sin ruta
    assert uso.pendientes() == 0


def test_el_middleware_cuenta_aunque_la_ruta_reviente(app_de_prueba):
    """La persona igual quiso usarla. Y un 500 que además no se cuenta
    esconde justo la función que está fallando."""
    assert app_de_prueba.get("/api/rompe").status_code == 500
    assert uso.pendientes() == 1


def test_anotar_el_pedido_nunca_levanta():
    class _Raro:
        def get(self, *a):
            raise RuntimeError("scope roto")
    assert uso.anotar_el_pedido(_Raro()) is False


def test_la_puerta_de_sesion_cuelga_el_rol_del_pedido():
    """Sin el rol colgado, el contador no distingue clientes de personal y
    cuenta el sondeo del panel."""
    fuente = pathlib.Path(_BACKEND, "routes", "dependencies.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_current_user")
    cuerpo = ast.unparse(fn)
    assert "estado.user_id = user.get('user_id')" in cuerpo
    assert "estado.rol = user.get('role')" in cuerpo


# ══════════════════════════════════════════════════════════════════════════
# 4 y 5. Se borra solo; el servidor lo arranca, lo cuenta y lo para
# ══════════════════════════════════════════════════════════════════════════

def test_el_contador_se_borra_solo_con_un_ttl():
    fuente = pathlib.Path(_BACKEND, "services", "uso.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "preparar_indices")
    assert "expireAfterSeconds" in ast.unparse(fn), "se fue el índice TTL"
    assert uso.DIAS_QUE_SE_GUARDAN <= 90


def test_el_servidor_lo_engancha_entero():
    fuente = pathlib.Path(_BACKEND, "server.py").read_text()
    assert "app.add_middleware(uso.Contador)" in fuente, "se fue el middleware"
    assert "uso.preparar_indices(db)" in fuente
    assert "uso.arrancar(db)" in fuente
    antes, _, despues = fuente.partition("\n    yield\n")
    assert "uso.arrancar(db)" in antes, "arrancar va antes del yield (arranque)"
    assert "await uso.parar(db)" in despues, "parar va después del yield (apagado)"
    assert despues.index("uso.parar(db)") < despues.index("client.close()"), \
        "hay que volcar ANTES de cerrar la base"


def test_parar_vuelca_lo_que_quedo_en_memoria(base):
    async def cuerpo():
        uso.arrancar(base)
        cliente(user_id="u_1")
        await uso.parar(base)
        assert uso._tarea is None
        d = await base.uso.find_one({}, {"_id": 0})
        assert d and d["pedidos"] == 1
    corre(cuerpo())


def test_el_volcado_periodico_escribe_solo(base, monkeypatch):
    monkeypatch.setattr(uso, "CADA_CUANTO_SE_VUELCA", 0.01)

    async def cuerpo():
        uso.arrancar(base)
        cliente(user_id="u_1")
        await asyncio.sleep(0.05)
        try:
            assert await base.uso.count_documents({}) == 1
        finally:
            await uso.parar(base)
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 6. Lo que se lee
# ══════════════════════════════════════════════════════════════════════════

def test_el_resumen_cuenta_cuentas_distintas_de_verdad(base):
    """Una persona que usó algo tres días es UNA cuenta, no tres. Sumar el
    largo de cada día daría tres."""
    async def cuerpo():
        for d in range(3):
            cliente(user_id="u_1", ahora=HOY - timedelta(days=d))
        cliente(user_id="u_2")
        cliente(ruta="/api/reais/send", metodo="POST", user_id="u_2")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert r["desde"] == "2026-09-12" and r["hasta"] == "2026-09-18"
        assert [f["ruta"] for f in r["funciones"]] == ["/api/transactions", "/api/reais/send"]
        movimientos = r["funciones"][0]
        assert movimientos["pedidos"] == 4
        assert movimientos["cuentas"] == 2, "sumó los días en vez de contar cuentas"
        assert movimientos["nombre"] == "Movimientos (inicio e historial)"
        assert len(r["por_dia"]) == 7, "la serie tiene que traer TODOS los días, con ceros"
        assert r["por_dia"][-1] == {"dia": "2026-09-18", "pedidos": 3, "cuentas": 2}
        assert r["por_dia"][0] == {"dia": "2026-09-12", "pedidos": 0, "cuentas": 0}
    corre(cuerpo())


def test_el_resumen_deja_afuera_lo_de_antes_de_la_ventana(base):
    async def cuerpo():
        cliente(user_id="u_1", ahora=HOY - timedelta(days=10))
        cliente(user_id="u_2")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert r["funciones"][0]["pedidos"] == 1
        assert r["funciones"][0]["cuentas"] == 1
    corre(cuerpo())


def test_las_funciones_con_nombre_que_nadie_uso_salen_aparte(base):
    """La pregunta que sirve para decidir qué sacar. Una función en cero no
    aparecía en cero: no aparecía, y no se distinguía de una que no existe."""
    async def cuerpo():
        cliente(ruta="/api/transactions", metodo="GET")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert "Movimientos (inicio e historial)" not in r["sin_uso"], \
            "la usó alguien y salió como que no"
        assert "Referidos" in r["sin_uso"]
        assert "Cotización de encomienda" in r["sin_uso"]
        assert r["sin_uso"] == sorted(r["sin_uso"]), "sale ordenada, para poder leerla"
    corre(cuerpo())


def test_un_nombre_con_dos_rutas_no_sale_como_que_nadie_lo_uso(base):
    """Mandar bolívares se pide por dos caminos y los dos se llaman igual. Con
    las rutas crudas, usar uno dejaba al otro en la lista de «nadie la usó», o
    sea el mismo nombre arriba con tráfico y abajo en cero."""
    async def cuerpo():
        cliente(ruta="/api/withdraw", metodo="POST")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert "Envío a Venezuela (bolívares)" not in r["sin_uso"]
        # Y el otro camino, el que nadie tocó, tampoco arrastra el nombre.
        assert r["sin_uso"].count("Envío a Venezuela (bolívares)") == 0
    corre(cuerpo())


def test_sin_nada_contado_estan_TODAS_las_funciones_con_nombre(base):
    async def cuerpo():
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert r["funciones"] == []
        assert sorted(set(uso.NOMBRES.values())) == r["sin_uso"]
    corre(cuerpo())


def test_una_ruta_sin_nombre_NO_ensucia_la_lista_de_las_que_nadie_uso(base):
    """La lista es de funciones CON nombre. Una plantilla cruda no es una
    función que alguien decidió ofrecer: es una ruta que todavía no se nombró,
    y meterla acá convierte la lista en una lista de rutas."""
    async def cuerpo():
        cliente(ruta="/api/algo/nuevo", metodo="POST")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert "/api/algo/nuevo" not in r["sin_uso"]
        assert all(n in set(uso.NOMBRES.values()) for n in r["sin_uso"])
    corre(cuerpo())


def test_lo_de_afuera_de_la_ventana_no_salva_a_una_funcion(base):
    """Si se usó hace un mes y la ventana es de una semana, en esta ventana
    nadie la usó. Mirar toda la colección en vez de la ventana la escondería
    para siempre."""
    async def cuerpo():
        cliente(ruta="/api/referidos/mis-referidos", metodo="GET",
                ahora=HOY - timedelta(days=10))
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert "Referidos" in r["sin_uso"]
    corre(cuerpo())


def test_una_ruta_sin_nombre_sale_igual_con_su_plantilla(base):
    async def cuerpo():
        cliente(ruta="/api/algo/nuevo", metodo="POST")
        await uso.volcar(base)
        r = await uso.resumen(base, dias=7, hoy=HOY)
        assert r["funciones"] == [{"metodo": "POST", "ruta": "/api/algo/nuevo", "nombre": None,
                                   "pedidos": 1, "cuentas": 1}]
    corre(cuerpo())


def _cuenta(user_id, hace_dias, estado="unverified", ingreso_hace=None, **extra):
    d = {"user_id": user_id, "email": f"{user_id}@ejemplo.com",
         "created_at": HOY - timedelta(days=hace_dias),
         "verification_status": estado,
         "balance_ris": to_decimal128(0), **extra}
    if ingreso_hace is not None:
        d["last_login"] = HOY - timedelta(days=ingreso_hace)
    return d


def _tx(tipo, entra, sale, estado="completed", hace_dias=0):
    return {"type": tipo, "currency_input": entra, "currency_output": sale,
            "status": estado, "created_at": HOY - timedelta(days=hace_dias),
            "amount_input": to_decimal128("10.00"), "amount_output": to_decimal128("50.00")}


def test_los_numeros_de_la_base_altas_embudo_y_activos(base):
    async def cuerpo():
        await base.users.insert_many([
            _cuenta("u_1", 2, "verified", ingreso_hace=1),
            _cuenta("u_2", 9, "pending", ingreso_hace=10),
            _cuenta("u_3", 20, "rejected"),
            _cuenta("u_4", 100, "unverified", ingreso_hace=40),     # fuera de la ventana
            _cuenta("u_5", 1, "verified", is_deleted=True),         # borrada: no existe
        ])
        n = await uso.numeros_de_la_base(base, dias=30, ahora=HOY)
        assert n["embudo"] == {"registrados": 3, "enviaron_documentos": 3,
                               "en_revision": 1, "aprobados": 1, "rechazados": 1}
        assert n["totales"] == {"cuentas": 4, "verificadas": 1}
        assert n["activos"] == {"7": 1, "30": 2}
        semanas = {s["semana"]: s["cuantos"] for s in n["altas_por_semana"]}
        assert semanas["2026-09-14"] == 1      # u_1, el miércoles 16
        assert semanas["2026-09-07"] == 1      # u_2, el miércoles 9
        assert semanas["2026-08-24"] == 1      # u_3, el sábado 29
        assert semanas["2026-08-31"] == 0, "una semana sin altas tiene que salir en cero, no faltar"
        assert [s["semana"] for s in n["altas_por_semana"]] == sorted(semanas)
    corre(cuerpo())


def test_los_numeros_de_la_base_operaciones_por_tipo(base):
    """Las de `transactions` se distinguen por moneda; las demás viven cada
    una en su colección con su campo de fecha."""
    async def cuerpo():
        await base.transactions.insert_many([
            _tx("withdrawal", "RIS", "BRL"),
            _tx("withdrawal", "RIS", "BRL", estado="pending"),
            _tx("withdrawal", "RIS", "VES"),
            _tx("withdrawal", "USDT", "VES"),
            _tx("recharge_ves", None, None),
            _tx("recharge_ves", None, None, hace_dias=45),         # fuera de la ventana
        ])
        await base.gestor_pix_payments.insert_many([
            {"status": "paid", "created_at": HOY, "amount_ris": to_decimal128("10")},
            {"status": "expired", "created_at": HOY, "amount_ris": to_decimal128("10")},
        ])
        await base.card_payments.insert_one({"status": "approved", "created_at": HOY})
        await base.crypto_deposits.insert_one({"credited": False, "created_at": HOY})
        await base.btc_remesas.insert_one({"estado": "enviado", "creado_en": HOY})
        await base.envios.insert_one({"estado": "esperando_postagem", "confirmado_at": HOY})
        await base.soporte_casos.insert_one({"estado": "abierto", "creado_en": HOY})
        n = await uso.numeros_de_la_base(base, dias=30, ahora=HOY)
        por_nombre = {o["nombre"]: (o["iniciadas"], o["terminadas"]) for o in n["operaciones"]}
        assert por_nombre["Envíos a Brasil"] == (2, 1)
        assert por_nombre["Envíos a Venezuela"] == (1, 1)
        assert por_nombre["Envíos con cripto"] == (1, 1)
        assert por_nombre["Recargas desde Venezuela"] == (1, 1)
        assert por_nombre["Recargas por PIX"] == (2, 1)
        assert por_nombre["Recargas con tarjeta"] == (1, 1)
        assert por_nombre["Depósitos cripto"] == (1, 0)
        assert por_nombre["Envíos BTC Lightning"] == (1, 1)
        assert por_nombre["Encomiendas confirmadas"] == (1, None)
        assert por_nombre["Casos de soporte"] == (1, None)
        assert n["operaciones"][0]["nombre"] in ("Envíos a Brasil", "Recargas por PIX")
    corre(cuerpo())


def test_todo_junta_las_dos_fuentes(base):
    async def cuerpo():
        cliente()
        await uso.volcar(base)
        t = await uso.todo(base, dias=7)
        assert set(t) == {"dias", "desde", "hasta", "funciones", "sin_uso",
                          "por_dia", "base"}
        assert t["funciones"][0]["pedidos"] == 1
        assert "Referidos" in t["sin_uso"], "la lista de las que nadie usó no llegó"
        assert "embudo" in t["base"] and "operaciones" in t["base"]
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 7. La ruta y la pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_la_ruta_es_solo_del_super_administrador():
    from routes import uso_admin
    from routes.dependencies import get_super_admin
    rutas = [r for r in uso_admin.router.routes if getattr(r, "path", "") == "/admin/uso"]
    assert len(rutas) == 1
    puertas = [d.call for d in rutas[0].dependant.dependencies]
    assert get_super_admin in puertas, "la ruta dejó de exigir super administrador"


def test_la_ruta_acota_los_dias(base, monkeypatch):
    from routes import uso_admin
    monkeypatch.setattr(uso_admin, "db", base)

    async def cuerpo():
        assert (await uso_admin.ver(dias=7, admin=None))["dias"] == 7
        assert (await uso_admin.ver(dias=90, admin=None))["dias"] == 90
        assert (await uso_admin.ver(dias=900, admin=None))["dias"] == 30, "pedir 900 días tiene que caer al valor de siempre"
        assert (await uso_admin.ver(dias=-1, admin=None))["dias"] == 30
    corre(cuerpo())


def test_la_pestana_existe_y_es_solo_del_super_administrador():
    panel = _PANEL.read_text(encoding="utf-8")
    assert "key: 'uso'" in panel, "se fue la pestaña Uso"
    linea = next(l for l in panel.splitlines() if "key: 'uso'" in l)
    assert "superAdminOnly: true" in linea
    assert "'uso'" in next(l for l in panel.splitlines() if "hijas: ['overview'" in l)
    assert "<Uso />" in panel


def test_la_pantalla_pega_a_la_ruta_y_ofrece_los_tres_periodos():
    assert _COMPONENTE.is_file()
    fuente = _COMPONENTE.read_text(encoding="utf-8")
    assert "api.get(`/admin/uso?dias=${dias}`)" in fuente
    assert "const PERIODOS = [7, 30, 90];" in fuente
    for testid in ("uso-funciones", "uso-operaciones", "uso-embudo", "uso-por-dia"):
        assert f'data-testid="{testid}"' in fuente, testid


def test_la_pantalla_dibuja_las_que_nadie_uso_CON_la_advertencia():
    """La advertencia no es decoración: sin ella la lista se lee como «esto
    sobra», y el número no dice eso. Un botón escondido da el mismo cero."""
    fuente = _COMPONENTE.read_text(encoding="utf-8")
    assert 'datos?.sin_uso' in fuente, "la pantalla no lee la lista"
    assert 'data-testid="uso-sin-uso"' in fuente
    # La condición, y no sólo que el bloque exista. Escrito sin esta línea, el
    # test quedaba en verde con el bloque colgado de un `false`: estaba en el
    # archivo y no se dibujaba nunca. Se vio rompiéndolo a propósito.
    assert '{sinUso.length > 0 ? (' in fuente, "el bloque no se dibuja aunque haya lista"
    assert "Nadie las usó en" in fuente
    assert "o una a la que no se" in fuente and "botón quedó escondido" in fuente


# ══════════════════════════════════════════════════════════════════════════
# 8. Los nombres y los latidos apuntan a rutas que existen
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def rutas_vivas():
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    from fastapi.routing import APIRoute
    vivas = set()
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                vivas.add((m, r.path))
    assert len(vivas) > 100
    return vivas


def test_cada_nombre_apunta_a_una_ruta_que_existe(rutas_vivas):
    """Un nombre sobre una ruta que se renombró es un nombre que nunca más
    aparece, y la función vuelve a salir cruda sin que nadie se entere."""
    muertas = sorted(k for k in uso.NOMBRES if k not in rutas_vivas)
    assert not muertas, muertas


def test_cada_latido_apunta_a_una_ruta_que_existe(rutas_vivas):
    """Un latido mal escrito no excluye nada: la ruta se cuenta igual y tapa
    a las demás."""
    muertos = sorted(k for k in uso.LATIDOS if k not in rutas_vivas)
    assert not muertos, muertos


def test_ningun_latido_lleva_nombre():
    """Serían dos listas diciendo cosas contrarias de la misma ruta.

    Se pregunta con `es_latido` y NO cruzando contra `LATIDOS`, que es como
    estaba escrita antes. Cruzar los dos conjuntos deja afuera la mitad de la
    regla: además de la lista explícita, cualquier `GET` con `/status` adentro
    es latido. Escrita de la forma obvia, esta guarda estaba en verde con
    «Estado de la verificación» nombrado y descartado al mismo tiempo, y
    recién se vio cuando la pantalla empezó a dibujar las funciones en cero:
    esa iba a salir como «nadie la usa» sin que nadie la hubiera podido usar.
    """
    mal = sorted(k for k in uso.NOMBRES if uso.es_latido(*k))
    assert not mal, mal
