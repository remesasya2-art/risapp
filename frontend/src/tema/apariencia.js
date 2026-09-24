/**
 * apariencia.js — claro, oscuro o automático, y cómo se le avisa a la página.
 *
 * TRES VALORES QUE SE ELIGEN, DOS QUE SE PINTAN
 *
 *   La persona elige 'auto', 'claro' u 'oscuro'. La página sólo sabe pintar
 *   'claro' u 'oscuro': 'auto' se resuelve acá mirando lo que dice el aparato.
 *   Lo resuelto se escribe en `<html data-tema="...">`, y la hoja de estilos
 *   (index.css) cuelga los colores de ese atributo.
 *
 * POR QUE NO SE TOCA `color-scheme` EN EL <html>
 *
 *   `color-scheme: dark` en el documento entero le cambia al navegador los
 *   colores de TODOS los campos, listas y barras de desplazamiento que no
 *   tienen color propio. Las pantallas que todavía no pasaron al tema nuevo
 *   tienen muchos: quedarían campos oscuros con letra oscura, ilegibles. Por
 *   eso `color-scheme` va sólo dentro de `.con-tema`, que es la marca de las
 *   pantallas ya preparadas.
 *
 * POR QUE HAY UNA COPIA EN EL APARATO SI LA ELECCION VIVE EN LA CUENTA
 *
 *   La portada y el login se ven antes de saber de quién es la cuenta, y al
 *   abrir la app se pinta la primera pantalla antes de que conteste el
 *   servidor. Sin la copia, quien eligió oscuro vería un destello blanco cada
 *   vez. La cuenta manda; la copia sólo adelanta.
 */

export const APARIENCIAS = ['auto', 'claro', 'oscuro'];
const CLAVE = 'apariencia';
const OSCURO_DEL_APARATO = '(prefers-color-scheme: dark)';

export function esValida(valor) {
  return APARIENCIAS.includes(valor);
}

// El almacenamiento del navegador puede no estar (modo privado, bloqueado por
// la configuración): leer o escribir ahí nunca puede tirar la pantalla.
export function leerDelAparato() {
  try {
    const v = window.localStorage.getItem(CLAVE);
    return esValida(v) ? v : 'auto';
  } catch {
    return 'auto';
  }
}

export function guardarEnElAparato(valor) {
  try {
    window.localStorage.setItem(CLAVE, valor);
  } catch {
    // Sin almacenamiento, la elección dura lo que dura la pestaña. Nada más.
  }
}

export function elAparatoPrefiereOscuro() {
  try {
    return window.matchMedia(OSCURO_DEL_APARATO).matches;
  } catch {
    return false;
  }
}

export function resolver(apariencia) {
  if (apariencia === 'oscuro') return 'oscuro';
  if (apariencia === 'claro') return 'claro';
  return elAparatoPrefiereOscuro() ? 'oscuro' : 'claro';
}

export function aplicar(apariencia) {
  const tema = resolver(apariencia);
  document.documentElement.dataset.tema = tema;
  return tema;
}

// Avisa cuando el aparato cambia solo de claro a oscuro (al anochecer, por
// ejemplo). Devuelve la función que deja de escuchar.
export function alCambiarElAparato(avisar) {
  let consulta;
  try {
    consulta = window.matchMedia(OSCURO_DEL_APARATO);
  } catch {
    return () => {};
  }
  consulta.addEventListener('change', avisar);
  return () => consulta.removeEventListener('change', avisar);
}
