"""
El libro del núcleo: partida doble nativa, correlativo, encadenado, inmutable.

LAS CINCO REGLAS, Y DONDE SE HACEN CUMPLIR

    1. Cada asiento tiene al menos dos partidas y la suma de los debes es
       igual a la de los haberes. Se comprueba ANTES de escribir, en
       `_validar`. Un asiento descuadrado no llega a la base.
    2. Los montos son enteros positivos en centavos. Ni cero, ni negativo, ni
       float. Un float que llegue hasta acá es un error de quien llama.
    3. El número de asiento es correlativo y sin huecos. Se toma dentro de la
       misma transacción que escribe el asiento, así que dos escrituras
       concurrentes no pueden llevarse el mismo número: la clave primaria lo
       rechaza y la transacción perdedora se reintenta.
    4. Cada asiento lleva el hash del anterior y el suyo, calculado sobre su
       contenido canónico. Cambiar un asiento viejo rompe la cadena desde ahí,
       y `verificar_cadena` lo encuentra.
    5. Una referencia, un asiento. Pedir dos veces con la misma referencia
       devuelve el mismo asiento y no escribe nada: es la idempotencia por
       comando, y vive en la restricción única de la tabla, no en un `if`.

NO HAY FUNCION QUE EDITE NI BORRE

    A propósito. Un error contable se corrige con un asiento de ajuste que
    lo revierte, con su propia referencia y su propia explicación, y los dos
    quedan en el libro. Es la diferencia entre un libro y una planilla.

CADA ASIENTO DEJA UN EVENTO EN LA MISMA TRANSACCION

    «Se registró el asiento N» va a la bandeja de salida (`eventos`) dentro
    de la misma transacción que el asiento. Si el asiento no entra, el evento
    tampoco; si entra, el evento queda aunque el proceso muera un instante
    después. Lo que se hace con ese evento —avisar, informar— es asunto de
    la cola (`nucleo/cola.py`), no del libro. Lo mismo con el cierre del día.

EL SALDO SE DERIVA DE LAS PARTIDAS

    No hay columna de saldo en `cuentas`. El saldo es haber menos debe (para
    una cuenta de pasivo, que es lo que son las cuentas de pago), calculado
    sobre las partidas. Es más lento que un campo y es la única forma de que
    el saldo no pueda desviarse del libro: no existe un segundo número.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from nucleo.esquema import (
    ACREEDORA, HASH_DEL_PRINCIPIO, asientos, cierres, cuentas, partidas, plan_de_cuentas,
)


class AsientoInvalido(ValueError):
    """El asiento no cumple una regla. El mensaje dice cuál."""


class DiaCerrado(ValueError):
    """Se quiso asentar con fecha de un día ya cerrado."""


@dataclass(frozen=True)
class Partida:
    cuenta_contable: str
    debe: int = 0
    haber: int = 0
    cuenta: Optional[str] = None      # la cuenta de pago del titular, si la partida es de una


def _validar(lineas: Sequence[Partida]):
    if len(lineas) < 2:
        raise AsientoInvalido("Un asiento lleva al menos dos partidas.")
    total_debe = total_haber = 0
    for p in lineas:
        for nombre, valor in (("debe", p.debe), ("haber", p.haber)):
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise AsientoInvalido(f"El {nombre} tiene que ser un entero en centavos, no {type(valor).__name__}.")
            if valor < 0:
                raise AsientoInvalido(f"El {nombre} no puede ser negativo.")
        if (p.debe > 0) == (p.haber > 0):
            raise AsientoInvalido("Cada partida va al debe o al haber, con monto mayor que cero.")
        total_debe += p.debe
        total_haber += p.haber
    if total_debe != total_haber:
        raise AsientoInvalido(
            f"El asiento no cuadra: debe {total_debe} ≠ haber {total_haber} (centavos).")


def _hash_de(numero: int, fecha: date, descripcion: str, referencia: str, comando: str,
             actor: str, lineas: Sequence[Partida], hash_previo: str) -> str:
    """El hash del asiento, sobre una forma canónica: claves ordenadas, sin
    espacios, siempre la misma serialización. Cambiar cualquier campo cambia
    el hash."""
    canonico = json.dumps({
        "numero": numero, "fecha": fecha.isoformat(), "descripcion": descripcion,
        "referencia": referencia, "comando": comando, "actor": actor,
        "partidas": [[p.cuenta_contable, p.cuenta, p.debe, p.haber] for p in lineas],
        "hash_previo": hash_previo,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


async def _ultimo(sesion):
    """(numero, hash) del último asiento, o (0, HASH_DEL_PRINCIPIO)."""
    fila = (await sesion.execute(
        select(asientos.c.numero, asientos.c.hash).order_by(asientos.c.numero.desc()).limit(1)
    )).first()
    return (fila.numero, fila.hash) if fila else (0, HASH_DEL_PRINCIPIO)


async def _ultimo_dia_cerrado(sesion) -> Optional[date]:
    return (await sesion.execute(select(func.max(cierres.c.dia)))).scalar_one_or_none()


async def _existe_con_referencia(sesion, referencia: str):
    return (await sesion.execute(
        select(asientos).where(asientos.c.referencia == referencia))).first()


async def _comprobar_cuentas(sesion, lineas: Sequence[Partida]):
    codigos = {p.cuenta_contable for p in lineas}
    vivas = {c for (c,) in (await sesion.execute(
        select(plan_de_cuentas.c.codigo).where(plan_de_cuentas.c.codigo.in_(codigos)))).all()}
    faltan = codigos - vivas
    if faltan:
        raise AsientoInvalido(f"Cuenta contable inexistente: {', '.join(sorted(faltan))}.")
    de_titular = {p.cuenta for p in lineas if p.cuenta}
    if de_titular:
        filas = (await sesion.execute(
            select(cuentas.c.id, cuentas.c.estado).where(cuentas.c.id.in_(de_titular)))).all()
        estados = {f.id: f.estado for f in filas}
        faltan = de_titular - set(estados)
        if faltan:
            raise AsientoInvalido(f"Cuenta de pago inexistente: {', '.join(sorted(faltan))}.")
        cerradas = [c for c, e in estados.items() if e != "activa"]
        if cerradas:
            raise AsientoInvalido(f"Cuenta de pago no activa: {', '.join(sorted(cerradas))}.")


async def asentar(sesion, *, fecha: date, descripcion: str, referencia: str, comando: str,
                  actor: str, lineas: Sequence[Partida]) -> int:
    """Escribe un asiento y devuelve su número. Idempotente por referencia.

    Corre dentro de la transacción de `sesion`. Si otra transacción se llevó
    el mismo número correlativo, la clave primaria lo rechaza y `IntegrityError`
    sube: quien llama reintenta con una transacción nueva (`comandos` lo hace).
    """
    _validar(lineas)
    ya = await _existe_con_referencia(sesion, referencia)
    if ya:
        return ya.numero
    cerrado = await _ultimo_dia_cerrado(sesion)
    if cerrado is not None and fecha <= cerrado:
        raise DiaCerrado(f"El día {fecha.isoformat()} ya está cerrado (último cierre: {cerrado.isoformat()}).")
    await _comprobar_cuentas(sesion, lineas)

    anterior, hash_previo = await _ultimo(sesion)
    numero = anterior + 1
    hash_propio = _hash_de(numero, fecha, descripcion, referencia, comando, actor, lineas, hash_previo)
    await sesion.execute(asientos.insert().values(
        numero=numero, fecha=fecha, descripcion=descripcion, referencia=referencia,
        comando=comando, actor=actor, hash_previo=hash_previo, hash=hash_propio))
    await sesion.execute(partidas.insert(), [
        dict(asiento=numero, orden=i, cuenta_contable=p.cuenta_contable, cuenta=p.cuenta,
             debe=p.debe, haber=p.haber)
        for i, p in enumerate(lineas)
    ])
    # El evento, en la misma transacción. Ver el encabezado.
    from nucleo import cola
    await cola.anotar_evento(sesion, tipo="asiento_registrado", clave=f"asiento:{numero}", carga={
        "numero": numero, "fecha": fecha.isoformat(), "referencia": referencia, "comando": comando,
        "actor": actor, "descripcion": descripcion, "hash": hash_propio,
        "cuentas": sorted({p.cuenta for p in lineas if p.cuenta}),
    })
    return numero


async def saldo(sesion, cuenta_id: str) -> int:
    """El saldo de una cuenta de pago, en centavos: haber menos debe, porque
    es un pasivo. Positivo es plata del titular."""
    fila = (await sesion.execute(
        select(func.coalesce(func.sum(partidas.c.haber), 0), func.coalesce(func.sum(partidas.c.debe), 0))
        .where(partidas.c.cuenta == cuenta_id))).one()
    return int(fila[0]) - int(fila[1])


async def saldos(sesion, cuenta_ids: Sequence[str]) -> dict:
    if not cuenta_ids:
        return {}
    filas = (await sesion.execute(
        select(partidas.c.cuenta, func.coalesce(func.sum(partidas.c.haber), 0),
               func.coalesce(func.sum(partidas.c.debe), 0))
        .where(partidas.c.cuenta.in_(list(cuenta_ids))).group_by(partidas.c.cuenta))).all()
    resultado = {c: 0 for c in cuenta_ids}
    for cuenta_id, haber, debe in filas:
        resultado[cuenta_id] = int(haber) - int(debe)
    return resultado


async def balance_de_comprobacion(sesion, hasta: Optional[date] = None) -> dict:
    """Por cuenta contable: total debe, total haber y saldo según naturaleza.
    Cuadra si la suma de debes es igual a la de haberes."""
    consulta = (select(partidas.c.cuenta_contable, plan_de_cuentas.c.nombre, plan_de_cuentas.c.grupo,
                       plan_de_cuentas.c.naturaleza,
                       func.coalesce(func.sum(partidas.c.debe), 0),
                       func.coalesce(func.sum(partidas.c.haber), 0))
                .select_from(partidas.join(plan_de_cuentas, partidas.c.cuenta_contable == plan_de_cuentas.c.codigo))
                .group_by(partidas.c.cuenta_contable, plan_de_cuentas.c.nombre, plan_de_cuentas.c.grupo,
                          plan_de_cuentas.c.naturaleza)
                .order_by(partidas.c.cuenta_contable))
    if hasta is not None:
        consulta = consulta.where(partidas.c.asiento.in_(select(asientos.c.numero).where(asientos.c.fecha <= hasta)))
    filas = []
    total_debe = total_haber = 0
    for codigo, nombre, grupo, naturaleza, debe, haber in (await sesion.execute(consulta)).all():
        debe, haber = int(debe), int(haber)
        saldo_ = (haber - debe) if naturaleza == ACREEDORA else (debe - haber)
        filas.append({"codigo": codigo, "nombre": nombre, "grupo": grupo, "naturaleza": naturaleza,
                      "debe": debe, "haber": haber, "saldo": saldo_})
        total_debe += debe
        total_haber += haber
    return {"filas": filas, "total_debe": total_debe, "total_haber": total_haber,
            "cuadra": total_debe == total_haber}


async def verificar_cadena(sesion) -> dict:
    """Recorre todos los asientos y recalcula cada hash. Devuelve dónde se
    rompe, si se rompe. Es lo que un auditor haría a mano."""
    filas = (await sesion.execute(select(asientos).order_by(asientos.c.numero))).all()
    todas = (await sesion.execute(select(partidas).order_by(partidas.c.asiento, partidas.c.orden))).all()
    por_asiento = {}
    for p in todas:
        por_asiento.setdefault(p.asiento, []).append(
            Partida(cuenta_contable=p.cuenta_contable, debe=p.debe, haber=p.haber, cuenta=p.cuenta))
    esperado_previo = HASH_DEL_PRINCIPIO
    esperado_numero = 1
    for a in filas:
        if a.numero != esperado_numero:
            return {"ok": False, "asientos": len(filas), "roto_en": a.numero,
                    "motivo": f"hueco en la numeración: esperaba {esperado_numero}, hay {a.numero}"}
        if a.hash_previo != esperado_previo:
            return {"ok": False, "asientos": len(filas), "roto_en": a.numero,
                    "motivo": "el hash previo no coincide con el asiento anterior"}
        recalculado = _hash_de(a.numero, a.fecha, a.descripcion, a.referencia, a.comando, a.actor,
                               por_asiento.get(a.numero, []), a.hash_previo)
        if recalculado != a.hash:
            return {"ok": False, "asientos": len(filas), "roto_en": a.numero,
                    "motivo": "el contenido no coincide con su hash: el asiento fue alterado"}
        esperado_previo = a.hash
        esperado_numero += 1
    return {"ok": True, "asientos": len(filas), "roto_en": None, "motivo": None,
            "hash_final": esperado_previo}


async def cerrar_dia(sesion, dia: date, *, actor: str, nota: Optional[str] = None) -> dict:
    """Cierra un día: deja un renglón con hasta qué asiento llega, el hash
    final y los totales. Después nadie asienta con esa fecha ni anterior.

    Se cierra en orden: no se puede cerrar un día anterior al último cerrado,
    ni saltear días con asientos sin cerrar en el medio.
    """
    ultimo = await _ultimo_dia_cerrado(sesion)
    if ultimo is not None and dia <= ultimo:
        raise DiaCerrado(f"El día {dia.isoformat()} ya está cerrado (último cierre: {ultimo.isoformat()}).")
    hasta = (await sesion.execute(
        select(func.max(asientos.c.numero)).where(asientos.c.fecha <= dia))).scalar_one_or_none() or 0
    hash_final = HASH_DEL_PRINCIPIO
    if hasta:
        hash_final = (await sesion.execute(
            select(asientos.c.hash).where(asientos.c.numero == hasta))).scalar_one()
    cuantos = (await sesion.execute(
        select(func.count()).select_from(asientos).where(asientos.c.fecha <= dia))).scalar_one()
    desde = 0
    if ultimo is not None:
        desde = (await sesion.execute(
            select(cierres.c.hasta_asiento).where(cierres.c.dia == ultimo))).scalar_one()
    totales = (await sesion.execute(
        select(func.coalesce(func.sum(partidas.c.debe), 0), func.coalesce(func.sum(partidas.c.haber), 0))
        .where(partidas.c.asiento > desde, partidas.c.asiento <= hasta))).one()
    fila = dict(dia=dia, hasta_asiento=hasta, hash_final=hash_final, asientos=int(cuantos),
                total_debe=int(totales[0]), total_haber=int(totales[1]), cerrado_por=actor, nota=nota)
    await sesion.execute(cierres.insert().values(**fila))
    fila["dia"] = dia.isoformat()
    from nucleo import cola
    await cola.anotar_evento(sesion, tipo="dia_cerrado", clave=f"cierre:{fila['dia']}", carga={
        "dia": fila["dia"], "hasta_asiento": hasta, "hash_final": hash_final, "asientos": int(cuantos),
        "total_debe": fila["total_debe"], "total_haber": fila["total_haber"], "cerrado_por": actor,
    })
    return fila


async def listar_asientos(sesion, *, limite: int = 50, desde_numero: Optional[int] = None) -> list:
    consulta = select(asientos).order_by(asientos.c.numero.desc()).limit(limite)
    if desde_numero is not None:
        consulta = consulta.where(asientos.c.numero < desde_numero)
    cabeceras = (await sesion.execute(consulta)).all()
    if not cabeceras:
        return []
    numeros = [a.numero for a in cabeceras]
    lineas = (await sesion.execute(
        select(partidas).where(partidas.c.asiento.in_(numeros)).order_by(partidas.c.asiento, partidas.c.orden))).all()
    por_asiento = {}
    for p in lineas:
        por_asiento.setdefault(p.asiento, []).append(
            {"cuenta_contable": p.cuenta_contable, "cuenta": p.cuenta, "debe": p.debe, "haber": p.haber})
    return [{
        "numero": a.numero, "fecha": a.fecha.isoformat(), "momento": a.momento.isoformat() if a.momento else None,
        "descripcion": a.descripcion, "referencia": a.referencia, "comando": a.comando, "actor": a.actor,
        "hash_previo": a.hash_previo, "hash": a.hash, "partidas": por_asiento.get(a.numero, []),
    } for a in cabeceras]


async def listar_cierres(sesion, limite: int = 30) -> list:
    filas = (await sesion.execute(select(cierres).order_by(cierres.c.dia.desc()).limit(limite))).all()
    return [{"dia": f.dia.isoformat(), "hasta_asiento": f.hasta_asiento, "hash_final": f.hash_final,
             "asientos": f.asientos, "total_debe": f.total_debe, "total_haber": f.total_haber,
             "cerrado_en": f.cerrado_en.isoformat() if f.cerrado_en else None,
             "cerrado_por": f.cerrado_por, "nota": f.nota} for f in filas]


# Para que quien lea `IntegrityError` en `comandos` sepa qué es sin importar SQLAlchemy.
ChoqueDeEscritura = IntegrityError
