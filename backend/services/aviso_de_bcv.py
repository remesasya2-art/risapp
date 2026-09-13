"""
services/aviso_de_bcv.py — Avisar cuando la tasa del BCV quedó vieja.

POR QUE EXISTE

    El raspador del BCV se rompió y nadie se enteró durante semanas. No hubo
    ningún síntoma visible: la contabilidad siguió calculando, con el último
    número que había traído, congelado. Y ese número le ganaba al que el
    operador cargaba a mano en el panel, así que ni cambiar la tasa servía para
    darse cuenta.

    Un fallo sin síntoma es el peor tipo de fallo. Ahora la tasa vieja pierde
    contra la del panel —eso está en `accounting_engine`— y además se avisa.

LA PARTE QUE IMPORTA: AVISAR UNA VEZ, NO UNA POR REVISION

    El revisor corre cada hora —`server.py` arranca el planificador con
    `interval_hours=1`, y no con el 3 que dice la constante del módulo—. Avisar
    en cada pasada serían veinticuatro avisos por día por el mismo problema, y
    a los dos días nadie mira los avisos de esta aplicación.

    Por eso se deja una marca con la fecha del raspado que se avisó. Mientras el
    raspado siga siendo ese, no se vuelve a avisar. Cuando el raspador se
    recupera, la fecha cambia, la marca deja de coincidir, y el aviso vuelve a
    estar disponible para el próximo vencimiento. No hace falta borrar nada.

    Es el mismo mecanismo que `services/aviso_de_tasa.py`, y por el mismo
    motivo.

QUE PASA SI EL AVISO FALLA

    Nada que importe. Avisar es un agregado: la protección de verdad es que la
    contabilidad ya dejó de usar el número vencido. Si la base no contesta o no
    hay a quién notificar, se registra y se sigue.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CLAVE_MARCA = "aviso_bcv_vencida"

TITULO = "La tasa del BCV quedó vieja"


def _cuanto(edad_horas):
    if edad_horas is None:
        return "sin fecha"
    horas = int(edad_horas)
    return f"{horas} horas" if horas < 48 else f"{horas // 24} días"


def _mensaje(estado):
    if estado.get("edad_horas") is None:
        detalle = ("El último dato del Banco Central no tiene fecha, así que no "
                   "se puede saber si sirve.")
    else:
        detalle = (f"El último dato del Banco Central es de hace "
                   f"{_cuanto(estado['edad_horas'])}, y el límite está en "
                   f"{estado['horas_de_vigencia']} horas.")
    return (
        f"{detalle} La contabilidad dejó de usarlo y está usando el dólar que "
        "está cargado a mano en Tasas. Revisá que ese número esté al día. Si el "
        "raspador sigue sin traer nada, el registro del servidor dice por qué."
    )


async def avisar_si_vencio(db, estado) -> int:
    """Avisa a los super administradores, una vez por raspado vencido.

    `estado` es lo que devuelve `bcv_scraper.vigencia`. La fecha del raspado
    identifica el problema: dos vencimientos distintos tienen fechas distintas,
    y el mismo vencimiento revisado cien veces tiene la misma. Es lo que hace
    que esto se pueda llamar en cada revisión sin inundar a nadie.
    """
    if not estado or not estado.get("vencida"):
        return 0

    # Sin fecha no hay con qué marcar, y marcar con un texto fijo taparía el
    # aviso para siempre. Se usa la fecha cuando está; cuando no, un sello que
    # cambia una vez por día, para que el aviso se repita pero no cada tres
    # horas.
    sello = estado.get("fetched_at") or (
        "sin-fecha:" + datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    try:
        marca = await db.config.find_one({"clave": CLAVE_MARCA})
        if marca and marca.get("valor") == sello:
            return 0

        # La marca se escribe ANTES de notificar, igual que en
        # `aviso_de_tasa.py`: si se escribiera después, dos revisiones que se
        # cruzan pasarían las dos por la comprobación de arriba.
        await db.config.update_one(
            {"clave": CLAVE_MARCA},
            {"$set": {
                "clave": CLAVE_MARCA,
                "valor": sello,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

        from services.notifications import avisar_al_personal

        # Sólo super administradores: la tasa de reemplazo (`usd_to_ves`) y el
        # ajuste de vigencia se editan con permisos que un `admin` común no
        # tiene. Quien recibe el aviso es quien puede arreglarlo.
        cuantos = await avisar_al_personal(
            title=TITULO,
            message=_mensaje(estado),
            notification_type="warning",
            solo_super_admin=True,
            data={"motivo": "bcv_vencida",
                  "edad_horas": estado.get("edad_horas"),
                  "raspado_en": estado.get("fetched_at")},
        )

        if not cuantos:
            logger.error("La tasa del BCV venció y no hay ningún super "
                         "administrador a quien avisar.")
        else:
            logger.warning(f"Tasa del BCV vencida ({_cuanto(estado.get('edad_horas'))}): "
                           f"se avisó a {cuantos} super administrador(es).")
        return cuantos
    except Exception as e:
        # Avisar es un agregado sobre la protección, y la protección ya actuó.
        logger.error(f"No se pudo avisar de la tasa del BCV vencida: {type(e).__name__}")
        return 0
