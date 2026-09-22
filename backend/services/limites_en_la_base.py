"""¿Los contadores de intentos viven en Mongo o en la memoria del proceso?

Es UNA decisión y se lee en UN lugar. Antes vivía adentro de
`routes/security_2fa.py`, y la salud de la aplicación —un servicio— tenía que
importar una ruta para preguntarla, que es la dirección equivocada. Ver el
encabezado de `security_2fa` para el porqué de que arranque apagado.
"""
import os

VARIABLE = "LIMITES_EN_LA_BASE"
_PRENDIDO = ("si", "sí", "1", "true", "on")


def activo() -> bool:
    """Se decide por variable de entorno, no por código. Un valor mal escrito
    no puede prender algo que toca el login: sólo las formas de la lista."""
    return (os.getenv(VARIABLE, "no") or "").strip().lower() in _PRENDIDO
