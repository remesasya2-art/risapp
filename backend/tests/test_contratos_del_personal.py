"""
tests/test_contratos_del_personal.py — El personal se da de alta, se cambia y
se da de baja sólo por Recursos Humanos, y lo que el panel ve del personal
sale por un contrato. Ver routes/recursos_humanos.py y models/panel_personal.py.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")


def ya(c):
    return asyncio.run(c)


# ══════════════════════════════════════════════════════════════════════════
# 1. El camino viejo de alta de administradores no vuelve
# ══════════════════════════════════════════════════════════════════════════

def _rutas_de_la_app():
    """(método, camino) de todo lo que atiende la aplicación de verdad."""
    from _lote_c_comun import sin_webpush
    sin_webpush()
    import server
    return {(m, r.path) for r in server.app.routes for m in (getattr(r, "methods", None) or ())}


def test_EL_ALTA_CAMBIO_Y_BAJA_DE_ADMINISTRADORES_ES_SOLO_DE_RRHH():
    """`POST`, `PUT` y `DELETE /admin/sub-admins` se saltaban las reglas del
    personal: promovían a un cliente con saldo, no marcaban la cuenta como
    personal —y así el candado de la plata no la frenaba— y no dejaban
    rastro en el libro. Se sacaron; ver el bloque que las reemplaza en
    `admin_routes.py`. El alta, el cambio de permisos y la baja son de RRHH."""
    rutas = _rutas_de_la_app()
    volvieron = sorted(f"{m} {c}" for m, c in rutas
                       if "sub-admins" in c and m in ("POST", "PUT", "PATCH", "DELETE"))
    assert not volvieron, f"volvió el camino viejo de alta de administradores: {volvieron}"
    # Y la lectura se queda, igual que las puertas de RRHH: si el filtro de
    # arriba dejara de encontrar rutas, este test no probaría nada.
    assert ("GET", "/api/admin/sub-admins") in rutas
    for m, c in (("POST", "/api/admin/rrhh"), ("PUT", "/api/admin/rrhh/{user_id}/permisos"),
                 ("DELETE", "/api/admin/rrhh/{user_id}")):
        assert (m, c) in rutas, f"falta {m} {c}: RRHH es el único camino y tiene que estar"


# ══════════════════════════════════════════════════════════════════════════
# 2. Cada ruta del personal tiene su contrato
# ══════════════════════════════════════════════════════════════════════════

from test_contratos_de_acceso import _claves                    # noqa: E402
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta   # noqa: E402

RH = "routes/recursos_humanos.py"
RUTAS_DE_RRHH = [
    ("GET", "/permisos", "PermisosQueSePuedenDar"),
    ("GET", "", "ListaDelPersonal"),
    ("GET", "/{user_id}", "LegajoCompleto"),
    ("POST", "", "AltaDelPersonal"),
    ("POST", "/{user_id}/reenviar-invitacion", "InvitacionReenviada"),
    ("PUT", "/{user_id}/permisos", "PermisosCambiados"),
    ("PUT", "/{user_id}/legajo", "LegajoCambiado"),
    ("POST", "/{user_id}/reiniciar-dos-pasos", "SesionesCerradas"),
    ("DELETE", "/{user_id}", "SesionesCerradas"),
    ("GET", "/auditoria/libro", "LibroDeAuditoria"),
    ("GET", "/auditoria/acciones", "AccionesAuditables"),
]
# Las que arman su respuesta en el cuerpo de la ruta, con un diccionario a la
# vista: a ésas se les leen las claves del código.
CON_CLAVES_A_LA_VISTA = {"/{user_id}/reenviar-invitacion", "/{user_id}/permisos", "/{user_id}/legajo",
                         "/{user_id}/reiniciar-dos-pasos", "/{user_id}", ""}


@pytest.mark.parametrize("metodo,camino,modelo", RUTAS_DE_RRHH, ids=[f"{m} {c or '/'}" for m, c, _ in RUTAS_DE_RRHH])
def test_CADA_RUTA_DE_RRHH_TIENE_SU_CONTRATO(metodo, camino, modelo):
    ruta = _ruta(RH, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True
    if camino in CON_CLAVES_A_LA_VISTA:
        claves = _claves(RH, metodo, camino, None)
        faltan = claves - set(ruta.response_model.model_fields)
        assert not faltan, f"{camino or '/'} devuelve {sorted(faltan)} y su contrato no los tiene"


def test_LA_FICHA_Y_EL_ACCESO_SON_LOS_QUE_ARMA_RRHH():
    """`_ficha`, `_acceso` e `_invitar` arman lo que sale de cada persona. Sus
    claves, leídas del código, tienen que estar en el contrato."""
    from models import panel_personal as m
    from routes import recursos_humanos as rh
    from test_contratos_de_acceso import _claves_de_las_funciones
    assert _claves_de_las_funciones(RH, ["_ficha"]) - {"acceso"} <= set(m.FichaDelPersonal.model_fields)
    assert _claves_de_las_funciones(RH, ["_acceso"]) <= set(m.AccesoDelPersonal.model_fields)
    assert _claves_de_las_funciones(RH, ["_invitar"]) <= set(m.InvitacionEmitida.model_fields)
    assert set(rh.CAMPOS_DEL_LEGAJO) == set(m.LegajoDelPersonal.model_fields), "el legajo y su contrato se separaron"


def test_LAS_DOS_RUTAS_VIEJAS_QUE_QUEDAN_TIENEN_CONTRATO():
    for camino, modelo in (("/permissions-list", "CatalogoDePermisos"), ("/sub-admins", "Administradores")):
        (r,) = [r for r in __import__("admin_routes").admin_router.routes
                if r.path == "/api/admin" + camino and "GET" in r.methods]
        assert r.response_model is not None and r.response_model_exclude_unset is True, camino


# Lo que leen las pantallas de RRHH y del libro (RecursosHumanos.jsx y
# LibroAuditoria.jsx). Si un contrato lo pierde, la pantalla queda con un
# hueco y nadie se entera.
LO_QUE_LEEN_LAS_PANTALLAS = {
    "FichaDelPersonal": {"user_id", "email", "nombre", "rol", "activo", "permisos", "legajo", "alta", "baja",
                         "acceso"},
    "AccesoDelPersonal": {"clave_configurada", "dos_pasos", "invitacion"},
    "EstadoDeLaInvitacion": {"estado"},
    "LegajoDelPersonal": {"nombre_completo", "documento", "telefono", "cargo", "area", "fecha_ingreso", "notas"},
    "LegajoCompleto": {"ficha", "historial"},
    "LineaDelLibro": {"accion", "categoria", "etiqueta", "actor", "objetivo", "origen", "antes", "despues",
                      "detalle", "exito", "cuando", "cuando_caracas"},
    "ActorDeLaLinea": {"user_id", "email", "nombre", "rol"},
    "ObjetivoDeLaLinea": {"tipo", "id", "descripcion"},
    "OrigenDeLaLinea": {"ip", "pais", "navegador"},
    "LibroDeAuditoria": {"lineas", "total"},
    "AccionAuditable": {"accion", "categoria", "etiqueta"},
    "InvitacionEmitida": {"correo_enviado"},
    "SesionesCerradas": {"mensaje", "sesiones_cerradas"},
}


def test_LO_QUE_LEEN_RRHH_Y_EL_LIBRO_ESTA_EN_CADA_CONTRATO():
    from models import panel_personal as m
    for nombre, campos in LO_QUE_LEEN_LAS_PANTALLAS.items():
        faltan = campos - set(getattr(m, nombre).model_fields)
        assert not faltan, f"la pantalla lee {sorted(faltan)} de {nombre} y su contrato no lo tiene"


def test_LA_LISTA_DE_LO_QUE_LEEN_ESTA_EN_LAS_PANTALLAS():
    from _lote_c_comun import fuente
    texto = fuente("components/admin/RecursosHumanos.jsx") + fuente("components/admin/LibroAuditoria.jsx")
    sueltos = sorted({c for campos in LO_QUE_LEEN_LAS_PANTALLAS.values() for c in campos if c not in texto})
    assert not sueltos, f"las pantallas ya no leen {sueltos}"


# ══════════════════════════════════════════════════════════════════════════
# 3. Por HTTP, con una persona del equipo
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")

# Lo que vive en el documento de una persona del equipo y no es para mostrar.
SECRETOS = {"password_hash": "$2b$12$clave-del-personal", "two_factor_secret": "JBSWY3DPSECRETO",
            "pin_hash": "$2b$12$pin-del-personal", "backup_codes": ["codigo-de-respaldo-1"],
            "webauthn_credentials": [{"public_key": "CLAVE-PUBLICA-DEL-PERSONAL"}]}


@pytest.fixture
def rrhh(monkeypatch):
    import admin_routes
    from datetime import datetime, timezone
    from _lote_c_comun import SUPER, app_con
    from routes import dependencies as deps
    from routes import recursos_humanos as rh
    from services import personal
    c, base = app_con(rh.router, deps.get_super_admin, SUPER, "contratos_del_personal")
    c.app.include_router(admin_routes.admin_router)
    c.app.dependency_overrides[deps.get_admin_user] = lambda: SUPER
    monkeypatch.setattr(admin_routes, "db", base)
    # Los correos no salen: se contesta como si hubieran salido.
    async def _correo(*a, **k):
        return True
    monkeypatch.setattr(rh, "send_staff_invitation_email", _correo)
    monkeypatch.setattr(rh, "notify_dos_pasos_reiniciado", _correo)
    t = datetime(2026, 9, 20, tzinfo=timezone.utc)
    ya(base.users.insert_one({
        "user_id": "u_carla", "email": "carla@example.com", "name": "Carla", "role": "admin",
        personal.CAMPO: True, "is_active": True, "permissions": ["support.respond"],
        "password_set": True, "email_verified": True, "two_factor_enabled": True, "created_at": t,
        "legajo": {"nombre_completo": "Carla Pérez", "cargo": "Asesora", "area": "Soporte",
                   "dado_de_alta_en": t.isoformat()}, **SECRETOS}))
    return c, base


def _sin_secretos(texto):
    return [v for v in ("clave-del-personal", "JBSWY3DPSECRETO", "pin-del-personal", "codigo-de-respaldo",
                        "CLAVE-PUBLICA-DEL-PERSONAL") if v in texto]


def test_LA_LISTA_Y_EL_LEGAJO_POR_HTTP(rrhh):
    from _lote_c_comun import SUPER
    from routes import recursos_humanos as rh
    c, _ = rrhh
    r = c.get("/admin/rrhh")
    _igual_a_llamarla_directo(r, ya(rh.listar_personal(incluir_bajas=False, admin=SUPER)))
    (carla,) = r.json()["personal"]
    assert carla["legajo"]["cargo"] == "Asesora" and carla["acceso"]["dos_pasos"] is True
    assert not _sin_secretos(r.text)
    r = c.get("/admin/rrhh/u_carla")
    assert r.status_code == 200 and r.json()["ficha"]["user_id"] == "u_carla" and not _sin_secretos(r.text)


def test_CAMBIAR_PERMISOS_Y_LEGAJO_DEJA_UNA_LINEA_EN_EL_LIBRO_CON_SU_FORMA(rrhh):
    c, _ = rrhh
    r = c.put("/admin/rrhh/u_carla/permisos", json={"permisos": ["support.respond", "support.close"],
                                                   "motivo": "pasa a cerrar casos"})
    assert r.json() == {"mensaje": "Permisos actualizados", "permisos": ["support.close", "support.respond"]}
    r = c.put("/admin/rrhh/u_carla/legajo", json={"cargo": "Supervisora"})
    assert r.json() == {"mensaje": "Legajo actualizado", "cambios": {"cargo": "Supervisora"}}
    libro = c.get("/admin/rrhh/auditoria/libro")
    assert libro.status_code == 200 and libro.json()["total"] >= 2
    linea = next(x for x in libro.json()["lineas"] if x["antes"] and "permisos" in x["antes"])
    assert set(linea["actor"]) >= {"user_id", "nombre"} and linea["objetivo"]["id"] == "u_carla"
    assert linea["despues"]["permisos"] == ["support.close", "support.respond"], "lo que anota la acción sale entero"
    historial = c.get("/admin/rrhh/u_carla").json()["historial"]
    assert len(historial) >= 2 and all("cuando" in x for x in historial)
    assert c.get("/admin/rrhh/auditoria/acciones").json()["acciones"][0].keys() == {"accion", "categoria", "etiqueta"}


def test_DAR_DE_ALTA_Y_DE_BAJA_POR_HTTP(rrhh):
    c, _ = rrhh
    r = c.post("/admin/rrhh", json={"email": "nuevo@example.com", "nombre_completo": "Nuevo Asesor",
                                    "cargo": "Asesor", "area": "Soporte", "permisos": ["support.respond"]})
    assert r.status_code == 200, r.text
    alta = r.json()
    assert alta["user_id"] and alta["acceso"]["emitida"] is True and alta["acceso"]["correo_enviado"] is True
    assert "token" not in r.text.lower(), "la llave de la invitación no sale en la respuesta"
    r = c.post(f"/admin/rrhh/{alta['user_id']}/reenviar-invitacion")
    assert r.status_code == 200 and r.json()["acceso"]["emitida"] is True
    r = c.request("DELETE", "/admin/rrhh/u_carla", json={"motivo": "se fue de la empresa"})
    assert r.json() == {"mensaje": "Persona dada de baja", "sesiones_cerradas": 0}


def test_EL_CATALOGO_Y_LA_LISTA_DE_ADMINISTRADORES(rrhh):
    from _lote_c_comun import SUPER
    import admin_routes
    from services.permisos import CATALOGO, SERVICIO_DEL_PERMISO
    c, _ = rrhh
    # Con el servicio de cada permiso, para que RRHH los agrupe: ver
    # tests/test_permisos_por_servicio.py.
    assert c.get("/admin/rrhh/permisos").json() == {
        "permisos": CATALOGO, "servicio_de": SERVICIO_DEL_PERMISO}
    assert c.get("/api/admin/permissions-list").json() == CATALOGO
    r = c.get("/api/admin/sub-admins")
    assert r.status_code == 200 and not _sin_secretos(r.text)
    from fastapi.encoders import jsonable_encoder
    assert r.json() == jsonable_encoder(ya(admin_routes.get_sub_admins(admin_user=SUPER)))
