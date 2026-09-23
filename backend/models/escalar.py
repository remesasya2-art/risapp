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

from pydantic import BeforeValidator


def _sin_estructura(valor):
    """Un valor suelto pasa; un documento o una lista, no."""
    return None if isinstance(valor, (dict, list, tuple, set)) else valor


Escalar = Annotated[Optional[Any], BeforeValidator(_sin_estructura)]
