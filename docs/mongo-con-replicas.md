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
> P2P, conciliación) escribe en una sola operación, y el saldo del cliente va
> junto con su línea del libro…

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


---

# Segunda parte: tres miembros

**Qué se gana:** una copia viva de la base. Con un solo miembro, si ese Mongo
se cae o se daña su disco, la aplicación se queda sin base hasta restaurar el
respaldo. Con tres, si se cae **uno**, otro toma su lugar en unos diez
segundos, sin perder datos, y la aplicación sigue.

**Lo que no cambia:** tres miembros aguantan que se caiga **uno**. Si se caen
dos, el que queda no acepta escrituras: es así a propósito, para que dos copias
nunca escriban cosas distintas. Para ese caso está la sección 12.

**Lo que cuesta:** Mongo pasa de un contenedor y un disco a tres. Los tres
quedan en la misma región de Railway: protegen de que se caiga un contenedor o
se dañe un disco, no de que se caiga la región entera.

**Cómo se sabe que anda:** la salud de la aplicación tiene una línea
**réplicas**. Hoy dice «un solo miembro»; al terminar tiene que decir
«3 miembros: 1 primario y 2 al día». Si un día una copia se cae o se atrasa,
esa línea se pone en rojo y la campana del equipo avisa.

Todo lo de esta parte se ensayó con MongoDB 8, con los comandos copiados letra
por letra: desde un Mongo como el de producción hasta tres miembros, con uno
tirado abajo de golpe, con dos caídos y con la vuelta a uno solo (sección 13).

## 8. La llave del conjunto, calculada de la contraseña

Hoy la llave del conjunto (`/data/db/rs.key`) se genera al azar y sólo la tiene
el Mongo de hoy. Los miembros nuevos necesitan **la misma**, y nadie tiene que
verla ni copiarla. Por eso, desde esta parte, cada miembro la calcula a partir
de la contraseña de Mongo que Railway ya guarda: todos llegan a la misma llave
sin que viaje a ningún lado.

En el servicio **MongoDB** → Settings → Deploy → **Custom Start Command**,
reemplazá el comando de la sección 1 por éste, en una sola línea:

```
bash -c 'K=/data/db/rs.key; if [ -z "$RAILWAY_PRIVATE_DOMAIN" ]; then echo "SIN RED PRIVADA: Mongo arranca sin replicas"; exec docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false; fi; printf "%s" "rs0:$MONGO_INITDB_ROOT_PASSWORD" | sha256sum | cut -c1-64 > $K; chmod 400 $K; chown mongodb:mongodb $K 2>/dev/null; SH=$(command -v mongosh || command -v mongo); YO="$RAILWAY_PRIVATE_DOMAIN:27017"; (until $SH --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "try { rs.status().ok } catch (e) { rs.initiate({_id: \"rs0\", members: [{_id: 0, host: \"$YO\"}]}).ok }" 2>/dev/null | grep -q 1; do sleep 2; done; echo "REPLICAS LISTAS"; if [ "$SOLO_ESTE_MIEMBRO" = "si" ]; then $SH --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --eval "const c = rs.conf(); c.members = c.members.filter(m => m.host === \"$YO\"); rs.reconfig(c, {force: true}); print(\"QUEDA UN SOLO MIEMBRO\")"; fi) & exec docker-entrypoint.sh mongod --replSet rs0 --keyFile $K --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false'
```

Es el mismo de antes con dos cambios: la llave se calcula en vez de sortearse,
y aparece la variable `SOLO_ESTE_MIEMBRO` de la sección 12, que no está puesta
y no hace nada hasta que se la ponga.

Desplegá. En el registro de MongoDB tiene que aparecer **REPLICAS LISTAS**, como
siempre, y la salud tiene que seguir en `bien`. Es un reinicio de medio minuto.

## 9. Dos servicios de Mongo nuevos, vacíos

Hacé esto dos veces, una para **MongoDB2** y otra para **MongoDB3** (así, sin
guión: esos nombres se usan en la sección 11).

1. En el proyecto: **+ New** → **Database** → **MongoDB**. Crea el servicio con
   su disco. Cambiale el nombre a `MongoDB2` (o `MongoDB3`).
2. **La misma versión de Mongo que el de hoy.** En el servicio **MongoDB** →
   Settings → **Source**, mirá la imagen (por ejemplo `mongo:8.0.x`) y poné la
   misma en el nuevo. Mezclar versiones en un conjunto trae problemas.
3. En **Variables** del servicio nuevo, agregá estas tres, tal cual. Son
   *referencias*: Railway pone el valor, nadie lo ve ni lo copia.

   | Variable | Valor |
   |---|---|
   | `PRIMARIO` | `${{MongoDB.RAILWAY_PRIVATE_DOMAIN}}` |
   | `USUARIO_RAIZ` | `${{MongoDB.MONGO_INITDB_ROOT_USERNAME}}` |
   | `CLAVE_RAIZ` | `${{MongoDB.MONGO_INITDB_ROOT_PASSWORD}}` |

4. En Settings → Deploy → **Custom Start Command**, pegá esto, en una sola línea:

   ```
   bash -c 'K=/data/db/rs.key; printf "%s" "rs0:$CLAVE_RAIZ" | sha256sum | cut -c1-64 > $K; chmod 400 $K; chown mongodb:mongodb $K 2>/dev/null; unset MONGO_INITDB_ROOT_USERNAME MONGO_INITDB_ROOT_PASSWORD; SH=$(command -v mongosh || command -v mongo); (until $SH --host "rs0/$PRIMARIO:27017" --quiet -u "$USUARIO_RAIZ" -p "$CLAVE_RAIZ" --authenticationDatabase admin --eval "const yo = \"$RAILWAY_PRIVATE_DOMAIN:27017\"; if (!rs.conf().members.some(m => m.host === yo)) rs.add({host: yo, priority: 0.5}); print(\"SUMADO\")" 2>/dev/null | grep -q SUMADO; do sleep 5; done; echo "MIEMBRO SUMADO") & exec docker-entrypoint.sh mongod --replSet rs0 --keyFile $K --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false'
   ```

5. Desplegá. En el registro del servicio nuevo tiene que aparecer, en uno o dos
   minutos, **MIEMBRO SUMADO**. Después copia todos los datos del primero, y
   mientras tanto la salud dice que está «copiando los datos por primera vez».

Qué hace el comando: calcula la llave igual que el primero; arranca Mongo
**vacío**, como miembro del conjunto `rs0`; y en paralelo le pide al primero
que lo sume, con prioridad más baja, así el de hoy sigue siendo el principal
mientras esté bien. Si se reinicia, ve que ya está sumado y no hace nada más.
Borra las variables de usuario de la plantilla antes de arrancar: un miembro
nuevo tiene que empezar vacío y recibir los usuarios del primero, no crear los
suyos.

## 10. Comprobar

En la salud de la aplicación (tarjeta del panel, o la línea `SALUD|` del
registro del backend), **réplicas** tiene que decir:

> 3 miembros: 1 primario y 2 al día

Si dice «copiando los datos por primera vez», esperá: depende de cuántos datos
haya. Si dice «sin responder» por más de unos minutos, mirá el registro de ese
servicio.

## 11. Que el backend conozca los tres

Mientras el backend esté andando, se entera solo de los tres miembros. Pero si
**arranca** —un despliegue, un reinicio— justo cuando el Mongo de hoy está
caído, sólo conoce su dirección y no puede conectarse. Se arregla diciéndole
las tres.

En el servicio del **backend** → **Variables** → `MONGO_URL`:

1. Copiá el valor que tiene hoy a un lugar seguro, para poder volver. **No lo
   pegues en ningún chat.**
2. Reemplazalo por esto, tal cual:

   ```
   mongodb://${{MongoDB.MONGO_INITDB_ROOT_USERNAME}}:${{MongoDB.MONGO_INITDB_ROOT_PASSWORD}}@${{MongoDB.RAILWAY_PRIVATE_DOMAIN}}:27017,${{MongoDB2.RAILWAY_PRIVATE_DOMAIN}}:27017,${{MongoDB3.RAILWAY_PRIVATE_DOMAIN}}:27017/?replicaSet=rs0&authSource=admin
   ```

3. Desplegá el backend.

Igual que las variables de la sección 9, son referencias: la contraseña no se
ve ni se copia. Se ensayó: con el Mongo de hoy muerto de golpe, un backend que
arranca con esta dirección se conecta y escribe en unos diez segundos.

## 12. Si se caen dos: dejar uno solo

Con dos miembros caídos, el que queda no acepta escrituras y la aplicación no
puede operar. Si hace falta volver a escribir **ya**, sin esperar a que los
otros vuelvan:

1. En el servicio **MongoDB** → **Variables**, agregá `SOLO_ESTE_MIEMBRO` con el
   valor `si`, y desplegá.
2. En su registro tiene que aparecer **QUEDA UN SOLO MIEMBRO**. Desde ese
   momento es un conjunto de un miembro, como el de la primera parte, y
   escribe.
3. **Borrá la variable `SOLO_ESTE_MIEMBRO`** y desplegá otra vez. Si queda
   puesta, cada reinicio vuelve a sacar a los demás.

Cuando los otros dos vuelvan a andar, con reiniciarlos se suman solos.

## 13. Volver atrás, a un solo miembro

1. La sección 12 completa: `SOLO_ESTE_MIEMBRO=si`, esperar «QUEDA UN SOLO
   MIEMBRO», borrar la variable.
2. Borrá los servicios **MongoDB2** y **MongoDB3**, con sus discos.
3. En el backend, `MONGO_URL` vuelve al valor que copiaste en la sección 11.

**No** borres MongoDB2 y MongoDB3 antes del paso 1: el de hoy quedaría solo en
un conjunto de tres, sin mayoría, y dejaría de escribir.

El comando de arranque del MongoDB de hoy puede quedar como el de la sección 8.
Para volver al de antes de todo (el de la plantilla de Railway):

```
docker-entrypoint.sh mongod --ipv6 --bind_ip ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false
```
