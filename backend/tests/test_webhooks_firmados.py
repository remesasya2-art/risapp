"""
tests/test_webhooks_firmados.py — Las cinco puertas por las que entra el dinero.

DE QUE SE TRATA

    Cinco rutas de la aplicación no piden sesión ni clave: son los webhooks de
    Mercado Pago, Twilio, Blink, NOWPayments (créditos) y NOWPayments (envío
    cripto). Las llama el proveedor cuando algo pasó, y lo que dicen mueve
    plata: «este PIX se pagó», «esta factura se cobró».

    Lo único que las separa de internet es la firma. Por eso están declaradas
    como excepción en `test_puertas_sin_llave.py`, con el motivo «lo protege la
    firma» — y una excepción escrita así necesita un test que la respalde, o es
    nada más que una frase.

LAS DOS MITADES DE UNA FIRMA QUE SIRVE

    1. QUE SEA VALIDA. Sin eso, cualquiera manda «se pagó» y se acredita.
    2. QUE SEA RECIENTE. Una notificación firmada, capturada una vez, sigue
       siendo válida para siempre si nadie mira su hora: se reenvía cuando se
       quiera y el servidor la vuelve a atender.

    De los cinco, Blink miraba la hora y Mercado Pago no. El `ts` viaja adentro
    del manifiesto firmado —no se puede cambiar sin romper la firma— así que
    mirarlo no cuesta nada; simplemente no se estaba haciendo.

    Acreditar dos veces no podía: el webhook de MP exige que el pago siga en
    «pending» y le vuelve a preguntar a Mercado Pago antes de acreditar. Lo que
    un reenvío conseguía era gastar una consulta a la API de MP —que está
    limitada— y llenar el registro de eventos que no se distinguen de los
    legítimos.
"""
import hashlib
import hmac
import json
import os
import sys
import time

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                                      # noqa: E402

SECRETO = "un-secreto-de-prueba"
DATA_ID = "1234567890"
REQUEST_ID = "req-abc"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


@pytest.fixture
def cliente(base, monkeypatch):
    monkeypatch.setenv("MERCADOPAGO_WEBHOOK_SECRET", SECRETO)
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


def firma(ts, data_id=DATA_ID, request_id=REQUEST_ID, secreto=SECRETO):
    """La firma como la arma Mercado Pago: sobre el manifiesto, no sobre el
    cuerpo. El `ts` va adentro, así que cambiarlo la invalida."""
    manifiesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secreto.encode(), manifiesto.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def avisa(cliente, x_signature, data_id=DATA_ID, request_id=REQUEST_ID):
    return cliente.post(
        f"/api/webhook/mercadopago?data.id={data_id}",
        content=json.dumps({"type": "payment", "data": {"id": data_id}}),
        headers={"content-type": "application/json",
                 "x-signature": x_signature,
                 "x-request-id": request_id})


# ══════════════════════════════════════════════════════════════════════════
# 1. Mercado Pago: la firma
# ══════════════════════════════════════════════════════════════════════════

def test_sin_firma_no_se_atiende(cliente):
    r = cliente.post(f"/api/webhook/mercadopago?data.id={DATA_ID}",
                     json={"type": "payment", "data": {"id": DATA_ID}})
    assert r.status_code == 401


def test_UNA_FIRMA_INVENTADA_NO_ENTRA(cliente):
    ahora = int(time.time())
    assert avisa(cliente, f"ts={ahora},v1=" + "0" * 64).status_code == 401


def test_una_firma_de_otro_secreto_no_entra(cliente):
    ahora = int(time.time())
    otra = firma(ahora, secreto="el-secreto-de-otro")
    assert avisa(cliente, otra).status_code == 401


def test_la_firma_no_vale_para_otro_pago(cliente):
    """La firma cubre el `data.id`. Reusarla para un pago distinto —que es lo
    que haría alguien con una notificación ajena en la mano— tiene que fallar."""
    ahora = int(time.time())
    valida_para_otro = firma(ahora, data_id="9999999999")
    assert avisa(cliente, valida_para_otro, data_id=DATA_ID).status_code == 401


def test_una_firma_valida_y_fresca_pasa_el_control(cliente):
    """Pasa el control de firma. Después no encuentra el pago en la base y
    contesta que no existe — que es exactamente lo que tiene que pasar: lo que
    se prueba acá es la puerta, no lo que hay adentro."""
    r = avisa(cliente, firma(int(time.time())))
    assert r.status_code == 200, r.text
    assert r.json().get("error") == "payment_not_found"


def test_SIN_SECRETO_CONFIGURADO_EL_WEBHOOK_NO_SE_ABRE(base, monkeypatch):
    """El caso de la mala configuración, que es como esto se rompe de verdad.

    Si `MERCADOPAGO_WEBHOOK_SECRET` no está puesta, hay dos conductas posibles:
    atender igual —«bueno, no hay con qué verificar»— o plantarse. La primera
    convierte una variable de entorno olvidada en un webhook abierto que
    acredita saldo, y no avisa: todo parece andar.

    Este test faltaba. Se descubrió rompiendo a mano el `raise` de esa rama y
    viendo que ningún test se ponía en rojo, porque el cliente de los demás
    tests siempre configura el secreto.
    """
    monkeypatch.delenv("MERCADOPAGO_WEBHOOK_SECRET", raising=False)
    from fastapi.testclient import TestClient
    from server import app
    sin_secreto = TestClient(app)

    r = avisa(sin_secreto, firma(int(time.time())))
    assert r.status_code == 401, \
        "sin secreto configurado el webhook atendió igual"
    assert r.json()["detail"] == "webhook_secret_not_configured"


# ══════════════════════════════════════════════════════════════════════════
# 2. Mercado Pago: la frescura
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_NOTIFICACION_VIEJA_NO_SE_VUELVE_A_ATENDER(cliente):
    """El caso del reenvío: una notificación capturada hace una hora tiene la
    firma perfectamente válida. Lo que la descarta es la hora."""
    hace_una_hora = int(time.time()) - 3600
    r = avisa(cliente, firma(hace_una_hora))
    assert r.status_code == 401
    assert r.json()["detail"] == "stale_signature"


def test_una_notificacion_del_futuro_tampoco(cliente):
    """El reloj del proveedor puede ir unos segundos adelantado, pero no una
    hora. Una marca muy futura es un intento de esquivar la ventana."""
    dentro_de_una_hora = int(time.time()) + 3600
    assert avisa(cliente, firma(dentro_de_una_hora)).status_code == 401


@pytest.mark.parametrize("ts", ["", "ayer", "1.2.3", "9" * 40])
def test_un_ts_ilegible_no_pasa_de_largo(cliente, ts):
    """Lo importante es que un `ts` que no se puede leer se RECHACE, y no que
    se saltee el control como si no estuviera."""
    assert avisa(cliente, firma(ts)).status_code == 401


def test_la_ventana_es_la_misma_que_la_del_otro_webhook():
    """Dos webhooks del mismo servidor con criterios distintos es cómo uno de
    los dos se queda sin el control y nadie lo nota."""
    from routes.gestor_pix import VENTANA_WEBHOOK_SEGUNDOS
    fuente = open(os.path.join(_BACKEND, "routes", "btc_lightning.py"),
                  encoding="utf-8").read()
    assert str(VENTANA_WEBHOOK_SEGUNDOS) in fuente


def test_dentro_de_la_ventana_sigue_pasando(cliente):
    """Un minuto de atraso es normal: el proveedor reintenta, la red demora.
    Una ventana tan corta que rechaza reintentos legítimos pierde pagos."""
    from routes.gestor_pix import VENTANA_WEBHOOK_SEGUNDOS
    hace_un_rato = int(time.time()) - (VENTANA_WEBHOOK_SEGUNDOS - 30)
    assert avisa(cliente, firma(hace_un_rato)).status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 3. Que los cinco tengan las dos mitades
# ══════════════════════════════════════════════════════════════════════════

# Dónde vive cada webhook y con qué compara la firma. La lista es la misma que
# está exceptuada en `test_puertas_sin_llave.py`: si allá se agrega un webhook
# nuevo, acá tiene que aparecer también.
WEBHOOKS = [
    ("routes/gestor_pix.py", "compare_digest", True),
    ("routes/webhooks.py", "RequestValidator", False),
    ("routes/btc_lightning.py", "compare_digest", True),
    ("routes/credits.py", "verify_ipn_signature", False),
    ("routes/transactions.py", "verify_ipn_signature", False),
]


@pytest.mark.parametrize("archivo, comprobacion, _mira_hora", WEBHOOKS)
def test_cada_webhook_verifica_su_firma(archivo, comprobacion, _mira_hora):
    fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert comprobacion in fuente, (
        f"{archivo}: no se ve la verificación de firma. Es lo único que separa "
        "esa ruta de internet.")


@pytest.mark.parametrize("archivo, _c, mira_hora", WEBHOOKS)
def test_los_que_pueden_mirar_la_hora_la_miran(archivo, _c, mira_hora):
    """Sólo se le exige a los que reciben una marca de tiempo firmada. Twilio
    valida sobre la URL y el cuerpo, y NOWPayments firma sólo el cuerpo: no hay
    hora que mirar, y pedirla sería pedir algo que no existe."""
    if not mira_hora:
        pytest.skip(f"{archivo}: el proveedor no manda una marca de tiempo firmada")
    fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert "time.time()" in fuente, (
        f"{archivo}: recibe una marca de tiempo firmada y no la mira, así que "
        "una notificación capturada vale para siempre")


def test_LA_LISTA_DE_ACA_Y_LA_DE_LAS_EXCEPCIONES_SON_LA_MISMA():
    """Si alguien agrega un webhook y lo exceptúa del tope de intentos con el
    motivo «lo protege la firma», este test le pide que además lo pruebe."""
    from test_puertas_sin_llave import SIN_TOPE_A_PROPOSITO
    exceptuados = {p for (_, p), motivo in SIN_TOPE_A_PROPOSITO.items()
                   if "firma" in motivo}
    assert len(exceptuados) == len(WEBHOOKS), (
        f"hay {len(exceptuados)} webhooks exceptuados por su firma y "
        f"{len(WEBHOOKS)} probados acá. Los que faltan no tienen quien respalde "
        "la excepción.")
