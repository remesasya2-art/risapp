"""
services/envios_estados.py — El ciclo de vida de un envio y sus dos cobros.

POR QUE EXISTE ESTE MODULO
    Un envio pasa por trece estados y no todos los caminos entre ellos son
    validos. Sin un lugar donde eso este escrito, la regla termina repartida en
    los `if` de cada ruta, cada una con su propia idea de lo que se puede hacer,
    y aparece el bug clasico: un envio que avanza con una deuda encima, o un
    operador que "corrige" un estado terminal y borra la unica prueba de que el
    servicio se cumplio.

ESTADO (PR B)
    Modulo PURO y AISLADO: sin Mongo, sin red, sin framework. Ninguna ruta lo
    llama todavia. No cambia el comportamiento de la aplicacion.

EL MODELO DE PLATA: DOS COBROS, NINGUNO AL COTIZAR
    Cotizar no cuesta nada. El estimado sale de lo que el usuario declaro —la
    gente redondea, no mide la caja, pesa en una balanza de baño— y cobrar contra
    eso convierte cada envio en una diferencia que reclamar.

    El precio se construye en dos pasos, y cada uno se apoya en una medicion que
    NO salio del usuario:

      1. COBRO INICIAL, cuando el usuario carga el comprobante de despacho y el
         equipo lo verifica. Se calcula con **el peso por el que el transportista
         de origen ya le cobro a el**, que figura en ese comprobante: una medicion
         hecha por alguien sin ningun interes en que sea baja. Es un cobro real,
         pero no es el precio absoluto.

      2. AJUSTE, en el repesaje de Pacaraima, con balanza propia. Compara contra
         el cobro inicial y cierra el precio: cobra la diferencia, la devuelve, o
         no hace nada.

    La rama que devuelve importa mas de lo que parece: si el sistema solo cobrara
    de mas y nunca devolviera, el "cobro inicial" seria un anticipo disfrazado.

LOS ESTADOS DICEN DONDE ESTA EL PAQUETE, NO COMO VA LA PLATA
    El dinero vive en el bloque `cobros` del envio, con una partida por cobro y
    su propio estado. Mezclar las dos cosas llenaba la maquina de estados de
    casos como "en transito pero debiendo".

    La consecuencia practica: un cobro inicial impago NO cambia el estado del
    paquete, que sigue viajando hacia Pacaraima sin depender de nosotros. Lo que
    la deuda impide es **salir** de Pacaraima.

EL BUG MAS CARO DEL MODULO, Y COMO SE EVITA
    Recalcular con precios distintos de los que el usuario acepto. No falla
    ningun test obvio, no tira excepcion, y aparece como una avalancha de
    reclamos la semana siguiente a un cambio de precios. El ajuste corrige el
    PESO, nunca los precios.

    Se lo bloquea por partida triple:
      1. La VERSION de tarifa tiene que ser la congelada al cotizar, o lanza.
      2. La FECHA del calculo es la de la cotizacion, no la del mostrador. Sin
         esto, un recargo de temporada configurado DENTRO de la misma version se
         cobraria como si fuera peso.
      3. Los parametros comerciales —bultos, valor declarado— salen del envio, no
         de lo que pase la ruta.

EL CRITERIO ANTE UN DATO ROTO, QUE ES EL OPUESTO AL DE envios_tarifas.py
    Alla, ante un dato faltante, se cotiza cobrando de menos: es una estimacion y
    equivocarse para abajo es barato. Aca NO. Estos dos cobros son reales, con un
    paquete despachado o en la mano, y un dato ilegible no es una imprecision: es
    un envio roto. Por eso se LANZA ante lo que no se puede leer, en vez de
    asumir un cero que se convierte en un cobro o en una devolucion del total.
"""

from decimal import Decimal, InvalidOperation

from services.money import to_decimal, quantize_money, money_sub
from services.envios_tarifas import cotizar_servicio

# ─── Los estados ──────────────────────────────────────────────────────────

ESTADOS = {
    "cotizado":               "Precio estimado sobre lo declarado. Sin plata movida.",
    "esperando_postagem":     "Aceptó las condiciones y tiene los datos de despacho.",
    "en_transito_origen":     "Cargó el comprobante. Acá se emite el cobro inicial.",
    "disponible_retiro":      "Se espera en la agencia de Pacaraima. Reloj de guarda corriendo.",
    "recibido_pacaraima":     "Retirado del mostrador por el equipo. Ya está en manos de RIS App.",
    "repesado":               "Pesado con balanza propia. Se ajusta el precio.",
    "pago_pendiente":         "En Pacaraima y sin poder salir: hay una partida impaga.",
    "en_transito_int":        "Todo pago al día. En traslado hacia Santa Elena de Uairén.",
    "entregado_transportista": "Entregado con guía y foto. El servicio de RIS App terminó acá.",
    "cancelado":              "Cancelado antes de que hubiera nada que cobrar, o con devolución.",
    "retenido":               "Aduana o contenido observado. Requiere resolución manual.",
    "devuelto":               "Vuelve al remitente.",
    "siniestrado":            "Perdido o dañado. Abre indemnización.",
}

TRANSICIONES = {
    "cotizado":               {"esperando_postagem", "cancelado"},
    "esperando_postagem":     {"en_transito_origen", "cancelado"},
    # Acá se emite el COBRO INICIAL, contra el peso del comprobante. Que quede
    # impago no frena el paquete: ya está viajando y no depende de nosotros.
    "en_transito_origen":     {"disponible_retiro", "siniestrado", "cancelado"},
    "disponible_retiro":      {"recibido_pacaraima", "devuelto", "siniestrado"},
    "recibido_pacaraima":     {"repesado", "retenido", "devuelto", "siniestrado"},
    # El repesaje AJUSTA contra el cobro inicial.
    "repesado":               {"pago_pendiente", "en_transito_int", "retenido",
                               "devuelto", "siniestrado"},
    "pago_pendiente":         {"en_transito_int", "devuelto", "cancelado",
                               "retenido", "siniestrado"},
    "en_transito_int":        {"entregado_transportista", "retenido", "siniestrado"},
    # `retenido -> repesado` existe porque un paquete puede quedar retenido ANTES
    # de pesarse: sin esa vuelta, la única salida hacia adelante se saltea el
    # ajuste y el envío viaja con el precio todavía sin cerrar.
    "retenido":               {"repesado", "en_transito_int", "devuelto", "siniestrado"},
    # Terminales: de acá en adelante el paquete es del transportista y no se ve.
    "entregado_transportista": set(),
    "cancelado":              set(),
    "devuelto":               set(),
    "siniestrado":            set(),
}

TERMINALES = {"entregado_transportista", "cancelado", "devuelto", "siniestrado"}

# Salir de Pacaraima exige el precio cerrado y las partidas al día.
SALIDA_DE_PACARAIMA = "en_transito_int"
# Entregar exige, además, el flete pago cuando la modalidad es prepago.
ENTREGA_FINAL = "entregado_transportista"

ACTOR_POR_DEFECTO = frozenset({"admin"})
ACTORES_VALIDOS = frozenset({"user", "admin", "system"})

ACTORES = {
    # Confirmar el envío no cuesta nada: lo hace el usuario y no mueve saldo.
    ("cotizado", "esperando_postagem"):            frozenset({"user"}),
    ("cotizado", "cancelado"):                     frozenset({"user", "admin", "system"}),
    # Sin API de rastreo, quien avisa que despachó es el propio usuario.
    ("esperando_postagem", "en_transito_origen"):  frozenset({"user"}),
    ("esperando_postagem", "cancelado"):           frozenset({"user", "admin", "system"}),
    ("en_transito_origen", "disponible_retiro"):   frozenset({"system", "admin"}),
    ("en_transito_origen", "cancelado"):           frozenset({"admin"}),
    ("disponible_retiro", "recibido_pacaraima"):   frozenset({"admin"}),
    ("disponible_retiro", "devuelto"):             frozenset({"system", "admin"}),
    ("repesado", "pago_pendiente"):                frozenset({"system"}),
    ("repesado", "en_transito_int"):               frozenset({"system", "admin"}),
    ("pago_pendiente", "en_transito_int"):         frozenset({"system", "admin"}),
    ("pago_pendiente", "cancelado"):               frozenset({"admin"}),
}


def actores_de(desde: str, hacia: str) -> frozenset:
    return ACTORES.get((desde, hacia), ACTOR_POR_DEFECTO)


def es_terminal(estado: str) -> bool:
    return estado in TERMINALES


def transicion_existe(desde: str, hacia: str) -> bool:
    return hacia in TRANSICIONES.get(desde, set())


def puede_transicionar(desde: str, hacia: str, actor_type: str,
                       partida_impaga: bool = False,
                       precio_cerrado: bool = True,
                       flete_impago: bool = False) -> str | None:
    """Mensaje de error, o None si la transición es válida.

    No lanza: la ruta decide si eso es un 400, un 403 o un cartel — mismo
    criterio que services/limits.py.

    Tres banderas hacen cumplir invariantes que no se pueden leer del nombre del
    estado, y por eso se pasan explícitamente:

    `partida_impaga` — el cobro inicial o el ajuste sin pagar. El paquete no sale
    de Pacaraima. Es la única palanca de cobro que el negocio puede ejecutar de
    verdad: la posesión física.

    `precio_cerrado` — el envío no viaja si nunca se repesó. Existe por un camino
    real: `recibido_pacaraima → retenido → en_transito_int` esquiva el ajuste, y
    sin esta bandera el paquete sale con el precio sin cerrar y nadie se entera.

    `flete_impago` — en modalidad prepago, la remesa del usuario al transportista
    todavía no está acreditada. No se entrega el paquete.
    """
    if desde not in TRANSICIONES:
        return f"El estado de origen no existe: {desde!r}."
    if hacia not in TRANSICIONES:
        return f"El estado de destino no existe: {hacia!r}."
    if actor_type not in ACTORES_VALIDOS:
        return f"Actor desconocido: {actor_type!r}."

    if desde == hacia:
        return "El envío ya está en ese estado."

    if es_terminal(desde):
        return (
            f"El envío está en {desde}, que es un estado terminal. Corregir un terminal es "
            "una operación de administración explícita y auditada, no una transición."
        )

    if hacia not in TRANSICIONES[desde]:
        return f"Un envío en {desde} no puede pasar a {hacia}."

    permitidos = actores_de(desde, hacia)
    if actor_type not in permitidos:
        return (
            f"Esta transición la dispara {' o '.join(sorted(permitidos))}, "
            f"no {actor_type}."
        )

    # Los candados de avance. Se permite igual todo lo que RESUELVE el problema
    # —devolver, cancelar, retener, declarar siniestro—; lo que no se permite es
    # que el paquete siga viaje.
    if hacia == SALIDA_DE_PACARAIMA:
        if partida_impaga:
            return (
                "El envío tiene una partida sin pagar. El paquete no sale de Pacaraima "
                "hasta que se salde."
            )
        if not precio_cerrado:
            return (
                "El envío todavía no se repesó, así que su precio sigue sin cerrarse. "
                "El paquete no puede viajar sin que el precio se cierre."
            )
    elif hacia == ENTREGA_FINAL:
        if partida_impaga:
            return "El envío tiene una partida del servicio sin pagar."
        if flete_impago:
            return (
                "El flete todavía no está acreditado. El paquete espera con el equipo, "
                "no se entrega en el mostrador."
            )

    return None


# ─── El efecto monetario de cada transición ───────────────────────────────

# Invariante 1: el saldo se mueve en dos momentos, y los dos son DESPUÉS de que
# el paquete existe. El cobro inicial no figura acá porque no es una transición:
# se emite mientras el envío está en `en_transito_origen`, al verificarse el
# comprobante, y el paquete sigue viajando pase lo que pase con esa deuda.
EFECTOS = {
    ("repesado", "en_transito_int"):       "ajuste",             # rama A, B o C
    ("repesado", "pago_pendiente"):        "ninguno",            # se cobra al saldarse
    ("pago_pendiente", "en_transito_int"): "cobro_diferencia",
}

EFECTOS_POSIBLES = frozenset({"ninguno", "ajuste", "cobro_diferencia", "reembolso"})

# Los dos cobros del servicio, como datos. La ruta los emite; esta lista existe
# para que un test pueda recorrerla y para que nadie invente una tercera partida
# sin que se note.
PARTIDAS = ("inicial", "ajuste")


def efecto_monetario(desde: str, hacia: str) -> str:
    """Qué le pasa al saldo del usuario en esa transición.

    Lanza ante un par que no es una transición válida. Es deliberado: esta
    función materializa la invariante 1, y contestar "ninguno" sobre un camino
    que no existe da una falsa sensación de cobertura.

    Los reembolsos no se listan uno por uno porque dependen del destino y no del
    origen. *Cuánto* se devuelve no lo decide este módulo: cancelar antes de
    despachar no tiene nada que devolver, y un paquete ya retirado y pesado
    descuenta lo que costó traerlo hasta ahí.
    """
    if not transicion_existe(desde, hacia):
        raise ValueError(f"{desde} -> {hacia} no es una transición válida.")
    if hacia in ("cancelado", "devuelto", "siniestrado"):
        return "reembolso"
    return EFECTOS.get((desde, hacia), "ninguno")


def mueve_saldo(desde: str, hacia: str) -> bool:
    return efecto_monetario(desde, hacia) != "ninguno"


# ─── Errores ──────────────────────────────────────────────────────────────

class TarifaEquivocada(ValueError):
    """Se intentó calcular con una tarifa distinta de la congelada en el envío.

    Lanza en vez de devolver un mensaje porque del otro lado hay una ruta que le
    está por cobrar al usuario un aumento de lista posterior a lo que aceptó.
    Mejor un 500 en un envío que un cobro indebido en todos.
    """


class EnvioIncompleto(ValueError):
    """Falta un dato sin el cual no se puede emitir un cobro.

    No se asume un cero. Un peso ilegible en el comprobante haría un cobro
    inicial de cero; un `cobros.inicial` ausente convertiría el ajuste en un
    cobro del precio entero por segunda vez. Las dos cosas pasan en silencio y
    ninguna se reclama.
    """


TOLERANCIA_POR_DEFECTO = Decimal("2.00")

# Cota de cordura de las medidas. No es un límite de negocio —esos los pone
# envios_policy.py— sino la barrera contra la balanza que devuelve basura o el
# operador que teclea de más.
_PESO_MAX = Decimal("1000")


def _numero_estricto(valor, campo: str) -> Decimal:
    """Convierte a Decimal o lanza. Nunca devuelve un cero de consuelo.

    Rechaza explícitamente la coma decimal: "6,5" es una forma perfectamente
    razonable de tipear seis kilos y medio, y `to_decimal` la convierte en 0 sin
    decir nada.
    """
    if valor is None or isinstance(valor, bool):
        raise EnvioIncompleto(f"Falta {campo}.")
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            raise EnvioIncompleto(f"Falta {campo}.")
        if "," in texto:
            raise EnvioIncompleto(
                f"{campo} viene con coma decimal ({valor!r}). Se espera un número con punto."
            )
        try:
            d = Decimal(texto)
        except InvalidOperation:
            raise EnvioIncompleto(f"{campo} no es un número: {valor!r}.") from None
    else:
        try:
            d = to_decimal(valor)
        except Exception:
            raise EnvioIncompleto(f"{campo} no es un número: {valor!r}.") from None
        if d == 0 and not isinstance(valor, (int, float, Decimal)):
            raise EnvioIncompleto(f"{campo} no es un número: {valor!r}.")
    if not d.is_finite():
        raise EnvioIncompleto(f"{campo} no es un número finito: {valor!r}.")
    return d


def _medida_positiva(valor, campo: str, maximo=_PESO_MAX) -> Decimal:
    d = _numero_estricto(valor, campo)
    if d <= 0:
        raise EnvioIncompleto(f"{campo} tiene que ser mayor a 0; llegó {d}.")
    if d > maximo:
        raise EnvioIncompleto(f"{campo} no parece una medida real: {d}.")
    return d


def _tarifa_del_envio(envio: dict, tarifa: dict) -> str:
    """Comprueba que la tarifa sea la congelada al cotizar. Devuelve su version_id."""
    cotizacion = (envio or {}).get("cotizacion") or {}
    congelada = cotizacion.get("tarifa_version")
    recibida = (tarifa or {}).get("version_id")
    if not congelada:
        raise EnvioIncompleto(
            "El envío no tiene registrada la versión de tarifa con la que se cotizó, así que "
            "no hay forma de calcular sin arriesgarse a cobrarle precios que no aceptó."
        )
    if recibida != congelada:
        raise TarifaEquivocada(
            f"El envío se cotizó con la tarifa {congelada!r} y se intentó calcular con "
            f"{recibida!r}. Los dos cobros usan siempre la versión congelada: el ajuste "
            "corrige el peso, no los precios."
        )
    if not (tarifa.get("escalones_peso") or
            (tarifa.get("servicio_traslado") or {}).get("escalones")):
        raise EnvioIncompleto(
            f"La tarifa {recibida!r} no tiene tabla de escalones: calcular con ella daría cero."
        )
    return recibida


def _cotizar(envio: dict, tarifa: dict, peso, largo, ancho, alto) -> dict:
    """Precio del servicio para ese paquete, con los parámetros congelados del envío.

    Los parámetros comerciales —bultos, valor declarado, fecha— salen del envío y
    nunca de quien llama: son parte de lo que el usuario aceptó, y moverlos es
    cobrarle algo distinto sin decírselo.
    """
    declarado = (envio or {}).get("paquete") or {}
    cotizacion = (envio or {}).get("cotizacion") or {}
    return cotizar_servicio(
        tarifa, peso, largo, ancho, alto,
        valor_declarado=declarado.get("valor_declarado", 0),
        bultos=declarado.get("bultos") or 1,
        fecha=cotizacion.get("fecha"),      # la de la cotización, no la de hoy
    )


# ─── 1. El cobro inicial, contra el comprobante ───────────────────────────

def cobro_inicial(envio, tarifa_congelada, peso_comprobante_kg,
                  largo_cm, ancho_cm, alto_cm) -> dict:
    """El primer cobro, calculado con el peso que midió el transportista de origen.

    Ese peso figura en el comprobante de despacho que el usuario carga: es una
    medición hecha por alguien sin ningún interés en que sea baja, y llega antes
    de que el paquete cruce nada. No es el precio absoluto —la balanza propia
    puede dar otra cosa en Pacaraima— pero es infinitamente mejor que cobrar
    contra lo que el usuario declaró.

    NO recibe zona ni destino, igual que cotizar_servicio: el precio del servicio
    no depende de a dónde siga el paquete.
    """
    version = _tarifa_del_envio(envio, tarifa_congelada)

    peso = _medida_positiva(peso_comprobante_kg, "el peso del comprobante")
    largo = _medida_positiva(largo_cm, "el largo del comprobante")
    ancho = _medida_positiva(ancho_cm, "el ancho del comprobante")
    alto = _medida_positiva(alto_cm, "el alto del comprobante")

    cotizacion = _cotizar(envio, tarifa_congelada, peso, largo, ancho, alto)
    declarado = (envio or {}).get("paquete") or {}

    return {
        "partida": "inicial",
        "base": "comprobante",
        "tarifa_version": version,
        "monto": cotizacion["total"],
        "peso_base_kg": peso,
        "desglose": {
            "declarado": {
                "peso_kg": to_decimal(declarado.get("peso_kg")),
                "largo_cm": to_decimal(declarado.get("largo_cm")),
                "ancho_cm": to_decimal(declarado.get("ancho_cm")),
                "alto_cm": to_decimal(declarado.get("alto_cm")),
            },
            "comprobante": {
                "peso_kg": peso, "largo_cm": largo, "ancho_cm": ancho, "alto_cm": alto,
                "peso_facturable_kg": cotizacion["peso_facturable_kg"],
            },
            "cotizacion": cotizacion,
        },
    }


# ─── 2. El ajuste, contra la balanza propia ───────────────────────────────

def ajuste_por_repesaje(envio, tarifa_congelada, peso_verificado_kg,
                        largo_cm, ancho_cm, alto_cm,
                        tolerancia=None) -> dict:
    """Cierra el precio con el peso y las medidas reales, contra el cobro inicial.

    Devuelve el desglose completo —no un monto suelto— porque es lo que se le
    muestra al usuario: "el transportista registró 2,30 kg y nosotros pesamos
    2,65; la diferencia es 6,70". Un ajuste sin desglose es un reclamo
    garantizado.

    Tres ramas:
      A  |diferencia| <= tolerancia  -> no se mueve plata, pero se registra
      B  diferencia > tolerancia     -> hay que cobrar
      C  diferencia < -tolerancia    -> hay que devolver

    La rama A no es tacañería al revés: generar un cobro de treinta centavos
    cuesta más en soporte que lo que recauda. Y la rama C es la que hace creíble
    la palabra "inicial": si el sistema solo cobrara de más y nunca devolviera,
    el cobro inicial sería un anticipo disfrazado.

    NO devuelve el estado siguiente. Ese lo decide `estado_tras_ajuste()`, que
    mira el saldo: un ajuste a cobrar termina en `en_transito_int` o en
    `pago_pendiente` según si el usuario tiene con qué, y tener dos funciones del
    mismo módulo contestando "el próximo estado" es cómo un paquete termina
    viajando con la deuda encima.

    NO es idempotente ni pretende serlo: llamarla dos veces sin haber escrito el
    resultado devuelve la misma diferencia dos veces. La ruta es la que tiene que
    cobrar una sola vez, con la idempotencia del repositorio.
    """
    version = _tarifa_del_envio(envio, tarifa_congelada)

    peso = _medida_positiva(peso_verificado_kg, "el peso verificado")
    largo = _medida_positiva(largo_cm, "el largo verificado")
    ancho = _medida_positiva(ancho_cm, "el ancho verificado")
    alto = _medida_positiva(alto_cm, "el alto verificado")

    inicial = ((envio or {}).get("cobros") or {}).get("inicial") or {}
    cobrado = quantize_money(_numero_estricto(
        inicial.get("monto_ris"), "el monto del cobro inicial"))
    if cobrado <= 0:
        raise EnvioIncompleto(
            f"El envío figura con un cobro inicial de {cobrado}. Sin ese número el ajuste "
            "cobraría el precio entero por segunda vez."
        )

    tol = TOLERANCIA_POR_DEFECTO if tolerancia is None else _numero_estricto(
        tolerancia, "la tolerancia de ajuste")
    if tol < 0:
        raise EnvioIncompleto(f"La tolerancia no puede ser negativa; llegó {tol}.")

    nueva = _cotizar(envio, tarifa_congelada, peso, largo, ancho, alto)
    total_final = nueva["total"]
    diferencia = money_sub(total_final, cobrado)

    if abs(diferencia) <= tol:
        rama = "sin_ajuste"
    elif diferencia > 0:
        rama = "cobrar"
    else:
        rama = "devolver"

    comprobante = ((envio or {}).get("origen") or {})
    return {
        "partida": "ajuste",
        "rama": rama,
        "tarifa_version": version,
        "cobrado_inicial": cobrado,
        "total_final": total_final,
        "diferencia": diferencia,
        "tolerancia": tol,
        "desglose": {
            "comprobante": {
                "peso_kg": to_decimal(inicial.get("peso_base_kg")),
                "monto_ris": cobrado,
            },
            "verificado": {
                "peso_kg": peso, "largo_cm": largo, "ancho_cm": ancho, "alto_cm": alto,
                "peso_facturable_kg": nueva["peso_facturable_kg"],
            },
            "codigo_objeto": comprobante.get("codigo_objeto"),
            "cotizacion_nueva": nueva,
        },
    }


def estado_tras_ajuste(ajuste: dict, saldo_disponible) -> str:
    """A dónde va el envío después del repesaje, mirando el saldo del usuario.

    Separado de ajuste_por_repesaje() a propósito: el cálculo del precio es puro
    y no debería tener que saber cuánta plata tiene alguien en la cuenta.

    El débito real es de la ruta, con find_one_and_update condicional al saldo:
    esta función dice a dónde debería ir, no reemplaza la comprobación atómica.
    Que el saldo alcance ahora no garantiza que alcance dos líneas más abajo.
    """
    if ajuste["rama"] != "cobrar":
        return "en_transito_int"
    if to_decimal(saldo_disponible) >= ajuste["diferencia"]:
        return "en_transito_int"
    return "pago_pendiente"


def partidas_impagas(envio: dict) -> list[str]:
    """Qué cobros del servicio están sin pagar. Vacío = el paquete puede avanzar.

    Es la bandera `partida_impaga` de puede_transicionar(), calculada del envío en
    vez de deducida del estado: la deuda vive en el bloque de cobros, no en el
    nombre del estado. Una partida sin `estado` cuenta como pendiente — el que
    emite un cobro tiene que decir cómo quedó.
    """
    cobros = (envio or {}).get("cobros") or {}
    return [p for p in PARTIDAS
            if isinstance(cobros.get(p), dict)
            and cobros[p].get("estado") != "pagado"]
