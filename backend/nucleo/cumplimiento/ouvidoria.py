"""
La ouvidoria: Resolución CMN 4.860/2020.

    La ouvidoria es la segunda instancia: el cliente ya reclamó por los
    canales comunes (la mesa de ayuda, acá) y no quedó conforme, o vino
    directo por el Banco Central o por el Procon. Cada reclamo recibe un
    protocolo propio que se dicta por teléfono, y tiene DIEZ DIAS HABILES
    para una respuesta conclusiva (art. 6º). La respuesta dice si fue
    procedente, improcedente o en parte.

    Cuando viene de la mesa de ayuda, se cita el número del caso («S-000123»)
    como texto: la ouvidoria no lee la base de la mesa de ayuda, y el núcleo
    no importa nada de la aplicación. Es la frontera del paquete.

EL INFORME SEMESTRAL

    Cuántos reclamos, por canal, por resultado, cuántos respondidos en
    plazo, cuántos días tardaron en promedio. Lo guarda `reportes/registro.py`
    como un reporte más, por `armar_informe`.
"""
import json
import secrets
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from nucleo import base
from nucleo.cumplimiento import dias_habiles
from nucleo.esquema import reclamos
from nucleo.reportes import ReporteInvalido
from nucleo.reportes.periodos import SEMESTRE, limites
from nucleo.riesgo.coaf import COMUNICANTE
from nucleo.riesgo.monitoreo import HORA_DE_BRASIL

ABIERTO, RESPONDIDO = "abierto", "respondido"
CANALES = ("telefono", "correo", "panel", "bcb", "procon")
RESULTADOS = ("procedente", "improcedente", "parcial")
DIAS_HABILES_PARA_RESPONDER = 10       # art. 6º de la Resolución 4.860
DOCUMENTO_DEL_INFORME = "Informe semestral de la ouvidoria"


class ReclamoInvalido(ValueError):
    pass


def _ahora():
    return datetime.now(timezone.utc)


def _iso(v):
    # SQLite devuelve los momentos sin zona (y son UTC); Postgres, con zona.
    # Se les pone la zona antes de mostrarlos para que salgan iguales.
    return _aware(v).isoformat() if v else None


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _dia_de_brasil(momento) -> date:
    return _aware(momento).astimezone(HORA_DE_BRASIL).date()


def _fila(r, hoy: Optional[date] = None) -> dict:
    hoy = hoy or datetime.now(HORA_DE_BRASIL).date()
    return {"id": r.id, "protocolo": r.protocolo, "titular": r.titular, "canal": r.canal, "asunto": r.asunto,
            "descripcion": r.descripcion, "caso_soporte": r.caso_soporte, "estado": r.estado,
            "abierto_en": _iso(r.abierto_en), "abierto_por": r.abierto_por,
            "responder_hasta": r.responder_hasta.isoformat(), "respuesta": r.respuesta, "resultado": r.resultado,
            "respondido_en": _iso(r.respondido_en), "respondido_por": r.respondido_por,
            "vencido": r.estado == ABIERTO and r.responder_hasta < hoy,
            "en_plazo": (_dia_de_brasil(r.respondido_en) <= r.responder_hasta) if r.respondido_en else None}


async def _reclamo(sesion, reclamo_id: str):
    r = (await sesion.execute(select(reclamos).where(reclamos.c.id == reclamo_id))).first()
    if r is None:
        raise ReclamoInvalido(f"No existe el reclamo {reclamo_id}.")
    return r


async def _proximo_protocolo(sesion, anio: int) -> str:
    """«OUV-2026-000001», correlativo por año. El único de la tabla frena
    a dos que quieran el mismo número en el mismo instante."""
    prefijo = f"OUV-{anio}-"
    cuantos = (await sesion.execute(select(func.count()).select_from(reclamos).where(reclamos.c.protocolo.like(prefijo + "%")))).scalar_one()
    return f"{prefijo}{int(cuantos) + 1:06d}"


async def abrir(*, canal: str, asunto: str, descripcion: str, actor: str, titular: Optional[str] = None,
                caso_soporte: Optional[str] = None, ahora: Optional[datetime] = None) -> dict:
    ahora = ahora or _ahora()
    if canal not in CANALES:
        raise ReclamoInvalido(f"Canal desconocido: «{canal}».")
    if not asunto.strip() or not descripcion.strip():
        raise ReclamoInvalido("Un reclamo lleva asunto y descripción.")
    hoy = _dia_de_brasil(ahora)
    async with base.sesion() as s:
        protocolo = await _proximo_protocolo(s, hoy.year)
        id_ = f"ouv_{secrets.token_hex(6)}"
        await s.execute(reclamos.insert().values(
            id=id_, protocolo=protocolo, titular=titular, canal=canal, asunto=asunto.strip(),
            descripcion=descripcion.strip(), caso_soporte=(caso_soporte or "").strip() or None, estado=ABIERTO,
            abierto_en=ahora, abierto_por=actor,
            responder_hasta=dias_habiles.sumar_habiles(hoy, DIAS_HABILES_PARA_RESPONDER)))
        return _fila(await _reclamo(s, id_), hoy)


async def responder(reclamo_id: str, *, actor: str, respuesta: str, resultado: str, ahora: Optional[datetime] = None) -> dict:
    """La respuesta conclusiva. Una vez."""
    ahora = ahora or _ahora()
    if resultado not in RESULTADOS:
        raise ReclamoInvalido(f"Resultado desconocido: «{resultado}».")
    if not respuesta.strip():
        raise ReclamoInvalido("La respuesta está vacía.")
    async with base.sesion() as s:
        r = await _reclamo(s, reclamo_id)
        if r.estado != ABIERTO:
            raise ReclamoInvalido(f"El reclamo {r.protocolo} ya fue respondido.")
        await s.execute(reclamos.update().where(reclamos.c.id == reclamo_id).values(
            estado=RESPONDIDO, respuesta=respuesta.strip(), resultado=resultado, respondido_en=ahora, respondido_por=actor))
        return _fila(await _reclamo(s, reclamo_id), _dia_de_brasil(ahora))


# ─── el informe semestral ─────────────────────────────────────────────────

async def armar_informe(sesion, *, periodo: str, version: int, ahora: Optional[datetime] = None) -> tuple:
    ahora = ahora or _ahora()
    desde, hasta = limites(SEMESTRE, periodo)
    if ahora.date() <= hasta:
        raise ReporteInvalido(f"El informe de la ouvidoria de {periodo} se arma cuando el semestre terminó.")
    filas = [r for r in (await sesion.execute(select(reclamos).order_by(reclamos.c.abierto_en))).all()
             if desde <= _dia_de_brasil(r.abierto_en) <= hasta]
    por_canal, por_resultado = {}, {}
    for r in filas:
        por_canal[r.canal] = por_canal.get(r.canal, 0) + 1
        if r.resultado:
            por_resultado[r.resultado] = por_resultado.get(r.resultado, 0) + 1
    respondidos = [r for r in filas if r.respondido_en]
    en_plazo = sum(1 for r in respondidos if _dia_de_brasil(r.respondido_en) <= r.responder_hasta)
    dias = [(_dia_de_brasil(r.respondido_en) - _dia_de_brasil(r.abierto_en)).days for r in respondidos]
    archivo = json.dumps({
        "documento": DOCUMENTO_DEL_INFORME, "instituicao": COMUNICANTE, "semestre": periodo, "versao": version,
        "total": len(filas), "por_canal": por_canal, "por_resultado": por_resultado,
        "respondidos": len(respondidos), "respondidos_no_prazo": en_plazo,
        "abertos_ao_fim": sum(1 for r in filas if not r.respondido_en or _dia_de_brasil(r.respondido_en) > hasta),
        "dias_medios_de_resposta": round(sum(dias) / len(dias), 1) if dias else None,
        "prazo_em_dias_uteis": DIAS_HABILES_PARA_RESPONDER,
        "reclamacoes": [{"protocolo": r.protocolo, "canal": r.canal, "assunto": r.asunto, "aberto_em": _iso(r.abierto_en),
                         "respondido_em": _iso(r.respondido_en), "resultado": r.resultado, "caso_suporte": r.caso_soporte} for r in filas],
    }, sort_keys=True, ensure_ascii=False, indent=1, default=str)
    return archivo, {"total": len(filas), "respondidos": len(respondidos), "en_plazo": en_plazo}


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle(reclamo_id: str) -> dict:
    async with base.sesion() as s:
        return _fila(await _reclamo(s, reclamo_id))


async def listar(limite: int = 50, hoy: Optional[date] = None) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(reclamos).order_by(reclamos.c.abierto_en.desc(), reclamos.c.id.desc()).limit(limite))).all()
        return [_fila(r, hoy) for r in filas]


async def resumen(hoy: Optional[date] = None) -> dict:
    salida = {ABIERTO: 0, RESPONDIDO: 0, "vencidos": 0}
    async with base.sesion() as s:
        for r in (await s.execute(select(reclamos))).all():
            salida[r.estado] += 1
            if _fila(r, hoy)["vencido"]:
                salida["vencidos"] += 1
    return salida
