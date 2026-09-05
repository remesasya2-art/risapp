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

Idempotente — se puede correr las veces que haga falta.

Uso:
    cd /app/backend && python3 -m migrations.002_chats_a_casos
"""
import asyncio
from datetime import datetime, timezone

from database import db
from services import soporte


async def _numero(secuencia):
    return soporte.numero_legible(secuencia)


async def run() -> dict:
    resultado = {"casos_creados": 0, "mensajes_movidos": 0, "ya_estaban": 0}

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
        caso_id = soporte.nuevo_id()
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

        if mensajes:
            await db.soporte_mensajes.insert_many([{
                "mensaje_id": m.get("message_id") or f"msg_{i}",
                "caso_id": caso_id,
                "autor": (soporte.ASESOR if m.get("sender") == "admin"
                          else soporte.CLIENTE),
                "autor_id": m.get("admin_id") or m.get("user_id"),
                "autor_nombre": m.get("admin_name") or m.get("user_name"),
                "interno": False,
                "texto": m.get("message") or "",
                "adjunto": m.get("image"),
                "creado_en": m.get("created_at") or creado,
            } for i, m in enumerate(mensajes)])
            resultado["mensajes_movidos"] += len(mensajes)

    if resultado["casos_creados"]:
        await db.contadores.update_one(
            {"_id": "soporte_casos"}, {"$set": {"valor": siguiente}}, upsert=True)

    return resultado


if __name__ == "__main__":
    print(asyncio.run(run()))
