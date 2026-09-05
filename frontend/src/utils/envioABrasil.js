/**
 * envioABrasil.js — Las reglas del envío a Brasil, fuera de la pantalla.
 *
 * POR QUE UN MODULO APARTE
 *
 *   Lo mismo que `envioAVenezuela.js`: la pantalla dibuja, esto decide. Una
 *   regla metida entre el JSX no se puede probar sin montar un navegador, y
 *   termina probándose a mano una vez y nunca más.
 *
 * LO QUE SE ARREGLA ACA, Y NO ES COSMETICO
 *
 *   1. EL CPF NO SE VALIDABA. Al guardar un beneficiario sólo se comprobaba
 *      que el campo no estuviera vacío. Un CPF mal tipeado es plata que sale
 *      hacia una llave que no existe —o peor, hacia otra persona— y se entera
 *      alguien días después. El CPF trae DOS dígitos verificadores calculados
 *      a partir de los otros nueve: un error de tecleo se detecta acá mismo,
 *      sin preguntarle a nadie y sin salir a la red.
 *
 *   2. EL CPF Y LA LLAVE PIX SE MOSTRABAN ENTEROS en la lista de
 *      beneficiarios. Son datos de un tercero, en una pantalla que se abre en
 *      un teléfono y en un colectivo. Para reconocer a quién le estás
 *      mandando alcanza con el nombre y las últimas cifras. Es el mismo
 *      criterio de `cuentaAbreviada` en el flujo de Venezuela.
 *
 *   3. LOS LIMITES NO SE COMPROBABAN ANTES DE PEDIR EL PIN. La pantalla sólo
 *      miraba «mayor que cero y menor que el saldo»; el mínimo, el máximo y
 *      el cupo de la cuenta sin verificar los hacía cumplir el servidor. O
 *      sea que el usuario elegía, ponía su PIN, y RECIEN AHI se enteraba de
 *      que el monto no iba. Poner el PIN para nada es la clase de cosa que
 *      hace desconfiar de una aplicación que maneja plata.
 */

/* ─── El CPF ───────────────────────────────────────────────────────────── */

export function soloDigitos(valor) {
  return String(valor || '').replace(/\D/g, '');
}

/** `123.456.789-09`, que es como lo lee y lo tipea una persona en Brasil. */
export function cpfLegible(valor) {
  const d = soloDigitos(valor);
  if (d.length !== 11) return d;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/**
 * El CPF con su formato legal MIENTRAS se escribe.
 *
 * Los puntos y el guión aparecen solos a medida que entran los dígitos, así
 * que el campo nunca se ve como una tira de once números. Es el formato con el
 * que la persona lo tiene anotado: leerlo igual que como está escrito en el
 * papel es la mitad de no equivocarse al copiarlo.
 *
 * Se acepta borrar: si el usuario retrocede, no se le vuelve a meter el
 * separador que acaba de sacar. Por eso se trabaja sobre los dígitos y no
 * sobre el texto.
 */
export function formatearCpf(valor) {
  const d = soloDigitos(valor).slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/**
 * ¿Los dos dígitos verificadores cierran?
 *
 * El algoritmo es el oficial de la Receita Federal: cada dígito se calcula
 * como una suma ponderada de los anteriores, módulo 11. Detecta un dígito
 * cambiado y la mayoría de las transposiciones, que son los dos errores que
 * comete alguien copiando un número de once cifras.
 *
 * NO dice que el CPF exista ni que sea de esa persona: eso no se puede saber
 * sin consultar a la Receita. Dice que el número está bien formado, que es lo
 * que se puede comprobar gratis y evita el error más común.
 */
export function cpfValido(valor) {
  // Los separadores que una persona escribe —puntos, guiones, espacios— se
  // descartan. Cualquier otra cosa NO: `52998224725x` limpiaba a un CPF
  // válido y se aceptaba. Lo encontró un test, y es la clase de indulgencia
  // que convierte un tecleo mal hecho en un envío a una llave equivocada.
  if (/[^\d.\- ]/.test(String(valor || ''))) return false;

  const d = soloDigitos(valor);
  if (d.length !== 11) return false;

  // Los once dígitos iguales pasan la cuenta de módulo 11 —000.000.000-00 y
  // 111.111.111-11 incluidos— y no son CPF de nadie. Es la excepción que la
  // propia Receita declara, no una manía.
  if (/^(\d)\1{10}$/.test(d)) return false;

  const digito = (hasta) => {
    let suma = 0;
    for (let i = 0; i < hasta; i += 1) suma += Number(d[i]) * (hasta + 1 - i);
    const resto = (suma * 10) % 11;
    return resto === 10 ? 0 : resto;
  };

  return digito(9) === Number(d[9]) && digito(10) === Number(d[10]);
}

/** Las últimas tres cifras, que alcanzan para reconocer sin exponer. */
export function cpfAbreviado(valor) {
  const d = soloDigitos(valor);
  return d ? `•••.•••.${d.slice(-5, -2)}-${d.slice(-2)}` : '—';
}

/* ─── La llave PIX ─────────────────────────────────────────────────────── */

/**
 * Qué clase de llave es. PIX admite cinco formas y cada una se muestra
 * distinta: un correo se abrevia por el dominio, un teléfono por las últimas
 * cifras, una llave aleatoria por sus extremos.
 */
export function tipoDeLlave(llave) {
  const v = String(llave || '').trim();
  if (!v) return 'vacia';
  if (v.includes('@')) return 'correo';
  const d = soloDigitos(v);
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)) return 'aleatoria';
  if (d.length === 11 && cpfValido(d)) return 'cpf';
  if (d.length === 14) return 'cnpj';
  if (d.length >= 10 && d.length <= 13) return 'telefono';
  return 'otra';
}

export const NOMBRE_DE_LA_LLAVE = {
  correo: 'Correo',
  telefono: 'Teléfono',
  cpf: 'CPF',
  cnpj: 'CNPJ',
  aleatoria: 'Llave aleatoria',
  otra: 'Llave',
  vacia: 'Llave',
};

/** Reconocible para el dueño, inútil para quien mire por encima del hombro. */
export function llaveAbreviada(llave) {
  const v = String(llave || '').trim();
  if (!v) return '—';
  const tipo = tipoDeLlave(v);
  if (tipo === 'correo') {
    const [antes, dominio] = v.split('@');
    return `${antes.slice(0, 2)}•••@${dominio || ''}`;
  }
  if (tipo === 'aleatoria') return `${v.slice(0, 4)}…${v.slice(-4)}`;
  const d = soloDigitos(v);
  return d.length > 4 ? `•••${d.slice(-4)}` : v;
}

/* ─── El monto ─────────────────────────────────────────────────────────── */

export function aNumero(valor) {
  if (typeof valor === 'number') return valor;
  const limpio = String(valor ?? '').trim().replace(/\./g, '').replace(',', '.');
  const n = parseFloat(limpio);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Todo lo que puede impedir el envío, comprobado ANTES de pedir el PIN.
 *
 * Devuelve el mensaje, o null si el monto va. El orden importa: se dice el
 * problema más concreto primero. «Saldo insuficiente» cuando además está por
 * debajo del mínimo manda a recargar a alguien que en realidad tenía que
 * escribir un número más grande.
 *
 * `limites` y `cupo` llegan de `/limits/me`, que es el MISMO módulo que el
 * servidor usa para rechazar. Si no llegaron, no se inventa un límite: se
 * deja pasar y el servidor decide, que es lo que hacía antes de todos modos.
 */
export function validarMonto({ monto, saldo, limites, cupo }) {
  if (!monto || monto <= 0) return 'Escribí cuánto querés enviar.';

  const min = limites?.pix?.min_brl;
  const max = limites?.pix?.max_brl;
  if (min != null && monto < min) return `El mínimo por envío es R$ ${min}.`;
  if (max != null && monto > max) return `El máximo por envío es R$ ${max}.`;

  if (monto > saldo) return 'No te alcanza el saldo para este envío.';

  if (cupo?.aplica) {
    if (cupo.ops_restantes === 0) {
      return 'Se te agotaron las operaciones sin verificar. Verificá tu identidad para seguir enviando.';
    }
    if (cupo.ris_restantes != null && monto > cupo.ris_restantes) {
      return `Sin verificar la identidad te quedan RI$ ${cupo.ris_restantes} de cupo.`;
    }
  }
  return null;
}

/* ─── Los pasos ────────────────────────────────────────────────────────── */

export const PASOS = [
  { numero: 1, clave: 'beneficiario', titulo: 'Beneficiario' },
  { numero: 2, clave: 'monto', titulo: 'Monto' },
  { numero: 3, clave: 'confirmar', titulo: 'Confirmar' },
];

export function ultimoPasoAlcanzable({ beneficiario, montoOk }) {
  if (!beneficiario) return 1;
  return montoOk ? 3 : 2;
}
