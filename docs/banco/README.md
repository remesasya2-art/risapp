# El banco dentro de RIS: tres servicios, cada uno con su llave

Este documento explica cómo está armada RIS desde la fase F0 del banco: qué es
cada servicio, qué datos son de quién, qué hace cada llave, y qué falta para que
el banco opere de verdad. Está escrito para leerlo sin saber programar. Donde
hace falta un término técnico, se explica.

Fecha de esta versión: 26 de septiembre de 2026.

---

## 1. La idea

RIS ofrece tres cosas distintas, que se prenden y se apagan por separado:

| Servicio | Qué es | Dónde guarda sus datos |
|---|---|---|
| **Remesas** | Gastar en Venezuela y en Brasil, cargar saldo, la vía cripto | La base de la aplicación (Mongo) |
| **Encomiendas** | Mandar paquetes a Venezuela | La base de la aplicación (Mongo) |
| **Banco** | Cuentas de pago, PIX, tarjetas, boletos y TED | **Su propia base** (Postgres), aparte |

Debajo de los tres está la **plataforma**: el personal, los permisos, la
auditoría (el registro de quién hizo qué), el respaldo, la configuración y la
atención a clientes. La plataforma no se apaga nunca.

**Por qué así.** Si RIS se integra con un banco socio (por ejemplo, Hiperbanco),
ese socio no va a aceptar una empresa que haga remesas internacionales sin la
licencia correspondiente. Entonces tiene que ser posible **dejar sólo el banco**:
apagar remesas y encomiendas desde el panel, sin tocar código, y volver a
prenderlas el día que haya licencia. Todo queda construido y esperando detrás
de su botón.

---

## 2. Las llaves de cada servicio

Una **llave** es un ajuste de Configuración que prende o apaga un servicio. Se
cambian desde el panel, en **Plataforma → Administración → Servicios**, sólo el
super administrador. Esa pantalla guarda por la misma ruta que la pantalla de
Configuración. Así, cada cambio pasa por la validación, por los seguros entre
ajustes, por la aprobación de dos personas que exige el núcleo (los «cuatro
ojos») y queda en el libro de auditoría.

### Remesas — «Remesas (gastar en Venezuela y en Brasil)»

| Estado | Qué pasa |
|---|---|
| **Abierto** (1, de fábrica) | Todo como siempre. |
| **En pausa** (0) | No nacen envíos nuevos. Además cierra la carga de saldo y la entrada de cripto, aunque sus propias llaves digan otra cosa: es la **llave madre**. La cripto queda en «sólo salida», para que nadie quede con su plata adentro. No nace el bono de bienvenida. |

Con remesas en pausa **sigue funcionando todo lo que termina algo que ya
empezó**:

- ver el historial;
- subir el comprobante de un envío ya cotizado;
- pagar con tarjeta un envío ya creado;
- cancelar;
- recibir los avisos de pago que acreditan;
- todo el panel de operación, para que el equipo termine lo pendiente.

> **Ojo antes de pausar:** quien tenga saldo cargado no lo va a poder gastar
> mientras remesas esté en pausa. Conviene avisar a los clientes con saldo, o
> esperar a que lo gasten.

Las puertas exactas que se cierran están en `backend/services/remesas_abiertas.py`.
El test `backend/tests/test_remesas_cerradas.py` las recorre en la aplicación
armada.

### Encomiendas — «Envío de paquetes»

| Estado | Qué pasa |
|---|---|
| **Abierto** (1, de fábrica) | Todo como siempre. |
| **Suspendido** (0) | No se cotizan ni se confirman encomiendas nuevas. Las que están en camino siguen su curso. |

Detalle en `backend/services/encomiendas_abiertas.py`.

### Banco — «Núcleo de cuentas»

| Estado | Qué pasa |
|---|---|
| **Apagado** (0, de fábrica) | No existe: ni rutas ni sección en el panel. |
| **Laboratorio** (1) | Sólo el super administrador lo ve, con plata de prueba. Los clientes no ven nada. |
| **Activo** (2) | Reservado para cuando haya licencia o socio. Hoy hace lo mismo que el laboratorio. |

Detalle en `backend/nucleo/modo.py`.

### Por qué remesas y encomiendas tienen dos estados y el banco tres

Se pensó en darles a todos un estado intermedio, «sólo gerencia», para probar un
servicio antes de abrirlo. En remesas y encomiendas no funcionaría: las cuentas
del personal tienen prohibido mover plata, así que nadie podría probar nada en
ese modo. El banco sí lo tiene, porque su laboratorio trabaja con plata de
prueba.

---

## 3. El panel, separado por servicio

Arriba del menú del panel hay cuatro botones: **Plataforma · Remesas ·
Encomiendas · Banco**. Cada uno muestra sólo su menú:

| Servicio | Secciones |
|---|---|
| **Plataforma** | Resumen y uso · Clientes (usuarios, verificación de identidad, lista negra, chat, soporte, calificaciones) · Contabilidad (libro mayor, seguridad financiera, reportes) · Administración (servicios, configuración, respaldo, personal, auditoría, errores) |
| **Remesas** | Operación (órdenes, retiros, recargas en bolívares, diferencias de pago, pagos de Mercado Pago, Bitcoin, créditos cripto, tasas) · Tesorería (bancos, cobros sin acreditar) |
| **Encomiendas** | Cola de envíos y su configuración |
| **Banco** | La gerencia bancaria (hoy, el laboratorio del núcleo) |

Lo que suma plata de varios servicios queda en Plataforma: el libro mayor, los
reportes, la seguridad financiera y el uso. Partirlo sería perder la foto
entera.

Un servicio apagado se sigue viendo en el menú, con su estado escrito debajo
(«En pausa», «Apagado»). Hace falta poder entrar a terminar lo que quedó en
curso.

---

## 4. El personal: un solo equipo, con permisos por servicio

El personal es uno solo. En qué servicio trabaja cada persona lo dicen sus
**permisos**, que se asignan en Recursos Humanos, agrupados por servicio:

- **Plataforma:** ver usuarios, lista negra, verificación de identidad, soporte, configuración.
- **Remesas:** recargas, transacciones, ajustar saldos.
- **Encomiendas:** ver, operar y cobrar envíos.
- **Banco:** todavía ninguno. Hoy la gerencia bancaria es sólo del super administrador. Los permisos del banco llegan con la fase F5.

Cada persona ve en el panel sólo las secciones que el servidor le va a dejar
abrir, y sólo los botones de los servicios donde tiene algo que hacer. El
servidor sigue siendo el que decide: el menú sólo evita ofrecer una puerta que
va a contestar que no.

Todavía hay cosas de remesas que sólo puede hacer el super administrador (pagar
retiros, tasas, bancos, libro mayor). Delegarlas es una decisión aparte.

---

## 5. Los datos no se mezclan

Son dos bases distintas, y hay reglas que las mantienen separadas. Las vigila
`backend/tests/test_los_datos_no_se_mezclan.py`:

1. **El banco no lee ni escribe la base de la aplicación.** Lo único que toma
   de ahí son sus propias llaves de Configuración.
2. **La aplicación no abre la base del banco.**
3. **El banco no guarda datos de clientes de la aplicación.** Una cuenta del
   banco cuelga del legajo de su titular, que el banco verifica por su cuenta.
   Un cliente de remesas no tiene cuenta en el banco por serlo.
4. **La aplicación no guarda clientes ni cuentas del banco.**

Además, `backend/tests/test_nucleo_frontera_y_migraciones.py` cuida que el
código del banco y el de la aplicación no se usen el uno al otro. El objetivo es
que el día que el banco se separe en su propio servicio, salga del repositorio
sin arrastrar nada.

---

## 6. Las fases

| Fase | Qué es | Estado |
|---|---|---|
| **F0** | Separar los servicios: llaves, panel por servicio, permisos por servicio, datos que no se mezclan, este documento | **Hecha** |
| **F1** | Clientes del banco con su propio registro, ingreso, segundo factor y verificación de identidad, en la base del banco | Pendiente |
| **F2** | Cuenta de pago y PIX para esos clientes | Pendiente |
| **F3** | Boletos y TED | Pendiente |
| **F4** | Tarjetas, incluida la emisión en lote de tarjetas sin nombre | Pendiente |
| **F5** | La gerencia bancaria completa (la sección Banco del panel), con sus propios permisos | Pendiente |
| **F6** | El adaptador de Hiperbanco (o del socio que sea) | Pendiente: necesita acceso a su documentación y credenciales de prueba |

### Qué ya existe del banco

El núcleo de cuentas (`backend/nucleo/`) ya tiene, en modo laboratorio:

- el libro de partida doble;
- un plan de cuentas al estilo COSIF, con códigos provisorios;
- el riel PIX;
- los legajos de identidad;
- el riesgo y los avisos al COAF;
- los reportes regulatorios;
- incidentes y ouvidoria;
- la operación diaria.

**Todo lo que habla con afuera es un simulador.** El lugar donde se enchufa el
socio real ya está previsto (`backend/nucleo/rieles/`). El adaptador se escribe
con la misma forma que el simulador y se elige por configuración, nunca
editando código.

### Qué hace falta para F6

- Que el entorno de trabajo pueda leer `docs.hiperbanco.com.br`. Hoy lo bloquea
  la red del entorno: se habilita en la configuración de acceso a la red.
- Credenciales de prueba (sandbox) del socio. No se pegan en el chat ni en el
  código: van a las variables del entorno.
