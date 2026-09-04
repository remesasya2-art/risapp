/**
 * seguridadFinanciera.js — Las decisiones de la pantalla de Seguridad
 * financiera, separadas de cómo se dibujan.
 *
 * POR QUE ESTAN ACA Y NO ADENTRO DEL COMPONENTE
 *
 *   La pantalla contesta cuatro preguntas y ninguna admite un «más o menos»:
 *   si la plata está, si el libro cuadra, si el libro se puede defender, y
 *   quién tiene las llaves. Las respuestas se calculan acá, en funciones sin
 *   React y sin red, para que se puedan probar corriendo el archivo.
 *
 *   No es prolijidad. Un veredicto mal calculado en una pantalla de seguridad
 *   es peor que no tener la pantalla: alguien la mira, la ve verde, y se va
 *   tranquilo.
 *
 * LA REGLA QUE ORDENA TODO ESTE ARCHIVO
 *
 *   NO SABER NO ES ESTAR BIEN.
 *
 *   Si una consulta falla —el servidor tardó, devolvió 500, se cortó la red—
 *   el veredicto es «no se pudo comprobar», nunca verde. Es la trampa clásica
 *   de un tablero de estado: `if (error) return` deja la tarjeta en su color
 *   anterior, o en el color por defecto, y la pantalla afirma algo que no
 *   verificó. Acá el desconocido es un estado propio, con su color, y se
 *   trata como lo que es: una pregunta sin responder.
 */

/** Los tres permisos que el catálogo marca «(MUEVE DINERO)». */
export const PERMISOS_QUE_MUEVEN_DINERO = {
  'saldos.ajustar': 'Ajustar saldos a mano',
  'recharges.approve': 'Aprobar recargas',
  'envios.dinero': 'Cargar fletes y costos de viaje',
};

/**
 * Cambiar la tasa no mueve un saldo, pero cambia lo que todos pagan. Va en su
 * propia lista: mezclarlo con los de arriba haría que «mueve dinero» dejara de
 * significar algo preciso, y separarlo del todo escondería a quien puede
 * cambiarle el precio a la operación entera.
 */
export const PERMISOS_QUE_MUEVEN_LA_TASA = {
  'settings.edit': 'Editar configuración y tasas',
};

export const SUPER_ADMIN = 'super_admin';

/**
 * Qué llaves del dinero tiene una persona.
 *
 * EL SUPER ADMINISTRADOR ENTRA SIEMPRE, TENGA O NO PERMISOS MARCADOS
 *   `services/permisos.py` lo dice en una línea: `tiene()` devuelve `true`
 *   para el super administrador antes de mirar su lista. Si esta pantalla se
 *   guiara sólo por el arreglo `permisos` —que en su ficha suele venir vacío—
 *   informaría que nadie puede ajustar saldos en una aplicación donde él puede
 *   ajustar todos. Un listado de llaves que omite al que tiene todas es peor
 *   que no listar nada.
 */
export function llavesDe(persona) {
  const esSuper = (persona?.rol || persona?.role) === SUPER_ADMIN;
  const marcados = Array.isArray(persona?.permisos) ? persona.permisos : [];

  const dinero = esSuper
    ? Object.keys(PERMISOS_QUE_MUEVEN_DINERO)
    : marcados.filter((p) => p in PERMISOS_QUE_MUEVEN_DINERO);
  const tasa = esSuper
    ? Object.keys(PERMISOS_QUE_MUEVEN_LA_TASA)
    : marcados.filter((p) => p in PERMISOS_QUE_MUEVEN_LA_TASA);

  return {
    porSerSuperAdmin: esSuper,
    dinero,
    tasa,
    mueveDinero: dinero.length > 0,
    mueveLaTasa: tasa.length > 0,
  };
}

/**
 * En qué estado está el acceso de quien tiene llaves.
 *
 * QUE SIGNIFICA CADA UNO, Y POR QUE NINGUNO DICE «EXPUESTO»
 *   El personal no consigue sesión sin segundo factor: `routes/auth.py` le
 *   devuelve un token de enrolamiento, no una sesión, mientras no lo tenga
 *   puesto. Así que alguien con llaves y sin 2FA no es un agujero abierto —es
 *   una cuenta a medio asegurar, que hoy no puede entrar—.
 *
 *   La distinción importa. Una pantalla que pintara eso de rojo y dijera
 *   «expuesto» estaría gritando por algo que la aplicación ya frena, y a la
 *   tercera vez nadie la mira. El ámbar dice lo que de verdad pasa: falta
 *   terminar de dar el acceso.
 */
export function estadoDelAcceso(persona) {
  const acceso = persona?.acceso || {};
  if (acceso.dos_pasos) return 'listo';
  if (acceso.clave_configurada) return 'sin_dos_pasos';
  return 'sin_activar';
}

export const ETIQUETA_DEL_ACCESO = {
  listo: 'Acceso completo, con segundo factor',
  sin_dos_pasos: 'Clave puesta, sin segundo factor: no puede iniciar sesión hasta enrolarlo',
  sin_activar: 'Todavía no activó su acceso',
};

/**
 * Quiénes tienen llaves del dinero, ordenados por lo que pueden hacer.
 *
 * El orden no es cosmético: primero quien mueve dinero, después quien sólo
 * mueve la tasa, y dentro de cada grupo primero el acceso a medio terminar.
 * Lo que hay que mirar tiene que quedar arriba sin que nadie ordene la tabla.
 */
export function llaverosDelDinero(personal) {
  const lista = Array.isArray(personal) ? personal : [];
  const peso = { sin_dos_pasos: 0, sin_activar: 1, listo: 2 };

  return lista
    .map((p) => ({ persona: p, llaves: llavesDe(p), acceso: estadoDelAcceso(p) }))
    .filter((f) => f.llaves.mueveDinero || f.llaves.mueveLaTasa)
    .sort((a, b) => {
      if (a.llaves.mueveDinero !== b.llaves.mueveDinero) return a.llaves.mueveDinero ? -1 : 1;
      if (peso[a.acceso] !== peso[b.acceso]) return peso[a.acceso] - peso[b.acceso];
      return String(a.persona?.email || '').localeCompare(String(b.persona?.email || ''));
    });
}

/**
 * El veredicto de un bloque.
 *
 * `bloque` es `{ estado: 'ok' | 'error', valor }`. `esBueno` decide sobre el
 * valor y sólo se llama cuando hay valor: una consulta que falló no se le
 * pregunta a nadie, se informa como lo que es.
 */
export function veredicto(bloque, esBueno) {
  if (!bloque || bloque.estado !== 'ok') return 'desconocido';
  try {
    return esBueno(bloque.valor) ? 'bien' : 'mal';
  } catch {
    // Una respuesta con la forma cambiada tampoco es «todo bien». Si el
    // servidor devolvió algo que esta pantalla no sabe leer, lo honesto es
    // decir que no se pudo comprobar.
    return 'desconocido';
  }
}

/** Las cuatro preguntas, con su respuesta y su número. */
export function resumen(datos) {
  const d = datos || {};
  return [
    {
      clave: 'pozo',
      pregunta: '¿Está toda la plata?',
      detalle: 'Lo que la empresa debe contra lo que la empresa tiene.',
      estado: veredicto(d.pozo, (v) => v.cubre === true),
      cifra: d.pozo?.estado === 'ok' ? d.pozo.valor?.diferencia : null,
      unidad: d.pozo?.valor?.moneda || '',
    },
    {
      clave: 'reconciliacion',
      pregunta: '¿Cuadra cada cuenta con su libro?',
      detalle: 'El saldo guardado de cada usuario contra la suma de sus asientos.',
      estado: veredicto(d.reconciliacion, (v) => v.cuadra === true),
      cifra: d.reconciliacion?.estado === 'ok'
        ? String(d.reconciliacion.valor?.descuadres_totales ?? 0) : null,
      unidad: 'cuentas sin cuadrar',
    },
    {
      clave: 'integridad',
      pregunta: '¿El libro se puede defender?',
      detalle: 'Los defectos que impedirían sostenerlo ante un auditor.',
      estado: veredicto(d.integridad, (v) => v.sano === true),
      cifra: d.integridad?.estado === 'ok'
        ? String((d.integridad.valor?.hallazgos || []).length) : null,
      unidad: 'tipos de defecto',
    },
    {
      clave: 'llaves',
      pregunta: '¿Quién tiene las llaves del dinero?',
      detalle: 'Personal que puede mover saldo o cambiar la tasa.',
      // Este no es un bien/mal: es un recuento. Se pone en ámbar cuando alguien
      // con llaves todavía no terminó de asegurar su cuenta, y en neutro
      // cuando están todas en orden. Pintar de verde «hay cinco personas que
      // pueden mover plata» sería decir que eso está bien, y eso no lo decide
      // una pantalla.
      estado: llavesVeredicto(d.personal),
      cifra: d.personal?.estado === 'ok'
        ? String(llaverosDelDinero(d.personal.valor?.personal).length) : null,
      unidad: 'personas',
    },
  ];
}

function llavesVeredicto(bloque) {
  if (!bloque || bloque.estado !== 'ok') return 'desconocido';
  const llaveros = llaverosDelDinero(bloque.valor?.personal);
  return llaveros.some((f) => f.acceso !== 'listo') ? 'atencion' : 'neutro';
}

/**
 * Las consultas de la pantalla. Todas son de super administrador y todas son
 * de sólo lectura: esta pantalla no cambia nada, mira.
 */
export const CONSULTAS = [
  { clave: 'pozo', ruta: '/admin/ledger/pozo' },
  { clave: 'reconciliacion', ruta: '/admin/ledger/reconciliacion', params: { libro: 'RIS' } },
  { clave: 'integridad', ruta: '/admin/ledger/integridad' },
  { clave: 'personal', ruta: '/admin/rrhh' },
  { clave: 'movimientos', ruta: '/admin/rrhh/auditoria/libro', params: { categoria: 'dinero', limite: 25 } },
];
