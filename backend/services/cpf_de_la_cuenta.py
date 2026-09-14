"""
services/cpf_de_la_cuenta.py — El CPF que identifica a una cuenta.

QUE ATA ESTE MODULO

    Que quien paga sea el titular de la cuenta que recibe el saldo. Sin eso,
    cualquiera puede recargar la cuenta de cualquiera, y una plataforma que
    mueve plata a Venezuela sin saber de quién viene cada real no tiene cómo
    contestarle a un banco cuando pregunta.

    Hasta ahora eso no existía. La pantalla de recarga comparaba el CPF que
    escribía el cliente contra `users.cpf_number` —un campo que NINGUNA parte
    del código escribía— así que la comparación no podía dar bien nunca, y el
    servidor ni lo miraba: `client_cpf` llegaba con «00000000000» por omisión
    y se lo mandaba a Mercado Pago tal cual.

EL CPF SE ATA UNA VEZ Y NO SE CAMBIA SOLO

    La primera vez que una cuenta declara un CPF —al registrarse, o en su
    primera recarga si se registró antes de que esto existiera— ese número
    queda atado. De ahí en adelante es el único que puede pagar.

    Cambiarlo es cosa de un administrador, a mano y con su registro en la
    auditoría. Si el cliente pudiera cambiarlo, la atadura no ataría nada: el
    que quiere pagar con el CPF de otro simplemente lo cambiaría antes.

EL KYC NO LO VUELVE A PEDIR, PERO SI DISCREPA SE AVISA

    Quien ya lo declaró al registrarse no lo tipea de nuevo en la verificación:
    le llega puesto. Puede corregirlo —un dedo se equivoca, y el KYC es justo
    donde ese número se coteja contra la foto— y si lo cambia queda anotada la
    diferencia para quien revisa.

    Un CPF declarado sin foto no prueba nada por sí solo. Que DISCREPE del de
    los documentos sí dice algo, y es lo único que acá se puede detectar solo.
"""
import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from services import cpf

logger = logging.getLogger(__name__)


class CpfInvalido(ValueError):
    """El número no puede ser un CPF. El mensaje va al usuario."""


class CpfVetado(ValueError):
    """Ese CPF está en la lista negra."""


class CpfDeOtro(ValueError):
    """Esta cuenta ya tiene otro CPF atado."""


class CpfEnUso(ValueError):
    """Ese CPF ya está atado a otra cuenta. Un CPF, una cuenta."""


def el_de(usuario: dict) -> str:
    """El CPF atado a esta cuenta, normalizado. Vacío si todavía no tiene."""
    return cpf.normalizar((usuario or {}).get("cpf_number"))


def exigir_valido(valor, *, campo: str = "El CPF") -> str:
    """Devuelve el CPF normalizado, o levanta con un mensaje para el usuario."""
    n = cpf.normalizar(valor)
    if not n:
        raise CpfInvalido(f"{campo} es obligatorio.")
    if not cpf.es_valido(n):
        raise CpfInvalido(
            f"{campo} no es válido. Revisá que estén los once dígitos y que "
            "no falte ninguno.")
    return n


async def esta_vetado(db, valor) -> bool:
    """¿Este CPF está en la lista negra?

    La lista guarda el CPF en dígitos pelados (`_normalize_blacklist_value` en
    routes/admin.py), que es lo mismo que devuelve `cpf.normalizar`. Si esas
    dos normalizaciones se separan, el veto deja de encontrarse y nadie se
    entera: por eso las dos sacan todo lo que no es un dígito, y nada más.
    """
    n = cpf.normalizar(valor)
    if not n:
        return False
    return bool(await db.blacklist.find_one({"type": "cpf", "value": n}))


NOMBRE_DEL_INDICE = "cpf_number_unico"


async def asegurar_el_indice(db) -> str:
    """El índice ÚNICO sobre `users.cpf_number`. Devuelve qué pasó.

    ES LA GUARDA DE VERDAD DE «UN CPF, UNA CUENTA»

        La comprobación en el código mira y después escribe, y entre esas dos
        cosas hay una ventana por la que pasan dos registros simultáneos. La
        base no tiene esa ventana.

    POR QUE HAY QUE BORRAR EL VIEJO PRIMERO

        Ya existía un índice sobre el mismo campo, sin `unique`. Mongo NO
        reemplaza un índice cuando cambian sus opciones: falla con
        `IndexOptionsConflict` y deja el viejo. Este archivo ya tiene un
        comentario sobre esa misma trampa, en el índice de las sesiones, donde
        costó que las sesiones vencidas no se borraran nunca.

    SPARSE, PORQUE LOS QUE YA ESTAN NO TIENEN CPF

        Todas las cuentas creadas antes de esto no tienen el campo. Sin
        `sparse`, un índice único las tomaría a todas como el mismo valor
        —ausente— y sólo entraría una. Con `sparse`, las que no lo tienen
        quedan afuera del índice y conviven sin problema.

    NO LEVANTA NUNCA

        Si el índice no se puede crear —porque ya hay dos cuentas con el mismo
        CPF, que es lo único que lo haría fallar— la aplicación tiene que
        arrancar igual: dejar la plataforma caída es peor. Se registra como
        ERROR, y mientras tanto la comprobación del código sigue tapando el
        caso común.
    """
    from pymongo.errors import OperationFailure

    async def _crear():
        await db.users.create_index(
            "cpf_number", unique=True, sparse=True, name=NOMBRE_DEL_INDICE)

    try:
        await _crear()
        return "listo"
    except OperationFailure:
        pass

    # Segundo intento: sacar el que había y volver a crear.
    for viejo in (NOMBRE_DEL_INDICE, "cpf_number_1"):
        try:
            await db.users.drop_index(viejo)
        except Exception:
            pass
    try:
        await _crear()
        return "rehecho"
    except Exception as e:
        logger.error(
            "SIN INDICE UNICO en users.cpf_number (%s). Mientras falte, dos "
            "registros simultáneos con el mismo CPF pueden crear dos cuentas. "
            "Lo más probable es que ya haya CPF repetidos: buscalos con "
            "db.users.aggregate([{$group:{_id:'$cpf_number',n:{$sum:1}}},"
            "{$match:{n:{$gt:1},_id:{$ne:null}}}]).", e)
        return "no se pudo"


async def revisar_para_registrar(db, valor) -> str:
    """El CPF con el que se puede abrir una cuenta. Levanta si no se puede."""
    n = exigir_valido(valor)
    if await esta_vetado(db, n):
        # No se le dice al visitante que su CPF está vetado: eso convierte el
        # registro en una forma de averiguar quién está en la lista. El mensaje
        # es el mismo que el del correo vetado, que ya existía.
        logger.warning("registro rechazado: el CPF está en la lista negra")
        raise CpfVetado("Esta cuenta no puede registrarse. Contactá a soporte.")
    if await ya_es_de_otra_cuenta(db, n):
        raise CpfEnUso(
            "Ese CPF ya tiene una cuenta en RIS App. Iniciá sesión con ella, o "
            "recuperá tu contraseña si no la recordás.")
    return n


async def ya_es_de_otra_cuenta(db, valor, *, salvo: str = "") -> bool:
    """¿Este CPF ya está atado a otra cuenta?

    UN CPF, UNA CUENTA. El motivo es el cupo: una cuenta sin verificar puede
    operar hasta 200 R$ en dos operaciones, y sin esta regla la misma persona
    abre cuentas en serie y estira ese cupo todo lo que quiera.

    ESTO ES EL MENSAJE AMABLE, NO LA GARANTIA. Entre contar y escribir hay una
    ventana, y dos registros simultáneos con el mismo CPF la pasan los dos. Lo
    que de verdad lo impide es el índice ÚNICO de `users.cpf_number`
    (`server.py`): la base rechaza el segundo, pase lo que pase acá. Esta
    consulta existe para poder decir «ese CPF ya tiene cuenta» en vez de «error
    al registrar», no para decidir.
    """
    n = cpf.normalizar(valor)
    if not n:
        return False
    filtro = {"cpf_number": n}
    if salvo:
        filtro["user_id"] = {"$ne": salvo}
    return await db.users.count_documents(filtro) > 0


async def atar(db, user_id: str, valor) -> str:
    """Ata este CPF a la cuenta si todavía no tiene ninguno.

    Si ya tiene el mismo, no hace nada y devuelve el mismo. Si ya tiene OTRO,
    levanta: cambiarlo es cosa de un administrador.

    La condición va DENTRO del filtro de la escritura, no en un `if` antes.
    Dos pedidos simultáneos con CPF distintos no pueden atar los dos: el
    segundo no encuentra a quién escribirle y se entera.
    """
    n = exigir_valido(valor)
    if await esta_vetado(db, n):
        raise CpfVetado("Ese CPF no puede usarse. Contactá a soporte.")
    if await ya_es_de_otra_cuenta(db, n, salvo=user_id):
        raise CpfEnUso(
            "Ese CPF ya está registrado en otra cuenta. Un CPF puede tener una "
            "sola cuenta en RIS App.")

    try:
        resultado = await db.users.update_one(
            {"user_id": user_id,
             "$or": [{"cpf_number": {"$exists": False}}, {"cpf_number": None},
                     {"cpf_number": ""}]},
            {"$set": {"cpf_number": n,
                      "cpf_declarado_en": datetime.now(timezone.utc)}},
        )
    except DuplicateKeyError:
        # El índice único de la base ganó la carrera contra la comprobación de
        # arriba. Es el caso raro —dos pedidos a la vez con el mismo CPF— y es
        # justamente para eso que el índice existe. Se traduce al mismo mensaje
        # para que el cliente no vea la diferencia.
        logger.warning("dos cuentas intentaron atar el mismo CPF a la vez")
        raise CpfEnUso(
            "Ese CPF ya está registrado en otra cuenta. Un CPF puede tener una "
            "sola cuenta en RIS App.")

    if getattr(resultado, "modified_count", 0) == 1:
        return n

    # No se escribió: o ya tenía uno, o la cuenta no existe.
    usuario = await db.users.find_one({"user_id": user_id}, {"_id": 0, "cpf_number": 1})
    ya = el_de(usuario or {})
    if ya == n:
        return n
    if ya:
        raise CpfDeOtro(
            "Esta cuenta ya tiene un CPF registrado y no coincide con el que "
            "ingresaste. Si te equivocaste al registrarte, escribinos a soporte.")
    raise CpfInvalido("No se pudo registrar el CPF. Reintentá en un momento.")


async def exigir_para_pagar(db, usuario: dict, declarado) -> str:
    """El CPF con el que esta cuenta puede pagar. Levanta si no corresponde.

    Si la cuenta ya tiene uno atado, el declarado tiene que ser ése. Si no lo
    tiene —se registró antes de que esto existiera— se ata acá, en su primera
    recarga, y de ahí en adelante rige.
    """
    mio = el_de(usuario)
    n = exigir_valido(declarado, campo="El CPF del pagador")
    if not mio:
        return await atar(db, usuario.get("user_id"), n)
    if n != mio:
        raise CpfDeOtro(
            "El CPF del pagador tiene que ser el de tu cuenta. La recarga la "
            "tenés que hacer vos, no un tercero.")
    return mio


async def anotar_si_el_kyc_discrepa(db, user_id: str, del_kyc) -> dict:
    """Deja marcada la diferencia entre el CPF declarado y el de la verificación.

    No corta el KYC ni lo rechaza: es una señal para quien revisa, que tiene la
    foto delante y es el único que puede decidir. Cortar acá dejaría a alguien
    sin poder verificarse por un dedo equivocado, que es el caso frecuente.
    """
    usuario = await db.users.find_one({"user_id": user_id},
                                      {"_id": 0, "cpf_number": 1}) or {}
    declarado = el_de(usuario)
    n = cpf.normalizar(del_kyc)
    if not declarado or not n or declarado == n:
        return {"discrepa": False}

    logger.warning("KYC de %s: el CPF de la verificación no es el declarado "
                   "al registrarse", user_id)
    return {"discrepa": True, "declarado": declarado, "en_el_kyc": n}
