"""
El registro de reportes: generar, guardar tal cual, transmitir, mirar.

UNA VERSION NUEVA, NUNCA UNA EDICION

    Generar dos veces el mismo período no pisa nada: deja la versión 2, y
    el archivo lo dice (`tipo_remessa: S`, substituição). Lo que ya se
    transmitió queda como se transmitió; es lo que un supervisor va a pedir
    ver. No hay función que borre ni edite un reporte.

LO QUE GENERA LA COLA

    Cuando se cierra un día, `generar_lo_pendiente(dia)` mira qué períodos
    quedaron completos con ese cierre y genera lo que falte: el CCS de cada
    día nuevo con altas o bajas, el balancete de cada mes terminado, la
    e-Financeira de cada semestre terminado. Es idempotente: sólo genera lo
    que no tiene ninguna versión. Rectificar es una decisión de una persona,
    desde la pestaña.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from nucleo import base
from nucleo.esquema import asientos, cierres, cuentas, reportes
from nucleo.reportes import ReporteInvalido, transmisor as _transmisor
from nucleo.reportes import balancete, ccs, efinanceira, periodos
from nucleo.cumplimiento import incidentes as _incidentes, ouvidoria as _ouvidoria

BALANCETE, CCS, EFINANCEIRA, INCIDENTES, OUVIDORIA = "balancete", "ccs", "efinanceira", "incidentes", "ouvidoria"

# Por tipo: la clase de período que lleva, cómo lo llama el regulador y
# quién arma el archivo. Un tipo nuevo se agrega acá y en ningún otro lado.
TIPOS = {
    BALANCETE: (periodos.MES, balancete.DOCUMENTO, balancete.armar),
    CCS: (periodos.DIA, ccs.DOCUMENTO, ccs.armar),
    EFINANCEIRA: (periodos.SEMESTRE, efinanceira.DOCUMENTO, efinanceira.armar),
    # Los informes del cumplimiento (nucleo/cumplimiento/): del registro de
    # incidentes, una vez al año; de la ouvidoria, una vez por semestre.
    INCIDENTES: (periodos.ANIO, _incidentes.DOCUMENTO_DEL_INFORME, _incidentes.armar_informe),
    OUVIDORIA: (periodos.SEMESTRE, _ouvidoria.DOCUMENTO_DEL_INFORME, _ouvidoria.armar_informe),
}

# Los que sólo se arman con el período TERMINADO, y por eso preguntan la
# fecha. Se les pasa la de quien pide el informe: sin ella miraban el reloj de
# verdad, y `generar(..., ahora=...)` decía una fecha y el control usaba otra.
# Así se escribió un test que pasaba sólo mientras el semestre siguiente no
# hubiera terminado, y que el 1 de enero de 2027 se iba a poner rojo solo.
_PIDEN_LA_FECHA = {INCIDENTES, OUVIDORIA}


def _ahora():
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if v else None


def _fila(r, con_archivo: bool = False) -> dict:
    salida = {"id": r.id, "tipo": r.tipo, "periodo": r.periodo, "version": r.version, "documento": r.documento,
              "resumen": json.loads(r.resumen), "generado_en": _iso(r.generado_en), "generado_por": r.generado_por,
              "transmitido_en": _iso(r.transmitido_en), "transmitido_por": r.transmitido_por,
              "protocolo": r.protocolo, "transmisor": r.transmisor,
              "estado": "transmitido" if r.protocolo else "generado"}
    if con_archivo:
        salida["archivo"] = r.archivo
    return salida


async def _reporte(sesion, reporte_id: int):
    r = (await sesion.execute(select(reportes).where(reportes.c.id == reporte_id))).first()
    if r is None:
        raise ReporteInvalido(f"No existe el reporte {reporte_id}.")
    return r


async def _generar_en(sesion, tipo: str, periodo: str, *, actor: str, ahora: datetime, solo_si_falta: bool = False):
    if tipo not in TIPOS:
        raise ReporteInvalido(f"No existe el tipo de reporte «{tipo}».")
    clase, documento, armar = TIPOS[tipo]
    periodos.limites(clase, periodo)                         # PeriodoInvalido si no tiene la forma
    ultima = (await sesion.execute(select(func.max(reportes.c.version)).where(
        reportes.c.tipo == tipo, reportes.c.periodo == periodo))).scalar_one_or_none() or 0
    if solo_si_falta and ultima:
        return None
    extra = {"ahora": ahora} if tipo in _PIDEN_LA_FECHA else {}
    armado = await armar(sesion, periodo=periodo, version=ultima + 1, **extra)
    if armado is None:
        raise ReporteInvalido(f"El {periodo} no hubo altas ni bajas: el CCS de ese día no se manda.")
    archivo, resumen = armado
    r = await sesion.execute(reportes.insert().values(
        tipo=tipo, periodo=periodo, version=ultima + 1, documento=documento, archivo=archivo,
        resumen=json.dumps(resumen, ensure_ascii=False), generado_en=ahora, generado_por=actor))
    return _fila(await _reporte(sesion, r.inserted_primary_key[0]), con_archivo=True)


async def generar(tipo: str, periodo: str, *, actor: str, ahora: Optional[datetime] = None) -> dict:
    """Una versión nueva del reporte del período. Lanza ReporteInvalido (o
    PeriodoInvalido) si no se puede."""
    async with base.sesion() as s:
        return await _generar_en(s, tipo, periodo, actor=actor, ahora=ahora or _ahora())


async def transmitir(reporte_id: int, *, actor: str, ahora: Optional[datetime] = None) -> dict:
    """Manda la versión por el puerto y guarda el protocolo. Una vez."""
    ahora = ahora or _ahora()
    puerto = _transmisor()
    async with base.sesion() as s:
        r = await _reporte(s, reporte_id)
        if r.protocolo:
            raise ReporteInvalido(f"El reporte {reporte_id} ya se transmitió (protocolo {r.protocolo}).")
        protocolo = await puerto.transmitir(s, documento=r.documento, periodo=r.periodo, archivo=r.archivo)
        await s.execute(reportes.update().where(reportes.c.id == reporte_id).values(
            transmitido_en=ahora, transmitido_por=actor, protocolo=protocolo, transmisor=puerto.nombre))
        return _fila(await _reporte(s, reporte_id), con_archivo=True)


async def generar_lo_pendiente(dia: date, *, actor: str = "cola", ahora: Optional[datetime] = None) -> list:
    """Lo que el cierre de `dia` dejó listo para generar y todavía no tiene
    ninguna versión. Devuelve una línea por reporte generado."""
    ahora = ahora or _ahora()
    hechos = []
    async with base.sesion() as s:
        ultimo = await balancete.ultimo_dia_cerrado(s)
        if ultimo is None or ultimo < dia:
            return hechos                                    # el día no está cerrado: no hay nada definitivo
        primer_asiento = (await s.execute(select(func.min(asientos.c.fecha)))).scalar_one_or_none()
        primera_cuenta = (await s.execute(select(func.min(cuentas.c.creada)))).scalar_one_or_none()
        anterior = (await s.execute(select(func.max(cierres.c.dia)).where(cierres.c.dia < dia))).scalar_one_or_none()
        if anterior is not None:
            desde_ccs = anterior + timedelta(days=1)
        elif primera_cuenta is not None:
            desde_ccs = ccs.dia_de_brasil(primera_cuenta)
        else:
            desde_ccs = dia
        for d in periodos.dias_entre(min(desde_ccs, dia), dia):
            try:
                r = await _generar_en(s, CCS, d.isoformat(), actor=actor, ahora=ahora, solo_si_falta=True)
            except ReporteInvalido:
                continue                                     # sin altas ni bajas: no se manda
            if r:
                hechos.append(f"ccs {d.isoformat()}")
        if primer_asiento is not None:
            for mes in periodos.meses_entre(primer_asiento, dia):
                if periodos.limites(periodos.MES, mes)[1] <= dia:
                    r = await _generar_en(s, BALANCETE, mes, actor=actor, ahora=ahora, solo_si_falta=True)
                    if r:
                        hechos.append(f"balancete {mes}")
            for sem in periodos.semestres_entre(primer_asiento, dia):
                if periodos.limites(periodos.SEMESTRE, sem)[1] <= dia:
                    r = await _generar_en(s, EFINANCEIRA, sem, actor=actor, ahora=ahora, solo_si_falta=True)
                    if r:
                        hechos.append(f"efinanceira {sem}")
    return hechos


async def generar_del_cierre(carga: dict) -> str:
    """El manejador de la cola para «dia_cerrado»."""
    hechos = await generar_lo_pendiente(date.fromisoformat(carga["dia"]))
    return ("generados: " + ", ".join(hechos)) if hechos else "nada nuevo que generar"


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle(reporte_id: int) -> dict:
    async with base.sesion() as s:
        return _fila(await _reporte(s, reporte_id), con_archivo=True)


async def listar(limite: int = 100) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(reportes).order_by(reportes.c.id.desc()).limit(limite))).all()
        return [_fila(r) for r in filas]


async def ultimas_versiones(sesion) -> dict:
    """{(tipo, periodo): fila de la última versión}. Lo usa el calendario."""
    filas = (await sesion.execute(select(reportes).order_by(reportes.c.tipo, reportes.c.periodo, reportes.c.version))).all()
    return {(r.tipo, r.periodo): _fila(r) for r in filas}


async def resumen() -> dict:
    salida = {t: {"generados": 0, "transmitidos": 0} for t in TIPOS}
    async with base.sesion() as s:
        for r in (await s.execute(select(reportes))).all():
            salida.setdefault(r.tipo, {"generados": 0, "transmitidos": 0})
            salida[r.tipo]["generados"] += 1
            if r.protocolo:
                salida[r.tipo]["transmitidos"] += 1
    return salida
