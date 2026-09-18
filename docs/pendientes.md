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

## Lo que falta para integrar un proveedor de cambio

Ya está puesto el terreno: cada envío a Venezuela puede guardar con qué tasa
se le cobró al cliente, cuánto costó y cuánto quedó; los dos números se cargan
desde el panel; y hay una sola función —`comisiones.tasa_de_costo`— que el día
de la integración pasa de leer el panel a preguntarle al proveedor.

**Lo primero, y es tuyo:** pedirle al proveedor la documentación de
integración y el acceso de pruebas. Sin eso, todo lo de abajo es adivinanza, y
adivinar la forma de una API que no se vio es trabajo que se tira.

**Qué falta, cuando lleguen esos papeles:**

- **El receptor de sus avisos.** Ya está anotado en la sección 11 del dossier
  como decisión deliberada: no se escribe hasta que publiquen su esquema de
  firma. Un receptor que valida mal da una sensación de seguridad que no
  existe.
- **Conciliar contra su extracto.** Para eso está el campo `proveedor_ref`,
  que hoy se guarda vacío en cada operación. Agregarlo ahora es un campo;
  agregarlo con un año de operaciones encima es una migración.
- **Usar `services/firma.py`.** Está escrito y probado, y **no lo llama
  nadie**: firma un pedido saliente con HMAC-SHA256 y marca de tiempo, que es
  lo que pide casi cualquier proveedor. Si la integración se cae del plan,
  este archivo se borra.
- **Las demás vías.** Hoy sólo el envío a Venezuela calcula comisión, porque
  es la única con margen en la tasa. Las otras necesitan decidir primero de
  dónde sale la ganancia.

**Ojo con los dos decimales.** La tasa de costo se guarda con dos decimales,
que sobran para bolívares por real. Para una tasa cercana a uno —el precio de
un dólar cripto en reales— no alcanzan, y hay un test que se pone rojo si
alguien lo intenta.

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
