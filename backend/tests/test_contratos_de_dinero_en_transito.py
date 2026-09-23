"""
tests/test_contratos_de_dinero_en_transito.py — Bitcoin, créditos cripto, PIX y
retiros, vistos por el cliente, salen por un contrato; y ningún contrato se
come un campo que su ruta devuelve.

Estas rutas ya armaban la respuesta campo por campo, así que el contrato es la
segunda capa. Lo que sí corta de verdad hoy es lo de ADENTRO del beneficiario:
las órdenes Bitcoin viejas lo guardaron como copia entera del documento.

El riesgo de ponerle contrato a una ruta que ya funciona es el contrario al de
siempre: que el contrato se coma un campo y la pantalla quede con un hueco sin
avisar. Por eso la sección 1 lee del código las claves que devuelve cada ruta
y exige que estén todas en su contrato.
"""
import ast
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

ANA = User(user_id="u_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime.now(timezone.utc)
_BACKEND = Path(__file__).resolve().parents[1]

# (archivo, camino, prefijo con el que se registra, contrato)
RUTAS = [
    ("routes/btc_lightning.py", "/precio", "/btc", "PrecioBtc"),
    ("routes/btc_lightning.py", "/limite-diario", "/btc", "LimiteDiarioBtc"),
    ("routes/btc_lightning.py", "/mi-remesa-activa", "/btc", "MiRemesaActiva"),
    ("routes/btc_lightning.py", "/status/{remesa_id}", "/btc", "EstadoDeMiRemesa"),
    ("routes/btc_lightning.py", "/wallet", "/btc", "MiBilleteraBtc"),
    ("routes/btc_lightning.py", "/historial", "/btc", "MiHistorialBtc"),
    ("routes/credits.py", "/networks", "/credits", "RedesDeCredito"),
    ("routes/credits.py", "/min-amount", "/credits", "MontoMinimoDeCredito"),
    ("routes/credits.py", "/deposit/{order_id}/status", "/credits", "EstadoDeMiDeposito"),
    ("routes/credits.py", "/history", "/credits", "MiHistorialCripto"),
    ("routes/gestor_pix.py", "/pending", "/gestor/pix", "MiPixPendiente"),
    ("routes/gestor_pix.py", "/status/{payment_id}", "/gestor/pix", "EstadoDeMiPix"),
    ("routes/gestor_pix.py", "/active", "/gestor/pix", "MiPixActivo"),
    ("routes/gestor_pix.py", "/history", "/gestor/pix", "List[UnPixDeMiHistorial]"),
    ("routes/transactions.py", "/withdrawal/pending", "", "MiRetiroPendiente"),
    ("routes/transactions.py", "/withdraw-crypto/{transaction_id}/status", "", "EstadoDeMiEnvioCripto"),
]


def ya(c):
    return asyncio.run(c)


def _router(archivo):
    import importlib
    return importlib.import_module(archivo[:-3].replace("/", ".")).router


def _ruta(archivo, camino):
    router = _router(archivo)
    prefijo = router.prefix or ""
    (r,) = [r for r in router.routes if r.path == prefijo + camino and "GET" in r.methods]
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Cada ruta tiene su contrato, y el contrato no se come nada
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,camino,prefijo,modelo", RUTAS, ids=[c for _, c, _, _ in RUTAS])
def test_CADA_RUTA_TIENE_SU_CONTRATO(archivo, camino, prefijo, modelo):
    ruta = _ruta(archivo, camino)
    # `str()` y no `__name__`: el de una lista (`List[...]`) es «List» a secas.
    nombre = str(ruta.response_model)
    assert modelo.split("[")[-1].rstrip("]") in nombre, nombre
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def _claves_que_devuelve(archivo, camino):
    """Las claves de cada diccionario que la función devuelve, leídas del
    código: el `return {...}`, el que se arma en una variable y se devuelve
    (con sus `.update(...)`), y el que se agrega a una lista devuelta."""
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
                and d.args[0].value == camino for d in f.decorator_list):
            break
    else:                                                     # pragma: no cover
        raise AssertionError(f"no encontré {camino} en {archivo}")
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
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("update", "append") and isinstance(n.func.value, ast.Name)
                and n.func.value.id in devueltas and n.args and isinstance(n.args[0], ast.Dict)):
            claves |= de(n.args[0])
    return claves


def _campos(modelo):
    import typing
    if typing.get_origin(modelo) in (list, typing.List):
        modelo = typing.get_args(modelo)[0]
    return set(modelo.model_fields)


@pytest.mark.parametrize("archivo,camino,prefijo,modelo", RUTAS, ids=[c for _, c, _, _ in RUTAS])
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_RUTA_DEVUELVE(archivo, camino, prefijo, modelo):
    ruta = _ruta(archivo, camino)
    faltan = _claves_que_devuelve(archivo, camino) - _campos(ruta.response_model)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene: la pantalla los perdería"


def test_LA_LECTURA_DEL_CODIGO_ENCUENTRA_CLAVES():
    """Sin esto, el de arriba pasaría igual si la lectura dejara de encontrar
    diccionarios: cero claves de cero es verde y no prueba nada."""
    vacias = [c for a, c, _, _ in RUTAS if not _claves_que_devuelve(a, c)]
    # `/status/{remesa_id}` devuelve lo que trae la proyección, no un dict armado.
    assert vacias == ["/status/{remesa_id}"], vacias


def test_EL_ESTADO_DE_UNA_REMESA_CUBRE_SU_PROYECCION():
    """La única que devuelve el documento tal como lo trae la consulta: se
    compara con la proyección escrita en la ruta."""
    from models.btc_salida import EstadoDeMiRemesa
    fuente = (_BACKEND / "routes/btc_lightning.py").read_text(encoding="utf-8")
    inicio = fuente.index('@router.get("/status/{remesa_id}"')
    trozo = fuente[inicio:inicio + 1200]
    proyeccion = ast.literal_eval(trozo[trozo.index('{"_id": 0'):trozo.index("}", trozo.index('{"_id": 0')) + 1])
    assert set(proyeccion) - {"_id"} <= set(EstadoDeMiRemesa.model_fields)


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que corta de verdad: el beneficiario viejo de las órdenes Bitcoin
# ══════════════════════════════════════════════════════════════════════════

BENEFICIARIO_ENTERO = {
    "full_name": "José Rodríguez", "bank": "Banesco", "account_number": "01340000000000000001",
    "payment_type": "pago_movil", "user_id": "u_ana", "beneficiary_id": "ben_interno_9",
    "created_at": "2026-01-01", "campo_nuevo_del_futuro": "no tiene que salir",
}


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["dinero_en_transito"]
    usar_base(m)
    # Las rutas de PIX buscan a la persona en la base antes de contestar.
    ya(m.users.insert_one({"user_id": "u_ana", "role": "user"}))
    ya(m.btc_remesas.insert_many([
        {"remesa_id": "r_vieja", "user_id": "u_ana", "estado": "enviado", "usd_cliente": 50,
         "ves_recibe": 1825.0, "sats": 50000, "tasa_ves": 36.5, "creado_en": AHORA - timedelta(days=3),
         "pagado_en": AHORA - timedelta(days=3), "precio_con_margen": 63000.0,
         "payment_hash": "hash_del_pago", "beneficiario_data": BENEFICIARIO_ENTERO},
        {"remesa_id": "r_activa", "user_id": "u_ana", "estado": "pendiente", "usd_cliente": 20,
         "ves_recibe": 730.0, "sats": 20000, "btc_pagar": 0.0002, "payment_request": "lnbc1...",
         "creado_en": AHORA, "expira_en": AHORA + timedelta(minutes=10),
         "precio_con_margen": 63000.0, "beneficiario_data": BENEFICIARIO_ENTERO},
    ]))
    ya(m.transactions.insert_one({
        "transaction_id": "tx_ret", "display_id": "R000200", "user_id": "u_ana", "type": "withdrawal",
        "status": "pending", "amount_input": 100.0, "amount_output": 3650.5, "created_at": AHORA,
        "beneficiary_data": BENEFICIARIO_ENTERO, "assigned_to_name": "agente@ejemplo.test"}))
    ya(m.gestor_pix_payments.insert_one({
        "payment_id": "pix_1", "gestor_id": "u_ana", "status": "pending", "amount_ris": 100.0,
        "amount_brl": 100.0, "qr_code": "000201...", "qr_code_base64": "iVBOR...",
        "created_at": AHORA, "expires_at": AHORA + timedelta(minutes=20),
        "mp_payment_id": "mp_interno_77", "gestor_name": "Ana", "security_note": "revisar IP"}))
    return m


def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    app = FastAPI()
    for archivo in ("routes/btc_lightning.py", "routes/gestor_pix.py", "routes/transactions.py"):
        app.include_router(_router(archivo), prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


SECRETOS_DEL_BENEFICIARIO = ("ben_interno_9", "no tiene que salir", "campo_nuevo_del_futuro")


@pytest.mark.parametrize("camino", ["/api/btc/historial", "/api/btc/mi-remesa-activa", "/api/withdrawal/pending"])
def test_EL_BENEFICIARIO_VIEJO_SALE_RECORTADO(base, camino):
    r = cliente().get(camino)
    assert r.status_code == 200, r.text
    assert "José Rodríguez" in r.text and "01340000000000000001" in r.text, "lo que se muestra sigue"
    for s in SECRETOS_DEL_BENEFICIARIO:
        assert s not in r.text, s
    assert "precio_con_margen" not in r.text and "hash_del_pago" not in r.text
    assert "agente@ejemplo.test" not in r.text


def test_LA_ORDEN_EN_CURSO_SIGUE_TRAYENDO_LO_QUE_LA_PANTALLA_USA(base):
    d = cliente().get("/api/btc/mi-remesa-activa").json()
    assert d["activa"] is True
    assert {"remesa_id", "estado", "sats", "usd_cliente", "ves_recibe", "btc_pagar",
            "payment_request", "creado_en", "expira_en"} <= set(d["remesa"])


def test_EL_PIX_PENDIENTE_NO_TRAE_LO_DEL_PROCESADOR(base):
    r = cliente().get("/api/gestor/pix/pending")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["has_pending"] is True and d["qr_code"] == "000201..." and d["qr_code_base64"] == "iVBOR..."
    assert "mp_interno_77" not in r.text and "revisar IP" not in r.text and "gestor_name" not in r.text


def test_UNA_RESPUESTA_CORTA_NO_INVENTA_NULLS(base):
    """Sin PIX pendiente la ruta contesta `{"has_pending": false}` y nada más.
    Sin `exclude_unset` salían las otras nueve claves en null."""
    ya(base.gestor_pix_payments.delete_many({}))
    assert cliente().get("/api/gestor/pix/pending").json() == {"has_pending": False}


def test_EL_HISTORIAL_CRIPTO_CORTA_LO_QUE_SE_COLARA(monkeypatch):
    """El historial cripto sale de una agregación. Si alguien le agrega un
    campo a la proyección, el contrato lo corta."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    import routes.credits as creditos

    class _Cursor:
        async def to_list(self, n):
            return [{"items": [{"kind": "deposit", "order_id": "o1", "amount": 10.0,
                                "admin_note": "cliente conocido del gerente", "admin_id": "u_jefa",
                                "payment_id": "np_interno"}],
                     "total": [{"count": 1}]}]

    class _Col:
        def aggregate(self, pipeline):
            return _Cursor()

    class _Base:
        crypto_deposits = _Col()

    monkeypatch.setattr(creditos, "db", _Base())
    app = FastAPI()
    app.include_router(creditos.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    r = TestClient(app).get("/api/credits/history")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["order_id"] == "o1" and item["amount"] == 10.0
    for s in ("cliente conocido del gerente", "u_jefa", "np_interno"):
        assert s not in r.text, s
