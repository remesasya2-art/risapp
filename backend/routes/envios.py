"""
routes/envios.py — Las rutas de lectura del módulo de envíos.

ESTADO (PR E)
    Las dos rutas de lectura, y la cotización. Ninguna mueve un centavo: cotizar
    es gratis y crear el envío es un paso posterior y separado. Los PRs
    siguientes agregan el resto acá mismo.

POR QUE COTIZAR PIDE KYC
    `get_verified_user` y no `get_current_user`. Cotizar escribe un documento en
    `envios` con el nombre, el documento y el teléfono de un destinatario en
    Venezuela; una cuenta sin verificar que puede escribir eso es un formulario
    de carga de datos de terceros abierto a cualquiera. Ver los límites y el
    catálogo, en cambio, no escribe nada.

POR QUE /envios/limites ES PUBLICA
    Mismo criterio que `/limits`: los límites físicos y la leyenda de tarifas no
    son información sensible, y la pantalla los necesita para validar antes de
    que alguien inicie sesión. Que sea pública también evita el bug del PR #40 —
    la pantalla los tenía escritos adentro justamente porque pedirlos era
    incómodo.

    Pero público no es lo mismo que "todo": el DETALLE de qué falta configurar
    —que incluye frases como "la tarifa no tiene divisor volumétrico, los bultos
    grandes cotizarían solo por su peso real"— es un diagnóstico interno, y
    explicarle a un anónimo cómo pagar de menos no le sirve a nadie. Afuera va
    `disponible: false`; el detalle lo ve el panel.

    El catálogo pide sesión: es la lista de agencias con sus direcciones, y no
    hay razón para regalarla a un scraper ajeno.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from routes.dependencies import get_current_user, get_verified_user
from services import envios_catalogo, envios_cotizador
from services.envios_policy import CATEGORIAS_PROHIBIDAS_POR_DEFECTO, TERMINOS_VERSION
from models.envios_cotizacion import PedidoDeCotizacion
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/envios", tags=["envios"])

_MENSAJE_NO_DISPONIBLE = (
    "El servicio de envíos no está disponible en este momento. "
    "Escribinos si necesitás cotizar un envío."
)


def _sin_detalle(payload: dict) -> dict:
    """Saca el diagnóstico de configuración del payload público.

    Se reemplaza por un mensaje, no se borra la clave: la pantalla ya sabe leer
    `faltantes` y tiene que poder mostrar algo cuando el servicio no está.
    """
    salida = dict(payload)
    if salida.get("faltantes"):
        salida["faltantes"] = [_MENSAJE_NO_DISPONIBLE]
    return salida


@router.get("/limites")
async def obtener_limites():
    """Límites físicos vigentes, prohibidos y versión de términos.

    Nunca 500: si el módulo todavía no está configurado, contesta
    `disponible: false`. Un sistema recién instalado no es un error.
    """
    try:
        return _sin_detalle(await envios_catalogo.limites())
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: /limites falló: {e}")
        # La lista de prohibidos NO va vacía en el fallback: una lista vacía se
        # lee literalmente como "no hay nada prohibido", que es el mismo tipo de
        # bug que unos límites en null leídos como "sin restricciones".
        return {
            "disponible": False,
            "faltantes": [_MENSAJE_NO_DISPONIBLE],
            "limites": {}, "impuesto_por": {},
            "prohibidos": CATEGORIAS_PROHIBIDAS_POR_DEFECTO,
            "tarifa_version": None, "moneda": "RIS",
            "terminos_version": TERMINOS_VERSION,
        }


@router.get("/catalogo")
async def obtener_catalogo(current_user: User = Depends(get_current_user)):
    """Transportistas de destino y sus agencias activas, para el formulario."""
    try:
        return await envios_catalogo.catalogo()
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: /catalogo falló: {e}")
        return {"transportistas": [], "disponible": False, "degradado": True}


@router.post("/cotizar")
async def cotizar(pedido: PedidoDeCotizacion,
                  current_user: User = Depends(get_verified_user)):
    """El precio del servicio, más las dos orientaciones. **No cobra nada.**

    Cotizar es gratis y no reserva nada: el número es un ESTIMADO sobre lo que
    el usuario declaró, y se confirma al repesar en Pacaraima con balanza
    propia. Por eso la respuesta trae `es_estimado: true` y `aviso_estimado`
    siempre, sin condición.

    Los errores del usuario —una descripción de tres letras, una caja de 80 kg,
    una agencia que ya no recibe— vuelven como 400 con el texto exacto de qué
    arreglar. Lo que depende de la configuración vuelve como 503 con un mensaje
    que no le explica a un anónimo qué le falta al panel.
    """
    try:
        return await envios_cotizador.cotizar(current_user, pedido.model_dump())
    except envios_cotizador.NoSePuedeCotizar as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: /cotizar falló: {e}")
        raise HTTPException(
            503, "No se pudo cotizar en este momento. Probá de nuevo en un minuto.")
