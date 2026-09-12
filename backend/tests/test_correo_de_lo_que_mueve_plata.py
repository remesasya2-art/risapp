"""
tests/test_correo_de_lo_que_mueve_plata.py — Enterarse sin abrir la aplicación.

LO QUE PASABA

    Ningún movimiento de dinero mandaba correo. Dieciocho eventos —retiros,
    recargas, envíos, reembolsos, bonos— avisaban dentro de la aplicación y
    nada más. Quien no la abría no se enteraba de que su plata se había
    movido, y no le quedaba constancia de nada.

    El único correo de dinero que existía era el del PIX recibido en el flujo
    del gestor, y estaba escrito a mano en ese archivo.

POR QUE UNA TABLA

    Agregar la línea del correo en los dieciocho lugares es exactamente lo que
    produjo las cinco formas distintas de avisarle al equipo que hubo que
    desarmar: las copias se desincronizan y la diecinueve se olvida.

    La regla vive en `services/avisos_por_correo.POR_CORREO`, y abajo hay un
    test que la compara contra la lista de clases de aviso que mueven plata.
    Quien agregue un evento nuevo y se olvide del correo, lo ve en rojo.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                       # noqa: E402
from services import avisos_por_correo, correo       # noqa: E402
from services import notifications as n              # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    corre(b.users.insert_many([
        {"user_id": "cliente", "email": "cliente@ejemplo.com", "role": "user"},
        {"user_id": "jefa", "email": "jefa@risappbr.com", "role": "super_admin"},
        {"user_id": "sin_casilla", "role": "user"},
    ]))
    return b


@pytest.fixture
def correos(monkeypatch):
    """Intercepta lo que sale, sin tocar Resend ni el bucle."""
    salieron = []

    def _mandar(destinatario, asunto, html, *, que_es="correo"):
        salieron.append({"a": destinatario, "asunto": asunto,
                         "html": html, "que_es": que_es})

    monkeypatch.setattr(correo, "en_segundo_plano", _mandar)
    # El push es otra cosa y no se prueba acá.
    monkeypatch.setattr(n, "_push_sin_romper",
                        lambda *a, **k: asyncio.sleep(0))
    return salieron


# ─── Que salga cuando corresponde ─────────────────────────────────────────

def test_un_retiro_completado_manda_correo(base, correos):
    corre(n.create_notification(
        "cliente", "Tu retiro fue completado",
        "Enviamos 4.500,00 Bs a tu beneficiario.",
        notification_type="withdrawal_completed"))

    assert len(correos) == 1
    assert correos[0]["a"] == "cliente@ejemplo.com"
    assert correos[0]["asunto"] == "Tu retiro se completó"
    assert "4.500,00 Bs" in correos[0]["html"], (
        "El correo tiene que decir lo mismo que el aviso. Decir dos cosas "
        "distintas por dos vías sobre el mismo hecho rompe la confianza en las "
        "dos.")


def test_el_aviso_queda_guardado_igual(base, correos):
    corre(n.create_notification("cliente", "Tu retiro fue completado", "x",
                                notification_type="withdrawal_completed"))
    assert corre(base.notifications.count_documents({})) == 1


def test_un_aviso_que_no_mueve_plata_no_manda_correo(base, correos):
    """`pin_updated`, `role_change`, `soporte_*`: se ven en la aplicación y
    nada más. Un correo por cada cosita es cómo se logra que nadie los mire."""
    for tipo in ("pin_updated", "role_change", "soporte_respuesta", "info"):
        corre(n.create_notification("cliente", "Algo", "x", notification_type=tipo))
    assert correos == []


def test_cada_actualizacion_del_paquete_manda_correo(base, correos):
    """Pedido expreso. El asunto es el título del aviso, que cambia con el
    estado: repetir «Novedades de tu paquete» en los diez haría diez correos
    indistinguibles en la bandeja."""
    corre(n.create_notification(
        "cliente", "Tu paquete llegó a Pacaraima", "Está en la agencia.",
        notification_type="envio"))
    corre(n.create_notification(
        "cliente", "Ya pesamos tu paquete", "El precio quedó cerrado.",
        notification_type="envio"))

    assert [c["asunto"] for c in correos] == [
        "Tu paquete llegó a Pacaraima", "Ya pesamos tu paquete"]


def test_el_aviso_del_equipo_no_sale_por_correo(base, correos):
    """Llenarle la casilla de trabajo a cada operador es la forma más rápida
    de que deje de mirar los correos de la aplicación.

    Se usa a propósito una clase de aviso que SI está en la tabla. Con una que
    no esté —`kyc`, por ejemplo— el test pasa igual aunque el ámbito se deje de
    mirar, porque lo frena la tabla y no la regla que se quiere probar.
    """
    corre(n.create_notification(
        "jefa", "Tu retiro fue completado", "x",
        notification_type="withdrawal_completed", ambito=n.TRABAJO))
    assert correos == [], (
        "Un aviso de trabajo salió por correo. Lo tiene que frenar el ÁMBITO, "
        "no la casualidad de que su clase no esté en la tabla.")


def test_si_no_hay_casilla_no_se_rompe_nada(base, correos):
    corre(n.create_notification("sin_casilla", "Tu retiro fue completado", "x",
                                notification_type="withdrawal_completed"))
    assert correos == []
    assert corre(base.notifications.count_documents({})) == 1, (
        "El aviso tiene que quedar guardado igual.")


def test_no_se_trae_el_usuario_entero_para_mandar_un_correo(base, correos,
                                                            monkeypatch):
    """Sin proyección esto traía documento, teléfono y direcciones en CADA
    movimiento de dinero."""
    pedidos = []
    coleccion = base.users

    class _Espia:
        async def find_one(self, filtro, proyeccion=None, *a, **k):
            pedidos.append(proyeccion)
            return await coleccion.find_one(filtro, proyeccion, *a, **k)

    # Se reemplaza en la BASE y no en la colección: `base.users` devuelve un
    # envoltorio nuevo en cada acceso, así que sustituirle un método ahí no
    # llega al que se usa después.
    base.users = _Espia()
    corre(n.create_notification("cliente", "Tu retiro fue completado", "x",
                                notification_type="withdrawal_completed"))

    assert pedidos and pedidos[0], "Se pidió el usuario sin proyección."
    assert set(pedidos[0]) <= {"_id", "email", "is_active"}, (
        f"Se pidieron campos de más: {sorted(pedidos[0])}")


def test_si_el_correo_falla_el_aviso_igual_queda(base, correos, monkeypatch):
    """El movimiento de dinero ya ocurrió. Que no se pueda avisar por correo
    no puede deshacerlo ni devolver un error sobre un trabajo ya hecho."""
    def _roto(*a, **k):
        raise RuntimeError("el correo no anda")

    monkeypatch.setattr(correo, "en_segundo_plano", _roto)
    corre(n.create_notification("cliente", "Tu retiro fue completado", "x",
                                notification_type="withdrawal_completed"))

    assert corre(base.notifications.count_documents({})) == 1


# ─── La guarda: que no quede un movimiento de dinero sin correo ───────────

# Las clases de aviso que mueven plata. Sale de recorrer los dieciocho lugares
# que crean un aviso después de mover un saldo.
#
# SI AGREGAS UN EVENTO DE DINERO, AGREGALO ACA Y EN `POR_CORREO`. Este test
# existe para que el que se olvide lo vea en rojo y no meses después, cuando
# un cliente pregunte por qué no le avisaron de su retiro.
# `gestor_transaction` y `partner_bonus` estaban acá y salieron al eliminarse
# el área de socios y gestores. No los emite nadie, así que exigirles correo
# sería exigir correo para algo que no ocurre.
MUEVEN_PLATA = {
    "withdrawal_pending", "withdrawal_completed", "withdrawal_rejected",
    "recharge_approved", "recharge_rejected",
    "pix_received", "card_received", "credit_deposit", "btc_payment",
    "crypto_send_paid", "crypto_send_refunded", "crypto_send_awaiting_topup",
    "crypto_send_underpaid_review",
    "btc_enviado", "btc_remesa_enviada",
}


def test_ningun_movimiento_de_dinero_quedo_sin_correo():
    faltan = sorted(MUEVEN_PLATA - set(avisos_por_correo.POR_CORREO))
    assert not faltan, (
        "Estas clases de aviso mueven plata y no mandan correo:\n  "
        + "\n  ".join(faltan)
        + "\n\nAgregalas a POR_CORREO en services/avisos_por_correo.py.")


def test_la_tabla_no_declara_clases_de_aviso_que_no_existen():
    """Al revés: una entrada que sobra es una pista falsa.

    Se recorre la aplicación buscando los `notification_type=` que se usan de
    verdad. Una clase en la tabla que ya nadie emite hace creer que ese correo
    sale, y nadie va a buscar por qué no llegó.
    """
    import ast

    usados = set()
    for carpeta in ("routes", "services"):
        raiz = os.path.join(_BACKEND, carpeta)
        for nombre in sorted(os.listdir(raiz)):
            if not nombre.endswith(".py"):
                continue
            with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
                arbol = ast.parse(f.read())
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, ast.Call):
                    continue
                for kw in nodo.keywords:
                    if (kw.arg == "notification_type"
                            and isinstance(kw.value, ast.Constant)):
                        usados.add(kw.value.value)

    fantasmas = sorted(set(avisos_por_correo.POR_CORREO) - usados)
    assert not fantasmas, (
        "POR_CORREO declara clases de aviso que ya nadie emite:\n  "
        + "\n  ".join(fantasmas))


def test_la_guarda_de_arriba_sabe_leer_los_tipos():
    """Una guarda que no encuentra nada pasa siempre.

    Si el recorrido se rompiera —un cambio en cómo se llama a
    `create_notification`—, el conjunto de «usados» quedaría vacío y todo se
    vería como fantasma. Acá se comprueba que encuentra los que sabemos que
    están.
    """
    import ast
    fuente = ast.parse('await create_notification(user_id="u", '
                       'notification_type="withdrawal_completed")')
    encontrados = {kw.value.value for nodo in ast.walk(fuente)
                   if isinstance(nodo, ast.Call)
                   for kw in nodo.keywords
                   if kw.arg == "notification_type"}
    assert encontrados == {"withdrawal_completed"}
