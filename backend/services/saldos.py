"""
services/saldos.py — El saldo de los usuarios, en un solo lugar.

POR QUE EXISTE ESTE MODULO

    `users.balance_ris` y `users.balance_ris_terceros` se mueven desde VEINTE
    lugares. La plata llega bien a todos —el `$inc` es atómico— pero alrededor
    del `$inc` hay dos defectos que se repiten copiados, y los dos importan para
    la cuenta ómnibus.

DEFECTO 1: EL SALDO ANTERIOR SE CALCULA SOBRE UN VALOR CRUDO DE LA BASE

    El patrón, repetido en cinco sitios:

        usuario = await db.users.find_one_and_update(..., return_document=True)
        saldo_despues = usuario.get("balance_ris")       # crudo
        saldo_antes = saldo_despues - monto              # ← acá

    `balance_ris` se escribe con `to_decimal128(...)` desde `transactions.py`,
    `gestor.py`, `admin.py` y `envios_cobros.py`, y con floats crudos desde
    otros. Si el valor viene como `Decimal128`, esa resta es:

        >>> Decimal128(Decimal("1000.00")) - 500.0
        TypeError: unsupported operand type(s) for -: 'Decimal128' and 'float'

    Cuatro de esos cinco sitios están dentro de un `try` que sólo loguea: la
    plata se acredita y **la línea del libro no se escribe**, en silencio. El
    quinto —`gestor_pix.py`, la confirmación de un PIX— está FUERA de todo
    `try`: el `$inc` ya ocurrió, así que el usuario queda acreditado y la
    función revienta después, sin línea de libro y sin avisarle a nadie.

    No pude comprobar acá cómo promueve tipos el `$inc` de Mongo cuando el campo
    es `Decimal128` y el operando un `float` (no hay un Mongo real en este
    entorno, y la documentación no lo dice). Por eso este módulo **no depende de
    la respuesta**: lee siempre con `from_db`, que acepta `float`, `Decimal128`,
    `str` y `None`, y hace la aritmética en `Decimal`. Sea cual sea la regla, el
    resultado es el mismo.

DEFECTO 2: MOVIMIENTOS QUE NO DEJAN LINEA EN EL LIBRO

    Cuatro caminos mueven saldo sin asentar nada:

        routes/gestor_pix.py   webhook de tarjeta       acredita balance_ris
        routes/gestor.py       envío de un gestor       debita  balance_ris_terceros
        admin_routes.py        aprobación de recarga    acredita balance_ris
        admin_routes.py        ajuste manual de saldo   ajusta  balance_ris

    Para la conciliación del pozo eso es lo peor que puede pasar: la suma del
    libro deja de coincidir con el saldo, y no hay forma de saber si la
    diferencia es un error de la app o plata que de verdad se movió.

QUE HACE ESTE MODULO

    Una sola operación —`mover`— que mueve el saldo y asienta la línea, con el
    saldo posterior tomado del RESULTADO de la escritura y no de una lectura
    anterior. Con dos operaciones simultáneas sobre el mismo usuario, dos
    lecturas previas dan el mismo número y las dos líneas del libro mienten;
    `return_document=True` devuelve el único valor que de verdad quedó.

    El libro nunca rompe el flujo del dinero: si el asiento falla, la plata ya
    se movió y deshacerla sería peor. Pero **no falla en silencio**: se loguea a
    nivel ERROR con todo lo necesario para reponer la línea a mano.
"""

import logging
from decimal import Decimal

from services import kyc_quota
from services.ledger import record_ris_entry
from services.money import from_db, quantize_money, to_decimal, to_decimal128, to_float

logger = logging.getLogger(__name__)

COLECCION = "users"

# Las dos cuentas de saldo RIS. El resto de los `balance_*` del usuario son
# otros libros (cripto) y no se tocan desde acá.
CUENTAS = frozenset({"balance_ris", "balance_ris_terceros"})


class CuentaDesconocida(ValueError):
    """Se pidió mover una cuenta que este módulo no administra."""

    def __init__(self, cuenta):
        self.cuenta = cuenta
        super().__init__(
            f"«{cuenta}» no es una cuenta de saldo RIS. Las que este módulo "
            f"mueve son: {', '.join(sorted(CUENTAS))}")


class UsuarioInexistente(Exception):
    """No hay ningún usuario con ese `user_id`."""

    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(f"No existe el usuario {user_id}")


class SaldoInsuficiente(Exception):
    """El débito no se hizo porque el usuario no tenía con qué."""

    def __init__(self, user_id, cuenta, pedido, disponible=None):
        self.user_id = user_id
        self.cuenta = cuenta
        self.pedido = pedido
        self.disponible = disponible
        super().__init__(
            f"El usuario {user_id} no tiene saldo suficiente en {cuenta}: "
            f"se pedían {pedido}"
            + (f" y hay {disponible}" if disponible is not None else ""))


def saldo_de(usuario, cuenta: str = "balance_ris") -> Decimal:
    """El saldo de un usuario, como Decimal, venga como venga de la base.

    Funciona igual sobre un usuario viejo cuyo saldo nunca salió de `float` y
    sobre uno que ya pasó por una escritura en `Decimal128`.
    """
    if usuario is None:
        return Decimal("0.00")
    return from_db(usuario.get(cuenta))


async def mover(db, user_id: str, monto, *, movimiento: str,
                cuenta: str = "balance_ris", exigir_saldo: bool = False,
                consumir_cupo: bool = False, session=None, **libro) -> dict:
    """Mueve el saldo de un usuario y asienta la línea del libro.

    `monto` es con signo: positivo acredita, negativo debita. Se acepta como
    `float`, `str`, `Decimal` o `Decimal128` y se normaliza acá, para que quien
    llama no tenga que acordarse.

    `movimiento` es el `movement_type` del libro, y tiene que estar en el mapa
    `ASIENTOS` de `services/contabilidad.py`: si no, la línea aparece igual pero
    contra la cuenta puente, y el chequeo de integridad la denuncia.

    Con `exigir_saldo=True` el débito sólo ocurre si el usuario tiene con qué, y
    la comprobación va DENTRO del filtro de la escritura: entre mirar y descontar
    no hay ventana para que otra operación se lleve la plata. Si no alcanza,
    levanta `SaldoInsuficiente` y no escribe nada.

    `consumir_cupo=True` mete el contador de cupo sin KYC en la MISMA escritura
    que el saldo, que es la única forma de que no se separen.

    Todo lo demás (`reference_kind`, `reference_id`, `transaction_id`,
    `actor_type`, `actor_id`, `rate`, `amount_output`, `metadata`, `notes`…)
    viaja tal cual a `record_ris_entry`.

    Devuelve `{"saldo_anterior", "saldo_nuevo", "usuario", "entry_id"}`, con los
    saldos en `Decimal` y `entry_id` en `None` si el asiento no se pudo escribir
    (que se loguea a nivel ERROR, pero no interrumpe: la plata ya se movió).
    """
    if cuenta not in CUENTAS:
        raise CuentaDesconocida(cuenta)

    monto = quantize_money(to_decimal(monto))

    if monto == 0:
        # Mover cero no es un error del que valga la pena morirse, pero tampoco
        # merece una línea de libro: sería ruido en el mayor. Se avisa y se
        # devuelve el estado actual sin escribir nada.
        logger.warning(
            f"saldos.mover: movimiento de 0 sobre {user_id}/{cuenta} "
            f"({movimiento}); no se escribe nada")
        actual = await db[COLECCION].find_one({"user_id": user_id}, session=session)
        if actual is None:
            raise UsuarioInexistente(user_id)
        saldo = saldo_de(actual, cuenta)
        return {"saldo_anterior": saldo, "saldo_nuevo": saldo,
                "usuario": actual, "entry_id": None}

    filtro = {"user_id": user_id}
    if exigir_saldo and monto < 0:
        # `$gte` compara Decimal128 contra Decimal128 sin sorpresas de tipo.
        filtro[cuenta] = {"$gte": to_decimal128(-monto)}

    incremento = {cuenta: to_decimal128(monto)}
    if consumir_cupo:
        incremento.update(kyc_quota.consume_inc(to_float(monto)))

    documento = await db[COLECCION].find_one_and_update(
        filtro,
        {"$inc": incremento},
        return_document=True,          # el documento DESPUES de la escritura
        session=session,
    )

    if documento is None:
        # La escritura no encontró a quién aplicarse. Son dos causas distintas y
        # confundirlas manda a buscar donde no es: o el usuario no existe, o
        # existe y no tenía saldo.
        actual = await db[COLECCION].find_one({"user_id": user_id}, session=session)
        if actual is None:
            raise UsuarioInexistente(user_id)
        raise SaldoInsuficiente(user_id, cuenta, -monto, saldo_de(actual, cuenta))

    saldo_nuevo = saldo_de(documento, cuenta)
    saldo_anterior = quantize_money(saldo_nuevo - monto)

    entry_id = await record_ris_entry(
        user_id=user_id,
        movement_type=movimiento,
        amount=to_float(abs(monto)),
        direction=("credit" if monto > 0 else "debit"),
        account=cuenta,
        balance_before=to_float(saldo_anterior),
        balance_after=to_float(saldo_nuevo),
        **libro,
    )

    if entry_id is None:
        # `record_ris_entry` se traga sus errores por contrato: no puede tumbar
        # un flujo de plata que ya ocurrió. Pero una línea que falta y nadie
        # nombra es exactamente el agujero que este módulo vino a tapar, así que
        # queda gritado en el log con todo lo necesario para reponerla a mano.
        logger.error(
            "LIBRO SIN LINEA: el saldo se movió y el asiento NO se escribió — "
            f"user_id={user_id} cuenta={cuenta} movimiento={movimiento} "
            f"monto={monto} saldo_anterior={saldo_anterior} "
            f"saldo_nuevo={saldo_nuevo} contexto={libro}")

    return {"saldo_anterior": saldo_anterior, "saldo_nuevo": saldo_nuevo,
            "usuario": documento, "entry_id": entry_id}


async def transferir(db, user_id: str, monto, *, de: str, a: str,
                     movimiento: str = "traspaso_interno", session=None,
                     **libro) -> dict:
    """Pasa saldo de una cuenta del usuario a otra, en UNA sola escritura.

    Es el traspaso del gestor entre su saldo personal y el de terceros. Se hace
    con un único `$inc` que toca los dos campos a la vez —y no con dos `mover`
    encadenados— porque partirlo en dos abre la ventana en la que la plata salió
    de una cuenta y todavía no llegó a la otra.

    La comprobación de saldo va DENTRO del filtro. Antes se leía el saldo, se
    comparaba en Python y después se escribía: dos traspasos simultáneos pasaban
    los dos la comprobación y el saldo personal quedaba en negativo.

    Deja DOS líneas en el libro —el débito de una cuenta y el crédito de la
    otra— porque eso es un traspaso: las dos patas se anulan contra la cuenta de
    traspasos internos y el balance no se mueve.
    """
    for cuenta in (de, a):
        if cuenta not in CUENTAS:
            raise CuentaDesconocida(cuenta)
    if de == a:
        raise ValueError(f"El origen y el destino del traspaso son la misma cuenta: {de}")

    monto = quantize_money(to_decimal(monto))
    if monto <= 0:
        raise ValueError(f"Un traspaso tiene que ser positivo, no {monto}")

    documento = await db[COLECCION].find_one_and_update(
        {"user_id": user_id, de: {"$gte": to_decimal128(monto)}},
        {"$inc": {de: to_decimal128(-monto), a: to_decimal128(monto)}},
        return_document=True,
        session=session,
    )

    if documento is None:
        actual = await db[COLECCION].find_one({"user_id": user_id}, session=session)
        if actual is None:
            raise UsuarioInexistente(user_id)
        raise SaldoInsuficiente(user_id, de, monto, saldo_de(actual, de))

    saldo_origen = saldo_de(documento, de)
    saldo_destino = saldo_de(documento, a)

    entradas = []
    for cuenta, direccion, despues in (
            (de, "debit", saldo_origen), (a, "credit", saldo_destino)):
        antes = quantize_money(despues + monto if direccion == "debit"
                               else despues - monto)
        entradas.append(await record_ris_entry(
            user_id=user_id,
            movement_type=movimiento,
            amount=to_float(monto),
            direction=direccion,
            account=cuenta,
            balance_before=to_float(antes),
            balance_after=to_float(despues),
            **libro,
        ))

    if any(e is None for e in entradas):
        logger.error(
            "LIBRO SIN LINEA: el traspaso se hizo y falta al menos una de sus "
            f"dos patas — user_id={user_id} de={de} a={a} monto={monto} "
            f"movimiento={movimiento} entradas={entradas} contexto={libro}")

    return {"saldo_origen": saldo_origen, "saldo_destino": saldo_destino,
            "usuario": documento, "entry_ids": entradas}
