"""
tests/test_btc_operador_solo_super_admin.py — las dos rutas «de operador» del
Bitcoin son sólo del super administrador, como todo el panel de Bitcoin y
como los retiros.

Pedían `get_current_user` y comprobaban a mano el rol `admin`, así que
cualquier colaborador entraba, tuviera los permisos que tuviera: la tabla de
`services/permisos.py` sólo la aplican `get_admin_user` y `get_crm_user`.
Comprobado corriéndolo con alguien que sólo tenía permiso de KYC.

El dinero de la billetera BTC-VES se guarda como float
(`routes/btc_lightning.py`, `$inc` con `ves_recibe`), y así se escribe acá.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402

AGENTE_KYC = User(user_id="u_agente", name="Agente", email="agente@ejemplo.test",
                  role="admin", permissions=["kyc.view"])
JEFA = User(user_id="u_jefa", name="Jefa", email="jefa@ejemplo.test", role="super_admin")
CLIENTA = User(user_id="u_cli", name="Ana", email="ana@ejemplo.test", role="user")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def base():
    m = mongomock_motor.AsyncMongoMockClient()["btc_operador"]
    usar_base(m)
    ya(m.btc_remesas.insert_one({
        "remesa_id": "r1", "user_id": "u_cli", "estado": "pagado", "usd_cliente": 50,
        "ves_recibe": 1825.0, "sats": 50000, "precio_btc_usado": 60000.0,
        "precio_con_margen": 63000.0, "payment_hash": "hash_del_pago", "memo": "RIS r1",
        "beneficiario_id": "ben_9", "no_reembolsable": True, "pagado_en": 1, "creado_en": 0,
        "beneficiario_data": {"full_name": "José Rodríguez", "bank": "Banesco",
                              "account_number": "01340000000000000001", "payment_type": "pago_movil",
                              "user_id": "u_cli", "beneficiary_id": "ben_9"},
    }))
    ya(m.btc_ves_wallets.insert_one({"user_id": "u_cli", "saldo": 2000.0}))
    return m


def como(quien):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.btc_lightning import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: quien
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. Marcar una orden como enviada: mueve la billetera del cliente
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("quien", [AGENTE_KYC, CLIENTA], ids=["admin_con_permiso_de_kyc", "cliente"])
def test_NADIE_MAS_QUE_EL_SUPER_ADMIN_MARCA_UNA_ORDEN_COMO_ENVIADA(base, quien):
    r = como(quien).post("/api/btc/operador/marcar-enviado", json={"remesa_id": "r1", "operador_id": "u_operador"})
    assert r.status_code == 403, r.text
    assert ya(base.btc_remesas.find_one({"remesa_id": "r1"}))["estado"] == "pagado"
    assert ya(base.btc_ves_wallets.find_one({"user_id": "u_cli"}))["saldo"] == 2000.0, "no se debitó nada"


def test_EL_SUPER_ADMIN_SIGUE_PUDIENDO(base):
    r = como(JEFA).post("/api/btc/operador/marcar-enviado", json={"remesa_id": "r1", "operador_id": "u_operador"})
    assert r.status_code == 200, r.text
    assert ya(base.btc_remesas.find_one({"remesa_id": "r1"}))["estado"] == "enviado"
    assert ya(base.btc_ves_wallets.find_one({"user_id": "u_cli"}))["saldo"] == 175.0


# ══════════════════════════════════════════════════════════════════════════
# 2. La lista de órdenes pendientes del panel
# ══════════════════════════════════════════════════════════════════════════

SECRETOS = ("precio_con_margen", "63000", "precio_btc_usado", "hash_del_pago", "RIS r1",
            "u_cli", "ben_9", "no_reembolsable")


@pytest.mark.parametrize("quien", [AGENTE_KYC, CLIENTA], ids=["admin_con_permiso_de_kyc", "cliente"])
def test_LA_LISTA_DE_PENDIENTES_ES_SOLO_DEL_SUPER_ADMIN(base, quien):
    assert como(quien).get("/api/btc/operador/pendientes").status_code == 403


def test_LA_LISTA_TRAE_LO_QUE_LEE_LA_PESTANA_Y_NADA_DEL_MARGEN(base):
    r = como(JEFA).get("/api/btc/operador/pendientes")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 1 and d["ordenes"] == d["remesas"]
    o = d["ordenes"][0]
    assert o["remesa_id"] == "r1" and o["ves_recibe"] == 1825.0 and o["usd_cliente"] == 50
    assert o["sats"] == 50000 and o["creado_en"] == 0
    assert o["beneficiario_data"]["full_name"] == "José Rodríguez"
    assert o["beneficiario_data"]["account_number"] == "01340000000000000001"
    for s in SECRETOS:
        assert s not in r.text, s


class _BaseQueAnota:
    def __init__(self, base, anotadas):
        self._base, self._anotadas = base, anotadas

    def __getattr__(self, nombre):
        coleccion = getattr(self._base, nombre)
        if nombre != "btc_remesas":
            return coleccion
        anotadas = self._anotadas

        class _Col:
            def find(self, filtro, proyeccion=None, *a, **k):
                anotadas.append(proyeccion)
                return coleccion.find(filtro, proyeccion, *a, **k)

            def __getattr__(self, otro):
                return getattr(coleccion, otro)
        return _Col()


def test_LA_PROYECCION_SOLA_NO_TRAE_EL_MARGEN(base):
    from models.btc_salida import LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN
    anotadas = []
    usar_base(_BaseQueAnota(base, anotadas))
    como(JEFA).get("/api/btc/operador/pendientes")
    assert anotadas == [LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN]
    for campo in ("precio_con_margen", "precio_btc_usado", "payment_hash", "memo", "user_id"):
        assert campo not in LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN, campo


def test_EL_CONTRATO_SOLO_CORTA_EL_MARGEN(base, monkeypatch):
    import routes.btc_lightning as rutas
    monkeypatch.setattr(rutas, "LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN", {"_id": 0})
    r = como(JEFA).get("/api/btc/operador/pendientes")
    assert r.status_code == 200, r.text
    for s in SECRETOS:
        assert s not in r.text, s


def test_LA_PESTANA_DE_BITCOIN_ES_SOLO_DEL_SUPER_ADMIN_EN_EL_PANEL():
    """Si el panel se la mostrara a un `admin`, vería la pestaña y un 403."""
    import re
    from pathlib import Path
    panel = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "AdminPanel.jsx").read_text(encoding="utf-8")
    assert re.search(r"\{\s*key:\s*'btc'[^}]*superAdminOnly:\s*true", panel), "la pestaña 'btc' tiene que ser superAdminOnly"
