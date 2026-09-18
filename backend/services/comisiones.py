"""
services/comisiones.py — Cuánto te queda a vos en cada operación.

QUE PASABA

    La ganancia estaba metida en la tasa —se le ofrece al cliente una peor que
    la que conseguís vos— y NO QUEDABA ESCRITA EN NINGUN LADO. La operación
    guardaba `rate`, la tasa que vio el cliente, y nada más: ni cuánto costó,
    ni cuánto quedó.

    Eso se puede calcular después con un informe, y de hecho hay un motor
    contable que lo hace, pero con dos límites: lo carga un super
    administrador a mano, una fila por operación de arbitraje, y no sabe nada
    de cada envío concreto.

    Y sobre todo: LO QUE NO SE REGISTRA HOY NO SE RECUPERA DESPUES. El día que
    se conecte un proveedor y haya con qué comparar, la historia anterior no
    existe. Por eso esto se escribe ahora aunque el proveedor no esté.

COMO SE CALCULA, Y POR QUE ASI

    Con las dos tasas de la MISMA operación, nunca con un porcentaje nominal:

        salida        = monto_cliente × tasa_cliente      (lo que recibe el destino)
        costo_en_ris  = salida ÷ tasa_costo               (lo que te costó a vos)
        comisión      = monto_cliente − costo_en_ris

    Guardar el porcentaje configurado en vez de la resta de arriba es el error
    que hace que la contabilidad no cuadre desde el primer día, y es fácil de
    cometer. Con un 1 % nominal, una tasa de 5,45 y el redondeo a 5,50 que
    pide la pantalla, lo que de verdad se cobra es 0,917 %. Si el sistema
    anota «1 %», anota algo que no pasó.

    Todo en `Decimal`. Con `float`, 181.818181... × 5.45 no da 990,91.

DE FABRICA NO HACE NADA, Y ES A PROPOSITO

    El ajuste `comision_registrar` viene en 0. Con eso, esto no anota nada y
    no rechaza nada: la aplicación se comporta exactamente igual que antes.

    Se prende desde el panel, y recién ahí entra en juego la guarda: sin tasa
    de costo cargada, la operación NO se procesa. Es el mismo camino que el
    piso de peticiones y la política de contenido —primero mirar, después
    cortar— y por el mismo motivo: una guarda cerrada que se despliega prendida
    frena la plata de todo el mundo en el minuto cero si el número no estaba
    cargado.

LOS DOS DECIMALES DE LA TASA DE COSTO

    El catálogo de configuración guarda plata con dos decimales, y la tasa de
    costo va ahí. Para las tasas que esta aplicación tiene hoy —bolívares por
    real, números grandes— dos decimales sobran.

    NO ALCANZARIAN para una tasa cercana a uno, como el precio de un dólar
    cripto en reales: ahí el segundo decimal vale casi dos décimas de por
    ciento, que sobre un margen del uno por ciento es un error enorme. El día
    que aparezca una tasa así, el catálogo necesita un tipo con más decimales,
    y esto hay que revisarlo. Queda escrito para que no se descubra tarde.
"""
import logging
from decimal import Decimal, DivisionByZero, InvalidOperation

from services import configuracion
from services.money import quantize_money, to_decimal128

logger = logging.getLogger(__name__)

# El ajuste que la prende, y los de la tasa de costo de cada vía.
AJUSTE_PRENDIDA = "comision_registrar"

# (vía) -> clave del ajuste con su tasa de costo.
COSTO_DE_LA_VIA = {
    "ris_to_ves": "costo_ris_to_ves",
}


async def esta_prendida(db) -> bool:
    """Si el registro de comisiones está activo. De fábrica, no."""
    try:
        return bool(await configuracion.leer(db, AJUSTE_PRENDIDA))
    except Exception as e:                                # pragma: no cover
        # Ante la duda, apagada: que un fallo leyendo la configuración frene
        # los envíos de todo el mundo sería mucho peor que no anotar un rato.
        logger.warning("comisiones: no se pudo leer si está prendida: %s", e)
        return False


async def tasa_de_costo(db, via: str):
    """La tasa que a VOS te cuesta esa vía, o None si no hay.

    ESTA ES LA COSTURA. Hoy contesta leyendo el panel; el día que haya un
    proveedor con API, esta función pregunta allá y NADA MAS CAMBIA. Por eso
    es una función y no una lectura de configuración repartida por las rutas:
    el objetivo de todo este módulo es que la integración toque un archivo.
    """
    clave = COSTO_DE_LA_VIA.get(via)
    if not clave:
        return None
    try:
        valor = await configuracion.leer(db, clave)
    except Exception as e:                                # pragma: no cover
        logger.warning("comisiones: no se pudo leer %s: %s", clave, e)
        return None
    if valor is None:
        return None
    costo = quantize_money(valor)
    # Cero no es «gratis»: es «no lo cargaron». Y dividir por él revienta.
    return costo if costo > 0 else None


def calcular(*, monto_cliente, tasa_cliente, tasa_costo):
    """La comisión de UNA operación, en la moneda que puso el cliente.

    Devuelve `None` si no se puede calcular —falta una tasa, o alguna es cero
    o negativa—. Nunca levanta: esto corre en el camino de la plata.
    """
    try:
        monto = quantize_money(monto_cliente)
        cliente = quantize_money(tasa_cliente)
        costo = quantize_money(tasa_costo)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if monto <= 0 or cliente <= 0 or costo <= 0:
        return None
    try:
        salida = monto * cliente
        costo_en_la_moneda_del_cliente = salida / costo
    except (DivisionByZero, InvalidOperation):            # pragma: no cover
        return None
    return quantize_money(monto - costo_en_la_moneda_del_cliente)


class FaltaLaTasaDeCosto(Exception):
    """Está prendido el registro y no hay tasa de costo cargada para la vía.

    Cerrado por omisión: sin saber cuánto cuesta, la operación no se procesa.
    Es la misma decisión que ya toma la tasa de cambio —«sin tasa válida no se
    procesa»—, y por el mismo motivo: una operación cuyo costo nadie conoce es
    una operación cuya ganancia nadie va a poder calcular nunca.
    """


async def campos_de(db, *, via: str, monto_cliente, tasa_cliente) -> dict:
    """Lo que hay que guardar en la operación. Listo para el documento.

    Devuelve `{}` cuando el registro está apagado, que es lo de fábrica: así
    la operación queda EXACTAMENTE igual que antes de este módulo.

    Levanta `FaltaLaTasaDeCosto` cuando está prendido y falta el número.
    """
    if not await esta_prendida(db):
        return {}
    costo = await tasa_de_costo(db, via)
    if costo is None:
        raise FaltaLaTasaDeCosto(via)
    comision = calcular(monto_cliente=monto_cliente, tasa_cliente=tasa_cliente,
                        tasa_costo=costo)
    if comision is None:
        raise FaltaLaTasaDeCosto(via)
    return {
        "tasa_cliente": to_decimal128(tasa_cliente),
        "tasa_costo": to_decimal128(costo),
        "comision": to_decimal128(comision),
        # El identificador que le dará el proveedor el día que haya uno. Va
        # vacío desde hoy a propósito: agregar un campo a una colección con un
        # año de operaciones encima es una migración; agregarlo ahora es esto.
        "proveedor_ref": None,
    }
