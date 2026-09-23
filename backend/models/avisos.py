"""
models/avisos.py — Lo que la persona ve de sus avisos (la campana).

`/notifications` devolvía cada aviso entero, con `{"_id": 0}` como única
exclusión. Hoy eso es `user_id` y `ambito` además de lo que la campana lee;
mañana es cualquier campo que alguien le agregue a `create_notification`.
Dos capas, como en el resto de los contratos: la consulta pide sólo lo que
leen las pantallas (`NotificationBell.jsx`, `CampanaDelEquipo.jsx`,
`pages/Notifications.jsx`) y el contrato corta lo que se cuele.

`data` va entero a propósito: lo arma cada aviso para que la pantalla sepa a
dónde llevar al tocarlo (la orden, la pestaña del panel), y sus claves cambian
según el tipo.
"""
from typing import Any, Optional

from pydantic import BaseModel

from models.escalar import Escalar

LO_QUE_VE_DE_UN_AVISO = {
    "_id": 0, "notification_id": 1, "title": 1, "message": 1, "type": 1,
    "data": 1, "read": 1, "created_at": 1,
}


class UnAviso(BaseModel):
    notification_id: Escalar = None
    title: Escalar = None
    message: Escalar = None
    type: Escalar = None
    data: Optional[Any] = None
    read: Escalar = None
    created_at: Escalar = None


class AvisosSinLeer(BaseModel):
    unread_count: Escalar = None
