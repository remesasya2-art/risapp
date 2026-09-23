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


# ══════════════════════════════════════════════════════════════════════════
# Las rutas del cliente
# ══════════════════════════════════════════════════════════════════════════
#
# Ya armaban la respuesta campo por campo, o con una proyección de lo
# permitido: en pantalla no cambia nada. El contrato es la segunda capa, y un
# test (`tests/test_contratos_de_dinero_en_transito.py`) compara las claves
# que devuelve cada ruta con su contrato, para que ninguno se coma un campo.

class PrecioBtc(BaseModel):
    precio_btc: Escalar = None
    tasa_btc_ves: Escalar = None
    disponible: Escalar = None
    updated_at: Escalar = None
    tasa_actualizada_en: Escalar = None


class LimiteDiarioBtc(BaseModel):
    limite_diario_usd: Escalar = None
    enviado_hoy_usd: Escalar = None
    disponible_usd: Escalar = None


class MiRemesaEnCurso(BaseModel):
    remesa_id: Escalar = None
    estado: Escalar = None
    sats: Escalar = None
    usd_cliente: Escalar = None
    ves_recibe: Escalar = None
    btc_pagar: Escalar = None
    payment_request: Escalar = None
    beneficiario_data: Optional[BeneficiarioDeLaOperacion] = None
    creado_en: Escalar = None
    expira_en: Escalar = None


class MiRemesaActiva(BaseModel):
    activa: Escalar = None
    remesa: Optional[MiRemesaEnCurso] = None


class EstadoDeMiRemesa(BaseModel):
    remesa_id: Escalar = None
    estado: Escalar = None
    sats: Escalar = None
    usd_cliente: Escalar = None
    ves_recibe: Escalar = None
    creado_en: Escalar = None
    expira_en: Escalar = None


class MiBilleteraBtc(BaseModel):
    saldo: Escalar = None
    moneda: Escalar = None
    user_id: Escalar = None          # el del propio cliente, que ya lo sabe
    actualizado_en: Escalar = None


class UnaRemesaDeMiHistorial(BaseModel):
    remesa_id: Escalar = None
    estado: Escalar = None
    sats: Escalar = None
    usd_cliente: Escalar = None
    ves_recibe: Escalar = None
    tasa_ves: Escalar = None
    creado_en: Escalar = None
    pagado_en: Escalar = None
    beneficiario_data: Optional[BeneficiarioDeLaOperacion] = None


class MiHistorialBtc(BaseModel):
    remesas: List[UnaRemesaDeMiHistorial] = []
    total: Escalar = None
