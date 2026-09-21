/**
 * calculadora — las cuentas de la calculadora del inicio, sin React.
 *
 * POR QUE VIVE APARTE DE LA PANTALLA
 *
 *   Por lo mismo que `envioAVenezuela.js`: una cuenta que muestra dinero se
 *   prueba con números exactos, y una función sin React se prueba con node en
 *   un renglón. La pantalla sólo dibuja lo que esto devuelve.
 *
 * DOS SENTIDOS, DOS TASAS, Y NO SE MEZCLAN
 *
 *   Brasil → Venezuela usa `ris_to_ves` (bolívares por 1 real, la tasa con la
 *   que se cotiza «Gastar en Venezuela»). Venezuela → Brasil usa
 *   `ves_to_ris_rate` (bolívares por 1 real en el sentido inverso, la de
 *   «Gastar en Brasil»). Son números distintos que el dueño carga por separado,
 *   y el servidor les aplica a los dos su ajuste de horario antes de
 *   publicarlos. La elección de cuál va con cada sentido está en UN lugar,
 *   `tasaDelSentido`, para que una pantalla no pueda usar la equivocada.
 *
 * SIN TASA NO HAY CUENTA
 *
 *   `RateContext` deja 110 y 140 como relleno cuando `/rate` no contesta, y
 *   avisa con `tasaDisponible`. Con eso en falso no se calcula nada: mostrar
 *   una cifra inventada en la pantalla principal es peor que no mostrarla.
 */

export const A_VENEZUELA = 'a_venezuela';   // se pagan reales, llegan bolívares
export const A_BRASIL = 'a_brasil';         // se pagan bolívares, llegan reales

// Las tres casillas. En las dos direcciones son las mismas monedas: lo que
// cambia es cuál se paga y cuál llega, y la tasa.
export const REALES = 'brl';
export const BOLIVARES = 'ves';
export const DOLARES_BCV = 'usd';

/** Lo que la persona escribió, como número. Acepta «1.234,56» y «1234.56». */
export function aNumero(escrito) {
  const texto = String(escrito ?? '').trim();
  if (!texto) return 0;
  // Con coma es formato local: los puntos son de miles. Sin coma, el punto es
  // decimal — es lo que escribe un teclado numérico del teléfono.
  const limpio = texto.includes(',') ? texto.replace(/\./g, '').replace(',', '.') : texto;
  const n = parseFloat(limpio);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Bolívares por 1 real, según el sentido del envío. 0 si no hay tasa. */
export function tasaDelSentido(rates, sentido, tasaDisponible = true) {
  if (!tasaDisponible || !rates) return 0;
  const cruda = sentido === A_BRASIL ? rates.ves_to_ris_rate : rates.ris_to_ves;
  const tasa = Number(cruda);
  return Number.isFinite(tasa) && tasa > 0 ? tasa : 0;
}

/**
 * Las tres casillas a partir de la que se escribió.
 *
 * @param {object} p
 * @param {string} p.origen   REALES, BOLIVARES o DOLARES_BCV: dónde se escribió.
 * @param {number} p.monto    Lo escrito, ya como número.
 * @param {number} p.tasa     Bolívares por 1 real (ver `tasaDelSentido`).
 * @param {number} p.bcv      Bolívares por 1 dólar al BCV. 0 si no hay dato.
 * @returns {{brl:number, ves:number, usd:number}} Todo en 0 si no hay tasa
 *   o no hay monto. `usd` en 0 si falta el BCV.
 */
export function convertir({ origen, monto, tasa, bcv = 0 }) {
  const nada = { brl: 0, ves: 0, usd: 0 };
  if (!(tasa > 0) || !(monto > 0)) return nada;

  // Todo pasa por bolívares: es la moneda que las tres casillas comparten.
  let ves;
  if (origen === REALES) ves = monto * tasa;
  else if (origen === BOLIVARES) ves = monto;
  else if (origen === DOLARES_BCV) ves = bcv > 0 ? monto * bcv : 0;
  else return nada;
  if (!(ves > 0)) return nada;

  return {
    brl: redondear(ves / tasa),
    ves: redondear(ves),
    usd: bcv > 0 ? redondear(ves / bcv) : 0,
  };
}

function redondear(n) {
  return Math.round(n * 100) / 100;
}
