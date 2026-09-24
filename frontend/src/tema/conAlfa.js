/**
 * conAlfa — un color con transparencia, sea un color escrito o una variable.
 *
 * POR QUE NO SE PEGAN LAS DOS CIFRAS AL FINAL
 *
 *   La costumbre era sumarle las dos cifras al color: a `#d97706` le quedaba
 *   `#d9770633`, el mismo naranja al 20 %. Con el modo oscuro los colores pasaron a ser
 *   variables —`var(--en-oscuro-alerta, #d97706)`— y pegarle `33` a eso da un
 *   texto que ningún navegador entiende: el borde o el fondo desaparecen sin
 *   aviso, también en claro.
 *
 *   `color-mix` acepta variables. Se comprobó en Chromium que da los mismos
 *   píxeles que la forma vieja, para cada transparencia que usa el panel.
 *
 * `alfa` va en las mismas dos cifras hexadecimales de antes ('33', '55'), para
 * que cambiar una línea vieja sea sólo envolverla.
 */
export default function conAlfa(color, alfa) {
  const porcentaje = ((parseInt(alfa, 16) / 255) * 100).toFixed(4);
  return `color-mix(in srgb, ${color} ${porcentaje}%, transparent)`;
}
