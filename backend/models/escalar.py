"""
models/escalar.py — Un valor simple, para los contratos de salida.

`Any` a secas deja pasar CUALQUIER cosa, sub-documentos incluidos, y así un
contrato no corta nada. Lo encontró su propio test en envíos: con la función
de la lista devolviendo de más, `destino.destinatario` —que la función
convierte en el nombre— salía como el documento entero de quien recibe, con
su cédula y su teléfono.

`Escalar` acepta texto, número, fecha o booleano de cualquier forma —un
documento viejo con un número donde otro tiene un texto no puede dar 500—,
pero un diccionario o una lista se muestra vacío en vez de mostrarse de más:
si llega uno a un campo simple, es un error de quien armó la respuesta.

Vive acá, y no en uno de los contratos, porque lo usan varios.
"""
from typing import Annotated, Any, Optional

from bson.decimal128 import Decimal128
from pydantic import BeforeValidator

from services.json_de_mongo import _a_float


def _sin_estructura(valor):
    """Un valor suelto pasa; un documento o una lista, no.

    LA PLATA DE LA BASE SE CONVIERTE ACA, Y NO ES UN DETALLE

        Con contrato, la respuesta la arma el modelo, NO el traductor de
        FastAPI: la red de `services/json_de_mongo.py` —que le enseña
        `Decimal128` a ese traductor— no llega. Un monto crudo de la base en
        un campo de un contrato daba 500, comprobado: la misma ruta, sin
        contrato, contestaba el número. O sea que poner un contrato podía
        voltear una pantalla que andaba.

        Se convierte con la misma función de la red, sin redondear (ver el
        porqué allá: redondear rompe la cripto).
    """
    if isinstance(valor, Decimal128):
        return _a_float(valor)
    return None if isinstance(valor, (dict, list, tuple, set)) else valor


Escalar = Annotated[Optional[Any], BeforeValidator(_sin_estructura)]
