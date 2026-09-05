# Dossier técnico de seguridad — RIS App

**Operador:** SAIPHA Servicios Digitais
**Plataforma:** risappbr.com
**Versión del documento:** 1.0
**Fecha:** septiembre de 2026

---

## 0. Para qué sirve este documento y cómo leerlo

Este dossier describe los controles técnicos que la plataforma tiene **hoy,
funcionando en producción**. Está escrito para que un tercero —un proveedor de
servicios de pago, un banco, un auditor— pueda evaluar el riesgo de integrarse
con nosotros sin tener que creernos nada.

Tres reglas de redacción, y conviene decirlas antes que nada:

1. **No hay nada aspiracional.** Cada control descrito está implementado. Lo
   que falta está en la sección 11, con nombre y apellido.
2. **Cada afirmación apunta a un archivo y a una prueba automatizada.** La
   sección 12 es la tabla de verificación. Un control que no se puede señalar
   en el código no está en este documento.
3. **Las cifras son medidas, no estimadas.** Cuando decimos «65 rutas» es
   porque se contaron sobre la aplicación armada, y hay una prueba que falla
   si el número deja de coincidir.

Si algo de acá resulta insuficiente para el proceso de homologación, se puede
pedir el detalle: el código es auditable y las pruebas se pueden correr
delante de quien lo solicite.

---

## 1. Identificación del operador

| | |
|---|---|
| Razón social | J. del Carmen Hernandez Barreto |
| Nombre comercial | SAIPHA Servicios Digitais |
| CNPJ | 66.994.057/0001-61 |
| Domicilio | Rua Monte Roraima, s/n, Bairro Vila Nova, Pacaraima – RR, CEP 69345-000, Brasil |
| Sitio | https://risappbr.com |
| Canal de contacto | Soporte dentro de la aplicación (`/support`) |

La identificación completa está publicada en el documento legal del sitio
(`/legal`), conforme al Decreto 7.962/2013.

---

## 2. Qué es la plataforma, en una página

RIS App es una plataforma de **soluciones digitales** que opera entre Brasil y
Venezuela. Sus funciones principales:

- **Cuenta y saldo del usuario**, con verificación de identidad (KYC) escalonada.
- **Logística de encomiendas**: cotización, despacho, seguimiento y entrega,
  con evidencia fotográfica en cada tramo.
- **Cobros y acreditaciones** a través de proveedores externos (PIX, tarjeta,
  criptoactivos), siempre liquidados contra un libro mayor propio.
- **Panel de administración** con segregación de funciones por permiso.

**Arquitectura.** Backend en Python (FastAPI) sobre MongoDB; frontend en React.
Todo el tráfico va por HTTPS. El almacenamiento de objetos (fotos, comprobantes)
está separado de la base de datos.

**Superficie de administración medida:** 209 rutas de administración. Las 65
que atienden colaboradores están gobernadas por el catálogo de permisos
(sección 4). Una ruta de administración que no figure en ese catálogo **se
niega a todo el que no sea el super administrador**, así que el resto de la
superficie queda reservado a él o a puentes autenticados con clave de API.

---

## 3. Identidad y acceso

### 3.1 Contraseñas

- Algoritmo: **bcrypt** con sal por contraseña (`bcrypt.gensalt()`).
- No se guarda, registra ni transmite ninguna contraseña en claro.
- La comparación se hace con `bcrypt.checkpw` (tiempo constante).

`backend/utils/security.py`

### 3.2 Sesiones

- **No se usan JWT.** Los tokens de sesión son **opacos**: 256 bits de
  `secrets.token_urlsafe(32)` —generador criptográfico del sistema operativo—
  guardados en la colección `user_sessions` y resueltos contra la base en cada
  petición.
- Consecuencia deliberada: **una sesión se puede revocar de verdad**. No hay
  nada firmado que siga siendo válido después de cerrarla.
- **Caducidad diferenciada:** 30 minutos para `admin` y `super_admin`, 7 días
  para usuarios comunes.
- Al cerrar sesión se borran **todas** las sesiones del usuario, no sólo la
  actual.
- **Cambiar la contraseña cierra las sesiones abiertas.** Esta línea es nueva, y
  la anterior situación merece contarse: hasta septiembre de 2026, las **cinco**
  formas de cambiar una contraseña —el cambio propio, los dos reseteos por
  correo, el reseteo que hace un administrador y el alta del personal— escribían
  la contraseña nueva y no tocaban las sesiones.

  Eso rompía la única defensa que una persona sabe usar sola. Alguien entra a
  una cuenta ajena, la dueña lo sospecha y hace lo que todo el mundo sabe hacer:
  cambia la contraseña. Y el intruso seguía adentro, con la sesión que ya tenía.
  El caso del administrador era peor: nos avisan que una cuenta está tomada, la
  reseteamos y contestamos «listo» — una certeza falsa, que es peor que ninguna.

  El cambio propio conserva la sesión desde la que se hace y cierra las demás;
  los otros cuatro caminos cierran todas, porque quien dispara el cambio no es
  quien tiene las sesiones abiertas.
- El repositorio **no contiene ninguna clave de firma de sesión**. Las
  constantes `SECRET_KEY` / `ALGORITHM` fueron eliminadas de `config.py`
  precisamente porque un placeholder en el historial de un repositorio es una
  trampa para quien mañana agregue firma.

`backend/config.py`, `backend/routes/dependencies.py`, `backend/routes/auth.py`,
`backend/services/sesiones.py`, `backend/tests/test_sesiones_al_cambiar_clave.py`

### 3.3 Segundo factor obligatorio para el personal

**Ningún colaborador con acceso al panel puede tener una sesión sin segundo
factor.** La regla no distingue por antigüedad ni por rol dentro del personal:

```
ROLES_CON_PANEL = {"agent", "admin", "super_admin"}
```

Quien pertenece a ese conjunto —o está marcado como personal— entra por un
camino en dos pasos:

1. `POST /auth/login-password` valida la contraseña y **no emite sesión**:
   devuelve un *pending token* de 5 minutos.
2. `POST /auth/2fa/verify` valida el código TOTP y recién ahí emite la sesión.

Si el colaborador **todavía no tiene 2FA**, el paso 1 devuelve
`enrollment_required=true` y un *pending token* de enrolamiento. **No hay
sesión hasta que el segundo factor esté puesto.** No existe la opción de
posponerlo.

- TOTP estándar (RFC 6238), con QR para cualquier autenticador.
- **10 códigos de respaldo** de un solo uso, guardados con bcrypt.

`backend/services/personal.py`, `backend/routes/auth.py`, `backend/routes/security_2fa.py`

### 3.4 Primer acceso del personal: invitación de un solo uso

Un colaborador dado de alta **no tiene contraseña ni correo verificado**, y por
diseño ningún camino de recuperación le sirve. El primer acceso es por
invitación explícita del super administrador:

- Se emite un token de un solo uso. **En la base se guarda sólo el SHA-256.**
  El token en claro existe una única vez: en el correo.
- Emitir una invitación nueva **anula la anterior antes de insertar la nueva**,
  así que nunca hay una ventana con dos llaves vivas.
- El consumo es **atómico**: `usada: False` va dentro del filtro del
  `find_one_and_update`, no en una comprobación previa. Dos peticiones
  simultáneas no pueden consumir la misma invitación.
- La contraseña se valida **antes** de consumir el token, para que un error de
  tipeo no queme la invitación.
- Activar la cuenta **no emite sesión**: emite el *pending token* de
  enrolamiento de 2FA. El primer acceso de un colaborador termina, siempre, con
  el segundo factor puesto.

`backend/services/invitaciones.py`, `backend/routes/auth.py`

### 3.5 Llave de seguridad y biometría (WebAuthn)

Como factor adicional, la plataforma admite WebAuthn/FIDO2:

- Registro con `userVerification: REQUIRED` y
  `authenticatorAttachment: PLATFORM` — la huella o el rostro del propio
  dispositivo, no una llave USB anónima.
- Verificación de firma con `require_user_verification=True`.
- El origen esperado está **fijado en el servidor** a los dominios propios; no
  se lee de la petición.
- El estado del segundo factor reportado hacia el resto del sistema es el que
  **efectivamente informó el autenticador** (`user_verified`), no un valor fijo.
- Antes de verificar la firma se comprueba que la cuenta no esté borrada,
  bloqueada ni suspendida. El orden importa: una cuenta cerrada no debería
  llegar a la criptografía.

`backend/routes/webauthn_login.py`

### 3.6 Límite de intentos

Todas las rutas que se pueden llamar **sin sesión** tienen límite por IP real
del cliente, o están declaradas como excepción con el motivo escrito.

Esa frase es nueva. Hasta la revisión de septiembre de 2026 este documento
decía «todos los puntos de entrada sensibles», y no era cierto: **nueve rutas
públicas no tenían ningún tope**. Entre ellas el registro de cuentas —que
además manda correos desde nuestro dominio—, el reseteo de contraseña con
contraseña temporal —cada llamada corre `bcrypt`, que gasta CPU a propósito—,
el reto de WebAuthn —que contesta distinto según si la cuenta existe, o sea que
era una lista de correos— y el seguimiento público de envíos.

Se corrigió el hecho y se corrigió el documento. Y para que la frase deje de
depender de que alguien la mantenga, hay una prueba que **recorre todas las
rutas sin sesión** y exige que cada una tenga tope o esté declarada con su
motivo: una ruta pública nueva sin tope pone la suite en rojo el día que se
escribe.

Detalle no menor: el límite se aplica con una función explícita
(`frenar(request, alcance, regla)`) y **no** con un decorador sobre funciones
anidadas. La implementación anterior registraba una regla nueva por cada
petición, y el consumo acumulado terminaba bloqueando el inicio de sesión de
**todos** los usuarios tras unas decenas de accesos, sin recuperación posible
salvo reinicio. Está medido y corregido, con prueba de regresión.

**Y la IP con la que se cuenta ya no la elige quien hace el pedido.** Este es
el hallazgo que vuelve condicional a todo lo demás de esta sección, así que
conviene decirlo entero. La IP se resolvía tomando el **primer** valor de
`X-Forwarded-For`, que es una cabecera que manda el cliente. Un proxy no la
reemplaza: le agrega la IP real **al final**. Así que un pedido enviado con

    X-Forwarded-For: 1.2.3.4

llegaba como «1.2.3.4, ‹ip real›», y esa lectura devolvía el valor elegido por
quien atacaba. Cambiándolo en cada intento, cada uno caía en un contador
distinto: **ningún** límite de la aplicación frenaba a nadie. No es que fueran
flojos — no existían.

La cadena se lee ahora de **derecha a izquierda**: el último valor lo escribió
el proxy que tenemos adelante, el único que no se puede falsear desde afuera. Y
antes que eso se prefiere `CF-Connecting-IP`, que la red de distribución escribe
pisando lo que venga.

La misma IP falseable se asentaba en cada envío y en cada línea del libro de
auditoría, o sea en los dos únicos lugares donde después se busca a alguien.
Hay una segunda función, `desde_donde_dice_venir()`, que sí devuelve el primer
valor de la cadena: existe aparte y con ese nombre para registrar e investigar,
nunca para decidir a quién frenar. El nombre es la advertencia.

`backend/services/ip_cliente.py`, `backend/routes/security_2fa.py`,
`backend/tests/test_limite_por_ip.py`, `backend/tests/test_ip_cliente.py`,
`backend/tests/test_puertas_sin_llave.py`

---

## 4. Segregación de funciones

### 4.1 Dónde se decide

Los permisos **no** se comprueban ruta por ruta. Se comprueban en las **dos
dependencias por las que ya pasan todas las rutas de administración**:
`get_admin_user` y `get_crm_user`. Una ruta nueva hereda la comprobación por el
solo hecho de usar el guard de siempre.

- **Catálogo:** 18 permisos. «Ver» y «hacer» están separados, porque leer los
  datos de un cliente y decidir sobre su dinero no son la misma confianza. Los
  tres que mueven dinero están marcados como tales en la propia etiqueta que ve
  quien los otorga (`saldos.ajustar`, `recharges.approve`, `envios.dinero`).
- **Mapa:** 65 pares (método, ruta) → permiso.
- **El super administrador no pasa por el mapa**: los permisos existen para
  repartir trabajo, y él es de quien se reparte.

`backend/services/permisos.py`, `backend/routes/dependencies.py`

### 4.2 Falla cerrado

Una ruta de administración que **no** esté declarada en el mapa **se niega**, y
queda un `ERROR` en el registro con el método, la ruta y a quién se le negó.

Es la decisión de diseño central del módulo. Un mapa incompleto que deja pasar
es exactamente el agujero que se está tapando, y no avisa nunca; uno que frena
se nota el primer día y se arregla agregando una línea. Además hay una prueba
que recorre la aplicación armada y falla si alguna ruta quedó sin mapear, así
que un olvido no llega a producción.

### 4.3 El personal no opera a título personal

Regla: **un colaborador no puede hacer transacciones con su propia cuenta.**

Se implementa con **dos candados**, y la razón es medida: de las diez vías por
las que un usuario mueve dinero, sólo una liquida en el momento del pedido. Las
otras nueve dejan una transacción pendiente o arrancan un cobro externo que
liquida **después**, por webhook.

| Candado | Dónde | Qué ataja |
|---|---|---|
| En la puerta | `Depends(sin_transacciones_personales)` en las rutas de usuario | El pedido, con un mensaje claro |
| En el dinero | `saldos.mover` se niega a mover el saldo de un empleado, venga de donde venga | El webhook, que no tiene puerta |

El segundo es el que cierra la regla. El primero existe para que el colaborador
entienda por qué no puede, en vez de ver un error opaco.

Corolario deliberado: **no se convierte en personal a alguien que tiene saldo.**
Su dinero quedaría encerrado —no podría retirarlo, porque retirar es una
transacción—. El alta se rechaza y se pide vaciar la cuenta primero.

`backend/services/personal.py`, `backend/services/saldos.py`

---

## 5. Integridad del dinero

### 5.1 Aritmética exacta

Todo importe se maneja con `decimal.Decimal` y se persiste como
`bson.Decimal128`. **No hay `float` en el camino del dinero.** El redondeo es
`ROUND_HALF_UP` explícito, con la cantidad de decimales de cada moneda
(2 para fiat, 8 para BTC).

Los dos dueños del saldo —cuentas bancarias y saldo de usuario— más el cobro de
envíos, el libro mayor y la contabilidad se apoyan en este módulo.

`backend/services/money.py`

### 5.2 Libro mayor (append-only)

Cada cambio de saldo escribe una línea inmutable: quién, qué, cuánto, saldo
antes y después, a qué operación pertenece, qué tasa se usó, el beneficiario y
quién lo procesó.

- El módulo **no ofrece función para modificar ni borrar una línea.**
- Registrar nunca rompe la operación: si el libro falla, queda un `ERROR` en el
  registro y la operación sigue. Un libro que tumba una acreditación legítima
  es peor que un libro con un hueco anotado.

`backend/services/ledger.py`

### 5.3 Idempotencia

Las operaciones que crean movimientos aceptan una `idempotency_key` por
intento. Una clave repetida devuelve el resultado original en vez de crear una
segunda operación —doble clic, reintento de red, reenvío de webhook—.

`backend/services/idempotency.py`

### 5.4 Límites y cupos

Dos capas distintas, y la distinción es intencional:

- **Por operación** (iguales para todos): definidos en un único módulo, que el
  servidor valida **antes de escribir en la base** y del que la pantalla lee
  sus números. Antes vivían escritos en el frontend y el servidor no los
  aplicaba: la aplicación prometía un techo que no existía.
- **Por cuenta sin verificar:** 200 RIS acumulados **y** 2 operaciones
  completadas. Se agota con lo que ocurra primero, y **no se renueva por mes**:
  la única salida es verificar la identidad. Cualquier operación por encima de
  200 exige KYC aprobado, porque no hay forma de que entre en el cupo.

`backend/services/limits.py`, `backend/services/kyc_quota.py`

### 5.5 Restricción de jurisdicciones

Para la vía de criptoactivos se aplica `assert_payment_allowed(...)` **antes de
crear el cobro**: bloqueo por país (EE.UU., Reino Unido y los 27 de la UE),
según el ToS del proveedor, **más una declaración explícita del usuario** de que
no es residente ni ciudadano de esas jurisdicciones.

Las dos capas están juntas por una razón que el propio módulo documenta: **el
bloqueo por IP indica desde dónde se conecta el usuario, no su nacionalidad**.
Un ciudadano estadounidense conectado desde otro país pasaría el filtro. Por eso
la IP es la primera capa, la declaración la segunda, y la nacionalidad
verificada en el KYC la más fuerte.

`backend/services/geo_restrictions.py`, `backend/routes/credits.py`

### 5.6 Sin cotización no se cobra

Los envíos con Bitcoin se cobran con dos números: el precio de Bitcoin en
dólares y la tasa USDI → VES. Los dos estaban escritos a mano como valor por
defecto, y los dos fallaban en silencio hacia lados opuestos.

| | Valor por defecto | Qué pasaba si se usaba |
|---|---|---|
| Precio de Bitcoin | 58 500 USD en el caché inicial | Con el bitcoin cerca de 79 000, el cliente pagaba ~36 % de más en bitcoin |
| Tasa USDI → VES | 680,0 al faltar la configuración | Con la real en 270, al beneficiario se le prometían 2,5 veces los bolívares; la diferencia la pone el operador |

Ninguno hacía ruido: la remesa se emitía, el cliente pagaba, el número estaba
mal. Es la decisión que tomó el operador con sus palabras: «mejor que falle por
error de cálculo en la tasa; asumir representa perder o ganar dinero y quiero
ser lo más justo posible».

Lo que se hace cumplir ahora:

- **El caché del precio arranca vacío.** El precio se pide en vivo en cada
  consulta —no hay intervalo de actualización— y la pantalla consulta cada
  diez segundos. Si el proveedor no contesta, se acepta el último precio
  conocido sólo **treinta segundos**: el bitcoin se mueve, y cobrar con el
  precio de hace un minuto es cobrar mal, para un lado o para el otro.
- **La tasa devuelve nada** si falta, si no es un número, o si es cero o
  negativa.
- **`_cotizacion_o_error()` es el único camino** por el que el cobro obtiene
  esas dos cifras, y corta con 503 y un mensaje que una persona entiende.
- **`GET /btc/precio` devuelve nulos** en vez de inventar. La pantalla no
  convierte, no promete y no deja avanzar.

**La antigüedad de la tasa, que es el modo de fallar más probable.** El precio
de Bitcoin se pide en vivo, así que no envejece. La tasa USDI → VES es la
paralela y se fija **a mano**: el raspador que corre solo trae el dólar del BCV
—otro número, otra colección— y nadie lo conecta con esta clave. O sea que el
riesgo real no es que la tasa falte, sino que nadie la toque durante semanas y
se sigan prometiendo bolívares con la de hace un mes.

Por eso se controla contra `EDAD_MAXIMA_DE_LA_TASA` (24 h, un solo número
puesto para ajustarlo a la cadencia con que se fije). Al vencerse, los envíos
con Bitcoin se cortan **y se avisa al super administrador** —una vez por
vencimiento, no una por consulta: la pantalla consulta cada diez segundos y un
aviso que llega cien veces deja de ser un aviso—. El panel muestra desde cuándo
rige la tasa y cuántas horas le quedan, para no enterarse por la notificación,
que es enterarse tarde.

**La ventana del cobro: diez minutos.** Es LA exposición a la volatilidad del
bitcoin. Al generar el cobro quedan fijos los sats que paga el cliente y los
bolívares que recibe el beneficiario; si el precio se mueve en ese rato, la
diferencia la absorbe el operador, con el colchón del margen y la comisión
(~3 %). Eran treinta minutos.

Acortarla obligó a cerrar dos huecos que ya existían y que la ventana más corta
volvía **más** probables, porque más órdenes vencen:

- **El invoice se pedía sin vencimiento propio** y quedaba con el del
  proveedor, mucho más largo. La ventana era sólo del lado nuestro: se podía
  pagar a los cuarenta minutos y la red aceptaba. Ahora se le pide al proveedor
  el mismo vencimiento, con reintento sin ese campo si no lo conoce —adivinar
  el nombre de un campo y errarle no puede costar que no se emita ningún cobro.
- **El webhook acreditaba sin mirar la fecha.** Un pago tardío enviaba
  bolívares calculados con un bitcoin de otro momento; y si la orden estaba
  cancelada, la búsqueda filtraba por «pendiente», no encontraba nada y el
  webhook contestaba «ya procesada»: el cliente pagaba y no quedaba rastro.
  Ahora la orden se busca sin filtrar por estado, un pago fuera de ventana
  queda en `revision_manual` y se avisa al super administrador. No se acredita
  solo y no se ignora: la plata llegó, y qué hacer con ella —devolver o
  completar a la cotización de hoy— es una decisión de negocio.

`backend/routes/btc_lightning.py`, `backend/services/aviso_de_tasa.py`,
`backend/tests/test_cotizacion_btc.py`,
`backend/tests/test_aviso_de_tasa_vencida.py`,
`backend/tests/test_ventana_del_cobro.py`

---

### 5.7 Dónde se miran estos controles

Un control que nadie puede mirar no es un control. Los cuatro de arriba
—solvencia, reconciliación, integridad y quién tiene las llaves del dinero—
tienen una pantalla propia en el panel, **Seguridad financiera**, reservada al
super administrador y de sólo lectura: no cambia un saldo ni corrige un
asiento.

Cada pregunta se contesta con un veredicto y un número, y desde ahí se salta
al detalle contable. La regla de diseño que la ordena es una sola:

> **No saber no es estar bien.** Si una consulta falla, el veredicto es «no se
> pudo comprobar» y nunca verde. Cada bloque se pide y falla por separado, así
> que una consulta caída no deja la pantalla en blanco ni —peor— deja una
> tarjeta en verde que nadie actualizó.

`frontend/src/components/admin/SeguridadFinanciera.jsx`,
`frontend/src/utils/seguridadFinanciera.js`

---

## 6. Trazabilidad

Libro de auditoría único: quién hizo qué, sobre quién, cuándo y desde dónde.

Antes existían cuatro registros distintos, cada uno escrito por un solo módulo,
uno de ellos sin ningún endpoint que lo leyera, y ninguno visible en el panel.
De las 96 rutas de administración que escriben en la base, **sólo cuatro**
dejaban rastro. Aprobar un KYC, aprobar una recarga, suspender a un usuario,
mover la tasa de cambio **u otorgar permisos** no se registraban en ningún lado.

Lo que garantiza el libro actual:

- **Se escribe, nunca se edita ni se borra.** No hay función para modificar una
  línea: el módulo no la ofrece.
- **Cada línea se basta sola.** Guarda nombre y correo del actor, no sólo su
  id, porque dentro de un año ese usuario puede no existir y la línea tiene que
  seguir diciendo quién fue.
- **Estado antes y después.** Un registro que dice «se cambiaron los permisos»
  sin decir de qué a qué no sirve para investigar nada.
- **Fecha y hora en UTC y en hora local de Caracas** —la que usa quien lee el
  panel—.
- **Nunca rompe la operación que audita.**

El otorgamiento de permisos es el asiento que ordena a todos los demás: mover
dinero se anotaba, pero entregarle a una persona *el poder* de mover dinero no.

`backend/services/auditoria.py`, `backend/tests/test_auditoria.py`

### 6.1 Lo que se publica de todo esto, y lo que no

Las páginas públicas prometen el **resultado**; no describen el **mecanismo**.

Durante un tiempo lo describieron. La página «Cómo funciona» enumeraba, para
mostrar seriedad, que el acceso administrativo exige un segundo factor, que la
comprobación de saldos es periódica, y la lista completa de lo que puede hacer
una cuenta interna: aprobar una verificación, aprobar una recarga, **ajustar un
saldo**, cambiar una tasa, modificar permisos. La portada y la política de
privacidad decían además que el segundo factor es obligatorio para el personal.

Nada de eso ayuda a quien está decidiendo si confía, y todo eso ayuda a quien
está mirando por dónde entrar: le nombra la operación que vale la pena tomar
—ajustar un saldo—, le dice qué defensa va a encontrar del otro lado, y le
dice qué tiene que imitar una pantalla falsa dirigida a un empleado para que el
empleado no sospeche. «Periódica», además, es la palabra que anuncia que hay
una ventana.

Lo que quedó publicado: que todo movimiento de saldo deja un asiento, que un
asiento no se reescribe, que toda intervención del equipo queda asentada, y que
el usuario puede pedir ese detalle. Todas son promesas comprobables y ninguna
es un plano.

Dos distinciones que costaron una corrección y conviene no perder:

- **Ofrecerle el segundo factor al usuario se sigue diciendo.** Es una función
  que él puede prender; contarla lo protege y no le sirve a nadie más. Lo que
  no se publica es qué se le exige al **personal**. La regla no está en la
  palabra sino en de quién se habla, y por eso el test busca las dos cosas en
  la misma oración y no una lista de palabras prohibidas.
- **La política de privacidad sigue declarando que hay medidas técnicas y
  organizativas**, que es lo que pide la LGPD (art. 46). Lo que dejó de hacer
  es enumerarlas: el detalle se documenta acá y se pone a disposición de la
  autoridad de control o de una auditoría que lo pida.

`backend/tests/test_lenguaje_de_las_paginas_publicas.py`

---

## 7. Datos personales y documentos

### 7.1 Documentos de identidad y evidencias

Las fotos —documento de identidad, comprobante de despacho, evidencia de
entrega— se guardan en colección propia y en almacén de objetos (S3/R2,
`signature_version="s3v4"`), **nunca dentro del documento de negocio**.

Tres validaciones no opcionales al recibir un archivo:

1. **El tipo se mira en los bytes**, no en el `content-type` ni en la
   extensión: las dos las elige quien sube el archivo. Un ejecutable renombrado
   a `.jpg` pasa cualquier control de nombre y ninguno de firma.
2. **Tope de tamaño medido sobre lo efectivamente leído**, no sobre lo
   declarado.
3. **Se quitan los metadatos EXIF** —incluida la geolocalización— antes de
   guardar.

Además se deduplica por SHA-256, y el orden de escritura es objeto primero,
ficha después: al revés, un fallo deja una ficha apuntando a nada.

`backend/services/envios_archivos.py`, `backend/services/envios_almacen.py`

**El camino viejo, y por qué necesitaba su propia validación.** Lo de arriba
vale para las fotos de envíos. Los documentos del KYC, los comprobantes de
recarga y los adjuntos del chat son anteriores y viajan de otra forma: como
**texto** adentro del JSON, normalmente un `data:image/jpeg;base64,…`. Ese
texto se guardaba sin mirarlo.

O sea que el campo era, en la práctica, texto libre elegido por quien sube el
archivo — y quien lo abría después, desde el panel, era un administrador. Un
`javascript:…` guardado ahí y abierto con `window.open` no abre nada: ejecuta
ese código en la sesión de quien hizo click. La cookie es `httpOnly` y no se
puede robar, pero no hace falta robarla: el código ya está corriendo adentro.

Se cerró en las dos puntas, con una **lista de lo permitido** y no de lo
prohibido — los navegadores ignoran espacios y caracteres de control adentro
del esquema, así que un filtro que busca la palabra «javascript» no la
encuentra en `java<TAB>script:`:

- Al **entrar**: `data:image/` salvo SVG, ruta propia o `https://`, con tope de
  8 MB. Nada más.
- Al **abrir**: el mismo criterio en el navegador, porque es lo único que
  protege de lo que ya estaba guardado antes de que existiera la validación.

Y tres barridos automáticos exigen que ningún `href={…}`, ningún
`window.open(…)` y ninguna ruta que guarde un campo de imagen se salteen el
filtro. El agujero no vuelve porque alguien lo deshaga: vuelve porque la
próxima pantalla no lo llama.

`backend/services/imagen_recibida.py`, `frontend/src/utils/urlDeArchivo.js`

### 7.2 Minimización en reportes

Los reportes y exportaciones **omiten las imágenes**; se transportan
referencias, no contenido. Un comprobante no tiene por qué viajar hasta una
planilla.

`backend/services/reportes.py`

### 7.3 Los documentos, cifrados en la base

Los documentos de identidad se pueden guardar **cifrados con clave propia**
(AES-256-GCM), de modo que quien llegue a la base sin permiso —una cadena de
conexión filtrada, un respaldo copiado a otro lado, el proveedor de
alojamiento— vea texto cifrado y no pueda abrirlo. No protege del
administrador que entra a revisar un KYC: para eso está su trabajo, y contra
eso protegen la contraseña, el segundo factor y el libro de auditoría.

**Está apagado por omisión, y eso es parte del diseño.** Cifrar crea un riesgo
nuevo y peor que el que resuelve: perder la llave es perder todos los
documentos, sin recuperación. Para una operación que arranca, quedarse sin
poder probar a quién verificó puede ser peor que una filtración. Así que:

- nada se prende solo, ni con un valor raro en la variable de entorno;
- leer funciona con las dos formas, así que la migración es gradual y volver
  atrás es posible;
- la llave anterior se sigue probando al leer: una rotación a medio camino no
  destruye nada;
- hay cómo comprobar que la llave respaldada es la correcta **sin restaurar
  nada** —una huella de ocho caracteres que no la revela, y un testigo en la
  base— porque «respaldá la llave» sin forma de verificarlo no es un control;
- si falta la llave, falla el KYC con un error claro y **las remesas siguen
  andando**;
- y si el modo dice cifrar pero la llave no sirve, **se corta antes de
  escribir**: guardar en claro creyendo que se cifró es la peor de las tres
  situaciones, porque no se nota nunca.

El tamaño no crece: se cifran los bytes de la imagen y no su representación en
base64, de modo que el documento ocupa lo mismo más 40 bytes. Importa porque un
documento de Mongo no puede pasar de 16 MB y una verificación con cuatro fotos
ya se acerca.

Se cifran las cuatro imágenes. `cpf_number` no: está indexado y cifrarlo
rompería las búsquedas.

El procedimiento para prenderlo —incluido qué hacer si algo sale mal— está en
`docs/la-llave-del-cofre.md`, escrito para que lo siga alguien sin
conocimientos de criptografía.

`backend/services/cofre.py`, `backend/scripts/cofre.py`,
`backend/tests/test_cofre.py`

### 7.4 Qué queda escrito en los registros

Un registro no es un archivo privado. Los de esta plataforma los ve cualquiera
con acceso al panel del proveedor de alojamiento, se copian a servicios de
terceros para poder buscarlos, se guardan más tiempo que los datos que
describen, y sobreviven a cualquier borrado que se haga en la base. Todo lo que
se escribe ahí sale del perímetro que la plataforma controla.

Y esto importa especialmente acá: un volcado de registros con correos,
teléfonos y documentos de esta operación no es «una filtración de datos», es
una lista de personas de una comunidad concreta con cuánto envía cada una y a
quién.

La revisión de septiembre de 2026 encontró **35 puntos** que escribían datos
personales o cuerpos ajenos completos. Los dos peores:

- El cuerpo **entero** que manda el proveedor de pagos en cada notificación. Hoy
  son campos inocuos; el día que el proveedor agregue el nombre del pagador,
  entra al registro sin que nadie lo haya decidido.
- Cuando el libro de auditoría fallaba al escribir, se registraba **la línea
  completa**, con el antes y el después del cambio: el documento más sensible
  del sistema, copiado al lugar menos protegido, justo cuando algo ya había
  salido mal.

El criterio que se aplicó: donde se puede se registra el identificador interno
—que no dice nada fuera de la base—; donde el correo hace falta de verdad se
enmascara conservando el dominio; y de un cuerpo ajeno se copian **sólo las
claves elegidas a mano**, de modo que lo que el proveedor agregue mañana no
entra solo.

Una prueba recorre **todos** los registros de la aplicación: uno nuevo con un
dato personal adentro pone la suite en rojo el día que se escribe.

`backend/services/registro.py`, `backend/tests/test_registros_sin_datos.py`

---

## 8. Comunicaciones

### 8.1 TLS verificado, sin excepciones silenciosas

Toda llamada saliente verifica el certificado del servidor. La única
excepción histórica —el consumo de la tasa oficial del BCV— fue eliminada:

```python
BCV_TLS_INSEGURO = os.environ.get("BCV_TLS_INSEGURO", "").strip() in ("1", "true", "True")
async with httpx.AsyncClient(verify=not BCV_TLS_INSEGURO, ...) as client:
```

- **Falla cerrado**: si el certificado no valida, la obtención falla con un
  `ERROR` que nombra la causa y el arreglo. No devuelve un número posiblemente
  manipulado.
- La válvula de escape existe, requiere una variable de entorno explícita, y
  **deja un `WARNING` en cada obtención** mientras esté activa. No se puede
  encender y olvidar.

`backend/services/bcv_scraper.py`, `backend/tests/test_tls_verificado.py`

### 8.2 Cabeceras y origen

Toda respuesta —incluidas las de error— lleva:

| Cabecera | Valor | Qué evita |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Que el navegador vuelva a hablar en claro con el dominio |
| `X-Frame-Options` | `DENY` | Que la aplicación se embeba en un iframe ajeno (*clickjacking*) |
| `X-Content-Type-Options` | `nosniff` | Que el navegador adivine el tipo de un archivo subido por un usuario |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Que una dirección con identificadores se filtre al salir del sitio |

**Política de contenido (CSP), incluida `script-src`.** Un XSS es código ajeno
corriendo en el origen de la aplicación con la sesión de quien mira; las
validaciones de entrada y de salida cierran los caminos conocidos, y la política
de contenido cierra el resto.

La versión anterior de este documento decía que `script-src` no estaba porque la
aplicación carga el SDK del proveedor de pagos y una lista mal armada rompería
los cobros. Era cierto y también una excusa cómoda: lo que faltaba era el
inventario. Hecho el inventario —el `index.html` construido tiene un solo
script, el propio; no hay ningún script en línea en el build; no hay `eval` en
el paquete; el único origen externo es el SDK de pagos— la directiva se pudo
escribir **sin `'unsafe-inline'` y sin `'unsafe-eval'`**, que es la diferencia
entre una política que protege y una decorativa: con cualquiera de las dos, un
XSS inyectado corre igual.

| Directiva | Valor | Por qué |
|---|---|---|
| `script-src` | propio + SDK de pagos | Sin `'unsafe-inline'` ni `'unsafe-eval'` |
| `style-src` | propio + `'unsafe-inline'` | Más de 4500 estilos en línea de React; un estilo no ejecuta código |
| `img-src` | propio, `data:`, `blob:`, `https:` | Hay comprobantes viejos en dominios que la plataforma no eligió |
| `object-src` | `'none'` | Plugins: camino clásico de ejecución con un archivo subido |
| `base-uri` | propio | Un `<base>` inyectado mueve **toda** ruta relativa, scripts incluidos |
| `form-action` | propio | Un formulario inyectado que postea las credenciales a otro sitio |
| `frame-ancestors` | `'none'` | Clickjacking, para los navegadores que ya no miran `X-Frame-Options` |

**Sale en modo reporte y no bloqueando.** El inventario describe lo que carga el
build; lo que un SDK ajeno pide en tiempo de ejecución no se ve leyendo el
código. Así que el navegador avisa lo que habría bloqueado, sin bloquear, y esos
avisos se recogen en un endpoint propio. Con tráfico real se completa la lista y
recién ahí se pasa a bloquear, cambiando una variable de entorno —sin desplegar
código, y con un tercer valor que la apaga del todo como salida de emergencia.

Publicar una política que bloquea sin haberla mirado con tráfico real es
exactamente la forma de romper los cobros en silencio que motivó no ponerla.

El endpoint que recoge los avisos es público por necesidad —el navegador los
manda sin sesión— y está tratado como tal: tope de intentos, tope de tamaño, y
**no registra el cuerpo que llega**; lee dos campos conocidos y los recorta.
Tampoco anota la dirección de la página, que diría qué pantalla estaba mirando
una persona concreta.

**CORS con lista blanca explícita** de orígenes propios, todos `https`. No hay
comodín: `allow_origins=["*"]` junto a `allow_credentials=True` es la
combinación que permite a cualquier sitio hacer peticiones con la cookie de
sesión de la víctima.

**La documentación automática de la API no se publica.** El marco de trabajo
sirve `/docs`, `/redoc` y `/openapi.json` sin pedir nada: el mapa completo de
las 337 rutas con sus parámetros y sus tipos, incluidas las de administración y
las de mantenimiento. Ninguna deja de estar protegida por eso, pero es la mitad
del trabajo de quien busca por dónde entrar. Salen apagadas; una variable de
entorno las prende en desarrollo, y el valor por omisión es apagado.

**Tope al tamaño del cuerpo de un pedido: 40 MB.** Antes no había ninguno, y un
cuerpo de varios gigabytes se leía entero en memoria antes de que ninguna ruta
lo mirara — sin necesitar credencial alguna, porque la validación de la ruta
corre después de que el cuerpo ya se armó. Se rechaza temprano al que declara de
más y se **cuenta** lo que llega, porque el `Content-Length` lo manda el cliente
y el que miente lo declara chico.

`backend/server.py`, `backend/services/csp.py`, `backend/routes/csp_reporte.py`,
`backend/services/limite_de_cuerpo.py`, `backend/tests/test_cabeceras_de_seguridad.py`,
`backend/tests/test_superficie_de_la_api.py`, `backend/tests/test_politica_de_contenido.py`

### 8.3 Autenticación con terceros: capa OAuth 2.0

Cliente OAuth 2.0 *client credentials* propio, escrito para las integraciones
con proveedores de pago:

- **Renovación anticipada** con margen de 60 segundos: no se espera al
  vencimiento para pedir el token nuevo.
- **Un solo pedido de token bajo concurrencia**: `asyncio.Lock` con doble
  comprobación. Veinte llamadas simultáneas al arrancar producen **una** ida al
  proveedor, no veinte.
- Reloj **monótono** (`time.monotonic()`), inmune a ajustes de hora del sistema.
- **Sin reintento ante 4xx**: un `400`/`401`/`403` es un problema de
  credenciales, y reintentarlo sólo agrega ruido y riesgo de bloqueo. Reintento
  sólo ante fallos transitorios, y **un** reintento ante `401` en mitad de una
  llamada (token revocado del otro lado).
- El secreto está marcado `repr=False`: no aparece en un volcado de excepción
  ni en un registro.
- Cabecera de idempotencia configurable, para que el proveedor reciba la clave
  con el nombre que espere.

`backend/services/oauth_cliente.py`, `backend/tests/test_oauth_cliente.py` (20 pruebas)

### 8.4 Webhooks entrantes

Los receptores de webhook **verifican la firma del emisor** antes de tocar
nada:

- Proveedor de criptoactivos: HMAC de la cabecera `x-nowpayments-sig`,
  verificada **sobre el cuerpo crudo** de la petición y antes de intentar
  interpretarlo. Firma inválida o ausente → `401`, sin efecto alguno.
- Mensajería: `X-Twilio-Signature` validada contra la URL pública y el cuerpo.
- Proveedor de pagos: HMAC sobre el manifiesto firmado, y **la marca de tiempo
  se verifica** contra una ventana de cinco minutos. Sin esa verificación —que
  faltaba hasta septiembre de 2026— una notificación firmada capturada una vez
  seguía siendo válida para siempre. Acreditar dos veces no podía (el pago tiene
  que seguir pendiente y se le vuelve a preguntar al proveedor), pero cada
  reenvío gastaba una consulta a una API limitada y llenaba el registro de
  eventos indistinguibles de los legítimos.
- Puentes internos con clave de API: comparación con `hmac.compare_digest`
  (tiempo constante) y **falla cerrado** si la clave no está configurada. Una
  prueba recorre **todas** las rutas de los dos puentes y exige que cada una
  reciba la cabecera, la mire, y la mire *primero*: así es como se rompió una
  vez `/withdrawal/create`, donde nadie sacó el control — alguien agregó la ruta
  siguiente y se olvidó.

**Postura declarada:** no escribimos un receptor de webhook para un proveedor
cuyo esquema de firma no conocemos. Un endpoint público que acredita saldo sin
verificar quién llama es lo peor que se puede dejar «preparado». Cuando el
proveedor publique su esquema, se implementa y se prueba contra él.

`backend/routes/credits.py`, `backend/routes/transactions.py`, `backend/routes/webhooks.py`, `backend/routes/gestor_pix.py`, `backend/routes/btc_lightning.py`, `backend/routes/adminbrl_bridge.py`, `backend/routes/centro_gestion.py`, `backend/tests/test_webhooks_firmados.py`, `backend/tests/test_puente_con_llave.py`

### 8.5 Pedidos salientes con credenciales nuestras

Hay un solo lugar donde el servidor sale a internet **con nuestro usuario y
contraseña de un proveedor** hacia una dirección que arma con lo que le
mandaron: el proxy que trae las fotos que llegan por mensajería. El navegador no
puede pedirlas —las credenciales no salen del servidor—, así que la pantalla
pide una ruta nuestra y el servidor va a buscarlas.

Esa ruta pegaba el camino recibido a la URL del proveedor sin mirarlo. Como el
marco de trabajo deja que ese parámetro se trague las barras, el pedido lo
escribía entero quien llamaba: cualquiera con sesión podía pedir
`…/Messages.json` y recibir **los cuerpos de todos los SMS de la cuenta** — que
es por donde viajan los códigos de verificación que la plataforma le manda a la
gente. También las grabaciones, las llamadas y los números.

Cuatro cosas lo cierran:

1. **El camino tiene una sola forma posible y se exige entera**, anclada en las
   dos puntas. Sin el ancla del final, `…/Media/ME…/../../Messages.json` empieza
   igual que un pedido válido.
2. **La cuenta tiene que ser la nuestra.** Aunque el formato calce.
3. **Los redireccionamientos no se siguen con las credenciales puestas.** El
   proveedor contesta con un salto a su red de distribución; ese salto se sigue
   a mano, una vez, sin autenticación y sólo hacia sus dominios. Seguirlo con la
   cabecera puesta es entregar el usuario y la contraseña a donde apunte el
   `Location`.
4. **Tope de bytes, y el tipo de contenido se acota a imágenes.** Un `text/html`
   servido desde una ruta nuestra es una página que corre en nuestro origen.

El mismo pedido estaba escrito una segunda vez, en una rutina de mantenimiento,
y ahí decidía a dónde ir con `"api.twilio.com" in url`: una subcadena, no un
dominio — `https://cualquier-cosa.example/?x=api.twilio.com` la pasaba, y ese
pedido salía con las credenciales adentro. Peor: el valor venía de un campo que
hasta esta revisión nadie validaba al guardar. Las dos entradas usan ahora la
misma función, porque tener el mismo pedido escrito dos veces **era** el
problema.

`backend/routes/media.py`, `backend/tests/test_media_twilio.py`

---

## 9. Continuidad y degradación

Criterio general, aplicado de forma consistente: **la falla de un componente
nuestro no se le cobra al usuario, y la falla de un control de seguridad sí
frena la operación.**

- Si el almacén de objetos no responde al subir, el archivo se guarda en la
  base y el despacho continúa.
- Si el libro de auditoría falla, la operación se completa y queda un `ERROR`.
- Si la idempotencia falla, deja pasar: es preferible arriesgar un duplicado
  raro que impedir una operación real.
- Si el certificado TLS no valida, **la obtención falla**.
- Si una ruta no tiene permiso declarado, **se niega**.

Las dos últimas son de seguridad. Las tres primeras, de disponibilidad. La
diferencia no es accidental.

---

## 10. Aseguramiento de calidad

- **Suite automatizada:** 94 archivos de prueba sobre el backend. Última
  ejecución completa: **2381 pruebas superadas, 102 omitidas, 0 fallidas**
  (las omitidas requieren credenciales de proveedores externos). Se corre en
  cada cambio.
- **Revisión de seguridad completa del repositorio, septiembre de 2026.** Se
  recorrieron las 337 rutas con sus guardias, se buscaron secretos incrustados,
  inyección en las consultas, referencias directas a objetos ajenos y
  dependencias con vulnerabilidades publicadas. Encontró ocho defectos —dos
  críticos— y todos están corregidos con prueba de regresión. Están descritos en
  las secciones 3.6, 7.1, 8.2, 8.4 y 8.5 de este mismo documento, cada uno
  diciendo qué estaba mal y no sólo qué hay ahora.

  Lo que **no** encontró, y también es un resultado: ningún secreto incrustado
  en el código, ninguna consulta armada con un diccionario del usuario, las
  contraseñas con `bcrypt` y sal, los identificadores de sesión de
  `secrets.token_urlsafe(32)`, y los dos puentes con clave de API completos —
  ninguna ruta suya quedó sin control.
- **Segunda tanda de la revisión, septiembre de 2026.** Enfocada en lectura no
  autorizada de datos. Se recorrieron TODAS las consultas a colecciones de
  datos personales verificando que cada una esté atada a su dueño —el resultado
  fue limpio: no hay ninguna ruta por la que un usuario lea los datos de otro—,
  se barrieron los registros, y se revisó qué pasa con las sesiones al cambiar
  una contraseña. De ahí salieron los tres hallazgos de las secciones 3.2, 7.3
  y 8.2.
- **Dependencias:** `pip-audit` sobre las versiones fijadas. Se pasó de 124
  advertencias en 22 paquetes a 22 en 4, subiendo diecinueve dentro de la misma
  versión mayor y verificando la suite completa después. Las cuatro que quedan
  están en la sección 11, con el motivo de cada una.
- **Pruebas de regresión por incidente:** cada defecto encontrado deja una
  prueba que falla si vuelve. Los casos de esta clase incluyen el agotamiento
  del límite por IP, la ruta de administración sin permiso, la cotización
  vencida sin camino de retorno y la verificación TLS.
- **Pruebas de mutación** sobre los módulos de seguridad: se rompe cada
  garantía a propósito y se comprueba que una prueba se ponga en rojo. Un
  mutante que sobrevive indica una prueba débil, no código seguro. La práctica
  detectó, entre otras, una comprobación que aceptaba `CROSS_PLATFORM` donde
  debía exigir `PLATFORM`, y una prueba de concurrencia cuyas corrutinas nunca
  llegaban a solaparse.

  Las pruebas que respaldan este dossier pasaron por la misma disciplina. Se
  introdujeron ocho defectos a propósito —igualar la duración de la sesión del
  administrador a la del cliente, agregarle al libro mayor una función para
  editar líneas, desactivar el bloqueo por jurisdicción, dejar la declaración
  marcada por omisión, correr el guardia de jurisdicción después de validar la
  moneda, quitar `X-Frame-Options`, abrir el CORS con comodín y acortar el
  HSTS— y los ocho pusieron en rojo alguna prueba.

  La revisión de septiembre de 2026 sumó **46 mutantes** sobre los módulos que
  tocó. Murieron 44. Los dos que sobrevivieron dicen más que los otros
  cuarenta y cuatro:

  - Uno mostró que la limpieza de caracteres de control del filtro de
    direcciones **no es lo que protege**: con una lista de lo permitido,
    `java<TAB>script:` cae por no estar en la lista, no por la limpieza.
    Quedó escrito en el módulo, porque el comentario anterior daba a entender
    lo contrario.
  - El otro descubrió una **prueba que faltaba**: nadie cubría qué pasa cuando
    el secreto del webhook de pagos no está configurado. O sea que la conducta
    más peligrosa de todas —una variable de entorno olvidada convirtiendo en
    abierto el receptor que acredita saldo— no estaba respaldada por nada. Se
    escribió la prueba y el mutante murió.

  Un mutante que sobrevive es una prueba débil o una creencia equivocada. Las
  dos veces fue eso, y las dos veces valió más que un barrido limpio.
- **Prueba de alcanzabilidad de rutas:** detecta rutas duplicadas que el
  enrutador nunca atiende. Ese defecto ya había convertido en decorativas nueve
  comprobaciones de permiso: quien leía el código concluía que el KYC estaba
  protegido, y no lo estaba.

---

## 11. Lo que falta

Esta sección existe porque un dossier sin ella no es creíble.

| Pendiente | Estado | Qué lo destraba |
|---|---|---|
| **mTLS con certificado ICP-Brasil A1** | No implementado | Confirmar si el producto contratado lo exige. La emisión del certificado tiene plazo real; conviene resolverlo antes de la homologación. |
| **Receptor de webhook del proveedor de pagos** | Deliberadamente no escrito | Que el proveedor publique su esquema de firma. Ver 8.4. |
| **Política PLD/FT formal** | Borrador redactado, sin aprobar | Cinco decisiones de negocio del operador, marcadas `[PROPUESTO]` en el borrador: umbral por operación, umbral acumulado, qué se considera sospechoso en esta operación, a quién y en qué plazo se reporta, y quién es el responsable designado. Requiere revisión de abogado brasileño. Ver `docs/politica-pld-ft.md`. |
| **Pasar la política de contenido a bloquear** | Implementada, en modo reporte | Unos días de tráfico real y mirar los avisos que recoge `/api/csp-reporte`. Si no hay ninguno, `CSP_MODO=exigir` la pasa a bloquear sin desplegar código. Si los hay, dicen exactamente qué falta agregar. Ver 8.2. |
| **`cryptography` con vulnerabilidades publicadas** | 46.0.7; el arreglo está en 49.0.0 | Un salto de tres versiones mayores. Media aplicación depende de ella y la suite no ejerce los caminos de red reales, así que no hay forma de comprobar acá que no rompa nada. Requiere una prueba en un entorno de ensayo. Junto con `black` (herramienta de desarrollo), `ecdsa` (sin versión arreglada publicada) y `litellm` (no se importa en el código propio) son las 22 advertencias que quedan de las 124 originales. |
| **Cada medio atado a su dueño** | No implementado | El proxy de medios deja que cualquiera con sesión pida el comprobante de cualquier otro **si conoce los tres identificadores**, que son 34 caracteres cada uno y no se adivinan. El secreto es hoy el identificador mismo. Atarlo al dueño requiere guardar esa relación, que no existe. Decisión consciente, anotada en `backend/routes/media.py`. |
| **Cifrado de documentos en reposo** | Implementado, apagado por omisión | Es una decisión del operador, no técnica. El mecanismo está y probado (ver 7.4); prenderlo requiere generar la llave, respaldarla en tres lugares y comprobar cada copia con `verificar`. El procedimiento está en `docs/la-llave-del-cofre.md`. |
| **Prueba de intrusión externa** | No realizada | Contratación. Las revisiones hechas hasta hoy son internas. |
| **Encargado de datos / LGPD** | No designado formalmente | Decisión del operador. |
| **Sesión corta para el rol `agent`** | Hoy dura 7 días | Decisión del operador. El agente entra al panel y se le exige segundo factor, pero su sesión dura como la de un cliente. Acortarla es un cambio de una línea; el costo es que el agente vuelva a autenticarse durante la jornada. Está fijado en `test_duracion_de_la_sesion.py` para que sea una decisión y no un olvido. |

---

## 12. Tabla de verificación

| Afirmación | Dónde vive | Cómo se comprueba |
|---|---|---|
| Contraseñas con bcrypt y sal | `backend/utils/security.py` | `test_primer_acceso_del_personal.py`, `test_password_recovery.py` |
| Sesiones opacas y revocables | `backend/routes/dependencies.py`, `backend/routes/auth.py` | `test_ttl_de_sesiones.py` |
| Caducidad diferenciada: 30 min administrador, 7 días usuario | `backend/routes/security_2fa.py` | `test_duracion_de_la_sesion.py` |
| Cada ingreso de administrador deja línea con IP y país | `backend/routes/security_2fa.py` | `test_duracion_de_la_sesion.py` |
| 2FA obligatorio para todo el personal | `backend/services/personal.py`, `backend/routes/auth.py` | `test_huella_del_personal.py` |
| Primer acceso por invitación de un solo uso, con hash y consumo atómico | `backend/services/invitaciones.py` | `test_primer_acceso_del_personal.py` |
| Límite de intentos por IP que no se acumula | `backend/routes/security_2fa.py` | `test_limite_por_ip.py` |
| WebAuthn con verificación de usuario exigida | `backend/routes/webauthn_login.py` | `test_huella_del_personal.py` |
| 18 permisos, 65 rutas, y falla cerrado | `backend/services/permisos.py` | `test_permisos_se_aplican.py` |
| Sin rutas duplicadas inalcanzables | `backend/routes/` | `test_rutas_alcanzables.py` |
| El personal no transacciona a título personal | `backend/services/personal.py`, `backend/services/saldos.py` | `test_personal_sin_transacciones.py` |
| Dinero en `Decimal`, nunca `float` | `backend/services/money.py` | `test_saldos.py`, `test_ledger_admin_decimal128.py`, `test_motor_contable.py` |
| Libro mayor sin edición ni borrado | `backend/services/ledger.py` | `test_libro_mayor_no_se_edita.py` |
| Idempotencia en creación de movimientos | `backend/services/idempotency.py` | `test_pago_una_sola_vez.py` |
| Límites por operación aplicados en el servidor | `backend/services/limits.py` | `test_limites_monto.py`, `test_limites_publicados.py` |
| Cupo de la cuenta sin verificar | `backend/services/kyc_quota.py` | `test_cupo_sin_kyc.py` |
| Solvencia del pozo: lo que se debe contra lo que hay | `backend/services/contabilidad.py` | `test_conciliacion_pozo.py` |
| Los controles del dinero son visibles para el operador, y un fallo nunca se lee como «todo bien» | `frontend/src/utils/seguridadFinanciera.js` | `test_seguridad_financiera.py` |
| Libro de auditoría con estado antes/después | `backend/services/auditoria.py` | `test_auditoria.py` |
| Tipo de archivo por bytes, EXIF removido, dedup por SHA-256 | `backend/services/envios_archivos.py` | `test_envios_almacen.py` |
| TLS verificado, falla cerrado | `backend/services/bcv_scraper.py` | `test_tls_verificado.py` |
| OAuth 2.0 con renovación anticipada y un solo pedido bajo concurrencia | `backend/services/oauth_cliente.py` | `test_oauth_cliente.py` |
| Cabeceras de seguridad en toda respuesta, incluidos los errores | `backend/server.py` | `test_cabeceras_de_seguridad.py` |
| CORS sin comodín y sólo sobre https | `backend/server.py` | `test_cabeceras_de_seguridad.py` |
| Webhooks con firma verificada | `backend/routes/credits.py`, `backend/routes/transactions.py` | `test_merma_nowpayments.py`, `test_underpaid_tiers.py`, `test_puente_adminbrl.py` |
| Bloqueo de jurisdicciones antes de crear el cobro | `backend/services/geo_restrictions.py`, `backend/routes/credits.py` | `test_jurisdicciones_bloqueadas.py` |
| Sin identidades personales incrustadas en el código | todo el repositorio | `test_sin_cuentas_con_nombre_propio.py` |
| La IP de un pedido no la elige quien lo hace | `backend/services/ip_cliente.py` | `test_ip_cliente.py`, `test_envios_crear.py`, `test_auditoria.py` |
| Un comprobante no puede ejecutar código al abrirlo | `frontend/src/utils/urlDeArchivo.js` | `test_url_de_archivo.py` |
| Un comprobante peligroso no se llega a guardar | `backend/services/imagen_recibida.py` | `test_imagen_recibida.py` |
| El proxy de medios sólo va a donde tiene que ir | `backend/routes/media.py` | `test_media_twilio.py` |
| Toda ruta pública tiene tope de intentos o motivo escrito | `backend/routes/` | `test_puertas_sin_llave.py` |
| Toda ruta de los puentes exige la clave, y la exige primero | `backend/routes/adminbrl_bridge.py`, `backend/routes/centro_gestion.py` | `test_puente_con_llave.py` |
| Los webhooks verifican firma y frescura | `backend/routes/gestor_pix.py`, `backend/routes/btc_lightning.py` | `test_webhooks_firmados.py` |
| La documentación de la API no se publica, y el cuerpo tiene tope | `backend/server.py`, `backend/services/limite_de_cuerpo.py` | `test_superficie_de_la_api.py` |
| Un documento cifrado vuelve idéntico, y el tamaño no crece | `backend/services/cofre.py` | `test_cofre.py` |
| El cifrado no se prende solo ni guarda en claro creyendo que cifra | `backend/services/cofre.py` | `test_cofre.py` |
| Cambiar la contraseña cierra las sesiones abiertas | `backend/services/sesiones.py` | `test_sesiones_al_cambiar_clave.py` |
| Ningún registro escribe un dato personal en claro | `backend/services/registro.py` | `test_registros_sin_datos.py` |
| `script-src` sin `unsafe-inline` ni `unsafe-eval` | `backend/services/csp.py` | `test_politica_de_contenido.py` |
| Cada consulta de usuario está atada a su dueño | `backend/routes/`, `backend/services/` | revisión de septiembre de 2026 (ver 10) |

---

## 13. Contacto para este dossier

Consultas técnicas sobre este documento: canal de soporte de la plataforma
(`https://risappbr.com/support`).
