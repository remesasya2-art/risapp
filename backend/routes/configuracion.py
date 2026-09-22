"""
routes/configuracion.py — La pantalla de configuración del panel.

DOS RUTAS Y NADA MAS

    `GET  /api/admin/configuracion`  → el catálogo con los valores de ahora.
    `PUT  /api/admin/configuracion`  → guarda los que vengan.

    No hay una ruta por ajuste. El catálogo vive en
    `services/configuracion.AJUSTES`, y agregar un número ahí no necesita
    ninguna ruta nueva ni ningún campo nuevo en la pantalla.

SOLO EL SUPER ADMINISTRADOR, Y POR ROL

    `Depends(get_super_admin)`, que compara `role == "super_admin"`. Nunca por
    cuenta: proteger una cuenta por su nombre la publica, y el bundle del
    frontend se le sirve a cada visitante.

    Acá se cambia cuánta plata se regala por cada cuenta que se registra. Es
    de las cosas que no se delegan: quien pudiera cambiarlo podría subirlo,
    cobrar y bajarlo otra vez.

SE VALIDA TODO ANTES DE ESCRIBIR NADA

    Si alguien manda tres ajustes y el segundo está mal, no se guarda ninguno.

    La alternativa —ir guardando de a uno y cortar en el que falle— deja la
    pantalla a mitad de camino: el primer número cambiado, el segundo no, y la
    persona mirando un cartel rojo sin saber qué quedó. Con plata de por medio
    eso no se puede.

QUEDA ANOTADO EN EL LIBRO DE AUDITORIA

    Con el valor de antes y el de después. Un cambio de estos mueve plata de
    la empresa a los usuarios, así que tiene que poder responderse «quién lo
    puso en cincuenta y cuándo».
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import auditoria, configuracion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/configuracion", tags=["configuracion"])


class GuardarAjustes(BaseModel):
    """Los ajustes a guardar, por nombre.

    Un diccionario y no un campo por ajuste, por dos motivos. El primero es
    que así agregar un ajuste no toca este archivo. El segundo es la lección
    del enlace de referido: con campos declarados uno por uno, un nombre que
    no coincide entre la pantalla y el servidor se DESCARTA EN SILENCIO, y eso
    ya dejó el código de invitación sin funcionar durante meses. Acá una clave
    que no existe es un 400 con su nombre adentro.
    """
    valores: Dict[str, Any]


def _respuesta(valores: dict) -> dict:
    """El catálogo con el valor de cada ajuste, como lo dibuja la pantalla."""
    ajustes = []
    for entrada in configuracion.catalogo_para_la_pantalla():
        ajuste = configuracion.AJUSTES[entrada["clave"]]
        ajustes.append({
            **entrada,
            "valor": configuracion.para_el_borde(
                ajuste, valores[entrada["clave"]]),
        })
    return {"ajustes": ajustes}


@router.get("")
async def ver_configuracion(_: User = Depends(get_super_admin)):
    return _respuesta(await configuracion.leer_todo(db))


@router.put("")
async def guardar_configuracion(cuerpo: GuardarAjustes, pedido: Request,
                                quien: User = Depends(get_super_admin)):
    if not cuerpo.valores:
        raise HTTPException(status_code=400, detail="No mandaste nada que guardar.")

    # ── Primera pasada: validar TODO. No se escribe nada todavía. ─────────
    limpios = {}
    for clave, escrito in cuerpo.valores.items():
        try:
            valor, motivo = configuracion.normalizar(clave, escrito)
        except configuracion.AjusteDesconocido:
            # Con nombre y con la lista de los que sí existen. Un 400 que dice
            # «clave inválida» y nada más obliga a ir a leer el código.
            raise HTTPException(
                status_code=400,
                detail=(f"No existe un ajuste llamado «{clave}». Los que hay "
                        f"son: {', '.join(configuracion.AJUSTES)}."))
        if motivo:
            raise HTTPException(status_code=400, detail=motivo)
        limpios[clave] = valor

    # Y la regla que ningún campo puede comprobar mirándose a sí mismo: que
    # ningún mínimo quede por encima de su máximo. Va acá, entre la validación y
    # la escritura, porque necesita saber cómo quedaría el conjunto entero.
    descuadre = await configuracion.revisar_las_parejas(db, limpios)
    if descuadre:
        raise HTTPException(status_code=400, detail=descuadre)

    # ── Segunda pasada: escribir, y anotar sólo lo que de verdad cambió ───
    antes = await configuracion.leer_todo(db)
    cambios = {c: v for c, v in limpios.items() if antes.get(c) != v}
    try:
        await configuracion.comprobar_guardas(db, cambios)
    except configuracion.CambioNoPermitido as e:
        raise HTTPException(status_code=400, detail=str(e))
    for clave, valor in cambios.items():
        await configuracion.escribir(db, clave, valor)

    if cambios:
        # `str` en los dos lados: el libro se lee, y un `Decimal` serializado
        # por accidente ahí adentro se ve como un objeto y no como un monto.
        await auditoria.registrar(
            db, "config.ajuste", quien=quien, request=pedido,
            objetivo_tipo="configuracion",
            objetivo_id=",".join(sorted(cambios)),
            objetivo_desc="Ajustes del panel",
            antes={c: str(antes.get(c)) for c in cambios},
            despues={c: str(v) for c, v in cambios.items()},
        )

    return {
        **_respuesta(await configuracion.leer_todo(db)),
        # Cuáles cambiaron de verdad, para que la pantalla pueda decir «nada
        # que guardar» en vez de un «guardado» que no guardó nada.
        "cambiados": sorted(cambios),
    }
