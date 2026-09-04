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
- El repositorio **no contiene ninguna clave de firma de sesión**. Las
  constantes `SECRET_KEY` / `ALGORITHM` fueron eliminadas de `config.py`
  precisamente porque un placeholder en el historial de un repositorio es una
  trampa para quien mañana agregue firma.

`backend/config.py`, `backend/routes/dependencies.py`, `backend/routes/auth.py`

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

Todos los puntos de entrada sensibles —inicio de sesión, verificación de
segundo factor, activación de invitación, recuperación— tienen límite por IP
real del cliente (`20/15minutes` en el inicio de sesión).

Detalle no menor: el límite se aplica con una función explícita
(`frenar(request, alcance, regla)`) y **no** con un decorador sobre funciones
anidadas. La implementación anterior registraba una regla nueva por cada
petición, y el consumo acumulado terminaba bloqueando el inicio de sesión de
**todos** los usuarios tras unas decenas de accesos, sin recuperación posible
salvo reinicio. Está medido y corregido, con prueba de regresión.

`backend/routes/security_2fa.py`, `backend/tests/test_limite_por_ip.py`

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

### 7.2 Minimización en reportes

Los reportes y exportaciones **omiten las imágenes**; se transportan
referencias, no contenido. Un comprobante no tiene por qué viajar hasta una
planilla.

`backend/services/reportes.py`

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

**CORS con lista blanca explícita** de orígenes propios, todos `https`. No hay
comodín: `allow_origins=["*"]` junto a `allow_credentials=True` es la
combinación que permite a cualquier sitio hacer peticiones con la cookie de
sesión de la víctima.

`backend/server.py`, `backend/tests/test_cabeceras_de_seguridad.py`

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
- Puentes internos con clave de API: comparación con `hmac.compare_digest`
  (tiempo constante) y **falla cerrado** si la clave no está configurada.

**Postura declarada:** no escribimos un receptor de webhook para un proveedor
cuyo esquema de firma no conocemos. Un endpoint público que acredita saldo sin
verificar quién llama es lo peor que se puede dejar «preparado». Cuando el
proveedor publique su esquema, se implementa y se prueba contra él.

`backend/routes/credits.py`, `backend/routes/transactions.py`, `backend/routes/webhooks.py`, `backend/routes/adminbrl_bridge.py`, `backend/routes/centro_gestion.py`

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

- **Suite automatizada:** 83 archivos de prueba sobre el backend. Última
  ejecución completa: **2013 pruebas superadas, 99 omitidas, 0 fallidas**
  (las omitidas requieren credenciales de proveedores externos). Se corre en
  cada cambio.
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
| **Política PLD/AML formal** | No redactada | Cinco decisiones de negocio del operador: umbral por operación, umbral acumulado, qué se considera sospechoso en esta operación, a quién y en qué plazo se reporta, y quién es el responsable designado. La plataforma ya tiene los controles técnicos (cupos, KYC, trazabilidad); falta el documento que los ordena. |
| **Cifrado de documentos en reposo** | Parcial | Los objetos se apoyan en el cifrado del proveedor de almacenamiento. El cifrado a nivel de aplicación, con claves propias, no está implementado. |
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
| Libro de auditoría con estado antes/después | `backend/services/auditoria.py` | `test_auditoria.py` |
| Tipo de archivo por bytes, EXIF removido, dedup por SHA-256 | `backend/services/envios_archivos.py` | `test_envios_almacen.py` |
| TLS verificado, falla cerrado | `backend/services/bcv_scraper.py` | `test_tls_verificado.py` |
| OAuth 2.0 con renovación anticipada y un solo pedido bajo concurrencia | `backend/services/oauth_cliente.py` | `test_oauth_cliente.py` |
| Cabeceras de seguridad en toda respuesta, incluidos los errores | `backend/server.py` | `test_cabeceras_de_seguridad.py` |
| CORS sin comodín y sólo sobre https | `backend/server.py` | `test_cabeceras_de_seguridad.py` |
| Webhooks con firma verificada | `backend/routes/credits.py`, `backend/routes/transactions.py` | `test_merma_nowpayments.py`, `test_underpaid_tiers.py`, `test_puente_adminbrl.py` |
| Bloqueo de jurisdicciones antes de crear el cobro | `backend/services/geo_restrictions.py`, `backend/routes/credits.py` | `test_jurisdicciones_bloqueadas.py` |
| Sin identidades personales incrustadas en el código | todo el repositorio | `test_sin_cuentas_con_nombre_propio.py` |

---

## 13. Contacto para este dossier

Consultas técnicas sobre este documento: canal de soporte de la plataforma
(`https://risappbr.com/support`).
