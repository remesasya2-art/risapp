"""
El cuatro ojos general: pedir, aprobar, ejecutar.

POR QUE UN MECANISMO Y NO UNO POR ACCION

    El riesgo ya tenía cuatro ojos para comunicar al COAF, escrito a mano
    dentro del caso. Cada acción sensible nueva iba a repetir la misma regla
    con otra forma, y una regla repetida es una regla que en algún lugar se
    escribe mal. Acá hay UN pedido, UNA decisión y UN registro de ejecutores:
    la acción se nombra, y el mecanismo es el mismo para todas.

QUE PASA POR ACA

    configurar            cambiar `nucleo_modo` o un umbral del monitoreo
                          MIENTRAS EL NUCLEO ESTA PRENDIDO. Prenderlo desde
                          apagado no: todavía no hay nada que proteger, y con
                          un solo super administrador sería imposible.
    transmitir_reporte    mandarle un archivo al regulador.
    comunicar_incidente   avisarle al BCB de un incidente relevante.

    Las que ya tenían su propio cuatro ojos (comunicar al COAF, la no
    ocurrencia) lo conservan: están probadas y son de la Circular 3.978.

LAS REGLAS

    - Quien decide no puede ser quien pidió. Es la regla entera.
    - Un pedido vence a las 72 horas: una aprobación vieja no debería
      ejecutar algo que ya cambió de contexto.
    - Un pedido pendiente por acción y objetivo: pedir dos veces lo mismo
      devuelve el mismo pedido.
    - Aprobar EJECUTA en la misma llamada. Si la ejecución falla, el pedido
      queda «fallido» con el error, y se vuelve a pedir. No se reintenta a
      ciegas algo que ya le habló al regulador.
    - Todo deja renglón en la bitácora, en la misma sesión que la decisión.

LA GUARDA DE CONFIGURACION

    `services/configuracion.py` no conoce el núcleo (frontera). Tiene una
    lista `GUARDAS` de funciones a las que consulta antes de escribir, y
    `server.py` mete la de acá. La guarda deja pasar cualquier clave que no
    sea del núcleo, deja pasar las del núcleo con el núcleo apagado, y frena
    las del núcleo prendido salvo que esté ejecutando un pedido aprobado
    (`_EJECUTANDO` es una variable de contexto, no una bandera global: dos
    pedidos a la vez no se pisan).
"""
import contextvars
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from nucleo import base, modo
from nucleo.esquema import aprobaciones
from nucleo.operacion import bitacora

PENDIENTE, APROBADO, RECHAZADO, EJECUTADO, FALLIDO, VENCIDO = "pendiente", "aprobado", "rechazado", "ejecutado", "fallido", "vencido"
HORAS_DE_VIGENCIA = 72
CLAVES_DEL_NUCLEO = "nucleo_"

_EJECUTANDO = contextvars.ContextVar("nucleo_ejecutando_aprobado", default=False)


class AprobacionInvalida(ValueError):
    pass


def _ahora():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(v):
    return _aware(v).isoformat() if v else None


def _fila(a) -> dict:
    return {"id": a.id, "accion": a.accion, "objetivo": a.objetivo, "carga": json.loads(a.carga), "motivo": a.motivo,
            "estado": a.estado, "pedido_por": a.pedido_por, "pedido_en": _iso(a.pedido_en), "vence_en": _iso(a.vence_en),
            "decidido_por": a.decidido_por, "decidido_en": _iso(a.decidido_en), "nota": a.nota,
            "ejecutado_en": _iso(a.ejecutado_en), "resultado": a.resultado}


# ─── los ejecutores ───────────────────────────────────────────────────────

async def _ejecutar_configurar(carga: dict, actor: str) -> str:
    from database import db
    from services import configuracion
    clave, escrito = carga["clave"], carga["valor"]
    valor, motivo = configuracion.normalizar(clave, escrito)
    if motivo:
        raise AprobacionInvalida(motivo)
    antes = await configuracion.leer(db, clave)
    marca = _EJECUTANDO.set(True)
    try:
        # Por las mismas guardas que la pantalla de Configuración. La de acá
        # se llama directo (deja pasar porque `_EJECUTANDO` está puesto, y
        # anota el cambio) por si nadie la registró todavía, como en los
        # tests; las demás, por la lista.
        await guarda_de_configuracion(db, {clave: valor})
        for otra in configuracion.GUARDAS:
            if otra is not guarda_de_configuracion:
                await otra(db, {clave: valor})
        await configuracion.escribir(db, clave, valor)
    finally:
        _EJECUTANDO.reset(marca)
    return f"{clave}: {antes} → {valor}"


async def _ejecutar_transmitir_reporte(carga: dict, actor: str) -> str:
    from nucleo.reportes import registro
    r = await registro.transmitir(int(carga["reporte_id"]), actor=actor)
    return f"protocolo {r['protocolo']}"


async def _ejecutar_comunicar_incidente(carga: dict, actor: str) -> str:
    from nucleo.cumplimiento import incidentes
    i = await incidentes.comunicar(carga["incidente_id"], actor=actor)
    return f"protocolo {i['protocolo']}"


EJECUTORES = {
    "configurar": _ejecutar_configurar,
    "transmitir_reporte": _ejecutar_transmitir_reporte,
    "comunicar_incidente": _ejecutar_comunicar_incidente,
}


# ─── pedir y decidir ──────────────────────────────────────────────────────

async def _pedido(sesion, pedido_id: str):
    a = (await sesion.execute(select(aprobaciones).where(aprobaciones.c.id == pedido_id))).first()
    if a is None:
        raise AprobacionInvalida(f"No existe el pedido {pedido_id}.")
    return a


async def pedir(*, accion: str, objetivo: str, carga: dict, actor: str, motivo: str, ahora: Optional[datetime] = None) -> dict:
    ahora = ahora or _ahora()
    if accion not in EJECUTORES:
        raise AprobacionInvalida(f"No hay cuatro ojos para «{accion}».")
    if not motivo.strip():
        raise AprobacionInvalida("Un pedido lleva motivo: quien aprueba tiene que saber por qué.")
    async with base.sesion() as s:
        abierto = (await s.execute(select(aprobaciones).where(
            aprobaciones.c.accion == accion, aprobaciones.c.objetivo == objetivo,
            aprobaciones.c.estado == PENDIENTE))).first()
        if abierto is not None:
            return _fila(abierto)
        id_ = f"apr_{secrets.token_hex(6)}"
        await s.execute(aprobaciones.insert().values(
            id=id_, accion=accion, objetivo=objetivo, carga=json.dumps(carga, ensure_ascii=False, default=str),
            motivo=motivo.strip(), estado=PENDIENTE, pedido_por=actor, pedido_en=ahora,
            vence_en=ahora + timedelta(hours=HORAS_DE_VIGENCIA)))
        await bitacora.anotar(s, actor=actor, accion="aprobacion.pedida", objetivo=id_,
                              despues={"accion": accion, "objetivo": objetivo, "carga": carga}, detalle=motivo.strip()[:300], ahora=ahora)
        return _fila(await _pedido(s, id_))


async def decidir(pedido_id: str, *, actor: str, aprobar: bool, nota: Optional[str] = None,
                  ahora: Optional[datetime] = None) -> dict:
    """La segunda firma. Aprobar ejecuta en la misma llamada."""
    ahora = ahora or _ahora()
    async with base.sesion() as s:
        a = await _pedido(s, pedido_id)
        vencido = a.estado == PENDIENTE and _aware(a.vence_en) < ahora
        if vencido:
            # La marca de vencido va en ESTA sesión y se lanza DESPUES de
            # salir: lanzar adentro deshace la transacción y la marca se
            # pierde (ya pasó en el legajo, con el mismo patrón).
            await s.execute(aprobaciones.update().where(aprobaciones.c.id == pedido_id).values(estado=VENCIDO))
            await bitacora.anotar(s, actor=actor, accion="aprobacion.vencida", objetivo=pedido_id, ahora=ahora)
    if vencido:
        raise AprobacionInvalida(f"El pedido {pedido_id} venció a las {HORAS_DE_VIGENCIA} horas; hay que pedirlo de nuevo.")
    async with base.sesion() as s:
        a = await _pedido(s, pedido_id)
        if a.estado != PENDIENTE:
            raise AprobacionInvalida(f"El pedido {pedido_id} ya está {a.estado}.")
        if actor == a.pedido_por:
            raise AprobacionInvalida("Cuatro ojos: quien decide no puede ser quien pidió.")
        estado = APROBADO if aprobar else RECHAZADO
        await s.execute(aprobaciones.update().where(aprobaciones.c.id == pedido_id).values(
            estado=estado, decidido_por=actor, decidido_en=ahora, nota=(nota or "").strip() or None))
        await bitacora.anotar(s, actor=actor, accion="aprobacion.aprobada" if aprobar else "aprobacion.rechazada",
                              objetivo=pedido_id, antes={"estado": PENDIENTE}, despues={"estado": estado}, detalle=(nota or "")[:300] or None, ahora=ahora)
        carga = json.loads(a.carga)
        accion = a.accion
        pedido_por = a.pedido_por
    if not aprobar:
        return await detalle(pedido_id)
    # La ejecución va FUERA de la sesión de la decisión: la decisión ya
    # quedó, pase lo que pase con la ejecución; y el ejecutor abre las
    # sesiones que necesite (transmitir, por ejemplo, escribe en reportes).
    try:
        resultado = await EJECUTORES[accion](carga, actor)
        estado, texto = EJECUTADO, resultado
    except Exception as e:
        estado, texto = FALLIDO, f"{type(e).__name__}: {e}"
    async with base.sesion() as s:
        await s.execute(aprobaciones.update().where(aprobaciones.c.id == pedido_id).values(
            estado=estado, ejecutado_en=ahora, resultado=texto))
        await bitacora.anotar(s, actor=f"{pedido_por} + {actor}", accion=f"aprobacion.{estado}", objetivo=pedido_id,
                              despues={"accion": accion, "carga": carga, "resultado": texto}, ahora=ahora)
    if estado == FALLIDO:
        raise AprobacionInvalida(f"Aprobado, pero la ejecución falló: {texto}. El pedido queda «fallido»; hay que pedirlo de nuevo.")
    return await detalle(pedido_id)


# ─── la guarda de configuración ───────────────────────────────────────────

async def guarda_de_configuracion(db, cambios: dict) -> None:
    """La consulta `services.configuracion.comprobar_guardas` antes de escribir.
    Lanza `CambioNoPermitido` si hay claves del núcleo y el núcleo está
    prendido, salvo que se esté ejecutando un pedido aprobado."""
    from services import configuracion
    del_nucleo = sorted(c for c in cambios if c.startswith(CLAVES_DEL_NUCLEO))
    if not del_nucleo:
        return
    vigente = await modo.leer(db)
    if not modo.se_puede_usar(vigente):
        return                                             # apagado: prenderlo o ajustarlo no exige a nadie más
    if _EJECUTANDO.get():
        if base.hay_base():
            async with base.sesion() as s:
                for clave in del_nucleo:
                    await bitacora.anotar(s, actor="cuatro ojos", accion="config.cambio", objetivo=clave,
                                          antes={"valor": str(await configuracion.leer(db, clave))},
                                          despues={"valor": str(cambios[clave])})
        return
    raise configuracion.CambioNoPermitido(
        "El núcleo está prendido: " + ", ".join(del_nucleo) + " se cambia con cuatro ojos, desde la pestaña «Núcleo» "
        "(uno lo pide, otra persona lo aprueba).")


# ─── para mirar ───────────────────────────────────────────────────────────

async def detalle(pedido_id: str) -> dict:
    async with base.sesion() as s:
        return _fila(await _pedido(s, pedido_id))


async def listar(limite: int = 50, ahora: Optional[datetime] = None) -> list:
    """Con los vencidos marcados al pasar: un pendiente viejo no se ofrece
    para aprobar."""
    ahora = ahora or _ahora()
    async with base.sesion() as s:
        filas = (await s.execute(select(aprobaciones).order_by(aprobaciones.c.pedido_en.desc(), aprobaciones.c.id.desc()).limit(limite))).all()
        salida = []
        for a in filas:
            f = _fila(a)
            if a.estado == PENDIENTE and _aware(a.vence_en) < ahora:
                f["estado"] = VENCIDO
            salida.append(f)
        return salida


async def resumen(ahora: Optional[datetime] = None) -> dict:
    salida = {e: 0 for e in (PENDIENTE, APROBADO, RECHAZADO, EJECUTADO, FALLIDO, VENCIDO)}
    for a in await listar(limite=10_000, ahora=ahora):
        salida[a["estado"]] += 1
    return salida
