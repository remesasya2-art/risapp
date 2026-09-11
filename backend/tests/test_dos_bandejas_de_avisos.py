"""
tests/test_dos_bandejas_de_avisos.py — Lo del equipo y lo de uno, separados.

QUE SOSTIENE ESTE ARCHIVO

    Un administrador tiene las dos clases de aviso: los suyos —«te aprobaron el
    KYC»— y los del equipo —«hay un KYC nuevo por revisar»—. Hasta ahora la
    campana los pedía todos juntos y los mostraba en una sola lista, sin
    ninguna diferencia visual.

    Eso tiene dos costos, y el segundo es el caro:

        Lo del equipo se pierde entre lo personal.
        Y «marcar todas como leídas» en la bandeja personal daba por atendido
        cada KYC pendiente del equipo, sin que nadie lo decidiera.

LA PREGUNTA SE HACE AL REVES, Y ES EL PUNTO

    «Personal» se pregunta como «que NO sea de trabajo».

    Los avisos guardados antes de que el campo existiera no lo tienen.
    Preguntando `ambito == "personal"` desaparecerían de la bandeja de su
    dueño, y son casi todos los que hay hoy en producción.
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

from conftest import usar_base                         # noqa: E402
from routes import notifications as rutas              # noqa: E402
from services import notifications as n                # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Quien:
    """Lo único que las rutas le piden a la sesión."""
    def __init__(self, user_id):
        self.user_id = user_id


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def _hace(minutos):
    return datetime.now(timezone.utc) - timedelta(minutes=minutos)


@pytest.fixture
def con_avisos(base):
    """La bandeja de una administradora: lo suyo, lo del equipo, y uno viejo."""
    corre(base.notifications.insert_many([
        {"notification_id": "mio_1", "user_id": "jefa", "read": False,
         "title": "Te aprobamos el KYC", "message": "Listo",
         "type": "verification_approved", "ambito": n.PERSONAL,
         "created_at": _hace(10)},
        {"notification_id": "equipo_1", "user_id": "jefa", "read": False,
         "title": "🆔 Nueva verificación KYC", "message": "Revisalo",
         "type": "kyc", "ambito": n.TRABAJO, "created_at": _hace(5)},
        {"notification_id": "equipo_2", "user_id": "jefa", "read": True,
         "title": "La tasa venció", "message": "Actualizala",
         "type": "warning", "ambito": n.TRABAJO, "created_at": _hace(2)},
        # Guardado antes de que el campo existiera. No tiene `ambito`.
        {"notification_id": "viejo", "user_id": "jefa", "read": False,
         "title": "Llegó tu recarga", "message": "R$ 200",
         "type": "recharge_approved", "created_at": _hace(60)},
        # De otra persona. No tiene que aparecer en ninguna de las dos.
        {"notification_id": "ajeno", "user_id": "otra", "read": False,
         "title": "Lo de otra persona", "message": "x",
         "ambito": n.TRABAJO, "created_at": _hace(1)},
    ]))
    return base


JEFA = _Quien("jefa")


def _ids(avisos):
    return sorted(a["notification_id"] for a in avisos)


# ─── Qué trae cada bandeja ────────────────────────────────────────────────

def test_la_bandeja_del_equipo_trae_solo_el_trabajo(con_avisos):
    lista = corre(rutas.get_notifications(JEFA, ambito=n.TRABAJO))
    assert _ids(lista) == ["equipo_1", "equipo_2"]


def test_la_bandeja_personal_no_trae_el_trabajo(con_avisos):
    lista = corre(rutas.get_notifications(JEFA, ambito=n.PERSONAL))
    assert "equipo_1" not in _ids(lista), (
        "El aviso del equipo se coló en la campana del cliente.")


def test_un_aviso_viejo_sin_marca_sigue_siendo_de_su_dueno(con_avisos):
    """La mitad que se rompe si la pregunta se hace al derecho.

    Si «personal» se preguntara como `ambito == "personal"`, todos los avisos
    guardados antes de este cambio desaparecerían de la campana.
    """
    lista = corre(rutas.get_notifications(JEFA, ambito=n.PERSONAL))
    assert "viejo" in _ids(lista), (
        "Un aviso guardado antes de que existiera el campo desapareció de la "
        "bandeja de su dueño. Son casi todos los que hay hoy.")


def test_ninguna_bandeja_trae_avisos_de_otra_persona(con_avisos):
    for cual in (n.PERSONAL, n.TRABAJO, None):
        lista = corre(rutas.get_notifications(JEFA, ambito=cual))
        assert "ajeno" not in _ids(lista), f"ambito={cual!r} filtró de más"


def test_sin_ambito_trae_todo_lo_suyo(con_avisos):
    """A propósito: el servidor se despliega antes que la pantalla.

    Durante esos minutos la campana vieja pide sin filtro. Devolverle una
    lista vacía sería un apagón de avisos en cada despliegue.
    """
    lista = corre(rutas.get_notifications(JEFA, ambito=None))
    assert _ids(lista) == ["equipo_1", "equipo_2", "mio_1", "viejo"]


def test_vienen_del_mas_nuevo_al_mas_viejo(con_avisos):
    lista = corre(rutas.get_notifications(JEFA, ambito=None))
    fechas = [a["created_at"] for a in lista]
    assert fechas == sorted(fechas, reverse=True)


def test_un_ambito_mal_escrito_se_rechaza(con_avisos):
    """No se trata como «todo»: un `persnal` mal tipeado devolvería la bandeja
    entera y el aviso del equipo aparecería en la campana del cliente."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        corre(rutas.get_notifications(JEFA, ambito="persnal"))
    assert e.value.status_code == 400


# ─── El número rojo ───────────────────────────────────────────────────────

def test_el_numero_cuenta_solo_su_bandeja(con_avisos):
    del_equipo = corre(rutas.get_unread_count(JEFA, ambito=n.TRABAJO))
    personal = corre(rutas.get_unread_count(JEFA, ambito=n.PERSONAL))

    assert del_equipo == {"unread_count": 1}, (
        "`equipo_2` ya está leído: no puede contar.")
    assert personal == {"unread_count": 2}, (
        "Lo personal son el aviso propio y el viejo sin marca.")


# ─── «Marcar todas» ───────────────────────────────────────────────────────

def test_marcar_todas_no_apaga_la_otra_bandeja(con_avisos):
    """El costo caro del sistema viejo.

    El operador vaciaba su bandeja personal y de paso se daba por enterado de
    cada KYC pendiente del equipo.
    """
    corre(rutas.mark_all_read(JEFA, ambito=n.PERSONAL))

    assert corre(rutas.get_unread_count(JEFA, ambito=n.TRABAJO)) == {"unread_count": 1}, (
        "«Marcar todas» en lo personal apagó los avisos del equipo.")
    assert corre(rutas.get_unread_count(JEFA, ambito=n.PERSONAL)) == {"unread_count": 0}


def test_marcar_todas_del_equipo_no_toca_lo_personal(con_avisos):
    corre(rutas.mark_all_read(JEFA, ambito=n.TRABAJO))

    assert corre(rutas.get_unread_count(JEFA, ambito=n.TRABAJO)) == {"unread_count": 0}
    assert corre(rutas.get_unread_count(JEFA, ambito=n.PERSONAL)) == {"unread_count": 2}


def test_marcar_todas_no_toca_a_otra_persona(con_avisos):
    corre(rutas.mark_all_read(JEFA, ambito=None))
    ajeno = corre(con_avisos.notifications.find_one({"notification_id": "ajeno"}))
    assert ajeno["read"] is False


def test_marcar_uno_no_sirve_para_el_aviso_de_otro(con_avisos):
    corre(rutas.mark_notification_read("ajeno", JEFA))
    ajeno = corre(con_avisos.notifications.find_one({"notification_id": "ajeno"}))
    assert ajeno["read"] is False, (
        "Se pudo marcar leído el aviso de otra persona sabiendo su número.")
