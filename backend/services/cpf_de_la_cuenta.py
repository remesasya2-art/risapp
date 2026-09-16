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
import uuid
from datetime import datetime, timedelta, timezone

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


# ══════════════════════════════════════════════════════════════════════════
# LA RESERVA DEL CPF: TOMADO DESDE EL PRIMER INSTANTE
# ══════════════════════════════════════════════════════════════════════════
#
# EL AGUJERO QUE CIERRA, QUE NO ERA EL QUE ESTE ARCHIVO CREIA
#
#     El archivo decía que la ventana era de milisegundos —«entre contar y
#     escribir»— y que el índice único de `users` la tapaba. Las dos cosas
#     eran optimistas.
#
#     Al registrarse, el CPF NO SE GUARDA EN LA CUENTA: la cuenta todavía no
#     existe. Queda en `pending_verifications` esperando que la persona
#     confirme su correo, y la comprobación sólo mira `users`. O sea que
#     durante los QUINCE MINUTOS que dura el código de verificación, otra
#     persona podía registrarse con el mismo CPF y pasar igual. No hacía falta
#     que fuera simultáneo.
#
#     Así aparecieron los CPF repetidos que hoy impiden crear el índice.
#
# POR QUE EL CPF ES EL `_id`, Y NO UN CAMPO CON INDICE UNICO
#
#     En Mongo el `_id` es único POR CONSTRUCCION: no es un índice que haya
#     que crear, ni que pueda fallar por datos que ya están. Insertar es
#     atómico — el primero que llega gana y el segundo se entera en el mismo
#     instante—, que es exactamente la regla pedida: tomado desde que se
#     escribe, no quince minutos después.
#
#     Y esquiva el problema de hoy: el índice sobre `users.cpf_number` no se
#     puede crear porque ya hay repetidos. Esta colección nace vacía.
#
# LAS DOS VIDAS DE UNA RESERVA
#
#     Mientras se registra    tiene `vence_en`: si no confirma el correo, la
#                             reserva caduca sola y el CPF vuelve a estar libre
#     Cuando confirma         se le saca `vence_en` y queda anclada a su
#                             `user_id`, para siempre
#
#     La caducidad no es comodidad: sin ella, un dedo equivocado que tipea el
#     CPF de un tercero le bloquea la cuenta a esa persona PARA SIEMPRE, y sólo
#     un administrador podría liberarla. Quince minutos es lo que ya dura el
#     código de verificación: pasado eso el código no sirve, y la reserva
#     tampoco tiene por qué seguir en pie.
COLECCION_TOMADOS = "cpf_tomados"

# Lo mismo que dura el código que llega por correo (`routes/auth.py`). Si uno
# cambia, el otro tiene que acompañarlo: una reserva más corta que el código
# deja entrar a otro mientras el dueño todavía puede confirmar.
MINUTOS_DE_LA_RESERVA = 15

# ── Los mensajes ───────────────────────────────────────────────────────────
#
# Hay dos porque las dos situaciones se arreglan de forma distinta: si ya hay
# una cuenta, la persona tiene que entrar a ESA cuenta; si hay un registro a
# medio confirmar, tiene que ir a su correo. Un mensaje único mandaría a la
# mitad de la gente al lugar equivocado.
_YA_TIENE_CUENTA = (
    "Ese CPF ya tiene una cuenta en RIS App. Iniciá sesión con ella, o "
    "recuperá tu contraseña si no la recordás.")

_TOMADO_HACE_UN_RATO = (
    "Ese CPF ya está en un registro empezado hace unos minutos. Si fuiste vos, "
    "revisá tu correo y confirmá ese registro; si no lo confirmás, el CPF "
    "vuelve a quedar libre en unos minutos.")

NOMBRE_DE_LA_CADUCIDAD = "cpf_tomados_caducan"


def _tapado(n: str) -> str:
    """El CPF con casi todo tapado, para poder nombrarlo en el registro.

    El registro de la aplicación lo lee más gente de la que tiene por qué ver
    el documento de un cliente. Con los últimos tres dígitos alcanza para
    reconocerlo cuando ya se tiene el `user_id` al lado, que es el que sirve
    para encontrar la cuenta.
    """
    return "•••••••" + (n or "")[-3:]


def _vencida(reserva: dict, ahora: datetime) -> bool:
    """¿Esta reserva ya caducó?

    No alcanza con la caducidad de la base, por dos motivos: Mongo pasa el
    barrendero UNA VEZ POR MINUTO —así que hay hasta un minuto en que el
    documento sigue ahí, vencido— y en los tests no hay barrendero ninguno. Una
    reserva vencida tiene que poder tomarse en el acto.

    Sin fecha de vencimiento = anclada a una cuenta = no caduca nunca.
    """
    vence = (reserva or {}).get("vence_en")
    if not isinstance(vence, datetime):
        return False
    if vence.tzinfo is None:
        # El driver devuelve las fechas SIN zona horaria (el cliente no se crea
        # con `tz_aware`). Comparar una con zona contra una sin zona no devuelve
        # False: levanta TypeError. Eso ya vació un informe entero en este mismo
        # repositorio, y acá haría fallar el registro.
        vence = vence.replace(tzinfo=timezone.utc)
    return vence <= ahora


def _como_queda(ahora: datetime, user_id: str, correo: str) -> dict:
    """La escritura que deja la reserva como corresponde: a prueba, o anclada."""
    if user_id:
        cambio = {"$set": {"user_id": user_id, "anclado_en": ahora},
                  # Sin `vence_en` la caducidad de la base ni la mira. Es
                  # exactamente así como una reserva pasa a ser para siempre.
                  "$unset": {"vence_en": "", "marca": ""}}
    else:
        cambio = {"$set": {
            "vence_en": ahora + timedelta(minutes=MINUTOS_DE_LA_RESERVA)}}
    if correo:
        cambio["$set"]["correo"] = correo
    return cambio


async def asegurar_la_caducidad(db) -> str:
    """El índice que suelta solo las reservas sin confirmar. Devuelve qué pasó.

    `expireAfterSeconds=0` no quiere decir «borralo enseguida»: quiere decir
    «borralo cuando la fecha de `vence_en` ya pasó».

    Y lo que hace que todo el diseño funcione: Mongo IGNORA los documentos que
    NO tienen ese campo. A la reserva anclada a una cuenta se le saca
    `vence_en`, y con eso queda fuera del alcance del barrendero para siempre.

    NO LEVANTA NUNCA, por lo mismo que `asegurar_el_indice`: sin caducidad la
    regla sigue en pie, sólo que un registro abandonado se queda con su CPF
    hasta que alguien lo suelte a mano. Dejar la plataforma caída es peor.
    """
    try:
        await db[COLECCION_TOMADOS].create_index(
            "vence_en", expireAfterSeconds=0, name=NOMBRE_DE_LA_CADUCIDAD)
        return "listo"
    except Exception as e:
        logger.error(
            "SIN CADUCIDAD en %s (%s): un registro que nunca se confirma se "
            "queda con su CPF hasta que un administrador lo suelte.",
            COLECCION_TOMADOS, e)
        return "no se pudo"


async def esta_tomado_por_otro(db, valor, *, correo: str = "",
                               user_id: str = "") -> str:
    """¿Este CPF ya es de alguien que no es quien pregunta?

    Devuelve "" si está libre, "cuenta" si ya está anclado a una cuenta, y
    "reserva" si hay un registro empezado que todavía no confirmó el correo.

    ES SOLO PARA EL MENSAJE, NO PARA DECIDIR. Lee y después alguien escribe, y
    entre esas dos cosas hay una ventana. Lo que de verdad lo impide es `tomar`,
    que escribe y deja que la base decida.
    """
    n = cpf.normalizar(valor)
    if not n:
        return ""
    reserva = await db[COLECCION_TOMADOS].find_one({"_id": n})
    if not reserva:
        return ""
    duena = reserva.get("user_id") or ""
    if duena:
        return "" if user_id and duena == user_id else "cuenta"
    if correo and reserva.get("correo") == correo:
        return ""
    if _vencida(reserva, datetime.now(timezone.utc)):
        return ""
    return "reserva"


async def _sacar_la_vencida(db, n: str, marca) -> bool:
    """Saca una reserva vencida, pero SOLO si sigue siendo la que se leyó.

    Por qué el filtro lleva la `marca` y no alcanza con el `_id`: dos pedidos
    pueden leer la misma reserva vencida. El primero la saca y pone la suya; si
    el segundo borrara por `_id` a secas, borraría LA DEL PRIMERO —que está
    viva— y pondría la suya encima. Los dos se irían creyendo que tienen el CPF
    y uno de los dos estaría equivocado, sin enterarse nunca.

    La `marca` es lo que distingue «la vencida que vi» de «otra que entró
    recién». Si ya no coincide, este borrado no hace nada, y el `insert` de
    arriba se choca como corresponde.
    """
    resultado = await db[COLECCION_TOMADOS].delete_one(
        {"_id": n, "marca": marca, "user_id": {"$exists": False}})
    return bool(getattr(resultado, "deleted_count", 0))


async def tomar(db, valor, *, correo: str = "", user_id: str = "") -> str:
    """Toma el CPF. Levanta `CpfEnUso` si ya es de otro.

    ESTA ES LA GUARDA DE VERDAD, no el mensaje amable. El CPF es el `_id`, así
    que de dos pedidos simultáneos la base acepta UNO y al otro le contesta
    `DuplicateKeyError` en el mismo instante. No hay «contar y después
    escribir», que es la ventana por la que se colaron los repetidos que hoy
    están en la base.

    Sin `user_id` la reserva nace a prueba, con fecha de vencimiento: es un
    registro que todavía tiene que confirmar el correo. Con `user_id` nace —o
    queda— anclada, que es lo que pasa cuando el correo ya está confirmado.

    Es IDEMPOTENTE para el mismo correo: quien manda el formulario de nuevo
    —porque se equivocó la contraseña, o porque pidió otro código— no se choca
    consigo mismo.
    """
    n = exigir_valido(valor)
    ahora = datetime.now(timezone.utc)

    nueva = {"_id": n, "correo": correo, "tomado_en": ahora}
    if user_id:
        nueva["user_id"] = user_id
        nueva["anclado_en"] = ahora
    else:
        nueva["vence_en"] = ahora + timedelta(minutes=MINUTOS_DE_LA_RESERVA)
        # Para distinguir «la reserva vencida que acabo de leer» de «otra que
        # entró recién». Ver más abajo, donde se saca una vencida.
        nueva["marca"] = uuid.uuid4().hex

    try:
        await db[COLECCION_TOMADOS].insert_one(dict(nueva))
        return n
    except DuplicateKeyError:
        pass

    reserva = await db[COLECCION_TOMADOS].find_one({"_id": n}) or {}
    duena = reserva.get("user_id") or ""

    if duena:
        # Ya está anclada. Sólo sirve si es de quien pregunta.
        if user_id and duena == user_id:
            return n
        raise CpfEnUso(_YA_TIENE_CUENTA)

    if correo and reserva.get("correo") == correo:
        # Es de este mismo registro: se le renuevan los minutos, o se la ancla
        # si el correo ya quedó confirmado.
        await db[COLECCION_TOMADOS].update_one(
            {"_id": n, "correo": correo, "user_id": {"$exists": False}},
            _como_queda(ahora, user_id, correo))
        return n

    if _vencida(reserva, ahora):
        # Caducó y el barrendero de Mongo todavía no pasó. Se la saca y se
        # vuelve a intentar.
        await _sacar_la_vencida(db, n, reserva.get("marca"))
        try:
            await db[COLECCION_TOMADOS].insert_one(dict(nueva))
            return n
        except DuplicateKeyError:
            # Otro llegó primero a la que quedó libre. Es de él.
            raise CpfEnUso(_TOMADO_HACE_UN_RATO)

    raise CpfEnUso(_TOMADO_HACE_UN_RATO)


async def anclar(db, valor, user_id: str, *, correo: str = "") -> str:
    """Deja el CPF atado a esta cuenta para siempre.

    Es `tomar` con dueño: la misma escritura atómica, y de paso resuelve solo
    el caso de la reserva que ya no está —la caducidad se la comió porque el
    correo se confirmó tarde— volviéndola a crear, ya anclada.

    NO PISA la reserva de otro. Si en el medio alguien más tomó ese CPF, esto
    levanta `CpfEnUso` en vez de robárselo.
    """
    return await tomar(db, valor, correo=correo, user_id=user_id)


async def soltar_las_del_correo(db, correo: str, *, salvo: str = "") -> int:
    """Suelta las reservas de un registro que no se va a confirmar.

    El filtro lleva `user_id: {$exists: False}` y no es un detalle: sin esa
    condición, un registro abandonado con el mismo correo que una cuenta que ya
    existe le soltaría el CPF a esa cuenta.

    `salvo` es el CPF que este mismo registro está por tomar de nuevo. Sin él,
    volver a mandar el formulario con el MISMO CPF lo soltaría un instante antes
    de volver a tomarlo, y en ese instante otro puede llevárselo.
    """
    if not correo:
        return 0
    filtro = {"correo": correo, "user_id": {"$exists": False}}
    if salvo:
        filtro["_id"] = {"$ne": salvo}
    resultado = await db[COLECCION_TOMADOS].delete_many(filtro)
    return getattr(resultado, "deleted_count", 0) or 0


async def renovar_las_del_correo(db, correo: str) -> int:
    """Le corre el vencimiento a las reservas de este registro.

    Va de la mano de `/auth/resend-verification-code`, que le da minutos nuevos
    al código. Si la reserva no lo acompañara, el CPF quedaría libre mientras el
    código todavía sirve, y otro podría tomarlo justo antes de que el dueño
    confirme.
    """
    if not correo:
        return 0
    resultado = await db[COLECCION_TOMADOS].update_many(
        {"correo": correo, "user_id": {"$exists": False}},
        {"$set": {"vence_en": datetime.now(timezone.utc)
                  + timedelta(minutes=MINUTOS_DE_LA_RESERVA)}})
    return getattr(resultado, "modified_count", 0) or 0


async def soltar_el_ancla(db, valor, user_id: str) -> bool:
    """Deshace un anclaje que no llegó a escribirse en la cuenta.

    Pasa cuando se ancla el CPF y enseguida se descubre que la cuenta ya tenía
    otro. Sin esto, ese CPF quedaría anclado a una cuenta que no lo tiene, o
    sea bloqueado para todos y sin dueño que lo use.
    """
    n = cpf.normalizar(valor)
    if not n or not user_id:
        return False
    resultado = await db[COLECCION_TOMADOS].delete_one(
        {"_id": n, "user_id": user_id})
    return bool(getattr(resultado, "deleted_count", 0))


async def sembrar(db) -> dict:
    """Crea la reserva de cada CPF que ya está en una cuenta. Devuelve el resumen.

    HACE FALTA. La colección nace vacía, y una colección vacía quiere decir
    «todos los CPF están libres»: sin sembrarla, el CPF de cada cuenta que ya
    existe podría ser tomado por un registro nuevo.

    Y DE PASO DICE CUALES ESTAN REPETIDOS. Los repetidos son justamente los que
    impiden crear el índice único de `users.cpf_number`, y hasta ahora saber
    cuáles eran obligaba a consultar la base a mano. Acá el arranque los deja
    escritos, con el `user_id` de cada cuenta al lado.

    NO BORRA NI ARREGLA NADA. Qué hacer con dos cuentas que comparten un CPF
    —cuál se queda, qué pasa con el saldo de la otra— no lo puede decidir un
    arranque: lo decide una persona mirando las dos cuentas.
    """
    creadas, ya_estaban, repetidos = 0, 0, []

    cursor = db.users.find({"cpf_number": {"$nin": [None, ""]}},
                           {"_id": 0, "user_id": 1, "cpf_number": 1})
    async for usuario in cursor:
        n = cpf.normalizar(usuario.get("cpf_number"))
        user_id = usuario.get("user_id") or ""
        if not n or not user_id:
            continue
        ahora = datetime.now(timezone.utc)
        try:
            await db[COLECCION_TOMADOS].insert_one(
                {"_id": n, "user_id": user_id, "tomado_en": ahora,
                 "anclado_en": ahora, "sembrada": True})
            creadas += 1
            continue
        except DuplicateKeyError:
            pass
        otra = await db[COLECCION_TOMADOS].find_one({"_id": n}) or {}
        if otra.get("user_id") == user_id:
            ya_estaban += 1
            continue
        repetidos.append({"cpf": _tapado(n), "lo_tiene": otra.get("user_id"),
                          "tambien": user_id})

    if repetidos:
        logger.error(
            "CPF REPETIDOS: %s cuenta(s) comparten el CPF de otra. Hasta que se "
            "resuelvan, el índice único de users.cpf_number no se puede crear. "
            "Son: %s", len(repetidos), repetidos)

    return {"creadas": creadas, "ya_estaban": ya_estaban,
            "repetidos": repetidos}


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


async def revisar_para_registrar(db, valor, *, correo: str = "") -> str:
    """El CPF con el que se puede abrir una cuenta. Levanta si no se puede.

    Esto es el MENSAJE, y por eso mira las dos formas de estar tomado: la
    cuenta que ya existe y el registro que todavía no confirmó su correo. La
    segunda es la que faltaba, y es la que dejó entrar a los repetidos: durante
    los quince minutos del código, el CPF no estaba en ninguna cuenta.

    Quien decide es `tomar`, unas líneas más adelante en el registro.
    """
    n = exigir_valido(valor)
    if await esta_vetado(db, n):
        # No se le dice al visitante que su CPF está vetado: eso convierte el
        # registro en una forma de averiguar quién está en la lista. El mensaje
        # es el mismo que el del correo vetado, que ya existía.
        logger.warning("registro rechazado: el CPF está en la lista negra")
        raise CpfVetado("Esta cuenta no puede registrarse. Contactá a soporte.")
    if await ya_es_de_otra_cuenta(db, n):
        raise CpfEnUso(_YA_TIENE_CUENTA)
    tomado = await esta_tomado_por_otro(db, n, correo=correo)
    if tomado == "cuenta":
        raise CpfEnUso(_YA_TIENE_CUENTA)
    if tomado:
        raise CpfEnUso(_TOMADO_HACE_UN_RATO)
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

    # El anclaje va ANTES de escribir la cuenta, porque es lo único atómico de
    # los dos. Si algo sale mal después, se suelta más abajo.
    await anclar(db, n, user_id)

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

    # La cuenta se quedó con OTRO CPF (o no existe), así que el que se acaba de
    # anclar no es de nadie. Hay que soltarlo: un CPF anclado a una cuenta que
    # no lo tiene queda bloqueado para todos y sin dueño que lo use.
    await soltar_el_ancla(db, n, user_id)

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
