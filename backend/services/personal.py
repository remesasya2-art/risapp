"""
El personal de la empresa: quién trabaja acá y qué puede tocar.

LAS TRES REGLAS QUE PEDISTE

    1. Al personal lo da de alta el super administrador, y sólo él.
    2. El personal entra por Recursos Humanos, no promoviendo una cuenta
       cualquiera desde la pantalla de usuarios.
    3. El personal NO puede hacer transacciones a título personal.

POR QUE LA TERCERA NECESITA DOS CANDADOS Y NO UNO

    Se midieron las diez rutas por las que un usuario mueve plata. Sólo UNA
    pasa por `saldos.mover` en el momento del pedido. Las otras nueve o crean
    una transacción pendiente, o arrancan un cobro externo —un PIX, un
    invoice de Lightning, un pago con tarjeta— que liquida DESPUÉS un webhook.

    Un candado sólo en la puerta dejaría pasar todo eso: el empleado pide el
    PIX, la puerta lo frena… pero si no lo frenara, el webhook llega más tarde
    y acredita sin pasar por ninguna puerta. Por eso van dos:

        En la puerta   `Depends(sin_transacciones_personales)` en las rutas de
                       usuario. Es la que da el mensaje claro.
        En la plata    `saldos.mover` se niega a mover el saldo de un
                       empleado, venga de donde venga. Es la que ataja al
                       webhook, que no tiene puerta.

    La segunda es la que de verdad cierra la regla. La primera existe para que
    el empleado entienda por qué no puede, en vez de ver un error raro.

QUE NO SE PUEDE HACER, Y POR QUE

    No se convierte en personal a alguien que tiene saldo. Su plata quedaría
    encerrada: no podría retirarla, porque retirar es una transacción. Se
    rechaza el alta y se avisa que primero tiene que vaciar la cuenta. Atrapar
    la plata de alguien para cumplir una regla interna sería peor que la regla.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# La marca en el documento del usuario. Se guarda en `users` y no en una
# colección aparte para que TODA lectura de usuario la vea sin tener que
# acordarse de hacer un join: el que se olvida del join es justo el que deja
# pasar la transacción.
CAMPO = "es_personal"

ROL_PERSONAL = "admin"       # el rol con el que entra al panel

# Los roles que llegan a una superficie de administración. Es la lista que
# decide quién NO puede operar con contraseña sola.
#
#   agent        59 rutas por `get_crm_user`: ve y toca datos de clientes.
#   admin        el rol del personal dado de alta en RRHH. 37 rutas por
#                `get_admin_user`, más las 20 que además miran permisos.
#   super_admin  todo, incluida el alta de personal.
#
# `agent` está acá aunque no mueva plata: un colaborador que lee los datos
# personales de todos los clientes es exactamente lo que no puede quedar
# detrás de una sola contraseña.
ROLES_CON_PANEL = frozenset({"agent", "admin", "super_admin"})


def exige_dos_pasos(usuario) -> bool:
    """¿Esta cuenta tiene prohibido operar sin verificación en dos pasos?

    Se decide en UN solo lugar, y por dos motivos independientes: el rol
    llega a una pantalla de administración, o Recursos Humanos la marcó como
    personal. Con los dos, degradarle el rol a alguien no le saca la
    obligación mientras siga siendo personal de la empresa.

    Al usuario común NO lo alcanza: para él los dos pasos siguen siendo un
    botón que activa si quiere, en su perfil.
    """
    if not usuario:
        return False
    leer = usuario.get if isinstance(usuario, dict) else \
        (lambda k, d=None: getattr(usuario, k, d))
    return (leer("role", "user") in ROLES_CON_PANEL) or es_personal(usuario)


class TieneSaldo(Exception):
    """No se puede volver personal a alguien con plata en la cuenta."""
    def __init__(self, user_id, saldo):
        self.user_id, self.saldo = user_id, saldo
        super().__init__(
            f"{user_id} tiene {saldo} de saldo. El personal no puede hacer "
            f"transacciones, así que ese saldo quedaría encerrado: que lo "
            f"retire antes de darlo de alta.")


class TransaccionPersonalProhibida(Exception):
    """Un empleado intentó mover plata a título personal."""
    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(
            "Las cuentas del personal no pueden hacer transacciones a título "
            "personal. Usá una cuenta propia, no la del trabajo.")


def es_personal(usuario) -> bool:
    """¿Este documento de usuario es una cuenta de personal?"""
    if not usuario:
        return False
    leer = usuario.get if isinstance(usuario, dict) else \
        (lambda k, d=None: getattr(usuario, k, d))
    return bool(leer(CAMPO, False))


async def es_personal_por_id(db, user_id: str) -> bool:
    """Igual, pero yendo a buscar el documento. Para los caminos que sólo
    tienen el id — un webhook, por ejemplo."""
    if not user_id:
        return False
    try:
        doc = await db.users.find_one({"user_id": user_id}, {CAMPO: 1})
    except Exception as e:                                    # pragma: no cover
        # Si no se puede comprobar, NO se asume que está permitido. Esta
        # función existe para frenar plata; ante la duda, frena.
        logger.error("No se pudo comprobar si %s es personal: %s", user_id, e)
        return True
    return es_personal(doc)


async def saldo_en_cero(db, user_id: str) -> Optional[str]:
    """Devuelve el saldo como texto si NO está en cero, o None si está limpio."""
    from services import saldos
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        return None
    for cuenta in ("balance_ris", "balance_ris_terceros"):
        try:
            valor = saldos.saldo_de(doc, cuenta)
        except Exception:                                     # pragma: no cover
            continue
        if valor != 0:
            return f"{valor} en {cuenta}"
    return None
