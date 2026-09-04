"""
tests/test_ip_cliente.py — De qué IP viene un pedido.

POR QUE ESTE ARCHIVO EXISTE

    Todos los límites de intentos de la aplicación cuentan por IP: el ingreso,
    el reseteo de contraseña, la invitación del personal, el segundo factor. Si
    la IP la elige quien hace el pedido, ninguno de esos límites existe — no es
    que sean flojos, es que no frenan a nadie, porque cada intento cae en un
    contador distinto.

    La versión anterior tomaba `x-forwarded-for.split(",")[0]`, que es
    exactamente el valor que escribe el cliente. Este archivo fija el criterio
    correcto para que no se vuelva atrás sin que algo se ponga en rojo.

LO QUE HAY QUE TENER EN LA CABEZA PARA LEER ESTO

    `X-Forwarded-For` se arma por acumulación: cada proxy le AGREGA al final la
    IP de quien le habló. No la reemplaza. Por eso la cadena se lee de derecha
    a izquierda: el último valor lo escribió el proxy que tenemos adelante, el
    único que no se puede falsear desde afuera. Todo lo que está a su izquierda
    lo pudo haber puesto el cliente.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services.ip_cliente import (                                   # noqa: E402
    desde_donde_dice_venir, ip_del_cliente)


def pedido(xff=None, cf=None, socket="10.0.0.7"):
    cabeceras = {}
    if xff is not None:
        cabeceras["x-forwarded-for"] = xff
    if cf is not None:
        cabeceras["cf-connecting-ip"] = cf

    class _P:
        headers = cabeceras
        client = type("C", (), {"host": socket})()
    return _P()


# ══════════════════════════════════════════════════════════════════════════
# 1. El agujero que este módulo cierra
# ══════════════════════════════════════════════════════════════════════════

def test_LA_IP_QUE_ESCRIBE_EL_CLIENTE_NO_GANA():
    """El caso del atacante, tal cual llega al servidor.

    Alguien manda `X-Forwarded-For: 1.2.3.4`. El proxy no lo borra: le agrega
    su IP real al final. La aplicación ve «1.2.3.4, 200.5.5.5» y tiene que
    contar contra 200.5.5.5. Si contara contra 1.2.3.4, cambiando ese valor en
    cada intento se saltea cualquier límite de la aplicación.
    """
    assert ip_del_cliente(pedido("1.2.3.4, 200.5.5.5")) == "200.5.5.5"


def test_cambiar_la_cabecera_en_cada_intento_no_cambia_el_contador():
    """La forma directa de decir lo mismo: el atacante varía lo que él escribe,
    y la IP con la que se lo cuenta no se mueve."""
    vistas = {ip_del_cliente(pedido(f"{i}.{i}.{i}.{i}, 200.5.5.5"))
              for i in range(1, 20)}
    assert vistas == {"200.5.5.5"}, \
        "cada intento cayó en un contador distinto: el límite no frena a nadie"


# ══════════════════════════════════════════════════════════════════════════
# 2. El criterio, caso por caso
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("xff, esperado", [
    ("200.1.2.3", "200.1.2.3"),                     # un solo proxy adelante
    ("  8.8.8.8  ", "8.8.8.8"),                     # con espacios de sobra
    ("1.1.1.1, 2.2.2.2, 3.3.3.3", "3.3.3.3"),       # cadena larga: el último
    ("1.2.3.4, , 10.0.0.1", "10.0.0.1"),            # con un valor vacío
])
def test_de_derecha_a_izquierda(xff, esperado):
    assert ip_del_cliente(pedido(xff)) == esperado


def test_cloudflare_le_gana_a_todo_lo_demas():
    """`CF-Connecting-IP` la escribe Cloudflare PISANDO lo que venga del
    cliente: es la única de las tres que no se puede tocar desde afuera."""
    assert ip_del_cliente(
        pedido(xff="1.2.3.4, 10.0.0.1", cf="200.7.7.7")) == "200.7.7.7"


def test_sin_cabeceras_queda_la_direccion_del_socket():
    """La verdad de la conexión. Sin proxy adelante es la del cliente; con
    proxy es la del proxy, que al menos no la eligió nadie de afuera."""
    assert ip_del_cliente(pedido(socket="190.9.9.9")) == "190.9.9.9"


@pytest.mark.parametrize("xff", ["", "   ", ",", " , , "])
def test_una_cabecera_vacia_no_tapa_al_socket(xff):
    """Una cabecera presente pero sin nada útil adentro no puede devolver la
    cadena vacía: eso metería a todo el mundo en el MISMO contador, que es el
    otro extremo del mismo problema."""
    assert ip_del_cliente(pedido(xff, socket="190.9.9.9")) == "190.9.9.9"


# ══════════════════════════════════════════════════════════════════════════
# 3. Con más de un proxy encadenado
# ══════════════════════════════════════════════════════════════════════════

def test_con_dos_proxies_de_confianza_se_saltea_uno(monkeypatch):
    """Con dos hops nuestros adelante, los dos últimos valores los escribieron
    ellos: el del cliente es el ante-último."""
    monkeypatch.setenv("PROXIES_DE_CONFIANZA", "2")
    assert ip_del_cliente(
        pedido("1.2.3.4, 200.5.5.5, 10.0.0.1")) == "200.5.5.5"


@pytest.mark.parametrize("valor", ["0", "-3", "abc", ""])
def test_un_numero_de_proxies_absurdo_no_rompe_ni_afloja(valor, monkeypatch):
    """Una variable de entorno mal puesta no puede hacer que se vuelva a leer
    el primer valor de la cadena. El piso es uno."""
    monkeypatch.setenv("PROXIES_DE_CONFIANZA", valor)
    assert ip_del_cliente(pedido("1.2.3.4, 200.5.5.5")) == "200.5.5.5"


def test_mas_proxies_declarados_que_valores_en_la_cadena(monkeypatch):
    """Si alguien declara cinco proxies y llega un solo valor, se devuelve ese
    valor y no se cae. Un límite que revienta al resolver la IP deja de
    frenar, que es lo contrario de lo que se busca."""
    monkeypatch.setenv("PROXIES_DE_CONFIANZA", "5")
    assert ip_del_cliente(pedido("200.5.5.5")) == "200.5.5.5"


# ══════════════════════════════════════════════════════════════════════════
# 4. Que nunca levante
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("request_raro", [
    object(),                                        # sin headers ni client
    type("P", (), {"headers": None, "client": None})(),
])
def test_un_request_incompleto_devuelve_vacio_pero_no_explota(request_raro):
    assert ip_del_cliente(request_raro) == ""


def test_si_las_cabeceras_explotan_al_leerlas_se_cae_al_socket():
    class _Hostiles(dict):
        def get(self, *a, **k):
            raise RuntimeError("cabeceras rotas")

    class _P:
        headers = _Hostiles()
        client = type("C", (), {"host": "190.9.9.9"})()

    assert ip_del_cliente(_P()) == "190.9.9.9"


# ══════════════════════════════════════════════════════════════════════════
# 5. La otra función, la que SI lee el primer valor
# ══════════════════════════════════════════════════════════════════════════

def test_desde_donde_dice_venir_devuelve_lo_que_escribio_el_cliente():
    """Existe aparte, con ese nombre, para registrar e investigar. El nombre es
    la advertencia: lo que alguien DICE, no lo que se puede comprobar."""
    assert desde_donde_dice_venir(pedido("1.2.3.4, 200.5.5.5")) == "1.2.3.4"


def test_LAS_DOS_FUNCIONES_NO_DAN_LO_MISMO_ANTE_UN_FALSEO():
    """Si algún día alguien las «unifica», este test lo muestra. Son dos
    preguntas distintas y la diferencia es justamente el ataque."""
    p = pedido("1.2.3.4, 200.5.5.5")
    assert desde_donde_dice_venir(p) != ip_del_cliente(p)


def test_sin_cabecera_la_que_dice_venir_cae_en_la_confiable():
    assert desde_donde_dice_venir(pedido(socket="190.9.9.9")) == "190.9.9.9"
