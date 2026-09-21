"""
Los comandos del núcleo: lo que se le puede pedir, en el idioma del negocio.

    Cada comando es UN asiento con sus partidas ya decididas. Quien llama no
    elige cuentas contables: dice «acreditá 100 reales a esta cuenta por este
    motivo» y el comando sabe que eso es debe en la cuenta de liquidación y
    haber en la cuenta del titular. Es la única forma de que el plan de
    cuentas no se reparta por toda la aplicación.

    Todos son idempotentes por referencia (ver `libro.asentar`) y reintentan
    una vez si chocan con otra escritura por el número correlativo.

LOS MONTOS ENTRAN COMO TEXTO Y SE CONVIERTEN UNA SOLA VEZ

    «100.00» → 10000 centavos, con `Decimal`, sin pasar por float. Un monto
    con más de dos decimales se rechaza: no se redondea plata en silencio.
"""
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from nucleo import base, libro, plan
from nucleo.esquema import cuentas
from nucleo.libro import AsientoInvalido, ChoqueDeEscritura, Partida

CENTAVOS = 100


class MontoInvalido(ValueError):
    pass


def a_centavos(texto) -> int:
    """«100.00» o «100,00» → 10000. Rechaza negativos, cero y más de dos decimales."""
    if isinstance(texto, bool) or isinstance(texto, float):
        raise MontoInvalido("El monto viaja como texto, nunca como float.")
    crudo = str(texto).strip().replace(",", ".")
    try:
        d = Decimal(crudo)
    except (InvalidOperation, ValueError):
        raise MontoInvalido(f"Monto ilegible: {texto!r}.")
    if d <= 0:
        raise MontoInvalido("El monto tiene que ser mayor que cero.")
    if d != d.quantize(Decimal("0.01")):
        raise MontoInvalido("El monto no puede tener más de dos decimales.")
    return int(d * CENTAVOS)


def a_texto(centavos: int) -> str:
    """10000 → «100.00». Para los bordes de la API."""
    signo = "-" if centavos < 0 else ""
    c = abs(int(centavos))
    return f"{signo}{c // CENTAVOS}.{c % CENTAVOS:02d}"


def _hoy() -> date:
    return datetime.now(timezone.utc).date()


def nuevo_id_de_cuenta() -> str:
    return "cta_" + secrets.token_hex(6)


async def crear_cuenta(*, titular_ref: str, moneda: str = "BRL", de_prueba: bool = True) -> dict:
    async with base.sesion() as s:
        await plan.sembrar(s)
        id_ = nuevo_id_de_cuenta()
        await s.execute(cuentas.insert().values(
            id=id_, titular_ref=titular_ref, cuenta_contable=plan.DE_TITULARES,
            moneda=moneda, estado="activa", de_prueba=de_prueba))
        return {"id": id_, "titular_ref": titular_ref, "moneda": moneda, "estado": "activa",
                "de_prueba": de_prueba, "saldo": "0.00"}


async def listar_cuentas(limite: int = 100) -> list:
    async with base.sesion() as s:
        filas = (await s.execute(select(cuentas).order_by(cuentas.c.creada.desc()).limit(limite))).all()
        saldos = await libro.saldos(s, [f.id for f in filas])
        return [{"id": f.id, "titular_ref": f.titular_ref, "moneda": f.moneda, "estado": f.estado,
                 "de_prueba": f.de_prueba, "saldo": a_texto(saldos.get(f.id, 0)),
                 "creada": f.creada.isoformat() if f.creada else None} for f in filas]


async def _asentar_con_reintento(**kw) -> int:
    """Dos intentos: si la primera transacción choca con otra por el número
    correlativo, la segunda lo toma de nuevo. Más de dos es otro problema."""
    for intento in (1, 2):
        try:
            async with base.sesion() as s:
                return await libro.asentar(s, **kw)
        except ChoqueDeEscritura:
            if intento == 2:
                raise
    raise RuntimeError("inalcanzable")


async def acreditar(*, cuenta_id: str, monto: str, referencia: str, actor: str,
                    descripcion: str = "Acreditación", fecha: date = None) -> int:
    """Entra plata a la cuenta del titular desde la cuenta de liquidación."""
    c = a_centavos(monto)
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="acreditar",
        actor=actor, lineas=[
            Partida(plan.LIQUIDACION, debe=c),
            Partida(plan.DE_TITULARES, haber=c, cuenta=cuenta_id),
        ])


async def debitar(*, cuenta_id: str, monto: str, referencia: str, actor: str,
                  descripcion: str = "Débito", fecha: date = None) -> int:
    """Sale plata de la cuenta del titular hacia la cuenta de liquidación.
    Exige saldo: la cuenta de pago de un titular no queda en negativo."""
    c = a_centavos(monto)
    async with base.sesion() as s:
        disponible = await libro.saldo(s, cuenta_id)
    if disponible < c:
        raise AsientoInvalido(
            f"Saldo insuficiente: hay {a_texto(disponible)} y se piden {a_texto(c)}.")
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="debitar",
        actor=actor, lineas=[
            Partida(plan.DE_TITULARES, debe=c, cuenta=cuenta_id),
            Partida(plan.LIQUIDACION, haber=c),
        ])


async def transferir(*, desde: str, hacia: str, monto: str, referencia: str, actor: str,
                     descripcion: str = "Transferencia entre cuentas", fecha: date = None) -> int:
    """Entre dos cuentas de pago del núcleo, en UN asiento. Exige saldo."""
    if desde == hacia:
        raise AsientoInvalido("Una transferencia va de una cuenta a otra distinta.")
    c = a_centavos(monto)
    async with base.sesion() as s:
        disponible = await libro.saldo(s, desde)
    if disponible < c:
        raise AsientoInvalido(
            f"Saldo insuficiente: hay {a_texto(disponible)} y se piden {a_texto(c)}.")
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="transferir",
        actor=actor, lineas=[
            Partida(plan.DE_TITULARES, debe=c, cuenta=desde),
            Partida(plan.DE_TITULARES, haber=c, cuenta=hacia),
        ])


async def cobrar_tarifa(*, cuenta_id: str, monto: str, referencia: str, actor: str,
                        descripcion: str = "Tarifa", fecha: date = None) -> int:
    """Una tarifa: sale de la cuenta del titular y es ingreso de la institución."""
    c = a_centavos(monto)
    async with base.sesion() as s:
        disponible = await libro.saldo(s, cuenta_id)
    if disponible < c:
        raise AsientoInvalido(
            f"Saldo insuficiente: hay {a_texto(disponible)} y se piden {a_texto(c)}.")
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="tarifa",
        actor=actor, lineas=[
            Partida(plan.DE_TITULARES, debe=c, cuenta=cuenta_id),
            Partida(plan.TARIFAS, haber=c),
        ])


# ─── los tres asientos de un pago saliente ────────────────────────────────
#
#   Un pago por PIX no es un débito: entre que se ordena y que el SPI lo
#   liquida pasan segundos, y en ese rato la plata ya no es del titular pero
#   tampoco salió del banco. Por eso son tres asientos y no uno:
#
#     1. reservar   titular → obligaciones por pagos en tránsito (2.1.02)
#     2. liquidar   tránsito → cuenta de liquidación (la plata salió)
#     3. revertir   tránsito → titular (el SPI lo rechazó; la plata vuelve)
#
#   Cada uno con su referencia propia, así un aviso repetido del riel no
#   liquida dos veces ni revierte lo ya liquidado.

async def reservar_para_pago(*, cuenta_id: str, monto: str, referencia: str, actor: str,
                             descripcion: str = "Pago ordenado, en tránsito", fecha: date = None) -> int:
    c = a_centavos(monto)
    async with base.sesion() as s:
        disponible = await libro.saldo(s, cuenta_id)
    if disponible < c:
        raise AsientoInvalido(
            f"Saldo insuficiente: hay {a_texto(disponible)} y se piden {a_texto(c)}.")
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="reservar_pago",
        actor=actor, lineas=[
            Partida(plan.DE_TITULARES, debe=c, cuenta=cuenta_id),
            Partida(plan.TRANSITO, haber=c),
        ])


async def liquidar_pago(*, monto: str, referencia: str, actor: str,
                        descripcion: str = "Pago liquidado por el SPI", fecha: date = None) -> int:
    c = a_centavos(monto)
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="liquidar_pago",
        actor=actor, lineas=[
            Partida(plan.TRANSITO, debe=c),
            Partida(plan.LIQUIDACION, haber=c),
        ])


async def revertir_pago(*, cuenta_id: str, monto: str, referencia: str, actor: str,
                        descripcion: str = "Pago rechazado, vuelve al titular", fecha: date = None) -> int:
    c = a_centavos(monto)
    return await _asentar_con_reintento(
        fecha=fecha or _hoy(), descripcion=descripcion, referencia=referencia, comando="revertir_pago",
        actor=actor, lineas=[
            Partida(plan.TRANSITO, debe=c),
            Partida(plan.DE_TITULARES, haber=c, cuenta=cuenta_id),
        ])


async def cerrar_dia(*, dia: date, actor: str, nota: str = None) -> dict:
    async with base.sesion() as s:
        return await libro.cerrar_dia(s, dia, actor=actor, nota=nota)


async def estado() -> dict:
    """Lo que la pestaña del panel muestra arriba de todo."""
    if not base.hay_base():
        return {"base": "sin configurar", "conectada": False, "cuentas": 0, "asientos": 0,
                "ultimo_cierre": None, "cadena": None, "cola": None}
    try:
        async with base.sesion() as s:
            from sqlalchemy import func
            from nucleo.esquema import asientos, cierres
            n_cuentas = (await s.execute(select(func.count()).select_from(cuentas))).scalar_one()
            n_asientos = (await s.execute(select(func.count()).select_from(asientos))).scalar_one()
            ultimo = (await s.execute(select(func.max(cierres.c.dia)))).scalar_one_or_none()
            cadena = await libro.verificar_cadena(s)
            from nucleo import cola
            resumen_de_la_cola = await cola.resumen(s)
        return {"base": base.descripcion_de_la_url(), "conectada": True, "cuentas": int(n_cuentas),
                "asientos": int(n_asientos), "ultimo_cierre": ultimo.isoformat() if ultimo else None,
                "cadena": cadena, "cola": resumen_de_la_cola}
    except Exception as e:  # la pestaña tiene que poder decir «no conecta» sin caerse
        return {"base": base.descripcion_de_la_url(), "conectada": False, "cuentas": 0, "asientos": 0,
                "ultimo_cierre": None, "cadena": None, "cola": None, "detalle": type(e).__name__}
