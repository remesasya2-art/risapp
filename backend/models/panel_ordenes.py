"""
models/panel_ordenes.py — Lo que el panel ve de las órdenes por pagar, de los
lotes de pago y de sus comprobantes.

Segunda tanda de los contratos del panel (la primera, sobre los clientes, en
`models/panel_usuarios.py`).

Casi todo se arma campo por campo en `routes/admin/` y en los servicios de
lotes y comprobantes. Los contratos fijan esos campos: el día que alguien
agregue «un dato más» a una orden, no sale solo.

EL BENEFICIARIO DE UNA ORDEN

    La cola lo NORMALIZA (nombre, documento, banco, teléfono, cuenta, llave):
    sale de lo que se guardó con la operación, pero con nombres fijos. El
    contrato es esa misma forma. `banco_codigo` la pantalla no lo lee, pero
    lo usa quien arma el archivo del lote para el banco.

ARMAR UN LOTE DEVOLVIA LAS ORDENES CON SU BENEFICIARIO

    `POST /lotes` contestaba el lote entero, con cada orden y su
    beneficiario. La pantalla usa el texto del archivo, el número, el banco
    que paga y los contadores; las órdenes y sus beneficiarios ya están en el
    archivo. El contrato no deja salir la lista de órdenes.

Un test (`tests/test_contratos_del_panel.py`) compara lo que las pantallas
leen con cada contrato, y recorre las rutas con órdenes y lotes de ejemplo.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── Las órdenes ───────────────────────────────────────────────────────────

BeneficiarioDeLaOrden = _simple("BeneficiarioDeLaOrden", (
    "nombre", "documento", "banco", "banco_codigo", "telefono", "cuenta", "tipo_pago", "pix_key"))

MontoYUnidad = _simple("MontoYUnidad", ("valor", "unidad"))

OrdenPorProcesar = _simple("OrdenPorProcesar", (
    "orden_id", "flujo", "flujo_label", "accion", "display_id", "created_at", "user_name", "user_email",
    "comprobante_usuario", "assigned_to", "assigned_to_name", "estado_admin"),
    origen=(Optional[MontoYUnidad], None),
    destino=(Optional[MontoYUnidad], None),
    beneficiario=(Optional[BeneficiarioDeLaOrden], None))


class OrdenesPorProcesar(BaseModel):
    ordenes: List[OrdenPorProcesar] = []
    total: Escalar = None


# Las que pagaron de menos o de más y esperan que alguien decida.
OrdenEnRevisionDePago = _simple("OrdenEnRevisionDePago", (
    "orden_id", "display_id", "created_at", "user_name", "user_email", "moneda", "red",
    "pay_amount", "actually_paid", "topup_actually_paid", "recibido_total", "faltante", "paid_ratio",
    "topup_expired", "amount_input", "amount_output", "currency_output"),
    beneficiario=(Optional[BeneficiarioDeLaOrden], None))


class OrdenesEnRevisionDePago(BaseModel):
    ordenes: List[OrdenEnRevisionDePago] = []
    total: Escalar = None
    vencidas_ahora: Escalar = None


BancoParaPagar = _simple("BancoParaPagar", ("codigo", "nombre"))


class BancosParaPagar(BaseModel):
    bancos: List[BancoParaPagar] = []


# ── Los lotes de pago ─────────────────────────────────────────────────────

Banco = _simple("Banco", ("codigo", "nombre"))
PorSeccion = _simple("PorSeccion", ("pago_movil", "mismo_banco", "otros_bancos", "sin_datos"))

# Un lote abierto o cerrado, en la lista. `sin_datos` son los números de las
# órdenes a las que les falta algo para pagarse.
LoteEnLaLista = _simple("LoteEnLaLista", (
    "lote_id", "numero", "creado_en", "creado_por_nombre", "cerrado_en", "cerrado_por_nombre", "total"),
    banco_pagador=(Optional[Banco], None),
    por_seccion=(Optional[PorSeccion], None),
    sin_datos=(List[Escalar], []))


class ListaDeLotes(BaseModel):
    lotes: List[LoteEnLaLista] = []


# El lote recién armado: sin la lista de órdenes (ver arriba).
LoteArmado = _simple("LoteArmado", (
    "lote_id", "numero", "estado", "creado_en", "creado_por_nombre", "texto", "total"),
    banco_pagador=(Optional[Banco], None),
    por_seccion=(Optional[PorSeccion], None),
    sin_datos=(List[Escalar], []),
    no_se_pudieron_tomar=(List[Escalar], []),
    ya_no_estan=(List[Escalar], []))

ArchivoDelLote = _simple("ArchivoDelLote", ("lote_id", "numero", "texto", "estado"),
                         banco_pagador=(Optional[Banco], None),
                         por_seccion=(Optional[PorSeccion], None),
                         sin_datos=(List[Escalar], []))

LoteCerrado = _simple("LoteCerrado", ("lote_id", "numero", "asentadas"), ya_estaban=(List[Escalar], []))
LoteCancelado = _simple("LoteCancelado", ("lote_id", "devueltas"), no_volvieron=(List[Escalar], []))
OrdenDevuelta = _simple("OrdenDevuelta", ("lote_id", "orden_id", "motivo"))

# ── Los comprobantes del lote ─────────────────────────────────────────────

# Lo que el lector sacó de la foto: cuentas, teléfonos, cédulas, montos y
# referencias. Listas de textos, nada más.
LoLeido = _simple("LoLeido", (), **{c: (List[Escalar], []) for c in (
    "cuentas", "telefonos", "cedulas", "montos", "referencias")})

ComprobanteDelLote = _simple("ComprobanteDelLote", (
    "comprobante_id", "estado", "motivo", "orden_id", "display_id", "beneficiario", "monto"),
    candidatas=(List[Escalar], []),
    leido=(Optional[LoLeido], None))

OrdenDelLote = _simple("OrdenDelLote", (
    "orden_id", "display_id", "beneficiario", "monto", "tiene_comprobante", "estado_comprobante",
    "listo_para_registrar"))


class ComprobantesDelLote(BaseModel):
    lote_id: Escalar = None
    numero: Escalar = None
    estado: Escalar = None
    hay_lector: Escalar = None
    por_que_no_hay_lector: Escalar = None
    idiomas_del_lector: List[Escalar] = []
    comprobantes: List[ComprobanteDelLote] = []
    descartadas: Escalar = None
    ordenes: List[OrdenDelLote] = []
    resumen: Optional[Dict[str, Escalar]] = None


class ComprobantesCargados(BaseModel):
    lote_id: Escalar = None
    resumen: Optional[Dict[str, Escalar]] = None
    repetidas: Escalar = None
    comprobantes: List[ComprobanteDelLote] = []


ComprobanteDescartado = _simple("ComprobanteDescartado", ("comprobante_id", "estado", "motivo"))
ImagenDelComprobante = _simple("ImagenDelComprobante", ("imagen",))
