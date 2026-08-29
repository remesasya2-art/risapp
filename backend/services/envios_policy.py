"""
services/envios_policy.py — Que se puede enviar, y de que tamano.

POR QUE EXISTE ESTE MODULO
    Hay dos formas de que un envio termine mal, y las dos se evitan en el
    formulario o no se evitan nunca:

    1. El paquete no entra en las reglas de alguno de los transportistas. El
       usuario cotiza, paga, despacha... y en el mostrador le dicen que no. La
       plata ya se debito y el paquete esta en la calle.
    2. El contenido no se puede trasladar. Se descubre en Pacaraima, con el
       paquete ya del otro lado, y ahi no hay solucion barata.

    Las dos barreras van ANTES de cotizar.

LOS LIMITES NO SON UNA CONSTANTE
    Son la INTERSECCION de los transportistas habilitados: el mas estricto gana.
    Se calculan en tiempo de ejecucion a partir de los transportistas activos,
    que se cargan desde el panel. La consecuencia practica es que el dia que se
    habilite una empresa mas restrictiva, el formulario se ajusta solo — nadie
    tiene que acordarse de tocar un numero en el codigo.

    Y hay minimos, no solo maximos. Es el error facil de omitir: se valida que la
    caja no sea demasiado grande y nadie valida que no sea demasiado chica. Un
    sobre por debajo del minimo cotiza bien, se paga, y despues no se despacha.

ESTADO (PR A)
    Modulo PURO y AISLADO: sin Mongo, sin red, sin framework. Recibe la lista de
    transportistas ya leida y devuelve numeros o mensajes. Ninguna ruta lo llama
    todavia.

SOBRE LA LISTA DE PROHIBIDOS
    La de aca abajo es la SEMILLA, no la fuente de verdad. La lista que se aplica
    vive en la configuracion y se edita desde el panel, porque cambia con un
    criterio de aduana y no puede depender de un deploy. Esta constante sirve
    para poblarla la primera vez y como red si la configuracion viniera vacia.

    Los mensajes de error se devuelven, no se lanzan — mismo criterio que
    services/limits.py: el que llama decide si eso es un 400, un toast o un
    cartel rojo.
"""

from decimal import Decimal

from services.money import to_decimal

TERMINOS_VERSION = "envios-v1"

ZERO = Decimal("0")

# Techo de cordura, independiente de lo que este cargado en el panel. Un sistema
# sin transportistas todavia tiene que rechazar un peso de 1e40: sin esto, ese
# valor pasa la validacion y revienta mas adelante, en el calculo, con un 500 en
# la cara del usuario en vez de un mensaje.
PESO_ABSURDO_KG = Decimal("1000")
LADO_ABSURDO_CM = Decimal("1000")
VALOR_ABSURDO = Decimal("1000000")

_TEXTOS_FALSOS = {"false", "no", "0", "off", "", "none", "null"}


def _activo(fila) -> bool:
    """Un transportista esta activo salvo que diga que no.

    Mismo criterio que services/envios_tarifas.py, y por la misma razon: del
    panel un checkbox puede llegar como False, 0 o el texto "false", y
    `bool("false")` es True.
    """
    valor = (fila or {}).get("activo", True)
    if isinstance(valor, str):
        return valor.strip().lower() not in _TEXTOS_FALSOS
    return bool(valor)

# ─── Contenido ────────────────────────────────────────────────────────────

CATEGORIAS_PROHIBIDAS_POR_DEFECTO = [
    "armas, municiones y sus partes",
    "explosivos, inflamables, corrosivos y gases comprimidos",
    "sustancias controladas y medicamentos sin receta",
    "dinero en efectivo, cheques al portador y metales preciosos",
    "animales vivos y material biológico",
    "productos perecederos que requieran cadena de frío",
    "maquinaria y equipos de uso industrial",
]

# Por que la maquinaria industrial esta fuera y no es un capricho comercial:
#   - Excede el peso y las dimensiones que aceptan los transportistas.
#   - No entra en un vehiculo de reparto ni la mueve una persona sola.
#   - Cambia el regimen aduanero: deja de ser encomienda personal y pasa a
#     importacion comercial, con documentacion que este servicio no tramita.
# Por eso se rechaza en el formulario, antes de cotizar, y no en el mostrador.

DESCRIPCION_MIN_CARACTERES = 10


def validar_descripcion(descripcion) -> str | None:
    """La descripcion de contenido es obligatoria y tiene que decir algo.

    Diez caracteres no hacen que una descripcion sea buena, pero descartan la
    mitad de las que no son descripciones: "cosas", "ropa", un punto.
    """
    texto = (descripcion or "").strip()
    if len(texto) < DESCRIPCION_MIN_CARACTERES:
        return (
            f"Describí el contenido con al menos {DESCRIPCION_MIN_CARACTERES} caracteres. "
            "Es lo que se declara ante la aduana."
        )
    return None


# ─── Limites fisicos: la interseccion ─────────────────────────────────────

# Los maximos se intersecan tomando el MENOR de los declarados; los minimos, el
# MAYOR. En ambos casos gana el transportista mas estricto.
_MAXIMOS = ("peso_max_kg", "lado_max_cm", "suma_lados_max_cm", "valor_declarado_max")
_MINIMOS = ("largo_min_cm", "ancho_min_cm", "alto_min_cm", "suma_lados_min_cm")


def _limite_utilizable(valor) -> Decimal | None:
    """Un límite que se puede comparar, o None.

    NaN e infinito no son límites: comparar un Decimal NaN LANZA —a diferencia
    del float, que devuelve False en silencio— así que una ficha con un valor
    roto tumbaba la intersección entera y con ella la ruta pública. Un dato que
    no se puede comparar es un límite que no está declarado.
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, str):
        # to_decimal es tolerante a propósito y devuelve 0 ante basura. Acá un 0
        # es peor que nada: sería un límite de cero kilos que rechaza todo.
        try:
            d = Decimal(valor.strip().replace(",", "."))
        except Exception:
            return None
    else:
        try:
            d = to_decimal(valor)
        except Exception:
            return None
    return d if d.is_finite() else None


def limites_efectivos(transportistas, limites_propios=None) -> dict:
    """Interseca los limites de los transportistas activos con los propios.

    Un transportista que no declara un limite no lo restringe: si ninguno declara
    peso maximo, el resultado no tiene peso maximo y el formulario no lo valida.
    Es preferible a inventar un techo que despues nadie puede explicar.

    'limites_propios' son los del vehiculo de RIS App, que viven en la version de
    tarifa. Entran en la interseccion como uno mas.

    Los transportistas DESACTIVADOS no restringen nada: un limite que sobrevive
    a la baja de la empresa que lo imponia es un limite que nadie puede explicar
    ni encontrar en el panel.
    """
    fuentes = [t.get("limites") or {} for t in (transportistas or []) if _activo(t)]
    if limites_propios:
        fuentes.append(limites_propios)

    efectivos: dict = {}
    for clave in _MAXIMOS:
        valores = [v for v in (_limite_utilizable(f.get(clave)) for f in fuentes)
                   if v is not None]
        if valores:
            efectivos[clave] = min(valores)
    for clave in _MINIMOS:
        valores = [v for v in (_limite_utilizable(f.get(clave)) for f in fuentes)
                   if v is not None]
        if valores:
            efectivos[clave] = max(valores)
    return efectivos


def _codigo(t) -> str:
    """Como se nombra a un transportista en un mensaje: por su codigo.

    Nunca por su nombre comercial. El nombre lo pone la pantalla si quiere, a
    partir del catalogo; el codigo es lo unico que este modulo conoce.
    """
    return (t or {}).get("codigo") or (t or {}).get("transportista_id") or "?"


def quien_impone(transportistas, clave, limites_propios=None) -> str | None:
    """Codigo del transportista que impone ese limite. Sirve para el mensaje.

    "No se despachan paquetes de mas de 100 cm de lado" es una regla anonima que
    el usuario no puede verificar; con el codigo, soporte sabe a quien mirar.
    """
    fuentes = [(_codigo(t), (t.get("limites") or {}))
               for t in (transportistas or []) if _activo(t)]
    if limites_propios:
        fuentes.append(("propio", limites_propios))
    candidatos = [(c, v) for c, v in
                  ((c, _limite_utilizable(l.get(clave))) for c, l in fuentes)
                  if v is not None]
    if not candidatos:
        return None
    if clave in _MAXIMOS:
        return min(candidatos, key=lambda x: x[1])[0]
    return max(candidatos, key=lambda x: x[1])[0]


def _fmt(valor) -> str:
    """Numero como lo lee una persona: sin ceros de mas, con coma decimal."""
    d = to_decimal(valor).normalize()
    texto = format(d, "f")
    return texto.replace(".", ",")


def validar_paquete(peso_kg, largo_cm, ancho_cm, alto_cm, valor_declarado=0,
                    limites=None) -> str | None:
    """Mensaje de error, o None si el paquete se puede despachar.

    Se valida contra la INTERSECCION que devuelve limites_efectivos(), nunca
    contra un solo transportista. No lanza: devuelve el primer problema, que es
    el que el usuario tiene que arreglar antes de ver el siguiente.
    """
    # Los limites se convierten aca y no se asumen ya convertidos: la firma
    # invita a pasarle el dict del panel o los limites propios de la tarifa
    # directamente, y comparar un Decimal contra el string "30" lanza TypeError.
    limites = {k: to_decimal(v) for k, v in (limites or {}).items() if v is not None}

    valores = {"peso": peso_kg, "largo": largo_cm, "ancho": ancho_cm, "alto": alto_cm}
    convertidos = {}
    for nombre, bruto in valores.items():
        try:
            d = to_decimal(bruto)
        except Exception:  # pragma: no cover — to_decimal ya es tolerante
            d = ZERO
        if d <= 0:
            return f"El {nombre} tiene que ser un número mayor a 0."
        convertidos[nombre] = d

    peso = convertidos["peso"]
    largo, ancho, alto = convertidos["largo"], convertidos["ancho"], convertidos["alto"]

    # Antes que cualquier limite configurable: lo que directamente no puede ser
    # una medida. Vale incluso con el panel vacio.
    if peso > PESO_ABSURDO_KG:
        return "El peso que cargaste no parece un peso real. Revisá la unidad: son kilos."
    if max(largo, ancho, alto) > LADO_ABSURDO_CM:
        return "Las medidas no parecen medidas reales. Revisá la unidad: son centímetros."
    if to_decimal(valor_declarado) > VALOR_ABSURDO:
        return "El valor declarado que cargaste no parece un valor real."

    suma = largo + ancho + alto
    lado_mayor = max(largo, ancho, alto)
    valor = to_decimal(valor_declarado)

    if limites.get("peso_max_kg") is not None and peso > limites["peso_max_kg"]:
        return f"El peso máximo por paquete es {_fmt(limites['peso_max_kg'])} kg."

    if limites.get("lado_max_cm") is not None and lado_mayor > limites["lado_max_cm"]:
        return (
            f"Ningún lado puede superar los {_fmt(limites['lado_max_cm'])} cm "
            f"(el mayor de los que cargaste mide {_fmt(lado_mayor)} cm)."
        )

    if limites.get("suma_lados_max_cm") is not None and suma > limites["suma_lados_max_cm"]:
        return (
            f"La suma de largo + ancho + alto no puede superar los "
            f"{_fmt(limites['suma_lados_max_cm'])} cm (la tuya da {_fmt(suma)} cm)."
        )

    # Los minimos, que son los que se olvidan.
    for clave, medida, etiqueta in (("largo_min_cm", largo, "largo"),
                                    ("ancho_min_cm", ancho, "ancho"),
                                    ("alto_min_cm", alto, "alto")):
        if limites.get(clave) is not None and medida < limites[clave]:
            return (
                f"El {etiqueta} mínimo es {_fmt(limites[clave])} cm. "
                "Un paquete más chico que eso no se despacha."
            )

    if limites.get("suma_lados_min_cm") is not None and suma < limites["suma_lados_min_cm"]:
        return (
            f"La suma de los tres lados tiene que llegar a "
            f"{_fmt(limites['suma_lados_min_cm'])} cm."
        )

    if limites.get("valor_declarado_max") is not None and valor > limites["valor_declarado_max"]:
        return (
            f"El valor declarado máximo es {_fmt(limites['valor_declarado_max'])}. "
            "Por encima de eso hace falta otro tipo de envío."
        )
    if valor < 0:
        return "El valor declarado no puede ser negativo."

    return None


def limites_payload(limites) -> dict:
    """La forma que consume la pantalla, con floats y sin claves ausentes.

    Existe por el bug del PR #40: la pantalla tenia los limites escritos adentro
    y anunciaba techos que el servidor no validaba. Ahora los lee de acá, y si un
    limite no existe viaja como null para que la pantalla sepa que ahi no hay
    nada que mostrar.
    """
    limites = limites or {}
    claves = _MAXIMOS + _MINIMOS
    return {c: (float(limites[c]) if limites.get(c) is not None else None) for c in claves}


def configuracion_incompleta(transportistas, tarifa_vigente) -> list[str]:
    """Que le falta al sistema para poder cotizar. Lista vacia = puede operar.

    El panel lo muestra en su portada. Sin esto, la primera senal de que falta
    cargar algo es una cotizacion que devuelve 500 en la cara de un usuario.
    """
    faltan = []
    activos = [t for t in (transportistas or []) if _activo(t)]
    if not any(t.get("rol") == "brasil" for t in activos):
        faltan.append("No hay ningún transportista activo con rol Brasil.")
    if not any(t.get("rol") == "venezuela" for t in activos):
        faltan.append("No hay ningún transportista activo con rol Venezuela.")
    if not tarifa_vigente:
        faltan.append("No hay una versión de tarifa vigente para el servicio propio.")
    else:
        if not (tarifa_vigente.get("escalones_peso") or
                (tarifa_vigente.get("servicio_traslado") or {}).get("escalones")):
            faltan.append("La tarifa vigente no tiene tabla de escalones cargada.")
        if not (tarifa_vigente.get("regla_peso") or {}).get("divisor"):
            faltan.append(
                "La tarifa vigente no tiene regla de peso con divisor volumétrico: los "
                "bultos grandes y livianos cotizarían solo por su peso real."
            )
    return faltan
