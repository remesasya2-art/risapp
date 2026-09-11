"""
Migración: los chats de soporte pasan a ser casos.

QUE MUEVE

    `support_chats` tenía UN documento por usuario, con toda su historia
    mezclada. Cada uno se convierte en UN caso —el primero de esa persona— con
    sus mensajes adentro, conservando fechas, autores y adjuntos.

    No se intenta partir la historia vieja en varias consultas: no hay dato
    para hacerlo bien y adivinar dónde termina una y empieza otra dejaría
    conversaciones cortadas al medio. La historia vieja queda como un caso, y
    lo nuevo ya nace separado.

QUE NO TOCA

    `support_chats` y `support_messages` quedan intactas. La migración sólo
    escribe en las colecciones nuevas: si algo sale mal, no se perdió nada y se
    puede volver a correr.

ANTES DE CORRERLA

    Los índices de `soporte_mensajes` tienen que existir —en particular el
    único sobre `mensaje_id`, que es la red que hay debajo de todo esto—. Los
    crea `services/soporte_indices.py` en cada arranque de la aplicación. Si
    la corrés contra una base donde la aplicación nunca levantó, corré primero:

        python3 -c "import asyncio; from services.soporte_indices import \\
            asegurar_indices; print(asyncio.run(asegurar_indices()))"

    Y ANTES QUE ESO: que nadie siga escribiendo en `support_chats`. La
    idempotencia de esta migración es POR CHAT, no por mensaje: un chat ya
    migrado se saltea entero, así que un mensaje que entre por la puerta vieja
    DESPUES de la corrida no lo trae una segunda corrida. La puerta vieja
    —`routes/support.py`— ya está apagada; esto queda escrito por si alguien
    la reabre.

Idempotente — se puede correr las veces que haga falta.

Uso:
    cd /app/backend && python3 -m migrations.002_chats_a_casos --ensayo   # cuenta, no escribe
    cd /app/backend && python3 -m migrations.002_chats_a_casos            # migra
"""
import asyncio
import hashlib
import sys
from datetime import datetime, timezone

from pymongo.errors import BulkWriteError

from database import db
from services import soporte


async def _numero(secuencia):
    return soporte.numero_legible(secuencia)


async def _insertar(faltan):
    """Mete los mensajes que faltan. Devuelve (cuántos entraron, repetidos).

    `ordered=False` hace que Mongo siga después de un duplicado en vez de
    frenar en el primero — pero igual LEVANTA `BulkWriteError` al terminar.
    Sin este try, dos mensajes viejos que compartan `message_id` —pasa: la
    llave la ponía quien insertaba, y no siempre estuvo— cortan la corrida
    entera y dejan sin migrar todos los chats que venían después.

    Lo que entró, entró: son los mensajes con llave distinta, y el chequeo de
    `ya_movidos` hace que la próxima corrida no los duplique. Lo que se
    descarta es exactamente lo que ya estaba con esa misma llave.
    """
    try:
        await db.soporte_mensajes.insert_many(faltan, ordered=False)
        return len(faltan), []
    except BulkWriteError as e:
        detalles = e.details or {}
        errores = detalles.get("writeErrors") or []
        # Un error que NO sea de llave repetida (11000) es otra cosa —la base
        # sin espacio, un documento inválido— y ahí sí hay que frenar: seguir
        # sería migrar a medias sin decirlo.
        otros = [w for w in errores if w.get("code") != 11000]
        if otros:
            raise
        repetidos = [(w.get("op") or {}).get("mensaje_id") for w in errores]
        return detalles.get("nInserted", 0), [r for r in repetidos if r]


async def ensayo() -> dict:
    """Cuenta qué haría, sin escribir una sola línea.

    Es una función aparte y no un `if` adentro de `run()` a propósito: un
    ensayo que comparte camino con la corrida real es un ensayo a un `if` de
    distancia de escribir en producción. Acá no hay ninguna escritura que
    desactivar, porque no hay ninguna.
    """
    chats = await db.support_chats.find({}, {"_id": 0}).to_list(10000)
    sin_user = sum(1 for c in chats if not c.get("user_id"))
    ya, nuevos, mensajes = 0, 0, 0
    for chat in chats:
        user_id = chat.get("user_id")
        if not user_id:
            continue
        if await db.soporte_casos.find_one({"origen_chat": user_id}, {"_id": 0}):
            ya += 1
            continue
        nuevos += 1
        mensajes += await db.support_messages.count_documents({"user_id": user_id})

    contador = await db.contadores.find_one({"_id": "soporte_casos"})
    desde = (contador or {}).get("valor") or 0
    return {
        "chats": len(chats),
        "chats_sin_user_id": sin_user,
        "casos_a_crear": nuevos,
        "mensajes_a_mover": mensajes,
        "ya_migrados": ya,
        "numeros": f"{soporte.numero_legible(desde + 1)}..{soporte.numero_legible(desde + nuevos)}"
                   if nuevos else "—",
    }


async def run() -> dict:
    resultado = {"casos_creados": 0, "mensajes_movidos": 0, "ya_estaban": 0,
                 "mensajes_repetidos": []}

    # Se arranca la numeración donde esté el contador, para que la migración no
    # pise números de casos abiertos después de ella.
    contador = await db.contadores.find_one({"_id": "soporte_casos"})
    siguiente = (contador or {}).get("valor") or 0

    chats = await db.support_chats.find({}, {"_id": 0}).to_list(10000)
    for chat in chats:
        user_id = chat.get("user_id")
        if not user_id:
            continue

        # Idempotencia: si ya se migró este chat, no se vuelve a crear.
        ya = await db.soporte_casos.find_one({"origen_chat": user_id}, {"_id": 0})
        if ya:
            resultado["ya_estaban"] += 1
            continue

        mensajes = await db.support_messages.find(
            {"user_id": user_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)

        primero = mensajes[0] if mensajes else None
        creado = (chat.get("created_at") or (primero or {}).get("created_at")
                  or datetime.now(timezone.utc))
        cerrado = chat.get("status") == "closed"

        # La primera respuesta del equipo, para que el histórico no aparezca
        # todo en rojo en el semáforo del primer día.
        primera = next((m.get("created_at") for m in mensajes
                        if m.get("sender") == "admin"), None)

        siguiente += 1
        # El identificador del caso sale del chat y no de un sorteo: si una
        # corrida se corta después de mover los mensajes y antes de crear el
        # caso, la siguiente tiene que reusar EL MISMO, o los mensajes ya
        # movidos quedan colgando de un caso que no existe y el caso nuevo
        # nace vacío —los reinsertos se descartan por repetidos—.
        caso_id = "caso_" + hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:12]
        # Los mensajes ANTES que el caso, y no al revés. Si algo falla en el
        # medio, un caso sin su conversación es peor que unos mensajes
        # huérfanos: la idempotencia va por `origen_chat`, así que el caso ya
        # creado hace que la re-corrida SALTEE el chat y su historia se pierde
        # para siempre. Al revés, la re-corrida lo termina.
        if mensajes:
            # El identificador viejo si lo tiene; si no, uno derivado del chat
            # y la posición. `msg_{i}` a secas se repetía entre chats
            # distintos —el primer mensaje de todos era `msg_0`— y el índice
            # único de `soporte_mensajes` frenaba la inserción entera del
            # segundo chat en adelante.
            candidatos = [{
                "mensaje_id": m.get("message_id") or f"msg_{user_id}_{i}",
                "caso_id": caso_id,
                "autor": (soporte.ASESOR if m.get("sender") == "admin"
                          else soporte.CLIENTE),
                "autor_id": m.get("admin_id") or m.get("user_id"),
                "autor_nombre": m.get("admin_name") or m.get("user_name"),
                "interno": False,
                "texto": m.get("message") or "",
                "adjunto": m.get("image"),
                "creado_en": m.get("created_at") or creado,
            } for i, m in enumerate(mensajes)]

            # Se saltean los que ya están de una corrida anterior que se cortó.
            # Se mira acá y no se confía en el índice único: la migración tiene
            # que ser idempotente por sí misma, porque puede correrse en una
            # base donde los índices todavía no se crearon.
            ya_movidos = set(await db.soporte_mensajes.distinct(
                "mensaje_id", {"caso_id": caso_id}))
            faltan = [d for d in candidatos if d["mensaje_id"] not in ya_movidos]
            if faltan:
                entraron, repetidos = await _insertar(faltan)
                resultado["mensajes_movidos"] += entraron
                resultado["mensajes_repetidos"].extend(repetidos)

        await db.soporte_casos.insert_one({
            "caso_id": caso_id,
            "numero": await _numero(siguiente),
            "origen_chat": user_id,
            "user_id": user_id,
            "user_name": chat.get("user_name") or "Usuario",
            "user_email": chat.get("user_email"),
            "motivo": "otro",
            "asunto": soporte.asunto_desde(
                (primero or {}).get("message") or chat.get("last_message") or "Conversación anterior"),
            "estado": soporte.CERRADO if cerrado else soporte.EN_CURSO,
            "prioridad": "normal",
            "area": "soporte",
            "asignado_a": chat.get("assigned_to"),
            "asignado_a_nombre": chat.get("assigned_to_name"),
            "asignado_en": chat.get("assigned_at"),
            "escalado": False,
            "creado_en": creado,
            "actualizado_en": chat.get("last_message_at") or creado,
            "ultimo_mensaje": chat.get("last_message"),
            "ultimo_mensaje_en": chat.get("last_message_at") or creado,
            "ultimo_mensaje_de": soporte.CLIENTE,
            "primera_respuesta_en": primera,
            "cerrado_en": chat.get("closed_at") if cerrado else None,
            "sin_leer_asesor": chat.get("unread_count") or 0,
            "sin_leer_cliente": 0,
            # La calificación vieja era del usuario, no del caso. Se conserva
            # sobre este caso, que es la conversación que se calificó.
            "calificacion": ({"estrellas": chat.get("rating_stars"),
                              "comentario": "", "en": chat.get("closed_at")}
                             if chat.get("rated") else None),
        })
        resultado["casos_creados"] += 1

    if resultado["casos_creados"]:
        await db.contadores.update_one(
            {"_id": "soporte_casos"}, {"$set": {"valor": siguiente}}, upsert=True)

    return resultado


if __name__ == "__main__":
    if "--ensayo" in sys.argv or "--dry-run" in sys.argv:
        print("ENSAYO — no se escribe nada:")
        print(asyncio.run(ensayo()))
    else:
        print(asyncio.run(run()))
