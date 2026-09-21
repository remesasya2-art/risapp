"""
tests/test_nucleo_libro.py — el libro del núcleo: partida doble, correlativo
sin huecos, encadenado por hash, idempotencia, cierre y saldo derivado.

    Corre sobre SQLite en memoria con la misma lógica que Postgres: los
    montos son enteros en centavos, exactos en las dos.
"""
import asyncio
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nucleo import base, comandos, libro, plan                 # noqa: E402
from nucleo.esquema import HASH_DEL_PRINCIPIO, asientos         # noqa: E402
from nucleo.libro import AsientoInvalido, DiaCerrado, Partida   # noqa: E402

HOY = date(2026, 9, 21)


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


def cuenta(titular="u_ana"):
    from _nucleo_comun import cuenta_aprobada
    return cuenta_aprobada(titular)


# ─── reglas del asiento ───────────────────────────────────────────────────

def test_un_asiento_descuadrado_no_llega_a_la_base():
    async def intento():
        async with base.sesion() as s:
            await libro.asentar(s, fecha=HOY, descripcion="x", referencia="r1", comando="ajuste",
                                actor="t", lineas=[Partida(plan.LIQUIDACION, debe=100),
                                                   Partida(plan.CAPITAL, haber=99)])
    with pytest.raises(AsientoInvalido, match="no cuadra"):
        ya(intento())
    assert ya(comandos.estado())["asientos"] == 0


@pytest.mark.parametrize("lineas, motivo", [
    ([Partida(plan.LIQUIDACION, debe=100)], "al menos dos"),
    ([Partida(plan.LIQUIDACION, debe=0), Partida(plan.CAPITAL, haber=0)], "mayor que cero"),
    ([Partida(plan.LIQUIDACION, debe=100, haber=100), Partida(plan.CAPITAL, haber=0)], "debe o al haber"),
    ([Partida(plan.LIQUIDACION, debe=-5), Partida(plan.CAPITAL, haber=-5)], "negativo"),
    ([Partida(plan.LIQUIDACION, debe=1.5), Partida(plan.CAPITAL, haber=1.5)], "entero en centavos"),
    ([Partida("9.9.99", debe=5), Partida(plan.CAPITAL, haber=5)], "inexistente"),
])
def test_LAS_REGLAS_DEL_ASIENTO(lineas, motivo):
    async def intento():
        async with base.sesion() as s:
            await libro.asentar(s, fecha=HOY, descripcion="x", referencia="r", comando="ajuste",
                                actor="t", lineas=lineas)
    with pytest.raises(AsientoInvalido, match=motivo):
        ya(intento())


# ─── correlativo, hash, idempotencia ──────────────────────────────────────

def test_la_numeracion_es_correlativa_y_el_primero_encadena_con_el_principio():
    c = cuenta()
    n1 = ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="a1", actor="t", fecha=HOY))
    n2 = ya(comandos.acreditar(cuenta_id=c, monto="50.00", referencia="a2", actor="t", fecha=HOY))
    assert (n1, n2) == (1, 2)

    async def leer():
        async with base.sesion() as s:
            return await libro.listar_asientos(s)
    a2, a1 = ya(leer())
    assert a1["hash_previo"] == HASH_DEL_PRINCIPIO
    assert a2["hash_previo"] == a1["hash"]
    assert a1["hash"] != a2["hash"] and len(a1["hash"]) == 64


def test_LA_MISMA_REFERENCIA_NO_ASIENTA_DOS_VECES():
    c = cuenta()
    n1 = ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="misma", actor="t", fecha=HOY))
    n2 = ya(comandos.acreditar(cuenta_id=c, monto="100.00", referencia="misma", actor="t", fecha=HOY))
    assert n1 == n2 == 1
    assert ya(comandos.estado())["asientos"] == 1

    async def saldo():
        async with base.sesion() as s:
            return await libro.saldo(s, c)
    assert ya(saldo()) == 10000


def test_ALTERAR_UN_ASIENTO_ROMPE_LA_CADENA_Y_SE_ENCUENTRA():
    c = cuenta()
    for i in range(3):
        ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia=f"r{i}", actor="t", fecha=HOY))

    async def verificar():
        async with base.sesion() as s:
            return await libro.verificar_cadena(s)
    assert ya(verificar())["ok"] is True

    async def alterar():
        async with base.sesion() as s:
            await s.execute(asientos.update().where(asientos.c.numero == 2).values(descripcion="otra cosa"))
    ya(alterar())
    v = ya(verificar())
    assert v["ok"] is False and v["roto_en"] == 2
    assert "alterado" in v["motivo"]


def test_un_hueco_en_la_numeracion_se_encuentra():
    c = cuenta()
    for i in range(3):
        ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia=f"r{i}", actor="t", fecha=HOY))

    async def borrar_el_dos():
        from nucleo.esquema import partidas
        async with base.sesion() as s:
            await s.execute(partidas.delete().where(partidas.c.asiento == 2))
            await s.execute(asientos.delete().where(asientos.c.numero == 2))
    ya(borrar_el_dos())

    async def verificar():
        async with base.sesion() as s:
            return await libro.verificar_cadena(s)
    v = ya(verificar())
    assert v["ok"] is False and "hueco" in v["motivo"]


# ─── saldo derivado, comandos y cierre ────────────────────────────────────

def test_el_saldo_se_deriva_de_las_partidas_y_no_queda_en_negativo():
    a, b = cuenta("u_a"), cuenta("u_b")
    ya(comandos.acreditar(cuenta_id=a, monto="100.00", referencia="in", actor="t", fecha=HOY))
    ya(comandos.transferir(desde=a, hacia=b, monto="30.50", referencia="tr", actor="t", fecha=HOY))
    ya(comandos.cobrar_tarifa(cuenta_id=a, monto="1.25", referencia="fee", actor="t", fecha=HOY))
    ya(comandos.debitar(cuenta_id=b, monto="0.50", referencia="out", actor="t", fecha=HOY))
    filas = {f["id"]: f["saldo"] for f in ya(comandos.listar_cuentas())}
    assert filas[a] == "68.25" and filas[b] == "30.00"
    with pytest.raises(AsientoInvalido, match="Saldo insuficiente"):
        ya(comandos.debitar(cuenta_id=b, monto="30.01", referencia="mas", actor="t", fecha=HOY))


def test_el_balance_de_comprobacion_cuadra_y_la_tarifa_es_ingreso():
    a = cuenta()
    ya(comandos.acreditar(cuenta_id=a, monto="100.00", referencia="in", actor="t", fecha=HOY))
    ya(comandos.cobrar_tarifa(cuenta_id=a, monto="2.00", referencia="fee", actor="t", fecha=HOY))

    async def balance():
        async with base.sesion() as s:
            return await libro.balance_de_comprobacion(s)
    b = ya(balance())
    assert b["cuadra"] and b["total_debe"] == b["total_haber"] == 10200
    por_codigo = {f["codigo"]: f for f in b["filas"]}
    assert por_codigo[plan.TARIFAS]["saldo"] == 200          # ingreso, acreedora
    assert por_codigo[plan.DE_TITULARES]["saldo"] == 9800    # pasivo con el titular
    assert por_codigo[plan.LIQUIDACION]["saldo"] == 10000    # activo, deudora


def test_DESPUES_DEL_CIERRE_NO_SE_ASIENTA_EN_ESE_DIA():
    a = cuenta()
    ya(comandos.acreditar(cuenta_id=a, monto="10.00", referencia="r1", actor="t", fecha=HOY))
    cierre = ya(comandos.cerrar_dia(dia=HOY, actor="t"))
    assert cierre["hasta_asiento"] == 1 and cierre["asientos"] == 1
    assert cierre["total_debe"] == cierre["total_haber"] == 1000
    with pytest.raises(DiaCerrado):
        ya(comandos.acreditar(cuenta_id=a, monto="10.00", referencia="r2", actor="t", fecha=HOY))
    with pytest.raises(DiaCerrado):
        ya(comandos.cerrar_dia(dia=HOY, actor="t"))
    # el día siguiente sigue abierto
    assert ya(comandos.acreditar(cuenta_id=a, monto="10.00", referencia="r3", actor="t",
                                 fecha=date(2026, 9, 22))) == 2


def test_no_se_cierra_un_dia_anterior_al_ultimo_cerrado():
    ya(comandos.cerrar_dia(dia=HOY, actor="t"))
    with pytest.raises(DiaCerrado):
        ya(comandos.cerrar_dia(dia=date(2026, 9, 20), actor="t"))


# ─── el dinero en los bordes ──────────────────────────────────────────────

@pytest.mark.parametrize("texto, centavos", [("100.00", 10000), ("100", 10000), ("0.01", 1), ("1,50", 150), ("2500.99", 250099)])
def test_el_monto_entra_como_texto_y_se_vuelve_centavos(texto, centavos):
    assert comandos.a_centavos(texto) == centavos
    assert comandos.a_texto(centavos) == comandos.a_texto(comandos.a_centavos(texto))


@pytest.mark.parametrize("malo", ["0", "-1", "abc", "1.005", "", 1.5, True])
def test_LO_QUE_NO_ES_UN_MONTO_SE_RECHAZA(malo):
    with pytest.raises(comandos.MontoInvalido):
        comandos.a_centavos(malo)


def test_no_hay_funcion_que_edite_ni_borre_asientos():
    """Por contrato: un error se corrige con otro asiento."""
    nombres = [n for n in dir(libro) if not n.startswith("_")]
    for prohibido in ("editar", "borrar", "eliminar", "delete", "update", "modificar", "anular"):
        assert not any(prohibido in n.lower() for n in nombres), nombres


def test_ALTERAR_UNA_PARTIDA_TAMBIEN_ROMPE_LA_CADENA():
    """El hash cubre las partidas, no sólo la cabecera: cambiar un monto o la
    cuenta de una línea se encuentra igual que cambiar la descripción. Una
    mutación que dejó las partidas fuera del hash sobrevivió al test de
    arriba; por eso existe éste."""
    from nucleo.esquema import partidas
    c = cuenta()
    ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="r1", actor="t", fecha=HOY))

    async def verificar():
        async with base.sesion() as s:
            return await libro.verificar_cadena(s)
    assert ya(verificar())["ok"] is True

    async def inflar():
        async with base.sesion() as s:
            await s.execute(partidas.update().where(partidas.c.asiento == 1, partidas.c.haber > 0).values(haber=999999))
    ya(inflar())
    v = ya(verificar())
    assert v["ok"] is False and v["roto_en"] == 1 and "alterado" in v["motivo"]
