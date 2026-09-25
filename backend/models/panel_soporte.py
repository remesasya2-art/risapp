"""
models/panel_soporte.py — Lo que el panel ve de la mesa de ayuda: la bandeja,
el caso con su conversación, los pedidos entre áreas, las respuestas rápidas,
y lo que contesta cada acción del asesor.

LA BANDEJA Y EL CASO SALIAN ENTEROS

    Cada caso, cada mensaje y cada pedido salían tal como están en la base,
    con `{"_id": 0}` como única exclusión. Es información del equipo, así que
    no había un secreto a la vista; lo que había era la puerta abierta: el día
    que alguien le agregue al caso un campo interno, sale a la pantalla sin
    que nadie lo decida. Así se le colaron al cliente, la primera vez, quién
    escaló su caso y por qué (ver `models/soporte.py`).

    El contrato deja lo que la consola lee (`MesaDeAyuda.jsx` y
    `utils/soporte.js`) y lo que identifica y fecha cada cosa. Afuera quedan
    los identificadores internos de quién escaló o cerró —la pantalla muestra
    el nombre— y `origen_chat`, que sólo sirve para que la migración no
    duplique casos.

`asignado_a` SI va, aunque sea un identificador

    La consola decide con él si el caso es de quien lo mira: tomar, soltar y
    responder se habilitan comparándolo con el usuario de la sesión
    (`accionesDelAsesor`). Sin él, ningún asesor podría contestarle a nadie.

Un test (`tests/test_contratos_de_la_mesa_de_ayuda.py`) compara lo que la
consola lee con cada contrato, y recorre las rutas con un caso de ejemplo.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── El caso ───────────────────────────────────────────────────────────────

CalificacionDelCaso = _simple("CalificacionDelCaso", ("estrellas", "comentario", "en"))

CasoQueVeElAsesor = _simple("CasoQueVeElAsesor", (
    "caso_id", "numero", "user_id", "user_name", "user_email", "motivo", "asunto", "estado",
    "prioridad", "area", "asignado_a", "asignado_a_nombre", "asignado_en",
    "escalado", "escalado_motivo", "escalado_por_nombre", "escalado_en",
    "creado_en", "actualizado_en", "ultimo_mensaje", "ultimo_mensaje_en", "ultimo_mensaje_de",
    "primera_respuesta_en", "sin_leer_asesor", "sin_leer_cliente",
    "cerrado_en", "cerrado_por_nombre",
    # Lo que calcula la ruta al servirlo: el color, y cuánto hace que espera.
    "semaforo", "minutos_esperando", "minutos_sin_respuesta"),
    calificacion=(Optional[CalificacionDelCaso], None))


class BandejaDelAsesor(BaseModel):
    casos: List[CasoQueVeElAsesor] = []


# Del mensaje, todo menos `caso_id`, que es el caso que la consola acaba de
# pedir. `autor_id` va aunque la pantalla muestre el nombre: dos asesores
# pueden llamarse igual, y quién escribió cada cosa es lo que el equipo tiene
# que poder saber (`test_EL_PANEL_DEL_EQUIPO_SIGUE_VIENDO_EL_MENSAJE_ENTERO`).
# Al cliente, en cambio, no le llega (`models/soporte.py`).
MensajeQueVeElAsesor = _simple("MensajeQueVeElAsesor", (
    "mensaje_id", "autor", "autor_id", "autor_nombre", "interno", "texto", "adjunto", "creado_en"))

PedidoAUnArea = _simple("PedidoAUnArea", (
    "pedido_id", "caso_id", "caso_numero", "area", "detalle", "estado",
    "pedido_por_nombre", "creado_en", "respuesta", "respondido_por_nombre", "respondido_en"))

# La ficha del cliente al lado de la conversación. La consulta ya es una lista
# de lo permitido (`routes/soporte.ver_caso`); el contrato repite la misma.
ClienteDelCaso = _simple("ClienteDelCaso", (
    "user_id", "name", "email", "phone", "balance_ris", "verification_status", "created_at",
    "role", "is_active"))

OperacionDelCliente = _simple("OperacionDelCliente", (
    "transaction_id", "type", "amount", "status", "created_at", "currency"))


class CasoCompleto(BaseModel):
    caso: Optional[CasoQueVeElAsesor] = None
    mensajes: List[MensajeQueVeElAsesor] = []
    pedidos: List[PedidoAUnArea] = []
    cliente: Optional[ClienteDelCaso] = None
    operaciones: List[OperacionDelCliente] = []
    casos_previos: Escalar = None


class PedidosDeMiArea(BaseModel):
    pedidos: List[PedidoAUnArea] = []
    areas: List[Escalar] = []


# ── Los catálogos ─────────────────────────────────────────────────────────

AreaDeSoporte = _simple("AreaDeSoporte", ("clave", "nombre"))


class AreasDeSoporte(BaseModel):
    areas: List[AreaDeSoporte] = []


Asesor = _simple("Asesor", ("user_id", "nombre", "rol", "area", "cargo"))


class Asesores(BaseModel):
    asesores: List[Asesor] = []


# Sin `created_by`: el identificador de quien la escribió. La lista muestra el
# texto, y el nombre alcanza para saber de quién es.
RespuestaRapida = _simple("RespuestaRapida", ("qr_id", "text", "created_by_name", "created_at"))
RespuestasRapidas = List[RespuestaRapida]
RespuestaRapidaCreada = _simple("RespuestaRapidaCreada", ("success", "error", "qr_id", "text"))

# ── Lo que contesta cada acción ───────────────────────────────────────────

AccionDeSoporte = _simple("AccionDeSoporte", ("success",))
CasoTomado = _simple("CasoTomado", ("success", "ya_era_mio", "asignado_a_nombre"))
MensajeDelAsesor = _simple("MensajeDelAsesor", ("success", "interno"))
EstadoDelCaso = _simple("EstadoDelCaso", ("success", "estado"))
CasoTransferido = _simple("CasoTransferido", ("success", "area", "asignado_a"))
PedidoHecho = _simple("PedidoHecho", ("success",), pedido=(Optional[PedidoAUnArea], None))
