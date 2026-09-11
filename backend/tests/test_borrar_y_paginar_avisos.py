"""
tests/test_borrar_y_paginar_avisos.py — Vaciar la bandeja sin perder nada.

QUE SOSTIENE ESTE ARCHIVO

    Hasta ahora un aviso entraba y no salía nunca. La lista traía cincuenta y
    ahí se terminaba: el aviso cincuenta y uno no existía para nadie, y no
    había forma de borrar ninguno.

LAS DOS DECISIONES QUE SE PRUEBAN ACA

    NADA SE BORRA SOLO. No hay vencimiento automático, y fue una decisión: un
    aviso que desaparece solo es un aviso que alguien no llegó a leer, y nadie
    se entera de que existió.

    Y EL BORRADO EN TANDA NO TOCA LO QUE NO SE LEYO. «Limpiar leídas» limpia
    lo leído. Un botón que vacía la bandeja entera de un clic es un botón que
    alguien aprieta sin querer, y lo que se lleva no vuelve: ese aviso era la
    única copia de «tu retiro se completó» que esa persona iba a ver.

Y POR QUE EL PAGINADO NO CUENTA POSICIONES

    Se pagina por contenido —«dame los más viejos que éste»— y no por posición
    —«saltea los primeros veinte»—. Con posiciones, un aviso nuevo que llega
    mientras alguien está mirando corre todo un lugar, y la página siguiente
    repite el último que ya vio. Acá hay un test que lo hace pasar.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import FastAPI                        # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from conftest import usar_base                      # noqa: E402
from routes import notifications as rutas           # noqa: E402
from routes.dependencies import get_current_user    # noqa: E402
from services import notifications as n             # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Quien:
    def __init__(self, user_id):
        self.user_id = user_id


JEFA = _Quien("jefa")
AJENA = _Quien("otra")

# Se pasa por HTTP y no se llaman las funciones a mano.
#
# Llamándolas a mano, los valores por omisión de FastAPI no se resuelven: el
# parámetro llega como el objeto `Query(...)` en vez de `None`, y el test
# prueba un camino que en producción no existe. Además así se prueba lo que
# sólo existe en el enrutador: que `/notifications/leidas` gane sobre
# `/notifications/{id}`.
_app = FastAPI()
_app.include_router(rutas.router, prefix="/api")
_QUIEN = {"actual": JEFA}
_app.dependency_overrides[get_current_user] = lambda: _QUIEN["actual"]
cliente = TestClient(_app)


@pytest.fixture(autouse=True)
def como_la_jefa():
    _QUIEN["actual"] = JEFA
    yield
    _QUIEN["actual"] = JEFA


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def pedir(**parametros):
    r = cliente.get("/api/notifications", params=parametros)
    assert r.status_code == 200, r.text
    return r.json()


def _aviso(num, *, user_id="jefa", leido=False, ambito=n.PERSONAL, minutos=None):
    return {
        "notification_id": f"notif_{num:03d}",
        "user_id": user_id,
        "title": f"Aviso {num}",
        "message": "x",
        "type": "info",
        "ambito": ambito,
        "data": {},
        "read": leido,
        "created_at": datetime.now(timezone.utc) - timedelta(
            minutes=num if minutos is None else minutos),
    }


def _ids(avisos):
    return [a["notification_id"] for a in avisos]


# ─── El paginado ──────────────────────────────────────────────────────────

@pytest.fixture
def cincuenta(base):
    """Cincuenta avisos, el 1 el más nuevo y el 50 el más viejo."""
    corre(base.notifications.insert_many([_aviso(i) for i in range(1, 51)]))
    return base


def test_la_primera_pagina_trae_los_mas_nuevos(cincuenta):
    assert _ids(pedir(limite=20)) == [f"notif_{i:03d}" for i in range(1, 21)]


def test_la_pagina_siguiente_sigue_donde_quedo_la_anterior(cincuenta):
    primera = pedir(limite=20)
    ultimo = primera[-1]

    segunda = pedir(limite=20, antes_de=ultimo["created_at"],
                    ultimo_id=ultimo["notification_id"])

    assert _ids(segunda) == [f"notif_{i:03d}" for i in range(21, 41)]


def test_se_llega_hasta_el_final(cincuenta):
    vistos, cursor = [], {}
    for _ in range(10):
        pagina = pedir(limite=20, **cursor)
        if not pagina:
            break
        vistos += _ids(pagina)
        cursor = {"antes_de": pagina[-1]["created_at"],
                  "ultimo_id": pagina[-1]["notification_id"]}

    assert len(vistos) == 50, f"Se vieron {len(vistos)} de 50."
    assert len(set(vistos)) == 50, "Alguno vino dos veces."


def test_un_aviso_nuevo_no_repite_ni_saltea_la_pagina_siguiente(cincuenta):
    """Lo que se rompe si el paginado contara posiciones.

    Con «saltea los primeros veinte», el aviso nuevo corre todo un lugar y la
    página siguiente arranca repitiendo el último que ya se vio.
    """
    primera = pedir(limite=20)
    ultimo = primera[-1]

    corre(cincuenta.notifications.insert_one(_aviso(0, minutos=0)))

    segunda = pedir(limite=20, antes_de=ultimo["created_at"],
                    ultimo_id=ultimo["notification_id"])

    assert not set(_ids(primera)) & set(_ids(segunda)), (
        "La página siguiente repitió avisos de la anterior.")
    assert _ids(segunda)[0] == "notif_021", "Y tampoco se saltea ninguno."


def test_dos_avisos_del_mismo_instante_no_se_pierden(base):
    """El desempate por identificador.

    Una operación puede disparar dos avisos en el mismo milisegundo. Sin
    desempatar, el orden entre ellos es arbitrario y el paginado se come uno.
    """
    mismo = datetime.now(timezone.utc)
    corre(base.notifications.insert_many([
        {**_aviso(i), "created_at": mismo} for i in range(1, 7)]))

    vistos, cursor = [], {}
    for _ in range(6):
        pagina = pedir(limite=2, **cursor)
        if not pagina:
            break
        vistos += _ids(pagina)
        cursor = {"antes_de": pagina[-1]["created_at"],
                  "ultimo_id": pagina[-1]["notification_id"]}

    assert sorted(vistos) == [f"notif_{i:03d}" for i in range(1, 7)], (
        f"Se vieron {sorted(vistos)}.")


def test_una_fecha_que_no_es_una_fecha_se_rechaza(cincuenta):
    r = cliente.get("/api/notifications", params={"antes_de": "ayer a la tarde"})
    assert r.status_code == 400


def test_el_paginado_respeta_la_bandeja(base):
    corre(base.notifications.insert_many([
        _aviso(1, ambito=n.PERSONAL), _aviso(2, ambito=n.TRABAJO),
        _aviso(3, ambito=n.PERSONAL)]))

    assert _ids(pedir(ambito=n.TRABAJO, limite=20)) == ["notif_002"]


# ─── El filtro de sin leer ────────────────────────────────────────────────

def test_solo_sin_leer_deja_afuera_los_leidos(base):
    corre(base.notifications.insert_many([
        _aviso(1, leido=True), _aviso(2), _aviso(3, leido=True), _aviso(4)]))

    assert _ids(pedir(solo_sin_leer=True)) == ["notif_002", "notif_004"]


def test_sin_el_filtro_vienen_todos(base):
    corre(base.notifications.insert_many([_aviso(1, leido=True), _aviso(2)]))
    assert len(pedir()) == 2


# ─── Borrar de a uno ──────────────────────────────────────────────────────

def test_se_puede_borrar_uno(base):
    corre(base.notifications.insert_many([_aviso(1), _aviso(2)]))

    assert cliente.delete("/api/notifications/notif_001").status_code == 200

    assert _ids(pedir()) == ["notif_002"]


def test_se_puede_borrar_uno_sin_leer(base):
    """De a uno sí: la persona lo está mirando cuando decide."""
    corre(base.notifications.insert_one(_aviso(1, leido=False)))
    assert cliente.delete("/api/notifications/notif_001").status_code == 200
    assert corre(base.notifications.count_documents({})) == 0


def test_no_se_puede_borrar_el_aviso_de_otra_persona(base):
    corre(base.notifications.insert_one(_aviso(1, user_id="otra")))

    r = cliente.delete("/api/notifications/notif_001")

    assert r.status_code == 404, (
        "Tiene que contestar lo mismo que si no existiera. Distinguirlos deja "
        "averiguar, probando identificadores, qué avisos tiene otra persona.")
    assert corre(base.notifications.count_documents({})) == 1, "Y no borrarlo."


def test_borrar_uno_que_no_existe_contesta_404(base):
    assert cliente.delete("/api/notifications/notif_nada").status_code == 404


# ─── «Limpiar leídas» ─────────────────────────────────────────────────────

def test_limpiar_leidas_no_toca_lo_que_no_se_leyo(base):
    """La mitad del diseño. Lo que se lleva no vuelve."""
    corre(base.notifications.insert_many([
        _aviso(1, leido=True), _aviso(2, leido=False),
        _aviso(3, leido=True), _aviso(4, leido=False)]))

    r = cliente.delete("/api/notifications/leidas")

    assert r.status_code == 200 and r.json()["borrados"] == 2, r.text
    assert _ids(pedir()) == ["notif_002", "notif_004"]


def test_limpiar_una_bandeja_no_vacia_la_otra(base):
    corre(base.notifications.insert_many([
        _aviso(1, leido=True, ambito=n.PERSONAL),
        _aviso(2, leido=True, ambito=n.TRABAJO)]))

    cliente.delete("/api/notifications/leidas", params={"ambito": n.PERSONAL})

    assert _ids(pedir()) == ["notif_002"], (
        "Limpiar lo personal se llevó puesto el trabajo del equipo.")


def test_limpiar_no_toca_a_otra_persona(base):
    corre(base.notifications.insert_many([
        _aviso(1, leido=True), _aviso(2, leido=True, user_id="otra")]))

    cliente.delete("/api/notifications/leidas")

    _QUIEN["actual"] = AJENA
    assert _ids(pedir()) == ["notif_002"]


def test_limpiar_un_ambito_mal_escrito_no_borra_nada(base):
    """Se rechaza antes de tocar la base, igual que en la lectura."""
    corre(base.notifications.insert_one(_aviso(1, leido=True)))

    r = cliente.delete("/api/notifications/leidas", params={"ambito": "persnal"})

    assert r.status_code == 400
    assert corre(base.notifications.count_documents({})) == 1


def test_limpiar_con_la_bandeja_ya_limpia_no_falla(base):
    assert cliente.delete("/api/notifications/leidas").json()["borrados"] == 0


# ─── Que «leidas» no se tome por un identificador ─────────────────────────

def test_la_ruta_de_limpiar_no_la_atiende_la_de_borrar_uno():
    """`/notifications/leidas` y `/notifications/{id}` compiten por el mismo
    camino. FastAPI resuelve por orden de declaración: si alguien mueve una de
    las dos, «limpiar leídas» pasa a buscar un aviso llamado «leidas», no
    encuentra nada y contesta 404 sin borrar.
    """
    caminos = [r.path for r in rutas.router.routes
               if "DELETE" in (getattr(r, "methods", None) or set())]

    assert caminos.index("/notifications/leidas") < \
        caminos.index("/notifications/{notification_id}"), (
        f"El orden es {caminos}. «leidas» tiene que declararse ANTES.")
