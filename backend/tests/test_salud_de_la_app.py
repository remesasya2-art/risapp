"""
tests/test_salud_de_la_app.py — el ping de vida dice si la base responde,
y el reloj de salud avisa al equipo sólo cuando eso cambia.
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
from services import salud_de_la_app as salud                 # noqa: E402
from services.cpf_de_la_cuenta import NOMBRE_DEL_INDICE       # noqa: E402


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base():
    m = mongomock_motor.AsyncMongoMockClient()["salud_app"]
    usar_base(m)
    salud.reiniciar_para_tests()
    return m


class _BaseCaida:
    """Una base que no contesta: lo que se ve cuando Mongo se cae."""
    async def list_collection_names(self):
        raise ConnectionError("no route to host")


def comprobacion(r, nombre):
    return next(c for c in r["comprobaciones"] if c["nombre"] == nombre)


def test_SANA_CUANDO_LA_BASE_RESPONDE_Y_ESTA_EL_CANDADO_DEL_CPF(base):
    ya(base.users.create_index("cpf_number", unique=True, sparse=True, name=NOMBRE_DEL_INDICE))
    r = ya(salud.revisar(base))
    assert r["ok"] is True
    assert comprobacion(r, "base")["ok"] and "responde en" in comprobacion(r, "base")["detalle"] and comprobacion(r, "base")["grave"] is True
    assert comprobacion(r, "cpf_unico")["ok"] is True


def test_sin_el_candado_del_cpf_no_es_sana_pero_no_es_grave(base):
    r = ya(salud.revisar(base))
    assert r["ok"] is False
    c = comprobacion(r, "cpf_unico")
    assert c["ok"] is False and c["grave"] is False and "CPF repetidos" in c["detalle"]


def test_CON_LA_BASE_CAIDA_LO_DICE_SIN_CAERSE():
    r = ya(salud.revisar(_BaseCaida()))
    assert r["ok"] is False and r["comprobaciones"][0]["nombre"] == "base" and "no responde" in r["comprobaciones"][0]["detalle"]
    assert r["comprobaciones"][0]["grave"] is True


def test_VIGILAR_AVISA_UNA_VEZ_POR_CAMBIO_Y_SOLO_A_LOS_SUPER_ADMINISTRADORES(base, monkeypatch):
    avisos = []

    async def falso(**kw):
        avisos.append(kw)
        return 1
    import services.notifications as notif
    monkeypatch.setattr(notif, "avisar_al_personal", falso)
    ya(base.users.create_index("cpf_number", unique=True, sparse=True, name=NOMBRE_DEL_INDICE))
    assert ya(salud.vigilar(base, forzar=True))["ok"] is True
    assert avisos == []                                              # la primera vuelta no avisa: no hay cambio
    assert salud.ultimo_ok_de_la_base() is True
    ya(salud.vigilar(_BaseCaida(), forzar=True))
    assert len(avisos) == 1 and avisos[0]["solo_super_admin"] is True and avisos[0]["notification_type"] == "error"
    assert "NO está sana (grave)" in avisos[0]["title"]
    assert salud.ultimo_ok_de_la_base() is False
    ya(salud.vigilar(_BaseCaida(), forzar=True))                   # sigue caída: no se repite
    assert len(avisos) == 1
    ya(salud.vigilar(base, forzar=True))
    assert len(avisos) == 2 and "volvió" in avisos[1]["title"] and avisos[1]["notification_type"] == "warning"
    assert [c["ok"] for c in salud.estado()["cambios"]] == [True, False]


def test_un_aviso_que_falla_no_frena_la_vigilancia(base, monkeypatch):
    async def roto(**kw):
        raise RuntimeError("sin red")
    import services.notifications as notif
    monkeypatch.setattr(notif, "avisar_al_personal", roto)
    ya(base.users.create_index("cpf_number", unique=True, sparse=True, name=NOMBRE_DEL_INDICE))
    assert ya(salud.vigilar(base, forzar=True))["ok"] is True           # sana; el cambio de abajo sí avisa
    r = ya(salud.vigilar(_BaseCaida(), forzar=True))
    assert r["ok"] is False and salud.estado()["ultimo_ok"] is False and salud.estado()["cambios"][0]["ok"] is False


def test_sin_turno_la_vuelta_se_saltea_y_con_turno_corre(base, monkeypatch):
    from services import turnos

    async def nunca(db, nombre, *, segundos):
        return False
    monkeypatch.setattr(turnos, "me_toca", nunca)
    assert ya(salud.vigilar(base)) is None

    async def siempre(db, nombre, *, segundos):
        assert nombre == salud.TURNO and segundos < salud.CADA_SEGUNDOS
        return True
    monkeypatch.setattr(turnos, "me_toca", siempre)
    assert ya(salud.vigilar(base)) is not None


def test_el_reloj_esta_enganchado_en_server():
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[1].joinpath("server.py").read_text(encoding="utf-8")
    assert "_salud_de_la_app.arrancar(db)" in fuente and "await _salud_de_la_app.parar()" in fuente


# ─── por HTTP ─────────────────────────────────────────────────────────────

@pytest.fixture
def cliente(base):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.basic import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, TestClient(app)


def test_EL_PING_DE_VIDA_SIGUE_EN_200_Y_DICE_SI_LA_BASE_RESPONDE(cliente, base):
    app, c = cliente
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "healthy", "base": None}   # antes de la primera vuelta
    ya(salud.vigilar(base, forzar=True))
    assert c.get("/api/health").json() == {"status": "healthy", "base": True}
    ya(salud.vigilar(_BaseCaida(), forzar=True))
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["base"] is False           # 200 igual: reiniciar no levanta a Mongo


def test_el_detalle_es_solo_del_super_administrador(cliente):
    from routes import dependencies as deps
    app, c = cliente
    assert c.get("/api/admin/salud").status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: User(user_id="u_jefa", name="J", email="j@ejemplo.test", role="super_admin")
    r = c.get("/api/admin/salud")
    assert r.status_code == 200 and {x["nombre"] for x in r.json()["comprobaciones"]} == {"base", "cpf_unico"}
    assert r.json()["vigilancia"]["cada_segundos"] == 300
