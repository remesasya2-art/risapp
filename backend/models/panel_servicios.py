"""
models/panel_servicios.py — Lo que el panel ve de los servicios: cuál está
prendido y qué significa cada estado. Ver services/servicios.py.

Es un catálogo armado a mano en el servicio, no un documento de la base: el
contrato fija sus campos para que un campo nuevo no salga sin que alguien lo
decida.
"""
from typing import List

from pydantic import BaseModel

from models.escalar import Escalar


class EstadoDeUnServicio(BaseModel):
    valor: Escalar = None
    nombre: Escalar = None
    detalle: Escalar = None


class UnServicio(BaseModel):
    servicio: Escalar = None
    nombre: Escalar = None
    descripcion: Escalar = None
    llave: Escalar = None
    valor: Escalar = None
    estado: Escalar = None
    encendido: Escalar = None
    estados: List[EstadoDeUnServicio] = []


class LosServicios(BaseModel):
    servicios: List[UnServicio] = []
