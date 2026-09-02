"""
services/envios_operacion.py — El panel del operador: lo que pasa con el paquete.

DE QUE SE OCUPA
    De los cinco momentos en que alguien del equipo toca un envio:

      1. AVISAR que llego a la agencia de Pacaraima y arranca el reloj de guarda.
      2. RETIRARLO del mostrador, por LOTE: nadie va a la agencia por un paquete.
      3. REPESARLO con balanza propia. Aca se cierra el precio.
      4. SACARLO de Pacaraima hacia Santa Elena.
      5. ENTREGARLO en la oficina del transportista, con guia y foto.

EL REPESAJE ES EL UNICO MOMENTO EN QUE EL PRECIO SE CIERRA
    Hasta ahi todo fue estimado: la cotizacion sobre lo que el usuario declaro, y
    el cobro inicial sobre lo que midio el transportista de origen. La balanza
    propia es la ultima palabra, y el ajuste tiene TRES ramas —cobrar, devolver,
    no hacer nada— porque un ajuste que solo sube no es un ajuste, es un
    recargo.

LA UNICA PALANCA DE COBRO ES LA POSESION FISICA
    El paquete no sale de Pacaraima con una partida impaga. No es una decision
    de este modulo: es la unica forma real que tiene el negocio de cobrar, y por
    eso esta escrita como invariante en `puede_transicionar` y no como una
    condicion suelta en una ruta.

    Lo contrario tambien: mientras el paquete esta viajando por Brasil, una deuda
    NO frena nada. El paquete no depende de nosotros y no hay nada que retener.

LA COLA SE AGRUPA POR EL NOMBRE CONGELADO
    Quien viaja a Pacaraima necesita saber a que nombre estan rotulados los
    paquetes, porque en el mostrador van a comparar la etiqueta contra un
    documento. Agrupar por el retirador de HOY seria mandarlo a reclamar cajas
    que no puede reclamar.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from services.envios_estados import (SALIDA_DE_PACARAIMA, es_terminal,
                                     partidas_impagas, puede_transicionar)
from services.money import ZERO, quantize_money, to_decimal

logger = logging.getLogger(__name__)

# Cuantos dias guarda la agencia un paquete antes de devolverlo al remitente. Es
# configurable y este es el piso: el producto que hay que usar da 30 dias
# corridos, contados desde que el objeto queda disponible para retiro.
DIAS_GUARDA_POR_DEFECTO = 30
TOPE_LOTE = 200


class OperacionRechazada(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def nuevo_lote_id() -> str:
    return f"lot_{uuid.uuid4().hex[:10]}"


# ─── La cola ──────────────────────────────────────────────────────────────

async def cola(estado: str = "disponible_retiro", db=None, limite: int = 200,
               ahora=None) -> dict:
    """Los envíos en un estado, AGRUPADOS POR EL NOMBRE ROTULADO.

    El agrupamiento es lo que hace útil esta pantalla. Quien viaja a Pacaraima
    va a reclamar cajas en un mostrador donde comparan la etiqueta contra un
    documento: necesita saber cuáles puede reclamar él y cuáles no, y eso lo dice
    el nombre CONGELADO en cada envío, no quién esté de turno hoy.
    """
    ahora = ahora or datetime.now(timezone.utc)
    try:
        base = await _db(db)
        filas = await base.envios.find(
            {"estado": estado},
            {"_id": 0, "envio_id": 1, "display_id": 1, "user_id": 1, "estado": 1,
             "origen": 1, "destino": 1, "destino_brasil": 1, "cobros": 1,
             "created_at": 1,
             # Sin estos dos, `_fila_de_cola` no puede decir si el flete traba la
             # entrega y la cola contesta que si a todo. Un campo que existe en
             # la base y se pierde en la proyeccion es peor que uno que falta:
             # la respuesta se ve completa.
             "modalidad_flete": 1, "flete": 1},
        ).sort("created_at", 1).to_list(limite + 1)
    except Exception as e:
        logger.error(f"envios: no se pudo leer la cola de {estado}: {e}")
        return {"estado": estado, "grupos": [], "total": 0, "degradado": True}

    # Se pide uno mas para poder DECIR que hay mas. Truncar en silencio hace que
    # quien viaja a Pacaraima arme la lista con doscientos y deje las cajas 201 a
    # 250 en el mostrador consumiendo dias de guarda, sin ninguna senal.
    hay_mas = len(filas or []) > limite
    filas = (filas or [])[:limite]

    grupos = {}
    for envio in filas or []:
        nombre = ((envio.get("destino_brasil") or {}).get("retirador_nombre")
                  or "Sin nombre en la etiqueta")
        grupos.setdefault(nombre, []).append(_fila_de_cola(envio, ahora))

    return {
        "estado": estado,
        "total": len(filas or []),
        "hay_mas": hay_mas,
        "grupos": [{"retirador_nombre": nombre, "envios": envios,
                    "cuantos": len(envios)}
                   for nombre, envios in sorted(grupos.items())],
        "degradado": False,
    }


def _fila_de_cola(envio: dict, ahora) -> dict:
    origen = envio.get("origen") or {}
    vence = _fecha(origen.get("guarda_vence_at"))
    impagas = partidas_impagas(envio)
    return {
        "envio_id": envio.get("envio_id"),
        "display_id": envio.get("display_id"),
        "codigo_objeto": origen.get("codigo_objeto"),
        # El operador necesita PODER MIRAR la foto que despues se le pide
        # verificar. Sin el asset, el paso de verificacion es tipear un peso a
        # ciegas.
        "comprobante_asset_id": origen.get("comprobante_asset_id"),
        "comprobante_verificado": bool((origen.get("verificado") or {}).get("at")),
        # Y si esa misma foto ya estaba en otro envio: es la forma barata de
        # intentar que a uno de los dos no se lo cobren.
        "foto_repetida_en": origen.get("foto_repetida_en"),
        "agencia_destino": (envio.get("destino") or {}).get("agencia_nombre"),
        "estado_ve": (envio.get("destino") or {}).get("estado_ve"),
        "guarda_vence_at": vence,
        "dias_de_guarda_restantes": (
            None if vence is None else (vence - ahora).days),
        # Se muestra en la cola porque es lo que decide si el paquete puede
        # salir de Pacaraima, y el operador tiene que saberlo ANTES de cargar la
        # camioneta y no después.
        "partidas_impagas": impagas,
        "puede_salir": not impagas,
        # Y lo mismo para el OTRO candado, el de la entrega. El operador estaba
        # llenando el numero de guia, adjuntando la foto del remito, apretando
        # «Registrar la entrega» y RECIEN AHI se enteraba de que el flete no
        # estaba acreditado. Con el paquete en el mostrador y el cliente
        # enfrente. El candado esta bien —no se suelta un paquete contra una
        # remesa que nadie vio llegar—; lo que estaba mal es enterarse al final.
        "flete_modalidad": (envio.get("modalidad_flete") or "contra_entrega"),
        "flete_estado": ((envio.get("flete") or {}).get("estado") or "sin_registrar"),
        "puede_entregar": not _flete_impago(envio),
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


# ─── 1. Llegó a la agencia ────────────────────────────────────────────────

async def marcar_disponible(operador, envio_id: str, *, db=None, ahora=None,
                            dias_guarda: int = None) -> dict:
    """El paquete está en el mostrador. Arranca el reloj de guarda.

    Ese reloj es el parámetro operativo más caro del módulo: pasado el plazo, la
    agencia devuelve el paquete al remitente, con el costo del retorno y un
    usuario que ya pagó. Se guarda la fecha de vencimiento CALCULADA y no solo
    los días, para que cambiar la configuración no le mueva el vencimiento a los
    paquetes que ya están esperando.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)
    _exigir_transicion(envio, "disponible_retiro", "admin")

    dias = await _dias_de_guarda(base, dias_guarda)
    parche = {
        "estado": "disponible_retiro",
        "origen.disponible_retiro_at": ahora,
        "origen.guarda_vence_at": ahora + timedelta(days=dias),
        "origen.dias_guarda": dias,
    }
    actualizado = await _mover(base, envio, "disponible_retiro", parche, operador,
                              ahora, detalle={"dias_guarda": dias})
    return {"ok": True, "envio_id": envio_id, "estado": "disponible_retiro",
            "guarda_vence_at": actualizado["origen"]["guarda_vence_at"]}


async def _dias_de_guarda(base, explicito) -> int:
    if explicito is not None:
        try:
            return max(1, min(int(explicito), 180))
        except (TypeError, ValueError):
            pass
    from services.envios_config import leer
    operacion = await leer("operacion", db=base) or {}
    try:
        return max(1, min(int(operacion.get("dias_guarda")), 180))
    except (TypeError, ValueError):
        return DIAS_GUARDA_POR_DEFECTO


# ─── 2. Retiro por lote ───────────────────────────────────────────────────

async def retirar_lote(operador, codigos: list, *, db=None, ahora=None,
                       nota: str = "") -> dict:
    """Retira varios paquetes del mostrador de una vez, por código de objeto.

    Es por lote porque nadie viaja a Pacaraima por un paquete: se va con una
    lista y se vuelve con una camioneta. Y por CÓDIGO DE OBJETO porque es lo que
    está impreso en la caja que el operador tiene en la mano — pedirle el
    `envio_id` sería pedirle que busque cada caja en una pantalla.

    Un código desconocido NO aborta el lote. El operador está en un mostrador con
    treinta cajas: que una no se reconozca no puede hacerle perder las
    veintinueve que sí. Vuelven en `rechazados`, con el motivo de cada una.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)

    limpios, invalidos = [], []
    for bruto in (codigos or [])[:TOPE_LOTE]:
        try:
            from services.envios_comprobante import normalizar_codigo
            limpios.append(normalizar_codigo(bruto))
        except Exception:
            invalidos.append({"codigo": str(bruto)[:40], "motivo": "formato"})
    if not limpios and not invalidos:
        raise OperacionRechazada("El lote llegó vacío: no hay nada que retirar.")

    lote_id = nuevo_lote_id()
    retirados, rechazados = [], list(invalidos)

    for codigo in limpios:
        try:
            envio = await base.envios.find_one(
                {"origen.codigo_objeto": codigo}, {"_id": 0})
        except Exception as e:                                # pragma: no cover
            logger.error(f"envios: no se pudo leer el código {codigo}: {e}")
            rechazados.append({"codigo": codigo, "motivo": "no_se_pudo_leer"})
            continue
        if not envio:
            rechazados.append({"codigo": codigo, "motivo": "desconocido"})
            continue

        problema = puede_transicionar(envio.get("estado") or "",
                                      "recibido_pacaraima", "admin")
        if problema:
            rechazados.append({"codigo": codigo, "envio_id": envio.get("envio_id"),
                               "display_id": envio.get("display_id"),
                               "motivo": "estado", "detalle": problema})
            continue

        try:
            actualizado = await _mover(
                base, envio, "recibido_pacaraima",
                {"estado": "recibido_pacaraima", "origen.retirado_at": ahora,
                 "origen.retirado_por": getattr(operador, "user_id", None),
                 "origen.lote_retiro_id": lote_id},
                operador, ahora, detalle={"lote_retiro_id": lote_id})
        except OperacionRechazada as e:
            rechazados.append({"codigo": codigo, "envio_id": envio.get("envio_id"),
                               "motivo": "carrera", "detalle": e.mensaje})
            continue
        retirados.append({"codigo": codigo, "envio_id": actualizado.get("envio_id"),
                          "display_id": actualizado.get("display_id")})

    try:
        await base.envios_lotes.insert_one({
            "lote_id": lote_id, "retirado_por": getattr(operador, "user_id", None),
            "created_at": ahora, "nota": (nota or "").strip()[:300],
            "cuantos": len(retirados),
            "envio_ids": [r["envio_id"] for r in retirados],
        })
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo registrar el lote {lote_id}: {e}")

    return {"ok": True, "lote_id": lote_id, "retirados": retirados,
            "rechazados": rechazados,
            "cuantos": len(retirados), "cuantos_rechazados": len(rechazados)}


# ─── 3. El repesaje: acá se cierra el precio ──────────────────────────────

async def repesar(operador, envio_id: str, *, peso_kg, largo_cm, ancho_cm, alto_cm,
                  db=None, ahora=None, idempotency_key: str = None) -> dict:
    """Pesa con balanza propia, ajusta el precio y decide si el paquete sigue.

    Las tres ramas del ajuste están acá y las tres importan:
      COBRAR    — el paquete pesó más. Se emite la diferencia.
      DEVOLVER  — pesó menos. Se le acredita al usuario. Un ajuste que solo sube
                  no es un ajuste, es un recargo.
      SIN_AJUSTE— la diferencia está dentro de la tolerancia. No se emite nada:
                  un cobro de doce centavos cuesta más en soporte que en plata.
    """
    from services import envios_cobros
    from services.envios_estados import ajuste_por_repesaje, estado_tras_ajuste

    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)
    _exigir_transicion(envio, "repesado", "admin")

    # Que el cobro inicial exista NO es un detalle: `ajuste_por_repesaje` lo
    # necesita para calcular contra que ajustar, y sin el lanza un error que
    # decia "revisa las medidas que cargaste" — culpando al operador de que
    # nadie verifico el comprobante todavia.
    inicial = ((envio.get("cobros") or {}).get("inicial")) or {}
    if not inicial.get("monto_ris"):
        raise OperacionRechazada(
            "Este envío todavía no tiene el cobro inicial emitido. Verificá primero el "
            "comprobante de despacho: sin ese número no hay contra qué ajustar.",
            http=409)

    tarifa = await envios_cobros._tarifa_congelada(base, envio)
    tolerancia = await _tolerancia(base)
    try:
        ajuste = ajuste_por_repesaje(envio, tarifa, peso_kg, largo_cm, ancho_cm,
                                     alto_cm, tolerancia=tolerancia)
    except Exception as e:
        logger.error(f"envios: no se pudo ajustar {envio_id}: {e}")
        raise OperacionRechazada(
            "No se pudo calcular el ajuste con esas medidas. Revisá lo que cargaste.",
            http=400) from e

    # EL AJUSTE VA ANTES DE MOVER EL ESTADO, y el orden es el defecto mas caro
    # que tuvo este archivo. Al reves, si el cobro fallaba por un 503 pasajero el
    # estado ya habia cambiado a `repesado`, el reintento chocaba contra "el
    # envio ya esta en ese estado", ninguna otra ruta emite la partida `ajuste`,
    # y el paquete salia de Pacaraima sin la diferencia cobrada. La rama de
    # devolver tenia el mismo agujero al reves: el usuario nunca la recibia.
    #
    # Cobrar primero es seguro porque `cobrar` es idempotente por partida: un
    # reintento devuelve la que ya existe en vez de emitir otra.
    resultado = {"rama": ajuste["rama"], "diferencia_ris": str(ajuste["diferencia"]),
                 "total_final_ris": str(ajuste["total_final"]),
                 "cobro": None, "devolucion": None}

    if ajuste["rama"] == "cobrar":
        resultado["cobro"] = await envios_cobros.cobrar(
            envio, "ajuste", ajuste["diferencia"], db=base, ahora=ahora,
            idempotency_key=idempotency_key, base_calculo="repesaje",
            peso_base_kg=peso_kg, detalle={"tarifa_version": ajuste["tarifa_version"]},
            actor_type="admin", actor_id=getattr(operador, "user_id", None))
    elif ajuste["rama"] == "devolver":
        resultado["devolucion"] = await envios_cobros.devolver(
            envio, ajuste["diferencia"], db=base, ahora=ahora,
            motivo="repesaje", actor_type="admin",
            actor_id=getattr(operador, "user_id", None))

    verificado = {"peso_kg": str(peso_kg), "largo_cm": str(largo_cm),
                  "ancho_cm": str(ancho_cm), "alto_cm": str(alto_cm),
                  "verificado_por": getattr(operador, "user_id", None),
                  "verificado_at": ahora}
    actualizado = await _mover(
        base, envio, "repesado",
        {"estado": "repesado", "paquete.verificado": verificado,
         "cotizacion.es_estimado": False,
         "cotizacion.total_final_ris": str(ajuste["total_final"])},
        operador, ahora,
        detalle={"rama": ajuste["rama"], "diferencia": str(ajuste["diferencia"])})

    # A donde va el paquete lo decide el saldo, no el operador — y se ESCRIBE,
    # no se sugiere. `pago_pendiente` existe para que el usuario reciba el aviso
    # de que su paquete espera un pago; dejarlo como sugerencia lo volvia un
    # estado inalcanzable y ese aviso, codigo muerto.
    impagas = partidas_impagas(actualizado)
    siguiente = "pago_pendiente" if impagas else SALIDA_DE_PACARAIMA
    if siguiente == "pago_pendiente":
        actualizado = await _mover(base, actualizado, "pago_pendiente",
                                   {"estado": "pago_pendiente"}, operador, ahora,
                                   actor="system",
                                   detalle={"partidas_impagas": impagas})

    resultado.update({"ok": True, "envio_id": envio_id,
                      "estado": actualizado.get("estado"),
                      "partidas_impagas": impagas,
                      "puede_salir": not impagas})
    return resultado


async def _tolerancia(base):
    """La tolerancia del panel, o None para que rija el piso del codigo.

    `to_decimal(None)` devuelve 0 —es su contrato— y 0 es finito y >= 0, asi que
    pasarlo tal cual entregaba una tolerancia EXPLICITA de cero: la rama
    "sin_ajuste" desaparecia y una diferencia de un peso con cincuenta se
    cobraba, con lo cual un envio podia quedar frenado en Pacaraima por 1,50. Y
    pasaba en toda instalacion nueva, porque el bloque `operacion` no existe
    hasta que alguien lo guarda desde el panel.
    """
    from services.envios_config import leer
    operacion = await leer("operacion", db=base) or {}
    bruto = operacion.get("tolerancia_ajuste_ris")
    if bruto is None or bruto == "":
        return None
    valor = to_decimal(bruto)
    return valor if valor.is_finite() and valor >= ZERO else None


# ─── 4. Sale de Pacaraima ─────────────────────────────────────────────────

async def despachar(operador, envio_id: str, *, db=None, ahora=None) -> dict:
    """El paquete sale hacia Santa Elena. **Solo con todo pago.**

    Es la única palanca de cobro real del negocio: la posesión física. Por eso el
    chequeo no es una condición suelta acá sino una invariante de
    `puede_transicionar`, que la aplica venga de donde venga la llamada.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)
    _exigir_transicion(envio, SALIDA_DE_PACARAIMA, "admin")

    await _mover(base, envio, SALIDA_DE_PACARAIMA,
                 {"estado": SALIDA_DE_PACARAIMA, "salida_pacaraima_at": ahora},
                 operador, ahora)
    return {"ok": True, "envio_id": envio_id, "estado": SALIDA_DE_PACARAIMA}


# ─── El ticket que se pega en la caja ─────────────────────────────────────

# Como se lee en el mostrador de Santa Elena: no es una etiqueta de sistema, es
# un papel que alguien mira de parado, con la caja en la mano y otras veinte
# esperando. Por eso el ticket dice CUATRO cosas y en este orden: a quien se le
# entrega, donde, quien paga el tramo final, y si la caja puede salir.

PAGO_A_DESTINO = "destino"
PAGO_PREPAGO = "prepago"


async def ticket(envio_id: str, db=None) -> dict:
    """Los datos del papel que se pega en la caja antes de que salga.

    Es una consulta aparte y no un campo mas de la cola por dos motivos. Uno: la
    direccion de la agencia no esta congelada en el envio, hay que ir a buscarla
    a `agencias`, y hacer esa lectura por cada fila de una cola de doscientas es
    un N+1 en la pantalla que el operador usa todo el dia. Dos: un ticket se
    imprime de a uno.

    **La direccion se lee VIVA, no congelada.** Es lo contrario de la etiqueta
    del tramo brasileno, y a proposito: aquella tiene que decir lo mismo que leyo
    el usuario cuando despacho, porque es un compromiso con el. Esta se pega
    ahora sobre una caja que sale ahora, y tiene que decir donde esta la agencia
    HOY. Si se mudo, la direccion vieja manda la caja al lugar equivocado.

    Nunca lanza por la agencia: si no se puede leer, el ticket sale igual con el
    nombre —que es lo que esta congelado— y sin la calle. Un ticket incompleto se
    completa a mano en el mostrador; un ticket que no se imprime frena la caja.
    """
    base = await _db(db)
    envio = await _envio(base, envio_id)

    destino = envio.get("destino") or {}
    destinatario = destino.get("destinatario") or {}
    paquete = envio.get("paquete") or {}
    verificado = paquete.get("verificado") or {}
    declarado = paquete.get("declarado") or {}
    impagas = partidas_impagas(envio)

    agencia = await _agencia_de(base, destino)
    transportista = await _nombre_de_transportista(base, destino.get("transportista_id"))

    modalidad = envio.get("modalidad_flete") or PAGO_A_DESTINO
    flete = envio.get("flete") or {}

    return {
        "envio_id": envio.get("envio_id"),
        "display_id": envio.get("display_id"),
        "estado": envio.get("estado"),
        "codigo_objeto": (envio.get("origen") or {}).get("codigo_objeto"),
        "destinatario": {
            "nombre": destinatario.get("nombre"),
            "documento": destinatario.get("documento"),
            "telefono": destinatario.get("telefono"),
        },
        "agencia": {
            "nombre": destino.get("agencia_nombre"),
            "codigo": destino.get("agencia_codigo"),
            "ciudad": destino.get("ciudad"),
            "estado_ve": destino.get("estado_ve"),
            # Puede venir vacia: la agencia se pudo borrar del catalogo, o
            # cargarse sin calle. El ticket lo dice en vez de mentir un renglon.
            "direccion": (agencia or {}).get("direccion"),
            "transportista": transportista,
        },
        # LO QUE DECIDE QUE PASA EN EL MOSTRADOR. "destino" = lo cobra el
        # transportista a quien recibe. "prepago" = ya se pago por remesa, y no
        # se le cobra nada a quien retira — cobrarle de nuevo es cobrar dos
        # veces el mismo tramo.
        "pago": {
            "modalidad": modalidad,
            "cobrar_al_recibir": modalidad == PAGO_A_DESTINO,
            "flete_estado": flete.get("estado") or "sin_registrar",
            "flete_monto_ris": flete.get("monto_ris"),
        },
        "paquete": {
            # El peso de la balanza propia si ya se repeso; si no, lo declarado.
            # Se dice CUAL de los dos: un peso sin origen en un papel que viaja
            # es el que despues nadie puede defender.
            "peso_kg": verificado.get("peso_kg") or declarado.get("peso_kg"),
            "peso_es_verificado": bool(verificado.get("peso_kg")),
            "contenido": paquete.get("contenido_descripcion"),
        },
        "puede_salir": not impagas,
        "partidas_impagas": impagas,
    }


async def _agencia_de(base, destino: dict) -> dict | None:
    codigo = destino.get("agencia_codigo")
    transportista_id = destino.get("transportista_id")
    if not (codigo and transportista_id):
        return None
    try:
        return await base.agencias.find_one(
            {"transportista_id": transportista_id, "codigo": codigo},
            {"_id": 0, "direccion": 1, "nombre": 1, "ciudad": 1, "estado": 1})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la agencia {codigo} para el ticket: {e}")
        return None


async def _nombre_de_transportista(base, transportista_id) -> str | None:
    if not transportista_id:
        return None
    try:
        ficha = await base.transportistas.find_one(
            {"transportista_id": transportista_id}, {"_id": 0, "nombre": 1})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el transportista para el ticket: {e}")
        return None
    return (ficha or {}).get("nombre")


# ─── 5. Entregado en el mostrador de destino ──────────────────────────────

async def entregar(operador, envio_id: str, *, guia: str, foto: bytes = None,
                   db=None, ahora=None) -> dict:
    """Entregado en la oficina del transportista. El servicio de RIS App terminó.

    La guía es obligatoria: es el único comprobante de que el paquete cambió de
    manos, y sin ella la única prueba de la entrega es la palabra del operador.
    """
    from services import envios_archivos

    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)

    numero = (guia or "").strip()
    if len(numero) < 4:
        raise OperacionRechazada(
            "Cargá el número de guía que emitió el transportista. Es el único "
            "comprobante de que el paquete cambió de manos.")
    _exigir_transicion(envio, "entregado_transportista", "admin",
                       flete_impago=_flete_impago(envio))

    parche = {"estado": "entregado_transportista",
              "entrega.guia": numero[:60],
              "entrega.at": ahora,
              "entrega.por": getattr(operador, "user_id", None)}
    if foto:
        ficha = await envios_archivos.guardar(
            foto, envio_id=envio_id, user_id=envio.get("user_id"), clase="entrega",
            db=base, ahora=ahora)
        parche["entrega.foto_asset_id"] = ficha["asset_id"]

    await _mover(base, envio, "entregado_transportista", parche, operador, ahora,
                 detalle={"guia": numero[:60]})
    return {"ok": True, "envio_id": envio_id, "estado": "entregado_transportista",
            "guia": numero[:60]}


def _flete_impago(envio: dict) -> bool:
    """En modalidad prepago, la remesa al transportista tiene que estar acreditada.

    Se lee del envío y no se calcula: la remesa la ejecuta el usuario por el
    circuito de pagos que ya existe, y este módulo solo mira si alguien la marcó
    como acreditada.
    """
    if (envio or {}).get("modalidad_flete") != "prepago":
        return False
    flete = (envio or {}).get("flete") or {}
    return flete.get("estado") != "acreditado"


# ─── Piezas ───────────────────────────────────────────────────────────────

async def _envio(base, envio_id: str) -> dict:
    try:
        envio = await base.envios.find_one({"envio_id": envio_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        raise OperacionRechazada(
            "No se pudo leer el envío. Reintentá en un momento.", http=503) from e
    if not envio:
        raise OperacionRechazada("Ese envío no existe.", http=404)
    return envio


def _exigir_transicion(envio: dict, hacia: str, actor: str, **banderas) -> None:
    """La transición, con las invariantes del envío calculadas de sus datos.

    `partida_impaga` y `precio_cerrado` NO se pasan desde la ruta: se derivan del
    documento. Dejarlos en manos de quien llama es dejar que una ruta nueva se
    olvide de uno y saque un paquete de Pacaraima con la deuda encima.
    """
    impagas = partidas_impagas(envio)
    problema = puede_transicionar(
        envio.get("estado") or "", hacia, actor,
        partida_impaga=bool(impagas),
        precio_cerrado=not (envio.get("cotizacion") or {}).get("es_estimado", True),
        **banderas)
    if problema:
        raise OperacionRechazada(problema, http=409)


async def _mover(base, envio: dict, hacia: str, parche: dict, operador, ahora,
                 detalle: dict = None, actor: str = "admin") -> dict:
    """Aplica la transición con el estado en el FILTRO, y deja su línea.

    El estado va en el filtro y no solo en el chequeo previo: entre que se leyó y
    que se escribe, otro operador pudo mover el mismo paquete. Con dos personas
    en un mostrador, eso no es hipotético.
    """
    from services import envios_eventos
    desde = envio.get("estado")
    try:
        actualizado = await base.envios.find_one_and_update(
            {"envio_id": envio.get("envio_id"), "estado": desde},
            {"$set": parche}, return_document=True)
    except Exception as e:
        logger.error(f"envios: no se pudo mover {envio.get('envio_id')} a {hacia}: {e}")
        raise OperacionRechazada(
            "No se pudo actualizar el envío. Reintentá en un momento.", http=503) from e
    if actualizado is None:
        raise OperacionRechazada(
            "El envío cambió de estado mientras trabajabas. Recargá la cola.", http=409)

    await envios_eventos.registrar(
        actualizado, desde, hacia, actor,
        actor_id=getattr(operador, "user_id", None), detalle=detalle,
        db=base, ahora=ahora)

    # El aviso va al final y no puede deshacer nada: el paquete ya esta donde
    # esta, y un aviso que falla no lo devuelve.
    from services import envios_seguimiento
    await envios_seguimiento.avisar(actualizado, hacia, db=base)
    return actualizado


# ─── 6. Los caminos que no son el feliz ───────────────────────────────────
#
# Sin esto, la mitad de las transiciones que `envios_estados` declara no las
# implementaba nadie y los paquetes quedaban atascados. El caso mas caro: un
# paquete cuya guarda vence en la agencia y que la agencia devuelve al remitente
# — el envio se quedaba en `disponible_retiro` para siempre, y `cola()` lo
# mostraba con los dias en negativo sin ninguna salida.

# Los estados a los que se puede llevar un envio "a mano", con su motivo. NO es
# cualquier transicion: es la lista de las que un operador tiene que poder hacer
# desde el panel, y cada una sigue pasando por `puede_transicionar`.
DESVIOS = ("retenido", "devuelto", "siniestrado", "cancelado")


async def desviar(operador, envio_id: str, hacia: str, *, motivo: str,
                  db=None, ahora=None, actor: str = "admin") -> dict:
    """Lleva un envío a un estado que no es el camino feliz. Exige un motivo.

    El motivo no es burocracia: estos estados abren consecuencias —una
    indemnización, una devolución, un reclamo— y dentro de seis meses la única
    forma de entender por qué un paquete terminó así es lo que alguien escribió
    acá.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    if hacia not in DESVIOS:
        raise OperacionRechazada(
            f"No se puede llevar un envío a {hacia!r} desde acá.", http=400)
    razon = (motivo or "").strip()
    if len(razon) < 10:
        raise OperacionRechazada(
            "Escribí qué pasó, con al menos diez caracteres. Es lo único que va a "
            "explicar este envío dentro de seis meses.")

    envio = await _envio(base, envio_id)
    _exigir_transicion(envio, hacia, actor)
    actualizado = await _mover(base, envio, hacia,
                               {"estado": hacia, "desvio": {
                                   "motivo": razon[:500], "at": ahora,
                                   "por": getattr(operador, "user_id", None)}},
                               operador, ahora, detalle={"motivo": razon[:200]},
                               actor=actor)
    return {"ok": True, "envio_id": envio_id, "estado": actualizado.get("estado")}


async def cancelar(usuario, envio_id: str, *, motivo: str = "", db=None,
                   ahora=None) -> dict:
    """El usuario cancela un envío suyo. Solo antes de que exista un paquete.

    `puede_transicionar` ya limita desde dónde: cotizado y esperando_postagem. Un
    envío ya despachado no se cancela — el paquete está viajando y cancelarlo en
    una pantalla no lo trae de vuelta.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    user_id = getattr(usuario, "user_id", None)
    try:
        envio = await base.envios.find_one(
            {"envio_id": envio_id, "user_id": user_id}, {"_id": 0})
    except Exception as e:                                    # pragma: no cover
        raise OperacionRechazada("No se pudo leer el envío.", http=503) from e
    if not envio:
        raise OperacionRechazada("No encontramos ese envío.", http=404)

    _exigir_transicion(envio, "cancelado", "user")
    actualizado = await _mover(
        base, envio, "cancelado",
        {"estado": "cancelado", "desvio": {
            "motivo": (motivo or "cancelado por el usuario").strip()[:500],
            "at": ahora, "por": user_id}},
        usuario, ahora, actor="user")
    return {"ok": True, "envio_id": envio_id, "estado": actualizado.get("estado")}


# ─── 7. El flete del tramo de destino ─────────────────────────────────────
#
# En modalidad `prepago` el usuario le paga el flete al transportista de destino
# por el circuito de remesas que la aplicacion ya tiene. Este modulo NO cobra ese
# flete y no lo factura: solo registra cuanto pidio el mostrador y si la remesa
# se acredito, porque de eso depende que el paquete se entregue.

async def cargar_flete(operador, envio_id: str, *, monto, db=None, ahora=None) -> dict:
    """Registra lo que el transportista de destino pidió por el tramo final.

    Lo carga el operador que está parado en el mostrador, porque hasta ese
    momento el precio no existe: nadie puede cotizarlo antes. Y no es un cobro de
    RIS App — es el número que el usuario tiene que enviar como remesa.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)

    importe = to_decimal(monto)
    if not importe.is_finite() or importe <= ZERO:
        raise OperacionRechazada(
            "Cargá el monto que pidió el transportista. Sin ese número el usuario no "
            "sabe cuánto tiene que enviar.")

    await _actualizar(base, envio_id, {
        "flete.monto_acordado_ris": str(quantize_money(importe)),
        "flete.cargado_por": getattr(operador, "user_id", None),
        "flete.cargado_at": ahora,
        "flete.estado": (envio.get("flete") or {}).get("estado") or "pendiente",
    })
    return {"ok": True, "envio_id": envio_id,
            "monto_acordado_ris": str(quantize_money(importe)),
            "estado": (envio.get("flete") or {}).get("estado") or "pendiente"}


async def acreditar_flete(operador, envio_id: str, *, referencia: str = "",
                          db=None, ahora=None) -> dict:
    """Marca que la remesa del usuario al transportista llegó.

    Es lo que destraba la entrega en modalidad prepago. Lo confirma una persona
    porque la remesa se ejecuta por fuera de este módulo y nadie de acá puede
    verla llegar.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    envio = await _envio(base, envio_id)
    flete = envio.get("flete") or {}
    if not flete.get("monto_acordado_ris"):
        raise OperacionRechazada(
            "Cargá primero cuánto pidió el transportista.", http=409)
    if flete.get("estado") == "acreditado":
        return {"ok": True, "envio_id": envio_id, "estado": "acreditado"}

    await _actualizar(base, envio_id, {
        "flete.estado": "acreditado",
        "flete.acreditado_at": ahora,
        "flete.acreditado_por": getattr(operador, "user_id", None),
        "flete.referencia": (referencia or "").strip()[:80] or None,
    })
    return {"ok": True, "envio_id": envio_id, "estado": "acreditado"}


async def _actualizar(base, envio_id: str, parche: dict) -> None:
    try:
        resultado = await base.envios.update_one({"envio_id": envio_id},
                                                 {"$set": parche})
    except Exception as e:
        logger.error(f"envios: no se pudo actualizar {envio_id}: {e}")
        raise OperacionRechazada(
            "No se pudo guardar. Reintentá en un momento.", http=503) from e
    if getattr(resultado, "matched_count", 1) == 0:            # pragma: no cover
        raise OperacionRechazada("Ese envío no existe.", http=404)
