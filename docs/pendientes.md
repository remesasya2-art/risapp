# Pendientes

Lo que quedó sin hacer y por qué, para que no se pierda entre una sesión y la
siguiente.

**Lo de seguridad no está acá.** Vive en la sección 11 del
`docs/dossier-tecnico-de-seguridad.md`, que es su lugar y ya existía. Dos
listas de pendientes de seguridad, que tarde o temprano se contradicen, es
peor que una sola aunque esté en un documento largo. Ahí están, entre otros:
el modo TLS de Cloudflare, `preload` en HSTS, el segundo factor que un cliente
activa y nadie le pide, el piso de pedidos que todavía no corta, y pasar la
política de contenido a bloquear.

Acá queda lo de producto.

## Prender el botón de Google

El código está desplegado y probado. No se ve porque falta la variable
`GOOGLE_CLIENT_ID` en el servidor, y sin ella el botón no se dibuja y la
puerta contesta que no está disponible. Es un identificador público, no un
secreto.

Quedó postergado a propósito: crear el cliente OAuth en la consola de Google
no tiene plan gratuito permanente, y no vale pagarlo antes de tener clientes
reales.

**Qué falta, cuando llegue el momento:** crear un ID de cliente OAuth de tipo
«aplicación web» con los orígenes `https://risappbr.com` y
`https://www.risappbr.com`, y poner ese identificador en el servidor. No hace
falta secreto de cliente ni URI de redirección.
