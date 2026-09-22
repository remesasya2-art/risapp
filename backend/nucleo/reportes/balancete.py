"""
El balancete mensual con códigos COSIF: el documento 4010 del CADOC.

    El CADOC es el catálogo de documentos que el Banco Central recibe; el
    4010 es el balancete patrimonial analítico de cada mes. Lleva, por cuenta
    del COSIF, el saldo al último día del mes, y una cabecera que dice de
    quién es, de qué mes, y si es la primera remesa (I, inclusão) o una que
    reemplaza a otra (S, substituição).

SOLO SOBRE DIAS CERRADOS

    Se genera cuando el último día del mes está cerrado en el libro. Antes
    de eso todavía se puede asentar con fecha de ese mes, y el balancete
    cambiaría después de mandado. El cierre es lo que lo vuelve definitivo.

CUADRA CONTRA EL LIBRO

    Sale de `libro.balance_de_comprobacion(hasta=fin de mes)`, y el archivo
    lleva la suma de debes y haberes y si son iguales. Si no cuadran no se
    genera: un balancete que no cuadra no es un balancete, es un error.
"""
import json
from datetime import date

from sqlalchemy import func, select

from nucleo import libro, plan
from nucleo.esquema import ACREEDORA, cierres
from nucleo.reportes import ReporteInvalido
from nucleo.reportes.periodos import MES, limites
from nucleo.riesgo.coaf import COMUNICANTE

DOCUMENTO = "CADOC 4010"


def _canonico(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=1, default=str)


async def ultimo_dia_cerrado(sesion):
    return (await sesion.execute(select(func.max(cierres.c.dia)))).scalar_one_or_none()


async def exigir_cerrado(sesion, hasta: date, que: str):
    ultimo = await ultimo_dia_cerrado(sesion)
    if ultimo is None or ultimo < hasta:
        raise ReporteInvalido(f"{que} exige el día {hasta.isoformat()} cerrado en el libro"
                              + (f" (último cierre: {ultimo.isoformat()})." if ultimo else " y no hay ningún día cerrado."))
    return ultimo


async def armar(sesion, *, periodo: str, version: int) -> tuple:
    """(archivo, resumen) del balancete del mes, o ReporteInvalido."""
    desde, hasta = limites(MES, periodo)
    await exigir_cerrado(sesion, hasta, "El balancete")
    balance = await libro.balance_de_comprobacion(sesion, hasta=hasta)
    if not balance["cuadra"]:
        raise ReporteInvalido(f"El libro no cuadra al {hasta.isoformat()}: debe {balance['total_debe']} ≠ haber {balance['total_haber']}.")
    por_cosif = {}
    for f in balance["filas"]:
        c = por_cosif.setdefault(plan.cosif_de(f["codigo"]), {"cosif": plan.cosif_de(f["codigo"]), "cuentas": [],
                                                            "natureza": "C" if f["naturaleza"] == ACREEDORA else "D", "saldo": 0})
        c["cuentas"].append({"codigo": f["codigo"], "nombre": f["nombre"], "saldo": f["saldo"]})
        c["saldo"] += f["saldo"]
    cierre = (await sesion.execute(select(cierres).where(cierres.c.dia <= hasta).order_by(cierres.c.dia.desc()).limit(1))).first()
    archivo = _canonico({
        "documento": DOCUMENTO,
        "nombre": "Balancete patrimonial analítico",
        "instituicao": COMUNICANTE,
        "data_base": periodo.replace("-", ""),
        "tipo_remessa": "I" if version == 1 else "S",
        "versao": version,
        "plan": "provisorio: los códigos COSIF los confirma el contador antes del primer envío de verdad",
        "contas": sorted(por_cosif.values(), key=lambda c: c["cosif"]),
        "total_debe": balance["total_debe"], "total_haber": balance["total_haber"], "cuadra": balance["cuadra"],
        "fechado_ate": {"dia": cierre.dia.isoformat(), "hasta_asiento": cierre.hasta_asiento, "hash_final": cierre.hash_final} if cierre else None,
    })
    resumen = {"contas": len(por_cosif), "total_debe": balance["total_debe"], "total_haber": balance["total_haber"],
               "cuadra": balance["cuadra"], "tipo_remessa": "I" if version == 1 else "S"}
    return archivo, resumen
