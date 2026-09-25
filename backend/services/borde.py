"""
services/borde.py — La puerta que exige haber pasado por Cloudflare.

EL AGUJERO QUE CIERRA

    Todos los límites por IP de la aplicación —ingreso, reseteo de contraseña,
    segundo factor— cuentan usando `services/ip_cliente.ip_del_cliente`, que
    confía en la cabecera `CF-Connecting-IP` cuando está presente.

    Esa cabecera es confiable SOLO si Cloudflare está adelante, porque él la
    escribe pisando lo que mande el cliente. Pero el hostname de Railway
    responde igual sin pasar por Cloudflare: quien entra por ahí escribe él
    mismo la cabecera, la cambia en cada pedido, y cada intento cae en un
    contador distinto. Los límites dejan de existir. No hacía falta romper
    nada: bastaba con no usar el dominio.

    Mover el API detrás del dominio NO alcanza. El hostname de Railway sigue
    existiendo y sigue respondiendo. Lo que lo cierra es que la aplicación
    sepa distinguir «vino por nuestro Cloudflare» de «vino por la puerta de
    atrás», y eso es lo que hace este módulo.

COMO FUNCIONA

    Cloudflare inyecta una cabecera con un valor secreto en cada pedido hacia
    `api.risappbr.com` (una Request Header Transform Rule). La aplicación
    exige esa cabecera. Quien entre directo por Railway no la tiene y no la
    puede adivinar.

POR QUE ARRANCA EN MODO AVISO Y NO BLOQUEANDO

    Porque esta puerta puede tirar abajo la aplicación entera, y de tres
    formas distintas:

      · `railway.toml` declara `healthcheckPath = "/api/health"`. Si la puerta
        le contesta 403 al chequeo de salud, Railway da el despliegue por
        fallido y REINICIA EN BUCLE. La aplicación no levanta más.
      · Siete rutas las llama un tercero que jamás va a traer nuestra
        cabecera: Mercado Pago, NOWPayments, Blink, Twilio y la integración
        de contabilidad. Bloquearlas es dejar de acreditar pagos.
      · Si la regla de Cloudflare se escribe mal, o se borra, o alguien toca
        el secreto, la puerta deja afuera a TODOS los usuarios a la vez.

    Así que el valor por omisión es `reporte`: registra lo que habría
    bloqueado y no bloquea nada. Se lee el registro unos días, se confirma que
    sólo cae lo que tiene que caer, y recién ahí se pasa a `exigir`. Es el
    mismo camino que ya usa `services/csp.py`, por el mismo motivo.

    Y si no hay secreto configurado, la puerta está apagada del todo: no se
    puede exigir lo que no existe. Una variable que falta no puede dejar la
    aplicación sin responder.
"""
import hmac
import logging
import os

logger = logging.getLogger(__name__)

# La cabecera que escribe Cloudflare. El nombre no es secreto —el secreto es
# el valor—, así que puede ser legible.
CABECERA = "x-llave-del-borde"

VARIABLE_LLAVE = "LLAVE_DEL_BORDE"
VARIABLE_MODO = "LLAVE_DEL_BORDE_MODO"

# Lo que NUNCA pasa por esta puerta, y por qué cada uno.
#
# Se compara por prefijo sobre la ruta completa. La lista es corta a
# propósito: cada línea es una puerta que queda abierta, así que agregar una
# tiene que costar tanto como pensarla.
EXENTAS = (
    # Railway le pega a esto para saber si la aplicación vive. Un 403 acá y el
    # despliegue no levanta nunca. Es la más importante de la lista.
    "/api/health",

    # Los que llama un tercero. Ninguno va a traer nuestra cabecera, y todos
    # tienen su propia autenticación: Mercado Pago valida firma HMAC y es
    # fail-closed; la integración de contabilidad exige su propia clave.
    "/api/webhook/mercadopago",
    "/api/credits/webhook",
    "/api/btc/webhook/blink",
    "/api/transactions/crypto-send/webhook",
    "/api/webhooks/",
)


def llave() -> str:
    """El secreto que tiene que traer el pedido. Vacío = puerta apagada."""
    return (os.environ.get(VARIABLE_LLAVE) or "").strip()


def modo() -> str:
    """`exigir` bloquea; `reporte` sólo registra; `apagado` no mira nada.

    Por omisión `reporte`, y sin llave configurada, `apagado`: no se puede
    exigir lo que no está puesto.
    """
    if not llave():
        return "apagado"
    valor = (os.environ.get(VARIABLE_MODO, "reporte") or "").strip().lower()
    return valor if valor in ("exigir", "reporte", "apagado") else "reporte"


def esta_exenta(ruta: str) -> bool:
    return any((ruta or "").startswith(p) for p in EXENTAS)


def paso_por_el_borde(cabeceras) -> bool:
    """Si este pedido trae el secreto que escribe nuestro Cloudflare.

    `compare_digest` y no `==`: comparar cadenas con `==` corta en la primera
    letra distinta, y el tiempo que tarda dice cuántas acertó quien prueba.
    Con suficientes intentos se adivina letra por letra.
    """
    esperada = llave()
    if not esperada:
        return False
    try:
        traida = ((cabeceras or {}).get(CABECERA) or "").strip()
    except Exception:                                         # pragma: no cover
        return False
    return bool(traida) and hmac.compare_digest(traida, esperada)


def confiar_en_cloudflare(cabeceras) -> bool:
    """Si `CF-Connecting-IP` se puede usar para contar intentos.

    DOS CASOS, Y EL SEGUNDO ES EL QUE EVITA UN DESASTRE AL DESPLEGAR

      1. Hay llave configurada: se confía sólo si el pedido la trae. Ese es el
         arreglo.

      2. NO hay llave configurada: se confía igual, como se hacía hasta ahora.

    El segundo parece que deja el agujero abierto, y lo deja — a propósito,
    hasta que la llave esté puesta. La alternativa es peor, y se midió:

        Hoy `www.risappbr.com` YA pasa por Cloudflare: cliente → Cloudflare →
        Railway → aplicación. Son DOS proxies. Si se deja de usar
        `CF-Connecting-IP` sin llave configurada, se cae al respaldo de
        `X-Forwarded-For` con `PROXIES_DE_CONFIANZA=1`, que en esa cadena
        devuelve la IP del BORDE DE CLOUDFLARE y no la del usuario.

        Medido: cinco usuarios distintos caían en un solo contador. El límite
        de veinte intentos se lo comerían usuarios inocentes que comparten
        borde, y el ingreso empezaría a devolver 429 a gente que nunca falló.

    O sea: desplegar el arreglo sin la llave puesta ROMPERIA a los usuarios de
    verdad para cerrarle la puerta a nadie, porque el atacante entra por el
    hostname de Railway igual. Un número solo no puede ser correcto para los
    dos caminos a la vez —dos proxies por Cloudflare, uno por la puerta de
    atrás—, y por eso el arreglo es la llave y no el número.

    El arranque avisa, fuerte, que la puerta está apagada.
    """
    if not llave():
        return True
    return paso_por_el_borde(cabeceras)


def revisar() -> dict:
    """Qué va a hacer la puerta, para decirlo en el arranque."""
    m = modo()
    if m == "apagado":
        return {"modo": m, "listo": False, "detalle": (
            f"La puerta del borde está APAGADA: falta {VARIABLE_LLAVE}. "
            "Quien entre por el hostname de Railway puede falsear su IP y "
            "saltarse todos los límites de intentos.")}
    if m == "reporte":
        return {"modo": m, "listo": False, "detalle": (
            "La puerta del borde está en AVISO: registra lo que bloquearía y "
            f"no bloquea nada. Cuando el registro esté limpio, poné "
            f"{VARIABLE_MODO}=exigir.")}
    return {"modo": m, "listo": True, "detalle": (
        "La puerta del borde EXIGE la cabecera de Cloudflare.")}


# ─── La puerta, como middleware ───────────────────────────────────────────

class PuertaDelBorde:
    """Middleware ASGI: deja pasar sólo lo que vino por nuestro Cloudflare.

    En ASGI y no `@app.middleware("http")` para poder contestar sin armar el
    `Request`, igual que `services/limite_de_cuerpo.py`.

    NUNCA LEVANTA. Si algo sale mal resolviendo si el pedido pasó o no, el
    pedido PASA. Una puerta que se rompe y deja a todos afuera es peor que el
    agujero que cierra: el agujero deja entrar a quien insiste, la puerta rota
    deja afuera a todos los clientes a la vez.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        try:
            bloquear = self._hay_que_frenarlo(scope)
        except Exception as e:                                # pragma: no cover
            logger.warning("borde: no se pudo revisar el pedido, pasa: %s", e)
            bloquear = False

        if not bloquear:
            await self.app(scope, receive, send)
            return

        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body",
                    "body": b'{"detail":"no_paso_por_el_borde"}'})

    def _hay_que_frenarlo(self, scope) -> bool:
        m = modo()
        if m == "apagado":
            return False

        ruta = scope.get("path") or ""
        if esta_exenta(ruta):
            return False

        cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1")
                     for k, v in scope.get("headers") or []}
        if paso_por_el_borde(cabeceras):
            return False

        if m == "reporte":
            # Lo que se anota es la RUTA y nada más. Ni la IP ni las cabeceras:
            # acá todavía no se sabe de quién vienen —ése es justamente el
            # problema que se está cerrando— y un registro lleno de datos que
            # los escribe el atacante no sirve para decidir nada.
            logger.warning(
                "borde (aviso): este pedido se bloquearía en modo exigir: %s. "
                "Si es legítimo, agregalo a EXENTAS antes de pasar a exigir.",
                ruta)
            return False

        logger.info("borde: pedido rechazado por no venir del borde: %s", ruta)
        return True
