"""
services/envios_puesta_en_marcha.py — Que le falta al modulo para poder operar.

POR QUE EXISTE ESTA PANTALLA
    El modulo recien instalado no puede cotizar, y tiene razon: no hay
    transportistas, no hay precios, no hay una direccion a la que despachar. La
    ruta publica `/envios/limites` contesta `disponible: false` y —a proposito—
    NO dice por que: el diagnostico de configuracion es informacion interna y no
    tiene por que estar del lado de afuera.

    El resultado es que la unica forma de saber que falta era leer el codigo.
    Esto es ese diagnostico, entero, del lado de adentro, y en el ORDEN en que
    hay que cargarlo: cada paso depende de los anteriores.

"NO ESTA CARGADO" Y "NO LO PUDE LEER" NO SON LO MISMO
    Es la regla mas importante del archivo, y no es teorica: `envios_config.leer`
    devuelve None tanto si el bloque nunca se cargo como si Mongo no contesto.
    Una pantalla que confunde las dos le dice "carga el punto de origen" a
    alguien durante un corte de base — y esa persona lo carga de memoria y pisa
    la plantilla y la Caixa Postal reales, que si estaban.

    Por eso cada paso tiene tres estados y no dos: `listo`, `falta` e
    `ilegible`. Y `puede_operar` solo es True cuando no hay ninguno de los dos
    ultimos: durante un corte, la respuesta honesta es "no se", no "si".

NO DECIDE NADA, SOLO MIRA
    Ninguna funcion de este archivo escribe. Es una pantalla de diagnostico: si
    ademas arreglara cosas, el dia que alguien la abra para entender un problema
    se lo cambiaria abajo de los pies.
"""

import logging

logger = logging.getLogger(__name__)

# El orden importa: cada paso depende de los de arriba. Designar a alguien de
# turno necesita el punto de origen cargado; publicar una tarifa sin
# transportistas activos deja el sistema igual de inutil.
ORDEN = ("punto_origen", "contenido", "operacion", "transportistas", "agencias",
         "nomina", "tarifa")

LISTO, FALTA, ILEGIBLE = "listo", "falta", "ilegible"


def _paso(clave, titulo, estado, detalle, donde=None, extra=None):
    return {"clave": clave, "titulo": titulo, "estado": estado,
            "detalle": detalle, "donde": donde, **(extra or {})}


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def _bloque(clave: str):
    """(valor, se_pudo_leer). El segundo es el que separa falta de ilegible."""
    from services import envios_config
    try:
        return await envios_config.leer_con_estado(clave)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo leer el bloque {clave}: {e}")
        return None, False


async def _contar(base, coleccion, filtro) -> int | None:
    """El conteo, o None si no se pudo. None NO es cero."""
    try:
        return await base[coleccion].count_documents(filtro)
    except Exception as e:
        logger.warning(f"envios: no se pudo contar {coleccion}: {e}")
        return None


async def _paso_punto_origen(valor, se_leyo):
    if not se_leyo:
        return _paso("punto_origen", "Punto de origen", ILEGIBLE,
                     "No se pudo leer. **No lo cargues de nuevo hasta que vuelva**: "
                     "lo pisarías.", "config/punto_origen")
    if not valor:
        return _paso("punto_origen", "Punto de origen", FALTA,
                     "La agencia de Pacaraima, la razón social y la plantilla de la "
                     "dirección que el usuario copia sobre la caja.",
                     "config/punto_origen")
    return _paso("punto_origen", "Punto de origen", LISTO,
                 f"{valor.get('nombre')} · {valor.get('ciudad')}/{valor.get('uf')}",
                 "config/punto_origen")


async def _paso_bloque(clave, titulo, detalle_falta, resumen):
    valor, se_leyo = await _bloque(clave)
    if not se_leyo:
        return _paso(clave, titulo, ILEGIBLE,
                     "No se pudo leer. No lo cargues de nuevo hasta que vuelva.",
                     f"config/{clave}")
    if not valor:
        return _paso(clave, titulo, FALTA, detalle_falta, f"config/{clave}")
    return _paso(clave, titulo, LISTO, resumen(valor), f"config/{clave}")


async def _paso_transportistas(base):
    try:
        activos = await base.transportistas.find(
            {}, {"_id": 0, "rol": 1, "activo": 1, "codigo": 1,
                 "transportista_id": 1, "cuenta_bancaria": 1}).to_list(200)
    except Exception as e:
        logger.warning(f"envios: no se pudieron leer los transportistas: {e}")
        return _paso("transportistas", "Transportistas", ILEGIBLE,
                     "No se pudo leer la lista.", "transportistas"), None

    vivos = [t for t in activos if t.get("activo")]
    brasil = [t for t in vivos if t.get("rol") == "brasil"]
    venezuela = [t for t in vivos if t.get("rol") == "venezuela"]
    faltan = []
    if not brasil:
        faltan.append("ninguno con rol Brasil")
    if not venezuela:
        faltan.append("ninguno con rol Venezuela")
    # "hay ninguno" no es castellano. Se nombra SOLO el que falta: mencionar
    # tambien el que ya esta cargado manda a alguien a revisar algo que esta bien.
    extra = {"brasil": len(brasil), "venezuela": len(venezuela),
             "total": len(activos)}
    if faltan:
        return _paso("transportistas", "Transportistas", FALTA,
                     f"Hace falta uno de cada rol: no hay {' ni '.join(faltan)}. El de "
                     f"Brasil lleva el paquete hasta Pacaraima; el de Venezuela, "
                     f"desde Santa Elena hasta el destino.",
                     "transportistas", extra), vivos
    return _paso("transportistas", "Transportistas", LISTO,
                 f"{len(brasil)} activo(s) en Brasil, {len(venezuela)} en Venezuela.",
                 "transportistas", extra), vivos


async def _paso_agencias(base, vivos):
    if vivos is None:
        return _paso("agencias", "Agencias de destino", ILEGIBLE,
                     "No se pudieron leer los transportistas.", "transportistas")
    venezolanos = [t.get("transportista_id") for t in vivos
                   if t.get("rol") == "venezuela"]
    if not venezolanos:
        return _paso("agencias", "Agencias de destino", FALTA,
                     "Primero cargá un transportista con rol Venezuela.",
                     "transportistas")
    total = await _contar(base, "agencias",
                          {"transportista_id": {"$in": venezolanos}, "activa": True})
    entrega = await _contar(base, "agencias",
                            {"transportista_id": {"$in": venezolanos},
                             "es_punto_entrega": True, "activa": True})
    if total is None or entrega is None:
        return _paso("agencias", "Agencias de destino", ILEGIBLE,
                     "No se pudieron contar.", "transportistas")
    if not total:
        return _paso("agencias", "Agencias de destino", FALTA,
                     "Son las oficinas donde el destinatario retira. Se cargan de a "
                     "una o por CSV.", "transportistas",
                     {"total": 0, "punto_entrega": 0})
    if not entrega:
        return _paso("agencias", "Agencias de destino", FALTA,
                     f"Hay {total} agencia(s) activa(s), pero ninguna **activa y "
                     f"marcada como punto de entrega**: es la oficina de Santa Elena "
                     f"donde RIS App deja los paquetes, y es lo que después le dice "
                     f"al operador dónde termina el traslado.",
                     "transportistas", {"total": total, "punto_entrega": 0})
    return _paso("agencias", "Agencias de destino", LISTO,
                 f"{total} activa(s), con punto de entrega marcado.",
                 "transportistas", {"total": total, "punto_entrega": entrega})


async def _paso_nomina(base, punto, punto_legible=True):
    from services import envios_retiro
    from datetime import datetime, timezone
    if not punto_legible:
        # Quien esta de turno vive en `punto_origen`. Sin poder leerlo, "nadie
        # esta de turno" es una afirmacion que no se puede hacer.
        return _paso("nomina", "Nómina de retiro", ILEGIBLE,
                     "No se pudo leer el punto de origen, que es donde vive quién "
                     "está de turno.", "retiro")
    try:
        # El mismo tope que usa el modulo que la lee de verdad. Con uno mas
        # chico, en una nomina larga —y nada se borra— el designado puede caer
        # fuera de la ventana y el paso diria "nadie de turno" mientras la
        # cotizacion rotula bien.
        nomina = await base.colaboradores_retiro.find(
            {}, {"_id": 0, "cpf": 0, "telefono": 0}).to_list(envios_retiro._NOMINA_MAX)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la nómina: {e}")
        return _paso("nomina", "Nómina de retiro", ILEGIBLE,
                     "No se pudo leer la nómina.", "retiro")

    ahora = datetime.now(timezone.utc)
    vigentes = [c for c in nomina if envios_retiro._vigente(c, ahora)]
    extra = {"total": len(nomina), "vigentes": len(vigentes)}
    if not vigentes:
        return _paso("nomina", "Nómina de retiro", FALTA,
                     "Nadie autorizado a retirar en Pacaraima. Es el nombre que va "
                     "rotulado en la caja y el que el mostrador compara contra un "
                     "documento.", "retiro", extra)

    de_turno = (punto or {}).get("retirador_activo_id")
    if not de_turno or not any(c.get("colaborador_id") == de_turno for c in vigentes):
        return _paso("nomina", "Nómina de retiro", FALTA,
                     f"Hay {len(vigentes)} persona(s) vigente(s), pero ninguna está de "
                     f"turno. Sin alguien de turno, la cotización no tiene a qué nombre "
                     f"rotular.", "retiro", extra)
    nombre = next(c.get("nombre") for c in vigentes
                  if c.get("colaborador_id") == de_turno)
    return _paso("nomina", "Nómina de retiro", LISTO,
                 f"De turno: {nombre}.", "retiro", {**extra, "de_turno": nombre})


async def _paso_tarifa(base):
    from services import envios_catalogo
    from services.envios_policy import configuracion_incompleta
    try:
        tarifa = await envios_catalogo.tarifa_vigente(db=base)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo leer la tarifa vigente: {e}")
        return _paso("tarifa", "Precios del servicio", ILEGIBLE,
                     "No se pudo leer la versión vigente.", "tarifas"), None
    if not tarifa:
        return _paso("tarifa", "Precios del servicio", FALTA,
                     "No hay ninguna versión publicada. Cargá el borrador, simulá "
                     "unas cajas y publicá con una nota de qué cambió.",
                     "tarifas"), None
    # Los problemas de la tarifa MISMA, sin los de transportistas —esos ya son
    # su propio paso y repetirlos acá haría que un solo error se vea como dos.
    problemas = [m for m in configuracion_incompleta([], tarifa)
                 if "transportista" not in m.lower()]
    extra = {"version_id": tarifa.get("version_id"), "moneda": tarifa.get("moneda")}
    if problemas:
        return _paso("tarifa", "Precios del servicio", FALTA,
                     " ".join(problemas), "tarifas", extra), tarifa
    return _paso("tarifa", "Precios del servicio", LISTO,
                 f"Versión {tarifa.get('version_id')} vigente.", "tarifas",
                 extra), tarifa


async def estado(db=None) -> dict:
    """El checklist entero. Nunca lanza: es la pantalla de diagnóstico."""
    base = await _db(db)
    pasos = []

    # UNA sola lectura, compartida. Leerlo dos veces abre la puerta a que la
    # segunda falle: `punto` quedaba en None, el paso 1 decia LISTO y el de la
    # nomina decia "nadie de turno" — mandando a re-designar durante un corte,
    # que es exactamente el error que este archivo existe para no cometer.
    punto, punto_legible = await _bloque("punto_origen")
    pasos.append(await _paso_punto_origen(punto, punto_legible))

    pasos.append(await _paso_bloque(
        "contenido", "Contenido y términos",
        "La lista de prohibidos que el usuario lee al cotizar, el texto que acepta "
        "y la versión de los términos.",
        lambda v: f"{len(v.get('prohibidos') or [])} prohibidos · términos "
                  f"{v.get('terminos_version')}"))

    pasos.append(await _paso_bloque(
        "operacion", "Operación",
        "**Cargalo aunque sea con los valores por defecto**: la tolerancia del "
        "ajuste y los días de guarda salen de acá, y sin el bloque no hay "
        "tolerancia — con lo cual todo repesaje ajusta.",
        lambda v: f"Tolerancia {v.get('tolerancia_ajuste_ris')} · guarda "
                  f"{v.get('dias_guarda')} días"))

    paso_transportistas, vivos = await _paso_transportistas(base)
    pasos.append(paso_transportistas)
    pasos.append(await _paso_agencias(base, vivos))
    pasos.append(await _paso_nomina(base, punto, punto_legible))
    paso_tarifa, _tarifa = await _paso_tarifa(base)
    pasos.append(paso_tarifa)

    faltan = [p for p in pasos if p["estado"] == FALTA]
    ilegibles = [p for p in pasos if p["estado"] == ILEGIBLE]
    return {
        # Solo True cuando NADA falta y NADA quedó ilegible. Durante un corte la
        # respuesta honesta es "no sé", y "no sé" no es "sí".
        "puede_operar": not faltan and not ilegibles,
        "hay_lecturas_fallidas": bool(ilegibles),
        "pasos": pasos,
        "faltan": len(faltan),
        "siguiente": (faltan[0]["clave"] if faltan else None),
    }
