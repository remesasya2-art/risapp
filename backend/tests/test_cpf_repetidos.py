"""
tests/test_cpf_repetidos.py — ver desde el panel qué cuentas comparten un
CPF, y liberar el de una de ellas con motivo y rastro.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services import cpf_de_la_cuenta as svc                  # noqa: E402
from services.money import to_decimal128                      # noqa: E402

CPF = "52998224725"          # un CPF válido de ejemplo
OTRO = "11144477735"
JEFA = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base():
    m = mongomock_motor.AsyncMongoMockClient()["cpf_repetidos"]
    usar_base(m)
    ya(m.users.insert_many([
        {"user_id": "u_vieja", "name": "Ana Vieja", "email": "vieja@ejemplo.test", "cpf_number": CPF,
         "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc), "verification_status": "verified", "balance_ris": to_decimal128("120.50")},
        {"user_id": "u_nueva", "name": "Ana Nueva", "email": "nueva@ejemplo.test", "cpf_number": CPF,
         "created_at": datetime(2026, 3, 1, tzinfo=timezone.utc), "verification_status": "pending", "balance_ris": to_decimal128("0")},
        {"user_id": "u_sola", "name": "Beto", "email": "beto@ejemplo.test", "cpf_number": OTRO,
         "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    ]))
    ya(svc.sembrar(m))
    return m


def test_LA_LISTA_TRAE_SOLO_LOS_REPETIDOS_CON_EL_CPF_TAPADO_Y_LA_MAS_VIEJA_PRIMERO(base):
    r = ya(svc.repetidos(base))
    assert len(r) == 1 and r[0]["cpf"] == "•••••••725" and CPF not in str(r)
    assert [c["user_id"] for c in r[0]["cuentas"]] == ["u_vieja", "u_nueva"]
    vieja = r[0]["cuentas"][0]
    assert vieja["saldo_ris"] == 120.5 and vieja["verificacion"] == "verified" and vieja["email"] == "vieja@ejemplo.test"
    assert set(vieja) == {"user_id", "nombre", "email", "creada", "ultimo_ingreso", "verificacion", "estado", "borrada", "vetada", "saldo_ris"}


def test_LIBERAR_SACA_EL_CPF_SUELTA_LA_RESERVA_ASIENTA_Y_CREA_EL_CANDADO(base):
    # La reserva del CPF la tiene la cuenta nueva (pasa cuando se registró
    # después de la siembra): al liberar, tiene que pasar a la que queda.
    ya(base[svc.COLECCION_TOMADOS].update_one({"_id": CPF}, {"$set": {"user_id": "u_nueva"}}))
    r = ya(svc.liberar(base, "u_nueva", motivo="Cuenta duplicada; la verificada es la vieja", quien=JEFA))
    assert r["cpf"] == "•••••••725" and r["quedan_repetidos"] == 0 and r["indice"] in ("listo", "rehecho")
    u = ya(base.users.find_one({"user_id": "u_nueva"}))
    assert u["cpf_number"] is None and u["cpf_liberado"]["por"] == "u_jefa" and u["cpf_liberado"]["cpf"] == "•••••••725"
    assert CPF not in str(u["cpf_liberado"])
    assert ya(base.users.find_one({"user_id": "u_vieja"}))["cpf_number"] == CPF          # la otra no se toca
    reserva = ya(base[svc.COLECCION_TOMADOS].find_one({"_id": CPF}))
    assert reserva["user_id"] == "u_vieja" and "vence_en" not in reserva            # anclada a la que queda
    linea = ya(base.auditoria.find_one({"accion": "usuario.cpf_liberado"}))
    assert linea and linea["objetivo"]["id"] == "u_nueva" and linea["detalle"]["motivo"].startswith("Cuenta duplicada")
    assert svc.NOMBRE_DEL_INDICE in ya(base.users.index_information())


def test_no_se_libera_sin_motivo_ni_la_unica_cuenta_con_ese_cpf_ni_una_que_no_existe(base):
    with pytest.raises(svc.NoSePuedeLiberar, match="motivo"):
        ya(svc.liberar(base, "u_nueva", motivo="  ", quien=JEFA))
    with pytest.raises(svc.NoSePuedeLiberar, match="única"):
        ya(svc.liberar(base, "u_sola", motivo="probando", quien=JEFA))
    with pytest.raises(svc.NoSePuedeLiberar, match="No existe"):
        ya(svc.liberar(base, "u_nadie", motivo="probando", quien=JEFA))
    assert ya(base.users.find_one({"user_id": "u_sola"}))["cpf_number"] == OTRO


# ─── por HTTP ─────────────────────────────────────────────────────────────

@pytest.fixture
def cliente(base):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.cpf_repetidos import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, TestClient(app)


def test_solo_el_super_administrador_ve_y_libera(cliente):
    from routes import dependencies as deps
    app, c = cliente
    assert c.get("/api/admin/cpf-repetidos").status_code in (401, 403)
    assert c.post("/api/admin/users/u_nueva/cpf/liberar", json={"motivo": "x"}).status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    r = c.get("/api/admin/cpf-repetidos")
    assert r.status_code == 200 and r.json()["candado"] is False and len(r.json()["repetidos"]) == 1
    assert c.post("/api/admin/users/u_nueva/cpf/liberar", json={"motivo": ""}).status_code == 422
    r = c.post("/api/admin/users/u_sola/cpf/liberar", json={"motivo": "probando"})
    assert r.status_code == 400 and "única" in r.json()["detail"]
    r = c.post("/api/admin/users/u_nueva/cpf/liberar", json={"motivo": "Duplicada; queda la verificada"})
    assert r.status_code == 200 and r.json()["quedan_repetidos"] == 0
    r = c.get("/api/admin/cpf-repetidos")
    assert r.json()["repetidos"] == [] and r.json()["candado"] is True
