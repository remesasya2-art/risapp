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

DIRECTIVAS = {
    # Lo que no esté nombrado abajo, sólo desde nuestro origen.
    "default-src": "'self'",

    # LA QUE IMPORTA. Sin `'unsafe-inline'` y sin `'unsafe-eval'`: el build no
    # genera scripts en línea ni usa `eval`, así que no hacen falta — y con
    # cualquiera de los dos puesto, un XSS inyectado en la página corre igual y
    # la directiva no sirve para nada.
    "script-src": f"'self' {PAGOS}",

    # Los estilos SI llevan `'unsafe-inline'`: la aplicación tiene más de 4500
    # `style={{...}}` de React. Un estilo no ejecuta código; sacarlo sería
    # reescribir toda la interfaz para ganar muy poco.
    "style-src": "'self' 'unsafe-inline'",

    # Las imágenes vienen de todos lados: `data:` para los base64 que ya están
    # guardados, `blob:` para la vista previa de un archivo recién elegido, y
    # `https:` porque hay comprobantes viejos apuntando a dominios que no
    # elegimos. Una imagen no ejecuta nada; el riesgo acá es que una dirección
    # ajena sepa cuándo se abrió la pantalla, no que corra código.
    "img-src": "'self' data: blob: https:",
    "font-src": "'self' data:",
    "media-src": "'self' data: blob:",

    # A dónde puede hablar la aplicación. Nuestra API es del mismo origen.
    "connect-src": f"'self' {PAGOS} https://api.qrserver.com",

    # El formulario de tarjeta del proveedor va en un iframe suyo.
    "frame-src": PAGOS,

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


def modo() -> str:
    valor = (os.getenv("CSP_MODO", "reporte") or "").strip().lower()
    return valor if valor in ("exigir", "reporte", "apagado") else "reporte"


def politica(*, con_reporte: bool = True) -> str:
    partes = [f"{nombre} {valor}" for nombre, valor in DIRECTIVAS.items()]
    if con_reporte:
        # `report-uri` está en desuso pero es lo que entienden casi todos los
        # navegadores hoy; `report-to` es el reemplazo. Se mandan los dos.
        partes.append(f"report-uri {RUTA_DE_REPORTE}")
        partes.append("report-to csp")
    return "; ".join(partes)


def cabecera():
    """El nombre de la cabecera y su valor, o `None` si está apagada.

    En modo reporte el navegador NO bloquea nada: sólo avisa lo que habría
    bloqueado. Es el mismo texto de política, en la otra cabecera.
    """
    actual = modo()
    if actual == "apagado":
        return None
    if actual == "exigir":
        return ("Content-Security-Policy", politica())
    return ("Content-Security-Policy-Report-Only", politica())
