"""
tests/test_nucleo_riesgo.py — el monitoreo, los casos y la comunicación al
COAF.

    Cada regla de monitoreo con su caso de prueba; el expediente con sus
    plazos y sus cuatro ojos; la comunicación con su archivo y su acuse; la
    no ocurrencia que sólo se declara cuando de verdad no hubo nada.
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

from _nucleo_comun import cuenta_aprobada, titular_aprobado                   # noqa: E402
from conftest import usar_base                                                # noqa: E402
from nucleo import base, comandos, plan, trabajador                           # noqa: E402
from nucleo.esquema import operaciones                                        # noqa: E402
from nucleo.identidad import legajos, simulador as id_sim                     # noqa: E402
from nucleo.rieles import operaciones as op, simulador as riel_sim            # noqa: E402
from nucleo.riesgo import casos, coaf, monitoreo                              # noqa: E402

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
    m = mongomock_motor.AsyncMongoMockClient()["nucleo_riesgo"]
    usar_base(m)
    return m


def cobrar_y_pagar(c, monto):
    """Un cobro pagado por Ana, liquidado por la cola. Devuelve el id de la operación."""
    cobro = ya(op.crear_cobro(cuenta_id=c, monto=monto, actor="t"))

    async def pagar():
        async with base.sesion() as s:
            await riel_sim.Simulador().simular_pago_del_cobro(s, txid=cobro["txid"], monto=comandos.a_centavos(monto),
                                                              pagador_clave="ana@ejemplo.test")
    ya(pagar()); ya(trabajador.una_vuelta())
    return cobro["id"]


def pagar_a(c, clave, monto):
    import secrets
    p = ya(op.ordenar_pago(cuenta_id=c, clave=clave, monto=monto, referencia=f"p-{clave}-{monto}-{secrets.token_hex(3)}", actor="t"))
    ya(trabajador.una_vuelta())
    return p["id"]


def alertas_de(operacion_id):
    return [a for a in ya(monitoreo.listar()) if a["operacion"] == operacion_id]


# ─── los umbrales ─────────────────────────────────────────────────────────

def test_sin_configuracion_rigen_los_de_fabrica():
    u = ya(monitoreo.umbrales(object()))          # una «base» que no contesta
    assert u == {"umbral_operacion": 1000000, "umbral_30_dias": 5000000, "umbral_12_meses": 30000000,
                 "fraccionamiento_horas": 24, "velocidad_por_hora": 10}


def test_LOS_UMBRALES_SE_CAMBIAN_DESDE_LA_CONFIGURACION(mongo):
    ya(mongo.config.insert_one({"clave": "nucleo_umbral_operacion", "valor": "500.00"}))
    ya(mongo.config.insert_one({"clave": "nucleo_velocidad_por_hora", "valor": "2"}))
    u = ya(monitoreo.umbrales(mongo))
    assert u["umbral_operacion"] == 50000 and u["velocidad_por_hora"] == 2 and u["umbral_30_dias"] == 5000000


# ─── las reglas ───────────────────────────────────────────────────────────

def test_UNA_OPERACION_SOBRE_EL_UMBRAL_DEJA_ALERTA_Y_ABRE_UN_CASO(mongo):
    c = cuenta_aprobada("u_ana")
    o = cobrar_y_pagar(c, "12000.00")
    reglas = {a["regla"] for a in alertas_de(o)}
    assert "umbral_operacion" in reglas
    (caso,) = ya(casos.listar())
    assert caso["estado"] == "abierto" and caso["origen"] == "alerta"
    assert alertas_de(o)[0]["caso"] == caso["id"]
    assert caso["analizar_hasta"] > caso["abierto_en"]


def test_una_operacion_chica_no_deja_alerta(mongo):
    c = cuenta_aprobada("u_ana")
    o = cobrar_y_pagar(c, "100.00")
    # «horario» depende de la hora real a la que corra el test; las demás, no
    assert [a["regla"] for a in alertas_de(o) if a["regla"] != "horario"] == []


def test_EVALUAR_DOS_VECES_NO_DUPLICA(mongo):
    c = cuenta_aprobada("u_ana")
    o = cobrar_y_pagar(c, "12000.00")
    n = len(alertas_de(o))
    assert ya(monitoreo.evaluar_operacion(o, db=mongo)) == []
    assert len(alertas_de(o)) == n and len(ya(casos.listar())) == 1


def test_EL_FRACCIONAMIENTO_SE_VE_EN_LA_TERCERA(mongo):
    c = cuenta_aprobada("u_ana")
    o1 = cobrar_y_pagar(c, "4000.00")
    o2 = cobrar_y_pagar(c, "4000.00")
    assert not any(a["regla"] == "fraccionamiento" for a in alertas_de(o1) + alertas_de(o2))
    o3 = cobrar_y_pagar(c, "4000.00")
    (a,) = [a for a in alertas_de(o3) if a["regla"] == "fraccionamiento"]
    assert a["detalle"]["operaciones"] == 3 and a["detalle"]["suma"] == 1200000


def test_el_acumulado_de_30_dias_y_de_12_meses(mongo):
    ya(mongo.config.insert_one({"clave": "nucleo_umbral_30_dias", "valor": "9000.00"}))
    ya(mongo.config.insert_one({"clave": "nucleo_umbral_12_meses", "valor": "13000.00"}))
    ya(mongo.config.insert_one({"clave": "nucleo_umbral_operacion", "valor": "100000.00"}))
    c = cuenta_aprobada("u_ana")
    cobrar_y_pagar(c, "5000.00")
    o2 = cobrar_y_pagar(c, "5000.00")
    reglas = {a["regla"] for a in ya(monitoreo.evaluar_operacion(o2, db=mongo))} | {a["regla"] for a in alertas_de(o2)}
    assert "acumulado_30_dias" in reglas and "acumulado_12_meses" not in reglas
    o3 = cobrar_y_pagar(c, "5000.00")
    ya(monitoreo.evaluar_operacion(o3, db=mongo))
    assert "acumulado_12_meses" in {a["regla"] for a in alertas_de(o3)}


def test_la_velocidad_y_la_contraparte_repetida(mongo):
    ya(mongo.config.insert_one({"clave": "nucleo_velocidad_por_hora", "valor": "3"}))
    ya(mongo.config.insert_one({"clave": "nucleo_umbral_operacion", "valor": "100000.00"}))
    c = cuenta_aprobada("u_ana")
    cobrar_y_pagar(c, "200.00")
    ultimo = None
    for i in range(5):
        ultimo = pagar_a(c, "ana@ejemplo.test", "10.00")
    ya(monitoreo.evaluar_operacion(ultimo, db=mongo))
    reglas = {a["regla"] for a in alertas_de(ultimo)}
    assert "velocidad" in reglas and "contraparte_repetida" in reglas


def test_el_horario_inusual_se_mide_en_hora_de_brasil(mongo):
    c = cuenta_aprobada("u_ana")
    o = cobrar_y_pagar(c, "50.00")

    async def madrugada():
        from nucleo.esquema import alertas
        async with base.sesion() as s:
            await s.execute(operaciones.update().where(operaciones.c.id == o)
                            .values(actualizada=datetime(2026, 9, 21, 6, 30, tzinfo=timezone.utc)))   # 03:30 en Brasil
            # La cola ya evaluó la operación con la hora REAL al liquidarla. Si
            # el test corre entre las 0 y las 5 de Brasilia, esa evaluación ya
            # dejó la alerta de horario (con la hora real) y la de acá no sería
            # «nueva». Se borra la de la cola para que el test mida lo suyo: el
            # producto no tiene función que borre alertas, y así tiene que seguir.
            await s.execute(alertas.delete().where(alertas.c.operacion == o))
    ya(madrugada())
    nuevas = ya(monitoreo.evaluar_operacion(o, db=mongo))
    assert any(a["regla"] == "horario" and a["detalle"]["hora"] == 3 for a in nuevas)


# ─── los casos ────────────────────────────────────────────────────────────

def test_UN_CASO_ABIERTO_POR_TITULAR_Y_LAS_ALERTAS_SE_ANEXAN():
    t = titular_aprobado("u_ana")
    a = ya(casos.abrir(titular=t, origen="manual", actor="jefa", detalle="denuncia"))
    b = ya(casos.abrir(titular=t, origen="alerta", actor="monitoreo", detalle="umbral"))
    assert a["id"] == b["id"] and len(b["notas"]) == 2
    with pytest.raises(casos.CasoInvalido):
        ya(casos.abrir(titular=t, origen="rumor", actor="x"))


def test_LOS_PLAZOS_DE_LA_CIRCULAR():
    t = titular_aprobado("u_ana")
    c = ya(casos.abrir(titular=t, origen="manual", actor="jefa", ahora=T0))
    # El «no vencido» se pregunta en T0. Lo que devuelve `abrir` calcula el
    # vencimiento con el reloj de verdad, y el plazo es el 5 de noviembre de
    # 2026: desde el 6 este test se rompía solo.
    assert c["analizar_hasta"].startswith("2026-11-05")
    assert ya(casos.detalle(c["id"], ahora=T0))["analisis_vencido"] is False
    assert ya(casos.detalle(c["id"], ahora=T0 + timedelta(days=46)))["analisis_vencido"] is True
    ya(casos.tomar(c["id"], analista="ana"))
    d = ya(casos.concluir(c["id"], analista="ana", conclusion="indicios de fraccionamiento", comunicar=True, ahora=T0))
    assert d["estado"] == "concluido" and d["comunicar_hasta"].startswith("2026-09-22T15:00")
    assert ya(casos.detalle(c["id"], ahora=T0 + timedelta(hours=25)))["comunicacion_vencida"] is True
    assert ya(casos.resumen(ahora=T0 + timedelta(hours=25)))["vencidos"] == 1


def test_CUATRO_OJOS_PARA_COMUNICAR():
    t = titular_aprobado("u_ana")
    c = ya(casos.abrir(titular=t, origen="manual", actor="jefa"))
    with pytest.raises(casos.CasoInvalido, match="tomarlo"):
        ya(casos.concluir(c["id"], analista="ana", conclusion="x", comunicar=True))
    ya(casos.tomar(c["id"], analista="ana"))
    ya(casos.concluir(c["id"], analista="ana", conclusion="indicios claros", comunicar=True))
    with pytest.raises(casos.CasoInvalido, match="Cuatro ojos"):
        ya(casos.aprobar_comunicacion(c["id"], aprobador="ana"))
    d = ya(casos.aprobar_comunicacion(c["id"], aprobador="jefa"))
    assert d["estado"] == "comunicado" and d["acuse"].startswith("SISCOAF-SIM-") and d["aprobado_por"] == "jefa"
    (com,) = ya(casos.listar_comunicaciones())
    assert com["tipo"] == "comunicacion" and com["acuse"] == d["acuse"] and '"indicios"' in com["archivo"]
    with pytest.raises(casos.CasoInvalido):
        ya(casos.aprobar_comunicacion(c["id"], aprobador="otro"))      # ya comunicado


def test_sin_comunicar_queda_archivado_con_su_conclusion():
    t = titular_aprobado("u_ana")
    c = ya(casos.abrir(titular=t, origen="manual", actor="jefa"))
    ya(casos.tomar(c["id"], analista="ana"))
    d = ya(casos.concluir(c["id"], analista="ana", conclusion="operación explicada por la renta", comunicar=False))
    assert d["estado"] == "archivado" and d["archivado_en"] and d["comunicar"] is False
    with pytest.raises(casos.CasoInvalido):
        ya(casos.anotar(c["id"], autor="x", texto="tarde"))


def test_el_archivo_de_la_comunicacion_cita_los_indicios_y_las_operaciones(mongo):
    c = cuenta_aprobada("u_ana")
    o = cobrar_y_pagar(c, "12000.00")
    (caso,) = ya(casos.listar())
    ya(casos.tomar(caso["id"], analista="ana"))
    ya(casos.concluir(caso["id"], analista="ana", conclusion="valor incompatible con la renta", comunicar=True))
    d = ya(casos.aprobar_comunicacion(caso["id"], aprobador="jefa"))
    import json
    archivo = json.loads(ya(casos.listar_comunicaciones())[0]["archivo"])
    assert archivo["tipo"] == "comunicacion" and archivo["caso"] == caso["id"]
    assert any(i["codigo"] == coaf.INDICIOS["umbral_operacion"][0] for i in archivo["indicios"])
    assert archivo["operacoes"][0]["id"] == o and archivo["operacoes"][0]["valor"] == "12000.00"
    assert archivo["envolvidos"][0]["documento"] and archivo["descripcion"] == "valor incompatible con la renta"


def test_LA_NO_OCURRENCIA_SOLO_SI_NO_HUBO_NADA():
    with pytest.raises(casos.CasoInvalido, match="Cuatro ojos"):
        ya(casos.declarar_no_ocurrencia(anio=2025, actor="ana", aprobador="ana"))
    d = ya(casos.declarar_no_ocurrencia(anio=2025, actor="ana", aprobador="jefa"))
    assert d["tipo"] == "no_ocurrencia" and d["periodo"] == 2025 and d["acuse"].startswith("SISCOAF-SIM-")
    assert ya(casos.declarar_no_ocurrencia(anio=2025, actor="ana", aprobador="jefa"))["id"] == d["id"]
    t = titular_aprobado("u_ana")
    c = ya(casos.abrir(titular=t, origen="manual", actor="jefa"))
    ya(casos.tomar(c["id"], analista="ana"))
    ya(casos.concluir(c["id"], analista="ana", conclusion="x", comunicar=True))
    ya(casos.aprobar_comunicacion(c["id"], aprobador="jefa", ahora=datetime(2026, 3, 1, tzinfo=timezone.utc)))
    with pytest.raises(casos.CasoInvalido, match="sí hubo"):
        ya(casos.declarar_no_ocurrencia(anio=2026, actor="ana", aprobador="jefa"))


def test_UN_CRUCE_DE_SANCIONES_CONFIRMADO_ABRE_UN_CASO():
    cpf, nombre = next((c, n) for c, n, _x, comp in id_sim.PERSONAS_DE_PRUEBA if comp == "sancionado")
    t = ya(legajos.crear_titular(documento=cpf, nombre=nombre, actor="t"))
    ya(legajos.verificar(t["id"], actor="t"))
    (cr,) = ya(legajos.cruzar(t["id"], actor="t"))
    ya(legajos.resolver_cruce(cr["id"], resolucion="confirmado: es la persona listada", actor="jefa"))
    (caso,) = ya(casos.listar())
    assert caso["origen"] == "lista" and caso["titular"] == t["id"]


def test_no_hay_funcion_que_borre_casos_ni_alertas():
    for mod in (casos, monitoreo):
        nombres = [n for n in dir(mod) if not n.startswith("_")]
        for prohibido in ("borrar", "eliminar", "delete", "purgar"):
            assert not any(prohibido in n.lower() for n in nombres), (mod.__name__, nombres)
