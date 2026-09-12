# La llave del cofre

**Los documentos de identidad del KYC se pueden guardar cifrados.** Este
documento explica cómo prenderlo, cómo no perder la llave, y qué hacer si algo
sale mal.

Está escrito para que lo siga una persona sin conocimientos de criptografía. Si
algo no se entiende, no lo hagas y preguntá: es preferible seguir sin cifrar a
prenderlo mal.

---

## 0. Lo primero, porque es lo único irreversible

**Si perdés la llave, perdés todos los documentos cifrados con ella. No hay
recuperación, no hay soporte que los pueda sacar, no hay respaldo de la base que
sirva** — el respaldo tiene los documentos cifrados, y sin la llave son ruido.

Para una operación que arranca, quedarse sin poder probar a quién verificó puede
ser peor que una filtración. Por eso:

> **Regla:** no prendas el cofre hasta haber comprobado, con el comando
> `verificar`, que la llave que anotaste funciona.

Todo lo demás en este documento es reversible.

---

## 1. Qué protege, y qué no

**Protege de:** quien llegue a la base de datos sin permiso. Una cadena de
conexión filtrada, un respaldo copiado a un lugar equivocado, el proveedor de
alojamiento, alguien de adentro con acceso de lectura. En todos esos casos ve
documentos cifrados y no puede abrirlos.

**No protege de:** quien entre a la aplicación como administrador. Si alguien
tiene una sesión de administrador, la aplicación le abre los documentos porque
para eso está — es su trabajo revisarlos. Contra eso protegen la contraseña, el
segundo factor y el libro de auditoría, no el cifrado.

**Qué se cifra:** las cuatro fotos del KYC (documento frente, documento dorso,
CPF, selfie).

**Qué no:** el número de CPF y el de documento. Están indexados en la base y
cifrarlos rompería las búsquedas. Es una decisión consciente, no un olvido.

---

## 2. Prenderlo, paso a paso

Son cuatro pasos. **El orden importa.**

Todo esto se hace desde el panel: **Seguridad financiera → control C-06 → botón
«Preparar la llave del cofre»**. No hace falta ninguna terminal.

Al final de este documento, en el anexo, está el mismo procedimiento con el
guión de línea de comandos, para quien prefiera ése.

### Paso 1 — Generar la llave

En el panel, «Preparar la llave del cofre» → **Generar una llave**.

La muestra **una sola vez**. No se vuelve a mostrar y no se puede recuperar.

También muestra una **huella**: ocho caracteres que identifican a la llave sin
revelarla. La huella se puede anotar en cualquier lado, mandar por chat y dejar
a la vista. Sirve para reconocer cuál llave es cuál.

**También sirve la contraseña que genere tu gestor.** `COFRE_LLAVE` acepta
cualquier texto de 24 caracteres o más, sorteado al azar. El botón «generar
contraseña» de 1Password o Bitwarden produce una llave perfectamente buena, y
tiene la ventaja de quedar guardada en el gestor en el mismo acto.

### Paso 2 — Guardarla en tres lugares que no fallen juntos

1. **El servidor** — la variable `COFRE_LLAVE` en Railway.
2. **Un gestor de contraseñas** — 1Password, Bitwarden, el que uses.
3. **Papel** — escrita a mano, donde guardás lo importante.

Tres, y que no fallen juntos: si los tres están en la misma computadora, es un
solo lugar. Si sos más de uno en el negocio, que el papel no lo tenga una sola
persona.

Anotá la **huella** al lado, en los tres. Es lo que después te va a dejar saber
si la que tenés es la buena.

### Paso 3 — Comprobar que la copiaste bien

Esto es lo que hace que el paso 2 valga algo. Tomá la llave **de donde la
anotaste** —no de la pantalla donde se generó— y pegala en el paso 2 del panel,
«Comprobar una copia de respaldo».

Contesta tres cosas por separado:

| Lo que dice | Qué significa |
|---|---|
| Tiene forma de llave válida | El texto sirve como llave. Es lo mínimo. |
| Es la misma que está puesta en el servidor | Coincide con la que está corriendo ahora. |
| Con ella se abren los documentos ya guardados | **La que importa**: con esta copia se recuperan las fotos. |

Un renglón en gris quiere decir «no se pudo comprobar», que **no** es «no». Con
el cofre todavía apagado es lo normal: no hay nada cifrado con qué comparar.

Hacelo con cada una de las tres copias. Lleva dos minutos y es el único momento
en que se puede descubrir un error de copia sin consecuencias.

### Paso 4 — Prender

En Railway, **las dos variables en el mismo guardado**:

```
COFRE_LLAVE = <la llave>
COFRE_MODO  = cifrando
```

⚠️ `COFRE_MODO` sin `COFRE_LLAVE` deja el cofre prendido sin con qué cifrar, y
los expedientes nuevos no se pueden guardar. Por eso van juntas.

Desde ese momento, **los documentos nuevos se guardan cifrados**. Los que ya
estaban siguen en claro y se leen igual: la aplicación entiende las dos formas.

Comprobá que arrancó bien: volvé al control C-06 del panel. Tiene que decir modo
**Cifrando**, dictamen **conforme**, y **la misma huella** que anotaste.

---

## 3. Cifrar lo que ya estaba guardado

Es un paso aparte y se hace cuando el paso 2 ya funciona bien.

**Antes:** pedile a Railway un respaldo de la base, o hacelo vos. Es una
operación que reescribe documentos de personas reales.

Primero un simulacro, que hace todo menos escribir:

```bash
python backend/scripts/cofre.py cifrar --simulacro
```

Si el simulacro no reporta problemas:

```bash
python backend/scripts/cofre.py cifrar
```

Se puede cortar con Ctrl-C y volver a correr: lo ya cifrado se saltea.

**Cómo trabaja, para que sepas por qué es seguro:** por cada foto la cifra, la
vuelve a abrir, comprueba que salió idéntica a la original, y recién ahí la
escribe. Si la comprobación falla, deja la foto como estaba y sigue. Nunca
reemplaza un documento por algo que no comprobó que se recupera.

---

## 4. Si algo sale mal

### «El cofre dice que la llave no es la correcta»

Alguien cambió `COFRE_LLAVE` por otra. **No toques nada más** — sobre todo, no
corras `cifrar`.

1. Mirá qué huella espera: `python backend/scripts/cofre.py estado`.
2. Buscá entre tus copias la que tenga esa huella.
3. Poné esa en `COFRE_LLAVE`.

Los documentos están intactos: lo único que pasa es que la llave puesta no los
abre.

### «Prendí el cofre y quiero volver atrás»

Poné `COFRE_MODO=apagado`. Los documentos nuevos vuelven a guardarse en claro, y
los que ya se cifraron **se siguen leyendo**, siempre que `COFRE_LLAVE` siga
puesta. No borres esa variable.

Para volver del todo a texto plano hay que descifrar lo cifrado; pedilo antes de
sacar la llave.

### «Perdí la llave»

Si te quedan documentos cifrados y ninguna copia de la llave, esos documentos no
se recuperan. Lo que se puede hacer:

1. `COFRE_MODO=apagado`, para que lo nuevo se guarde en claro y el KYC siga
   funcionando.
2. Volver a pedirle los documentos a las personas afectadas.
3. Empezar de nuevo desde el paso 1, esta vez completando el paso 3.

---

## 5. Cambiar la llave

Sólo hace falta si sospechás que alguien la vio.

1. Generá una nueva (`crear`) y guardala como en el paso 2.
2. Poné la **vieja** en `COFRE_LLAVE_ANTERIOR` y la **nueva** en `COFRE_LLAVE`.
3. Corré `cifrar`: lo que estaba con la vieja se vuelve a cifrar con la nueva.
4. Cuando `estado` diga que está todo bien, sacá `COFRE_LLAVE_ANTERIOR`.

La llave vieja se sigue probando al leer mientras esté puesta. Por eso una
rotación a medio camino no rompe nada.

---

## 6. Resumen

| Situación | `COFRE_MODO` | `COFRE_LLAVE` | Qué pasa |
|---|---|---|---|
| Hoy, sin hacer nada | apagado | vacía | Todo en claro, como siempre |
| Cofre prendido | cifrando | puesta | Lo nuevo cifrado, lo viejo en claro, todo se lee |
| Después de `cifrar` | cifrando | puesta | Todo cifrado |
| Vuelta atrás | apagado | **puesta** | Lo nuevo en claro, lo cifrado se sigue leyendo |
| Error | cifrando | vacía o equivocada | El KYC falla con un error claro; **las remesas siguen andando** |

La última fila es a propósito: un cajón que no abre no puede cerrar el negocio
entero.

---

## Anexo — Lo mismo desde una terminal

El guión hace lo mismo que el panel, para quien prefiera la línea de comandos.
Corre en cualquier carpeta del proyecto y sólo necesita `cryptography`
instalado (`pip install cryptography`); las órdenes `crear` y `verificar` no
tocan la base de datos.

```bash
python backend/scripts/cofre.py crear       # paso 1: generar la llave
python backend/scripts/cofre.py verificar   # paso 3: comprobar una copia
python backend/scripts/cofre.py estado      # paso 4: cómo quedó
```

Para `verificar`, la llave va delante de la orden:

```bash
COFRE_LLAVE='<la que anotaste>' python backend/scripts/cofre.py verificar
```

`estado` y `cifrar` necesitan llegar a la base, así que además hace falta
`MONGO_URL` y `DB_NAME` apuntando a la de producción.

**Por qué el panel es el camino principal y esto el anexo.** Porque el cofre
estuvo apagado desde que se escribió, y no por falta de código: producir una
llave exigía una terminal, y el paso que de verdad protege los documentos
quedaba fuera del alcance de quien tiene que darlo. Configurar no puede requerir
tocar código.
