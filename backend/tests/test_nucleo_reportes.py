"""
tests/test_nucleo_reportes.py — el balancete COSIF, el CCS, la e-Financeira
y el registro que los guarda, versiona y transmite.

    Lo que más importa acá: nada se genera sobre un período que todavía se
    puede asentar, nada se manda vacío, nada se transmite dos veces, y una
    corrección es una versión nueva y no una edición.
"""
import asyncio
import inspect
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from _nucleo_comun import cuenta_aprobada                                     # noqa: E402
from conftest import usar_base                                                # noqa: E402
from nucleo import base, comandos, plan, trabajador                           # noqa: E402
from nucleo.esquema import cuentas, reportes as tabla_reportes                # noqa: E402
from nucleo.reportes import ReporteInvalido, periodos, registro, sta          # noqa: E402
from nucleo.reportes.periodos import PeriodoInvalido                          # noqa: E402
from nucleo.riesgo.monitoreo import HORA_DE_BRASIL                            # noqa: E402

HOY = datetime.now(HORA_DE_BRASIL).date()
FIN_DE_MES = periodos.limites(periodos.MES, periodos.mes_de(HOY))[1]


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia():
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())
    usar_base(mongomock_motor.AsyncMongoMockClient()["nucleo_reportes"])

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())


def acreditar(c, monto, fecha, ref):
    return ya(comandos.acreditar(cuenta_id=c, monto=monto, referencia=ref, actor="t", fecha=fecha))


# ─── el plan ──────────────────────────────────────────────────────────────

def test_TODAS_LAS_CUENTAS_DEL_PLAN_TIENEN_CODIGO_COSIF():
    """Una cuenta sin código COSIF es plata que se cae del balancete."""
    for codigo, *_ in plan.CUENTAS:
        assert plan.cosif_de(codigo)
    assert set(plan.COSIF) == {c for c, *_ in plan.CUENTAS}


# ─── los períodos ─────────────────────────────────────────────────────────

def test_los_periodos_se_leen_y_se_rechazan():
    assert periodos.limites(periodos.MES, "2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert periodos.limites(periodos.SEMESTRE, "2026-S2") == (date(2026, 7, 1), date(2026, 12, 31))
    assert periodos.limites(periodos.ANIO, "2026") == (date(2026, 1, 1), date(2026, 12, 31))
    assert periodos.meses_entre(date(2026, 11, 3), date(2027, 1, 9)) == ["2026-11", "2026-12", "2027-01"]
    assert periodos.semestres_entre(date(2026, 5, 1), date(2026, 8, 1)) == ["2026-S1", "2026-S2"]
    for clase, malo in ((periodos.MES, "2026-13"), (periodos.MES, "2026-09-01"), (periodos.DIA, "2026-02-30"),
                        (periodos.SEMESTRE, "2026-S3"), (periodos.ANIO, "26")):
        with pytest.raises(PeriodoInvalido):
            periodos.limites(clase, malo)


# ─── el balancete ─────────────────────────────────────────────────────────

def test_EL_BALANCETE_SOLO_SOBRE_UN_MES_CERRADO():
    c = cuenta_aprobada("u_ana")
    acreditar(c, "100.00", date(2026, 9, 3), "in-1")
    with pytest.raises(ReporteInvalido, match="cerrado"):
        ya(registro.generar("balancete", "2026-09", actor="t"))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 29), actor="t"))
    with pytest.raises(ReporteInvalido, match="2026-09-30"):
        ya(registro.generar("balancete", "2026-09", actor="t"))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    r = ya(registro.generar("balancete", "2026-09", actor="t"))
    assert r["version"] == 1 and r["estado"] == "generado" and r["documento"] == "CADOC 4010"


def test_el_balancete_cuadra_contra_el_libro_y_suma_por_codigo_cosif():
    a, b = cuenta_aprobada("u_ana"), cuenta_aprobada("u_beto")
    acreditar(a, "100.00", date(2026, 9, 3), "in-1")
    acreditar(b, "50.00", date(2026, 9, 4), "in-2")
    ya(comandos.cobrar_tarifa(cuenta_id=a, monto="1.50", referencia="tf-1", actor="t", fecha=date(2026, 9, 5)))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    archivo = json.loads(ya(registro.generar("balancete", "2026-09", actor="t"))["archivo"])
    assert archivo["cuadra"] is True and archivo["total_debe"] == archivo["total_haber"] == 15150
    assert archivo["tipo_remessa"] == "I" and archivo["data_base"] == "202609"
    assert archivo["plan"].startswith("provisorio")
    por_cosif = {c["cosif"]: c for c in archivo["contas"]}
    assert por_cosif[plan.cosif_de(plan.DE_TITULARES)]["saldo"] == 14850            # pasivo con los titulares
    assert por_cosif[plan.cosif_de(plan.DE_TITULARES)]["natureza"] == "C"
    assert por_cosif[plan.cosif_de(plan.LIQUIDACION)]["saldo"] == 15000            # activo: entró al banco
    assert por_cosif[plan.cosif_de(plan.TARIFAS)]["saldo"] == 150
    assert archivo["fechado_ate"]["dia"] == "2026-09-30"


def test_dos_cuentas_nuestras_con_el_mismo_codigo_cosif_se_suman(monkeypatch):
    """Hoy cada cuenta tiene su código; el día que el contador junte dos en
    uno, el balancete tiene que sumarlas y no quedarse con la última."""
    monkeypatch.setitem(plan.COSIF, plan.TARIFAS, plan.COSIF[plan.DE_TITULARES])
    a = cuenta_aprobada("u_ana")
    acreditar(a, "100.00", date(2026, 9, 3), "in-1")
    ya(comandos.cobrar_tarifa(cuenta_id=a, monto="1.50", referencia="tf-1", actor="t", fecha=date(2026, 9, 5)))
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    archivo = json.loads(ya(registro.generar("balancete", "2026-09", actor="t"))["archivo"])
    juntas = [c for c in archivo["contas"] if c["cosif"] == plan.COSIF[plan.DE_TITULARES]]
    assert len(juntas) == 1 and juntas[0]["saldo"] == 9850 + 150 == 10000
    assert sorted(x["codigo"] for x in juntas[0]["cuentas"]) == [plan.DE_TITULARES, plan.TARIFAS]


def test_UNA_SEGUNDA_GENERACION_ES_UNA_VERSION_NUEVA_Y_NO_PISA_NADA():
    c = cuenta_aprobada("u_ana")
    acreditar(c, "100.00", date(2026, 9, 3), "in-1")
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    primero = ya(registro.generar("balancete", "2026-09", actor="t"))
    segundo = ya(registro.generar("balancete", "2026-09", actor="t"))
    assert (primero["version"], segundo["version"]) == (1, 2)
    assert json.loads(segundo["archivo"])["tipo_remessa"] == "S"
    assert ya(registro.detalle(primero["id"]))["archivo"] == primero["archivo"]
    assert [r["version"] for r in ya(registro.listar())] == [2, 1]


def test_un_balancete_que_no_cuadra_no_se_genera():
    from sqlalchemy import insert
    from nucleo.esquema import partidas
    c = cuenta_aprobada("u_ana")
    n = acreditar(c, "100.00", date(2026, 9, 3), "in-1")
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))

    async def desbalancear():
        async with base.sesion() as s:                    # una partida suelta, como la dejaría un bug
            await s.execute(insert(partidas).values(asiento=n, orden=9, cuenta_contable=plan.PUENTE, debe=1, haber=0))
    ya(desbalancear())
    with pytest.raises(ReporteInvalido, match="no cuadra"):
        ya(registro.generar("balancete", "2026-09", actor="t"))


# ─── el CCS ───────────────────────────────────────────────────────────────

def test_EL_CCS_LISTA_LAS_ALTAS_Y_LAS_BAJAS_DEL_DIA_Y_NO_MANDA_UN_DIA_VACIO():
    a = cuenta_aprobada("u_ana")
    b = cuenta_aprobada("u_beto")
    ayer = (HOY - timedelta(days=1)).isoformat()
    with pytest.raises(ReporteInvalido, match="no hubo altas ni bajas"):
        ya(registro.generar("ccs", ayer, actor="t"))

    async def cerrar_b():
        async with base.sesion() as s:
            await s.execute(cuentas.update().where(cuentas.c.id == b).values(estado="cerrada", cerrada_en=datetime.now(timezone.utc)))
    ya(cerrar_b())
    r = ya(registro.generar("ccs", HOY.isoformat(), actor="t"))
    archivo = json.loads(r["archivo"])
    assert r["resumen"] == {"altas": 2, "bajas": 1}
    vinculos = {(v["conta"], v["operacao"]): v for v in archivo["vinculos"]}
    assert vinculos[(a, "inclusao")]["fim"] is None and vinculos[(a, "inclusao")]["inicio"] == HOY.isoformat()
    assert vinculos[(b, "exclusao")]["fim"] == HOY.isoformat()
    assert all(len(v["cpf_cnpj"]) == 11 for v in archivo["vinculos"])          # el CPF del legajo, no el id


# ─── la e-Financeira ──────────────────────────────────────────────────────

def test_LA_EFINANCEIRA_SOLO_LOS_MESES_SOBRE_EL_LIMITE_Y_CON_EL_SALDO_ACUMULADO():
    a, b = cuenta_aprobada("u_ana"), cuenta_aprobada("u_beto")
    acreditar(a, "500.00", date(2026, 6, 10), "in-0")            # semestre anterior: entra al saldo, no al informe
    acreditar(a, "2500.00", date(2026, 7, 10), "in-1")           # sobre el límite
    acreditar(a, "100.00", date(2026, 8, 10), "in-2")            # bajo el límite: no se informa
    ya(comandos.debitar(cuenta_id=a, monto="2100.00", referencia="out-1", actor="t", fecha=date(2026, 9, 10)))
    acreditar(b, "1999.99", date(2026, 7, 11), "in-3")           # un centavo bajo el límite
    with pytest.raises(ReporteInvalido, match="2026-12-31"):
        ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
        ya(registro.generar("efinanceira", "2026-S2", actor="t"))
    ya(comandos.cerrar_dia(dia=date(2026, 12, 31), actor="t"))
    archivo = json.loads(ya(registro.generar("efinanceira", "2026-S2", actor="t"))["archivo"])
    assert [d["conta"] for d in archivo["declarados"]] == [a]
    meses = archivo["declarados"][0]["meses"]
    assert [m["mes"] for m in meses] == ["2026-07", "2026-09"]
    assert meses[0] == {"mes": "2026-07", "creditos": 250000, "debitos": 0, "saldo_final": 300000}
    assert meses[1] == {"mes": "2026-09", "creditos": 0, "debitos": 210000, "saldo_final": 100000}


# ─── transmitir ───────────────────────────────────────────────────────────

def test_TRANSMITIR_DEJA_EL_PROTOCOLO_Y_NO_SE_TRANSMITE_DOS_VECES():
    c = cuenta_aprobada("u_ana")
    acreditar(c, "100.00", date(2026, 9, 3), "in-1")
    ya(comandos.cerrar_dia(dia=date(2026, 9, 30), actor="t"))
    r = ya(registro.generar("balancete", "2026-09", actor="t"))
    t = ya(registro.transmitir(r["id"], actor="jefa"))
    assert t["estado"] == "transmitido" and t["protocolo"].startswith("STA-SIM-") and t["transmisor"] == "simulador-sta"
    assert t["transmitido_por"] == "jefa" and t["archivo"] == r["archivo"]
    with pytest.raises(ReporteInvalido, match="ya se transmitió"):
        ya(registro.transmitir(r["id"], actor="jefa"))
    with pytest.raises(ReporteInvalido, match="No existe"):
        ya(registro.transmitir(999, actor="jefa"))
    assert ya(registro.resumen())["balancete"] == {"generados": 1, "transmitidos": 1}


def test_el_simulador_del_sta_rechaza_un_archivo_de_otro_documento():
    with pytest.raises(ValueError):
        ya(sta.SimuladorSta().transmitir(None, documento="CCS", periodo="2026-09-21", archivo=json.dumps({"documento": "CADOC 4010"})))
    with pytest.raises(ValueError):
        ya(sta.SimuladorSta().transmitir(None, documento="CCS", periodo="2026-09-21", archivo="{no es json"))


# ─── la cola ──────────────────────────────────────────────────────────────

def test_EL_CIERRE_DEL_DIA_GENERA_LO_QUE_QUEDO_COMPLETO_UNA_SOLA_VEZ():
    c = cuenta_aprobada("u_ana")
    acreditar(c, "100.00", HOY, "in-1")
    ya(comandos.cerrar_dia(dia=FIN_DE_MES, actor="t"))
    ya(trabajador.una_vuelta())
    hechos = {(r["tipo"], r["periodo"], r["version"]) for r in ya(registro.listar())}
    assert ("balancete", periodos.mes_de(HOY), 1) in hechos
    assert ("ccs", HOY.isoformat(), 1) in hechos
    assert all(r["generado_por"] == "cola" for r in ya(registro.listar()))
    # Otro cierre, otra vuelta: nada se genera dos veces.
    ya(comandos.cerrar_dia(dia=FIN_DE_MES + timedelta(days=1), actor="t"))
    ya(trabajador.una_vuelta())
    assert {(r["tipo"], r["periodo"], r["version"]) for r in ya(registro.listar())} == hechos


def test_sin_cerrar_el_dia_la_cola_no_genera_nada():
    c = cuenta_aprobada("u_ana")
    acreditar(c, "100.00", HOY, "in-1")
    assert ya(registro.generar_lo_pendiente(FIN_DE_MES)) == []


# ─── lo que no existe ─────────────────────────────────────────────────────

def test_no_hay_funcion_que_borre_ni_edite_reportes():
    nombres = [n for n, _ in inspect.getmembers(registro, inspect.isfunction)]
    assert not [n for n in nombres if n.startswith(("borrar", "eliminar", "editar", "modificar", "corregir"))]
    fuente = inspect.getsource(registro)
    assert fuente.count("reportes.delete(") == 0
    assert fuente.count("reportes.update(") == 1            # sólo la transmisión anota su protocolo
