"""
routes/admin/lotes.py — Los lotes de pago en bolívares: armarlos, el archivo para el banco, cerrarlos
y los comprobantes subidos de una sola carga.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional

from database import db
from models.user import User
from models.panel_ordenes import (ArchivoDelLote, BancosParaPagar, ComprobanteDelLote, ComprobanteDescartado,
                                   ComprobantesCargados, ComprobantesDelLote, ImagenDelComprobante,
                                   ListaDeLotes, LoteArmado, LoteCancelado, LoteCerrado, OrdenDevuelta)
from models.panel_tablero import DesempenoDelLector
from pydantic import BaseModel, Field
from routes.dependencies import get_super_admin
from services import (comprobantes_del_lote, desempeno_del_lector,
                      lotes_de_pago)
from services.imagen_recibida import ImagenInvalida
from routes.admin.recargas_ves import get_ordenes_pendientes

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== EL ARCHIVO DE PAGOS DE UN LOTE ==============
#
# Para pagar un grupo de órdenes en bolívares hay que pasar los datos de cada
# beneficiario a la banca en línea. Hoy eso se hace copiando de la pantalla, de
# a un campo por vez: con once órdenes son cuarenta y cuatro copiados, y cada
# uno es una chance de pegar el monto de una fila en la cuenta de otra.
#
# Esta ruta arma ese texto de una sola vez, agrupado por banco y numerado.
# SOLO LEE: no cambia el estado de ninguna orden, no toca plata, no marca nada
# como pagado. Bajar el archivo y pagar son dos cosas distintas, y quien baja
# el archivo todavía no pagó nada.

class ArmarLoteRequest(BaseModel):
    orden_ids: List[str] = Field(..., min_length=1, max_length=lotes_de_pago.MAXIMO)
    # El código de cuatro dígitos del banco desde el que se paga ESTE lote.
    # Es un dato del lote y no una constante: la misma orden va a «mismo banco»
    # o a «otros bancos» según desde dónde se pague ese día.
    banco_pagador: str


@router.post("/lotes", response_model=LoteArmado, response_model_exclude_unset=True)
async def armar_lote(
    cuerpo: ArmarLoteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Arma un lote con estas órdenes y devuelve su archivo.

    Las órdenes salen de la MISMA consulta que alimenta la pantalla, filtradas
    por los identificadores que mandó el operador. Que sea la misma fuente no
    es comodidad: si el lote armara su propia lista, podría incluir una orden
    que en la pantalla ya no está —porque otro operador la tomó hace diez
    segundos— y esa orden se pagaría dos veces.

    Armar un lote NO mueve plata ni marca nada como pagado: reserva las
    órdenes y guarda el papel que se va a pegar en el banco.
    """
    disponibles = (await get_ordenes_pendientes(admin=admin)).get("ordenes", [])
    por_id = {o.get("orden_id"): o for o in disponibles}

    elegidas, ya_no_estan = [], []
    for oid in cuerpo.orden_ids:
        if oid in por_id:
            elegidas.append(por_id[oid])
        else:
            ya_no_estan.append(oid)

    try:
        lote = await lotes_de_pago.armar(
            db, elegidas, banco_pagador=cuerpo.banco_pagador,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))

    # Las que se cayeron entre que la pantalla cargó y el operador pulsó el
    # botón vuelven nombradas. Sacarlas en silencio sería entregar un archivo
    # con menos pagos de los que la persona creyó pedir.
    lote["ya_no_estan"] = ya_no_estan
    return lote


@router.get("/lotes", response_model=ListaDeLotes, response_model_exclude_unset=True)
async def listar_lotes_abiertos(admin: User = Depends(get_super_admin)):
    """Los lotes que todavía están en la calle, con sus órdenes reservadas."""
    return {"lotes": await lotes_de_pago.abiertos(db)}


# NO CUELGA DE `/lotes/...`, Y ES A PROPOSITO
#
#   El informe es de TODOS los lotes cerrados, no de uno. Colgarlo de
#   `/lotes/algo` lo pondría a competir por el orden de registro con
#   `/lotes/{lote_id}/...`, que es el choque que ya pasó dos veces en este
#   repositorio y que vigila `tests/test_rutas_alcanzables.py`.
@router.get("/lector/desempeno", response_model=DesempenoDelLector, response_model_exclude_unset=True)
async def desempeno_del_lector_de_comprobantes(
        admin: User = Depends(get_super_admin)):
    """Cómo viene adjudicando el lector, sobre los últimos lotes cerrados."""
    return await desempeno_del_lector.medir(db)


@router.get("/lotes/{lote_id}/archivo", response_model=ArchivoDelLote, response_model_exclude_unset=True)
async def archivo_del_lote(lote_id: str, admin: User = Depends(get_super_admin)):
    """El archivo GUARDADO de un lote, para volver a bajarlo idéntico.

    No se vuelve a generar: entre que se bajó y ahora pudo cambiar la tasa o
    corregirse la cuenta de un beneficiario, y entonces el segundo archivo no
    sería el que la persona ya pegó en el banco.
    """
    try:
        return await lotes_de_pago.archivo(db, lote_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


class DevolverOrdenRequest(BaseModel):
    # El motivo se valida en el servicio, donde viven el mínimo y el tope.
    motivo: str


@router.get("/lotes/cerrados", response_model=ListaDeLotes, response_model_exclude_unset=True)
async def listar_lotes_cerrados(admin: User = Depends(get_super_admin)):
    """Los últimos lotes cerrados. Adentro viven el archivo y las fotos."""
    return {"lotes": await lotes_de_pago.cerrados(db)}


@router.post("/lotes/{lote_id}/cerrar", response_model=LoteCerrado, response_model_exclude_unset=True)
async def cerrar_lote(lote_id: str, request: Request,
                      admin: User = Depends(get_super_admin)):
    """Asienta de una vez el pago de todas las órdenes del lote y lo cierra."""
    try:
        return await lotes_de_pago.cerrar(db, lote_id, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/ordenes/{orden_id}/devolver", response_model=OrdenDevuelta, response_model_exclude_unset=True)
async def devolver_orden_del_lote(lote_id: str, orden_id: str,
                                  cuerpo: DevolverOrdenRequest,
                                  request: Request,
                                  admin: User = Depends(get_super_admin)):
    """Saca una orden del lote y la manda de vuelta a la cola de pendientes."""
    try:
        return await lotes_de_pago.devolver_una(
            db, lote_id, orden_id, cuerpo.motivo, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/cancelar", response_model=LoteCancelado, response_model_exclude_unset=True)
async def cancelar_lote(lote_id: str, request: Request,
                        admin: User = Depends(get_super_admin)):
    """Deshace un lote: sus órdenes vuelven a la cola de pendientes."""
    try:
        return await lotes_de_pago.cancelar(db, lote_id, quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ============== LOS COMPROBANTES DEL LOTE, DE UNA SOLA CARGA ==============
#
# El agente paga las once órdenes en la banca en línea y vuelve con once
# capturas en el teléfono. Antes tenía que abrir orden por orden y buscar cuál
# de las once era la de ésa — y el único dato a mano para distinguirlas era el
# monto, que es justo el que se repite cuando dos personas cobran lo mismo.
#
# Acá se suben todas juntas y el sistema dice de quién es cada una. Lo que no
# puede decir con certeza queda marcado y lo resuelve una persona: ver
# `services/comprobantes_del_lote.py`, que explica por qué el monto nunca
# adjudica y por qué ante la duda no se elige.
#
# Esto NO aprueba ni acredita nada. Colgar la foto y dar la orden por pagada
# son dos decisiones distintas.

class ComprobantesRequest(BaseModel):
    imagenes: List[str] = Field(
        ..., min_length=1, max_length=comprobantes_del_lote.MAXIMO_POR_CARGA)


class AsignarComprobanteRequest(BaseModel):
    # `None` suelta la foto: la saca de la orden que la tenía y la deja sin
    # dueño, para volver a asignarla.
    orden_id: Optional[str] = None


class DescartarComprobanteRequest(BaseModel):
    # El motivo es obligatorio y se valida en el servicio, no acá: el mínimo de
    # letras y el tope viven al lado de la regla que los usa.
    motivo: str


@router.post("/lotes/{lote_id}/comprobantes", response_model=ComprobantesCargados, response_model_exclude_unset=True)
async def cargar_comprobantes_del_lote(
    lote_id: str,
    cuerpo: ComprobantesRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Sube varias fotos de una vez y las reparte entre las órdenes del lote."""
    try:
        return await comprobantes_del_lote.cargar(
            db, lote_id, cuerpo.imagenes, quien=admin, request=request)
    except ImagenInvalida as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/lotes/{lote_id}/comprobantes", response_model=ComprobantesDelLote, response_model_exclude_unset=True)
async def ver_comprobantes_del_lote(lote_id: str,
                                    admin: User = Depends(get_super_admin)):
    """La tabla de fotos del lote y las órdenes a las que se pueden asignar."""
    try:
        return await comprobantes_del_lote.listar(db, lote_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/lotes/{lote_id}/comprobantes/{comprobante_id}/imagen", response_model=ImagenDelComprobante, response_model_exclude_unset=True)
async def ver_una_foto_del_lote(lote_id: str, comprobante_id: str,
                                admin: User = Depends(get_super_admin)):
    """Una foto concreta. Se pide de a una: once en base64 son decenas de megas."""
    try:
        return {"imagen": await comprobantes_del_lote.imagen(
            db, lote_id, comprobante_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/lotes/{lote_id}/comprobantes/{comprobante_id}/asignar", response_model=ComprobanteDelLote, response_model_exclude_unset=True)
async def asignar_comprobante_del_lote(
    lote_id: str, comprobante_id: str,
    cuerpo: AsignarComprobanteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Cambia a mano de qué orden es una foto, o la suelta."""
    try:
        return await comprobantes_del_lote.asignar(
            db, lote_id, comprobante_id, cuerpo.orden_id,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/lotes/{lote_id}/comprobantes/{comprobante_id}/descartar", response_model=ComprobanteDescartado, response_model_exclude_unset=True)
async def descartar_comprobante_del_lote(
    lote_id: str, comprobante_id: str,
    cuerpo: DescartarComprobanteRequest,
    request: Request,
    admin: User = Depends(get_super_admin),
):
    """Saca una foto de la pantalla, con el motivo escrito."""
    try:
        return await comprobantes_del_lote.descartar(
            db, lote_id, comprobante_id, cuerpo.motivo,
            quien=admin, request=request)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/ordenes/bancos-para-pagar", response_model=BancosParaPagar, response_model_exclude_unset=True)
async def bancos_para_pagar(admin: User = Depends(get_super_admin)):
    """La lista de bancos, para elegir desde cuál se paga el lote."""
    from services import bancos_venezuela
    return {"bancos": [{"codigo": c, "nombre": n}
                       for c, n in sorted(bancos_venezuela.BANCOS.items())]}
