"""
El monitoreo: reglas sobre lo que ya pasó, con umbrales que se configuran
desde el panel.

CUANDO CORRE

    Cada vez que una operación por un riel queda liquidada, `operaciones`
    deja un evento «operacion_liquidada», la cola lo convierte en el trabajo
    «evaluar_riesgo», y ese trabajo llama a `evaluar_operacion`. O sea: con
    reintentos, y sin que un fallo en una regla le toque la plata a nadie.

LAS REGLAS

    umbral_operacion      la operación sola llega al umbral
    acumulado_30_dias     lo liquidado por el titular en 30 días llega al umbral
    acumulado_12_meses    ídem en 12 meses
    fraccionamiento       tres o más operaciones bajo el umbral, en pocas horas,
                          que juntas lo pasan: la forma clásica de esquivarlo
    velocidad             más de N operaciones en una hora
    contraparte_repetida  la misma clave cinco veces o más en 24 horas
    horario               entre las 0 y las 5 de la mañana

    Cada regla deja UNA alerta por operación (única por operación y regla),
    y las alertas de una operación abren o engordan el caso abierto del
    titular. Ninguna regla bloquea la operación: ya está liquidada. Lo que
    sigue es de una persona.

LOS UMBRALES

    Salen del catálogo de `services/configuracion.py` y se cambian desde el
    panel del super administrador. Si no se pueden leer, se usan los de
    fábrica: en monitoreo, fallar cerrado es alertar de más, nunca de menos.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select

from nucleo import base
from nucleo.esquema import alertas, cuentas, operaciones

REGLAS = ("umbral_operacion", "acumulado_30_dias", "acumulado_12_meses", "fraccionamiento",
          "velocidad", "contraparte_repetida", "horario")

# Las claves del catálogo de configuración, y lo de fábrica por si no se
# pueden leer. Los montos en reales; acá se pasan a centavos.
DE_FABRICA = {
    "nucleo_umbral_operacion": Decimal("10000.00"),
    "nucleo_umbral_30_dias": Decimal("50000.00"),
    "nucleo_umbral_12_meses": Decimal("300000.00"),
    "nucleo_fraccionamiento_horas": 24,
    "nucleo_velocidad_por_hora": 10,
}
MINIMO_PARA_FRACCIONAR = 3
CONTRAPARTE_REPETIDA_VECES = 5
HORARIO_INUSUAL = range(0, 6)
# Brasilia no cambia de hora desde 2019: un desfasaje fijo alcanza y no
# depende de que la máquina tenga la base de zonas horarias.
HORA_DE_BRASIL = timezone(timedelta(hours=-3))


async def umbrales(db=None) -> dict:
    """Los umbrales vigentes, en centavos y enteros."""
    valores = dict(DE_FABRICA)
    try:
        from services import configuracion
        if db is None:
            from database import db as real
            db = real
        for clave in DE_FABRICA:
            valores[clave] = await configuracion.leer(db, clave)
    except Exception:
        pass                                             # lo de fábrica, que es más estricto
    return {
        "umbral_operacion": int(Decimal(valores["nucleo_umbral_operacion"]) * 100),
        "umbral_30_dias": int(Decimal(valores["nucleo_umbral_30_dias"]) * 100),
        "umbral_12_meses": int(Decimal(valores["nucleo_umbral_12_meses"]) * 100),
        "fraccionamiento_horas": int(valores["nucleo_fraccionamiento_horas"]),
        "velocidad_por_hora": int(valores["nucleo_velocidad_por_hora"]),
    }


def _iso(dt):
    return dt.isoformat() if dt else None


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _liquidadas_del_titular(sesion, titular_ref: str, desde: datetime):
    """Las operaciones liquidadas de todas las cuentas del titular desde una fecha."""
    return (await sesion.execute(
        select(operaciones).join(cuentas, operaciones.c.cuenta == cuentas.c.id)
        .where(cuentas.c.titular_ref == titular_ref, operaciones.c.estado == "liquidada",
               operaciones.c.actualizada >= desde)
        .order_by(operaciones.c.actualizada))).all()


async def evaluar_operacion(operacion_id: str, *, db=None, ahora: Optional[datetime] = None) -> list:
    """Corre todas las reglas sobre una operación liquidada. Devuelve las
    alertas nuevas. Idempotente: la misma operación evaluada dos veces no
    duplica alertas."""
    ahora = ahora or datetime.now(timezone.utc)
    u = await umbrales(db)
    async with base.sesion() as s:
        op = (await s.execute(select(operaciones).where(operaciones.c.id == operacion_id))).first()
        if op is None or op.estado != "liquidada":
            return []
        cuenta = (await s.execute(select(cuentas).where(cuentas.c.id == op.cuenta))).first()
        titular_ref = cuenta.titular_ref
        momento = _aware(op.actualizada) or ahora
        hallazgos = []

        if op.monto >= u["umbral_operacion"]:
            hallazgos.append(("umbral_operacion", {"monto": op.monto, "umbral": u["umbral_operacion"]}))

        mes = await _liquidadas_del_titular(s, titular_ref, momento - timedelta(days=30))
        total_mes = sum(o.monto for o in mes)
        if total_mes >= u["umbral_30_dias"]:
            hallazgos.append(("acumulado_30_dias", {"acumulado": total_mes, "umbral": u["umbral_30_dias"], "operaciones": len(mes)}))

        anio = await _liquidadas_del_titular(s, titular_ref, momento - timedelta(days=365))
        total_anio = sum(o.monto for o in anio)
        if total_anio >= u["umbral_12_meses"]:
            hallazgos.append(("acumulado_12_meses", {"acumulado": total_anio, "umbral": u["umbral_12_meses"], "operaciones": len(anio)}))

        ventana = [o for o in mes if _aware(o.actualizada) >= momento - timedelta(hours=u["fraccionamiento_horas"])]
        chicas = [o for o in ventana if o.monto < u["umbral_operacion"]]
        if len(chicas) >= MINIMO_PARA_FRACCIONAR and sum(o.monto for o in chicas) >= u["umbral_operacion"]:
            hallazgos.append(("fraccionamiento", {"operaciones": len(chicas), "suma": sum(o.monto for o in chicas),
                                                  "umbral": u["umbral_operacion"], "horas": u["fraccionamiento_horas"]}))

        ultima_hora = [o for o in ventana if _aware(o.actualizada) >= momento - timedelta(hours=1)]
        if len(ultima_hora) > u["velocidad_por_hora"]:
            hallazgos.append(("velocidad", {"operaciones": len(ultima_hora), "maximo": u["velocidad_por_hora"]}))

        if op.clave:
            mismas = [o for o in ventana if o.clave == op.clave and _aware(o.actualizada) >= momento - timedelta(hours=24)]
            if len(mismas) >= CONTRAPARTE_REPETIDA_VECES:
                hallazgos.append(("contraparte_repetida", {"clave": op.clave, "veces": len(mismas)}))

        hora_local = momento.astimezone(HORA_DE_BRASIL).hour
        if hora_local in HORARIO_INUSUAL:
            hallazgos.append(("horario", {"hora": hora_local}))

        existentes = {r for (r,) in (await s.execute(
            select(alertas.c.regla).where(alertas.c.operacion == operacion_id))).all()}
        nuevas = []
        for regla, detalle in hallazgos:
            if regla in existentes:
                continue
            r = await s.execute(alertas.insert().values(
                titular=titular_ref, cuenta=op.cuenta, operacion=operacion_id, regla=regla,
                detalle=json.dumps(detalle, sort_keys=True, ensure_ascii=False)))
            nuevas.append({"id": r.inserted_primary_key[0], "regla": regla, "detalle": detalle,
                           "titular": titular_ref, "operacion": operacion_id})
    if nuevas:
        from nucleo.riesgo import casos
        caso = await casos.abrir(titular=titular_ref, origen="alerta", actor="monitoreo",
                                 detalle="; ".join(f"{a['regla']}" for a in nuevas), ahora=ahora)
        async with base.sesion() as s:
            await s.execute(alertas.update().where(alertas.c.id.in_([a["id"] for a in nuevas])).values(caso=caso["id"]))
        for a in nuevas:
            a["caso"] = caso["id"]
    return nuevas


async def evaluar_riesgo(carga: dict) -> str:
    """Manejador de la cola."""
    nuevas = await evaluar_operacion(carga["operacion"])
    return "sin alertas" if not nuevas else "alertas: " + ", ".join(a["regla"] for a in nuevas)


async def listar(limite: int = 100, titular: Optional[str] = None) -> list:
    async with base.sesion() as s:
        q = select(alertas).order_by(alertas.c.id.desc()).limit(limite)
        if titular:
            q = q.where(alertas.c.titular == titular)
        return [{"id": a.id, "titular": a.titular, "cuenta": a.cuenta, "operacion": a.operacion, "regla": a.regla,
                 "detalle": json.loads(a.detalle) if a.detalle else {}, "momento": _iso(a.momento), "caso": a.caso}
                for a in (await s.execute(q)).all()]


async def resumen() -> dict:
    async with base.sesion() as s:
        filas = (await s.execute(select(alertas.c.regla, func.count()).group_by(alertas.c.regla))).all()
    return {r: int(n) for r, n in filas}
