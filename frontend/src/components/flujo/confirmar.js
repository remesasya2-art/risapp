/**
 * confirmar.js — Preguntar antes de hacer algo, sin cuadros del navegador.
 *
 * Acá viven las FUNCIONES. La ventana que dibuja la pregunta está en
 * `ConfirmacionHost.jsx`, y se monta una sola vez en la raíz.
 *
 * EL DEFECTO QUE CIERRA, Y NO ES DE ESTILO
 *
 *   `window.confirm` y `window.prompt` PUEDEN DEJAR DE APARECER, y cuando eso
 *   pasa devuelven `false` y `null`. O sea: el botón no hace nada. Sin error,
 *   sin aviso, sin nada en la consola.
 *
 *   No es teórico ni raro. Chrome ofrece «Impedir que esta página cree más
 *   diálogos» en cuanto una página abre varios seguidos, y la casilla queda
 *   puesta para todo el sitio hasta que se recarga. Quien abre varios seguidos
 *   es exactamente el operador que está procesando una cola de pagos: aprueba,
 *   confirma, aprueba, confirma… y en algún momento tilda la casilla para
 *   sacarse el cuadro de encima.
 *
 *   A partir de ahí, «Aprobar» deja de aprobar. El operador clickea, no pasa
 *   nada, vuelve a clickear. La plata no se mueve y nadie sabe por qué.
 *
 *   El mismo cuadro también se bloquea en la aplicación instalada y en algunos
 *   navegadores embebidos, que es como entra buena parte de la gente.
 *
 * POR QUE ESTA FORMA
 *
 *   Igual que `toast()`, que esta aplicación ya usa: una función de módulo que
 *   se llama desde cualquier lado y un host montado una sola vez en la raíz.
 *   Así cada lugar que preguntaba con `window.confirm` cambia UNA línea:
 *
 *       if (!window.confirm('¿Aprobar?')) return;
 *       if (!await confirmar({ titulo: '¿Aprobar?' })) return;
 *
 *   No hay que reestructurar la pantalla, ni subir estado, ni pasar props por
 *   tres niveles. Eso importa: son veintiún lugares, varios adentro de
 *   pantallas de dos mil líneas que mueven plata, y un cambio de una línea se
 *   puede leer y verificar. Uno de veinte, no.
 *
 * LO QUE MEJORA DE PASO
 *
 *   `window.prompt` no valida, no limita el largo, y no distingue «cancelé» de
 *   «lo dejé vacío» salvo por `null`. Los motivos que se escribían ahí —el de
 *   un baneo, el del rechazo de una recarga, el de la baja de una persona—
 *   quedan asentados en el libro de auditoría. `pedirTexto` los limita, los
 *   recorta y sí distingue cancelar de dejar vacío.
 */

/* ─── El canal entre la función y el host ──────────────────────────────── */

let pedirAlHost = null;

/**
 * El host se anota acá al montarse, y se borra al desmontarse.
 *
 * Vive en este archivo y no en el del componente porque `confirmar()` y
 * `pedirTexto()` se llaman desde módulos que no dibujan nada: si acá hubiera
 * JSX, cada pantalla que sólo quiere preguntar arrastraría el componente.
 */
export function registrarHost(fn) {
  pedirAlHost = fn;
  return () => { if (pedirAlHost === fn) pedirAlHost = null; };
}

/** Lo que se muestra cuando no hay un host montado. Ver `sinHost`. */
function sinHost(que) {
  // Si esto pasa, es un error de programación: falta `<ConfirmacionHost />` en
  // la raíz. Se avisa fuerte y se responde que NO. Nunca que sí: una pregunta
  // que no se pudo hacer no es un permiso concedido, y del otro lado de estas
  // preguntas hay pagos, baneos y bajas.
  console.error('[confirmar] Falta <ConfirmacionHost /> en la raíz de la aplicación.', que);
  return null;
}

/**
 * Pregunta y devuelve `true` sólo si la persona dijo que sí.
 *
 * @param {object} opciones
 * @param {string} opciones.titulo    La pregunta. Corta y en la voz de la app.
 * @param {string} [opciones.detalle] Qué va a pasar. Lo que no entra en el título.
 * @param {string} [opciones.accion]  El texto del botón que confirma.
 * @param {'peligro'|'normal'} [opciones.tono]
 */
export function confirmar(opciones) {
  if (!pedirAlHost) return Promise.resolve(Boolean(sinHost(opciones)));
  return pedirAlHost({ ...opciones, clase: 'confirmar' })
    .then((r) => r !== null);
}

/**
 * Pide un texto. Devuelve lo escrito, o `null` si canceló.
 *
 * `null` es cancelar y `''` es «lo dejé vacío». Son cosas distintas y el
 * llamador tiene que poder distinguirlas: en un motivo opcional, cancelar
 * quiere decir «no hagas nada» y vacío quiere decir «hacelo sin motivo».
 */
export function pedirTexto(opciones) {
  if (!pedirAlHost) return Promise.resolve(sinHost(opciones));
  return pedirAlHost({ ...opciones, clase: 'texto' });
}
