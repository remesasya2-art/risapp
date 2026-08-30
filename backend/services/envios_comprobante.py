"""
services/envios_comprobante.py — El usuario avisa que despacho.

POR QUE ESTE PASO EXISTE
    No hay API de rastreo. Sin contrato con el transportista de origen, el
    sistema no tiene forma de enterarse solo de que un paquete se despacho: el
    unico que lo sabe es el usuario, que tiene el comprobante en la mano.

    Por eso este es el unico punto del flujo donde el usuario le informa algo al
    sistema y el sistema le cree — con un limite, que es el punto siguiente.

CARGAR NO ES VERIFICAR, Y ES POR PLATA
    El cobro inicial se calcula con el PESO QUE FIGURA EN EL COMPROBANTE. Si ese
    numero lo tipeara el usuario y se cobrara sin mirar, cualquiera escribiria
    0,1 kg. Por eso son dos pasos:

      CARGAR (el usuario): sube el codigo de objeto, la foto y la fecha. El envio
      pasa a `en_transito_origen`. No se cobra nada.

      VERIFICAR (el operador): mira la foto, confirma el peso y las medidas que
      leyo ahi, y RECIEN AHI se emite el cobro inicial.

    La medicion sigue siendo ajena —la hizo el transportista de origen, que no
    tiene ningun interes en que sea baja— y ahora ademas la confirmo alguien de
    este lado mirando el papel.

EL CODIGO DE OBJETO SE VALIDA DE FORMA, NO DE EXISTENCIA
    Trece caracteres, dos letras, nueve digitos y dos letras de pais. Es lo unico
    que se puede comprobar sin una API: que sea un codigo con forma de codigo.
    Que exista lo dira el mostrador de Pacaraima.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ESTADO_ORIGEN = "esperando_postagem"
ESTADO_DESTINO = "en_transito_origen"

# AA123456789BR: dos letras, nueve digitos, dos letras. Es el formato del sistema
# postal internacional (S10), no el de una empresa en particular.
_CODIGO = re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$")

# Cuanto para atras se acepta una fecha de despacho. Mas que esto no es un
# comprobante reciente: o es un error de tipeo o es de otro envio.
DIAS_ATRAS_MAX = 60


class ComprobanteRechazado(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def normalizar_codigo(bruto) -> str:
    """El código sin espacios ni guiones y en mayúsculas, o lanza.

    Se normaliza antes de validar porque la gente lo copia del comprobante tal
    como está impreso, con espacios cada cuatro caracteres. Rechazar eso sería
    rechazar el dato correcto por su formato de presentación.
    """
    texto = re.sub(r"[\s\-.]", "", str(bruto or "")).upper()
    if not _CODIGO.match(texto):
        raise ComprobanteRechazado(
            "Ese código de objeto no tiene el formato correcto. Son trece caracteres: "
            "dos letras, nueve números y dos letras, como AA123456789BR. Está impreso "
            "en el comprobante que te dieron.")
    return texto


def _fecha(valor, ahora):
    """La fecha de despacho, validada. Lanza con un motivo legible."""
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            raise ComprobanteRechazado(
                "La fecha del comprobante no se entiende. Usá el formato AAAA-MM-DD.")
    if not isinstance(valor, datetime):
        raise ComprobanteRechazado("Falta la fecha del comprobante.")
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)

    # Un día de tolerancia hacia adelante: el usuario puede estar en otro huso y
    # despachar a la noche. Más que eso es una fecha futura, que no existe.
    if valor > ahora + timedelta(days=1):
        raise ComprobanteRechazado(
            "La fecha del comprobante está en el futuro. Revisá el día que despachaste.")
    if valor < ahora - timedelta(days=DIAS_ATRAS_MAX):
        raise ComprobanteRechazado(
            f"La fecha del comprobante tiene más de {DIAS_ATRAS_MAX} días. Si el envío "
            f"es viejo, escribinos antes de cargarlo.")
    return valor


# ─── 1. El usuario carga ──────────────────────────────────────────────────

async def cargar(usuario, envio_id: str, *, codigo_objeto, posteado_at, foto: bytes,
                 servicio: str = None, monto_pagado_brl=None, db=None,
                 ahora=None) -> dict:
    """Registra el comprobante y mueve el envío. **No cobra nada.**"""
    from services import envios_archivos, envios_eventos
    from services.envios_estados import puede_transicionar

    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    user_id = getattr(usuario, "user_id", None)

    envio = await _envio_del_usuario(base, user_id, envio_id)
    if envio.get("estado") == ESTADO_DESTINO:
        # Ya estaba cargado. Un reintento de red no puede parecer un fallo.
        return _resultado(envio)
    problema = puede_transicionar(envio.get("estado") or "", ESTADO_DESTINO, "user")
    if problema:
        raise ComprobanteRechazado(
            "Este envío no está esperando el comprobante. Abrilo para ver en qué punto "
            "está.", http=409)

    codigo = normalizar_codigo(codigo_objeto)
    fecha = _fecha(posteado_at, ahora)

    # El código no puede estar en otro envío: dos envíos con el mismo comprobante
    # son dos cobros sobre un despacho, y el segundo se descubre en el mostrador.
    otro = await _codigo_en_otro_envio(base, codigo, envio_id)
    if otro:
        raise ComprobanteRechazado(
            "Ese código de objeto ya está cargado en otro de tus envíos. Revisá que no "
            "hayas copiado el comprobante equivocado.", http=409)

    ficha = await envios_archivos.guardar(
        foto, envio_id=envio_id, user_id=user_id, clase="comprobante",
        db=base, ahora=ahora)
    repetida = await envios_archivos.ya_usado(ficha["sha256"], envio_id, db=base)

    origen = {
        "codigo_objeto": codigo,
        "comprobante_asset_id": ficha["asset_id"],
        "posteado_at": fecha,
        "servicio": (servicio or "").strip()[:40] or None,
        "monto_pagado_brl": None if monto_pagado_brl is None
        else str(monto_pagado_brl).strip()[:20],
        "cargado_at": ahora,
        # La verificación es de otro: acá solo se deja el lugar preparado.
        "verificado": None,
        "foto_repetida_en": repetida,
    }

    try:
        actualizado = await base.envios.find_one_and_update(
            {"envio_id": envio_id, "user_id": user_id, "estado": ESTADO_ORIGEN},
            {"$set": {"estado": ESTADO_DESTINO,
                      **{f"origen.{k}": v for k, v in origen.items()}}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo cargar el comprobante de {envio_id}: {e}")
        raise ComprobanteRechazado(
            "No se pudo guardar el comprobante. Probá de nuevo en un momento.",
            http=503) from e

    if actualizado is None:
        actual = await _envio_del_usuario(base, user_id, envio_id)
        if actual.get("estado") == ESTADO_DESTINO:
            return _resultado(actual)
        raise ComprobanteRechazado(
            "Este envío ya no está esperando el comprobante.", http=409)

    if repetida:
        logger.warning(
            f"envios: la foto del comprobante de {envio_id} ya estaba en {repetida}")

    await envios_eventos.registrar(
        actualizado, ESTADO_ORIGEN, ESTADO_DESTINO, "user", actor_id=user_id,
        detalle={"codigo_objeto": codigo, "posteado_at": fecha.isoformat()},
        db=base, ahora=ahora)
    return _resultado(actualizado)


# ─── 2. El operador verifica, y ahi se cobra ──────────────────────────────

async def verificar(operador, envio_id: str, *, peso_kg, largo_cm, ancho_cm, alto_cm,
                    db=None, ahora=None, idempotency_key: str = None) -> dict:
    """Confirma lo que dice el comprobante y emite el cobro inicial.

    Es el único lugar donde una persona de este lado mira el papel. El peso no
    puede salir de lo que el usuario tipeó: con eso, cualquiera escribiría 0,1 kg
    y el servicio se cobraría solo.
    """
    from services import envios_cobros, envios_eventos

    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)

    envio = await _envio(base, envio_id)
    origen = envio.get("origen") or {}
    if not origen.get("codigo_objeto"):
        raise ComprobanteRechazado(
            "Este envío todavía no tiene comprobante cargado.", http=409)
    if (origen.get("verificado") or {}).get("at"):
        return {"ok": True, "ya_verificado": True,
                "cobro": _cobro_de(envio)}

    verificado = {
        "peso_kg": str(peso_kg), "largo_cm": str(largo_cm),
        "ancho_cm": str(ancho_cm), "alto_cm": str(alto_cm),
        "at": ahora, "por": getattr(operador, "user_id", None),
    }
    try:
        actualizado = await base.envios.find_one_and_update(
            {"envio_id": envio_id, "origen.verificado": None},
            {"$set": {"origen.verificado": verificado}}, return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo verificar {envio_id}: {e}")
        raise ComprobanteRechazado(
            "No se pudo registrar la verificación. Reintentá en un momento.",
            http=503) from e
    if actualizado is None:
        return {"ok": True, "ya_verificado": True,
                "cobro": _cobro_de(await _envio(base, envio_id))}

    # El cobro va DESPUÉS de registrar la verificación. Al revés, un fallo al
    # registrar dejaría un cobro emitido sin nada que lo explique.
    cobro = await envios_cobros.emitir_inicial(
        actualizado, peso_kg, largo_cm, ancho_cm, alto_cm,
        db=base, ahora=ahora, idempotency_key=idempotency_key,
        actor_id=getattr(operador, "user_id", None))

    await envios_eventos.registrar(
        actualizado, ESTADO_DESTINO, ESTADO_DESTINO, "admin",
        actor_id=getattr(operador, "user_id", None),
        detalle={"verificacion": "comprobante", "peso_kg": str(peso_kg),
                 "cobro": cobro.get("estado"), "monto_ris": cobro.get("monto_ris")},
        db=base, ahora=ahora)
    return {"ok": True, "ya_verificado": False, "cobro": cobro}


# ─── Piezas ───────────────────────────────────────────────────────────────

async def _envio_del_usuario(base, user_id, envio_id: str) -> dict:
    try:
        envio = await base.envios.find_one(
            {"envio_id": envio_id, "user_id": user_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        raise ComprobanteRechazado(
            "No se pudo leer el envío. Probá de nuevo en un momento.", http=503) from e
    if not envio:
        raise ComprobanteRechazado("No encontramos ese envío.", http=404)
    return envio


async def _envio(base, envio_id: str) -> dict:
    try:
        envio = await base.envios.find_one({"envio_id": envio_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        raise ComprobanteRechazado(
            "No se pudo leer el envío. Reintentá en un momento.", http=503) from e
    if not envio:
        raise ComprobanteRechazado("Ese envío no existe.", http=404)
    return envio


async def _codigo_en_otro_envio(base, codigo: str, envio_id: str) -> str | None:
    try:
        otro = await base.envios.find_one(
            {"origen.codigo_objeto": codigo}, {"_id": 0, "envio_id": 1})
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo chequear el código {codigo}: {e}")
        return None
    if otro and otro.get("envio_id") and otro["envio_id"] != envio_id:
        return otro["envio_id"]
    return None


def _cobro_de(envio: dict) -> dict:
    from services.money import to_decimal
    partida = ((envio.get("cobros") or {}).get("inicial")) or {}
    return {"partida": "inicial",
            "estado": "pagado" if partida.get("estado") == "pagado" else "pendiente",
            "monto_ris": str(to_decimal(partida.get("monto_ris")))}


def _resultado(envio: dict) -> dict:
    origen = envio.get("origen") or {}
    return {
        "ok": True,
        "envio_id": envio.get("envio_id"),
        "estado": envio.get("estado"),
        "codigo_objeto": origen.get("codigo_objeto"),
        # `foto_repetida_en` es un dato del operador, no del usuario: decirle a
        # quien sube "esta foto ya está en el envío env_xxx" le confirma qué
        # identificadores existen, y no le sirve para nada.
        "comprobante_cargado": bool(origen.get("comprobante_asset_id")),
        "proximo_paso": (
            "Recibido. Vamos a revisar el comprobante y ahí te cobramos el servicio, "
            "calculado sobre el peso que midió el transportista. Te avisamos cuando el "
            "paquete llegue a Pacaraima."
        ),
    }
