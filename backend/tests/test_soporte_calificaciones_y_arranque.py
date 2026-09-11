"""
tests/test_soporte_calificaciones_y_arranque.py — Cuatro arreglos de la mesa de
ayuda, cada uno con el defecto que lo motivó escrito al lado.

POR QUE ESTE ARCHIVO

    Los cuatro son del mismo tipo: nada explota, nada aparece en el registro de
    errores, y el que mira la pantalla no tiene manera de saber que falta algo.
    Un campo que se escribe con un nombre y se lee con otro, una puerta vieja
    que quedó abierta al lado de la nueva, un adjunto que entra sin que nadie
    lo mire, y una migración que había que acordarse de correr a mano.

    Ese silencio es justo la razón de los tests: son defectos que sólo se ven
    comparando dos archivos que nadie abre juntos.
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
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")


def _ya(corrutina):
    """Corre una corrutina y devuelve su resultado.

    `asyncio.run` y no `get_event_loop().run_until_complete`: el segundo toma
    el lazo que otro archivo de la suite ya cerró, así que estos tests pasarían
    corriendo el archivo solo y fallarían en la suite completa.
    """
    return asyncio.run(corrutina)


def _base_limpia(nombre="ris_calificaciones"):
    """Una base propia por test, y `database.db` apuntando a ella."""
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)
    return base


def _sin_webpush():
    """`pywebpush` no compila en todos lados y sólo sirve para avisar."""
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


# ══════════════════════════════════════════════════════════════════════════
# 1. El panel de calificaciones dice de qué caso habla
# ══════════════════════════════════════════════════════════════════════════

def _armar_app():
    """La aplicación de verdad, con la mesa de ayuda montada."""
    _sin_webpush()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.soporte import router
    from routes import dependencies as deps
    from models.user import User

    app = FastAPI()
    app.include_router(router, prefix="/api")
    actual = {"user": None}
    app.dependency_overrides[deps.get_current_user] = lambda: actual["user"]
    app.dependency_overrides[deps.get_crm_user] = lambda: ASESOR
    return TestClient(app), actual, User


from models.user import User as _User                                  # noqa: E402

CLIENTA = _User(user_id="u_ana", name="Ana Cliente", email="ana@test.com",
                role="user")
ASESOR = _User(user_id="s_beto", name="Beto Asesor", email="beto@test.com",
               role="agent", permissions=["support.view", "support.respond",
                                          "support.close"])


def _caso_calificado(cliente, actual, estrellas=5):
    """El circuito entero: se abre, se atiende, se resuelve y se califica."""
    actual["user"] = CLIENTA
    caso = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Mi envío no llegó"}).json()["caso"]
    actual["user"] = ASESOR
    cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/tomar")
    cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/mensajes",
                 json={"mensaje": "Lo estamos viendo"})
    cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/estado",
                 json={"estado": "resuelto"})
    actual["user"] = CLIENTA
    respuesta = cliente.post(f"/api/soporte/casos/{caso['caso_id']}/calificar",
                             json={"estrellas": estrellas, "comentario": "Muy bien"})
    assert respuesta.status_code == 200, respuesta.text
    return caso


def test_la_calificacion_guarda_el_numero_de_caso_legible():
    """El defecto: se escribía `case_ref` y el panel leía `case_code`.

    Los dos escritores de `ratings` guardaban `case_ref`; `get_agent_ratings`
    pedía `case_code`, que no existía en ningún documento. Resultado: el super
    admin veía «★★★★★ · 11/9/2026» sin manera de saber a qué atención
    correspondía, y como ningún test cubría el enlace, nadie se enteró.

    Además de arreglar el nombre hace falta el número LEGIBLE: `case_ref`
    guarda `caso_a1b2c3…`, que no sirve para citar un caso por teléfono.
    """
    base = _base_limpia()
    cliente, actual, _ = _armar_app()
    caso = _caso_calificado(cliente, actual)

    async def revisar():
        doc = await base.ratings.find_one({}, {"_id": 0})
        assert doc is not None, "la calificación no se guardó en `ratings`"
        # El identificador interno sigue estando: es con lo que se busca.
        assert doc["case_ref"] == caso["caso_id"]
        # Y ahora también el número que una persona puede leer y repetir.
        assert doc["case_code"] == caso["numero"]
        assert doc["case_code"].startswith("S-")

    _ya(revisar())


def test_el_panel_del_super_admin_muestra_el_numero_de_caso():
    """El mismo defecto, mirado desde donde se notaba: la pantalla."""
    _base_limpia()
    cliente, actual, _ = _armar_app()
    caso = _caso_calificado(cliente, actual)

    async def revisar():
        from routes.admin import get_agent_ratings
        salida = await get_agent_ratings(admin=ASESOR)
        fila = salida["agents"][0]["ratings"][0]
        assert fila["case_code"] == caso["numero"], (
            "el panel volvió a quedarse sin la referencia al caso")
        assert fila["stars"] == 5

    _ya(revisar())


def test_las_calificaciones_ya_guardadas_no_se_quedan_sin_referencia():
    """El respaldo, que es la mitad del arreglo.

    Las calificaciones que ya están en la base se escribieron sólo con
    `case_ref`. Sin leerlo de respaldo, el panel seguiría mudo sobre todas
    ellas hasta que entrara una calificación nueva — y las viejas no vuelven a
    escribirse nunca.
    """
    base = _base_limpia()

    async def escenario():
        await base.ratings.insert_one({
            "rating_id": "rat_vieja", "channel": "caso",
            "case_ref": "caso_de_antes",          # sin `case_code`, como antes
            "agent_id": "s_beto", "agent_name": "Beto Asesor",
            "stars": 4, "comment": "", "created_at": datetime.now(timezone.utc),
        })
        from routes.admin import get_agent_ratings
        salida = await get_agent_ratings(admin=ASESOR)
        fila = salida["agents"][0]["ratings"][0]
        assert fila["case_code"] == "caso_de_antes"

    _ya(escenario())


# ══════════════════════════════════════════════════════════════════════════
# 2. Una atención, una sola calificación
# ══════════════════════════════════════════════════════════════════════════

def test_la_puerta_vieja_para_calificar_el_chat_ya_no_existe():
    """El defecto: la misma conversación se podía calificar dos veces.

    El cliente cuyo chat se migró califica su caso por la ruta nueva, y además
    podía volver a `POST /support/rate` y calificar el chat original —que la
    migración deja intacto a propósito—. Eran dos documentos en `ratings` por
    una sola atención, los dos contando en el promedio del agente.
    """
    from routes.support import router

    rutas = {r.path for r in router.routes}
    assert "/support/rate" not in rutas, (
        "volvió la ruta que permitía calificar dos veces la misma atención")
    # Y la de casos, que es la que queda, sigue en pie.
    from routes.soporte import router as router_casos
    assert any(r.path.endswith("/calificar") for r in router_casos.routes)


# ══════════════════════════════════════════════════════════════════════════
# 3. El adjunto del endpoint viejo se mira antes de guardarlo
# ══════════════════════════════════════════════════════════════════════════

def test_el_endpoint_viejo_no_guarda_una_imagen_que_no_es_una_imagen():
    """El defecto: `/admin/support/respond` guardaba `image` tal cual llegaba.

    La mesa de ayuda nueva lo saneaba; la vieja, que quedó montada al lado, no.
    El campo lo elige quien manda el mensaje y lo abre el otro, así que un
    `javascript:…` guardado ahí espera a que alguien abra «la imagen».
    """
    _base_limpia("ris_adjunto")
    _sin_webpush()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.support import router
    from routes import dependencies as deps

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_crm_user] = lambda: ASESOR
    cliente = TestClient(app)

    respuesta = cliente.post("/api/admin/support/respond", json={
        "user_id": "u_ana", "message": "Mirá la captura",
        "image": "javascript:alert(document.cookie)",
    })
    assert respuesta.status_code == 400, (
        f"se guardó un adjunto que no es una imagen: {respuesta.text}")

    async def revisar():
        from database import db
        assert await db.support_messages.count_documents({}) == 0, (
            "el mensaje se guardó igual, con el adjunto adentro")

    _ya(revisar())


# ══════════════════════════════════════════════════════════════════════════
# 4. La migración se corre sola
# ══════════════════════════════════════════════════════════════════════════

def _modulo_migracion():
    import importlib
    return importlib.import_module("migrations.002_chats_a_casos")


async def _un_chat(base, uid):
    await base.support_chats.insert_one({
        "user_id": uid, "user_name": f"Cliente {uid}", "status": "open",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "last_message": "Hola", "last_message_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
    })
    await base.support_messages.insert_one({
        "message_id": f"m_{uid}", "user_id": uid, "sender": "user",
        "message": "Necesito ayuda",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    })


def test_al_arrancar_mueve_los_chats_y_despues_no_vuelve_a_recorrerlos():
    """El defecto: la migración se corría a mano, así que no se corrió nunca.

    Mientras tanto el frontend ya leía únicamente casos: el historial de cada
    cliente seguía entero en la base y no se veía en ninguna pantalla.

    La segunda parte —que no vuelva a recorrer— no es rendimiento porque sí:
    sin el atajo, cada reinicio y cada despliegue se traen hasta diez mil chats
    para descubrir que ya están todos movidos.
    """
    base = _base_limpia("ris_arranque")
    migracion = _modulo_migracion()

    async def escenario():
        await _un_chat(base, "u_ana")
        await _un_chat(base, "u_beto")

        primera = await migracion.ejecutar_si_hace_falta()
        assert primera["casos_creados"] == 2
        assert await base.soporte_casos.count_documents({}) == 2

        # La segunda vez no hay nada nuevo: se vuelve por el atajo.
        segunda = await migracion.ejecutar_si_hace_falta()
        assert segunda == {"ya_estaba": True, "chats_vistos": 2}
        assert await base.soporte_casos.count_documents({}) == 2

    _ya(escenario())


def test_un_chat_que_aparece_despues_tambien_se_mueve():
    """El atajo no puede convertirse en una marca de «hecha y nunca más».

    Las rutas viejas siguen montadas. Si alguien escribe por ahí después de la
    primera corrida, ese chat no puede quedarse sin caso: la cuenta cambia y la
    migración vuelve a correr sola.
    """
    base = _base_limpia("ris_arranque_2")
    migracion = _modulo_migracion()

    async def escenario():
        await _un_chat(base, "u_ana")
        await migracion.ejecutar_si_hace_falta()
        assert await base.soporte_casos.count_documents({}) == 1

        await _un_chat(base, "u_tarde")
        tercera = await migracion.ejecutar_si_hace_falta()
        assert tercera["casos_creados"] == 1
        assert tercera["ya_estaban"] == 1, "volvió a mover el que ya estaba"
        assert await base.soporte_casos.count_documents({}) == 2

    _ya(escenario())


def test_sin_chats_viejos_no_toca_nada():
    """Una base nueva no tiene historia que mudar: ni una escritura."""
    base = _base_limpia("ris_arranque_3")
    migracion = _modulo_migracion()

    async def escenario():
        resultado = await migracion.ejecutar_si_hace_falta()
        assert resultado == {"nada_que_migrar": True}
        assert await base.soporte_casos.count_documents({}) == 0
        assert await base.migraciones.count_documents({}) == 0

    _ya(escenario())
