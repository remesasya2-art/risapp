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

## Qué errores 4xx vale la pena guardar

La pestaña «Errores» guarda los 500 y los 5xx que el código levanta a
propósito. Los 4xx no: un 404 o un 403 es el sistema diciendo que no, no algo
roto, y guardarlos llena el registro de cosas que funcionan bien.

Pero algunos 4xx sí cuentan una historia. Un 400 repetido en la misma pantalla
puede ser un formulario que pide algo que nadie entiende; una tanda de 401 en
una sola cuenta puede ser alguien probando contraseñas.

**Qué falta:** elegir cuáles, de a uno y con el motivo al lado. No es «prender
los 4xx»: es nombrar los tres o cuatro que valen. Ver
`backend/services/errores.py`.

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
