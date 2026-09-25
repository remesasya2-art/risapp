# Pasar el Mongo de Railway a un conjunto de réplicas

> **Hecho en producción el 25 de septiembre de 2026.** La salud de la
> aplicación pasó a `SALUD| bien`, con «transacciones» en verde. Esta guía queda
> para volver atrás (sección 5) o para repetirlo en otro entorno.

**Qué se gana:** que cada movimiento de plata del cliente se escriba entero o no
se escriba. Un Mongo de **un solo nodo** no tiene *transacciones* —la forma de
agrupar varias escrituras para que queden todas o ninguna—. La aplicación está
preparada para usarlas: cuando el Mongo las tiene, las usa sola. Lo que hace
falta es un ajuste del Mongo, no del código.

Un *conjunto de réplicas* (en inglés, *replica set*) es la forma que tiene Mongo
de trabajar con transacciones. Acá va a ser un conjunto **de un solo miembro**:
el mismo Mongo de siempre, con los mismos datos, arrancado de otra manera.

Todo se hace desde la pantalla de Railway. **No hay que tocar código, ni la
variable `MONGO_URL`, ni copiar ninguna contraseña.** La única llave nueva que
hace falta la genera el propio Mongo adentro de su disco, y no sale de ahí.

Todo lo que dice este documento es **reversible**. La vuelta atrás está en la
sección 5 y también se probó.

---

## 0. Antes de empezar

- **Elegí una hora tranquila.** Mongo se reinicia una vez. Durante ese medio
  minuto la aplicación no puede leer ni escribir, y quien esté usándola ve un
  error y tiene que reintentar.
- **Mirá que el respaldo de hoy exista.** En el panel, arriba, «Salud de la
  aplicación» → la línea **respaldo** tiene que estar con ✓. El cambio no toca
  los datos —se probó—, pero un respaldo del día no cuesta nada.

---

## 1. Pegar el comando de arranque

En Railway: el proyecto → el servicio de **MongoDB** → **Settings** →
sección **Deploy** → **Custom Start Command**.

**Antes de borrar lo que haya ahí, copialo:** es lo que se restaura para volver
atrás. En producción el campo ya traía, de la plantilla de Railway:

```
docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false
```

Esas opciones —escuchar por IPv6, que es por donde anda la red privada de
Railway, y no juntar datos de diagnóstico— se conservan en el comando nuevo.
La primera versión de esta guía no las traía; se corrigieron antes de usarla.

Reemplazalo por esto, **en una sola línea, tal cual**:

```
bash -c 'K=/data/db/rs.key; if [ -z "$RAILWAY_PRIVATE_DOMAIN" ]; then echo "SIN RED PRIVADA: Mongo arranca sin replicas"; exec docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false; fi; [ -f $K ] || head -c 512 /dev/urandom | base64 -w0 > $K; chmod 400 $K; chown mongodb:mongodb $K 2>/dev/null; SH=$(command -v mongosh || command -v mongo); (until $SH --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "try { rs.status().ok } catch (e) { rs.initiate({_id: \"rs0\", members: [{_id: 0, host: \"$RAILWAY_PRIVATE_DOMAIN:27017\"}]}).ok }" 2>/dev/null | grep -q 1; do sleep 2; done; echo "REPLICAS LISTAS") & exec docker-entrypoint.sh mongod --replSet rs0 --keyFile $K --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false'
```

Qué hace, en orden:

1. **Si no hay red privada, no cambia nada.** Mongo arranca como hoy y deja en
   el registro «SIN RED PRIVADA». Es un resguardo: sin red privada, el conjunto
   de réplicas no tendría un nombre con el que encontrarse a sí mismo.
2. **La llave del conjunto.** Un conjunto de réplicas con usuario y contraseña
   exige un archivo de llave. Se genera al azar la primera vez, se guarda en el
   disco de Mongo (`/data/db/rs.key`) y en los arranques siguientes se reusa.
   Nadie la ve ni la copia: es interna de Mongo.
3. **Arranca Mongo** como conjunto de réplicas llamado `rs0`, con los mismos
   datos, el mismo usuario y la misma contraseña de siempre.
4. **En paralelo, lo inicia.** La primera vez, un conjunto de réplicas tiene
   que *iniciarse* una sola vez, diciéndole cuál es su dirección. Eso lo hace
   solo, con el usuario que Railway ya tiene configurado, y cuando termina
   escribe **REPLICAS LISTAS** en el registro. En los arranques siguientes ve
   que ya está iniciado y sólo escribe el mensaje.

## 2. Desplegar y mirar el registro de Mongo

Guardá y desplegá el servicio de MongoDB. En **Deployments → View logs** del
servicio de MongoDB, esperá hasta **un minuto** a que aparezca:

    REPLICAS LISTAS

- **Apareció:** seguí con el paso 3.
- **Apareció «SIN RED PRIVADA»:** Mongo quedó como estaba, no se rompió nada.
  No sigas: la red privada del proyecto está apagada y hay que verlo antes.
- **Pasaron dos minutos y no apareció ninguno de los dos:** **volvé atrás ya**
  (sección 5). Mientras un conjunto de réplicas no está iniciado, Mongo no
  acepta escrituras, y la aplicación no puede operar.

## 3. Reiniciar el backend

La aplicación se fija **una vez, al arrancar**, si Mongo tiene transacciones, y
lo recuerda. Hay que reiniciarla para que se entere: en Railway, el servicio del
**backend** → **Deployments** → los tres puntos del último → **Redeploy**.

## 4. Comprobar

En el panel, «Salud de la aplicación», la línea **transacciones** tiene que
estar con ✓ y decir:

> Mongo es un conjunto de réplicas: el motor contable (lotes de USDT, ventas
> P2P, conciliación) escribe en una sola operación, y el saldo en RIS del
> cliente va junto con su línea del libro…

El mismo texto aparece cada cinco minutos en el registro del backend, en la
línea que empieza con `SALUD|`, que tiene que decir `SALUD| bien`.

Justo después del reinicio es normal ver una o dos veces

    SALUD| me salteé la vuelta: el turno lo tiene otro proceso

Durante el reinicio conviven el contenedor viejo y el nuevo, y la revisión la
hace uno solo; el turno se libera solo a los cuatro minutos. Para no esperar,
abrí el panel: la tarjeta de salud revisa en el momento, sin turno.

Hasta hoy esa línea decía «Mongo es de UN solo nodo» con ✗. Si sigue diciendo
eso después del paso 3, el backend no se reinició o Mongo no quedó como
conjunto de réplicas: mirá otra vez el registro del paso 2.

---

## 5. Volver atrás

Si algo no se ve bien, en cualquier momento:

1. Servicio de **MongoDB** → Settings → Deploy → en **Custom Start Command**
   poné de nuevo el comando que había antes (sección 1), y desplegá. En
   producción es:

   ```
   docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false
   ```

   Si el campo estaba vacío antes, dejalo vacío.
2. **Redeploy** del backend.

Mongo vuelve a arrancar como un solo nodo, con todos sus datos, y la aplicación
vuelve a trabajar sin transacciones, como hasta hoy. El archivo de la llave
queda en el disco sin molestar; si más adelante se vuelve a pegar el comando,
lo reusa.

---

## 6. Si alguien se conecta a Mongo desde afuera de Railway

La aplicación no cambia nada: su `MONGO_URL` sigue igual, y el controlador de
Mongo descubre solo que ahora es un conjunto de réplicas.

Un programa que se conecte **desde afuera** de Railway —Compass, una terminal en
una computadora— puede quedarse esperando: el conjunto se anuncia con su
dirección *interna* de Railway, que desde afuera no existe. La solución es
agregarle a la dirección de conexión de ese programa:

    directConnection=true

(con `?` si la dirección no tiene otros parámetros, o con `&` si ya tiene).

---

## 7. Qué se probó, y qué no se puede probar desde acá

**Se probó**, con MongoDB 8 en una máquina de ensayo, arrancando desde un Mongo
de un solo nodo con usuario, contraseña y datos —el mismo punto de partida que
Railway—, y con el comando de arriba copiado letra por letra:

- que los datos que había antes siguen ahí;
- que queda como conjunto de réplicas y una transacción se confirma;
- que sin usuario y contraseña no se entra;
- que un segundo arranque reusa la misma llave y no hace nada nuevo;
- que sin red privada arranca como hoy;
- que la vuelta atrás (sección 5) deja Mongo como un solo nodo, con los datos,
  leyendo y escribiendo.

El ensayo se repitió con las opciones de la plantilla de Railway (IPv6 y sin
diagnóstico): mismo resultado, y el diagnóstico sigue apagado.

**Lo que sólo se podía ver en Railway**: cómo ejecuta el comando de arranque,
que el disco de Mongo esté montado en `/data/db` y que la imagen traiga
`mongosh`. Se vio el 25 de septiembre de 2026, en producción:

- en el registro de Mongo, el comando reintentó iniciar el conjunto cada dos
  segundos —se ve como «Connection not authenticating» desde `127.0.0.1`, con
  el controlador `nodejs`, que es `mongosh`— y dejó de intentar al lograrlo;
- el backend, al reiniciarse, creó sus índices sin error: Mongo aceptaba
  escrituras;
- la salud dijo `SALUD| bien`, con «Mongo es un conjunto de réplicas», y la
  base pasó a responder en 1 ms.
