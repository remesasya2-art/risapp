"""
services/firma.py — Firmar un pedido saliente, y verificar uno entrante.

PARA QUE, Y POR QUE ESTA ESCRITO ANTES DE QUE HAGA FALTA

    Todo proveedor bancario o de cambio pide lo mismo: que cada pedido vaya
    firmado con una clave compartida y una marca de tiempo. Esta aplicación ya
    sabe VERIFICAR firmas así —lo hace con los avisos de Mercado Pago y con los
    de NOWPayments— pero nunca tuvo que EMITIR una.

    Está acá, con sus tests, para que el día de la integración sea cambiar de
    dónde sale la clave y no aprender el mecanismo con apuro y con plata real
    del otro lado.

    POR AHORA NO LO LLAMA NADIE, y eso es deliberado. Código sin llamador es
    deuda: si la integración se cae del plan, esto se borra.

LO QUE NO ES

    NO es un adaptador de proveedores. Cada uno arma su cadena a firmar de una
    forma distinta —Mercado Pago usa `id:...;request-id:...;ts:...;`— y
    adivinar la de uno que todavía no publicó su documentación es trabajo que
    se tira. Acá está el esquema MAS COMUN, y `firmar_cadena` deja pasar
    cualquier otro sin reescribir nada.

LAS DOS COSAS QUE CASI TODOS SE SALTAN

    · COMPARAR CON `compare_digest` Y NO CON `==`. Un `==` corta en la primera
      letra distinta, así que tarda distinto según cuánto acertaste, y eso
      alcanza para adivinar una firma byte a byte. `compare_digest` tarda lo
      mismo siempre.

    · LA MARCA DE TIEMPO. Sin ella, una firma válida sirve para siempre: quien
      capture un pedido lo puede repetir mañana y el receptor lo acepta, porque
      la firma sigue siendo correcta. Con ventana, el pedido repetido llega
      viejo y se rechaza.
"""
import hashlib
import hmac
import time

# Cuánto puede tardar un pedido en llegar antes de considerarse repetido.
# Cinco minutos es lo que usan casi todos: aguanta un reloj desfasado y no
# deja una ventana cómoda para repetir un pedido capturado.
VENTANA_SEGUNDOS = 300

CABECERA = "X-Signature"


def cadena_a_firmar(cuerpo: bytes, marca: int) -> bytes:
    """Lo que se firma: la marca de tiempo, un punto, y el cuerpo EXACTO.

    El cuerpo va tal cual sale a la red, sin volver a serializarlo. Firmar el
    diccionario y mandar otro JSON —con las claves en otro orden, o con otros
    espacios— da una firma que no valida del otro lado, y es de los errores más
    difíciles de encontrar porque el código «se ve bien».
    """
    if isinstance(cuerpo, str):
        cuerpo = cuerpo.encode("utf-8")
    return f"{int(marca)}.".encode("utf-8") + (cuerpo or b"")


def firmar_cadena(secreto: str, cadena: bytes) -> str:
    """HMAC-SHA256 en hexadecimal. La pieza mínima, por si el proveedor arma
    la cadena de otra forma: se le pasa la suya y listo."""
    if isinstance(secreto, str):
        secreto = secreto.encode("utf-8")
    return hmac.new(secreto, cadena, hashlib.sha256).hexdigest()


def firmar(secreto: str, cuerpo: bytes, marca: int = None) -> dict:
    """Las cabeceras que hay que mandar. `{"X-Signature": "ts=...,v1=..."}`

    El formato `ts=...,v1=...` es el de Mercado Pago, que esta aplicación ya
    sabe leer. Tener una sola forma en los dos sentidos es lo que hace que un
    test pueda firmar y verificar con el mismo código.
    """
    marca = int(time.time()) if marca is None else int(marca)
    firma = firmar_cadena(secreto, cadena_a_firmar(cuerpo, marca))
    return {CABECERA: f"ts={marca},v1={firma}"}


def _partes(cabecera: str) -> dict:
    return dict(p.split("=", 1) for p in (cabecera or "").split(",") if "=" in p)


def verificar(secreto: str, cuerpo: bytes, cabecera: str, ahora=None) -> bool:
    """Si la firma es de quien dice y llegó a tiempo. Nunca levanta.

    Devuelve `False` ante cualquier cosa rara —cabecera mal armada, marca que
    no es un número, firma ausente—. Un verificador que levanta una excepción
    con una entrada torcida es un verificador que se puede tumbar desde afuera.
    """
    try:
        partes = _partes(cabecera)
        marca, firma = partes.get("ts", ""), partes.get("v1", "")
        if not marca or not firma:
            return False
        marca = int(marca)
        ahora = int(time.time() if ahora is None else ahora)
        # En valor absoluto: una marca del FUTURO también se rechaza. Sin eso,
        # alguien con el reloj adelantado se fabrica una firma que sirve horas.
        if abs(ahora - marca) > VENTANA_SEGUNDOS:
            return False
        esperada = firmar_cadena(secreto, cadena_a_firmar(cuerpo, marca))
        return hmac.compare_digest(esperada, firma)
    except Exception:
        return False
