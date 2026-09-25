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
        (era routes/adminbrl_bridge.py:191, antes de quitar ese puente)
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

import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from services.money import from_db, quantize_money, to_decimal, to_decimal128

logger = logging.getLogger(__name__)

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


async def asegurar_indices(db) -> None:
    """Los índices que hacen imposible tener dos veces la misma cuenta.

    Se llaman al arrancar. Si alguno no se puede crear porque YA hay
    duplicados, eso no es un problema de índices: es que la cuenta ya se
    duplicó y hay que ir a mirarla. Queda en el log como ERROR, y la app
    arranca igual — no arrancar sería peor.
    """
    puestos = []
    try:
        await db[COLECCION].create_index("bank_id", unique=True, name="ux_bank_id")
        puestos.append("ux_bank_id")
    except Exception as e:
        logger.error("SIN INDICE UNICO en %s.bank_id (%s). Puede haber cuentas "
                     "duplicadas.", COLECCION, e)
    try:
        # Sólo para las cuentas de pasarela, que son las que el código crea
        # solo. Las cuentas cargadas a mano pueden repetir nombre y moneda sin
        # que eso sea un error: dos cuentas en el mismo banco es normal.
        await db[COLECCION].create_index(
            [("name", 1), ("currency", 1)], unique=True, name="ux_pasarela",
            partialFilterExpression={"is_gateway": True})
        puestos.append("ux_pasarela")
    except Exception as e:
        logger.error("SIN INDICE UNICO de pasarela en %s (%s). Dos cobros "
                     "simultáneos pueden crear dos veces la misma cuenta.",
                     COLECCION, e)
    if puestos:
        # Igual que en pagos_una_sola_vez: el éxito se anuncia. No ver un error
        # no puede ser la única señal de que esto corrió.
        logger.info("Índices de %s verificados: %s", COLECCION, ", ".join(puestos))


async def asegurar_cuenta(db, *, bank_id: str, name: str, currency: str,
                          saldo_inicial=0, **extra) -> dict:
    """Devuelve la cuenta con ese `bank_id`, creándola si no existe.

    El saldo nace en Decimal128. Las pasarelas creaban su cuenta al vuelo con
    `"balance": 0.0` —un float— y después le sumaban floats; naciendo en
    Decimal128 el tipo no depende de quién la tocó primero.

    Es un `upsert`, no un `find_one` seguido de un `insert_one`: entre esos dos
    hay una ventana por la que dos pedidos simultáneos entran los dos y crean
    la cuenta dos veces.
    """
    return await db[COLECCION].find_one_and_update(
        {"bank_id": bank_id},
        {"$setOnInsert": {
            "bank_id": bank_id,
            "name": name,
            "currency": (currency or "").upper(),
            "balance": to_decimal128(saldo_inicial),
            **extra,
        }},
        upsert=True,
        return_document=True,
    )


async def asegurar_pasarela(db, *, name: str, currency: str,
                            prefijo_id: str, **extra) -> dict:
    """La cuenta de una pasarela (Mercado Pago, tarjeta), creándola si falta.

    Se busca por nombre y moneda, no por `bank_id`, porque el id se generaba
    al azar en cada creación: buscar por id crearía una cuenta nueva cada vez
    y dejaría el saldo viejo colgado en la anterior.

    Antes esto estaba escrito dos veces, en gestor_pix y en payments_card, las
    dos como `find_one` y después `insert_one`. Son justo los dos caminos que
    corren a la vez cuando entra un pago, así que los dos podían leer que no
    había cuenta y crear una cada uno: dos filas "Mercado Pago" en BRL, con el
    saldo repartido entre las dos y sin forma de distinguirlas en el panel.

    El `upsert` cierra casi toda la ventana; el índice único parcial de
    `asegurar_indices` la cierra del todo.
    """
    return await db[COLECCION].find_one_and_update(
        {"name": name, "currency": (currency or "").upper(), "is_gateway": True},
        {"$setOnInsert": {
            "bank_id": f"{prefijo_id}_{uuid.uuid4().hex[:8]}",
            "balance": to_decimal128(0),
            "created_at": datetime.now(timezone.utc),
            **extra,
        }},
        upsert=True,
        return_document=True,
    )


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


# ── El nombre de un banco, reducido a lo comparable ─────────────────────
#
# Vive acá y no en la recarga porque lo usan dos lados que tienen que
# coincidir: la recarga en bolívares, que busca el banco por su nombre, y la
# pantalla de bancos, que no deja cargar dos que se confundirían en esa
# búsqueda. Si cada uno tuviera su copia, se podrían separar.

_ACENTOS = str.maketrans("áéíóúÁÉÍÓÚàâãêôõçÀÂÃÊÔÕÇ", "aeiouAEIOUaaaeoocAAAEOOC")


def clave_del_nombre(texto) -> str:
    """Un nombre de banco reducido a lo comparable: sin acentos, sin puntuacion.

    'Banco de Venezuela', 'banco_venezuela' y 'BANCO DE VENEZUELA' tienen que
    ser la misma cosa. Sin esto, la traduccion depende de como lo tipeo quien
    cargo el banco en contabilidad, que es una fuente distinta de quien escribio
    la lista del frontend.
    """
    limpio = str(texto or "").translate(_ACENTOS).lower()
    palabras = [p for p in "".join(c if c.isalnum() else " " for c in limpio).split()
                # 'de' y 'del' sobran: "Banco de Venezuela" y "banco_venezuela"
                # tienen que colapsar al mismo valor.
                if p not in ("de", "del", "la", "el", "banco")]
    return " ".join(palabras)


# ── Los datos para que el cliente transfiera ────────────────────────────
#
# A QUE CUENTA TRANSFIERE EL CLIENTE, Y POR QUE ESTO VIVE EN LA BASE
#
#   La pantalla de recarga en bolívares tenía escritos en el código el
#   titular, su cédula, su teléfono y los números de cuenta. Ese código se le
#   sirve a cualquier visitante, tenga sesión o no; y cambiar de cuenta exigía
#   editar el código. Ahora cada banco de contabilidad guarda sus datos de
#   cobro en `cobro`, se cargan desde el panel, y el cliente los ve sólo con
#   sesión y sólo de los bancos publicados.
#
# LO QUE SE REVISA, Y POR QUE
#
#   Un dígito mal cargado manda la plata de un cliente a otra cuenta. Por eso
#   no se guarda texto libre: el número de cuenta son 20 dígitos y empieza por
#   el código del banco (así funcionan las cuentas en Venezuela, y es la forma
#   de atrapar que se pegó la cuenta de otro banco); la cédula o el RIF lleva
#   su letra.


class DatosDeCobroInvalidos(ValueError):
    """Lo que no se puede guardar, dicho para quien lo escribió."""


def _solo_digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def normalizar_cobro(datos: dict) -> dict:
    """Los datos de cobro limpios, o `DatosDeCobroInvalidos` con el motivo.

    Acepta lo que se escribe a mano —espacios, guiones, puntos— y guarda
    una sola forma, que es la que el cliente copia."""
    codigo = _solo_digitos(datos.get("codigo"))
    if len(codigo) != 4:
        raise DatosDeCobroInvalidos("El código del banco son 4 dígitos: 0102, 0134…")

    titular = " ".join(str(datos.get("titular") or "").split())
    if not 3 <= len(titular) <= 80:
        raise DatosDeCobroInvalidos("Escribí el titular de la cuenta, como figura en el banco.")

    documento = str(datos.get("documento") or "").strip().upper().replace(" ", "").replace(".", "")
    m = re.fullmatch(r"([VEJGP])-?(\d{5,10})(?:-?(\d))?", documento)
    if not m:
        raise DatosDeCobroInvalidos("La cédula o el RIF lleva su letra y los números: V-12345678 o J-123456789.")
    documento = f"{m.group(1)}-{m.group(2)}" + (f"-{m.group(3)}" if m.group(3) else "")

    # SOLO TRANSFERENCIA. Pago Móvil y el tipo de cuenta se sacaron por
    # decisión del dueño del proyecto: el cliente ve tres datos —nombre,
    # cédula y cuenta— y los copia de una. Si llegan, se ignoran.
    cuenta = _solo_digitos(datos.get("numero_cuenta"))
    if not cuenta:
        raise DatosDeCobroInvalidos("Escribí el número de cuenta: es a donde transfiere el cliente.")
    if len(cuenta) != 20:
        raise DatosDeCobroInvalidos(f"El número de cuenta son 20 dígitos; tiene {len(cuenta)}.")
    if not cuenta.startswith(codigo):
        raise DatosDeCobroInvalidos(
            f"El número de cuenta empieza por el código del banco ({codigo}) y éste empieza por "
            f"{cuenta[:4]}. ¿Es la cuenta de otro banco?")

    return {"codigo": codigo, "titular": titular, "documento": documento, "numero_cuenta": cuenta}


def para_el_cliente(banco: dict):
    """Lo que ve el cliente de un banco publicado, o None si no se muestra.

    Lista de lo permitido, armada acá: ni el saldo, ni quién lo cargó, ni
    nada que se le agregue mañana al banco llega a la pantalla del cliente."""
    cobro = banco.get("cobro") or {}
    if banco.get("currency") != "VES" or banco.get("is_gateway") or not cobro.get("publicado"):
        return None
    try:
        # Se vuelve a revisar al servir: un documento tocado a mano en la base
        # no llega al cliente si no pasa las mismas reglas que el panel.
        limpio = normalizar_cobro(cobro)
    except DatosDeCobroInvalidos:
        return None
    return {
        "bank_id": banco.get("bank_id"),
        "name": banco.get("name"),
        "titular": limpio["titular"],
        "documento": limpio["documento"],
        "numero_cuenta": limpio["numero_cuenta"],
    }
