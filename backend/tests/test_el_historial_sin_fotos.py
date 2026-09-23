"""
tests/test_el_historial_sin_fotos.py — la lista del historial dice SI hay
comprobante y no manda las fotos; el detalle de una operación las sigue
mandando; y la lista tiene tope.

QUE PASABA

    La lista mandaba las fotos del comprobante —base64, unos 667 KB cada una,
    dos o más por retiro completado— para dibujar un ojito. Medido corriendo
    la ruta con diez operaciones con foto, la primera página del inicio: 10 MB
    cada vez que el cliente abría la app. Y `limit` no tenía tope: con
    `?limit=60`, 60 MB, y nada impedía pedir el historial entero.

LO QUE ESTE ARCHIVO CUIDA

    Que el ojito aparezca exactamente donde aparecía. Antes lo decidía la
    pantalla mirando las fotos (`proof_images` no vacía, o `proof_image`, o
    `comprobante_pago`); ahora lo decide la base. Si la pregunta de la base
    se equivoca, el ojito se apaga y el cliente cree que no tiene comprobante,
    sin que nada dé error.

La plata se escribe con `to_decimal128`, igual que la app.
"""
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
from services.money import to_decimal128                      # noqa: E402

ANA = User(user_id="usr_ana", name="Ana", email="ana@ejemplo.test", role="user")
AHORA = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
# Del tamaño de una foto de celular guardada en base64.
FOTO = "data:image/jpeg;base64," + "A" * 667_000

# Cada forma que tiene una operación de tener —o de no tener— comprobante, y
# si la pantalla vieja le mostraba el ojito.
CASOS = {
    "tx_lista": ({"proof_images": [FOTO, FOTO]}, True),
    "tx_lista_vacia": ({"proof_images": []}, False),
    "tx_suelta": ({"proof_image": FOTO}, True),
    "tx_suelta_vacia": ({"proof_image": ""}, False),
    "tx_suelta_nula": ({"proof_image": None}, False),
    "tx_bitcoin": ({"comprobante_pago": "/api/media/btc.jpg"}, True),
    "tx_sin_nada": ({}, False),
}


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["historial_sin_fotos"]
    usar_base(m)
    docs = []
    for i, (tx_id, (fotos, _)) in enumerate(CASOS.items()):
        docs.append({"transaction_id": tx_id, "user_id": "usr_ana", "type": "withdrawal",
                     "status": "completed", "created_at": AHORA - timedelta(minutes=i),
                     "amount_input": to_decimal128("10.00"), "currency_input": "RIS", **fotos})
    ya(m.transactions.insert_many(docs))
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


# ══════════════════════════════════════════════════════════════════════════
# 1. El ojito aparece donde aparecía
# ══════════════════════════════════════════════════════════════════════════

def test_EL_OJITO_APARECE_DONDE_APARECIA(base):
    r = cliente().get("/api/transactions")
    assert r.status_code == 200, r.text
    por_id = {t["transaction_id"]: t["tiene_comprobante"] for t in r.json()["transactions"]}
    assert por_id == {tx_id: esperado for tx_id, (_, esperado) in CASOS.items()}


def test_LA_LISTA_NO_TRAE_NINGUNA_FOTO(base):
    r = cliente().get("/api/transactions")
    assert "base64" not in r.text and "/api/media/btc.jpg" not in r.text
    # Siete operaciones, tres con foto (cuatro fotos de 667 KB): antes, unos 2,7 MB.
    assert len(r.content) < 10_000, len(r.content)


def test_EL_DETALLE_SIGUE_TRAYENDO_LAS_FOTOS(base):
    """Es lo que se pide al tocar el ojito."""
    c = cliente()
    assert c.get("/api/transactions/tx_lista").json()["proof_images"] == [FOTO, FOTO]
    assert c.get("/api/transactions/tx_suelta").json()["proof_image"] == FOTO
    assert c.get("/api/transactions/tx_bitcoin").json()["comprobante_pago"] == "/api/media/btc.jpg"


def test_LA_FOTO_DE_OTRO_CLIENTE_NO_PRENDE_EL_OJITO(base):
    """La pregunta por las fotos va con el `user_id`, igual que la lista."""
    ya(base.transactions.insert_one({"transaction_id": "tx_sin_nada", "user_id": "usr_otro",
                                     "proof_image": FOTO, "created_at": AHORA}))
    por_id = {t["transaction_id"]: t["tiene_comprobante"]
              for t in cliente().get("/api/transactions").json()["transactions"]}
    assert por_id["tx_sin_nada"] is False


def test_UN_CAMPO_DE_FOTOS_NUEVO_ENTRA_SOLO_EN_LA_PREGUNTA(base, monkeypatch):
    """La pregunta se arma recorriendo `LAS_FOTOS`: agregar un campo ahí lo
    incluye sin tener que acordarse de este lugar."""
    import services.las_fotos as las_fotos
    monkeypatch.setattr(las_fotos, "LAS_FOTOS", las_fotos.LAS_FOTOS + ("foto_del_futuro",))
    ya(base.transactions.update_one({"transaction_id": "tx_sin_nada"},
                                    {"$set": {"foto_del_futuro": "/api/media/x.jpg"}}))
    assert ya(las_fotos.cuales_tienen_comprobante(base, {"user_id": "usr_ana"})) == {
        "tx_lista", "tx_suelta", "tx_bitcoin", "tx_sin_nada"}


# ══════════════════════════════════════════════════════════════════════════
# 2. El tope
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("pedido", ["limit=51", "limit=100000", "limit=0", "limit=-5", "page=0", "page=-1"])
def test_LA_LISTA_TIENE_TOPE(base, pedido):
    assert cliente().get(f"/api/transactions?{pedido}").status_code == 422


def test_LO_QUE_PIDEN_LAS_PANTALLAS_SIGUE_ANDANDO(base):
    c = cliente()
    assert c.get("/api/transactions?page=1&limit=10").status_code == 200
    r = c.get("/api/transactions?page=2&limit=5")
    assert r.status_code == 200 and len(r.json()["transactions"]) == 2
    assert c.get("/api/transactions?limit=50").status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 3. Las pantallas
# ══════════════════════════════════════════════════════════════════════════

_FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_EL_OJITO_SE_DECIDE_CON_LO_QUE_MANDA_LA_LISTA():
    fuente = (_FRONT / "components" / "dashboard" / "TransactionItem.jsx").read_text(encoding="utf-8")
    assert "const showVoucher = tx.tiene_comprobante;" in fuente


def test_AL_TOCAR_EL_OJITO_SE_PIDE_EL_DETALLE():
    fuente = (_FRONT / "hooks" / "useComprobante.js").read_text(encoding="utf-8")
    assert "api.get(`/transactions/${encodeURIComponent(id)}`)" in fuente
    # Los envíos por Bitcoin guardan la foto en `comprobante_pago` y la
    # ventana la busca en `proof_image`: sin este paso, «No hay imágenes».
    assert "normalized.proof_image = normalized.comprobante_pago;" in fuente
    # La respuesta vieja no pisa a la nueva.
    assert fuente.count("pedido.current !== id") + fuente.count("pedido.current === id") == 2
    for pantalla in ("Dashboard.jsx", "History.jsx"):
        texto = (_FRONT / "pages" / pantalla).read_text(encoding="utf-8")
        assert "useComprobante()" in texto, pantalla
        assert "<AvisoDelComprobante estado={estadoDelComprobante} />" in texto, pantalla
