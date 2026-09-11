# Cómo se trabaja en este repositorio

Este archivo lo lee Claude al empezar cualquier sesión sobre `risapp`. Está
escrito para que no haya que repetir lo mismo cada vez.

## El idioma

**Todo en español.** La conversación, los mensajes de commit, los cuerpos de los
pull requests, los comentarios del código y los nombres de los tests. El
repositorio ya está así y conviene que siga.

Y en español llano, no en jerga. Si hace falta un término técnico, explicarlo la
primera vez: «migración» no le dice nada a nadie que no escriba código.

## El orden de las cosas

Este es el flujo pedido, y **no se salta ningún paso**:

1. **Investigar.** Leer el código que importa antes de opinar. Comprobar las
   cosas ejecutándolas, no deduciéndolas.
2. **Proponer un plan.** Contar qué se encontró y qué se propone hacer. Cuando
   hay más de un camino razonable, presentar las opciones con lo que gana y
   pierde cada una.
3. **Esperar.** El plan lo elige el dueño del proyecto. **No se escribe código
   antes de esa respuesta.**
4. **Mostrar cómo queda en pantalla**, con capturas reales de la aplicación
   corriendo. No bocetos: la app de verdad, en un navegador de verdad. La receta
   está más abajo.
5. **Correr los tests.** La suite completa del backend, y las guardas nuevas
   probadas por mutación.
6. **Abrir el pull request** en borrador, con el cuerpo explicando qué cambió y
   qué hay que revisar después de desplegar.
7. **Fusionar sólo cuando se pida.** Ni sacar de borrador ni fusionar por
   iniciativa propia.

El paso 3 es el que más se salta y el que más molesta cuando se salta. Encontrar
un defecto no autoriza a arreglarlo sin preguntar.

## Las capturas de pantalla

Hacen falta un backend y un frontend levantados. No hay MongoDB en el entorno de
las sesiones, así que el backend se levanta contra `mongomock`, igual que los
tests, con la sesión sustituida para no pasar por el login.

    # Backend de vista previa, en el puerto 8001. Tarda ~90 s en arrancar:
    # varios servicios abren su propia conexión a Mongo y esperan a que caduque.
    # Hay que lanzarlo en segundo plano SIN tuberías: un `| tail` se traga la
    # salida, y un `nohup` suelto lo mata el entorno al terminar la llamada.

    # Frontend, apuntando ahí sin tocar el repositorio:
    cd frontend && npm install --legacy-peer-deps
    VITE_API_URL=http://localhost:8001/api npm run dev

    # Chromium ya está instalado. La librería no:
    pip install playwright
    # El binario está en /opt/pw-browsers/chromium-1194/chrome-linux/chrome
    # (la ruta lleva número de versión; `/opt/pw-browsers/chromium/` no existe).

Para entrar sin login, el frontend sólo mira `localStorage`:

    localStorage.setItem('has_session', '1');
    localStorage.setItem('last_activity', Date.now().toString());

El chat de soporte del cliente no tiene ruta propia: es el botón flotante de la
esquina inferior derecha del panel.

Los errores 403 que aparecen en la consola del navegador son recursos externos
—Cloudflare, fuentes— que el proxy del entorno bloquea. No son fallos de la
aplicación.

## Los tests

La suite completa se corre así, y tiene que quedar **entera** en verde:

    cd backend && python -m pytest tests/ -q

`mongomock-motor` es obligatorio. Sin él, cientos de tests se saltan **en
silencio** y la suite termina en verde igual. El número total importa: si baja
de golpe, algo se está salteando.

`http_ece` y `pywebpush` no compilan en este entorno. Se instala el resto y se
sustituye `pywebpush` por un doble que no hace nada.

### Mutación

**Cada guarda nueva se rompe a propósito y se confirma que un test se pone en
rojo.** Una guarda sin mutación probada es una guarda que no se sabe si anda.

Esto no es ceremonia: en este repositorio apareció así que dos guardas
redundantes se tapaban entre sí, y ninguna estaba realmente probada.

### Lo que `mongomock` no puede ver

No es MongoDB. La diferencia que ya causó dos errores 500 en producción: el
dinero se guarda en `Decimal128`, y `mongomock` lo conserva **sólo si el test lo
inserta así**. Un test que escribe `1234.56` a secas pasa con el producto roto.

**La plata en los tests se escribe con `to_decimal128`, igual que la escribe la
aplicación.**

## Reglas del proyecto que no se discuten

Están explicadas en el código, con el motivo al lado. En resumen:

- **`Decimal` en todo el dinero.** Nunca `float`. En los bordes de la API,
  strings; al guardar, `Decimal128`; al mostrar, `to_float`.
- **Proyecciones por lista de lo permitido** en todo lo que ve el usuario. Una
  lista de lo prohibido deja pasar cada campo nuevo hasta que alguien se acuerde.
- **Ningún nombre real de empresa de transporte** en el código: se referencian
  por su código alfanumérico (`TRP-7K2M`). No hay un test que recorra el
  repositorio buscándolos; lo que sí hay son tests que comprueban que los
  mensajes al usuario citen el código y no una marca — por ejemplo
  `test_quien_impone_el_limite_devuelve_el_codigo_y_no_una_marca`.
- **Ninguna dirección de correo personal** en el código. Éste sí tiene un
  guardián que recorre todo el repositorio:
  `tests/test_sin_cuentas_con_nombre_propio.py`. Se usa el rol
  (`role == 'super_admin'`), no la cuenta, porque proteger una cuenta por su
  nombre la publica — y en el frontend el bundle se le sirve a cada visitante.
  En los datos de prueba, dominios de ejemplo, nunca un proveedor real.
- **Nunca «cruce de frontera»**: se dice «traslado transfronterizo». Es una
  convención escrita, sin test que la vigile.
- **Configurar nunca puede requerir editar código en GitHub.**

## Los comentarios del código

El repositorio tiene una costumbre que conviene sostener: los comentarios
explican **por qué**, no qué. Y cuando algo está escrito de una forma rara,
cuentan qué pasó la vez que se escribió de la forma obvia.

Son los comentarios que evitan que alguien «simplifique» una guarda dentro de
seis meses.
