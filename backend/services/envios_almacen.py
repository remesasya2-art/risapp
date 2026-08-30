"""
services/envios_almacen.py — Donde viven los bytes de las fotos.

POR QUE UN ALMACEN DE OBJETOS Y NO MONGO
    Un comprobante pesa entre 1 y 4 MB y se lee dos veces en su vida: cuando el
    operador lo verifica y cuando alguien reclama. Mongo cobra por ese byte el
    precio del almacenamiento de base de datos —replicado, indexado, respaldado
    todas las noches— para servir un archivo que nunca se consulta por contenido.
    Mil envios por mes son ~3 GB mensuales de fotos: en un almacen de objetos es
    calderilla; adentro de la base es lo que hace que el proximo plan cueste el
    doble.

    R2 habla S3, asi que este modulo sirve igual contra R2, S3, MinIO o
    cualquier cosa que firme igual. No hay nada de Cloudflare aca adentro.

LAS CREDENCIALES VIENEN DEL ENTORNO, NO DE LA BASE
    El resto de la configuracion del modulo se edita desde el panel del super
    administrador, y esta bien: son precios, direcciones, nombres. Estas cuatro
    variables no.

    Una clave de R2 con permiso de escritura sobre el bucket es la capacidad de
    reemplazar cualquier comprobante del historial. Guardarla en Mongo la pone en
    el mismo lugar que el log de auditoria y que los respaldos —mas lectores, y
    menos control, que el original— y ademas la vuelve editable desde una
    pantalla web. Van en variables de entorno, que en Railway se cargan desde su
    panel: no hace falta tocar el repositorio, que es la regla que importa.

    El panel igual muestra el ESTADO (si esta activo, contra que bucket, si las
    credenciales estan cargadas) y tiene un boton para probar la conexion. Lo que
    no muestra nunca es el secreto.

EL TOKEN NO NECESITA PERMISO DE BORRAR
    Este modulo escribe y lee. No borra: no hay una sola llamada a `delete_object`
    en el archivo, a proposito. El token de R2 se emite con Put y Get solamente,
    y asi una falla —o un abuso— de este servicio no puede vaciar el historial de
    comprobantes. Una migracion que escribe mal deja un objeto huerfano, que es
    basura barata; una que borra mal deja un envio sin prueba.

BOTO3 ES SINCRONO
    Cada llamada va a un hilo. Un `put_object` de 4 MB contra un servicio remoto
    adentro del bucle de eventos congela TODO el proceso —las cotizaciones, los
    cobros, la cola del operador— por lo que tarde la red.

    El hilo sale de un pool PROPIO y acotado, no del executor por defecto. El de
    por defecto lo comparte todo el proceso: un bucket lento dejaria sin hilos a
    cualquier otra cosa que quiera uno, y el numero de hilos coincide con
    `max_pool_connections` para que urllib3 no ande abriendo y tirando
    conexiones.

TRES RELOJES, Y NINGUNO ALCANZA SOLO
    `connect_timeout` acota el saludo. `read_timeout` acota **cada operacion de
    socket**, no la transferencia entera: un endpoint que gotea un byte cada
    diez segundos no lo dispara nunca. Y `max_attempts` multiplica los dos.

    Por eso arriba de todo hay un presupuesto de tiempo de pared, con
    `asyncio.wait_for`, y los reintentos de botocore estan en UNO: el plan B de
    este modulo es Mongo, que siempre funciona, asi que reintentar contra un
    bucket que no contesta solo hace esperar mas al usuario para terminar en el
    mismo lugar. El presupuesto de la subida en linea es corto a proposito
    —degradar rapido— y el de la migracion es mas largo, porque ahi no hay nadie
    mirando una rueda.

    `wait_for` libera la peticion pero NO cancela el hilo: por eso el pool es
    acotado y hay un semaforo. Un bucket colgado ocupa hilos hasta que botocore
    corte, y lo unico que se puede garantizar es que no ocupe mas de N.
"""

import asyncio
import functools
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VAR_ENDPOINT = "ENVIOS_R2_ENDPOINT"
VAR_BUCKET = "ENVIOS_R2_BUCKET"
VAR_ACCESS_KEY = "ENVIOS_R2_ACCESS_KEY_ID"
VAR_SECRETO = "ENVIOS_R2_SECRET_ACCESS_KEY"
VAR_PREFIJO = "ENVIOS_R2_PREFIJO"

OBLIGATORIAS = (VAR_ENDPOINT, VAR_BUCKET, VAR_ACCESS_KEY, VAR_SECRETO)

PREFIJO_POR_DEFECTO = "envios"

SEGUNDOS_CONEXION = 4
SEGUNDOS_SOCKET = 15
# UNO. Ver "tres relojes" arriba: el reintento de este modulo es Mongo.
INTENTOS_MAX = 1

# Los presupuestos de pared. El de la subida es corto porque hay un usuario
# esperando y hay un plan B; el de la lectura es mas largo porque no hay plan B
# —los bytes estan alla— y el de la migracion todavia mas porque no hay nadie
# mirando.
SEGUNDOS_SUBIDA = 12
SEGUNDOS_LECTURA = 25

# Hilos propios y conexiones del pool de urllib3: el mismo numero a proposito.
HILOS = 8

# Los componentes de una clave son identificadores que genera este sistema
# (`env_...`, `ast_...`, una extension de la lista blanca). Se validan igual: el
# dia que alguien pase por aca un dato del usuario, la clave se rechaza en vez de
# escribir en `../` de otro prefijo.
_COMPONENTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PREFIJO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$")

CLAVE_DE_PRUEBA = "_prueba/conexion.txt"

_cache = {"firma": None, "cliente": None}
_pool_hilos = None
_turnos = None


def _pool():
    global _pool_hilos
    if _pool_hilos is None:
        _pool_hilos = ThreadPoolExecutor(max_workers=HILOS,
                                         thread_name_prefix="envios-almacen")
    return _pool_hilos


def _semaforo():
    """Acota cuántas llamadas al bucket hay en vuelto a la vez.

    Se crea perezoso: un `asyncio.Semaphore` construido en el import queda atado
    a ningún loop en 3.10+, pero crearlo acá evita depender de esa sutileza.
    """
    global _turnos
    if _turnos is None:
        _turnos = asyncio.Semaphore(HILOS)
    return _turnos


async def _en_hilo(funcion, *args, presupuesto: float):
    """Corre una llamada sincrónica de boto3 fuera del bucle, con techo de tiempo."""
    loop = asyncio.get_running_loop()
    async with _semaforo():
        return await asyncio.wait_for(
            loop.run_in_executor(_pool(), functools.partial(funcion, *args)),
            presupuesto)


def _texto(nombre: str) -> str:
    return (os.environ.get(nombre) or "").strip()


def prefijo() -> str:
    crudo = _texto(VAR_PREFIJO).strip("/") or PREFIJO_POR_DEFECTO
    if ".." in crudo or not _PREFIJO.match(crudo):
        logger.error(
            f"envios: {VAR_PREFIJO}={crudo!r} no es un prefijo valido; se usa "
            f"{PREFIJO_POR_DEFECTO!r}")
        return PREFIJO_POR_DEFECTO
    return crudo


def faltantes() -> list[str]:
    """Las variables obligatorias que no estan cargadas."""
    return [n for n in OBLIGATORIAS if not _texto(n)]


def _endpoint_valido(endpoint: str) -> bool:
    """https y con host. Un endpoint en http manda la firma en claro.

    Falla CERRADO: sin endpoint valido el modulo se declara no configurado y los
    bytes se quedan en Mongo, que funciona. La alternativa —seguir igual— es
    filtrar la credencial del bucket en la primera peticion.
    """
    try:
        partes = urlparse(endpoint)
    except Exception:                                         # pragma: no cover
        return False
    return partes.scheme == "https" and bool(partes.hostname)


def configurado() -> bool:
    """True si hay a donde escribir. Si no, los bytes viven en Mongo."""
    if faltantes():
        return False
    if not _endpoint_valido(_texto(VAR_ENDPOINT)):
        logger.error(
            f"envios: {VAR_ENDPOINT} tiene que ser una URL https con host; el "
            f"almacen de objetos queda desactivado")
        return False
    return True


def _construir_cliente(endpoint: str, access_key: str, secreto: str):
    """Aislado para que los tests lo reemplacen sin instalar boto3."""
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secreto,
        # R2 no tiene regiones; el firmante igual exige uno.
        region_name="auto",
        config=Config(connect_timeout=SEGUNDOS_CONEXION,
                      read_timeout=SEGUNDOS_SOCKET,
                      max_pool_connections=HILOS,
                      retries={"max_attempts": INTENTOS_MAX},
                      signature_version="s3v4"))


def _cliente():
    """El cliente, cacheado. Se reconstruye si cambio alguna credencial.

    Construir un cliente de boto3 arma el firmante y resuelve el endpoint; a una
    foto por peticion, hacerlo cada vez es caro para nada. La firma del cache son
    las credenciales mismas, asi que rotar una en Railway lo invalida sin que
    haya que acordarse de invalidarlo.
    """
    endpoint = _texto(VAR_ENDPOINT)
    access_key = _texto(VAR_ACCESS_KEY)
    secreto = _texto(VAR_SECRETO)
    firma = (endpoint, access_key, secreto)
    if _cache["firma"] == firma and _cache["cliente"] is not None:
        return _cache["cliente"]
    cliente = _construir_cliente(endpoint, access_key, secreto)
    _cache["firma"] = firma
    _cache["cliente"] = cliente
    return cliente


def olvidar_cliente():
    """Tira el cliente cacheado. La usan los tests.

    En producción no hace falta llamarla: la firma del caché son las credenciales
    mismas, así que rotarlas en Railway ya lo invalida.
    """
    _cache["firma"] = None
    _cache["cliente"] = None


def bucket_actual() -> str | None:
    """El bucket configurado AHORA. Se guarda en cada ficha al escribir.

    Una ficha que solo dice `clave` tiene media dirección: el resto vive en una
    variable de entorno que alguien puede cambiar. El día que se apunte a otro
    bucket —uno definitivo después de probar, uno por región, un endpoint de
    cuenta nuevo— todo lo ya migrado se vuelve ilegible y los bytes de Mongo ya
    se borraron. La ficha guarda la dirección completa.
    """
    return _texto(VAR_BUCKET) or None


def clave_de(envio_id: str, asset_id: str, extension: str) -> str:
    """`<prefijo>/<envio>/<asset>.<ext>`. Lanza ValueError si algo no valida."""
    for nombre, parte in (("envio_id", envio_id), ("asset_id", asset_id),
                          ("extension", extension)):
        if not parte or not _COMPONENTE.match(str(parte)):
            raise ValueError(f"{nombre} no sirve como componente de clave: {parte!r}")
    return f"{prefijo()}/{envio_id}/{asset_id}.{extension}"


def _leer_objeto(cliente, bucket: str, clave: str, tope: int) -> bytes:
    """Corre en un hilo. Lee un byte de mas para poder detectar el exceso."""
    objeto = cliente.get_object(Bucket=bucket, Key=clave)
    cuerpo = objeto["Body"]
    try:
        return cuerpo.read(tope + 1)
    finally:
        try:
            cuerpo.close()
        except Exception:                                     # pragma: no cover
            pass


# Los codigos de S3 que significan "ese objeto no esta, y no va a estar por
# esperar". Todo lo demas se trata como caida transitoria.
_CODIGOS_AUSENTE = ("NoSuchKey", "NoSuchBucket", "404")


def _clasificar(e) -> str:
    """"ausente" si el objeto no existe; "almacen" para cualquier otra falla.

    La diferencia termina en el mensaje que ve una persona. Decirle "probá de
    nuevo en un minuto" a alguien cuyo objeto no existe es mandarlo a reintentar
    para siempre, y el módulo ya tiene escrita esa regla en otro lado.
    """
    respuesta = getattr(e, "response", None)
    if isinstance(respuesta, dict):
        codigo = str((respuesta.get("Error") or {}).get("Code") or "")
        if codigo in _CODIGOS_AUSENTE:
            return "ausente"
    return "almacen"


async def poner(clave: str, datos: bytes, content_type: str, *,
                presupuesto: float = SEGUNDOS_SUBIDA) -> bool:
    """Escribe el objeto. True si quedo escrito; False si no, sin lanzar.

    No lanza a proposito: quien llama tiene un plan B (Mongo) y lo unico que
    necesita saber es si hace falta usarlo.
    """
    if not configurado():
        return False
    try:
        cliente = _cliente()
        await _en_hilo(
            functools.partial(cliente.put_object, Bucket=_texto(VAR_BUCKET),
                              Key=clave, Body=datos, ContentType=content_type),
            presupuesto=presupuesto)
        return True
    except Exception as e:
        logger.error(f"envios: no se pudo escribir {clave} en el almacen: {e}")
        return False


async def traer(clave: str, *, tope: int, bucket: str = None,
                presupuesto: float = SEGUNDOS_LECTURA) -> tuple[bytes | None, str | None]:
    """(bytes, motivo). El motivo es None cuando salio bien.

    `tope` no es una cortesia: el objeto lo devuelve un servicio remoto, y leerlo
    entero sin limite convierte un bucket mal escrito —o cualquier cosa que
    alguien haya subido con la misma clave— en memoria del proceso. Se lee un
    byte de mas y se rechaza el que se pasa.

    `bucket` viene de la ficha: es la mitad de la direccion que no puede quedar
    en una variable de entorno mutable.
    """
    if not configurado():
        return None, "almacen"
    if not clave:
        return None, "ausente"
    destino = bucket or _texto(VAR_BUCKET)
    if bucket and bucket != _texto(VAR_BUCKET):
        logger.warning(
            f"envios: {clave} vive en el bucket {bucket!r} y la configuracion "
            f"actual apunta a {_texto(VAR_BUCKET)!r}; se lee del de la ficha")
    try:
        cliente = _cliente()
        datos = await _en_hilo(_leer_objeto, cliente, destino, clave, tope,
                               presupuesto=presupuesto)
    except Exception as e:
        motivo = _clasificar(e)
        # `error` y no `warning`: si no se puede leer el comprobante, el operador
        # no puede verificar el peso, y sin peso verificado no hay cobro. Una
        # caida de esto frena la plata del modulo.
        logger.error(f"envios: no se pudo leer {clave} del almacen ({motivo}): {e}")
        return None, motivo
    if len(datos) > tope:
        logger.error(
            f"envios: el objeto {clave} supera el tope de {tope} bytes; no se sirve")
        return None, "grande"
    return datos, None


async def probar() -> dict:
    """Escribe y vuelve a leer un objeto minusculo. Para el boton del panel.

    Sirve para descubrir que la credencial esta mal ANTES de migrar tres mil
    fotos, no despues. Usa siempre la misma clave para no ir dejando basura: se
    sobrescribe.
    """
    if not configurado():
        return {"ok": False, "detalle": "El almacén de objetos no está configurado.",
                "faltantes": faltantes()}
    clave = f"{prefijo()}/{CLAVE_DE_PRUEBA}"
    testigo = b"ok"
    if not await poner(clave, testigo, "text/plain"):
        return {"ok": False,
                "detalle": "No se pudo escribir en el bucket. Revisá la clave, el "
                           "secreto y que el token tenga permiso de escritura."}
    vuelta, _ = await traer(clave, tope=len(testigo) + 16)
    if vuelta != testigo:
        return {"ok": False,
                "detalle": "Se escribió pero no se pudo leer de vuelta. Revisá que el "
                           "token también tenga permiso de lectura."}
    return {"ok": True, "detalle": "El bucket responde: escribe y lee."}


def estado() -> dict:
    """Lo que el panel puede mostrar. Nunca la clave ni el secreto.

    El `access_key_id` tampoco: es la mitad de una credencial y no le dice nada
    util a quien mira la pantalla. Lo que se contesta es "¿esta cargada?".
    """
    endpoint = _texto(VAR_ENDPOINT)
    return {
        "activo": configurado(),
        # `_endpoint_valido` y no `if endpoint`: `urlparse` LANZA con una URL mal
        # formada (un `[` suelto y es "Invalid IPv6 URL"), y esta es justo la
        # pantalla a la que entra el admin cuando la configuracion esta mal. Que
        # reviente ahi es dejarlo sin el unico diagnostico que tiene.
        "endpoint_host": (urlparse(endpoint).hostname
                          if _endpoint_valido(endpoint) else None),
        "endpoint_https": _endpoint_valido(endpoint) if endpoint else None,
        "hilos": HILOS,
        "bucket": _texto(VAR_BUCKET) or None,
        "prefijo": prefijo(),
        "credenciales_cargadas": bool(_texto(VAR_ACCESS_KEY) and _texto(VAR_SECRETO)),
        "variables_faltantes": faltantes(),
    }
