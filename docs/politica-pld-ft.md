# Política de prevención de lavado de dinero y financiamiento del terrorismo

**Operador:** SAIPHA Servicios Digitais (J. del Carmen Hernandez Barreto — CNPJ 66.994.057/0001-61)
**Plataforma:** risappbr.com
**Estado del documento:** BORRADOR CON VALORES PROPUESTOS — no aprobado
**Fecha:** septiembre de 2026

---

## 0. Cómo leer este documento, y qué NO es

Este borrador existe para invertir el trabajo. En vez de pedirle al operador que
invente cinco umbrales desde cero —que es difícil, y por eso quedó trabado—
propone números concretos con el razonamiento de cada uno, para que el operador
**tache y corrija** en vez de inventar.

Tres advertencias, y son en serio:

1. **No es asesoramiento legal.** Los valores propuestos están fundados en la
   práctica habitual y en lo que la norma brasileña exige a sectores
   comparables, pero antes de aprobar esta política tiene que revisarla un
   profesional de cumplimiento o un abogado en Brasil.

2. **Las fuentes normativas citadas se consultaron de forma indirecta.** Los
   sitios oficiales (bcb.gov.br, gov.br/coaf) no eran alcanzables desde el
   entorno donde se redactó este borrador; lo que hay acá viene de resúmenes
   de buscador y de publicaciones de estudios jurídicos. **Cada cita marcada
   con ⚠️ hay que verificarla contra el texto oficial antes de firmar nada.**

3. **La sección 1 puede cambiarlo todo.** Hay una duda de perímetro
   regulatorio, con fecha límite cercana, que decide bajo qué régimen opera la
   empresa. Si la respuesta es la que parece, varias secciones de acá se
   reescriben.

Todo valor propuesto está marcado **[PROPUESTO]**. Todo lo que ya está
implementado y funcionando está marcado **[VIGENTE]** y se puede señalar en el
código.

---

## 1. Perímetro regulatorio — LA PREGUNTA QUE HAY QUE RESOLVER PRIMERO

### 1.1 Las dos mitades del negocio

La plataforma tiene dos mitades con tratamiento regulatorio muy distinto:

| Mitad | Qué hace | Régimen |
|---|---|---|
| **Logística y servicios digitales** | Cotización, despacho, seguimiento y entrega de encomiendas; cobro en reales por PIX y tarjeta | Actividad comercial común |
| **Activos virtuales** | Acredita saldos en USDT y USDC a nombre del usuario, permite enviarlos a un beneficiario, y opera BTC Lightning | **Posiblemente regulada — ver 1.2** |

### 1.2 La duda, y por qué es urgente

⚠️ **Según lo consultado**, el Banco Central de Brasil publicó en noviembre de
2025 las Resoluções BCB nº 519, 520 y 521, que crean la figura de la
**Prestadora de Serviços de Ativos Virtuais (PSAV)** y someten a autorización
previa la **intermediación, la custodia, la corretaje y la transferencia** de
activos virtuales por cuenta de terceros. Los puntos relevantes:

| Punto | Lo consultado |
|---|---|
| Entrada en vigor | 2 de febrero de 2026 |
| Plazo para pedir autorización (empresas ya operando) | **30 de octubre de 2026** |
| Patrimonio líquido mínimo | Entre **R$ 10,8 y R$ 37,2 millones** según la actividad (Resolução Conjunta CMN/BC nº 14/2025) |
| Transferencias internacionales liquidadas con activos virtuales | Pasan a integrar el mercado de cambio (Res. 521); tope de **US$ 100.000** cuando la contraparte no está autorizada a operar en cambio |
| Información mínima exigida en esas operaciones | Desde el 4 de mayo de 2026 |
| A partir del 30 de octubre de 2026 | Las instituciones autorizadas por el BCB tendrían prohibido operar con activos virtuales frente a contrapartes brasileñas no autorizadas |

**Por qué esto toca a esta plataforma y no es una preocupación abstracta:**

- `services/credits.py` acredita y mantiene **saldos en USDT y USDC a nombre de
  cada usuario** (`balance_usdt`, `balance_usdc`), con su propio libro mayor.
  Mantener el activo de un tercero es, en la lectura natural, custodia.
- `routes/transactions.py` permite **enviar esos activos a un beneficiario en
  Venezuela**. Es una transferencia internacional liquidada con activos
  virtuales, que es exactamente lo que la Resolução 521 trae al mercado de
  cambio.
- El código ya distingue los dos casos: uno de los caminos está anotado como
  «sin custodia previa», lo que confirma que el otro sí lo es.

**El plazo es el problema.** A la fecha de este borrador quedan alrededor de
ocho semanas para el 30 de octubre de 2026, y el patrimonio líquido mínimo está
fuera del alcance de esta empresa por varios órdenes de magnitud.

### 1.3 Las preguntas exactas para el abogado

No hace falta un estudio: hacen falta cinco respuestas.

1. ¿Acreditar y mantener saldos de USDT/USDC a nombre de usuarios configura
   **custodia de activos virtuales de terceros** a los efectos de la Resolução
   BCB nº 520?
2. ¿Enviar esos activos a un beneficiario en el exterior configura
   **transferencia** o **intermediación** a los mismos efectos?
3. ¿Existe alguna **exclusión** aplicable: comerciante que acepta cripto como
   medio de pago, uso propio, o actuación exclusivamente a través de un
   procesador tercero ya autorizado?
4. Si la respuesta es que sí califica: ¿qué alternativas hay además de la
   autorización — operar la vía cripto **a través de un tercero autorizado**, o
   **discontinuarla**?
5. ¿Qué exposición existe por lo ya operado entre el 2 de febrero de 2026 y hoy?

### 1.4 Postura mientras tanto **[PROPUESTO]**

Hasta tener esas respuestas:

- **No se amplía la vía cripto.** Ni montos, ni monedas, ni redes nuevas.
- **Se documenta el volumen actual** de saldos en USDT/USDC y de envíos
  liquidados en cripto, para poder dimensionar la exposición en una conversación
  con el abogado. La pantalla de Seguridad financiera y el libro mayor de
  créditos cripto ya tienen los datos.
- **La mitad de logística y reales sigue normal.** Nada de esto la alcanza.

### 1.5 Régimen del resto de la operación

Para la mitad no-cripto, y con la reserva de la sección 0: la empresa **no es
institución financiera ni de pago** autorizada por el BCB. Sus obligaciones de
prevención le llegan, en la práctica, por dos vías: la ley general
(Lei 9.613/1998) y, sobre todo, **el contrato con el proveedor de servicios de
pago**, que traslada a sus clientes obligaciones de conocimiento del cliente,
monitoreo y reporte.

Esto no es una excusa para tener menos control: es el motivo por el cual esta
política existe antes de que nadie la exija.

---

## 2. Gobierno: quién responde

### 2.1 Responsable designado **[PROPUESTO]**

**Propuesta: el super administrador de la plataforma**, en su carácter de
titular de la empresa, hasta que la estructura justifique separarlo.

Razonamiento, y su límite: en una empresa de esta escala no hay a quién más
designar, y un responsable nominal que no existe es peor que uno real que
además hace otras cosas. **Pero la designación tiene un costo de control**: la
misma persona que aprueba las operaciones es la que las revisa. Eso hay que
compensarlo con lo único que lo compensa, que es el rastro: el libro de
auditoría registra cada aprobación con quién, cuándo y desde dónde, y no se
puede editar ni borrar. **[VIGENTE]**

**Cuándo hay que revisar esta designación:** al incorporar el primer
colaborador con permiso de mover dinero de forma permanente, o al superar los
umbrales de la sección 4 de forma habitual.

### 2.2 Segregación de funciones **[VIGENTE]**

Ya implementado y verificable:

- 18 permisos, 65 rutas gobernadas, y una ruta no declarada **se niega**.
- Tres permisos marcados «MUEVE DINERO» y separados de los de sólo lectura.
- **El personal no puede transaccionar a título personal**, con dos candados:
  uno en la puerta y otro en el movimiento del saldo, de modo que un cobro
  externo que liquida por webhook tampoco puede acreditarle.
- Segundo factor obligatorio para todo el personal con acceso al panel.

### 2.3 Quién puede mirar **[VIGENTE]**

La pantalla **Seguridad financiera** del panel reúne los cuatro controles de
integridad del dinero y la lista de quién tiene llaves. Es de sólo lectura y
sólo del super administrador.

---

## 3. Conocimiento del cliente (KYC)

### 3.1 Lo que se recoge hoy **[VIGENTE]**

| Dato | Estado |
|---|---|
| Documento de identidad (tipo y número) | Se pide y se guarda |
| CPF | Se pide y se guarda |
| Imagen del documento | Se pide |
| Imagen del CPF | Se pide |
| Selfie | Se pide |
| Nivel de riesgo (bajo / medio / alto) | Lo asigna el administrador al revisar |

Las imágenes se guardan con el tipo verificado en los bytes, sin metadatos EXIF
y deduplicadas por SHA-256.

### 3.2 El cupo sin verificar **[VIGENTE]**

Una cuenta sin KYC aprobado tiene **200 RIS acumulados y 2 operaciones**. Se
agota con lo que ocurra primero y **no se renueva**. Cualquier operación mayor a
200 exige verificación, porque no hay forma de que entre en el cupo.

### 3.3 Lo que falta recoger **[PROPUESTO]**

Tres datos que hoy no se piden y que una revisión de cumplimiento va a pedir:

1. **Declaración de origen de fondos** por encima del umbral de la sección 4.
   Hoy no se pide nunca.
2. **Ocupación o actividad económica declarada.** Sin esto no hay «perfil» contra
   el cual comparar una operación, y sin perfil la palabra «inusual» no
   significa nada.
3. **Persona expuesta políticamente (PEP)**: una declaración del propio usuario,
   más su relación con el beneficiario. Es una casilla y una pregunta.

### 3.4 Vigencia del legajo **[PROPUESTO]**

- Riesgo bajo: revisión cada **36 meses**.
- Riesgo medio: cada **24 meses**.
- Riesgo alto: cada **12 meses**, y siempre antes de una operación que supere el
  umbral reforzado.

---

## 4. Los umbrales **[PROPUESTO]**

### 4.1 Punto de partida: lo que ya existe **[VIGENTE]**

| Vía | Mínimo | Máximo |
|---|---|---|
| PIX / reales | R$ 10,00 | R$ 5.000,00 por operación |
| Bolívares | 100 VES | **sin techo** |
| Cuenta sin verificar | — | 200 RIS acumulados y 2 operaciones |

**Dos huecos, y conviene nombrarlos antes de proponer nada:**

- **No hay ningún límite acumulado.** Hoy nada impide veinte operaciones de
  R$ 5.000 en un mes: R$ 100.000 sin que se encienda una sola luz. El techo por
  operación no sustituye a un acumulado; sólo obliga a fraccionar, que es
  justamente lo que un techo sin acumulado enseña a hacer.
- **La vía en bolívares no tiene techo**, por decisión de negocio documentada en
  `services/limits.py`. Puede seguir sin techo, pero entonces necesita
  acumulado con más razón.

### 4.2 La escala propuesta

| Nivel | Umbral | Qué se hace |
|---|---|---|
| **Ordinario** | Hasta R$ 5.000 por operación y **R$ 10.000 acumulados en 30 días** | KYC aprobado. Nada adicional. |
| **Atención** | **R$ 10.000** acumulados en 30 días | Revisión documentada de coherencia con el perfil declarado. Queda asentada en el legajo, se apruebe o no. |
| **Reforzado** | **R$ 30.000** acumulados en 30 días, o cualquier operación única sobre R$ 5.000 equivalentes | Declaración documentada de **origen de fondos**. Aprobación explícita del responsable designado. |
| **Revisión anual** | **R$ 100.000** acumulados en 12 meses | Revisión completa del legajo y del patrón de operación. |
| **Comunicación** | **Cualquier monto**, si hay indicio | Ver sección 6. El monto no es condición: un indicio con R$ 300 se comunica igual. |

**Cómo se eligieron estos números.** El acumulado de 30 días arranca en el doble
del techo por operación (R$ 10.000): por debajo de eso, un usuario que opera dos
veces al máximo no debería tener que explicar nada. R$ 30.000 es el orden de
magnitud que la norma brasileña usa habitualmente para exigir diligencia
reforzada en sectores no financieros ⚠️. R$ 100.000 anuales es el punto donde
un cliente de esta plataforma deja de parecerse a un usuario y empieza a
parecerse a un negocio, y entonces corresponde entenderlo como tal.

**Todos estos números son discutibles y están puestos para que se discutan.**
Si el operador cree que su cliente típico manda R$ 20.000 por mes sin nada raro,
la escala está mal calibrada y hay que subirla: **un umbral que se dispara todos
los días es un umbral que se termina ignorando**, y eso es peor que no tenerlo.

### 4.3 Los bolívares y la cripto **[PROPUESTO]**

- **Bolívares:** el acumulado se mide **convertido a reales** con la tasa del día
  de la operación, y se guarda la tasa usada junto al asiento. Sin eso, el
  umbral se mueve solo cuando se mueve el bolívar, y un control que cambia sin
  que nadie toque la plata es un control que se deja de mirar.
- **Cripto:** hoy queda **fuera del cupo por KYC**, y está anotado como pendiente
  en `services/kyc_quota.py` — sumarlo exigiría una conversión USDT→RIS que el
  código no tiene. **Es un hueco real**: alguien puede mover por la vía cripto
  montos que en PIX exigirían verificación. Se resuelve con la conversión, o
  suspendiendo la vía (ver 1.4).

---

## 5. Qué se considera sospechoso EN ESTA OPERACIÓN

Una lista genérica no sirve: describe el lavado en abstracto y no ayuda a nadie
a decidir un martes. Ésta está armada sobre el corredor real —Brasil a
Venezuela, encomiendas y saldo— y sobre lo que el sistema efectivamente puede
ver. **[PROPUESTO]**

### 5.1 Sobre el monto y el ritmo

1. **Fraccionamiento.** Varias operaciones por debajo del techo, el mismo día o
   en días seguidos, que sumadas superarían un umbral. Es el indicio más
   importante de todos, precisamente porque hay un techo por operación.
2. **Cuenta dormida que despierta al máximo.** Sin operar durante meses y de
   golpe al techo, repetidas veces.
3. **Ingreso y salida inmediatos.** Saldo que entra y sale el mismo día sin uso
   intermedio, de forma repetida. La plataforma es para enviar, no para guardar.

### 5.2 Sobre las personas

4. **Muchos remitentes, un beneficiario.** Personas sin relación declarada entre
   sí que envían a un mismo destinatario en Venezuela.
5. **Un remitente, muchos beneficiarios** sin relación aparente ni explicación.
6. **El beneficiario no coincide** con el titular declarado, o cambia
   seguidamente sin motivo.
7. **Datos compartidos entre cuentas distintas**: mismo teléfono, mismo
   dispositivo, mismo beneficiario, con titulares diferentes.

### 5.3 Sobre la conducta

8. **Se niega o demora en aportar documentación** cuando se le pide, o la aporta
   incompleta de forma repetida.
9. **Pregunta por los límites antes de operar**, o pide expresamente que la
   operación no quede registrada.
10. **Insiste en la vía cripto** para montos que por PIX exigirían verificación.
11. **Origen declarado incoherente** con la ocupación o el patrón de operación.

### 5.4 Sobre la operación de encomiendas

12. **Encomiendas cuyo valor declarado no guarda relación** con el contenido
    manifestado o con el flete pagado.
13. **Un mismo remitente despachando al mismo destinatario** de forma
    sistemática con valores declarados justo debajo de cualquier umbral.

### 5.5 Del lado de adentro

14. **Un colaborador aprobando repetidamente** operaciones de las mismas cuentas.
15. **Ajustes manuales de saldo** sin operación de respaldo. Cada uno ya queda
    asentado con estado antes y después. **[VIGENTE]**

**Ninguno de estos indicios, por sí solo, es una acusación.** Son motivos para
mirar. Lo que se comunica es el resultado del análisis, no el indicio.

---

## 6. Comunicación

### 6.1 A quién **[PROPUESTO — verificar ⚠️]**

Al **COAF**, a través del **SISCOAF**. La empresa no tiene órgano regulador
propio para esta actividad, por lo que la comunicación va directamente al COAF.

⚠️ Esto cambia si la sección 1 concluye que la empresa queda bajo supervisión
del Banco Central: en ese caso el régimen de comunicación es el del BCB.

### 6.2 En qué plazo **[PROPUESTO]**

| Etapa | Plazo |
|---|---|
| Detección → inicio del análisis | Inmediato |
| Análisis → conclusión | **Hasta 45 días** ⚠️ (es el plazo de la Circular Bacen 3.978 para instituciones financieras; se adopta como estándar propio) |
| Conclusión → comunicación | **Hasta el día hábil siguiente** |

**Sin aviso al cliente.** La comunicación no se le informa a la persona
comunicada, ni directa ni indirectamente. Esto es una regla, no una cortesía.

### 6.3 Comunicación de no ocurrencia — LA QUE MÁS SE OLVIDA

Si durante todo el año calendario **no hubo ninguna operación comunicable**,
igual hay que declararlo. El plazo es **hasta el 31 de enero** del año
siguiente.

Es la obligación que más multas genera, porque nadie la asocia con «no pasó
nada». **Próximo vencimiento: 31 de enero de 2027**, por el año 2026.

### 6.4 Qué se conserva de cada comunicación **[PROPUESTO]**

El caso completo: qué se detectó, qué se analizó, qué se concluyó, quién
decidió, cuándo, y el acuse del SISCOAF. También **los casos analizados y NO
comunicados**, con el motivo — un análisis que concluye que no hay nada es
parte del control, y no dejarlo asentado equivale a no haberlo hecho.

---

## 7. Conservación de registros **[PROPUESTO]**

| Qué | Cuánto |
|---|---|
| Legajo de identificación del cliente | **10 años** desde el cierre de la relación |
| Registros de operaciones | **10 años** desde la operación |
| Comunicaciones al COAF y sus análisis | **10 años** |
| Libro de auditoría (quién hizo qué) | **Permanente** — no hay función para borrarlo **[VIGENTE]** |

⚠️ El plazo legal habitual en Brasil es de 5 años, extensible. Se propone 10 por
margen; si el volumen de almacenamiento lo hace caro, bajarlo a 5 es defendible.

---

## 8. Capacitación **[PROPUESTO]**

- **Al ingreso**, antes de recibir cualquier permiso que mueva dinero. Sin la
  capacitación registrada, no se otorga el permiso.
- **Anual**, para todo el personal con acceso al panel.
- **Registro**: quién, cuándo, sobre qué. Una capacitación sin registro no
  existe para un auditor.

El contenido mínimo: esta política, la lista de la sección 5, cómo se escala un
caso, y la prohibición de avisarle al cliente.

---

## 9. Lo que la aplicación todavía no hace

Honestidad de inventario. Estas son las brechas entre lo que esta política dice
y lo que el sistema hoy puede sostener solo:

| Brecha | Qué haría falta |
|---|---|
| **No hay acumulado por cliente** | Contador de 30 días y de 12 meses, en reales, sobre todas las vías |
| **La cripto no entra en ningún cupo** | Conversión USDT→RIS, o suspender la vía |
| **No se pide origen de fondos** | Un campo y un flujo de aprobación sobre el umbral reforzado |
| **No se declara ocupación ni PEP** | Dos campos en el KYC |
| **No hay detección de fraccionamiento** | Regla sobre el acumulado móvil |
| **No hay expediente de caso** | Colección propia: detección, análisis, conclusión, acuse |
| **Los bolívares no tienen techo** | Decisión de negocio, no técnica |

Ninguna de estas es difícil. Pero **una política que promete controles que el
sistema no tiene es peor que no tener política**: convierte un hueco técnico en
un incumplimiento declarado por escrito. Por eso están acá, en vez de dar por
supuesto que existen.

---

## 10. Revisión de esta política **[PROPUESTO]**

- **Anual**, como mínimo.
- **Inmediata** ante: un cambio de régimen regulatorio (empezando por la
  sección 1), la incorporación de una vía de dinero nueva, o la primera
  comunicación al COAF.

Cada revisión deja constancia de qué cambió y por qué.

---

## 11. Las decisiones que faltan

Lo que el operador tiene que resolver para que este borrador deje de serlo:

| # | Decisión | Propuesta de este documento |
|---|---|---|
| 1 | Perímetro regulatorio de la vía cripto | Consultar ya, con las cinco preguntas de 1.3 |
| 2 | Umbral de atención (30 días) | R$ 10.000 |
| 3 | Umbral reforzado (30 días) | R$ 30.000 |
| 4 | Umbral de revisión anual | R$ 100.000 |
| 5 | Responsable designado | El super administrador, con revisión al crecer |
| 6 | Plazo de conservación | 10 años |
| 7 | Techo para la vía en bolívares | Sin techo por operación, pero con acumulado |

---

*Documento preparado como borrador de trabajo. Requiere revisión profesional
antes de su aprobación y de cualquier presentación ante autoridad.*
