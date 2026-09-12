"""
El cofre: los documentos de identidad, cifrados en la base.

QUE PROBLEMA RESUELVE

    Los documentos del KYC —la foto del documento, la del CPF, la selfie— viven
    en la base como texto. Quien llegue a la base los ve todos: una cadena de
    conexión filtrada, un respaldo que se copió a un lugar equivocado, alguien
    de adentro con acceso de lectura, el proveedor de alojamiento.

    Es el conjunto de datos más sensible de la plataforma. No son montos ni
    saldos: son las caras y los documentos de gente que manda plata a Venezuela.

EL RIESGO QUE SE CREA AL CIFRAR, Y POR QUE MANDA EL DISEÑO

    Cifrar crea un peligro nuevo y peor que el que resuelve: **perder la llave
    es perder todos los documentos, sin recuperación posible**. Para una
    operación que recién arranca, quedarse sin poder probar a quién verificó es
    peor que una filtración.

    Así que todo lo de acá abajo está armado alrededor de esa idea:

      1. NADA SE PRENDE SOLO. Sin `COFRE_MODO=cifrando` la aplicación funciona
         exactamente como hoy: guarda en claro y lee en claro. Cifrar es una
         decisión explícita que se toma cuando la llave ya está respaldada.

      2. LEER SIEMPRE FUNCIONA CON LAS DOS FORMAS. Un documento en claro y uno
         cifrado se leen igual. Eso hace que la migración sea gradual y que
         volver atrás sea posible: si algo sale mal, se apaga el modo y lo ya
         cifrado se sigue leyendo mientras la llave esté.

      3. LA LLAVE VIEJA SE SIGUE PROBANDO. `COFRE_LLAVE_ANTERIOR` se intenta al
         leer. Una rotación mal hecha no destruye nada.

      4. HAY COMO COMPROBAR QUE LA LLAVE GUARDADA ES LA BUENA, sin restaurar
         nada. La huella de la llave (`huella()`) es pública y se puede mirar en
         el panel: alcanza para cotejar la que está corriendo contra la que hay
         anotada en papel. Ver `docs/la-llave-del-cofre.md`.

      5. SI FALTA LA LLAVE, NO SE CAE LA APLICACION. Falla el KYC, con un error
         claro, y las remesas siguen andando. Un cajón que no abre no puede
         cerrar el negocio entero.

QUE SE CIFRA Y QUE NO

    Sólo las cuatro imágenes del KYC. `cpf_number` y `document_number` NO se
    cifran: `cpf_number` tiene un índice en la base y cifrarlo rompería la
    búsqueda. Cifrar un campo que se busca exige otra técnica —índices ciegos—
    que no vale la pena a esta escala. Queda dicho para que no se lea como un
    olvido.

EL TAMAÑO NO CRECE, Y ESO NO ES UN DETALLE

    Un documento de Mongo no puede pasar de 16 MB, y una verificación con
    cuatro fotos ya se acerca. Cifrar el texto en base64 y volver a codificarlo
    lo haría crecer un tercio, lo que acercaría el problema.

    Por eso, cuando el valor es un `data:` —que es el 99% del volumen— se
    DECODIFICA el base64, se cifran los bytes reales, y se vuelve a codificar.
    El resultado ocupa lo mismo que el original, más 40 bytes de sobre.

COMO ESTA CIFRADO

    AES-256-GCM, del paquete `cryptography` que ya usa el proyecto. GCM además
    de cifrar AUTENTICA: un byte cambiado en la base se detecta al abrir y
    devuelve nada, en vez de devolver basura que parezca una foto rota.

    Un nonce aleatorio de 12 bytes por documento, guardado adelante del texto
    cifrado. No se reutiliza nunca porque se sortea en cada guardado.
"""
import base64
import hashlib
import hmac
import logging
import os

logger = logging.getLogger(__name__)

# La marca que dice «esto está cifrado». Un valor sin ella está en claro, y así
# es como conviven los dos formatos durante la migración y después de ella.
MARCA = "cofre:v1:"

VARIABLE_MODO = "COFRE_MODO"
VARIABLE_LLAVE = "COFRE_LLAVE"
VARIABLE_LLAVE_ANTERIOR = "COFRE_LLAVE_ANTERIOR"

# Lo que se guarda en la base para poder comprobar, sin restaurar nada, que la
# llave que está corriendo es la misma con la que se cifró todo.
TESTIGO = "el-cofre-abre"


# Los cuatro campos que se cifran. Vive acá, en un solo lugar, para que los
# puntos de lectura y de escritura no puedan desincronizarse — y para que una
# prueba pueda recorrerlos y exigir que ninguno se olvide de abrir el cofre.
CAMPOS_KYC = ("id_document_image", "id_document_image_back",
              "cpf_image", "selfie_image")


class CofreCerrado(Exception):
    """No se puede cifrar: falta la llave o está mal. El mensaje va al usuario."""


# ── De qué puede estar hecha una llave ─────────────────────────────────────
#
# EL MINIMO DE LARGO, Y POR QUE ES UN NUMERO Y NO UNA REGLA DE CONTRASEÑAS
#
#   Una llave generada al azar por un gestor de contraseñas tiene 40 o 64
#   caracteres y pasa esto sin enterarse. El mínimo no está para molestar a esa:
#   está para frenar la que alguien escribe a mano queriendo poder recordarla,
#   que es exactamente la que no sirve. No se piden mayúsculas ni símbolos
#   porque eso empuja a inventar «Risapp2026!», que cumple la regla y es peor
#   que veinticuatro letras al azar.
MINIMO_DE_LA_LLAVE = 24

# Y un mínimo de caracteres DISTINTOS: «aaaaaaaa…» treinta veces cumple el largo
# y no aporta nada. Cualquier llave sorteada lo pasa de sobra.
MINIMO_DE_DISTINTOS = 10

# El prefijo con el que se derivan los 32 bytes de una llave escrita como texto.
#
#   ESTE TEXTO NO SE CAMBIA NUNCA. Cambiarlo hace que la misma llave dé otros 32
#   bytes, y entonces los documentos cifrados con ella no se abren más. Si
#   alguna vez hiciera falta otra derivación, va con otro nombre y probando las
#   dos al leer, como ya se hace con la llave anterior.
_SAL_DE_LA_DERIVACION = b"llave-del-cofre:v1:"


def bytes_y_motivo(valor):
    """Los 32 bytes de una llave escrita, y si no se puede, POR QUE.

    DOS FORMAS DE ESCRIBIR UNA LLAVE, Y POR QUE HAY DOS

        La primera son 32 bytes en base64 —44 caracteres— que es lo que genera
        el panel. Se reconoce porque decodifica a 32 bytes justos, y se usa
        tal cual.

        La segunda es CUALQUIER TEXTO LARGO, del que se derivan los 32 bytes con
        sha256. Existe porque la primera forma, sola, obligaba al dueño del
        proyecto a abrir una terminal y correr Python para poder llenar una
        variable de entorno. En este proyecto hay una regla escrita sobre eso:
        configurar nunca puede requerir tocar código. Con la segunda forma
        alcanza el botón «generar contraseña» de cualquier gestor.

        EL ORDEN NO SE CAMBIA. Si la derivación se probara primero, una llave en
        base64 que ya estuviera en uso pasaría a dar OTROS 32 bytes, y todo lo
        cifrado con ella quedaría ilegible.

    POR QUE DEVUELVE EL MOTIVO Y NO SOLO `None`

        Porque hay dos lectores: los registros del servidor y una persona
        parada frente al panel con la llave en la mano. Si el motivo se armara
        en dos lugares, un día dirían cosas distintas — y el día que eso pase es
        el día en que alguien está tratando de entender por qué su llave no
        entra.
    """
    texto = (valor or "").strip()
    if not texto:
        return None, "No hay ninguna llave escrita."

    # LO QUE DISCRIMINA UNA FORMA DE LA OTRA ES QUE DECODIFIQUE A 32 BYTES
    # EXACTOS, y nada más. La primera versión de esto traía además una lista de
    # largos permitidos y el alfabeto de base64, para que una contraseña con un
    # «!» en el medio no se colara por esta rama: `b64decode` sin `validate`
    # descarta en silencio lo que no es del alfabeto.
    #
    # Ninguna de las dos hacía nada, y se comprobó rompiéndolas: quitar un
    # carácter cambia el largo, y un largo que no es múltiplo de cuatro hace
    # fallar el decodificador antes de devolver nada. O sea que la puerta que
    # pretendían cerrar no existe mientras se exijan 32 bytes justos.
    #
    # Se fueron. Dos guardas que se tapan entre sí y no se pueden romper es
    # justo lo que este proyecto ya pagó una vez: nadie sabe cuál de las dos
    # anda, y el día que una se toca nadie se entera.
    try:
        crudo = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except Exception:
        crudo = None
    if crudo is not None and len(crudo) == 32:
        return crudo, ""

    if len(texto) < MINIMO_DE_LA_LLAVE:
        return None, (
            f"La llave tiene {len(texto)} caracteres y necesita al menos "
            f"{MINIMO_DE_LA_LLAVE}. Usá el botón «generar contraseña» de tu "
            "gestor de contraseñas, o el del panel.")

    if len(set(texto)) < MINIMO_DE_DISTINTOS:
        return None, (
            "La llave repite muy pocos caracteres distintos. Tiene que ser algo "
            "sorteado al azar, no una palabra ni una tecla repetida.")

    return hashlib.sha256(_SAL_DE_LA_DERIVACION + texto.encode("utf-8")).digest(), ""


def _bytes_de_llave(valor):
    """Los 32 bytes, o `None` con el motivo escrito en los registros."""
    crudo, motivo = bytes_y_motivo(valor)
    if crudo is None and (valor or "").strip():
        # El caso «no hay llave» no se registra: es el estado normal mientras el
        # cofre está apagado, y un error por cada lectura llenaría los registros
        # de ruido justo donde hay que poder ver los problemas de verdad.
        logger.error("cofre: la llave puesta no sirve. %s", motivo)
    return crudo


def llave_nueva() -> dict:
    """Una llave nueva al azar, con su huella. NO la guarda en ningún lado.

    Sortear una llave no cambia nada: hasta que alguien la escriba en la
    variable de entorno, esto es texto en una pantalla. Por eso puede vivir
    detrás de un botón, mientras que cifrar los documentos viejos sigue siendo
    un guión que se corre a mano.
    """
    crudo = os.urandom(32)
    return {
        "llave": base64.urlsafe_b64encode(crudo).decode("ascii"),
        "huella": huella(crudo),
    }


def llave_actual():
    return _bytes_de_llave(os.environ.get(VARIABLE_LLAVE))


def llaves_para_leer():
    """Todas las llaves con las que se puede intentar abrir, en orden.

    La actual primero. La anterior existe para que una rotación a medio camino
    —donde parte está cifrado con una y parte con la otra— siga leyéndose
    entera. Sin esto, rotar la llave es destruir lo viejo.
    """
    llaves = []
    for variable in (VARIABLE_LLAVE, VARIABLE_LLAVE_ANTERIOR):
        llave = _bytes_de_llave(os.environ.get(variable))
        if llave and llave not in llaves:
            llaves.append(llave)
    return llaves


def modo() -> str:
    """`cifrando` guarda cifrado; `apagado` guarda en claro, como hasta ahora.

    Por omisión, apagado: prender el cifrado tiene que ser una decisión que
    alguien toma después de respaldar la llave, nunca algo que pasa solo en un
    despliegue.
    """
    valor = (os.environ.get(VARIABLE_MODO, "apagado") or "").strip().lower()
    return "cifrando" if valor == "cifrando" else "apagado"


def huella(llave=None) -> str:
    """Ocho caracteres que identifican a la llave sin revelarla.

    Es lo que hace operable todo esto: se puede mirar en el panel y cotejar
    contra la que está anotada en papel, sin sacar la llave de ningún lado y
    sin restaurar un respaldo para probar.
    """
    llave = llave if llave is not None else llave_actual()
    if not llave:
        return "(sin llave)"
    return hashlib.sha256(b"huella-del-cofre:" + llave).hexdigest()[:8]


def esta_cifrado(valor) -> bool:
    return isinstance(valor, str) and valor.startswith(MARCA)


# ── Guardar ────────────────────────────────────────────────────────────────

def _partir_data_url(texto):
    """`data:image/jpeg;base64,AAA` → (`image/jpeg`, bytes crudos), o `None`.

    Se separa para poder cifrar los BYTES y no el base64: así lo guardado ocupa
    lo mismo que antes, en vez de un tercio más.
    """
    if not texto.startswith("data:") or ";base64," not in texto:
        return None
    cabecera, datos = texto.split(";base64,", 1)
    tipo = cabecera[len("data:"):]
    try:
        return tipo, base64.b64decode(datos, validate=False)
    except Exception:
        return None


def guardar(valor):
    """Devuelve el valor cifrado, o tal cual si el cofre está apagado.

    Levanta `CofreCerrado` si el modo es `cifrando` y la llave no sirve. Es a
    propósito: guardar en claro creyendo que se está cifrando es la peor de las
    tres situaciones posibles, porque no se nota nunca.
    """
    if not isinstance(valor, str) or not valor:
        return valor
    if esta_cifrado(valor):
        return valor
    if modo() != "cifrando":
        return valor

    llave = llave_actual()
    if not llave:
        logger.error("cofre: COFRE_MODO=cifrando pero la llave no sirve. "
                     "No se guarda nada en claro.")
        raise CofreCerrado(
            "No se pudo guardar el documento de forma segura. Avisale a soporte; "
            "tus datos no se guardaron a medias.")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    partido = _partir_data_url(valor)
    tipo, crudo = partido if partido else ("", valor.encode("utf-8"))

    nonce = os.urandom(12)
    sellado = AESGCM(llave).encrypt(nonce, crudo, None)
    return f"{MARCA}{tipo}:{base64.b64encode(nonce + sellado).decode('ascii')}"


# ── Abrir ──────────────────────────────────────────────────────────────────

def abrir(valor, llaves=None):
    """El valor original. Un valor en claro pasa tal cual.

    Devuelve `None` si está cifrado y no se pudo abrir. Nunca devuelve algo a
    medias: GCM autentica, así que un byte cambiado en la base se detecta acá y
    no termina en la pantalla como una foto rota que nadie sabe explicar.

    `llaves` sirve para preguntar «¿ESTA llave abre esto?» sin tocar el entorno,
    que es lo que necesita el cotejo del panel. Se pasa la lista explícita en vez
    de escribir un descifrado aparte: un segundo descifrado en otro lugar se
    desincroniza del de verdad, y el día que eso pase la respuesta del panel
    sería «tu llave sirve» sobre documentos que no se abren.
    """
    if not isinstance(valor, str) or not valor:
        return valor
    if not esta_cifrado(valor):
        return valor                      # en claro: la migración es gradual

    resto = valor[len(MARCA):]
    tipo, _, cuerpo = resto.partition(":")
    try:
        crudo = base64.b64decode(cuerpo, validate=False)
        nonce, sellado = crudo[:12], crudo[12:]
    except Exception:
        logger.error("cofre: un valor cifrado está mal formado.")
        return None

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    for llave in (llaves_para_leer() if llaves is None else llaves):
        try:
            abierto = AESGCM(llave).decrypt(nonce, sellado, None)
        except Exception:
            continue                      # esta llave no es; se prueba la otra
        if tipo:
            return f"data:{tipo};base64,{base64.b64encode(abierto).decode('ascii')}"
        return abierto.decode("utf-8", errors="replace")

    if llaves is None:
        # Sólo se grita cuando el que no abre es el cofre de verdad. Con `llaves`
        # dadas, el que pregunta es el cotejo del panel y un «no abre» es una
        # respuesta esperada: registrarlo como alarma haría que probar una llave
        # equivocada a propósito ensuciara los registros con el aviso más grave
        # que tiene este módulo, que es justo el que no se puede ignorar.
        logger.error("cofre: NO SE PUDO ABRIR un documento. La llave que está "
                     "corriendo (huella %s) no es la que lo cifró. Ver "
                     "docs/la-llave-del-cofre.md antes de tocar nada.", huella())
    return None


def abrir_varios(documento, campos):
    """Abre varios campos de un documento. Devuelve una copia."""
    if not isinstance(documento, dict):
        return documento
    copia = dict(documento)
    for campo in campos:
        if campo in copia:
            copia[campo] = abrir(copia[campo])
    return copia


# ── Saber si está bien, sin restaurar nada ─────────────────────────────────

async def sellar_testigo(db):
    """Deja en la base una prueba de qué llave se está usando.

    Se escribe una sola vez, al prender el cofre. Sirve para que después
    `revisar()` pueda decir «la llave que hay puesta es la que cifró esto» sin
    tener que abrir un documento de una persona real.
    """
    if modo() != "cifrando" or not llave_actual():
        return None
    ya = await db.config.find_one({"_id": "cofre_testigo"})
    if ya:
        return ya
    doc = {"_id": "cofre_testigo", "testigo": guardar(TESTIGO), "huella": huella()}
    await db.config.insert_one(doc)
    logger.info("cofre: testigo sellado con la llave de huella %s", huella())
    return doc


async def revisar(db) -> dict:
    """El estado del cofre, para el panel y para el arranque.

    `ok` en False con el modo en `cifrando` significa que hay documentos que no
    se van a poder abrir. Es la única alarma que importa de todo este módulo.
    """
    estado = {
        "modo": modo(),
        "huella": huella(),
        "hay_llave": bool(llave_actual()),
        "hay_llave_anterior": bool(_bytes_de_llave(
            os.environ.get(VARIABLE_LLAVE_ANTERIOR))),
        "ok": True,
        # POR QUE HAY UN «MOTIVO» Y NO ALCANZA CON `ok`
        #
        #   «No llego a la base» y «la llave está mal» son dos problemas
        #   completamente distintos, y confundirlos es peligroso: alguien que
        #   lee «la llave no es la correcta» cuando en realidad la base está
        #   caída puede ponerse a cambiar la llave, que es exactamente lo que
        #   NO hay que tocar. Se separan.
        "motivo": "",
        "detalle": "",
    }

    if estado["modo"] == "apagado":
        estado["detalle"] = ("Los documentos se guardan en claro. Ver "
                             "docs/la-llave-del-cofre.md para prenderlo.")
        return estado

    if not estado["hay_llave"]:
        estado["ok"] = False
        estado["motivo"] = "sin_llave"
        estado["detalle"] = ("COFRE_MODO=cifrando pero no hay una llave válida. "
                             "El KYC no va a poder guardar ni leer documentos.")
        return estado

    try:
        testigo = await db.config.find_one({"_id": "cofre_testigo"})
    except Exception as e:
        estado["ok"] = False
        estado["motivo"] = "sin_base"
        estado["detalle"] = (
            "No se pudo hablar con la base, así que no hay con qué comprobar la "
            f"llave. Esto NO dice nada sobre la llave: no la cambies. ({type(e).__name__})")
        return estado

    if not testigo:
        estado["detalle"] = ("Cofre prendido, sin testigo todavía. Se sella solo "
                             "en el próximo arranque.")
        return estado

    if abrir(testigo.get("testigo")) != TESTIGO:
        estado["ok"] = False
        estado["motivo"] = "llave_equivocada"
        estado["detalle"] = (
            f"LA LLAVE NO ES LA CORRECTA. La que está corriendo tiene huella "
            f"{huella()} y los documentos se cifraron con {testigo.get('huella')}. "
            "NO cambies nada más: poné la llave correcta en COFRE_LLAVE. Ver "
            "docs/la-llave-del-cofre.md.")
        return estado

    estado["detalle"] = "Cofre abierto y verificado contra el testigo."
    return estado


async def cotejar(db, texto) -> dict:
    """¿Esta llave anotada sirve, y es la que abre lo que ya está guardado?

    POR QUE ESTO NO ES UN LUJO

        El procedimiento entero descansa en una frase: «guardá la llave en tres
        lugares que no fallen juntos». Una instrucción así no vale nada si quien
        la sigue no puede comprobar que la siguió. Copiar cuarenta caracteres a
        mano y no tener forma de saber si se copiaron bien es guardar un respaldo
        que nadie probó — que es lo mismo que no tener respaldo, sólo que con la
        tranquilidad puesta.

        Antes esto se contestaba con un guión en una terminal. Eso dejaba el
        único paso que de verdad protege los documentos fuera del alcance de
        quien tiene que darlo.

    LAS TRES PREGUNTAS, QUE SON DISTINTAS Y NO SE MEZCLAN

        1. `sirve`: el texto tiene forma de llave. Es lo mínimo.
        2. `es_la_que_corre`: es la misma que está puesta en el servidor ahora.
        3. `abre_los_documentos`: con ella se abre el testigo, o sea que es la
           llave con la que se cifró lo que ya está guardado. Es la única de las
           tres que responde «¿podría recuperar las fotos con esto?».

        La 3 vale `None` —no «False»— cuando no hay testigo todavía, porque el
        cofre nunca se prendió. Decir «no abre los documentos» ahí sería mandar a
        alguien a buscar un problema que no existe.
    """
    llave, motivo = bytes_y_motivo(texto)
    if llave is None:
        # Las otras dos en `None` y no en `False`: si el texto no tiene forma de
        # llave, no se llegó a evaluar ninguna de las dos preguntas. Decir «no es
        # la que corre» ahí es pintar de rojo algo que nadie miró, y tres
        # renglones rojos esconden cuál es el que importa — que es el primero.
        return {"sirve": False, "huella": "", "es_la_que_corre": None,
                "abre_los_documentos": None, "detalle": motivo}

    puesta = llave_actual()
    respuesta = {
        "sirve": True,
        "huella": huella(llave),
        # `None` cuando no hay ninguna llave puesta en el servidor, por el mismo
        # motivo que `abre_los_documentos`: sin nada con qué comparar, «no es la
        # misma» es cierto y se lee como una alarma. La pantalla lo pintaba en
        # rojo con el cofre apagado —que es el estado normal— y eso se vio en la
        # primera captura, no en los tests: las tres respuestas eran correctas
        # una por una y el conjunto asustaba.
        #
        # `compare_digest` y no `==`: comparar secretos así es la costumbre
        # correcta y no cuesta nada. Acá el que pregunta ya es el super
        # administrador, así que no cambia el riesgo — cambia que la costumbre
        # quede escrita donde alguien la va a copiar.
        "es_la_que_corre": hmac.compare_digest(llave, puesta) if puesta else None,
        "abre_los_documentos": None,
        "detalle": "",
    }

    try:
        testigo = await db.config.find_one({"_id": "cofre_testigo"})
    except Exception as e:
        respuesta["detalle"] = (
            "La llave tiene forma válida, pero no se pudo llegar a la base para "
            f"comprobar si es la de los documentos. ({type(e).__name__})")
        return respuesta

    if not testigo or not testigo.get("testigo"):
        respuesta["detalle"] = (
            "La llave tiene forma válida. Todavía no hay documentos cifrados con "
            "ninguna llave, así que no hay con qué compararla.")
        return respuesta

    respuesta["abre_los_documentos"] = abrir(testigo["testigo"], llaves=[llave]) == TESTIGO
    respuesta["detalle"] = (
        "Con esta llave se abren los documentos guardados."
        if respuesta["abre_los_documentos"] else
        "Esta llave NO abre los documentos guardados. Los cifró otra: la de "
        f"huella {testigo.get('huella')}.")
    return respuesta
