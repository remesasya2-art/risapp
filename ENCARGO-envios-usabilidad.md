# Encargo: la caja, el instructivo y las agencias por estado

Trabajás sobre `remesasya2-art/risapp`, rama nueva desde `main`. El módulo de
envíos (traslado transfronterizo Brasil → Pacaraima → Santa Elena) ya está
mergeado y **corriendo en producción** en `risappbr.com` — es el PR #42, 21
commits, 1058 tests.

Esto sale de pruebas reales con usuarios. Tres problemas, en orden de cuánto
duelen.

---

## Lo que está pasando hoy en producción

`GET https://risappbr.com/api/envios/limites` devuelve, ahora mismo:

```json
{"disponible": false,
 "limites": {"peso_max_kg": 30.0, "lado_max_cm": 0.0, "suma_lados_max_cm": 200.0,
             "valor_declarado_max": 600.0, "largo_min_cm": 15.0,
             "ancho_min_cm": 10.0, "alto_min_cm": 1.0, "suma_lados_min_cm": 26.0},
 "impuesto_por": {"lado_max_cm": "TRP-VZL", "valor_declarado_max": "TRP-VZL", ...},
 "tarifa_version": null,
 "descripcion_min_caracteres": 130}
```

Dos cosas para leer ahí, porque explican todo el encargo:

1. **`lado_max_cm` está en 0** y lo impone `TRP-VZL`. Cero significa que ninguna
   caja pasa: toda cotización se rechaza con «ningún lado puede superar los
   0 cm». El super administrador escribió 0 creyendo que era «sin límite».
   **Vacío y cero son opuestos y en el panel se ven igual.** Eso es un defecto
   de diseño del formulario, no del usuario.
2. **`descripcion_min_caracteres` en 130.** Le pide al cliente tres renglones de
   descripción. Mismo problema: un campo que acepta cualquier número sin decir
   qué significa.

El dueño lo resumió así: *«configurar los centímetros fue muy complicado, y al
usuario se le complicó generar la cotización»*.

---

## PARTE 1 — El límite deja de ser «el lado» y pasa a ser LA CAJA

**La decisión de negocio, ya tomada:** el tope es una caja física real —la más
grande que acepta el transportista de origen— de **40 × 52 × 32 cm**. La regla
no es «ningún lado supera X», es **«el paquete tiene que entrar en esta caja»**.

### Lo que se va

De los límites de transportista Y de `limites_propios` de la tarifa, se
eliminan por completo:

```
suma_lados_max_cm
largo_min_cm     ancho_min_cm     alto_min_cm     suma_lados_min_cm
```

Nadie los pidió, nadie los entendía, y son la mitad de la pantalla que enredó
al super administrador. `_MINIMOS` desaparece de `services/envios_policy.py`.

### Lo que llega

`lado_max_cm` (un número) se reemplaza por una caja:

```python
"caja_max_cm": {"largo": "40", "ancho": "52", "alto": "32"}
```

Los límites quedan en tres, y solo tres: **la caja, el peso, el valor
declarado.**

### La validación: entra rotando

Un paquete entra en la caja si, **ordenando las tres medidas de cada uno de
mayor a menor**, cada medida del paquete es ≤ la de la caja. Es la prueba
estándar de «cabe, girándolo».

```
caja  40 × 52 × 32  →  ordenada: 52, 40, 32
50 × 35 × 30        →  ordenada: 50, 35, 30   → ENTRA
45 × 45 × 45        →  ordenada: 45, 45, 45   → NO ENTRA (45 > 40)
52 × 40 × 32        →  exacta                  → ENTRA
```

Ojo con el segundo: con el modelo viejo de «lado máximo 52» ese cubo pasaba, y
no entra en la caja. Es justamente el caso que este cambio viene a arreglar, y
**quiero un test con ese ejemplo exacto.**

### La intersección entre transportistas

`limites_efectivos` sigue tomando el más estricto, pero ahora sobre la caja:
se ordenan las tres medidas de cada caja y se toma **el mínimo posición por
posición**. El resultado es la caja más chica que satisface a todos.

`impuesto_por` tiene que seguir diciendo **quién** impone cada límite, por su
CÓDIGO (`TRP-BRL`, `TRP-VZL`) — nunca por nombre comercial. Eso ya funciona y
no se puede perder: es lo que permite decirle al usuario «el transportista
TRP-VZL no despacha cajas más grandes que…» en vez de una regla anónima.

### El valor declarado cambia de dueño

**Decisión tomada:** el tope del valor declarado sale **únicamente del
transportista con rol `brasil`**. El valor declarado cubre el despacho de
origen; el transportista de Venezuela no tiene nada que decir ahí.

Hoy sale del más estricto de los dos, y por eso en producción el tope efectivo
es 600 por `TRP-VZL`. Después de este cambio, `impuesto_por.valor_declarado_max`
tiene que decir `TRP-BRL`.

### Migración — leelo antes de tocar nada

**Hay datos en producción con el modelo viejo.** Un despliegue que asuma
`caja_max_cm` en todos los documentos deja el módulo caído.

- Una ficha que solo tiene `lado_max_cm` se lee como caja cúbica de ese lado
  (`lado × lado × lado`), que es la interpretación más permisiva y no rompe a
  nadie.
- `lado_max_cm: 0` y cualquier valor no comparable (NaN, infinito, texto) se
  leen como **límite no declarado**, no como cero. Esto solo arregla el sitio en
  el instante del despliegue, sin que nadie toque el panel.
- Los campos eliminados se ignoran si están; no hace falta borrarlos de Mongo.

`_limite_utilizable` ya trata NaN/infinito así — extendé ese criterio, no
escribas uno nuevo.

---

## PARTE 2 — El panel del super administrador

Objetivo textual del dueño: **«para que el super administrador no se enrede
configurando su sistema»**.

En `frontend/src/components/admin/envios/Transportistas.jsx`:

1. **Vacío y cero dejan de parecerse.** Por cada límite, un interruptor
   **«Sin límite» / «Poner un tope»**. El número solo aparece si elige poner
   tope, y entonces es obligatorio y mayor que cero. Que sea imposible guardar
   un cero que significa «no pasa nada».
2. **Los valores por defecto, ya cargados.** Un transportista nuevo arranca con
   **40 × 52 × 32 cm** y **30 kg**. El super administrador confirma, no
   investiga.
3. **Vista previa en vivo, debajo del formulario.** Mientras escribe:
   *«Con esto entra una caja de 50 × 35 × 30. No entra una de 45 × 45 × 45.»*
   Calculada con **la misma función del servidor**, no con una copia en el
   cliente — que es exactamente cómo el PR #40 llegó a anunciar topes que el
   servidor no validaba.
4. **No se guarda una configuración que rechaza todo.** Si la caja efectiva
   queda en cero o el peso máximo en cero, cartel rojo y confirmación explícita.
5. **Sacar de la pantalla** los campos eliminados en la Parte 1.

Y en `Contenido.jsx`, el mínimo de caracteres de la descripción: hoy acepta
cualquier número entre 3 y 200 sin decir qué significa. Que muestre un ejemplo
de una descripción de ese largo mientras lo elige, y que avise arriba de ~60.
Alguien puso 130 y está en producción.

---

## PARTE 3 — El formulario del usuario

En `frontend/src/pages/EnvioNuevo.jsx`. Pedido textual: **«que el usuario, a
medida que va llenando cada cuadro, vaya recibiendo una especie de instructivo,
para que sea muy amigable»**.

La clave: **`GET /api/envios/limites` ya devuelve los límites reales y quién
impone cada uno.** Esa información está y el formulario la desperdicia. Todo lo
que sigue sale de ahí, así que **cuando el super administrador cambie la
configuración, el instructivo cambia solo, sin tocar código.**

1. **Cada campo dice su regla ANTES de que el usuario escriba**, con los números
   configurados: *«Tiene que entrar en una caja de 40 × 52 × 32 cm»*, *«Hasta
   30 kg»*, *«Valor declarado hasta X»*.
2. **Validación mientras escribe, no al enviar**, y con el motivo verificable:
   *«No entra en la caja de 40 × 52 × 32 que despacha TRP-BRL. Probá con el lado
   más largo de 52 cm o menos.»* Una regla que el usuario puede comprobar.
3. **El peso volumétrico, explicado en el momento.** Es lo que más confunde: la
   caja pesa 2 kg y se le cobra por 4,8. Mostrar el cálculo mientras carga las
   medidas —no después del precio— y decir cuál de los dos pesos manda.
4. **Valor declarado:** mostrar el tope y que sale del transportista de Brasil.
5. **Agencias en dos pasos.** Hoy es una lista larga de todas las oficinas y el
   dueño dice que **«es muy desordenado»**. Primero un selector de **Estado**
   —solo los que tengan oficinas activas—, después las **oficinas de ese
   estado**, con la dirección debajo de cada una, y un buscador por nombre o
   ciudad cuando haya muchas.
   Los datos ya están: cada agencia guarda `estado` y `ciudad`, y
   `_agencias_de` en `services/envios_catalogo.py` ya los devuelve ordenados
   por estado. Es trabajo de frontend, no hace falta tocar la consulta.

---

## Lo que NO se toca, pase lo que pase

Reglas de negocio que ya están implementadas y verificadas. Si algún cambio de
arriba las contradice, **preguntá antes de romperlas**:

- **RIS App cobra UN servicio.** Los dos tramos de transporte los contrata y
  paga el usuario; sus montos son ORIENTATIVOS y **no entran en ningún total**.
- **Nadie paga por adelantado.** El cobro inicial se emite cuando el operador
  verifica el comprobante. El precio se cierra en el repesaje.
- **Una partida impaga no es un error:** el paquete simplemente no sale de
  Pacaraima. Nunca un 402.
- **Lo que va impreso en una caja se congela** (tarifa, agencia, nombre de quien
  retira). La excepción deliberada es la cuenta bancaria del transportista, que
  se lee siempre viva.
- **Ningún nombre real de empresa de transporte en el código.** Se cargan desde
  el panel y se referencian por su código alfanumérico. Hay un test que lo
  vigila.
- **Nunca la expresión «cruce de frontera».** Se dice **«traslado
  transfronterizo»**.
- **El servicio no transporta maquinaria industrial.**
- **Configurar nunca puede requerir editar código en GitHub.**
- `Decimal` en todo el dinero, strings en los bordes de la API, proyecciones por
  lista blanca en todo lo que ve el usuario.

---

## Cómo quiero que se trabaje

El módulo se construyó con esta disciplina y conviene sostenerla:

1. **Mutation testing de cada guarda nueva.** Rompela a propósito y confirmá que
   un test se pone en rojo. Una guarda sin mutación probada es una guarda que no
   sabés si anda. En este módulo aparecieron así defectos que ningún test veía.
2. **Revisión adversarial** antes de dar nada por terminado, buscando
   específicamente **tests que pasarían igual con el producto roto**.
3. **Los 1058 tests tienen que seguir en verde**, más los nuevos.
4. **`backend/tests/test_envios_e2e.py` es el que importa**: levanta la
   aplicación FastAPI real contra `mongomock-motor` y recorre el circuito
   completo. Declara `ORDEN_IMPORTA = True` porque es un recorrido y el orden es
   el test. Necesita `pip install mongomock-motor`; si falta, se saltea solo y
   verías *1024 passed, 1 skipped* en vez de **1058 passed**. Fijate en ese
   número.
5. **Agregá al e2e** el caso del cubo de 45 × 45 × 45 que no entra, y el de la
   ficha vieja con solo `lado_max_cm` que se sigue leyendo bien después de
   migrar.

## Al terminar

Un PR contra `main` con el cuerpo explicando qué cambió y **qué tiene que
revisar el super administrador en el panel después de desplegar** — porque este
cambio toca datos que ya están cargados en producción.
