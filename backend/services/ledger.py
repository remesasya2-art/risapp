"""
Libro mayor (ledger) de saldo RIS — append-only.

Sub-fase A1: modo "solo registra". Este módulo escribe líneas inmutables cada
vez que el saldo RIS de un usuario cambia. NO modifica saldos y NO rompe el
flujo: cualquier error al registrar se captura y se loguea, nunca se propaga.

El saldo se sigue calculando como hoy (campo balance_ris en el usuario); el
ledger es la historia auditable paralela y, en una fase posterior, la base de
la reconciliación.

Cada línea guarda el máximo contexto del negocio: quién, qué, cuánto, saldo
antes/después, a qué operación pertenece, qué tasa se usó, el beneficiario,
quién lo procesó y metadatos libres.

El BTC NO va en este libro: es una orden directa que no toca el saldo RIS y
tendrá su propio libro (ledger_btc) en un paso aparte.
"""

import logging
import uuid
from datetime import datetime, timezone

from decimal import Decimal

from database import db
from services.money import ZERO, from_db, quantize_money, to_decimal, to_decimal128, to_float

logger = logging.getLogger(__name__)

LEDGER_COLLECTION = "ledger"

_indexes_ready = False


async def _ensure_indexes():
    """Crea índices del ledger una sola vez (idempotente)."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db[LEDGER_COLLECTION].create_index([("user_id", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index("entry_id", unique=True)
        await db[LEDGER_COLLECTION].create_index([("movement_type", 1), ("created_at", -1)])
        await db[LEDGER_COLLECTION].create_index([("reference.kind", 1), ("reference.id", 1)])
        _indexes_ready = True
    except Exception as e:
        logger.warning(f"No se pudieron crear índices del ledger: {e}")


async def record_ris_entry(
    *,
    user_id: str,
    movement_type: str,            # recarga_pix, envio_ves, envio_reais, refund_envio_ves, refund_envio_reais, bono_referido, pago_tarjeta, ajuste_admin...
    amount,                        # SIEMPRE positivo; 'direction' define el signo. Decimal, texto o float: se normaliza
    direction: str,                # "credit" (entra saldo) | "debit" (sale saldo)
    account: str = "balance_ris",  # balance_ris | balance_ris_terceros
    balance_before=None,
    balance_after=None,
    decimales: int = 2,            # 2 para RIS; el libro cripto pasa 8
    reference_kind: str = None,    # transaction | pix_payment | btc_remesa | referral | card_payment | manual
    reference_id: str = None,
    transaction_id: str = None,
    display_id=None,
    actor_type: str = "system",    # user | admin | system | webhook
    actor_id: str = None,
    actor_email: str = None,
    rate=None,
    rate_kind: str = None,         # ris_to_ves | brl_to_ris | ves_to_ris ...
    amount_output=None,            # p.ej. VES o BRL resultantes de la operación
    currency_output: str = None,   # VES | BRL ...
    counterparty: dict = None,     # snapshot del beneficiario u origen
    user_snapshot: dict = None,    # email/name/role del usuario (si ya se tiene a mano)
    metadata: dict = None,         # contexto libre adicional
    notes: str = None,
):
    """Escribe una línea inmutable en el libro de RIS. Nunca lanza excepción.

    Devuelve el entry_id si se registró, o None si hubo algún problema (sin
    afectar el flujo que la invocó).
    """
    try:
        await _ensure_indexes()

        # Snapshot del usuario si no se proporcionó
        if user_snapshot is None:
            u = await db.users.find_one(
                {"user_id": user_id},
                {"email": 1, "name": 1, "full_name": 1, "role": 1},
            ) or {}
            user_snapshot = {
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
            }

        # EL DINERO SE GUARDA EN Decimal128, NO EN float.
        #
        #   Acá decía `abs(float(amount or 0))`. Cada línea del libro quedaba en
        #   coma flotante mientras el resto de la aplicación cuida los saldos en
        #   `Decimal128`, y los lectores tuvieron que aprender a sumar en Decimal
        #   «por si acaso» (`sum_ris_balance`, `contabilidad._monto`). Un libro
        #   contable que guarda 0.1 + 0.2 como 0.30000000000000004 no es un libro:
        #   es una aproximación. Se normaliza con `to_decimal` (un float entra
        #   por `str`, sin arrastrar su ruido) y se guarda ya redondeado a los
        #   decimales de la cuenta.
        #
        #   Lo que ya está escrito en float queda como está: `from_db` y
        #   `to_decimal` leen las dos formas, y así tiene que seguir.
        amount_abs = quantize_money(abs(to_decimal(amount)), decimales)
        signed = amount_abs if direction == "credit" else -amount_abs

        entry = {
            "entry_id": f"le_{uuid.uuid4().hex[:16]}",
            "created_at": datetime.now(timezone.utc),
            "book": "RIS",
            # Titular del movimiento
            "user_id": user_id,
            "user_email": user_snapshot.get("email"),
            "user_name": user_snapshot.get("name"),
            "user_role": user_snapshot.get("role"),
            # Naturaleza del movimiento
            "movement_type": movement_type,
            "direction": direction,
            "amount": to_decimal128(amount_abs, decimales),
            "signed_amount": to_decimal128(signed, decimales),
            "currency": "RIS",
            "account": account,
            # Saldo antes/después (si el llamador lo provee)
            "balance_before": None if balance_before is None else to_decimal128(balance_before, decimales),
            "balance_after": None if balance_after is None else to_decimal128(balance_after, decimales),
            # Enlace al origen
            "reference": ({"kind": reference_kind, "id": reference_id} if reference_kind else None),
            "transaction_id": transaction_id,
            "display_id": display_id,
            # Quién lo ejecutó
            "actor": {"type": actor_type, "id": actor_id, "email": actor_email},
            # Económico de la operación
            "rate": rate,
            "rate_kind": rate_kind,
            "amount_output": amount_output,
            "currency_output": currency_output,
            # Contexto
            "counterparty": counterparty,
            "metadata": metadata or {},
            "notes": notes,
        }

        await db[LEDGER_COLLECTION].insert_one(entry)
        return entry["entry_id"]
    except Exception as e:
        # No se relanza: el saldo YA se movió y tumbar el flujo no lo repone.
        # Pero tampoco se calla: fila en Errores y campana a los super
        # administradores, con lo necesario para reponer la línea a mano.
        # Ver services/gritos.py.
        from services import gritos
        await gritos.libro_sin_linea(db, libro="RIS", user_id=user_id, movement_type=movement_type,
                                     amount=amount, account=account, error=e)
        return None


async def sum_ris_balance(user_id: str, account: str = "balance_ris",
                          decimales: int = 2) -> Decimal:
    """Suma todas las líneas del libro de un usuario/cuenta, en Decimal.

    Se suma en Python y NO con el `$sum` de Mongo a propósito: `signed_amount`
    se guarda como float, y sumar mil líneas con `$sum` arrastra el error
    binario a un total que después se compara contra un saldo exacto. Un
    "descuadre" de 0.00000001 que sólo existe porque el total se sumó en coma
    flotante manda a revisar una cuenta que está bien.

    Devuelve `Decimal`. Antes devolvía `float`; quien necesite un número suelto
    lo convierte al mostrarlo, que es donde el redondeo no hace daño.

    `decimales` existe por el libro cripto: USDT y USDC llevan ocho, y cerrarlos
    a dos dejaría un residuo del que después nadie sabe el origen.
    """
    try:
        total = ZERO
        cursor = db[LEDGER_COLLECTION].find(
            {"user_id": user_id, "account": account},
            {"_id": 0, "signed_amount": 1},
        )
        async for linea in cursor:
            total += to_decimal(linea.get("signed_amount"))
        return quantize_money(total, decimales)
    except Exception as e:
        logger.warning(f"sum_ris_balance fallo: {e}")
        return ZERO


async def create_opening_entries():
    """Crea, UNA sola vez por usuario y cuenta, una línea 'saldo_apertura' que
    iguala la suma del ledger al saldo actual del usuario.

    Esto resuelve la migración: como el ledger empezó a registrar después de que
    los usuarios ya tenían saldo, la apertura representa ese saldo inicial. Tras
    ejecutarla, sum(ledger) == balance del usuario y la reconciliación cuadra.

    Es idempotente: si un usuario ya tiene apertura en esa cuenta, no la repite.
    El valor de apertura = saldo_actual - suma_ledger_existente, de modo que
    también respeta los movimientos ya registrados desde que el libro arrancó.
    """
    creados = 0
    revisados = 0
    try:
        await _ensure_indexes()
        async for u in db.users.find(
            {},
            {"user_id": 1, "balance_ris": 1, "balance_ris_terceros": 1,
             "email": 1, "name": 1, "full_name": 1, "role": 1},
        ):
            uid = u.get("user_id")
            if not uid:
                continue
            revisados += 1
            snapshot = {
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
            }
            for account, field in (("balance_ris", "balance_ris"),
                                   ("balance_ris_terceros", "balance_ris_terceros")):
                # ¿ya tiene apertura en esta cuenta? (idempotencia)
                existing = await db[LEDGER_COLLECTION].find_one(
                    {"user_id": uid, "movement_type": "saldo_apertura", "account": account}
                )
                if existing:
                    continue
                # `float(u.get(field) or 0)` reventaba: el saldo se guarda en
                # `Decimal128` y `float(Decimal128)` es un TypeError. El `or 0`
                # no salvaba nada, porque un Decimal128 es truthy.
                current = from_db(u.get(field))
                led = await sum_ris_balance(uid, account)
                opening = quantize_money(current - led)
                if opening == ZERO:
                    continue  # nada que abrir
                await record_ris_entry(
                    user_id=uid,
                    movement_type="saldo_apertura",
                    amount=abs(opening),
                    direction="credit" if opening > 0 else "debit",
                    account=account,
                    balance_before=led,
                    balance_after=current,
                    reference_kind="manual",
                    reference_id="opening_migration",
                    actor_type="system",
                    actor_id="ledger_opening",
                    user_snapshot=snapshot,
                    notes="Saldo de apertura (migración al libro mayor)",
                )
                creados += 1
        return {"revisados": revisados, "aperturas_creadas": creados}
    except Exception as e:
        logger.error(f"create_opening_entries fallo: {e}")
        return {"revisados": revisados, "aperturas_creadas": creados, "error": str(e)}


# ─── El cierre del libro ──────────────────────────────────────────────────
#
# Las cuentas que este cierre alcanza, con los decimales de cada una. Las de
# cripto llevan ocho: cerrarlas a dos dejaría un resto invisible.
CUENTAS_A_CERRAR = (
    ("balance_ris", 2, "RIS"),
    ("balance_ris_terceros", 2, "RIS"),
    ("balance_usdt", 8, "USDT"),
    ("balance_usdc", 8, "USDC"),
)


async def create_closing_entries(*, actor_id: str, actor_email: str = None,
                                 motivo: str = "wipe_all") -> dict:
    """Lleva el libro de cada usuario a CERO sin borrar una sola línea.

    POR QUE ESTO Y NO BORRAR EL LIBRO

        El borrado de datos pone los saldos en cero y no toca el libro. A partir
        de ahí la reconciliación marca descuadre en TODOS los usuarios a la vez,
        y el informe deja de servir para encontrar el descuadre que sí importa.

        La salida obvia sería agregar `ledger` a la lista de colecciones que se
        borran. Sería un error: un libro contable es append-only justamente para
        que no se pueda borrar, y el día que un auditor —o el propio proveedor de
        pagos— pida la historia, «la borramos» no es una respuesta.

        Así que el borrado CIERRA el libro en vez de tirarlo: por cada cuenta con
        saldo se escribe una línea que lo lleva a cero. Después del cierre,
        suma(libro) == 0 == saldo, la reconciliación cuadra, y cada peso que
        alguna vez se movió sigue teniendo su renglón.

        Es la operación simétrica de `create_opening_entries`, y las dos van
        contra la misma cuenta de patrimonio, así que se anulan entre sí.

    El cierre se calcula sobre la SUMA DEL LIBRO, no sobre el saldo guardado: lo
    que hay que llevar a cero es el libro. Si el saldo y el libro no coincidían
    —que es justo lo que la reconciliación denuncia— la diferencia queda visible
    en la línea de cierre, con el `balance_before` real.
    """
    from services.ledger_crypto import record_crypto_entry

    creados = 0
    revisados = 0
    por_cuenta = {}
    try:
        await _ensure_indexes()
        async for u in db.users.find(
            {},
            {"user_id": 1, "email": 1, "name": 1, "full_name": 1, "role": 1},
        ):
            uid = u.get("user_id")
            if not uid:
                continue
            revisados += 1
            snapshot = {
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
            }
            for account, decimales, libro in CUENTAS_A_CERRAR:
                saldo_libro = await sum_ris_balance(uid, account, decimales)
                if saldo_libro == ZERO:
                    continue

                # El saldo baja a cero: si el libro estaba en positivo, la línea
                # es un débito; si estaba en negativo, un crédito.
                direccion = "debit" if saldo_libro > ZERO else "credit"
                # El monto va en Decimal, con los decimales de la cuenta: un
                # cierre cripto de 12.3456789 redondeado a dos dejaría el libro
                # en -0.0043211, un resto del que nadie sabría el origen.
                comun = dict(
                    user_id=uid,
                    movement_type="cierre_de_libro",
                    amount=abs(saldo_libro),
                    direction=direccion,
                    balance_before=saldo_libro,
                    balance_after=ZERO,
                    decimales=decimales,
                    reference_kind="manual",
                    reference_id=f"cierre_{motivo}",
                    actor_type="admin",
                    actor_id=actor_id,
                    actor_email=actor_email,
                    user_snapshot=snapshot,
                    metadata={"motivo": motivo},
                    notes="Cierre del libro por borrado de datos",
                )
                if libro == "RIS":
                    await record_ris_entry(account=account, **comun)
                else:
                    await record_crypto_entry(currency=libro.lower(), **comun)

                creados += 1
                por_cuenta[account] = por_cuenta.get(account, 0) + 1

        return {"revisados": revisados, "cierres_creados": creados,
                "por_cuenta": por_cuenta}
    except Exception as e:
        logger.error(f"create_closing_entries fallo: {e}")
        return {"revisados": revisados, "cierres_creados": creados,
                "por_cuenta": por_cuenta, "error": str(e)}
