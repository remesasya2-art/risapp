"""
tests/test_contratos_de_acciones_de_dinero.py — Las acciones del cliente que
mueven plata salen por un contrato, y ningún contrato se come un campo que su
ruta devuelve.

Hasta esta tanda los contratos cubrían lo que el cliente consulta. Éstas son
las rutas donde el cliente manda algo: retirar, recargar, cotizar y pagar un
envío, pagar con tarjeta, depositar cripto, generar una factura Bitcoin.

Hoy todas arman la respuesta campo por campo. Lo que corta de verdad es la
repetición: cuando el cliente reintenta con la misma clave, la ruta devuelve
la respuesta GUARDADA en la base, tal como esté. La sección 2 lo prueba con
una respuesta guardada que trae de más.
"""
import ast
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")
_BACKEND = Path(__file__).resolve().parents[1]

# (archivo, camino, contrato)
RUTAS = [
    ("routes/transactions.py", "/reais/send", "MiEnvioDeReais"),
    ("routes/transactions.py", "/withdraw", "MiRetiroPedido"),
    ("routes/transactions.py", "/withdrawal/create", "MiRetiroPedido"),
    ("routes/transactions.py", "/withdraw-crypto", "MiEnvioCripto"),
    ("routes/transactions.py", "/withdraw-crypto/{transaction_id}/cancelar", "MiOrdenCriptoCancelada"),
    ("routes/transactions.py", "/recharge/ves", "MiRecargaVes"),
    ("routes/transactions.py", "/withdraw-ves/cotizar", "MiCotizacionVes"),
    ("routes/transactions.py", "/enviar-reais/cotizar", "MiCotizacionReais"),
    ("routes/transactions.py", "/enviar-reais/comprobante", "MiComprobanteRecibido"),
    ("routes/payments_card.py", "/quote", "MiCotizacionDeTarjeta"),
    ("routes/payments_card.py", "/process", "MiPagoConTarjeta"),
    ("routes/credits.py", "/deposit", "MiDepositoCripto"),
    ("routes/btc_lightning.py", "/generar-invoice", "MiFacturaBtc"),
    ("routes/btc_lightning.py", "/cancelar/{remesa_id}", "MiRemesaCancelada"),
]


def ya(c):
    return asyncio.run(c)


def _router(archivo):
    import importlib
    return importlib.import_module(archivo[:-3].replace("/", ".")).router


def _ruta(archivo, camino):
    router = _router(archivo)
    (r,) = [r for r in router.routes
            if r.path == (router.prefix or "") + camino and "POST" in r.methods]
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Cada ruta tiene su contrato, y el contrato no se come nada
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,camino,modelo", RUTAS, ids=[c for _, c, _ in RUTAS])
def test_CADA_ACCION_TIENE_SU_CONTRATO(archivo, camino, modelo):
    ruta = _ruta(archivo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def _funcion(archivo, camino):
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
                and d.args[0].value == camino for d in f.decorator_list):
            return f
    raise AssertionError(f"no encontré {camino} en {archivo}")    # pragma: no cover


def _claves_que_devuelve(archivo, camino):
    """Las claves de cada diccionario que la función devuelve, leídas del
    código: el `return {...}` y el que se arma en una variable y se devuelve."""
    f = _funcion(archivo, camino)
    devueltas = {r.value.id for r in ast.walk(f) if isinstance(r, ast.Return) and isinstance(r.value, ast.Name)}
    claves = set()

    def de(d):
        return {k.value for k in d.keys if isinstance(k, ast.Constant)}
    for n in ast.walk(f):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            claves |= de(n.value)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict) and any(
                isinstance(t, ast.Name) and t.id in devueltas for t in n.targets):
            claves |= de(n.value)
    return claves


@pytest.mark.parametrize("archivo,camino,modelo", RUTAS, ids=[c for _, c, _ in RUTAS])
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_ACCION_DEVUELVE(archivo, camino, modelo):
    ruta = _ruta(archivo, camino)
    faltan = _claves_que_devuelve(archivo, camino) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene: la pantalla los perdería"


def test_LA_LECTURA_DEL_CODIGO_ENCUENTRA_CLAVES():
    """Sin esto, el de arriba pasaría igual si la lectura dejara de encontrar
    diccionarios: cero claves de cero es verde y no prueba nada."""
    vacias = [c for a, c, _ in RUTAS if not _claves_que_devuelve(a, c)]
    assert vacias == [], vacias


def test_EL_DESGLOSE_DE_TARJETA_DE_LA_COTIZACION_TIENE_SU_LUGAR():
    """La cotización a Venezuela agrega `credit_card` y `debit_card` por
    índice (`_resp[_tipo] = ...`), que la lectura de arriba no ve. Sin estos
    dos campos en el contrato, la pantalla perdería el desglose de la tarjeta
    y el cliente vería el total sin saber de dónde salen los centavos."""
    from models.acciones_de_dinero import DesgloseDeTarjeta, MiCotizacionVes
    fuente = (_BACKEND / "routes/transactions.py").read_text(encoding="utf-8")
    assert 'for _tipo in ("credit_card", "debit_card"):' in fuente
    for tipo in ("credit_card", "debit_card"):
        assert tipo in MiCotizacionVes.model_fields
    from services.tarjeta_del_envio import cuanto_se_le_cobra
    from routes.payments_card import DEFAULT_CARD_FEES as tarifas
    desglose = cuanto_se_le_cobra(100, "credit_card", tarifas)
    assert set(desglose) <= set(DesgloseDeTarjeta.model_fields), set(desglose)


def test_LA_FACTURA_BTC_NO_LLEVA_EL_PRECIO_CON_MARGEN():
    """Con el precio con margen y el de mercado —público en `/btc/precio`— el
    cliente saca el margen exacto de la operación."""
    from models.acciones_de_dinero import MiFacturaBtc
    assert "precio_con_margen" not in MiFacturaBtc.model_fields
    assert "precio_con_margen" not in _claves_que_devuelve("routes/btc_lightning.py", "/generar-invoice")


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que corta de verdad: la respuesta guardada para los reintentos
# ══════════════════════════════════════════════════════════════════════════

DE_MAS = {"margen_interno": 0.07, "nota_del_operador": "revisar a este cliente",
          "beneficiary_data": {"full_name": "José", "beneficiary_id": "ben_interno_9"}}


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["acciones_de_dinero"]
    usar_base(m)
    ya(m.users.insert_one({"user_id": "u_ana", "role": "user", "is_active": True}))
    # El índice único es lo que hace que la clave repetida se note. La
    # aplicación lo crea una sola vez por proceso, así que en una base nueva
    # de cada test hay que ponerlo a mano.
    ya(m.idempotency_keys.create_index([("user_id", 1), ("action", 1), ("key", 1)], unique=True))
    ya(m.idempotency_keys.insert_many([
        {"user_id": "u_ana", "action": "withdraw_ves", "key": "k_retiro", "status": "completed",
         "result": {"message": "Retiro solicitado exitosamente", "transaction_id": "tx_1",
                    "display_id": "R000001", "amount_ris": 10.0, "amount_ves": 1100.0, "rate": 110.0,
                    **DE_MAS}},
    ]))
    return m


def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    app.include_router(_router("routes/transactions.py"), prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


@pytest.mark.parametrize("camino,cuerpo,esperado", [
    ("/api/withdraw", {"amount": 10, "beneficiary_id": "b_1", "idempotency_key": "k_retiro"},
     {"transaction_id": "tx_1", "amount_ves": 1100.0}),
    # La segunda puerta del mismo retiro: registrada aparte, con su propio contrato.
    ("/api/withdrawal/create", {"amount": 10, "beneficiary_id": "b_1", "idempotency_key": "k_retiro"},
     {"transaction_id": "tx_1", "amount_ves": 1100.0}),
])
def test_EL_REINTENTO_DEVUELVE_LO_GUARDADO_SIN_LO_DE_MAS(base, camino, cuerpo, esperado):
    r = cliente().post(camino, json=cuerpo)
    assert r.status_code == 200, r.text
    datos = r.json()
    for clave, valor in esperado.items():
        assert datos[clave] == valor, (clave, datos)
    for clave in DE_MAS:
        assert clave not in datos, f"{camino} devolvió «{clave}», guardado en la base"
    assert "ben_interno_9" not in r.text and "revisar a este cliente" not in r.text
