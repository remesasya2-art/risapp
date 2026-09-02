"""
services/envios_origenes.py — El catalogo de ciudades de Brasil desde donde se despacha.

POR QUE EXISTE
    La matriz de referencia del transportista de Brasil se indexa por la UF de
    origen. Esa UF esta adentro del CEP que el usuario escribe, pero hoy el
    formulario le pide las tres cosas por separado —CEP, ciudad y UF— y la UF
    llega tipeada a mano. Un error de dos letras trae el precio de otro estado
    sin que nadie se entere: la referencia sale, es plausible, y esta mal.

    Con el catalogo la cadena se cierra sola:

        el usuario elige su ciudad -> CEP -> UF -> clave de la matriz -> precio

    y el super administrador es el unico que escribe una UF, una sola vez por
    ciudad, mirando lo que carga.

DOS COLECCIONES

    `origenes_brasil`     el catalogo. Lo carga el panel, de a uno o por CSV.
    `origenes_propuestos` lo que la gente pidio y no estaba. Es una COLA, no un
                          catalogo: nada entra solo.

POR QUE NADA SE ESCRIBE SOLO
    Es la misma regla que ya rige para los precios observados, y por el mismo
    motivo: un catalogo que se autocompleta es un catalogo donde un error de
    tipeo se vuelve permanente sin que nadie lo mire. Alguien escribe "SP" para
    una ciudad de Minas y a partir de ahi todos los envios de esa ciudad cotizan
    contra la matriz equivocada.

SIN DATOS PERSONALES EN LA COLA
    `origenes_propuestos` guarda el conteo y las fechas, nunca quien lo pidio.
    Para decidir si una ciudad entra al catalogo no hace falta saber de quien era
    el paquete, y un `user_id` ahi seria un dato personal en una coleccion que se
    lee para tomar una decision de negocio.
"""

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Las 27 unidades federativas. Es una lista CERRADA a proposito: es la clave con
# la que se busca el precio, y aceptar cualquier cosa de dos letras es aceptar
# que "SP " o "Sp" o "XX" queden guardadas como si fueran un estado.
UF_BRASIL = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)

_SOLO_DIGITOS = re.compile(r"\D")


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


# ─── El CEP: una sola forma adentro, otra afuera ──────────────────────────

def normalizar_cep(valor) -> str | None:
    """Ocho digitos, sin guion ni espacios. None si no es un CEP.

    Se guarda normalizado y se muestra con guion. Sin esto, "01310-100" y
    "01310100" son dos filas distintas para la misma ciudad, y el indice unico
    —que es lo que impide el duplicado— no sirve de nada.
    """
    if valor is None:
        return None
    limpio = _SOLO_DIGITOS.sub("", str(valor))
    return limpio if len(limpio) == 8 else None


def formatear_cep(valor) -> str:
    """Con guion, como lo escribe la gente: 01310-100."""
    limpio = normalizar_cep(valor)
    return f"{limpio[:5]}-{limpio[5:]}" if limpio else str(valor or "")


def normalizar_uf(valor) -> str | None:
    """Dos letras mayusculas y de la lista. None si no es una UF."""
    if valor is None:
        return None
    limpio = str(valor).strip().upper()
    return limpio if limpio in UF_BRASIL else None


def _texto(valor, maximo: int) -> str:
    return str(valor or "").strip()[:maximo]


def validar(cep, ciudad, uf) -> tuple[dict | None, list[str]]:
    """(fila normalizada, errores). No lanza: el que llama decide el HTTP.

    Es una funcion aparte de las rutas porque la usan las tres vias de carga
    —alta manual, CSV y aprobacion de un propuesto— y las tres tienen que
    rechazar exactamente lo mismo. Una validacion por via es una via con un
    agujero.
    """
    errores = []
    limpio = normalizar_cep(cep)
    if limpio is None:
        errores.append(f"El CEP {str(cep or '').strip()!r} no tiene ocho dígitos.")
    ciudad_limpia = _texto(ciudad, 80)
    if len(ciudad_limpia) < 2:
        errores.append("La ciudad no puede estar vacía.")
    uf_limpia = normalizar_uf(uf)
    if uf_limpia is None:
        errores.append(
            f"{str(uf or '').strip().upper()!r} no es una UF de Brasil. Son dos letras, "
            f"de la lista de 27.")
    if errores:
        return None, errores
    return {"cep": limpio, "ciudad": ciudad_limpia, "uf": uf_limpia}, []


# ─── El catalogo ──────────────────────────────────────────────────────────

_PROYECCION = {"_id": 0, "cep": 1, "ciudad": 1, "uf": 1, "activo": 1}


def _activo(fila) -> bool:
    """Un origen esta activo salvo que diga que no.

    Mismo criterio que agencias y transportistas, y se comprueba en Python por
    lo mismo: `{"activo": True}` en Mongo no matchea un `1` ni un `"true"`, y un
    origen cargado por CSV desapareceria del formulario sin un solo log.
    """
    valor = fila.get("activo", True)
    if isinstance(valor, str):
        return valor.strip().lower() not in ("false", "no", "0", "off", "", "none", "null")
    return bool(valor)


async def listar(db=None, solo_activos: bool = True) -> tuple[list[dict], bool]:
    """(origenes, se_pudo_leer). Ordenados por UF y despues por ciudad.

    El segundo valor NO es decorativo: una lectura fallida y un catalogo vacio
    mandan a lugares distintos —«esperá y reintentá» contra «cargá el primero»—
    y confundirlos hace que alguien reimporte un CSV encima de datos que si
    estaban.
    """
    try:
        base = await _db(db)
        filas = await base.origenes_brasil.find({}, _PROYECCION).sort(
            [("uf", 1), ("ciudad", 1)]).to_list(None)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el catálogo de orígenes: {e}")
        return [], False
    if solo_activos:
        filas = [f for f in filas if _activo(f)]
    return [{"cep": f.get("cep"), "cep_legible": formatear_cep(f.get("cep")),
             "ciudad": f.get("ciudad"), "uf": f.get("uf"),
             **({} if solo_activos else {"activo": _activo(f)})}
            for f in filas], True


async def buscar_uf(cep, db=None) -> str | None:
    """La UF del catalogo para ese CEP, o None si no esta.

    Es la traduccion que cierra la cadena. Devuelve None —y no lanza— cuando no
    hay dato o la base no contesta: un origen que no esta en el catalogo cotiza
    igual, solo que sin referencia del tramo brasileño.
    """
    limpio = normalizar_cep(cep)
    if limpio is None:
        return None
    try:
        base = await _db(db)
        fila = await base.origenes_brasil.find_one({"cep": limpio}, _PROYECCION)
    except Exception as e:
        logger.warning(f"envios: no se pudo buscar el CEP {limpio}: {e}")
        return None
    return fila.get("uf") if fila and _activo(fila) else None


async def guardar(fila: dict, admin=None, db=None, ahora=None) -> dict:
    """Alta o edicion de un origen, por su CEP. Devuelve el documento guardado.

    Es un upsert por `cep` y no un insert: el CEP es la identidad de la fila —lo
    dice su indice unico— y cargar dos veces la misma ciudad tiene que corregir,
    no fallar ni duplicar. Es lo que hace que el CSV se pueda volver a subir
    corregido sin limpiar nada antes.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    doc = {**fila, "activo": fila.get("activo", True)}
    await base.origenes_brasil.update_one(
        {"cep": doc["cep"]},
        {"$set": doc,
         "$setOnInsert": {"creado_at": ahora,
                          "creado_por": getattr(admin, "user_id", None)}},
        upsert=True)
    return doc


# ─── La cola de propuestos ────────────────────────────────────────────────

async def registrar_propuesto(cep, ciudad, uf, db=None, ahora=None) -> bool:
    """Alguien cotizo desde un CEP que no esta en el catalogo. Queda anotado.

    SIN `user_id` NI NINGUN DATO PERSONAL. Se guarda el conteo y las fechas: para
    decidir si una ciudad entra al catalogo alcanza con saber cuantos la
    pidieron, y no hace falta saber de quien era el paquete.

    El indice unico por `cep` hace que el segundo pedido INCREMENTE el contador
    en vez de crear otra fila. Sin eso la cola se llena de la misma ciudad y el
    orden por `pedidos` —que es lo que dice cual cargar primero— no significa
    nada.

    Devuelve si se pudo anotar. NUNCA lanza: esto es telemetria y corre adentro
    de una cotizacion. Que no se pueda escribir una sugerencia no puede tumbar
    el precio que el usuario esta esperando.
    """
    limpio = normalizar_cep(cep)
    if limpio is None:
        return False
    ahora = ahora or datetime.now(timezone.utc)
    try:
        base = await _db(db)
        await base.origenes_propuestos.update_one(
            {"cep": limpio},
            {"$inc": {"pedidos": 1},
             "$set": {"ciudad": _texto(ciudad, 80),
                      "uf": normalizar_uf(uf), "ultima_at": ahora},
             "$setOnInsert": {"primera_at": ahora, "estado": "pendiente"}},
            upsert=True)
        return True
    except Exception as e:
        logger.warning(f"envios: no se pudo anotar el origen propuesto {limpio}: {e}")
        return False


async def listar_propuestos(db=None, estado: str = "pendiente") -> tuple[list[dict], bool]:
    """(propuestos, se_pudo_leer), del mas pedido al menos pedido.

    El orden es la mitad del valor de esta pantalla: siete personas pidiendo el
    mismo CEP vale mas que una, y una cola sin ordenar obliga a leerla entera
    para descubrirlo.
    """
    try:
        base = await _db(db)
        filas = await base.origenes_propuestos.find(
            {"estado": estado} if estado else {},
            {"_id": 0, "cep": 1, "ciudad": 1, "uf": 1, "pedidos": 1,
             "primera_at": 1, "ultima_at": 1, "estado": 1, "motivo": 1},
        ).sort([("pedidos", -1), ("ultima_at", -1)]).to_list(None)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la cola de orígenes propuestos: {e}")
        return [], False
    return [{**f, "cep_legible": formatear_cep(f.get("cep"))} for f in filas], True


async def resolver_propuesto(cep, estado: str, motivo: str = None,
                             db=None, ahora=None) -> bool:
    """Marca un propuesto como aprobado o descartado. No lo borra.

    Nada se borra en todo el modulo, y acá menos: el descarte es informacion.
    Sin la fila, la misma ciudad vuelve a la cola en la proxima cotizacion y
    alguien la vuelve a evaluar desde cero, sin saber que ya se decidio que no.
    """
    limpio = normalizar_cep(cep)
    if limpio is None:
        return False
    base = await _db(db)
    resultado = await base.origenes_propuestos.update_one(
        {"cep": limpio},
        {"$set": {"estado": estado, "motivo": _texto(motivo, 300) or None,
                  "resuelto_at": ahora or datetime.now(timezone.utc)}})
    return bool(getattr(resultado, "matched_count", 0))
