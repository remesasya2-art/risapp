"""
La e-Financeira: lo que la Receita Federal recibe de cada institución
sobre las cuentas de sus clientes, por semestre.

    Desde 2024 (Instrução Normativa RFB 2.219) las instituições de pagamento
    también la mandan. Por cada cuenta y cada mes: la suma de los créditos,
    la suma de los débitos y el saldo al fin del mes. Sólo los meses en que
    los créditos o los débitos superan el límite: R$ 2.000 para personas
    físicas, R$ 6.000 para jurídicas. Son números de la norma, no de la
    casa; por eso están en código y no en la configuración.

    El semestre se informa cuando su último día está cerrado en el libro,
    por el mismo motivo que el balancete.
"""
import json
from datetime import date

from sqlalchemy import select

from nucleo.esquema import asientos, cuentas, partidas, titulares
from nucleo.reportes.balancete import exigir_cerrado
from nucleo.reportes.periodos import SEMESTRE, limites, meses_entre
from nucleo.riesgo.coaf import COMUNICANTE

DOCUMENTO = "e-Financeira"
LIMITE_PERSONA_FISICA = 2000_00      # centavos, por mes
LIMITE_PERSONA_JURIDICA = 6000_00


def _canonico(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=1, default=str)


async def movimientos_por_cuenta_y_mes(sesion, hasta: date) -> dict:
    """{cuenta: {mes: [creditos, debitos]}} de todo el libro hasta `hasta`.
    Hasta el principio y no sólo el semestre, porque el saldo final es
    acumulado."""
    filas = (await sesion.execute(
        select(partidas.c.cuenta, asientos.c.fecha, partidas.c.debe, partidas.c.haber)
        .select_from(partidas.join(asientos, partidas.c.asiento == asientos.c.numero))
        .where(partidas.c.cuenta.isnot(None), asientos.c.fecha <= hasta))).all()
    salida = {}
    for cuenta, fecha, debe, haber in filas:
        mes = f"{fecha.year:04d}-{fecha.month:02d}"
        acumulado = salida.setdefault(cuenta, {}).setdefault(mes, [0, 0])
        acumulado[0] += int(haber)          # un haber en la cuenta del titular es un crédito para él
        acumulado[1] += int(debe)
    return salida


async def armar(sesion, *, periodo: str, version: int) -> tuple:
    desde, hasta = limites(SEMESTRE, periodo)
    await exigir_cerrado(sesion, hasta, "La e-Financeira")
    movimientos = await movimientos_por_cuenta_y_mes(sesion, hasta)
    personas = {t.id: t for t in (await sesion.execute(select(titulares))).all()}
    declarados = []
    for c in (await sesion.execute(select(cuentas).order_by(cuentas.c.id))).all():
        t = personas.get(c.titular_ref)
        limite = LIMITE_PERSONA_JURIDICA if (t and t.tipo == "cnpj") else LIMITE_PERSONA_FISICA
        por_mes = movimientos.get(c.id, {})
        saldo = sum(cr - db for m, (cr, db) in por_mes.items() if m < f"{desde.year:04d}-{desde.month:02d}")
        meses = []
        for mes in meses_entre(desde, hasta):
            creditos, debitos = por_mes.get(mes, (0, 0))
            saldo += creditos - debitos
            if creditos >= limite or debitos >= limite:
                meses.append({"mes": mes, "creditos": creditos, "debitos": debitos, "saldo_final": saldo})
        if meses:
            declarados.append({"cpf_cnpj": t.documento if t else None, "nome": t.nombre if t else c.titular_ref,
                               "conta": c.id, "meses": meses})
    archivo = _canonico({"documento": DOCUMENTO, "evento": "evtMovOpFin", "instituicao": COMUNICANTE,
                         "periodo": periodo, "versao": version,
                         "limites": {"pessoa_fisica": LIMITE_PERSONA_FISICA, "pessoa_juridica": LIMITE_PERSONA_JURIDICA},
                         "declarados": declarados})
    return archivo, {"declarados": len(declarados), "meses_informados": sum(len(d["meses"]) for d in declarados)}
