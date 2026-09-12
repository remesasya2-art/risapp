"""
services/configuracion.py — Los números que se cambian desde el panel.

POR QUE EXISTE

    La regla del proyecto es que configurar nunca pueda requerir editar código
    en GitHub. Hoy no se cumple: el monto del bono, el mínimo y el máximo de
    PIX (`services/limits.py`) y el cupo de la cuenta sin verificar
    (`services/kyc_quota.py`) están escritos a mano en archivos .py. Cambiar
    cualquiera de esos números es un commit, un despliegue y un rato de espera.

    Este módulo es el lugar donde van esos números. Empieza con los del bono
    de referidos, que es el trabajo en curso, y está hecho para que agregar el
    siguiente sea UNA LINEA y nada más.

POR QUE UN CATALOGO Y NO UNA FUNCION POR AJUSTE

    Cada ajuste se declara en `AJUSTES` con su tipo, su valor por omisión, su
    rango y su texto. De ahí sale todo lo demás:

      · la validación, que no se repite en la ruta;
      · lo que devuelve el API;
      · Y LA PANTALLA, que se dibuja a partir de lo que el API le manda.

    Ese último punto es el que importa. La pantalla no sabe qué ajustes
    existen: los pide y los dibuja. Así que agregar el mínimo de PIX acá es
    una entrada en este diccionario, sin tocar el frontend, sin una ruta nueva
    y sin un despliegue del bundle.

    La alternativa —una ruta y un campo por cada cosa— es la que llevó a que
    `routes/btc_admin.py` tenga sus propios `_read_config_value` y
    `_write_config_value` privados, y a que la pantalla de BTC repita la
    validación de cada número en JavaScript. Dos copias de la misma regla.

UN AJUSTE DESCONOCIDO SE RECHAZA, NO SE IGNORA

    Es la lección del enlace de referido, que nunca funcionó porque la
    pantalla mandaba `referral_code`, el servidor esperaba `referred_by` y
    Pydantic descartó el campo en silencio durante meses.

    Acá, mandar una clave que no está en `AJUSTES` es un error con nombre. Si
    alguien renombra un ajuste y se olvida de la pantalla, se entera en el
    primer intento de guardar, no seis meses después mirando por qué el bono
    sigue en quince.

LA PLATA, CON LAS TRES REGLAS DEL PROYECTO

    · En el borde del API, STRINGS. `{"bono_al_referido": "15.00"}`. Un JSON
      con 15.1 adentro ya perdió precisión antes de que el servidor lo lea.
    · Al guardar, DECIMAL128. Igual que los saldos.
    · Adentro, DECIMAL. Nunca `float`.

    Y una trampa que hay que esquivar a mano: `money.to_decimal` está escrito
    para ser tolerante —un valor inválido devuelve `Decimal('0')` en vez de
    levantar— porque leer un saldo viejo y raro no puede tirar abajo una
    pantalla. Pero acá eso sería un desastre: escribir «abc» en el campo del
    bono guardaría CERO sin que nadie se entere, y lo mismo «15,50» con coma,
    que es como se escribe un monto en Brasil.

    Por eso `_a_dinero` parsea ESTRICTO y devuelve el error, y la coma se
    normaliza antes. La tolerancia de `to_decimal` sirve para leer; para
    escribir hace falta lo contrario.

POR QUE NO HAY CACHE

    Se leen de a puñados y en momentos que no son calientes: al mostrar la
    pantalla del panel, al acreditar un bono. Una consulta a Mongo cuesta
    menos que un valor viejo servido después de guardar, que es el defecto que
    nadie encuentra porque «yo lo cambié y no pasó nada».
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from services.money import from_db, quantize_money, to_decimal128

logger = logging.getLogger(__name__)

COLECCION = "config"

# Los dos tipos que hay. No hace falta un tercero todavía, y un tipo que no se
# usa es una rama sin probar.
DINERO = "dinero"
ENTERO = "entero"


class Ajuste:
    """Un número configurable, con todo lo que hace falta para validarlo y
    para dibujarlo en la pantalla.

    `minimo` y `maximo` no son adorno. El bono se paga solo, a cada cuenta que
    se registra: un cero de más al tipear —1500 en vez de 150— es plata que
    sale sin que nadie lo apruebe. El tope es la red.
    """

    def __init__(self, *, tipo, defecto, minimo, maximo, etiqueta, ayuda,
                 unidad=""):
        self.tipo = tipo
        self.defecto = defecto
        self.minimo = minimo
        self.maximo = maximo
        self.etiqueta = etiqueta
        self.ayuda = ayuda
        self.unidad = unidad


# ─── El catálogo ──────────────────────────────────────────────────────────
#
# Agregar uno es agregar una entrada acá. La pantalla lo dibuja sola.
AJUSTES = {
    "bono_al_referido": Ajuste(
        tipo=DINERO, defecto="15.00", minimo="0", maximo="500",
        unidad="R$",
        etiqueta="Bono para quien se registra con un código",
        ayuda="Se acredita bloqueado y se libera cuando la cuenta aprueba su "
              "verificación de identidad. Sólo se puede gastar en envíos a "
              "Venezuela."),

    "bono_a_quien_refiere": Ajuste(
        tipo=DINERO, defecto="5.00", minimo="0", maximo="500",
        unidad="R$",
        etiqueta="Bono para el dueño del código",
        ayuda="Se paga libre, cuando la cuenta que usó su código aprueba su "
              "verificación de identidad."),

    "referidos_que_pagan_con_solo_kyc": Ajuste(
        tipo=ENTERO, defecto=10, minimo=0, maximo=10000,
        unidad="cuentas",
        etiqueta="Cuántas cuentas pagan con sólo la verificación",
        ayuda="Hasta este número de cuentas referidas, el dueño del código "
              "cobra en cuanto la cuenta aprueba su verificación. De ahí en "
              "adelante hace falta además que esa cuenta haga su primer "
              "envío."),
}


class AjusteDesconocido(KeyError):
    """Una clave que no está en `AJUSTES`.

    Tiene su propia excepción —en vez de devolver `None`— porque el silencio
    es exactamente lo que se está evitando acá.
    """

    def __init__(self, clave):
        self.clave = clave
        super().__init__(clave)


def _a_dinero(escrito):
    """`(Decimal, None)` si es un monto, `(None, motivo)` si no.

    Estricto a propósito. `money.to_decimal` devolvería `Decimal('0')` para
    «abc» y para «15,50», y guardar un bono de cero porque alguien escribió el
    monto con coma es la clase de error que se descubre cuando un cliente
    pregunta por qué no le llegó nada.
    """
    if isinstance(escrito, bool):
        # `bool` es subclase de `int` en Python, así que `True` pasaría como 1.
        return None, "no es un número"
    if isinstance(escrito, (int, Decimal)):
        return quantize_money(escrito), None
    if isinstance(escrito, float):
        # Se acepta, pero por `str` y no por el binario: 15.1 en float es
        # 15.0999999999999996447286321199499070644378662109375.
        escrito = repr(escrito)
    if not isinstance(escrito, str):
        return None, "no es un número"

    limpio = escrito.strip().replace(" ", "")
    # La coma decimal, que es como se escribe un monto en Brasil y en
    # Venezuela. Sin esto, «15,50» se guardaría como cero.
    limpio = limpio.replace(",", ".")
    if not limpio:
        return None, "está vacío"
    try:
        valor = Decimal(limpio)
    except (InvalidOperation, ValueError):
        return None, "no es un número"
    if not valor.is_finite():
        return None, "no es un número"
    return quantize_money(valor), None


def _a_entero(escrito):
    """`(int, None)` o `(None, motivo)`. Igual de estricto que el de arriba."""
    if isinstance(escrito, bool):
        return None, "no es un número entero"
    if isinstance(escrito, int):
        return escrito, None
    if isinstance(escrito, str):
        limpio = escrito.strip()
        if not limpio:
            return None, "está vacío"
        try:
            return int(limpio), None
        except ValueError:
            return None, "no es un número entero"
    if isinstance(escrito, (float, Decimal)):
        valor = Decimal(str(escrito))
        if valor != valor.to_integral_value():
            return None, "tiene decimales y tiene que ser un número entero"
        return int(valor), None
    return None, "no es un número entero"


def normalizar(clave: str, escrito):
    """Lo que escribió la persona, listo para guardar. O el motivo del rechazo.

    Devuelve `(valor, None)` o `(None, mensaje)`. No levanta: la ruta decide
    si eso es un 400 o un cartel, igual que hace `services/limits.py`.
    """
    ajuste = AJUSTES.get(clave)
    if ajuste is None:
        raise AjusteDesconocido(clave)

    if ajuste.tipo == DINERO:
        valor, motivo = _a_dinero(escrito)
        piso, techo = quantize_money(ajuste.minimo), quantize_money(ajuste.maximo)
    else:
        valor, motivo = _a_entero(escrito)
        piso, techo = ajuste.minimo, ajuste.maximo

    if motivo:
        return None, f"«{ajuste.etiqueta}»: {motivo}."
    if valor < piso:
        return None, (f"«{ajuste.etiqueta}»: no puede ser menos de "
                      f"{_mostrar(ajuste, piso)}.")
    if valor > techo:
        return None, (f"«{ajuste.etiqueta}»: no puede ser más de "
                      f"{_mostrar(ajuste, techo)}. El tope está puesto para "
                      "que un cero de más al tipear no salga solo.")
    return valor, None


def _mostrar(ajuste, valor) -> str:
    unidad = f" {ajuste.unidad}" if ajuste.unidad else ""
    return f"{valor}{unidad}"


def para_el_borde(ajuste, valor):
    """El valor como viaja por el API: la plata en texto, el resto entero.

    En texto porque un JSON con `15.1` adentro ya perdió precisión antes de
    que el servidor lo lea. Es la misma regla que usan los montos de las
    operaciones en este proyecto.
    """
    return str(valor) if ajuste.tipo == DINERO else int(valor)


async def leer(db, clave: str):
    """El valor de un ajuste: `Decimal` si es plata, `int` si es un contador.

    Si no se guardó nunca, el valor por omisión del catálogo. Y si lo que hay
    guardado no se puede leer, TAMBIEN el valor por omisión, con un ERROR en
    el registro: un ajuste ilegible no puede dejar sin bono a todo el mundo.
    """
    ajuste = AJUSTES.get(clave)
    if ajuste is None:
        raise AjusteDesconocido(clave)

    doc = await db[COLECCION].find_one({"clave": clave}, {"_id": 0, "valor": 1})
    if not doc or doc.get("valor") is None:
        return _defecto(ajuste)

    if ajuste.tipo == DINERO:
        # `from_db` y no `to_decimal`: lee Decimal128, float y texto por igual,
        # que es lo que hace falta para datos que ya están guardados.
        return from_db(doc["valor"])
    valor, motivo = _a_entero(doc["valor"])
    if motivo:
        logger.error("configuracion: %r guardado con un valor ilegible (%r); "
                     "se usa el de fábrica", clave, doc["valor"])
        return _defecto(ajuste)
    return valor


def _defecto(ajuste):
    return (quantize_money(ajuste.defecto) if ajuste.tipo == DINERO
            else int(ajuste.defecto))


async def leer_todo(db) -> dict:
    """Todos los ajustes. Una sola consulta, no una por clave."""
    guardados = {}
    async for doc in db[COLECCION].find(
            {"clave": {"$in": list(AJUSTES)}}, {"_id": 0, "clave": 1, "valor": 1}):
        guardados[doc.get("clave")] = doc.get("valor")

    salida = {}
    for clave, ajuste in AJUSTES.items():
        crudo = guardados.get(clave)
        if crudo is None:
            salida[clave] = _defecto(ajuste)
            continue
        if ajuste.tipo == DINERO:
            salida[clave] = from_db(crudo)
        else:
            valor, motivo = _a_entero(crudo)
            if motivo:
                logger.error("configuracion: %r guardado con un valor "
                             "ilegible (%r); se usa el de fábrica", clave, crudo)
                valor = _defecto(ajuste)
            salida[clave] = valor
    return salida


async def escribir(db, clave: str, valor) -> None:
    """Guarda un ajuste YA NORMALIZADO por `normalizar`.

    La plata va en `Decimal128`, igual que los saldos. No se acepta el texto
    crudo de la pantalla: quien llama tiene que haber pasado por `normalizar`,
    porque ahí está la validación y el rango.
    """
    ajuste = AJUSTES.get(clave)
    if ajuste is None:
        raise AjusteDesconocido(clave)

    guardado = to_decimal128(valor) if ajuste.tipo == DINERO else int(valor)
    await db[COLECCION].update_one(
        {"clave": clave},
        {"$set": {"clave": clave, "valor": guardado,
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def catalogo_para_la_pantalla() -> list:
    """El catálogo como lo necesita la pantalla, que se dibuja con esto.

    El orden es el de `AJUSTES`, y por eso el diccionario está escrito en el
    orden en que se quieren ver los campos.
    """
    return [
        {
            "clave": clave,
            "tipo": a.tipo,
            "etiqueta": a.etiqueta,
            "ayuda": a.ayuda,
            "unidad": a.unidad,
            "minimo": para_el_borde(a, quantize_money(a.minimo)
                                    if a.tipo == DINERO else a.minimo),
            "maximo": para_el_borde(a, quantize_money(a.maximo)
                                    if a.tipo == DINERO else a.maximo),
            "defecto": para_el_borde(a, _defecto(a)),
        }
        for clave, a in AJUSTES.items()
    ]
