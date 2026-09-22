"""
El registro de incidentes: Resolución BCB 85/2021 (política de seguridad
cibernética y requisitos para contratar servicios de las instituições de
pagamento) y Resolución CMN 4.893/2021, que es la misma para bancos.

EL CAMINO DE UN INCIDENTE

    abierto ──(notas)──► cerrado
        └─ si es relevante: comunicar al BCB, con plazo, antes o después de cerrar

    Se abre cuando se detecta, con lo que se sabe: qué, desde cuándo, qué
    impacto, a cuántos clientes. Se anota lo que se va sabiendo. Se cierra
    UNA vez, con el fin, la causa y las acciones: eso no se edita después.
    Si estaba mal, se anota una nota que lo diga.

LO RELEVANTE SE COMUNICA

    La norma pide comunicar «tempestivamente» los incidentes relevantes. La
    palabra no trae un número; la política de la casa pone 24 horas desde
    que se registró, y el sistema lo muestra como plazo. Comunicar va por el
    mismo puerto que los reportes (`Transmisor`) y deja protocolo. Un
    incidente no relevante no se comunica: comunicarlo es un error, no una
    precaución.

EL INFORME ANUAL

    Una vez al año, el informe de incidentes del año: cuántos, de qué tipo,
    cuánto duraron, a cuántos tocaron, cuáles se comunicaron. Sale de este
    registro por `armar_informe`, y `reportes/registro.py` lo guarda como un
    reporte más, con versión y transmisión.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from nucleo import base
from nucleo.esquema import incidente_notas, incidentes
from nucleo.reportes import ReporteInvalido, transmisor as _transmisor
from nucleo.reportes.periodos import ANIO, limites
from nucleo.riesgo.coaf import COMUNICANTE

ABIERTO, CERRADO = "abierto", "cerrado"
TIPOS = ("indisponibilidad", "fuga_de_datos", "fraude", "ciberataque", "otro")
HORAS_PARA_COMUNICAR = 24            # política de la casa sobre el «tempestivamente» de la norma
DOCUMENTO_DE_LA_COMUNICACION = "Incidente relevante"
DOCUMENTO_DEL_INFORME = "Informe anual de incidentes"


class IncidenteInvalido(ValueError):
    pass


def _ahora():
    return datetime.now(timezone.utc)


def _iso(v):
    # SQLite devuelve los momentos sin zona (y son UTC); Postgres, con zona.
    # Se les pone la zona antes de mostrarlos para que salgan iguales.
    return _aware(v).isoformat() if v else None


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fila(i, notas=None, ahora=None) -> dict:
    ahora = ahora or _ahora()
    return {"id": i.id, "tipo": i.tipo, "titulo": i.titulo, "inicio": _iso(i.inicio), "fin": _iso(i.fin),
            "impacto": i.impacto, "clientes_afectados": i.clientes_afectados, "relevante": i.relevante,
            "estado": i.estado, "causa": i.causa, "acciones": i.acciones,
            "abierto_en": _iso(i.abierto_en), "abierto_por": i.abierto_por,
            "comunicar_hasta": _iso(i.comunicar_hasta), "comunicado_en": _iso(i.comunicado_en),
            "comunicado_por": i.comunicado_por, "protocolo": i.protocolo,
            "cerrado_en": _iso(i.cerrado_en), "cerrado_por": i.cerrado_por,
            "comunicacion_vencida": bool(i.relevante and not i.protocolo and i.comunicar_hasta and _aware(i.comunicar_hasta) < ahora),
            "notas": notas or []}


async def _incidente(sesion, incidente_id: str):
    i = (await sesion.execute(select(incidentes).where(incidentes.c.id == incidente_id))).first()
    if i is None:
        raise IncidenteInvalido(f"No existe el incidente {incidente_id}.")
    return i


async def _anotar(sesion, incidente_id: str, autor: str, texto: str):
    await sesion.execute(incidente_notas.insert().values(incidente=incidente_id, autor=autor, texto=texto))


async def abrir(*, tipo: str, titulo: str, impacto: str, clientes_afectados: int, relevante: bool, actor: str,
                inicio: Optional[datetime] = None, ahora: Optional[datetime] = None) -> dict:
    ahora = ahora or _ahora()
    if tipo not in TIPOS:
        raise IncidenteInvalido(f"Tipo de incidente desconocido: «{tipo}».")
    if clientes_afectados < 0:
        raise IncidenteInvalido("Los clientes afectados no pueden ser negativos.")
    inicio = inicio or ahora
    if _aware(inicio) > ahora:
        raise IncidenteInvalido("Un incidente no empieza en el futuro.")
    id_ = f"inc_{secrets.token_hex(6)}"
    async with base.sesion() as s:
        await s.execute(incidentes.insert().values(
            id=id_, tipo=tipo, titulo=titulo.strip(), inicio=inicio, impacto=impacto.strip(),
            clientes_afectados=clientes_afectados, relevante=relevante, estado=ABIERTO,
            abierto_en=ahora, abierto_por=actor,
            comunicar_hasta=(ahora + timedelta(hours=HORAS_PARA_COMUNICAR)) if relevante else None))
        await _anotar(s, id_, actor, "Incidente registrado" + (" · RELEVANTE: se comunica al BCB" if relevante else ""))
        return await detalle_(id_, sesion=s, ahora=ahora)


async def anotar(incidente_id: str, *, autor: str, texto: str) -> dict:
    if not texto.strip():
        raise IncidenteInvalido("La nota está vacía.")
    async with base.sesion() as s:
        await _incidente(s, incidente_id)
        await _anotar(s, incidente_id, autor, texto.strip())
        return await detalle_(incidente_id, sesion=s)


def armar_comunicacion(i, notas: list) -> str:
    return json.dumps({
        "documento": DOCUMENTO_DE_LA_COMUNICACION, "instituicao": COMUNICANTE, "incidente": i.id,
        "tipo": i.tipo, "titulo": i.titulo, "inicio": _iso(i.inicio), "fim": _iso(i.fin),
        "impacto": i.impacto, "clientes_afetados": i.clientes_afectados, "estado": i.estado,
        "causa": i.causa, "acoes": i.acciones,
        "linha_do_tempo": [{"quando": _iso(n.momento), "quem": n.autor, "o_que": n.texto} for n in notas],
    }, sort_keys=True, ensure_ascii=False, indent=1, default=str)


async def comunicar(incidente_id: str, *, actor: str, ahora: Optional[datetime] = None) -> dict:
    """Manda la comunicación al BCB por el puerto y guarda el protocolo. Sólo
    un incidente relevante, y una sola vez."""
    ahora = ahora or _ahora()
    puerto = _transmisor()
    async with base.sesion() as s:
        i = await _incidente(s, incidente_id)
        if not i.relevante:
            raise IncidenteInvalido("Un incidente no relevante no se comunica al BCB.")
        if i.protocolo:
            raise IncidenteInvalido(f"El incidente ya se comunicó (protocolo {i.protocolo}).")
        notas = (await s.execute(select(incidente_notas).where(incidente_notas.c.incidente == incidente_id).order_by(incidente_notas.c.id))).all()
        archivo = armar_comunicacion(i, notas)
        protocolo = await puerto.transmitir(s, documento=DOCUMENTO_DE_LA_COMUNICACION, periodo=i.id, archivo=archivo)
        await s.execute(incidentes.update().where(incidentes.c.id == incidente_id).values(
            comunicado_en=ahora, comunicado_por=actor, protocolo=protocolo))
        await _anotar(s, incidente_id, actor, f"Comunicado al BCB por {puerto.nombre}; protocolo {protocolo}")
        return await detalle_(incidente_id, sesion=s, ahora=ahora)


async def cerrar(incidente_id: str, *, actor: str, causa: str, acciones: str, fin: Optional[datetime] = None,
                 ahora: Optional[datetime] = None) -> dict:
    """Una vez. Con el fin, la causa y las acciones."""
    ahora = ahora or _ahora()
    if not causa.strip() or not acciones.strip():
        raise IncidenteInvalido("Cerrar exige la causa y las acciones tomadas.")
    fin = fin or ahora
    async with base.sesion() as s:
        i = await _incidente(s, incidente_id)
        if i.estado != ABIERTO:
            raise IncidenteInvalido("El incidente ya está cerrado; lo que falte se agrega como nota.")
        if _aware(fin) < _aware(i.inicio):
            raise IncidenteInvalido("El fin no puede ser anterior al inicio.")
        await s.execute(incidentes.update().where(incidentes.c.id == incidente_id).values(
            estado=CERRADO, fin=fin, causa=causa.strip(), acciones=acciones.strip(), cerrado_en=ahora, cerrado_por=actor))
        await _anotar(s, incidente_id, actor, "Cerrado. Causa: " + causa.strip())
        return await detalle_(incidente_id, sesion=s, ahora=ahora)


# ─── el informe anual ─────────────────────────────────────────────────────

async def armar_informe(sesion, *, periodo: str, version: int, ahora: Optional[datetime] = None) -> tuple:
    """(archivo, resumen) del informe del año. Sólo de un año terminado."""
    ahora = ahora or _ahora()
    desde, hasta = limites(ANIO, periodo)
    if ahora.date() <= hasta:
        raise ReporteInvalido(f"El informe de incidentes de {periodo} se arma cuando el año terminó.")
    filas = (await sesion.execute(select(incidentes).order_by(incidentes.c.inicio))).all()
    del_anio = [i for i in filas if desde <= _aware(i.inicio).date() <= hasta]
    por_tipo = {}
    for i in del_anio:
        por_tipo[i.tipo] = por_tipo.get(i.tipo, 0) + 1
    duraciones = [(_aware(i.fin) - _aware(i.inicio)).total_seconds() / 3600 for i in del_anio if i.fin]
    archivo = json.dumps({
        "documento": DOCUMENTO_DEL_INFORME, "instituicao": COMUNICANTE, "ano": periodo, "versao": version,
        "total": len(del_anio), "por_tipo": por_tipo, "relevantes": sum(1 for i in del_anio if i.relevante),
        "comunicados": sum(1 for i in del_anio if i.protocolo),
        "abertos_ao_fim_do_ano": sum(1 for i in del_anio if not i.fin or _aware(i.fin).date() > hasta),
        "horas_de_indisponibilidade": round(sum(d for d, i in zip(duraciones, [x for x in del_anio if x.fin]) if i.tipo == "indisponibilidad"), 2),
        "clientes_afetados": sum(i.clientes_afectados for i in del_anio),
        "incidentes": [{"id": i.id, "tipo": i.tipo, "titulo": i.titulo, "inicio": _iso(i.inicio), "fim": _iso(i.fin),
                        "clientes_afetados": i.clientes_afectados, "relevante": i.relevante, "protocolo": i.protocolo,
                        "causa": i.causa, "acoes": i.acciones} for i in del_anio],
    }, sort_keys=True, ensure_ascii=False, indent=1, default=str)
    return archivo, {"total": len(del_anio), "relevantes": sum(1 for i in del_anio if i.relevante),
                     "comunicados": sum(1 for i in del_anio if i.protocolo)}


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle_(incidente_id: str, sesion=None, ahora: Optional[datetime] = None) -> dict:
    async def _(s):
        i = await _incidente(s, incidente_id)
        notas = (await s.execute(select(incidente_notas).where(incidente_notas.c.incidente == incidente_id).order_by(incidente_notas.c.id))).all()
        return _fila(i, [{"autor": n.autor, "texto": n.texto, "momento": _iso(n.momento)} for n in notas], ahora)
    if sesion is not None:
        return await _(sesion)
    async with base.sesion() as s:
        return await _(s)


detalle = detalle_


async def listar(limite: int = 50, ahora: Optional[datetime] = None) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(incidentes).order_by(incidentes.c.abierto_en.desc(), incidentes.c.id.desc()).limit(limite))).all()
        ids = [i.id for i in filas]
        notas = {}
        if ids:
            for n in (await s.execute(select(incidente_notas).where(incidente_notas.c.incidente.in_(ids)).order_by(incidente_notas.c.id))).all():
                notas.setdefault(n.incidente, []).append({"autor": n.autor, "texto": n.texto, "momento": _iso(n.momento)})
        return [_fila(i, notas.get(i.id), ahora) for i in filas]


async def resumen(ahora: Optional[datetime] = None) -> dict:
    salida = {ABIERTO: 0, CERRADO: 0, "relevantes_sin_comunicar": 0, "comunicacion_vencida": 0}
    async with base.sesion() as s:
        for i in (await s.execute(select(incidentes))).all():
            salida[i.estado] += 1
            if i.relevante and not i.protocolo:
                salida["relevantes_sin_comunicar"] += 1
                if _fila(i, ahora=ahora)["comunicacion_vencida"]:
                    salida["comunicacion_vencida"] += 1
    return salida
