"""
tests/test_permisos_por_servicio.py — Los permisos ordenados por servicio, y
un menú que muestra lo que el servidor de verdad deja abrir.

QUE PASABA

    El panel decidía qué secciones mostrar mirando sólo el rol. Un
    colaborador veía Órdenes, Retiros, Recargas VES, Libro mayor y Reportes,
    entraba, y recibía un 403: esas rutas son del super administrador. Y al
    revés: una sección que pide un permiso se le mostraba aunque no lo tuviera.

QUE SE CUIDA ACA

    1. Que cada permiso del catálogo sea de un servicio.
    2. Que el permiso escrito en cada sección del menú sea EXACTAMENTE el que
       pide su ruta principal en `services/permisos.MAPA`. Si alguien cambia
       uno solo de los dos lados, el menú vuelve a mentir.
    3. Que las secciones marcadas «sólo super administrador» lo sean en el
       servidor, mirando la aplicación armada.
    4. Que `/admin/mi-acceso` le dé a cada quien lo suyo y nada a un cliente.
"""
import asyncio
import os
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
_SECCIONES = _BACKEND.parent / "frontend" / "src" / "components" / "admin" / "seccionesDelPanel.js"


def _fichas():
    """`{clave: línea}` de cada sección de seccionesDelPanel.js."""
    texto = _SECCIONES.read_text(encoding="utf-8")
    return {m.group(1): m.group(0) for m in re.finditer(r"\{ key: '(\w+)', label: [^\n]*\}", texto)}


# ══════════════════════════════════════════════════════════════════════════
# 1. El catálogo
# ══════════════════════════════════════════════════════════════════════════

def test_CADA_PERMISO_ES_DE_UN_SERVICIO():
    from services import permisos
    assert set(permisos.SERVICIO_DEL_PERMISO) == set(permisos.CATALOGO), (
        "un permiso sin servicio no aparece bajo ningún título en RRHH, o hay "
        "un servicio asignado a un permiso que ya no existe")
    assert set(permisos.SERVICIO_DEL_PERMISO.values()) <= {
        "plataforma", "remesas", "encomiendas", "banco"}


def test_LOS_DE_ENCOMIENDAS_Y_LOS_QUE_MUEVEN_PLATA_DE_REMESAS():
    from services import permisos
    s = permisos.SERVICIO_DEL_PERMISO
    assert {p for p, v in s.items() if v == "encomiendas"} == {"envios.view", "envios.operar", "envios.dinero"}
    assert s["saldos.ajustar"] == s["recharges.approve"] == "remesas"


def test_RRHH_ENTREGA_EL_SERVICIO_DE_CADA_PERMISO():
    from routes import recursos_humanos
    from services import permisos
    salida = asyncio.run(recursos_humanos.catalogo_de_permisos(admin=None))
    assert salida["servicio_de"] == permisos.SERVICIO_DEL_PERMISO
    from models.panel_personal import PermisosQueSePuedenDar
    assert PermisosQueSePuedenDar(**salida).model_dump()["servicio_de"], "el contrato lo tira"


def test_LA_PANTALLA_DE_RRHH_LOS_AGRUPA():
    rrhh = (_SECCIONES.parent / "RecursosHumanos.jsx").read_text(encoding="utf-8")
    assert "servicioDe: cat.data?.servicio_de || {}" in rrhh
    assert "{conTitulos(permisos, servicioDe).map(([clave, etiqueta, titulo]) => {" in rrhh


# ══════════════════════════════════════════════════════════════════════════
# 2 y 3. El menú dice lo mismo que el servidor
# ══════════════════════════════════════════════════════════════════════════

# Cada sección con permiso, y la ruta que abre al entrar.
RUTA_PRINCIPAL = {
    "users": ("GET", "/api/admin/users"),
    "kyc": ("GET", "/api/admin/kyc/list"),
    "blacklist": ("GET", "/api/admin/blacklist"),
    "chat": ("GET", "/api/admin/soporte/casos"),
    "support": ("GET", "/api/admin/support-requests"),
    "hoja_mp": ("GET", "/api/admin/hoja-mercadopago"),
    "rates": ("GET", "/api/admin/bcv-rates"),
    "operacion": ("GET", "/api/admin/envios/envios/cola"),
}

# Las que el servidor reserva al super administrador y el menú mostraba igual.
DEL_SUPER_EN_EL_SERVIDOR = {
    "ordenes": "/api/admin/ordenes/pendientes",
    "withdrawals": "/api/admin/withdrawals/all",
    "recharges": "/api/admin/recharges/ves",
    "ledger": "/api/admin/ledger/balance",
    "reportes": "/api/admin/reportes",
}


def test_EL_PERMISO_DE_CADA_SECCION_ES_EL_DE_SU_RUTA():
    from services import permisos
    fichas = _fichas()
    for seccion, (metodo, camino) in RUTA_PRINCIPAL.items():
        m = re.search(r"permiso: '([\w.]+)'", fichas[seccion])
        assert m, f"«{seccion}» no dice qué permiso pide"
        assert m.group(1) == permisos.MAPA[(metodo, camino)], (
            f"«{seccion}» dice {m.group(1)} y su ruta pide {permisos.MAPA[(metodo, camino)]}")


def test_TODA_SECCION_CON_PERMISO_ESTA_REVISADA_ACA():
    """Una sección nueva con `permiso` y sin su ruta en la tabla de arriba
    escaparía a la comprobación."""
    con_permiso = {c for c, l in _fichas().items() if "permiso:" in l}
    assert con_permiso == set(RUTA_PRINCIPAL)


def _nombres_de_dependencias(dependant, visto=None):
    visto = visto if visto is not None else set()
    salida = []
    for d in getattr(dependant, "dependencies", []) or []:
        if id(d) in visto:
            continue
        visto.add(id(d))
        if getattr(d, "call", None):
            salida.append(d.call.__name__)
        salida.extend(_nombres_de_dependencias(d, visto))
    return salida


def test_LAS_SECCIONES_DEL_SUPER_LO_SON_EN_EL_SERVIDOR():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "ris_test")
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {e}")
    rutas = {r.path: r for r in app.routes if "GET" in (getattr(r, "methods", None) or ())}
    fichas = _fichas()
    for seccion, camino in DEL_SUPER_EN_EL_SERVIDOR.items():
        assert "superAdminOnly: true" in fichas[seccion], f"«{seccion}» se le muestra a quien no la puede abrir"
        assert "get_super_admin" in _nombres_de_dependencias(rutas[camino].dependant), (
            f"{camino} ya no es sólo del super: revisá si «{seccion}» tiene que dejar de serlo")


def test_EL_MENU_FILTRA_CON_LOS_PERMISOS():
    texto = _SECCIONES.read_text(encoding="utf-8")
    funcion = texto[texto.index("export function puedeVerSeccion("):]
    assert "if (rol === 'super_admin') return true;" in funcion
    assert "if (!s || s.superAdminOnly) return false;" in funcion
    assert "return !s.permiso || (permisos || []).includes(s.permiso);" in funcion
    menu = (_SECCIONES.parent / "MenuDelPanel.jsx").read_text(encoding="utf-8")
    assert "api.get('/admin/mi-acceso')" in menu
    assert "puedeVerSeccion(c, user?.role, permisos)" in menu


# ══════════════════════════════════════════════════════════════════════════
# 4. /admin/mi-acceso
# ══════════════════════════════════════════════════════════════════════════

pytest.importorskip("mongomock_motor")


@pytest.fixture
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.user import User
    from routes import dependencies
    from routes.admin import servicios as ruta

    app = FastAPI()
    app.include_router(ruta.router, prefix="/api")
    quien = {"rol": "admin", "permisos": ["kyc.view", "envios.view"]}
    app.dependency_overrides[dependencies.get_current_user] = lambda: User(
        user_id="u_1", name="X", email="x@ejemplo.test",
        role=quien["rol"], permissions=quien["permisos"])
    return TestClient(app), quien


def test_CADA_UNO_RECIBE_LO_SUYO(cliente):
    c, _ = cliente
    r = c.get("/api/admin/mi-acceso")
    assert r.status_code == 200
    assert r.json() == {"rol": "admin", "permisos": ["kyc.view", "envios.view"]}


def test_UN_CLIENTE_NO_RECIBE_NADA(cliente):
    c, quien = cliente
    quien["rol"], quien["permisos"] = "user", []
    assert c.get("/api/admin/mi-acceso").status_code == 403
