"""
services/bancos.py — El saldo de las cuentas bancarias, en un solo lugar.

POR QUE EXISTE ESTE MODULO

    `bank_accounts.balance` se escribía desde TRECE lugares, con dos tipos
    distintos: unos `$inc` con `Decimal128` (el ajuste manual de contabilidad) y
    otros con `float` (la aprobación de recargas, Mercado Pago, la pasarela de
    tarjeta, la compra/venta de USDT, el puente de reales).

    Mongo acepta las dos cosas y convierte el campo al tipo del último operando
    que lo tocó. El problema aparece del lado de Python: `Decimal128` NO soporta
    aritmética con `float`, y tampoco `float(...)`:

        >>> Decimal128(Decimal("1000")) + 500.0
        TypeError: unsupported operand type(s) for +: 'Decimal128' and 'float'
        >>> float(Decimal128(Decimal("1000")))
        TypeError

    Y SEIS rutas hacían exactamente eso, para calcular el saldo que anotan en el
    libro bancario:

        routes/admin.py:1821          bank["balance"] + amount_ves
        routes/accounting.py:266      bank["balance"] + total_fiat
        routes/accounting.py:296      bank["balance"] - total_fiat
        routes/adminbrl_bridge.py:191 bank["balance"] - amount_output
        routes/gestor_pix.py:407      float(bank.get("balance", 0)) + ...
        routes/payments_card.py:97    float(bank.get("balance", 0)) + ...

    O sea: **el primer ajuste manual sobre una cuenta la deja en `Decimal128`, y
    a partir de ahí esas seis rutas devuelven 500 sobre esa cuenta.** Ninguna
    está dentro de un `try`. No es un riesgo teórico: es una bomba de tiempo con
    la espoleta en el panel de contabilidad.

EL SEGUNDO DEFECTO, MAS SILENCIOSO

    Todos esos sitios calculaban el saldo posterior a partir de una lectura
    ANTERIOR al `$inc`:

        bank = await db.bank_accounts.find_one(...)      # lee 1000
        await db.bank_accounts.update_one(..., {"$inc": ...})
        new_balance = bank["balance"] + monto             # 1000 + 100 = 1100

    Con dos operaciones simultáneas sobre la misma cuenta, las dos leen 1000 y
    las dos anotan 1100 en `bank_ledger`, cuando el saldo real quedó en 1200. El
    `$inc` es atómico, pero el número que se archiva no sale de él. Acá el saldo
    posterior sale del RESULTADO de la escritura, que es el único valor que de
    verdad ocurrió.

POR QUE IMPORTA PARA LA CUENTA OMNIBUS

    Con un solo pozo en el proveedor, la única forma de saber que la plata
    cierra es comparar la suma de los saldos de los usuarios contra el dinero
    real de las cuentas. Ese control no puede pararse sobre un campo que a veces
    es `float`, a veces `Decimal128`, y cuyo historial anota saldos que no
    ocurrieron.
"""

from decimal import Decimal

from services.money import from_db, quantize_money, to_decimal, to_decimal128

# El nombre de la colección, en un solo lugar.
COLECCION = "bank_accounts"


class CuentaInexistente(Exception):
    """No hay ninguna cuenta con ese `bank_id`."""

    def __init__(self, bank_id):
        self.bank_id = bank_id
        super().__init__(f"No existe la cuenta bancaria {bank_id}")


class CuentaNoDisponible(Exception):
    """La cuenta existe pero no cumple las condiciones exigidas (p. ej. oculta)."""

    def __init__(self, bank_id, condiciones):
        self.bank_id = bank_id
        self.condiciones = condiciones
        super().__init__(
            f"La cuenta {bank_id} no está disponible para esta operación: "
            f"no cumple {condiciones}")


class SaldoInsuficiente(Exception):
    """El débito no se hizo porque la cuenta no tenía con qué."""

    def __init__(self, bank_id, pedido, disponible=None):
        self.bank_id = bank_id
        self.pedido = pedido
        self.disponible = disponible
        super().__init__(
            f"El banco {bank_id} no tiene saldo suficiente: se pedían {pedido}"
            + (f" y hay {disponible}" if disponible is not None else "")
        )


def saldo_de(banco) -> Decimal:
    """El saldo de una cuenta, como Decimal, venga como venga de la base.

    `from_db` acepta `float`, `Decimal128`, `str` y `None`, así que esto
    funciona igual sobre una cuenta vieja que nunca se tocó y sobre una que ya
    pasó por el ajuste manual.
    """
    if banco is None:
        return Decimal("0.00")
    return from_db(banco.get("balance"))


async def ajustar(db, bank_id: str, delta, *, session=None,
                  exigir_saldo: bool = False, filtro_extra: dict = None) -> dict:
    """Suma `delta` al saldo de una cuenta y devuelve el saldo REAL resultante.

    Devuelve `{"saldo_anterior", "saldo_nuevo", "banco"}`, todos en Decimal, con
    el saldo nuevo tomado del documento DESPUES de la escritura: es el único
    número que de verdad quedó en la base.

    `delta` puede ser positivo (entrada) o negativo (salida), y se acepta como
    `float`, `str`, `Decimal` o `Decimal128`: se normaliza acá para que quien
    llama no tenga que acordarse.

    Con `exigir_saldo=True` el débito sólo ocurre si la cuenta tiene con qué, y
    la comprobación va DENTRO del filtro de la escritura: entre mirar y descontar
    no hay ventana para que otra operación se lleve la plata. Si no alcanza,
    levanta `SaldoInsuficiente` y no escribe nada.
    """
    monto = quantize_money(to_decimal(delta))

    filtro = {"bank_id": bank_id}
    if filtro_extra:
        # Condiciones que tienen que valer EN EL MOMENTO de la escritura, no
        # antes. El débito del motor contable excluye así las cuentas
        # deshabilitadas: comprobarlo con una lectura previa dejaría una ventana
        # para que la cuenta se deshabilite entre el chequeo y el descuento.
        filtro.update(filtro_extra)
    if exigir_saldo and monto < 0:
        # `$gte` compara Decimal128 contra Decimal128 sin sorpresas de tipo.
        filtro["balance"] = {"$gte": to_decimal128(-monto)}

    documento = await db[COLECCION].find_one_and_update(
        filtro,
        {"$inc": {"balance": to_decimal128(monto)}},
        return_document=True,          # el documento DESPUES de la escritura
        session=session,
    )

    if documento is None:
        # La escritura no encontró a quién aplicarse. Son dos causas distintas y
        # confundirlas manda al operador a buscar donde no es: o la cuenta no
        # existe, o existe y no tenía saldo.
        actual = await db[COLECCION].find_one({"bank_id": bank_id})
        if actual is None:
            raise CuentaInexistente(bank_id)
        if filtro_extra:
            # La cuenta existe pero no cumple alguna condición del filtro (por
            # ejemplo, está oculta). Tratarlo como falta de saldo mandaría al
            # operador a reponer plata que no arregla nada.
            no_cumple = await db[COLECCION].find_one({"bank_id": bank_id, **filtro_extra})
            if no_cumple is None:
                raise CuentaNoDisponible(bank_id, filtro_extra)
        raise SaldoInsuficiente(bank_id, -monto, saldo_de(actual))

    saldo_nuevo = saldo_de(documento)
    return {
        "saldo_anterior": quantize_money(saldo_nuevo - monto),
        "saldo_nuevo": saldo_nuevo,
        "banco": documento,
    }


async def asegurar_cuenta(db, *, bank_id: str, name: str, currency: str,
                          saldo_inicial=0, **extra) -> dict:
    """Devuelve la cuenta, creándola si no existe, con el saldo en Decimal128.

    Las pasarelas (Mercado Pago, tarjeta) creaban su cuenta al vuelo con
    `"balance": 0.0` —un float— y después le sumaban floats. Naciendo en
    Decimal128 se evita que el tipo dependa de quién la tocó primero.
    """
    cuenta = await db[COLECCION].find_one({"bank_id": bank_id})
    if cuenta is not None:
        return cuenta
    cuenta = {
        "bank_id": bank_id,
        "name": name,
        "currency": (currency or "").upper(),
        "balance": to_decimal128(saldo_inicial),
        **extra,
    }
    await db[COLECCION].insert_one(cuenta)
    return cuenta


async def total_por_moneda(db) -> dict:
    """Cuánto dinero real hay, por moneda, sumando en Decimal.

    Es la mitad «dinero real» de la conciliación del pozo: la otra mitad es la
    suma de los saldos de los usuarios. Se suma en Python y no con `$sum` de
    Mongo a propósito: con el campo migrándose de `float` a `Decimal128`, un
    `$sum` mezcla los dos tipos y el total hereda la imprecisión del float.
    """
    totales = {}
    cursor = db[COLECCION].find(
        {"hidden_from_admin": {"$ne": True}},
        {"_id": 0, "currency": 1, "balance": 1, "bank_id": 1, "name": 1},
    )
    async for cuenta in cursor:
        moneda = (cuenta.get("currency") or "").upper() or "SIN_MONEDA"
        caja = totales.setdefault(moneda, {"total": Decimal("0.00"), "cuentas": 0})
        caja["total"] = quantize_money(caja["total"] + saldo_de(cuenta))
        caja["cuentas"] += 1
    return totales
