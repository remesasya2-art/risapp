"""
services/envios_tarifas.py — El motor de precios del modulo de traslado transfronterizo.

POR QUE EXISTE ESTE MODULO
    Un paquete no tiene un peso: tiene tres. El transportista de Brasil lo cubica
    con su divisor, el de Venezuela con el suyo, y RIS App con el propio. La misma
    caja "pesa" distinto en cada tramo, y solo uno de esos tres numeros decide un
    cobro: el de RIS App. Los otros dos se muestran como orientacion y sirven para
    validar el formulario.

    Este modulo concentra ese calculo. Es PURO: no toca Mongo, no sale a la red,
    no importa nada del framework. Recibe la regla y la tarifa como diccionarios
    —tal como salen de la base— y devuelve numeros.

ESTADO (PR A)
    El modulo esta AISLADO, igual que la Fase 1 de services/money.py: define las
    funciones pero todavia ninguna ruta lo llama. No cambia el comportamiento de
    la aplicacion. Los PRs siguientes lo van conectando.

DE DONDE SALEN LOS DATOS
    Ni las reglas ni los precios viven aca. Las reglas de peso son un campo de
    cada transportista y se editan desde el panel de configuracion; la tarifa
    propia es un documento versionado de la coleccion tarifas_envio. Este archivo
    solo conoce la FORMA de esos diccionarios, nunca sus valores, y jamas el
    nombre de una empresa: los transportistas se nombran por su codigo
    alfanumerico.

EL CRITERIO ANTE UNA CONFIGURACION INCOMPLETA
    Es uno solo y se aplica en todo el archivo: **ante un dato faltante o
    ilegible, se cobra de menos, nunca de mas**. Un divisor invalido no cubica,
    un sobrecargo con una condicion que no se entiende no se aplica, una tabla
    vacia no inventa un precio. Cobrarle de mas a un usuario por un typo en el
    panel es el peor error posible de este modulo, porque nadie lo reclama: el
    que paga de mas no sabe que pago de mas.

    Lo que impide que ese criterio se transforme en regalar el servicio es
    validar_tarifa(): la configuracion incompleta se rechaza ANTES de publicar,
    no se compensa despues cobrando.

TODO EN DECIMAL, SIN EXCEPCION
    Multiplicar tres dimensiones y dividir por un divisor amplifica el ruido del
    float mas que cualquier otro calculo del sistema: 30 * 20 * 15 / 6000 en float
    puede dar 1.4999999999999998 y caer un escalon mas abajo del que corresponde.
    Por eso todo entra por to_decimal() y sale como Decimal.

LO QUE ESTE MODULO NO HACE
    No decide si un paquete se puede enviar —eso es envios_policy.py—, no lee la
    tarifa vigente, no persiste nada y no sabe que es una zona: el precio del
    servicio propio es una funcion de UNA sola variable, el peso facturable.
"""

from math import isfinite
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from services.money import to_decimal, quantize_money

ZERO = Decimal("0")
UNO = Decimal("1")

# Precision del peso: gramos. Mas alla de tres decimales no hay balanza que lo
# distinga, y deja el numero legible en la pantalla del operador.
_PESO_EXP = Decimal("0.001")

# Techo de cordura para las magnitudes. No es un limite de negocio —esos los pone
# envios_policy.py con la interseccion de los transportistas— sino la barrera que
# evita que un 1e40 pegado en un campo haga estallar el contexto decimal (28
# digitos) con un InvalidOperation en la cara del usuario.
_MAGNITUD_MAX = Decimal("1000000")


def _sano(valor) -> Decimal:
    """Convierte a Decimal y descarta lo que no puede ser una medida real."""
    d = to_decimal(valor)
    if d < 0 or d > _MAGNITUD_MAX or not d.is_finite():
        return ZERO
    return d


_TEXTOS_FALSOS = {"false", "no", "0", "off", "", "none", "null"}


def _activo(fila) -> bool:
    """Una fila de configuracion esta activa salvo que diga que no.

    La ausencia del campo significa activa; lo que apaga la fila es un valor
    falso. Y "falso" incluye los strings: del panel un checkbox puede viajar
    como False, 0, "" o el texto "false" segun como se serialice el formulario,
    y `bool("false")` es True. Comparando con `is False` —o confiando en la
    falsedad de Python— un sobrecargo desactivado se seguia cobrando.
    """
    valor = fila.get("activo", True)
    if isinstance(valor, str):
        return valor.strip().lower() not in _TEXTOS_FALSOS
    return bool(valor)


# ─── Peso facturable ──────────────────────────────────────────────────────
#
# Una regla por transportista. NO hay divisor global. La forma del diccionario:
#
#   {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
#    "umbral_cubado_kg": None}      # None = el cubado se aplica siempre
#
# La unica excepcion es la regla propia de RIS App, que vive dentro de la version
# de tarifa porque cambia junto con los precios y se versiona con ellos.

def peso_volumetrico(largo_cm, ancho_cm, alto_cm, divisor) -> Decimal:
    """Kilos que "ocupa" la caja segun el divisor del transportista.

    Divisor 0, negativo o basura devuelve 0: no se inventa un peso, y el que
    llama se queda con el peso real. Es preferible cobrar de menos por una
    configuracion incompleta que cobrar un numero que salio de una division
    invalida.
    """
    d = _sano(divisor)
    if d <= 0:
        return ZERO
    vol = _sano(largo_cm) * _sano(ancho_cm) * _sano(alto_cm)
    if vol <= 0:
        return ZERO
    try:
        return (vol / d).quantize(_PESO_EXP, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # pragma: no cover — _sano ya acota la magnitud
        return ZERO


def peso_facturable(peso_real_kg, largo_cm, ancho_cm, alto_cm, regla) -> Decimal:
    """El peso por el que ese transportista cobraria esta caja.

    Tres pasos, en este orden:
      1. bruto  = max(real, cubado), salvo que el cubado no llegue al umbral.
      2. escalonado = bruto redondeado HACIA ARRIBA al escalon (0,5 kg tipico).
      3. facturable = max(minimo, escalonado).

    El umbral se compara contra el peso CUBICADO, que es como lo declaran los
    transportistas que lo usan ("por debajo de N kg de cubaje no se cubica"), y
    es inclusivo: un cubado exactamente igual al umbral no lo supera. Con umbral
    None se cubica siempre.
    """
    regla = regla or {}
    real = _sano(peso_real_kg)
    cubado = peso_volumetrico(largo_cm, ancho_cm, alto_cm, regla.get("divisor"))

    umbral = regla.get("umbral_cubado_kg")
    if umbral is not None and cubado <= to_decimal(umbral):
        bruto = real
    else:
        bruto = max(real, cubado)

    escalon = _sano(regla.get("escalon_kg"))
    minimo = _sano(regla.get("minimo_kg"))

    if escalon <= 0:
        escalonado = bruto
    else:
        pasos = (bruto / escalon).quantize(Decimal("1"), rounding=ROUND_CEILING)
        escalonado = pasos * escalon

    return max(minimo, escalonado).quantize(_PESO_EXP, rounding=ROUND_HALF_UP)


# ─── La tabla de precios del servicio propio ──────────────────────────────

def _escalones_ordenados(escalones) -> list[dict]:
    """Normaliza la tabla a [{desde, hasta, precio}] ordenada, descartando basura.

    Acepta las dos formas que conviven en la base: la del editor, con desde_kg y
    hasta_kg explicitos, y la vieja, con solo hasta_kg —donde cada fila arranca
    donde termino la anterior—. Asi una tarifa cargada antes del panel sigue
    cotizando igual despues.

    Dos precauciones que parecen de mas y no lo son:
      - Se ORDENA POR 'hasta' ANTES de derivar los 'desde' implicitos. Si se
        derivaran en el orden en que vienen, la misma tabla guardada en otro
        orden cotizaria distinto, y el orden de un array de Mongo no es una
        garantia que valga la pena confiar.
      - Una fila sin 'hasta_kg' legible se DESCARTA en vez de valer 0. Valiendo
        0 se colaba adelante de todas y se llevaba puestos los escalones
        siguientes: un paquete de 4 kg podia terminar pagando el escalon de 10.
        validar_tarifa() la reporta antes de que se publique.
    """
    filas = []
    for e in (escalones or []):
        if not isinstance(e, dict) or e.get("hasta_kg") is None:
            continue
        hasta = to_decimal(e.get("hasta_kg"))
        if hasta <= 0:
            continue
        desde = to_decimal(e["desde_kg"]) if e.get("desde_kg") is not None else None
        filas.append({"desde": desde, "hasta": hasta, "precio": to_decimal(e.get("precio"))})

    filas.sort(key=lambda f: (f["hasta"], f["desde"] if f["desde"] is not None else ZERO))

    anterior = ZERO
    for f in filas:
        if f["desde"] is None:
            f["desde"] = anterior
        anterior = f["hasta"]
    return filas


def precio_por_escalon(peso_kg, escalones, adicional_por_unidad=0) -> Decimal:
    """Precio de la tabla para un peso —o un volumen— dado.

    Se exige que el valor caiga DENTRO del escalon (desde <= x <= hasta), no solo
    que no lo supere: con la comparacion a medias, dos filas que empiezan en el
    mismo punto hacian que el precio dependiera del orden de la lista.

    EL BORDE COMPARTIDO: `desde` y `hasta` son los dos INCLUSIVOS, asi que en una
    tabla contigua —3–6 seguida de 6–10— el 6,00 cae adentro de las dos filas.
    Gana la de ABAJO: un paquete de 6 kg justos paga el escalon "hasta 6". Es lo
    que dice el nombre del campo —`hasta_kg`, o sea que el 6 esta incluido—, es
    lo que cobra el sitio desde que existe, y es coherente con el criterio de
    todo el modulo: ante la duda, de menos y no de mas.

    Lo hace la iteracion en orden: `_escalones_ordenados` ordena por `hasta`, asi
    que la primera fila que matchea es siempre la de tope mas bajo. NO cambiar
    esto por un `max`, un `reversed` o un "la ultima que matchea" sin entender
    que es una decision de precio: cada borde de la tabla cambiaria de banda y
    los paquetes de peso redondo —que son muchos, porque el facturable se
    redondea al escalon— pasarian a pagar el tramo siguiente.

    La ambiguedad de fondo la resuelve el editor de precios, que escribe el
    `desde` siguiente en +0,01 para que cada peso pertenezca a una sola fila.
    Esto es lo que hace que las tablas YA cargadas, con el borde compartido,
    sigan cobrando exactamente lo mismo.

    Por encima del ultimo escalon se cobra el adicional por cada unidad que
    sobra. Por debajo del primero —una tabla que no arranca en cero, que
    validar_tarifa() rechaza— se cobra el escalon mas barato: ante una tabla mal
    cargada, de menos y no de mas.
    """
    filas = _escalones_ordenados(escalones)
    if not filas:
        return ZERO

    valor = to_decimal(peso_kg)
    for f in filas:
        if f["desde"] <= valor <= f["hasta"]:
            return f["precio"]

    if valor < filas[0]["desde"]:
        return filas[0]["precio"]

    ultimo = filas[-1]
    if valor > ultimo["hasta"]:
        return ultimo["precio"] + ((valor - ultimo["hasta"]) * to_decimal(adicional_por_unidad))

    # Cayo en un hueco interno: se cobra el escalon inmediato anterior, el mas
    # barato de los dos que lo rodean. La tabla con huecos no deberia haberse
    # publicado; validar_tarifa() la rechaza.
    previas = [f for f in filas if f["hasta"] < valor]
    return previas[-1]["precio"] if previas else filas[0]["precio"]


def volumen_m3(largo_cm, ancho_cm, alto_cm) -> Decimal:
    """Metros cubicos de la caja. Un millon de cm3 = 1 m3."""
    vol = _sano(largo_cm) * _sano(ancho_cm) * _sano(alto_cm)
    if vol <= 0:
        return ZERO
    try:
        return (vol / Decimal("1000000")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except InvalidOperation:  # pragma: no cover
        return ZERO


# ─── Sobrecargos, descuentos y temporada ──────────────────────────────────

# Las condiciones que el panel puede ofrecer. Son declarativas y viven en la
# base; el codigo solo sabe evaluarlas.
CONDICIONES_SOPORTADAS = (
    "suma_lados_cm_mayor_a",
    "valor_declarado_mayor_a",
    "peso_facturable_mayor_a",
    "lado_max_cm_mayor_a",
)


def _condicion_se_cumple(condicion, ctx) -> bool:
    """Evalua la condicion de un sobrecargo contra el contexto del paquete.

    Una clave desconocida NO activa el sobrecargo —cobrar de mas por un typo en
    el panel es peor que no cobrarlo— pero tampoco rompe la cotizacion.
    """
    if not condicion:
        return True
    campos = {
        "suma_lados_cm_mayor_a": "suma_lados_cm",
        "valor_declarado_mayor_a": "valor_declarado",
        "peso_facturable_mayor_a": "peso_facturable_kg",
        "lado_max_cm_mayor_a": "lado_mayor_cm",
    }
    for clave, valor in condicion.items():
        campo = campos.get(clave)
        if campo is None:
            return False
        if not (ctx.get(campo, ZERO) > to_decimal(valor)):
            return False
    return True


def calcular_sobrecargos(sobrecargos, base, ctx) -> list[dict]:
    """Devuelve los sobrecargos que aplican, ya valorizados.

    'base' es el precio del servicio antes de sobrecargos: es sobre eso que se
    calculan los porcentuales, nunca sobre un total que ya incluya otro
    sobrecargo. Que el orden de la lista no cambie el total es justamente lo que
    evita discusiones de "me cobraron el 2 % del 2 %".
    """
    aplicados = []
    for s in (sobrecargos or []):
        if not isinstance(s, dict) or not _activo(s):
            continue
        if not _condicion_se_cumple(s.get("condicion"), ctx):
            continue
        tipo = s.get("tipo")
        valor = to_decimal(s.get("valor"))
        if tipo == "fijo":
            monto = valor
        elif tipo == "porcentual":
            monto = to_decimal(base) * valor
        elif tipo == "por_kg":
            monto = ctx.get("peso_facturable_kg", ZERO) * valor
        else:
            continue
        aplicados.append({
            "codigo": s.get("codigo"),
            "nombre": s.get("nombre"),
            "tipo": tipo,
            "monto": quantize_money(monto),
        })
    return aplicados


def descuento_por_cantidad(descuentos, bultos: int) -> Decimal:
    """El mejor descuento aplicable para esa cantidad de bultos, como fraccion.

    Se toma el tramo mas alto que el envio alcanza, no la suma de todos: con
    3 -> 5 % y 6 -> 10 %, un envio de siete bultos lleva 10 %, no 15 %. Una fila
    sin 'desde_bultos' se descarta: valiendo 0 le aplicaria el descuento a todo
    el mundo, incluido el envio de un solo bulto.
    """
    mejor = ZERO
    try:
        n = int(bultos or 0)
    except (TypeError, ValueError):
        return ZERO
    for d in (descuentos or []):
        if not isinstance(d, dict) or d.get("desde_bultos") is None:
            continue
        try:
            desde = int(d["desde_bultos"])
        except (TypeError, ValueError):
            continue
        if desde >= 1 and n >= desde:
            mejor = max(mejor, to_decimal(d.get("descuento")))
    return mejor


def multiplicador_temporada(recargos, fecha) -> Decimal:
    """Multiplicador vigente en esa fecha, o 1 si no hay ninguno.

    Puede ser menor a 1: una temporada baja configurada al 0,85 tiene que
    aplicarse, no ignorarse. Si dos ventanas se solapan gana **la que empezo mas
    tarde** —la decision mas reciente— y no la mas cara: quedarse siempre con el
    multiplicador mayor convertia una promocion en letra muerta.

    Las fechas se comparan como texto ISO (YYYY-MM-DD), que ordena igual que el
    calendario.
    """
    if not fecha:
        return UNO
    dia = fecha if isinstance(fecha, str) else fecha.isoformat()[:10]

    vigentes = []
    for r in (recargos or []):
        if not isinstance(r, dict) or not _activo(r):
            continue
        desde, hasta = r.get("desde"), r.get("hasta")
        if desde and dia < str(desde):
            continue
        if hasta and dia > str(hasta):
            continue
        mult = to_decimal(r.get("multiplicador"))
        if mult <= 0:
            continue
        vigentes.append((str(desde or ""), mult))

    if not vigentes:
        return UNO
    vigentes.sort(key=lambda v: (v[0], v[1]))
    return vigentes[-1][1]


def _redondeo_final(monto, config) -> Decimal:
    """Redondeo comercial del total: a N decimales, y opcionalmente a multiplo."""
    config = config or {}
    valor = to_decimal(monto)

    multiplo = to_decimal(config.get("multiplo")) if config.get("multiplo") else ZERO
    if multiplo > 0:
        pasos = (valor / multiplo).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        valor = pasos * multiplo

    try:
        decimales = int(config.get("decimales", 2))
    except (TypeError, ValueError):
        decimales = 2
    if decimales < 0 or decimales > 6:
        decimales = 2
    return quantize_money(valor, decimales)


# ─── La cotizacion del servicio propio ────────────────────────────────────

def _bloque(tarifa, clave_nueva, clave_vieja):
    """Lee un bloque de la tarifa aceptando la forma nueva y la anidada vieja.

    Con `is not None` y no con `or`: un adicional_por_kg puesto en 0 a proposito
    ("lo que excede el ultimo escalon no se cobra aparte") es un valor, no una
    ausencia, y con `or` se caia silenciosamente al de la version anterior.
    """
    if tarifa.get(clave_nueva) is not None:
        return tarifa[clave_nueva]
    viejo = tarifa.get("servicio_traslado") or {}
    return viejo.get(clave_vieja)


def cotizar_servicio(tarifa, peso_real_kg, largo_cm, ancho_cm, alto_cm,
                     valor_declarado=0, bultos: int = 1, fecha=None) -> dict:
    """El unico numero que RIS App cobra: retiro, repesaje y traslado.

    NO recibe zona, ni destino, ni transportista, y eso es a proposito. El
    servicio termina siempre en el mismo mostrador de Santa Elena, asi que su
    precio es una funcion de una sola variable —el peso facturable— y no puede
    depender de a donde siga el paquete despues. Si algun dia esta firma pide una
    zona, algo se rompio en el modelo de negocio antes que en el codigo.

    El orden de las operaciones es parte del contrato y esta fijado aca:

        base            tabla de escalones (o la mayor de las dos tablas)
        + sobrecargos   los porcentuales, sobre la base y no entre si
        = subtotal
        + margen        sobre el subtotal
        - descuento     por cantidad de bultos, sobre el subtotal con margen
        x temporada     sobre el precio ya descontado
        piso            la tarifa minima, que nada baja
        redondeo        comercial

    Devuelve el desglose completo, no solo el total: es lo que la pantalla le
    muestra al usuario y lo que el simulador del panel compara contra la version
    vigente.
    """
    tarifa = tarifa or {}
    regla = tarifa.get("regla_peso") or {}
    modo = tarifa.get("modo_tarifa") or "peso"

    # En modo peso_o_volumen el volumen se cobra por su PROPIA tabla, asi que la
    # tabla de kilos tiene que trabajar sobre el peso real: si ademas cubicara,
    # el mismo volumen entraria dos veces y el "mayor de los dos" seria siempre
    # el cubado. Son dos maneras distintas de cobrar lo mismo, no dos cargos.
    regla_efectiva = dict(regla, divisor=0) if modo == "peso_o_volumen" else regla

    pf = peso_facturable(peso_real_kg, largo_cm, ancho_cm, alto_cm, regla_efectiva)
    pv = peso_volumetrico(largo_cm, ancho_cm, alto_cm, regla.get("divisor"))

    base = precio_por_escalon(pf,
                              _bloque(tarifa, "escalones_peso", "escalones"),
                              _bloque(tarifa, "adicional_por_kg", "adicional_por_kg"))

    base_volumen = ZERO
    if modo == "peso_o_volumen":
        m3 = volumen_m3(largo_cm, ancho_cm, alto_cm)
        base_volumen = precio_por_escalon(m3, tarifa.get("escalones_volumen"),
                                          tarifa.get("adicional_por_m3") or 0)
        base = max(base, base_volumen)

    ctx = {
        "peso_facturable_kg": pf,
        "suma_lados_cm": _sano(largo_cm) + _sano(ancho_cm) + _sano(alto_cm),
        "lado_mayor_cm": max(_sano(largo_cm), _sano(ancho_cm), _sano(alto_cm)),
        "valor_declarado": to_decimal(valor_declarado),
    }
    sobrecargos = calcular_sobrecargos(tarifa.get("sobrecargos"), base, ctx)
    total_sobrecargos = sum((s["monto"] for s in sobrecargos), ZERO)

    subtotal = to_decimal(base) + total_sobrecargos

    margen_cfg = tarifa.get("margen") or {}
    if margen_cfg.get("tipo") == "porcentual":
        margen = subtotal * to_decimal(margen_cfg.get("valor"))
    elif margen_cfg.get("tipo") == "fijo":
        margen = to_decimal(margen_cfg.get("valor"))
    else:
        margen = ZERO

    con_margen = subtotal + margen

    dto_pct = descuento_por_cantidad(tarifa.get("descuentos_cantidad"), bultos)
    descuento = con_margen * dto_pct

    mult = multiplicador_temporada(tarifa.get("recargos_temporada"), fecha)
    con_temporada = (con_margen - descuento) * mult

    minimo = to_decimal(tarifa.get("tarifa_minima"))
    redondeo = tarifa.get("redondeo_final")
    total = _redondeo_final(max(con_temporada, minimo), redondeo)
    # El redondeo a multiplo puede tirar el total por debajo del piso; el piso
    # gana, porque es el numero que se prometio que nadie baja de ahi.
    if minimo > ZERO and total < minimo:
        total = _redondeo_final(minimo, dict(redondeo or {}, multiplo=None))

    return {
        "version_id": tarifa.get("version_id"),
        "moneda": tarifa.get("moneda") or "RIS",
        "peso_real_kg": _sano(peso_real_kg).quantize(_PESO_EXP, rounding=ROUND_HALF_UP),
        "peso_volumetrico_kg": pv,
        "peso_facturable_kg": pf,
        "base": quantize_money(base),
        "base_volumen": quantize_money(base_volumen),
        "sobrecargos": sobrecargos,
        "total_sobrecargos": quantize_money(total_sobrecargos),
        "subtotal": quantize_money(subtotal),
        "margen": quantize_money(margen),
        "descuento_cantidad_pct": dto_pct,
        "descuento_cantidad": quantize_money(descuento),
        "multiplicador_temporada": mult,
        "aplico_tarifa_minima": minimo > ZERO and total <= minimo and con_temporada < minimo,
        "total": total,
    }


# ─── Validacion: lo que impide publicar una tarifa ────────────────────────

def validar_escalones(escalones, adicional_por_unidad=None, unidad: str = "kg") -> list[str]:
    """Los errores de una tabla de escalones. Lista vacia = se puede publicar.

    Son tres cosas distintas y las tres arruinan el dia:
      - Un HUECO deja un peso sin precio y la cotizacion cae al escalon anterior.
      - Un SOLAPAMIENTO hace que el precio dependa del orden de las filas.
      - Una tabla NO MONOTONA le paga al usuario por declarar mas peso.
    Se devuelven todos los errores juntos, no el primero: el que carga la tabla
    quiere ver de una vez todo lo que tiene que arreglar.
    """
    errores = []
    crudos = [e for e in (escalones or []) if isinstance(e, dict)]
    filas = _escalones_ordenados(escalones)

    descartadas = len(crudos) - len(filas)
    if descartadas > 0:
        errores.append(
            f"Hay {descartadas} fila(s) sin un 'hasta' válido: sin ese dato el escalón no "
            "se puede ubicar en la tabla."
        )
    if not filas:
        errores.append("La tabla de escalones no puede estar vacía.")
        return errores

    for i, f in enumerate(filas, start=1):
        if f["precio"] <= 0:
            errores.append(f"El escalón {i} tiene un precio de {f['precio']}; debe ser mayor a 0.")
        if f["hasta"] <= f["desde"]:
            errores.append(
                f"El escalón {i} termina en {f['hasta']} {unidad} y empieza en {f['desde']} "
                f"{unidad}: el final tiene que ser mayor que el inicio."
            )

    if filas[0]["desde"] > 0:
        errores.append(
            f"La tabla empieza en {filas[0]['desde']} {unidad}: los paquetes por debajo de "
            "eso no tienen precio."
        )

    # Hueco o solapamiento entre filas consecutivas. Se tolera una separacion de
    # hasta 0,01 porque asi se cargan las tablas a mano (…3,00 / 3,01…) y eso no
    # es un hueco real con escalones de 0,5 kg.
    tolerancia = Decimal("0.01")
    for a, b in zip(filas, filas[1:]):
        salto = b["desde"] - a["hasta"]
        if salto > tolerancia:
            errores.append(
                f"Hay un hueco entre {a['hasta']} {unidad} y {b['desde']} {unidad}: un "
                "paquete de ese tamaño no tendría precio propio."
            )
        elif salto < 0:
            errores.append(
                f"Los escalones se solapan entre {b['desde']} {unidad} y {a['hasta']} "
                f"{unidad}: el precio dependería del orden de las filas."
            )
        if b["precio"] < a["precio"]:
            errores.append(
                f"El escalón que termina en {b['hasta']} {unidad} ({b['precio']}) sale más "
                f"barato que el anterior ({a['precio']}): declarar más saldría menos."
            )

    if adicional_por_unidad is not None and to_decimal(adicional_por_unidad) <= 0:
        errores.append(
            f"El adicional por {unidad} tiene que ser mayor a 0: sin él, todo lo que exceda "
            "el último escalón viaja gratis."
        )

    return errores


# Cotas de cordura de los porcentajes. No son opiniones comerciales: son el
# rango dentro del cual un numero puede ser un porcentaje y no un error de
# tipeo. Un margen cargado como "20" en vez de "0.20" multiplica el precio por
# veintiuno, y sin esta validacion se publica sin que nada chille.
_MARGEN_PCT_MAX = Decimal("2")        # 200 %
_SOBRECARGO_PCT_MAX = Decimal("1")    # 100 %
_TEMPORADA_MIN = Decimal("0.5")
_TEMPORADA_MAX = Decimal("3")


def _valores_no_finitos(valor, camino: str = "la tarifa") -> list[tuple[str, object]]:
    """Los caminos que llevan a un NaN o a un Infinity, para poder nombrarlos."""
    if isinstance(valor, dict):
        salida = []
        for clave, sub in valor.items():
            salida += _valores_no_finitos(sub, f"{camino}.{clave}")
        return salida
    if isinstance(valor, (list, tuple)):
        salida = []
        for i, sub in enumerate(valor):
            salida += _valores_no_finitos(sub, f"{camino}[{i}]")
        return salida
    if isinstance(valor, float) and not isfinite(valor):
        return [(camino, valor)]
    if isinstance(valor, Decimal) and not valor.is_finite():
        return [(camino, str(valor))]
    if isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except (InvalidOperation, ValueError):
            return []
        return [] if d.is_finite() else [(camino, valor)]
    return []


def validar_tarifa(tarifa) -> list[str]:
    """Todo lo que impide publicar una version de tarifa. Lista vacia = adelante.

    Es la contracara del criterio de "ante la duda, cobrar de menos": el modulo
    de calculo es indulgente con los datos raros porque esta funcion los frena
    antes, en el editor, donde hay una persona mirando y todavia se puede
    arreglar.
    """
    tarifa = tarifa or {}

    # Los NO FINITOS primero y solos. Un "NaN" guardado en la base —lo escribio
    # una version vieja, una migracion o una mano— sale de to_decimal como un
    # Decimal valido, y `Decimal("NaN") < 0` no devuelve False: LANZA
    # InvalidOperation. O sea que el validador, que existe para que nada rompa
    # mas adelante, rompia el primero. No se sigue validando: con un valor asi
    # adentro cualquier comparacion posterior es una ruleta.
    #
    # No se arregla en money.to_decimal a proposito. Ahi un no finito tiene que
    # seguir llegando como no finito, porque services/envios_policy lo lee como
    # "limite roto = limite no declarado", y convertirlo en 0 haria que un peso
    # maximo roto pase a ser el limite mas chico de todos y no se pueda despachar
    # nada.
    no_finitos = _valores_no_finitos(tarifa)
    if no_finitos:
        return [f"{camino} no es un número finito ({valor!r}). Corregilo antes de "
                f"publicar: con eso adentro, cada cotización falla."
                for camino, valor in no_finitos[:12]]

    errores = list(validar_escalones(_bloque(tarifa, "escalones_peso", "escalones"),
                                     _bloque(tarifa, "adicional_por_kg", "adicional_por_kg"),
                                     "kg"))

    if (tarifa.get("modo_tarifa") or "peso") == "peso_o_volumen":
        errores += validar_escalones(tarifa.get("escalones_volumen"),
                                     tarifa.get("adicional_por_m3"), "m³")
        # Mismo criterio que la tabla de kilos: sin adicional, todo lo que excede
        # el ultimo escalon de m³ viaja gratis. validar_escalones no lo puede
        # decir por su cuenta porque un adicional ausente y uno en cero son
        # indistinguibles desde adentro.
        if tarifa.get("adicional_por_m3") is None:
            errores.append(
                "La tabla de volumen no tiene 'adicional_por_m3': todo lo que exceda el "
                "último escalón de m³ viajaría gratis."
            )

    regla = tarifa.get("regla_peso") or {}
    if to_decimal(regla.get("divisor")) <= 0 and (tarifa.get("modo_tarifa") or "peso") == "peso":
        errores.append(
            "La regla de peso no tiene divisor volumétrico: los bultos grandes y livianos "
            "cotizarían solo por su peso real."
        )

    # El minimo y el escalon de la regla de peso se validan CONTRA LA TABLA, no
    # contra un rango abstracto: un minimo_kg de 1000 con una tabla que llega a
    # 30 kg no es un numero fuera de rango, es una caja de 1 kg cobrada como si
    # pesara una tonelada. Es el mismo error de tipeo que el margen "20" en vez
    # de "0.20", una celda mas a la derecha, y sin esto se publica sin que nada
    # chille.
    _filas = _escalones_ordenados(_bloque(tarifa, "escalones_peso", "escalones"))
    if _filas:
        tope = _filas[-1]["hasta"]
        for clave, comodin in (("minimo_kg", "mínimo facturable"),
                               ("escalon_kg", "escalón de redondeo de peso")):
            if regla.get(clave) is None:
                continue
            valor = to_decimal(regla.get(clave))
            if valor > tope:
                errores.append(
                    f"El {comodin} de la regla de peso es {valor} kg y la tabla termina en "
                    f"{tope} kg: cualquier paquete saldría del último escalón. Suele ser un "
                    f"cero de más."
                )

    margen = tarifa.get("margen") or {}
    if margen.get("tipo") == "porcentual":
        v = to_decimal(margen.get("valor"))
        if v < 0 or v > _MARGEN_PCT_MAX:
            errores.append(
                f"El margen porcentual es {v}. Se escribe como fracción: 0.20 es 20 %. "
                f"El máximo admitido es {_MARGEN_PCT_MAX}."
            )
    elif margen.get("tipo") == "fijo":
        if to_decimal(margen.get("valor")) < 0:
            errores.append("El margen fijo no puede ser negativo.")
    elif margen.get("tipo") is not None:
        errores.append(f"Tipo de margen desconocido: {margen.get('tipo')!r}.")

    for s in (tarifa.get("sobrecargos") or []):
        if not isinstance(s, dict):
            continue
        codigo = s.get("codigo") or "sin código"
        tipo, valor = s.get("tipo"), to_decimal(s.get("valor"))
        if tipo not in ("fijo", "porcentual", "por_kg"):
            errores.append(f"El sobrecargo {codigo} tiene un tipo desconocido: {tipo!r}.")
        elif valor < 0:
            errores.append(f"El sobrecargo {codigo} tiene un valor negativo.")
        elif tipo == "porcentual" and valor > _SOBRECARGO_PCT_MAX:
            errores.append(
                f"El sobrecargo {codigo} es {valor}: se escribe como fracción (0.02 es 2 %)."
            )
        for clave in (s.get("condicion") or {}):
            if clave not in CONDICIONES_SOPORTADAS:
                errores.append(
                    f"El sobrecargo {codigo} tiene una condición que el sistema no sabe "
                    f"evaluar ({clave}), así que nunca se aplicaría."
                )

    for d in (tarifa.get("descuentos_cantidad") or []):
        if not isinstance(d, dict):
            continue
        if d.get("desde_bultos") is None:
            errores.append("Hay un descuento por cantidad sin 'desde_bultos'.")
            continue
        pct = to_decimal(d.get("descuento"))
        if pct <= 0 or pct >= 1:
            errores.append(
                f"El descuento desde {d['desde_bultos']} bultos es {pct}: se escribe como "
                "fracción entre 0 y 1."
            )

    for r in (tarifa.get("recargos_temporada") or []):
        if not isinstance(r, dict):
            continue
        nombre = r.get("nombre") or "sin nombre"
        mult = to_decimal(r.get("multiplicador"))
        if mult < _TEMPORADA_MIN or mult > _TEMPORADA_MAX:
            errores.append(
                f"La temporada {nombre} tiene un multiplicador de {mult}; se admite entre "
                f"{_TEMPORADA_MIN} y {_TEMPORADA_MAX}."
            )
        if r.get("desde") and r.get("hasta") and str(r["desde"]) > str(r["hasta"]):
            errores.append(f"La temporada {nombre} termina antes de empezar.")

    minimo = to_decimal(tarifa.get("tarifa_minima"))
    if minimo < 0:
        errores.append("La tarifa mínima no puede ser negativa.")

    redondeo = tarifa.get("redondeo_final") or {}
    if redondeo.get("multiplo") is not None:
        m = to_decimal(redondeo.get("multiplo"))
        filas = _escalones_ordenados(_bloque(tarifa, "escalones_peso", "escalones"))
        mas_barato = min((f["precio"] for f in filas), default=ZERO)
        if m <= 0:
            errores.append("El múltiplo de redondeo tiene que ser mayor a 0.")
        elif mas_barato > 0 and m > mas_barato / Decimal("10"):
            errores.append(
                f"El múltiplo de redondeo ({m}) es grande frente al escalón más barato "
                f"({mas_barato}): movería el precio más de lo que nadie querría redondear."
            )

    return errores
