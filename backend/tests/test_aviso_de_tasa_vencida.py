"""
tests/test_aviso_de_tasa_vencida.py — Avisar una vez, no una por consulta.

QUE SOSTIENE ESTE ARCHIVO

    Decisión del operador: cuando la tasa paralela se pasa de antigua, el envío
    con Bitcoin se corta Y se avisa. El corte solo convierte «la tasa está
    vieja» en «la aplicación no anda», y el operador se entera por un cliente
    que no pudo enviar.

EL DETALLE QUE HACE QUE EL AVISO SIRVA

    La pantalla del envío consulta el precio cada diez segundos. Si se avisara
    en cada detección serían seis notificaciones por minuto y por persona con
    la pantalla abierta. A los cinco minutos nadie mira los avisos de esta
    aplicación, y el próximo —el que sí importaba— se pierde entre los otros.

    Un aviso que llega cien veces no es cien veces mejor: deja de ser un aviso.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import aviso_de_tasa  # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Coleccion:
    """`config` y `users`, con lo justo. Guarda de verdad: la marca que evita
    el segundo aviso se escribe y se vuelve a leer, y eso es lo que se prueba."""

    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.escrituras = 0

    async def find_one(self, filtro):
        return next((d for d in self.docs
                     if all(d.get(k) == v for k, v in filtro.items())), None)

    async def update_one(self, filtro, cambio, upsert=False):
        self.escrituras += 1
        doc = await self.find_one(filtro)
        if doc is None:
            if not upsert:
                return
            doc = dict(filtro)
            self.docs.append(doc)
        doc.update(cambio["$set"])

    def find(self, filtro):
        docs = [d for d in self.docs
                if all(d.get(k) == v for k, v in filtro.items())]

        class _Cursor:
            def __aiter__(self):
                self._i = iter(docs)
                return self

            async def __anext__(self):
                try:
                    return next(self._i)
                except StopIteration:
                    raise StopAsyncIteration
        return _Cursor()


class _Base:
    def __init__(self, config=None, users=None):
        self.config = _Coleccion(config)
        self.users = _Coleccion(users)


@pytest.fixture
def avisos(monkeypatch):
    """Intercepta las notificaciones creadas, sin tocar la base ni el push."""
    recibidas = []

    async def _crear(user_id, title, message, notification_type="info", data=None):
        recibidas.append({"user_id": user_id, "title": title,
                          "message": message, "type": notification_type,
                          "data": data or {}})
        return "notif_test"

    import services.notifications as n
    monkeypatch.setattr(n, "create_notification", _crear)
    return recibidas


UN_SUPER = [{"user_id": "u1", "role": "super_admin"},
            {"user_id": "u2", "role": "admin"}]


def test_avisa_a_los_super_administradores(avisos):
    base = _Base(users=UN_SUPER)
    cuando = datetime.now(timezone.utc) - timedelta(days=2)
    cuantos = corre(aviso_de_tasa.avisar_si_hace_falta(base, cuando, timedelta(days=2)))

    assert cuantos == 1
    assert [a["user_id"] for a in avisos] == ["u1"], (
        "El aviso tiene que ir a quien puede arreglarlo. Un `admin` común no "
        "puede cambiar la tasa: avisarle sólo agrega ruido.")
    assert avisos[0]["type"] == "warning"


def test_no_vuelve_a_avisar_por_la_misma_tasa(avisos):
    """La pantalla consulta cada diez segundos: acá se simulan cinco consultas."""
    base = _Base(users=UN_SUPER)
    cuando = datetime.now(timezone.utc) - timedelta(days=2)
    for _ in range(5):
        corre(aviso_de_tasa.avisar_si_hace_falta(base, cuando, timedelta(days=2)))

    assert len(avisos) == 1, (
        f"Se mandaron {len(avisos)} avisos por el mismo vencimiento. Un aviso "
        "que llega cien veces deja de ser un aviso.")


def test_vuelve_a_avisar_cuando_la_tasa_es_otra(avisos):
    """Se actualiza la tasa, pasa el tiempo y vuelve a vencer: eso sí se avisa.

    Es la otra mitad. Una marca que no caduca convierte el primer aviso en el
    último para siempre.
    """
    base = _Base(users=UN_SUPER)
    primera = datetime.now(timezone.utc) - timedelta(days=9)
    corre(aviso_de_tasa.avisar_si_hace_falta(base, primera, timedelta(days=9)))

    segunda = datetime.now(timezone.utc) - timedelta(days=2)
    corre(aviso_de_tasa.avisar_si_hace_falta(base, segunda, timedelta(days=2)))

    assert len(avisos) == 2, (
        "La tasa se actualizó y volvió a vencer, y no se avisó de nuevo.")


def test_la_marca_se_escribe_antes_de_notificar(avisos):
    """Contra dos consultas simultáneas, y son varias por segundo.

    Si la marca se escribiera después de notificar, las dos pasarían por la
    comprobación y las dos avisarían.
    """
    base = _Base(users=UN_SUPER)
    orden = []

    async def _crear(*_a, **_k):
        orden.append("aviso")
        return "x"

    import services.notifications as n
    n.create_notification = _crear
    escribir = base.config.update_one

    async def _update(*a, **k):
        orden.append("marca")
        return await escribir(*a, **k)

    base.config.update_one = _update
    corre(aviso_de_tasa.avisar_si_hace_falta(
        base, datetime.now(timezone.utc), timedelta(days=2)))

    assert orden and orden[0] == "marca", (
        f"El orden fue {orden}. La marca tiene que quedar escrita antes de "
        "notificar, o dos consultas a la vez avisan las dos.")


def test_si_no_hay_a_quien_avisar_queda_registrado(avisos, caplog):
    base = _Base(users=[{"user_id": "u2", "role": "admin"}])
    with caplog.at_level(logging.ERROR):
        cuantos = corre(aviso_de_tasa.avisar_si_hace_falta(
            base, datetime.now(timezone.utc), timedelta(days=2)))

    assert cuantos == 0
    assert any("super administrador" in m for m in caplog.messages), (
        "No había a quién avisar y no quedó registrado. Un aviso que no se "
        "manda y no se anota es indistinguible de uno que sí se mandó.")


def test_si_el_aviso_falla_no_arrastra_a_la_consulta(avisos, caplog):
    """El corte ya ocurrió. Que falle el aviso no puede además tirar la
    consulta de precio, que es lo que le muestra a la persona por qué no puede
    enviar."""
    class _BaseRota:
        class config:
            @staticmethod
            async def find_one(_f):
                raise RuntimeError("la base no contesta")

    with caplog.at_level(logging.ERROR):
        cuantos = corre(aviso_de_tasa.avisar_si_hace_falta(
            _BaseRota(), datetime.now(timezone.utc), timedelta(days=2)))

    assert cuantos == 0
    assert any("No se pudo avisar" in m for m in caplog.messages)


def test_el_mensaje_dice_que_lo_demas_sigue_andando(avisos):
    """Quien lo lee tiene que saber el tamaño del problema.

    «La tasa venció» a secas se lee como «la aplicación está caída». Se cortan
    los envíos con Bitcoin y nada más.
    """
    base = _Base(users=UN_SUPER)
    corre(aviso_de_tasa.avisar_si_hace_falta(
        base, datetime.now(timezone.utc), timedelta(days=3)))

    m = avisos[0]["message"]
    assert "Bitcoin" in m and "resto de la aplicación" in m
    assert "panel" in m, "No dice dónde se arregla."


def test_el_camino_del_precio_avisa_al_vencer(monkeypatch, avisos):
    """La integración: que `_get_tasa_ves` llame al aviso, y no sólo corte.

    Sin esto, los tests de arriba prueban un servicio que nadie usa.
    """
    from routes import btc_lightning as btc

    vieja = datetime.now(timezone.utc) - btc.EDAD_MAXIMA_DE_LA_TASA - timedelta(hours=2)
    base = _Base(config=[{"clave": "tasa_usd_ves_btc", "valor": 268.4,
                          "updated_at": vieja}],
                 users=UN_SUPER)
    monkeypatch.setattr(btc, "db", base)

    assert corre(btc._get_tasa_ves()) is None
    assert len(avisos) == 1, (
        "La tasa venció, se cortó, y no se avisó. El operador se entera por un "
        "cliente que no pudo enviar.")
