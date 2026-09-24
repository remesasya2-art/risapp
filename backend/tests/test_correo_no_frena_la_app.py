"""
tests/test_correo_no_frena_la_app.py — Mandar un correo no puede parar todo.

LO QUE PASABA

    `resend.Emails.send()` es una llamada que ESPERA: abre una conexión a un
    servicio ajeno y se queda ahí hasta que contesta. Estaba metida dentro de
    funciones `async`, que son las que atienden los pedidos.

    En Python una espera de ésas no para sólo a quien la hizo: para el hilo
    entero. Mientras salía un correo, el servidor NO ATENDIA A NADIE. Y uno de
    los cinco lugares era el inicio de sesión: cada vez que alguien entraba,
    todos los demás esperaban a Resend.

COMO SE PRUEBA QUE YA NO

    Con un doble de Resend que duerme de verdad —`time.sleep`, el que bloquea,
    no `asyncio.sleep`— y comprobando que MIENTRAS ESO PASA el bucle sigue
    contestando. Es la única forma de probar esto: si se prueba con un doble
    que no bloquea, el test pasa igual con el código roto.

Y EL OTRO PROBLEMA: EL REMITENTE

    Había tres valores por omisión distintos en tres archivos, y uno apuntaba a
    un dominio que no es de la empresa. Si esa variable faltaba, los correos de
    seguridad salían desde ahí, Resend los rechazaba, y el error se tragaba en
    silencio: la función devolvía «no se envió» y nadie miraba.
"""
import asyncio
import logging
import os
import sys
import time

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import correo               # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _ResendDeMentira:
    """El doble. `Emails.send` BLOQUEA, como el de verdad."""

    def __init__(self, demora=0.0, revienta=False):
        self.demora = demora
        self.revienta = revienta
        self.enviados = []
        self.api_key = "re_de_mentira"

        doble = self

        class Emails:
            @staticmethod
            def send(params):
                if doble.demora:
                    time.sleep(doble.demora)     # BLOQUEA a propósito.
                if doble.revienta:
                    raise RuntimeError("Resend contestó que no")
                doble.enviados.append(params)
                return {"id": "msg_1"}

        self.Emails = Emails


@pytest.fixture
def resend_falso(monkeypatch):
    doble = _ResendDeMentira()
    monkeypatch.setitem(sys.modules, "resend", doble)
    monkeypatch.setattr(correo, "RESEND_API_KEY", "re_de_mentira")
    monkeypatch.setattr(correo, "REMITENTE", "RISApp <noreply@risappbr.com>")
    return doble


# ─── Lo que arregla este archivo ──────────────────────────────────────────

def test_mientras_sale_un_correo_el_servidor_sigue_atendiendo(resend_falso):
    """El test que se pone rojo si alguien vuelve a llamar a Resend derecho.

    NO SE MIDE EL TIEMPO, se hace una cita. El doble de Resend se queda
    esperando una señal que sólo puede dar el bucle que atiende pedidos:

        - Si el correo sale en otro hilo, el bucle sigue vivo, da la señal, y
          el correo termina.
        - Si el correo bloquea al bucle, la señal no puede llegar nunca. El
          doble se cansa de esperar y el correo no sale.

    Medir tiempos no servía: con el código roto, el otro pedido arranca a
    contar DESPUES del bloqueo, y desde su punto de vista tardó lo mismo.
    """
    import threading

    el_bucle_avanzo = threading.Event()
    llego_a_resend = threading.Event()

    def _send(params):
        llego_a_resend.set()
        if not el_bucle_avanzo.wait(timeout=3):
            raise TimeoutError(
                "El bucle no pudo avanzar mientras salía el correo: la llamada "
                "a Resend está bloqueando al hilo que atiende los pedidos.")
        resend_falso.enviados.append(params)
        return {"id": "msg_1"}

    resend_falso.Emails.send = staticmethod(_send)

    async def _atender_otro_pedido():
        # Se espera a que el correo esté DENTRO de Resend: sin esto, el pedido
        # podría dar la señal antes de que el bloqueo empiece, y el test
        # pasaría igual con el código roto.
        while not llego_a_resend.is_set():
            await asyncio.sleep(0.01)
        el_bucle_avanzo.set()

    async def _las_dos_cosas():
        return await asyncio.gather(
            correo.enviar("quien@ejemplo.com", "Hola", "<p>Hola</p>"),
            _atender_otro_pedido())

    salio, _ = corre(_las_dos_cosas())

    assert salio, (
        "El correo no salió porque el bucle nunca pudo avanzar. Ver el mensaje "
        "del TimeoutError en el registro.")
    assert len(resend_falso.enviados) == 1


def test_el_remitente_es_uno_solo_y_sale_del_correo(resend_falso):
    corre(correo.enviar("quien@ejemplo.com", "Hola", "<p>Hola</p>"))
    assert resend_falso.enviados[0]["from"] == "RISApp <noreply@risappbr.com>"


def test_el_remitente_lleva_el_nombre_de_la_aplicacion(monkeypatch):
    """Una casilla pelada en el «de:» se lee como correo automático de nadie.

    Se prueba la función que lo ARMA, no el valor sustituido: si se probara el
    sustituido, esto pasaría igual con el armado roto.
    """
    monkeypatch.setattr(correo, "FROM_EMAIL", "noreply@risappbr.com")
    assert correo._remitente() == "RISApp <noreply@risappbr.com>"


def test_si_ya_viene_con_nombre_no_se_le_pone_otro(monkeypatch):
    monkeypatch.setattr(correo, "FROM_EMAIL", "Otra Cosa <hola@risappbr.com>")
    assert correo._remitente() == "Otra Cosa <hola@risappbr.com>"


def test_sin_FROM_EMAIL_se_usa_SENDER_EMAIL(monkeypatch):
    """El respaldo, para no romper una instalación que sólo tenga configurada
    la vieja."""
    monkeypatch.setattr(correo, "FROM_EMAIL", "")
    monkeypatch.setenv("SENDER_EMAIL", "avisos@risappbr.com")
    assert correo._remitente() == "RISApp <avisos@risappbr.com>"


def test_los_dos_servicios_de_correo_usan_la_misma_puerta(resend_falso):
    """Antes cada uno llamaba a Resend por su cuenta, con su propio remitente."""
    from services import email, email_notifications

    corre(email.send_verification_email("quien@ejemplo.com", "123456", "Quien"))
    corre(email_notifications.send_email("quien@ejemplo.com", "Otro", "<p>x</p>"))

    assert len(resend_falso.enviados) == 2, (
        f"Salieron {len(resend_falso.enviados)} de 2 correos.")
    remitentes = {e["from"] for e in resend_falso.enviados}
    assert remitentes == {"RISApp <noreply@risappbr.com>"}, (
        f"Salieron desde {remitentes}.")


# ─── Que un correo caído no se lleve puesta la operación ──────────────────

def test_si_resend_contesta_que_no_se_devuelve_false_y_no_levanta(resend_falso, caplog):
    resend_falso.revienta = True
    with caplog.at_level(logging.ERROR):
        assert corre(correo.enviar("quien@ejemplo.com", "Hola", "<p>x</p>")) is False
    assert any("No se pudo mandar" in m for m in caplog.messages)


# ─── Que la mala configuración se grite ───────────────────────────────────

def test_sin_llave_no_se_intenta_y_queda_registrado(monkeypatch, caplog):
    monkeypatch.setattr(correo, "RESEND_API_KEY", "")
    with caplog.at_level(logging.ERROR):
        assert corre(correo.enviar("quien@ejemplo.com", "Hola", "<p>x</p>")) is False
    assert any("RESEND_API_KEY" in m for m in caplog.messages)


@pytest.mark.parametrize("remitente", [
    "RISApp <noreply@example.com>",
    "RISApp <notificaciones@risapp.com>",
])
def test_un_remitente_de_ejemplo_no_pasa(monkeypatch, caplog, remitente):
    """Los dos valores de ejemplo que traía el proyecto.

    El segundo es el que estaba puesto de verdad en el servicio de correos de
    seguridad, y apunta a un dominio que no es de la empresa: Resend lo
    rechaza, y antes eso no se notaba desde ningún lado.
    """
    monkeypatch.setattr(correo, "RESEND_API_KEY", "re_de_mentira")
    monkeypatch.setattr(correo, "REMITENTE", remitente)

    with caplog.at_level(logging.ERROR):
        assert corre(correo.enviar("quien@ejemplo.com", "Hola", "<p>x</p>")) is False

    assert not correo.revisar()
    assert any("rechazar" in m or "verificado" in m for m in caplog.messages)


def test_bien_configurado_revisar_dice_que_si(monkeypatch, caplog):
    monkeypatch.setattr(correo, "RESEND_API_KEY", "re_de_mentira")
    monkeypatch.setattr(correo, "REMITENTE", "RISApp <noreply@risappbr.com>")
    with caplog.at_level(logging.INFO):
        assert correo.revisar()


# ─── El de cortesía no hace esperar a nadie ───────────────────────────────

def test_el_correo_de_cortesia_no_hace_esperar_a_quien_opera(resend_falso):
    """«Entraste a tu cuenta» sale solo. Quien inició sesión no espera por él."""
    resend_falso.demora = 0.3

    async def _entrar_a_la_cuenta():
        arranque = time.monotonic()
        correo.en_segundo_plano("quien@ejemplo.com", "Entraste", "<p>x</p>")
        tardo = time.monotonic() - arranque
        # Que salga antes de terminar: si no, el test no prueba nada.
        await asyncio.sleep(0.6)
        return tardo

    tardo = corre(_entrar_a_la_cuenta())

    assert tardo < 0.1, (
        f"Quien inició sesión esperó {tardo:.2f}s por un correo de cortesía.")
    assert len(resend_falso.enviados) == 1, "Y el correo igual tiene que salir."


def test_la_tarea_de_cortesia_queda_agarrada_mientras_viaja(resend_falso):
    """`asyncio` sólo guarda una referencia DEBIL a las tareas que corren.

    Sin la lista de las que están en vuelo, el recolector de basura puede
    llevarse una a mitad de camino: el correo no sale y no queda ni un error.

    Se comprueba la LISTA, no el recolector. Cuándo pasa el recolector no se
    puede forzar, así que un test que dependa de eso pasa o falla por razones
    que no son el código.
    """
    resend_falso.demora = 0.2
    en_vuelo = {}

    async def _mandar_y_mirar():
        correo.en_segundo_plano("quien@ejemplo.com", "Hola", "<p>x</p>")
        en_vuelo["mientras"] = len(correo._EN_VUELO)
        await asyncio.sleep(0.5)
        en_vuelo["despues"] = len(correo._EN_VUELO)

    corre(_mandar_y_mirar())

    assert en_vuelo["mientras"] == 1, (
        "La tarea no quedó agarrada mientras el correo viajaba: el recolector "
        "se la puede llevar y el correo no sale nunca.")
    assert en_vuelo["despues"] == 0, "Y al terminar tiene que soltarse."
    assert len(resend_falso.enviados) == 1


def test_sin_bucle_no_revienta(resend_falso, caplog):
    """Un script o un test sincrónico no tienen dónde encolar la tarea."""
    with caplog.at_level(logging.WARNING):
        correo.en_segundo_plano("quien@ejemplo.com", "Hola", "<p>x</p>")
    assert any("bucle" in m for m in caplog.messages)


# ─── La guarda de forma ───────────────────────────────────────────────────

def test_nadie_llama_a_resend_por_su_cuenta():
    """La guarda, porque el bug reaparece igual en el archivo siguiente.

    Si esto se pone rojo, el arreglo no es envolverlo en otro hilo ahí mismo:
    es llamar a `services/correo.py`.
    """
    import ast

    culpables = []
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for nombre in sorted(os.listdir(raiz)):
            if not nombre.endswith(".py") or nombre == "correo.py":
                continue
            with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
                arbol = ast.parse(f.read())
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Attribute) and nodo.attr == "send"
                        and isinstance(nodo.value, ast.Attribute)
                        and nodo.value.attr == "Emails"):
                    culpables.append(f"{carpeta}/{nombre}")

    assert not culpables, (
        "Estos archivos llaman a Resend por su cuenta, y esa llamada frena al "
        "servidor entero mientras el correo viaja:\n  " + "\n  ".join(culpables))
