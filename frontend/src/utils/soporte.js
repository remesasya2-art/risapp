/**
 * soporte.js — Las reglas de pantalla de la mesa de ayuda.
 *
 * POR QUE ESTE MODULO
 *
 *   Lo mismo que `envioABrasil.js` o `perfil.js`: la pantalla dibuja, esto
 *   decide. Y acá pesa más que en otras pantallas, porque el asesor tiene seis
 *   botones que a veces se pueden usar y a veces no —tomar, responder,
 *   transferir, escalar, pedir, cerrar—, y esa lógica metida entre el JSX es
 *   la que después nadie se anima a tocar.
 *
 * ESTO ESPEJA A `backend/services/soporte.py`
 *
 *   Las mismas transiciones, los mismos estados, el mismo semáforo. El
 *   servidor sigue siendo el que manda: acá se decide qué botón se ve apagado
 *   para no ofrecer algo que va a fallar, no qué se permite.
 */

/* ─── Los estados ──────────────────────────────────────────────────────── */

export const ABIERTO = 'abierto';
export const EN_CURSO = 'en_curso';
export const ESPERANDO_CLIENTE = 'esperando_cliente';
export const RESUELTO = 'resuelto';
export const CERRADO = 'cerrado';

/**
 * Cómo se nombra cada estado, de los dos lados.
 *
 * El cliente y el asesor NO leen lo mismo: «esperando_cliente» para el equipo
 * es «la pelota la tiene él»; para el cliente es «te respondimos». Decirle a
 * un cliente que el caso está «esperando cliente» lo deja sin saber qué se
 * espera de él.
 */
export const ESTADOS = {
  [ABIERTO]: { asesor: 'Sin tomar', cliente: 'Recibido', tono: 'alerta' },
  [EN_CURSO]: { asesor: 'En curso', cliente: 'Lo estamos viendo', tono: 'info' },
  [ESPERANDO_CLIENTE]: { asesor: 'Esperando al cliente', cliente: 'Te respondimos', tono: 'info' },
  [RESUELTO]: { asesor: 'Resuelto', cliente: 'Resuelto', tono: 'exito' },
  [CERRADO]: { asesor: 'Cerrado', cliente: 'Cerrado', tono: 'neutro' },
};

export function nombreDeEstado(estado, para = 'asesor') {
  return ESTADOS[estado]?.[para] || estado || '—';
}

export function tonoDeEstado(estado) {
  return ESTADOS[estado]?.tono || 'neutro';
}

/** Espeja a `TRANSICIONES` del backend. Lo que no está acá, no se ofrece.
 *
 *  Un test compara las dos tablas estado por estado: si allá se agrega un paso
 *  y acá no, el asesor deja de ver una opción que sí existe; al revés, se le
 *  ofrece una que el servidor va a rechazar. */
const TRANSICIONES = {
  [ABIERTO]: [EN_CURSO, RESUELTO, CERRADO],
  [EN_CURSO]: [ESPERANDO_CLIENTE, RESUELTO, CERRADO, ABIERTO],
  [ESPERANDO_CLIENTE]: [EN_CURSO, RESUELTO, CERRADO, ABIERTO],
  [RESUELTO]: [EN_CURSO, ESPERANDO_CLIENTE, CERRADO, ABIERTO],
  [CERRADO]: [],
};

export function estadosPosibles(desde) {
  return TRANSICIONES[desde] || [];
}

/* ─── Las prioridades ──────────────────────────────────────────────────── */

export const PRIORIDADES = ['baja', 'normal', 'alta', 'urgente'];

export const COMPROMISO_MINUTOS = {
  urgente: 15, alta: 60, normal: 240, baja: 480,
};

/* ─── El semáforo ──────────────────────────────────────────────────────── */

/**
 * Cuánto lleva esperando la PRIMERA respuesta, o null si ya se le contestó.
 *
 * El backend manda `minutos_esperando` calculado; esto es para recalcularlo
 * mientras la pantalla está abierta sin volver a pedir la lista. Un caso que
 * entra en rojo tiene que ponerse en rojo solo, no en el próximo refresco.
 */
export function minutosEsperando(caso, ahora = Date.now()) {
  if (!caso || caso.primera_respuesta_en) return null;
  if (caso.estado === CERRADO) return null;
  const creado = Date.parse(caso.creado_en);
  if (Number.isNaN(creado)) return null;
  return Math.max(0, Math.floor((ahora - creado) / 60000));
}

/**
 * Cuánto hace que el cliente escribió y nadie le contestó.
 *
 * `null` si la pelota no la tiene la casa. Espeja a `minutos_sin_respuesta`
 * del backend, que es lo que decide el orden de la bandeja: se muestra para
 * que ese orden se pueda explicar mirando la fila.
 */
export function minutosSinRespuesta(caso, ahora = Date.now()) {
  if (!caso || caso.estado === CERRADO) return null;
  if (caso.ultimo_mensaje_de !== 'cliente') return null;
  const cuando = Date.parse(caso.ultimo_mensaje_en || caso.creado_en);
  if (Number.isNaN(cuando)) return null;
  return Math.max(0, Math.floor((ahora - cuando) / 60000));
}

/** `verde` | `amarillo` | `rojo` | null. Amarillo a la mitad, para llegar. */
export function semaforo(caso, ahora = Date.now()) {
  const minutos = minutosEsperando(caso, ahora);
  if (minutos === null) return null;
  const tope = COMPROMISO_MINUTOS[caso?.prioridad] ?? COMPROMISO_MINUTOS.normal;
  if (minutos >= tope) return 'rojo';
  if (minutos >= tope / 2) return 'amarillo';
  return 'verde';
}

/** «hace 3 h», «hace 12 min». Para la lista, donde la hora exacta no aporta. */
export function haceCuanto(fecha, ahora = Date.now()) {
  const t = Date.parse(fecha);
  if (Number.isNaN(t)) return '';
  const minutos = Math.max(0, Math.floor((ahora - t) / 60000));
  if (minutos < 1) return 'recién';
  const horas = Math.floor(minutos / 60);
  if (horas >= 24) {
    const dias = Math.floor(horas / 24);
    return dias === 1 ? 'ayer' : `hace ${dias} días`;
  }
  return `hace ${duracion(minutos)}`;
}

/**
 * Un rato, en palabras: «40 min», «3 h», «2 días».
 *
 * Sin el «hace» adelante, para poder decir «Espera hace 3 h» sin que quede
 * «Espera hace hace 3 h».
 */
export function duracion(minutos) {
  const m = Math.max(0, Math.round(minutos || 0));
  if (m < 60) return `${m} min`;
  const horas = Math.floor(m / 60);
  if (horas < 24) return `${horas} h`;
  const dias = Math.floor(horas / 24);
  return dias === 1 ? '1 día' : `${dias} días`;
}

/* ─── Qué puede hacer el asesor ────────────────────────────────────────── */

/**
 * Los botones de la barra del caso, con su motivo cuando están apagados.
 *
 * Devuelve un objeto por acción: `{ puede, porque }`. La pantalla apaga el
 * botón Y muestra el porqué; un botón gris sin motivo es una pared, y de eso
 * ya aprendimos en el perfil.
 */
export function accionesDelAsesor({ caso, yo, esSuperAdmin = false }) {
  const cerrado = caso?.estado === CERRADO;
  const mio = caso?.asignado_a === yo;
  const deOtro = Boolean(caso?.asignado_a) && !mio;
  const quien = caso?.asignado_a_nombre || 'otro asesor';

  const sinCaso = !caso;
  const bloqueoCerrado = cerrado ? 'El caso está cerrado.' : null;
  const bloqueoAjeno = deOtro && !esSuperAdmin ? `Lo está atendiendo ${quien}.` : null;

  return {
    tomar: {
      puede: !sinCaso && !cerrado && !caso?.asignado_a,
      porque: bloqueoCerrado || (caso?.asignado_a ? `Ya lo tomó ${quien}.` : null),
    },
    soltar: {
      puede: !sinCaso && !cerrado && Boolean(caso?.asignado_a) && (mio || esSuperAdmin),
      porque: bloqueoCerrado || bloqueoAjeno
        || (!caso?.asignado_a ? 'Nadie lo tomó todavía.' : null),
    },
    // Espeja a `problema_para_responder` del backend, y el test lo comprueba
    // caso por caso: el caso tiene que tener dueño, y ser tuyo —o vos ser
    // super administrador, que es quien destraba—. Acá estaba pidiendo sólo
    // «que sea mío», así que al super administrador le apagaba un botón que
    // el servidor sí le habilitaba.
    responder: {
      puede: !sinCaso && !cerrado && Boolean(caso?.asignado_a) && (mio || esSuperAdmin),
      porque: bloqueoCerrado
        || (!caso?.asignado_a ? 'Tomá el caso antes de responder.' : null)
        || bloqueoAjeno,
    },
    // La nota interna es contexto para el equipo, no una respuesta al cliente:
    // se puede dejar en un caso que no es tuyo. Lo que se protege es que al
    // cliente le hable una sola persona.
    notaInterna: {
      puede: !sinCaso && !cerrado,
      porque: bloqueoCerrado,
    },
    transferir: {
      puede: !sinCaso && !cerrado && (!deOtro || esSuperAdmin),
      porque: bloqueoCerrado || bloqueoAjeno,
    },
    escalar: {
      puede: !sinCaso && !cerrado && !caso?.escalado,
      porque: bloqueoCerrado || (caso?.escalado ? 'Ya está escalado.' : null),
    },
    pedir: {
      puede: !sinCaso && !cerrado,
      porque: bloqueoCerrado,
    },
    cerrar: {
      puede: !sinCaso && !cerrado,
      porque: bloqueoCerrado,
    },
  };
}

/* ─── Los pedidos a otra área ──────────────────────────────────────────── */

/** Un pedido sin detalle obliga a la otra área a volver a preguntar. */
export function problemaDelPedido({ area, detalle }) {
  if (!area) return 'Elegí a qué área le estás pidiendo.';
  if ((detalle || '').trim().length < 10) {
    return 'Contá qué necesitás, con lo suficiente para que lo puedan resolver sin volver a preguntarte.';
  }
  return null;
}

/** La nota de traspaso es obligatoria, y es lo único que evita empezar de cero. */
export function problemaDeLaTransferencia({ area, nota }) {
  if (!area) return 'Elegí el área que va a seguir.';
  if ((nota || '').trim().length < 5) {
    return 'Escribí qué se hizo y qué falta. Sin eso, el que recibe lee todo de nuevo mientras el cliente espera.';
  }
  return null;
}

export function problemaDelEscalamiento(motivo) {
  if ((motivo || '').trim().length < 5) {
    return 'Escribí por qué lo escalás: es lo primero que va a leer quien lo tome.';
  }
  return null;
}

/* ─── El primer mensaje del cliente ────────────────────────────────────── */

export function problemaParaAbrirCaso({ motivo, mensaje }) {
  if (!motivo) return 'Elegí sobre qué es tu consulta.';
  if (!(mensaje || '').trim()) return 'Contanos qué pasó.';
  return null;
}

/**
 * ¿Se puede seguir escribiendo en este caso?
 *
 * Cerrado no: para hablar de otra cosa se abre uno nuevo. Es lo que mantiene
 * cada consulta con su propia historia, en vez del hilo único de antes.
 */
export function sePuedeEscribir(caso) {
  return Boolean(caso) && caso.estado !== CERRADO;
}

/**
 * Se califica cuando el trabajo ya está hecho: resuelto o cerrado.
 *
 * Los dos y no sólo cerrado. Al asesor se le dice —y con razón— que deje el
 * caso en «resuelto» si puede faltar algo, porque cerrado no se reabre. Con la
 * calificación atada a «cerrado», se le pedía la opinión al cliente justo en
 * el estado que al asesor se le pide NO usar.
 *
 * Espeja a `TERMINADOS` del backend.
 */
export const TERMINADOS = [RESUELTO, CERRADO];

export function sePuedeCalificar(caso) {
  return Boolean(caso) && TERMINADOS.includes(caso.estado) && !caso.calificacion;
}

/**
 * ¿Puede el cliente dar por terminado el caso?
 *
 * El que abrió la consulta es el que sabe si ya no la necesita —encontró la
 * respuesta solo, se arregló, se equivocó de motivo—. Sin esto, ese caso
 * quedaba en la cola del asesor como trabajo pendiente hasta que alguien lo
 * mirara para descubrir que no había nada que hacer.
 */
export function sePuedeCerrarPorElCliente(caso) {
  return Boolean(caso) && caso.estado !== CERRADO;
}

/**
 * La respuesta a un pedido de otra área.
 *
 * Vuelve al caso como nota interna y la lee el asesor que está con el cliente:
 * un «ok» no le sirve para nada, porque después tiene que traducírselo al
 * cliente. Por eso se pide algo escrito, no un visto.
 */
export function problemaDeLaRespuestaAlPedido(respuesta) {
  const texto = (respuesta || '').trim();
  if (texto.length < 3) {
    return 'Escribí la respuesta. El asesor que atiende al cliente la va a leer para contestarle.';
  }
  if (texto.length > 2000) return 'La respuesta es demasiado larga.';
  return null;
}
