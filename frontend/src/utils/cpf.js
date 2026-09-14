/**
 * cpf.js — Qué es un CPF válido, del lado del navegador.
 *
 * ES LA MISMA CUENTA QUE `backend/services/cpf.py`, Y ESTA EN LOS DOS LADOS
 *
 *   El servidor es el que decide: acá se puede apagar con la consola abierta,
 *   y por eso el registro y la recarga lo vuelven a comprobar allá. Esto está
 *   para que la persona se entere ANTES de mandar el formulario, no después.
 *
 *   Si las dos cuentas se separan, lo que pasa es que el navegador acepta algo
 *   que el servidor rechaza —o al revés—, y el cliente ve un error que no
 *   entiende. Son quince líneas idénticas a propósito.
 *
 * POR QUE NO ALCANZA CON CONTAR ONCE DIGITOS
 *
 *   El CPF lleva dos dígitos verificadores calculados sobre los nueve
 *   primeros: de cada cien números de once cifras, sólo uno es un CPF posible.
 *   Contar once acepta un teléfono tipeado en el campo equivocado, y acepta
 *   cualquier dedo que se equivoque en una cifra — que es el error que más
 *   pasa y el que queda guardado hasta que hay que reclamar un pago.
 */

/** Los once dígitos repetidos pasan la cuenta pero no son documentos de nadie. */
const TODOS_IGUALES = new Set(
  Array.from({ length: 10 }, (_, d) => String(d).repeat(11)),
);

/** Los dígitos, sin puntos ni guiones. Es lo que se manda al servidor. */
export function normalizarCpf(valor) {
  return String(valor || '').replace(/\D/g, '');
}

function digitoVerificador(digitos, pesoInicial) {
  let suma = 0;
  for (let i = 0; i < digitos.length; i += 1) {
    suma += Number(digitos[i]) * (pesoInicial - i);
  }
  const resto = (suma * 10) % 11;
  // 10 y 11 valen cero: es parte de la fórmula, no un caso borde nuestro.
  return resto >= 10 ? '0' : String(resto);
}

/** `true` si el número puede ser un CPF. */
export function cpfEsValido(valor) {
  const n = normalizarCpf(valor);
  if (n.length !== 11 || TODOS_IGUALES.has(n)) return false;
  return n[9] === digitoVerificador(n.slice(0, 9), 10)
      && n[10] === digitoVerificador(n.slice(0, 10), 11);
}

/** «123.456.789-09», para el campo. Nunca para mandar ni comparar. */
export function formatearCpf(valor) {
  const n = normalizarCpf(valor).slice(0, 11);
  if (n.length <= 3) return n;
  if (n.length <= 6) return `${n.slice(0, 3)}.${n.slice(3)}`;
  if (n.length <= 9) return `${n.slice(0, 3)}.${n.slice(3, 6)}.${n.slice(6)}`;
  return `${n.slice(0, 3)}.${n.slice(3, 6)}.${n.slice(6, 9)}-${n.slice(9)}`;
}

/**
 * El mensaje de lo que está mal, o cadena vacía si está bien.
 *
 * Se devuelve el TEXTO y no un booleano porque los dos motivos de rechazo se
 * arreglan distinto: «te falta un dígito» y «ese número no existe» mandan a la
 * persona a mirar cosas diferentes.
 */
export function queLeFaltaAlCpf(valor) {
  const n = normalizarCpf(valor);
  if (!n) return 'Ingresá tu CPF.';
  if (n.length !== 11) return 'El CPF tiene once dígitos.';
  if (!cpfEsValido(n)) return 'Ese CPF no es válido. Revisá los números.';
  return '';
}
