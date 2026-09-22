"""
tests/test_nucleo_rutas.py — el laboratorio del núcleo por HTTP, como lo usa
la pestaña del panel.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from _nucleo_comun import cuenta_por_http                    # noqa: E402
from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from nucleo import base as nucleo_base, modo                  # noqa: E402

SUPER = User(user_id="u_jefa", name="La jefa", email="jefa@ejemplo.test", role="super_admin")


def ya(c):
    return asyncio.run(c)


@pytest.fixture
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nucleo.rutas import router
    from routes import dependencies as deps
    base = mongomock_motor.AsyncMongoMockClient()["nucleo_rutas"]
    usar_base(base)
    ya(base.config.insert_one({"clave": modo.CLAVE, "valor": str(modo.LABORATORIO)}))
    nucleo_base.usar("sqlite+aiosqlite://")
    ya(nucleo_base.crear_todo())
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_super_admin] = lambda: SUPER
    return TestClient(app)


def test_el_recorrido_del_laboratorio(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    b = cuenta_por_http(cliente, "u_beto")

    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "in-1"})
    assert r.status_code == 200 and r.json()["numero"] == 1
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "transferir", "desde": a, "hacia": b, "monto": "40.00", "referencia": "tr-1"})
    assert r.status_code == 200 and r.json()["numero"] == 2

    cuentas = {c["id"]: c["saldo"] for c in cliente.get("/api/nucleo/laboratorio/cuentas").json()}
    assert cuentas[a] == "60.00" and cuentas[b] == "40.00"

    libro = cliente.get("/api/nucleo/laboratorio/libro").json()
    assert [x["numero"] for x in libro] == [2, 1]
    assert libro[1]["partidas"][0]["debe"] == 10000

    assert cliente.get("/api/nucleo/laboratorio/balance").json()["cuadra"] is True
    assert cliente.get("/api/nucleo/laboratorio/cadena").json()["ok"] is True

    # El día de hoy según el núcleo (el que llevan los asientos), no uno
    # escrito a mano: el test se puso en rojo solo el día que el reloj pasó
    # la fecha que tenía escrita.
    from nucleo import comandos
    hoy = comandos._hoy().isoformat()
    r = cliente.post("/api/nucleo/laboratorio/cierres", json={"dia": hoy, "nota": "prueba"})
    assert r.status_code == 200 and r.json()["hasta_asiento"] == 2
    assert cliente.get("/api/nucleo/laboratorio/cierres").json()[0]["dia"] == hoy

    e = cliente.get("/api/nucleo/estado").json()
    assert e["cuentas"] == 2 and e["asientos"] == 2 and e["ultimo_cierre"] == hoy
    assert e["cadena"]["ok"] is True


def test_los_errores_del_libro_llegan_como_mensajes_claros(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "debitar", "cuenta": a, "monto": "5.00", "referencia": "d1"})
    assert r.status_code == 400 and "Saldo insuficiente" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "1.005", "referencia": "d2"})
    assert r.status_code == 400 and "dos decimales" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": "cta_nadie", "monto": "1.00", "referencia": "d3"})
    assert r.status_code == 400 and "inexistente" in r.json()["detail"]
    cliente.post("/api/nucleo/laboratorio/cierres", json={"dia": "2099-01-01"})
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "1.00", "referencia": "d4"})
    assert r.status_code == 409 and "cerrado" in r.json()["detail"]


def test_LA_MISMA_REFERENCIA_POR_HTTP_NO_DUPLICA(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    cuerpo = {"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "unica"}
    n1 = cliente.post("/api/nucleo/laboratorio/movimientos", json=cuerpo).json()["numero"]
    n2 = cliente.post("/api/nucleo/laboratorio/movimientos", json=cuerpo).json()["numero"]
    assert n1 == n2
    assert cliente.get("/api/nucleo/laboratorio/cuentas").json()[0]["saldo"] == "100.00"


def test_sin_base_configurada_el_laboratorio_dice_que_falta(cliente, monkeypatch):
    monkeypatch.setattr(nucleo_base, "_motor", None)
    monkeypatch.delenv(nucleo_base.VARIABLE, raising=False)
    r = cliente.get("/api/nucleo/laboratorio/cuentas")
    assert r.status_code == 503 and nucleo_base.VARIABLE in r.json()["detail"]
    e = cliente.get("/api/nucleo/estado").json()
    assert e["conectada"] is False and e["base"] == "sin configurar"


# ─── la cola por HTTP ─────────────────────────────────────────────────────

def test_la_cola_por_http_encola_procesa_y_revive(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    cliente.post("/api/nucleo/laboratorio/movimientos",
                 json={"tipo": "acreditar", "cuenta": a, "monto": "100.00", "referencia": "in-1"})
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "carga": {"mensaje": "hola"}})
    assert r.status_code == 200 and r.json()["nuevo"] is True, r.text
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "fallar", "clave": "f1"})
    assert r.status_code == 200
    muerto = r.json()["id"]

    r = cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert r.status_code == 200, r.text
    # el asiento dejó un evento, el evento se despachó como trabajo y corrió
    assert r.json() == {"despachados": 1, "corridos": 3, "hechos": 2, "muertos": 0, "reintentan": 1}

    q = cliente.get("/api/nucleo/laboratorio/cola").json()
    assert q["resumen"]["hecho"] == 2 and q["resumen"]["pendiente"] == 1
    assert q["resumen"]["eventos"] == 1 and q["resumen"]["eventos_sin_publicar"] == 0
    assert q["trabajador"]["nombre"]
    por_tipo = {t["tipo"]: t for t in q["trabajos"]}
    assert por_tipo["eco"]["resultado"] == "eco: hola"
    assert por_tipo["avisar_asiento"]["clave"] == "asiento_registrado:asiento:1"
    assert "a propósito" in por_tipo["fallar"]["ultimo_error"] or "Falla" in por_tipo["fallar"]["ultimo_error"]
    assert q["eventos"][0]["tipo"] == "asiento_registrado" and q["eventos"][0]["publicado"]

    # un pendiente no se reintenta a mano: sólo un muerto
    r = cliente.post(f"/api/nucleo/laboratorio/cola/trabajos/{muerto}/reintentar")
    assert r.status_code == 409

    e = cliente.get("/api/nucleo/estado").json()
    assert e["cola"]["pendiente"] == 1 and e["trabajador"]["nombre"]


def test_DESDE_LA_PESTANA_SOLO_SE_ENCOLAN_LOS_DE_LABORATORIO(cliente):
    """Un aviso real no se fabrica a mano desde un botón."""
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "avisar_asiento", "carga": {}})
    assert r.status_code == 422
    r = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "clave": "misma"})
    r2 = cliente.post("/api/nucleo/laboratorio/cola/trabajos", json={"tipo": "eco", "clave": "misma"})
    assert r.json()["nuevo"] is True and r2.json()["nuevo"] is False and r.json()["id"] == r2.json()["id"]


# ─── los rieles por HTTP ──────────────────────────────────────────────────

def test_los_rieles_por_http_cobran_pagan_y_devuelven(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    r = cliente.get("/api/nucleo/laboratorio/rieles")
    assert r.status_code == 200, r.text
    assert r.json()["riel"] == "simulador" and any(c["clave"] == "rechaza@ejemplo.test" for c in r.json()["claves_de_prueba"])

    r = cliente.post("/api/nucleo/laboratorio/rieles/cobros", json={"cuenta": a, "monto": "150.00", "descripcion": "prueba"})
    assert r.status_code == 200, r.text
    cobro = r.json()
    assert cobro["estado"] == "activa" and cobro["codigo_br"].startswith("000201")
    r = cliente.post(f"/api/nucleo/laboratorio/rieles/cobros/{cobro['id']}/simular_pago", json={"pagador_clave": "ana@ejemplo.test"})
    assert r.status_code == 200 and r.json()["nuevo"] is True
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert cliente.get("/api/nucleo/laboratorio/cuentas").json()[0]["saldo"] == "150.00"

    r = cliente.post("/api/nucleo/laboratorio/rieles/pagos", json={"cuenta": a, "clave": "rechaza@ejemplo.test", "monto": "30.00"})
    assert r.status_code == 200, r.text
    pago = r.json()
    assert pago["estado"] == "pendiente" and pago["contraparte"]["banco"] == "Banco Cerrado de Prueba"
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    d = cliente.get(f"/api/nucleo/laboratorio/rieles/operaciones/{pago['id']}").json()
    assert d["estado"] == "rechazada" and "AC06" in d["motivo"]
    assert [h["estado"] for h in d["historial"]] == ["pendiente", "enviada", "rechazada"]
    assert cliente.get("/api/nucleo/laboratorio/cuentas").json()[0]["saldo"] == "150.00"

    r = cliente.post("/api/nucleo/laboratorio/rieles/pagos", json={"cuenta": a, "clave": "tarda@ejemplo.test", "monto": "30.00"})
    tarda = r.json()
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert cliente.get(f"/api/nucleo/laboratorio/rieles/operaciones/{tarda['id']}").json()["estado"] == "enviada"
    r = cliente.post(f"/api/nucleo/laboratorio/rieles/pagos/{tarda['id']}/simular_resultado", json={"estado": "ACSC"})
    assert r.status_code == 200, r.text
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert cliente.get(f"/api/nucleo/laboratorio/rieles/operaciones/{tarda['id']}").json()["estado"] == "liquidada"

    r = cliente.post("/api/nucleo/laboratorio/rieles/devoluciones", json={"operacion": cobro["id"], "monto": "20.00", "motivo": "MD06"})
    assert r.status_code == 200, r.text
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    assert cliente.get("/api/nucleo/laboratorio/cuentas").json()[0]["saldo"] == "100.00"
    assert cliente.get("/api/nucleo/laboratorio/balance").json()["cuadra"] is True
    lista = cliente.get("/api/nucleo/laboratorio/rieles").json()
    assert lista["resumen"] == {"entrada_liquidada": 1, "salida_rechazada": 1, "salida_liquidada": 1, "devolucion_liquidada": 1}
    assert len(lista["avisos"]) == 4 and all(av["procesado"] for av in lista["avisos"])


def test_LOS_ERRORES_DE_LOS_RIELES_LLEGAN_COMO_MENSAJES_CLAROS(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    r = cliente.get("/api/nucleo/laboratorio/rieles/claves/ana@ejemplo.test")
    assert r.status_code == 200 and r.json()["documento"] == "***.456.789-**"
    assert cliente.get("/api/nucleo/laboratorio/rieles/claves/noexiste@ejemplo.test").status_code == 404
    r = cliente.get("/api/nucleo/laboratorio/rieles/claves/12345678900")
    assert r.status_code == 400 and "verificadores" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/rieles/pagos", json={"cuenta": a, "clave": "ana@ejemplo.test", "monto": "30.00"})
    assert r.status_code == 400 and "Saldo insuficiente" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/rieles/pagos", json={"cuenta": a, "clave": "noexiste@ejemplo.test", "monto": "30.00"})
    assert r.status_code == 404
    r = cliente.post("/api/nucleo/laboratorio/rieles/devoluciones", json={"operacion": "op_nada", "monto": "1.00", "motivo": "MD06"})
    assert r.status_code == 400
    r = cliente.post("/api/nucleo/laboratorio/rieles/devoluciones", json={"operacion": "op_nada", "monto": "1.00", "motivo": "ZZ00"})
    assert r.status_code == 422
    assert cliente.get("/api/nucleo/laboratorio/rieles/operaciones/op_nada").status_code == 404


# ─── la identidad por HTTP ────────────────────────────────────────────────

def test_la_identidad_por_http_recorre_el_legajo_y_abre_la_cuenta(cliente):
    r = cliente.get("/api/nucleo/laboratorio/identidad")
    assert r.status_code == 200, r.text
    assert r.json()["verificador"].startswith("simulador") and "salario" in r.json()["origenes_de_fondos"]
    pep = next(p for p in r.json()["personas_de_prueba"] if p["comportamiento"] == "pep")

    r = cliente.post("/api/nucleo/laboratorio/identidad/titulares",
                     json={"documento": pep["documento"], "nombre": pep["nombre"], "ocupacion": "funcionaria",
                           "renta_declarada": "12000.00", "origen_de_fondos": "salario"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["estado"] == "incompleto" and t["renta_declarada"] == "12000.00"
    # con el legajo incompleto no hay cuenta: 409, con el motivo
    r = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular": t["id"]})
    assert r.status_code == 409 and "incompleto" in r.json()["detail"]

    v = cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{t['id']}/verificar").json()
    assert v["aprobada"] is True
    c = cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{t['id']}/cruzar").json()
    assert len(c) == 1 and c[0]["lista"] == "PEP-CGU"
    d = cliente.get(f"/api/nucleo/laboratorio/identidad/titulares/{t['id']}").json()
    assert d["pep"] is True and d["estado"] == "en_revision"
    r = cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{t['id']}/aprobar", json={"nivel_de_riesgo": "bajo"})
    assert r.status_code == 400 and "riesgo alto" in r.json()["detail"]
    r = cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{t['id']}/aprobar", json={"nivel_de_riesgo": "alto"})
    assert r.status_code == 200 and r.json()["estado"] == "aprobado"
    r = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular": t["id"]})
    assert r.status_code == 200 and r.json()["titular_ref"] == t["id"]
    assert cliente.get("/api/nucleo/laboratorio/identidad?estado=aprobado").json()["titulares"][0]["id"] == t["id"]


def test_LOS_ERRORES_DE_LA_IDENTIDAD_LLEGAN_COMO_MENSAJES_CLAROS(cliente):
    r = cliente.post("/api/nucleo/laboratorio/identidad/titulares", json={"documento": "12345678900", "nombre": "X"})
    assert r.status_code == 400 and "CPF" in r.json()["detail"]
    assert cliente.get("/api/nucleo/laboratorio/identidad/titulares/tit_nadie").status_code == 404
    r = cliente.post("/api/nucleo/laboratorio/identidad/titulares/tit_nadie/aprobar", json={"nivel_de_riesgo": "raro"})
    assert r.status_code == 422
    r = cliente.post("/api/nucleo/laboratorio/identidad/cruces/999/resolver", json={"resolucion": "x"})
    assert r.status_code == 400
    assert cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular": "tit_nadie"}).status_code == 409


# ─── el riesgo por HTTP ───────────────────────────────────────────────────

def test_el_riesgo_por_http_del_umbral_al_acuse(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    cobro = cliente.post("/api/nucleo/laboratorio/rieles/cobros", json={"cuenta": a, "monto": "12000.00"}).json()
    cliente.post(f"/api/nucleo/laboratorio/rieles/cobros/{cobro['id']}/simular_pago", json={})
    cliente.post("/api/nucleo/laboratorio/cola/paso")
    r = cliente.get("/api/nucleo/laboratorio/riesgo")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["umbrales"]["umbral_operacion"] == 1000000 and d["comunicador"].startswith("simulador")
    assert any(al["regla"] == "umbral_operacion" for al in d["alertas"])
    (caso,) = [c for c in d["casos"] if c["origen"] == "alerta"]
    assert caso["estado"] == "abierto" and caso["alertas"]

    # tomar como ana, concluir a comunicar, y los cuatro ojos
    r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso['id']}/tomar", json={"como": "ana"})
    assert r.status_code == 200 and r.json()["analista"] == "ana"
    r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso['id']}/anotar", json={"texto": "renta no explica", "como": "ana"})
    assert r.status_code == 200 and len(r.json()["notas"]) >= 2
    r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso['id']}/concluir",
                     json={"conclusion": "valor incompatible", "comunicar": True, "como": "ana"})
    assert r.status_code == 200 and r.json()["estado"] == "concluido" and r.json()["comunicar_hasta"]
    r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso['id']}/aprobar_comunicacion", json={"como": "ana"})
    assert r.status_code == 400 and "Cuatro ojos" in r.json()["detail"]
    r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso['id']}/aprobar_comunicacion", json={"como": "jefa"})
    assert r.status_code == 200 and r.json()["estado"] == "comunicado" and r.json()["acuse"].startswith("SISCOAF-SIM-")
    d = cliente.get("/api/nucleo/laboratorio/riesgo").json()
    assert d["comunicaciones"][0]["acuse"] == r.json()["acuse"] and d["resumen_casos"]["comunicado"] == 1

    r = cliente.post("/api/nucleo/laboratorio/riesgo/no_ocurrencia", json={"anio": 2025, "como": "jefa"})
    assert r.status_code == 200 and r.json()["tipo"] == "no_ocurrencia"
    r = cliente.post("/api/nucleo/laboratorio/riesgo/no_ocurrencia", json={"anio": 2025})
    assert r.status_code == 400 and "Cuatro ojos" in r.json()["detail"]     # sin «como»: la misma persona


def test_EN_ACTIVO_NADIE_ACTUA_COMO_OTRO(cliente):
    """«como» es del laboratorio. En activo, quien actúa es quien está
    logueado, y por eso los cuatro ojos no se pueden fingir."""
    from routes import dependencies as deps
    t = cuenta_por_http(cliente, "u_ana")
    r = cliente.post("/api/nucleo/laboratorio/riesgo/casos", json={"titular": "tit_x", "detalle": "a mano"})
    assert r.status_code == 200
    caso = r.json()["id"]
    from nucleo import modo as _modo
    cliente.app.dependency_overrides[_modo.exigir_encendido] = lambda: _modo.ACTIVO
    try:
        r = cliente.post(f"/api/nucleo/laboratorio/riesgo/casos/{caso}/tomar", json={"como": "ana"})
        assert r.status_code == 200 and r.json()["analista"] == SUPER.user_id
    finally:
        cliente.app.dependency_overrides.pop(_modo.exigir_encendido, None)
    assert t


# ─── los reportes por HTTP ────────────────────────────────────────────────

def test_los_reportes_por_http_del_cierre_al_protocolo(cliente):
    a = cuenta_por_http(cliente, "u_ana")
    r = cliente.post("/api/nucleo/laboratorio/movimientos",
                     json={"tipo": "acreditar", "cuenta": a, "monto": "3000.00", "referencia": "in-1"})
    assert r.status_code == 200
    from datetime import datetime
    from nucleo.reportes import periodos
    from nucleo.riesgo.monitoreo import HORA_DE_BRASIL
    from nucleo import comandos
    hoy = datetime.now(HORA_DE_BRASIL).date()        # el CCS mide el día en hora de Brasil
    mes = periodos.mes_de(comandos._hoy())           # el balancete, el mes de la fecha que llevan los asientos

    r = cliente.get("/api/nucleo/laboratorio/reportes")
    assert r.status_code == 200
    assert r.json()["transmisor"] == "simulador-sta" and r.json()["tipos"] == ["balancete", "ccs", "efinanceira", "incidentes", "ouvidoria"]
    assert {c["codigo"] for c in r.json()["cosif"]} == {"1.1.01", "1.1.02", "1.1.03", "1.2.01", "2.1.01", "2.1.02",
                                                          "2.2.01", "3.1.01", "3.2.01", "4.1.01", "4.2.01", "5.1.01", "5.1.02", "5.9.99"}
    assert r.json()["reportes"] == []

    # Sin el mes cerrado, 400 con el motivo. Y un período mal escrito, también 400.
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "balancete", "periodo": mes})
    assert r.status_code == 400 and "cerrado" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "balancete", "periodo": "2026-13"})
    assert r.status_code == 400 and "no es un período" in r.json()["detail"]
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "otro", "periodo": mes})
    assert r.status_code == 422

    # Cierra el mes; la cola genera el balancete y el CCS del día.
    fin = periodos.limites(periodos.MES, mes)[1]
    assert cliente.post("/api/nucleo/laboratorio/cierres", json={"dia": fin.isoformat()}).status_code == 200
    assert cliente.post("/api/nucleo/laboratorio/cola/paso").status_code == 200
    generados = {(x["tipo"], x["periodo"]): x for x in cliente.get("/api/nucleo/laboratorio/reportes").json()["reportes"]}
    assert ("balancete", mes) in generados and ("ccs", hoy.isoformat()) in generados
    balancete = generados[("balancete", mes)]
    assert balancete["estado"] == "generado" and balancete["resumen"]["cuadra"] is True and balancete["archivo"] is None

    # El archivo entero, por su id. Y la transmisión, con protocolo, una vez.
    r = cliente.get(f"/api/nucleo/laboratorio/reportes/{balancete['id']}")
    assert r.status_code == 200 and '"documento": "CADOC 4010"' in r.json()["archivo"]
    r = cliente.post(f"/api/nucleo/laboratorio/reportes/{balancete['id']}/transmitir")
    assert r.status_code == 200 and r.json()["estado"] == "transmitido" and r.json()["protocolo"].startswith("STA-SIM-")
    r = cliente.post(f"/api/nucleo/laboratorio/reportes/{balancete['id']}/transmitir")
    assert r.status_code == 400 and "ya se transmitió" in r.json()["detail"]
    assert cliente.get("/api/nucleo/laboratorio/reportes/999").status_code == 404

    # Rectificar: una versión nueva, sustitución.
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "balancete", "periodo": mes})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["resumen"]["tipo_remessa"] == "S"
    assert cliente.get("/api/nucleo/laboratorio/reportes").json()["resumen"]["balancete"] == {"generados": 2, "transmitidos": 1}


# ─── el cumplimiento por HTTP ─────────────────────────────────────────────

def test_el_cumplimiento_por_http_incidente_reclamo_y_calendario(cliente):
    r = cliente.get("/api/nucleo/laboratorio/cumplimiento")
    assert r.status_code == 200
    assert r.json()["tipos_de_incidente"] == ["indisponibilidad", "fuga_de_datos", "fraude", "ciberataque", "otro"]
    assert r.json()["canales"] == ["telefono", "correo", "panel", "bcb", "procon"] and r.json()["acciones"] == []

    # Un incidente relevante: lleva plazo, aparece como acción, se comunica una vez, se cierra una vez.
    r = cliente.post("/api/nucleo/laboratorio/cumplimiento/incidentes",
                     json={"tipo": "indisponibilidad", "titulo": "PIX caído", "impacto": "Sin pagos", "clientes_afectados": 12, "relevante": True})
    assert r.status_code == 200 and r.json()["comunicar_hasta"] and r.json()["estado"] == "abierto"
    inc = r.json()["id"]
    assert cliente.post("/api/nucleo/laboratorio/cumplimiento/incidentes",
                        json={"tipo": "raro", "titulo": "x", "impacto": "x", "clientes_afectados": 0}).status_code == 422
    assert cliente.post("/api/nucleo/laboratorio/cumplimiento/incidentes",
                        json={"tipo": "otro", "titulo": "x", "impacto": "x", "clientes_afectados": 0, "inicio": "ayer"}).status_code == 400
    acciones = cliente.get("/api/nucleo/laboratorio/cumplimiento").json()["acciones"]
    assert [(a["accion"], a["referencia"]) for a in acciones] == [("comunicar_incidente", inc)]
    r = cliente.post(f"/api/nucleo/laboratorio/cumplimiento/incidentes/{inc}/anotar", json={"texto": "Se reinició el trabajador."})
    assert r.status_code == 200 and r.json()["notas"][-1]["texto"] == "Se reinició el trabajador."
    r = cliente.post(f"/api/nucleo/laboratorio/cumplimiento/incidentes/{inc}/comunicar")
    assert r.status_code == 200 and r.json()["protocolo"].startswith("STA-SIM-")
    assert cliente.post(f"/api/nucleo/laboratorio/cumplimiento/incidentes/{inc}/comunicar").status_code == 400
    r = cliente.post(f"/api/nucleo/laboratorio/cumplimiento/incidentes/{inc}/cerrar", json={"causa": "Certificado vencido", "acciones": "Renovado y alarma"})
    assert r.status_code == 200 and r.json()["estado"] == "cerrado"
    assert cliente.post(f"/api/nucleo/laboratorio/cumplimiento/incidentes/{inc}/cerrar", json={"causa": "x", "acciones": "x"}).status_code == 400

    # Un reclamo: protocolo, diez días hábiles, respuesta una vez.
    r = cliente.post("/api/nucleo/laboratorio/cumplimiento/reclamos",
                     json={"canal": "bcb", "asunto": "Cobro duplicado", "descripcion": "Se cobró dos veces", "caso_soporte": "S-000042"})
    assert r.status_code == 200 and r.json()["protocolo"].startswith("OUV-") and r.json()["caso_soporte"] == "S-000042"
    rec = r.json()["id"]
    assert [a["accion"] for a in cliente.get("/api/nucleo/laboratorio/cumplimiento").json()["acciones"]] == ["responder_reclamo"]
    assert cliente.post(f"/api/nucleo/laboratorio/cumplimiento/reclamos/{rec}/responder",
                        json={"respuesta": "x", "resultado": "raro"}).status_code == 422
    r = cliente.post(f"/api/nucleo/laboratorio/cumplimiento/reclamos/{rec}/responder",
                     json={"respuesta": "Se devolvió el segundo cobro.", "resultado": "procedente"})
    assert r.status_code == 200 and r.json()["estado"] == "respondido" and r.json()["en_plazo"] is True
    assert cliente.post(f"/api/nucleo/laboratorio/cumplimiento/reclamos/{rec}/responder",
                        json={"respuesta": "otra", "resultado": "parcial"}).status_code == 400
    todo = cliente.get("/api/nucleo/laboratorio/cumplimiento").json()
    assert todo["acciones"] == [] and todo["resumen_incidentes"]["cerrado"] == 1 and todo["resumen_reclamos"]["respondido"] == 1

    # El calendario y los informes del cumplimiento por el mismo camino que los reportes.
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "incidentes", "periodo": "2025"})
    assert r.status_code == 200 and r.json()["documento"] == "Informe anual de incidentes" and r.json()["resumen"]["total"] == 0
    r = cliente.post("/api/nucleo/laboratorio/reportes/generar", json={"tipo": "ouvidoria", "periodo": "2099-S1"})
    assert r.status_code == 400 and "terminó" in r.json()["detail"]
    assert isinstance(todo["calendario"], list) and set(todo["resumen_calendario"]) == {"pendientes", "vencidas", "acciones", "acciones_vencidas"}
