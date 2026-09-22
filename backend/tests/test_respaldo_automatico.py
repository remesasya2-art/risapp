"""
tests/test_respaldo_automatico.py — el reloj que crea un respaldo por día, lo
firma, lo guarda afuera, lo comprueba entero y conserva los últimos N.
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
from services import envios_almacen as almacen                # noqa: E402
from services import gritos, salud_de_la_app                  # noqa: E402
from services import respaldo_automatico as ra                # noqa: E402
from services import respaldo_de_mongo as rm                  # noqa: E402
from services.money import to_decimal128                      # noqa: E402

JEFA = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")
T0 = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)


def ya(c):
    return asyncio.run(c)


class _BucketFalso:
    """Un S3 de mentira: guarda, devuelve, borra y firma enlaces."""
    def __init__(self):
        self.objetos = {}
        self.falla_al_escribir = False
        self.falla_al_preguntar = False
        self.escribe_pero_altera = False

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):
        if self.falla_al_escribir:
            raise RuntimeError("503 del bucket")
        datos = bytes(Body)
        if self.escribe_pero_altera:
            datos = datos.replace(b'"10.50"', b'"99.50"', 1)                 # el bucket guardó otra cosa
        self.objetos[(Bucket, Key)] = (datos, ContentType)
        return {}

    def get_object(self, Bucket=None, Key=None):
        if (Bucket, Key) not in self.objetos:
            e = RuntimeError("NoSuchKey")
            e.response = {"Error": {"Code": "NoSuchKey"}}
            raise e
        import io
        return {"Body": io.BytesIO(self.objetos[(Bucket, Key)][0])}

    def head_object(self, Bucket=None, Key=None):
        if self.falla_al_preguntar:
            raise RuntimeError("timeout del bucket")
        if (Bucket, Key) not in self.objetos:
            # La forma exacta del error de boto3: `_clasificar` lee `.response`.
            e = RuntimeError("NoSuchKey")
            e.response = {"Error": {"Code": "NoSuchKey"}}
            raise e
        return {}

    def generate_presigned_url(self, operacion, Params=None, ExpiresIn=None):
        return f"https://r2.example/{Params['Bucket']}/{Params['Key']}?firma=xyz&vence={ExpiresIn}"


@pytest.fixture
def bucket(monkeypatch):
    b = _BucketFalso()
    monkeypatch.setenv(almacen.VAR_ENDPOINT, "https://cuenta.r2.example")
    monkeypatch.setenv(almacen.VAR_BUCKET, "risapp-pruebas")
    monkeypatch.setenv(almacen.VAR_ACCESS_KEY, "clave")
    monkeypatch.setenv(almacen.VAR_SECRETO, "secreto")
    monkeypatch.setattr(almacen, "_construir_cliente", lambda *a, **k: b)
    almacen.olvidar_cliente()
    yield b
    almacen.olvidar_cliente()


@pytest.fixture(autouse=True)
def base(monkeypatch):
    monkeypatch.setenv("LLAVE_DE_RESPALDO", "llave-de-prueba")
    for v in (almacen.VAR_ENDPOINT, almacen.VAR_BUCKET, almacen.VAR_ACCESS_KEY, almacen.VAR_SECRETO):
        monkeypatch.delenv(v, raising=False)
    m = mongomock_motor.AsyncMongoMockClient()["respaldo_automatico"]
    usar_base(m)
    ra.reiniciar_para_tests()
    gritos.reiniciar_para_tests()
    ya(m.users.insert_one({"user_id": "sa-1", "role": "super_admin", "is_active": True, "name": "S", "email": "s@example.com"}))
    ya(m.users.insert_one({"user_id": "u1", "email": "u1@ejemplo.test", "balance_ris": to_decimal128("10.50")}))
    ya(m.ledger.insert_one({"user_id": "u1", "amount": to_decimal128("10.50")}))
    return m


def filas(base):
    return ya(base[rm.COLECCION_DEL_REGISTRO].find({}).sort("momento", 1).to_list(100))


# ══════════════════════════════════════════════════════════════════════════
# 1. Un respaldo automático completo
# ══════════════════════════════════════════════════════════════════════════

def test_EL_RELOJ_EXPORTA_SUBE_COMPRUEBA_Y_REGISTRA(base, bucket):
    r = ya(ra.correr(base, ahora=T0))
    assert r["hecho"] is True and r["clave"] == "respaldos/risapp-respaldo-2026-09-23T030000.jsonl"
    (contenido, tipo), = [bucket.objetos[k] for k in bucket.objetos]
    assert tipo == "application/x-ndjson"
    texto = contenido.decode("utf-8")
    assert texto.startswith('{"actor":"reloj"') and '"tipo":"firma"' in texto.strip().split("\n")[-1]
    # Lo guardado se puede comprobar como cualquier archivo, con la firma de adentro.
    assert rm.comprobar(texto)["ok"] is True and rm.comprobar(texto)["firma"] == "ok"
    (fila,) = filas(base)
    assert fila["origen"] == "automatico" and fila["actor"] == "reloj" and fila["error"] is None
    assert fila["almacen"] == {"bucket": "risapp-pruebas", "clave": r["clave"], "bytes": len(contenido), "borrado_en": None}
    assert fila["comprobacion"]["ok"] is True and fila["comprobacion"]["en"] == "servidor" and ra._aware(fila["comprobado_en"]) == T0
    acciones = ya(base.auditoria.find({"accion": {"$regex": "^respaldo"}}).to_list(10))
    assert {a["accion"] for a in acciones} == {"respaldo.creado"} and acciones[0]["detalle"]["origen"] == "automatico"
    assert acciones[0]["detalle"]["guardado_afuera"] is True
    assert ya(base.errores.count_documents({})) == 0


def test_sin_almacen_no_hay_a_donde_guardar_y_no_se_hace_nada(base):
    assert ya(ra.correr(base, ahora=T0)) == {"hecho": False, "motivo": "sin_almacen"}
    assert filas(base) == []
    ok, detalle, grave = ya(ra.para_la_salud(base, ahora=T0))
    assert ok is False and grave is False and "ENVIOS_R2_" in detalle


def test_apagado_desde_configuracion_no_corre_pero_el_boton_ahora_si(base, bucket):
    ya(base.config.insert_one({"clave": ra.AJUSTE_ENCENDIDO, "valor": "0"}))
    assert ya(ra.correr(base, ahora=T0)) == {"hecho": False, "motivo": "apagado"}
    assert ya(ra.vigilar(base, forzar=True, ahora=T0)) == {"hecho": False, "motivo": "apagado"}
    assert ya(ra.correr(base, ahora=T0, forzar=True))["hecho"] is True
    ok, detalle, _ = ya(ra.para_la_salud(base, ahora=T0))
    assert ok is False and "APAGADO" in detalle


def test_UNO_POR_DIA_Y_NO_MAS(base, bucket):
    assert ya(ra.hace_falta(base, T0)) is True
    ya(ra.correr(base, ahora=T0))
    assert ya(ra.hace_falta(base, T0 + timedelta(hours=1))) is False
    assert ya(ra.vigilar(base, forzar=True, ahora=T0 + timedelta(hours=22)))["motivo"] == "reciente"
    assert ya(ra.hace_falta(base, T0 + timedelta(hours=ra.HORAS_ENTRE_RESPALDOS))) is True
    assert ya(ra.vigilar(base, forzar=True, ahora=T0 + timedelta(hours=24)))["hecho"] is True
    assert len(filas(base)) == 2


def test_LA_APLICACION_NO_BORRA_NADA_DEL_ALMACEN_Y_SE_ENTERA_DE_LO_QUE_R2_BORRO(base, bucket):
    """El token de R2 no puede borrar, a propósito: la retención es una regla
    de ciclo de vida del bucket. Cuando R2 se lleva uno, la aplicación lo
    marca al pedir el enlace, en vez de ofrecer un enlace a nada."""
    import ast as _ast
    import pathlib
    for archivo in ("respaldo_automatico.py", "envios_almacen.py"):
        arbol = _ast.parse(pathlib.Path(__file__).resolve().parents[1].joinpath("services", archivo).read_text(encoding="utf-8"))
        assert not ({n.attr for n in _ast.walk(arbol) if isinstance(n, _ast.Attribute)} & {"delete_object", "delete_objects"}), archivo
    ya(ra.correr(base, ahora=T0))
    (fila,) = filas(base)
    assert ya(ra.enlace_de_descarga(base, fila["_id"] and str(fila["_id"]))).startswith("https://r2.example/")
    bucket.objetos.clear()                                          # la regla de retención de R2 se lo llevó
    assert ya(ra.enlace_de_descarga(base, str(fila["_id"]))) is None
    (fila,) = filas(base)
    assert fila["almacen"]["borrado_en"] is not None, "la fila queda: dice que existió y cuándo se supo que ya no estaba"
    assert ya(ra.enlace_de_descarga(base, str(fila["_id"]))) is None
    assert ra.estado()["retencion_recomendada_dias"] == 30


def test_si_no_se_puede_preguntar_al_almacen_el_enlace_se_da_igual(base, bucket):
    """Un error de red al preguntar no es «no está»: se da el enlace y que lo
    diga R2. Marcar como borrado por un timeout sería mentir."""
    ya(ra.correr(base, ahora=T0))
    (fila,) = filas(base)
    bucket.falla_al_preguntar = True
    assert ya(ra.enlace_de_descarga(base, str(fila["_id"]))) is not None
    assert filas(base)[0]["almacen"]["borrado_en"] is None


def test_UN_ALMACEN_QUE_NO_ESCRIBE_DEJA_REGISTRO_CON_ERROR_Y_GRITA(base, bucket):
    bucket.falla_al_escribir = True
    r = ya(ra.correr(base, ahora=T0))
    assert r["hecho"] is False and r["motivo"] == "almacen"
    (fila,) = filas(base)
    assert fila["almacen"] is None and fila["error"] == "no se pudo guardar en el almacén de objetos"
    (grito,) = ya(base.errores.find({"tipo": gritos.RESPALDO_FALLIDO}).to_list(5))
    assert "RESPALDO" in grito["mensaje"].upper() or "almacén" in grito["mensaje"]
    (aviso,) = ya(base.notifications.find({}).to_list(5))
    assert aviso["user_id"] == "sa-1" and "RESPALDO" in aviso["title"]
    assert ya(ra.ultimo_bueno(base)) is None, "un respaldo fallido no cuenta como el último bueno"
    assert ya(ra.hace_falta(base, T0 + timedelta(hours=1))) is True, "y se vuelve a intentar en la próxima vuelta"


def test_LO_QUE_SE_COMPRUEBA_ES_LO_QUE_QUEDO_EN_EL_ALMACEN(base, bucket):
    """Si el bucket guardó otra cosa, comprobar el texto que se tenía en
    memoria diría «bien». Se vuelve a leer de ahí y se comprueba eso."""
    bucket.escribe_pero_altera = True
    r = ya(ra.correr(base, ahora=T0))
    assert r["hecho"] is False and r["motivo"] == "comprobacion"
    (fila,) = filas(base)
    assert fila["almacen"] is not None and "no pasa la comprobación" in fila["error"] and fila["comprobacion"]["ok"] is False
    assert ya(base.errores.count_documents({"tipo": gritos.RESPALDO_FALLIDO})) == 1
    assert ya(ra.ultimo_bueno(base)) is None


def test_una_exportacion_que_explota_tambien_grita(base, bucket, monkeypatch):
    async def rota(db, *, actor, ahora=None):
        raise RuntimeError("Mongo se cayó a mitad de camino")
    monkeypatch.setattr(rm, "exportar", rota)
    r = ya(ra.correr(base, ahora=T0))
    assert r["hecho"] is False and r["motivo"] == "exportar"
    assert ya(base.errores.count_documents({"tipo": gritos.RESPALDO_FALLIDO})) == 1


# ══════════════════════════════════════════════════════════════════════════
# 2. La salud y el reloj
# ══════════════════════════════════════════════════════════════════════════

def test_LA_SALUD_DICE_SI_HAY_UNO_DE_MENOS_DE_UN_DIA(base, bucket):
    ok, detalle, _ = ya(ra.para_la_salud(base, ahora=T0))
    assert ok is False and "todavía" in detalle
    ya(ra.correr(base, ahora=T0))
    ok, detalle, grave = ya(ra.para_la_salud(base, ahora=T0 + timedelta(hours=5)))
    assert ok is True and grave is False and "de hace 5 h" in detalle and "comprobado" in detalle
    ok, detalle, _ = ya(ra.para_la_salud(base, ahora=T0 + timedelta(hours=ra.HORAS_PARA_ESTAR_SANO + 1)))
    assert ok is False and "de hace 27 h" in detalle
    r = ya(salud_de_la_app.revisar(base))
    assert any(c["nombre"] == "respaldo" for c in r["comprobaciones"])


def test_sin_turno_la_vuelta_se_saltea(base, bucket, monkeypatch):
    from services import turnos

    async def nunca(db, nombre, *, segundos):
        assert nombre == ra.TURNO and segundos < ra.CADA_SEGUNDOS
        return False
    monkeypatch.setattr(turnos, "me_toca", nunca)
    assert ya(ra.vigilar(base, ahora=T0)) is None and filas(base) == []


def test_el_reloj_esta_enganchado_en_server():
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[1].joinpath("server.py").read_text(encoding="utf-8")
    assert "_respaldo_automatico.arrancar(db)" in fuente and "await _respaldo_automatico.parar()" in fuente


# ══════════════════════════════════════════════════════════════════════════
# 3. Por HTTP
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def cliente(base):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import dependencies as deps
    from routes.respaldo_admin import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, TestClient(app), deps


def test_POR_HTTP_EL_BOTON_AHORA_Y_EL_ENLACE_SON_DEL_SUPER_ADMINISTRADOR(cliente, bucket, base):
    app, c, deps = cliente
    assert c.post("/api/admin/respaldos/automatico").status_code in (401, 403)
    assert c.get("/api/admin/respaldos/000000000000000000000000/enlace").status_code in (401, 403)
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    r = c.post("/api/admin/respaldos/automatico")
    assert r.status_code == 200 and r.json()["hecho"] is True and r.json()["clave"].startswith("respaldos/")
    lista = c.get("/api/admin/respaldos").json()
    assert lista["automatico"]["configurado"] is True and lista["automatico"]["encendido"] is True and lista["automatico"]["retencion_recomendada_dias"] == 30
    (fila,) = lista["respaldos"]
    assert fila["origen"] == "automatico" and fila["actor"] == "u_jefa"
    assert set(fila["almacen"]) == {"bucket", "clave", "borrado_en"}, "del almacén sólo dónde quedó, nunca una credencial"
    assert set(ya(rm.listar(base))[0]["almacen"]) == {"bucket", "clave", "borrado_en"}, "y la lista del servicio ya viene así, no sólo el modelo"
    e = c.get(f"/api/admin/respaldos/{fila['id']}/enlace")
    assert e.status_code == 200 and e.json()["url"].startswith("https://r2.example/risapp-pruebas/respaldos/") and e.json()["vence_en_segundos"] == 600
    assert c.get("/api/admin/respaldos/000000000000000000000000/enlace").status_code == 404


def test_por_http_un_respaldo_podado_no_tiene_enlace(cliente, bucket, base):
    app, c, deps = cliente
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    ya(ra.correr(base, ahora=T0))
    fila = c.get("/api/admin/respaldos").json()["respaldos"][0]
    ya(base[rm.COLECCION_DEL_REGISTRO].update_one({}, {"$set": {"almacen.borrado_en": T0}}))
    assert c.get(f"/api/admin/respaldos/{fila['id']}/enlace").status_code == 404


def test_sin_almacen_la_lista_lo_dice(cliente):
    app, c, deps = cliente
    app.dependency_overrides[deps.get_super_admin] = lambda: JEFA
    lista = c.get("/api/admin/respaldos").json()
    assert lista["automatico"]["configurado"] is False
    assert c.post("/api/admin/respaldos/automatico").json() == {"hecho": False, "motivo": "sin_almacen", "error": None, "id": None,
                                                               "clave": None, "documentos": None, "bytes": None, "hash": None}


def test_LA_PANTALLA_TIENE_EL_BOTON_AHORA_Y_EL_ENLACE_DE_DESCARGA():
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend", "src", "components", "admin", "Respaldo.jsx").read_text(encoding="utf-8")
    assert "'/admin/respaldos/automatico'" in fuente and "/enlace`" in fuente
