"""
tests/test_salud_de_la_app.py — el ping de vida dice si la base responde,
y el reloj de salud avisa al equipo sólo cuando eso cambia.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services import limites_en_la_base                       # noqa: E402
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


TODAS = {"base", "cpf_unico", "transacciones", "bcv", "cofre", "contadores", "respaldo"}


def bcv_de_hace(base, horas):
    ya(base.bcv_rates.insert_one({"rates": {"dolar": 36.5}, "value_date": "2026-09-22",
                                  "fetched_at": datetime.now(timezone.utc) - timedelta(hours=horas)}))


@pytest.fixture
def todo_sano(base, monkeypatch):
    """La aplicación como tiene que estar en producción: candado del CPF,
    Mongo con réplicas, BCV fresco, cofre cifrando con la llave buena y los
    contadores en la base."""
    from services import cofre, transacciones
    ya(base.users.create_index("cpf_number", unique=True, sparse=True, name=NOMBRE_DEL_INDICE))
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", True)
    bcv_de_hace(base, 2)
    monkeypatch.setenv(cofre.VARIABLE_MODO, "cifrando")
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, cofre.llave_nueva()["llave"])
    ya(cofre.sellar_testigo(base))
    monkeypatch.setenv(limites_en_la_base.VARIABLE, "si")
    # Un respaldo automático de hace dos horas, guardado afuera y comprobado.
    from services import envios_almacen
    for v in (envios_almacen.VAR_ENDPOINT, envios_almacen.VAR_BUCKET, envios_almacen.VAR_ACCESS_KEY, envios_almacen.VAR_SECRETO):
        monkeypatch.setenv(v, "https://cuenta.r2.example" if v == envios_almacen.VAR_ENDPOINT else "x")
    ya(base.respaldos.insert_one({"origen": "automatico", "error": None, "documentos": 9, "momento": datetime.now(timezone.utc) - timedelta(hours=2),
                                  "almacen": {"bucket": "x", "clave": "respaldos/a.jsonl", "borrado_en": None}, "comprobacion": {"ok": True}}))
    return base


def test_SANA_CUANDO_TODO_ESTA_COMO_TIENE_QUE_ESTAR(todo_sano):
    r = ya(salud.revisar(todo_sano))
    assert r["ok"] is True, r
    assert {c["nombre"] for c in r["comprobaciones"]} == TODAS
    assert comprobacion(r, "base")["ok"] and "responde en" in comprobacion(r, "base")["detalle"] and comprobacion(r, "base")["grave"] is True
    assert all(c["ok"] for c in r["comprobaciones"])
    assert "de hace 2 h" in comprobacion(r, "bcv")["detalle"]


def test_sin_el_candado_del_cpf_no_es_sana_pero_no_es_grave(todo_sano):
    ya(todo_sano.users.drop_index(NOMBRE_DEL_INDICE))
    r = ya(salud.revisar(todo_sano))
    assert r["ok"] is False
    c = comprobacion(r, "cpf_unico")
    assert c["ok"] is False and c["grave"] is False and "CPF repetidos" in c["detalle"]


def test_CON_MONGO_DE_UN_SOLO_NODO_LO_DICE(todo_sano, monkeypatch):
    """Lo detecta el motor contable al arrancar y lo decía sólo en el log."""
    from services import transacciones
    monkeypatch.setattr(transacciones, "_SUPPORTS_TRANSACTIONS", False)
    c = comprobacion(ya(salud.revisar(todo_sano)), "transacciones")
    assert c["ok"] is False and c["grave"] is False
    assert "replica set" in c["detalle"] and "dos escrituras" in c["detalle"]


def test_CON_REPLICAS_NO_PROMETE_LO_QUE_NO_PASA(todo_sano):
    """Decía «los cobros se escriben en una sola operación» y el saldo del
    cliente nunca pasó por una transacción: con réplicas, la salud se ponía en
    verde afirmando algo falso."""
    c = comprobacion(ya(salud.revisar(todo_sano)), "transacciones")
    assert c["ok"] is True
    assert "los cobros se escriben en una sola operación" not in c["detalle"]
    assert "todavía son dos escrituras separadas" in c["detalle"]


def test_con_la_tasa_del_bcv_vencida_o_ausente_lo_dice(todo_sano):
    ya(todo_sano.bcv_rates.delete_many({}))
    c = comprobacion(ya(salud.revisar(todo_sano)), "bcv")
    assert c["ok"] is False and "ningún raspado" in c["detalle"]
    bcv_de_hace(todo_sano, 80)
    c = comprobacion(ya(salud.revisar(todo_sano)), "bcv")
    assert c["ok"] is False and "VENCIDA" in c["detalle"] and "de hace 80 h" in c["detalle"]


def test_con_el_cofre_apagado_no_es_sana_y_no_es_grave(todo_sano, monkeypatch):
    from services import cofre
    monkeypatch.setenv(cofre.VARIABLE_MODO, "apagado")
    c = comprobacion(ya(salud.revisar(todo_sano)), "cofre")
    assert c["ok"] is False and c["grave"] is False and "en claro" in c["detalle"]


def test_CON_LA_LLAVE_EQUIVOCADA_DEL_COFRE_ES_GRAVE(todo_sano, monkeypatch):
    """El KYC no puede abrir ni guardar documentos: es una caída, no un aviso."""
    from services import cofre
    monkeypatch.setenv(cofre.VARIABLE_LLAVE, cofre.llave_nueva()["llave"])
    r = ya(salud.revisar(todo_sano))
    c = comprobacion(r, "cofre")
    assert c["ok"] is False and c["grave"] is True and "NO ES LA CORRECTA" in c["detalle"]


def test_con_los_contadores_en_memoria_lo_dice_y_nombra_la_variable(todo_sano, monkeypatch):
    monkeypatch.delenv(limites_en_la_base.VARIABLE)
    c = comprobacion(ya(salud.revisar(todo_sano)), "contadores")
    assert c["ok"] is False and c["grave"] is False
    assert "MEMORIA" in c["detalle"] and "LIMITES_EN_LA_BASE=si" in c["detalle"]


def test_UNA_COMPROBACION_QUE_EXPLOTA_NO_DEJA_A_LAS_OTRAS_SIN_MIRAR(todo_sano, monkeypatch):
    from services import bcv_scraper

    async def rota(db, session=None):
        raise RuntimeError("se rompió el raspador")
    monkeypatch.setattr(bcv_scraper, "vigencia", rota)
    r = ya(salud.revisar(todo_sano))
    assert {c["nombre"] for c in r["comprobaciones"]} == TODAS
    c = comprobacion(r, "bcv")
    assert c["ok"] is False and "no se pudo mirar" in c["detalle"] and "se rompió el raspador" in c["detalle"]
    assert comprobacion(r, "cofre")["ok"] and comprobacion(r, "contadores")["ok"]


def test_CON_LA_BASE_CAIDA_LO_DICE_SIN_CAERSE():
    r = ya(salud.revisar(_BaseCaida()))
    assert r["ok"] is False and r["comprobaciones"][0]["nombre"] == "base" and "no responde" in r["comprobaciones"][0]["detalle"]
    assert r["comprobaciones"][0]["grave"] is True


def test_VIGILAR_AVISA_UNA_VEZ_POR_CAMBIO_Y_SOLO_A_LOS_SUPER_ADMINISTRADORES(todo_sano, monkeypatch):
    base = todo_sano
    avisos = []

    async def falso(**kw):
        avisos.append(kw)
        return 1
    import services.notifications as notif
    monkeypatch.setattr(notif, "avisar_al_personal", falso)
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


def test_un_aviso_que_falla_no_frena_la_vigilancia(todo_sano, monkeypatch):
    base = todo_sano
    async def roto(**kw):
        raise RuntimeError("sin red")
    import services.notifications as notif
    monkeypatch.setattr(notif, "avisar_al_personal", roto)
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
    assert r.status_code == 200 and {x["nombre"] for x in r.json()["comprobaciones"]} == TODAS
    assert r.json()["vigilancia"]["cada_segundos"] == 300


def test_sin_respaldo_automatico_reciente_no_es_sana(todo_sano):
    ya(todo_sano.respaldos.delete_many({}))
    c = comprobacion(ya(salud.revisar(todo_sano)), "respaldo")
    assert c["ok"] is False and c["grave"] is False and "todavía" in c["detalle"]
