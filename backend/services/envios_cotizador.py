"""
services/envios_cotizador.py — La cotizacion: un precio, dos orientaciones.

QUE ES UNA COTIZACION ACA
    Un ESTIMADO. No es un acuerdo comercial, no reserva nada y no cobra nada.
    El numero final del servicio se cierra en Pacaraima, con balanza propia
    (§4). Por eso `es_estimado: true` viaja en la respuesta y `aviso_estimado`
    tambien, siempre, sin excepcion.

LO QUE RIS APP COBRA, Y LO QUE NO
    RIS App cobra UN solo servicio: retirar el paquete en Pacaraima, repesarlo y
    llevarlo hasta la oficina del transportista en Santa Elena. Nada mas.

    Los dos tramos de transporte —el de Brasil hasta Pacaraima y el de Venezuela
    desde Santa Elena— los contrata y los paga el usuario por su cuenta. Los
    montos que se muestran de esos dos son ORIENTATIVOS y salen de matrices de
    referencia cargadas a mano.

    NINGUNA REFERENCIA ENTRA EN EL TOTAL. Ni sumada, ni promediada, ni "para
    darse una idea del total del viaje". Son dos contratos distintos, con dos
    empresas distintas, en dos monedas distintas, y un numero que los sume
    parece un total y no lo es — y ese numero terminaria algun dia al lado del
    que RIS App si cobra. Hay un test que lo verifica sumando todo lo que
    aparece en la respuesta.

QUE SE CONGELA Y QUE NO
    Se congelan la VERSION DE TARIFA (para que un aumento posterior no le cambie
    el precio a alguien que ya cotizo), la AGENCIA elegida con su nombre (para
    que cerrar una sucursal no deje un envio apuntando al vacio) y el BLOQUE DE
    DESPACHO con el nombre del retirador (porque va impreso en una etiqueta
    pegada a una caja).

    NO se congela la cuenta bancaria del transportista, que se lee siempre viva
    (§4.6). Y no se congela ningun monto de referencia como si fuera un precio.

ORDEN DE LAS VALIDACIONES
    Primero lo que el usuario puede arreglar solo —descripcion, medidas,
    limites—, despues lo que depende de la configuracion. Al reves, alguien con
    una caja de 80 kg recibe "el servicio no esta disponible" y escribe a
    soporte, cuando el problema era su caja.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from services.envios_policy import (limites_efectivos, validar_descripcion,
                                    validar_paquete, quien_impone)
from services.envios_tarifas import cotizar_servicio, peso_facturable
from services.money import quantize_money, to_decimal

logger = logging.getLogger(__name__)

TTL_HORAS_POR_DEFECTO = 48

# Lo que se le dice al usuario, siempre, con el mismo peso visual que el precio.
# No es un tooltip ni una nota al pie en gris claro: es lo que evita el peor
# malentendido posible, que es creer que pagando en RIS App ya cubrio el envio
# entero. El texto real lo edita el super administrador (bloque `contenido`);
# este es el piso, para que nunca falte.
AVISO_POR_DEFECTO = (
    "RIS App cobra un solo servicio: retirar tu paquete en Pacaraima, repesarlo y "
    "llevarlo hasta la oficina del transportista en Santa Elena. Ese precio es una "
    "estimación sobre lo que declaraste y se confirma al repesar. El envío dentro de "
    "Brasil y el tramo dentro de Venezuela los contratás y los pagás vos aparte: los "
    "montos que ves de esos dos son referenciales."
)

CONCEPTO = ("Retiro en Pacaraima, repesaje y traslado hasta la oficina del "
            "transportista en Santa Elena")

# Lo que ve un anonimo cuando el modulo no puede cotizar. El DETALLE de que le
# falta al panel —"la tarifa no tiene divisor volumetrico"— es un diagnostico
# interno: explicarle a un desconocido como pagar de menos no le sirve a nadie.
_NO_DISPONIBLE = ("El servicio de envíos no está disponible en este momento. "
                  "Escribinos si necesitás cotizar un envío.")

# Cuanto se espera por todo lo que no es el precio: las orientaciones y el
# bloque de despacho. El cliente de Mongo del proyecto no fija socketTimeout, o
# sea que una lectura colgada espera para siempre y se queda con un worker.
TIMEOUT_ACCESORIOS_S = 6.0

# Cuantas cotizaciones sin confirmar puede tener alguien a la vez. No es una
# regla comercial: es el freno que evita que la coleccion crezca sin techo con
# datos personales de terceros adentro. Diez es mucho mas de lo que necesita
# cualquiera que este cotizando de verdad.
COTIZACIONES_ABIERTAS_MAX = 10
_CANDIDATAS_A_MIRAR = 20


class NoSePuedeCotizar(Exception):
    """Un motivo que el usuario puede leer. La ruta lo vuelve un 400 o un 503."""

    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def nuevo_envio_id() -> str:
    return f"env_{uuid.uuid4().hex[:12]}"


# ─── Cotizar ──────────────────────────────────────────────────────────────

async def cotizar(usuario, pedido: dict, db=None, ahora=None,
                  persistir: bool = True) -> dict:
    """La cotización completa. Lanza NoSePuedeCotizar con un motivo legible.

    No mueve un centavo y no toca ningún saldo: crear el envío y cobrar son
    pasos posteriores y separados. Cotizar es gratis, y eso no es una promesa
    comercial sino una propiedad del código — no hay ninguna escritura de dinero
    en este archivo.
    """
    ahora = ahora or datetime.now(timezone.utc)
    base = await _db(db)
    pedido = pedido or {}
    paquete = pedido.get("paquete") or {}

    # 1. La configuración, primero, porque el mínimo de la descripción sale de
    #    ahí: es un criterio de aduana, no una constante de ingeniería.
    contexto = await _contexto(base, ahora=ahora)

    # 2. Lo que el usuario puede arreglar solo, antes que lo que depende del
    #    panel. Al revés, alguien con una caja de 80 kg recibe "el servicio no
    #    está disponible" y escribe a soporte, cuando el problema era su caja.
    problema = validar_descripcion(
        paquete.get("contenido_descripcion"),
        contexto["contenido"].get("descripcion_min_caracteres"))
    if problema:
        raise NoSePuedeCotizar(problema)

    tarifa = contexto["tarifa"]
    if not tarifa or not contexto["transportistas"]:
        raise NoSePuedeCotizar(_NO_DISPONIBLE, http=503)

    if not contexto["catalogo_completo"]:
        # Un rol que no se pudo leer llega como lista vacía, y la intersección de
        # límites se calcula solo con el otro: una caja de 110 cm que el
        # transportista de origen rechaza a los 100 pasaría a cotizar bien. El
        # usuario paga el tramo 1 y la caja se rechaza en el mostrador. Es el bug
        # del PR #40 —un techo anunciado que nadie valida— entrando por atrás.
        logger.error("envios: no se pudo leer un rol del catálogo; no se cotiza")
        raise NoSePuedeCotizar(_NO_DISPONIBLE, http=503)

    limites = limites_efectivos(contexto["transportistas"], tarifa.get("limites_propios"))
    problema = validar_paquete(paquete.get("peso_kg"), paquete.get("largo_cm"),
                               paquete.get("ancho_cm"), paquete.get("alto_cm"),
                               paquete.get("valor_declarado_brl"), limites)
    if problema:
        # Se rechaza en el formulario y no en el mostrador de Pacaraima con el
        # paquete en la mano: ahí ya se pagó el tramo 1 y no hay vuelta atrás.
        raise NoSePuedeCotizar(problema)

    # 3. La agencia de destino, que se congela con su nombre.
    agencia = await _agencia(base, (pedido.get("destino") or {}),
                             contexto["transportistas"])

    # 4. El precio del servicio. Es lo único que RIS App cobra.
    try:
        servicio = cotizar_servicio(
            tarifa, paquete.get("peso_kg"), paquete.get("largo_cm"),
            paquete.get("ancho_cm"), paquete.get("alto_cm"),
            valor_declarado=paquete.get("valor_declarado_brl") or 0,
            bultos=1,          # una caja: ver models/envios_cotizacion.Paquete
            fecha=ahora.date(),
        )
    except Exception as e:
        logger.error(f"envios: no se pudo cotizar el servicio: {e}")
        raise NoSePuedeCotizar(
            "No se pudo calcular el precio del servicio. Escribinos y lo resolvemos.",
            http=503) from e

    if not servicio.get("version_id"):
        # Sin version congelada, los dos cobros posteriores fallan PARA SIEMPRE:
        # `envios_estados` se niega a calcular sin ella, y con razón. Mejor no dar
        # el precio que darlo y no poder cobrarlo nunca.
        logger.error("envios: la tarifa vigente no tiene version_id; no se cotiza")
        raise NoSePuedeCotizar(
            "El servicio de envíos no está disponible en este momento. Escribinos si "
            "necesitás cotizar un envío.", http=503)

    # 5. Lo que el usuario paga afuera, y el bloque de despacho. En paralelo: ni
    #    el precio ni la validación dependen de ninguna de las dos, así que
    #    encadenarlas solo le agrega latencia a la pantalla.
    referencias, despacho = await _en_paralelo(
        base, pedido, agencia, paquete, ahora)

    if not despacho.get("disponible"):
        # Sin bloque de despacho no hay a dónde mandar el paquete. Cotizar igual
        # sería darle un precio a alguien que después no puede despachar.
        raise NoSePuedeCotizar(
            "El servicio de envíos no está disponible en este momento. Escribinos si "
            "necesitás cotizar un envío.", http=503)

    envio = _armar(usuario, pedido, paquete, agencia, servicio, referencias,
                   despacho, contexto, limites, ahora)
    envio["cotizacion"]["huella"] = huella(envio)

    if not persistir:
        return _payload(envio, servicio, referencias, despacho, contexto, limites)

    # Cotizar escribe un documento con el nombre, el documento y el telefono de
    # una persona en Venezuela. Sin ninguna cota, un doble clic deja un envio
    # huerfano ensuciando la cola del panel, y un bucle deja la coleccion del
    # tamano que se quiera. Dos frenos, los dos baratos.
    previa = await _cotizacion_equivalente(base, envio, ahora)
    if previa is not None:
        # Mismo usuario, mismo paquete, mismo destino, todavia vigente: es el
        # mismo pedido, no uno nuevo. Se devuelve la que ya existe con su
        # `envio_id` original, para que un doble clic no parta el flujo en dos
        # envios de los que uno queda a la deriva.
        envio = previa
        return _payload(envio, servicio, referencias, despacho, contexto, limites)

    if await _demasiadas_abiertas(base, envio["user_id"], ahora):
        raise NoSePuedeCotizar(
            f"Tenés {COTIZACIONES_ABIERTAS_MAX} cotizaciones sin confirmar. Confirmá o "
            "dejá vencer alguna antes de pedir otra.")

    try:
        await base.envios.insert_one(dict(envio))
    except Exception as e:
        logger.error(f"envios: no se pudo guardar la cotización: {e}")
        raise NoSePuedeCotizar(
            "No se pudo guardar la cotización. Probá de nuevo en un momento.",
            http=503) from e

    return _payload(envio, servicio, referencias, despacho, contexto, limites)


def huella(envio: dict) -> str:
    """Que hace que dos cotizaciones sean el mismo pedido.

    El paquete declarado, el destino y la modalidad de flete. NO entra la fecha
    ni el precio: si la tarifa cambio entre un clic y el siguiente, el usuario
    sigue teniendo derecho a la cotizacion que le mostramos — que es la misma
    razon por la que la version de tarifa se congela.
    """
    import hashlib
    import json
    destino = envio.get("destino") or {}
    material = {
        "paquete": (envio.get("paquete") or {}).get("declarado"),
        "descripcion": (envio.get("paquete") or {}).get("contenido_descripcion"),
        "agencia": destino.get("agencia_codigo"),
        "transportista": destino.get("transportista_id"),
        "destinatario": destino.get("destinatario"),
        "flete": envio.get("modalidad_flete"),
        "origen": (envio.get("origen") or {}).get("cep"),
    }
    crudo = json.dumps(material, sort_keys=True, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]


async def _cotizacion_equivalente(base, envio: dict, ahora):
    """La cotización vigente del mismo pedido, si ya existe. Nunca lanza."""
    try:
        candidatas = await base.envios.find(
            {"user_id": envio["user_id"], "estado": "cotizado",
             "cotizacion.huella": envio["cotizacion"]["huella"]},
            {"_id": 0},
        ).to_list(_CANDIDATAS_A_MIRAR)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo buscar una cotización previa: {e}")
        return None
    for previa in candidatas or []:
        if not esta_vencida(previa, ahora=ahora):
            return previa
    return None


async def _demasiadas_abiertas(base, user_id, ahora) -> bool:
    try:
        abiertas = await base.envios.find(
            {"user_id": user_id, "estado": "cotizado"},
            {"_id": 0, "cotizacion": 1},
        ).to_list(COTIZACIONES_ABIERTAS_MAX * 4)
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudieron contar las cotizaciones abiertas: {e}")
        return False
    vigentes = [e for e in (abiertas or []) if not esta_vencida(e, ahora=ahora)]
    return len(vigentes) >= COTIZACIONES_ABIERTAS_MAX


async def _en_paralelo(base, pedido, agencia, paquete, ahora):
    from services import envios_retiro
    from services.referencias import referencias_para

    origen = pedido.get("origen") or {}
    tareas = (
        referencias_para(
            clave_brasil=(origen.get("uf") or "").strip().upper() or None,
            clave_venezuela=agencia.get("zona"),
            peso_kg=paquete.get("peso_kg"),
            largo_cm=paquete.get("largo_cm"), ancho_cm=paquete.get("ancho_cm"),
            alto_cm=paquete.get("alto_cm"), db=base,
            solo_transportista=agencia.get("transportista_id"),
        ),
        envios_retiro.bloque_de_despacho(db=base, ahora=ahora),
    )
    try:
        referencias, despacho = await asyncio.wait_for(
            asyncio.gather(*tareas, return_exceptions=True),
            timeout=TIMEOUT_ACCESORIOS_S)
    except asyncio.TimeoutError:
        logger.error("envios: la orientación y el despacho no llegaron a tiempo")
        return [], {"disponible": False,
                    "faltantes": ["No se pudo armar la dirección de despacho."]}

    # BaseException y no Exception: `CancelledError` dejó de heredar de Exception
    # en 3.8, y `gather(return_exceptions=True)` igual la deposita en la lista.
    # Sin esto, un cliente que aborta produce un AttributeError sobre el
    # resultado, que la ruta le presenta al usuario como una caída del servicio.
    if isinstance(referencias, BaseException):
        logger.warning(f"envios: la orientación falló entera: {referencias!r}")
        referencias = []
    if isinstance(despacho, BaseException):
        logger.error(f"envios: no se pudo armar el bloque de despacho: {despacho!r}")
        despacho = {"disponible": False, "faltantes": ["No se pudo armar la dirección."]}
    return referencias, despacho


async def _contexto(base, ahora=None) -> dict:
    """Tarifa vigente, transportistas activos y configuración, en una lectura."""
    from services.envios_catalogo import tarifa_vigente
    from services.envios_config import leer_con_estado
    from services.referencias import _catalogo

    try:
        crudo = await asyncio.wait_for(asyncio.gather(
            tarifa_vigente(db=base, ahora=ahora),
            # `_catalogo` y no `transportistas_activos`: devuelve un flag que
            # distingue "no hay ninguno" de "Mongo no contestó", y confundirlos
            # afloja los límites en silencio.
            _catalogo("brasil", db=base),
            _catalogo("venezuela", db=base),
            leer_con_estado("contenido", db=base),
            leer_con_estado("operacion", db=base),
            return_exceptions=True,
        ), timeout=TIMEOUT_ACCESORIOS_S)
    except asyncio.TimeoutError:
        logger.error("envios: la configuración no llegó a tiempo")
        return {"tarifa": None, "transportistas": [], "catalogo_completo": False,
                "contenido": {}, "operacion": {}, "contenido_ok": False}

    tarifa, brasil, venezuela, contenido, operacion = crudo

    def _par(valor, porDefecto):
        if isinstance(valor, BaseException):
            return porDefecto, False
        return valor

    br, br_ok = _par(brasil, [])
    ve, ve_ok = _par(venezuela, [])
    cont, cont_ok = _par(contenido, None)
    oper, _ = _par(operacion, None)

    return {
        "tarifa": None if isinstance(tarifa, BaseException) else tarifa,
        "transportistas": (br or []) + (ve or []),
        "catalogo_completo": bool(br_ok and ve_ok),
        "contenido": cont or {},
        "contenido_ok": bool(cont_ok),
        "operacion": oper or {},
    }


async def _agencia(base, destino: dict, transportistas: list) -> dict:
    """La agencia elegida, congelada con su nombre.

    Se guarda el NOMBRE además del código: si la sucursal cierra y sale del
    catálogo, el envío tiene que poder seguir diciendo a dónde iba. Un envío que
    apunta a un código que ya no existe es un ticket de soporte sin respuesta.
    """
    codigo = (destino.get("agencia_codigo") or "").strip()
    transportista_id = (destino.get("transportista_id") or "").strip()
    if not codigo or not transportista_id:
        raise NoSePuedeCotizar("Elegí a qué agencia de destino va el paquete.")

    # El transportista tiene que estar en el catálogo ACTIVO y ser de destino. La
    # ruta acepta cualquier id que el cliente mande, y `/catalogo` no los ofrece
    # —pero no ofrecerlos no es lo mismo que rechazarlos. Sin este chequeo se
    # podía cotizar contra una empresa dada de baja (cuyos límites, además, ya no
    # entran en la intersección) o apuntar el destino en Venezuela a un
    # transportista de rol Brasil.
    elegido = next((t for t in (transportistas or [])
                    if t.get("transportista_id") == transportista_id
                    and t.get("rol") == "venezuela"), None)
    if elegido is None:
        raise NoSePuedeCotizar(
            "Ese transportista de destino no está disponible. Elegí uno de la lista.")

    try:
        fila = await base.agencias.find_one(
            {"transportista_id": transportista_id, "codigo": codigo}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la agencia {codigo}: {e}")
        raise NoSePuedeCotizar(
            "No se pudo verificar la agencia de destino. Probá de nuevo en un momento.",
            http=503) from e

    if not fila:
        raise NoSePuedeCotizar(
            "Esa agencia de destino no existe. Elegí una de la lista.")

    # El filtro por `activa` va en Python: `{"activa": True}` no matchea un 1 ni
    # un "true", y una agencia dada de alta desde el panel con un checkbox
    # serializado como número desaparecería sin un solo log.
    from services.referencias import _activo
    if not _activo({"activo": fila.get("activa")}):
        raise NoSePuedeCotizar(
            "Esa agencia de destino no está recibiendo paquetes. Elegí otra de la lista.")

    return fila


def _armar(usuario, pedido, paquete, agencia, servicio, referencias, despacho,
           contexto, limites, ahora) -> dict:
    """El documento que se guarda. Los montos en texto, nunca en float."""
    horas = _horas_ttl(contexto["operacion"])
    origen = pedido.get("origen") or {}
    destino = pedido.get("destino") or {}

    return {
        "envio_id": nuevo_envio_id(),
        "user_id": getattr(usuario, "user_id", None),
        "estado": "cotizado",
        "created_at": ahora,
        "modalidad_flete": pedido.get("modalidad_flete") or "destino",

        "origen": {"cep": origen.get("cep"), "ciudad": origen.get("ciudad"),
                   "uf": origen.get("uf")},

        # Congelado: cambiar la nómina no cambia la etiqueta de una caja que ya
        # está viajando.
        "destino_brasil": {k: v for k, v in despacho.items()
                           if k not in ("disponible", "faltantes")},

        "destino": {
            "transportista_id": agencia.get("transportista_id"),
            "agencia_codigo": agencia.get("codigo"),
            "agencia_nombre": agencia.get("nombre"),
            "estado_ve": agencia.get("estado"),
            "ciudad": agencia.get("ciudad"),
            "zona_tarifa": agencia.get("zona"),
            "codigo_postal": destino.get("codigo_postal"),
            "destinatario": destino.get("destinatario"),
        },

        "paquete": {
            "declarado": {
                "peso_kg": str(paquete.get("peso_kg")),
                "largo_cm": str(paquete.get("largo_cm")),
                "ancho_cm": str(paquete.get("ancho_cm")),
                "alto_cm": str(paquete.get("alto_cm")),
                "valor_declarado": str(paquete.get("valor_declarado_brl") or "0"),
            },
            "verificado": None,
            "pf_declarado": _pesos_facturables(contexto["transportistas"], paquete,
                                               servicio),
            "contenido_descripcion": paquete.get("contenido_descripcion"),
            "valor_declarado_brl": str(paquete.get("valor_declarado_brl") or "0"),
            "bultos": 1,
        },

        "cotizacion": {
            "es_estimado": True,
            "tarifa_version": servicio.get("version_id"),
            "terminos_version": _terminos(contexto),
            "cotizada_at": ahora,
            "huella": None,          # se completa abajo: depende del documento
            # `fecha` es el nombre que lee envios_estados para congelar el
            # multiplicador de temporada. Se escribe la MISMA fecha con la que se
            # cotizó, no la de hoy: sin esto, un recargo de temporada cotizado no
            # se cobraba, y uno que empezó después se cobraba sin que el usuario
            # lo hubiera aceptado.
            "fecha": ahora.date().isoformat(),
            "servicio_traslado_ris": str(servicio.get("base")),
            "sobrecargos": [{"codigo": s.get("codigo"), "monto": str(s.get("monto"))}
                            for s in (servicio.get("sobrecargos") or [])],
            "subtotal_ris": str(servicio.get("subtotal")),
            "margen_ris": str(servicio.get("margen")),
            "total_estimado_ris": str(servicio.get("total")),
            "moneda": servicio.get("moneda") or "RIS",
            # Las referencias se guardan por CÓDIGO y con su fuente. Nunca como
            # un precio, nunca sumadas, y nunca sin decir de dónde salieron.
            "referencias": [_referencia_guardada(r) for r in (referencias or [])],
            "total_final_ris": None,
            "vence_at": ahora + timedelta(hours=horas),
        },

        "cobros": {"inicial": None, "ajuste": None,
                   "reembolsado_ris": "0.00", "total_cobrado_ris": "0.00"},
    }


def _referencia_guardada(r: dict) -> dict:
    monto = r.get("monto")
    return {
        "transportista_id": r.get("transportista_id"),
        "codigo": r.get("codigo"),
        "rol": r.get("rol"),
        "clave": r.get("clave"),
        "monto": None if monto is None else str(monto),
        "moneda": r.get("moneda"),
        "fuente": r.get("fuente"),
        "desactualizada": bool(r.get("desactualizada")),
        # El candado viaja con el dato. referencias.py lo pone en cada
        # orientación y dice por qué: no es decoración, es lo que hace que un
        # `sum()` distraído sea un test que falla en vez de un cobro de más.
        # Descartarlo justo antes de que la referencia salga del backend sería
        # tirar el único aviso que acompaña al número.
        "facturable": False,
    }


def _pesos_facturables(transportistas, paquete, servicio) -> dict:
    """Un peso facturable por transportista, con su código. Y el propio.

    La misma caja pesa distinto en cada uno porque cada uno tiene su divisor y su
    umbral. Mostrarlos por separado evita el ticket "¿por qué en un lado pesa
    2,30 y en otro 5?" — y esconderlo no hace que la diferencia no exista.
    """
    salida = {"propio": str(servicio.get("peso_facturable_kg"))}
    for t in transportistas or []:
        codigo = (t or {}).get("codigo")
        if not codigo:
            continue
        try:
            pf = peso_facturable(paquete.get("peso_kg"), paquete.get("largo_cm"),
                                 paquete.get("ancho_cm"), paquete.get("alto_cm"),
                                 t.get("regla_peso") or {})
        except Exception as e:                                # pragma: no cover
            logger.warning(f"envios: peso facturable ilegible para {codigo}: {e}")
            continue
        salida[codigo] = str(pf)
    return salida


def _horas_ttl(operacion: dict) -> int:
    bruto = (operacion or {}).get("ttl_cotizacion_horas")
    try:
        horas = int(bruto)
    except (TypeError, ValueError):
        return TTL_HORAS_POR_DEFECTO
    # Un TTL de 0 o negativo dejaría toda cotización vencida en el instante en
    # que se crea. Es configuración, pero no cualquier número es un TTL.
    return horas if 1 <= horas <= 720 else TTL_HORAS_POR_DEFECTO


# ─── La respuesta ─────────────────────────────────────────────────────────

def _payload(envio, servicio, referencias, despacho, contexto, limites) -> dict:
    """Lo que ve la pantalla. Separa lo que se paga adentro de lo que se paga
    afuera, y lo dice con palabras, no con un color.

    Es la parte más importante del diseño de esta respuesta. El peor
    malentendido posible es que el usuario crea que pagando en RIS App ya cubrió
    el envío entero, y eso no se arregla después: se arregla acá, poniendo el
    concepto del servicio escrito y las referencias en otro bloque, con su
    etiqueta de quién las cobra.
    """
    cot = envio["cotizacion"]
    return {
        "envio_id": envio["envio_id"],
        "estado": envio["estado"],
        "es_estimado": True,
        "modalidad_flete": envio["modalidad_flete"],
        "moneda": cot["moneda"],

        "peso_real_kg": str(servicio.get("peso_real_kg")),
        "peso_facturable": {
            "propio": {
                "kg": str(servicio.get("peso_facturable_kg")),
                "volumetrico_kg": str(servicio.get("peso_volumetrico_kg")),
            },
            "por_transportista": [
                {"codigo": codigo, "kg": kg}
                for codigo, kg in envio["paquete"]["pf_declarado"].items()
                if codigo != "propio"
            ],
        },

        # LO ÚNICO QUE COBRA RIS APP.
        "a_pagar_en_risapp": {
            "concepto": CONCEPTO,
            "servicio_traslado": {"monto_ris": cot["servicio_traslado_ris"]},
            "sobrecargos": cot["sobrecargos"],
            "subtotal_ris": cot["subtotal_ris"],
            "margen_ris": cot["margen_ris"],
            "total_estimado_ris": cot["total_estimado_ris"],
        },

        # ORIENTACIÓN. Los contrata y los paga el usuario. No entran en el total.
        "referencias": [_referencia_visible(r) for r in (referencias or [])],

        "retiro": {k: v for k, v in despacho.items()
                   if k not in ("disponible", "faltantes", "retirador_id",
                                "retirador_motivo", "congelado_at")},

        "vence_at": cot["vence_at"],
        "terminos_version": cot["terminos_version"],
        "aviso_estimado": _aviso(contexto["contenido"]),
        "banda_variacion_pct": _banda(contexto["operacion"]),
        "limites": {k: str(v) for k, v in (limites or {}).items()},
    }


_ETIQUETAS = {
    "brasil": "Vas a pagar al despachar en Brasil",
    "venezuela": "Vas a pagar por el tramo dentro de Venezuela",
}

_SIN_DATO = "Consultalo en la agencia: todavía no tenemos una referencia de este tramo."

_BANDA_POR_DEFECTO = "15"


def _terminos(contexto: dict) -> str:
    """La versión de términos que se congela en el envío.

    Sale de la MISMA constante que publica `envios_catalogo.limites()`. Leerla
    del bloque `contenido` parecía más configurable y era peor: con el bloque sin
    cargar —o con un error de lectura de dos segundos— el envío se guardaba con
    `terminos_version: None` mientras la pantalla mostraba una versión, y quedaba
    un envío sin registro de qué aceptó el usuario.
    """
    from services.envios_policy import TERMINOS_VERSION
    if contexto.get("contenido_ok"):
        propia = (contexto.get("contenido") or {}).get("terminos_version")
        if propia:
            return str(propia)
    return TERMINOS_VERSION


def _referencia_visible(r: dict) -> dict:
    monto = r.get("monto")
    return {
        # Por CODIGO, no por nombre. El nombre comercial lo pone la pantalla
        # desde `/envios/catalogo`, que es la única ruta que lo sirve: la
        # proyección de referencias.py lo excluye a propósito para que no viaje a
        # un log, y volver a pedirlo acá sería deshacer esa decisión de un lado
        # sin enterarse del otro.
        "codigo": r.get("codigo"),
        "rol": r.get("rol"),
        "etiqueta": _ETIQUETAS.get(r.get("rol"), "Lo pagás vos, por fuera de RIS App"),
        "monto": None if monto is None else str(monto),
        "moneda": r.get("moneda"),
        "fuente": r.get("fuente"),
        "desactualizada": bool(r.get("desactualizada")),
        "facturable": False,
        "detalle": None if monto is not None else _SIN_DATO,
    }


def _aviso(contenido: dict) -> str:
    texto = ((contenido or {}).get("texto_estimado") or "").strip()
    return texto or AVISO_POR_DEFECTO


def _banda(operacion: dict) -> str:
    """La banda de variación esperada, en porcentaje y como texto."""
    bruto = (operacion or {}).get("banda_variacion_pct")
    if bruto is None:
        return _BANDA_POR_DEFECTO
    try:
        pct = to_decimal(bruto)
    except Exception:                                         # pragma: no cover
        return _BANDA_POR_DEFECTO
    # Un 0 CARGADO A PROPOSITO es "el precio no varía", que es una decisión
    # comercial legítima y no una ausencia. Tragárselo con el fallback es la
    # misma clase de bug que un `or` sobre un cero, escrita como comparación.
    if not pct.is_finite() or pct < 0 or pct > 1:
        return _BANDA_POR_DEFECTO
    return str(quantize_money(pct * 100, 0))


# ─── Vencimiento ──────────────────────────────────────────────────────────

def esta_vencida(envio: dict, ahora=None) -> bool:
    """Una cotización vencida no se puede confirmar. Nunca lanza.

    Sin fecha de vencimiento se considera vencida, no eterna: es el mismo
    criterio que el resto del módulo usa con los datos que no se pueden leer, y
    acá el error caro es confirmar dentro de seis meses un precio de hoy.
    """
    ahora = ahora or datetime.now(timezone.utc)
    vence = ((envio or {}).get("cotizacion") or {}).get("vence_at")
    if isinstance(vence, str):
        try:
            vence = datetime.fromisoformat(vence.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(vence, datetime):
        return True
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    return vence <= ahora
