"""
models/soporte.py — Lo que el cliente ve de sus casos de soporte.

POR QUE HACE FALTA

    La ficha del caso ya salía por una lista de lo permitido (`_DEL_CLIENTE`,
    que ahora vive acá como `LO_QUE_VE_DE_SU_CASO`). La conversación no: cada
    mensaje salía entero, con `{"_id": 0}` como única exclusión. Comprobado
    corriéndolo, al cliente le llegaba el `autor_id` del asesor que le
    contestó —el identificador interno de una cuenta del equipo—, que la
    pantalla no usa y que la ficha del caso ya había decidido no mostrar
    (sale `asignado_a_nombre`, no `asignado_a`).

    Las notas internas ya no llegaban: las corta la consulta. Lo que faltaba
    era que el mensaje que SÍ llega traiga sólo lo que se lee.

DOS CAPAS

    La proyección de la consulta (`LO_QUE_VE_DE_UN_MENSAJE`) no trae de la base
    lo que no se muestra, y el contrato corta lo que se cuele igual si alguien
    ensancha la proyección. Cada capa tiene su test propio, porque dos guardas
    que se tapan entre sí no se sabe si andan
    (tests/test_contratos_de_soporte.py).
"""
from typing import Any, List, Optional

from pydantic import BaseModel, create_model


# Lo que el cliente ve de su caso. LISTA DE LO PERMITIDO, no de lo prohibido, y
# la diferencia no es de estilo: con una lista de lo prohibido, cada campo nuevo
# que se le agregue al caso viaja al cliente hasta que alguien se acuerde de
# agregarlo a la lista, y el que se olvida no avisa. Así se escribió la primera
# vez y ya se colaban `escalado_por_nombre` y el motivo del escalamiento —quién
# de la casa marcó el caso como grave y por qué—.
#
# `asignado_a_nombre` va a propósito: el cliente lee «¿Cómo fue la atención de
# Ana?». `asignado_a` no: el identificador interno no le sirve para nada.
LO_QUE_VE_DE_SU_CASO = (
    "caso_id", "numero", "asunto", "motivo", "estado", "creado_en",
    "actualizado_en", "ultimo_mensaje", "ultimo_mensaje_en", "ultimo_mensaje_de",
    "sin_leer_cliente", "calificacion", "asignado_a_nombre", "cerrado_en",
)

# De cada mensaje, lo que la pantalla del cliente lee
# (components/soporte/CasosDelCliente.jsx) y nada más. Sin `autor_id`: del
# asesor es un identificador interno, y del cliente es el suyo, que ya sabe.
# Sin `interno` ni `caso_id`: el primero siempre vale falso en lo que llega, y
# el segundo es el caso que la pantalla acaba de pedir.
LO_QUE_VE_DE_UN_MENSAJE = {
    "_id": 0, "mensaje_id": 1, "autor": 1, "autor_nombre": 1,
    "texto": 1, "adjunto": 1, "creado_en": 1,
}

# Generado de la misma lista, y no escrito a mano al lado: dos listas de los
# mismos campos terminan distintas, y cuando pasa el campo se pierde en
# silencio. `Any` porque los casos viejos guardan fechas y números con la forma
# que tuvieran; el contrato recorta, no convierte.
CasoQueVeElCliente = create_model(
    "CasoQueVeElCliente",
    **{campo: (Optional[Any], None) for campo in LO_QUE_VE_DE_SU_CASO})

MensajeQueVeElCliente = create_model(
    "MensajeQueVeElCliente",
    **{campo: (Optional[Any], None)
       for campo in LO_QUE_VE_DE_UN_MENSAJE if campo != "_id"})


class MisCasos(BaseModel):
    casos: List[CasoQueVeElCliente]


class MiCaso(BaseModel):
    caso: Optional[CasoQueVeElCliente] = None
    mensajes: List[MensajeQueVeElCliente]


class UnMotivo(BaseModel):
    clave: str
    texto: str


class LosMotivos(BaseModel):
    motivos: List[UnMotivo]
