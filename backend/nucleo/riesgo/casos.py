"""
El expediente de caso: lo que pasa cuando una alerta, una lista o una
persona dicen «esto hay que mirarlo».

EL CAMINO DE UN CASO

    abierto ──► en_analisis ──► concluido ──► comunicado
                                          └─► archivado

    Se abre solo (una alerta, un cruce confirmado) o a mano. Un analista lo
    toma. Anota. Concluye: con comunicación al COAF o sin ella. Si es sin,
    queda archivado con su conclusión. Si es con, otra persona la aprueba
    —cuatro ojos— y recién ahí se manda y queda el acuse.

LOS PLAZOS (Circular 3.978)

    Analizar: 45 días desde que se abre. Comunicar: 24 horas desde que se
    concluye. El sistema los calcula y los muestra; una persona no tiene
    que acordarse. Y una vez al año, la comunicación de no ocurrencia.

UN CASO ABIERTO POR TITULAR

    Una segunda alerta sobre el mismo titular no abre un segundo caso: se
    anexa al abierto, como nota. Es lo que un analista quiere ver: todo lo
    de una persona junto, no diez expedientes sueltos.

CUATRO OJOS

    Quien aprueba la comunicación no puede ser quien concluyó. Es la regla
    más simple que existe contra el error de una sola persona, y contra la
    presión sobre una sola persona. El sistema la hace cumplir.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from nucleo import base
from nucleo.esquema import alertas, caso_notas, casos, comunicaciones, cuentas, operaciones, titulares
from nucleo.riesgo import coaf, comunicador as _comunicador

ABIERTO, EN_ANALISIS, CONCLUIDO, COMUNICADO, ARCHIVADO = "abierto", "en_analisis", "concluido", "comunicado", "archivado"
ORIGENES = ("alerta", "lista", "manual")

DIAS_PARA_ANALIZAR = 45
HORAS_PARA_COMUNICAR = 24


class CasoInvalido(ValueError):
    pass


def _nuevo_id() -> str:
    return "caso_" + secrets.token_hex(6)


def _ahora():
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if v else None


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fila(c, notas=None, alertas_=None, ahora=None) -> dict:
    ahora = ahora or _ahora()
    return {"id": c.id, "titular": c.titular, "origen": c.origen, "estado": c.estado, "analista": c.analista,
            "detalle": c.detalle, "abierto_en": _iso(c.abierto_en), "analizar_hasta": _iso(c.analizar_hasta),
            "concluido_en": _iso(c.concluido_en), "conclusion": c.conclusion, "comunicar": c.comunicar,
            "comunicar_hasta": _iso(c.comunicar_hasta), "aprobado_por": c.aprobado_por,
            "comunicado_en": _iso(c.comunicado_en), "acuse": c.acuse, "archivado_en": _iso(c.archivado_en),
            "analisis_vencido": c.estado in (ABIERTO, EN_ANALISIS) and _aware(c.analizar_hasta) < ahora,
            "comunicacion_vencida": c.estado == CONCLUIDO and bool(c.comunicar) and _aware(c.comunicar_hasta) < ahora,
            "notas": notas or [], "alertas": alertas_ or []}


async def _caso(sesion, caso_id: str):
    c = (await sesion.execute(select(casos).where(casos.c.id == caso_id))).first()
    if c is None:
        raise CasoInvalido(f"Caso inexistente: {caso_id}.")
    return c


async def _anotar(sesion, caso_id: str, autor: str, texto: str):
    await sesion.execute(caso_notas.insert().values(caso=caso_id, autor=autor, texto=(texto or "")[:1000]))


# ─── abrir y trabajar ─────────────────────────────────────────────────────

async def abrir(*, titular: str, origen: str, actor: str, detalle: str = "", ahora: Optional[datetime] = None) -> dict:
    """Abre un caso, o anexa al abierto del mismo titular."""
    if origen not in ORIGENES:
        raise CasoInvalido("El origen es alerta, lista o manual.")
    ahora = ahora or _ahora()
    async with base.sesion() as s:
        abierto = (await s.execute(select(casos).where(
            casos.c.titular == titular, casos.c.estado.in_((ABIERTO, EN_ANALISIS))))).first()
        if abierto is not None:
            await _anotar(s, abierto.id, actor, f"Nuevo motivo ({origen}): {detalle}")
            return await detalle_(abierto.id, sesion=s)
        id_ = _nuevo_id()
        await s.execute(casos.insert().values(
            id=id_, titular=titular, origen=origen, estado=ABIERTO, detalle=(detalle or "")[:300],
            abierto_en=ahora, analizar_hasta=ahora + timedelta(days=DIAS_PARA_ANALIZAR)))
        await _anotar(s, id_, actor, f"Caso abierto por {origen}: {detalle}")
        return await detalle_(id_, sesion=s)


async def tomar(caso_id: str, *, analista: str) -> dict:
    async with base.sesion() as s:
        c = await _caso(s, caso_id)
        if c.estado not in (ABIERTO, EN_ANALISIS):
            raise CasoInvalido(f"El caso está {c.estado}: no se toma.")
        await s.execute(casos.update().where(casos.c.id == caso_id).values(estado=EN_ANALISIS, analista=analista))
        await _anotar(s, caso_id, analista, "Tomado para análisis")
        return await detalle_(caso_id, sesion=s)


async def anotar(caso_id: str, *, autor: str, texto: str) -> dict:
    if not (texto or "").strip():
        raise CasoInvalido("La nota está vacía.")
    async with base.sesion() as s:
        c = await _caso(s, caso_id)
        if c.estado in (COMUNICADO, ARCHIVADO):
            raise CasoInvalido("Un caso cerrado no se anota: se abre otro.")
        await _anotar(s, caso_id, autor, texto.strip())
        return await detalle_(caso_id, sesion=s)


async def concluir(caso_id: str, *, analista: str, conclusion: str, comunicar: bool,
                   ahora: Optional[datetime] = None) -> dict:
    """El analista concluye. Sin comunicación: queda archivado con la
    conclusión. Con comunicación: queda concluido, esperando la segunda
    firma, con 24 horas de plazo."""
    if not (conclusion or "").strip():
        raise CasoInvalido("La conclusión lleva un texto.")
    ahora = ahora or _ahora()
    async with base.sesion() as s:
        c = await _caso(s, caso_id)
        if c.estado != EN_ANALISIS:
            raise CasoInvalido("Sólo se concluye un caso en análisis: primero hay que tomarlo.")
        cambios = dict(analista=analista, conclusion=conclusion.strip()[:2000], concluido_en=ahora, comunicar=bool(comunicar))
        if comunicar:
            cambios.update(estado=CONCLUIDO, comunicar_hasta=ahora + timedelta(hours=HORAS_PARA_COMUNICAR))
        else:
            cambios.update(estado=ARCHIVADO, archivado_en=ahora)
        await s.execute(casos.update().where(casos.c.id == caso_id).values(**cambios))
        await _anotar(s, caso_id, analista, ("Concluido, a comunicar: " if comunicar else "Concluido sin comunicar: ") + conclusion.strip())
        return await detalle_(caso_id, sesion=s)


async def aprobar_comunicacion(caso_id: str, *, aprobador: str, ahora: Optional[datetime] = None) -> dict:
    """La segunda firma. Arma el archivo, lo manda por el puerto, guarda el
    acuse. Quien aprueba no puede ser quien concluyó."""
    ahora = ahora or _ahora()
    com = _comunicador()
    async with base.sesion() as s:
        c = await _caso(s, caso_id)
        if c.estado != CONCLUIDO or not c.comunicar:
            raise CasoInvalido("Sólo se aprueba la comunicación de un caso concluido «a comunicar».")
        if aprobador == c.analista:
            raise CasoInvalido("Cuatro ojos: quien aprueba la comunicación no puede ser quien concluyó el caso.")
        t = (await s.execute(select(titulares).where(titulares.c.id == c.titular))).first()
        titular = {"id": t.id, "nombre": t.nombre, "documento": t.documento, "ocupacion": t.ocupacion,
                   "pep": t.pep, "nivel_de_riesgo": t.nivel_de_riesgo} if t else {"id": c.titular, "nombre": c.titular, "documento": ""}
        als = (await s.execute(select(alertas).where(alertas.c.caso == caso_id))).all()
        ops = []
        for a in als:
            o = (await s.execute(select(operaciones).where(operaciones.c.id == a.operacion))).first()
            if o and o.id not in [x["id"] for x in ops]:
                from nucleo import comandos
                ops.append({"id": o.id, "creada": _iso(o.creada), "monto": comandos.a_texto(o.monto),
                            "direccion": o.direccion, "end_to_end": o.end_to_end})
        archivo = coaf.armar_comunicacion(caso={"id": c.id, "origen": c.origen}, titular=titular,
                                          alertas=[{"regla": a.regla} for a in als], operaciones=ops,
                                          conclusion=c.conclusion or "")
        acuse = await com.enviar(s, archivo=archivo, tipo=coaf.COMUNICACION)
        await s.execute(comunicaciones.insert().values(
            caso=caso_id, tipo=coaf.COMUNICACION, archivo=archivo, acuse=acuse, enviada_en=ahora,
            enviada_por=c.analista, aprobada_por=aprobador, comunicador=com.nombre))
        await s.execute(casos.update().where(casos.c.id == caso_id).values(
            estado=COMUNICADO, aprobado_por=aprobador, comunicado_en=ahora, acuse=acuse))
        await _anotar(s, caso_id, aprobador, f"Comunicación aprobada y enviada; acuse {acuse}")
        return await detalle_(caso_id, sesion=s)


async def declarar_no_ocurrencia(*, anio: int, actor: str, aprobador: str, ahora: Optional[datetime] = None) -> dict:
    """La declaración anual de que no hubo nada que comunicar. Sólo si de
    verdad no se comunicó nada ese año, y también con cuatro ojos."""
    ahora = ahora or _ahora()
    if actor == aprobador:
        raise CasoInvalido("Cuatro ojos: la declaración la firman dos personas distintas.")
    com = _comunicador()
    async with base.sesion() as s:
        enviadas = (await s.execute(select(comunicaciones).where(comunicaciones.c.tipo == coaf.COMUNICACION))).all()
        if any((_aware(e.enviada_en) or ahora).year == anio for e in enviadas):
            raise CasoInvalido(f"En {anio} sí hubo comunicaciones al COAF: no corresponde declarar no ocurrencia.")
        ya = (await s.execute(select(comunicaciones).where(
            comunicaciones.c.tipo == coaf.NO_OCURRENCIA, comunicaciones.c.periodo == anio))).first()
        if ya is not None:
            return _comunicacion(ya)
        archivo = coaf.armar_no_ocurrencia(anio=anio)
        acuse = await com.enviar(s, archivo=archivo, tipo=coaf.NO_OCURRENCIA)
        r = await s.execute(comunicaciones.insert().values(
            caso=None, tipo=coaf.NO_OCURRENCIA, periodo=anio, archivo=archivo, acuse=acuse, enviada_en=ahora,
            enviada_por=actor, aprobada_por=aprobador, comunicador=com.nombre))
        return _comunicacion((await s.execute(select(comunicaciones).where(comunicaciones.c.id == r.inserted_primary_key[0]))).first())


# ─── para mirar ───────────────────────────────────────────────────────────

def _comunicacion(e) -> dict:
    return {"id": e.id, "caso": e.caso, "tipo": e.tipo, "periodo": e.periodo, "archivo": e.archivo, "acuse": e.acuse,
            "enviada_en": _iso(e.enviada_en), "enviada_por": e.enviada_por, "aprobada_por": e.aprobada_por,
            "comunicador": e.comunicador}


async def detalle_(caso_id: str, sesion=None, ahora: Optional[datetime] = None) -> dict:
    async def _(s):
        import json
        c = await _caso(s, caso_id)
        notas = (await s.execute(select(caso_notas).where(caso_notas.c.caso == caso_id).order_by(caso_notas.c.id))).all()
        als = (await s.execute(select(alertas).where(alertas.c.caso == caso_id).order_by(alertas.c.id))).all()
        return _fila(c, [{"autor": n.autor, "texto": n.texto, "momento": _iso(n.momento)} for n in notas],
                     [{"id": a.id, "regla": a.regla, "operacion": a.operacion,
                       "detalle": json.loads(a.detalle) if a.detalle else {}, "momento": _iso(a.momento)} for a in als],
                     ahora)
    if sesion is not None:
        return await _(sesion)
    async with base.sesion() as s:
        return await _(s)


detalle = detalle_


async def listar(limite: int = 50, ahora: Optional[datetime] = None) -> list:
    """Con sus notas y alertas: la pestaña muestra el expediente desde la
    lista, sin una consulta por caso."""
    import json
    async with base.sesion() as s:
        filas = (await s.execute(select(casos).order_by(casos.c.abierto_en.desc(), casos.c.id.desc()).limit(limite))).all()
        ids = [c.id for c in filas]
        notas, als = {}, {}
        if ids:
            for n in (await s.execute(select(caso_notas).where(caso_notas.c.caso.in_(ids)).order_by(caso_notas.c.id))).all():
                notas.setdefault(n.caso, []).append({"autor": n.autor, "texto": n.texto, "momento": _iso(n.momento)})
            for a in (await s.execute(select(alertas).where(alertas.c.caso.in_(ids)).order_by(alertas.c.id))).all():
                als.setdefault(a.caso, []).append({"id": a.id, "regla": a.regla, "operacion": a.operacion,
                                                   "detalle": json.loads(a.detalle) if a.detalle else {}, "momento": _iso(a.momento)})
        return [_fila(c, notas.get(c.id), als.get(c.id), ahora) for c in filas]


async def listar_comunicaciones(limite: int = 50) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(comunicaciones).order_by(comunicaciones.c.id.desc()).limit(limite))).all()
        return [_comunicacion(e) for e in filas]


async def resumen(ahora: Optional[datetime] = None) -> dict:
    ahora = ahora or _ahora()
    salida = {e: 0 for e in (ABIERTO, EN_ANALISIS, CONCLUIDO, COMUNICADO, ARCHIVADO)}
    salida["vencidos"] = 0
    async with base.sesion() as s:
        for c in (await s.execute(select(casos))).all():
            salida[c.estado] = salida.get(c.estado, 0) + 1
            f = _fila(c, ahora=ahora)
            if f["analisis_vencido"] or f["comunicacion_vencida"]:
                salida["vencidos"] += 1
    return salida
