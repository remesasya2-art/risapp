"""
services/envios_archivos.py — Las fotos del envio: comprobantes y evidencias.

QUE GUARDA Y POR QUE APARTE
    El comprobante de despacho, la foto del paquete en el mostrador, la guia del
    transportista de destino. Van en su propia coleccion y NO adentro del
    documento del envio: ese documento se lee en cada cotizacion, en cada cobro y
    en cada pantalla del operador, y una foto de 3 MB adentro lo vuelve caro para
    siempre — ademas de acercarlo al limite de 16 MB de Mongo.

    El envio guarda un `asset_id` y nada mas.

LA CAPA ERA DELIBERADA, Y AHORA SE USA
    Cuando este modulo se escribio, los bytes vivian en Mongo y el docstring
    prometia que conectar un almacen de objetos iba a ser cambiar `guardar` y
    `leer` y nada mas. Eso es exactamente lo que paso: ni las rutas, ni el
    comprobante, ni el panel del operador saben donde estan los bytes.

DOS ALMACENES A LA VEZ, Y ESO NO ES UN ESTADO TRANSITORIO
    Cada ficha dice DONDE estan sus bytes (`almacen`: "r2" o "mongo") y con que
    clave. No hay un interruptor global, y es a proposito:

      * las fotos viejas siguen en Mongo hasta que la migracion las mueva, y
        mientras tanto se sirven igual;
      * si el almacen de objetos no contesta al subir, el archivo se guarda en
        Mongo y el usuario despacha. Rechazar el comprobante porque un servicio
        NUESTRO esta caido es cobrarle al usuario nuestra falla;
      * apagar las variables de entorno vuelve a Mongo para lo nuevo sin romper
        lo ya migrado... salvo para leerlo, que es la unica cosa que sigue
        necesitando el bucket.

    El precio es que hay dos caminos de lectura para siempre. La alternativa
    —migrar todo de una y confiar— es la que deja envios sin comprobante.

EL ORDEN DE ESCRITURA NO ES CASUAL
    Primero el objeto, despues la ficha en Mongo. Al reves, una escritura fallida
    del objeto deja una ficha que apunta a nada: una foto que da 404 para
    siempre y nadie sabe por que. En este orden, lo que queda de una falla es un
    objeto huerfano — basura barata que nadie lee.

TRES VALIDACIONES QUE NO SON OPCIONALES
    1. EL TIPO SE MIRA EN LOS BYTES, no en el `content-type` ni en la extension.
       Las dos las elige quien sube el archivo. Un .exe renombrado a .jpg pasa
       cualquier chequeo de nombre y ninguno de firma.
    2. UN TOPE DE TAMANO, medido sobre lo que efectivamente se leyo. Confiar en
       el `content-length` es confiar en el cliente.
    3. EL EXIF SE BORRA. Una foto sacada con un telefono lleva las coordenadas
       GPS de donde se saco. El comprobante de un envio no tiene por que
       registrar la casa de nadie, y una vez guardado ya no se puede deshacer.
"""

import asyncio
import hashlib
import io
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 8 MB. Una foto de comprobante sacada con un telefono pesa entre 1 y 4; el resto
# es margen. Mas que esto no es un comprobante, es otra cosa.
TAMANO_MAX_BYTES = 8 * 1024 * 1024

# Las firmas de los formatos que se aceptan. Es una lista blanca a proposito: un
# formato que no este aca no se guarda, aunque el navegador lo mande.
_FIRMAS = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"%PDF-", "application/pdf", "pdf"),
)

# HEIC/HEIF: el formato por defecto de los iPhone. La firma esta en el offset 4.
_FIRMA_HEIF = (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1", b"ftypmsf1")

TIPOS = tuple(t for _, t, _ in _FIRMAS) + ("image/heic",)


class ArchivoRechazado(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def tipo_real(datos: bytes) -> tuple[str, str] | None:
    """(content_type, extension) segun los BYTES, o None si no se reconoce."""
    if not datos:
        return None
    for firma, tipo, ext in _FIRMAS:
        if datos.startswith(firma):
            return tipo, ext
    if len(datos) >= 12 and datos[4:12] in _FIRMA_HEIF:
        return "image/heic", "heic"
    return None


def sin_exif(datos: bytes, tipo: str) -> bytes:
    """La misma imagen, sin metadatos. Si no se puede, devuelve los datos tal cual.

    Una foto de telefono lleva GPS, modelo, numero de serie y fecha exacta. Nada
    de eso hace falta para saber que un paquete se despacho, y todo eso queda
    guardado para siempre.

    Cuando la limpieza no se puede hacer —un PDF, una libreria ausente— se
    devuelve el original y se avisa. Rechazar el archivo seria peor: el usuario
    no puede despachar por un problema nuestro.
    """
    if tipo == "application/pdf":
        return datos
    try:
        from PIL import Image
        with Image.open(io.BytesIO(datos)) as imagen:
            formato = imagen.format
            # `paste` sobre una imagen nueva y no `copy()`: copiar arrastra el
            # diccionario `info`, que es donde vive el EXIF. Lo unico que cruza
            # aca son los pixeles.
            limpia = Image.new(imagen.mode, imagen.size)
            limpia.paste(imagen)
            salida = io.BytesIO()
            limpia.save(salida, format=formato)
            return salida.getvalue()
    except Exception as e:
        logger.warning(f"envios: no se pudo limpiar el EXIF ({tipo}): {e}")
        return datos


async def guardar(datos: bytes, *, envio_id: str, user_id: str, clase: str,
                  db=None, ahora=None) -> dict:
    """Guarda un archivo y devuelve su ficha. Lanza ArchivoRechazado."""
    ahora = ahora or datetime.now(timezone.utc)
    if not datos:
        raise ArchivoRechazado("El archivo llegó vacío. Probá de nuevo.")
    if len(datos) > TAMANO_MAX_BYTES:
        raise ArchivoRechazado(
            f"El archivo pesa {len(datos) // (1024 * 1024)} MB y el máximo son "
            f"{TAMANO_MAX_BYTES // (1024 * 1024)} MB. Sacá la foto de nuevo con menos "
            f"resolución.", http=413)

    reconocido = tipo_real(datos)
    if reconocido is None:
        raise ArchivoRechazado(
            "No reconocemos ese archivo. Subí una foto (JPG, PNG o HEIC) o un PDF.")
    tipo, extension = reconocido

    # En un hilo: decodificar y volver a codificar una imagen de 8 MB con PIL es
    # CPU pura, cientos de milisegundos, y adentro del bucle de eventos congela
    # las cotizaciones y los cobros de todo el proceso mientras dura. Es el mismo
    # argumento por el que boto3 no corre acá adentro.
    limpios = await asyncio.to_thread(sin_exif, datos, tipo)
    ficha = {
        "asset_id": f"ast_{uuid.uuid4().hex}",
        "envio_id": envio_id,
        "user_id": user_id,
        "clase": clase,
        "content_type": tipo,
        "extension": extension,
        "bytes": len(limpios),
        # El hash del contenido LIMPIO: sirve para detectar que alguien sube el
        # mismo comprobante en dos envios distintos, que es la forma barata de
        # intentar que a uno no se lo cobren.
        "sha256": hashlib.sha256(limpios).hexdigest(),
        "exif_removido": limpios != datos,
        # Donde estan los bytes de ESTA ficha. Un interruptor global mentiria en
        # cuanto haya un archivo de cada lado, que es el estado normal durante y
        # despues de una migracion.
        "almacen": "mongo",
        "clave": None,
        "bucket": None,
        "created_at": ahora,
    }
    from services import envios_almacen
    documento = {**ficha, "contenido": limpios}
    if envios_almacen.configurado():
        try:
            clave = envios_almacen.clave_de(envio_id, ficha["asset_id"], extension)
        except ValueError as e:
            # Los tres componentes los genera este sistema. Que uno no valide es
            # un defecto nuestro, no del usuario: se anota y se guarda en Mongo,
            # que siempre puede.
            logger.error(f"envios: clave de almacén inválida para {envio_id}: {e}")
            clave = None
        if clave and await envios_almacen.poner(clave, limpios, tipo):
            ficha["almacen"] = "r2"
            ficha["clave"] = clave
            ficha["bucket"] = envios_almacen.bucket_actual()
            # Sin `contenido`: es lo que hace que la ficha ocupe medio kilobyte y
            # lo que permite encontrar las que faltan migrar con un `$exists`.
            documento = dict(ficha)

    try:
        base = await _db(db)
        await base.envios_archivos.insert_one(documento)
    except Exception as e:
        logger.error(f"envios: no se pudo guardar el archivo de {envio_id}: {e}")
        raise ArchivoRechazado(
            "No se pudo guardar el archivo. Probá de nuevo en un momento.",
            http=503) from e
    return ficha


async def leer(asset_id: str, *, envio_id: str, db=None) -> dict | None:
    """El archivo con su contenido, o None si no existe la ficha.

    `envio_id` es OBLIGATORIO. Antes tenía default `None`, y con `None` el filtro
    se relajaba solo: el `asset_id` se servía desde cualquier envío. Un control
    que se apaga cuando le falta su insumo no es un control.

    Cuando la ficha existe pero los bytes no se pudieron traer, devuelve la ficha
    SIN `contenido` y con `error`. La diferencia importa: "no existe" es 404 y
    "no lo pudimos traer" no lo es, y contestar 404 a una caída del almacén manda
    al operador a buscar un comprobante que sí está.

    OJO: esta es la única lectura del módulo sin proyección de lista blanca, y la
    ficha lleva la ruta exacta del objeto en el bucket. Devolverla tal cual desde
    una ruta filtraría esa ruta. Las dos que existen sirven `contenido` y nada
    más.
    """
    if not asset_id or not envio_id:
        return None
    filtro = {"asset_id": asset_id, "envio_id": envio_id}
    try:
        base = await _db(db)
        ficha = await base.envios_archivos.find_one(filtro, {"_id": 0})
    except Exception as e:
        # Una caída de Mongo NO es "esa foto no existe". Contestar 404 acá es
        # exactamente el error que este módulo se cuida de no cometer con el
        # almacén de objetos, y encima afecta también a las fotos sin migrar.
        logger.error(f"envios: no se pudo leer el archivo {asset_id}: {e}")
        return {"asset_id": asset_id, "error": "base"}
    if not ficha:
        return None
    if ficha.get("contenido") is not None:
        return ficha

    clave = ficha.get("clave")
    if not clave:
        # Ficha sin bytes de ningún lado. No es una caída: no hay nada que traer.
        return ficha

    from services import envios_almacen
    datos, motivo = await envios_almacen.traer(
        clave, tope=TAMANO_MAX_BYTES, bucket=ficha.get("bucket"))
    if datos is None:
        ficha["error"] = motivo or "almacen"
        return ficha

    esperado = ficha.get("sha256")
    if esperado and hashlib.sha256(datos).hexdigest() != esperado:
        # Lo que volvió no es lo que guardamos. Puede ser una lectura truncada o
        # un objeto reemplazado; en los dos casos, servirlo es peor que no
        # servirlo: el operador VERIFICA EL PESO mirando esta foto y de ahí sale
        # un cobro. Un cobro calculado sobre bytes que no podemos identificar no
        # se puede defender después.
        logger.error(
            f"envios: el contenido de {asset_id} no coincide con su hash "
            f"({clave}); no se sirve")
        ficha["error"] = "integridad"
        return ficha

    ficha["contenido"] = datos
    return ficha


# Los motivos que mejoran solos. El resto no: repetir la petición no va a hacer
# aparecer un objeto que no está ni arreglar un hash que no coincide.
TRANSITORIOS = ("almacen", "base")


def exigir_bytes(ficha):
    """Lanza ArchivoRechazado si la ficha no trae bytes servibles.

    404 si la foto no existe; **503 si existe y no la pudimos traer**. La
    diferencia no es cosmética: contestar 404 cuando el almacén no responde manda
    al operador a buscar un comprobante que sí está cargado, y a decirle al
    usuario que lo suba de nuevo. Es convertir una falla nuestra, transitoria, en
    trabajo del usuario.

    Vive acá y no en la ruta porque las dos rutas que sirven fotos —la del
    usuario y la del operador— tienen que contestar exactamente lo mismo.
    """
    if not ficha:
        raise ArchivoRechazado("No encontramos esa foto.", http=404)
    if not ficha.get("contenido"):
        motivo = ficha.get("error")
        if motivo in TRANSITORIOS:
            raise ArchivoRechazado(
                "La foto está guardada pero no la pudimos traer. Probá de nuevo en "
                "un minuto.", http=503)
        if motivo:
            # Permanente. Decirle "probá de nuevo en un minuto" a alguien cuyo
            # objeto no existe, o cuyos bytes no coinciden con su hash, es
            # mandarlo a reintentar para siempre. 410: estuvo, y no se puede
            # recuperar por acá.
            raise ArchivoRechazado(
                "No pudimos recuperar esta foto. Avisale a soporte con el número "
                "del envío.", http=410)
        raise ArchivoRechazado("No encontramos esa foto.", http=404)
    return ficha


async def ya_usado(sha256: str, envio_id: str, db=None) -> str | None:
    """El envío en el que ya se subió este mismo archivo, si hay otro.

    Subir el comprobante de un envío en otro es la forma barata de intentar que
    uno de los dos no se cobre. No se rechaza automáticamente —dos fotos idénticas
    pueden ser un reintento legítimo del mismo usuario— pero el operador tiene
    que verlo antes de verificar.
    """
    try:
        base = await _db(db)
        # `$ne` sobre el propio envio: `guardar` INSERTA antes de llamar aca, y
        # si Mongo devolvia primero el documento recien insertado la marca se
        # perdia en silencio. Depender del orden natural para una senal de fraude
        # es no tener la senal.
        otro = await base.envios_archivos.find_one(
            {"sha256": sha256, "envio_id": {"$ne": envio_id}},
            {"_id": 0, "envio_id": 1})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo chequear duplicados de archivo: {e}")
        return None
    if otro and otro.get("envio_id") and otro["envio_id"] != envio_id:
        return otro["envio_id"]
    return None


# --- Migración de lo que quedó en Mongo -------------------------------------
#
# La migración es POR LOTES y REANUDABLE, no un script de una sola corrida. Tres
# razones, y ninguna es preferencia:
#
#   1. Son miles de archivos contra un servicio remoto. Una corrida larga que se
#      corta a la mitad, sin registro de por dónde iba, se reintenta desde cero.
#   2. Cada lote es una petición HTTP del panel. Una que tarda cinco minutos la
#      corta el proxy antes de terminar, y el admin ve un error sobre trabajo que
#      en realidad se hizo.
#   3. Un lote no la termina y está bien: el estado mixto ES el diseño (ver
#      arriba). Se puede migrar de a poco, mirando el contador bajar.
#
# LO QUE HACE QUE SEA SEGURA: se escribe, SE VUELVE A LEER Y SE COMPARA, y recién
# entonces se borran los bytes de Mongo. Sin la relectura, un `put_object` que
# devuelve 200 sobre un bucket que descarta el cuerpo —o una clave mal armada—
# borra el único ejemplar que existía.

MIGRACION_LOTE_POR_DEFECTO = 20
MIGRACION_LOTE_MAX = 50

# Presupuesto de pared del lote. El comentario de arriba dice que una petición de
# cinco minutos la corta el proxy y el admin ve un error sobre trabajo que sí se
# hizo; sin este techo, veinte archivos contra un bucket degradado llegan ahí
# tranquilamente. Se corta, se devuelve lo hecho y `parcial` lo dice.
MIGRACION_SEGUNDOS_MAX = 45

# Lo que todavía no está en el almacén de objetos. `$ne` y no `== "mongo"`: los
# documentos escritos ANTES de este PR no tienen el campo `almacen`, y con
# `{"almacen": "mongo"}` la migración no veía una sola de las fotos que existen
# —que son exactamente las que viene a mover— y encima el panel informaba
# `en_mongo: 0`, que se lee como "ya está". Un filtro que falla en la dirección
# de "no queda nada pendiente" es peor que uno que falla ruidosamente.
#
# `migracion_error` saca de la cola lo que falló de manera PERMANENTE. Sin eso,
# un archivo cuyo hash no coincide vuelve en el primer lugar de cada lote para
# siempre: el admin clickea, ve `migrados: 0`, clickea otra vez, ve `migrados: 0`
# y la migración no avanza nunca más.
_PENDIENTES = {"almacen": {"$ne": "r2"}, "migracion_error": {"$exists": False}}

_PROYECCION_MIGRACION = {"_id": 0, "asset_id": 1, "envio_id": 1, "extension": 1,
                         "sha256": 1, "content_type": 1}


async def conteo(db=None) -> dict:
    """Cuántas fotos hay de cada lado. Es lo que mira el panel."""
    try:
        base = await _db(db)
        en_mongo = await base.envios_archivos.count_documents(_PENDIENTES)
        en_almacen = await base.envios_archivos.count_documents({"almacen": "r2"})
        con_problema = await base.envios_archivos.count_documents(
            {"migracion_error": {"$exists": True}})
    except Exception as e:
        logger.warning(f"envios: no se pudieron contar los archivos: {e}")
        # `None` y no `0`: "no sé" y "no queda ninguno" no se pueden confundir en
        # la pantalla desde la que alguien decide que la migración terminó.
        return {"en_mongo": None, "en_almacen": None, "con_problema": None}
    return {"en_mongo": en_mongo, "en_almacen": en_almacen,
            "con_problema": con_problema}


async def migrar_lote(*, limite: int = MIGRACION_LOTE_POR_DEFECTO, db=None,
                      ahora=None) -> dict:
    """Mueve al almacén de objetos un lote de fotos que todavía viven en Mongo."""
    ahora = ahora or datetime.now(timezone.utc)
    from services import envios_almacen
    if not envios_almacen.configurado():
        return {"activo": False, "migrados": 0, "fallidos": 0, "sospechosos": 0,
                "ya_estaban": 0, "parcial": False,
                "detalle": ["El almacén de objetos no está configurado."]}
    try:
        limite = int(limite or MIGRACION_LOTE_POR_DEFECTO)
    except (TypeError, ValueError):
        limite = MIGRACION_LOTE_POR_DEFECTO
    limite = max(1, min(limite, MIGRACION_LOTE_MAX))

    base = await _db(db)
    try:
        # Se busca por `almacen` y no por `{"contenido": {"$exists": True}}`
        # —que es la verdad literal— porque el segundo no puede usar un indice, y
        # un indice sobre `contenido` seria un indice sobre los blobs: claves de
        # megabytes, por encima del limite de Mongo. Los dos filtros son
        # equivalentes por construccion: `guardar` escribe `almacen` siempre. El
        # `$exists` sigue estando donde importa, que es el filtro del update.
        fichas = await base.envios_archivos.find(
            _PENDIENTES, _PROYECCION_MIGRACION).to_list(limite)
    except Exception as e:
        logger.error(f"envios: no se pudo listar el lote a migrar: {e}")
        return {"activo": True, "migrados": 0, "fallidos": 0, "sospechosos": 0,
                "ya_estaban": 0, "parcial": False,
                "detalle": ["No se pudo leer la lista de archivos pendientes."]}

    migrados = fallidos = sospechosos = ya_estaban = 0
    parcial = False
    detalle = []
    limite_de_tiempo = time.monotonic() + MIGRACION_SEGUNDOS_MAX
    for ficha in fichas:
        if time.monotonic() >= limite_de_tiempo:
            parcial = True
            break
        asset_id = ficha.get("asset_id")
        try:
            resultado = await _migrar_una(base, ficha, ahora)
        except Exception as e:
            # `_migrar_una` promete no lanzar. Si algún día deja de cumplirlo, la
            # excepción no puede tirar el lote entero y perder la cuenta de lo
            # que sí se movió.
            logger.error(f"envios: la migración de {asset_id} lanzó: {e}")
            resultado = "error inesperado"
        if resultado == "ok":
            migrados += 1
        elif resultado == "ya_estaba":
            ya_estaban += 1
        elif resultado == "sospechoso":
            sospechosos += 1
            detalle.append(f"{asset_id}: los bytes en Mongo no coinciden con su hash; "
                           f"se dejó donde está y se sacó de la cola.")
        else:
            fallidos += 1
            detalle.append(f"{asset_id}: {resultado}")

    salida = {"activo": True, "migrados": migrados, "fallidos": fallidos,
              "sospechosos": sospechosos, "ya_estaban": ya_estaban,
              "parcial": parcial, "detalle": detalle[:20]}
    salida.update(await conteo(base))
    return salida


async def _marcar_problema(base, asset_id: str, motivo: str, ahora):
    """Saca de la cola de migración un archivo que no se puede migrar nunca.

    Los transitorios NO pasan por acá: un bucket que no contesta hoy contesta
    mañana, y esos tienen que volver a intentarse en el lote siguiente.
    """
    try:
        await base.envios_archivos.update_one(
            {"asset_id": asset_id},
            {"$set": {"migracion_error": motivo, "migracion_error_at": ahora}})
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo marcar {asset_id} como problemático: {e}")


async def _migrar_una(base, ficha: dict, ahora) -> str:
    """"ok", "ya_estaba", "sospechoso", o el motivo de la falla. Nunca lanza."""
    from services import envios_almacen
    asset_id = ficha.get("asset_id")
    if not asset_id:                                          # pragma: no cover
        return "la ficha no tiene asset_id"
    try:
        completa = await base.envios_archivos.find_one(
            {"asset_id": asset_id}, {"_id": 0, "contenido": 1})
        if not completa or completa.get("contenido") is None:
            # Otro lote la migró entre el listado y ahora. No es una falla, pero
            # tampoco es una migración: contarla como tal infla el número que el
            # admin usa para saber si avanzó.
            return "ya_estaba"
        # La conversión va ADENTRO del try: un `contenido` de un tipo inesperado
        # lanza TypeError, y afuera esa excepción se llevaba puesto el lote.
        datos = bytes(completa["contenido"])
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el contenido de {asset_id}: {e}")
        return "no se pudo leer el contenido en Mongo"

    esperado = ficha.get("sha256")
    if esperado and hashlib.sha256(datos).hexdigest() != esperado:
        # Los bytes que hay en Mongo no son los que se guardaron. Migrarlos
        # propagaría la corrupción Y borraría el único ejemplar. Se deja quieto y
        # se reporta: es lo único honesto que se puede hacer con un dato que no
        # se puede identificar.
        logger.error(f"envios: {asset_id} no coincide con su hash en Mongo; no se migra")
        await _marcar_problema(base, asset_id, "hash_no_coincide", ahora)
        return "sospechoso"

    try:
        clave = envios_almacen.clave_de(
            ficha.get("envio_id"), asset_id, ficha.get("extension"))
    except ValueError as e:
        logger.error(f"envios: no se pudo armar la clave de {asset_id}: {e}")
        # Permanente: la clave se arma con campos de la ficha, que no cambian
        # solos. Reintentarlo cada lote es trabar la cola.
        await _marcar_problema(base, asset_id, "clave_invalida", ahora)
        return "no se pudo armar la clave"

    if not await envios_almacen.poner(
            clave, datos, ficha.get("content_type") or "application/octet-stream",
            presupuesto=envios_almacen.SEGUNDOS_LECTURA):
        return "no se pudo escribir en el almacén"

    vuelta, _ = await envios_almacen.traer(clave, tope=TAMANO_MAX_BYTES,
                                           bucket=envios_almacen.bucket_actual())
    if vuelta != datos:
        # La relectura es la razón de ser de esta función. Acá es donde se
        # descubre que el bucket aceptó la escritura y guardó otra cosa, ANTES de
        # borrar el ejemplar bueno.
        logger.error(f"envios: {asset_id} no volvió igual de {clave}; no se borra de Mongo")
        return "lo que se leyó de vuelta no es lo que se escribió"

    try:
        resultado = await base.envios_archivos.update_one(
            # `contenido` va EN EL FILTRO: si otro lote ya lo migró entre medio,
            # este update no matchea y no pisa la clave que dejó el otro.
            {"asset_id": asset_id, "contenido": {"$exists": True}},
            {"$set": {"almacen": "r2", "clave": clave, "migrado_at": ahora,
                      # La dirección completa, no solo la mitad de adentro.
                      "bucket": envios_almacen.bucket_actual()},
             # El ÚNICO borrado de bytes de todo el módulo. Está acá, después de
             # escribir, releer y comparar, y en ningún otro lado.
             "$unset": {"contenido": ""}})
    except Exception as e:
        logger.error(f"envios: no se pudo marcar {asset_id} como migrado: {e}")
        return "no se pudo actualizar la ficha"
    if getattr(resultado, "matched_count", 0) == 0:
        # No matcheó: otro lote llegó primero. El objeto ya está escrito y la
        # ficha ya apunta ahí. Nada que arreglar, pero tampoco lo migró éste.
        return "ya_estaba"
    return "ok"
