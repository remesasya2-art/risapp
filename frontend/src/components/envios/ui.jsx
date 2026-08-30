/**
 * ui.jsx — Las piezas que comparten las siete pantallas del panel de envíos.
 *
 * POR QUE UN ARCHIVO DE PIEZAS Y NO CADA PANTALLA CON LO SUYO
 *   El panel de envíos son siete pantallas que se cargan en un orden y se leen
 *   como una sola tarea. Si cada una define su propia tarjeta y su propio input,
 *   la tercera no se parece a la primera y el que está cargando la configuración
 *   —una sola vez en la vida del sistema, con la caja de otro esperando— tiene
 *   que volver a aprender dónde mirar en cada paso.
 *
 * Los tokens (colores, tarjeta, grilla) están en `estilos.js`: acá van solo
 * componentes, que es lo que el fast refresh de Vite necesita para no recargar
 * la página entera y tirar un formulario a medio cargar.
 */
import { AlertTriangle, Check, Info, Loader2, RefreshCw, X } from 'lucide-react';
import {
  COLOR, botonPeligro, botonPrimario, botonSecundario, deshabilitado, entrada,
} from './estilos';


export function Boton({ variante = 'primario', cargando, disabled, children, style, ...resto }) {
  const base = variante === 'primario' ? botonPrimario
    : variante === 'peligro' ? botonPeligro : botonSecundario;
  const off = disabled || cargando;
  return (
    <button {...resto} disabled={off}
      style={{ ...base, ...(off ? deshabilitado : {}), ...style }}>
      {cargando ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : null}
      {children}
    </button>
  );
}

/**
 * Un campo con su ayuda debajo.
 *
 * La ayuda NO es decorativa: casi todos los campos de este panel terminan
 * impresos en una etiqueta, cobrados a alguien, o comparados contra un documento
 * en un mostrador de otro país. El que los carga los ve una sola vez.
 */
export function Campo({ etiqueta, ayuda, error, children, ancho }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', gridColumn: ancho }}>
      <label style={{ fontSize: '12px', fontWeight: 700, color: COLOR.texto,
        textTransform: 'uppercase', letterSpacing: '0.03em' }}>
        {etiqueta}
      </label>
      {children}
      {error ? (
        <span style={{ fontSize: '12px', color: COLOR.error, lineHeight: 1.4 }}>{error}</span>
      ) : ayuda ? (
        <span style={{ fontSize: '12px', color: COLOR.suave, lineHeight: 1.4 }}>{ayuda}</span>
      ) : null}
    </div>
  );
}

export function Texto({ invalido, ...resto }) {
  return <input {...resto} style={{ ...entrada(invalido), ...(resto.style || {}) }} />;
}

export function Area({ invalido, filas = 4, ...resto }) {
  return <textarea {...resto} rows={filas}
    style={{ ...entrada(invalido), resize: 'vertical', lineHeight: 1.5, ...(resto.style || {}) }} />;
}

export function Seleccion({ invalido, opciones = [], ...resto }) {
  return (
    <select {...resto} style={{ ...entrada(invalido), ...(resto.style || {}) }}>
      {opciones.map((o) => (
        <option key={o.valor} value={o.valor}>{o.texto}</option>
      ))}
    </select>
  );
}

export function Interruptor({ activo, onChange, etiqueta, ayuda }) {
  return (
    <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
      <input type="checkbox" checked={!!activo} onChange={(e) => onChange(e.target.checked)}
        style={{ width: '18px', height: '18px', marginTop: '1px', accentColor: COLOR.primario,
          cursor: 'pointer', flexShrink: 0 }} />
      <span>
        <span style={{ fontSize: '14px', fontWeight: 600, color: COLOR.texto }}>{etiqueta}</span>
        {ayuda ? (
          <span style={{ display: 'block', fontSize: '12px', color: COLOR.suave, lineHeight: 1.4 }}>
            {ayuda}
          </span>
        ) : null}
      </span>
    </label>
  );
}

const TONOS = {
  info: { fondo: COLOR.primarioSuave, borde: '#c7d2fe', texto: '#3730a3', Icono: Info },
  ok: { fondo: COLOR.okSuave, borde: '#a7f3d0', texto: '#065f46', Icono: Check },
  alerta: { fondo: COLOR.alertaSuave, borde: '#fde68a', texto: '#92400e', Icono: AlertTriangle },
  error: { fondo: COLOR.errorSuave, borde: '#fecaca', texto: '#991b1b', Icono: X },
};

export function Aviso({ tono = 'info', titulo: encabezado, children, style }) {
  const t = TONOS[tono] || TONOS.info;
  const { Icono } = t;
  return (
    <div style={{ display: 'flex', gap: '10px', padding: '12px 14px', borderRadius: '12px',
      backgroundColor: t.fondo, border: `1px solid ${t.borde}`, color: t.texto, ...style }}>
      <Icono size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
      <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
        {encabezado ? <strong style={{ display: 'block', marginBottom: '2px' }}>{encabezado}</strong> : null}
        {children}
      </div>
    </div>
  );
}

export function Cargando({ texto = 'Cargando…' }) {
  return (
    <div style={{ padding: '48px', textAlign: 'center', color: COLOR.suave, fontSize: '13px' }}>
      <Loader2 size={26} style={{ color: COLOR.primario, animation: 'spin 1s linear infinite' }} />
      <p style={{ margin: '10px 0 0 0' }}>{texto}</p>
    </div>
  );
}

export function Vacio({ titulo: encabezado, children }) {
  return (
    <div style={{ padding: '36px 20px', textAlign: 'center', border: `1px dashed ${COLOR.borde}`,
      borderRadius: '14px', color: COLOR.suave }}>
      <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: COLOR.texto }}>{encabezado}</p>
      <div style={{ fontSize: '13px', marginTop: '6px', lineHeight: 1.5 }}>{children}</div>
    </div>
  );
}


/**
 * Lo que se muestra EN LUGAR de la pantalla cuando la lectura falló.
 *
 * En lugar, no además: un formulario vacío con un botón de Guardar al lado es
 * una invitación a pisar lo que sí estaba. Acá no hay nada que guardar, hay un
 * botón de reintentar.
 */
export function NoSePudoLeer({ que, detalle, onReintentar, reintentando }) {
  return (
    <div style={{ padding: '36px 24px', borderRadius: '16px',
      backgroundColor: COLOR.alertaSuave, border: '1px solid #fde68a',
      textAlign: 'center' }}>
      <AlertTriangle size={26} color={COLOR.alerta} />
      <p style={{ margin: '10px 0 0 0', fontSize: '16px', fontWeight: 700,
        color: '#92400e' }}>
        No se pudo leer {que}
      </p>
      <p style={{ margin: '8px auto 0 auto', fontSize: '13px', color: '#92400e',
        lineHeight: 1.6, maxWidth: '520px' }}>
        <strong>No lo cargues de nuevo hasta que vuelva.</strong> Lo que guardes ahora
        pisaría lo que ya había — y esta pantalla no puede mostrarte qué había,
        justamente porque no lo pudo leer.
      </p>
      {detalle ? (
        <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: '#b45309',
          fontFamily: 'monospace' }}>{detalle}</p>
      ) : null}
      <Boton variante="secundario" style={{ marginTop: '16px' }}
        onClick={onReintentar} cargando={reintentando}>
        <RefreshCw size={14} /> Reintentar
      </Boton>
    </div>
  );
}
