/**
 * PuestaEnMarcha.jsx — La portada: qué falta para poder operar, en orden.
 *
 * El módulo recién instalado no puede cotizar y tiene razón: no hay
 * transportistas, no hay precios, no hay una dirección a la que despachar. Sin
 * esta pantalla, la primera señal de que falta cargar algo es una cotización que
 * falla en la cara de un usuario.
 *
 * DOS COSAS QUE ESTA PANTALLA NO PUEDE HACER
 *   1. Confundir "no está cargado" con "no lo pude leer". El backend distingue
 *      los tres estados a propósito; acá se muestran distinto y el ilegible NO
 *      invita a cargar nada. Alguien que carga el punto de origen de memoria
 *      durante un corte pisa la plantilla y la Caixa Postal reales.
 *   2. Decir que se puede operar cuando hubo lecturas fallidas. "No sé" no es
 *      "sí".
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, CircleDashed, RefreshCw } from 'lucide-react';
import api from '../../../utils/api';
import { Aviso, Boton, Cargando } from '../../envios/ui';
import { COLOR, mensajeDeError, tarjeta } from '../../envios/estilos';

const ICONO = {
  listo: { Icono: Check, color: COLOR.ok, fondo: COLOR.okSuave, borde: '#a7f3d0' },
  falta: { Icono: CircleDashed, color: COLOR.suave, fondo: '#f9fafb', borde: COLOR.borde },
  ilegible: { Icono: AlertTriangle, color: COLOR.alerta, fondo: COLOR.alertaSuave, borde: '#fde68a' },
};

/** Convierte el `**negrita**` que usan los mensajes del backend. */
function conNegritas(texto) {
  return String(texto || '').split(/(\*\*[^*]+\*\*)/g).map((parte, i) =>
    parte.startsWith('**') && parte.endsWith('**')
      ? <strong key={i}>{parte.slice(2, -2)}</strong>
      : <span key={i}>{parte}</span>);
}

export default function PuestaEnMarcha({ onIr }) {
  const [estado, setEstado] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [visto, setVisto] = useState(null);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/estado');
      if (!vivo.current) return;
      setEstado(res.data);
      setError(null);
      setVisto(new Date());
    } catch (err) {
      if (!vivo.current) return;
      setError(mensajeDeError(err, 'No se pudo leer el estado del módulo.'));
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  if (cargando && !estado) return <Cargando texto="Revisando qué falta…" />;
  if (error && !estado) {
    return (
      <div style={tarjeta}>
        <Aviso tono="error" titulo="No se pudo leer el estado">{error}</Aviso>
        <Boton variante="secundario" onClick={cargar} style={{ marginTop: '14px' }}>
          <RefreshCw size={14} /> Reintentar
        </Boton>
      </div>
    );
  }

  const pasos = estado?.pasos || [];
  const listos = pasos.filter((p) => p.estado === 'listo').length;
  const puedeOperar = !!estado?.puede_operar;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{
        ...tarjeta,
        background: puedeOperar
          ? 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)'
          : 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
        borderColor: puedeOperar ? '#a7f3d0' : '#c7d2fe',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <p style={{ fontSize: '12px', margin: 0, fontWeight: 700, letterSpacing: '0.04em',
              textTransform: 'uppercase', color: puedeOperar ? '#065f46' : '#3730a3' }}>
              Puesta en marcha
            </p>
            <p style={{ fontSize: '24px', fontWeight: 800, margin: '4px 0 0 0',
              color: puedeOperar ? '#065f46' : '#312e81' }}>
              {puedeOperar
                ? 'El módulo puede operar'
                : `${listos} de ${pasos.length} pasos listos`}
            </p>
            <p style={{ fontSize: '13px', margin: '4px 0 0 0', lineHeight: 1.5,
              color: puedeOperar ? '#047857' : '#4338ca' }}>
              {puedeOperar
                ? 'Los usuarios pueden cotizar. Cambiar cualquiera de estos bloques sigue siendo seguro: la tarifa se versiona y lo que va impreso en una caja queda congelado en el envío.'
                : 'Hasta que estén los siete, /envios/limites contesta que el servicio no está disponible y nadie puede cotizar. Cargalos en este orden: cada uno depende de los de arriba.'}
            </p>
          </div>
          <Boton variante="secundario" onClick={() => { setCargando(true); cargar(); }} cargando={cargando}>
            <RefreshCw size={14} /> Revisar de nuevo
          </Boton>
        </div>
      </div>

      {error ? (
        // El checklist viejo sigue en pantalla, y puede estar diciendo «el módulo
        // puede operar» en verde mientras la base está caída. «No sé» no es «sí»,
        // y eso vale también para el refresco, no solo para la primera lectura.
        <Aviso tono="error" titulo="Este checklist puede estar viejo">
          El último intento de revisar falló: {error}
          {visto ? ` Lo de abajo es lo que se leyó a las ${visto.toLocaleTimeString('es-AR')}.` : ''}
        </Aviso>
      ) : null}

      {estado?.hay_lecturas_fallidas ? (
        <Aviso tono="alerta" titulo="Hay bloques que no se pudieron leer">
          No los cargues de nuevo hasta que la base vuelva: lo que guardes ahora pisaría lo que
          ya había. Un bloque que no se puede leer no es un bloque vacío.
        </Aviso>
      ) : null}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {pasos.map((paso, i) => {
          const t = ICONO[paso.estado] || ICONO.falta;
          const { Icono } = t;
          const esSiguiente = paso.clave === estado?.siguiente;
          return (
            <div key={paso.clave} style={{
              ...tarjeta, padding: '16px 18px', display: 'flex', gap: '14px',
              // `wrap` y no `nowrap`: en un teléfono el botón le comía el ancho
              // al texto hasta dejarlo en una columna de dos palabras, y encima
              // se montaba sobre la insignia. Acá baja a su propia línea.
              alignItems: 'flex-start', flexWrap: 'wrap',
              borderColor: esSiguiente ? COLOR.primario : t.borde,
              backgroundColor: esSiguiente ? COLOR.primarioSuave : t.fondo,
              borderWidth: esSiguiente ? '2px' : '1px',
            }}>
              <div style={{ width: '30px', height: '30px', borderRadius: '9px', flexShrink: 0,
                backgroundColor: '#fff', border: `1px solid ${t.borde}`,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icono size={16} color={t.color} />
              </div>
              <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                <p style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: COLOR.texto }}>
                  <span style={{ color: COLOR.suave, fontWeight: 600 }}>{i + 1}. </span>
                  {paso.titulo}
                  {esSiguiente ? (
                    <span style={{ marginLeft: '8px', fontSize: '11px', fontWeight: 700,
                      color: COLOR.primarioOscuro, backgroundColor: '#fff', padding: '2px 8px',
                      borderRadius: '999px', border: `1px solid ${COLOR.primario}` }}>
                      empezá por acá
                    </span>
                  ) : null}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: COLOR.suave,
                  lineHeight: 1.5 }}>
                  {conNegritas(paso.detalle)}
                </p>
              </div>
              {paso.estado !== 'ilegible' && paso.donde ? (
                <Boton variante={esSiguiente ? 'primario' : 'secundario'}
                  style={{ marginLeft: 'auto' }}
                  onClick={() => onIr(paso.donde)}>
                  {paso.estado === 'listo' ? 'Ver' : 'Cargar'} <ArrowRight size={14} />
                </Boton>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
