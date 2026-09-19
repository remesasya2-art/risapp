"""
Pagar un envío con tarjeta, sin pasar por el saldo.

POR QUE ESTO EXISTE, Y POR QUE NO ES UNA RECARGA

    La empresa no custodia dinero de terceros. Cargar saldo se cerró
    —`services/recarga_abierta.py`—, así que la tarjeta dejó de servir para lo
    único que servía.

    Pero la tarjeta pagando UN ENVIO no es custodia: la plata entra y sale en
    la misma operación, igual que el PIX que cobra al final. No queda saldo en
    el medio, que es justo lo que había que evitar.

    Por eso las rutas que cargan saldo con tarjeta siguen cerradas y ésta no.

LA TRAMPA QUE DEFINE ESTE ARCHIVO: EL DOBLE COBRO

    Cotizar un envío deja una orden esperando el pago Y genera un QR de PIX.
    Si además se pudiera pagar esa misma orden con tarjeta, el cliente podría
    pagar las dos veces —el QR sigue vivo y la tarjeta también cobra— y sólo
    una contaría: `pago_al_final.confirmar` es un `find_one_and_update` con el
    estado en el filtro, así que la segunda no encuentra nada que avanzar.

    Y para entonces ya le sacaron la plata dos veces.

    No alcanza con confiar en esa atomicidad: protege la ORDEN, no la
    BILLETERA del cliente. Así que el método se elige ANTES de cotizar:

      · Con PIX se genera el QR, como siempre, y esta vía la rechaza.
      · Con tarjeta NO se genera ningún QR. La orden sólo se puede pagar acá.

    `es_de_tarjeta` es la guarda que lo hace cumplir, y es la más importante
    del archivo.

LA COMISION LA PAGA EL CLIENTE

    Decisión del dueño del proyecto. Se suma ARRIBA del envío, igual que en la
    recarga con tarjeta: el beneficiario recibe los mismos bolívares y lo que
    sube es lo que se le cobra a la tarjeta.

    Un envío de R$ 100 se cobra R$ 104,89 en crédito o R$ 102,39 en débito, con
    los porcentajes de fábrica. Con PIX se cobran R$ 100. Esa diferencia tiene
    que estar en la pantalla ANTES de que elija, y por eso `cotizar` la
    devuelve desglosada y no sólo el total.

SOLO CLIENTES VERIFICADOS

    También decisión del dueño, y el motivo es el contracargo: una tarjeta se
    puede desconocer hasta ciento veinte días después del cobro, cosa que con
    PIX no pasa. Si para entonces el envío ya se despachó en Venezuela, la
    plata se fue, los bolívares también, y la pérdida es de la empresa.

    Exigir identidad verificada no elimina ese riesgo; lo ata a una persona
    identificable. Es la misma exigencia que ya tenía la recarga con tarjeta
    (`routes/payments_card.py`), y acá se repite en vez de heredarse porque
    heredar una guarda de otra ruta es tenerla hasta que alguien reordena las
    rutas.
"""
import logging
from decimal import Decimal

from services.money import to_decimal

logger = logging.getLogger(__name__)

# Cómo se paga el envío. Se guarda en el documento del cobro, y es lo que
# `es_de_tarjeta` mira.
POR_PIX = "pix"
POR_TARJETA = "tarjeta"
METODOS = (POR_PIX, POR_TARJETA)

# Lo que ve el usuario cuando intenta pagar con tarjeta una orden que se
# cotizó para PIX. Nombra la salida, porque el QR que tiene en pantalla SI
# funciona y no hay por qué asustarlo.
NO_ES_DE_TARJETA = ("Este envío se cotizó para pagar con PIX. Escaneá el "
                    "código que te dimos, o volvé atrás y elegí pagar con "
                    "tarjeta.")

SIN_VERIFICAR = ("Para pagar con tarjeta necesitás verificar tu identidad. "
                 "Mientras tanto podés pagar este envío con PIX.")


def normalizar_metodo(metodo) -> str:
    """El método con el que se va a pagar, o PIX si no dijeron nada.

    PIX es el que vale por omisión porque es el que ya existía: un cliente
    viejo que no manda el campo tiene que seguir recibiendo su QR.
    """
    limpio = str(metodo or "").strip().lower()
    return limpio if limpio in METODOS else POR_PIX


def es_de_tarjeta(pago: dict) -> bool:
    """¿Esta orden se cotizó para pagarse con tarjeta?

    LA GUARDA IMPORTANTE. Ver la trampa del doble cobro, arriba.

    Falla CERRADO: un documento sin el campo —los cobros de antes de que este
    archivo existiera— es de PIX, y esos tienen QR. Dejarlos pasar acá sería
    exactamente el doble cobro que este archivo evita.
    """
    if not pago:
        return False
    return pago.get("metodo") == POR_TARJETA


def tiene_qr(pago: dict) -> bool:
    """¿Quedó un código de PIX que alguien todavía puede pagar?

    Es la comprobación de respaldo de `es_de_tarjeta`, y no es redundante con
    ella: aquélla mira lo que se PIDIO, ésta lo que QUEDO. Si un día una orden
    de tarjeta terminara con un QR guardado —un cambio en la cotización, una
    migración a medias—, `es_de_tarjeta` la dejaría pasar y el doble cobro
    volvería sin que nada avisara.

    Las dos juntas dicen: ni se pidió PIX, ni quedó un PIX pagable.
    """
    return bool((pago or {}).get("qr_code"))


def comision(monto: Decimal, tipo_de_tarjeta: str, tarifas: dict) -> Decimal:
    """Lo que cobra la pasarela por este cobro, en reales.

    `tarifas` son las mismas de `routes/payments_card.py` —salen de
    `app_settings.card_fees` y se cambian sin desplegar—, así que un cambio de
    tarifa vale para las dos vías y no para una sola.

    En Decimal y no en float: es plata que se le suma a lo que paga una
    persona. `payments_card` lo hace en float porque es de antes de la regla;
    lo nuevo no arrastra eso.
    """
    porcentaje = to_decimal(
        tarifas["debit_pct"] if tipo_de_tarjeta == "debit_card"
        else tarifas["credit_pct"])
    fijo = to_decimal(tarifas["flat_brl"])
    return (to_decimal(monto) * porcentaje / to_decimal(100) + fijo).quantize(
        to_decimal("0.01"))


def cuanto_se_le_cobra(monto: Decimal, tipo_de_tarjeta: str,
                       tarifas: dict) -> dict:
    """El desglose que va a la pantalla.

    Devuelve las tres cifras por separado y no sólo el total, porque el total
    solo no deja comparar con el PIX. Quien ve «R$ 104,89» al lado de
    «R$ 100,00» y no sabe de dónde salen los 4,89 se va a creer que le están
    cobrando de más.
    """
    neto = to_decimal(monto)
    fee = comision(neto, tipo_de_tarjeta, tarifas)
    return {"envio_brl": neto, "comision_brl": fee, "total_brl": neto + fee}
