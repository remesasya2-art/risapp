"""
services/envios_tarifa_editor.py — Borrador, simulador y publicacion de tarifas.

LA PANTALLA MAS IMPORTANTE DEL PANEL
    Define el unico ingreso del modulo. Se usa como una consola de precios
    —tabla a la izquierda, simulador a la derecha— y nada se aplica hasta
    publicar.

BORRADOR Y VERSION SON COSAS DISTINTAS
    El BORRADOR se edita todo lo que haga falta y no afecta a nadie: hay uno
    solo, se reemplaza entero, y no lo lee ninguna cotizacion.

    La VERSION es inmutable. Publicar crea una, cierra la anterior con
    `vigente_hasta` y pide una nota de que cambio y por que — esa nota es lo que
    se lee dentro de seis meses. Los envios en vuelo siguen apuntando a la suya.

COPY-FORWARD: TOCAR UN BLOQUE SIN RE-ESTAMPAR LOS OTROS
    Como la version es un documento entero, subir el precio del traslado
    obligaria tecnicamente a rehacerla completa. Para que eso no lleve a editar
    en la base a mano, el borrador arranca como una COPIA de la vigente y el
    editor manda solo lo que cambia. El resultado sigue siendo una version
    inmutable y completa.

EL SIMULADOR USA LA MISMA FUNCION QUE LA COTIZACION
    No una parecida: la misma, y con la MISMA fecha. Un simulador que ignora los
    recargos de temporada muestra 0 % de variacion para un aumento del 50 %, que
    es peor que no tener simulador: da confianza para publicar.

LO QUE BLOQUEA PUBLICAR
    Dos filtros, no uno:
      1. El ESQUEMA (models/envios_tarifa.TarifaEnvio). Lo que se publica sale
         de Mongo, y de Mongo puede venir cualquier cosa: un "NaN" que escribio
         una version vieja, un Decimal128, un numero en notacion cientifica. Sin
         re-validar el esquema, publicar es 500 en el mejor caso y una tarifa
         rota cobrando en el peor.
      2. validar_tarifa() de envios_tarifas.py: huecos, solapamientos, tablas no
         monotonas, precios en cero, porcentajes escritos como enteros.

VENTANAS DE VIGENCIA, NO "LA QUE NO TIENE FECHA DE CIERRE"
    Publicar para el 1 de octubre y despues corregirse tiene que poder hacerse.
    Por eso al publicar en una fecha D:
      - se ANULAN las versiones programadas que empezaban en D o despues (nunca
        rigieron: la correccion las reemplaza, no se encola detras de ellas), y
      - se CIERRA en D la version que cubre D.
    La alternativa —cerrar "las que no tienen vigente_hasta"— dejaba viva la
    programada equivocada y el precio cambiaba solo un mes despues.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from services.envios_tarifas import validar_tarifa, cotizar_servicio

logger = logging.getLogger(__name__)

SETTING_BORRADOR = "envios_tarifa_borrador"

# Cuanto skew de reloj se le perdona al cliente cuando manda "vigente desde:
# ahora". El formulario manda la hora que ve el navegador; entre eso, la latencia
# y un reloj corrido, la fecha llega unos cientos de milisegundos en el pasado y
# rechazar eso es un 400 que nadie entiende.
TOLERANCIA_RELOJ_S = 120

# Los metadatos del borrador, que no son parte de la tarifa.
_METADATOS = ("actualizado_por", "actualizado_at", "setting_id", "_id")

# Lo que estampa la publicacion y por lo tanto no se copia hacia adelante.
_IDENTIDAD = ("version_id", "vigente_desde", "vigente_hasta", "creada_por",
              "creada_at", "nota", "anulada", "anulada_por", "anulada_at")


class BaseInaccesible(Exception):
    """No se pudo leer. Distinto de 'no hay nada', que es un dato."""


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def _sin(doc: dict, claves) -> dict:
    return {k: v for k, v in (doc or {}).items() if k not in claves}


def _aware(valor):
    """Una fecha comparable, venga de donde venga.

    Pydantic parsea un ISO sin zona ("2026-10-01T00:00:00", que es exactamente lo
    que manda un <input type="datetime-local">) como datetime naive. Compararlo
    contra un aware es un TypeError sin capturar, o sea un 500 en el boton de
    programar un aumento.
    """
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def serializable(valor):
    """El payload como lo quiere el JSON: los decimales en texto, nunca en float.

    Es la misma regla que models/envios_tarifa: un Decimal que FastAPI convierte
    a float es el ruido binario volviendo a entrar por la ventana de salida. Y un
    Decimal128 —que es como services/money.py guarda dinero en Mongo— ni siquiera
    llega a float: revienta el encoder y tumba la consola de precios entera.
    """
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [serializable(v) for v in valor]
    nombre = type(valor).__name__
    if nombre in ("Decimal128", "Int64", "ObjectId"):
        return str(valor)
    return valor


# ─── Borrador ─────────────────────────────────────────────────────────────

async def leer_borrador(db=None) -> dict | None:
    """El borrador guardado, o None si no hay ninguno.

    Un fallo de lectura NO devuelve None: si lo hiciera, un timeout de Mongo se
    veria en pantalla como "no tenes cambios sin publicar", el administrador
    volveria a cargarlos y al publicar el `delete_one` se llevaria el borrador
    real que si estaba. Un error se propaga.
    """
    try:
        base = await _db(db)
        doc = await base.app_settings.find_one({"setting_id": SETTING_BORRADOR}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el borrador de tarifa: {e}")
        raise BaseInaccesible(str(e)) from e
    if not doc:
        return None
    return _sin(doc, ("setting_id", "_id"))


async def guardar_borrador(datos: dict, admin, db=None) -> dict:
    """Guarda el borrador tal cual. NO valida la coherencia: es un borrador.

    Validar acá sería impedirle a alguien guardar una tabla a medio cargar y
    volver mañana. Lo que se valida es publicar, que es cuando el número empieza
    a cobrarse.

    Es un REEMPLAZO, no un `$set`: con `$set` las claves que el editor sacó
    sobreviven, y como publicar congela el documento entero, esa basura entra a
    una version inmutable donde ya no se puede tocar.
    """
    doc = _sin(datos or {}, _METADATOS)
    doc["actualizado_por"] = getattr(admin, "user_id", None)
    doc["actualizado_at"] = datetime.now(timezone.utc)
    base = await _db(db)
    await base.app_settings.replace_one(
        {"setting_id": SETTING_BORRADOR}, {**doc, "setting_id": SETTING_BORRADOR},
        upsert=True)
    return doc


async def vigente(db=None, ahora=None) -> dict | None:
    """La versión que está cobrando hoy. Duplicada de envios_catalogo a
    propósito: este módulo no debería depender del que sirve el catálogo."""
    from services.envios_catalogo import tarifa_vigente
    return await tarifa_vigente(db=db, ahora=ahora)


async def borrador_o_copia(db=None) -> tuple[dict, str]:
    """(borrador, de dónde salió). Si no hay borrador, arranca copiando la vigente.

    Es el copy-forward: el que entra a subir un precio no tiene que volver a
    tipear los sobrecargos, los descuentos ni los límites.

    Origenes posibles: "borrador", "copia_de_vigente", "vacio", "error". El
    ultimo no es una tarifa vacia: es "no sabemos", y publicar sobre "no sabemos"
    borra trabajo ajeno.
    """
    try:
        borrador = await leer_borrador(db=db)
    except BaseInaccesible:
        return {}, "error"
    if borrador:
        return borrador, "borrador"
    try:
        actual = await vigente(db=db)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo copiar la vigente: {e}")
        return {}, "error"
    if actual:
        return _normalizar(_sin(actual, _IDENTIDAD)), "copia_de_vigente"
    return {}, "vacio"


def _normalizar(tarifa: dict) -> dict:
    """La forma anidada vieja llevada a la forma que entiende el esquema.

    `servicio_traslado.escalones` es la forma que el motor todavía acepta por
    compatibilidad. Copiarla verbatim hacia el borrador producía un objeto que el
    esquema rechaza por partida doble —clave desconocida y tabla vacía—, o sea
    que el copy-forward no funcionaba justo para las versiones más viejas, que
    son las que más ganas dan de copiar.
    """
    viejo = tarifa.get("servicio_traslado")
    if not isinstance(viejo, dict):
        return tarifa
    salida = _sin(tarifa, ("servicio_traslado",))
    for nueva, vieja in (("escalones_peso", "escalones"),
                         ("adicional_por_kg", "adicional_por_kg")):
        if salida.get(nueva) is None and viejo.get(vieja) is not None:
            salida[nueva] = viejo[vieja]
    return salida


# ─── Simulador ────────────────────────────────────────────────────────────

def simular(tarifa: dict, caja: dict, fecha=None) -> dict:
    """Cotiza una caja contra una tarifa. Nunca lanza: es una pantalla, no un cobro.

    Usa `cotizar_servicio`, la MISMA función que `POST /envios/cotizar`. No una
    parecida — y con fecha, que es la mitad que faltaba: sin ella
    `multiplicador_temporada` devuelve 1 siempre y los recargos de temporada son
    invisibles en la única pantalla donde se los podía ver antes de publicarlos.
    """
    try:
        return cotizar_servicio(
            tarifa,
            caja.get("peso_kg"), caja.get("largo_cm"), caja.get("ancho_cm"),
            caja.get("alto_cm"),
            valor_declarado=caja.get("valor_declarado", 0),
            bultos=caja.get("bultos") or 1,
            fecha=fecha or date.today(),
        )
    except Exception as e:
        logger.warning(f"envios: no se pudo simular {caja}: {e}")
        return {"error": str(e), "total": None}


def comparar(borrador: dict, actual: dict | None, cajas: list[dict], fecha=None) -> list[dict]:
    """Cada caja contra las dos tarifas, con la diferencia en porcentaje.

    Es lo que evita publicar un aumento del 40 % creyendo que era del 4 %. La
    comparación se muestra siempre, incluso cuando da cero: que el número esté
    ahí y sea cero es información, y que no esté no lo es.

    La variación se calcula en Decimal y se devuelve en texto. Redondear en float
    un número que la pantalla usa para decidir si publicar es exactamente el tipo
    de atajo que services/money.py existe para no tomar.
    """
    fecha = fecha or date.today()
    salida = []
    for caja in cajas or []:
        nuevo = simular(borrador, caja, fecha=fecha)
        viejo = simular(actual, caja, fecha=fecha) if actual else {"total": None}
        fila = {"caja": caja, "nuevo": nuevo, "actual": viejo, "variacion_pct": None}

        t_nuevo, t_viejo = nuevo.get("total"), viejo.get("total")
        if t_nuevo is not None and t_viejo is not None and t_viejo != 0:
            try:
                fila["variacion_pct"] = str(
                    ((t_nuevo - t_viejo) / t_viejo * 100).quantize(Decimal("0.01"))
                )
            except (InvalidOperation, ArithmeticError, TypeError):  # pragma: no cover
                fila["variacion_pct"] = None
        salida.append(fila)
    return salida


# ─── Publicación ──────────────────────────────────────────────────────────

def _errores_de_esquema(borrador: dict) -> list[str]:
    from models.envios_tarifa import TarifaEnvio
    try:
        TarifaEnvio(**_sin(borrador, _METADATOS + _IDENTIDAD))
        return []
    except Exception as e:
        detalle = getattr(e, "errors", None)
        if not callable(detalle):
            return [f"La tarifa no tiene una forma válida: {e}"]
        return [
            f"{'.'.join(str(p) for p in d.get('loc') or ()) or 'la tarifa'}: {d.get('msg')}"
            for d in detalle()[:12]
        ]


def _identicas(a: dict, b: dict | None) -> bool:
    if not b:
        return False
    return serializable(_sin(a, _METADATOS + _IDENTIDAD)) == \
        serializable(_sin(b, _METADATOS + _IDENTIDAD))


async def publicar(borrador: dict, nota: str, admin, db=None,
                   vigente_desde=None, consumir_borrador: bool = True,
                   marca_borrador=None) -> tuple[dict | None, list[str]]:
    """Valida, crea la versión nueva y reordena las ventanas. (versión, errores).

    ORDEN: primero se INSERTA la nueva y después se cierran las viejas. Al revés
    —cerrar y después insertar— un fallo del insert dejaba el módulo sin ninguna
    versión vigente y sin forma de reabrir la anterior desde el panel: todos los
    usuarios veían "el servicio no está disponible" hasta que alguien se diera
    cuenta. Insertando primero, el peor caso es un solapamiento de milisegundos
    que `tarifa_vigente` resuelve a favor de la más nueva, que es la que
    corresponde.
    """
    # El esquema PRIMERO y solo. validar_tarifa asume valores ya tipados: pasarle
    # un documento que el esquema rechazo es pedirle que compare contra basura.
    errores = _errores_de_esquema(borrador)
    if errores:
        return None, errores

    errores = validar_tarifa(borrador)
    if not (nota or "").strip():
        errores.append(
            "Falta la nota de qué cambió y por qué. Es lo que alguien va a leer "
            "dentro de seis meses para entender este precio."
        )
    if errores:
        return None, errores

    ahora = datetime.now(timezone.utc)
    desde = _aware(vigente_desde) or ahora
    if (ahora - desde).total_seconds() > TOLERANCIA_RELOJ_S:
        return None, ["Una versión no puede empezar a regir en el pasado."]
    desde = max(desde, ahora)

    base = await _db(db)

    # El borrador se reclama ANTES de insertar. Es lo que hace que un doble clic
    # en Publicar no cree dos versiones idénticas: el segundo no encuentra el
    # borrador con la marca que leyó y se detiene.
    if consumir_borrador:
        try:
            filtro = {"setting_id": SETTING_BORRADOR}
            if marca_borrador is not None:
                filtro["actualizado_at"] = marca_borrador
            reclamado = await base.app_settings.delete_one(filtro)
        except Exception as e:
            logger.error(f"envios: no se pudo reclamar el borrador: {e}")
            return None, ["No se pudo publicar. Reintentá en un momento."]
        if marca_borrador is not None and getattr(reclamado, "deleted_count", 1) == 0:
            # Solo es un conflicto si se esperaba UN borrador concreto. Sin marca
            # —publicar una tarifa cargada a mano, o un borrador viejo sin
            # `actualizado_at`— no hay nada que reclamar y no hay conflicto.
            return None, ["El borrador cambió mientras publicabas: alguien más lo editó "
                          "o ya lo publicó. Recargá la pantalla antes de reintentar."]

    version = _sin(borrador, _METADATOS + _IDENTIDAD)
    version.update({
        "version_id": f"tar_{uuid.uuid4().hex[:12]}",
        "vigente_desde": desde,
        "vigente_hasta": None,
        "creada_por": getattr(admin, "user_id", None),
        "creada_at": ahora,
        "nota": nota.strip(),
    })

    try:
        await base.tarifas_envio.insert_one(dict(version))
    except Exception as e:
        logger.error(f"envios: no se pudo publicar la tarifa: {e}")
        return None, ["No se pudo publicar. Revisá el estado de las versiones antes "
                      "de reintentar."]

    await _reordenar_ventanas(base, version["version_id"], desde, admin, ahora)
    return version, []


async def _reordenar_ventanas(base, version_id: str, desde: datetime, admin, ahora):
    """Deja una sola versión rigiendo en cada instante, a partir de `desde`.

    El filtrado se hace EN PYTHON y no en la query. Un `update_many` con
    `{"vigente_desde": {"$gte": desde}}` no matchea las fechas guardadas como
    texto, y es la clase de bug que este proyecto ya tuvo tres veces: las que no
    matchean no se cierran y quedan dos versiones vigentes.

    Que falle no invalida la publicación: la nueva versión ya está insertada y
    `tarifa_vigente` resuelve el solapamiento por la fecha de inicio más
    reciente. Por eso se registra y se sigue.
    """
    try:
        candidatas = await base.tarifas_envio.find(
            {}, {"_id": 0, "version_id": 1, "vigente_desde": 1, "vigente_hasta": 1,
                 "anulada": 1}
        ).to_list(_A_REVISAR)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudieron reordenar las ventanas de vigencia: {e}")
        return

    cerrar, anular = [], []
    for t in candidatas or []:
        otra = t.get("version_id")
        if not otra or otra == version_id or t.get("anulada"):
            continue
        inicio = _aware(t.get("vigente_desde"))
        if inicio is None:
            continue
        if inicio >= desde:
            # Programada para después de la nueva: nunca llegó a regir. Se anula,
            # no se borra — el historial tiene que poder mostrar que existió y
            # que se dio marcha atrás.
            anular.append(otra)
            continue
        fin = _aware(t.get("vigente_hasta"))
        if fin is None or fin > desde:
            cerrar.append(otra)

    for otra in cerrar:
        try:
            await base.tarifas_envio.update_one(
                {"version_id": otra}, {"$set": {"vigente_hasta": desde}})
        except Exception as e:                                # pragma: no cover
            logger.error(f"envios: no se pudo cerrar la versión {otra}: {e}")
    for otra in anular:
        try:
            await base.tarifas_envio.update_one(
                {"version_id": otra},
                {"$set": {"anulada": True, "anulada_por": getattr(admin, "user_id", None),
                          "anulada_at": ahora, "anulada_por_version": version_id}})
        except Exception as e:                                # pragma: no cover
            logger.error(f"envios: no se pudo anular la versión {otra}: {e}")


# Cuántas versiones se miran para reordenar ventanas y para armar el historial.
# La colección crece de a una publicación: con un cambio de precios por semana
# son cuatro años.
_A_REVISAR = 200


async def historial(db=None, limite: int = 20) -> list[dict]:
    """Las versiones, de la más nueva a la más vieja, con su nota."""
    try:
        base = await _db(db)
        filas = await base.tarifas_envio.find(
            {}, {"_id": 0, "version_id": 1, "vigente_desde": 1, "vigente_hasta": 1,
                 "creada_por": 1, "creada_at": 1, "nota": 1, "modo_tarifa": 1,
                 "anulada": 1, "anulada_at": 1}
        ).sort("creada_at", -1).to_list(limite)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el historial de tarifas: {e}")
        return []
    return [serializable(f) for f in (filas or [])]
