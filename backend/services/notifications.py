"""
services/notifications.py — Los avisos dentro de la aplicación.

DOS CLASES DE AVISO, Y NO SON LO MISMO

    Un aviso PERSONAL le habla a alguien de lo suyo: «te aprobaron el KYC»,
    «llegó tu recarga». Lo lee el dueño de la cuenta y nadie más.

    Un aviso de TRABAJO le habla al equipo de algo que hay que atender: «hay un
    KYC nuevo por revisar», «la tasa está vencida». No es de nadie en
    particular: es de quien pueda resolverlo.

    Hasta ahora los dos salían por la misma puerta y caían en la misma lista.
    El campo `ambito` los separa, que es lo que necesita el panel para tener su
    propia bandeja. Los avisos que ya están guardados no lo tienen; al leerlos,
    la ausencia se lee como «personal», que es lo que eran casi todos.

POR QUE EXISTE `avisar_al_personal`

    Porque antes había CINCO formas de avisarle al equipo, cada una escrita a
    mano en su archivo, y las cinco distintas:

        routes/misc.py             sólo super_admin, tope 50
        routes/btc_lightning.py    sólo super_admin, sin tope
        routes/btc_lightning.py    admin + super_admin, tope 50
        services/push_notifications  admin + super_admin, tope 100 (nadie la usaba)
        services/aviso_de_tasa.py  sólo super_admin, sin tope

    NINGUNA miraba `is_active`. Un administrador dado de baja seguía recibiendo
    las alertas de tasa, las operaciones con Bitcoin y los KYC nuevos después
    de irse de la empresa.

    Y los roles no seguían ningún criterio. El aviso de una orden de Bitcoin
    pagada le llegaba también a los `admin`, que no pueden abrir el panel de
    Bitcoin: un aviso sobre algo que no pueden atender.

QUIEN RECIBE: EL QUE PUEDE ACTUAR

    El destinatario se elige por PERMISO, no por rol. «Quién puede aprobar un
    KYC» es una pregunta que la tabla de permisos ya responde
    (`services/permisos.py`), y responde bien: cubre a cualquiera que mañana
    tenga ese permiso, sin tocar esta lista.

    El super administrador entra siempre: es quien destraba.

    Para lo que NO tiene permiso propio —el panel de Bitcoin lo guarda
    `get_super_admin` directamente— se pide `solo_super_admin=True`, que dice
    lo mismo que dice esa puerta.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Los dos ámbitos. Un aviso sin `ambito` es de los viejos y se lee como
# personal: es lo que eran casi todos antes de que existiera esta separación.
PERSONAL = "personal"
TRABAJO = "trabajo"

# Quién puede tener un aviso de trabajo. Mismo criterio que
# `services/soporte.es_personal`: un cliente no atiende nada, y un empleado
# dado de baja tampoco, porque ya no entra al panel.
ROLES_DEL_PERSONAL = ("agent", "admin", "super_admin")

# Cuánta gente puede recibir un mismo aviso. No es paginación: es un techo de
# cordura para que un error de configuración —todos los usuarios marcados como
# admin— no convierta un aviso en miles de escrituras.
_TOPE_DESTINATARIOS = 200


async def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",
    data: dict = None,
    ambito: str = PERSONAL,
) -> str:
    """Guarda un aviso para una persona y le manda el push.

    Si esta función RETORNA, el aviso está guardado. El push es otra cosa: es
    una cortesía que sale a un servicio ajeno, y su caída no puede llevarse
    puesta la operación que disparó el aviso.

    Antes no era así: un fallo del push subía hasta el que llamó y devolvía un
    500 sobre un trabajo YA hecho. `routes/soporte.py` lo envolvía en un `try`
    por ese motivo; los otros sesenta y nueve lugares, no.
    """
    from database import db

    notification_id = f"notif_{uuid.uuid4().hex[:12]}"

    await db.notifications.insert_one({
        "notification_id": notification_id,
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "ambito": ambito,
        "data": data or {},
        "read": False,
        "created_at": datetime.now(timezone.utc),
    })

    await _push_sin_romper(user_id, title, message, data)

    # Y el correo, para las clases de aviso que lo llevan: todo lo que mueve
    # dinero, y cada actualización de un paquete. La regla vive en una tabla
    # —`services/avisos_por_correo.py`— y no repartida por los dieciocho
    # lugares que avisan.
    #
    # Sólo lo personal: llenarle la casilla de trabajo a cada operador es la
    # forma más rápida de que deje de mirar los correos de la aplicación.
    if ambito == PERSONAL:
        from services.avisos_por_correo import acompanar
        # `data` va también: es de donde sale el número de la operación, y sin
        # él el correo no puede armar el comprobante y sale como un párrafo.
        await acompanar(user_id, title, message, notification_type, data)

    return notification_id


async def _push_sin_romper(user_id, title, message, data):
    """El push, con su caída contenida acá adentro."""
    try:
        from services.push_notifications import send_push_to_user
        await send_push_to_user(user_id, title, message, data)
    except Exception as e:                                    # pragma: no cover
        logger.warning("no se pudo mandar el push a %s: %s", user_id, e)


async def personal_que_puede(permiso: str | None = None, *,
                             solo_super_admin: bool = False) -> list[dict]:
    """Quién del equipo puede ACTUAR sobre esto.

    Sale de la tabla de permisos que ya gobierna el trabajo, no de una lista
    aparte que hay que acordarse de actualizar. El super administrador entra
    siempre: es quien destraba.

    `is_active` es lo que faltaba en las cinco versiones sueltas de esto.
    """
    from database import db

    if solo_super_admin:
        consulta = {"role": "super_admin", "is_active": {"$ne": False}}
    else:
        consulta = {"role": {"$in": list(ROLES_DEL_PERSONAL)},
                    "is_active": {"$ne": False}}
        if permiso:
            consulta = {"$and": [consulta, {"$or": [
                {"role": "super_admin"},
                {"permissions": permiso},
            ]}]}

    return await db.users.find(
        consulta, {"_id": 0, "user_id": 1, "name": 1, "role": 1},
    ).limit(_TOPE_DESTINATARIOS).to_list(_TOPE_DESTINATARIOS)


async def avisar_al_personal(*, title: str, message: str,
                             notification_type: str = "info",
                             permiso: str | None = None,
                             solo_super_admin: bool = False,
                             data: dict = None) -> int:
    """Un aviso de TRABAJO a todo el que pueda resolverlo. Devuelve a cuántos.

    NO LEVANTA NUNCA. Quien la llama acaba de terminar un trabajo de verdad —un
    KYC recibido, una orden pagada— y ese trabajo ya está guardado. Que no se
    pueda avisar es un problema que se anota, no uno que se devuelve.

    Los avisos salen TODOS A LA VEZ. De a uno, avisarle a veinte
    administradores son veinte viajes encadenados al servicio de push, y el
    cliente que disparó la acción mira la ruedita hasta que termina el último.
    """
    try:
        gente = await personal_que_puede(permiso, solo_super_admin=solo_super_admin)
    except Exception as e:                                    # pragma: no cover
        logger.error("no se pudo averiguar a quién avisar (%s): %s", title, e)
        return 0

    if not gente:
        # Que no haya nadie es una condición de configuración, no un caso
        # normal: alguien tiene que poder atender esto.
        logger.warning("nadie puede recibir el aviso %r (permiso=%r, "
                       "solo_super_admin=%s)", title, permiso, solo_super_admin)
        return 0

    async def _uno(persona):
        try:
            await create_notification(
                user_id=persona["user_id"], title=title, message=message,
                notification_type=notification_type, data=data, ambito=TRABAJO)
            return True
        except Exception as e:                                # pragma: no cover
            logger.warning("no se pudo avisar a %s: %s", persona.get("user_id"), e)
            return False

    resultados = await asyncio.gather(*[_uno(p) for p in gente])
    return sum(1 for ok in resultados if ok)
