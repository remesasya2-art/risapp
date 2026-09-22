"""
El CCS: Cadastro de Clientes do Sistema Financeiro Nacional.

    El Banco Central mantiene un registro de quién tiene relación con qué
    institución (no de los saldos: sólo de que la relación existe, desde
    cuándo y hasta cuándo). Cada institución le informa las altas y las bajas
    del día, al día siguiente. Un día sin altas ni bajas no se informa.

    Acá una «relación» es una cuenta de pago de un titular: empieza cuando
    la cuenta se crea, termina cuando se cierra (`cerrada_en`). El día se
    mide en hora de Brasil, porque es un registro brasileño.
"""
import json
from datetime import date, timezone

from sqlalchemy import select

from nucleo.esquema import cuentas, titulares
from nucleo.reportes.periodos import DIA, limites
from nucleo.riesgo.coaf import COMUNICANTE
from nucleo.riesgo.monitoreo import HORA_DE_BRASIL

DOCUMENTO = "CCS"
TIPO_DE_RELACION = "conta de pagamento"


def _canonico(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=1, default=str)


def dia_de_brasil(momento) -> date:
    """El día, en hora de Brasil, de un momento guardado. SQLite devuelve
    los momentos sin zona (y son UTC); Postgres los devuelve con zona. Por
    eso el día se calcula acá y no en SQL: en SQL la comparación de un
    momento sin zona contra una hora de Brasil corre tres horas."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(HORA_DE_BRASIL).date()


async def vinculos_del_dia(sesion, periodo: str) -> list:
    dia, _ = limites(DIA, periodo)
    nombres = {t.id: t for t in (await sesion.execute(select(titulares))).all()}
    salida = []
    for c in (await sesion.execute(select(cuentas).order_by(cuentas.c.creada, cuentas.c.id))).all():
        t = nombres.get(c.titular_ref)
        persona = {"cpf_cnpj": t.documento if t else None, "nome": t.nombre if t else c.titular_ref}
        if dia_de_brasil(c.creada) == dia:
            salida.append({"operacao": "inclusao", **persona, "tipo": TIPO_DE_RELACION, "conta": c.id,
                           "inicio": dia.isoformat(), "fim": None})
        if c.cerrada_en is not None and dia_de_brasil(c.cerrada_en) == dia:
            salida.append({"operacao": "exclusao", **persona, "tipo": TIPO_DE_RELACION, "conta": c.id,
                           "inicio": dia_de_brasil(c.creada).isoformat(), "fim": dia.isoformat()})
    return salida


async def armar(sesion, *, periodo: str, version: int):
    """(archivo, resumen) del CCS del día, o None si ese día no hubo altas
    ni bajas: un archivo vacío no se manda."""
    vinculos = await vinculos_del_dia(sesion, periodo)
    if not vinculos:
        return None
    archivo = _canonico({"documento": DOCUMENTO, "nombre": "Cadastro de Clientes do SFN · movimento diário",
                         "instituicao": COMUNICANTE, "data": periodo, "versao": version, "vinculos": vinculos})
    return archivo, {"altas": sum(1 for v in vinculos if v["operacao"] == "inclusao"),
                     "bajas": sum(1 for v in vinculos if v["operacao"] == "exclusao")}
