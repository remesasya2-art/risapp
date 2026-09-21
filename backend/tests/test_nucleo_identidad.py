"""
tests/test_nucleo_identidad.py — el legajo del titular, la verificación,
las listas, y la guarda que lo ata todo: sin legajo aprobado no hay cuenta.

    Cada guarda con su test, y cada camino del simulador con el suyo: el
    rostro que no coincide, el documento vencido, el nombre distinto, el
    CPF irregular, el sancionado, el PEP.
"""
import asyncio
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from nucleo import base, comandos, plan                                  # noqa: E402
from nucleo.identidad import formas, legajos, simulador                  # noqa: E402


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


PERSONAS = {comp: (cpf, nombre) for cpf, nombre, _n, comp in simulador.PERSONAS_DE_PRUEBA}
ANA = ("12345678909", "Ana Prueba")


def titular(comp="normal", **extra):
    cpf, nombre = PERSONAS[comp] if comp != "normal" else ANA
    return ya(legajos.crear_titular(documento=cpf, nombre=nombre, actor="t", **extra))


def preparar(comp="normal", **extra):
    """Creado, verificado y cruzado: listo para que alguien decida."""
    t = titular(comp, **extra)
    ya(legajos.verificar(t["id"], actor="t"))
    ya(legajos.cruzar(t["id"], actor="t"))
    return ya(legajos.detalle(t["id"]))


# ─── el alta ──────────────────────────────────────────────────────────────

def test_el_legajo_nace_incompleto_y_es_uno_por_documento():
    t = titular(renta_declarada="3500.00", origen_de_fondos="salario", ocupacion="docente")
    assert t["estado"] == "incompleto" and t["tipo"] == "cpf" and t["renta_declarada"] == "3500.00"
    assert titular()["id"] == t["id"]
    assert len(ya(legajos.listar())) == 1


@pytest.mark.parametrize("malo", ["12345678900", "abc", "", "1234567890123"])
def test_UN_DOCUMENTO_INVALIDO_NO_ABRE_LEGAJO(malo):
    with pytest.raises(legajos.LegajoInvalido):
        ya(legajos.crear_titular(documento=malo, nombre="Alguien", actor="t"))


def test_el_origen_de_fondos_es_del_catalogo():
    with pytest.raises(legajos.LegajoInvalido, match="Origen de fondos"):
        titular(origen_de_fondos="loteria")


# ─── verificar ────────────────────────────────────────────────────────────

def test_una_persona_normal_pasa_la_verificacion():
    t = titular()
    v = ya(legajos.verificar(t["id"], actor="t"))
    assert v["aprobada"] and v["motivos"] == [] and v["puntaje_rostro"] >= formas.PUNTAJE_MINIMO
    assert ya(legajos.detalle(t["id"]))["estado"] == "incompleto"        # falta cruzar


@pytest.mark.parametrize("comp, texto", [
    ("cara_no_coincide", "rostro"), ("documento_vencido", "vencido"),
    ("nombre_distinto", "nombre"), ("cpf_irregular", "Receita"),
])
def test_CADA_MOTIVO_DE_RECHAZO_QUEDA_ESCRITO(comp, texto):
    t = titular(comp)
    v = ya(legajos.verificar(t["id"], actor="t"))
    assert v["aprobada"] is False and any(texto in m for m in v["motivos"]), v["motivos"]
    d = ya(legajos.detalle(t["id"]))
    assert d["estado"] == "incompleto" and len(d["verificaciones"]) == 1


def test_la_regla_de_evaluacion_es_una_sola():
    r = formas.evaluar(proveedor="x", puntaje_documento=79, puntaje_vida=100, puntaje_rostro=100,
                       situacion_cpf="regular", nombre_en_documento="Ana Prueba", nombre_declarado="ana  prueba",
                       documento_vencido=False)
    assert not r.aprobada and "documento" in r.motivos[0]
    r = formas.evaluar(proveedor="x", puntaje_documento=80, puntaje_vida=80, puntaje_rostro=80,
                       situacion_cpf="regular", nombre_en_documento="Ána Prueba", nombre_declarado="ana prueba",
                       documento_vencido=False)
    assert r.aprobada


# ─── cruzar ───────────────────────────────────────────────────────────────

def test_el_sancionado_deja_un_cruce_abierto_y_no_se_aprueba_hasta_que_alguien_lo_mire():
    d = preparar("sancionado")
    assert len(d["cruces"]) == 1 and d["cruces"][0]["lista"] == "CSNU" and d["cruces"][0]["clase"] == "sanciones"
    assert d["estado"] == "incompleto"
    with pytest.raises(legajos.LegajoInvalido, match="sin resolver"):
        ya(legajos.aprobar(d["id"], nivel_de_riesgo="alto", actor="t"))
    # cruzar de nuevo no duplica el cruce abierto
    assert len(ya(legajos.cruzar(d["id"], actor="t"))) == 1
    ya(legajos.resolver_cruce(d["cruces"][0]["id"], resolucion="falso positivo: homónimo, otra fecha de nacimiento", actor="jefa"))
    d = ya(legajos.detalle(d["id"]))
    assert d["estado"] == "en_revision" and d["cruces"][0]["resuelto_por"] == "jefa"
    assert ya(legajos.aprobar(d["id"], nivel_de_riesgo="medio", actor="t"))["estado"] == "aprobado"


def test_UN_CRUCE_DE_SANCIONES_CONFIRMADO_NO_SE_APRUEBA_NUNCA():
    d = preparar("sancionado")
    ya(legajos.resolver_cruce(d["cruces"][0]["id"], resolucion="confirmado: es la persona de la lista", actor="jefa"))
    with pytest.raises(legajos.LegajoInvalido, match="confirmado"):
        ya(legajos.aprobar(d["id"], nivel_de_riesgo="alto", actor="t"))


def test_EL_PEP_DE_LA_LISTA_SOLO_SE_APRUEBA_CON_RIESGO_ALTO():
    d = preparar("pep")
    assert d["pep"] is True and d["pep_declarado"] is False and d["estado"] == "en_revision"
    with pytest.raises(legajos.LegajoInvalido, match="riesgo alto"):
        ya(legajos.aprobar(d["id"], nivel_de_riesgo="bajo", actor="t"))
    a = ya(legajos.aprobar(d["id"], nivel_de_riesgo="alto", actor="t"))
    assert a["estado"] == "aprobado" and a["nivel_de_riesgo"] == "alto"


def test_el_pep_declarado_tambien_exige_riesgo_alto():
    d = preparar(pep_declarado=True)
    with pytest.raises(legajos.LegajoInvalido, match="riesgo alto"):
        ya(legajos.aprobar(d["id"], nivel_de_riesgo="medio", actor="t"))


# ─── decidir ──────────────────────────────────────────────────────────────

def test_NO_SE_APRUEBA_SIN_VERIFICACION_APROBADA():
    t = titular("cara_no_coincide")
    ya(legajos.verificar(t["id"], actor="t")); ya(legajos.cruzar(t["id"], actor="t"))
    with pytest.raises(legajos.LegajoInvalido, match="verificación"):
        ya(legajos.aprobar(t["id"], nivel_de_riesgo="bajo", actor="t"))


def test_NO_SE_APRUEBA_SIN_CRUZAR():
    t = titular()
    ya(legajos.verificar(t["id"], actor="t"))
    with pytest.raises(legajos.LegajoInvalido, match="cruzarlo"):
        ya(legajos.aprobar(t["id"], nivel_de_riesgo="bajo", actor="t"))


def test_la_vigencia_depende_del_riesgo():
    d = preparar()
    hoy = date(2026, 9, 21)
    a = ya(legajos.aprobar(d["id"], nivel_de_riesgo="bajo", actor="t", hoy=hoy))
    assert a["vigente_hasta"] == "2028-09-21" and a["decidido_por"] == "t"
    d2 = preparar("pep")
    a2 = ya(legajos.aprobar(d2["id"], nivel_de_riesgo="alto", actor="t", hoy=date(2026, 1, 31)))
    assert a2["vigente_hasta"] == "2027-01-31"


def test_un_rechazado_no_se_verifica_ni_se_aprueba_de_nuevo():
    d = preparar()
    r = ya(legajos.rechazar(d["id"], motivo="documento con indicios de adulteración", actor="t"))
    assert r["estado"] == "rechazado" and "adulteración" in r["motivo"]
    with pytest.raises(legajos.LegajoInvalido):
        ya(legajos.verificar(d["id"], actor="t"))
    with pytest.raises(legajos.LegajoInvalido):
        ya(legajos.aprobar(d["id"], nivel_de_riesgo="bajo", actor="t"))


# ─── la guarda de la cuenta ───────────────────────────────────────────────

def test_SIN_LEGAJO_APROBADO_NO_HAY_CUENTA():
    with pytest.raises(legajos.LegajoNoApto):
        ya(comandos.crear_cuenta(titular_ref="tit_nadie"))
    d = preparar()
    with pytest.raises(legajos.LegajoNoApto, match="en_revision"):
        ya(comandos.crear_cuenta(titular_ref=d["id"]))
    ya(legajos.aprobar(d["id"], nivel_de_riesgo="bajo", actor="t"))
    c = ya(comandos.crear_cuenta(titular_ref=d["id"]))
    assert c["titular_ref"] == d["id"]
    assert ya(comandos.estado())["cuentas"] == 1


def test_UN_LEGAJO_VENCIDO_NO_ABRE_CUENTA_Y_QUEDA_MARCADO():
    d = preparar()
    ya(legajos.aprobar(d["id"], nivel_de_riesgo="alto", actor="t", hoy=date(2024, 1, 1)))   # venció en 2025
    with pytest.raises(legajos.LegajoNoApto, match="venció"):
        ya(comandos.crear_cuenta(titular_ref=d["id"]))
    assert ya(legajos.detalle(d["id"]))["estado"] == "vencido"


def test_revisar_vigencias_marca_los_vencidos():
    d = preparar()
    ya(legajos.aprobar(d["id"], nivel_de_riesgo="bajo", actor="t", hoy=date(2020, 1, 1)))
    assert ya(legajos.revisar_vigencias(hoy=date(2026, 9, 21))) == 1
    assert ya(legajos.detalle(d["id"]))["estado"] == "vencido"


def test_no_hay_funcion_que_borre_legajos_ni_cruces():
    """Se conservan diez años (Circular 3.978). Por contrato, no hay cómo borrar."""
    nombres = [n for n in dir(legajos) if not n.startswith("_")]
    for prohibido in ("borrar", "eliminar", "delete", "purgar"):
        assert not any(prohibido in n.lower() for n in nombres), nombres
