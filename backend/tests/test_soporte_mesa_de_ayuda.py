"""
tests/test_soporte_mesa_de_ayuda.py — Las guardas del lado del asesor.

POR QUE ESTE ARCHIVO

    Los cuatro defectos que cubre son de la misma familia: reglas que existían
    en la pantalla y no en el servidor, o comprobaciones que se hacían leyendo
    y después escribiendo. Ninguno rompe nada a la vista. El peor de los cuatro
    —un caso asignado a alguien que no puede atenderlo— no produce ni un error:
    el caso simplemente sale de la cola de todo el equipo y el cliente sigue
    esperando.

    `MesaDeAyuda.jsx` promete en su cabecera que «si un botón se ofrece, el
    servidor lo va a aceptar». Eso sólo se sostiene si la regla vive en el
    servidor y la pantalla la espeja. Estos tests sostienen ese lado.
"""
import asyncio
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")


def _ya(corrutina):
    """`asyncio.run` y no el lazo global, que otro archivo de la suite cierra."""
    return asyncio.run(corrutina)


def _sin_webpush():
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


from models.user import User                                          # noqa: E402

CLIENTA = User(user_id="u_ana", name="Ana Cliente", email="ana@t.com", role="user")
BETO = User(user_id="s_beto", name="Beto Asesor", email="beto@t.com", role="agent",
            permissions=["support.view", "support.respond", "support.close",
                         "support.pedidos"])
CARO = User(user_id="s_caro", name="Caro Asesora", email="caro@t.com", role="agent",
            permissions=["support.view", "support.respond", "support.close"])


def _mesa(nombre):
    """La aplicación real, la base limpia, y el asesor en sesión intercambiable."""
    _sin_webpush()
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.soporte import router
    from routes import dependencies as deps

    app = FastAPI()
    app.include_router(router, prefix="/api")
    actual = {"u": None}
    app.dependency_overrides[deps.get_current_user] = lambda: actual["u"]
    app.dependency_overrides[deps.get_crm_user] = lambda: actual["u"]
    return TestClient(app), actual, base


async def _gente(base):
    """Quién es quién en la base: dos del equipo, una clienta, dos de baja."""
    await base.users.insert_many([
        {"user_id": "u_ana", "name": "Ana Cliente", "role": "user", "is_active": True},
        {"user_id": "s_beto", "name": "Beto Asesor", "role": "agent", "is_active": True},
        {"user_id": "s_caro", "name": "Caro Asesora", "role": "agent", "is_active": True},
        {"user_id": "s_ex", "name": "Ex Empleado", "role": "agent", "is_active": False},
        {"user_id": "sa_hoy", "name": "Super de hoy", "role": "super_admin", "is_active": True},
        {"user_id": "sa_baja", "name": "Super de baja", "role": "super_admin", "is_active": False},
    ])


def _abrir(cliente, actual, base):
    """Un caso abierto por la clienta y tomado por Beto."""
    _ya(_gente(base))
    actual["u"] = CLIENTA
    caso = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Mi envío no llegó al beneficiario"}).json()["caso"]
    actual["u"] = BETO
    cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/tomar")
    return caso["caso_id"]


# ══════════════════════════════════════════════════════════════════════════
# 1. Un caso no se le transfiere a quien no puede atenderlo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("destino,quien", [
    ("u_ana", "la clienta del propio caso"),
    ("s_ex", "un empleado dado de baja"),
])
def test_no_se_transfiere_un_caso_a_quien_no_es_del_equipo(destino, quien):
    """El defecto: se preguntaba si el destinatario EXISTE, no si es del equipo.

    El `role` ya venía de la base —estaba en la proyección— y nadie lo miraba.
    """
    cliente, actual, base = _mesa(f"ris_tr_{destino}")
    caso_id = _abrir(cliente, actual, base)

    r = cliente.post(f"/api/admin/soporte/casos/{caso_id}/transferir", json={
        "area": "soporte", "asesor_id": destino,
        "nota": "Te paso el caso, mirá el comprobante adjunto"})
    assert r.status_code == 400, f"se transfirió el caso a {quien}: {r.text}"

    async def revisar():
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] == "s_beto", "el caso cambió de dueño igual"

    _ya(revisar())


def test_la_nota_interna_de_la_transferencia_no_le_llega_al_cliente():
    """La otra mitad del mismo defecto, y la que no se ve.

    El aviso de transferencia lleva la nota del asesor —información de la casa,
    con su nombre— y salía derecho a la bandeja del cliente.
    """
    cliente, actual, base = _mesa("ris_tr_aviso")
    caso_id = _abrir(cliente, actual, base)
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/transferir", json={
        "area": "soporte", "asesor_id": "u_ana", "nota": "Ojo que este reclama fuerte"})

    async def revisar():
        avisos = await base.notifications.find(
            {"user_id": "u_ana"}, {"_id": 0}).to_list(20)
        traidores = [a for a in avisos
                     if a.get("type") == "soporte_transferencia"
                     or "transfir" in (a.get("title") or "").lower()]
        assert not traidores, f"le llegó al cliente: {traidores}"

    _ya(revisar())


def test_a_alguien_del_equipo_si_se_transfiere():
    """Sin esto, un test que sólo probara el rechazo pasaría igual con una
    implementación que no deja transferir a nadie."""
    cliente, actual, base = _mesa("ris_tr_ok")
    caso_id = _abrir(cliente, actual, base)
    r = cliente.post(f"/api/admin/soporte/casos/{caso_id}/transferir", json={
        "area": "soporte", "asesor_id": "s_caro", "nota": "Caro conoce este caso"})
    assert r.status_code == 200, r.text

    async def revisar():
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] == "s_caro"
        assert c["asignado_a_nombre"] == "Caro Asesora"

    _ya(revisar())


# ══════════════════════════════════════════════════════════════════════════
# 2. Un caso escalado no se escala dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_el_servidor_no_deja_escalar_dos_veces():
    """La regla vivía SOLO en la pantalla, que apagaba el botón.

    Volver a escalar sobrescribe el motivo y el autor del escalamiento
    original, que es justo lo que lee un super administrador para decidir.
    """
    cliente, actual, base = _mesa("ris_esc")
    caso_id = _abrir(cliente, actual, base)

    primero = cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                           json={"motivo": "El cliente perdió 800 reales"})
    assert primero.status_code == 200, primero.text

    actual["u"] = CARO
    segundo = cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                           json={"motivo": "probando"})
    assert segundo.status_code == 400, "se escaló dos veces"
    # Que diga QUIEN lo escaló, no sólo que no se puede. Es lo único que aporta
    # la comprobación de lectura sobre el filtro de la escritura —las dos
    # rechazan— y sin mirarlo esa guarda se podría borrar sin que nada avisara.
    detalle = segundo.json().get("detail", "")
    assert "Beto Asesor" in detalle, f"el mensaje no dice quién lo escaló: {detalle!r}"
    assert "nota interna" in detalle, "ni qué hacer en su lugar"

    async def revisar():
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["escalado_motivo"] == "El cliente perdió 800 reales", (
            "se perdió el motivo del escalamiento original")
        assert c["escalado_por_nombre"] == "Beto Asesor"
        lineas = await base.soporte_mensajes.find(
            {"caso_id": caso_id, "interno": True}, {"_id": 0}).to_list(50)
        escalos = [m for m in lineas if "escaló el caso" in (m.get("texto") or "")]
        assert len(escalos) == 1, f"quedaron {len(escalos)} escalamientos en el hilo"

    _ya(revisar())


def test_re_escalar_no_pisa_una_bajada_de_prioridad_deliberada():
    """Escalar fuerza «urgente». Hacerlo de nuevo revertía una decisión que
    alguien tomó a mano después."""
    cliente, actual, base = _mesa("ris_esc_prio")
    caso_id = _abrir(cliente, actual, base)
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                 json={"motivo": "Urgente de verdad"})
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/prioridad", json={"prioridad": "baja"})
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar", json={"motivo": "otra vez"})

    async def revisar():
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["prioridad"] == "baja"

    _ya(revisar())


def test_un_caso_sin_escalar_si_se_escala():
    """El contraste, para que la guarda no pueda ser «rechazar siempre»."""
    cliente, actual, base = _mesa("ris_esc_ok")
    caso_id = _abrir(cliente, actual, base)
    r = cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                     json={"motivo": "Hace tres días que espera"})
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
# 3. Los avisos no persiguen a quien ya no trabaja acá
# ══════════════════════════════════════════════════════════════════════════

def test_un_super_administrador_dado_de_baja_no_recibe_los_escalados():
    """Era la única consulta del módulo sin `is_active`, porque no pasaba por
    `_staff_con`. El aviso lleva el número del caso y el motivo."""
    cliente, actual, base = _mesa("ris_baja")
    caso_id = _abrir(cliente, actual, base)
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                 json={"motivo": "El cliente perdió dinero"})

    async def revisar():
        # Sólo los avisos de ESCALAMIENTO: un super administrador activo recibe
        # además los de caso nuevo, por `_staff_con`, y contarlos todos haría
        # que este test pasara o fallara por una razón que no es la suya.
        escalados = {"type": "soporte_escalado"}
        de_baja = await base.notifications.count_documents(
            dict(escalados, user_id="sa_baja"))
        de_hoy = await base.notifications.count_documents(
            dict(escalados, user_id="sa_hoy"))
        assert de_baja == 0, "le siguió llegando a alguien que ya no está"
        assert de_hoy == 1, "y al que sí está dejó de llegarle"

    _ya(revisar())


# ══════════════════════════════════════════════════════════════════════════
# 4. Un pedido se contesta una sola vez
# ══════════════════════════════════════════════════════════════════════════

def test_un_pedido_ya_respondido_no_se_responde_otra_vez():
    """La comprobación se hacía leyendo y después escribiendo, sin filtro por
    estado en la escritura: dos personas del área contestando a la vez ganaban
    las dos, con dos notas en el hilo y la segunda pisando a la primera."""
    cliente, actual, base = _mesa("ris_ped")
    caso_id = _abrir(cliente, actual, base)
    hecho = cliente.post(f"/api/admin/soporte/casos/{caso_id}/pedidos", json={
        "area": "soporte", "detalle": "¿Le devolvemos el dinero a esta clienta?"})
    assert hecho.status_code == 200, hecho.text
    pedido_id = hecho.json()["pedido"]["pedido_id"]

    primera = cliente.post(f"/api/admin/soporte/pedidos/{pedido_id}/responder",
                           json={"respuesta": "Sí, ya se le devolvió el martes"})
    assert primera.status_code == 200, primera.text

    segunda = cliente.post(f"/api/admin/soporte/pedidos/{pedido_id}/responder",
                           json={"respuesta": "No, todavía no"})
    assert segunda.status_code == 400, "se respondió dos veces el mismo pedido"

    async def revisar():
        p = await base.soporte_pedidos.find_one({"pedido_id": pedido_id}, {"_id": 0})
        assert p["respuesta"] == "Sí, ya se le devolvió el martes", (
            "la segunda respuesta pisó a la primera")
        lineas = await base.soporte_mensajes.find(
            {"caso_id": caso_id, "interno": True}, {"_id": 0}).to_list(50)
        respuestas = [m for m in lineas if "respondió" in (m.get("texto") or "")]
        assert len(respuestas) == 1

    _ya(revisar())


# ══════════════════════════════════════════════════════════════════════════
# 5. El rescate de los que ya estaban atascados
# ══════════════════════════════════════════════════════════════════════════

def _rescate():
    import importlib
    return importlib.import_module("migrations.003_casos_atascados")


def test_un_caso_asignado_a_quien_no_puede_atenderlo_vuelve_a_la_cola():
    """Cerrar la puerta no libera a los que quedaron adentro.

    Un caso asignado a un cliente no figura como libre —está asignado— y quien
    lo tiene no puede abrir la consola. Sale de la cola de todo el equipo sin
    que nada avise.
    """
    cliente, actual, base = _mesa("ris_atasco")
    caso_id = _abrir(cliente, actual, base)

    async def escenario():
        # Se escribe directo: la ruta ya no lo permite, y lo que se prueba es
        # el rescate de lo que quedó de ANTES del arreglo.
        await base.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
            "asignado_a": "u_ana", "asignado_a_nombre": "Ana Cliente",
            "estado": "en_curso"}})

        resultado = await _rescate().ejecutar_si_hace_falta()
        assert resultado["liberados"] == 1, resultado

        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] is None
        assert c["asignado_a_nombre"] is None
        # `en_curso` significa «alguien lo está atendiendo», y no era cierto.
        assert c["estado"] == "abierto"

        # La línea en el hilo, para que el asesor entienda mañana por qué un
        # caso empezado le aparece como nuevo.
        lineas = await base.soporte_mensajes.find(
            {"caso_id": caso_id, "interno": True}, {"_id": 0}).to_list(50)
        assert any("vuelve a la cola" in (m.get("texto") or "").lower()
                   for m in lineas), "se liberó sin explicar por qué"

        # Y a la segunda pasada no hay nada que hacer.
        assert (await _rescate().ejecutar_si_hace_falta())["liberados"] == 0

    _ya(escenario())


def test_el_rescate_no_le_saca_el_caso_a_quien_si_lo_esta_atendiendo():
    """El contraste que impide que el rescate sea «soltar todo»."""
    cliente, actual, base = _mesa("ris_atasco_ok")
    caso_id = _abrir(cliente, actual, base)

    async def escenario():
        resultado = await _rescate().ejecutar_si_hace_falta()
        assert resultado["liberados"] == 0, resultado
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] == "s_beto"

    _ya(escenario())


def test_un_caso_cerrado_asignado_a_quien_ya_no_esta_se_deja_en_paz():
    """Un caso terminado no le hace daño a nadie, y reabrir la cola con
    historia vieja sí."""
    cliente, actual, base = _mesa("ris_atasco_cerrado")
    caso_id = _abrir(cliente, actual, base)

    async def escenario():
        await base.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
            "asignado_a": "s_ex", "asignado_a_nombre": "Ex Empleado",
            "estado": "cerrado"}})
        assert (await _rescate().ejecutar_si_hace_falta())["liberados"] == 0
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] == "s_ex"

    _ya(escenario())


def test_un_caso_asignado_a_un_identificador_que_ya_no_existe_tambien_se_libera():
    """Está igual de atascado que el asignado a un cliente, y es más fácil de
    pasar por alto: en `users` no hay nada que mirar."""
    cliente, actual, base = _mesa("ris_atasco_fantasma")
    caso_id = _abrir(cliente, actual, base)

    async def escenario():
        await base.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
            "asignado_a": "s_que_ya_no_esta", "asignado_a_nombre": "Quien Sea"}})
        assert (await _rescate().ejecutar_si_hace_falta())["liberados"] == 1
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["asignado_a"] is None

    _ya(escenario())


# ══════════════════════════════════════════════════════════════════════════
# 6. La segunda línea de defensa, probada sola
# ══════════════════════════════════════════════════════════════════════════
#
# Escalar y responder un pedido tienen DOS guardas: una que lee y comprueba, y
# el filtro dentro de la escritura. La de arriba es la que da el mensaje claro;
# la de abajo es la que sostiene la carrera entre dos personas simultáneas.
#
# Probando de la forma obvia, cada una tapa a la otra: romper una deja pasar el
# test porque la que queda devuelve el mismo 400. Medido con mutación, y por eso
# están estos dos tests: anulan la guarda de lectura —que es exactamente lo que
# pasa en una carrera, donde lo leído ya quedó viejo— y exigen que el filtro de
# la escritura frene igual.


def test_en_una_carrera_el_segundo_escalamiento_no_escribe(monkeypatch):
    """Dos asesores escalan a la vez: los dos leen «sin escalar» y los dos
    escriben. Sin el filtro en la escritura, el segundo pisa el motivo del
    primero."""
    cliente, actual, base = _mesa("ris_esc_carrera")
    caso_id = _abrir(cliente, actual, base)
    cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                 json={"motivo": "El cliente perdió 800 reales"})

    from routes import soporte as rutas
    # La comprobación de lectura ve el caso como estaba ANTES: es lo que le pasa
    # al segundo asesor de la carrera.
    monkeypatch.setattr(rutas.soporte, "problema_para_escalar", lambda caso: None)

    actual["u"] = CARO
    segundo = cliente.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                           json={"motivo": "probando"})
    assert segundo.status_code == 400, "la escritura no tiene guarda propia"

    async def revisar():
        c = await base.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})
        assert c["escalado_motivo"] == "El cliente perdió 800 reales"
        assert c["escalado_por_nombre"] == "Beto Asesor"

    _ya(revisar())


def test_en_una_carrera_la_segunda_respuesta_al_pedido_no_escribe(monkeypatch):
    """Dos personas de la misma área contestan a la vez. Sin el filtro en la
    escritura quedan dos notas en el hilo y la segunda pisa a la primera."""
    cliente, actual, base = _mesa("ris_ped_carrera")
    caso_id = _abrir(cliente, actual, base)
    pedido_id = cliente.post(f"/api/admin/soporte/casos/{caso_id}/pedidos", json={
        "area": "soporte",
        "detalle": "¿Le devolvemos el dinero a esta clienta?"}).json()["pedido"]["pedido_id"]
    cliente.post(f"/api/admin/soporte/pedidos/{pedido_id}/responder",
                 json={"respuesta": "Sí, ya se le devolvió el martes"})

    from routes import soporte as rutas
    monkeypatch.setattr(rutas.soporte, "problema_para_responder_pedido",
                        lambda pedido, permisos, es_super=False: None)

    segunda = cliente.post(f"/api/admin/soporte/pedidos/{pedido_id}/responder",
                           json={"respuesta": "No, todavía no"})
    assert segunda.status_code == 400, "la escritura no tiene guarda propia"

    async def revisar():
        p = await base.soporte_pedidos.find_one({"pedido_id": pedido_id}, {"_id": 0})
        assert p["respuesta"] == "Sí, ya se le devolvió el martes"

    _ya(revisar())
