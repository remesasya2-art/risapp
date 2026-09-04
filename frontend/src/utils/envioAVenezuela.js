/**
 * envioAVenezuela.js — Las cuentas del envío, separadas de cómo se dibujan.
 *
 * POR QUE ESTAN ACA
 *
 *   Esta pantalla le dice a alguien cuánto va a recibir su familia. Si esa
 *   cifra está mal, no es un error de interfaz: es una promesa incumplida que
 *   se descubre del otro lado de la frontera, cuando ya no se puede hacer nada.
 *
 *   Por eso las cuentas viven en funciones sin React y sin red, que se pueden
 *   correr y comprobar.
 *
 * LA REGLA QUE ORDENA TODO ESTE ARCHIVO
 *
 *   LO QUE SE MUESTRA TIENE QUE SER LO QUE VA A PASAR.
 *
 *   El servidor calcula los bolívares como `round(ris * tasa, 2)` a partir del
 *   RIS que recibe. Así que la pantalla no puede mostrar el número que el
 *   usuario tipeó en bolívares: tiene que mostrar el que sale de ESE RIS.
 *
 *   Si alguien escribe 10.000 VES con la tasa en 165, el RIS que se envía es
 *   60,61 —redondeado a dos decimales, que es lo que el saldo admite— y lo que
 *   su familia va a recibir son 10.000,65 VES, no 10.000. La diferencia es de
 *   céntimos, pero la pantalla que dice «10.000» está mintiendo, y la que dice
 *   «10.000,65» está diciendo lo que va a pasar.
 *
 *   El mismo criterio con la tasa: si no se pudo obtener, NO se convierte con
 *   un valor por defecto. Una conversión inventada es peor que ninguna.
 */

/** Los decimales del saldo. El servidor redondea a dos: la pantalla también. */
export const DECIMALES_RIS = 2;
export const DECIMALES_VES = 2;

function redondear(n, decimales) {
  if (!Number.isFinite(n)) return 0;
  const factor = 10 ** decimales;
  // `Math.round(n * factor)` sobre un float puede caer del lado equivocado en
  // los casos justos (2.675 → 2.67). `Number.EPSILON` los empuja al lado que
  // corresponde sin afectar a los demás.
  return Math.round((n + Number.EPSILON) * factor) / factor;
}

export function aNumero(valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  const n = typeof valor === 'number' ? valor : Number(String(valor).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

/**
 * El RIS que se va a enviar, a partir de lo que el usuario escribió.
 *
 * Devuelve `null` cuando no hay con qué calcular —sin monto, sin tasa, tasa no
 * disponible— en vez de un cero que se confundiría con «no recibe nada».
 */
export function risAEnviar({ risEscrito, vesEscrito, tasa, tasaDisponible }) {
  if (!tasaDisponible || !(tasa > 0)) return null;

  const ris = aNumero(risEscrito);
  if (ris !== null) return redondear(ris, DECIMALES_RIS);

  const ves = aNumero(vesEscrito);
  if (ves !== null) return redondear(ves / tasa, DECIMALES_RIS);

  return null;
}

/**
 * Lo que el beneficiario va a recibir. SIEMPRE se deriva del RIS que se envía,
 * nunca de lo que el usuario tipeó en bolívares — ver la cabecera del archivo.
 */
export function vesARecibir({ ris, tasa, tasaDisponible }) {
  if (!tasaDisponible || !(tasa > 0) || ris === null || ris === undefined) return null;
  return redondear(ris * tasa, DECIMALES_VES);
}

/* ─── Validación del monto ─────────────────────────────────────────────── */

export const MOTIVO = {
  SIN_TASA: 'sin_tasa',
  VACIO: 'vacio',
  NO_POSITIVO: 'no_positivo',
  SIN_SALDO: 'sin_saldo',
  EXCEDE_SALDO: 'excede_saldo',
};

export const MENSAJE_DEL_MOTIVO = {
  [MOTIVO.SIN_TASA]: 'No pudimos obtener la tasa. Actualizá para intentar de nuevo.',
  [MOTIVO.VACIO]: 'Escribí cuánto querés enviar.',
  [MOTIVO.NO_POSITIVO]: 'El monto tiene que ser mayor a cero.',
  [MOTIVO.SIN_SALDO]: 'Todavía no tenés saldo. Recargá para poder enviar.',
  [MOTIVO.EXCEDE_SALDO]: 'Te falta saldo para este envío.',
};

/**
 * ¿Se puede continuar con este monto?
 *
 * Devuelve el motivo además del sí o el no. Una pantalla que sólo sabe que
 * «no se puede» tiene que inventar el mensaje, y termina diciendo «saldo
 * insuficiente» a quien todavía no escribió nada.
 */
export function validarMonto({ ris, saldo, tasaDisponible, escribioAlgo }) {
  if (!tasaDisponible) return { ok: false, motivo: MOTIVO.SIN_TASA };

  const disponible = aNumero(saldo) ?? 0;
  if (disponible <= 0) return { ok: false, motivo: MOTIVO.SIN_SALDO };

  if (ris === null || ris === undefined) {
    return { ok: false, motivo: escribioAlgo ? MOTIVO.NO_POSITIVO : MOTIVO.VACIO };
  }
  if (ris <= 0) return { ok: false, motivo: MOTIVO.NO_POSITIVO };
  if (ris > disponible) return { ok: false, motivo: MOTIVO.EXCEDE_SALDO };

  return { ok: true, motivo: null };
}

/* ─── La tasa que se movió mientras el usuario decidía ─────────────────── */

/**
 * Entre que alguien mira el monto y confirma pueden pasar varios minutos, y la
 * tasa se refresca sola cada cinco. Si cambió, lo que va a recibir su
 * beneficiario ya no es lo que vio.
 *
 * Esto no bloquea el envío: informa. El servidor manda, y siempre mandó — lo
 * que faltaba era decírselo a quien está por confirmar en vez de que se
 * enterara después.
 */
export function tasaSeMovio({ tasaAlCotizar, tasaAhora }) {
  const antes = aNumero(tasaAlCotizar);
  const ahora = aNumero(tasaAhora);
  if (antes === null || ahora === null || antes <= 0 || ahora <= 0) return null;
  if (antes === ahora) return null;
  return {
    antes,
    ahora,
    mejora: ahora > antes,
  };
}

/* ─── Presentación de los datos del beneficiario ───────────────────────── */

/**
 * Cómo se nombra un banco en pantalla.
 *
 * Para Pago Móvil el formulario guarda SÓLO el código (`bank` = "0134"), que
 * es lo que el banco pide al momento de pagar. Pero mostrarle «0134» a quien
 * eligió «BANESCO» lo obliga a recordar un número para reconocer al suyo. Se
 * muestran los dos: el nombre para reconocerlo, el código porque es el dato
 * operativo.
 */
export function nombreDelBanco(beneficiario, catalogo) {
  const b = beneficiario || {};
  const codigo = String(b.bank_code || b.bank || '').trim();
  const guardado = String(b.bank || '').trim();

  const enCatalogo = (catalogo || []).find((x) => x.code === codigo);
  const nombre = enCatalogo?.name
    || (guardado && guardado !== codigo ? guardado : '');

  if (nombre && codigo) return `${nombre} · ${codigo}`;
  return nombre || codigo || '—';
}

/** Los últimos cuatro dígitos, para reconocer una cuenta sin exponerla. */
export function cuentaAbreviada(numero) {
  const limpio = String(numero || '').replace(/\D/g, '');
  return limpio ? `••••${limpio.slice(-4)}` : '—';
}

/** El teléfono de Pago Móvil, agrupado para poder leerlo en voz alta. */
export function telefonoLegible(numero) {
  const limpio = String(numero || '').replace(/\D/g, '');
  if (limpio.length !== 11) return limpio || '—';
  return `${limpio.slice(0, 4)} ${limpio.slice(4, 7)} ${limpio.slice(7)}`;
}

/* ─── Los pasos ────────────────────────────────────────────────────────── */

export const PASOS = [
  { numero: 1, clave: 'monto', titulo: 'Monto' },
  { numero: 2, clave: 'metodo', titulo: 'Método' },
  { numero: 3, clave: 'beneficiario', titulo: 'Beneficiario' },
  { numero: 4, clave: 'confirmar', titulo: 'Confirmar' },
];

/**
 * Hasta qué paso se puede avanzar con lo que hay cargado.
 *
 * Existe para que el indicador de progreso no sea decorativo: se puede volver
 * a un paso ya completado tocándolo, y no se puede saltar a uno que todavía no
 * tiene sus datos.
 */
export function ultimoPasoAlcanzable({ montoOk, metodo, beneficiario }) {
  if (!montoOk) return 1;
  if (!metodo) return 2;
  if (!beneficiario) return 3;
  return 4;
}
