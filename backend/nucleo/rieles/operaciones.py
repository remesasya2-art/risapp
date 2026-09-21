"""
Las operaciones por un riel: cobros, pagos y devoluciones, con su estado,
su contabilidad y su línea de tiempo.

    Es el único módulo que junta las tres cosas: el riel (por dónde va la
    plata), el libro (qué significa contablemente) y la cola (que lo que
    tiene que pasar después, pase aunque el proceso se caiga).

LOS ESTADOS

    entrada (un cobro):      activa ──► liquidada
    salida (un pago):        pendiente ──► enviada ──► liquidada
                                                   └──► rechazada
    devolucion (de un cobro): pendiente ──► enviada ──► liquidada
                                                    └──► rechazada

    Cada cambio queda en `operacion_estados`, que sólo se agrega. Es la
    línea de tiempo que un cliente, un auditor o el Banco Central pueden
    pedir por una operación.

LOS ASIENTOS, Y CUANDO

    Cobro liquidado:   acreditar al titular          referencia pix:<end_to_end>
    Pago ordenado:     reservar (titular → tránsito)  referencia pago:<id>:reserva
    Pago liquidado:    liquidar (tránsito → banco)    referencia pago:<id>:liquidacion
    Pago rechazado:    revertir (tránsito → titular)  referencia pago:<id>:reversion
    Devolución:        igual que un pago, con «devolucion:» en la referencia.

    Las referencias son deterministas: un aviso que llega dos veces pide el
    mismo asiento dos veces, y el libro devuelve el que ya estaba.

EL ORDEN DE LAS COSAS AL ORDENAR UN PAGO

    Primero la reserva en el libro, después la operación, después el trabajo
    en la cola. Si algo se cae entre la reserva y la operación, la plata
    queda en tránsito con una referencia que dice de qué pedido es, y
    repetir el pedido con la misma referencia la encuentra en vez de
    reservar de nuevo. Nunca puede salir plata sin reserva: el riel recién
    se llama desde el trabajo, y el trabajo recién existe con la operación.

LOS AVISOS

    Lo que el riel nos dice entra por `recibir_aviso`, se guarda crudo
    (idempotente por su identificador) y se procesa desde la cola. Un aviso
    que no se entiende no se pierde: queda con su resultado en la hoja.
"""
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from nucleo import base, cola, comandos
from nucleo.esquema import avisos_riel, cuentas, operacion_estados, operaciones
from nucleo.libro import AsientoInvalido
from nucleo.rieles import pix, vigente

ENTRADA, SALIDA, DEVOLUCION = "entrada", "salida", "devolucion"
ACTIVA, PENDIENTE, ENVIADA, LIQUIDADA, RECHAZADA = "activa", "pendiente", "enviada", "liquidada", "rechazada"

ACTOR = "riel"


class OperacionInvalida(ValueError):
    pass


class ClaveDesconocida(ValueError):
    pass


def _nuevo_id() -> str:
    return "op_" + secrets.token_hex(6)


def _ahora():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _fila(f, historial=None) -> dict:
    return {"id": f.id, "riel": f.riel, "direccion": f.direccion, "estado": f.estado, "cuenta": f.cuenta,
            "monto": comandos.a_texto(f.monto), "referencia": f.referencia, "txid": f.txid,
            "end_to_end": f.end_to_end, "clave": f.clave,
            "contraparte": json.loads(f.contraparte) if f.contraparte else None,
            "descripcion": f.descripcion, "motivo": f.motivo, "origen": f.origen, "codigo_br": f.codigo_br,
            "creada": _iso(f.creada), "actualizada": _iso(f.actualizada),
            "historial": historial or []}


async def _registrar_estado(sesion, operacion_id: str, estado: str, detalle: str = None, **cambios):
    await sesion.execute(operacion_estados.insert().values(
        operacion=operacion_id, estado=estado, detalle=(detalle or "")[:300] or None))
    await sesion.execute(operaciones.update().where(operaciones.c.id == operacion_id)
                         .values(estado=estado, actualizada=_ahora(), **cambios))


async def _cuenta_activa(sesion, cuenta_id: str):
    fila = (await sesion.execute(select(cuentas).where(cuentas.c.id == cuenta_id))).first()
    if fila is None:
        raise OperacionInvalida(f"Cuenta de pago inexistente: {cuenta_id}.")
    if fila.estado != "activa":
        raise OperacionInvalida(f"Cuenta de pago no activa: {cuenta_id}.")
    return fila


async def _por_referencia(sesion, referencia: str):
    return (await sesion.execute(select(operaciones).where(operaciones.c.referencia == referencia))).first()


# ─── cobros (entrada) ─────────────────────────────────────────────────────

async def crear_cobro(*, cuenta_id: str, monto: str, descripcion: str = "", actor: str) -> dict:
    """Un QR para que alguien pague a la cuenta del titular."""
    centavos = comandos.a_centavos(monto)
    riel = vigente()
    txid = pix.nuevo_txid()
    async with base.sesion() as s:
        await _cuenta_activa(s, cuenta_id)
        cobro = await riel.cobrar(s, txid=txid, monto=centavos, cuenta_id=cuenta_id, descripcion=descripcion)
        id_ = _nuevo_id()
        await s.execute(operaciones.insert().values(
            id=id_, riel=riel.nombre, direccion=ENTRADA, estado=ACTIVA, cuenta=cuenta_id, monto=centavos,
            referencia=f"cobro:{txid}", txid=txid, clave=cobro.clave_receptora,
            descripcion=(descripcion or None), codigo_br=cobro.codigo_br))
        await _registrar_estado(s, id_, ACTIVA, f"cobro generado por {actor}")
        return await detalle(id_, sesion=s)


# ─── pagos (salida) ───────────────────────────────────────────────────────

async def ordenar_pago(*, cuenta_id: str, clave: str, monto: str, referencia: str, actor: str,
                       descripcion: str = "") -> dict:
    """Ordena un pago PIX a una clave. Idempotente por referencia."""
    centavos = comandos.a_centavos(monto)
    clave = pix.normalizar_clave(clave)
    riel = vigente()
    async with base.sesion() as s:
        ya = await _por_referencia(s, referencia)
        if ya is not None:
            return await detalle(ya.id, sesion=s)
        await _cuenta_activa(s, cuenta_id)
        receptor = await riel.consultar_clave(s, clave)
    if receptor is None:
        raise ClaveDesconocida(f"La clave {clave} no está en el DICT.")
    return await _ordenar_salida(direccion=SALIDA, cuenta_id=cuenta_id, clave=clave, centavos=centavos,
                                 referencia=referencia, actor=actor, descripcion=descripcion,
                                 receptor=receptor, riel=riel, origen=None, motivo=None)


async def _ordenar_salida(*, direccion, cuenta_id, clave, centavos, referencia, actor, descripcion,
                          receptor, riel, origen, motivo) -> dict:
    prefijo = "pago" if direccion == SALIDA else "devolucion"
    # 1. la reserva en el libro (exige saldo; falla antes de crear nada)
    await comandos.reservar_para_pago(cuenta_id=cuenta_id, monto=comandos.a_texto(centavos),
                                      referencia=f"{prefijo}:{referencia}:reserva", actor=actor,
                                      descripcion=f"{'Pago' if direccion == SALIDA else 'Devolución'} PIX a {receptor.nombre}, en tránsito")
    # 2. la operación
    end_to_end = pix.nuevo_end_to_end(riel.ispb)
    async with base.sesion() as s:
        id_ = _nuevo_id()
        await s.execute(operaciones.insert().values(
            id=id_, riel=riel.nombre, direccion=direccion, estado=PENDIENTE, cuenta=cuenta_id, monto=centavos,
            referencia=referencia, end_to_end=end_to_end, clave=clave,
            contraparte=json.dumps({"nombre": receptor.nombre, "documento": receptor.documento_enmascarado,
                                    "ispb": receptor.ispb, "banco": receptor.banco, "tipo": receptor.tipo},
                                   ensure_ascii=False),
            descripcion=(descripcion or None), origen=origen, motivo=motivo))
        await _registrar_estado(s, id_, PENDIENTE, f"ordenado por {actor}; reservado en tránsito")
        # 3. el trabajo que habla con el riel
        await cola.encolar(s, tipo="enviar_pago", clave=f"{prefijo}:{id_}", carga={"operacion": id_})
        return await detalle(id_, sesion=s)


async def enviar_pago(carga: dict) -> str:
    """Manejador de la cola: manda la orden (o la devolución) al riel."""
    op_id = carga["operacion"]
    riel = vigente()
    async with base.sesion() as s:
        f = (await s.execute(select(operaciones).where(operaciones.c.id == op_id))).first()
        if f is None:
            raise OperacionInvalida(f"Operación inexistente: {op_id}.")
        if f.estado != PENDIENTE:
            return f"ya estaba {f.estado}"
        contraparte = json.loads(f.contraparte or "{}")
        receptor = pix.TitularDeClave(clave=f.clave, tipo=contraparte.get("tipo", ""), nombre=contraparte.get("nombre", ""),
                                      documento_enmascarado=contraparte.get("documento", ""),
                                      ispb=contraparte.get("ispb", ""), banco=contraparte.get("banco", ""))
        if f.direccion == DEVOLUCION:
            origen = (await s.execute(select(operaciones.c.end_to_end).where(operaciones.c.id == f.origen))).scalar_one()
            respuesta = await riel.devolver(s, devolucion=pix.Devolucion(
                end_to_end_original=origen, end_to_end=f.end_to_end, monto=f.monto, motivo=f.motivo))
        else:
            respuesta = await riel.pagar(s, orden=pix.OrdenDePago(
                end_to_end=f.end_to_end, monto=f.monto, clave_destino=f.clave, receptor=receptor,
                pagador_cuenta=f.cuenta, descripcion=f.descripcion or ""))
        await _registrar_estado(s, op_id, ENVIADA, f"el riel contestó {respuesta.estado}")
        return f"enviado, {respuesta.estado}"


# ─── devoluciones ─────────────────────────────────────────────────────────

async def devolver(*, operacion_id: str, monto: str, motivo: str, actor: str) -> dict:
    """Devuelve (parte de) un cobro liquidado a quien lo pagó."""
    centavos = comandos.a_centavos(monto)
    if motivo not in pix.MOTIVOS_DE_DEVOLUCION:
        raise OperacionInvalida("El motivo de la devolución tiene que ser uno del catálogo (MD06, SL02, FR01, BE08).")
    riel = vigente()
    async with base.sesion() as s:
        f = (await s.execute(select(operaciones).where(operaciones.c.id == operacion_id))).first()
        if f is None or f.direccion != ENTRADA or f.estado != LIQUIDADA:
            raise OperacionInvalida("Sólo se devuelve un cobro que ya se liquidó.")
        devuelto = (await s.execute(
            select(func.coalesce(func.sum(operaciones.c.monto), 0))
            .where(operaciones.c.origen == operacion_id, operaciones.c.estado != RECHAZADA))).scalar_one()
        if int(devuelto) + centavos > f.monto:
            raise OperacionInvalida(
                f"Ya se devolvieron {comandos.a_texto(int(devuelto))} de {comandos.a_texto(f.monto)}: no alcanza.")
        pagador = json.loads(f.contraparte or "{}")
    receptor = pix.TitularDeClave(clave=pagador.get("clave", ""), tipo=pagador.get("tipo", ""), nombre=pagador.get("nombre", ""),
                                  documento_enmascarado=pagador.get("documento", ""),
                                  ispb=pagador.get("ispb", ""), banco=pagador.get("banco", ""))
    referencia = f"dev:{operacion_id}:{secrets.token_hex(4)}"
    return await _ordenar_salida(direccion=DEVOLUCION, cuenta_id=f.cuenta, clave=receptor.clave, centavos=centavos,
                                 referencia=referencia, actor=actor,
                                 descripcion=f"Devolución {motivo}: {pix.MOTIVOS_DE_DEVOLUCION[motivo]}",
                                 receptor=receptor, riel=riel, origen=operacion_id, motivo=motivo)


# ─── los avisos del riel ──────────────────────────────────────────────────

async def recibir_aviso(sesion, *, riel: str, id_externo: str, tipo: str, carga: dict) -> dict:
    """Nuestro webhook. Guarda el aviso crudo y encola procesarlo. Un aviso
    repetido (mismo riel, mismo id) se reconoce y no se encola de nuevo."""
    ya = (await sesion.execute(
        select(avisos_riel.c.id).where(avisos_riel.c.riel == riel, avisos_riel.c.id_externo == id_externo))).scalar_one_or_none()
    if ya is not None:
        return {"id": ya, "nuevo": False}
    r = await sesion.execute(avisos_riel.insert().values(
        riel=riel, id_externo=id_externo, tipo=tipo,
        carga=json.dumps(carga, sort_keys=True, separators=(",", ":"), ensure_ascii=False)))
    id_ = r.inserted_primary_key[0]
    await cola.encolar(sesion, tipo="procesar_aviso", clave=f"aviso:{id_}", carga={"aviso": id_})
    return {"id": id_, "nuevo": True}


async def procesar_aviso(carga: dict) -> str:
    """Manejador de la cola: le da sentido a un aviso. Idempotente: los
    asientos van por referencia y los estados no retroceden."""
    aviso_id = carga["aviso"]
    async with base.sesion() as s:
        a = (await s.execute(select(avisos_riel).where(avisos_riel.c.id == aviso_id))).first()
    if a is None:
        raise OperacionInvalida(f"Aviso inexistente: {aviso_id}.")
    if a.procesado is not None:
        return a.resultado or "ya procesado"
    datos = json.loads(a.carga)
    if a.tipo == "credito_recibido":
        resultado = await _credito_recibido(datos)
    elif a.tipo == "estado_de_pago":
        resultado = await _estado_de_pago(datos)
    else:
        resultado = f"tipo de aviso desconocido: {a.tipo}"
    async with base.sesion() as s:
        await s.execute(avisos_riel.update().where(avisos_riel.c.id == aviso_id)
                        .values(procesado=_ahora(), resultado=resultado[:200]))
    return resultado


async def _credito_recibido(datos: dict) -> str:
    txid, end_to_end, monto = datos.get("txid"), datos.get("end_to_end"), int(datos.get("monto") or 0)
    pagador = datos.get("pagador") or {}
    if not pix.es_end_to_end(end_to_end or ""):
        return "end_to_end inválido; no se acredita"
    async with base.sesion() as s:
        f = (await s.execute(select(operaciones).where(operaciones.c.txid == txid, operaciones.c.direccion == ENTRADA))).first()
    if f is None:
        return f"cobro desconocido para txid {txid}; no se acredita"
    if f.estado == LIQUIDADA:
        return "cobro ya liquidado"
    if monto != f.monto:
        # Un QR dinámico lleva el monto adentro; el SPI no deja pagar otro.
        # Si igual llega distinto, se acredita LO QUE LLEGO y queda dicho.
        nota = f"monto distinto al del cobro ({comandos.a_texto(f.monto)}); se acreditó lo recibido"
    else:
        nota = "acreditado"
    await comandos.acreditar(cuenta_id=f.cuenta, monto=comandos.a_texto(monto), referencia=f"pix:{end_to_end}",
                             actor=ACTOR, descripcion=f"PIX recibido de {pagador.get('nombre', '?')}")
    async with base.sesion() as s:
        await _registrar_estado(s, f.id, LIQUIDADA, nota, end_to_end=end_to_end, monto=monto,
                                contraparte=json.dumps(pagador, ensure_ascii=False))
    return nota


async def _estado_de_pago(datos: dict) -> str:
    end_to_end, estado, motivo = datos.get("end_to_end"), datos.get("estado"), datos.get("motivo")
    async with base.sesion() as s:
        f = (await s.execute(select(operaciones).where(operaciones.c.end_to_end == end_to_end,
                                                       operaciones.c.direccion.in_((SALIDA, DEVOLUCION))))).first()
    if f is None:
        return f"operación desconocida para {end_to_end}"
    if f.estado in (LIQUIDADA, RECHAZADA):
        return f"ya estaba {f.estado}"
    prefijo = "pago" if f.direccion == SALIDA else "devolucion"
    monto = comandos.a_texto(f.monto)
    if estado == pix.ACSC:
        await comandos.liquidar_pago(monto=monto, referencia=f"{prefijo}:{f.referencia}:liquidacion", actor=ACTOR)
        async with base.sesion() as s:
            await _registrar_estado(s, f.id, LIQUIDADA, "ACSC: liquidado por el SPI")
        return "liquidado"
    if estado == pix.RJCT:
        explicado = pix.RespuestaDeEstado(end_to_end=end_to_end, estado=pix.RJCT, motivo=motivo).motivo_explicado
        await comandos.revertir_pago(cuenta_id=f.cuenta, monto=monto, referencia=f"{prefijo}:{f.referencia}:reversion",
                                     actor=ACTOR, descripcion=f"Pago rechazado ({explicado}), vuelve al titular")
        async with base.sesion() as s:
            await _registrar_estado(s, f.id, RECHAZADA, f"RJCT {explicado}", motivo=explicado)
        return f"rechazado: {explicado}"
    if estado == pix.ACSP:
        return "en liquidación"
    return f"estado desconocido: {estado}"


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle(operacion_id: str, sesion=None) -> dict:
    async def _(s):
        f = (await s.execute(select(operaciones).where(operaciones.c.id == operacion_id))).first()
        if f is None:
            raise OperacionInvalida(f"Operación inexistente: {operacion_id}.")
        hist = (await s.execute(select(operacion_estados).where(operacion_estados.c.operacion == operacion_id)
                                .order_by(operacion_estados.c.id))).all()
        return _fila(f, [{"estado": h.estado, "detalle": h.detalle, "momento": _iso(h.momento)} for h in hist])
    if sesion is not None:
        return await _(sesion)
    async with base.sesion() as s:
        return await _(s)


async def listar(limite: int = 50) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(operaciones).order_by(operaciones.c.creada.desc(), operaciones.c.id.desc())
                                 .limit(limite))).all()
        return [_fila(f) for f in filas]


async def listar_avisos(limite: int = 50) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(avisos_riel).order_by(avisos_riel.c.id.desc()).limit(limite))).all()
        return [{"id": f.id, "riel": f.riel, "id_externo": f.id_externo, "tipo": f.tipo, "carga": json.loads(f.carga),
                 "recibido": _iso(f.recibido), "procesado": _iso(f.procesado), "resultado": f.resultado} for f in filas]


async def consultar_clave(clave: str) -> Optional[dict]:
    clave = pix.normalizar_clave(clave)
    async with base.sesion() as s:
        t = await vigente().consultar_clave(s, clave)
    if t is None:
        return None
    return {"clave": t.clave, "tipo": t.tipo, "nombre": t.nombre, "documento": t.documento_enmascarado,
            "ispb": t.ispb, "banco": t.banco}


async def resumen() -> dict:
    async with base.sesion() as s:
        filas = (await s.execute(select(operaciones.c.direccion, operaciones.c.estado, func.count())
                                 .group_by(operaciones.c.direccion, operaciones.c.estado))).all()
    salida = {}
    for direccion, estado, n in filas:
        salida[f"{direccion}_{estado}"] = int(n)
    return salida
