"""
tests/test_ventana_del_cobro.py — El cobro dura diez minutos, y de verdad.

QUE DECIDIO EL OPERADOR

    Bajar la ventana de treinta a diez minutos: «así el usuario tiene más
    diligencia en hacer el pago rápido». Es LA ventana de exposición a la
    volatilidad del bitcoin — en ese rato el precio queda clavado y el
    movimiento lo absorbe el operador.

LO QUE HABIA QUE ARREGLAR PARA QUE ACORTARLA NO EMPEORARA LAS COSAS

    El invoice se le pedía al proveedor SIN vencimiento, así que quedaba con el
    suyo por omisión, mucho más largo. La ventana de treinta minutos era sólo
    del lado nuestro: el cliente podía pagar a los cuarenta y la red aceptaba.

    Y el webhook acreditaba ese pago sin mirar la fecha. Dos finales malos:

      · Orden vencida  → se enviaban bolívares calculados con un bitcoin de
        cuarenta minutos antes, y la diferencia la ponía alguien sin decidirlo.
      · Orden cancelada → la búsqueda filtraba por «pendiente», no encontraba
        nada, y el webhook contestaba «ya procesada». El cliente pagaba y no
        quedaba rastro de que su plata había llegado.

    Acortar la ventana hace las dos MAS probables, no menos: más órdenes van a
    vencer. Por eso los tres cambios van juntos.
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from routes import btc_lightning as btc  # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def _cuerpo_del_webhook(fuente):
    """El webhook, desde su primera línea hasta el siguiente endpoint.

    El corte se busca con expresión regular y no con `"\\n@router."`: en este
    archivo hay decoradores escritos con un espacio delante, y buscarlos como
    texto exacto hacía que el test se llevara medio módulo o directamente
    reventara. Un test que revienta al mover una línea no protege nada.
    """
    desde = fuente.index("payment_hash = transaction.get")
    siguiente = re.search(r"\n\s*@router\.", fuente[desde:])
    return fuente[desde:desde + siguiente.start()] if siguiente else fuente[desde:]


# ══════════════════════════════════════════════════════════════════════════
# La duración
# ══════════════════════════════════════════════════════════════════════════

def test_el_cobro_dura_diez_minutos():
    assert btc.DURACION_DEL_COBRO == timedelta(minutes=10)


def test_la_duracion_esta_escrita_una_sola_vez():
    """Estaba en cuatro lugares: dos en el servidor y dos en la pantalla.

    Cambiarla era acordarse de los cuatro, y el que se olvidara no rompía
    nada: la cuenta regresiva mostraba un número y el servidor aplicaba otro.
    """
    fuente = open(btc.__file__, encoding="utf-8").read()
    visible = "\n".join(l for l in fuente.splitlines()
                        if not l.strip().startswith("#"))
    assert "minutes=30" not in visible and "1800" not in visible, (
        "Quedó un 30 o un 1800 suelto: la duración del cobro tiene que salir "
        "de DURACION_DEL_COBRO y de ningún otro lado.")


def test_la_pantalla_no_tiene_la_duracion_escrita():
    ruta = os.path.join(_BACKEND, "..", "frontend", "src", "pages", "BTCLightning.jsx")
    fuente = open(ruta, encoding="utf-8").read()
    visible = "\n".join(l for l in fuente.splitlines()
                        if not l.strip().startswith(("//", "*", "/*")))
    assert "1800" not in visible, (
        "La pantalla tiene la duración escrita a mano. La decide el servidor: "
        "si no coinciden, la cuenta regresiva miente.")


# ══════════════════════════════════════════════════════════════════════════
# El invoice no puede sobrevivir a la ventana
# ══════════════════════════════════════════════════════════════════════════

def test_al_proveedor_se_le_pide_el_vencimiento():
    """Sin esto, acortar la ventana es acortarla sólo de nuestro lado."""
    fuente = open(btc.__file__, encoding="utf-8").read()
    cuerpo = fuente[fuente.index('@router.post("/generar-invoice"'):]
    assert '"expiresIn"' in cuerpo, (
        "El invoice se pide sin vencimiento: queda con el del proveedor, más "
        "largo que nuestra ventana, y se puede pagar tarde.")
    assert "DURACION_DEL_COBRO" in cuerpo, (
        "El vencimiento que se le pide al proveedor no sale de la misma "
        "constante que la ventana. Dos números que tienen que coincidir y "
        "cada uno por su lado terminan distintos.")


@pytest.mark.parametrize("respuesta, esperado, porque", [
    ({"errors": [{"message": "Field 'expiresIn' is not defined"}]}, True,
     "el proveedor no conoce el campo"),
    ({"errors": [{"message": "Invalid amount"}]}, False,
     "es un error de negocio: reintentar sería insistir con algo rechazado"),
    ({"data": {"lnInvoiceCreate": {"errors": [{"message": "expiresIn algo"}]}}}, False,
     "el error de negocio viene adentro, no arriba"),
    ({}, False, "no hay error"),
    ({"errors": None}, False, "la clave está pero vacía"),
])
def test_solo_se_reintenta_cuando_el_rechazo_es_por_el_campo(respuesta, esperado, porque):
    assert btc._blink_rechazo_el_vencimiento(respuesta) is esperado, porque


# ══════════════════════════════════════════════════════════════════════════
# Un pago que llega tarde
# ══════════════════════════════════════════════════════════════════════════

def test_el_webhook_no_acredita_una_orden_vencida():
    """Se mira el código: la comprobación tiene que estar antes de acreditar.

    Probar el webhook entero pediría firmar el evento y montar seis
    colecciones. Lo que hay que impedir es concreto y se puede afirmar de la
    forma: que `expira_en` se mire ANTES de tocar la billetera.
    """
    fuente = open(btc.__file__, encoding="utf-8").read()
    cuerpo = _cuerpo_del_webhook(fuente)

    assert "revision_manual" in cuerpo, (
        "El webhook no marca para revisión los pagos que llegan tarde.")
    assert cuerpo.index("expira_en") < cuerpo.index("btc_ves_wallets"), (
        "Se acredita el saldo ANTES de mirar si la orden venció. El orden es "
        "la garantía entera: mirar después es haber acreditado ya.")
    # La BUSQUEDA de la orden no puede filtrar por estado. Se mira sólo la
    # llamada a `find_one`, y no el resto del cuerpo: más abajo sí hay una
    # comprobación de «pendiente», y es la correcta —después de haber
    # encontrado la orden y de haber mirado si venció—.
    busqueda = cuerpo[cuerpo.index("db.btc_remesas.find_one"):]
    busqueda = busqueda[:busqueda.index(")")]
    assert "pendiente" not in busqueda, (
        "La orden se busca filtrando por «pendiente». Un pago de una orden "
        "cancelada no encuentra nada, el webhook contesta «ya procesada», y "
        "el cliente paga sin que quede rastro de que su plata llegó.")


def test_el_pago_tardio_avisa_a_quien_puede_resolverlo():
    fuente = open(btc.__file__, encoding="utf-8").read()
    cuerpo = _cuerpo_del_webhook(fuente)
    assert 'create_notification' in cuerpo and '"role": "super_admin"' in cuerpo, (
        "Llegó plata que no se acreditó y nadie se entera. Un pago en "
        "revisión que nadie mira es un cliente que pagó y no recibió nada.")


# ══════════════════════════════════════════════════════════════════════════
# Los dos nombres de `expira_en`
# ══════════════════════════════════════════════════════════════════════════

def test_la_respuesta_distingue_los_segundos_de_la_fecha():
    """Se devolvían segundos y una fecha ISO con el MISMO nombre.

    La pantalla lo resolvía sin querer: hacía `new Date(600)`, le daba 1970, lo
    descartaba por estar en el pasado, y caía en un 1800 escrito a mano que
    resultaba ser el valor correcto. Funcionaba de casualidad y dejó de
    funcionar en cuanto la duración cambió.
    """
    fuente = open(btc.__file__, encoding="utf-8").read()
    assert '"expira_en_segundos"' in fuente, (
        "Los segundos y la fecha volvieron a llamarse igual.")
