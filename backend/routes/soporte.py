"""
routes/soporte.py — La mesa de ayuda, del lado del cliente y del asesor.

El modelo y las reglas están en `services/soporte.py`. Acá sólo se atiende: se
lee lo que llega, se le pregunta al servicio si se puede, y se guarda.

LO QUE ESTE ARCHIVO AGREGA SOBRE EL CHAT VIEJO

    Del lado del cliente:
      · Casos separados, con número. Una consulta no se mezcla con la anterior.
      · Motivo al abrir, que encamina el caso al área correcta desde el primer
        mensaje en vez de hacerlo rebotar.
      · Puede adjuntar una imagen. Antes sólo podía el asesor, y la mitad de
        los problemas se explican con una captura.
      · Califica CADA caso, no una vez en la vida.

    Del lado del asesor:
      · Nota interna: contexto para el que siga, que el cliente no ve.
      · Transferencia a otro asesor o a otra área, con nota de traspaso.
      · Pedido a otra área SIN soltar el caso: el asesor sigue con el cliente
        y en paralelo pregunta a quien puede resolver.
      · Escalamiento a un super administrador, con motivo.
      · La ficha del cliente al lado de la conversación: saldo, verificación y
        últimas operaciones. Antes se atendía a ciegas o abriendo otra pestaña.

QUE NO SE TOCO

    Las rutas viejas de `routes/support.py` siguen ahí y siguen andando. La
    migración pasa los chats existentes a casos cerrados, así que el historial
    no se pierde ni se duplica.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_current_user, get_crm_user
from services import soporte
from services.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(tags=["soporte"])

_AHORA = lambda: datetime.now(timezone.utc)  # noqa: E731


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

async def _siguiente_numero():
    """Un contador propio, atómico.

    `count_documents() + 1` daría números repetidos en cuanto dos personas
    abran un caso en el mismo segundo, y un número de caso repetido es peor
    que no tener número: dos clientes distintos citando el mismo.
    """
    doc = await db.contadores.find_one_and_update(
        {"_id": "soporte_casos"},
        {"$inc": {"valor": 1}},
        upsert=True,
        return_document=True,
    )
    return soporte.numero_legible((doc or {}).get("valor") or 1)


async def _caso(caso_id):
    return await db.soporte_casos.find_one({"caso_id": caso_id}, {"_id": 0})


async def _mio(caso_id, user_id):
    return await db.soporte_casos.find_one(
        {"caso_id": caso_id, "user_id": user_id}, {"_id": 0})


async def _registrar(caso_id, texto, autor_id=None, autor_nombre=None):
    """Una línea de sistema en la conversación.

    Las transferencias, los cambios de estado y los escalamientos se ven en el
    hilo, no en un registro aparte que nadie abre. El asesor que entra al caso
    lee la historia completa en orden, incluido quién se lo pasó y por qué.
    """
    await db.soporte_mensajes.insert_one({
        "mensaje_id": f"msg_{uuid.uuid4().hex[:12]}",
        "caso_id": caso_id,
        "autor": soporte.SISTEMA,
        "autor_id": autor_id,
        "autor_nombre": autor_nombre,
        "interno": True,
        "texto": texto,
        "adjunto": None,
        "creado_en": _AHORA(),
    })


# Lo que el cliente ve de su caso. LISTA DE LO PERMITIDO, no de lo prohibido, y
# la diferencia no es de estilo: con una lista de lo prohibido, cada campo nuevo
# que se le agregue al caso viaja al cliente hasta que alguien se acuerde de
# agregarlo a la lista, y el que se olvida no avisa. Así lo escribí la primera
# vez y ya se colaban `escalado_por_nombre` y el motivo del escalamiento —quién
# de la casa marcó el caso como grave y por qué—.
#
# `asignado_a_nombre` va a propósito: el cliente lee «¿Cómo fue la atención de
# Ana?». `asignado_a` no: el identificador interno no le sirve para nada.
_DEL_CLIENTE = (
    "caso_id", "numero", "asunto", "motivo", "estado", "creado_en",
    "actualizado_en", "ultimo_mensaje", "ultimo_mensaje_en", "ultimo_mensaje_de",
    "sin_leer_cliente", "calificacion", "asignado_a_nombre", "cerrado_en",
)


def _publico(caso):
    """El caso como lo ve el cliente: sin nada de la cocina."""
    if not caso:
        return None
    return {k: caso[k] for k in _DEL_CLIENTE if k in caso}


async def _avisar(**aviso):
    """Manda un aviso sin que su caída se lleve puesta la operación.

    El aviso es una cortesía: el caso, la respuesta y el cambio de estado ya
    están guardados cuando se llega acá. Si se cae la base de notificaciones o
    el servicio de push, antes la petición devolvía 500 sobre un trabajo YA
    hecho, y la pantalla lo reintentaba: dos casos iguales, dos mensajes
    repetidos. Se anota en el registro y se sigue.
    """
    try:
        await create_notification(**aviso)
    except Exception as e:                                    # pragma: no cover
        logger.warning("no se pudo avisar a %s: %s", aviso.get("user_id"), e)


async def _avisar_a_varios(destinos, **aviso):
    """El mismo aviso a varias personas, todos a la vez.

    De a uno, avisarle a doce asesores son doce viajes al servicio de push
    encadenados: el cliente que abrió el caso mira la ruedita hasta que
    termina el último. Como `_avisar` ya se traga sus propias caídas, mandarlos
    juntos no puede romper nada que de a uno no rompiera.
    """
    ids = [d.get("user_id") for d in destinos if d.get("user_id")]
    if not ids:
        return
    await asyncio.gather(*[_avisar(user_id=uid, **aviso) for uid in ids])


async def _staff_con(permiso):
    """El personal que puede resolver algo de esa área.

    Sale de los permisos que ya gobiernan el trabajo, no de una lista aparte.
    El super administrador entra siempre: es quien destraba.
    """
    consulta = {"role": {"$in": ["agent", "admin", "super_admin"]},
                "is_active": {"$ne": False}}
    if permiso:
        consulta = {"$and": [consulta, {"$or": [
            {"role": "super_admin"},
            {"permissions": permiso},
        ]}]}
    return await db.users.find(consulta, {
        "_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "legajo": 1,
    }).to_list(200)


# ══════════════════════════════════════════════════════════════════════════
# EL CLIENTE
# ══════════════════════════════════════════════════════════════════════════

class AbrirCaso(BaseModel):
    motivo: str
    mensaje: str = Field(..., min_length=1, max_length=4000)
    adjunto: Optional[str] = None


class MensajeDelCliente(BaseModel):
    mensaje: str = Field("", max_length=4000)
    adjunto: Optional[str] = None


class Calificacion(BaseModel):
    estrellas: int
    comentario: Optional[str] = None


@router.get("/soporte/motivos")
async def motivos(current_user: User = Depends(get_current_user)):
    """Los motivos que se le ofrecen al cliente al abrir un caso."""
    return {"motivos": [{"clave": k, "texto": v[0]} for k, v in soporte.MOTIVOS.items()]}


@router.get("/soporte/casos")
async def mis_casos(current_user: User = Depends(get_current_user)):
    """Mis casos, el más reciente primero."""
    casos = await db.soporte_casos.find(
        {"user_id": current_user.user_id}, {"_id": 0},
    ).sort("actualizado_en", -1).to_list(100)
    return {"casos": [_publico(c) for c in casos]}


@router.get("/soporte/casos/{caso_id}")
async def mi_caso(caso_id: str, current_user: User = Depends(get_current_user)):
    """Un caso mío y su conversación, SIN las notas internas."""
    caso = await _mio(caso_id, current_user.user_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    mensajes = await db.soporte_mensajes.find(
        {"caso_id": caso_id, "interno": {"$ne": True}}, {"_id": 0},
    ).sort("creado_en", 1).to_list(500)
    # Al abrirlo, deja de haber nada sin leer para el cliente. La condición no
    # es un adorno: esta pantalla vuelve a preguntar cada ocho segundos, y sin
    # ella cada consulta sería una escritura para poner en cero algo que ya
    # estaba en cero.
    if caso.get("sin_leer_cliente"):
        await db.soporte_casos.update_one(
            {"caso_id": caso_id}, {"$set": {"sin_leer_cliente": 0}})
    return {"caso": _publico(caso), "mensajes": mensajes}


@router.post("/soporte/casos")
async def abrir_caso(datos: AbrirCaso, current_user: User = Depends(get_current_user)):
    """Abre un caso nuevo."""
    if not soporte.motivo_valido(datos.motivo):
        raise HTTPException(status_code=400, detail="Elegí un motivo de la lista")

    texto = datos.mensaje.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Escribí tu consulta")

    # Un cliente con muchos casos abiertos casi siempre es la misma consulta
    # escrita de nuevo porque no encontró la anterior. Se le devuelve la que ya
    # tiene en vez de multiplicar hilos que después nadie junta.
    abiertos = await db.soporte_casos.count_documents({
        "user_id": current_user.user_id,
        "estado": {"$in": list(soporte.ABIERTOS)},
    })
    if abiertos >= 5:
        raise HTTPException(
            status_code=400,
            detail="Ya tenés varias consultas abiertas. Seguí en una de esas y "
                   "te respondemos ahí.")

    ahora = _AHORA()
    caso = {
        "caso_id": soporte.nuevo_id(),
        "numero": await _siguiente_numero(),
        "user_id": current_user.user_id,
        "user_name": current_user.name or "Usuario",
        "user_email": current_user.email,
        "motivo": datos.motivo,
        "asunto": soporte.asunto_desde(texto),
        "estado": soporte.ABIERTO,
        "prioridad": "normal",
        "area": soporte.area_del_motivo(datos.motivo),
        "asignado_a": None,
        "asignado_a_nombre": None,
        "escalado": False,
        "creado_en": ahora,
        "actualizado_en": ahora,
        "ultimo_mensaje": soporte.asunto_desde(texto, 120),
        "ultimo_mensaje_en": ahora,
        "ultimo_mensaje_de": soporte.CLIENTE,
        "primera_respuesta_en": None,
        "sin_leer_asesor": 1,
        "sin_leer_cliente": 0,
        "calificacion": None,
    }
    await db.soporte_casos.insert_one(dict(caso))
    await db.soporte_mensajes.insert_one({
        "mensaje_id": f"msg_{uuid.uuid4().hex[:12]}",
        "caso_id": caso["caso_id"],
        "autor": soporte.CLIENTE,
        "autor_id": current_user.user_id,
        "autor_nombre": current_user.name or "Usuario",
        "interno": False,
        "texto": texto,
        "adjunto": datos.adjunto,
        "creado_en": ahora,
    })

    await _avisar_a_varios(
        await _staff_con(soporte.permiso_de_area(caso["area"])),
        title=f"Caso nuevo {caso['numero']}",
        message=f"{caso['user_name']}: {caso['asunto']}",
        notification_type="soporte_caso",
    )
    return {"caso": _publico(caso)}


@router.post("/soporte/casos/{caso_id}/mensajes")
async def responder_cliente(caso_id: str, datos: MensajeDelCliente,
                            current_user: User = Depends(get_current_user)):
    """El cliente escribe en un caso suyo.

    Si estaba resuelto, se REABRE solo. Es la razón por la que `resuelto` y
    `cerrado` son estados distintos: el asesor puede dar por terminado sin
    obligar al cliente a abrir un caso nuevo si no quedó conforme.
    """
    caso = await _mio(caso_id, current_user.user_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    if caso.get("estado") == soporte.CERRADO:
        raise HTTPException(
            status_code=400,
            detail="Este caso está cerrado. Abrí uno nuevo y lo vemos.")

    texto = (datos.mensaje or "").strip()
    if not texto and not datos.adjunto:
        raise HTTPException(status_code=400, detail="Escribí algo o adjuntá una imagen")

    ahora = _AHORA()
    await db.soporte_mensajes.insert_one({
        "mensaje_id": f"msg_{uuid.uuid4().hex[:12]}",
        "caso_id": caso_id,
        "autor": soporte.CLIENTE,
        "autor_id": current_user.user_id,
        "autor_nombre": current_user.name or "Usuario",
        "interno": False,
        "texto": texto,
        "adjunto": datos.adjunto,
        "creado_en": ahora,
    })

    cambios = {
        "actualizado_en": ahora,
        "ultimo_mensaje": soporte.asunto_desde(texto or "📎 Imagen", 120),
        "ultimo_mensaje_en": ahora,
        "ultimo_mensaje_de": soporte.CLIENTE,
    }
    reabierto = caso.get("estado") in (soporte.RESUELTO, soporte.ESPERANDO_CLIENTE)
    if reabierto:
        cambios["estado"] = soporte.EN_CURSO
    await db.soporte_casos.update_one(
        {"caso_id": caso_id},
        {"$set": cambios, "$inc": {"sin_leer_asesor": 1}},
    )
    if reabierto:
        await _registrar(caso_id, "El cliente volvió a escribir: el caso se reabrió.")

    destino = caso.get("asignado_a")
    await _avisar_a_varios(
        [{"user_id": destino}] if destino
        else await _staff_con(soporte.permiso_de_area(caso.get("area"))),
        title=f"Mensaje en {caso.get('numero')}",
        message=f"{caso.get('user_name')}: {soporte.asunto_desde(texto, 60)}",
        notification_type="soporte_caso",
    )
    return {"success": True, "reabierto": reabierto}


@router.post("/soporte/casos/{caso_id}/calificar")
async def calificar(caso_id: str, datos: Calificacion,
                    current_user: User = Depends(get_current_user)):
    """El cliente califica UN caso. Uno por caso, y sólo cerrado."""
    if datos.estrellas < 1 or datos.estrellas > 5:
        raise HTTPException(status_code=400, detail="La calificación va de 1 a 5")
    caso = await _mio(caso_id, current_user.user_id)
    problema = soporte.problema_para_calificar(caso)
    if problema:
        raise HTTPException(status_code=400, detail=problema)

    calificacion = {
        "estrellas": datos.estrellas,
        "comentario": (datos.comentario or "").strip()[:500],
        "en": _AHORA(),
    }
    await db.soporte_casos.update_one(
        {"caso_id": caso_id}, {"$set": {"calificacion": calificacion}})
    # El resumen por agente ya lee de `ratings`: se sigue escribiendo ahí para
    # no partir en dos la única vista de calidad que existe.
    await db.ratings.insert_one({
        "rating_id": f"rat_{uuid.uuid4().hex[:12]}",
        "channel": "caso",
        "case_ref": caso_id,
        "agent_id": caso.get("asignado_a"),
        "agent_name": caso.get("asignado_a_nombre"),
        "stars": datos.estrellas,
        "comment": calificacion["comentario"],
        "created_at": calificacion["en"],
    })
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════
# EL ASESOR
# ══════════════════════════════════════════════════════════════════════════

class Nota(BaseModel):
    nota: Optional[str] = Field(None, max_length=2000)


class RespuestaDelAsesor(BaseModel):
    mensaje: str = Field("", max_length=4000)
    adjunto: Optional[str] = None
    interno: bool = False


class CambioDeEstado(BaseModel):
    estado: str
    nota: Optional[str] = Field(None, max_length=2000)


class CambioDePrioridad(BaseModel):
    prioridad: str


class Transferencia(BaseModel):
    area: str
    asesor_id: Optional[str] = None
    nota: str = Field(..., min_length=5, max_length=2000)


class Escalamiento(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=2000)


class PedidoAArea(BaseModel):
    area: str
    detalle: str = Field(..., max_length=2000)


class RespuestaAlPedido(BaseModel):
    respuesta: str = Field(..., min_length=1, max_length=2000)


@router.get("/admin/soporte/areas")
async def areas(current_user: User = Depends(get_crm_user)):
    """Las áreas a las que se puede transferir o pedir algo."""
    return {"areas": [{"clave": k, "nombre": v[0]} for k, v in soporte.AREAS.items()]}


@router.get("/admin/soporte/asesores")
async def asesores(area: Optional[str] = None,
                   current_user: User = Depends(get_crm_user)):
    """Quién puede recibir una transferencia de esa área."""
    gente = await _staff_con(soporte.permiso_de_area(area) if area else None)
    return {"asesores": [{
        "user_id": p.get("user_id"),
        "nombre": p.get("name") or p.get("email"),
        "rol": p.get("role"),
        "area": (p.get("legajo") or {}).get("area"),
        "cargo": (p.get("legajo") or {}).get("cargo"),
    } for p in gente]}


@router.get("/admin/soporte/casos")
async def bandeja(estado: Optional[str] = None, area: Optional[str] = None,
                  mios: bool = False, buscar: Optional[str] = None,
                  current_user: User = Depends(get_crm_user)):
    """La bandeja del asesor, ya ordenada por lo que hay que hacer primero."""
    consulta = {}
    if estado == "abiertos" or estado is None:
        consulta["estado"] = {"$in": list(soporte.ABIERTOS)}
    elif estado != "todos":
        consulta["estado"] = estado
    if area:
        consulta["area"] = area
    if mios:
        consulta["asignado_a"] = current_user.user_id
    if buscar:
        aguja = {"$regex": buscar.strip()[:60], "$options": "i"}
        consulta["$or"] = [{"user_name": aguja}, {"user_email": aguja},
                           {"numero": aguja}, {"asunto": aguja}]

    casos = await db.soporte_casos.find(consulta, {"_id": 0}).to_list(300)
    ahora = _AHORA()
    casos.sort(key=lambda c: soporte.clave_de_orden(c, ahora))
    for c in casos:
        c["semaforo"] = soporte.semaforo(c, ahora)
        c["minutos_esperando"] = soporte.minutos_esperando(c, ahora)
    return {"casos": casos}


@router.get("/admin/soporte/casos/{caso_id}")
async def ver_caso(caso_id: str, current_user: User = Depends(get_crm_user)):
    """El caso completo: conversación, notas internas, pedidos y ficha del cliente.

    La ficha viene en la MISMA respuesta a propósito. Antes el asesor atendía a
    ciegas o abría otra pestaña para ver el saldo: dos pantallas para una sola
    conversación es como se contesta mal.
    """
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")

    mensajes = await db.soporte_mensajes.find(
        {"caso_id": caso_id}, {"_id": 0}).sort("creado_en", 1).to_list(500)
    pedidos = await db.soporte_pedidos.find(
        {"caso_id": caso_id}, {"_id": 0}).sort("creado_en", 1).to_list(50)

    cliente = await db.users.find_one(
        {"user_id": caso.get("user_id")},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "phone": 1,
         "balance_ris": 1, "verification_status": 1, "created_at": 1,
         "role": 1, "is_active": 1},
    ) or {}
    operaciones = await db.transactions.find(
        {"user_id": caso.get("user_id"), "hidden_from_admin": {"$ne": True}},
        {"_id": 0, "transaction_id": 1, "type": 1, "amount": 1, "status": 1,
         "created_at": 1, "currency": 1},
    ).sort("created_at", -1).to_list(8)
    otros = await db.soporte_casos.count_documents({
        "user_id": caso.get("user_id"), "caso_id": {"$ne": caso_id}})

    ahora = _AHORA()
    caso["semaforo"] = soporte.semaforo(caso, ahora)
    caso["minutos_esperando"] = soporte.minutos_esperando(caso, ahora)

    # Igual que del lado del cliente: la consola relee el caso cada seis
    # segundos y no tiene por qué escribir en cada vuelta.
    if caso.get("sin_leer_asesor"):
        await db.soporte_casos.update_one(
            {"caso_id": caso_id}, {"$set": {"sin_leer_asesor": 0}})

    return {
        "caso": caso,
        "mensajes": mensajes,
        "pedidos": pedidos,
        "cliente": cliente,
        "operaciones": operaciones,
        "casos_previos": otros,
    }


@router.post("/admin/soporte/casos/{caso_id}/tomar")
async def tomar(caso_id: str, current_user: User = Depends(get_crm_user)):
    """Toma el caso, de forma atómica: sólo uno puede."""
    resultado = await db.soporte_casos.update_one(
        {"caso_id": caso_id, "$or": [{"asignado_a": None},
                                     {"asignado_a": {"$exists": False}},
                                     {"asignado_a": ""}]},
        {"$set": {
            "asignado_a": current_user.user_id,
            "asignado_a_nombre": current_user.name or "Asesor",
            "asignado_en": _AHORA(),
            "estado": soporte.EN_CURSO,
            "actualizado_en": _AHORA(),
        }},
    )
    if resultado.modified_count == 1:
        await _registrar(caso_id, f"{current_user.name or 'Un asesor'} tomó el caso.",
                         current_user.user_id, current_user.name)
        return {"success": True}
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    if caso.get("asignado_a") == current_user.user_id:
        return {"success": True, "ya_era_mio": True}
    return {"success": False,
            "asignado_a_nombre": caso.get("asignado_a_nombre")}


@router.post("/admin/soporte/casos/{caso_id}/soltar")
async def soltar(caso_id: str, current_user: User = Depends(get_crm_user)):
    """Suelta el caso. Sólo quien lo atiende, o un super administrador."""
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    if (caso.get("asignado_a") and caso.get("asignado_a") != current_user.user_id
            and current_user.role != "super_admin"):
        raise HTTPException(status_code=403,
                            detail="Sólo quien atiende el caso puede soltarlo")
    await db.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
        "asignado_a": None, "asignado_a_nombre": None, "asignado_en": None,
        "estado": soporte.ABIERTO, "actualizado_en": _AHORA(),
    }})
    await _registrar(caso_id, f"{current_user.name or 'Un asesor'} soltó el caso: vuelve a la bandeja.",
                     current_user.user_id, current_user.name)
    return {"success": True}


@router.post("/admin/soporte/casos/{caso_id}/mensajes")
async def responder_asesor(caso_id: str, datos: RespuestaDelAsesor,
                           current_user: User = Depends(get_crm_user)):
    """Responde al cliente, o deja una nota interna que el cliente no ve."""
    caso = await _caso(caso_id)
    es_super = current_user.role == "super_admin"

    texto = (datos.mensaje or "").strip()
    if not texto and not datos.adjunto:
        raise HTTPException(status_code=400, detail="Escribí algo o adjuntá una imagen")

    # Una nota interna se puede dejar aunque el caso no sea tuyo: es contexto
    # para el equipo, no una respuesta al cliente. Lo que se protege es que al
    # cliente le conteste una sola persona.
    if not datos.interno:
        problema = soporte.problema_para_responder(caso, current_user.user_id, es_super)
        if problema:
            raise HTTPException(status_code=400, detail=problema)
    elif not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")

    ahora = _AHORA()
    await db.soporte_mensajes.insert_one({
        "mensaje_id": f"msg_{uuid.uuid4().hex[:12]}",
        "caso_id": caso_id,
        "autor": soporte.ASESOR,
        "autor_id": current_user.user_id,
        "autor_nombre": current_user.name or "Soporte",
        "interno": bool(datos.interno),
        "texto": texto,
        "adjunto": datos.adjunto,
        "creado_en": ahora,
    })

    if datos.interno:
        return {"success": True, "interno": True}

    cambios = {
        "actualizado_en": ahora,
        "ultimo_mensaje": soporte.asunto_desde(texto or "📎 Imagen", 120),
        "ultimo_mensaje_en": ahora,
        "ultimo_mensaje_de": soporte.ASESOR,
        "sin_leer_asesor": 0,
        "estado": soporte.ESPERANDO_CLIENTE,
    }
    if not caso.get("primera_respuesta_en"):
        cambios["primera_respuesta_en"] = ahora
    await db.soporte_casos.update_one(
        {"caso_id": caso_id}, {"$set": cambios, "$inc": {"sin_leer_cliente": 1}})

    await _avisar(
        user_id=caso.get("user_id"),
        title=f"Respuesta en tu caso {caso.get('numero')}",
        message=soporte.asunto_desde(texto or "Te enviamos una imagen", 80),
        notification_type="soporte_respuesta",
    )
    return {"success": True}


@router.post("/admin/soporte/casos/{caso_id}/estado")
async def cambiar_estado(caso_id: str, datos: CambioDeEstado,
                         current_user: User = Depends(get_crm_user)):
    """Mueve el caso de estado, si la transición es válida."""
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    if datos.estado not in soporte.ESTADOS:
        raise HTTPException(status_code=400, detail="Ese estado no existe")
    if not soporte.puede_pasar(caso.get("estado"), datos.estado):
        raise HTTPException(
            status_code=400,
            detail=f"Un caso {caso.get('estado')} no puede pasar a {datos.estado}.")

    # Cerrar tiene su propio permiso en el catálogo, y esta ruta hace más que
    # cerrar. Por eso el guard pide `support.respond` —lo que necesitan todos
    # los estados— y el cierre se comprueba acá.
    if datos.estado == soporte.CERRADO:
        from services import permisos
        if not permisos.tiene(current_user, "support.close"):
            raise HTTPException(
                status_code=403,
                detail="Te falta el permiso «support.close» para cerrar casos.")

    cambios = {"estado": datos.estado, "actualizado_en": _AHORA()}
    if datos.estado == soporte.CERRADO:
        cambios["cerrado_en"] = _AHORA()
        cambios["cerrado_por"] = current_user.user_id
        cambios["cerrado_por_nombre"] = current_user.name or "Asesor"
    await db.soporte_casos.update_one({"caso_id": caso_id}, {"$set": cambios})

    detalle = f" · {datos.nota.strip()}" if (datos.nota or "").strip() else ""
    await _registrar(caso_id,
                     f"{current_user.name or 'Un asesor'} pasó el caso a «{datos.estado}»{detalle}",
                     current_user.user_id, current_user.name)

    if datos.estado in (soporte.RESUELTO, soporte.CERRADO):
        await _avisar(
            user_id=caso.get("user_id"),
            title=f"Tu caso {caso.get('numero')} quedó {datos.estado}",
            message=("Si algo quedó sin resolver, escribinos y lo retomamos."
                     if datos.estado == soporte.RESUELTO
                     else "Podés calificar la atención desde el caso."),
            notification_type="soporte_estado",
        )
    return {"success": True, "estado": datos.estado}


@router.post("/admin/soporte/casos/{caso_id}/prioridad")
async def cambiar_prioridad(caso_id: str, datos: CambioDePrioridad,
                            current_user: User = Depends(get_crm_user)):
    if datos.prioridad not in soporte.PRIORIDADES:
        raise HTTPException(status_code=400, detail="Esa prioridad no existe")
    resultado = await db.soporte_casos.update_one(
        {"caso_id": caso_id},
        {"$set": {"prioridad": datos.prioridad, "actualizado_en": _AHORA()}})
    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    await _registrar(caso_id,
                     f"{current_user.name or 'Un asesor'} puso la prioridad en «{datos.prioridad}»",
                     current_user.user_id, current_user.name)
    return {"success": True}


@router.post("/admin/soporte/casos/{caso_id}/transferir")
async def transferir(caso_id: str, datos: Transferencia,
                     current_user: User = Depends(get_crm_user)):
    """Pasa el caso a otra área, y opcionalmente a un asesor concreto.

    LA NOTA ES OBLIGATORIA, y no es burocracia: una transferencia sin nota
    obliga al que recibe a leer toda la conversación para adivinar qué se
    espera de él, y mientras tanto el cliente espera. Es el momento exacto en
    que el contexto está en la cabeza de alguien y se pierde si no se escribe.
    """
    caso = await _caso(caso_id)
    es_super = current_user.role == "super_admin"
    problema = soporte.problema_para_transferir(caso, current_user.user_id, es_super)
    if problema:
        raise HTTPException(status_code=400, detail=problema)
    if not soporte.area_valida(datos.area):
        raise HTTPException(status_code=400, detail="Elegí un área de la lista")

    destino_nombre = None
    if datos.asesor_id:
        destino = await db.users.find_one({"user_id": datos.asesor_id},
                                          {"_id": 0, "name": 1, "role": 1})
        if not destino:
            raise HTTPException(status_code=404, detail="Ese asesor no existe")
        destino_nombre = destino.get("name") or "Asesor"

    await db.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
        "area": datos.area,
        "asignado_a": datos.asesor_id,
        "asignado_a_nombre": destino_nombre,
        "asignado_en": _AHORA() if datos.asesor_id else None,
        "estado": soporte.EN_CURSO if datos.asesor_id else soporte.ABIERTO,
        "actualizado_en": _AHORA(),
    }})

    hacia = destino_nombre or soporte.nombre_de_area(datos.area)
    await _registrar(
        caso_id,
        f"{current_user.name or 'Un asesor'} transfirió el caso a {hacia}: {datos.nota.strip()}",
        current_user.user_id, current_user.name)

    receptores = ([{"user_id": datos.asesor_id}] if datos.asesor_id
                  else await _staff_con(soporte.permiso_de_area(datos.area)))
    await _avisar_a_varios(
        receptores,
        title=f"Te transfirieron el caso {caso.get('numero')}",
        message=f"{current_user.name or 'Un asesor'}: {datos.nota.strip()[:80]}",
        notification_type="soporte_transferencia",
    )
    return {"success": True, "area": datos.area, "asignado_a": datos.asesor_id}


@router.post("/admin/soporte/casos/{caso_id}/escalar")
async def escalar(caso_id: str, datos: Escalamiento,
                  current_user: User = Depends(get_crm_user)):
    """Marca el caso como escalado, con motivo, y lo pone primero en la lista."""
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    if caso.get("estado") == soporte.CERRADO:
        raise HTTPException(status_code=400, detail="Un caso cerrado no se escala")

    await db.soporte_casos.update_one({"caso_id": caso_id}, {"$set": {
        "escalado": True,
        "escalado_motivo": datos.motivo.strip(),
        "escalado_por": current_user.user_id,
        "escalado_por_nombre": current_user.name or "Asesor",
        "escalado_en": _AHORA(),
        "prioridad": "urgente",
        "actualizado_en": _AHORA(),
    }})
    await _registrar(caso_id,
                     f"{current_user.name or 'Un asesor'} escaló el caso: {datos.motivo.strip()}",
                     current_user.user_id, current_user.name)

    for jefe in await db.users.find({"role": "super_admin"},
                                    {"_id": 0, "user_id": 1}).to_list(20):
        await _avisar(
            user_id=jefe.get("user_id"),
            title=f"Caso escalado {caso.get('numero')}",
            message=datos.motivo.strip()[:100],
            notification_type="soporte_escalado",
        )
    return {"success": True}


@router.post("/admin/soporte/casos/{caso_id}/pedidos")
async def pedir_a_area(caso_id: str, datos: PedidoAArea,
                       current_user: User = Depends(get_crm_user)):
    """Le pide algo a otra área SIN soltar el caso.

    Es la diferencia con transferir: el asesor sigue siendo el que le habla al
    cliente, y en paralelo pregunta a quien puede resolver. El cliente sigue
    hablando con la misma persona en vez de que lo pasen de mano en mano.
    """
    caso = await _caso(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Ese caso no existe")
    problema = soporte.problema_para_pedir(datos.area, datos.detalle)
    if problema:
        raise HTTPException(status_code=400, detail=problema)

    pedido = {
        "pedido_id": f"ped_{uuid.uuid4().hex[:12]}",
        "caso_id": caso_id,
        "caso_numero": caso.get("numero"),
        "area": datos.area,
        "detalle": datos.detalle.strip(),
        "estado": soporte.PEDIDO_PENDIENTE,
        "pedido_por": current_user.user_id,
        "pedido_por_nombre": current_user.name or "Asesor",
        "creado_en": _AHORA(),
        "respuesta": None,
    }
    await db.soporte_pedidos.insert_one(dict(pedido))
    await _registrar(
        caso_id,
        f"{current_user.name or 'Un asesor'} le pidió a {soporte.nombre_de_area(datos.area)}: {datos.detalle.strip()}",
        current_user.user_id, current_user.name)

    await _avisar_a_varios(
        await _staff_con(soporte.permiso_de_area(datos.area)),
        title=f"Pedido de soporte · {soporte.nombre_de_area(datos.area)}",
        message=f"{pedido['pedido_por_nombre']} ({caso.get('numero')}): {datos.detalle.strip()[:80]}",
        notification_type="soporte_pedido",
    )
    return {"success": True, "pedido": pedido}


@router.get("/admin/soporte/pedidos")
async def pedidos_de_mi_area(pendientes: bool = True,
                             current_user: User = Depends(get_crm_user)):
    """Los pedidos que le tocan a quien pregunta, según lo que puede resolver."""
    permisos = set(getattr(current_user, "permissions", None) or [])
    es_super = current_user.role == "super_admin"
    mias = [k for k, (_, permiso) in soporte.AREAS.items()
            if es_super or (permiso and permiso in permisos)]
    consulta = {"area": {"$in": mias}}
    if pendientes:
        consulta["estado"] = soporte.PEDIDO_PENDIENTE
    lista = await db.soporte_pedidos.find(consulta, {"_id": 0}).sort(
        "creado_en", 1).to_list(200)
    return {"pedidos": lista, "areas": mias}


@router.post("/admin/soporte/pedidos/{pedido_id}/responder")
async def responder_pedido(pedido_id: str, datos: RespuestaAlPedido,
                           current_user: User = Depends(get_crm_user)):
    """Contesta un pedido. La respuesta vuelve al caso como nota interna.

    Nota interna y no mensaje al cliente a propósito: lo que dice Finanzas o
    KYC es información de la casa, y traducirla al cliente es trabajo del
    asesor que lo está atendiendo, que sabe qué le preguntaron.
    """
    pedido = await db.soporte_pedidos.find_one({"pedido_id": pedido_id}, {"_id": 0})
    permisos = list(getattr(current_user, "permissions", None) or [])
    problema = soporte.problema_para_responder_pedido(
        pedido, permisos, current_user.role == "super_admin")
    if problema:
        raise HTTPException(status_code=400, detail=problema)

    ahora = _AHORA()
    await db.soporte_pedidos.update_one({"pedido_id": pedido_id}, {"$set": {
        "estado": soporte.PEDIDO_RESPONDIDO,
        "respuesta": datos.respuesta.strip(),
        "respondido_por": current_user.user_id,
        "respondido_por_nombre": current_user.name or "Área",
        "respondido_en": ahora,
    }})
    await _registrar(
        pedido["caso_id"],
        f"{soporte.nombre_de_area(pedido.get('area'))} respondió ({current_user.name or 'área'}): {datos.respuesta.strip()}",
        current_user.user_id, current_user.name)
    await db.soporte_casos.update_one(
        {"caso_id": pedido["caso_id"]}, {"$set": {"actualizado_en": ahora}})

    await _avisar(
        user_id=pedido.get("pedido_por"),
        title=f"Respondieron tu pedido · {pedido.get('caso_numero')}",
        message=datos.respuesta.strip()[:100],
        notification_type="soporte_pedido_respuesta",
    )
    return {"success": True}
