"""
El calendario de obligaciones: qué vence cuándo, y en qué está.

    No se guarda en ninguna tabla. Se calcula cada vez que se mira, desde
    lo que hay: los reportes generados y transmitidos, las comunicaciones al
    COAF, los incidentes relevantes sin comunicar, los reclamos sin
    responder. Un calendario guardado envejece; uno deducido no puede.

LOS PLAZOS

    Están todos en `PLAZOS`, con su fuente. Los de la norma que traen un
    número (diez días hábiles de la ouvidoria, D+1 del CCS, el último día
    hábil de agosto y febrero de la e-Financeira) son de la norma. Los que
    la norma deja abiertos («tempestivamente», «anualmente») o que dependen
    de cómo se entregue el documento, están puestos como política de la
    casa y MARCADOS «a confirmar»: el área de cumplimiento los confirma
    antes del primer envío de verdad, y el cambio es en este único lugar.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from nucleo import base
from nucleo.cumplimiento import dias_habiles, incidentes, ouvidoria
from nucleo.esquema import asientos, comunicaciones, cuentas
from nucleo.reportes import ccs, periodos, registro
from nucleo.riesgo import coaf
from nucleo.riesgo.monitoreo import HORA_DE_BRASIL

PENDIENTE, GENERADO, TRANSMITIDO, NO_CORRESPONDE = "pendiente", "generado", "transmitido", "no_corresponde"

# (periodicidad, cómo se calcula el vencimiento a partir del fin del período, fuente)
PLAZOS = {
    "balancete": ("mensual", "fin de mes + 30 días · a confirmar", "CADOC 4010"),
    "ccs": ("diaria", "el día hábil siguiente", "CCS, manual del BCB"),
    "efinanceira": ("semestral", "último día hábil de agosto (1º sem.) y de febrero (2º sem.)", "IN RFB 2.219/2024"),
    "no_ocurrencia": ("anual", "diez días hábiles después del cierre del año · a confirmar", "Circular BCB 3.978, art. 51"),
    "incidentes": ("anual", "31 de marzo del año siguiente · a confirmar", "Res. BCB 85/2021"),
    "ouvidoria": ("semestral", "fin de semestre + 30 días · a confirmar", "Res. CMN 4.860/2020"),
}
DIAS_PARA_EL_BALANCETE = 30
DIAS_PARA_EL_INFORME_DE_OUVIDORIA = 30
DIAS_HABILES_PARA_LA_NO_OCURRENCIA = 10
DIAS_DE_CCS_QUE_SE_MUESTRAN = 30


def vence(tipo: str, periodo: str) -> date:
    clase = {"balancete": periodos.MES, "ccs": periodos.DIA, "efinanceira": periodos.SEMESTRE,
             "no_ocurrencia": periodos.ANIO, "incidentes": periodos.ANIO, "ouvidoria": periodos.SEMESTRE}[tipo]
    _, fin = periodos.limites(clase, periodo)
    if tipo == "balancete":
        return fin + timedelta(days=DIAS_PARA_EL_BALANCETE)
    if tipo == "ccs":
        return dias_habiles.siguiente_habil(fin)
    if tipo == "efinanceira":
        return dias_habiles.ultimo_habil_del_mes(fin.year, 8) if fin.month == 6 else dias_habiles.ultimo_habil_del_mes(fin.year + 1, 2)
    if tipo == "no_ocurrencia":
        return dias_habiles.sumar_habiles(fin, DIAS_HABILES_PARA_LA_NO_OCURRENCIA)
    if tipo == "incidentes":
        return date(fin.year + 1, 3, 31)
    return fin + timedelta(days=DIAS_PARA_EL_INFORME_DE_OUVIDORIA)


def _renglon(tipo: str, periodo: str, estado: str, hoy: date, detalle: str = "", reporte=None, vence_en: Optional[date] = None) -> dict:
    v = vence_en or vence(tipo, periodo)
    return {"obligacion": tipo, "periodicidad": PLAZOS[tipo][0], "fuente": PLAZOS[tipo][2], "plazo": PLAZOS[tipo][1],
            "periodo": periodo, "vence": v.isoformat(), "dias": (v - hoy).days, "estado": estado,
            "vencido": estado == PENDIENTE and v < hoy, "detalle": detalle,
            "reporte": reporte["id"] if reporte else None, "protocolo": reporte["protocolo"] if reporte else None}


def _estado_de(reporte) -> str:
    if reporte is None:
        return PENDIENTE
    return TRANSMITIDO if reporte["protocolo"] else GENERADO


async def obligaciones(hoy: Optional[date] = None) -> list:
    """Un renglón por obligación y período ya terminado, desde que el
    núcleo tuvo actividad. Ordenado por vencimiento."""
    hoy = hoy or datetime.now(HORA_DE_BRASIL).date()
    salida = []
    async with base.sesion() as s:
        ultimas = await registro.ultimas_versiones(s)
        primer_asiento = (await s.execute(select(func.min(asientos.c.fecha)))).scalar_one_or_none()
        primera_cuenta = (await s.execute(select(func.min(cuentas.c.creada)))).scalar_one_or_none()
        inicio = min([d for d in (primer_asiento, ccs.dia_de_brasil(primera_cuenta) if primera_cuenta else None) if d] or [hoy])
        ayer = hoy - timedelta(days=1)
        # Balancete: cada mes terminado.
        for mes in periodos.meses_entre(inicio, ayer):
            if periodos.limites(periodos.MES, mes)[1] <= ayer:
                r = ultimas.get(("balancete", mes))
                salida.append(_renglon("balancete", mes, _estado_de(r), hoy, reporte=r))
        # e-Financeira y ouvidoria: cada semestre terminado.
        for sem in periodos.semestres_entre(inicio, ayer):
            if periodos.limites(periodos.SEMESTRE, sem)[1] <= ayer:
                for tipo in ("efinanceira", "ouvidoria"):
                    r = ultimas.get((tipo, sem))
                    salida.append(_renglon(tipo, sem, _estado_de(r), hoy, reporte=r))
        # Informe de incidentes y no ocurrencia: cada año terminado.
        enviadas = (await s.execute(select(comunicaciones))).all()
        for anio in range(inicio.year, hoy.year):
            r = ultimas.get(("incidentes", str(anio)))
            salida.append(_renglon("incidentes", str(anio), _estado_de(r), hoy, reporte=r))
            del_anio = [e for e in enviadas if (e.enviada_en.replace(tzinfo=timezone.utc) if e.enviada_en.tzinfo is None else e.enviada_en).year == anio]
            if any(e.tipo == coaf.COMUNICACION for e in del_anio):
                salida.append(_renglon("no_ocurrencia", str(anio), NO_CORRESPONDE, hoy, detalle="ese año sí hubo comunicaciones al COAF"))
            else:
                declarada = next((e for e in del_anio if e.tipo == coaf.NO_OCURRENCIA and e.periodo == anio), None) \
                    or next((e for e in enviadas if e.tipo == coaf.NO_OCURRENCIA and e.periodo == anio), None)
                salida.append(_renglon("no_ocurrencia", str(anio), TRANSMITIDO if declarada else PENDIENTE, hoy,
                                       detalle=f"acuse {declarada.acuse}" if declarada else "declarar al COAF que no hubo nada que comunicar"))
        # CCS: los últimos días con altas o bajas.
        desde_ccs = max(inicio, hoy - timedelta(days=DIAS_DE_CCS_QUE_SE_MUESTRAN))
        for d in periodos.dias_entre(desde_ccs, ayer):
            vinculos = await ccs.vinculos_del_dia(s, d.isoformat())
            if vinculos:
                r = ultimas.get(("ccs", d.isoformat()))
                salida.append(_renglon("ccs", d.isoformat(), _estado_de(r), hoy, reporte=r,
                                       detalle=f"{len(vinculos)} altas/bajas"))
    salida.sort(key=lambda x: (x["vence"], x["obligacion"]))
    return salida


async def acciones_con_plazo(hoy: Optional[date] = None) -> list:
    """Lo que no es un reporte pero también vence: comunicar un incidente
    relevante, responder un reclamo."""
    hoy = hoy or datetime.now(HORA_DE_BRASIL).date()
    salida = []
    for i in await incidentes.listar():
        if i["relevante"] and not i["protocolo"]:
            # El día del plazo en hora de Brasil, como «hoy»: si no, a las
            # diez de la noche de Brasilia el plazo ya parece de «mañana».
            v = ccs.dia_de_brasil(datetime.fromisoformat(i["comunicar_hasta"]))
            salida.append({"accion": "comunicar_incidente", "referencia": i["id"], "titulo": i["titulo"],
                           "vence": i["comunicar_hasta"], "dias": (v - hoy).days, "vencido": i["comunicacion_vencida"],
                           "fuente": "Res. BCB 85/2021 · política de la casa: 24 h"})
    for r in await ouvidoria.listar(hoy=hoy):
        if r["estado"] == ouvidoria.ABIERTO:
            v = date.fromisoformat(r["responder_hasta"])
            salida.append({"accion": "responder_reclamo", "referencia": r["id"], "titulo": f"{r['protocolo']} · {r['asunto']}",
                           "vence": r["responder_hasta"], "dias": (v - hoy).days, "vencido": r["vencido"],
                           "fuente": "Res. CMN 4.860/2020 · diez días hábiles"})
    salida.sort(key=lambda x: x["vence"])
    return salida


async def resumen(hoy: Optional[date] = None) -> dict:
    obl = await obligaciones(hoy)
    acc = await acciones_con_plazo(hoy)
    return {"pendientes": sum(1 for o in obl if o["estado"] == PENDIENTE), "vencidas": sum(1 for o in obl if o["vencido"]),
            "acciones": len(acc), "acciones_vencidas": sum(1 for a in acc if a["vencido"])}
