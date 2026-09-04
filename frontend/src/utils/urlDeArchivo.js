/**
 * urlDeArchivo.js — De dónde se puede sacar una imagen, y de dónde no.
 *
 * EL AGUJERO QUE ESTE MODULO CIERRA
 *
 *   Los comprobantes, los documentos del KYC y los adjuntos del chat llegan
 *   como TEXTO y se guardan como texto. La pantalla los usaba tal cual:
 *
 *       <a href={usuario.id_document_image} target="_blank">
 *       onClick={() => window.open(tx.proof_image, '_blank')}
 *
 *   Un `href` o un `window.open` con `javascript:...` NO abre nada: ejecuta ese
 *   código en el origen de la página, con la sesión de quien hizo click. La
 *   cookie es httpOnly, así que ese código no puede robársela — pero no la
 *   necesita: ya está adentro, y puede pedirle a la API todo lo que quien mira
 *   pueda pedir.
 *
 *   Y quien mira estos campos es un administrador. O sea: el que sube el
 *   archivo elige el texto, y el que lo abre es el que puede aprobar KYCs y
 *   mover plata. Es el peor par posible.
 *
 * COMO SE CIERRA
 *
 *   Con una LISTA DE LO PERMITIDO, no de lo prohibido. Y la diferencia no es
 *   de estilo: filtrar `javascript:` por nombre no alcanza, porque los
 *   navegadores ignoran los espacios y los caracteres de control antes y DENTRO
 *   del esquema. «java<TAB>script:alert(1)» y « javascript:alert(1)» se
 *   ejecutan igual y no contienen la palabra. Una lista de lo prohibido tiene
 *   que adivinar todas esas formas; una de lo permitido no tiene que adivinar
 *   nada: lo que no es una de las cuatro cosas de abajo, no pasa.
 *
 *   Lo que se permite es lo que la aplicación usa de verdad:
 *     - una ruta propia   (`/api/media/...`)
 *     - `https:` y `http:`
 *     - `data:image/...` salvo SVG, que lleva scripts adentro
 *     - `blob:`, que es la vista previa de un archivo recién elegido
 *
 *   Todo lo demás devuelve `null`, y la pantalla muestra «no disponible» en vez
 *   de un link del que no se sabe qué hace.
 *
 * POR QUE TAMBIEN ACA Y NO SOLO EN EL SERVIDOR
 *
 *   El servidor valida lo que entra DESDE AHORA. Lo que ya está guardado entró
 *   antes, y este módulo es lo único que lo mira antes de abrirlo.
 */

/** Los tipos de imagen que se pueden incrustar. SVG no: lleva script adentro. */
const TIPOS_DATA = ['png', 'jpeg', 'jpg', 'gif', 'webp', 'bmp', 'avif'];

/**
 * Saca lo que el navegador ignora al leer el esquema: los espacios y TODOS los
 * caracteres de control, estén donde estén.
 *
 * NO ES ESTO LO QUE PROTEGE, Y CONVIENE SABERLO
 *
 *   Se probó cambiando esta línea por un `trim()` pelado, y los tests siguen
 *   todos en verde: ninguno de los bypass conocidos pasa igual. La razón es que
 *   protege la LISTA DE LO PERMITIDO — «java<TAB>script:» tampoco empieza con
 *   `/`, ni con `https://`, ni con `data:image/`, así que cae por no estar en
 *   la lista, no por la limpieza.
 *
 *   Queda porque las comparaciones de `rutaDeArchivo` (`startsWith('/api/…')`,
 *   `includes('api.twilio.com')`) tienen que mirar el mismo texto que va a leer
 *   el navegador. Pero si alguna vez alguien cambia la lista de lo permitido
 *   por una de lo prohibido, esto NO alcanza para tapar la diferencia.
 */
function normalizar(valor) {
  if (typeof valor !== 'string') return '';
  // eslint-disable-next-line no-control-regex
  return valor.replace(/[\u0000-\u0020\u007F]/g, '');
}

/** ¿Es un `data:` de imagen, y de un tipo que no ejecuta nada? */
function esDataDeImagen(limpio) {
  const m = /^data:image\/([a-z0-9.+-]+)[;,]/i.exec(limpio);
  return Boolean(m) && TIPOS_DATA.includes(m[1].toLowerCase());
}

/**
 * La URL si se puede abrir, `null` si no.
 *
 * Devuelve el valor ORIGINAL, no el normalizado: sacarle caracteres a una URL
 * legítima la rompería. La normalización es sólo para decidir.
 */
export function urlDeArchivoSegura(valor) {
  const limpio = normalizar(valor);
  if (!limpio) return null;

  // Una ruta nuestra. `//` no: eso es «otro sitio, mismo protocolo».
  if (limpio.startsWith('/') && !limpio.startsWith('//')) return valor;

  if (/^https?:\/\//i.test(limpio)) return valor;
  if (esDataDeImagen(limpio)) return valor;
  if (/^blob:/i.test(limpio)) return valor;

  return null;
}

/** ¿Se puede mostrar? Para decidir entre dibujar el bloque o el «no disponible». */
export function sePuedeAbrir(valor) {
  return urlDeArchivoSegura(valor) !== null;
}

/**
 * La ruta desde la que se pide un medio.
 *
 * Estaba copiada como `convertTwilioUrl` en `AdminPanel.jsx` y en `History.jsx`,
 * con el mismo cuerpo en los dos. Vive acá para que la limpieza se aplique en
 * los dos lugares y no en uno solo.
 */
export function rutaDeArchivo(valor) {
  const seguro = urlDeArchivoSegura(valor);
  if (seguro === null) return null;

  const limpio = normalizar(seguro);
  if (limpio.startsWith('/api/static/') || limpio.startsWith('/api/media/')) return seguro;
  if (limpio.startsWith('data:')) return seguro;

  if (limpio.includes('api.twilio.com')) {
    const m = limpio.match(/\/Accounts\/(AC[^/]+\/.*)/);
    // El proxy de medios sólo acepta este formato. Si no calza, no hay ruta:
    // devolver la URL cruda de Twilio mandaría al navegador a pedirla sin
    // credenciales y a mostrar un 401 dentro de un `<img>`.
    return m ? `/api/media/twilio/${m[1]}` : null;
  }
  return seguro;
}

/**
 * Abrir un archivo en otra pestaña.
 *
 * `noopener` además de la lista: sin él, la pestaña que se abre puede cambiar
 * la nuestra con `window.opener.location`, que es una pantalla de login falsa a
 * un click de distancia.
 */
export function abrirArchivo(valor) {
  const url = rutaDeArchivo(valor);
  if (url === null) return false;
  window.open(url, '_blank', 'noopener,noreferrer');
  return true;
}

/** Bajar un archivo, con el mismo criterio. Devuelve si se pudo. */
export function bajarArchivo(valor, nombre) {
  const url = rutaDeArchivo(valor);
  if (url === null) return false;
  const a = document.createElement('a');
  a.href = url;
  a.download = nombre || 'archivo';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  return true;
}
