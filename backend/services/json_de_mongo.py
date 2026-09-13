"""
services/json_de_mongo.py — Que una respuesta con plata adentro no se caiga.

EL PROBLEMA, CON EL ERROR TEXTUAL

    La plata de este proyecto se guarda en Mongo como `Decimal128`. El traductor
    a JSON de FastAPI no conoce ese tipo: cuando se le cruza uno, intenta
    recorrerlo como si fuera una lista, después mirarle los atributos, y termina
    tirando un 500:

        ValueError: [TypeError("'Decimal128' object is not iterable"),
                     TypeError('vars() argument must have __dict__ attribute')]

    O sea que CUALQUIER ruta que devuelva un documento tal como sale de la base
    se cae en cuanto ese documento tenga un saldo adentro.

    Eso le pasó a `GET /api/admin/users`, y la lista de usuarios del panel
    estuvo caída desde el 3 de septiembre — el día en que el registro empezó a
    guardar `balance_ris` con este tipo. No fallaba para las cuentas viejas, que
    tenían un número común, así que dependía de a quién le tocara mirar.

POR QUE UNA RED Y NO UN ARREGLO POR RUTA

    Porque ya se arregló una vez a mano. En `/auth/me` se convierten los saldos
    uno por uno, y ese arreglo no se contagió al resto.

    Al buscar cuántas rutas tenían el mismo problema aparecieron TREINTA Y OCHO
    funciones que devuelven documentos leídos de la base. Arreglarlas a mano es
    treinta y ocho oportunidades de olvidarse, más todas las que se escriban de
    acá en adelante. El defecto no es de ninguna ruta en particular: es que el
    traductor no conoce un tipo que este proyecto usa en todos lados.

    Se le enseña una vez.

QUE HACE Y QUE NO

    Convierte `Decimal128` a `float` al serializar. Nada más.

    NO REDONDEA, y eso es deliberado: `to_float` redondea a dos decimales, que
    está bien para reales y es destructivo para cripto —un saldo de 0,00123456
    BTC saldría como 0,00—. Un cero donde hay plata es peor que el error 500,
    porque el 500 se ve y el cero se cree. Lo guardado ya viene redondeado a lo
    que corresponde desde que se escribió.

    Tampoco toca fechas, `ObjectId` ni nada más. Sólo el tipo que rompe.

EL RIESGO DE ESTO, DICHO DE FRENTE

    `encoders_by_class_tuples` es una tabla INTERNA de FastAPI, no una puerta
    documentada. El día que FastAPI la mueva o la renombre, esta red deja de
    estar puesta — y en silencio, que es lo peor que puede pasarle a una red.

    Por eso hay una prueba que comprueba el COMPORTAMIENTO y no la tabla:
    `tests/test_la_plata_viaja_en_json.py` serializa un `Decimal128` de verdad.
    Si FastAPI cambia por dentro, esa prueba se pone roja al actualizar la
    librería, en el momento en que se puede arreglar barato, y no en producción.
"""
import logging

from bson.decimal128 import Decimal128
from fastapi import encoders

logger = logging.getLogger(__name__)

TABLA = "encoders_by_class_tuples"


def _a_float(valor: Decimal128) -> float:
    """Sin redondear. Ver el comentario de arriba: redondear rompe la cripto."""
    return float(valor.to_decimal())


def ya_esta_puesta() -> bool:
    """¿El traductor ya sabe qué hacer con `Decimal128`?"""
    tabla = getattr(encoders, TABLA, None)
    if not isinstance(tabla, dict):
        return False
    return any(Decimal128 in clases for clases in tabla.values())


def ensenarle_decimal128_a_fastapi() -> bool:
    """Pone la red. Devuelve si quedó puesta.

    LLAMARLA DOS VECES NO HACE DAÑO, Y NO HAY NINGUNA COMPROBACION QUE LO EVITE

        La tabla se indexa por la FUNCION que convierte, y `_a_float` es
        siempre el mismo objeto: escribirla dos veces deja una sola entrada.

        La primera versión traía además un `if ya_esta_puesta(): return`. Al
        romperlo a propósito no se puso roja ninguna prueba, porque no hacía
        nada. Se fue. Una guarda que no se puede poner en rojo es una guarda de
        la que nadie sabe si anda — y este proyecto ya pagó eso una vez.

    NO LEVANTA SI NO PUEDE. Una aplicación que no arranca es peor que una
    aplicación con una ruta caída; es la misma regla que sigue el cofre. Se
    grita en los registros, que es donde alguien lo va a ver.
    """
    tabla = getattr(encoders, TABLA, None)
    if not isinstance(tabla, dict):
        logger.error(
            "json_de_mongo: FastAPI ya no tiene «%s». La plata guardada como "
            "Decimal128 va a hacer fallar con 500 a toda ruta que devuelva un "
            "documento de la base. Ver services/json_de_mongo.py.", TABLA)
        return False

    tabla[_a_float] = (Decimal128,)
    logger.info("json_de_mongo: el traductor a JSON ya entiende Decimal128.")
    return True
