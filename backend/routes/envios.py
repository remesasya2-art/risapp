"""
routes/envios.py — Las rutas de lectura del módulo de envíos.

ESTADO (PR G)
    Lectura, cotización, confirmación y el pago de una partida pendiente.

    Cotizar y confirmar NO mueven un centavo: el usuario paga el tramo 1
    directamente al transportista de origen, y RIS App recién cobra cuando puede
    verificar contra una medición ajena —el peso que figura en el comprobante de
    despacho—. La única ruta de este archivo que toca saldo es
    `/{envio_id}/cobros/{partida}/pagar`, y solo salda algo ya emitido.

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

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     Request, UploadFile)
from fastapi.responses import Response

from routes.dependencies import get_current_user, get_verified_user
from services import (envios_archivos, envios_catalogo, envios_cobros,
                      envios_comprobante, envios_cotizador, envios_crear)
from services.envios_policy import CATEGORIAS_PROHIBIDAS_POR_DEFECTO, TERMINOS_VERSION
from models.envios_cotizacion import PedidoDeCotizacion, PedidoDeCreacion
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


def _ip_real(request) -> str | None:
    """La IP del usuario, no la del proxy.

    Detrás del edge de Railway, `request.client.host` es la misma para todos, y
    este dato existe únicamente para el argumento legal que motiva la doble
    aceptación: una IP idéntica para todo el mundo no distingue a nadie. El
    proyecto ya resolvió esto en `routes/security_2fa.get_real_client_ip`, que
    además es el `key_func` del rate limiter. Acá se repite el criterio en vez de
    importarlo: importar un módulo de rutas desde otro, en tiempo de petición,
    arrastra slowapi y media aplicación, y el `except` que eso obliga a poner
    degradaba en silencio justo a la IP del proxy que se quería evitar. Hay un
    test que compara las dos implementaciones para que no se separen.
    """
    encabezado = ""
    try:
        encabezado = (request.headers.get("x-forwarded-for") or "").strip()
    except Exception:                                         # pragma: no cover
        encabezado = ""
    if encabezado:
        # El primero de la cadena es el cliente; los demás son proxies.
        return encabezado.split(",")[0].strip() or None
    return getattr(getattr(request, "client", None), "host", None)


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


@router.post("/crear")
async def crear(pedido: PedidoDeCreacion, request: Request,
                current_user: User = Depends(get_verified_user)):
    """Confirma una cotización y entrega los datos de despacho. **No cobra nada.**

    Es el botón que en cualquier otra app de este rubro sacaría plata, y acá no.
    Por eso la respuesta trae `cobrado_ahora_ris: "0.00"` explícito y el próximo
    paso escrito: despachar, y después cargar el comprobante.

    Idempotente: dos `POST` con la misma `idempotency_key` devuelven el mismo
    resultado y crean un solo envío.
    """
    try:
        return await envios_crear.crear(
            current_user, pedido.envio_id, pedido.declaracion.model_dump(),
            idempotency_key=pedido.idempotency_key,
            ip=_ip_real(request))
    except envios_crear.NoSePuedeCrear as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: /crear falló: {e}")
        raise HTTPException(
            503, "No se pudo confirmar el envío. Probá de nuevo en un minuto.")


@router.post("/{envio_id}/cobros/{partida}/pagar")
async def pagar_cobro(envio_id: str, partida: str,
                      current_user: User = Depends(get_verified_user)):
    """Salda una partida pendiente con el saldo RIS del usuario.

    Que una partida esté pendiente no es un error: cuando se emitió, el paquete
    ya estaba viajando y quedarse sin saldo no cancela nada. Esta ruta existe
    para que el usuario pueda ponerse al día cuando quiera — y para que el
    paquete pueda salir de Pacaraima, que es el único lugar donde una deuda
    detiene algo.

    Sin saldo devuelve 200 con `estado: "pendiente"`, no un 402: el usuario no
    hizo nada mal y no hay nada que revertir.
    """
    try:
        envio = await envios_cobros.envio_del_usuario(current_user, envio_id)
        return await envios_cobros.pagar_pendiente(
            envio, partida, actor_type="user", actor_id=current_user.user_id)
    except envios_cobros.CobroImposible as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: /cobros/pagar falló: {e}")
        raise HTTPException(
            503, "No se pudo procesar el pago. Probá de nuevo en un minuto.")


@router.post("/{envio_id}/comprobante")
async def cargar_comprobante(envio_id: str,
                             codigo_objeto: str = Form(...),
                             posteado_at: str = Form(...),
                             foto: UploadFile = File(...),
                             servicio: str = Form(None),
                             monto_pagado_brl: str = Form(None),
                             current_user: User = Depends(get_verified_user)):
    """El usuario avisa que despachó. **No cobra nada.**

    Sin API de rastreo, es la única forma de que el sistema se entere. Lo que se
    carga acá se verifica después contra la foto, y recién ahí se emite el cobro
    inicial: el peso no puede salir de lo que el usuario tipeó.
    """
    try:
        datos = await foto.read(envios_archivos.TAMANO_MAX_BYTES + 1)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo leer la foto: {e}")
        raise HTTPException(400, "No se pudo leer el archivo. Probá de nuevo.")

    try:
        return await envios_comprobante.cargar(
            current_user, envio_id, codigo_objeto=codigo_objeto,
            posteado_at=posteado_at, foto=datos, servicio=servicio,
            monto_pagado_brl=monto_pagado_brl)
    except envios_comprobante.ComprobanteRechazado as e:
        raise HTTPException(e.http, e.mensaje)
    except envios_archivos.ArchivoRechazado as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: /comprobante falló: {e}")
        raise HTTPException(
            503, "No se pudo guardar el comprobante. Probá de nuevo en un minuto.")


@router.get("/{envio_id}/foto/{asset_id}")
async def ver_foto(envio_id: str, asset_id: str,
                   current_user: User = Depends(get_current_user)):
    """Devuelve una foto del envío, si el envío es de quien la pide.

    El `asset_id` no alcanza por sí solo: se exige que pertenezca a ESE envío y
    que ese envío sea del usuario. Un identificador de archivo suelto no puede
    ser una llave — es lo que convierte una galería privada en una pública.
    """
    if current_user is None:
        raise HTTPException(401, "Iniciá sesión para ver esta foto.")
    try:
        envio = await envios_cobros.envio_del_usuario(current_user, envio_id)
    except envios_cobros.CobroImposible as e:
        raise HTTPException(e.http, e.mensaje)

    ficha = await envios_archivos.leer(asset_id, envio_id=envio.get("envio_id"))
    if not ficha or not ficha.get("contenido"):
        raise HTTPException(404, "No encontramos esa foto.")
    return Response(content=bytes(ficha["contenido"]),
                    media_type=ficha.get("content_type") or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})
