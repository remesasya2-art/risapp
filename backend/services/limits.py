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

    Ahora el limite se define aca, el servidor lo valida antes de escribir en la
    base, y la pantalla lo lee de /limits en vez de tenerlo hardcodeado. Si cambia
    un numero, se cambia en este archivo y las dos puntas quedan de acuerdo solas.

UNIDADES
    PIX opera en reales y la plataforma acredita RIS a la par (1 BRL = 1 RIS), asi
    que el mismo par de numeros sirve para la recarga (que entra en BRL) y para el
    envio (que sale contra el saldo en RIS).

    Bolivares NO se limitan en VES sino que se convierten: el piso esta expresado
    en VES porque es lo que el usuario tipea, pero no hay techo por decision de
    negocio.

LO QUE ESTE MODULO NO HACE
    No sabe nada de KYC ni de cupos por usuario. Esto son limites por operacion,
    iguales para todos. El cupo de la cuenta sin verificar es otra cosa y vive en
    otro lado.
"""

# ─── PIX / reales ─────────────────────────────────────────────────────────
PIX_MIN_BRL = 10.0
PIX_MAX_BRL = 5000.0

# ─── Bolivares ────────────────────────────────────────────────────────────
VES_MIN = 100.0
VES_MAX = None  # sin techo, a proposito


def _fmt(valor: float) -> str:
    """Formatea con coma de miles, como se le muestra al usuario."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def validate_pix_amount(amount) -> str | None:
    """Valida un monto de PIX (recarga o envio).

    Devuelve el mensaje de error, o None si el monto esta dentro de rango. No
    lanza: el que llama decide si es un 400, un toast o un cartel.
    """
    try:
        valor = float(amount)
    except (TypeError, ValueError):
        return "El monto no es un número válido."
    if valor <= 0:
        return "El monto debe ser mayor a 0."
    if valor < PIX_MIN_BRL:
        return f"El monto mínimo es R$ {_fmt(PIX_MIN_BRL)}."
    if valor > PIX_MAX_BRL:
        return f"El monto máximo es R$ {_fmt(PIX_MAX_BRL)}."
    return None


def validate_ves_amount(amount) -> str | None:
    """Valida un monto de recarga en bolivares. Sin techo, solo piso."""
    try:
        valor = float(amount)
    except (TypeError, ValueError):
        return "El monto no es un número válido."
    if valor <= 0:
        return "El monto debe ser mayor a 0."
    if valor < VES_MIN:
        return f"El monto mínimo es {_fmt(VES_MIN)} VES."
    return None


def limits_payload() -> dict:
    """Lo que /limits le devuelve al frontend.

    La pantalla arma sus textos y sus validaciones con esto, para que el cartel
    que ve el usuario y el 400 que devuelve el servidor no puedan discrepar.
    """
    from services.kyc_quota import UNVERIFIED_MAX_OPS, UNVERIFIED_MAX_RIS
    return {
        "pix": {"min_brl": PIX_MIN_BRL, "max_brl": PIX_MAX_BRL},
        "ves": {"min_ves": VES_MIN, "max_ves": VES_MAX},
        # El cupo de quien todavía no verificó su identidad. Es una REGLA
        # pública, no un dato de nadie: sale acá para que la página que la
        # publica lea el mismo número que el servidor hace cumplir. Un texto
        # aparte se desactualiza el día que alguien cambie la constante y se
        # olvide de la página.
        "sin_verificar": {
            "max_ris": UNVERIFIED_MAX_RIS,
            "max_operaciones": UNVERIFIED_MAX_OPS,
        },
    }
