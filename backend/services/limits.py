"""
services/limits.py — Los limites de monto de cada via de dinero, en UN solo lugar.

POR QUE EXISTE ESTE MODULO
    Los limites vivian escritos en la pantalla y en ningun otro lado. Recharge.jsx
    anunciaba "Minimo: R$ 10 - Maximo: R$ 2.000" y validaba solo el minimo; el
    maximo era un atributo max="2000" en el input, que el navegador nunca aplica
    porque el envio va por onClick y no por submit nativo. Del lado del servidor,
    /gestor/pix/create y /reais/send solo comprobaban que el monto fuera mayor a 0.
    Resultado: la app prometia un techo que no existia.

    El mismo problema, distinto sintoma, en bolivares: Recharge.jsx exigia 100 VES
    y RechargeVES.jsx —que postea al MISMO endpoint— no exigia nada.

    Ahora el limite se define en UN lugar, el servidor lo valida antes de escribir
    en la base, y la pantalla lo lee de /limits en vez de tenerlo hardcodeado.

DE DONDE SALEN LOS NUMEROS, Y POR QUE YA NO ESTAN ACA
    Estaban escritos a mano en este archivo. Cambiar el maximo de PIX era un
    commit, un despliegue y un rato de espera — y la regla del proyecto es que
    configurar nunca pueda requerir editar codigo en GitHub.

    Ahora viven en el catalogo de `services/configuracion.py` y se cambian desde
    el panel del super administrador. Lo que queda escrito alla es tambien el
    valor de fabrica: si nunca se guardo nada, es el que rige.

POR QUE ESTAS FUNCIONES SON ASINCRONAS Y PIDEN LA BASE
    Porque leer la configuracion es una consulta. Antes eran funciones puras que
    comparaban contra una constante.

    El costo de ese cambio no es la consulta —una sola, sobre una coleccion de
    siete documentos— sino que quien llame TIENE QUE PONER `await`. Sin el,
    `error_monto` queda siendo una corrutina, que en Python es un valor
    verdadero, y entonces TODA operacion se rechazaria con un mensaje absurdo.
    Falla ruidoso y en el primer intento, pero hay una guarda que recorre el
    repositorio exigiendo el `await`, porque «ruidoso» y «en produccion» es una
    combinacion que no hace falta probar.

UNIDADES
    PIX opera en reales y la plataforma acredita RIS a la par (1 BRL = 1 RIS), asi
    que el mismo par de numeros sirve para la recarga (que entra en BRL) y para el
    envio (que sale contra el saldo en RIS).

    Bolivares NO se limitan en VES sino que se convierten: el piso esta expresado
    en VES porque es lo que el usuario tipea, pero no hay techo por decision de
    negocio. Ese "sin techo" sigue escrito aca y no en el catalogo: el catalogo
    guarda numeros, y "ninguno" no es un numero.

LO QUE ESTE MODULO NO HACE
    No sabe nada de KYC ni de cupos por usuario. Esto son limites por operacion,
    iguales para todos. El cupo de la cuenta sin verificar es otra cosa y vive en
    otro lado.
"""
from decimal import Decimal

# El unico limite que sigue escrito en codigo, y a proposito: no es un numero.
VES_MAX = None  # sin techo, a proposito


def _fmt(valor) -> str:
    """Formatea con coma de miles, como se le muestra al usuario."""
    return f"{Decimal(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _a_decimal(amount):
    """El monto como `Decimal`, o `None` si no es un numero.

    `money.to_decimal` NO sirve aca: es tolerante a proposito y devuelve
    `Decimal('0')` para "abc", lo que convertiria "el monto no es valido" en "el
    monto debe ser mayor a 0" — un mensaje que manda a la persona a cambiar el
    numero cuando el problema es otro.

    LA COMA SE RECHAZA, Y ES LO CONTRARIO DE LO QUE HACE EL PANEL

        En `services/configuracion.py` la coma se normaliza, porque ahi la
        escribe una persona y "15,50" es como se escribe un monto en Brasil.

        Aca no: esto llega de un navegador, y "1,050" no se sabe si es mil
        cincuenta o uno coma cero cinco. Interpretarlo mal es equivocarse por
        mil veces. Se rechaza con un mensaje y que el que manda lo aclare.
    """
    if isinstance(amount, bool):
        return None
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, (int, float)):
        try:
            return Decimal(str(amount))
        except Exception:
            return None
    if isinstance(amount, str):
        limpio = amount.strip()
        if not limpio:
            return None
        try:
            valor = Decimal(limpio)
        except Exception:
            return None
        return valor if valor.is_finite() else None
    return None


async def validate_pix_amount(db, amount) -> str | None:
    """Valida un monto de PIX (recarga o envio).

    Devuelve el mensaje de error, o None si el monto esta dentro de rango. No
    lanza: el que llama decide si es un 400, un toast o un cartel.
    """
    from services import configuracion

    valor = _a_decimal(amount)
    if valor is None:
        return "El monto no es un número válido."
    if valor <= 0:
        return "El monto debe ser mayor a 0."

    minimo = await configuracion.leer(db, "pix_minimo")
    maximo = await configuracion.leer(db, "pix_maximo")
    if valor < minimo:
        return f"El monto mínimo es R$ {_fmt(minimo)}."
    if valor > maximo:
        return f"El monto máximo es R$ {_fmt(maximo)}."
    return None


async def validate_card_amount(db, amount) -> str | None:
    """Valida un monto de recarga con tarjeta.

    Es otra via y otro par de numeros: la tarjeta cobra una comision fija ademas
    del porcentaje, asi que su minimo puede ser distinto al de PIX.
    """
    from services import configuracion

    valor = _a_decimal(amount)
    if valor is None:
        return "El monto no es un número válido."
    if valor <= 0:
        return "El monto debe ser mayor a 0."

    minimo = await configuracion.leer(db, "tarjeta_minimo")
    maximo = await configuracion.leer(db, "tarjeta_maximo")
    if valor < minimo or valor > maximo:
        return (f"Monto debe estar entre R$ {_fmt(minimo)} y R$ {_fmt(maximo)}.")
    return None


async def validate_ves_amount(db, amount) -> str | None:
    """Valida un monto de recarga en bolivares. Sin techo, solo piso."""
    from services import configuracion

    valor = _a_decimal(amount)
    if valor is None:
        return "El monto no es un número válido."
    if valor <= 0:
        return "El monto debe ser mayor a 0."

    minimo = await configuracion.leer(db, "ves_minimo")
    if valor < minimo:
        return f"El monto mínimo es {_fmt(minimo)} VES."
    return None


async def limits_payload(db) -> dict:
    """Lo que /limits le devuelve al frontend.

    La pantalla arma sus textos y sus validaciones con esto, para que el cartel
    que ve el usuario y el 400 que devuelve el servidor no puedan discrepar.

    Los montos salen como `float` y no como texto, que es lo contrario de lo que
    hace el resto del proyecto. Es a proposito y por compatibilidad: seis
    pantallas ya comparan estos valores con `parseFloat`, y cambiarlos a texto
    las romperia en silencio —`"10.00" > 5` es verdadero en JavaScript, pero
    `"10.00" > "5"` es falso—. Son topes de tres cifras, no saldos: no hay nada
    que redondear mal.
    """
    from services import configuracion, cripto_abierta, pago_al_final
    from services import encomiendas_abiertas, recarga_abierta, remesas_abiertas
    from services.money import to_float

    ajustes = await configuracion.leer_todo(db)
    # La llave madre. Recarga y cripto se publican YA recortadas por ella,
    # igual que las recortan sus guardas en el servidor: si se publicara la
    # llave suelta, la pantalla ofrecería recargar con remesas cerrada y el
    # servidor le contestaría 503.
    remesas = bool(int(ajustes[remesas_abiertas.CLAVE]))
    return {
        "pix": {"min_brl": to_float(ajustes["pix_minimo"]),
                "max_brl": to_float(ajustes["pix_maximo"])},
        "tarjeta": {"min_brl": to_float(ajustes["tarjeta_minimo"]),
                    "max_brl": to_float(ajustes["tarjeta_maximo"])},
        "ves": {"min_ves": to_float(ajustes["ves_minimo"]), "max_ves": VES_MAX},
        # El cupo de quien todavía no verificó su identidad. Es una REGLA
        # pública, no un dato de nadie: sale acá para que la página que la
        # publica lea el mismo número que el servidor hace cumplir. Un texto
        # aparte se desactualiza el día que alguien cambie el ajuste y se
        # olvide de la página.
        "sin_verificar": {
            "max_ris": to_float(ajustes["cupo_sin_verificar_ris"]),
            "max_operaciones": int(ajustes["cupo_sin_verificar_operaciones"]),
        },
        # EL ESTADO DE LA VIA CRIPTO VIAJA ACA, Y NO EN UNA RUTA NUEVA.
        #
        #   Por el motivo del docstring de arriba: la pantalla y el servidor
        #   tienen que leer lo mismo. Si la pantalla preguntara aparte, habría
        #   un momento —y un despliegue a medias— en el que dibuja un botón que
        #   el servidor ya rechaza. Y esta ruta la consulta toda pantalla que
        #   muestre un monto, así que no agrega ni un pedido.
        #
        #   Se publican las respuestas resueltas y no sólo el número: ver
        #   `cripto_abierta.para_el_frontend`.
        "cripto": cripto_abierta.para_el_frontend(
            cripto_abierta.con_la_llave_madre(
                int(ajustes[cripto_abierta.CLAVE]), remesas)),
        # El flujo de pago, por el mismo motivo que la línea de arriba: la
        # pantalla del envío tiene que ofrecer exactamente lo que el servidor
        # acepta. Con esto apagado, `/withdraw-ves/cotizar` contesta 503, así
        # que un botón que lo llame sería un botón que lleva a un error.
        "pago_al_final": bool(int(ajustes[pago_al_final.CLAVE])),
        # Si se puede cargar saldo. Con esto en false las cuatro rutas de
        # recarga contestan 503, así que la pantalla tiene que esconder sus
        # ocho puertas: un botón que lleva a un error no es una opción.
        "recarga": bool(int(ajustes[recarga_abierta.CLAVE])) and remesas,
        # Si se pueden mandar encomiendas nuevas. Con esto en false, cotizar y
        # confirmar contestan 503, así que el menú tiene que dejar de ofrecer
        # «Enviar un paquete». Lo que ya está en camino no depende de esto.
        "encomiendas": bool(int(ajustes[encomiendas_abiertas.CLAVE])),
        # Si se puede gastar en Venezuela y en Brasil. Con esto en false las
        # cinco rutas que crean un envío contestan 503, así que el menú deja
        # de ofrecerlas. Lo que ya está en curso no depende de esto.
        "remesas": remesas,
    }
