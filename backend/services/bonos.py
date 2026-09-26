"""
services/bonos.py — El bono de bienvenida y el del dueño del código.

LAS DOS REGLAS, COMO LAS PIDIO EL DUEÑO DEL PROYECTO

    Quien se registra con el código de otro recibe un bono —15 R$ por
    omisión— que queda BLOQUEADO hasta que apruebe su verificación de
    identidad. Una vez liberado, se puede gastar SOLO en envíos a Venezuela.

    El dueño del código recibe su bono —5 R$ por omisión— cuando la cuenta que
    usó su código aprueba su verificación. Eso vale para las primeras diez
    cuentas; de la once en adelante hace falta además que esa cuenta haga su
    primer envío a Venezuela, por encima de un monto mínimo.

    Los cuatro números —los dos bonos, el tope de diez y el mínimo del primer
    envío— se configuran desde el panel (`services/configuracion.py`). Ninguno
    está escrito acá.

POR QUE EL BONO VIVE EN SU PROPIA CUENTA, Y SIGUE AHI DESPUES DE LIBERARSE

    Porque «sólo para envíos a Venezuela» no se puede sostener de otra forma.

    Si al liberarse se pasara a `balance_ris`, quedaría gastable en cualquier
    cosa: un envío a Brasil, un retiro, una recarga. Habría que enseñarle la
    restricción a las veinte funciones que debitan `balance_ris`, y la primera
    que se olvidara dejaría el bono suelto.

    Así que la plata nunca se mezcla. Vive en `balance_ris_bono` desde que se
    otorga hasta que se gasta, y la ÚNICA ruta que sabe debitar de ahí es la
    del envío a Venezuela. Lo que cambia al liberarse no es dónde está la
    plata: es el estado que dice si se puede usar.

EL DESBLOQUEO CUELGA DE UNA SOLA FUNCION, Y ESO NO ES CASUAL

    Hay TRES lugares en el código que escriben `verification_status:
    "verified"`:

        routes/admin.py:2298    (aprobar una verificación por su id)
        routes/admin.py:2362    (la ruta vieja, que sigue viva)
        routes/kyc_admin.py     (el panel de KYC que se usa hoy)

    Si el desbloqueo colgara de uno solo, a las cuentas aprobadas por los
    otros dos el bono les quedaría bloqueado PARA SIEMPRE y en silencio: no
    hay error, no hay aviso, nadie mira. El usuario ve quince reales que no
    puede usar y escribe a soporte.

    Por eso los tres llaman a `al_aprobarse_el_kyc`, y por eso hay un test que
    recorre el repositorio buscando quién escribe ese estado y se pone rojo si
    aparece un cuarto que no la llame.

    (Una aclaración, porque es fácil contar mal: `admin_routes.py` también
    escribe `verification_status: "verified"`, pero al CREAR una cuenta de
    administrador nueva. Una cuenta que nace administradora no viene de un
    código de referido y no tiene bono. No es una puerta del KYC.)

NADA DE ESTO PUEDE TIRAR ABAJO LO QUE LO LLAMA

    Ni el registro, ni la aprobación del KYC, ni un envío. Las tres funciones
    de este módulo atrapan todo y devuelven un informe. Un bono que no se pudo
    acreditar es un reclamo; una aprobación de KYC que se cae porque el bono
    falló es un cliente que no puede operar y un administrador que no entiende
    por qué.

    Lo que sí queda es un ERROR en el registro con todo lo necesario para
    arreglarlo a mano.

UN DOCUMENTO NO COBRA DOS VECES

    La misma persona puede abrir dos cuentas con dos correos y usar su propio
    código. Al registrarse no hay con qué detectarlo —todavía no hay
    documento—, pero al aprobarse el KYC sí: ahí está el CPF.

    Se guarda el HASH del documento en `bonos_por_documento`, nunca el número.
    Un hash alcanza para preguntar «¿este documento ya cobró?» y no publica el
    documento de nadie en una colección más.
"""
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal

from services import configuracion, saldos
from services.money import from_db, para_mostrar, quantize_money

logger = logging.getLogger(__name__)

CUENTA_DEL_BONO = "balance_ris_bono"
COLECCION_DE_DOCUMENTOS = "bonos_por_documento"

# Los estados del bono de quien se registró con un código.
BLOQUEADO = "bloqueado"
LIBERADO = "liberado"
# El bono se anuló porque el documento de identidad ya había cobrado con otra
# cuenta. La plata se devuelve al asiento de gasto: un bono que nunca se va a
# pagar no puede quedar como deuda en el libro.
ANULADO_POR_DOCUMENTO = "anulado_documento_repetido"

# Los estados del pago al dueño del código.
PENDIENTE_KYC = "pendiente_kyc"
PENDIENTE_ENVIO = "pendiente_envio"
PAGADO = "pagado"
SIN_PAGO = "sin_pago"


def _ahora():
    return datetime.now(timezone.utc)


def huella_del_documento(numero: str) -> str:
    """El hash del documento, que es lo único que se guarda.

    `sha256` sobre el número normalizado. No lleva sal: una sal por documento
    haría imposible la única pregunta que se necesita —«¿este documento ya
    cobró?»— y una sal fija compartida no agrega nada contra quien tenga la
    base, porque el espacio de los CPF es chico y se recorre entero igual.

    Lo que sí hace es que la colección no contenga documentos de nadie. Para
    el propósito de acá —comparar contra los que ya cobraron— alcanza.
    """
    limpio = "".join(c for c in (numero or "") if c.isdigit())
    if not limpio:
        return ""
    return hashlib.sha256(limpio.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# 1. Al registrarse con un código
# ══════════════════════════════════════════════════════════════════════════

async def al_registrarse(db, user_id: str, codigo: str) -> dict:
    """Acredita el bono bloqueado a quien se registró con un código.

    Devuelve un informe. Nunca levanta: si esto falla, la cuenta ya está
    creada y el registro no se puede deshacer.
    """
    try:
        return await _al_registrarse(db, user_id, codigo)
    except Exception as e:                                   # pragma: no cover
        logger.error("bonos: no se pudo acreditar el bono de bienvenida a %s "
                     "con el código %r: %s", user_id, codigo, e)
        return {"acreditado": False, "motivo": "error"}


async def _al_registrarse(db, user_id: str, codigo: str) -> dict:
    if not codigo:
        return {"acreditado": False, "motivo": "sin_codigo"}

    # Proyección por lista de lo permitido: de quien refirió alcanza con el id.
    referente = await db.users.find_one({"referral_code": codigo},
                                        {"_id": 0, "user_id": 1})
    if not referente or not referente.get("user_id"):
        # La ruta de registro ya comprueba que el código exista, así que llegar
        # acá quiere decir que el dueño del código desapareció en el medio
        # —borró su cuenta durante los quince minutos de la verificación
        # pendiente—. No es un error: es que no hay a quién pagarle.
        logger.warning("bonos: el código %r ya no tiene dueño; %s se registra "
                       "sin bono", codigo, user_id)
        return {"acreditado": False, "motivo": "codigo_sin_dueno"}

    if referente["user_id"] == user_id:
        # No puede pasar por el camino normal —al registrarse la cuenta todavía
        # no tiene código propio— pero si algún día pasa, que no se pague.
        logger.warning("bonos: %s intentó usar su propio código", user_id)
        return {"acreditado": False, "motivo": "codigo_propio"}

    from services import remesas_abiertas
    if not await remesas_abiertas.esta_abierta(db):
        # El bono sólo se puede gastar en envíos a Venezuela. Con remesas en
        # pausa sería plata que la cuenta no puede usar y que la empresa
        # igual debe. Se registra sin bono, como con el bono en cero.
        return {"acreditado": False, "motivo": "remesas_en_pausa"}

    monto = await configuracion.leer(db, "bono_al_referido")
    if monto <= 0:
        # El bono apagado desde el panel. No es un error: es la forma de
        # cortar la promoción sin desplegar nada.
        return {"acreditado": False, "motivo": "bono_en_cero"}

    await saldos.mover(
        db, user_id, monto,
        movimiento="bono_bienvenida",
        cuenta=CUENTA_DEL_BONO,
        reference_kind="referido",
        reference_id=codigo,
        actor_type="sistema",
        notes=f"Bono de bienvenida por registrarse con el código {codigo}",
    )

    await db.users.update_one({"user_id": user_id}, {"$set": {
        "bono": {
            "estado": BLOQUEADO,
            "monto": str(monto),
            "codigo": codigo,
            "referente": referente["user_id"],
            "otorgado_en": _ahora(),
            "liberado_en": None,
            "pago_al_referente": PENDIENTE_KYC,
        },
    }})
    logger.info("bonos: %s recibió %s bloqueado por el código %s",
                user_id, monto, codigo)
    return {"acreditado": True, "monto": str(monto),
            "referente": referente["user_id"]}


# ══════════════════════════════════════════════════════════════════════════
# 2. Al aprobarse el KYC — la puerta única
# ══════════════════════════════════════════════════════════════════════════

async def al_aprobarse_el_kyc(db, user_id: str, *, documento: str = "") -> dict:
    """Libera el bono de quien verificó, y le paga al dueño de su código.

    La llaman las TRES rutas que aprueban un KYC, así:

        from services import bonos
        await bonos.al_aprobarse_el_kyc(db, user_id)

    `documento` es sólo para los tests. En producción se deja vacío y lo busca
    `_buscar_el_documento`, porque una de las tres rutas no lo tiene a mano y
    un parámetro que una ruta pasa vacío es una comprobación que se saltea sin
    que nadie lo note.

    Nunca levanta: una aprobación que se cae porque el bono falló deja al
    cliente sin poder operar y al administrador sin entender por qué.
    """
    try:
        return await _al_aprobarse_el_kyc(db, user_id, documento=documento)
    except Exception as e:                                   # pragma: no cover
        logger.error("bonos: falló el bono al aprobarse el KYC de %s: %s",
                     user_id, e)
        return {"liberado": False, "pagado_al_referente": False,
                "motivo": "error"}


async def _buscar_el_documento(db, user_id: str) -> str:
    """El CPF de la verificación aprobada de esta persona.

    Lo busca este módulo en vez de recibirlo como parámetro, y es a propósito.
    De las tres rutas que aprueban un KYC, dos tienen la verificación en la
    mano y la vieja sólo tiene el `user_id`. Si el documento fuera un
    parámetro, esa ruta lo pasaría vacío, la comprobación de «un documento no
    cobra dos veces» se saltearía SIN QUE NADIE LO NOTE, y el agujero estaría
    exactamente en la ruta que menos se mira.

    Así las tres llaman igual y ninguna puede olvidarse de nada.
    """
    v = await db.verifications.find_one(
        {"user_id": user_id},
        {"_id": 0, "cpf_number": 1, "document_number": 1},
        sort=[("submitted_at", -1)],
    )
    if not v:
        return ""
    return str(v.get("cpf_number") or v.get("document_number") or "")


async def _al_aprobarse_el_kyc(db, user_id: str, *, documento: str = "") -> dict:
    if not documento:
        documento = await _buscar_el_documento(db, user_id)
    persona = await db.users.find_one(
        {"user_id": user_id}, {"_id": 0, "user_id": 1, "bono": 1})
    bono = (persona or {}).get("bono") or {}
    if not bono or bono.get("estado") != BLOQUEADO:
        # Sin bono, o ya liberado. Que aprobar dos veces el mismo KYC no pague
        # dos veces es media guarda de este módulo.
        return {"liberado": False, "pagado_al_referente": False,
                "motivo": "sin_bono_bloqueado"}

    # ── El documento no puede cobrar dos veces ───────────────────────────
    huella = huella_del_documento(documento)
    if huella:
        ya = await db[COLECCION_DE_DOCUMENTOS].find_one(
            {"_id": huella}, {"_id": 1, "user_id": 1})
        if ya and ya.get("user_id") != user_id:
            return await _anular_por_documento_repetido(db, user_id, bono, ya)
        if not ya:
            try:
                await db[COLECCION_DE_DOCUMENTOS].insert_one(
                    {"_id": huella, "user_id": user_id, "cuando": _ahora()})
            except Exception as e:
                # Clave duplicada: dos aprobaciones simultáneas del mismo
                # documento. El que perdió la carrera se anula, que es lo mismo
                # que habría pasado si hubiera llegado un segundo después.
                logger.warning("bonos: el documento de %s ya estaba anotado "
                               "(%s); se anula su bono", user_id, e)
                otro = await db[COLECCION_DE_DOCUMENTOS].find_one(
                    {"_id": huella}, {"_id": 1, "user_id": 1})
                if otro and otro.get("user_id") != user_id:
                    return await _anular_por_documento_repetido(
                        db, user_id, bono, otro)

    # ── Se libera: la plata NO se mueve, cambia el estado ────────────────
    await db.users.update_one({"user_id": user_id}, {"$set": {
        "bono.estado": LIBERADO,
        "bono.liberado_en": _ahora(),
    }})
    logger.info("bonos: liberado el bono de %s", user_id)

    # El aviso de que ya lo puede usar. Es el momento en que la plata pasa de
    # ser una promesa a ser gastable, y sin aviso el usuario lo descubre sólo
    # si entra a mirar su panel. Va en su propio try, como el otro.
    try:
        from services.notifications import create_notification
        monto_del_bono = quantize_money(bono.get("monto") or 0)
        await create_notification(
            user_id=user_id,
            title="Tu bono de bienvenida quedó disponible",
            message=(f"Ya podés usar {para_mostrar(monto_del_bono, 'R$')} en "
                     "tus envíos a Venezuela."),
            notification_type="bono_liberado",
            data={"monto": str(monto_del_bono)},
        )
    except Exception as e:
        logger.error("bonos: no se pudo avisarle a %s de su bono liberado: %s",
                     user_id, e)

    pago = await _pagarle_al_referente(db, user_id, bono)
    return {"liberado": True, "monto": bono.get("monto"), **pago}


async def _anular_por_documento_repetido(db, user_id, bono, dueno) -> dict:
    """Devuelve el bono al gasto: no se va a pagar nunca, no puede ser deuda."""
    monto = quantize_money(bono.get("monto") or 0)
    if monto > 0:
        try:
            await saldos.mover(
                db, user_id, -monto,
                movimiento="bono_bienvenida",
                cuenta=CUENTA_DEL_BONO,
                reference_kind="referido",
                reference_id=str(bono.get("codigo") or ""),
                actor_type="sistema",
                notes="Bono anulado: el documento de identidad ya cobró con "
                      "otra cuenta",
            )
        except Exception as e:
            logger.error("bonos: no se pudo revertir el bono de %s: %s",
                         user_id, e)

    await db.users.update_one({"user_id": user_id}, {"$set": {
        "bono.estado": ANULADO_POR_DOCUMENTO,
        "bono.pago_al_referente": SIN_PAGO,
        "bono.anulado_en": _ahora(),
    }})
    logger.warning(
        "bonos: el bono de %s se anuló porque su documento ya había cobrado "
        "con %s", user_id, (dueno or {}).get("user_id"))
    return {"liberado": False, "pagado_al_referente": False,
            "motivo": "documento_repetido"}


async def _pagarle_al_referente(db, user_id: str, bono: dict) -> dict:
    """El bono del dueño del código, con la regla del tope.

    Hasta `referidos_que_pagan_con_solo_kyc` cuentas, cobra con el KYC. De ahí
    en adelante espera el primer envío de la cuenta referida.
    """
    referente = bono.get("referente")
    if not referente:
        return {"pagado_al_referente": False, "motivo": "sin_referente"}

    # El contador se incrementa con `find_one_and_update` y se lee el resultado:
    # leer, sumar en Python y escribir dejaría que dos aprobaciones simultáneas
    # vieran el mismo número y las dos se creyeran la número diez.
    despues = await db.users.find_one_and_update(
        {"user_id": referente},
        {"$inc": {"referidos_con_kyc": 1}},
        return_document=True,
        projection={"_id": 0, "user_id": 1, "referidos_con_kyc": 1},
    )
    if despues is None:
        logger.warning("bonos: el referente %s de %s ya no existe",
                       referente, user_id)
        await db.users.update_one({"user_id": user_id}, {
            "$set": {"bono.pago_al_referente": SIN_PAGO}})
        return {"pagado_al_referente": False, "motivo": "referente_inexistente"}

    numero = int(despues.get("referidos_con_kyc") or 1)
    tope = await configuracion.leer(db, "referidos_que_pagan_con_solo_kyc")

    if numero > tope:
        await db.users.update_one({"user_id": user_id}, {
            "$set": {"bono.pago_al_referente": PENDIENTE_ENVIO}})
        logger.info("bonos: %s es el referido número %s de %s (tope %s); su "
                    "bono espera el primer envío", user_id, numero, referente, tope)
        return {"pagado_al_referente": False, "motivo": "espera_primer_envio",
                "numero_de_referido": numero}

    return await _acreditarle_al_referente(db, user_id, referente, numero)


async def _acreditarle_al_referente(db, user_id, referente, numero) -> dict:
    """Le acredita al dueño del código, LIBRE y en su saldo normal.

    Libre y no bloqueado: ya es un usuario nuestro, con su cuenta y su
    historia. Bloquearlo complicaría sin proteger nada.
    """
    monto = await configuracion.leer(db, "bono_a_quien_refiere")
    if monto <= 0:
        await db.users.update_one({"user_id": user_id}, {
            "$set": {"bono.pago_al_referente": SIN_PAGO}})
        return {"pagado_al_referente": False, "motivo": "bono_en_cero"}

    try:
        await saldos.mover(
            db, referente, monto,
            movimiento="bono_referido",
            cuenta="balance_ris",
            reference_kind="referido",
            reference_id=user_id,
            actor_type="sistema",
            notes=f"Bono por el referido número {numero}",
        )
    except Exception as e:
        # Una cuenta de personal no puede recibir plata a título propio
        # (services/personal.py), y `saldos.mover` lo frena. Que no se pague no
        # puede dejar el bono del referido sin liberar.
        logger.error("bonos: no se le pudo acreditar el bono a %s por %s: %s",
                     referente, user_id, e)
        return {"pagado_al_referente": False, "motivo": "no_se_pudo_acreditar"}

    await db.users.update_one({"user_id": user_id}, {
        "$set": {"bono.pago_al_referente": PAGADO,
                 "bono.pagado_al_referente_en": _ahora()}})
    logger.info("bonos: %s cobró %s por su referido número %s (%s)",
                referente, monto, numero, user_id)

    # El aviso. Va DESPUES de acreditar y en su propio try: un aviso que no
    # sale no puede deshacer una plata que ya se movió. Y sin esto, los cinco
    # reales aparecían en el saldo sin que nadie le dijera por qué —el único
    # rastro era una línea en su historial que hay que ir a buscar—.
    #
    # NO SE NOMBRA AL REFERIDO. Quien invitó no tiene por qué enterarse de que
    # esa persona completó su verificación de identidad, ni cuándo. Es dato de
    # otro, y el bono se explica igual sin él.
    try:
        from services.notifications import create_notification
        await create_notification(
            user_id=referente,
            title="Cobraste tu bono por invitar",
            message=(f"Sumamos {para_mostrar(monto, 'R$')} a tu saldo porque "
                     "alguien que entró con tu código completó su "
                     "verificación. Gracias por recomendarnos."),
            notification_type="bono_referido",
            data={"monto": str(monto)},
        )
    except Exception as e:
        logger.error("bonos: no se pudo avisarle a %s de su bono: %s",
                     referente, e)

    return {"pagado_al_referente": True, "monto_al_referente": str(monto),
            "numero_de_referido": numero}


# ══════════════════════════════════════════════════════════════════════════
# 3. Al hacer el primer envío — para los que pasaron el tope
# ══════════════════════════════════════════════════════════════════════════

async def al_enviar_a_venezuela(db, user_id: str, monto_ris) -> dict:
    """Paga el bono que quedó esperando el primer envío de esta cuenta.

    Se llama DESPUES de que el envío quedó registrado. Nunca levanta: que un
    bono no se pague no puede hacer fallar una remesa que ya se cobró.
    """
    try:
        return await _al_enviar_a_venezuela(db, user_id, monto_ris)
    except Exception as e:                                   # pragma: no cover
        logger.error("bonos: falló el pago al referente de %s tras su envío: %s",
                     user_id, e)
        return {"pagado_al_referente": False, "motivo": "error"}


async def _al_enviar_a_venezuela(db, user_id: str, monto_ris) -> dict:
    persona = await db.users.find_one({"user_id": user_id},
                                      {"_id": 0, "bono": 1})
    bono = (persona or {}).get("bono") or {}
    if bono.get("pago_al_referente") != PENDIENTE_ENVIO:
        return {"pagado_al_referente": False, "motivo": "no_habia_nada_pendiente"}

    minimo = await configuracion.leer(db, "minimo_del_primer_envio")
    enviado = quantize_money(monto_ris)
    if enviado < minimo:
        logger.info("bonos: el envío de %s (%s) no llega al mínimo de %s; el "
                    "bono de su referente sigue esperando",
                    user_id, enviado, minimo)
        return {"pagado_al_referente": False, "motivo": "envio_menor_al_minimo",
                "minimo": str(minimo)}

    # `numero` es informativo acá: el contador ya se incrementó al aprobarse el
    # KYC, y volver a incrementarlo contaría dos veces al mismo referido.
    return await _acreditarle_al_referente(
        db, user_id, bono.get("referente"), bono.get("numero_de_referido", "?"))


# ══════════════════════════════════════════════════════════════════════════
# 4. La lista de referidos de una persona
# ══════════════════════════════════════════════════════════════════════════

POR_PAGINA = 20

# Qué se le cuenta al dueño del código de cada persona que usó su enlace, y
# qué no.
#
# LO QUE SE MUESTRA: el nombre de pila con la inicial del apellido, el mes en
# que se registró, y en qué estado está EL BONO —con el motivo, si está
# pendiente—.
#
# LO QUE NO: el correo. No le sirve para contactar a nadie que no pueda
# contactar ya —a esa persona la invitó él— y es el dato más abusable de los
# tres. Si algún día hace falta de verdad, es un campo más en la proyección y
# una decisión escrita al lado.
#
# El motivo SI se muestra, por decisión del dueño del proyecto. Vale decirlo
# claro: «le falta verificar su identidad» le cuenta a una persona algo del
# estado de otra. Se aceptó porque sin el motivo la pantalla no sirve para lo
# único que se le pide —saber a quién recordarle— y porque quien invitó ya
# sabe quién es.
MOTIVOS = {
    PENDIENTE_KYC: "Le falta verificar su identidad",
    PENDIENTE_ENVIO: "Le falta hacer su primer envío a Venezuela",
    PAGADO: "Cobrado",
    SIN_PAGO: "Sin bono",
}

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def nombre_corto(nombre: str) -> str:
    """«Ana Pereira Souza» → «Ana P.».

    El nombre de pila entero y la inicial del apellido. Alcanza para que quien
    invitó reconozca a quién invitó, y no publica el apellido completo de
    nadie en una pantalla que alguien puede estar mirando por encima del
    hombro en un colectivo.
    """
    partes = [p for p in (nombre or "").strip().split() if p]
    if not partes:
        return "Alguien"
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {partes[1][0].upper()}."


def _cuando(fecha) -> str:
    """«marzo de 2026». El mes y no el día: para recordarle a alguien alcanza
    con saber que fue hace mucho o hace poco, y el día exacto es más dato de
    esa persona sin ser más útil."""
    if not fecha:
        return ""
    try:
        return f"{MESES[fecha.month - 1]} de {fecha.year}"
    except Exception:                                        # pragma: no cover
        return ""


async def mis_referidos(db, user_id: str, *, pagina: int = 1) -> dict:
    """Los números y la página de referidos de ESTA persona.

    PAGINADA DESDE EL PRIMER DIA, aunque hoy nadie tenga veinte. Una lista que
    crece sin techo se descubre cuando alguien tiene cuatrocientos y la
    pantalla tarda diez segundos en abrir; y agregar la paginación después
    obliga a cambiar la ruta, la pantalla y sus tests a la vez.
    """
    pagina = max(1, int(pagina or 1))
    filtro = {"bono.referente": user_id}

    total = await db.users.count_documents(filtro)

    # Los números, contados por la base y no trayendo todo para contar en
    # Python: con cuatrocientos referidos eso serían cuatrocientos documentos
    # para mostrar cuatro números.
    cobrados = await db.users.count_documents(
        {**filtro, "bono.pago_al_referente": PAGADO})
    pendientes = await db.users.count_documents(
        {**filtro, "bono.pago_al_referente": {"$in": [PENDIENTE_KYC,
                                                      PENDIENTE_ENVIO]}})

    # Lo ganado sale del LIBRO y no de multiplicar cobrados por el monto de
    # hoy: el monto se configura desde el panel y puede haber cambiado entre
    # un cobro y otro. El libro dice lo que de verdad se acreditó.
    ganado = quantize_money(0)
    try:
        async for linea in db.ledger.find(
                {"user_id": user_id, "movement_type": "bono_referido",
                 "direction": "credit"},
                {"_id": 0, "amount": 1}):
            ganado += quantize_money(linea.get("amount") or 0)
    except Exception as e:                                   # pragma: no cover
        logger.warning("bonos: no se pudo sumar lo ganado de %s: %s", user_id, e)

    # Proyección por lista de lo permitido, como todo lo que ve el usuario.
    # Sin esto acá viajarían los documentos de identidad de cada referido.
    filas = []
    cursor = (db.users.find(filtro, {"_id": 0, "name": 1, "full_name": 1,
                                     "bono": 1})
              .sort("bono.otorgado_en", -1)
              .skip((pagina - 1) * POR_PAGINA)
              .limit(POR_PAGINA))
    async for persona in cursor:
        bono = persona.get("bono") or {}
        estado_del_pago = bono.get("pago_al_referente") or PENDIENTE_KYC
        filas.append({
            "nombre": nombre_corto(persona.get("full_name")
                                   or persona.get("name")),
            "cuando": _cuando(bono.get("otorgado_en")),
            "cobrado": estado_del_pago == PAGADO,
            "motivo": MOTIVOS.get(estado_del_pago, "Sin bono"),
        })

    return {
        "total": total,
        "cobrados": cobrados,
        "pendientes": pendientes,
        "ganado": str(ganado),
        "pagina": pagina,
        "por_pagina": POR_PAGINA,
        "hay_mas": total > pagina * POR_PAGINA,
        "referidos": filas,
    }


# ══════════════════════════════════════════════════════════════════════════
# 5. Lo que la pantalla necesita saber del bono propio
# ══════════════════════════════════════════════════════════════════════════

def para_la_pantalla(usuario: dict) -> dict:
    """El estado del bono de esta persona, como lo muestra la aplicación.

    La plata sale en TEXTO, que es como viaja el dinero por el borde del API.
    """
    bono = (usuario or {}).get("bono") or {}
    estado = bono.get("estado")
    if estado not in (BLOQUEADO, LIBERADO):
        # Sin bono, o anulado: no hay nada que mostrar. Un cero en pantalla
        # invita a preguntar por qué es cero.
        return {"tiene": False}

    saldo = from_db((usuario or {}).get(CUENTA_DEL_BONO))
    return {
        "tiene": saldo > 0,
        "saldo": str(saldo),
        "bloqueado": estado == BLOQUEADO,
        # El texto lo arma el servidor y no la pantalla, para que el monto y la
        # condición no puedan discrepar entre los dos lados.
        "leyenda": ("Se libera cuando aprobemos tu verificación de identidad. "
                    "Después lo podés usar en tus envíos a Venezuela."
                    if estado == BLOQUEADO else
                    "Disponible para tus envíos a Venezuela."),
    }


async def estado_para_la_pantalla(db, user_id: str) -> dict:
    """Lo que la aplicación le muestra a esta persona sobre su bono.

    Hace la lectura acá, en vez de recibir el documento del usuario, para que
    la ruta que lo muestra NO tenga que nombrar `balance_ris_bono`. Eso deja la
    guarda `test_solo_el_envio_a_venezuela_sabe_gastar_el_bono` con sentido:
    la lista de archivos que pueden tocar esa cuenta se mantiene corta, y una
    pantalla que sólo quiere mostrar un número no entra en esa lista.
    """
    usuario = await db.users.find_one(
        {"user_id": user_id},
        # Proyección por lista de lo permitido, como todo lo que ve el usuario.
        {"_id": 0, CUENTA_DEL_BONO: 1, "bono": 1})
    return para_la_pantalla(usuario or {})


async def disponible_para_enviar(db, usuario: dict) -> Decimal:
    """Cuánto del bono se puede usar en un envío a Venezuela, ahora mismo.

    Cero si está bloqueado, anulado, o si no hay bono. Es la única función que
    decide si el bono se puede gastar, así que la ruta del envío no repite la
    regla.
    """
    bono = (usuario or {}).get("bono") or {}
    if bono.get("estado") != LIBERADO:
        return quantize_money(0)
    return from_db((usuario or {}).get(CUENTA_DEL_BONO))
