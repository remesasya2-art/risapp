"""
El legajo del titular: quién es, qué declaró, qué dijo el verificador, qué
dijeron las listas, y si con todo eso se puede abrir una cuenta.

EL CAMINO DE UN LEGAJO

    incompleto ──► en_revision ──► aprobado ──► vencido
                                └─► rechazado

    Nace incompleto. Pasa a «en revisión» solo, cuando tiene una
    verificación aprobada Y ya se cruzó con las listas sin un cruce de
    sanciones pendiente. Lo aprueba una persona, con un nivel de riesgo, y
    desde ahí vale hasta una fecha. Vencido es aprobado con fecha pasada:
    se vuelve a verificar y se vuelve a aprobar.

LAS GUARDAS, Y POR QUE SON DEL SISTEMA Y NO DEL AGENTE

    1. No se aprueba sin una verificación aprobada.
    2. No se aprueba con un cruce de sanciones sin resolver.
    3. Un PEP (declarado o encontrado en la lista) sólo se aprueba con
       riesgo ALTO. Es lo que la Circular 3.978 llama diligencia reforzada.
    4. No se abre una cuenta de pago sin legajo aprobado y vigente. Esta la
       hace cumplir `comandos.crear_cuenta`, y es la que más importa: es
       la que hace que las otras tres no se puedan saltear.

    Cada una tiene su test y su mutación. Un agente puede equivocarse; el
    sistema no le deja.

LO QUE QUEDA ESCRITO

    Cada verificación, con puntajes y motivos, aunque falle. Cada cruce,
    con cómo se resolvió y quién. Nada se borra: no hay función para eso.
"""
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from nucleo import base
from nucleo.esquema import cruces, titulares, verificaciones
from nucleo.identidad import formas, listas as _listas, verificador as _verificador
from nucleo.rieles import pix


class LegajoInvalido(ValueError):
    pass


class LegajoNoApto(ValueError):
    """No hay legajo aprobado y vigente para esta persona: no se abre cuenta."""


def _nuevo_id() -> str:
    return "tit_" + secrets.token_hex(6)


def _ahora():
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if v else None


def _fila(f, verificaciones_=None, cruces_=None) -> dict:
    from nucleo import comandos
    return {"id": f.id, "documento": f.documento, "tipo": f.tipo, "nombre": f.nombre,
            "nacimiento": _iso(f.nacimiento), "ocupacion": f.ocupacion,
            "renta_declarada": comandos.a_texto(f.renta_declarada) if f.renta_declarada is not None else None,
            "pep_declarado": f.pep_declarado, "pep": f.pep, "origen_de_fondos": f.origen_de_fondos,
            "nivel_de_riesgo": f.nivel_de_riesgo, "estado": f.estado, "vigente_hasta": _iso(f.vigente_hasta),
            "motivo": f.motivo, "decidido_por": f.decidido_por, "cruzado_en": _iso(f.cruzado_en),
            "creado": _iso(f.creado), "actualizado": _iso(f.actualizado),
            "verificaciones": verificaciones_ or [], "cruces": cruces_ or []}


def _verificacion(v) -> dict:
    return {"id": v.id, "proveedor": v.proveedor, "puntaje_documento": v.puntaje_documento,
            "puntaje_vida": v.puntaje_vida, "puntaje_rostro": v.puntaje_rostro, "situacion_cpf": v.situacion_cpf,
            "nombre_en_documento": v.nombre_en_documento, "documento_vencido": v.documento_vencido,
            "aprobada": v.aprobada, "motivos": json.loads(v.motivos) if v.motivos else [], "momento": _iso(v.momento)}


def _cruce(c) -> dict:
    return {"id": c.id, "titular": c.titular, "lista": c.lista, "clase": c.clase, "nombre_en_lista": c.nombre_en_lista,
            "detalle": c.detalle, "momento": _iso(c.momento), "resuelto": c.resuelto, "resolucion": c.resolucion,
            "resuelto_por": c.resuelto_por, "resuelto_en": _iso(c.resuelto_en)}


async def _titular(sesion, titular_id: str):
    f = (await sesion.execute(select(titulares).where(titulares.c.id == titular_id))).first()
    if f is None:
        raise LegajoInvalido(f"Titular inexistente: {titular_id}.")
    return f


async def _ultima_verificacion(sesion, titular_id: str):
    return (await sesion.execute(select(verificaciones).where(verificaciones.c.titular == titular_id)
                                 .order_by(verificaciones.c.id.desc()).limit(1))).first()


async def _sanciones_pendientes(sesion, titular_id: str) -> int:
    filas = (await sesion.execute(select(cruces.c.id).where(
        cruces.c.titular == titular_id, cruces.c.clase == formas.SANCIONES, cruces.c.resuelto.is_(False)))).all()
    return len(filas)


async def _listo_para_aprobar(sesion, f) -> bool:
    v = await _ultima_verificacion(sesion, f.id)
    return bool(v and v.aprobada and f.cruzado_en is not None and await _sanciones_pendientes(sesion, f.id) == 0)


async def _acomodar_estado(sesion, titular_id: str):
    """incompleto ↔ en_revision, según lo que haya. Los estados decididos
    por una persona (aprobado, rechazado) y el vencido no se tocan acá."""
    f = await _titular(sesion, titular_id)
    if f.estado in (formas.APROBADO, formas.RECHAZADO, formas.VENCIDO):
        return
    nuevo = formas.EN_REVISION if await _listo_para_aprobar(sesion, f) else formas.INCOMPLETO
    if nuevo != f.estado:
        await sesion.execute(titulares.update().where(titulares.c.id == titular_id)
                             .values(estado=nuevo, actualizado=_ahora()))


# ─── el alta ──────────────────────────────────────────────────────────────

async def crear_titular(*, documento: str, nombre: str, actor: str, nacimiento: Optional[str] = None,
                        ocupacion: Optional[str] = None, renta_declarada: Optional[str] = None,
                        pep_declarado: bool = False, origen_de_fondos: Optional[str] = None) -> dict:
    """Nace el legajo, incompleto. Idempotente por documento."""
    from nucleo import comandos
    documento = (documento or "").strip()
    try:
        tipo = pix.tipo_de_clave(documento)
    except pix.ClaveInvalida:
        tipo = None
    if tipo not in (pix.CPF, pix.CNPJ):
        raise LegajoInvalido("El documento tiene que ser un CPF o un CNPJ válido, sólo dígitos.")
    if not (nombre or "").strip():
        raise LegajoInvalido("Falta el nombre.")
    if origen_de_fondos and origen_de_fondos not in formas.ORIGENES_DE_FONDOS:
        raise LegajoInvalido(f"Origen de fondos desconocido; se espera uno de: {', '.join(formas.ORIGENES_DE_FONDOS)}.")
    renta = comandos.a_centavos(renta_declarada) if renta_declarada else None
    nac = date.fromisoformat(nacimiento) if nacimiento else None
    async with base.sesion() as s:
        ya = (await s.execute(select(titulares).where(titulares.c.documento == documento))).first()
        if ya is not None:
            return await detalle(ya.id, sesion=s)
        id_ = _nuevo_id()
        await s.execute(titulares.insert().values(
            id=id_, documento=documento, tipo=tipo, nombre=nombre.strip(), nacimiento=nac, ocupacion=ocupacion,
            renta_declarada=renta, pep_declarado=bool(pep_declarado), pep=bool(pep_declarado),
            origen_de_fondos=origen_de_fondos, estado=formas.INCOMPLETO))
        return await detalle(id_, sesion=s)


# ─── verificar y cruzar ───────────────────────────────────────────────────

async def verificar(titular_id: str, *, actor: str) -> dict:
    """Le pide al verificador que mire el documento, la vida y el rostro.
    El resultado queda escrito, apruebe o no."""
    v = _verificador()
    async with base.sesion() as s:
        f = await _titular(s, titular_id)
        if f.estado == formas.RECHAZADO:
            raise LegajoInvalido("Un legajo rechazado no se vuelve a verificar: se abre otro.")
        r = await v.verificar(s, documento=f.documento, nombre=f.nombre,
                              nacimiento=_iso(f.nacimiento) or "")
        res = await s.execute(verificaciones.insert().values(
            titular=titular_id, proveedor=r.proveedor, puntaje_documento=r.puntaje_documento,
            puntaje_vida=r.puntaje_vida, puntaje_rostro=r.puntaje_rostro, situacion_cpf=r.situacion_cpf,
            nombre_en_documento=r.nombre_en_documento, documento_vencido=r.documento_vencido,
            aprobada=r.aprobada, motivos=json.dumps(list(r.motivos), ensure_ascii=False)))
        await _acomodar_estado(s, titular_id)
        fila = (await s.execute(select(verificaciones).where(verificaciones.c.id == res.inserted_primary_key[0]))).first()
        return _verificacion(fila)


async def cruzar(titular_id: str, *, actor: str) -> list:
    """Sanciones y PEP. Cada coincidencia queda como un cruce a resolver; una
    de PEP marca al titular como PEP aunque no lo haya declarado."""
    ls = _listas()
    async with base.sesion() as s:
        f = await _titular(s, titular_id)
        encontradas = await ls.consultar(s, documento=f.documento, nombre=f.nombre)
        abiertos = {(c.lista, c.resuelto) for c in (await s.execute(
            select(cruces.c.lista, cruces.c.resuelto).where(cruces.c.titular == titular_id))).all()}
        nuevos = []
        for c in encontradas:
            if (c.lista, False) in abiertos:
                continue                                  # ya está abierto, no se duplica
            r = await s.execute(cruces.insert().values(
                titular=titular_id, lista=c.lista, clase=c.clase, nombre_en_lista=c.nombre, detalle=c.detalle))
            nuevos.append(r.inserted_primary_key[0])
        cambios = {"cruzado_en": _ahora(), "actualizado": _ahora()}
        if any(c.clase == formas.PEP for c in encontradas):
            cambios["pep"] = True
        await s.execute(titulares.update().where(titulares.c.id == titular_id).values(**cambios))
        await _acomodar_estado(s, titular_id)
        filas = (await s.execute(select(cruces).where(cruces.c.titular == titular_id).order_by(cruces.c.id))).all()
        return [_cruce(c) for c in filas]


async def resolver_cruce(cruce_id: int, *, resolucion: str, actor: str) -> dict:
    """Una persona mira el cruce y dice qué es: falso positivo o confirmado.
    Queda con su nombre. Un cruce confirmado de sanciones deja el legajo
    sin poder aprobarse igual: lo que se resuelve es que alguien lo miró."""
    if not (resolucion or "").strip():
        raise LegajoInvalido("La resolución lleva una explicación.")
    async with base.sesion() as s:
        c = (await s.execute(select(cruces).where(cruces.c.id == cruce_id))).first()
        if c is None:
            raise LegajoInvalido(f"Cruce inexistente: {cruce_id}.")
        if c.resuelto:
            return _cruce(c)
        await s.execute(cruces.update().where(cruces.c.id == cruce_id).values(
            resuelto=True, resolucion=resolucion.strip()[:300], resuelto_por=actor, resuelto_en=_ahora()))
        await _acomodar_estado(s, c.titular)
        resultado = _cruce((await s.execute(select(cruces).where(cruces.c.id == cruce_id))).first())
    # Un cruce de sanciones CONFIRMADO es un caso: se abre solo, para que
    # el análisis y la comunicación queden en el expediente.
    if c.clase == formas.SANCIONES and resolucion.strip().lower().startswith("confirmado"):
        from nucleo.riesgo import casos
        await casos.abrir(titular=c.titular, origen="lista", actor=actor,
                          detalle=f"{c.lista}: {resolucion.strip()[:200]}")
    return resultado


# ─── decidir ──────────────────────────────────────────────────────────────

async def aprobar(titular_id: str, *, nivel_de_riesgo: str, actor: str, hoy: Optional[date] = None) -> dict:
    if nivel_de_riesgo not in formas.NIVELES_DE_RIESGO:
        raise LegajoInvalido("El nivel de riesgo es bajo, medio o alto.")
    hoy = hoy or _ahora().date()
    async with base.sesion() as s:
        f = await _titular(s, titular_id)
        if f.estado == formas.RECHAZADO:
            raise LegajoInvalido("Un legajo rechazado no se aprueba: se abre otro.")
        v = await _ultima_verificacion(s, titular_id)
        if not (v and v.aprobada):
            raise LegajoInvalido("No se aprueba un legajo sin una verificación de identidad aprobada.")
        if f.cruzado_en is None:
            raise LegajoInvalido("No se aprueba un legajo sin cruzarlo con las listas.")
        if await _sanciones_pendientes(s, titular_id):
            raise LegajoInvalido("Hay un cruce de sanciones sin resolver: alguien tiene que mirarlo primero.")
        confirmados = (await s.execute(select(cruces.c.id).where(
            cruces.c.titular == titular_id, cruces.c.clase == formas.SANCIONES, cruces.c.resuelto.is_(True),
            cruces.c.resolucion.like("confirmado%")))).all()
        if confirmados:
            raise LegajoInvalido("Un cruce de sanciones confirmado no se aprueba: se rechaza y se comunica.")
        if f.pep and nivel_de_riesgo != formas.ALTO:
            raise LegajoInvalido("Una persona expuesta políticamente sólo se aprueba con riesgo alto (diligencia reforzada).")
        vigente_hasta = _sumar_meses(hoy, formas.MESES_DE_VIGENCIA[nivel_de_riesgo])
        await s.execute(titulares.update().where(titulares.c.id == titular_id).values(
            estado=formas.APROBADO, nivel_de_riesgo=nivel_de_riesgo, vigente_hasta=vigente_hasta,
            decidido_por=actor, motivo=None, actualizado=_ahora()))
        return await detalle(titular_id, sesion=s)


async def rechazar(titular_id: str, *, motivo: str, actor: str) -> dict:
    if not (motivo or "").strip():
        raise LegajoInvalido("Un rechazo lleva un motivo.")
    async with base.sesion() as s:
        await _titular(s, titular_id)
        await s.execute(titulares.update().where(titulares.c.id == titular_id).values(
            estado=formas.RECHAZADO, motivo=motivo.strip()[:300], decidido_por=actor, actualizado=_ahora()))
        return await detalle(titular_id, sesion=s)


def _sumar_meses(d: date, meses: int) -> date:
    mes = d.month - 1 + meses
    anio = d.year + mes // 12
    mes = mes % 12 + 1
    dia = min(d.day, [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    return date(anio, mes, dia)


# ─── la guarda que usa el libro ───────────────────────────────────────────

async def exigir_apto(titular_id: str, hoy: Optional[date] = None):
    """Aprobado y vigente, o no hay cuenta. Un aprobado con la fecha pasada
    se marca vencido acá mismo, para que quede dicho.

    Con SESION PROPIA, y el error se lanza DESPUES de cerrarla: si se
    lanzara adentro, la transacción se desharía y la marca de vencido se
    perdería con ella. Pasó en el primer intento; hay un test."""
    hoy = hoy or _ahora().date()
    motivo = None
    async with base.sesion() as s:
        f = (await s.execute(select(titulares).where(titulares.c.id == titular_id))).first()
        if f is None:
            motivo = f"No hay legajo para {titular_id!r}: una cuenta de pago se abre a un titular con legajo aprobado."
        elif f.estado == formas.APROBADO and f.vigente_hasta and f.vigente_hasta < hoy:
            await s.execute(titulares.update().where(titulares.c.id == titular_id)
                            .values(estado=formas.VENCIDO, actualizado=_ahora()))
            motivo = f"El legajo de {f.nombre} venció el {f.vigente_hasta.isoformat()}: hay que renovarlo."
        elif f.estado != formas.APROBADO:
            motivo = f"El legajo de {f.nombre} está «{f.estado}», no aprobado."
    if motivo:
        raise LegajoNoApto(motivo)
    return f


async def revisar_vigencias(hoy: Optional[date] = None) -> int:
    """Marca vencidos los aprobados con fecha pasada. Para correr cada tanto."""
    hoy = hoy or _ahora().date()
    async with base.sesion() as s:
        r = await s.execute(titulares.update().where(
            titulares.c.estado == formas.APROBADO, titulares.c.vigente_hasta < hoy)
            .values(estado=formas.VENCIDO, actualizado=_ahora()))
        return r.rowcount


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle(titular_id: str, sesion=None) -> dict:
    async def _(s):
        f = await _titular(s, titular_id)
        vs = (await s.execute(select(verificaciones).where(verificaciones.c.titular == titular_id)
                              .order_by(verificaciones.c.id.desc()))).all()
        cs = (await s.execute(select(cruces).where(cruces.c.titular == titular_id).order_by(cruces.c.id))).all()
        return _fila(f, [_verificacion(v) for v in vs], [_cruce(c) for c in cs])
    if sesion is not None:
        return await _(sesion)
    async with base.sesion() as s:
        return await _(s)


async def listar(estado: Optional[str] = None, limite: int = 100) -> list:
    """Con sus verificaciones y cruces: la pestaña muestra el legajo entero
    desde la lista, sin una consulta por titular."""
    async with base.sesion() as s:
        q = select(titulares).order_by(titulares.c.creado.desc(), titulares.c.id.desc()).limit(limite)
        if estado:
            q = q.where(titulares.c.estado == estado)
        filas = (await s.execute(q)).all()
        ids = [f.id for f in filas]
        vs, cs = {}, {}
        if ids:
            for v in (await s.execute(select(verificaciones).where(verificaciones.c.titular.in_(ids))
                                      .order_by(verificaciones.c.id.desc()))).all():
                vs.setdefault(v.titular, []).append(_verificacion(v))
            for c in (await s.execute(select(cruces).where(cruces.c.titular.in_(ids)).order_by(cruces.c.id))).all():
                cs.setdefault(c.titular, []).append(_cruce(c))
        return [_fila(f, vs.get(f.id), cs.get(f.id)) for f in filas]


async def alta_aprobada_de_prueba(documento: str = "12345678909", nombre: str = "Ana Prueba",
                                  actor: str = "prueba", nivel: str = formas.BAJO) -> str:
    """El camino entero de un legajo, de una vez: crear, verificar, cruzar,
    aprobar. SOLO para tests y para la vista previa; en el laboratorio del
    panel el camino se hace paso a paso. Devuelve el id del titular."""
    t = await crear_titular(documento=documento, nombre=nombre, actor=actor, origen_de_fondos="salario")
    if t["estado"] == formas.APROBADO:
        return t["id"]
    await verificar(t["id"], actor=actor)
    await cruzar(t["id"], actor=actor)
    await aprobar(t["id"], nivel_de_riesgo=nivel, actor=actor)
    return t["id"]
