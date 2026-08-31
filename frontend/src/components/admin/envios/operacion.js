/**
 * operacion.js — Lo que el panel del operador tiene que saber de cada estado.
 *
 * EL ORDEN DE ESTA LISTA ES EL DIA DEL OPERADOR
 *   Un paquete pasa por acá de arriba hacia abajo, y cada parada tiene UNA acción
 *   principal. Esa correspondencia es lo que permite que la pantalla no sea una
 *   lista de botones: en cada pestaña hay una cosa para hacer.
 *
 * DOS DE ESTAS ACCIONES MUEVEN PLATA
 *   Verificar el comprobante EMITE el cobro inicial. Repesar puede cobrar o
 *   acreditar. Las dos piden `get_admin_user` en el backend —el rol `agent`, que
 *   es soporte de chat, no las tiene— y las dos llevan clave de idempotencia.
 */

export const PARADAS = [
  {
    estado: 'en_transito_origen',
    etiqueta: 'Por verificar',
    resumen: 'El usuario despachó y cargó el comprobante. Acá se lee el peso en la foto '
      + 'y se emite el cobro inicial.',
    acciones: ['verificar'],
    mueveSaldo: true,
  },
  {
    estado: 'disponible_retiro',
    etiqueta: 'En el mostrador',
    resumen: 'El paquete llegó a Pacaraima y corre el reloj de guarda. Se retiran por '
      + 'lote, escaneando el código impreso en cada caja.',
    acciones: [],
    agrupar: true,
  },
  {
    estado: 'recibido_pacaraima',
    etiqueta: 'Por repesar',
    resumen: 'Retirados del mostrador. Acá se pesa con balanza propia y se cierra el '
      + 'precio: es el único momento en que deja de ser un estimado.',
    acciones: ['repesar'],
    mueveSaldo: true,
  },
  {
    estado: 'repesado',
    etiqueta: 'Por despachar',
    resumen: 'Precio cerrado y todo pago. Salen hacia Santa Elena.',
    acciones: ['despachar'],
  },
  {
    estado: 'pago_pendiente',
    etiqueta: 'Esperando pago',
    resumen: 'El ajuste del repesaje quedó impago. No es un error: el paquete '
      + 'simplemente no sale de Pacaraima hasta que se pague. Es la única palanca '
      + 'de cobro real que tiene el negocio.',
    acciones: ['despachar'],
  },
  {
    estado: 'en_transito_int',
    etiqueta: 'Por entregar',
    resumen: 'En camino a Santa Elena. Se entregan en la oficina del transportista, '
      + 'con guía.',
    acciones: ['entregar'],
  },
  {
    estado: 'retenido',
    etiqueta: 'Retenidos',
    resumen: 'Frenados por algún motivo. Tienen camino hacia adelante: si todavía no se '
      + 'pesaron, se repesan; si ya está el precio cerrado y todo pago, salen.',
    // Las DOS: un retenido puede estar antes o después del repesaje, y la cola no
    // dice cuál. Sin esto, las únicas salidas que ofrecía la pantalla eran
    // «devuelto» y «siniestrado» — las dos que cuestan plata y ninguna reversible.
    acciones: ['repesar', 'despachar'],
  },
];

export const POR_ESTADO = Object.fromEntries(PARADAS.map((p) => [p.estado, p]));

/**
 * Qué desvíos son legales desde cada parada.
 *
 * Copiado de `TRANSICIONES` en `services/envios_estados.py`, y no inventado:
 * ofrecer los cuatro siempre hacía que el operador eligiera «devuelto al
 * remitente» —el caso MÁS común del mostrador—, escribiera el motivo, tildara
 * «entiendo que no se puede deshacer», y recibiera un 400. Un formulario de
 * confirmación irreversible completado para nada.
 */
export const DESVIOS_LEGALES = {
  en_transito_origen: ['siniestrado', 'cancelado'],
  disponible_retiro: ['devuelto', 'siniestrado'],
  recibido_pacaraima: ['retenido', 'devuelto', 'siniestrado'],
  repesado: ['retenido', 'devuelto', 'siniestrado'],
  pago_pendiente: ['retenido', 'devuelto', 'cancelado', 'siniestrado'],
  en_transito_int: ['retenido', 'siniestrado'],
  retenido: ['devuelto', 'siniestrado'],
};

/** Las cuatro salidas que no son la entrega. Ninguna se puede deshacer. */
export const DESVIOS = [
  { hacia: 'retenido', etiqueta: 'Retener',
    ayuda: 'Frena el paquete sin sacarlo del circuito. Después puede volver al repesaje.' },
  { hacia: 'devuelto', etiqueta: 'Devuelto al remitente',
    ayuda: 'La agencia lo devolvió — casi siempre porque venció la guarda. El usuario '
      + 'ya pagó y hay costo de retorno.' },
  { hacia: 'siniestrado', etiqueta: 'Siniestrado',
    ayuda: 'Perdido o dañado. Abre una indemnización.' },
  { hacia: 'cancelado', etiqueta: 'Cancelado',
    ayuda: 'Cierra el envío sin entregarlo. Desde el mostrador solo se puede cuando '
      + 'quedó esperando un pago que nunca llegó.' },
];

/**
 * Una clave de idempotencia por acción y por envío.
 *
 * QUE GARANTIZA ESTO Y QUE NO
 *   La garantía real de que nadie cobra dos veces **está en el servidor**, y no
 *   acá: `envios_cobros.cobrar` corta en `_partida_existente` y el
 *   `find_one_and_update` filtra por `{"cobros.<partida>": None}`, así que dos
 *   peticiones simultáneas —con claves distintas, incluso desde dos máquinas—
 *   terminan en una sola partida. Esta clave es una segunda línea, no la
 *   primera. Conviene tenerlo escrito: alguien que en seis meses toque `cobrar`
 *   podría sacar ese guard creyendo que el cliente ya lo cubre.
 *
 *   Lo que sí aporta es que el reintento devuelva el MISMO resultado en vez de
 *   un 409 confuso, que en un mostrador con mala señal es la diferencia entre
 *   seguir trabajando y llamar a soporte.
 *
 * VIVE EN sessionStorage, NO EN MEMORIA
 *   Un `Map` de módulo se pierde con F5 — y recargar es exactamente lo primero
 *   que hace cualquiera cuando una petición se cuelga, o sea el único escenario
 *   donde la clave importaba. En `sessionStorage` sobrevive a la recarga y
 *   sigue siendo por pestaña, que es lo correcto: dos pestañas son dos intentos
 *   distintos y el servidor ya sabe resolverlos.
 */
const PREFIJO = 'envios_clave:';
const EN_MEMORIA = new Map();   // respaldo si el navegador no deja guardar

function leer(k) {
  try {
    return sessionStorage.getItem(PREFIJO + k) || EN_MEMORIA.get(k) || null;
  } catch {
    return EN_MEMORIA.get(k) || null;
  }
}

function escribir(k, v) {
  EN_MEMORIA.set(k, v);
  try { sessionStorage.setItem(PREFIJO + k, v); } catch { /* modo privado */ }
}

export function claveDe(accion, envioId) {
  const k = `${accion}:${envioId}`;
  const guardada = leer(k);
  if (guardada) return guardada;
  const nueva = (globalThis.crypto?.randomUUID?.()
    || `k_${Date.now()}_${Math.random().toString(36).slice(2)}`);
  escribir(k, nueva);
  return nueva;
}

export function olvidarClave(accion, envioId) {
  const k = `${accion}:${envioId}`;
  EN_MEMORIA.delete(k);
  try { sessionStorage.removeItem(PREFIJO + k); } catch { /* modo privado */ }
}

/**
 * Los rechazos del retiro por lote, en castellano.
 *
 * El backend manda un slug en `motivo` y la frase en `detalle`. Mostrar el slug
 * pelado le deja al operador, parado con treinta cajas, una lista que dice
 * «estado», «carrera», «desconocido» — sin forma de saber si la caja ya estaba
 * retirada, si está en otro punto, o si otro operador se la ganó hace un
 * segundo. Todo el diseño de «un código rechazado no frena el lote» se apoya en
 * que el rechazo sea accionable.
 */
export const MOTIVOS_DE_RECHAZO = {
  formato: 'El código no tiene la forma de un código de objeto.',
  desconocido: 'Ningún envío tiene ese código de objeto.',
  estado: 'El envío no está en el mostrador.',
  carrera: 'Otro operador lo retiró hace un momento.',
  no_se_pudo_leer: 'No se pudo leer el envío. Reintentá este código.',
};
