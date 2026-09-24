"""
tests/test_nucleo_operacion.py — la bitácora encadenada y el cuatro ojos
general (pedir, decidir, ejecutar) con su guarda sobre la configuración.
"""
import asyncio
import inspect
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
from nucleo.cumplimiento import incidentes                                    # noqa: E402
from nucleo.esquema import bitacora as tabla_bitacora                         # noqa: E402
from nucleo.operacion import aprobaciones, bitacora                           # noqa: E402
from nucleo.reportes import registro                                          # noqa: E402
from services import configuracion                                            # noqa: E402

T0 = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia():
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())


@pytest.fixture
def mongo():
    m = mongomock_motor.AsyncMongoMockClient()["nucleo_operacion"]
    usar_base(m)
    return m


def anotar(**kw):
    async def _():
        async with base.sesion() as s:
            return await bitacora.anotar(s, **kw)
    return ya(_())


def cadena():
    async def _():
        async with base.sesion() as s:
            return await bitacora.verificar_cadena(s)
    return ya(_())


# ─── la bitácora ──────────────────────────────────────────────────────────

def test_LA_BITACORA_SE_ENCADENA_Y_DETECTA_UN_RENGLON_TOCADO():
    anotar(actor="ana", accion="cierre.dia", objetivo="2026-09-21", despues={"hasta_asiento": 3}, ahora=T0)
    anotar(actor="beto", accion="reporte.generado", objetivo="balancete 2026-09", ahora=T0 + timedelta(minutes=1))
    assert cadena()["ok"] is True and cadena()["renglones"] == 2
    filas = ya(bitacora.listar())
    assert [f["actor"] for f in filas] == ["beto", "ana"] and filas[1]["despues"] == {"hasta_asiento": 3}

    async def tocar():
        async with base.sesion() as s:
            await s.execute(tabla_bitacora.update().where(tabla_bitacora.c.actor == "ana").values(actor="carla"))
    ya(tocar())
    roto = cadena()
    assert roto["ok"] is False and roto["roto_en"] == 1 and "alterado" in roto["motivo"]


def test_UN_RENGLON_BORRADO_DEL_MEDIO_ROMPE_LA_CADENA():
    """Cada renglón sigue siendo válido consigo mismo; lo que delata el
    borrado es que el hash previo del siguiente ya no apunta a nadie."""
    for i in range(3):
        anotar(actor="ana", accion="x", objetivo=str(i), ahora=T0 + timedelta(minutes=i))

    async def borrar_el_segundo():
        async with base.sesion() as s:
            await s.execute(tabla_bitacora.delete().where(tabla_bitacora.c.id == 2))
    ya(borrar_el_segundo())
    roto = cadena()
    assert roto["ok"] is False and roto["roto_en"] == 3 and "hash previo" in roto["motivo"]


def test_el_hash_incluye_todo_lo_que_importa():
    h = bitacora.hash_de(T0, "ana", "x", "y", None, None, None, "0" * 64)
    assert h != bitacora.hash_de(T0, "beto", "x", "y", None, None, None, "0" * 64)
    assert h != bitacora.hash_de(T0, "ana", "x", "y", '{"a": 1}', None, None, "0" * 64)
    assert h != bitacora.hash_de(T0, "ana", "x", "y", None, None, "nota", "0" * 64)
    assert h != bitacora.hash_de(T0, "ana", "x", "y", None, None, None, "1" * 64)
    # Con y sin zona horaria da lo mismo: SQLite devuelve los momentos sin zona.
    assert h == bitacora.hash_de(T0.replace(tzinfo=None), "ana", "x", "y", None, None, None, "0" * 64)


def test_anotar_sin_romper_no_lanza_aunque_no_haya_base():
    base.usar("sqlite+aiosqlite://")                     # base vacía, sin tablas
    assert ya(bitacora.anotar_sin_romper(actor="ana", accion="x", objetivo="y")) is None


def test_no_hay_funcion_que_borre_ni_edite_la_bitacora():
    nombres = [n for n, _ in inspect.getmembers(bitacora, inspect.isfunction)]
    assert not [n for n in nombres if n.startswith(("borrar", "eliminar", "editar", "modificar"))]
    fuente = inspect.getsource(bitacora)
    assert "bitacora.update(" not in fuente and "bitacora.delete(" not in fuente


# ─── el cuatro ojos ───────────────────────────────────────────────────────

def test_QUIEN_PIDE_NO_APRUEBA_Y_APROBAR_EJECUTA(mongo):
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    p = ya(aprobaciones.pedir(accion="configurar", objetivo="nucleo_umbral_operacion",
                              carga={"clave": "nucleo_umbral_operacion", "valor": "20000"}, actor="ana", motivo="Sube el ticket promedio", ahora=T0))
    assert p["estado"] == "pendiente" and p["vence_en"] == (T0 + timedelta(hours=72)).isoformat()
    # CADA decisión lleva su hora, y no sólo la que se aprueba. Sin `ahora`,
    # `decidir` usa el reloj de verdad contra un pedido fechado en T0: pasaba
    # mientras el reloj estuviera dentro de las 72 horas de T0, y el 24 de
    # septiembre de 2026 a las 15:00 el pedido «venció» y el test se rompió
    # solo, sin que nadie tocara el código.
    with pytest.raises(aprobaciones.AprobacionInvalida, match="quien pidió"):
        ya(aprobaciones.decidir(p["id"], actor="ana", aprobar=True, ahora=T0 + timedelta(minutes=30)))
    d = ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True, nota="De acuerdo", ahora=T0 + timedelta(hours=1)))
    assert d["estado"] == "ejecutado" and d["decidido_por"] == "jefa" and "→ 20000" in d["resultado"]
    assert str(ya(configuracion.leer(mongo, "nucleo_umbral_operacion"))) == "20000.00"
    with pytest.raises(aprobaciones.AprobacionInvalida, match="ya está ejecutado"):
        ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True, ahora=T0 + timedelta(hours=2)))
    acciones = [f["accion"] for f in ya(bitacora.listar())]
    assert acciones == ["aprobacion.ejecutado", "config.cambio", "aprobacion.aprobada", "aprobacion.pedida"]
    assert cadena()["ok"] is True


def test_rechazar_no_ejecuta_y_pedir_dos_veces_devuelve_el_mismo(mongo):
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    p = ya(aprobaciones.pedir(accion="configurar", objetivo="nucleo_modo", carga={"clave": "nucleo_modo", "valor": "0"}, actor="ana", motivo="Apagar", ahora=T0))
    assert ya(aprobaciones.pedir(accion="configurar", objetivo="nucleo_modo", carga={"clave": "nucleo_modo", "valor": "2"}, actor="beto", motivo="Otro", ahora=T0))["id"] == p["id"]
    d = ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=False, nota="Todavía no", ahora=T0 + timedelta(hours=1)))
    assert d["estado"] == "rechazado" and d["nota"] == "Todavía no"
    assert ya(modo.leer(mongo)) == modo.LABORATORIO
    assert ya(aprobaciones.resumen(ahora=T0 + timedelta(hours=1)))["rechazado"] == 1


def test_UN_PEDIDO_VENCE_A_LAS_72_HORAS(mongo):
    p = ya(aprobaciones.pedir(accion="configurar", objetivo="nucleo_modo", carga={"clave": "nucleo_modo", "valor": "0"}, actor="ana", motivo="Apagar", ahora=T0))
    assert ya(aprobaciones.listar(ahora=T0 + timedelta(hours=73)))[0]["estado"] == "vencido"
    with pytest.raises(aprobaciones.AprobacionInvalida, match="venció"):
        ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True, ahora=T0 + timedelta(hours=73)))
    assert ya(aprobaciones.detalle(p["id"]))["estado"] == "vencido"


def test_un_pedido_sin_motivo_o_de_una_accion_desconocida_no_nace():
    with pytest.raises(aprobaciones.AprobacionInvalida, match="motivo"):
        ya(aprobaciones.pedir(accion="configurar", objetivo="x", carga={}, actor="ana", motivo="  "))
    with pytest.raises(aprobaciones.AprobacionInvalida, match="No hay cuatro ojos"):
        ya(aprobaciones.pedir(accion="borrar_todo", objetivo="x", carga={}, actor="ana", motivo="porque sí"))


def test_SI_LA_EJECUCION_FALLA_EL_PEDIDO_QUEDA_FALLIDO_Y_SE_VUELVE_A_PEDIR(mongo):
    p = ya(aprobaciones.pedir(accion="transmitir_reporte", objetivo="reporte:999", carga={"reporte_id": 999}, actor="ana", motivo="Mandar", ahora=T0))
    with pytest.raises(aprobaciones.AprobacionInvalida, match="la ejecución falló"):
        ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True, ahora=T0))
    d = ya(aprobaciones.detalle(p["id"]))
    assert d["estado"] == "fallido" and "No existe el reporte 999" in d["resultado"]
    otro = ya(aprobaciones.pedir(accion="transmitir_reporte", objetivo="reporte:999", carga={"reporte_id": 999}, actor="ana", motivo="Otra vez", ahora=T0))
    assert otro["id"] != p["id"]


def test_transmitir_un_reporte_y_comunicar_un_incidente_pasan_por_el_cuatro_ojos(mongo):
    from datetime import date
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t", fecha=date(2026, 9, 3)))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    r = ya(registro.generar("balancete", "2026-09", actor="ana"))
    p = ya(aprobaciones.pedir(accion="transmitir_reporte", objetivo=f"reporte:{r['id']}", carga={"reporte_id": r["id"]}, actor="ana", motivo="Balancete de septiembre"))
    d = ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True))
    assert d["estado"] == "ejecutado" and d["resultado"].startswith("protocolo STA-SIM-")
    assert ya(registro.detalle(r["id"]))["transmitido_por"] == "jefa"
    i = ya(incidentes.abrir(tipo="fraude", titulo="x", impacto="x", clientes_afectados=1, relevante=True, actor="ops"))
    p = ya(aprobaciones.pedir(accion="comunicar_incidente", objetivo=f"incidente:{i['id']}", carga={"incidente_id": i["id"]}, actor="ops", motivo="Relevante"))
    d = ya(aprobaciones.decidir(p["id"], actor="jefa", aprobar=True))
    assert d["estado"] == "ejecutado" and ya(incidentes.detalle(i["id"]))["comunicado_por"] == "jefa"


# ─── la guarda de configuración ───────────────────────────────────────────

def test_LA_GUARDA_FRENA_LA_CONFIGURACION_DEL_NUCLEO_PRENDIDO_Y_NADA_MAS(mongo):
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    with pytest.raises(configuracion.CambioNoPermitido, match="cuatro ojos"):
        ya(aprobaciones.guarda_de_configuracion(mongo, {"nucleo_umbral_operacion": 1}))
    with pytest.raises(configuracion.CambioNoPermitido, match="nucleo_modo"):
        ya(aprobaciones.guarda_de_configuracion(mongo, {"nucleo_modo": 0, "bono_de_bienvenida": 1}))
    ya(aprobaciones.guarda_de_configuracion(mongo, {"bono_de_bienvenida": 1}))          # no es del núcleo: pasa


def test_con_el_nucleo_apagado_la_configuracion_se_cambia_directo(mongo):
    ya(aprobaciones.guarda_de_configuracion(mongo, {"nucleo_modo": 1, "nucleo_umbral_operacion": 5}))   # prenderlo no exige a nadie más


def test_la_guarda_esta_enganchada_desde_server_y_la_lista_se_consulta():
    import pathlib
    fuente = pathlib.Path(__file__).resolve().parents[1].joinpath("server.py").read_text(encoding="utf-8")
    assert "_configuracion.GUARDAS.append(_nucleo_aprobaciones.guarda_de_configuracion)" in fuente
    ruta = pathlib.Path(__file__).resolve().parents[1].joinpath("routes", "configuracion.py").read_text(encoding="utf-8")
    assert "comprobar_guardas(db, cambios)" in ruta


def test_la_guarda_por_http_contesta_400_con_el_motivo(mongo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.user import User
    from routes import dependencies as deps
    from routes.configuracion import router
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    configuracion.GUARDAS.append(aprobaciones.guarda_de_configuracion)
    try:
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[deps.get_super_admin] = lambda: User(user_id="u_jefa", name="J", email="j@ejemplo.test", role="super_admin")
        cliente = TestClient(app)
        r = cliente.put("/api/admin/configuracion", json={"valores": {"nucleo_umbral_operacion": "20000"}})
        assert r.status_code == 400 and "cuatro ojos" in r.json()["detail"]
        assert str(ya(configuracion.leer(mongo, "nucleo_umbral_operacion"))) == "10000.00"   # no se escribió
        r = cliente.put("/api/admin/configuracion", json={"valores": {"nucleo_modo": "0"}})
        assert r.status_code == 400
        assert ya(modo.leer(mongo)) == modo.LABORATORIO
    finally:
        configuracion.GUARDAS.remove(aprobaciones.guarda_de_configuracion)


# ─── el trabajador anota el cambio del interruptor ────────────────────────

def test_el_trabajador_anota_en_la_bitacora_cuando_ve_cambiar_el_interruptor(mongo):
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": "1"}))
    ya(trabajador.latir(mongo))
    ya(mongo.config.update_one({"clave": modo.CLAVE}, {"$set": {"valor": "0"}}))
    ya(trabajador.latir(mongo))
    ya(trabajador.latir(mongo))                                             # sin cambio: sin renglón nuevo
    cambios = [f for f in ya(bitacora.listar()) if f["accion"] == "modo.cambio"]
    assert len(cambios) == 1 and cambios[0]["antes"] == {"modo": "laboratorio"} and cambios[0]["despues"] == {"modo": "apagado"}
