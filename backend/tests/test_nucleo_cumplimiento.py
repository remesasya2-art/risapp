"""
tests/test_nucleo_cumplimiento.py — incidentes, ouvidoria, días hábiles y
el calendario de obligaciones.

    Lo que más importa: un incidente relevante lleva plazo y se comunica
    una sola vez; el cierre se escribe una vez; el reclamo tiene diez días
    HABILES; los informes salen sólo de períodos terminados; el calendario
    dice pendiente, generado o transmitido sin que nadie lo guarde.
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

from _nucleo_comun import cuenta_aprobada, titular_aprobado                   # noqa: E402
from conftest import usar_base                                                # noqa: E402
from nucleo import base, comandos, plan                                       # noqa: E402
from nucleo.cumplimiento import calendario, dias_habiles, incidentes, ouvidoria   # noqa: E402
from nucleo.reportes import ReporteInvalido, registro                         # noqa: E402
from nucleo.riesgo import casos                                               # noqa: E402
from nucleo.riesgo.monitoreo import HORA_DE_BRASIL                            # noqa: E402

T0 = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
HOY = datetime.now(HORA_DE_BRASIL).date()


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia():
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())
    usar_base(mongomock_motor.AsyncMongoMockClient()["nucleo_cumplimiento"])

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())


# ─── días hábiles ─────────────────────────────────────────────────────────

def test_LOS_DIAS_HABILES_SALTAN_FINES_DE_SEMANA_Y_FERIADOS():
    assert dias_habiles.pascua(2026) == date(2026, 4, 5)
    assert date(2026, 2, 17) in dias_habiles.feriados(2026)          # martes de Carnaval
    assert date(2026, 4, 3) in dias_habiles.feriados(2026)           # Viernes Santo
    assert date(2026, 6, 4) in dias_habiles.feriados(2026)           # Corpus Christi
    assert not dias_habiles.es_habil(date(2026, 9, 7))               # Independencia
    assert not dias_habiles.es_habil(date(2026, 9, 19))              # sábado
    assert dias_habiles.siguiente_habil(date(2026, 9, 4)) == date(2026, 9, 8)    # viernes → salta finde y feriado
    # Diez hábiles desde el jueves 17/9/2026: 18, 21, 22, 23, 24, 25, 28, 29, 30, 1/10.
    assert dias_habiles.sumar_habiles(date(2026, 9, 17), 10) == date(2026, 10, 1)
    assert dias_habiles.ultimo_habil_del_mes(2026, 8) == date(2026, 8, 31)
    assert dias_habiles.ultimo_habil_del_mes(2027, 2) == date(2027, 2, 26)      # el 28 es domingo


# ─── incidentes ───────────────────────────────────────────────────────────

def test_UN_INCIDENTE_RELEVANTE_LLEVA_PLAZO_Y_SE_COMUNICA_UNA_VEZ():
    i = ya(incidentes.abrir(tipo="indisponibilidad", titulo="El PIX no liquidó", impacto="Pagos frenados",
                            clientes_afectados=40, relevante=True, actor="ops", ahora=T0))
    assert i["estado"] == "abierto" and i["comunicar_hasta"] == (T0 + timedelta(hours=24)).isoformat()
    assert i["comunicacion_vencida"] is False and i["notas"][0]["texto"].startswith("Incidente registrado · RELEVANTE")
    assert ya(incidentes.detalle(i["id"], ahora=T0 + timedelta(hours=25)))["comunicacion_vencida"] is True
    c = ya(incidentes.comunicar(i["id"], actor="jefa", ahora=T0 + timedelta(hours=2)))
    assert c["protocolo"].startswith("STA-SIM-") and c["comunicado_por"] == "jefa" and c["comunicacion_vencida"] is False
    with pytest.raises(incidentes.IncidenteInvalido, match="ya se comunicó"):
        ya(incidentes.comunicar(i["id"], actor="jefa"))
    assert ya(incidentes.resumen())["relevantes_sin_comunicar"] == 0


def test_un_incidente_no_relevante_no_lleva_plazo_ni_se_comunica():
    i = ya(incidentes.abrir(tipo="otro", titulo="Un botón torcido", impacto="Estético", clientes_afectados=0,
                            relevante=False, actor="ops", ahora=T0))
    assert i["comunicar_hasta"] is None
    with pytest.raises(incidentes.IncidenteInvalido, match="no relevante"):
        ya(incidentes.comunicar(i["id"], actor="jefa"))


def test_EL_CIERRE_SE_ESCRIBE_UNA_VEZ_Y_LO_DEMAS_SON_NOTAS():
    i = ya(incidentes.abrir(tipo="fraude", titulo="Cuenta tomada", impacto="Un titular", clientes_afectados=1,
                            relevante=True, actor="ops", ahora=T0))
    with pytest.raises(incidentes.IncidenteInvalido, match="causa"):
        ya(incidentes.cerrar(i["id"], actor="ops", causa="", acciones="bloqueo"))
    with pytest.raises(incidentes.IncidenteInvalido, match="anterior al inicio"):
        ya(incidentes.cerrar(i["id"], actor="ops", causa="phishing", acciones="bloqueo", fin=T0 - timedelta(hours=1)))
    c = ya(incidentes.cerrar(i["id"], actor="ops", causa="phishing", acciones="bloqueo y aviso", fin=T0 + timedelta(hours=3), ahora=T0 + timedelta(hours=4)))
    assert c["estado"] == "cerrado" and c["causa"] == "phishing" and c["fin"] == (T0 + timedelta(hours=3)).isoformat()
    with pytest.raises(incidentes.IncidenteInvalido, match="ya está cerrado"):
        ya(incidentes.cerrar(i["id"], actor="ops", causa="otra", acciones="otra"))
    n = ya(incidentes.anotar(i["id"], autor="ops", texto="La causa fue además una contraseña repetida."))
    assert [x["texto"] for x in n["notas"]][-2:] == ["Cerrado. Causa: phishing", "La causa fue además una contraseña repetida."]
    assert ya(incidentes.detalle(i["id"]))["causa"] == "phishing"           # la nota no editó el cierre


def test_un_incidente_no_empieza_en_el_futuro_ni_con_clientes_negativos():
    with pytest.raises(incidentes.IncidenteInvalido, match="futuro"):
        ya(incidentes.abrir(tipo="otro", titulo="x", impacto="x", clientes_afectados=0, relevante=False, actor="ops",
                            inicio=T0 + timedelta(days=1), ahora=T0))
    with pytest.raises(incidentes.IncidenteInvalido, match="negativos"):
        ya(incidentes.abrir(tipo="otro", titulo="x", impacto="x", clientes_afectados=-1, relevante=False, actor="ops", ahora=T0))


def test_EL_INFORME_ANUAL_DE_INCIDENTES_SOLO_DE_UN_ANIO_TERMINADO():
    inicio = datetime(2025, 3, 1, 10, 0, tzinfo=timezone.utc)
    i = ya(incidentes.abrir(tipo="indisponibilidad", titulo="Caída", impacto="x", clientes_afectados=120, relevante=True,
                            actor="ops", inicio=inicio, ahora=inicio))
    ya(incidentes.comunicar(i["id"], actor="jefa", ahora=inicio))
    ya(incidentes.cerrar(i["id"], actor="ops", causa="disco", acciones="cambio", fin=inicio + timedelta(hours=2, minutes=30), ahora=inicio + timedelta(hours=3)))
    ya(incidentes.abrir(tipo="otro", titulo="Del año siguiente", impacto="x", clientes_afectados=0, relevante=False, actor="ops", ahora=T0))
    with pytest.raises(ReporteInvalido, match="terminó"):
        ya(registro.generar("incidentes", str(HOY.year), actor="t"))
    r = ya(registro.generar("incidentes", "2025", actor="t"))
    archivo = json.loads(r["archivo"])
    assert r["documento"] == "Informe anual de incidentes" and r["resumen"] == {"total": 1, "relevantes": 1, "comunicados": 1}
    assert archivo["por_tipo"] == {"indisponibilidad": 1} and archivo["horas_de_indisponibilidade"] == 2.5
    assert archivo["clientes_afetados"] == 120 and archivo["incidentes"][0]["protocolo"].startswith("STA-SIM-")


# ─── ouvidoria ────────────────────────────────────────────────────────────

def test_UN_RECLAMO_TIENE_PROTOCOLO_Y_DIEZ_DIAS_HABILES():
    jueves = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    r = ya(ouvidoria.abrir(canal="bcb", asunto="Cobro no reconocido", descripcion="Detalle", actor="ouv",
                           caso_soporte="S-000123", ahora=jueves))
    assert r["protocolo"] == "OUV-2026-000001" and r["responder_hasta"] == "2026-10-01" and r["caso_soporte"] == "S-000123"
    r2 = ya(ouvidoria.abrir(canal="telefono", asunto="Otro", descripcion="Detalle", actor="ouv", ahora=jueves))
    assert r2["protocolo"] == "OUV-2026-000002"
    # «No vencido» se pregunta con fecha fija, como el «vencido» de abajo.
    # `detalle` usa el día de hoy, y el plazo vence el 1 de octubre de 2026:
    # desde el 2 de octubre este test se rompía solo, sin que nadie tocara
    # el código.
    (recien,) = [x for x in ya(ouvidoria.listar(hoy=date(2026, 9, 18))) if x["id"] == r["id"]]
    assert recien["vencido"] is False
    assert [x["vencido"] for x in ya(ouvidoria.listar(hoy=date(2026, 10, 2)))] == [True, True]
    assert ya(ouvidoria.resumen(hoy=date(2026, 10, 2)))["vencidos"] == 2


def test_LA_RESPUESTA_ES_UNA_Y_DICE_SI_LLEGO_EN_PLAZO():
    jueves = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    r = ya(ouvidoria.abrir(canal="correo", asunto="x", descripcion="x", actor="ouv", ahora=jueves))
    with pytest.raises(ouvidoria.ReclamoInvalido, match="Resultado desconocido"):
        ya(ouvidoria.responder(r["id"], actor="ouv", respuesta="Listo", resultado="raro"))
    a_tiempo = ya(ouvidoria.responder(r["id"], actor="ouv", respuesta="Se devolvió el cobro.", resultado="procedente",
                                      ahora=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)))
    assert a_tiempo["estado"] == "respondido" and a_tiempo["en_plazo"] is True and a_tiempo["vencido"] is False
    with pytest.raises(ouvidoria.ReclamoInvalido, match="ya fue respondido"):
        ya(ouvidoria.responder(r["id"], actor="ouv", respuesta="Otra", resultado="improcedente"))
    tarde = ya(ouvidoria.abrir(canal="correo", asunto="y", descripcion="y", actor="ouv", ahora=jueves))
    tarde = ya(ouvidoria.responder(tarde["id"], actor="ouv", respuesta="Tarde", resultado="parcial",
                                   ahora=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)))
    assert tarde["en_plazo"] is False


def test_EL_INFORME_SEMESTRAL_DE_LA_OUVIDORIA():
    abril = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)                      # 1º semestre
    r = ya(ouvidoria.abrir(canal="procon", asunto="x", descripcion="x", actor="ouv", ahora=abril))
    ya(ouvidoria.responder(r["id"], actor="ouv", respuesta="ok", resultado="procedente", ahora=abril + timedelta(days=3)))
    ya(ouvidoria.abrir(canal="panel", asunto="y", descripcion="y", actor="ouv", ahora=abril))
    ya(ouvidoria.abrir(canal="panel", asunto="z", descripcion="z", actor="ouv", ahora=T0))   # 2º semestre: no entra
    with pytest.raises(ReporteInvalido, match="terminó"):
        ya(registro.generar("ouvidoria", "2026-S2", actor="t"))
    archivo = json.loads(ya(registro.generar("ouvidoria", "2026-S1", actor="t"))["archivo"])
    assert archivo["total"] == 2 and archivo["por_canal"] == {"procon": 1, "panel": 1}
    assert archivo["respondidos"] == 1 and archivo["respondidos_no_prazo"] == 1 and archivo["abertos_ao_fim"] == 1
    assert archivo["dias_medios_de_resposta"] == 3.0 and archivo["prazo_em_dias_uteis"] == 10


# ─── el calendario ────────────────────────────────────────────────────────

def _por(obl, tipo, periodo):
    return next(o for o in obl if o["obligacion"] == tipo and o["periodo"] == periodo)


def test_EL_CALENDARIO_DICE_PENDIENTE_GENERADO_Y_TRANSMITIDO_SIN_GUARDAR_NADA():
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t", fecha=date(2026, 7, 3)))
    hoy = date(2026, 9, 21)
    obl = ya(calendario.obligaciones(hoy))
    julio = _por(obl, "balancete", "2026-07")
    assert julio["estado"] == "pendiente" and julio["vence"] == "2026-08-30" and julio["vencido"] is True
    agosto = _por(obl, "balancete", "2026-08")
    assert agosto["estado"] == "pendiente" and agosto["vence"] == "2026-09-30" and agosto["dias"] == 9 and agosto["vencido"] is False
    assert not [o for o in obl if o["obligacion"] == "balancete" and o["periodo"] == "2026-09"]      # el mes no terminó
    assert not [o for o in obl if o["obligacion"] == "efinanceira"]                                   # el semestre tampoco
    ya(comandos.cerrar_dia(dia=date(2026, 8, 31), actor="t"))
    r = ya(registro.generar("balancete", "2026-07", actor="t"))
    assert _por(ya(calendario.obligaciones(hoy)), "balancete", "2026-07")["estado"] == "generado"
    ya(registro.transmitir(r["id"], actor="t"))
    julio = _por(ya(calendario.obligaciones(hoy)), "balancete", "2026-07")
    assert julio["estado"] == "transmitido" and julio["protocolo"].startswith("STA-SIM-") and julio["reporte"] == r["id"]
    assert ya(calendario.resumen(hoy))["pendientes"] == 1                       # queda agosto


def test_el_calendario_de_un_anio_terminado_pide_los_informes_y_la_no_ocurrencia():
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t", fecha=date(2025, 11, 3)))
    hoy = date(2026, 2, 10)
    obl = ya(calendario.obligaciones(hoy))
    assert _por(obl, "incidentes", "2025")["vence"] == "2026-03-31"
    assert _por(obl, "ouvidoria", "2025-S2")["vence"] == "2026-01-30"
    assert _por(obl, "efinanceira", "2025-S2")["vence"] == "2026-02-27"          # último hábil de febrero
    no = _por(obl, "no_ocurrencia", "2025")
    assert no["estado"] == "pendiente" and no["vence"] == "2026-01-15"           # diez hábiles: 1/1 es feriado
    ya(casos.declarar_no_ocurrencia(anio=2025, actor="ana", aprobador="jefa"))
    no = _por(ya(calendario.obligaciones(hoy)), "no_ocurrencia", "2025")
    assert no["estado"] == "transmitido" and no["detalle"].startswith("acuse SISCOAF-SIM-")


def test_si_un_anio_tuvo_comunicaciones_al_coaf_la_no_ocurrencia_no_corresponde():
    from nucleo.esquema import comunicaciones
    c = cuenta_aprobada("u_ana")
    ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="in-1", actor="t", fecha=date(2025, 5, 3)))

    async def una_comunicacion_de_2025():
        async with base.sesion() as s:
            await s.execute(comunicaciones.insert().values(
                caso="caso_x", tipo="comunicacion", archivo="{}", acuse="SISCOAF-SIM-X", enviada_en=datetime(2025, 8, 1, tzinfo=timezone.utc),
                enviada_por="ana", aprobada_por="jefa", comunicador="simulador-siscoaf"))
    ya(una_comunicacion_de_2025())
    no = _por(ya(calendario.obligaciones(date(2026, 2, 10))), "no_ocurrencia", "2025")
    assert no["estado"] == "no_corresponde" and no["vencido"] is False


def test_LOS_VENCIMIENTOS_DEL_CALENDARIO():
    assert calendario.vence("ccs", "2026-09-04") == date(2026, 9, 8)          # viernes → salta el finde y el 7 de septiembre
    assert calendario.vence("ccs", "2026-09-22") == date(2026, 9, 23)
    assert calendario.vence("balancete", "2026-07") == date(2026, 8, 30)
    assert calendario.vence("efinanceira", "2026-S1") == date(2026, 8, 31)
    assert calendario.vence("efinanceira", "2026-S2") == date(2027, 2, 26)
    assert calendario.vence("no_ocurrencia", "2025") == date(2026, 1, 15)
    assert calendario.vence("incidentes", "2025") == date(2026, 3, 31)
    assert calendario.vence("ouvidoria", "2025-S2") == date(2026, 1, 30)


def test_el_calendario_lista_el_ccs_de_los_dias_con_altas_y_las_acciones_con_plazo():
    cuenta_aprobada("u_ana")                                                     # alta de hoy
    obl = ya(calendario.obligaciones(HOY + timedelta(days=1)))
    hoy_ccs = _por(obl, "ccs", HOY.isoformat())
    assert hoy_ccs["estado"] == "pendiente" and hoy_ccs["detalle"] == "1 altas/bajas"
    assert date.fromisoformat(hoy_ccs["vence"]) == dias_habiles.siguiente_habil(HOY)
    i = ya(incidentes.abrir(tipo="ciberataque", titulo="Intento", impacto="x", clientes_afectados=0, relevante=True, actor="ops", ahora=T0))
    r = ya(ouvidoria.abrir(canal="bcb", asunto="Queja", descripcion="x", actor="ouv", ahora=T0))
    acc = ya(calendario.acciones_con_plazo(date(2026, 9, 21)))
    assert [(a["accion"], a["referencia"]) for a in acc] == [("comunicar_incidente", i["id"]), ("responder_reclamo", r["id"])]
    ya(incidentes.comunicar(i["id"], actor="jefa"))
    ya(ouvidoria.responder(r["id"], actor="ouv", respuesta="ok", resultado="improcedente"))
    assert ya(calendario.acciones_con_plazo(date(2026, 9, 21))) == []


def test_cada_plazo_del_calendario_tiene_su_fuente():
    for tipo, (periodicidad, plazo, fuente) in calendario.PLAZOS.items():
        assert periodicidad in ("diaria", "mensual", "semestral", "anual") and fuente and plazo, tipo


# ─── lo que no existe ─────────────────────────────────────────────────────

def test_no_hay_funcion_que_borre_ni_edite_incidentes_ni_reclamos():
    for modulo in (incidentes, ouvidoria):
        nombres = [n for n, _ in inspect.getmembers(modulo, inspect.isfunction)]
        assert not [n for n in nombres if n.startswith(("borrar", "eliminar", "editar", "modificar"))], modulo.__name__
        assert ".delete(" not in inspect.getsource(modulo), modulo.__name__
    assert inspect.getsource(incidentes).count("incidentes.update(") == 2       # comunicar y cerrar, nada más
    assert inspect.getsource(ouvidoria).count("reclamos.update(") == 1          # responder, nada más
