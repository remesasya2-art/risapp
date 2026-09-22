"""
tests/test_nucleo_salud.py — los secretos por nombre (nunca el valor), los
registros en JSON, las métricas y la salud que avisa cuando cambia.
"""
import asyncio
import io
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from _nucleo_comun import cuenta_aprobada                                     # noqa: E402
from conftest import usar_base                                                # noqa: E402
from nucleo import base, comandos, modo, plan, trabajador                     # noqa: E402
from nucleo.esquema import asientos, trabajos                                 # noqa: E402
from nucleo.operacion import bitacora, registros, salud, secretos             # noqa: E402

T0 = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia(monkeypatch):
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())
    m = mongomock_motor.AsyncMongoMockClient()["nucleo_salud"]
    usar_base(m)
    ya(m.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    salud.reiniciar_para_tests()
    monkeypatch.setattr(trabajador, "_estado", {"nombre": "t", "corriendo": True, "vueltas": 1, "ultima_vuelta": None,
                                                 "ultimo_error": None, "ultimo_modo": "laboratorio"})

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())
    yield m


def comprobacion(r, nombre):
    return next(c for c in r["comprobaciones"] if c["nombre"] == nombre)


# ─── secretos ─────────────────────────────────────────────────────────────

def test_LOS_SECRETOS_SE_LEEN_POR_NOMBRE_Y_NUNCA_SE_MUESTRAN(monkeypatch):
    monkeypatch.setenv("NUCLEO_SECRETO_CREDENCIAL_STA", "usuario:clave-secretisima")
    puerto = secretos.secretos()
    assert puerto.leer("credencial_sta") == "usuario:clave-secretisima"
    assert puerto.leer("credencial_dict") is None
    with pytest.raises(KeyError):
        puerto.leer("lo_que_sea")
    filas = {f["nombre"]: f for f in ya(secretos.estado(modo.LABORATORIO))}
    sta = filas["credencial_sta"]
    assert sta["configurado"] is True and len(sta["huella"]) == 12 and "secretisima" not in json.dumps(filas)
    assert sta["huella"] != "usuario:clave-secretisima" and sta["obligatorio"] is False
    assert filas["base_de_datos"]["obligatorio"] is True and filas["base_de_datos"]["variable"] == "NUCLEO_DATABASE_URL"


def test_en_activo_todos_los_obligatorios_y_en_laboratorio_solo_la_base(monkeypatch):
    monkeypatch.delenv("NUCLEO_DATABASE_URL", raising=False)
    monkeypatch.setattr(base, "_url_en_uso", None)
    assert secretos.faltantes(modo.LABORATORIO) == ["base_de_datos"]
    assert "certificado_spi" in secretos.faltantes(modo.ACTIVO) and "llave_de_respaldo" not in secretos.faltantes(modo.ACTIVO)
    monkeypatch.setenv("NUCLEO_DATABASE_URL", "postgresql+asyncpg://x")
    assert secretos.faltantes(modo.LABORATORIO) == []


def test_UNA_ROTACION_QUEDA_EN_LA_BITACORA_SIN_EL_VALOR(monkeypatch):
    monkeypatch.setenv("NUCLEO_SECRETO_CREDENCIAL_SIscoaf".upper(), "primera")
    ya(secretos.estado(modo.LABORATORIO))
    monkeypatch.setenv("NUCLEO_SECRETO_CREDENCIAL_SISCOAF", "segunda")
    filas = {f["nombre"]: f for f in ya(secretos.estado(modo.LABORATORIO))}
    assert filas["credencial_siscoaf"]["rotado"] is True
    ya(secretos.estado(modo.LABORATORIO))                                  # sin cambio: sin renglón nuevo
    vistos = [b for b in ya(bitacora.listar()) if b["objetivo"] == "credencial_siscoaf"]
    assert [b["detalle"] for b in vistos] == ["rotado", "configurado"]
    assert vistos[0]["antes"] == {"huella": secretos.huella("primera")} and vistos[0]["despues"] == {"huella": secretos.huella("segunda")}
    assert "primera" not in json.dumps(vistos) and "segunda" not in json.dumps(vistos)


# ─── registros ────────────────────────────────────────────────────────────

def test_LOS_REGISTROS_DEL_NUCLEO_SALEN_EN_JSON_Y_UNA_SOLA_VEZ():
    salida = io.StringIO()
    raiz = registros.instalar(salida)
    registros.instalar(salida)                                             # idempotente
    assert sum(1 for m in raiz.handlers if getattr(m, "name", None) == registros.NOMBRE_DEL_MANEJADOR) == 1
    assert raiz.propagate is False
    logging.getLogger("nucleo.cola").info("trabajo %s terminado", 7, extra={"quien": "cola", "trabajo": 7, "duracion_ms": 12})
    linea = json.loads(salida.getvalue().strip().splitlines()[-1])
    assert linea["mensaje"] == "trabajo 7 terminado" and linea["nivel"] == "INFO" and linea["quien_escribe"] == "nucleo.cola"
    assert linea["trabajo"] == 7 and linea["duracion_ms"] == 12 and linea["momento"].endswith("+00:00")


def test_un_error_lleva_su_traza():
    salida = io.StringIO()
    registros.instalar(salida)
    try:
        raise RuntimeError("se rompió")
    except RuntimeError:
        logging.getLogger("nucleo.x").exception("falló")
    linea = json.loads(salida.getvalue().strip().splitlines()[-1])
    assert linea["nivel"] == "ERROR" and "RuntimeError: se rompió" in linea["error"]


# ─── métricas ─────────────────────────────────────────────────────────────

def test_LAS_METRICAS_SALEN_DE_LA_BASE_Y_EN_TEXTO_PARA_EL_RECOLECTOR():
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t"))
    ya(comandos.debitar(cuenta_id=c, monto="30.00", referencia="out-1", actor="t"))
    m = ya(registros.resumen())
    assert m["cuentas_activas"] == 1 and m["asientos_total"] == 2 and m["asientos_hoy"] == 2
    assert m["saldo_de_titulares_centavos"] == 7000 and m["trabajos_muertos"] == 0 and m["aprobaciones_pendientes"] == 0
    texto = registros.en_texto(m)
    assert "nucleo_saldo_de_titulares_centavos 7000\n" in texto and "nucleo_cuentas_activas 1\n" in texto
    assert all(l.startswith("nucleo_") or l.startswith("#") for l in texto.strip().splitlines())


# ─── salud ────────────────────────────────────────────────────────────────

def test_SANO_CUANDO_TODO_PASA(monkeypatch):
    trabajador._estado["ultima_vuelta"] = T0.isoformat()
    r = ya(salud.revisar(ahora=T0 + timedelta(minutes=1), modo_vigente=modo.LABORATORIO))
    assert r["ok"] is True, r
    assert {c["nombre"] for c in r["comprobaciones"]} == {"base", "esquema", "cola", "libro", "bitacora", "trabajador", "plazos", "secretos"}
    assert {c["nombre"] for c in r["comprobaciones"] if c["grave"]} == {"base", "libro", "bitacora"}


def test_el_trabajador_sin_latir_no_es_sano():
    trabajador._estado["ultima_vuelta"] = T0.isoformat()
    r = ya(salud.revisar(ahora=T0 + timedelta(minutes=6), modo_vigente=modo.LABORATORIO))
    assert r["ok"] is False and comprobacion(r, "trabajador")["ok"] is False and "sin latir" in comprobacion(r, "trabajador")["detalle"]
    trabajador._estado["corriendo"] = False
    assert "no está corriendo" in comprobacion(ya(salud.revisar(ahora=T0, modo_vigente=modo.LABORATORIO)), "trabajador")["detalle"]


def test_un_trabajo_muerto_no_es_sano():
    trabajador._estado["ultima_vuelta"] = T0.isoformat()

    async def matar_uno():
        from nucleo import cola
        async with base.sesion() as s:
            # Con `ahora=T0`. Sin él, el trabajo se encolaba con el reloj REAL y
            # las vueltas van con el reloj del test (T0 = 21/09/2026 15:00):
            # cada vuelta anterior a la hora real no lo tomaba. El test pasó
            # hasta el 22/09/2026 a las 15:00 UTC y empezó a fallar solo.
            t = await cola.encolar(s, tipo="fallar", clave="x", carga={}, ahora=T0)
        for _ in range(cola.INTENTOS_MAXIMOS + 1):
            await trabajador.una_vuelta(ahora=T0 + timedelta(days=_))
    ya(matar_uno())
    r = ya(salud.revisar(ahora=T0, modo_vigente=modo.LABORATORIO))
    assert comprobacion(r, "cola")["ok"] is False and "1 trabajos muertos" in comprobacion(r, "cola")["detalle"]


def test_UN_LIBRO_ALTERADO_ES_GRAVE():
    trabajador._estado["ultima_vuelta"] = T0.isoformat()
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t"))

    async def tocar():
        async with base.sesion() as s:
            await s.execute(asientos.update().where(asientos.c.numero == 1).values(descripcion="otra cosa"))
    ya(tocar())
    r = ya(salud.revisar(ahora=T0, modo_vigente=modo.LABORATORIO))
    libro_ = comprobacion(r, "libro")
    assert r["ok"] is False and libro_["ok"] is False and libro_["grave"] is True and "alterado" in libro_["detalle"]


def test_faltan_secretos_en_activo(monkeypatch):
    trabajador._estado["ultima_vuelta"] = T0.isoformat()
    monkeypatch.delenv("NUCLEO_SECRETO_CERTIFICADO_SPI", raising=False)
    r = ya(salud.revisar(ahora=T0, modo_vigente=modo.ACTIVO))
    assert comprobacion(r, "secretos")["ok"] is False and "certificado_spi" in comprobacion(r, "secretos")["detalle"]


def test_una_obligacion_vencida_no_es_sano():
    from datetime import date
    trabajador._estado["ultima_vuelta"] = datetime.now(timezone.utc).isoformat()
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t", fecha=date(2025, 3, 3)))   # un balancete de 2025 sin generar
    r = ya(salud.revisar(modo_vigente=modo.LABORATORIO))
    assert comprobacion(r, "plazos")["ok"] is False


def test_sin_base_la_salud_lo_dice_sin_caerse(monkeypatch):
    monkeypatch.delenv("NUCLEO_DATABASE_URL", raising=False)
    monkeypatch.setattr(base, "_motor", None)
    monkeypatch.setattr(base, "_url_en_uso", None)
    r = ya(salud.revisar(ahora=T0, modo_vigente=modo.LABORATORIO))
    assert r["ok"] is False and r["comprobaciones"][0]["nombre"] == "base" and "sin base" in r["comprobaciones"][0]["detalle"]


def test_VIGILAR_AVISA_UNA_VEZ_POR_CAMBIO_Y_LO_ANOTA(monkeypatch):
    avisos = []

    async def avisador(titulo, mensaje, grave):
        avisos.append((titulo, grave))
    monkeypatch.setattr(salud, "AVISADORES", [avisador])
    trabajador._estado["ultima_vuelta"] = T0.isoformat()
    assert ya(salud.vigilar(ahora=T0))["ok"] is True
    assert avisos == []                                                    # la primera revisión no avisa: no hay cambio
    assert ya(salud.vigilar(ahora=T0 + timedelta(seconds=30))) is None    # todavía no pasaron cinco minutos
    trabajador._estado["corriendo"] = False
    r = ya(salud.vigilar(ahora=T0 + timedelta(minutes=6)))
    assert r["ok"] is False and avisos == [("El núcleo NO está sano", False)]
    ya(salud.vigilar(ahora=T0 + timedelta(minutes=12)))                    # sigue mal: no se repite
    assert len(avisos) == 1
    trabajador._estado["corriendo"] = True
    trabajador._estado["ultima_vuelta"] = (T0 + timedelta(minutes=18)).isoformat()
    ya(salud.vigilar(ahora=T0 + timedelta(minutes=18)))
    assert avisos[-1] == ("El núcleo volvió a estar sano", False) and len(avisos) == 2
    cambios = [b for b in ya(bitacora.listar()) if b["accion"] == "salud.cambio"]
    assert [b["despues"]["ok"] for b in cambios] == [True, False] and cambios[1]["despues"]["fallas"] == ["trabajador"]
    assert salud.estado()["ultimo_ok"] is True


def test_un_avisador_que_falla_no_frena_a_los_demas(monkeypatch):
    llegaron = []

    async def roto(t, m, g):
        raise RuntimeError("sin red")

    async def sano(t, m, g):
        llegaron.append(t)
    monkeypatch.setattr(salud, "AVISADORES", [roto, sano])
    ya(salud.avisar("x", "y", False))
    assert llegaron == ["x"]


def test_el_latido_del_trabajador_llama_a_la_vigilancia(base_limpia, monkeypatch):
    llamadas = []

    async def falsa(ahora=None, forzar=False):
        llamadas.append(1)
    monkeypatch.setattr(salud, "vigilar", falsa)
    ya(trabajador.latir(base_limpia))
    assert llamadas == [1]


def test_la_sonda_anonima_y_los_avisadores_estan_en_server():
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[1].joinpath("server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/health/nucleo"' in fuente and "_nucleo_salud.AVISADORES.append(_avisar_salud_del_nucleo)" in fuente
    assert "solo_super_admin=True" in fuente


def test_la_sonda_no_calcula_nada_devuelve_lo_ultimo_que_vio_la_vigilancia(monkeypatch):
    trabajador._estado["ultima_vuelta"] = datetime.now(timezone.utc).isoformat()
    assert ya(salud.ok_para_la_sonda()) is True                          # sin vigilancia previa: revisa una vez
    trabajador._estado["corriendo"] = False
    assert ya(salud.ok_para_la_sonda()) is True                          # y después no recalcula: devuelve lo visto
    ya(salud.vigilar(forzar=True))
    assert ya(salud.ok_para_la_sonda()) is False


def test_LA_SONDA_ANONIMA_CONTESTA_404_APAGADA_Y_SOLO_OK_PRENDIDA(monkeypatch):
    try:
        from fastapi.testclient import TestClient
        import server
    except Exception as e:                                        # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    m = mongomock_motor.AsyncMongoMockClient()["nucleo_sonda"]
    monkeypatch.setattr(server, "db", m)
    with TestClient(server.app) as cliente:
        assert cliente.get("/api/health/nucleo").status_code == 404
        ya(m.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
        r = cliente.get("/api/health/nucleo")
        assert r.status_code in (200, 503) and set(r.json()) == {"ok"}   # nada más que el ok: es anónima
        assert r.status_code == (200 if r.json()["ok"] else 503)
