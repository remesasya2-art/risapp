/**
 * montoDeLaUrl — el monto con el que arranca una pantalla de envío, si vino
 * en la dirección.
 *
 *   La calculadora del inicio lo manda como `?monto=245.54`, en reales, para
 *   que la persona no tenga que tipear de nuevo lo que acaba de escribir. Las
 *   dos pantallas de envío (`Send.jsx` y `SendReais.jsx`) toman el monto en
 *   reales, así que el mismo número sirve para las dos.
 *
 *   SOLO UN NUMERO POSITIVO. La dirección la escribe cualquiera: un texto, un
 *   negativo o un cero no arrancan la pantalla con basura en la casilla, la
 *   arrancan vacía, como si no hubiera venido nada.
 *
 * @param {URLSearchParams} parametros  Los de `useSearchParams()`.
 * @returns {string} Lo que va en la casilla: el número, o ''.
 */
export function montoDeLaUrl(parametros) {
  const crudo = parametros?.get?.('monto');
  if (!crudo) return '';
  const n = Number(String(crudo).replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? String(n) : '';
}
