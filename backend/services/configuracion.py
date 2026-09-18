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

from bson import Decimal128

from services.money import quantize_money, to_decimal128

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

    "minimo_del_primer_envio": Ajuste(
        tipo=DINERO, defecto="100.00", minimo="0", maximo="5000",
        unidad="R$",
        etiqueta="Envío mínimo que cuenta como «primer envío»",
        ayuda="A partir de la cuenta número que diga el ajuste de abajo, el "
              "dueño del código cobra recién cuando la cuenta referida hace un "
              "envío a Venezuela de al menos este monto. Sin un mínimo, un "
              "envío de diez reales alcanzaría para cobrar el bono, y la "
              "condición no protegería nada."),

    "referidos_que_pagan_con_solo_kyc": Ajuste(
        tipo=ENTERO, defecto=10, minimo=0, maximo=10000,
        unidad="cuentas",
        etiqueta="Cuántas cuentas pagan con sólo la verificación",
        ayuda="Hasta este número de cuentas referidas, el dueño del código "
              "cobra en cuanto la cuenta aprueba su verificación. De ahí en "
              "adelante hace falta además que esa cuenta haga su primer "
              "envío."),

    # ── Cuántas operaciones de dinero seguidas ─────────────────────────────
    #
    # No es cuánta plata: es cuántas VECES. Un pedido de retiro, un envío,
    # una recarga, un cobro PIX, cada uno cuenta uno. Son los frenos de
    # `routes/dependencies.py::sin_transacciones_personales`, la única puerta
    # por la que pasan todas las rutas que mueven plata.
    #
    # Antes no había ninguno: una cuenta con sesión podía crear pedidos de
    # retiro sin parar. Y los límites de la aplicación eran todos por IP, que
    # para quien ya tiene sesión y cambia de red es no tener límite.
    "dinero_operaciones_por_cuenta_por_hora": Ajuste(
        tipo=ENTERO, defecto=30, minimo=1, maximo=10000,
        unidad="por hora",
        etiqueta="Operaciones de dinero por cuenta, por hora",
        ayuda="Cuántas veces una misma cuenta puede pedir un retiro, un envío, "
              "una recarga o un cobro en una hora, sumando todas. Al pasarse "
              "recibe «Hiciste demasiadas operaciones seguidas». Treinta es "
              "holgado para una persona y corta a un programa."),

    "dinero_operaciones_por_ip_por_hora": Ajuste(
        tipo=ENTERO, defecto=120, minimo=1, maximo=100000,
        unidad="por hora",
        etiqueta="Operaciones de dinero por conexión (IP), por hora",
        ayuda="Lo mismo, pero por la conexión desde la que se pide, sin importar "
              "la cuenta. Va bastante más alto que el de cuenta porque detrás de "
              "una misma IP puede haber una oficina o un wifi compartido: a ellos "
              "no hay que frenarlos, a un programa que abre cuentas sí."),

    # ── Los límites de cada vía de dinero ──────────────────────────────────
    #
    # Vivían escritos a mano en tres archivos distintos —`services/limits.py`,
    # `services/kyc_quota.py` y `routes/payments_card.py`— y cambiar cualquiera
    # de ellos era un commit y un despliegue.
    #
    # LOS TOPES DE CADA AJUSTE NO SON EL LIMITE: SON LA RED
    #
    #   El «máximo» de acá abajo es hasta dónde se puede subir el número desde
    #   el panel, no cuánto puede mandar un usuario. Están anchos a propósito,
    #   para no tener que volver a tocar código por una promoción, y cerrados lo
    #   suficiente como para que un cero de más al tipear no pase.

    "pix_minimo": Ajuste(
        tipo=DINERO, defecto="10.00", minimo="0", maximo="500",
        unidad="R$",
        etiqueta="Mínimo de una operación por PIX",
        ayuda="Vale para recargar y para enviar. Por debajo de esto la "
              "comisión fija se come la operación."),

    "pix_maximo": Ajuste(
        tipo=DINERO, defecto="5000.00", minimo="10", maximo="50000",
        unidad="R$",
        etiqueta="Máximo de una operación por PIX",
        ayuda="El techo por operación, no por día. Subirlo es subir cuánto "
              "puede mover una sola persona de una sola vez."),

    "tarjeta_minimo": Ajuste(
        tipo=DINERO, defecto="5.00", minimo="0", maximo="500",
        unidad="R$",
        etiqueta="Mínimo de una recarga con tarjeta",
        ayuda="La tarjeta cobra una comisión fija además del porcentaje, así "
              "que un monto muy chico se va casi entero en comisión."),

    "tarjeta_maximo": Ajuste(
        tipo=DINERO, defecto="5000.00", minimo="10", maximo="50000",
        unidad="R$",
        etiqueta="Máximo de una recarga con tarjeta",
        ayuda="Recargar con tarjeta además exige tener la identidad "
              "verificada; eso no se configura acá."),

    "ves_minimo": Ajuste(
        tipo=DINERO, defecto="100.00", minimo="0", maximo="100000",
        unidad="VES",
        etiqueta="Mínimo de una recarga en bolívares",
        ayuda="No hay máximo en bolívares, por decisión de negocio, y por eso "
              "no aparece acá: el catálogo guarda números y «sin techo» no lo "
              "es."),

    "cupo_sin_verificar_ris": Ajuste(
        tipo=DINERO, defecto="200.00", minimo="0", maximo="10000",
        unidad="RIS",
        etiqueta="Cuánto puede mover una cuenta sin verificar",
        ayuda="El total acumulado, no por operación. Este número SE PUBLICA en "
              "la página de «cómo funciona», así que cambiarlo cambia lo que la "
              "aplicación le promete a quien todavía no verificó."),

    # ── Cuánto vale una tasa del BCV recién raspada ────────────────────────
    #
    # NO ES UN LIMITE DE DINERO, ES UNA FECHA DE VENCIMIENTO, y está acá porque
    # la regla del proyecto es que configurar no requiera editar código.
    #
    # Lo que pasó: el sitio del BCV empezó a rechazar la conexión (le falta una
    # pieza de su cadena de certificados) y el raspador dejó de traer nada. La
    # contabilidad siguió usando el ULTIMO número raspado, sin mirar de cuándo
    # era, y encima ese número le GANABA al que el operador carga a mano en
    # Tasas. O sea que cambiar la tasa en el panel no cambiaba la contabilidad,
    # y nadie tenía forma de saberlo.
    "bcv_horas_de_vigencia": Ajuste(
        tipo=ENTERO, defecto=24, minimo=1, maximo=720,
        unidad="horas",
        etiqueta="Cuántas horas vale la tasa del BCV que trae el raspador",
        ayuda="Pasadas estas horas, la contabilidad deja de usar el número del "
              "raspador y usa el que está cargado a mano en Tasas. Además el "
              "panel lo muestra en rojo y se avisa a los super "
              "administradores. Bajarlo hace que la aplicación desconfíe "
              "antes; subirlo, que aguante más tiempo con el último dato."),

    "cupo_sin_verificar_operaciones": Ajuste(
        tipo=ENTERO, defecto=2, minimo=0, maximo=100,
        unidad="operaciones",
        etiqueta="Cuántas operaciones puede hacer una cuenta sin verificar",
        ayuda="Se agota con lo que llegue primero: estas operaciones o el monto "
              "de arriba. También se publica."),
}


# ─── Las parejas que tienen que quedar en orden ───────────────────────────
#
# POR QUE ESTO NO PUEDE VIVIR EN `Ajuste`
#
#   Cada ajuste se valida solo: su tipo, su piso, su techo. Pero «el mínimo de
#   PIX no puede ser mayor que el máximo de PIX» es una regla ENTRE DOS, y
#   ninguno de los dos la puede comprobar mirándose a sí mismo.
#
#   Sin esto, poner el mínimo en 400 y el máximo en 100 se guarda sin chistar y
#   deja la vía entera muerta: ningún monto cumple las dos condiciones a la vez,
#   y el usuario ve «el monto mínimo es R$ 400» justo después de «el monto
#   máximo es R$ 100». Nadie relaciona eso con un campo del panel.
PAREJAS_MINIMO_Y_MAXIMO = (
    ("pix_minimo", "pix_maximo", "PIX"),
    ("tarjeta_minimo", "tarjeta_maximo", "tarjeta"),
)


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


def _dinero_guardado(crudo):
    """Un monto LEIDO DE LA BASE: `(Decimal, None)` o `(None, motivo)`.

    POR QUE NO ALCANZA CON `from_db`, Y COMO SE DESCUBRIO

        `from_db` es tolerante a propósito: un valor que no se entiende vuelve
        como `Decimal('0')`. Para leer un saldo viejo y raro eso está bien —una
        pantalla no puede caerse por un dato feo—, pero para un AJUSTE es un
        desastre distinto.

        Esta función faltaba. La rama de los enteros ya volvía al valor de
        fábrica cuando lo guardado era ilegible, y hasta lo anotaba en los
        registros; la de la plata no comprobaba nada y devolvía cero. O sea que
        un `pix_maximo` ilegible en la base dejaba el máximo en cero y NADIE
        podía pagar por PIX, y un `bono_al_referido` ilegible le daba cero de
        bono a todo el mundo sin un solo error en ningún lado.

        Lo encontró un test que guardaba basura a mano y esperaba que la vía
        siguiera andando. El comentario de la cabecera de este módulo ya avisaba
        del peligro —«escribir "abc" en el campo del bono guardaría CERO sin que
        nadie se entere»— pero la guarda se había puesto sólo al ESCRIBIR.
        Escribir está cerrado con `normalizar`; leer no lo estaba.

        Por eso la lista de tipos es blanca y no negra: lo que no se reconoce se
        rechaza y se vuelve al valor de fábrica, en vez de intentar interpretarlo.
    """
    if isinstance(crudo, bool):
        return None, "no es un número"
    if isinstance(crudo, Decimal128):
        try:
            return quantize_money(crudo.to_decimal()), None
        except Exception:
            return None, "no es un número"
    if isinstance(crudo, (int, Decimal, float, str)):
        return _a_dinero(crudo)
    return None, "no es un número"


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

    valor, motivo = (_dinero_guardado(doc["valor"]) if ajuste.tipo == DINERO
                     else _a_entero(doc["valor"]))
    if motivo:
        logger.error("configuracion: %r guardado con un valor ilegible (%r); "
                     "se usa el de fábrica", clave, doc["valor"])
        return _defecto(ajuste)
    return valor


def _defecto(ajuste):
    return (quantize_money(ajuste.defecto) if ajuste.tipo == DINERO
            else int(ajuste.defecto))


async def revisar_las_parejas(db, limpios: dict):
    """¿Queda algún mínimo por encima de su máximo? El motivo, o `None`.

    SE MIRA EL RESULTADO, NO LO QUE SE MANDÓ

        La pantalla puede mandar un solo campo. Comprobar la pareja sólo cuando
        vienen los dos dejaría pasar el caso más probable de todos: alguien
        cambia únicamente el mínimo de PIX, lo pone en 6.000, y el máximo
        guardado sigue en 5.000. Por eso se arma cómo QUEDARIA todo —lo guardado
        más lo que se está por guardar— y se mira eso.

    SE COMPRUEBA ANTES DE ESCRIBIR NADA

        Igual que la validación de cada campo. Escribir el mínimo y después
        rechazar el máximo dejaría la vía muerta a medio camino, que es peor que
        rechazar las dos cosas.
    """
    queda = {**await leer_todo(db), **limpios}
    for clave_min, clave_max, via in PAREJAS_MINIMO_Y_MAXIMO:
        if queda[clave_min] > queda[clave_max]:
            return (
                f"El mínimo de {via} ({_mostrar(AJUSTES[clave_min], queda[clave_min])}) "
                f"quedaría por encima del máximo "
                f"({_mostrar(AJUSTES[clave_max], queda[clave_max])}). Así ningún "
                "monto sería válido y esa vía dejaría de funcionar para todos.")
    return None


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
        valor, motivo = (_dinero_guardado(crudo) if ajuste.tipo == DINERO
                         else _a_entero(crudo))
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
