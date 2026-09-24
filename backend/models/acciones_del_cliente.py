"""
models/acciones_del_cliente.py — Lo que contestan las acciones del cliente
sobre encomiendas, beneficiarios y soporte.

Segunda tanda de los contratos de salida de las acciones (la primera, lo que
mueve plata, vive en `models/acciones_de_dinero.py`; el porqué completo está
ahí).

La que más importa de esta tanda es la cotización de encomiendas: es la ruta
que alguna vez le mandó al cliente el margen de ganancia. Hoy arma la
respuesta con cuidado (`services/envios_cotizador._payload`) y el desglose se
queda guardado en el envío. El contrato es la segunda capa, para que la
próxima vez que alguien agregue «un dato más, que total la pantalla no lo
muestra», no salga.

Un test (`tests/test_contratos_de_acciones_del_cliente.py`) compara las
claves que devuelve cada ruta, leídas del código, con su contrato.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.cuenta import MiBeneficiario, MiBeneficiarioEnBrasil
from models.envios_salida import RetiroQueVeElCliente
from models.escalar import Escalar
from models.soporte import CasoQueVeElCliente
from services.envios_policy import _MAXIMOS, _MINIMOS


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ── Cotizar una encomienda ────────────────────────────────────────────────

PesoPropio = _simple("PesoPropio", ("kg", "volumetrico_kg"))
PesoDeUnTransportista = _simple("PesoDeUnTransportista", ("codigo", "kg"))


class PesoFacturable(BaseModel):
    propio: Optional[PesoPropio] = None
    por_transportista: List[PesoDeUnTransportista] = []


# Lo ÚNICO que cobra RISApp: el concepto y el total. Sin el desglose —el
# servicio, los sobrecargos, el subtotal—: con cualquiera de ellos el margen
# es una resta. Ver el comentario en `envios_cotizador._payload`.
LoQueSePagaEnRisapp = _simple("LoQueSePagaEnRisapp", ("concepto", "total_estimado_ris"))

UnaReferencia = _simple("UnaReferencia", (
    "codigo", "rol", "etiqueta", "monto", "moneda", "fuente", "desactualizada",
    "facturable", "detalle"))

# Las claves salen de las mismas dos listas que usa la regla de los límites:
# una clave nueva allá aparece acá sola, y una clave inventada en la
# respuesta no pasa.
LimitesDeLaCotizacion = _simple("LimitesDeLaCotizacion", _MAXIMOS + _MINIMOS)


class MiCotizacionDeEncomienda(BaseModel):
    envio_id: Escalar = None
    estado: Escalar = None
    es_estimado: Escalar = None
    modalidad_flete: Escalar = None
    moneda: Escalar = None
    peso_real_kg: Escalar = None
    peso_facturable: Optional[PesoFacturable] = None
    a_pagar_en_risapp: Optional[LoQueSePagaEnRisapp] = None
    referencias: List[UnaReferencia] = []
    retiro: Optional[RetiroQueVeElCliente] = None
    vence_at: Escalar = None
    terminos_version: Escalar = None
    aviso_estimado: Escalar = None
    banda_variacion_pct: Escalar = None
    limites: Optional[LimitesDeLaCotizacion] = None


# ── Confirmar la encomienda ───────────────────────────────────────────────


class MiEncomiendaCreada(BaseModel):
    success: Escalar = None
    envio_id: Escalar = None
    display_id: Escalar = None
    # El enlace de seguimiento es una credencial (quien lo tiene ve el envío),
    # pero ésta es la respuesta a su dueño, en el momento de crearlo: es la
    # única vez que la pantalla lo recibe para ofrecer compartirlo.
    tracking_token: Escalar = None
    estado: Escalar = None
    es_estimado: Escalar = None
    total_estimado_ris: Escalar = None
    moneda: Escalar = None
    cobrado_ahora_ris: Escalar = None
    retiro: Optional[RetiroQueVeElCliente] = None
    proximo_paso: Escalar = None


MiCobroDeEncomienda = _simple("MiCobroDeEncomienda", (
    "partida", "estado", "monto_ris", "saldo_restante", "entry_id", "motivo"))

MiComprobanteDeEncomienda = _simple("MiComprobanteDeEncomienda", (
    "ok", "envio_id", "estado", "codigo_objeto", "comprobante_cargado", "proximo_paso"))

# ── Beneficiarios ─────────────────────────────────────────────────────────

# El beneficiario recién guardado va entero, con el MISMO contrato que la
# lista: la pantalla lo elige con esta respuesta y lo muestra en la
# confirmación del envío.


class MiBeneficiarioCreado(BaseModel):
    message: Escalar = None
    beneficiary_id: Escalar = None
    beneficiario: Optional[MiBeneficiario] = None


class MiBeneficiarioEnBrasilCreado(BaseModel):
    message: Escalar = None
    beneficiary_id: Escalar = None
    beneficiario: Optional[MiBeneficiarioEnBrasil] = None


MiBeneficiarioEliminado = _simple("MiBeneficiarioEliminado", ("message",))

# ── Soporte ───────────────────────────────────────────────────────────────


class MiCasoAbierto(BaseModel):
    caso: Optional[CasoQueVeElCliente] = None


MiRespuestaEnviada = _simple("MiRespuestaEnviada", ("success", "reabierto"))
MiCasoActualizado = _simple("MiCasoActualizado", ("success",))
