"""
tests/test_el_panel_por_servicio.py — El panel separado por servicio:
Plataforma, Remesas, Encomiendas y Banco, cada uno con su menú.

QUE SE CUIDA

    1. Que cada sección sea de UN servicio, el que corresponde. El reparto
       está escrito acá, sección por sección: mover una de servicio tiene
       que ser una decisión visible, no un renglón que pasa en un diff.
    2. Que el menú muestre sólo los grupos del servicio elegido. Si vuelve a
       mostrar todos, los botones de arriba quedan de adorno.
    3. Que la ruta que dice qué servicio está prendido lea las llaves de
       verdad, y que no se la dé a un cliente.
    4. Que la pantalla «Servicios» guarde por la ruta de Configuración y no
       por una puerta propia: con una segunda puerta, los seguros entre
       ajustes y los cuatro ojos del núcleo se podrían saltear.
"""
import asyncio
import os
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
_ADMIN = _BACKEND.parent / "frontend" / "src" / "components" / "admin"


def _leer(nombre):
    return (_ADMIN / nombre).read_text(encoding="utf-8")


def _grupos():
    """`{grupo: (servicio, [secciones])}` leído de seccionesDelPanel.js."""
    texto = _leer("seccionesDelPanel.js")
    bloque = texto[texto.index("export const GRUPOS = ["):]
    bloque = bloque[:bloque.index("\n];") + 3]
    salida = {}
    for grupo, servicio, hijas in re.findall(
            r"key: '(g_\w+)', servicio: '(\w+)'.*?hijas: \[([^\]]*)\]", bloque, re.S):
        salida[grupo] = (servicio, re.findall(r"'(\w+)'", hijas))
    assert salida, "no se encontró ningún grupo con servicio"
    return salida


def _servicio_de_cada_seccion():
    return {h: s for s, hijas in _grupos().values() for h in hijas}


# ══════════════════════════════════════════════════════════════════════════
# 1. El reparto
# ══════════════════════════════════════════════════════════════════════════

REMESAS = {"ordenes", "withdrawals", "recharges", "diferencias", "hoja_mp",
           "btc", "credits", "rates", "bancos", "cobros"}
ENCOMIENDAS = {"operacion", "envios"}
BANCO = {"nucleo"}


def test_LOS_CUATRO_SERVICIOS_Y_NINGUNO_MAS():
    texto = _leer("seccionesDelPanel.js")
    claves = re.findall(r"\{ key: '(\w+)', label: '[^']+', icon: \w+ \}",
                        texto[texto.index("SERVICIOS_DEL_PANEL = ["):texto.index("export const GRUPOS")])
    assert claves == ["plataforma", "remesas", "encomiendas", "banco"]
    assert {s for s, _ in _grupos().values()} == set(claves), (
        "hay un servicio sin grupos, o un grupo de un servicio que no existe")


def test_CADA_SECCION_ESTA_EN_SU_SERVICIO():
    de = _servicio_de_cada_seccion()
    for seccion, servicio in de.items():
        if seccion in REMESAS:
            esperado = "remesas"
        elif seccion in ENCOMIENDAS:
            esperado = "encomiendas"
        elif seccion in BANCO:
            esperado = "banco"
        else:
            esperado = "plataforma"
        assert servicio == esperado, f"«{seccion}» está en {servicio} y va en {esperado}"
    assert REMESAS | ENCOMIENDAS | BANCO <= set(de), "falta alguna sección en el menú"


def test_EL_BANCO_NO_COMPARTE_MENU_CON_NADIE():
    """El día que remesas se pause, la gerencia del banco no puede tener
    adentro nada de remesas, y al revés."""
    banco = [h for s, hijas in _grupos().values() if s == "banco" for h in hijas]
    assert banco == ["nucleo"]


def test_LA_SECCION_SERVICIOS_ES_DEL_SUPER_Y_SE_DIBUJA():
    texto = _leer("seccionesDelPanel.js")
    ficha = re.search(r"\{ key: 'servicios'[^}]*\}", texto)
    assert ficha and "superAdminOnly: true" in ficha.group(0)
    panel = (_BACKEND.parent / "frontend" / "src" / "pages" / "AdminPanel.jsx").read_text(encoding="utf-8")
    assert "{activeTab === 'servicios' && <ErrorBoundary clave=\"servicios\" donde=\"Servicios\"><Servicios /></ErrorBoundary>}" in panel


# ══════════════════════════════════════════════════════════════════════════
# 2. El menú
# ══════════════════════════════════════════════════════════════════════════

def test_EL_MENU_DIBUJA_SOLO_LOS_GRUPOS_DEL_SERVICIO_ELEGIDO():
    menu = _leer("MenuDelPanel.jsx")
    assert "const gruposDelServicio = gruposVisibles.filter((g) => g.servicio === servicioActual);" in menu
    assert "{gruposDelServicio.map((grupo) => {" in menu
    assert "{gruposVisibles.map((grupo) => {" not in menu, "volvió a dibujar todos los grupos juntos"


def test_EL_SERVICIO_SALE_DE_LA_SECCION_ABIERTA():
    """Llegando desde la campana o con `?tab=`, el botón correcto se enciende
    solo. Un estado aparte podría quedar mostrando Remesas con una sección
    del banco abierta."""
    menu = _leer("MenuDelPanel.jsx")
    assert "const servicioActual = SERVICIO_DE[activeTab] || serviciosVisibles[0]?.key;" in menu


def test_SOLO_SE_OFRECEN_LOS_SERVICIOS_QUE_LA_PERSONA_VE():
    menu = _leer("MenuDelPanel.jsx")
    assert re.search(r"const serviciosVisibles = SERVICIOS_DEL_PANEL\.filter\(\s*"
                     r"\(s\) => gruposVisibles\.some\(\(g\) => g\.servicio === s\.key\)\);", menu)
    assert "{serviciosVisibles.length > 1 && (" in menu


# ══════════════════════════════════════════════════════════════════════════
# 3. La ruta
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")


@pytest.fixture
def cliente(monkeypatch):
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "ris_test")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base
    from routes import dependencies
    from routes.admin import servicios as ruta

    base = mongomock_motor.AsyncMongoMockClient()["ris_servicios"]
    usar_base(base)
    monkeypatch.setattr(ruta, "db", base)
    app = FastAPI()
    app.include_router(ruta.router, prefix="/api")
    quien = {"rol": "agent"}

    def usuario():
        from models.user import User
        return User(user_id="u_1", name="X", email="x@ejemplo.test", role=quien["rol"])
    app.dependency_overrides[dependencies.get_current_user] = usuario
    return TestClient(app), base, quien


def test_TODO_EL_PERSONAL_VE_QUE_ESTA_PRENDIDO(cliente):
    c, base, quien = cliente
    r = c.get("/api/admin/servicios")
    assert r.status_code == 200, r.text
    servicios = {s["servicio"]: s for s in r.json()["servicios"]}
    assert list(servicios) == ["remesas", "encomiendas", "banco"]
    # De fábrica: remesas y encomiendas abiertas, el banco apagado.
    assert servicios["remesas"]["encendido"] is True
    assert servicios["encomiendas"]["encendido"] is True
    assert servicios["banco"]["encendido"] is False and servicios["banco"]["estado"] == "Apagado"
    assert [e["nombre"] for e in servicios["banco"]["estados"]] == ["Apagado", "Laboratorio", "Activo"]


def test_LEE_LAS_LLAVES_DE_VERDAD(cliente):
    from services import configuracion as cfg
    c, base, _ = cliente
    asyncio.run(cfg.escribir(base, "remesas_abiertas", 0))
    asyncio.run(cfg.escribir(base, "nucleo_modo", 1))
    servicios = {s["servicio"]: s for s in c.get("/api/admin/servicios").json()["servicios"]}
    assert servicios["remesas"]["encendido"] is False and servicios["remesas"]["estado"] == "En pausa"
    assert servicios["banco"]["encendido"] is True and servicios["banco"]["estado"] == "Laboratorio"


def test_UN_CLIENTE_NO_LA_VE(cliente):
    c, _, quien = cliente
    quien["rol"] = "user"
    assert c.get("/api/admin/servicios").status_code == 403


def test_CADA_SERVICIO_APUNTA_A_UNA_LLAVE_QUE_EXISTE():
    from services import configuracion as cfg
    from services import servicios
    for s in servicios.SERVICIOS:
        ajuste = cfg.AJUSTES[s.llave]
        assert [e.valor for e in s.estados] == list(range(ajuste.minimo, ajuste.maximo + 1)), (
            f"{s.clave}: los estados no cubren exactamente los valores de su llave")


# ══════════════════════════════════════════════════════════════════════════
# 4. La pantalla guarda por Configuración
# ══════════════════════════════════════════════════════════════════════════

def test_LA_PANTALLA_GUARDA_POR_LA_RUTA_DE_CONFIGURACION():
    pantalla = _leer("Servicios.jsx")
    assert "api.put('/admin/configuracion', { valores: { [servicio.llave]: String(estado.valor) } })" in pantalla
    assert "confirmar({" in pantalla, "apagar un servicio sin preguntar"
    assert "api.put('/admin/servicios" not in pantalla and "api.post('/admin/servicios" not in pantalla
    ruta = (_BACKEND / "routes" / "admin" / "servicios.py").read_text(encoding="utf-8")
    assert "@router.put" not in ruta and "@router.post" not in ruta, "la ruta de servicios sólo lee"
