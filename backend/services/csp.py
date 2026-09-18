"""
La política de contenido: qué le permitimos cargar al navegador.

QUE RESUELVE, Y POR QUE NO ESTABA

    Un XSS es código ajeno corriendo en el origen de la aplicación, con la
    sesión de quien mira. Las validaciones de entrada y de salida cierran los
    caminos que conocemos; la política de contenido cierra el resto —le dice al
    navegador de dónde puede venir un script, y todo lo demás no corre, venga
    por donde venga.

    Hasta ahora había tres directivas puestas y faltaba la que importa,
    `script-src`, con este motivo escrito: la aplicación carga el SDK del
    proveedor de pagos, y una lista mal armada rompe los cobros en silencio.

    Era un motivo honesto y también una excusa cómoda. Lo que faltaba era el
    inventario, y hacerlo llevó una tarde:

      * el `index.html` construido tiene UN script, el nuestro;
      * no hay NINGUN script en línea en el build;
      * no hay `eval` en el paquete;
      * el único origen externo de scripts es el SDK del proveedor de pagos.

    Con eso, `script-src` puede ir sin `'unsafe-inline'` ni `'unsafe-eval'`,
    que es la diferencia entre una política que sirve y una decorativa: con
    `'unsafe-inline'` puesto, un XSS inyectado en la página corre igual.

POR QUE ARRANCA EN MODO REPORTE

    El inventario dice qué carga la aplicación *hoy, en el build*. Lo que un
    SDK de terceros pide en tiempo de ejecución —otro dominio para un iframe de
    tarjeta, un endpoint de telemetría— no se ve leyendo el código.

    Así que la política sale primero como `Content-Security-Policy-Report-Only`:
    el navegador NO bloquea nada y avisa lo que habría bloqueado. Con unos días
    de tráfico real se sabe si falta algo, se completa, y recién ahí se pasa a
    bloquear cambiando una variable de entorno.

    Publicar una política que bloquea sin haberla mirado con tráfico real es
    exactamente la forma de romper los pagos en silencio que motivó no ponerla.

COMO SE PRENDE

    CSP_MODO=exigir      bloquea de verdad
    CSP_MODO=reporte     sólo avisa   (el valor por omisión)
    CSP_MODO=apagado     no manda nada

    El valor por omisión no bloquea: una política mal armada que se despliega
    sola un viernes es peor que no tenerla.
"""
import os

# Dónde vive el SDK del proveedor de pagos y sus recursos. Se nombran por
# dominio y no con un comodín general: `https:` a secas en `script-src` deja
# entrar a cualquiera, que es casi como no tener la directiva.
PAGOS = ("https://sdk.mercadopago.com https://*.mercadopago.com "
         "https://*.mlstatic.com")

# LOS DOMINIOS DE MERCADO LIBRE, Y POR QUE ESTAN APARTE.
#
# El SDK de pagos es de Mercado Pago, pero su antifraude corre bajo dominios de
# MERCADO LIBRE, que es otra cosa. No se ve leyendo el código: aparece recién
# cuando alguien abre el formulario de tarjeta. Medido en producción, con la
# política en modo reporte, los avisos fueron éstos:
#
#     frame-src       https://www.mercadolibre.com
#     connect-src     https://api.mercadolibre.com/tracks
#     connect-src     https://www.mercadolibre.com/jms/lgz/fingerprint/...
#     connect-src     https://www.mercadolibre.com/jms/lgz/background/etid
#
# ESTO ES EXACTAMENTE PARA LO QUE SE PUSO EL MODO REPORTE. El comentario de más
# arriba, escrito el día que se armó la política, decía: «lo que un SDK de
# terceros pide en tiempo de ejecución —otro dominio para un iframe de tarjeta,
# un endpoint de telemetría— no se ve leyendo el código». Era eso, literal.
#
# Si se hubiera pasado a bloquear sin esto, el cobro con tarjeta se rompía. Y no
# con un error claro: el formulario de Mercado Pago habría fallado por dentro y
# el cliente habría visto «Pago no aprobado», que le echa la culpa a su tarjeta.
#
# Van los dominios enteros y no un comodín: son de un tercero grande, con muchos
# subdominios que no tienen nada que ver con cobrar.
ANTIFRAUDE = "https://www.mercadolibre.com https://api.mercadolibre.com"

# LO QUE TODAVIA IMPIDE PASAR A `exigir`, Y NO LO ARREGLAN LOS DOMINIOS.
#
# En la misma tanda de avisos apareció éste:
#
#     directiva=script-src-elem origen=inline desde=https://sdk.mercadopago.com
#
# `desde` es el archivo que INYECTO el script (`source-file`). O sea: el SDK de
# pagos crea un `<script>` EN LINEA dentro de NUESTRA página. No es un dominio
# que falte —es código sin dirección propia— así que no se permite agregando
# nada a estas listas.
#
# Las tres salidas posibles, ninguna gratis:
#
#   · `'unsafe-inline'` en `script-src`. Deja la directiva decorativa: un XSS
#     inyectado en la página corre igual. Es lo que esta política vino a
#     evitar, así que no.
#   · El hash del script. No sirve si el contenido cambia entre versiones del
#     SDK, y habría que perseguirlo en cada actualización de ellos.
#   · `'strict-dynamic'`: un script ya confiado puede crear otros. Cubre este
#     caso, pero cambia cómo se evalúa la directiva entera —las listas de
#     dominios dejan de mirarse en los navegadores que lo soportan— y eso hay
#     que medirlo con tráfico antes, no decidirlo de una.
#
# MIENTRAS TANTO LA POLITICA SIGUE EN `reporte`, y este comentario está acá
# para que nadie prenda `CSP_MODO=exigir` creyendo que con los dominios
# alcanzaba. Si se prende hoy, el cobro con tarjeta se rompe.

# El medidor de visitas de Cloudflare. NO ESTA EN NUESTRO HTML: lo inyecta
# Cloudflare al servir la página, mientras «Web Analytics» esté prendido.
#
# ACA DECIA QUE NO SE PODIA FIRMAR CON UN `nonce` PORQUE EL HTML LO SERVIA
# CLOUDFLARE PAGES. Era falso, y se comprobó: `nixpacks.toml` compila el
# frontend y `server.py` lo sirve desde `frontend/dist`, o sea que lo sirve
# ESTA aplicación. La prueba de que la cabecera sale de acá es que los avisos
# de CSP existen: no hay archivo `_headers` en Pages, así que si la página la
# sirviera Pages el navegador no tendría ninguna política que reportar.
#
# Como la cabecera sale de acá, ahora lleva un `nonce` y Cloudflare lo copia a
# lo que inyecta. Se deja el dominio igual: firmar el medidor depende de que
# Cloudflare lo trate como script inyectado, y eso no está comprobado con
# tráfico real. Sacarlo sin comprobarlo rompería los únicos números de visitas
# que hay.
#
# Se permite en vez de apagarlo porque son los únicos números de visitas que
# hay, y porque Cloudflare ya sirve la página entera: si fuera hostil, esta
# política no cambiaría nada. Van los dos dominios porque son distintos y hacen
# cosas distintas: de uno viene el script, al otro le manda los datos.
MEDIDOR_SCRIPT = "https://static.cloudflareinsights.com"
MEDIDOR_DATOS = "https://cloudflareinsights.com"

# Entrar con Google. El script viene de su dominio, el botón lo dibuja Google
# adentro de un iframe suyo, sus estilos vienen de ahí, y la credencial vuelve
# por una conexión al mismo sitio. Se nombran las rutas exactas que documenta
# Google y no el dominio entero: `accounts.google.com` sirve muchas cosas.
GOOGLE_INGRESO_SCRIPT = "https://accounts.google.com/gsi/client"
GOOGLE_INGRESO = "https://accounts.google.com/gsi/"
GOOGLE_INGRESO_ESTILO = "https://accounts.google.com/gsi/style"

DIRECTIVAS = {
    # Lo que no esté nombrado abajo, sólo desde nuestro origen.
    "default-src": "'self'",

    # LA QUE IMPORTA. Sin `'unsafe-inline'` y sin `'unsafe-eval'`: el build no
    # genera scripts en línea ni usa `eval`, así que no hacen falta — y con
    # cualquiera de los dos puesto, un XSS inyectado en la página corre igual y
    # la directiva no sirve para nada.
    "script-src": f"'self' {PAGOS} {MEDIDOR_SCRIPT} {GOOGLE_INGRESO_SCRIPT}",

    # Los estilos SI llevan `'unsafe-inline'`: la aplicación tiene más de 4500
    # `style={{...}}` de React. Un estilo no ejecuta código; sacarlo sería
    # reescribir toda la interfaz para ganar muy poco.
    "style-src": f"'self' 'unsafe-inline' {GOOGLE_INGRESO_ESTILO}",

    # Las imágenes vienen de todos lados: `data:` para los base64 que ya están
    # guardados, `blob:` para la vista previa de un archivo recién elegido, y
    # `https:` porque hay comprobantes viejos apuntando a dominios que no
    # elegimos. Una imagen no ejecuta nada; el riesgo acá es que una dirección
    # ajena sepa cuándo se abrió la pantalla, no que corra código.
    "img-src": "'self' data: blob: https:",
    "font-src": "'self' data:",
    "media-src": "'self' data: blob:",

    # A dónde puede hablar la aplicación. Nuestra API es del mismo origen.
    "connect-src": f"'self' {PAGOS} {ANTIFRAUDE} https://api.qrserver.com {MEDIDOR_DATOS} {GOOGLE_INGRESO}",

    # El formulario de tarjeta del proveedor va en un iframe suyo, y su
    # antifraude abre otro bajo el dominio de Mercado Libre.
    "frame-src": f"{PAGOS} {ANTIFRAUDE} {GOOGLE_INGRESO}",

    # No hay plugins. Es un camino clásico para ejecutar código con un archivo
    # que subió un usuario.
    "object-src": "'none'",

    # Un `<base href>` inyectado cambia a dónde apunta TODA ruta relativa de la
    # página, scripts incluidos.
    "base-uri": "'self'",

    # Un formulario inyectado que postea las credenciales a otro lado.
    "form-action": "'self'",

    # Lo mismo que `X-Frame-Options`, que los navegadores nuevos ya no miran.
    "frame-ancestors": "'none'",
}

RUTA_DE_REPORTE = "/api/csp-reporte"


# ══════════════════════════════════════════════════════════════════════════
# EL NONCE, Y QUE PROBLEMA CONCRETO VINO A RESOLVER
# ══════════════════════════════════════════════════════════════════════════
#
# Cloudflare inyecta en la página un script EN LINEA para su detección de bots
# («JavaScript Detections»). Se reconoce por `__CF$cv$params` y por el camino
# `/cdn-cgi/challenge-platform/`. No es nuestro y no se puede sacar del HTML,
# porque no está en el HTML: lo mete Cloudflare al pasar la respuesta.
#
# Con `script-src` sin `'unsafe-inline'` —que es como tiene que estar— el día
# que la política pase a bloquear, la aplicación frenaría ese script. Apareció
# en los avisos del modo reporte, que es exactamente para lo que ese modo está.
#
# POR QUE NO SE ARREGLA CON UN HASH
#
#     El contenido de ese script cambia en cada respuesta, así que su hash
#     también. Un hash fijo en la política no serviría ni una vez.
#
# COMO SE ARREGLA
#
#     Cloudflare LEE la cabecera `Content-Security-Policy` de la respuesta del
#     origen y, si encuentra un `nonce`, se lo copia al script que inyecta. O
#     sea que alcanza con mandar uno distinto por respuesta desde acá.
#
#     Tres condiciones, las tres cumplidas:
#       · la política viaja como cabecera HTTP y no en un `<meta>`  → `cabecera()`
#       · `script-src 'self'` cubre `/cdn-cgi/challenge-platform/`  → ya estaba
#       · el origen no manda `Cache-Control: no-transform`          → no lo manda
#
# UNO NUEVO POR RESPUESTA, Y NO UNO FIJO
#
#     Un nonce fijo es lo mismo que `'unsafe-inline'` con pasos de más: quien
#     lo lea una vez puede firmar el script que quiera inyectar. Todo su valor
#     está en que sea impredecible y en que no sirva dos veces.
#
# LOS SCRIPTS DE LA APLICACION NO LO USAN
#
#     El build no genera ninguno en línea: el `index.html` tiene un solo
#     `<script>` y va con `src=`, que `'self'` ya permite. El nonce está para
#     lo que inyecta Cloudflare, no para nosotros. Si algún día el build empieza
#     a generar scripts en línea, habrá que ponérselo también — y hay una guarda
#     que avisa si eso pasa.
_BYTES_DEL_NONCE = 16


def nuevo_nonce() -> str:
    """Un nonce distinto por respuesta.

    `secrets` y no `random`: el segundo es predecible desde unas pocas salidas,
    y un nonce que se puede adivinar no es un nonce.
    """
    import base64
    import secrets

    return base64.b64encode(secrets.token_bytes(_BYTES_DEL_NONCE)).decode("ascii")


def modo() -> str:
    valor = (os.getenv("CSP_MODO", "reporte") or "").strip().lower()
    return valor if valor in ("exigir", "reporte", "apagado") else "reporte"


def politica(*, con_reporte: bool = True, nonce: str | None = None) -> str:
    """La política armada. Con `nonce`, se lo agrega a `script-src`.

    Se agrega SOLO a `script-src`. En `style-src` no haría nada bueno: esa
    directiva lleva `'unsafe-inline'` por los 4500 estilos de React, y un nonce
    junto a `'unsafe-inline'` hace que los navegadores IGNOREN el
    `'unsafe-inline'` — o sea que romperíamos todos los estilos de la
    aplicación para no ganar nada.
    """
    directivas = dict(DIRECTIVAS)
    if nonce:
        directivas["script-src"] = f"{directivas['script-src']} 'nonce-{nonce}'"
    partes = [f"{nombre} {valor}" for nombre, valor in directivas.items()]
    if con_reporte:
        # `report-uri` está en desuso pero es lo que entienden casi todos los
        # navegadores hoy; `report-to` es el reemplazo. Se mandan los dos.
        partes.append(f"report-uri {RUTA_DE_REPORTE}")
        partes.append("report-to csp")
    return "; ".join(partes)


def cabecera(nonce: str | None = None):
    """El nombre de la cabecera y su valor, o `None` si está apagada.

    En modo reporte el navegador NO bloquea nada: sólo avisa lo que habría
    bloqueado. Es el mismo texto de política, en la otra cabecera.

    EL NONCE VA TAMBIEN EN MODO REPORTE, y eso importa: si sólo fuera al
    bloquear, los avisos seguirían mostrando el script de Cloudflare como si
    fuera a romperse, y no habría forma de saber —antes de bloquear— que la
    firma funciona. El modo reporte tiene que ensayar la política de verdad.
    """
    actual = modo()
    if actual == "apagado":
        return None
    if actual == "exigir":
        return ("Content-Security-Policy", politica(nonce=nonce))
    return ("Content-Security-Policy-Report-Only", politica(nonce=nonce))
