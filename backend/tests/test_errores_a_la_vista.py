"""Los errores del servidor quedan asentados y el super administrador los ve.

QUE PASABA
    Cuando algo se rompía, el error iba al log de Railway y ahí se quedaba.
    El super administrador no tenía forma de saber que algo fallaba hasta que
    un cliente escribía. `rastro.py` ya daba un código para ENCONTRAR el
    error; faltaba que alguien lo VIERA antes.

LO QUE SE PRUEBA
    1. Que un 500 no previsto quede asentado, con rastro, ruta y usuario.
    2. Que un 5xx levantado a propósito (el 503 de PIX) también, y un 4xx no.
    3. Que se guarde SOLO la lista de lo permitido: jamás el cuerpo ni las
       cabeceras del pedido, que traen contraseñas y tokens.
    4. Que los secretos conocidos se tachen del mensaje antes de guardar.
    5. Que asentar nunca levante: es lo último en pie cuando todo se cayó.
    6. Que el registro se borre solo (índice TTL).
    7. Que la pantalla exista y pegue a la ruta.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_PANEL = pathlib.Path(_BACKEND, "..", "frontend", "src", "pages", "AdminPanel.jsx").resolve()
_COMPONENTE = pathlib.Path(_BACKEND, "..", "frontend", "src", "components", "admin", "Errores.jsx").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import HTTPException                                   # noqa: E402
from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base                                      # noqa: E402
from services import errores                                        # noqa: E402

LO_PERMITIDO = {"rastro", "metodo", "ruta", "status", "tipo", "mensaje",
                "traza", "user_id", "ip", "cuando"}


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_errores"]
    usar_base(b)
    yield b


def pedido(camino="/api/withdrawal/create", plantilla=None, user_id=None):
    r = PedidoReal({
        "type": "http", "method": "POST", "path": camino, "query_string": b"q=1",
        "headers": [(b"authorization", b"Bearer TOKEN-SECRETO"),
                    (b"cf-connecting-ip", b"10.0.0.7")],
        "client": ("10.0.0.7", 0),
    })
    if plantilla:
        class _Ruta:
            path = plantilla
        r.scope["route"] = _Ruta()
    r.state.user_id = user_id
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1 y 2. Los manejadores del servidor asientan
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def servidor():
    try:
        import server
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return server


def test_un_500_no_previsto_queda_asentado(base, servidor):
    async def cuerpo():
        servidor.db = base
        try:
            raise ValueError("se rompió algo adentro")
        except ValueError as exc:
            r = await servidor._error_no_previsto(
                pedido(plantilla="/api/withdrawal/create", user_id="u_7"), exc)
        assert r.status_code == 500
        lineas = await base.errores.find({}, {"_id": 0}).to_list(10)
        assert len(lineas) == 1
        l = lineas[0]
        assert l["status"] == 500
        assert l["ruta"] == "/api/withdrawal/create"
        assert l["tipo"] == "ValueError"
        assert "se rompió algo adentro" in l["mensaje"]
        assert "ValueError" in (l["traza"] or "")
        assert l["user_id"] == "u_7"
        assert l["ip"] == "10.0.0.7"
        assert l["rastro"]
    corre(cuerpo())


def test_la_ruta_se_guarda_como_plantilla_y_no_con_el_id_adentro(base, servidor):
    """Con el id adentro cada error es su propia ruta y la pantalla no agrupa
    nada."""
    async def cuerpo():
        servidor.db = base
        try:
            raise RuntimeError("x")
        except RuntimeError as exc:
            await servidor._error_no_previsto(
                pedido("/api/admin/users/u_123/ficha", plantilla="/api/admin/users/{user_id}/ficha"), exc)
        l = await base.errores.find_one({}, {"_id": 0})
        assert l["ruta"] == "/api/admin/users/{user_id}/ficha"
    corre(cuerpo())


def test_un_503_levantado_a_proposito_tambien_se_asienta(base, servidor):
    async def cuerpo():
        servidor.db = base
        r = await servidor._error_levantado_a_proposito(
            pedido(plantilla="/api/gestor/pix/create"),
            HTTPException(status_code=503, detail="No pudimos generar el cobro"))
        assert r.status_code == 503
        l = await base.errores.find_one({}, {"_id": 0})
        assert l and l["status"] == 503 and "No pudimos" in l["mensaje"]
    corre(cuerpo())


def test_un_4xx_NO_se_asienta(base, servidor):
    """Un 404 o un 403 es el sistema diciendo que no, no algo roto. Si se
    asentaran, el registro sería ruido y el super administrador dejaría de
    mirarlo."""
    async def cuerpo():
        servidor.db = base
        for st in (400, 401, 403, 404, 429):
            r = await servidor._error_levantado_a_proposito(
                pedido(), HTTPException(status_code=st, detail="no"))
            assert r.status_code == st
        assert await base.errores.count_documents({}) == 0
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. Lista de lo permitido: jamás el cuerpo ni las cabeceras
# ══════════════════════════════════════════════════════════════════════════

def test_se_guarda_solo_lo_permitido(base, servidor):
    async def cuerpo():
        servidor.db = base
        try:
            raise ValueError("x")
        except ValueError as exc:
            await servidor._error_no_previsto(pedido(user_id="u_1"), exc)
        l = await base.errores.find_one({}, {"_id": 0})
        assert set(l.keys()) == LO_PERMITIDO, sorted(set(l.keys()) ^ LO_PERMITIDO)
        crudo = repr(l)
        assert "TOKEN-SECRETO" not in crudo, "la cabecera de autorización quedó guardada"
        assert "q=1" not in crudo, "la consulta quedó guardada"
    corre(cuerpo())


def test_los_manejadores_no_le_pasan_el_pedido_entero_a_anotar():
    """Mirando el árbol: ningún `anotar(...)` del servidor recibe `body`,
    `headers`, `query` ni el `request`. Una lista de lo permitido en el
    servicio no sirve si el que llama puede meter cualquier cosa."""
    fuente = pathlib.Path(_BACKEND, "server.py").read_text()
    arbol = ast.parse(fuente)
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "anotar"]
    assert len(llamadas) >= 2, "se fueron las llamadas a errores.anotar del servidor"
    for c in llamadas:
        nombres = {k.arg for k in c.keywords}
        prohibidos = nombres & {"body", "headers", "query", "request", "cuerpo", "cabeceras"}
        assert not prohibidos, f"anotar recibe {prohibidos} en la línea {c.lineno}"


# ══════════════════════════════════════════════════════════════════════════
# 4. Los secretos conocidos se tachan
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sucio,tiene_que_faltar", [
    ("mongodb+srv://ris:LaClave123@cluster.mongodb.net/ris", "LaClave123"),
    ("mongodb://ris:LaClave123@localhost:27017", "LaClave123"),
    ("invalid access token APP_USR-7885788152376066-091234-abcdef", "091234-abcdef"),
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGciOiJIUzI1NiJ9"),
    ("MERCADOPAGO_ACCESS_TOKEN=APP_USR-1234567890-xyz", "1234567890-xyz"),
    ("password=Hola123!", "Hola123!"),
])
def test_el_mensaje_no_guarda_secretos_conocidos(sucio, tiene_que_faltar):
    limpio = errores._limpiar(sucio, 500)
    assert tiene_que_faltar not in limpio, limpio


def test_lo_que_no_es_secreto_se_conserva():
    assert "ValueError: saldo insuficiente" in errores._limpiar("ValueError: saldo insuficiente", 500)


def test_el_mensaje_y_la_traza_tienen_tope(base):
    async def cuerpo():
        await errores.anotar(base, rastro="r", metodo="POST", ruta="/x", status=500,
                             tipo="E", mensaje="a" * 10_000, traza="b" * 100_000)
        l = await base.errores.find_one({}, {"_id": 0})
        assert len(l["mensaje"]) == errores.MAX_MENSAJE
        assert len(l["traza"]) == errores.MAX_TRAZA
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 5. Nunca levanta
# ══════════════════════════════════════════════════════════════════════════

def test_anotar_nunca_levanta_aunque_la_base_este_caida():
    class _Rota:
        def __getitem__(self, _):
            class _C:
                async def insert_one(self, *_):
                    raise RuntimeError("base caída")
            return _C()

    async def cuerpo():
        await errores.anotar(_Rota(), rastro="r", metodo="GET", ruta="/x",
                             status=500, tipo="E", mensaje="m")   # no levanta
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 6. Se borra solo, y la pantalla lee lo que hace falta
# ══════════════════════════════════════════════════════════════════════════

def test_el_registro_se_borra_solo_con_un_ttl():
    fuente = pathlib.Path(_BACKEND, "services", "errores.py").read_text()
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "preparar_indices")
    assert "expireAfterSeconds" in ast.unparse(fn), "se fue el índice TTL"
    assert errores.DIAS_QUE_SE_GUARDAN <= 90


def test_el_servidor_prepara_los_indices_al_arrancar():
    fuente = pathlib.Path(_BACKEND, "server.py").read_text()
    assert "errores.preparar_indices(db)" in fuente


def test_buscar_devuelve_de_mas_nuevo_a_mas_viejo_y_el_resumen_cuenta(base):
    async def cuerpo():
        for i in range(3):
            await errores.anotar(base, rastro=f"r{i}", metodo="POST",
                                 ruta="/api/a" if i < 2 else "/api/b",
                                 status=500, tipo="E", mensaje=str(i))
        r = await errores.buscar(base)
        assert r["total"] == 3
        assert [l["rastro"] for l in r["lineas"]] == ["r2", "r1", "r0"]
        s = await errores.resumen(base, horas=24)
        assert s["total"] == 3
        assert s["rutas"][0] == {"ruta": "/api/a", "cuantos": 2}
        solo_b = await errores.buscar(base, ruta="/api/b")
        assert solo_b["total"] == 1
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 7. La pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_la_pestana_existe_y_es_solo_del_super_administrador():
    # Las secciones y sus grupos viven en seccionesDelPanel.js desde que el
    # panel llegó a su tope de líneas; el dibujo sigue en AdminPanel.jsx.
    panel = _PANEL.read_text(encoding="utf-8") + "\n" + (
        _PANEL.parent.parent / "components" / "admin" / "seccionesDelPanel.js").read_text(encoding="utf-8")
    assert "key: 'errores'" in panel, "se fue la pestaña Errores"
    linea = next(l for l in panel.splitlines() if "key: 'errores'" in l)
    assert "superAdminOnly: true" in linea
    assert "'errores'" in next(l for l in panel.splitlines() if "hijas: ['servicios', 'configuracion'" in l)
    assert "<Errores />" in panel


def test_la_pantalla_pega_a_la_ruta_del_registro():
    assert _COMPONENTE.is_file()
    fuente = _COMPONENTE.read_text(encoding="utf-8")
    assert "/admin/errores/resumen" in fuente
    assert "api.get(`/admin/errores?" in fuente
