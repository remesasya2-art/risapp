"""
tests/test_contratos_de_la_mesa_de_ayuda.py — Lo que el panel ve de la mesa de
ayuda sale por un contrato, y ningún contrato se come un campo que la consola
lee. Ver models/panel_soporte.py.

La lectura de las claves desde el código es la de las acciones del cliente
(`test_contratos_de_acceso._claves`), y la búsqueda de la ruta la del panel
(`test_contratos_del_panel._ruta`): una sola de cada una.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves                    # noqa: E402
from test_contratos_del_panel import _igual_a_llamarla_directo, _ruta   # noqa: E402

S = "routes/soporte.py"

# (método, camino, contrato) de lo que el asesor HACE.
ACCIONES = [
    ("POST", "/admin/soporte/casos/{caso_id}/tomar", "CasoTomado"),
    ("POST", "/admin/soporte/casos/{caso_id}/soltar", "AccionDeSoporte"),
    ("POST", "/admin/soporte/casos/{caso_id}/mensajes", "MensajeDelAsesor"),
    ("POST", "/admin/soporte/casos/{caso_id}/estado", "EstadoDelCaso"),
    ("POST", "/admin/soporte/casos/{caso_id}/prioridad", "AccionDeSoporte"),
    ("POST", "/admin/soporte/casos/{caso_id}/transferir", "CasoTransferido"),
    ("POST", "/admin/soporte/casos/{caso_id}/escalar", "AccionDeSoporte"),
    ("POST", "/admin/soporte/casos/{caso_id}/pedidos", "PedidoHecho"),
    ("POST", "/admin/soporte/pedidos/{pedido_id}/responder", "AccionDeSoporte"),
    ("POST", "/admin/quick-replies", "RespuestaRapidaCreada"),
    ("DELETE", "/admin/quick-replies/{qr_id}", "AccionDeSoporte"),
]
# Y lo que LEE.
LECTURAS = [
    ("GET", "/admin/soporte/areas", "AreasDeSoporte"),
    ("GET", "/admin/soporte/asesores", "Asesores"),
    ("GET", "/admin/soporte/casos", "BandejaDelAsesor"),
    ("GET", "/admin/soporte/casos/{caso_id}", "CasoCompleto"),
    ("GET", "/admin/soporte/pedidos", "PedidosDeMiArea"),
]
_IDS = [f"{m} {c}" for m, c, _ in ACCIONES]


@pytest.mark.parametrize("metodo,camino,modelo", ACCIONES + LECTURAS,
                         ids=[f"{m} {c}" for m, c, _ in ACCIONES + LECTURAS])
def test_CADA_RUTA_DE_LA_MESA_DE_AYUDA_TIENE_SU_CONTRATO(metodo, camino, modelo):
    ruta = _ruta(S, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def test_LAS_RESPUESTAS_RAPIDAS_SON_UNA_LISTA_CON_CONTRATO():
    """La pantalla lee la respuesta como una lista pelada (`r.data || []`):
    el contrato no la envuelve en un objeto."""
    ruta = _ruta(S, "router", "GET", "/admin/quick-replies")
    assert ruta.response_model.__origin__ is list
    assert ruta.response_model.__args__[0].__name__ == "RespuestaRapida"


@pytest.mark.parametrize("metodo,camino,modelo", ACCIONES, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_ACCION_DEVUELVE(metodo, camino, modelo):
    claves = _claves(S, metodo, camino, None)
    assert claves, f"no encontré qué devuelve {camino}: sin claves este test no prueba nada"
    faltan = claves - set(_ruta(S, "router", metodo, camino).response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene: la consola los perdería"


# ══════════════════════════════════════════════════════════════════════════
# Lo que la consola lee
# ══════════════════════════════════════════════════════════════════════════

# Buscado en frontend/src/components/admin/MesaDeAyuda.jsx y utils/soporte.js
# (el semáforo, y quién puede tomar, soltar o responder). Si un contrato lo
# pierde, la consola queda con un hueco y nadie se entera.
LO_QUE_LEE_LA_CONSOLA = {
    "caso": {"caso_id", "numero", "asunto", "estado", "prioridad", "user_name", "asignado_a",
             "asignado_a_nombre", "escalado", "escalado_motivo", "escalado_por_nombre", "creado_en",
             "ultimo_mensaje_en", "ultimo_mensaje_de", "primera_respuesta_en", "sin_leer_asesor",
             "calificacion"},
    "mensaje": {"mensaje_id", "autor", "autor_nombre", "interno", "texto", "adjunto", "creado_en"},
    "pedido": {"pedido_id", "caso_numero", "detalle", "estado", "pedido_por_nombre", "creado_en", "respuesta"},
    "cliente": {"name", "balance_ris", "verification_status"},
    "operacion": {"transaction_id", "type", "amount"},
    "asesor": {"user_id", "nombre", "cargo"},
    "area": {"clave", "nombre"},
    "rapida": {"qr_id", "text"},
}


def test_LO_QUE_LA_CONSOLA_LEE_ESTA_EN_CADA_CONTRATO():
    from models import panel_soporte as m
    contratos = {"caso": m.CasoQueVeElAsesor, "mensaje": m.MensajeQueVeElAsesor, "pedido": m.PedidoAUnArea,
                 "cliente": m.ClienteDelCaso, "operacion": m.OperacionDelCliente, "asesor": m.Asesor,
                 "area": m.AreaDeSoporte, "rapida": m.RespuestaRapida}
    for que, campos in LO_QUE_LEE_LA_CONSOLA.items():
        faltan = campos - set(contratos[que].model_fields)
        assert not faltan, f"la consola lee {sorted(faltan)} de {que} y su contrato no lo tiene"
    completo = set(m.CasoCompleto.model_fields)
    assert {"caso", "mensajes", "pedidos", "cliente", "operaciones", "casos_previos"} <= completo


def test_LA_LISTA_DE_LO_QUE_LEE_LA_CONSOLA_ESTA_EN_LA_CONSOLA():
    """La lista de arriba no está inventada: cada campo aparece en la consola
    o en sus ayudantes. Sin esto, un campo que la pantalla dejó de leer
    seguiría obligando al contrato a tenerlo."""
    from _lote_c_comun import fuente
    texto = fuente("components/admin/MesaDeAyuda.jsx") + fuente("utils/soporte.js")
    sueltos = sorted({c for campos in LO_QUE_LEE_LA_CONSOLA.values() for c in campos if c not in texto})
    assert not sueltos, f"la consola ya no lee {sueltos}"


# ══════════════════════════════════════════════════════════════════════════
# Por HTTP, con un caso de ejemplo
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")

T = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def mesa(monkeypatch):
    """Un caso escalado, con una respuesta, una nota interna, un pedido a
    Finanzas, y un cliente con saldo guardado como lo guarda la aplicación.

    El caso trae lo que la ruta no tiene que mostrar: quién lo escaló y lo
    cerró por su identificador, y el chat viejo del que vino."""
    from _lote_c_comun import SUPER, app_con
    from routes import dependencies as deps
    from routes import soporte as rs
    from services.money import to_decimal128
    c, base = app_con(rs.router, deps.get_crm_user, SUPER, "mesa_de_ayuda")
    # El reloj quieto: la bandeja calcula minutos, y la comparación con la
    # función llamada a mano no puede depender de en qué segundo corre.
    monkeypatch.setattr(rs, "_AHORA", lambda: T)
    ya(base.soporte_casos.insert_one({
        "caso_id": "c1", "numero": "S-000007", "user_id": "u_ana", "user_name": "Ana",
        "user_email": "ana@example.com", "motivo": "envio", "asunto": "¿Dónde está mi envío?",
        "estado": "en_curso", "prioridad": "urgente", "area": "soporte",
        "asignado_a": SUPER.user_id, "asignado_a_nombre": "Jefa", "asignado_en": T,
        "escalado": True, "escalado_motivo": "cliente sospechoso", "escalado_por": "u_jefe_secreto",
        "escalado_por_nombre": "Jefe de turno", "escalado_en": T, "cerrado_por": "u_cierre_secreto",
        "origen_chat": "u_chat_viejo", "creado_en": T, "actualizado_en": T,
        "ultimo_mensaje": "¿Dónde está mi envío?", "ultimo_mensaje_en": T, "ultimo_mensaje_de": "cliente",
        "primera_respuesta_en": None, "sin_leer_asesor": 0, "sin_leer_cliente": 0,
        "calificacion": {"estrellas": 4, "comentario": "bien", "en": T}}))
    ya(base.soporte_mensajes.insert_many([
        {"mensaje_id": "m1", "caso_id": "c1", "autor": "cliente", "autor_id": "u_ana", "autor_nombre": "Ana",
         "interno": False, "texto": "¿Dónde está mi envío?", "adjunto": None, "creado_en": T},
        {"mensaje_id": "m2", "caso_id": "c1", "autor": "asesor", "autor_id": SUPER.user_id,
         "autor_nombre": "Jefa", "interno": True, "texto": "revisar origen", "adjunto": None,
         "creado_en": T + timedelta(minutes=1), "ip_del_asesor": "10.0.0.7"}]))
    ya(base.soporte_pedidos.insert_one({
        "pedido_id": "p1", "caso_id": "c1", "caso_numero": "S-000007", "area": "finanzas",
        "detalle": "¿salió el pago?", "estado": "pendiente", "pedido_por": "u_pide_secreto",
        "pedido_por_nombre": "Jefa", "creado_en": T, "respuesta": None}))
    ya(base.users.insert_one({
        "user_id": "u_ana", "name": "Ana", "email": "ana@example.com", "balance_ris": to_decimal128("80.50"),
        "verification_status": "verified", "password_hash": "$2b$12$clave", "two_factor_secret": "JBSWY3DP"}))
    ya(base.transactions.insert_one({
        "transaction_id": "tx_1", "user_id": "u_ana", "type": "withdrawal", "status": "completed",
        "amount": to_decimal128("20.00"), "currency": "RIS", "created_at": T, "nota_interna": "ojo"}))
    return c, base


LO_QUE_NO_SALE = ("u_jefe_secreto", "u_cierre_secreto", "u_chat_viejo", "u_pide_secreto", "10.0.0.7",
                  "$2b$12$clave", "JBSWY3DP", "nota_interna")


def test_LA_BANDEJA_ES_LA_DE_SIEMPRE_MENOS_LO_INTERNO(mesa):
    from _lote_c_comun import SUPER
    from routes import soporte as rs
    c, _ = mesa
    r = c.get("/admin/soporte/casos")
    directo = ya(rs.bandeja(estado=None, area=None, mios=False, buscar=None, current_user=SUPER))
    for caso in directo["casos"]:
        for k in ("escalado_por", "cerrado_por", "origen_chat"):
            caso.pop(k, None)
    _igual_a_llamarla_directo(r, directo)
    assert not [x for x in LO_QUE_NO_SALE if x in r.text]
    (caso,) = r.json()["casos"]
    assert caso["semaforo"] and caso["minutos_esperando"] is not None and caso["calificacion"]["estrellas"] == 4


def test_EL_CASO_TRAE_LA_CONVERSACION_Y_LA_FICHA_SIN_LO_INTERNO(mesa):
    c, _ = mesa
    r = c.get("/admin/soporte/casos/c1")
    assert r.status_code == 200, r.text
    d = r.json()
    assert not [x for x in LO_QUE_NO_SALE if x in r.text], "salió algo que no tenía que salir"
    assert d["caso"]["escalado_por_nombre"] == "Jefe de turno" and d["caso"]["asignado_a"]
    assert [m["mensaje_id"] for m in d["mensajes"]] == ["m1", "m2"] and d["mensajes"][1]["interno"] is True
    assert "caso_id" not in d["mensajes"][0]
    assert d["pedidos"][0]["pedido_por_nombre"] == "Jefa" and "pedido_por" not in d["pedidos"][0]
    # La plata guardada en Decimal128 sale como número, no como error.
    assert d["cliente"]["balance_ris"] == 80.5 and d["operaciones"][0]["amount"] == 20.0
    assert d["casos_previos"] == 0


def test_LOS_PEDIDOS_DE_MI_AREA_Y_LOS_CATALOGOS(mesa):
    from _lote_c_comun import SUPER
    from routes import soporte as rs
    c, _ = mesa
    r = c.get("/admin/soporte/pedidos")
    directo = ya(rs.pedidos_de_mi_area(pendientes=True, current_user=SUPER))
    for p in directo["pedidos"]:
        p.pop("pedido_por")
    _igual_a_llamarla_directo(r, directo)
    _igual_a_llamarla_directo(c.get("/admin/soporte/areas"), ya(rs.areas(current_user=SUPER)))
    assert c.get("/admin/soporte/asesores").status_code == 200


def test_LAS_RESPUESTAS_RAPIDAS_SIN_QUIEN_LAS_ESCRIBIO(mesa):
    c, _ = mesa
    r = c.post("/admin/quick-replies", json={"text": "Ya lo reviso"})
    assert r.status_code == 200 and r.json()["success"] is True and r.json()["text"] == "Ya lo reviso"
    lista = c.get("/admin/quick-replies")
    assert lista.status_code == 200 and isinstance(lista.json(), list)
    assert "Ya lo reviso" in [x["text"] for x in lista.json()]
    assert all(set(x) == {"qr_id", "text", "created_by_name", "created_at"} for x in lista.json())
    assert c.delete(f"/admin/quick-replies/{r.json()['qr_id']}").json() == {"success": True}


def test_LAS_ACCIONES_DEL_ASESOR_POR_HTTP(mesa):
    """Cada acción de la consola, en el orden en que se usan, contesta lo
    mismo que contestaba sin contrato."""
    c, base = mesa
    u = "/admin/soporte/casos/c1"
    assert c.post(f"{u}/tomar").json() == {"success": True, "ya_era_mio": True}
    assert c.post(f"{u}/mensajes", json={"mensaje": "nota", "interno": True}).json() == {
        "success": True, "interno": True}
    assert c.post(f"{u}/mensajes", json={"mensaje": "Ya sale"}).json() == {"success": True}
    assert c.post(f"{u}/prioridad", json={"prioridad": "alta"}).json() == {"success": True}
    pedido = c.post(f"{u}/pedidos", json={"area": "finanzas", "detalle": "¿Salió el pago de ayer?"}).json()
    assert pedido["success"] is True and pedido["pedido"]["detalle"] == "¿Salió el pago de ayer?"
    assert "pedido_por" not in pedido["pedido"] and pedido["pedido"]["pedido_por_nombre"]
    assert c.post(f"/admin/soporte/pedidos/{pedido['pedido']['pedido_id']}/responder",
                  json={"respuesta": "Sí"}).json() == {"success": True}
    assert c.post(f"{u}/estado", json={"estado": "resuelto"}).json() == {"success": True, "estado": "resuelto"}
    assert c.post(f"{u}/soltar").json() == {"success": True}
    assert c.post(f"{u}/transferir", json={"area": "finanzas", "nota": "Lo ve Finanzas"}).json() == {
        "success": True, "area": "finanzas", "asignado_a": None}


# ══════════════════════════════════════════════════════════════════════════
# La bandeja vieja (pedidos de ayuda sin cuenta) y las calificaciones
# ══════════════════════════════════════════════════════════════════════════

A = "routes/admin/soporte.py"
VIEJAS = [
    ("GET", "/support-requests", "SolicitudesDeAyuda"),
    ("POST", "/support-requests/{request_id}/resolve", "SolicitudResuelta"),
    ("POST", "/support-requests/{request_id}/reply", "RespuestaPorCorreo"),
    ("POST", "/support-requests/{request_id}/claim", "SolicitudTomada"),
    ("POST", "/support-requests/{request_id}/release", "AccionDeSoporte"),
    ("POST", "/support-requests/{request_id}/priority", "PrioridadDeLaSolicitud"),
    ("GET", "/agent-ratings", "CalificacionesPorAsesor"),
]


@pytest.mark.parametrize("metodo,camino,modelo", VIEJAS, ids=[f"{m} {c}" for m, c, _ in VIEJAS])
def test_LA_BANDEJA_VIEJA_Y_LAS_CALIFICACIONES_TIENEN_CONTRATO(metodo, camino, modelo):
    ruta = _ruta(A, "router", metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True
    faltan = _claves(A, metodo, camino, None) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


# Buscado en frontend/src/pages/AdminPanel.jsx (pestañas «Soporte» y
# «Calificaciones»).
LO_QUE_LEE_LA_PESTANA_SOPORTE = {"support_id", "status", "email", "message", "subject", "assigned_to",
                                 "assigned_to_name", "case_code", "created_at", "phone_number",
                                 "responded_at", "priority"}
LO_QUE_LEEN_LAS_CALIFICACIONES = {"agent_id", "agent_name", "average", "count", "ratings"}
LO_QUE_LEE_DE_CADA_CALIFICACION = {"case_code", "channel", "comment", "created_at", "stars"}


def test_LO_QUE_LEEN_LAS_PESTANAS_VIEJAS_ESTA_EN_SU_CONTRATO():
    from _lote_c_comun import fuente
    from models import panel_soporte as m
    assert LO_QUE_LEE_LA_PESTANA_SOPORTE <= set(m.SolicitudDeAyuda.model_fields)
    assert LO_QUE_LEEN_LAS_CALIFICACIONES <= set(m.CalificacionesDeUnAsesor.model_fields)
    assert LO_QUE_LEE_DE_CADA_CALIFICACION <= set(m.CalificacionRecibida.model_fields)
    texto = fuente("pages/AdminPanel.jsx")
    todos = LO_QUE_LEE_LA_PESTANA_SOPORTE | LO_QUE_LEEN_LAS_CALIFICACIONES | LO_QUE_LEE_DE_CADA_CALIFICACION
    assert not sorted(c for c in todos if c not in texto)


@pytest.fixture
def bandeja_vieja():
    from _lote_c_comun import SUPER, app_con
    from routes.admin import soporte as rutas_admin
    from routes import dependencies as deps
    c, base = app_con(rutas_admin.router, deps.get_crm_user, SUPER, "bandeja_vieja")
    c.app.dependency_overrides[deps.get_super_admin] = lambda: SUPER
    ya(base.support_requests.insert_one({
        "support_id": "sup_1", "case_number": 12, "case_code": "TKT-000012", "email": "luis@example.com",
        "subject": "No puedo entrar", "phone_number": "+58 412 0000000", "message": "Perdí el teléfono",
        "status": "pending", "created_at": T, "resolved_by": "u_resolvio_secreto",
        "responded_by": "u_respondio_secreto", "responded_at": T,
        "replies": [{"message": "texto de la respuesta vieja", "admin_id": "u_admin_secreto"}]}))
    ya(base.ratings.insert_many([
        {"rating_id": "r1", "channel": "caso", "case_ref": "c1", "case_code": "S-000007",
         "agent_id": "u_carla", "agent_name": "Carla", "stars": 5, "comment": "Rápida", "created_at": T},
        {"rating_id": "r2", "channel": "caso", "case_ref": "c2", "case_code": "S-000008",
         "agent_id": "u_carla", "agent_name": "Carla", "stars": 3, "comment": "", "created_at": T}]))
    return c


def test_LA_BANDEJA_VIEJA_SIN_LAS_RESPUESTAS_NI_LOS_IDENTIFICADORES(bandeja_vieja):
    from _lote_c_comun import SUPER
    from routes.admin import soporte as rutas_admin
    c = bandeja_vieja
    r = c.get("/admin/support-requests")
    directo = ya(rutas_admin.get_support_requests(admin=SUPER))
    for pedido in directo["requests"]:
        for k in ("resolved_by", "responded_by", "replies"):
            pedido.pop(k, None)
    _igual_a_llamarla_directo(r, directo)
    for secreto in ("u_resolvio_secreto", "u_respondio_secreto", "u_admin_secreto", "respuesta vieja"):
        assert secreto not in r.text, secreto


def test_LAS_ACCIONES_DE_LA_BANDEJA_VIEJA_POR_HTTP(bandeja_vieja):
    from _lote_c_comun import SUPER
    c = bandeja_vieja
    u = "/admin/support-requests/sup_1"
    assert c.post(f"{u}/claim").json() == {"success": True, "assigned_to": SUPER.user_id,
                                          "assigned_to_name": SUPER.name}
    assert c.post(f"{u}/claim").json()["already_mine"] is True
    assert c.post(f"{u}/priority", json={"priority": "alta"}).json() == {"success": True, "priority": "alta"}
    assert c.post(f"{u}/release").json() == {"success": True}
    assert c.post(f"{u}/resolve").json() == {"message": "Solicitud marcada como resuelta"}


def test_LAS_CALIFICACIONES_SON_LAS_DE_SIEMPRE(bandeja_vieja):
    from _lote_c_comun import SUPER
    from routes.admin import soporte as rutas_admin
    r = bandeja_vieja.get("/admin/agent-ratings")
    _igual_a_llamarla_directo(r, ya(rutas_admin.get_agent_ratings(admin=SUPER)))
    (carla,) = r.json()["agents"]
    assert carla["average"] == 4.0 and carla["count"] == 2 and len(carla["ratings"]) == 2
