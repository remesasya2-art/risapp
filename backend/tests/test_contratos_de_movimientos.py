"""
tests/test_contratos_de_movimientos.py — el historial y el detalle de una
operación salen por un contrato generado de la misma lista de lo permitido que
usa la consulta, y los datos del beneficiario que viajan adentro tienen su
propia lista. Ver models/movimientos.py.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services.money import to_decimal128                      # noqa: E402

ANA = User(user_id="usr_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)

# Lo que le escribe el panel a una orden mientras la procesa.
LO_DEL_PANEL = {
    "assigned_to": "usr_agente", "assigned_to_name": "agente@ejemplo.test",
    "estado_admin": "en_lote", "lote_id": "lote_7", "processed_by": "usr_agente",
    "paid_from_bank": "banco_interno_3", "hidden_from_admin": False,
}

# Un envío por Bitcoin guardado ANTES de este cambio: el bloque del
# beneficiario era una copia del documento entero.
BENEFICIARIO_ENTERO = {
    "beneficiary_id": "ben_interno_9", "user_id": "usr_ana", "created_at": AHORA,
    "full_name": "José Rodríguez", "id_document": "V12345678", "bank": "Banesco",
    "bank_code": "0134", "phone_number": "04141234567",
    "account_number": "01340000000000000001", "payment_type": "pago_movil",
    "campo_nuevo_del_futuro": "no tiene que salir",
}


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["contratos_movimientos"]
    usar_base(m)
    ya(m.transactions.insert_many([
        {"transaction_id": "tx_ve", "display_id": "R000101", "user_id": "usr_ana",
         "type": "withdrawal", "status": "completed", "created_at": AHORA,
         "amount_input": to_decimal128("100.00"), "amount_output": to_decimal128("3650.50"),
         "currency_input": "RIS", "currency_output": "VES",
         "rate": to_decimal128("36.505"),
         "beneficiary_data": {"full_name": "Carmen López", "bank": "Banco de Venezuela",
                              "bank_code": "0102", "account_number": "01020000000000000002",
                              "payment_type": "transferencia"},
         "proof_images": ["data:image/jpeg;base64,AAAA", "/api/media/comprobante_2.jpg"],
         **LO_DEL_PANEL},
        {"transaction_id": "tx_btc", "user_id": "usr_ana", "tipo": "envio",
         "estado": "completado", "created_at": AHORA, "usd_cliente": 50,
         "beneficiario": "José Rodríguez", "beneficiario_data": BENEFICIARIO_ENTERO,
         "comprobante_pago": "data:image/jpeg;base64,BBBB", **LO_DEL_PANEL},
        {"transaction_id": "tx_ajena", "user_id": "usr_otro", "type": "withdrawal",
         "status": "pending", "created_at": AHORA},
    ]))
    return m


def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.transactions import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ANA
    return TestClient(app)


SECRETOS = ("usr_agente", "agente@ejemplo.test", "lote_7", "banco_interno_3", "en_lote",
            "ben_interno_9", "no tiene que salir", "hidden_from_admin")


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que sale, con las dos capas puestas
# ══════════════════════════════════════════════════════════════════════════

def test_EL_HISTORIAL_MUESTRA_LO_DE_SIEMPRE_Y_NADA_DEL_PANEL(base):
    r = cliente().get("/api/transactions")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 2 and d["pages"] == 1
    por_id = {t["transaction_id"]: t for t in d["transactions"]}
    assert set(por_id) == {"tx_ve", "tx_btc"}, "sólo las suyas"
    ve = por_id["tx_ve"]
    assert ve["amount_output"] == 3650.5 and ve["currency_output"] == "VES"
    assert ve["beneficiary_data"]["full_name"] == "Carmen López"
    assert ve["beneficiary_data"]["account_number"] == "01020000000000000002"
    assert ve["proof_images"] == ["data:image/jpeg;base64,AAAA", "/api/media/comprobante_2.jpg"]
    for s in SECRETOS:
        assert s not in r.text, s


def test_EL_BENEFICIARIO_DE_UN_ENVIO_BTC_VIEJO_SALE_RECORTADO(base):
    """La orden se guardó con la copia entera; el contrato la recorta al mostrar."""
    r = cliente().get("/api/transactions/tx_btc")
    assert r.status_code == 200, r.text
    b = r.json()["beneficiario_data"]
    assert b["full_name"] == "José Rodríguez" and b["account_number"] == "01340000000000000001"
    for interno in ("beneficiary_id", "user_id", "created_at", "campo_nuevo_del_futuro"):
        assert interno not in b, interno
    assert r.json()["comprobante_pago"] == "data:image/jpeg;base64,BBBB"


def test_LO_QUE_LA_ORDEN_NO_TIENE_NO_SALE_COMO_NULL(base):
    d = cliente().get("/api/transactions/tx_ve").json()
    assert "completed_at" not in d and "voucher_url" not in d and "tipo" not in d
    assert "phone_number" not in d["beneficiary_data"]


def test_UNA_ORDEN_AJENA_SIGUE_SIENDO_404(base):
    assert cliente().get("/api/transactions/tx_ajena").status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 2. Cada capa sola
# ══════════════════════════════════════════════════════════════════════════

class _BaseQueAnota:
    """La base de siempre, anotando qué proyección le piden a `transactions`."""
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "transactions":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            def find(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return coleccion.find(filtro, proyeccion, *a, **k)

            async def find_one(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return await coleccion.find_one(filtro, proyeccion, *a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_LA_PROYECCION_SOLA_ES_LA_LISTA_DE_LO_PERMITIDO(base):
    from models.movimientos import LO_QUE_VE_EL_CLIENTE
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    c = cliente()
    c.get("/api/transactions")
    c.get("/api/transactions/tx_ve")
    assert anotadas == [LO_QUE_VE_EL_CLIENTE, LO_QUE_VE_EL_CLIENTE]


@pytest.mark.parametrize("camino", ["/api/transactions", "/api/transactions/tx_btc"])
def test_EL_CONTRATO_SOLO_CORTA_LO_QUE_LA_PROYECCION_DEJE_PASAR(base, monkeypatch, camino):
    """Si alguien vuelve a poner `{"_id": 0}` en la consulta, el contrato
    corta igual lo que el panel le escribió a la orden."""
    import routes.transactions as rutas
    monkeypatch.setattr(rutas, "LO_QUE_VE_EL_CLIENTE", {"_id": 0})
    r = cliente().get(camino)
    assert r.status_code == 200, r.text
    for s in SECRETOS:
        assert s not in r.text, s


def test_UN_DOCUMENTO_EN_UN_CAMPO_SIMPLE_SALE_VACIO(base):
    ya(base.transactions.update_one({"transaction_id": "tx_ve"},
                                    {"$set": {"status": {"interno": "usr_agente"}}}))
    r = cliente().get("/api/transactions/tx_ve")
    assert r.status_code == 200 and r.json()["status"] is None and "usr_agente" not in r.text


# ══════════════════════════════════════════════════════════════════════════
# 3. Al guardar: el envío por Bitcoin ya no copia el beneficiario entero
# ══════════════════════════════════════════════════════════════════════════

def test_EL_RECORTE_DEL_BENEFICIARIO_DEJA_AFUERA_LO_QUE_NO_CONOCE():
    from models.movimientos import beneficiario_para_la_orden
    b = beneficiario_para_la_orden({**BENEFICIARIO_ENTERO, "_id": "x"})
    assert b["full_name"] == "José Rodríguez" and b["bank_code"] == "0134"
    for interno in ("_id", "beneficiary_id", "user_id", "created_at", "campo_nuevo_del_futuro"):
        assert interno not in b, interno
    assert beneficiario_para_la_orden(None) == {}


def test_EL_ENVIO_BTC_GUARDA_EL_BENEFICIARIO_RECORTADO():
    fuente = (Path(__file__).resolve().parents[1] / "routes" / "btc_lightning.py").read_text(encoding="utf-8")
    assert '"beneficiario_data": beneficiario_para_la_orden(beneficiario)' in fuente
    assert 'for k, v in beneficiario.items() if k != "_id"' not in fuente


def test_EL_PANEL_SIGUE_TENIENDO_LO_QUE_LEE_DEL_BENEFICIARIO_BTC():
    """El operador paga con estos datos (`routes/btc_admin.py`)."""
    from models.movimientos import LO_QUE_VE_DEL_BENEFICIARIO
    for campo in ("full_name", "id_document", "cedula", "phone", "phone_number",
                  "bank", "bank_code", "account_number", "payment_type", "name"):
        assert campo in LO_QUE_VE_DEL_BENEFICIARIO, campo


# ══════════════════════════════════════════════════════════════════════════
# 4. Cada ruta tiene el suyo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("camino,modelo", [
    ("/transactions", "MisMovimientos"),
    ("/transactions/{transaction_id}", "MovimientoQueVeElCliente"),
])
def test_CADA_RUTA_TIENE_SU_CONTRATO(camino, modelo):
    from routes.transactions import router
    (ruta,) = [r for r in router.routes if r.path == camino and "GET" in r.methods]
    assert getattr(ruta.response_model, "__name__", None) == modelo
    assert ruta.response_model_exclude_unset is True


def test_EL_CONTRATO_SALE_DE_LA_MISMA_LISTA_QUE_LA_CONSULTA():
    from models.movimientos import LO_QUE_VE_EL_CLIENTE, MovimientoQueVeElCliente
    assert set(MovimientoQueVeElCliente.model_fields) == set(LO_QUE_VE_EL_CLIENTE) - {"_id"}
