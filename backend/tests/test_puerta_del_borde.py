"""
tests/test_puerta_del_borde.py — Que la IP no se pueda elegir.

EL AGUJERO

    Todos los límites por IP de la aplicación cuentan con
    `services/ip_cliente.ip_del_cliente`, que devolvía `CF-Connecting-IP`
    cuando estaba presente, SIN comprobar quién la había escrito.

    Esa cabecera la escribe Cloudflare pisando lo que mande el cliente… cuando
    Cloudflare está adelante. El hostname de Railway responde igual sin pasar
    por él: quien entra por ahí la escribe él mismo, la cambia en cada pedido,
    y cada intento cae en un contador distinto. Los límites no existían para
    quien conociera ese hostname.

    Lo llamativo es que `ip_cliente.py` razonaba con todo cuidado por qué no
    hay que confiar en una cabecera que manda el cliente, y después hacía una
    excepción con exactamente eso. La lectura de derecha a izquierda estaba
    bien escrita y no protegía nada, porque nunca se llegaba a ella.

EL TEST QUE IMPORTA

    `test_sin_la_llave_no_se_puede_elegir_la_ip` reproduce el ataque: veinte
    pedidos con una `CF-Connecting-IP` distinta cada uno. Antes daban veinte
    contadores; ahora dan uno solo.

POR QUE LA PUERTA ARRANCA SIN BLOQUEAR

    Porque puede tirar abajo la aplicación entera: `railway.toml` declara
    `healthcheckPath = "/api/health"`, y un 403 ahí deja el despliegue
    reiniciando en bucle. Hay tests abajo para cada exención.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import borde, ip_cliente                       # noqa: E402

LLAVE = "un-secreto-largo-y-aburrido-de-adivinar"


class _Pedido:
    """Lo mínimo que mira `ip_del_cliente`: cabeceras y socket."""

    def __init__(self, cabeceras=None, socket="10.0.0.1"):
        self.headers = {k.lower(): v for k, v in (cabeceras or {}).items()}
        self.client = type("C", (), {"host": socket})()


@pytest.fixture
def con_llave(monkeypatch):
    monkeypatch.setenv(borde.VARIABLE_LLAVE, LLAVE)
    monkeypatch.setenv(borde.VARIABLE_MODO, "exigir")
    return LLAVE


@pytest.fixture
def sin_llave(monkeypatch):
    monkeypatch.delenv(borde.VARIABLE_LLAVE, raising=False)
    monkeypatch.delenv(borde.VARIABLE_MODO, raising=False)


# ─── El agujero ───────────────────────────────────────────────────────────

def test_sin_la_llave_no_se_puede_elegir_la_ip(con_llave):
    """EL TEST DEL ARCHIVO.

    Veinte pedidos desde la misma conexión, cada uno declarando una
    `CF-Connecting-IP` distinta. Antes devolvían veinte IPs —veinte contadores,
    ningún límite—. Ahora tienen que devolver una sola.
    """
    # OJO CON COMO SE SIMULA EL ATAQUE.
    #
    # `X-Forwarded-For` lleva lo que eligió el atacante MAS la IP real que le
    # agrega Railway al final. Un proxy no reemplaza esa cabecera: acumula. Si
    # el test manda un solo valor está simulando un mundo sin proxy, y pasa o
    # falla por el motivo equivocado —la primera versión de este test falló
    # justamente así—.
    vistas = set()
    for i in range(20):
        vistas.add(ip_cliente.ip_del_cliente(_Pedido(
            {"CF-Connecting-IP": f"9.9.9.{i}",
             "X-Forwarded-For": f"9.9.9.{i}, 203.0.113.7"},
            socket="203.0.113.7")))

    assert vistas == {"203.0.113.7"}, (
        f"Se pudieron generar {len(vistas)} contadores distintos cambiando una "
        f"cabecera: {sorted(vistas)}. Los límites por IP no frenan nada.")


def test_con_la_llave_si_se_usa_la_cabecera_de_cloudflare(con_llave):
    """Por el camino bueno la cabecera es confiable: la escribe Cloudflare
    pisando lo que mande el cliente, y el secreto prueba que fue él."""
    ip = ip_cliente.ip_del_cliente(_Pedido({
        "CF-Connecting-IP": "198.51.100.4",
        borde.CABECERA: LLAVE,
        "X-Forwarded-For": "1.2.3.4, 198.51.100.4"}))
    assert ip == "198.51.100.4"


def test_una_llave_equivocada_no_alcanza(con_llave):
    ip = ip_cliente.ip_del_cliente(_Pedido({
        "CF-Connecting-IP": "9.9.9.9",
        borde.CABECERA: LLAVE + "x",
        "X-Forwarded-For": "9.9.9.9, 203.0.113.7"}))
    assert ip == "203.0.113.7", "una llave casi correcta abrió la puerta"


def test_sin_la_llave_se_cae_en_la_lectura_de_derecha_a_izquierda(con_llave):
    """El camino de respaldo ya estaba bien escrito; ahora por fin se usa."""
    ip = ip_cliente.ip_del_cliente(_Pedido({
        "X-Forwarded-For": "1.2.3.4, 5.6.7.8, 203.0.113.7"}))
    assert ip == "203.0.113.7"


def test_sin_ninguna_cabecera_queda_la_conexion(con_llave):
    assert ip_cliente.ip_del_cliente(_Pedido({}, socket="203.0.113.9")) == "203.0.113.9"


def test_si_no_hay_llave_configurada_nada_cambia(sin_llave):
    """Una variable que falta no puede romper la aplicación. Sin llave, la
    puerta está apagada y se comporta como antes."""
    assert borde.modo() == "apagado"
    assert borde.paso_por_el_borde({borde.CABECERA: "lo que sea"}) is False


def test_la_comparacion_de_la_llave_no_corta_en_la_primera_letra(con_llave):
    """Comparar con `==` corta apenas encuentra una letra distinta, y el
    tiempo que tarda dice cuántas se acertaron. Con suficientes intentos se
    adivina letra por letra. Se comprueba la FORMA, que es lo único
    observable: medir tiempos en un test da falsos rojos."""
    import inspect
    fuente = inspect.getsource(borde.paso_por_el_borde)
    assert "compare_digest" in fuente
    assert "traida == esperada" not in fuente


# ─── Que la puerta no tire abajo la aplicación ────────────────────────────

def test_el_chequeo_de_salud_de_railway_nunca_se_bloquea():
    """`railway.toml` declara `healthcheckPath = "/api/health"`. Un 403 ahí y
    el despliegue no levanta: Railway lo da por fallido y reinicia en bucle.
    Es la exención más importante de todas."""
    assert borde.esta_exenta("/api/health")

    ruta = None
    with open(os.path.join(_BACKEND, "..", "railway.toml")) as f:
        for linea in f:
            if "healthcheckPath" in linea:
                ruta = linea.split("=", 1)[1].strip().strip('"')
    assert ruta, "railway.toml ya no declara healthcheckPath"
    assert borde.esta_exenta(ruta), (
        f"Railway le pega a {ruta} y la puerta lo bloquearía: el despliegue "
        "no levantaría nunca.")


LOS_DE_AFUERA = [
    ("/api/webhook/mercadopago", "Mercado Pago: PIX y tarjeta"),
    ("/api/credits/webhook", "NOWPayments: depósitos en cripto"),
    ("/api/btc/webhook/blink", "Blink: custodia de Bitcoin"),
    ("/api/transactions/crypto-send/webhook", "pasarela de envíos en cripto"),
    ("/api/webhooks/twilio/whatsapp", "Twilio"),
    ("/api/centro-gestion/log", "integración de contabilidad"),
]


@pytest.mark.parametrize("ruta,quien", LOS_DE_AFUERA)
def test_lo_que_llama_un_tercero_no_se_bloquea(ruta, quien):
    """Ninguno de éstos va a traer nuestra cabecera, y todos tienen su propia
    autenticación. Bloquearlos es dejar de acreditar pagos."""
    assert borde.esta_exenta(ruta), f"quedaría bloqueado: {quien}"


def test_lo_que_no_esta_exento_si_pasa_por_la_puerta():
    """La guarda de la guarda: si todo estuviera exento, los tests de arriba
    pasarían y la puerta no serviría para nada."""
    for ruta in ("/api/auth/login", "/api/admin/users", "/api/transactions",
                 "/api/user/balance"):
        assert not borde.esta_exenta(ruta), ruta


def test_la_puerta_arranca_sin_bloquear(monkeypatch):
    """Con llave puesta pero sin modo, es AVISO. Una puerta que puede dejar
    afuera a todos los clientes a la vez no se estrena bloqueando."""
    monkeypatch.setenv(borde.VARIABLE_LLAVE, LLAVE)
    monkeypatch.delenv(borde.VARIABLE_MODO, raising=False)
    assert borde.modo() == "reporte"
    assert borde.revisar()["listo"] is False


def test_un_modo_escrito_mal_no_bloquea(monkeypatch):
    """Un dedazo en la variable no puede dejar la aplicación sin responder."""
    monkeypatch.setenv(borde.VARIABLE_LLAVE, LLAVE)
    for valor in ("exigir!", "bloquear", "sí", "", "exigirr"):
        monkeypatch.setenv(borde.VARIABLE_MODO, valor)
        assert borde.modo() == "reporte", valor


def test_exigir_en_mayusculas_o_con_espacios_si_vale(monkeypatch):
    monkeypatch.setenv(borde.VARIABLE_LLAVE, LLAVE)
    for valor in ("exigir", "EXIGIR", " Exigir "):
        monkeypatch.setenv(borde.VARIABLE_MODO, valor)
        assert borde.modo() == "exigir", valor
