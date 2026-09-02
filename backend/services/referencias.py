"""
services/referencias.py — Lo que le van a cobrar los transportistas, como orientacion.

QUE ES UNA REFERENCIA Y QUE NO ES
    El usuario contrata y paga por su cuenta dos servicios que RIS App no factura:
    el transportista de Brasil que lleva el paquete hasta Pacaraima, y el de
    Venezuela que lo lleva desde Santa Elena hasta su destino. La app igual
    necesita mostrarle un numero aproximado de cada uno, porque sin eso el
    usuario no puede decidir si le conviene mandar el paquete.

    Ese numero es una ORIENTACION. No se factura, no se concilia, no se ajusta y
    **jamas entra en el total que RIS App cobra**. Por eso cada referencia sale de
    aca marcada con `facturable: False` y con el monto como Decimal o None, nunca
    como float: no es decoracion, es lo que hace que un `sum()` distraido en la
    ruta de cotizacion sea un test que falla y no un cobro indebido.

DE DONDE SALEN LOS NUMEROS
    De `matrices_referencia`, una tabla por transportista, cargada a mano por el
    super administrador o refrescada por el job semanal (§2.5). **Ninguna tabla
    que se factura sale de un scraper**: si un parseo sale mal el usuario ve un
    numero raro y pregunta en el mostrador, pero nadie le cobra de mas.

NINGUN NOMBRE DE EMPRESA
    Este modulo no sabe que empresas existen. Recorre los transportistas activos
    por ROL —`brasil` y `venezuela`— y los nombra por su codigo alfanumerico. La
    proyeccion de la consulta es explicita y NO trae el campo `nombre`: lo que no
    sale de la base no puede terminar en un log ni en una respuesta.

LA REGLA QUE GOBIERNA TODO EL MODULO
    **Una referencia que falta no puede romper una cotizacion.** El precio que
    RIS App cobra no depende de estos numeros; si la matriz no tiene la fila, si
    la base no responde, si tarda demasiado o si el peso se sale de la tabla, se
    devuelve `None` con el motivo y la cotizacion sigue. Preferimos mostrar
    "consultá en el mostrador" antes que un error donde el usuario esperaba un
    precio.

    "No puede romper" incluye **no puede colgar**: una base degradada casi nunca
    falla, tarda. Por eso hay un tope de tiempo y los transportistas se consultan
    en paralelo, no uno atras del otro.

POR QUE EL FILTRADO SE HACE EN PYTHON Y NO EN LA CONSULTA
    Es deliberado y es la decision menos obvia del modulo. Mongo compara tipos
    con "type bracketing": un `hasta_kg` guardado como string nunca matchea un
    `$gte: 7.0`, un `Decimal128("2.1")` no es `>=` el double 2.1000000000000000888
    que sale de `float(Decimal("2.1"))`, y `{"activo": True}` no matchea un
    `activo: 1` guardado por un panel que serializo el checkbox como numero.

    Las tres cosas fallan en silencio: devuelven "sin dato" en produccion mientras
    los tests pasan. Como la matriz de un transportista para una clave son unas
    pocas franjas, se traen todas y se elige en Python con to_decimal, que si sabe
    leer las cuatro formas. Cuesta unos bytes y elimina una clase entera de bugs
    que solo se ven con la base real.

ESTADO (PR C)
    Este modulo SI lee Mongo —es su razon de ser— pero ninguna ruta lo llama
    todavia y no escribe nada. Todas las funciones aceptan un `db` inyectado para
    poder probarlas sin una base: si no se pasa, se importa el real igual que en
    services/kyc_quota.py, y el import va DENTRO del try, porque un ImportError
    tambien es una forma de romper una cotizacion.

    Las firmas son las que tendrian si algun dia hubiera una API con contrato. Ese
    dia se cambia el cuerpo de cotizar_referencia() y no se toca nada mas.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from services.money import to_decimal, quantize_money
from services.envios_tarifas import peso_facturable

logger = logging.getLogger(__name__)

ROLES = ("brasil", "venezuela")

# Una matriz que nadie refresco en un mes sigue sirviendo para dar una idea, pero
# el usuario tiene derecho a saber que el numero es viejo.
DIAS_FRESCURA = 30

# Tope de tiempo de TODA la orientacion, no de cada consulta. Es generoso para
# una lectura indexada y corto comparado con lo que un usuario tolera mirando un
# spinner: si se agota, la cotizacion sale igual, sin orientaciones.
TIMEOUT_S = 2.0

# Los indices que estas consultas necesitan. Los crea el lifespan en el PR D;
# viven aca para que la lista este al lado de las consultas que las usan y no se
# desincronice.
INDICES = (
    ("transportistas", [("rol", 1), ("orden", 1)]),
    ("matrices_referencia", [("transportista_id", 1), ("clave", 1), ("hasta_kg", 1)]),
)

# Campos que salen de la ficha del transportista. `nombre` NO esta en la lista:
# lo que no sale de la base no puede terminar en un log ni en una respuesta.
#
# `limites` SI esta, y es facil de olvidar porque este modulo no lo usa: lo usa
# envios_policy.limites_efectivos() para calcular la interseccion, y sin el la
# pantalla recibe todos los limites en null y los lee como "sin restricciones".
# Es el mismo bug del PR #40 —un techo anunciado que nadie valida— entrando por
# la puerta de atras, y ningun test con un fake que ignore proyecciones lo ve.
_PROYECCION_TRANSPORTISTA = {
    "_id": 0, "transportista_id": 1, "codigo": 1, "rol": 1, "orden": 1,
    "activo": 1, "moneda": 1, "regla_peso": 1, "limites": 1,
}

_TEXTOS_FALSOS = {"false", "no", "0", "off", "", "none", "null"}

MOTIVOS = ("matriz", "sin_clave", "sin_dato", "precio_invalido", "error",
           "timeout", "catalogo_no_disponible")


def _activo(fila) -> bool:
    """Mismo criterio que envios_tarifas y envios_policy, y por la misma razón.

    Se filtra acá y no en la consulta a propósito: `{"activo": True}` en Mongo no
    matchea un `activo: 1` ni un `"true"`, y un transportista dado de alta desde
    un panel que serializó el checkbox como número desaparecería de las
    orientaciones sin un solo log.
    """
    valor = (fila or {}).get("activo", True)
    if isinstance(valor, str):
        return valor.strip().lower() not in _TEXTOS_FALSOS
    return bool(valor)


def codigo_de(transportista: dict) -> str:
    """Cómo se nombra a un transportista en un log o en un error: por su código.

    Nunca por su nombre comercial, y nunca hay un fallback a `nombre`: el día que
    alguien lo agregue "por si el código está vacío", el nombre de una empresa
    real empieza a viajar en los logs y en el payload.
    """
    t = transportista or {}
    return t.get("codigo") or t.get("transportista_id") or "?"


# ─── Catálogo ─────────────────────────────────────────────────────────────

async def _catalogo(rol: str, db=None) -> tuple[list[dict], bool]:
    """(transportistas, se_pudo_leer). El booleano es la diferencia entre "no hay
    ninguno configurado" y "la base no contestó", que desde afuera se parecen y
    no son lo mismo."""
    if rol not in ROLES:
        logger.warning(f"referencias: rol desconocido {rol!r}")
        return [], True
    try:
        if db is None:
            from database import db as db_real
            db = db_real
        filas = await db.transportistas.find(
            {"rol": rol}, _PROYECCION_TRANSPORTISTA
        ).sort("orden", 1).to_list(None)
    except Exception as e:
        logger.warning(f"referencias: no se pudieron leer los transportistas de {rol}: {e}")
        return [], False
    return [t for t in filas if _activo(t)], True


async def transportistas_activos(rol: str, db=None) -> list[dict]:
    """Los transportistas activos de un rol, en el orden que fijó el panel.

    Un rol desconocido devuelve lista vacía en vez de lanzar: si mañana alguien
    escribe "brazil" en una ruta, el usuario tiene que ver una cotización sin esa
    orientación, no un 500. Y no se consulta la base: devolver vacío porque la
    consulta no encontró nada cuesta un viaje a Mongo por cotización, con un typo
    que nadie ve en los logs.
    """
    filas, _ = await _catalogo(rol, db=db)
    return filas


# ─── Una referencia ───────────────────────────────────────────────────────

# Todas las salidas tienen exactamente estas claves. Que la forma no dependa del
# camino es lo que evita el KeyError del consumidor que lee `desactualizada` en
# la referencia que no tuvo dato.
_FORMA = {
    "transportista_id": None, "codigo": "?", "rol": None, "clave": None,
    "peso_facturable_kg": None, "monto": None, "moneda": None, "hasta_kg": None,
    "fuente": "sin_dato", "origen_dato": None, "actualizada_at": None,
    "desactualizada": True, "facturable": False,
}


def _referencia(transportista, clave, **campos) -> dict:
    t = transportista or {}
    salida = dict(_FORMA)
    salida.update({
        "transportista_id": t.get("transportista_id"),
        "codigo": codigo_de(t),
        "rol": t.get("rol"),
        "clave": clave,
        "moneda": t.get("moneda"),
    })
    salida.update(campos)
    # El candado, al final y sin excepciones: ninguna referencia se factura.
    salida["facturable"] = False
    return salida


def _precio_valido(bruto):
    """El precio de la matriz, o None si no es un número usable.

    `to_decimal` devuelve 0 ante basura —es su política y está bien para cotizar—
    pero acá un 0 se le muestra al usuario como un tramo gratis, indistinguible
    de un precio real. Un precio ilegible es "no sé", no "sale cero".
    """
    if bruto is None:
        return None
    if isinstance(bruto, str) and ("," in bruto or not bruto.strip()):
        return None
    valor = to_decimal(bruto)
    if valor <= 0 or not valor.is_finite():
        return None
    return quantize_money(valor)


def _elegir_franja(filas, pf):
    """La franja más chica cuyo `hasta_kg` alcance el peso facturable.

    Se resuelve en Python porque Mongo no compara tipos entre sí: un `hasta_kg`
    guardado como string o como Decimal128 daría "sin dato" en producción con los
    tests en verde. Ante dos franjas con el mismo tope gana la actualizada más
    recientemente, para que el resultado no dependa del orden en que Mongo las
    devuelva.
    """
    candidatas = []
    for f in filas or []:
        if not isinstance(f, dict):
            continue
        tope = to_decimal(f.get("hasta_kg"))
        if tope <= 0 or tope < pf:
            continue
        candidatas.append((tope, _texto_fecha(f.get("actualizada_at")), f))
    if not candidatas:
        return None
    candidatas.sort(key=lambda c: (c[0], c[1]), reverse=False)
    menor = candidatas[0][0]
    empatadas = [c for c in candidatas if c[0] == menor]
    return max(empatadas, key=lambda c: c[1])[2]


def _texto_fecha(valor) -> str:
    """Fecha comparable como texto, para desempatar. Lo ilegible ordena primero."""
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor or "")


async def cotizar_referencia(transportista: dict, clave: str, peso_kg,
                             largo_cm=None, ancho_cm=None, alto_cm=None,
                             db=None, dias_frescura: int = DIAS_FRESCURA) -> dict:
    """Lo que ese transportista cobraría, según su matriz. Nunca lanza.

    'clave' es lo que la matriz de ese rol usa para indexar: la UF de origen para
    el de Brasil, la zona de destino para el de Venezuela. El módulo no interpreta
    esa clave, solo la pasa: qué significa es asunto de la ficha del transportista.

    El peso se convierte primero al facturable **de ese transportista**, con su
    divisor y su umbral: la misma caja pesa distinto en cada uno, y buscar en la
    matriz con el peso real daría una franja equivocada.

    Devuelve siempre las mismas claves, con `monto: None` cuando no hay dato y
    `fuente` diciendo por qué:
        matriz            hay fila y se usó
        sin_clave         no llegó una clave con la que buscar
        sin_dato          la matriz no tiene fila para esa clave y ese peso
        precio_invalido   la fila existe pero su precio no es un número usable
        error             la base no respondió
    """
    t = transportista or {}
    if not clave:
        return _referencia(t, clave, fuente="sin_clave")

    try:
        pf = peso_facturable(peso_kg, largo_cm, ancho_cm, alto_cm, t.get("regla_peso") or {})
    except Exception as e:                                   # pragma: no cover
        logger.warning(f"referencias: peso ilegible para {codigo_de(t)}: {e}")
        return _referencia(t, clave, fuente="error")

    try:
        if db is None:
            from database import db as db_real
            db = db_real
        filas = await db.matrices_referencia.find(
            {"transportista_id": t.get("transportista_id"), "clave": clave},
            {"_id": 0},
        ).to_list(None)
    except Exception as e:
        # Una referencia que no se pudo leer no puede tumbar una cotización.
        logger.warning(f"referencias: {codigo_de(t)} / {clave} / {pf} kg no se pudo leer: {e}")
        return _referencia(t, clave, fuente="error", peso_facturable_kg=pf)

    fila = _elegir_franja(filas, pf)
    if not fila:
        # Puede ser una clave que la matriz no cubre, o un paquete más pesado que
        # la última franja cargada. Las dos cosas son "no sé", no un error.
        logger.info(f"referencias: sin fila para {codigo_de(t)} / {clave} / {pf} kg")
        return _referencia(t, clave, fuente="sin_dato", peso_facturable_kg=pf)

    monto = _precio_valido(fila.get("precio"))
    if monto is None:
        logger.warning(
            f"referencias: {codigo_de(t)} / {clave} tiene un precio ilegible: "
            f"{fila.get('precio')!r}"
        )
        return _referencia(t, clave, fuente="precio_invalido", peso_facturable_kg=pf,
                           hasta_kg=to_decimal(fila.get("hasta_kg")))

    actualizada = fila.get("actualizada_at")
    return _referencia(
        t, clave,
        peso_facturable_kg=pf,
        monto=monto,
        moneda=fila.get("moneda") or t.get("moneda"),
        hasta_kg=to_decimal(fila.get("hasta_kg")),
        fuente="matriz",
        origen_dato=fila.get("origen") or "manual",
        actualizada_at=actualizada,
        desactualizada=_esta_vieja(actualizada, dias_frescura),
    )


def _esta_vieja(actualizada_at, dias: int) -> bool:
    """Una matriz que nadie refrescó en un mes sigue orientando, pero avisa.

    Todo lo que no se pueda leer como fecha cuenta como vieja: una matriz que no
    dice cuándo se cargó no puede presentarse como fresca, y un epoch cargado por
    un job en vez de un ISO no puede tirar un AttributeError adentro de la
    función que promete no lanzar.
    """
    if not actualizada_at:
        return True
    if isinstance(actualizada_at, str):
        try:
            actualizada_at = datetime.fromisoformat(actualizada_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    # Un epoch, una lista, un date: todo lo que no sea un datetime cuenta como
    # vieja. Sin esta comprobación, un job que guarda epoch en vez de ISO tira un
    # AttributeError adentro de la función que promete no lanzar.
    if not isinstance(actualizada_at, datetime):
        return True
    if actualizada_at.tzinfo is None:
        # Motor devuelve naive-UTC porque database.py crea el cliente sin
        # tz_aware; interpretarlo como local daría hasta 12 horas de error.
        actualizada_at = actualizada_at.replace(tzinfo=timezone.utc)
    return actualizada_at < datetime.now(timezone.utc) - timedelta(days=dias)


# ─── Las dos referencias de una cotización ────────────────────────────────

async def referencias_para(clave_brasil: str, clave_venezuela: str, peso_kg,
                           largo_cm=None, ancho_cm=None, alto_cm=None,
                           db=None, dias_frescura: int = DIAS_FRESCURA,
                           timeout_s: float = TIMEOUT_S,
                           solo_transportista: str = None) -> list[dict]:
    """Las orientaciones de los dos tramos que el usuario paga por su cuenta.

    Recorre los transportistas activos por ROL. El de Brasil es uno solo hoy; los
    de Venezuela pueden ser varios y el usuario elige, así que se devuelven todos.

    Nunca lanza, nunca cuelga y nunca devuelve una lista muda: si el catálogo no
    se pudo leer aparece una entrada con `fuente: "catalogo_no_disponible"` para
    ese rol, porque "no hay transportistas configurados" y "Mongo no contestó" se
    parecen desde afuera y no son lo mismo — uno lo arregla el super
    administrador y el otro no.

    Las consultas van en paralelo: en serie, cinco lecturas de 200 ms le agregan
    un segundo entero a la cotización, y el precio que RIS App cobra no depende de
    ninguna de ellas.

    `solo_transportista` acota el rol de Venezuela a uno. Es necesario y no una
    optimización: la clave de ese rol es la ZONA, y las zonas son de cada
    transportista —el índice es `[transportista_id, estado]`—, así que buscar
    `"zona_a"` en la matriz de otra empresa devuelve el precio de una zona que
    para ella significa otra cosa. Sin esto, el usuario que elige una agencia ve
    al lado una orientación de una empresa que no contrató, calculada con una
    clave que no es la suya.
    """
    try:
        return await asyncio.wait_for(
            _referencias(clave_brasil, clave_venezuela, peso_kg,
                         largo_cm, ancho_cm, alto_cm, db, dias_frescura,
                         solo_transportista),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning(f"referencias: la orientación no llegó en {timeout_s}s")
        return [_referencia({"rol": rol}, None, fuente="timeout") for rol in ROLES]
    except Exception as e:                                   # pragma: no cover
        logger.warning(f"referencias: la orientación falló entera: {e}")
        return [_referencia({"rol": rol}, None, fuente="error") for rol in ROLES]


async def _referencias(clave_brasil, clave_venezuela, peso_kg,
                       largo_cm, ancho_cm, alto_cm, db, dias_frescura,
                       solo_transportista=None) -> list[dict]:
    salida = []
    for rol, clave in (("brasil", clave_brasil), ("venezuela", clave_venezuela)):
        transportistas, ok = await _catalogo(rol, db=db)
        if not ok:
            salida.append(_referencia({"rol": rol}, clave, fuente="catalogo_no_disponible"))
            continue
        if rol == "venezuela" and solo_transportista:
            transportistas = [t for t in transportistas
                              if t.get("transportista_id") == solo_transportista]
        if not transportistas:
            continue
        resultados = await asyncio.gather(*[
            cotizar_referencia(t, clave, peso_kg, largo_cm, ancho_cm, alto_cm,
                               db=db, dias_frescura=dias_frescura)
            for t in transportistas
        ], return_exceptions=True)
        for t, r in zip(transportistas, resultados):
            if isinstance(r, Exception):                     # pragma: no cover
                logger.warning(f"referencias: {codigo_de(t)} falló entero: {r}")
                r = _referencia(t, clave, fuente="error")
            salida.append(r)
    return salida


def resumen(referencias: list[dict]) -> dict:
    """Lo que la pantalla necesita saber para redactar el bloque de orientación.

    Deliberadamente NO devuelve una suma de montos, ni en Decimal ni en float.
    Sumarlos daría un número que parece un total y no lo es —son dos contratos
    distintos, con dos empresas distintas, en dos monedas distintas—, y ese número
    terminaría algún día al lado del que RIS App sí cobra.
    """
    refs = referencias or []
    con_dato = [r for r in refs if r.get("monto") is not None]
    return {
        "total_transportistas": len(refs),
        "con_dato": len(con_dato),
        "sin_dato": len(refs) - len(con_dato),
        "hay_desactualizadas": any(r.get("desactualizada") for r in con_dato),
        "hay_problemas": any(r.get("fuente") in ("error", "timeout",
                                                 "catalogo_no_disponible") for r in refs),
        "monedas": sorted({r.get("moneda") for r in con_dato if r.get("moneda")}),
        "completo": bool(refs) and len(con_dato) == len(refs),
    }


# ─── Que hay cargado en la matriz, para el panel ──────────────────────────

async def claves_cargadas(transportista_id: str, db=None) -> tuple[set, bool]:
    """(claves con al menos una fila, se_pudo_leer).

    Existe para que el panel pueda decir QUE FALTA sin que nadie lo descubra por
    un bloque de referencia mudo en la pantalla de un usuario. Cruzada contra los
    origenes activos da «tenes 4 origenes en UF sin precio»; cruzada contra las
    zonas de las agencias, lo mismo del lado venezolano.

    Devuelve un `set` y no una lista: quien llama cruza, no enumera.

    El segundo valor separa «no hay ninguna clave cargada» de «no pude leer la
    matriz». Sin esa distincion, un hipo de la base le diria al super
    administrador que tiene que cargar de nuevo todos los precios.
    """
    if not transportista_id:
        return set(), True
    try:
        if db is None:
            from database import db as db_real
            db = db_real
        filas = await db.matrices_referencia.find(
            {"transportista_id": transportista_id}, {"_id": 0, "clave": 1},
        ).to_list(None)
    except Exception as e:
        logger.warning(f"referencias: no se pudieron leer las claves de "
                       f"{transportista_id}: {e}")
        return set(), False
    return {str(f.get("clave")).strip() for f in (filas or [])
            if str(f.get("clave") or "").strip()}, True
