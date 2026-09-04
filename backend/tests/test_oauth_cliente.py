"""
tests/test_oauth_cliente.py — El cliente OAuth 2.0 contra terceros.

QUE SE PRUEBA, Y POR QUE ESTAS COSAS

    Pedir un token es la parte fácil y se rompe sola si está mal. Lo que se
    prueba acá es todo lo de alrededor, que es lo que falla en producción y no
    falla en el escritorio de nadie:

      - Un token que vence a mitad de vuelo.
      - Veinte peticiones simultáneas al arrancar pidiendo veinte tokens.
      - Reintentar contra credenciales equivocadas.
      - Un token revocado antes de su vencimiento.
      - La llave de idempotencia, que si falta no rompe nada: deja pasar un
        cobro duplicado, que es peor.

    El reloj se controla con un doble de `time.monotonic`. Sin eso, probar el
    vencimiento pide esperar de verdad, y un test que duerme cinco minutos es
    un test que alguien termina borrando.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

import httpx                                                    # noqa: E402

from services import oauth_cliente as oc                        # noqa: E402


def corre(coro):
    return asyncio.run(coro)


# Se guarda ANTES de parchear. `oc.asyncio` es el mismo módulo `asyncio`, así
# que parchear `oc.asyncio.sleep` parchea el global — y una lambda que llame a
# `asyncio.sleep` se llamaría a sí misma. Recursión infinita, y el error que
# sale («maximum recursion depth») no se parece en nada a la causa.
_dormir_de_verdad = asyncio.sleep


@pytest.fixture
def sin_esperas(monkeypatch):
    """Las esperas entre reintentos, en cero. El test no puede tardar lo que
    tarda la espera creciente de producción."""
    async def _ya(*_a, **_k):
        await _dormir_de_verdad(0)
    monkeypatch.setattr(oc.asyncio, "sleep", _ya)


CRED = oc.Credenciales(
    token_url="https://proveedor.test/oauth/token",
    client_id="id_publico",
    client_secret="secreto",
    scope="pagos",
)


class Reloj:
    """Un `monotonic` que sólo avanza cuando se lo pide."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, segundos):
        self.t += segundos


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj()
    monkeypatch.setattr(oc.time, "monotonic", r)
    return r


class Transporte(httpx.AsyncBaseTransport):
    """Responde según lo que se le programe, y anota lo que recibió."""

    def __init__(self, respuestas):
        # `respuestas`: lista de (status, json) o de callables(request).
        self.respuestas = list(respuestas)
        self.pedidos = []

    async def handle_async_request(self, request):
        # Cede el control ANTES de anotar el pedido. Sin este punto de
        # suspensión, la primera corrutina termina entera antes de que la
        # segunda arranque, y el test de la estampida no prueba nada:
        # sacarle el candado al cliente lo dejaba en verde igual.
        await _dormir_de_verdad(0)
        self.pedidos.append(request)
        if not self.respuestas:                              # pragma: no cover
            raise AssertionError(f"pedido inesperado a {request.url}")
        siguiente = self.respuestas.pop(0)
        if callable(siguiente):
            siguiente = siguiente(request)
        estado, cuerpo = siguiente
        return httpx.Response(estado, json=cuerpo, request=request)


def cliente(respuestas, **kw):
    t = Transporte(respuestas)
    http = httpx.AsyncClient(transport=t)
    return oc.ClienteOAuth(CRED, cliente_http=http, **kw), t


TOKEN_OK = (200, {"access_token": "tok_1", "expires_in": 3600, "token_type": "Bearer"})


# ══════════════════════════════════════════════════════════════════════════
# El token
# ══════════════════════════════════════════════════════════════════════════

def test_pide_el_token_y_lo_devuelve(reloj):
    c, t = cliente([TOKEN_OK])

    assert corre(c.token()) == "tok_1"
    assert t.pedidos[0].url == CRED.token_url
    cuerpo = t.pedidos[0].content.decode()
    assert "grant_type=client_credentials" in cuerpo
    assert "scope=pagos" in cuerpo


def test_el_token_se_reusa_mientras_este_vigente(reloj):
    """Pedir uno nuevo en cada llamada es gratis para nosotros y caro para el
    proveedor, que suele limitarlo por abuso."""
    c, t = cliente([TOKEN_OK])

    corre(c.token())
    reloj.avanzar(100)
    corre(c.token())

    assert len(t.pedidos) == 1


def test_se_renueva_ANTES_de_vencer(reloj):
    """Un token que vale dos segundos más no vale.

    Entre que se decide usarlo y llega al otro lado, venció — y el proveedor
    devuelve 401 en una operación que ya se dio por lanzada.
    """
    c, t = cliente([TOKEN_OK, (200, {"access_token": "tok_2", "expires_in": 3600})])

    corre(c.token())
    # Faltan 30 s para vencer: dentro del margen de 60 s, así que ya no sirve.
    reloj.avanzar(3600 - 30)

    assert corre(c.token()) == "tok_2"
    assert len(t.pedidos) == 2


def test_sin_expires_in_se_asume_poco(reloj):
    """Asumir mucho significa usar un token muerto durante horas sin entender
    por qué todo devuelve 401."""
    c, t = cliente([(200, {"access_token": "tok_1"}),
                    (200, {"access_token": "tok_2"})])

    corre(c.token())
    reloj.avanzar(oc.DURACION_POR_DEFECTO)
    corre(c.token())

    assert len(t.pedidos) == 2


def test_un_expires_in_basura_no_rompe(reloj):
    c, _ = cliente([(200, {"access_token": "tok_1", "expires_in": "un rato"})])
    assert corre(c.token()) == "tok_1"


def test_una_respuesta_sin_access_token_no_pasa_por_buena(reloj):
    c, _ = cliente([(200, {"ok": True})])
    with pytest.raises(oc.NoSePudoAutenticar):
        corre(c.token())


# ══════════════════════════════════════════════════════════════════════════
# La estampida del arranque
# ══════════════════════════════════════════════════════════════════════════

def test_veinte_llamadas_simultaneas_piden_UN_token(reloj):
    """Sin candado, veinte peticiones ven el token vacío y piden veinte.

    Algunos proveedores lo cobran; otros lo toman por abuso y bloquean la
    cuenta. Es el caso del arranque, cuando el token todavía no existe.
    """
    c, t = cliente([TOKEN_OK])

    async def veinte():
        return await asyncio.gather(*[c.token() for _ in range(20)])

    resultados = corre(veinte())

    assert resultados == ["tok_1"] * 20
    assert len(t.pedidos) == 1, f"se pidieron {len(t.pedidos)} tokens en vez de uno"


# ══════════════════════════════════════════════════════════════════════════
# Los errores
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("estado", [400, 401, 403])
def test_credenciales_mal_no_se_reintentan(reloj, estado):
    """Un secreto equivocado no se arregla insistiendo: reintentar es golpear
    la puerta más fuerte, y algunos proveedores bloquean por eso."""
    c, t = cliente([(estado, {"error": "invalid_client"})])

    with pytest.raises(oc.ErrorDeCredenciales):
        corre(c.token())

    assert len(t.pedidos) == 1, "se reintentó contra credenciales equivocadas"


def test_un_error_del_servidor_si_se_reintenta(reloj, sin_esperas):
    c, t = cliente([(503, {}), (503, {}), TOKEN_OK])

    assert corre(c.token()) == "tok_1"
    assert len(t.pedidos) == 3


def test_si_no_se_recupera_nunca_levanta_con_claridad(reloj, sin_esperas):
    c, _ = cliente([(503, {})] * oc.REINTENTOS)

    with pytest.raises(oc.NoSePudoAutenticar):
        corre(c.token())


def test_el_secreto_no_aparece_al_imprimir_las_credenciales():
    """Un `logger.error("... %s", credenciales)` escrito con prisa no puede
    filtrar el secreto al log, que lo lee mucha más gente que la bóveda."""
    for texto in (repr(CRED), str(CRED), f"{CRED}"):
        assert "secreto" not in texto, "el secreto se filtra al imprimir"
        assert "client_secret" not in texto
    assert "id_publico" in repr(CRED), (
        "tapar el id además del secreto no ayuda a depurar")


# ══════════════════════════════════════════════════════════════════════════
# Las llamadas
# ══════════════════════════════════════════════════════════════════════════

def test_la_llamada_va_con_el_bearer(reloj):
    c, t = cliente([TOKEN_OK, (200, {"ok": True})])

    corre(c.pedir("GET", "https://proveedor.test/saldo"))

    assert t.pedidos[1].headers["authorization"] == "Bearer tok_1"


def test_un_post_lleva_llave_de_idempotencia(reloj):
    """Si falta, no falla nada: deja pasar un cobro duplicado. Por eso se
    prueba — un error que no rompe es el que nadie descubre."""
    c, t = cliente([TOKEN_OK, (200, {})])

    corre(c.pedir("POST", "https://proveedor.test/pagos", json={"monto": 1}))

    assert t.pedidos[1].headers.get("idempotency-key")


def test_la_llave_que_se_pasa_es_la_que_viaja(reloj):
    """La generada acá cambia en cada llamada, así que un reintento del
    llamador sería un pedido nuevo. La de él es la que sirve."""
    c, t = cliente([TOKEN_OK, (200, {})])

    corre(c.pedir("POST", "https://proveedor.test/pagos", idempotency_key="mia_123"))

    assert t.pedidos[1].headers["idempotency-key"] == "mia_123"


def test_un_get_no_lleva_llave(reloj):
    """Repetir un GET no repite ningún efecto."""
    c, t = cliente([TOKEN_OK, (200, {})])

    corre(c.pedir("GET", "https://proveedor.test/saldo"))

    assert "idempotency-key" not in t.pedidos[1].headers


def test_la_cabecera_de_idempotencia_es_configurable(reloj):
    """Cada proveedor la nombra distinto. Mandarla con el nombre equivocado es
    lo mismo que no mandarla, y tampoco falla."""
    cred = oc.Credenciales(token_url=CRED.token_url, client_id="x",
                           client_secret="y", cabecera_idempotencia="X-Chave")
    t = Transporte([TOKEN_OK, (200, {})])
    c = oc.ClienteOAuth(cred, cliente_http=httpx.AsyncClient(transport=t))

    corre(c.pedir("POST", "https://proveedor.test/pagos"))

    assert t.pedidos[1].headers.get("x-chave")


def test_un_401_renueva_el_token_y_reintenta_una_vez(reloj):
    """El token puede revocarse antes de vencer. Sin esto, la operación falla
    con un token que ya no sirve y nadie vuelve a intentar."""
    c, t = cliente([TOKEN_OK,
                    (401, {"error": "expired"}),
                    (200, {"access_token": "tok_2", "expires_in": 3600}),
                    (200, {"ok": True})])

    r = corre(c.pedir("GET", "https://proveedor.test/saldo"))

    assert r.status_code == 200
    assert t.pedidos[3].headers["authorization"] == "Bearer tok_2"


def test_un_401_persistente_no_hace_un_bucle(reloj):
    """Reintentar en bucle contra un 401 permanente es un bucle infinito con
    credenciales adentro. Se reintenta UNA vez y se devuelve el 401."""
    c, t = cliente([TOKEN_OK,
                    (401, {}),
                    (200, {"access_token": "tok_2", "expires_in": 3600}),
                    (401, {})])

    r = corre(c.pedir("GET", "https://proveedor.test/saldo"))

    assert r.status_code == 401
    assert len(t.pedidos) == 4, "reintentó más de una vez"
