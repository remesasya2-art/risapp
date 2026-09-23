"""
models/btc_salida.py — Lo que sale de las rutas de Bitcoin Lightning.

LA LISTA DE ORDENES PENDIENTES DEL PANEL

    `/btc/operador/pendientes` devolvía las órdenes enteras: la consulta sólo
    sacaba `_id`. Así viajaban el `precio_con_margen` y el `precio_btc_usado`
    —juntos, la ganancia de cada orden—, el `payment_hash` y el `memo` del
    pago, y el `user_id` del cliente. La pestaña del panel lee el número de
    orden, los montos, los sats, el beneficiario y la fecha; nada más.

    Dos capas, como en el resto: la consulta pide sólo lo permitido
    (`LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN`) y el contrato corta lo que se cuele.
"""
from typing import List, Optional

from pydantic import BaseModel

from models.escalar import Escalar
from models.movimientos import BeneficiarioDeLaOperacion


LO_QUE_VE_EL_PANEL_DE_UNA_ORDEN = {
    "_id": 0, "remesa_id": 1, "estado": 1, "usd_cliente": 1, "ves_recibe": 1,
    "sats": 1, "beneficiario_data": 1, "creado_en": 1, "pagado_en": 1,
}


class OrdenBtcParaElPanel(BaseModel):
    remesa_id: Escalar = None
    estado: Escalar = None
    usd_cliente: Escalar = None
    ves_recibe: Escalar = None
    sats: Escalar = None
    # El beneficiario con la misma lista que el historial del cliente: las
    # órdenes viejas lo guardaron como copia entera del documento.
    beneficiario_data: Optional[BeneficiarioDeLaOperacion] = None
    creado_en: Escalar = None
    pagado_en: Escalar = None


class OrdenesBtcPendientes(BaseModel):
    # Las dos listas son la misma: `remesas` quedó por compatibilidad con una
    # versión vieja del panel, que hoy lee `ordenes`.
    ordenes: List[OrdenBtcParaElPanel] = []
    remesas: List[OrdenBtcParaElPanel] = []
    total: Escalar = None
