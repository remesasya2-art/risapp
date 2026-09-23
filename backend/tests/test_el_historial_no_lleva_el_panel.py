"""
tests/test_el_historial_no_lleva_el_panel.py — Que el historial del cliente
lleve su operación y nada del panel.

QUE PASABA

    Las dos rutas del historial —la lista y el detalle— pedían el documento de
    la transacción con `{"_id": 0}`. Eso es una lista de lo PROHIBIDO con un
    solo elemento: saca el identificador interno de Mongo y deja pasar todo lo
    demás.

    Y al documento de una orden le escribe el panel mientras la procesa. Pedido
    tal como lo pide el navegador del cliente, esto es lo que volvía de una
    orden que pasó por un lote:

        assigned_to, assigned_to_name, assigned_at, estado_admin, lote_id,
        processed_by, paid_from_bank, hidden_from_admin

    El peor es `assigned_to_name`. Se llena con `full_name or name or email`
    —en `routes/admin.py` y en `services/lotes_de_pago.py`, las dos con la
    misma última alternativa—, así que un agente que no tenga el nombre
    cargado le deja SU DIRECCION DE CORREO escrita en la orden del cliente.
    Cerrar el lote no la borra. De ahí viajaba al navegador del cliente, que es
    donde no puede estar el correo de una persona del equipo.

POR QUE ESTE ARCHIVO, Y POR QUE TIENE DOS MITADES

    La primera mitad prueba la ruta: que lo del panel no salga y que lo del
    cliente sí.

    La segunda mitad es la que evita el modo de fallar de verdad. Si a la
    lista le falta un campo que la pantalla muestra, **la pantalla no da
    error**: muestra un espacio vacío. Nadie se entera hasta que un cliente
    pregunta por qué su comprobante no está.

    Así que la segunda mitad LEE LAS PANTALLAS DEL CLIENTE y exige que cada
    campo que muestran esté en la lista del servidor. Es la única forma de que
    quien agregue un dato a la pantalla se entere en el momento.

    Y tiene su propio guardián: una guarda que lee código con expresiones
    regulares se queda CIEGA si alguien renombra la variable que vigila, y una
    guarda ciega pasa en verde sin mirar nada. `test_la_guarda_no_esta_ciega`
    está para eso.

LA PLATA SE ESCRIBE CON `to_decimal128`, IGUAL QUE LA APP

    Un test que escriba `1234.56` a secas pasa con el producto roto: la app
    guarda el dinero en `Decimal128` y `mongomock` sólo lo conserva si el test
    lo inserta así. Por eso acá se inserta como lo inserta `services/saldos.py`
    y se pide la respuesta por HTTP, que es donde el `Decimal128` sin convertir
    reventaba con un 500 pelado.
"""
import asyncio
import os
import pathlib
import re
import sys
import types
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from routes.transactions import LO_QUE_VE_EL_CLIENTE                 # noqa: E402

CLIENTE_ID = "u_ana"


def _ya(corrutina):
    return asyncio.run(corrutina)


def _sin_webpush():
    """`pywebpush` no compila en este entorno y las rutas lo arrastran."""
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


def _app(nombre):
    _sin_webpush()
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.user import User
    from routes.transactions import router
    from routes import dependencies as deps

    ana = User(user_id=CLIENTE_ID, name="Ana Cliente", email="ana@ejemplo.test",
               role="user")

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ana
    return TestClient(app), base


# ─── Lo que le escribe el panel a la orden mientras la procesa ────────────
#
# Los nombres y los valores son los que escriben de verdad `routes/admin.py`
# (al tomar una orden) y `services/lotes_de_pago.py` (al armar el lote).
DEL_PANEL = {
    "assigned_to": "adm_9",
    # El caso que hay que evitar: el agente sin nombre cargado deja su correo.
    "assigned_to_name": "operador@ejemplo.test",
    "estado_admin": "en_lote",
    "lote_id": "lote_abc123",
    "processed_by": "adm_9",
    "paid_from_bank": "cuenta_interna_3",
    "hidden_from_admin": False,
}

# Lo que la pantalla del cliente muestra de su propia operación.
DEL_CLIENTE = {
    "transaction_id": "tx_1",
    "display_id": "W-000123",
    "type": "withdrawal",
    "status": "completed",
    "currency_input": "RIS",
    "beneficiary_data": {"full_name": "Fulana de Tal", "bank": "0102",
                         "account_number": "01020123456789012345"},
    "proof_images": ["/api/media/comprobante_1.jpg",
                     "/api/media/comprobante_2.jpg"],
}


def _sembrar_una_remesa_procesada(base, **extra):
    """Una remesa como queda DESPUES de que el agente subió el comprobante.

    O sea: con la foto colgada de la orden y con toda la marca del panel
    encima, que es el documento que este test vino a mirar.
    """
    from services.money import to_decimal128

    async def hacerlo():
        doc = {
            "user_id": CLIENTE_ID,
            # Como la escribe la app, no como la escribiría un test distraído.
            "amount_input": to_decimal128(Decimal("100.00")),
            "amount_output": to_decimal128(Decimal("12345.67")),
            **DEL_CLIENTE,
            **DEL_PANEL,
        }
        doc.update(extra)
        await base.transactions.insert_one(doc)

    _ya(hacerlo())


# ═══ Primera mitad: la ruta ══════════════════════════════════════════════

def test_el_correo_del_agente_no_llega_al_navegador_del_cliente():
    """El caso concreto que motivó todo esto."""
    cliente, base = _app("ris_hist_correo")
    _sembrar_una_remesa_procesada(base)

    r = cliente.get("/api/transactions")
    assert r.status_code == 200, r.text
    assert "operador@ejemplo.test" not in r.text, (
        "el correo del agente que procesó la orden viajó al cliente")


def test_el_correo_del_agente_no_llega_en_el_detalle():
    """La otra ruta tenía la misma proyección, y se arregla aparte."""
    cliente, base = _app("ris_hist_correo_det")
    _sembrar_una_remesa_procesada(base)

    r = cliente.get("/api/transactions/tx_1")
    assert r.status_code == 200, r.text
    assert "operador@ejemplo.test" not in r.text, (
        "el correo del agente viajó al cliente por el detalle")


@pytest.mark.parametrize("campo", sorted(DEL_PANEL))
def test_lo_que_escribe_el_panel_no_sale_en_la_lista(campo):
    cliente, base = _app(f"ris_hist_lista_{campo}")
    _sembrar_una_remesa_procesada(base)

    r = cliente.get("/api/transactions")
    assert r.status_code == 200, r.text
    assert campo not in r.json()["transactions"][0], (
        f"«{campo}» es del panel y salió en el historial del cliente")


@pytest.mark.parametrize("campo", sorted(DEL_PANEL))
def test_lo_que_escribe_el_panel_no_sale_en_el_detalle(campo):
    cliente, base = _app(f"ris_hist_det_{campo}")
    _sembrar_una_remesa_procesada(base)

    r = cliente.get("/api/transactions/tx_1")
    assert r.status_code == 200, r.text
    assert campo not in r.json(), (
        f"«{campo}» es del panel y salió en el detalle del cliente")


def test_el_comprobante_sigue_llegando():
    """Lo que el cliente viene a buscar a su historial.

    El agente sube las fotos al lote, el sistema las adjudica y quedan
    colgadas de la orden en `proof_images`. Si la proyección se las come, el
    cliente deja de ver su comprobante y la pantalla no da ningún error: dice
    «No hay comprobante disponible».
    """
    cliente, base = _app("ris_hist_comprobante")
    _sembrar_una_remesa_procesada(base)

    # La lista dice que lo hay —es lo que dibuja el ojito—, y el detalle, que
    # es lo que se pide al tocarlo, trae las fotos. Ver models/movimientos.py.
    tx = cliente.get("/api/transactions").json()["transactions"][0]
    assert tx["tiene_comprobante"] is True

    detalle = cliente.get("/api/transactions/tx_1").json()
    assert detalle["proof_images"] == DEL_CLIENTE["proof_images"]


def test_llega_todo_lo_que_la_pantalla_muestra():
    cliente, base = _app("ris_hist_todo")
    _sembrar_una_remesa_procesada(base)

    from services.las_fotos import LAS_FOTOS
    tx = cliente.get("/api/transactions").json()["transactions"][0]
    detalle = cliente.get("/api/transactions/tx_1").json()
    for campo, valor in DEL_CLIENTE.items():
        # Las fotos no viajan en la lista: llegan en el detalle.
        donde = detalle if campo in LAS_FOTOS else tx
        assert donde.get(campo) == valor, f"falta «{campo}» en el historial"


def test_el_envio_por_bitcoin_no_queda_en_blanco():
    """Los nombres en español del flujo de Bitcoin.

    `routes/btc_lightning.py` guarda `tipo`, `estado`, `beneficiario` y
    `usd_cliente` en vez de los nombres en inglés, y la misma pantalla los lee
    de las dos formas. Una lista de lo permitido que sólo tuviera los nombres
    en inglés dejaría este historial en blanco sin que nada avise.
    """
    cliente, base = _app("ris_hist_btc")

    async def sembrar():
        await base.transactions.insert_one({
            "transaction_id": "tx_btc", "user_id": CLIENTE_ID,
            "tipo": "envio", "subtipo": "btc_lightning", "estado": "procesando",
            "display_id": "ABC12345",
            "amount_ves": 12000.0, "usd_cliente": 55.0, "ves_recibe": 12000.0,
            "beneficiario": "Fulana de Tal",
            "beneficiario_data": {"full_name": "Fulana de Tal",
                                  "bank_code": "0102"},
            "comprobante_pago": "/api/media/btc.jpg",
        })

    _ya(sembrar())

    tx = cliente.get("/api/transactions").json()["transactions"][0]
    for campo in ("tipo", "subtipo", "estado", "usd_cliente", "ves_recibe",
                  "beneficiario", "beneficiario_data"):
        assert campo in tx, f"el historial de Bitcoin perdió «{campo}»"
    # La foto de Bitcoin está en `comprobante_pago`, no en `proof_images`: si
    # la pregunta de la lista no mirara ese campo, el ojito no aparecería.
    assert tx["tiene_comprobante"] is True
    assert cliente.get("/api/transactions/tx_btc").json()["comprobante_pago"] == "/api/media/btc.jpg"


def test_la_plata_sale_como_numero_y_no_como_decimal128():
    """Pedida por HTTP, que es donde el `Decimal128` sin convertir da un 500.

    La proyección no toca esto, pero es la respuesta donde hay que verlo: si
    alguien agrega un campo de dinero a la lista y se olvida de sumarlo a
    `_TX_MONEY_2`, la pantalla se cae con un 500 y el registro habla de un
    tipo de bson.
    """
    cliente, base = _app("ris_hist_plata")
    _sembrar_una_remesa_procesada(base)

    tx = cliente.get("/api/transactions").json()["transactions"][0]
    assert tx["amount_input"] == 100.00
    assert tx["amount_output"] == 12345.67


# ═══ Segunda mitad: la guarda contra el olvido ═══════════════════════════

_RAIZ = pathlib.Path(_BACKEND).parent
_FRONT = _RAIZ / "frontend" / "src"

# Las pantallas que muestran una transacción del historial, las variables de
# cada una que contienen la transacción que devolvió el servidor, y de CUAL de
# las dos rutas vino.
#
# Importa de cuál: la lista no trae las fotos y el detalle sí. Una pantalla
# que leyera `tx.proof_images` de la lista mostraría el ojito apagado sin dar
# error, que es el modo de fallar que este test está para ver.
#
# `normalized` es la copia que hace `useComprobante` antes de abrir el
# comprobante: le escribe `proof_image` cuando el envío por Bitcoin trae la
# foto en `comprobante_pago`. `deLaLista` es la fila que tocó el cliente.
LISTA, DETALLE = "lista", "detalle"
PANTALLAS = (
    ("pages/History.jsx", ("tx",), LISTA),
    ("pages/History.jsx", ("selectedVoucher",), DETALLE),
    ("pages/Dashboard.jsx", ("tx",), LISTA),
    ("pages/Dashboard.jsx", ("selectedVoucher",), DETALLE),
    ("components/dashboard/TransactionItem.jsx", ("tx",), LISTA),
    ("hooks/useComprobante.js", ("deLaLista",), LISTA),
    ("hooks/useComprobante.js", ("normalized",), DETALLE),
)


def _lo_que_manda(ruta):
    from models.movimientos import MovimientoEnLaLista
    if ruta == LISTA:
        return set(MovimientoEnLaLista.model_fields)
    return set(LO_QUE_VE_EL_CLIENTE)

# Campos que la pantalla se arma sola y NO vienen del servidor. Hoy no hay
# ninguno; cuando aparezca uno, va acá con el motivo al lado, y así queda
# escrito que se lo pensó en vez de que la guarda se haya aflojado sola.
SE_LOS_ARMA_LA_PANTALLA = frozenset()


def _campos_que_lee(texto, variables):
    campos = set()
    for v in variables:
        campos |= set(re.findall(rf"\b{v}\.([a-zA-Z_][a-zA-Z0-9_]*)", texto))
    return campos


def test_cada_campo_que_muestra_la_pantalla_esta_en_la_lista():
    """El modo de fallar silencioso de la proyección.

    Si a `LO_QUE_VE_EL_CLIENTE` le falta un campo que la pantalla muestra, no
    hay error: hay un espacio vacío. Este test es lo que hace que quien
    agregue el campo se entere ahora y no cuando pregunte un cliente.

    Si falla por un campo que la pantalla calcula sola, va a
    `SE_LOS_ARMA_LA_PANTALLA`. Si falla por un campo que sí viene del
    servidor, se agrega a la lista de la ruta.
    """
    faltan = {}
    for archivo, variables, ruta in PANTALLAS:
        texto = (_FRONT / archivo).read_text(encoding="utf-8")
        for campo in _campos_que_lee(texto, variables):
            if campo in _lo_que_manda(ruta) or campo in SE_LOS_ARMA_LA_PANTALLA:
                continue
            faltan.setdefault(campo, []).append(f"{archivo}, de la {ruta}")

    assert not faltan, (
        "la pantalla del cliente muestra campos que el servidor ya no le "
        "manda, y va a mostrarlos vacíos sin dar error:\n" +
        "\n".join(f"  {c}  ({', '.join(a)})" for c, a in sorted(faltan.items())))


@pytest.mark.parametrize("archivo,variables,ruta", PANTALLAS)
def test_la_guarda_no_esta_ciega(archivo, variables, ruta):
    """Que las variables que vigila el test de arriba sigan existiendo.

    Una guarda que busca `tx.` en un archivo donde alguien renombró `tx` a `t`
    no encuentra nada y pasa en verde. Es peor que no tenerla: dice que revisó
    cuando no revisó nada.

    Por eso acá se comprueba que cada variable de `PANTALLAS` aparezca de
    verdad en su archivo. Si se renombra, este test rompe y hay que
    actualizar la lista — que es exactamente lo que se quiere.
    """
    texto = (_FRONT / archivo).read_text(encoding="utf-8")
    for v in variables:
        assert _campos_que_lee(texto, (v,)), (
            f"la guarda vigila «{v}.algo» en {archivo} y ahí no hay ninguno: "
            "o se renombró la variable, o se movió la pantalla. Actualizá "
            "PANTALLAS.")
