"""
services/aviso_de_tasa.py — Avisar cuando la tasa paralela venció.

POR QUE EXISTE

    La tasa USDI → VES se fija a mano, por decisión del operador. El precio de
    Bitcoin se pide en vivo y el dólar del BCV lo trae un raspador, pero ésta
    —la única que decide cuántos bolívares recibe el beneficiario— la escribe
    una persona en el panel.

    Como se pasó el límite de antigüedad, los envíos con Bitcoin se cortan.
    Eso es lo que se pidió: mejor cortar que cobrar con una tasa que ya no es.
    Pero un corte del que nadie se entera se convierte en «la aplicación no
    anda», y el operador se entera por un cliente que no pudo enviar.

LA PARTE QUE IMPORTA: AVISAR UNA VEZ, NO UNA POR CONSULTA

    La pantalla del envío consulta el precio cada diez segundos. Avisar en cada
    detección serían seis notificaciones por minuto, por cada persona con la
    pantalla abierta. A los cinco minutos nadie mira los avisos de esta
    aplicación, y el próximo —el que sí importaba— se pierde entre los otros.

    Por eso se deja una marca con la fecha de la tasa que se avisó. Mientras la
    tasa siga siendo esa, no se vuelve a avisar. Cuando el operador la actualiza
    cambia su fecha, la marca deja de coincidir, y el aviso vuelve a estar
    disponible para el próximo vencimiento. No hace falta borrar nada.

QUE PASA SI EL AVISO FALLA

    Nada. Avisar es un agregado sobre el corte, y el corte ya ocurrió. Si la
    base no contesta o no hay a quién notificar, se registra y se sigue: que
    falle el aviso no puede además tirar la consulta de precio.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CLAVE_MARCA = "aviso_tasa_vencida"

TITULO = "La tasa USDI → VES venció"


def _mensaje(edad):
    horas = int(edad.total_seconds() // 3600)
    cuanto = f"{horas} horas" if horas < 48 else f"{horas // 24} días"
    return (
        f"La tasa para envíos con Bitcoin se fijó hace {cuanto} y dejó de "
        "usarse. Los envíos con Bitcoin están cortados hasta que la "
        "actualices desde el panel. El resto de la aplicación sigue "
        "funcionando normalmente."
    )


async def avisar_si_hace_falta(db, fecha_de_la_tasa, edad):
    """Avisa a los super administradores, una vez por tasa vencida.

    `fecha_de_la_tasa` identifica a la tasa: dos vencimientos distintos tienen
    fechas distintas, y el mismo vencimiento consultado cien veces tiene la
    misma. Es lo que hace que este llamado se pueda hacer en cada consulta sin
    que el operador reciba cien avisos.
    """
    try:
        marca = await db.config.find_one({"clave": CLAVE_MARCA})
        if marca and marca.get("valor") == fecha_de_la_tasa.isoformat():
            return 0

        # La marca se escribe ANTES de notificar. Si se escribiera después, dos
        # consultas simultáneas —y son varias por segundo— pasarían las dos por
        # la comprobación de arriba y avisarían las dos.
        await db.config.update_one(
            {"clave": CLAVE_MARCA},
            {"$set": {
                "clave": CLAVE_MARCA,
                "valor": fecha_de_la_tasa.isoformat(),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

        from services.notifications import create_notification

        cuantos = 0
        async for admin in db.users.find({"role": "super_admin"}):
            await create_notification(
                user_id=admin["user_id"],
                title=TITULO,
                message=_mensaje(edad),
                notification_type="warning",
                data={"motivo": "tasa_usd_ves_btc_vencida",
                      "fijada_en": fecha_de_la_tasa.isoformat()},
            )
            cuantos += 1

        if not cuantos:
            logger.error("La tasa venció y no hay ningún super administrador "
                         "a quien avisar.")
        else:
            logger.warning(f"Tasa USDI→VES vencida: se avisó a {cuantos} "
                           "super administrador(es).")
        return cuantos
    except Exception as e:
        # Avisar es un agregado sobre el corte, y el corte ya pasó.
        logger.error(f"No se pudo avisar de la tasa vencida: {type(e).__name__}")
        return 0
