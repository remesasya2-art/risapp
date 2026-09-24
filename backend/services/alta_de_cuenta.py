"""
services/alta_de_cuenta.py — El único lugar por el que nace una cuenta.

POR QUE UN SOLO LUGAR

    Una cuenta nacía en `/auth/verify-email`, con sus campos escritos ahí
    mismo: los saldos en cero y en Decimal128, el bono en su propia cuenta,
    el CPF anclado ANTES del insert, el índice único de la base atrapado y
    explicado, el bono de bienvenida liberado después. Cada uno de esos
    detalles fue un defecto en su momento (un saldo que nacía en float, un
    500 en vez de «ese CPF ya es de otro», un bono que quedaba bloqueado).

    Con el ingreso con Google aparece una segunda forma de nacer. Copiar
    esos treinta renglones es la manera segura de que la segunda copia se
    quede atrás en el próximo arreglo, y que una cuenta nacida por Google
    tenga un defecto que la nacida por correo ya no tiene. Así que las dos
    puertas llaman acá, y acá se decide con qué campos nace una cuenta.

LO QUE ESTO NO HACE

    No manda correos, no crea la sesión, no toca lo que quedaba pendiente
    de la puerta que llamó. Eso es de cada puerta. Acá: anclar el CPF,
    insertar, liberar el bono.
"""
import logging
import uuid
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from services import cpf_de_la_cuenta
from services.money import to_decimal128

logger = logging.getLogger(__name__)

# La versión de los términos que acepta quien se registra hoy. Vivía
# escrita adentro de verify-email; es la misma para las dos puertas.
VERSION_DE_LOS_TERMINOS = "2026-06-29"


def nuevo_codigo_de_referido() -> str:
    """El código de invitación con el que nace una cuenta.

    Vive acá y no escrito en cada lugar que lo necesita porque ahora son dos:
    el alta, y la cuenta vieja que no lo tiene y lo recibe al abrir su perfil
    (`routes/referidos.py`). Dos fórmulas escritas a mano terminan siendo dos
    formatos de código.
    """
    return f"REF{uuid.uuid4().hex[:8].upper()}"


class NoSePudoCrear(Exception):
    """Con el motivo para la persona adentro, en castellano."""


async def crear(db, *, email: str, name: str, password_hash, referred_by,
                cpf_number, google_sub: str = None, ahora=None) -> dict:
    """Crea la cuenta y devuelve su documento. Levanta `NoSePudoCrear`.

    `password_hash=None` es una cuenta sin contraseña (nació con Google):
    `password_set` queda en False y la puerta de la contraseña la rechaza
    con «No tienes contraseña configurada», que ya existía para este caso.
    """
    ahora = ahora or datetime.now(timezone.utc)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    referral_code = nuevo_codigo_de_referido()

    user = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "password_hash": password_hash,
        "password_set": password_hash is not None,
        "email_verified": True,
        # En Decimal128, como el resto de la app. Naciendo en float, el
        # tipo del saldo dependía de quién creó al usuario.
        "balance_ris": to_decimal128(0),
        "balance_ves": to_decimal128(0),
        # El bono de bienvenida vive en su propia cuenta y nace en cero, con
        # el tipo correcto. Naciendo ausente, el primer `$inc` lo crearía con
        # el tipo que trajera ese `$inc`.
        "balance_ris_bono": to_decimal128(0),
        "role": "user",
        "verification_status": "unverified",
        # Vacío se guarda como None y no como "", para que el documento diga
        # «sin código» de una sola forma.
        "referred_by": referred_by or None,
        # El CPF que declaró al registrarse. Es el único con el que esta
        # cuenta puede pagar, y el que le va a llegar puesto en la
        # verificación.
        "cpf_number": cpf_number,
        "cpf_declarado_en": ahora,
        "referral_code": referral_code,
        "created_at": ahora,
        "terms_accepted": True,
        "terms_accepted_at": ahora,
        "terms_version": VERSION_DE_LOS_TERMINOS,
    }
    if google_sub:
        # El identificador estable de la cuenta de Google. No sale por
        # ninguna puerta: no está en la lista de lo que ve su dueño.
        user["google_sub"] = google_sub
        user["registrada_via"] = "google"

    # ─── El CPF queda anclado a esta cuenta ──────────────────────────────
    #
    # Va ANTES del insert y no después: si el CPF resultara ser de otro, esto
    # levanta y la cuenta no llega a crearse. Al revés quedaría una cuenta
    # creada con un CPF que es de otra persona, que es exactamente lo que se
    # está tratando de que no pase.
    if cpf_number:
        try:
            await cpf_de_la_cuenta.anclar(db, cpf_number, user_id, correo=email)
        except (cpf_de_la_cuenta.CpfInvalido, cpf_de_la_cuenta.CpfEnUso) as e:
            raise NoSePudoCrear(str(e))

    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        # El índice único de `users.cpf_number`, cuando exista, puede rechazar
        # este insert. Sin este `except` el cliente recibía un 500 —«error del
        # servidor»— en vez del motivo, y encima con la reserva ya anclada.
        logger.warning("registro rechazado por la base: el CPF ya es de otra cuenta")
        await cpf_de_la_cuenta.soltar_el_ancla(db, cpf_number, user_id)
        raise NoSePudoCrear(
            "Ese CPF ya tiene una cuenta en RISApp. Iniciá sesión con "
            "ella, o recuperá tu contraseña si no la recordás.")

    # El bono de bienvenida, si se registró con el código de alguien. Va
    # DESPUES del insert porque necesita que la cuenta exista, y en su propio
    # try adentro del servicio: que el bono falle no puede dejar a medias un
    # registro que ya creó la cuenta.
    if user.get("referred_by"):
        from services import bonos
        await bonos.al_registrarse(db, user_id, user["referred_by"])

    return user
