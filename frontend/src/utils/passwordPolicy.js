/**
 * utils/passwordPolicy.js — La politica de contrasena, en UN solo lugar.
 *
 * POR QUE EXISTE ESTE MODULO
 *     Es el espejo de validate_password() en backend/utils/security.py. Cada pantalla
 *     que pide una contrasena tenia su propia copia de las reglas, y las copias se
 *     desincronizaron: una exigia 7 caracteres, otra 6, otra aceptaba simbolos que el
 *     backend rechaza. El usuario pasaba la validacion del formulario y recibia del
 *     servidor un error con otra regla.
 *
 *     Ahora las cuatro pantallas importan de aca. Si cambia la politica del backend,
 *     se cambia este archivo y nada mas.
 *
 * QUE EXPORTA
 *     PASSWORD_SPECIAL_CHARS  el set de simbolos como string, para interpolarlo en los
 *                             mensajes de error y en los textos de ayuda (que asi no
 *                             pueden contradecir a la validacion).
 *     passwordRules(pwd)      un booleano por regla. Para las pantallas que muestran
 *                             el checklist en vivo mientras el usuario tipea.
 *     validarPassword(pwd)    el primer mensaje de error, o null si la contrasena pasa.
 *     PASSWORD_HELP_TEXT      el texto de ayuda bajo el campo, ya armado.
 */

export const PASSWORD_MIN_LENGTH = 8;

// Set identico al de validate_password() en el backend. Si aca agregas un simbolo que
// el backend no acepta, volves a crear el bug que este modulo vino a cerrar.
export const PASSWORD_SPECIAL_CHARS = '!@#$%^&*(),.?":{}|<>';

const REGEX_ESPECIALES = /[!@#$%^&*(),.?":{}|<>]/;

/** Un booleano por regla, en el mismo orden en que se le muestran al usuario. */
export function passwordRules(pwd) {
  const valor = pwd || '';
  return {
    length: valor.length >= PASSWORD_MIN_LENGTH,
    uppercase: /[A-Z]/.test(valor),
    lowercase: /[a-z]/.test(valor),
    number: /\d/.test(valor),
    special: REGEX_ESPECIALES.test(valor),
  };
}

/** Devuelve el primer error como string, o null si la contrasena cumple todo. */
export function validarPassword(pwd) {
  const reglas = passwordRules(pwd);
  if (!reglas.length) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres`;
  if (!reglas.uppercase) return 'La contraseña debe contener al menos una letra mayúscula';
  if (!reglas.lowercase) return 'La contraseña debe contener al menos una letra minúscula';
  if (!reglas.number) return 'La contraseña debe contener al menos un número';
  if (!reglas.special) return `La contraseña debe contener al menos un carácter especial (${PASSWORD_SPECIAL_CHARS})`;
  return null;
}

/** Texto de ayuda bajo el campo. Sale de las mismas constantes que la validacion. */
export const PASSWORD_HELP_TEXT = `Mínimo ${PASSWORD_MIN_LENGTH} caracteres, con mayúscula, minúscula, número y símbolo (${PASSWORD_SPECIAL_CHARS})`;
