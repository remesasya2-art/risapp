"""
services/envios_archivos.py — Las fotos del envio: comprobantes y evidencias.

QUE GUARDA Y POR QUE APARTE
    El comprobante de despacho, la foto del paquete en el mostrador, la guia del
    transportista de destino. Van en su propia coleccion y NO adentro del
    documento del envio: ese documento se lee en cada cotizacion, en cada cobro y
    en cada pantalla del operador, y una foto de 3 MB adentro lo vuelve caro para
    siempre — ademas de acercarlo al limite de 16 MB de Mongo.

    El envio guarda un `asset_id` y nada mas.

LA CAPA ES DELIBERADA
    Hoy los bytes viven en Mongo. El dia que se conecte R2 —almacenamiento de
    objetos, que es donde tienen que estar— se cambia el cuerpo de `guardar` y
    `leer` y NADA MAS: ni las rutas, ni el comprobante, ni el panel del operador
    saben donde estan los bytes. Por eso este modulo existe aunque su primera
    implementacion sea la simple.

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

import hashlib
import io
import logging
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

    limpios = sin_exif(datos, tipo)
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
        "created_at": ahora,
    }
    try:
        base = await _db(db)
        await base.envios_archivos.insert_one({**ficha, "contenido": limpios})
    except Exception as e:
        logger.error(f"envios: no se pudo guardar el archivo de {envio_id}: {e}")
        raise ArchivoRechazado(
            "No se pudo guardar el archivo. Probá de nuevo en un momento.",
            http=503) from e
    return ficha


async def leer(asset_id: str, *, envio_id: str = None, db=None) -> dict | None:
    """El archivo con su contenido, o None. El envío se pasa para acotar: un
    asset_id suelto no debería poder leerse desde cualquier envío."""
    filtro = {"asset_id": asset_id}
    if envio_id:
        filtro["envio_id"] = envio_id
    try:
        base = await _db(db)
        return await base.envios_archivos.find_one(filtro, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el archivo {asset_id}: {e}")
        return None


async def ya_usado(sha256: str, envio_id: str, db=None) -> str | None:
    """El envío en el que ya se subió este mismo archivo, si hay otro.

    Subir el comprobante de un envío en otro es la forma barata de intentar que
    uno de los dos no se cobre. No se rechaza automáticamente —dos fotos idénticas
    pueden ser un reintento legítimo del mismo usuario— pero el operador tiene
    que verlo antes de verificar.
    """
    try:
        base = await _db(db)
        otro = await base.envios_archivos.find_one(
            {"sha256": sha256}, {"_id": 0, "envio_id": 1})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo chequear duplicados de archivo: {e}")
        return None
    if otro and otro.get("envio_id") and otro["envio_id"] != envio_id:
        return otro["envio_id"]
    return None
