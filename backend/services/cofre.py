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


def _bytes_de_llave(valor):
    """Una llave de 32 bytes a partir del texto de la variable de entorno."""
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        crudo = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except Exception:
        logger.error("cofre: la llave no está en base64. Generá una con "
                     "`python backend/scripts/cofre.py crear`.")
        return None
    if len(crudo) != 32:
        logger.error("cofre: la llave tiene %d bytes y tiene que tener 32.", len(crudo))
        return None
    return crudo


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

def abrir(valor):
    """El valor original. Un valor en claro pasa tal cual.

    Devuelve `None` si está cifrado y no se pudo abrir. Nunca devuelve algo a
    medias: GCM autentica, así que un byte cambiado en la base se detecta acá y
    no termina en la pantalla como una foto rota que nadie sabe explicar.
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

    for llave in llaves_para_leer():
        try:
            abierto = AESGCM(llave).decrypt(nonce, sellado, None)
        except Exception:
            continue                      # esta llave no es; se prueba la otra
        if tipo:
            return f"data:{tipo};base64,{base64.b64encode(abierto).decode('ascii')}"
        return abierto.decode("utf-8", errors="replace")

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
