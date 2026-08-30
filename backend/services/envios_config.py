"""
services/envios_config.py — Guardar configuración sin romper producción.

LAS TRES REGLAS DEL PANEL
    1. **Cada bloque tiene su esquema y se valida al guardar.** Un valor que no
       valida se rechaza con un mensaje que dice qué campo está mal. Nunca se
       escribe JSON libre en Mongo.
    2. **Todo cambio queda auditado** en `centro_gestion_log`, la colección que
       el repositorio ya tiene: quién, cuándo, qué bloque, valor anterior y valor
       nuevo.
    3. **Lo que afecta plata se versiona, no se pisa.** Las tarifas ya funcionan
       así; los datos bancarios también (§4.6). El resto se sobrescribe, pero con
       su registro de auditoría.

EL BUG CLASICO DE TODO PANEL DE CONFIGURACION
    La configuración se lee en cada cotización, así que hay que cachearla. Y ahí
    aparece el problema: **el super administrador cambia un precio, guarda, y no
    pasa nada** — el proceso sigue sirviendo el valor viejo hasta que Railway
    reinicie. Pasa una semana antes de que alguien lo note.

    La solución es barata si se hace desde el principio: caché con TTL corto e
    **invalidación explícita al guardar**. Las dos cosas, no una. Y la pantalla,
    después de guardar, vuelve a leer del servidor y muestra el valor efectivo —
    no el que el admin acaba de tipear.

EL LOG NO PUEDE VOLVERSE UNA COPIA DEL DATO SENSIBLE
    La auditoría la lee más gente de la que puede editar una cuenta bancaria. Un
    número de cuenta completo ahí es el mismo dato en un lugar con menos control
    que el original, así que se enmascara antes de escribirlo. Se guarda lo
    suficiente para responder "¿cambió?" y "¿a cuál?", no para copiarlo.
"""

import logging
import uuid
from datetime import datetime, timezone

from models.envios_config import ESQUEMAS, CAMPOS_SENSIBLES

logger = logging.getLogger(__name__)

SETTING_PREFIJO = "envios_"


def enmascarar(valor):
    """Deja un dato sensible reconocible pero no copiable: los últimos cuatro.

    Recorre en profundidad: un número de cuenta anidado dentro de la ficha de un
    transportista tiene que salir enmascarado igual que uno suelto.
    """
    if isinstance(valor, dict):
        return {k: ("****" + str(v)[-4:] if k in CAMPOS_SENSIBLES and v else enmascarar(v))
                for k, v in valor.items()}
    if isinstance(valor, list):
        return [enmascarar(v) for v in valor]
    return valor


def diferencias(antes, despues) -> dict:
    """Qué campos cambiaron, con su valor viejo y nuevo, ya enmascarados.

    Guardar el documento entero dos veces hace que el log crezca y que nadie lo
    lea. Guardar solo lo que cambió lo vuelve útil: se abre y se ve la línea.
    """
    antes = antes or {}
    despues = despues or {}
    salida = {}
    for clave in sorted(set(antes) | set(despues)):
        # Los metadatos del propio guardado no son un cambio de configuración:
        # si entraran, cada guardado registraría que cambió la fecha del guardado.
        # Los metadatos del propio guardado y los de creación. Sin los de
        # creación, cada edición de una ficha registraba que `colaborador_id`,
        # `creado_at` y `creado_por` pasaron a null —porque el modelo validado no
        # los lleva— y el log terminaba contradiciendo justo lo que existe para
        # contestar: quién retiró el paquete de marzo.
        if clave.startswith("_") or clave in ("actualizado_at", "actualizado_por",
                                              "setting_id", "version_id",
                                              "creado_at", "creado_por",
                                              "colaborador_id"):
            continue
        viejo, nuevo = antes.get(clave), despues.get(clave)
        if viejo != nuevo:
            salida[clave] = {"antes": enmascarar(viejo), "despues": enmascarar(nuevo)}
    return salida


def validar(bloque: str, datos: dict) -> tuple[dict | None, list[str]]:
    """(valor validado, errores). Nunca lanza: la ruta decide el código HTTP.

    Un bloque desconocido es un error del que llama, no del que guarda: agregar
    un bloque es agregar su esquema.
    """
    modelo = ESQUEMAS.get(bloque)
    if modelo is None:
        return None, [f"Bloque de configuración desconocido: {bloque!r}."]
    try:
        return modelo(**(datos or {})).model_dump(), []
    except Exception as e:
        return None, _legible(e)


def _legible(error) -> list[str]:
    """Los errores de Pydantic como frases que alguien puede accionar.

    "value_error, Input should be a valid integer" no le dice a nadie qué campo
    arreglar. "ttl_cotizacion_horas: el valor tiene que ser un número entero" sí.
    """
    detalles = getattr(error, "errors", None)
    if not callable(detalles):
        return [str(error)]
    salida = []
    for e in detalles():
        campo = ".".join(str(p) for p in e.get("loc", ())) or "el valor"
        mensaje = e.get("msg", "no es válido")
        salida.append(f"{campo}: {mensaje.replace('Value error, ', '')}")
    return salida or [str(error)]


# ─── Persistencia ─────────────────────────────────────────────────────────

async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def leer(bloque: str, db=None) -> dict | None:
    return (await leer_con_estado(bloque, db=db))[0]


async def leer_con_estado(bloque: str, db=None) -> tuple[dict | None, bool]:
    """(valor, se_pudo_leer). Existe porque `None` significa dos cosas distintas.

    "Todavía no está cargado" y "Mongo no contestó" se parecen desde afuera y no
    son lo mismo: al primero se responde "cargalo", al segundo "reintentá". Decir
    "cargá primero el punto de origen" durante un corte hace que alguien lo
    recargue de memoria y pise la plantilla y la Caixa Postal reales, que es un
    dato que después nadie sabe que se perdió.
    """
    try:
        base = await _db(db)
        return await base.app_settings.find_one(
            {"setting_id": SETTING_PREFIJO + bloque}, {"_id": 0}), True
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la configuración {bloque}: {e}")
        return None, False


async def guardar(bloque: str, datos: dict, admin, db=None,
                  invalidar=None) -> tuple[dict | None, list[str]]:
    """Valida, guarda, audita e invalida el caché. En ese orden y sin saltearse uno.

    `invalidar` se recibe como parámetro en vez de importarse para que este
    módulo no dependa de quién cachea: hoy es el catálogo, mañana puede ser otro,
    y una llamada olvidada es el bug del panel que no muestra lo que guardó.
    """
    validado, errores = validar(bloque, datos)
    if errores:
        return None, errores

    setting_id = SETTING_PREFIJO + bloque
    anterior = await leer(bloque, db=db) or {}

    try:
        base = await _db(db)
        await base.app_settings.update_one(
            {"setting_id": setting_id},
            {"$set": {**validado,
                      "setting_id": setting_id,
                      "actualizado_por": getattr(admin, "user_id", None),
                      "actualizado_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"envios: no se pudo guardar la configuración {bloque}: {e}")
        return None, ["No se pudo guardar. Intentá de nuevo."]

    await auditar(bloque, anterior, validado, admin, db=db)

    # Sin esto, el que guardó cree que no se guardó.
    if invalidar is not None:
        try:
            invalidar()
        except Exception as e:                                # pragma: no cover
            logger.warning(f"envios: no se pudo invalidar el caché de {bloque}: {e}")

    return validado, []


async def auditar(bloque: str, antes: dict, despues: dict, admin, db=None,
                  accion: str = "actualizar") -> None:
    """Escribe el cambio en centro_gestion_log. Fire-and-forget, como el resto.

    Que no lance es deliberado y tiene un límite: si la auditoría fallara siempre
    y en silencio, el panel quedaría sin registro sin que nadie se entere. Por eso
    el fallo se loguea como error, no como warning.
    """
    cambios = diferencias(antes, despues)
    if not cambios and accion == "actualizar":
        return                                   # guardar sin cambiar nada no es un evento

    doc = {
        "tipo": "envios_config",
        "transaction_id": f"cfg_{uuid.uuid4().hex[:12]}",
        "user_id": getattr(admin, "user_id", None),
        "user_email": getattr(admin, "email", None),
        "user_name": getattr(admin, "name", None),
        "status": "completed",
        "metadata": {"bloque": bloque, "accion": accion, "cambios": cambios},
        "registrado_en": datetime.now(timezone.utc),
        "origen": "risappbr",
    }
    try:
        base = await _db(db)
        await base.centro_gestion_log.insert_one(doc)
    except Exception as e:
        logger.error(f"envios: no se pudo auditar el cambio de {bloque}: {e}")
