/**
 * estilos.js — Los tokens visuales del panel de envíos.
 *
 * Separado de `ui.jsx` a propósito: un archivo que exporta componentes Y
 * constantes rompe el fast refresh de Vite, y entonces cada vez que se toca un
 * color se recarga la página entera y se pierde el formulario a medio cargar.
 * Es la clase de detalle que solo se nota cuando uno está cargando la
 * configuración de verdad, que es cuando más molesta.
 *
 * ESTILOS EN LINEA, COMO EL RESTO DEL PANEL
 *   El proyecto tiene Tailwind instalado y `components/admin/` no lo usa: todo
 *   está escrito con `style={{...}}`. Estas pantallas siguen esa convención
 *   aunque la otra sea más corta. Mezclar los dos sistemas adentro de la misma
 *   página es cómo se llega a que un botón cambie de tamaño según de qué archivo
 *   salió.
 */


export const COLOR = {
  texto: '#111827',
  suave: '#6b7280',
  borde: '#e5e7eb',
  fondo: '#ffffff',
  primario: '#6366f1',
  primarioOscuro: '#4F46E5',
  primarioSuave: '#eef2ff',
  ok: '#059669',
  okSuave: '#ecfdf5',
  alerta: '#d97706',
  alertaSuave: '#fffbeb',
  error: '#dc2626',
  errorSuave: '#fef2f2',
};

export const tarjeta = {
  backgroundColor: COLOR.fondo,
  borderRadius: '16px',
  border: `1px solid ${COLOR.borde}`,
  boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
  padding: '20px',
};

export const titulo = {
  fontSize: '15px', fontWeight: 700, color: COLOR.texto, margin: '0 0 4px 0',
  display: 'flex', alignItems: 'center', gap: '8px',
};

export const bajada = { fontSize: '13px', color: COLOR.suave, margin: '0 0 18px 0', lineHeight: 1.5 };

export const grilla = (min = '220px') => ({
  display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}, 1fr))`, gap: '16px',
});

const botonBase = {
  padding: '10px 16px', borderRadius: '12px', fontSize: '13px', fontWeight: 600,
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px',
  border: '1.5px solid transparent', whiteSpace: 'nowrap',
};

export const botonPrimario = {
  ...botonBase, backgroundColor: COLOR.primario, color: '#fff',
};
export const botonSecundario = {
  ...botonBase, backgroundColor: '#fff', color: COLOR.suave, borderColor: COLOR.borde,
};
export const botonPeligro = {
  ...botonBase, backgroundColor: '#fff', color: COLOR.error, borderColor: '#fecaca',
};
export const deshabilitado = { opacity: 0.5, cursor: 'not-allowed' };

/** El estilo de un campo de entrada. En rojo suave cuando el valor no sirve. */
export const entrada = (invalido) => ({
  padding: '10px 12px', borderRadius: '10px', fontSize: '14px', width: '100%',
  border: `1.5px solid ${invalido ? '#fca5a5' : COLOR.borde}`,
  backgroundColor: invalido ? COLOR.errorSuave : '#fff',
  color: COLOR.texto, outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
});


/**
 * El mensaje del backend, tal cual vino.
 *
 * Los mensajes de este módulo están escritos para que los lea una persona y
 * dicen qué campo está mal. Reemplazarlos por un "Error al guardar" genérico
 * tira justamente la parte útil.
 */
export function mensajeDeError(err, porDefecto = 'No se pudo completar la operación.') {
  const detalle = err?.response?.data?.detail;
  if (typeof detalle === 'string' && detalle.trim()) return detalle;
  if (Array.isArray(detalle) && detalle.length) {
    return detalle.map((d) => d?.msg || String(d)).join(' ');
  }
  return porDefecto;
}


/**
 * ¿Esto fue "no se pudo leer" o "no hay nada cargado"?
 *
 * ES LA DISTINCION MAS IMPORTANTE DE TODO EL PANEL, y el backend la construyó
 * entera para que la pantalla pudiera hacerla: `leer_con_estado`, los tres
 * estados de la puesta en marcha, y el 503 de la consola de precios que dice
 * literalmente "no edites hasta que vuelva: lo que guardes ahora puede pisar lo
 * que ya había".
 *
 * Si la pantalla las confunde, un corte de base de treinta segundos le muestra a
 * quien está cargando la configuración un formulario en blanco con un botón de
 * Guardar al lado. Esa persona lo completa de memoria y pisa la plantilla, la
 * Caixa Postal y la razón social reales.
 *
 * Sin respuesta (red caída, timeout) o 5xx es una falla de lectura. Un 4xx es el
 * servidor contestando algo sobre el dato, y eso sí se puede mostrar.
 */
export function esFallaDeLectura(err) {
  const estado = err?.response?.status;
  if (estado === undefined || estado === null) return true;
  return estado >= 500;
}
