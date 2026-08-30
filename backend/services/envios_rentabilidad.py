"""
services/envios_rentabilidad.py — Que dejo cada viaje, y que precio se vio.

DOS PREGUNTAS QUE SE CONTESTAN CON LOS MISMOS DATOS
    1. ¿CUANTO DEJO ESTE VIAJE? Lo que se cobro por los paquetes de un lote,
       menos lo que costo ir a buscarlos. Es la unica forma de saber si el
       negocio cierra, y hoy se contesta a mano con una planilla.

    2. ¿CUANTO COBRA DE VERDAD CADA TRAMO? Cada envio deja dos precios
       observados: lo que el usuario pago en el mostrador de origen y lo que el
       transportista de destino pidio en Santa Elena. Son precios REALES, de
       operaciones reales, y son mucho mejores que cualquier matriz cargada a
       mano hace tres meses.

NINGUNA SUGERENCIA SE ESCRIBE SOLA
    Es la regla dura de este modulo. Se PROPONE llevar un valor observado a la
    matriz de referencia, y alguien lo aprueba. Un job que corrige precios solo
    es un job que un dia mueve un numero por una muestra rara y nadie se entera
    hasta que un usuario pregunta por que le dijimos que iba a pagar el doble.

    Por eso `sugerencias()` solo lee, y `aprobar()` es una funcion aparte que
    exige que alguien la llame con un valor concreto.

LO OBSERVADO NO ES LO FACTURADO
    Ninguno de estos numeros toca lo que RIS App cobra. Son los dos tramos que
    el usuario paga por su cuenta, y sirven para que la ORIENTACION que se le
    muestra al proximo se parezca a la realidad. La tarifa propia se edita en su
    consola y no sale de aca.

POCAS MUESTRAS NO SON UNA CONCLUSION
    Una sugerencia con dos observaciones y una dispersion del 40 % no es un
    precio: es ruido. Por eso cada propuesta viaja con `muestras` y `dispersion`,
    y con un `confiable` que dice si el modulo se animaria a usarla. Ocultar eso
    y mostrar solo el promedio es como se toman decisiones con tres datos.
"""

import logging
import statistics
import uuid
from datetime import datetime, timedelta, timezone

from services.money import ZERO, quantize_money, to_decimal

logger = logging.getLogger(__name__)

# Cuantas observaciones hacen falta para que una sugerencia se considere algo
# mas que una anecdota, y cuanta dispersion se tolera.
MUESTRAS_MINIMAS = 4
DISPERSION_MAXIMA = 0.25          # 25 % del promedio
DIAS_A_MIRAR = 90


class RentabilidadRechazada(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def _numero(valor):
    """Un Decimal usable, o None. Nunca lanza y nunca inventa un cero.

    Un cero inventado acá no es inocuo: entra al promedio y baja el precio
    observado de un tramo, que es exactamente el número que después se le
    muestra a otro usuario como orientación.
    """
    if valor is None or valor == "":
        return None
    try:
        numero = to_decimal(valor)
    except Exception:                                         # pragma: no cover
        return None
    if not numero.is_finite() or numero <= ZERO:
        return None
    return numero


# ─── 1. Rentabilidad por viaje ────────────────────────────────────────────

async def por_lote(lote_id: str, db=None) -> dict:
    """Qué dejó un viaje a Pacaraima. Nunca lanza.

    Agrupa lo que se cobró por los paquetes que volvieron en ese viaje. El costo
    del viaje —combustible, peajes, horas— se carga a mano en el lote: no hay
    forma de deducirlo, y estimarlo sería inventar el único número que hace que
    la cuenta signifique algo.
    """
    base = await _db(db)
    try:
        lote = await base.envios_lotes.find_one({"lote_id": lote_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el lote {lote_id}: {e}")
        raise RentabilidadRechazada(
            "No se pudo leer el viaje. Reintentá en un momento.", http=503) from e
    if not lote:
        raise RentabilidadRechazada("Ese viaje no existe.", http=404)

    try:
        envios = await base.envios.find(
            {"origen.lote_retiro_id": lote_id},
            {"_id": 0, "envio_id": 1, "display_id": 1, "estado": 1, "cobros": 1,
             "paquete": 1, "origen": 1, "destino": 1},
        ).to_list(500)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudieron leer los envíos de {lote_id}: {e}")
        envios = []

    cobrado = ZERO
    pendiente = ZERO
    peso = ZERO
    detalle = []
    for envio in envios or []:
        cobros = envio.get("cobros") or {}
        de_este = ZERO
        impago_de_este = ZERO
        for partida in ("inicial", "ajuste"):
            doc = cobros.get(partida)
            if not isinstance(doc, dict) or not doc:
                continue
            monto = _numero(doc.get("monto_ris")) or ZERO
            if doc.get("estado") == "pagado":
                de_este += monto
            else:
                impago_de_este += monto
        devuelto = _numero((cobros.get("devolucion") or {}).get("monto_ris")) or ZERO
        de_este -= devuelto

        cobrado += de_este
        pendiente += impago_de_este
        verificado = (envio.get("paquete") or {}).get("verificado") or {}
        kilos = _numero(verificado.get("peso_kg")) or ZERO
        peso += kilos
        detalle.append({
            "envio_id": envio.get("envio_id"),
            "display_id": envio.get("display_id"),
            "estado": envio.get("estado"),
            "cobrado_ris": str(quantize_money(de_este)),
            "pendiente_ris": str(quantize_money(impago_de_este)),
            "peso_verificado_kg": str(kilos) if kilos else None,
        })

    costo = _numero(lote.get("costo_viaje_ris"))
    resultado = None if costo is None else quantize_money(cobrado - costo)
    return {
        "lote_id": lote_id,
        "retirado_por": lote.get("retirado_por"),
        "created_at": lote.get("created_at"),
        "cuantos": len(envios or []),
        "cobrado_ris": str(quantize_money(cobrado)),
        # Lo pendiente se muestra APARTE y no se suma al cobrado. Sumarlo daría
        # un viaje rentable con plata que todavía no entró, que es la forma
        # clásica de creerse rentable seis meses seguidos.
        "pendiente_ris": str(quantize_money(pendiente)),
        "peso_total_kg": str(peso),
        "costo_viaje_ris": None if costo is None else str(quantize_money(costo)),
        "resultado_ris": None if resultado is None else str(resultado),
        "costo_por_kg_ris": (
            None if costo is None or peso <= ZERO
            else str(quantize_money(costo / peso))),
        "falta_el_costo": costo is None,
        "envios": detalle,
    }


async def cargar_costo(operador, lote_id: str, costo, db=None, ahora=None) -> dict:
    """Carga a mano lo que costó el viaje. Es el único número que no se deduce."""
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    monto = _numero(costo)
    if monto is None:
        raise RentabilidadRechazada(
            "Cargá lo que costó el viaje: combustible, peajes y horas. Sin ese número "
            "la cuenta del viaje no significa nada.")
    try:
        actualizado = await base.envios_lotes.find_one_and_update(
            {"lote_id": lote_id},
            {"$set": {"costo_viaje_ris": str(quantize_money(monto)),
                      "costo_cargado_por": getattr(operador, "user_id", None),
                      "costo_cargado_at": ahora}},
            return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo cargar el costo de {lote_id}: {e}")
        raise RentabilidadRechazada(
            "No se pudo guardar. Reintentá en un momento.", http=503) from e
    if actualizado is None:
        raise RentabilidadRechazada("Ese viaje no existe.", http=404)
    return await por_lote(lote_id, db=base)


# ─── 2. Los precios observados ────────────────────────────────────────────

async def observaciones(db=None, ahora=None, dias: int = DIAS_A_MIRAR) -> list[dict]:
    """Lo que costó de verdad cada tramo, sacado de las operaciones. Nunca lanza.

    Dos fuentes, las dos de datos reales:
      ORIGEN — `origen.monto_pagado_brl`, lo que el usuario declaró haber pagado
      en el mostrador de Brasil, indexado por su UF.
      DESTINO — `flete.monto_acordado_ris`, lo que el transportista de destino
      pidió en Santa Elena, indexado por la zona de la agencia.
    """
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(days=max(1, min(int(dias or DIAS_A_MIRAR), 365)))
    base = await _db(db)
    try:
        envios = await base.envios.find(
            {},
            {"_id": 0, "created_at": 1, "origen": 1, "destino": 1, "flete": 1,
             "paquete": 1},
        ).sort("created_at", -1).to_list(2000)
    except Exception as e:
        logger.warning(f"envios: no se pudieron leer las observaciones: {e}")
        return []

    crudas = {}
    for envio in envios or []:
        creado = _fecha(envio.get("created_at"))
        if creado is not None and creado < desde:
            continue
        peso = _peso_facturado(envio)
        if peso is None:
            continue

        uf = ((envio.get("origen") or {}).get("uf") or "").strip().upper()
        pagado = _numero((envio.get("origen") or {}).get("monto_pagado_brl"))
        if uf and pagado is not None:
            crudas.setdefault(("brasil", uf, _franja(peso)), []).append(pagado)

        zona = (envio.get("destino") or {}).get("zona_tarifa")
        flete = _numero((envio.get("flete") or {}).get("monto_acordado_ris"))
        if zona and flete is not None:
            crudas.setdefault(("venezuela", str(zona), _franja(peso)), []).append(flete)

    return sorted((_resumen(rol, clave, hasta, valores)
                   for (rol, clave, hasta), valores in crudas.items()),
                  key=lambda o: (o["rol"], o["clave"], float(o["hasta_kg"])))


def _peso_facturado(envio: dict):
    """El peso con el que se facturó: el verificado, y si no, el declarado.

    El verificado primero porque es el que salió de nuestra balanza. Usar el
    declarado cuando existe el verificado metería en la muestra un peso que
    nadie confirmó.
    """
    paquete = envio.get("paquete") or {}
    for bloque in ("verificado", "declarado"):
        peso = _numero((paquete.get(bloque) or {}).get("peso_kg"))
        if peso is not None:
            return peso
    return None


# Las franjas de peso de la matriz. Se agrupa por franja y no por peso exacto
# porque una matriz de referencia tiene franjas: un promedio de precios de
# paquetes de 1 kg y de 9 kg no es el precio de ninguno de los dos.
_FRANJAS = ("1", "3", "5", "10", "20", "30")


def _franja(peso) -> str:
    for tope in _FRANJAS:
        if peso <= to_decimal(tope):
            return tope
    return _FRANJAS[-1]


def _resumen(rol: str, clave: str, hasta: str, valores: list) -> dict:
    numeros = [float(v) for v in valores]
    promedio = statistics.fmean(numeros)
    dispersion = (statistics.pstdev(numeros) / promedio) if promedio else 0.0
    confiable = (len(numeros) >= MUESTRAS_MINIMAS
                 and dispersion <= DISPERSION_MAXIMA)
    return {
        "rol": rol,
        "clave": clave,
        "hasta_kg": hasta,
        "muestras": len(numeros),
        "promedio": str(quantize_money(to_decimal(str(promedio)))),
        "mediana": str(quantize_money(to_decimal(str(statistics.median(numeros)))))
        ,
        "minimo": str(quantize_money(to_decimal(str(min(numeros))))),
        "maximo": str(quantize_money(to_decimal(str(max(numeros))))),
        "dispersion": round(dispersion, 3),
        # Lo que el modulo se animaria a usar. Se muestra siempre, junto con las
        # muestras: ocultarlo y dar solo el promedio es como se toman decisiones
        # con tres datos.
        "confiable": confiable,
        "por_que_no": None if confiable else (
            f"solo {len(numeros)} observaciones" if len(numeros) < MUESTRAS_MINIMAS
            else f"los precios varían un {round(dispersion * 100)} %"),
    }


def _fecha(valor):
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


# ─── 3. Aprobar: lo unico que escribe ─────────────────────────────────────

async def aprobar(admin, *, transportista_id: str, clave: str, hasta_kg,
                  precio, moneda: str = None, db=None, ahora=None) -> dict:
    """Lleva un valor a la matriz de referencia. **Nadie más escribe ahí.**

    Es una función aparte y no el final de `observaciones()` a propósito: un job
    que corrige precios solo es un job que un día mueve un número por una muestra
    rara, y nadie se entera hasta que un usuario pregunta por qué le dijimos que
    iba a pagar el doble.

    La fila queda con `origen: "observado"`, que es lo que después permite
    distinguir un precio que vimos de uno que alguien tipeó.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)

    monto = _numero(precio)
    tope = _numero(hasta_kg)
    if monto is None or tope is None or not (clave or "").strip():
        raise RentabilidadRechazada(
            "Falta la clave, el tope de peso o el precio. Los tres tienen que ser "
            "valores usables.")

    fila = {
        "transportista_id": transportista_id,
        "clave": str(clave).strip(),
        "hasta_kg": str(tope),
        "precio": str(quantize_money(monto)),
        "moneda": (moneda or "").strip() or None,
        "origen": "observado",
        "actualizada_at": ahora,
        "aprobada_por": getattr(admin, "user_id", None),
    }
    try:
        await base.matrices_referencia.update_one(
            {"transportista_id": transportista_id, "clave": fila["clave"],
             "hasta_kg": fila["hasta_kg"]},
            {"$set": fila}, upsert=True)
    except Exception as e:
        logger.error(f"envios: no se pudo aprobar la observación: {e}")
        raise RentabilidadRechazada(
            "No se pudo guardar en la matriz. Reintentá en un momento.",
            http=503) from e

    try:
        from services.envios_config import auditar
        await auditar("matriz_referencia", {}, fila, admin, db=base,
                      accion="aprobar_observado")
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo auditar la aprobación: {e}")
    return {"ok": True, "fila": fila}
