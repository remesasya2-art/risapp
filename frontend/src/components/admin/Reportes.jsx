/**
 * Reportes.jsx — El área de reportes.
 *
 * QUE TIENE QUE CONTESTAR ESTA PANTALLA
 *   «Cuánto movimos, de qué, en qué periodo» — y dejarlo en un archivo que
 *   alguien pueda abrir en Excel y mandar a contabilidad sin retocarlo.
 *
 * DOS COSAS QUE NO SON COSMETICAS
 *   1. LOS TOTALES SON DEL PERIODO, NO DE LA PAGINA. La tabla muestra cien
 *      filas; los totales de arriba suman todo lo que matchea. Si fueran de la
 *      página, el número de arriba y el archivo descargado no darían igual, y
 *      nadie sabría cuál creer.
 *
 *   2. EL HUSO HORARIO ES UN CONTROL, NO UN DETALLE. Define dónde corta el día.
 *      Una operación de las 22:00 en Caracas es del día siguiente en UTC: con el
 *      corte equivocado, el contador busca una operación donde no está.
 *
 * LA LISTA DE FLUJOS SE PIDE, NO SE ESCRIBE
 *   Viene de `/admin/reportes/fuentes`. Así, agregar un flujo en el backend lo
 *   hace aparecer acá sin tocar este archivo — y no puede pasar que la pantalla
 *   ofrezca un flujo que el motor no conoce.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, Download, FileSpreadsheet, FileText, Filter, RefreshCw,
} from 'lucide-react';
import api from '../../utils/api';

/** Husos con los que se corta el día. El negocio vive entre estos dos. */
const HUSOS = [
  { min: -240, etiqueta: 'Caracas (UTC−4)' },
  { min: -180, etiqueta: 'Brasilia (UTC−3)' },
  { min: 0, etiqueta: 'UTC' },
];

const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 10);

const primeroDelMes = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1, 12)
    .toISOString().slice(0, 10);
};

const COLOR = {
  borde: '#e5e7eb', suave: '#6b7280', texto: '#111827',
  primario: '#5B4FE9', primarioSuave: '#eef0ff',
};

const tarjeta = {
  backgroundColor: '#fff', borderRadius: '16px', padding: '18px',
  border: `1px solid ${COLOR.borde}`,
};

export default function Reportes() {
  const [fuentes, setFuentes] = useState([]);
  const [elegidos, setElegidos] = useState([]);
  const [desde, setDesde] = useState(primeroDelMes());
  const [hasta, setHasta] = useState(hoy());
  const [tz, setTz] = useState(-240);
  const [buscar, setBuscar] = useState('');
  const [operador, setOperador] = useState('');
  const [montoMin, setMontoMin] = useState('');
  const [montoMax, setMontoMax] = useState('');
  const [pagina, setPagina] = useState(0);

  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [bajando, setBajando] = useState('');

  const vivo = useRef(true);
  useEffect(() => {
    vivo.current = true;
    api.get('/admin/reportes/fuentes')
      .then((r) => { if (vivo.current) setFuentes(r.data?.fuentes || []); })
      .catch(() => toast.error('No se pudo leer la lista de flujos.'));
    return () => { vivo.current = false; };
  }, []);

  const criterios = useCallback((formato) => ({
    desde,
    hasta,
    tz_min: tz,
    flujos: elegidos.length ? elegidos.join(',') : undefined,
    buscar: buscar.trim() || undefined,
    operador: operador.trim() || undefined,
    monto_min: montoMin.trim() || undefined,
    monto_max: montoMax.trim() || undefined,
    formato,
    limite: 100,
    saltear: pagina * 100,
  }), [desde, hasta, tz, elegidos, buscar, operador, montoMin, montoMax, pagina]);

  const generar = async (paginaNueva = 0) => {
    setCargando(true);
    try {
      const { data } = await api.get('/admin/reportes', {
        params: { ...criterios('json'), saltear: paginaNueva * 100 },
      });
      if (!vivo.current) return;
      setDatos(data);
      setPagina(paginaNueva);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo generar el reporte.');
    } finally {
      if (vivo.current) setCargando(false);
    }
  };

  const descargar = async (formato) => {
    setBajando(formato);
    try {
      const res = await api.get('/admin/reportes', {
        params: criterios(formato), responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `risapp_reporte_${desde}_a_${hasta}.${formato}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('No se pudo descargar el reporte.');
    } finally {
      setBajando('');
    }
  };

  const alternar = (clave) => setElegidos((previos) => (
    previos.includes(clave) ? previos.filter((c) => c !== clave) : [...previos, clave]
  ));

  const filas = datos?.filas || [];
  const totales = Object.entries(datos?.totales || {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 700,
          display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileText size={17} /> Reportes de operaciones
        </h3>
        <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: COLOR.suave }}>
          Todo lo que la app cobró y movió en un periodo. Los totales son del
          <strong> periodo entero</strong>, no de lo que se ve en la tabla.
        </p>

        <div style={{ display: 'grid', gap: '12px',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <Campo etiqueta="Desde">
            <input type="date" value={desde} max={hasta} style={entrada}
              onChange={(e) => setDesde(e.target.value)} data-testid="reporte-desde" />
          </Campo>
          <Campo etiqueta="Hasta">
            <input type="date" value={hasta} min={desde} max={hoy()} style={entrada}
              onChange={(e) => setHasta(e.target.value)} data-testid="reporte-hasta" />
          </Campo>
          {/* No es cosmético: define dónde corta el día. */}
          <Campo etiqueta="El día corta en"
            ayuda="Una operación de las 22:00 en Caracas es del día siguiente en UTC.">
            <select value={tz} style={entrada}
              onChange={(e) => setTz(Number(e.target.value))}>
              {HUSOS.map((h) => (
                <option key={h.min} value={h.min}>{h.etiqueta}</option>
              ))}
            </select>
          </Campo>
        </div>

        <div style={{ marginTop: '14px' }}>
          <p style={{ margin: '0 0 8px 0', fontSize: '12px', fontWeight: 700,
            letterSpacing: '.5px', color: COLOR.suave, textTransform: 'uppercase' }}>
            Flujos
          </p>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {fuentes.map((f) => {
              const activo = elegidos.includes(f.clave);
              return (
                <button key={f.clave} type="button" onClick={() => alternar(f.clave)}
                  style={{ padding: '7px 13px', borderRadius: '999px', fontSize: '13px',
                    fontWeight: 600, cursor: 'pointer',
                    border: `1px solid ${activo ? COLOR.primario : COLOR.borde}`,
                    backgroundColor: activo ? COLOR.primarioSuave : '#fff',
                    color: activo ? COLOR.primario : COLOR.suave }}>
                  {f.etiqueta}
                </button>
              );
            })}
          </div>
          <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
            {elegidos.length === 0
              ? 'Sin elegir ninguno entran todos.'
              : `${elegidos.length} de ${fuentes.length} seleccionados.`}
          </p>
        </div>

        <details style={{ marginTop: '14px' }}>
          <summary style={{ cursor: 'pointer', fontSize: '13px', fontWeight: 600,
            color: COLOR.primario, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={14} /> Más filtros
          </summary>
          <div style={{ display: 'grid', gap: '12px', marginTop: '12px',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
            <Campo etiqueta="Buscar"
              ayuda="Referencia, email, nombre, beneficiario o documento.">
              <input value={buscar} style={entrada} placeholder="W-001, ana@…"
                onChange={(e) => setBuscar(e.target.value)} />
            </Campo>
            <Campo etiqueta="Procesado por">
              <input value={operador} style={entrada} placeholder="op_juan"
                onChange={(e) => setOperador(e.target.value)} />
            </Campo>
            <Campo etiqueta="Monto mínimo">
              <input value={montoMin} style={entrada} inputMode="decimal" placeholder="0"
                onChange={(e) => setMontoMin(e.target.value)} />
            </Campo>
            <Campo etiqueta="Monto máximo">
              <input value={montoMax} style={entrada} inputMode="decimal" placeholder="—"
                onChange={(e) => setMontoMax(e.target.value)} />
            </Campo>
          </div>
        </details>

        <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
          <Boton onClick={() => generar(0)} cargando={cargando} principal>
            <RefreshCw size={14} /> Generar
          </Boton>
          <Boton onClick={() => descargar('xlsx')} cargando={bajando === 'xlsx'}
            disabled={!datos}>
            <FileSpreadsheet size={14} /> Excel (.xlsx)
          </Boton>
          <Boton onClick={() => descargar('csv')} cargando={bajando === 'csv'}
            disabled={!datos}>
            <Download size={14} /> CSV
          </Boton>
        </div>
        {datos ? (
          <p style={{ margin: '10px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
            La descarga trae <strong>todas</strong> las filas del periodo, no solo las
            que se ven acá, y el archivo lleva los mismos totales arriba.
          </p>
        ) : null}
      </div>

      {datos?.truncado ? (
        <div style={{ ...tarjeta, backgroundColor: '#fef2f2', borderColor: '#fecaca',
          display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
          <AlertTriangle size={18} color="#b91c1c" style={{ flexShrink: 0 }} />
          <div style={{ fontSize: '13px', color: '#991b1b' }}>
            <strong>Estos números están incompletos.</strong> El periodo superó el
            tope de lectura, así que los totales de abajo <strong>no son el total
            real</strong>. Pedí el reporte en tramos más cortos.
          </div>
        </div>
      ) : null}

      {datos ? (
        <div style={tarjeta}>
          <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 700 }}>
            Totales del periodo · {datos.operaciones} operaciones
          </h4>
          {totales.length === 0 ? (
            <p style={{ margin: 0, fontSize: '13px', color: COLOR.suave }}>
              No hubo operaciones en este periodo con estos filtros.
            </p>
          ) : (
            <div style={{ display: 'grid', gap: '10px',
              gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))' }}>
              {totales.map(([flujo, t]) => (
                <div key={flujo} style={{ border: `1px solid ${COLOR.borde}`,
                  borderRadius: '12px', padding: '12px 14px' }}>
                  <p style={{ margin: 0, fontSize: '12px', fontWeight: 700,
                    color: COLOR.suave }}>{flujo}</p>
                  <p style={{ margin: '6px 0 0 0', fontSize: '20px', fontWeight: 800 }}>
                    {t.total_origen} <span style={{ fontSize: '13px',
                      color: COLOR.suave }}>{t.unidad_origen}</span>
                  </p>
                  {t.unidad_destino ? (
                    <p style={{ margin: '2px 0 0 0', fontSize: '13px', color: COLOR.suave }}>
                      → {t.total_destino} {t.unidad_destino}
                    </p>
                  ) : null}
                  <p style={{ margin: '6px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
                    {t.operaciones} {t.operaciones === 1 ? 'operación' : 'operaciones'}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {datos ? (
        <div style={{ ...tarjeta, padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb' }}>
                  {['Fecha', 'Flujo', 'Referencia', 'Usuario', 'Contraparte',
                    'Monto', 'Destino', 'Tasa', 'Operador', 'Compr.'].map((t) => (
                    <th key={t} style={celdaCabecera}>{t}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filas.length === 0 ? (
                  <tr><td colSpan={10} style={{ ...celda, textAlign: 'center',
                    color: COLOR.suave, padding: '28px' }}>
                    Nada para mostrar con estos criterios.
                  </td></tr>
                ) : filas.map((f, i) => (
                  <tr key={`${f.referencia}-${f.flujo}-${i}`}
                    style={{ borderTop: `1px solid ${COLOR.borde}` }}>
                    <td style={{ ...celda, whiteSpace: 'nowrap' }}>{f.fecha}</td>
                    <td style={celda}>{f.flujo}</td>
                    <td style={{ ...celda, fontFamily: 'monospace' }}>{f.referencia}</td>
                    <td style={celda}>{f.usuario || f.email}</td>
                    <td style={celda}>{f.contraparte || '—'}</td>
                    <td style={{ ...celda, textAlign: 'right', fontWeight: 700,
                      whiteSpace: 'nowrap' }}>
                      {f.monto_origen} {f.unidad_origen}
                    </td>
                    <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap',
                      color: COLOR.suave }}>
                      {f.monto_destino ? `${f.monto_destino} ${f.unidad_destino}` : '—'}
                    </td>
                    <td style={{ ...celda, color: COLOR.suave }}>{f.tasa || '—'}</td>
                    <td style={{ ...celda, color: COLOR.suave }}>{f.operador || '—'}</td>
                    <td style={{ ...celda, textAlign: 'center' }}>
                      {f.comprobante ? '✓' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(pagina > 0 || datos.hay_mas) ? (
            <div style={{ display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', padding: '12px 16px',
              borderTop: `1px solid ${COLOR.borde}` }}>
              <Boton onClick={() => generar(pagina - 1)} disabled={pagina === 0}>
                Anterior
              </Boton>
              <span style={{ fontSize: '12px', color: COLOR.suave }}>
                Filas {pagina * 100 + 1}–{pagina * 100 + filas.length} de {datos.operaciones}
              </span>
              <Boton onClick={() => generar(pagina + 1)} disabled={!datos.hay_mas}>
                Siguiente
              </Boton>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const entrada = {
  width: '100%', padding: '9px 11px', borderRadius: '10px',
  border: `1px solid ${COLOR.borde}`, fontSize: '13px', color: COLOR.texto,
  backgroundColor: '#fff', boxSizing: 'border-box',
};

const celdaCabecera = {
  padding: '10px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 700,
  letterSpacing: '.4px', textTransform: 'uppercase', color: COLOR.suave,
  whiteSpace: 'nowrap',
};

const celda = { padding: '10px 12px', verticalAlign: 'top' };

function Campo({ etiqueta, ayuda, children }) {
  return (
    <label style={{ display: 'block' }}>
      <span style={{ display: 'block', fontSize: '12px', fontWeight: 600,
        color: COLOR.suave, marginBottom: '5px' }}>{etiqueta}</span>
      {children}
      {ayuda ? (
        <span style={{ display: 'block', fontSize: '11px', color: COLOR.suave,
          marginTop: '4px' }}>{ayuda}</span>
      ) : null}
    </label>
  );
}

function Boton({ children, onClick, cargando, disabled, principal }) {
  const inactivo = cargando || disabled;
  return (
    <button type="button" onClick={onClick} disabled={inactivo}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '7px',
        padding: '9px 15px', borderRadius: '10px', fontSize: '13px', fontWeight: 600,
        cursor: inactivo ? 'not-allowed' : 'pointer',
        border: principal ? 'none' : `1px solid ${COLOR.borde}`,
        backgroundColor: principal ? COLOR.primario : '#fff',
        color: principal ? '#fff' : COLOR.texto,
        opacity: inactivo ? 0.5 : 1 }}>
      {cargando ? 'Trabajando…' : children}
    </button>
  );
}
