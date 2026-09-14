"""
services/lotes_de_pago.py — El grupo de órdenes que se paga de una vez.

POR QUE EL LOTE ES UN OBJETO Y NO UNA MARCA DE ESTADO

    La primera versión de esto guardaba la selección en el navegador y punto.
    Anda hasta que el agente cierra la pestaña, y entonces se perdió qué
    órdenes iban juntas. Peor: mientras un lote está en la calle pueden estar
    armándose otros, y una marca de estado no sabe cuál es cuál.

    Con el lote como objeto, «estas once órdenes son de este lote» sobrevive al
    navegador, y las imágenes de los comprobantes tienen dónde colgarse cuando
    lleguen.

EL TEXTO DEL ARCHIVO SE GUARDA, NO SE VUELVE A GENERAR

    Es la decisión menos obvia de este módulo y la más importante.

    Entre que el agente baja el archivo y vuelve con los comprobantes pasan
    minutos u horas. En el medio puede cambiar la tasa, o alguien puede
    corregir la cuenta de un beneficiario. Si el archivo se volviera a generar,
    el segundo no sería igual al que la persona ya pegó en el banco — y los
    comprobantes no cuadrarían contra nada.

    Lo que se pagó es lo que decía EL PAPEL. Así que el papel se guarda.

EL RECLAMO DE CADA ORDEN ES ATOMICO, Y LO QUE NO SE PUDO RECLAMAR SE DICE

    Dos agentes armando lotes al mismo tiempo no pueden llevarse la misma
    orden: se pagaría dos veces. Cada orden se reclama con una escritura
    condicional, y la que no se pudo reclamar NO se saltea en silencio — vuelve
    nombrada, con el motivo.

    Es la misma regla que el resto de este panel: un lote de diez cuando se
    pidieron once es un pago que no se hace y que nadie nota.

EL CLIENTE NO VE NADA DE ESTO

    `estado_admin` es un campo del panel: ninguna ruta del cliente lo devuelve.
    Para quien hizo la orden, sigue estando en proceso hasta que se paga.
"""
import logging
import uuid
from datetime import datetime, timezone

from services import archivo_de_pagos, auditoria, bancos_venezuela

logger = logging.getLogger(__name__)

COLECCION = "lotes_de_pago"

# Los estados de un lote. Cortos a propósito: mientras el lote sólo sirve para
# bajar el archivo, «abierto» y «cancelado» alcanzan. Cerrarlo contra los
# comprobantes es el paso siguiente y traerá el suyo.
ABIERTO = "abierto"
CANCELADO = "cancelado"

# La marca que lleva una orden mientras está en un lote. Sirve para sacarla de
# la cola de pendientes sin tocar su `status`, que es lo que ve el cliente.
EN_LOTE = "en_lote"

# Cuántas órdenes puede llevar un lote. El techo existe para que un error de
# selección —«todas»— no se convierta en un archivo de mil pagos que nadie
# revisa antes de pegar en el banco.
MAXIMO = 300


def _coleccion_y_filtro(db, flujo: str, orden_id: str):
    """Dónde vive esta orden. Mismo mapa que usa el panel para tomar y liberar."""
    if flujo in ("ris_ves", "ris_reais", "usdt_ves", "usdc_ves"):
        return db.transactions, {"transaction_id": orden_id, "type": "withdrawal"}
    if flujo == "ves_ris":
        return db.transactions, {"transaction_id": orden_id, "type": "recharge_ves"}
    if flujo == "btc_ves":
        return db.btc_remesas, {"remesa_id": orden_id}
    return None, None


async def _reclamar(db, orden, *, lote_id, quien_id, quien_nombre):
    """Toma una orden para este lote. Devuelve si se pudo.

    La condición `estado_admin != EN_LOTE` va DENTRO del filtro de la escritura:
    entre mirar y marcar no queda ventana para que otro agente se la lleve. Es
    la misma forma que usa `services/pagos_una_sola_vez`, y por el mismo motivo.
    """
    coleccion, filtro = _coleccion_y_filtro(db, orden.get("flujo"), orden.get("orden_id"))
    if coleccion is None:
        return False
    filtro = dict(filtro)
    filtro["estado_admin"] = {"$ne": EN_LOTE}
    resultado = await coleccion.update_one(filtro, {"$set": {
        "estado_admin": EN_LOTE,
        "lote_id": lote_id,
        "assigned_to": quien_id,
        "assigned_to_name": quien_nombre,
        "assigned_at": datetime.now(timezone.utc),
    }})
    return getattr(resultado, "modified_count", 0) == 1


async def _soltar(db, orden, *, lote_id):
    """Devuelve una orden a la cola. Sólo si sigue siendo de ESTE lote.

    El `lote_id` en el filtro no es adorno: sin él, cancelar un lote viejo
    podría soltar una orden que ya entró en otro, y esa orden se pagaría dos
    veces o ninguna.
    """
    coleccion, filtro = _coleccion_y_filtro(db, orden.get("flujo"), orden.get("orden_id"))
    if coleccion is None:
        return False
    filtro = dict(filtro)
    filtro["lote_id"] = lote_id
    resultado = await coleccion.update_one(filtro, {"$set": {
        "estado_admin": "pendiente", "lote_id": None,
        "assigned_to": None, "assigned_to_name": None, "assigned_at": None,
    }})
    return getattr(resultado, "modified_count", 0) == 1


async def _numero(db) -> str:
    """Un número corto y legible, para nombrar el lote en voz alta."""
    return f"L-{await db[COLECCION].count_documents({}) + 1:05d}"


async def armar(db, ordenes, *, banco_pagador: str, quien=None, request=None) -> dict:
    """Arma un lote con estas órdenes y guarda su archivo.

    `ordenes` son las normalizadas del panel, ya elegidas por el operador.
    """
    codigo = "".join(c for c in str(banco_pagador or "") if c.isdigit())
    if codigo not in bancos_venezuela.BANCOS:
        raise ValueError("El banco desde el que se paga no está en la lista")
    ordenes = list(ordenes)[:MAXIMO]
    if not ordenes:
        raise ValueError("No hay órdenes para armar el lote")

    lote_id = f"lote_{uuid.uuid4().hex[:12]}"
    quien_id = getattr(quien, "user_id", None)
    quien_nombre = (getattr(quien, "full_name", None) or getattr(quien, "name", None)
                    or getattr(quien, "email", None) or "—")

    tomadas, no_se_pudieron = [], []
    for orden in ordenes:
        if await _reclamar(db, orden, lote_id=lote_id, quien_id=quien_id,
                           quien_nombre=quien_nombre):
            tomadas.append(orden)
        else:
            no_se_pudieron.append(orden.get("display_id") or orden.get("orden_id"))

    if not tomadas:
        raise ValueError(
            "Ninguna de esas órdenes se pudo tomar: otro operador las puso en "
            "un lote mientras armabas éste. Actualizá la lista.")

    armado = archivo_de_pagos.armar(tomadas, banco_pagador=codigo)
    ahora = datetime.now(timezone.utc)
    lote = {
        "lote_id": lote_id,
        "numero": await _numero(db),
        "estado": ABIERTO,
        "creado_en": ahora,
        "creado_por": quien_id,
        "creado_por_nombre": quien_nombre,
        "banco_pagador": {"codigo": codigo, "nombre": bancos_venezuela.nombre_de(codigo)},
        # El archivo tal como se bajó. Ver el encabezado de este módulo: lo que
        # se pagó es lo que decía el papel, así que el papel se guarda.
        "texto": armado["texto"],
        "por_seccion": armado["por_seccion"],
        "sin_datos": armado["sin_datos"],
        # Una foto de cada orden al entrar al lote. Si mañana cambia la tasa o
        # alguien corrige una cuenta, esto sigue diciendo qué se mandó a pagar.
        "ordenes": [{
            "orden_id": o.get("orden_id"), "flujo": o.get("flujo"),
            "display_id": o.get("display_id"),
            "monto": (o.get("destino") or {}).get("valor"),
            "unidad": (o.get("destino") or {}).get("unidad"),
            "beneficiario": o.get("beneficiario"),
        } for o in tomadas],
    }
    await db[COLECCION].insert_one(dict(lote))

    await auditoria.registrar(
        db, "dinero.lote_armado", quien=quien, request=request,
        objetivo_tipo="lote", objetivo_id=lote_id,
        objetivo_desc=f"{lote['numero']}: {len(tomadas)} orden(es) por {lote['banco_pagador']['nombre']}",
        detalle={"ordenes": [o.get("orden_id") for o in tomadas],
                 "banco_pagador": codigo,
                 "no_se_pudieron_tomar": no_se_pudieron})

    logger.info("lote %s armado por %s: %s orden(es), %s no se pudieron tomar",
                lote["numero"], quien_id, len(tomadas), len(no_se_pudieron))

    salida = {k: v for k, v in lote.items() if k != "_id"}
    salida["no_se_pudieron_tomar"] = no_se_pudieron
    salida["total"] = len(tomadas)
    return salida


async def cancelar(db, lote_id: str, *, quien=None, request=None) -> dict:
    """Deshace un lote: las órdenes vuelven a la cola.

    Sólo vuelven las que siguen siendo de este lote. Una que ya se pagó, o que
    de alguna forma quedó en otro lado, se queda donde está y se informa.
    """
    lote = await db[COLECCION].find_one({"lote_id": lote_id})
    if not lote:
        raise ValueError("Ese lote no existe")
    if lote.get("estado") != ABIERTO:
        raise ValueError("Ese lote ya estaba cerrado o cancelado")

    devueltas, no_volvieron = [], []
    for orden in lote.get("ordenes") or []:
        if await _soltar(db, orden, lote_id=lote_id):
            devueltas.append(orden.get("orden_id"))
        else:
            no_volvieron.append(orden.get("display_id") or orden.get("orden_id"))

    await db[COLECCION].update_one({"lote_id": lote_id}, {"$set": {
        "estado": CANCELADO,
        "cancelado_en": datetime.now(timezone.utc),
        "cancelado_por": getattr(quien, "user_id", None),
    }})

    await auditoria.registrar(
        db, "dinero.lote_cancelado", quien=quien, request=request,
        objetivo_tipo="lote", objetivo_id=lote_id,
        objetivo_desc=f"{lote.get('numero')}: {len(devueltas)} orden(es) devuelta(s)",
        detalle={"devueltas": devueltas, "no_volvieron": no_volvieron})

    return {"lote_id": lote_id, "devueltas": len(devueltas),
            "no_volvieron": no_volvieron}


async def abiertos(db, limite: int = 50) -> list:
    """Los lotes que todavía están en la calle.

    Tienen que verse en alguna parte: sus órdenes salieron de la cola de
    pendientes, y si no hubiera dónde mirarlas, para el operador simplemente
    desaparecieron.
    """
    cursor = db[COLECCION].find(
        {"estado": ABIERTO},
        # Sin `texto` ni `ordenes`: la lista es para mirar de un vistazo, y el
        # archivo entero de cada lote la volvería pesada sin que nadie lo lea.
        {"_id": 0, "lote_id": 1, "numero": 1, "creado_en": 1,
         "creado_por_nombre": 1, "banco_pagador": 1, "por_seccion": 1,
         "sin_datos": 1, "ordenes": 1},
    ).sort("creado_en", -1).limit(limite)
    lotes = []
    async for doc in cursor:
        doc["total"] = len(doc.pop("ordenes", []) or [])
        doc["creado_en"] = (doc["creado_en"].isoformat()
                            if hasattr(doc.get("creado_en"), "isoformat") else None)
        lotes.append(doc)
    return lotes


async def archivo(db, lote_id: str) -> dict:
    """El archivo guardado de un lote, para volver a bajarlo igual."""
    lote = await db[COLECCION].find_one(
        {"lote_id": lote_id},
        {"_id": 0, "lote_id": 1, "numero": 1, "texto": 1, "banco_pagador": 1,
         "por_seccion": 1, "sin_datos": 1, "estado": 1})
    if not lote:
        raise ValueError("Ese lote no existe")
    return lote
