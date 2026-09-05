"""
tests/test_soporte_e2e.py — El circuito de la mesa de ayuda, contra la
aplicación de verdad.

POR QUE HACE FALTA ADEMAS DE LOS TESTS DEL SERVICIO

    `test_soporte.py` prueba las decisiones: cuándo se puede cerrar, quién
    contesta un pedido, cómo se ordena la bandeja. Todo eso sin tocar la base.

    Lo que NO prueba es que los manejadores anden: un nombre de campo mal
    escrito, un `await` que falta, una respuesta con otra forma que la que la
    pantalla espera. Eso sólo se ve pidiéndole a la aplicación.

    Acá se recorre el camino entero —el cliente abre, el asesor toma, responde,
    deja una nota, pide a otra área, transfiere y cierra, el cliente califica—
    con Mongo simulado y las dependencias de rol REALES.
"""
import asyncio
import os
import sys
import types
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para el circuito completo")


def _base():
    return mongomock_motor.AsyncMongoMockClient()["ris_soporte_e2e"]


DB = _base()


def _preparar():
    """Levanta la aplicación real una sola vez, contra la base simulada."""
    from conftest import usar_base
    usar_base(DB)

    # `pywebpush` no compila en todos los entornos y sólo se usa para mandar
    # avisos: se sustituye por un doble que no hace nada. Lo que se prueba acá
    # es el circuito del caso, no la entrega de la notificación.
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub

    try:
        from fastapi import FastAPI
        from routes.soporte import router
        from routes import dependencies as deps
    except Exception as e:                                    # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    app = FastAPI()
    app.include_router(router, prefix="/api")

    actual = {"user": None}

    def _quien():
        if actual["user"] is None:
            from fastapi import HTTPException
            raise HTTPException(401, "sin sesión")
        return actual["user"]

    # Sólo se sustituye QUIÉN está en sesión. El guard de rol y la tabla de
    # permisos siguen siendo los de verdad: si se sustituyeran, este archivo
    # daría por bueno que un `user` cualquiera puede cerrar casos ajenos.
    app.dependency_overrides[deps.get_current_user] = _quien
    return app, actual


APP, ACTUAL = _preparar()

from fastapi.testclient import TestClient                             # noqa: E402
from models.user import User                                          # noqa: E402

CLIENTE = TestClient(APP)


def _como(usuario):
    ACTUAL["user"] = usuario


CLIENTA = User(user_id="u_ana", name="Ana Cliente", email="ana@test.com",
               role="user")
ASESOR = User(user_id="s_beto", name="Beto Asesor", email="beto@test.com",
              role="agent", permissions=["support.view", "support.respond",
                                         "support.close", "support.pedidos"])
OTRO_ASESOR = User(user_id="s_caro", name="Caro Asesora", email="caro@test.com",
                   role="agent", permissions=["support.view", "support.respond"])
DE_KYC = User(user_id="s_dani", name="Dani KYC", email="dani@test.com",
              role="agent", permissions=["support.pedidos", "kyc.approve"])


@pytest.fixture(autouse=True)
def _base_limpia():
    """`database.db` es un proxy global y lo apunta el último fixture que corrió.

    Sin esto, cualquier otro archivo que instale su doble deja estos tests
    mirando una base que no es la suya: corriendo el archivo solo pasarían y en
    la suite completa fallarían enteros.
    """
    global DB
    DB = _base()
    from conftest import usar_base
    usar_base(DB)
    ACTUAL["user"] = None
    yield


def _abrir_caso(motivo="envio", mensaje="Mi envío de ayer no llegó al beneficiario"):
    _como(CLIENTA)
    r = CLIENTE.post("/api/soporte/casos", json={"motivo": motivo, "mensaje": mensaje})
    assert r.status_code == 200, r.text
    return r.json()["caso"]


# ══════════════════════════════════════════════════════════════════════════
# El camino feliz, de punta a punta
# ══════════════════════════════════════════════════════════════════════════

def test_el_circuito_completo():
    caso = _abrir_caso()
    assert caso["numero"].startswith("S-")
    assert caso["estado"] == "abierto"
    # El área es encaminamiento interno y no viaja al cliente: se comprueba
    # desde el lado del asesor, que es quien la usa.
    assert "area" not in caso

    caso_id = caso["caso_id"]

    # El asesor lo ve en la bandeja y lo toma.
    _como(ASESOR)
    # El motivo encamina el caso: «envío de dinero» arranca en soporte.
    assert CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()["caso"]["area"] == "soporte"
    r = CLIENTE.get("/api/admin/soporte/casos")
    assert r.status_code == 200, r.text
    assert any(c["caso_id"] == caso_id for c in r.json()["casos"])

    assert CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar").json()["success"]

    # Responde, y el caso queda esperando al cliente.
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Lo estoy viendo, dame unos minutos."})
    assert r.status_code == 200, r.text
    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()
    assert detalle["caso"]["estado"] == "esperando_cliente"
    assert detalle["caso"]["primera_respuesta_en"] is not None

    # Cierra y el cliente califica.
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado",
                     json={"estado": "cerrado"})
    assert r.status_code == 200, r.text

    _como(CLIENTA)
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/calificar",
                     json={"estrellas": 5, "comentario": "Rapidísimo"})
    assert r.status_code == 200, r.text
    assert CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["caso"]["calificacion"]["estrellas"] == 5


def test_dos_consultas_son_dos_casos():
    """Es la razón de ser del modelo nuevo.

    En el chat viejo, la consulta de un envío y la de la verificación eran el
    mismo hilo: cerrar una cerraba las dos.
    """
    uno = _abrir_caso("envio", "No llegó mi envío del martes")
    dos = _abrir_caso("verificacion", "Subí el documento y sigue pendiente")
    assert uno["caso_id"] != dos["caso_id"]
    assert uno["numero"] != dos["numero"]

    _como(ASESOR)
    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{dos['caso_id']}").json()
    assert detalle["caso"]["area"] == "verificaciones", (
        "El motivo del cliente tiene que encaminar el caso al área correcta.")

    _como(CLIENTA)
    assert len(CLIENTE.get("/api/soporte/casos").json()["casos"]) == 2


# ══════════════════════════════════════════════════════════════════════════
# Lo que el cliente NO tiene que poder hacer ni ver
# ══════════════════════════════════════════════════════════════════════════

def test_el_cliente_no_ve_las_notas_internas():
    """Es la garantía entera de la nota interna.

    Si se filtrara una sola vez, el asesor deja de escribirlas y la herramienta
    se muere.
    """
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                 json={"mensaje": "OJO: este cliente ya reclamó dos veces", "interno": True})

    _como(CLIENTA)
    mensajes = CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["mensajes"]
    assert all("reclamó dos veces" not in (m.get("texto") or "") for m in mensajes), (
        "Una nota interna llegó al cliente.")

    # El asesor sí la ve, y además ve las líneas de sistema del hilo.
    _como(ASESOR)
    todos = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()["mensajes"]
    assert any("reclamó dos veces" in (m.get("texto") or "") for m in todos)
    assert any(m["autor"] == "sistema" for m in todos), (
        "El hilo del asesor no muestra quién tomó el caso.")


def test_un_cliente_no_entra_al_caso_de_otro():
    caso_id = _abrir_caso()["caso_id"]
    _como(User(user_id="u_otro", name="Otro", email="otro@test.com", role="user"))
    assert CLIENTE.get(f"/api/soporte/casos/{caso_id}").status_code == 404


def test_en_un_caso_cerrado_el_cliente_no_escribe():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado", json={"estado": "cerrado"})

    _como(CLIENTA)
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/mensajes", json={"mensaje": "hola?"})
    assert r.status_code == 400
    assert "nuevo" in r.json()["detail"].lower()


def test_si_el_cliente_escribe_un_caso_resuelto_se_reabre():
    """Sin esto, «resuelto» sería «cerrado» con otro nombre."""
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado", json={"estado": "resuelto"})

    _como(CLIENTA)
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Sigue sin aparecer"})
    assert r.status_code == 200, r.text
    assert r.json()["reabierto"] is True
    assert CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["caso"]["estado"] == "en_curso"


# ══════════════════════════════════════════════════════════════════════════
# Entre asesores
# ══════════════════════════════════════════════════════════════════════════

def test_al_cliente_le_contesta_uno_solo():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")

    _como(OTRO_ASESOR)
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Hola, te ayudo yo"})
    assert r.status_code == 400
    assert "Beto" in r.json()["detail"]

    # Pero sí puede dejar una nota para el equipo: es aportar lo que sabe, no
    # hablarle al cliente.
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Yo lo atendí la semana pasada", "interno": True})
    assert r.status_code == 200, r.text


def test_dos_asesores_no_toman_el_mismo_caso():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    assert CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar").json()["success"]
    _como(OTRO_ASESOR)
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar").json()
    assert r["success"] is False
    assert r["asignado_a_nombre"] == "Beto Asesor"


def test_una_transferencia_deja_dicho_que_falta():
    """La nota queda EN EL HILO: el que recibe la lee sin abrir otra pantalla."""
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/transferir",
                     json={"area": "verificaciones", "asesor_id": None,
                           "nota": "Ya confirmé la identidad, falta aprobar el KYC"})
    assert r.status_code == 200, r.text

    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()
    assert detalle["caso"]["area"] == "verificaciones"
    assert detalle["caso"]["asignado_a"] is None      # vuelve a la bandeja del área
    assert any("falta aprobar el KYC" in (m.get("texto") or "")
               for m in detalle["mensajes"])


def test_una_transferencia_sin_nota_no_sale():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/transferir",
                     json={"area": "verificaciones", "nota": ""})
    assert r.status_code == 422        # lo frena el propio modelo del pedido


def test_escalar_sube_el_caso_y_lo_pone_urgente():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                     json={"motivo": "Reclama una operación de hace 20 días"})
    assert r.status_code == 200, r.text
    caso = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()["caso"]
    assert caso["escalado"] is True
    assert caso["prioridad"] == "urgente"

    # Y va primero en la bandeja, que es para lo que sirve.
    assert CLIENTE.get("/api/admin/soporte/casos").json()["casos"][0]["caso_id"] == caso_id


# ══════════════════════════════════════════════════════════════════════════
# Los pedidos a otra área
# ══════════════════════════════════════════════════════════════════════════

def test_se_le_pide_a_otra_area_sin_soltar_al_cliente():
    """Es la diferencia con transferir.

    El asesor sigue siendo el que le habla al cliente, y en paralelo pregunta a
    quien puede resolver. El cliente no va de mano en mano.
    """
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/pedidos",
                     json={"area": "verificaciones",
                           "detalle": "Subió el DNI el lunes y sigue pendiente"})
    assert r.status_code == 200, r.text

    # El caso NO cambió de dueño.
    caso = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()["caso"]
    assert caso["asignado_a"] == ASESOR.user_id

    # A quien puede resolverlo le aparece en su lista.
    _como(DE_KYC)
    pedidos = CLIENTE.get("/api/admin/soporte/pedidos").json()["pedidos"]
    assert len(pedidos) == 1
    pedido_id = pedidos[0]["pedido_id"]

    r = CLIENTE.post(f"/api/admin/soporte/pedidos/{pedido_id}/responder",
                     json={"respuesta": "Aprobado hace un rato, ya puede operar"})
    assert r.status_code == 200, r.text

    # La respuesta vuelve al caso como NOTA INTERNA: traducirla al cliente es
    # trabajo del asesor, que sabe qué preguntó.
    _como(ASESOR)
    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()
    assert any("ya puede operar" in (m.get("texto") or "") for m in detalle["mensajes"])

    _como(CLIENTA)
    mensajes = CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["mensajes"]
    assert all("ya puede operar" not in (m.get("texto") or "") for m in mensajes)


def test_un_pedido_lo_contesta_quien_puede_resolverlo():
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/pedidos",
                 json={"area": "finanzas", "detalle": "El saldo no cuadra con el libro"})

    # El asesor de soporte tiene `support.pedidos` pero NO `saldos.ajustar`.
    pedidos = CLIENTE.get("/api/admin/soporte/pedidos", params={"pendientes": False}).json()
    assert pedidos["pedidos"] == [] or "finanzas" not in pedidos["areas"]


# ══════════════════════════════════════════════════════════════════════════
# La ficha del cliente, al lado de la conversación
# ══════════════════════════════════════════════════════════════════════════

def test_el_asesor_ve_la_ficha_sin_abrir_otra_pantalla():
    """Antes se atendía a ciegas: para ver el saldo había que buscar al cliente
    por correo en otra pestaña."""
    # `asyncio.run` y no un test async: este proyecto no tiene pytest-asyncio, y
    # sumar una dependencia de desarrollo por dos inserciones no se paga.
    # mongomock vive en memoria y no se ata a un bucle, así que sembrar en uno
    # aparte y leer desde el del TestClient da lo mismo.
    async def _sembrar():
        await DB.users.insert_one({
            "user_id": "u_ana", "name": "Ana Cliente", "email": "ana@test.com",
            "balance_ris": 1500.0, "verification_status": "verified", "role": "user",
        })
        await DB.transactions.insert_one({
            "transaction_id": "t1", "user_id": "u_ana", "type": "send",
            "amount": 100.0, "status": "completed",
            "created_at": datetime.now(timezone.utc),
        })
    asyncio.run(_sembrar())

    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()
    assert detalle["cliente"]["balance_ris"] == 1500.0
    assert detalle["cliente"]["verification_status"] == "verified"
    assert len(detalle["operaciones"]) == 1


# ══════════════════════════════════════════════════════════════════════════
# La máquina de estados tiene que describir lo que el sistema HACE
# ══════════════════════════════════════════════════════════════════════════

def _estado(caso_id):
    return CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()["caso"]["estado"]


@pytest.mark.parametrize("operacion", ["soltar", "responder", "transferir"])
def test_ninguna_operacion_deja_el_caso_en_un_estado_imposible(operacion):
    """`tomar`, `soltar`, `responder` y `transferir` fijan el estado directo.

    Si el estado que dejan no está en `TRANSICIONES`, la máquina deja de
    describir el sistema: cualquiera que lea `services/soporte.py` para razonar
    sobre el ciclo de vida —o la pantalla, que ofrece el menú de estados a
    partir de ahí— saca conclusiones falsas.
    """
    from services import soporte

    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    # Se lo deja esperando al cliente, que es el estado desde el que las tres
    # operaciones producían un salto que la máquina no contemplaba.
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                 json={"mensaje": "Ya lo estoy viendo"})
    desde = _estado(caso_id)
    assert desde == soporte.ESPERANDO_CLIENTE

    if operacion == "soltar":
        CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/soltar")
    elif operacion == "responder":
        CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado",
                     json={"estado": "resuelto"})
        desde = _estado(caso_id)
        CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Una cosa más"})
    else:
        CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/transferir",
                     json={"area": "finanzas", "nota": "Falta revisar el saldo"})

    hasta = _estado(caso_id)
    assert soporte.puede_pasar(desde, hasta) or desde == hasta, (
        f"«{operacion}» dejó el caso de «{desde}» en «{hasta}», y la máquina "
        "dice que ese paso no existe.")


def test_al_cliente_no_le_viaja_nada_de_la_cocina():
    """La respuesta del cliente es una LISTA DE LO PERMITIDO.

    Con una de lo prohibido, cada campo nuevo del caso viaja hasta que alguien
    se acuerde de agregarlo — y el que se olvida no avisa. Así se colaban el
    motivo del escalamiento y el nombre de quien lo marcó.
    """
    caso_id = _abrir_caso()["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/escalar",
                 json={"motivo": "El cliente amenaza con denunciarnos"})

    _como(CLIENTA)
    caso = CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["caso"]
    prohibidos = ["escalado_motivo", "escalado_por", "escalado_por_nombre",
                  "asignado_a", "area", "prioridad", "sin_leer_asesor",
                  "escalado", "cerrado_por"]
    filtrados = [k for k in prohibidos if k in caso]
    assert not filtrados, f"Le viajaron al cliente campos internos: {filtrados}"

    # Y lo que sí necesita, sigue estando.
    for necesario in ("numero", "asunto", "estado", "asignado_a_nombre"):
        assert necesario in caso, f"Al cliente le falta «{necesario}»."


def test_si_falla_el_aviso_el_caso_igual_queda(monkeypatch):
    """El aviso es una cortesía; el caso es el trabajo.

    Al abrir un caso se le avisa a todo el personal del área, de a uno. Si el
    aviso número tres se cae —la base de notificaciones, el servicio de push—,
    la petición devolvía 500 con el caso YA guardado. Y la pantalla, al ver el
    error, lo vuelve a mandar: el cliente termina con dos casos iguales y el
    asesor sin saber cuál contestar.
    """
    import routes.soporte as rs

    async def _se_cae(*a, **k):
        raise RuntimeError("se cayó el servicio de avisos")

    monkeypatch.setattr(rs, "create_notification", _se_cae)

    _como(CLIENTA)
    r = CLIENTE.post("/api/soporte/casos",
                     json={"motivo": "envio", "mensaje": "No me llegó el envío"})
    assert r.status_code == 200, r.text
    caso_id = r.json()["caso"]["caso_id"]

    # Y el resto del circuito tampoco se cae por el aviso.
    _como(ASESOR)
    assert CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar").status_code == 200
    assert CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/mensajes",
                        json={"mensaje": "Lo veo ahora"}).status_code == 200
    assert CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado",
                        json={"estado": "resuelto"}).status_code == 200

    _como(CLIENTA)
    casos = CLIENTE.get("/api/soporte/casos").json()["casos"]
    assert len([c for c in casos if c["caso_id"] == caso_id]) == 1


def test_buscar_un_parentesis_no_rompe_la_bandeja():
    """Lo que el asesor escribe en el buscador es texto, no una expresión.

    Iba derecho al `$regex`: un paréntesis suelto —o el `+` de un teléfono, o
    el punto de un correo, que además hacía que buscara de más— reventaba la
    consulta y la bandeja volvía vacía con un error del servidor. Y un patrón
    del tipo `(a+)+$` deja a la base masticando.
    """
    _abrir_caso(mensaje="Consulta de Ana (la del envío)")
    _como(ASESOR)

    for aguja in ["(", "[", "*", "a(", "(a+)+$", "\\\\", "?"]:
        r = CLIENTE.get("/api/admin/soporte/casos",
                        params={"estado": "todos", "buscar": aguja})
        assert r.status_code == 200, f"«{aguja}» rompió la bandeja: {r.text}"

    # Y el punto tiene que buscar UN PUNTO, no «cualquier carácter».
    r = CLIENTE.get("/api/admin/soporte/casos",
                    params={"estado": "todos", "buscar": "ana.test"})
    assert r.status_code == 200
    assert r.json()["casos"] == []

    r = CLIENTE.get("/api/admin/soporte/casos",
                    params={"estado": "todos", "buscar": "ana@test"})
    assert len(r.json()["casos"]) == 1


def test_un_adjunto_que_no_es_una_imagen_no_entra():
    """El adjunto del caso lo abre un asesor, en su sesión de administrador.

    El campo es texto elegido por quien lo manda. Sin mirarlo, un
    `javascript:fetch('/api/admin/…')` guardado ahí se ejecuta cuando el asesor
    abre «la foto» del caso. El filtro del navegador ya no lo deja abrir; esto
    es la otra mitad, que no se guarde. Las dos hacen falta: la primera protege
    lo que ya está guardado, la segunda evita que entre más.
    """
    _como(CLIENTA)
    r = CLIENTE.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Adjunto el comprobante",
        "adjunto": "javascript:fetch('/api/admin/users')",
    })
    assert r.status_code == 400, r.text

    # Y no quedó un caso a medio hacer con su número quemado.
    assert CLIENTE.get("/api/soporte/casos").json()["casos"] == []

    # Una foto de verdad sí entra.
    r = CLIENTE.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Adjunto el comprobante",
        "adjunto": "data:image/png;base64,iVBORw0KGgo=",
    })
    assert r.status_code == 200, r.text
    caso_id = r.json()["caso"]["caso_id"]

    # Lo mismo al responder dentro del caso.
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "otra", "adjunto": "vbscript:msgbox(1)"})
    assert r.status_code == 400, r.text


def test_el_asesor_tampoco_manda_cualquier_cosa_como_imagen():
    """La imagen del asesor la abre el CLIENTE. El filtro corre para los dos."""
    caso = _abrir_caso()
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso['caso_id']}/tomar")
    r = CLIENTE.post(f"/api/admin/soporte/casos/{caso['caso_id']}/mensajes",
                     json={"mensaje": "mirá esto", "adjunto": "javascript:alert(1)"})
    assert r.status_code == 400, r.text


def test_el_cliente_puede_dar_por_terminada_su_consulta():
    """El que la abrió sabe si ya no la necesita.

    Sin esta puerta, la consulta que el cliente resolvió solo se quedaba en la
    cola del asesor como trabajo pendiente hasta que alguien la mirara para
    descubrir que no había nada que hacer —y encima le contaba contra el tope
    de cinco consultas abiertas—.
    """
    caso = _abrir_caso()
    caso_id = caso["caso_id"]

    _como(CLIENTA)
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/cerrar")
    assert r.status_code == 200, r.text
    assert CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["caso"]["estado"] == "cerrado"

    # Se cayó de la bandeja de abiertos del asesor.
    _como(ASESOR)
    abiertos = CLIENTE.get("/api/admin/soporte/casos").json()["casos"]
    assert all(c["caso_id"] != caso_id for c in abiertos)

    # Y queda en el hilo quién lo cerró, no aparece cerrado y ya.
    detalle = CLIENTE.get(f"/api/admin/soporte/casos/{caso_id}").json()
    assert any("dio por terminada" in (m.get("texto") or "")
               for m in detalle["mensajes"])


def test_nadie_cierra_la_consulta_de_otro():
    caso = _abrir_caso()
    _como(OTRO_ASESOR)      # ni siquiera un asesor por esta puerta
    assert CLIENTE.post(f"/api/soporte/casos/{caso['caso_id']}/cerrar").status_code == 404


def test_se_califica_un_caso_resuelto_sin_esperar_a_que_lo_cierren():
    """El asesor deja el caso en «resuelto» a propósito: cerrado no se reabre.

    Con la calificación atada a «cerrado», se le pedía la opinión al cliente
    justo en el estado que al asesor se le pide NO usar.
    """
    caso = _abrir_caso()
    caso_id = caso["caso_id"]
    _como(ASESOR)
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/tomar")
    CLIENTE.post(f"/api/admin/soporte/casos/{caso_id}/estado", json={"estado": "resuelto"})

    _como(CLIENTA)
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/calificar",
                     json={"estrellas": 4, "comentario": "Bien"})
    assert r.status_code == 200, r.text

    # Calificar no cierra: si faltaba algo, el cliente sigue pudiendo escribir
    # —y eso reabre el caso— sin perder la opinión que ya dejó.
    r = CLIENTE.post(f"/api/soporte/casos/{caso_id}/mensajes",
                     json={"mensaje": "Che, me pasó de nuevo"})
    assert r.status_code == 200, r.text
    mio = CLIENTE.get(f"/api/soporte/casos/{caso_id}").json()["caso"]
    assert mio["estado"] != "resuelto"
    assert mio["calificacion"]["estrellas"] == 4
