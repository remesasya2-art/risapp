"""
Migración: los casos asignados a alguien que no puede atenderlos.

QUE ARREGLA

    `transferir` preguntaba si el destinatario EXISTE, no si es del equipo —
    traía su `role` de la base y no lo miraba—. Con eso un caso se podía asignar
    a un cliente, incluido el del propio caso, y a un empleado dado de baja.

    Lo que pasaba entonces no era un error visible, y por eso es peor: el caso
    quedaba asignado, así que dejaba de figurar como libre en la bandeja, y
    quien lo tenía no podía abrir la consola porque el guardia de rol lo
    rechaza. El caso salía de la cola de TODOS y el cliente seguía esperando,
    sin que nada en ninguna pantalla dijera que algo andaba mal.

    La puerta ya está cerrada en `routes/soporte.py`. Esto es lo otro: los que
    quedaron atascados del lado de adentro antes del arreglo.

QUE HACE CON CADA UNO

    Lo devuelve a la cola —sin asignar, y `en_curso` vuelve a `abierto`— y deja
    una línea de sistema en el hilo contando qué pasó. La línea importa: el
    asesor que abra el caso mañana tiene que poder entender por qué figura como
    nuevo si la conversación venía por la mitad.

QUE NO TOCA

    Los casos CERRADOS. Un caso terminado asignado a quien ya no está no le
    hace daño a nadie, y reabrir la cola con historia vieja sí.

    Y el `asignado_a` de quien SI es del equipo, aunque no tenga el permiso del
    área: eso es una cuestión de reparto, no un atasco, y lo resuelve una
    transferencia.

Idempotente — una vez liberado, el caso ya no cumple la condición.

CUANDO CORRE

    Sola, al arrancar el servidor, igual que la de chats a casos. A mano:
        cd /app/backend && python3 -m migrations.003_casos_atascados
"""
import asyncio
import uuid
from datetime import datetime, timezone

from database import db
from services import soporte


async def _quien_no_puede_atender(ids):
    """De esos identificadores, los que NO son personal activo.

    Se resuelve en UNA consulta y no uno por uno: con la bandeja llena serían
    cientos de viajes a la base en el arranque.

    Un identificador que no existe en `users` también entra: un caso asignado a
    alguien que ya no está en la tabla está igual de atascado.
    """
    if not ids:
        return set()
    gente = await db.users.find(
        {"user_id": {"$in": list(ids)}},
        {"_id": 0, "user_id": 1, "role": 1, "is_active": 1},
    ).to_list(len(ids))
    pueden = {u["user_id"] for u in gente if soporte.es_personal(u)}
    return set(ids) - pueden


async def run() -> dict:
    resultado = {"revisados": 0, "liberados": 0}

    # Sólo los que siguen vivos y asignados. Un caso cerrado no estorba a nadie.
    casos = await db.soporte_casos.find(
        {"estado": {"$in": list(soporte.ABIERTOS)},
         "asignado_a": {"$nin": [None, ""]}},
        {"_id": 0, "caso_id": 1, "numero": 1, "estado": 1,
         "asignado_a": 1, "asignado_a_nombre": 1},
    ).to_list(5000)
    resultado["revisados"] = len(casos)
    if not casos:
        return resultado

    atascados = await _quien_no_puede_atender({c["asignado_a"] for c in casos})
    if not atascados:
        return resultado

    ahora = datetime.now(timezone.utc)
    for caso in casos:
        if caso["asignado_a"] not in atascados:
            continue

        nombre = caso.get("asignado_a_nombre") or "alguien que ya no atiende"
        # La línea ANTES de liberar. Si algo se corta en el medio, un caso en la
        # cola con una explicación de más es un ruido; uno liberado sin
        # explicación es un asesor preguntándose por qué un caso empezado
        # aparece como nuevo.
        await db.soporte_mensajes.insert_one({
            "mensaje_id": f"msg_{uuid.uuid4().hex[:12]}",
            "caso_id": caso["caso_id"],
            "autor": soporte.SISTEMA,
            "autor_id": None,
            "autor_nombre": None,
            "interno": True,
            "texto": (f"El caso estaba asignado a {nombre}, que no puede "
                      "atenderlo. Vuelve a la cola para que lo tome alguien "
                      "del equipo."),
            "adjunto": None,
            "creado_en": ahora,
        })

        cambios = {
            "asignado_a": None,
            "asignado_a_nombre": None,
            "asignado_en": None,
            "actualizado_en": ahora,
        }
        # `en_curso` significa «alguien lo está atendiendo», y no era cierto.
        if caso.get("estado") == soporte.EN_CURSO:
            cambios["estado"] = soporte.ABIERTO
        await db.soporte_casos.update_one(
            {"caso_id": caso["caso_id"]}, {"$set": cambios})
        resultado["liberados"] += 1

    return resultado


async def ejecutar_si_hace_falta() -> dict:
    """Lo mismo, decidiendo solo si hay algo que revisar.

    No lleva marca de «hecha y nunca más» a propósito: es barata —una consulta
    sobre un índice que ya existe (`asignado_a`, `estado`) y, sólo si hay casos
    asignados, una segunda por los usuarios— y lo que busca es una condición,
    no un paso de migración. Si alguna vez vuelve a aparecer un caso atascado
    por un camino que no previmos, el próximo arranque lo devuelve a la cola en
    vez de dejarlo perdido.
    """
    return await run()


if __name__ == "__main__":
    print(asyncio.run(run()))
