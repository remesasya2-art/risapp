"""
tests/test_nucleo_rieles.py — los rieles de pago del núcleo: las formas del
PIX, el simulador, las operaciones y su contabilidad.

    Lo que un liquidante y un auditor van a mirar: que los identificadores
    tengan la forma del SPI, que el QR pase el CRC, que un cobro pagado
    acredite UNA vez aunque el aviso llegue dos, que un pago reserve antes
    de salir y vuelva al titular si el SPI lo rechaza, que el balance cuadre
    en cada paso, y que nada de esto importe una pieza de la aplicación.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from nucleo import base, comandos, libro, plan, trabajador          # noqa: E402
from nucleo.libro import AsientoInvalido                            # noqa: E402
from nucleo.rieles import operaciones as op, pix, simulador          # noqa: E402


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


def cuenta(titular="u_ana", saldo=None):
    from _nucleo_comun import cuenta_aprobada
    c = cuenta_aprobada(titular)
    if saldo:
        ya(comandos.acreditar(cuenta_id=c, monto=saldo, referencia=f"in-{c}", actor="t"))
    return c


def saldo(c):
    return {f["id"]: f["saldo"] for f in ya(comandos.listar_cuentas())}[c]


def balance():
    async def _():
        async with base.sesion() as s:
            b = await libro.balance_de_comprobacion(s)
            return b["cuadra"], {f["codigo"]: f["saldo"] for f in b["filas"]}
    return ya(_())


def vuelta():
    return ya(trabajador.una_vuelta())


def simular_pago(cobro, monto_centavos, pagador="ana@ejemplo.test"):
    async def _():
        async with base.sesion() as s:
            return await simulador.Simulador().simular_pago_del_cobro(
                s, txid=cobro["txid"], monto=monto_centavos, pagador_clave=pagador)
    return ya(_())


# ─── las formas del PIX ───────────────────────────────────────────────────

@pytest.mark.parametrize("clave, tipo", [
    ("12345678909", pix.CPF), ("12345678000195", pix.CNPJ), ("ana@ejemplo.test", pix.EMAIL),
    ("+5511999990000", pix.TELEFONE), ("123e4567-e89b-12d3-a456-426614174000", pix.EVP),
])
def test_se_reconoce_cada_tipo_de_clave(clave, tipo):
    assert pix.tipo_de_clave(clave) == tipo


@pytest.mark.parametrize("mala", ["", "12345678900", "11111111111", "12345678000100", "ana@", "11999990000", "hola"])
def test_LO_QUE_NO_ES_UNA_CLAVE_SE_RECHAZA(mala):
    with pytest.raises(pix.ClaveInvalida):
        pix.tipo_de_clave(mala)


def test_el_end_to_end_tiene_la_forma_del_spi():
    e = pix.nuevo_end_to_end("99999999")
    assert len(e) == 32 and e.startswith("E99999999") and pix.es_end_to_end(e)
    assert not pix.es_end_to_end("E123")
    with pytest.raises(ValueError):
        pix.nuevo_end_to_end("abc")


def test_EL_BR_CODE_PASA_EL_CRC_Y_UN_CARACTER_CAMBIADO_NO():
    txid = pix.nuevo_txid()
    q = pix.br_code(clave="cobros@ejemplo.test", monto_centavos=15000, nombre="RIS Instituição", ciudad="São Paulo",
                    txid=txid, descripcion="Café")
    assert q.startswith("000201010212") and "br.gov.bcb.pix" in q and "5406150.00" in q and txid in q
    assert "RIS INSTITUICAO" in q and "SAO PAULO" in q and "CAFE" in q
    assert pix.br_code_valido(q)
    roto = q[:20] + ("0" if q[20] != "0" else "1") + q[21:]
    assert not pix.br_code_valido(roto)


def test_la_devolucion_exige_un_motivo_del_catalogo():
    e = pix.nuevo_end_to_end("99999999")
    pix.Devolucion(end_to_end_original=e, end_to_end=pix.nuevo_end_to_end("99999999"), monto=1, motivo="FR01")
    with pytest.raises(ValueError):
        pix.Devolucion(end_to_end_original=e, end_to_end=e, monto=1, motivo="XX99")
    with pytest.raises(ValueError):
        pix.Devolucion(end_to_end_original=e, end_to_end=e, monto=0, motivo="MD06")


def test_el_documento_se_enmascara_como_en_el_dict():
    assert pix.enmascarar_documento("12345678909") == "***.456.789-**"
    assert pix.enmascarar_documento("12345678000195") == "12.345.678/****-**"


def test_el_rechazo_se_explica_en_castellano():
    r = pix.RespuestaDeEstado(end_to_end="x", estado=pix.RJCT, motivo="AC06")
    assert r.motivo_explicado == "AC06: La cuenta del receptor está bloqueada"


# ─── el DICT del simulador ────────────────────────────────────────────────

def test_el_dict_de_prueba_contesta_y_enmascara():
    t = ya(op.consultar_clave("ana@ejemplo.test"))
    assert t["nombre"] == "Ana Prueba" and t["documento"] == "***.456.789-**" and t["ispb"] == "11111111"
    assert ya(op.consultar_clave("noexiste@ejemplo.test")) is None
    assert ya(op.consultar_clave("ANA@EJEMPLO.TEST"))["clave"] == "ana@ejemplo.test"


# ─── cobros ───────────────────────────────────────────────────────────────

def test_UN_COBRO_PAGADO_ACREDITA_AL_TITULAR_UNA_SOLA_VEZ():
    c = cuenta()
    cobro = ya(op.crear_cobro(cuenta_id=c, monto="150.00", descripcion="prueba", actor="t"))
    assert cobro["estado"] == "activa" and pix.br_code_valido(cobro["codigo_br"]) and pix.es_txid(cobro["txid"])
    assert saldo(c) == "0.00"

    aviso = simular_pago(cobro, 15000)
    assert aviso["nuevo"] is True
    r = vuelta()
    assert r["hechos"] >= 1
    assert saldo(c) == "150.00"
    d = ya(op.detalle(cobro["id"]))
    assert d["estado"] == "liquidada" and pix.es_end_to_end(d["end_to_end"])
    assert d["contraparte"]["nombre"] == "Ana Prueba"
    assert [h["estado"] for h in d["historial"]] == ["activa", "liquidada"]

    # el mismo aviso otra vez: se procesa de nuevo a mano y no acredita
    assert ya(op.procesar_aviso({"aviso": aviso["id"]})) == "acreditado"
    assert saldo(c) == "150.00"
    # y un segundo aviso distinto con el MISMO end_to_end tampoco
    async def repetido():
        async with base.sesion() as s:
            return await op.recibir_aviso(s, riel="simulador", id_externo="otro-id", tipo="credito_recibido",
                                          carga={"txid": cobro["txid"], "end_to_end": d["end_to_end"], "monto": 15000,
                                                 "pagador": {"nombre": "Ana Prueba"}})
    ya(repetido()); vuelta()
    assert saldo(c) == "150.00"
    assert ya(comandos.estado())["asientos"] == 1
    # y un «segundo pago» del mismo QR, con OTRO end_to_end, tampoco: un QR
    # dinámico se paga una vez
    async def otro_pago():
        async with base.sesion() as s:
            return await op.recibir_aviso(s, riel="simulador", id_externo="otro-pago", tipo="credito_recibido",
                                          carga={"txid": cobro["txid"], "end_to_end": pix.nuevo_end_to_end("11111111"),
                                                 "monto": 15000, "pagador": {"nombre": "Ana Prueba"}})
    ya(otro_pago()); vuelta()
    assert saldo(c) == "150.00" and ya(comandos.estado())["asientos"] == 1
    assert any(a["resultado"] == "cobro ya liquidado" for a in ya(op.listar_avisos()))
    # el asiento cita el end_to_end: es lo que ata la plata a la operación del SPI
    async def asientos():
        async with base.sesion() as s:
            return await libro.listar_asientos(s)
    assert ya(asientos())[0]["referencia"] == f"pix:{d['end_to_end']}"


def test_un_aviso_repetido_del_riel_no_se_encola_dos_veces():
    async def _():
        async with base.sesion() as s:
            a = await op.recibir_aviso(s, riel="simulador", id_externo="x1", tipo="estado_de_pago", carga={})
            b = await op.recibir_aviso(s, riel="simulador", id_externo="x1", tipo="estado_de_pago", carga={})
            return a, b
    a, b = ya(_())
    assert a["nuevo"] and not b["nuevo"] and a["id"] == b["id"]


def test_un_credito_para_un_cobro_desconocido_no_acredita_y_queda_dicho():
    c = cuenta()
    async def _():
        async with base.sesion() as s:
            return await op.recibir_aviso(s, riel="simulador", id_externo="raro", tipo="credito_recibido",
                                          carga={"txid": "NOEXISTE", "end_to_end": pix.nuevo_end_to_end("11111111"),
                                                 "monto": 100, "pagador": {}})
    ya(_()); vuelta()
    assert saldo(c) == "0.00"
    (a,) = ya(op.listar_avisos())
    assert a["procesado"] and "desconocido" in a["resultado"]


# ─── pagos ────────────────────────────────────────────────────────────────

def test_UN_PAGO_RESERVA_SALE_Y_SE_LIQUIDA_CON_EL_BALANCE_CUADRANDO():
    c = cuenta(saldo="100.00")
    p = ya(op.ordenar_pago(cuenta_id=c, clave="ana@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    assert p["estado"] == "pendiente" and pix.es_end_to_end(p["end_to_end"])
    assert saldo(c) == "70.00"                              # reservado, ya no es del titular
    cuadra, saldos = balance()
    assert cuadra and saldos[plan.TRANSITO] == 3000 and saldos[plan.LIQUIDACION] == 10000

    r = vuelta()
    assert r["hechos"] >= 2 and r["muertos"] == 0            # enviar_pago y procesar_aviso (ACSC), más los avisos de asiento
    d = ya(op.detalle(p["id"]))
    assert d["estado"] == "liquidada"
    assert [h["estado"] for h in d["historial"]] == ["pendiente", "enviada", "liquidada"]
    cuadra, saldos = balance()
    assert cuadra and saldos[plan.TRANSITO] == 0 and saldos[plan.LIQUIDACION] == 7000
    assert saldo(c) == "70.00"
    assert ya(comandos.estado())["asientos"] == 3            # acreditación, reserva, liquidación


def test_UN_PAGO_RECHAZADO_VUELVE_AL_TITULAR_CON_EL_MOTIVO():
    c = cuenta(saldo="100.00")
    p = ya(op.ordenar_pago(cuenta_id=c, clave="rechaza@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    assert saldo(c) == "70.00"
    vuelta()
    d = ya(op.detalle(p["id"]))
    assert d["estado"] == "rechazada" and "AC06" in d["motivo"] and "bloqueada" in d["motivo"]
    assert saldo(c) == "100.00"
    cuadra, saldos = balance()
    assert cuadra and saldos[plan.TRANSITO] == 0 and saldos[plan.LIQUIDACION] == 10000


def test_un_pago_que_tarda_queda_enviado_hasta_que_el_spi_conteste():
    c = cuenta(saldo="100.00")
    p = ya(op.ordenar_pago(cuenta_id=c, clave="tarda@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    vuelta()
    assert ya(op.detalle(p["id"]))["estado"] == "enviada"
    assert saldo(c) == "70.00" and balance()[1][plan.TRANSITO] == 3000

    async def contesta():
        async with base.sesion() as s:
            return await simulador.Simulador().simular_resultado(s, end_to_end=p["end_to_end"], estado="ACSC")
    ya(contesta()); vuelta()
    assert ya(op.detalle(p["id"]))["estado"] == "liquidada" and balance()[1][plan.TRANSITO] == 0


def test_SIN_SALDO_NO_SE_ORDENA_NADA():
    c = cuenta(saldo="10.00")
    with pytest.raises(AsientoInvalido, match="Saldo insuficiente"):
        ya(op.ordenar_pago(cuenta_id=c, clave="ana@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    assert ya(op.listar()) == [] and ya(comandos.estado())["asientos"] == 1


def test_UNA_CLAVE_QUE_NO_ESTA_EN_EL_DICT_NO_RESERVA_NADA():
    c = cuenta(saldo="100.00")
    with pytest.raises(op.ClaveDesconocida):
        ya(op.ordenar_pago(cuenta_id=c, clave="noexiste@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    with pytest.raises(pix.ClaveInvalida):
        ya(op.ordenar_pago(cuenta_id=c, clave="esto no es clave", monto="30.00", referencia="p2", actor="t"))
    assert saldo(c) == "100.00" and ya(comandos.estado())["asientos"] == 1


def test_LA_MISMA_REFERENCIA_ES_EL_MISMO_PAGO():
    c = cuenta(saldo="100.00")
    a = ya(op.ordenar_pago(cuenta_id=c, clave="ana@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    b = ya(op.ordenar_pago(cuenta_id=c, clave="ana@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    assert a["id"] == b["id"] and saldo(c) == "70.00" and len(ya(op.listar())) == 1


def test_el_resultado_llega_dos_veces_y_se_liquida_una():
    c = cuenta(saldo="100.00")
    p = ya(op.ordenar_pago(cuenta_id=c, clave="tarda@ejemplo.test", monto="30.00", referencia="p1", actor="t"))
    vuelta()
    async def contesta(i):
        async with base.sesion() as s:
            return await op.recibir_aviso(s, riel="simulador", id_externo=f"acsc-{i}", tipo="estado_de_pago",
                                          carga={"end_to_end": p["end_to_end"], "estado": "ACSC", "motivo": None})
    ya(contesta(1)); ya(contesta(2)); vuelta()
    d = ya(op.detalle(p["id"]))
    assert d["estado"] == "liquidada"
    assert [h["estado"] for h in d["historial"]] == ["pendiente", "enviada", "liquidada"]
    assert balance()[1][plan.LIQUIDACION] == 7000 and ya(comandos.estado())["asientos"] == 3

    # y un RJCT tardío sobre un pago ya liquidado NO lo revierte: la plata ya
    # salió del banco, devolverla al titular sería inventarla
    async def contradice():
        async with base.sesion() as s:
            return await op.recibir_aviso(s, riel="simulador", id_externo="rjct-tarde", tipo="estado_de_pago",
                                          carga={"end_to_end": p["end_to_end"], "estado": "RJCT", "motivo": "AB03"})
    ya(contradice()); vuelta()
    d = ya(op.detalle(p["id"]))
    assert d["estado"] == "liquidada" and len(d["historial"]) == 3 and saldo(c) == "70.00"
    assert ya(comandos.estado())["asientos"] == 3


# ─── devoluciones ─────────────────────────────────────────────────────────

def test_UNA_DEVOLUCION_SALE_DEL_TITULAR_Y_NO_PASA_DEL_COBRO():
    c = cuenta()
    cobro = ya(op.crear_cobro(cuenta_id=c, monto="50.00", actor="t"))
    simular_pago(cobro, 5000); vuelta()
    assert saldo(c) == "50.00"
    with pytest.raises(op.OperacionInvalida):
        ya(op.devolver(operacion_id=cobro["id"], monto="10.00", motivo="XX99", actor="t"))
    dv = ya(op.devolver(operacion_id=cobro["id"], monto="20.00", motivo="MD06", actor="t"))
    assert dv["direccion"] == "devolucion" and dv["origen"] == cobro["id"] and dv["clave"] == "ana@ejemplo.test"
    assert saldo(c) == "30.00"
    vuelta()
    assert ya(op.detalle(dv["id"]))["estado"] == "liquidada"
    with pytest.raises(op.OperacionInvalida, match="no alcanza"):
        ya(op.devolver(operacion_id=cobro["id"], monto="40.00", motivo="MD06", actor="t"))
    ya(op.devolver(operacion_id=cobro["id"], monto="30.00", motivo="FR01", actor="t")); vuelta()
    assert saldo(c) == "0.00"
    cuadra, saldos = balance()
    assert cuadra and saldos[plan.TRANSITO] == 0 and saldos[plan.LIQUIDACION] == 0


def test_no_se_devuelve_un_cobro_que_no_se_pago():
    c = cuenta()
    cobro = ya(op.crear_cobro(cuenta_id=c, monto="50.00", actor="t"))
    with pytest.raises(op.OperacionInvalida, match="liquidó"):
        ya(op.devolver(operacion_id=cobro["id"], monto="10.00", motivo="MD06", actor="t"))


# ─── la frontera ──────────────────────────────────────────────────────────

def test_el_riel_no_toca_el_libro():
    """Un riel dice qué pasó; asentar es de `operaciones`. Si un riel
    importara los comandos o el libro, habría un segundo camino a la plata.
    Y `pix.py` es puro: formas y reglas, sin base ni red."""
    import pathlib
    import re
    sim = pathlib.Path(simulador.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+nucleo\.(comandos|libro)\b|from nucleo import .*\b(comandos|libro)\b", sim, re.M)
    puro = pathlib.Path(pix.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+(nucleo|sqlalchemy|httpx|requests)\b", puro, re.M)
