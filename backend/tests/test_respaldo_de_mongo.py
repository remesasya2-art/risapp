"""
tests/test_respaldo_de_mongo.py — la exportación de la base de la
aplicación, su firma, y la comprobación que prueba que se puede leer.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")
from bson import json_util                                    # noqa: E402
from bson.binary import Binary                                # noqa: E402

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services import respaldo_de_mongo as resp                # noqa: E402
from services.money import to_decimal128                      # noqa: E402

JEFA = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base(monkeypatch):
    monkeypatch.delenv("LLAVE_DE_RESPALDO", raising=False)
    monkeypatch.delenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", raising=False)
    m = mongomock_motor.AsyncMongoMockClient()["respaldo_mongo"]
    usar_base(m)
    ya(m.users.insert_one({"user_id": "u1", "email": "u1@ejemplo.test", "balance_ris": to_decimal128("10.50"),
                           "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}))
    ya(m.verifications.insert_one({"user_id": "u1", "documento": Binary(b"\x00\x01cifrado")}))
    ya(m.ledger.insert_one({"user_id": "u1", "amount": to_decimal128("10.50")}))
    ya(m.user_sessions.insert_one({"user_id": "u1", "token": "secreto-de-sesion"}))       # no se conserva
    ya(m.bcv_rates.insert_one({"rate": 36.5}))                                            # se regenera sola
    return m


def test_EL_RESPALDO_LLEVA_LO_QUE_SE_CONSERVA_CON_SUS_TIPOS_Y_NO_LAS_SESIONES(base):
    r = ya(resp.crear(base, quien=JEFA))
    contenido, firma_del_archivo = resp.partir(r["contenido"])
    assert firma_del_archivo is None, "sin llave, la línea de firma va sin firma"
    lineas = contenido.strip().split("\n")
    cabecera, cierre = json_util.loads(lineas[0]), json_util.loads(lineas[-1])
    assert cabecera["tipo"] == "respaldo_risapp" and cierre["documentos"] == 3 == r["documentos"]
    filas = [json_util.loads(l) for l in lineas[1:-1]]
    assert {f["coleccion"] for f in filas} == {"users", "verifications", "ledger"}
    assert "secreto-de-sesion" not in r["contenido"] and "user_sessions" not in {f["coleccion"] for f in filas}
    usuario = next(f["doc"] for f in filas if f["coleccion"] == "users")
    assert usuario["balance_ris"].to_decimal() == Decimal("10.50")                       # Decimal128 conservado
    assert usuario["created_at"].year == 2026                                            # fecha conservada
    assert next(f["doc"] for f in filas if f["coleccion"] == "verifications")["documento"] == b"\x00\x01cifrado"
    assert r["firmado"] is False and r["firma"] is None
    assert ya(resp.listar(base))[0]["hash"] == r["hash"] and "contenido" not in ya(resp.listar(base))[0]
    assert ya(base.auditoria.find_one({"accion": "respaldo.creado"}))["actor"]["user_id"] == "u_jefa"


def test_LA_COMPROBACION_PASA_CON_EL_ARCHIVO_INTACTO_Y_FALLA_CON_UNO_TOCADO(base, monkeypatch):
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    assert r["firmado"] is True and len(r["firma"]) == 64
    c = ya(resp.comprobar_y_anotar(base, r["contenido"], r["firma"], quien=JEFA))
    assert c["ok"] is True and c["hash_ok"] is True and c["firma"] == "ok" and c["registrado"] is True
    assert set(c["colecciones"]) == {"users", "verifications", "ledger"} and c["documentos"] == 3
    assert ya(resp.listar(base))[0]["comprobacion"]["ok"] is True
    tocado = r["contenido"].replace('"10.50"', '"99.50"', 1)
    assert tocado != r["contenido"]
    c = resp.comprobar(tocado, r["firma"])
    assert c["ok"] is False and c["hash_ok"] is False and "alterado" in c["motivo"]
    assert resp.comprobar(r["contenido"], "0" * 64)["firma"] == "invalida"
    monkeypatch.delenv("LLAVE_DE_RESPALDO")
    assert resp.comprobar(r["contenido"], r["firma"])["firma"] == "sin_llave"
    assert ya(base.auditoria.count_documents({"accion": "respaldo.comprobado"})) == 1


def test_la_llave_del_nucleo_sirve_si_no_hay_una_propia(monkeypatch):
    monkeypatch.setenv("NUCLEO_SECRETO_LLAVE_DE_RESPALDO", "la-del-nucleo")
    assert resp.hay_llave() and resp.firmar("x") is not None
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "la-propia")
    import hashlib, hmac
    huella = hashlib.sha256(b"x").hexdigest()
    assert resp.firmar("x") == hmac.new(b"la-propia", huella.encode(), hashlib.sha256).hexdigest()
    assert resp.firmar("x") == resp.firmar_huella(huella), "la firma es sobre la huella, no sobre el contenido"


def test_UN_DOCUMENTO_SACADO_CON_EL_CIERRE_REHECHO_SE_NOTA_POR_LA_CUENTA(base):
    """Alguien saca una línea y rehace el hash del cierre para que coincida:
    la cantidad de documentos del cierre sigue siendo la original, y eso lo
    delata."""
    import hashlib
    r = ya(resp.crear(base, quien=JEFA))
    lineas = resp.partir(r["contenido"])[0].strip().split("\n")
    cierre = json_util.loads(lineas[-1])
    sin_una = lineas[:-2] + [lineas[-1]]                       # se saca el último documento
    cuerpo = "\n".join(sin_una[:-1]) + "\n"
    cierre["hash"] = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
    rehecho = cuerpo + json_util.dumps(cierre, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True, separators=(",", ":")) + "\n"
    c = resp.comprobar(rehecho)
    assert c["hash_ok"] is True and c["ok"] is False and "el cierre dice 3 documentos y hay 2" in c["motivo"]


def test_un_archivo_que_no_es_un_respaldo_se_rechaza_con_motivo():
    assert "cabecera" in resp.comprobar("")["motivo"]
    assert "JSON" in resp.comprobar("hola\nchau\n")["motivo"]
    assert "no es un respaldo" in resp.comprobar('{"tipo":"otro"}\n{"tipo":"fin"}\n')["motivo"]


def test_las_colecciones_que_se_conservan_no_incluyen_lo_efimero():
    for efimera in ("user_sessions", "password_recovery", "twofa_pending", "pending_verifications", "notifications", "bcv_rates", "rates", "counters", "contadores"):
        assert efimera not in resp.COLECCIONES_QUE_SE_CONSERVAN, efimera
    for vital in ("users", "transactions", "ledger", "verifications", "auditoria", "config", "gestor_pix_payments"):
        assert vital in resp.COLECCIONES_QUE_SE_CONSERVAN, vital


# ─── por HTTP ─────────────────────────────────────────────────────────────

def test_por_http_solo_el_super_administrador_y_la_lista_no_trae_el_contenido(base, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.respaldo_admin import router
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    c = TestClient(app)
    assert c.get("/api/admin/respaldos").status_code in (401, 403)
    assert c.post("/api/admin/respaldos").status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    r = c.get("/api/admin/respaldos")
    assert r.status_code == 200 and r.json()["llave_configurada"] is True and "users" in r.json()["colecciones_que_se_conservan"]
    r = c.post("/api/admin/respaldos")
    assert r.status_code == 200 and r.json()["firmado"] is True and r.json()["contenido"].startswith('{"actor"')
    contenido, firma = r.json()["contenido"], r.json()["firma"]
    assert c.get("/api/admin/respaldos").json()["respaldos"][0]["contenido"] is None
    r = c.post("/api/admin/respaldos/comprobar", json={"contenido": contenido, "firma": firma})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["registrado"] is True
    r = c.post("/api/admin/respaldos/comprobar", json={"contenido": contenido + "x", "firma": firma})
    assert r.status_code == 200 and r.json()["ok"] is False


# ══════════════════════════════════════════════════════════════════════════
# La firma sobre la huella, adentro del archivo, y la comprobación sin subirlo
# ══════════════════════════════════════════════════════════════════════════

def _huella(texto):
    import hashlib
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def test_EL_ARCHIVO_TERMINA_CON_LA_LINEA_DE_FIRMA_Y_SE_BASTA_SOLO(base, monkeypatch):
    """Cuatro respaldos creados y ninguna firma guardada: la pantalla la
    mostraba en un texto que desaparecía. Ahora viaja adentro del archivo."""
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    ultima = json_util.loads(r["contenido"].strip().split("\n")[-1])
    assert ultima == {"tipo": "firma", "hash": r["hash"], "firma": r["firma"], "documentos": 3}
    contenido, firma = resp.partir(r["contenido"])
    assert firma == r["firma"] and _huella(contenido) == r["hash"], "la huella registrada es la del contenido SIN la línea de firma"
    # Comprobar el archivo tal cual, sin pasar la firma aparte: la lee de adentro.
    c = ya(resp.comprobar_y_anotar(base, r["contenido"], None, quien=JEFA))
    assert c["ok"] is True and c["firma"] == "ok" and c["registrado"] is True and c["hash"] == r["hash"]


def test_LA_FIRMA_ES_SOBRE_LA_HUELLA_Y_LA_DEL_ESQUEMA_ANTERIOR_SIGUE_VALIENDO(base, monkeypatch):
    import hashlib, hmac
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    contenido, _ = resp.partir(r["contenido"])
    assert r["firma"] == hmac.new(b"llave-de-prueba", r["hash"].encode(), hashlib.sha256).hexdigest()
    vieja = hmac.new(b"llave-de-prueba", contenido.encode("utf-8"), hashlib.sha256).hexdigest()   # septiembre de 2026
    assert resp.comprobar(contenido, vieja)["firma"] == "ok", "los cuatro respaldos del esquema anterior no quedan huérfanos"
    assert resp.comprobar(contenido, "0" * 64)["firma"] == "invalida"


def test_COMPROBAR_POR_LA_HUELLA_NO_NECESITA_EL_ARCHIVO(base, monkeypatch):
    """Lo que hace el navegador: lee el archivo de su lado y manda la huella,
    la cuenta y lo que encontró. El servidor pone la firma y el registro."""
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    c = ya(resp.comprobar_huella(base, huella=r["hash"], documentos=3, hash_de_cierre_ok=True, lineas_ok=True,
                                 colecciones={"users": 1, "verifications": 1, "ledger": 1}, firma=r["firma"], quien=JEFA))
    assert c["ok"] is True and c["firma"] == "ok" and c["registrado"] is True and c["en"] == "navegador"
    fila = ya(resp.listar(base))[0]
    assert fila["comprobacion"]["ok"] is True and fila["comprobacion"]["en"] == "navegador" and fila["comprobado_en"]
    aud = ya(base.auditoria.find_one({"accion": "respaldo.comprobado"}))
    assert aud["detalle"]["en"] == "navegador" and aud["detalle"]["ok"] is True


def test_comprobar_por_la_huella_dice_por_que_no_pasa(base, monkeypatch):
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    bien = dict(huella=r["hash"], documentos=3, hash_de_cierre_ok=True, lineas_ok=True, firma=r["firma"], quien=JEFA)
    c = ya(resp.comprobar_huella(base, **{**bien, "huella": "a" * 64}))
    assert c["ok"] is False and c["registrado"] is False and "no figura" in c["motivo"]
    c = ya(resp.comprobar_huella(base, **{**bien, "firma": "0" * 64}))
    assert c["ok"] is False and c["firma"] == "invalida" and "firma" in c["motivo"]
    c = ya(resp.comprobar_huella(base, **{**bien, "hash_de_cierre_ok": False}))
    assert c["ok"] is False and c["hash_ok"] is False and "alterado" in c["motivo"]
    c = ya(resp.comprobar_huella(base, **{**bien, "lineas_ok": False, "motivo_del_navegador": "la línea 7 no se puede leer"}))
    assert c["ok"] is False and c["motivo"] == "la línea 7 no se puede leer"
    c = ya(resp.comprobar_huella(base, **{**bien, "documentos": 2}))
    assert c["ok"] is False and "el registro dice 3 documentos y el archivo tiene 2" in c["motivo"]
    c = ya(resp.comprobar_huella(base, **{**bien, "firma": None}))
    assert c["ok"] is True and c["firma"] == "sin_firma"
    assert ya(base.auditoria.count_documents({"accion": "respaldo.comprobado", "exito": False})) == 5


def test_una_firma_del_esquema_anterior_no_se_puede_verificar_por_la_huella_y_lo_dice(base, monkeypatch):
    import hashlib, hmac
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    r = ya(resp.crear(base, quien=JEFA))
    contenido, _ = resp.partir(r["contenido"])
    vieja = hmac.new(b"llave-de-prueba", contenido.encode("utf-8"), hashlib.sha256).hexdigest()
    ya(base[resp.COLECCION_DEL_REGISTRO].update_one({"hash": r["hash"]}, {"$unset": {"esquema_de_firma": ""}}))   # un registro de antes
    c = ya(resp.comprobar_huella(base, huella=r["hash"], documentos=3, hash_de_cierre_ok=True, lineas_ok=True, firma=vieja, quien=JEFA))
    assert c["firma"] == "no_verificable_por_la_huella" and c["ok"] is True, "el registro de la base respalda la huella; la firma vieja no se puede juzgar sin el archivo"
    # Con un registro del esquema actual, la misma firma vieja es simplemente inválida.
    ya(base[resp.COLECCION_DEL_REGISTRO].update_one({"hash": r["hash"]}, {"$set": {"esquema_de_firma": "huella"}}))
    c = ya(resp.comprobar_huella(base, huella=r["hash"], documentos=3, hash_de_cierre_ok=True, lineas_ok=True, firma=vieja, quien=JEFA))
    assert c["firma"] == "invalida" and c["ok"] is False


def test_por_http_la_comprobacion_por_huella_es_del_super_administrador(base, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.respaldo_admin import router
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    c = TestClient(app)
    cuerpo = {"hash": "a" * 64, "documentos": 3, "hash_de_cierre_ok": True, "lineas_ok": True}
    assert c.post("/api/admin/respaldos/comprobar-huella", json=cuerpo).status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    r = ya(resp.crear(base, quien=JEFA))
    cuerpo.update(hash=r["hash"], firma=r["firma"], colecciones={"users": 1, "verifications": 1, "ledger": 1})
    res = c.post("/api/admin/respaldos/comprobar-huella", json=cuerpo)
    assert res.status_code == 200 and res.json()["ok"] is True and res.json()["en"] == "navegador"
    assert c.post("/api/admin/respaldos/comprobar-huella", json={**cuerpo, "hash": "no-es-una-huella"}).status_code == 422


def test_LA_PANTALLA_COMPRUEBA_POR_LA_HUELLA_Y_NO_SUBE_EL_ARCHIVO():
    """Con 70 MB desde una conexión de casa, subir el archivo moría por tiempo
    en Cloudflare. La pantalla lee el archivo de su lado y manda la huella."""
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend", "src", "components", "admin", "Respaldo.jsx").read_text(encoding="utf-8")
    assert "'/admin/respaldos/comprobar-huella'" in fuente
    assert "'/admin/respaldos/comprobar'" not in fuente, "la pantalla no debe volver a subir el archivo entero"
    assert "crypto.subtle.digest('SHA-256'" in fuente, "la huella se calcula en el navegador"
    assert "readAsText" not in fuente
    assert "tipo === 'firma'" in fuente, "la firma se lee de la última línea del archivo"
