/**
 * Errores — lo que se rompió, antes de que un cliente lo cuente.
 *
 * Cada error de servidor queda asentado con su rastro (el código que el
 * cliente ve en pantalla y le pasa a soporte), la ruta, quién lo sufrió y
 * desde dónde. Acá se listan de más nuevo a más viejo, con un resumen de las
 * últimas 24 horas arriba: si el número es cero, no hay nada que leer.
 *
 * Lo que NO está: el cuerpo del pedido ni las cabeceras. Un pedido que falló
 * al entrar trae la contraseña; uno con sesión trae el token. Eso no se
 * guarda, así que tampoco se puede mostrar. Ver backend/services/errores.py.
 */
import { useState, useEffect } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

const POR_PAGINA = 50;

const fmtFecha = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'medium' }); }
  catch { return iso; }
};

const COLOR_DE_STATUS = (s) => (s >= 500 ? '#dc2626' : '#d97706');

const tarjeta = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 16px' };
const rotulo = { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280', marginBottom: 4 };

export default function Errores() {
  const [resumen, setResumen] = useState(null);
  const [lineas, setLineas] = useState([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [pagina, setPagina] = useState(0);
  const [ruta, setRuta] = useState('');
  const [abierta, setAbierta] = useState(null);
  const [vuelta, setVuelta] = useState(0);

  useEffect(() => {
    let vigente = true;
    api.get('/admin/errores/resumen?horas=24')
      .then((r) => { if (vigente) setResumen(r.data || null); })
      .catch(() => {});
    return () => { vigente = false; };
  }, [vuelta]);

  useEffect(() => {
    let vigente = true;
    const q = new URLSearchParams({ limite: String(POR_PAGINA), saltar: String(pagina * POR_PAGINA) });
    if (ruta) q.set('ruta', ruta);
    setCargando(true);
    api.get(`/admin/errores?${q.toString()}`)
      .then((r) => {
        if (!vigente) return;
        setLineas(r.data?.lineas || []);
        setTotal(r.data?.total || 0);
      })
      .catch((e) => { if (vigente) toast.error(e?.response?.data?.detail || 'No se pudo leer el registro de errores'); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [pagina, ruta, vuelta]);

  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} data-testid="errores">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <AlertTriangle size={20} color="#dc2626" />
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Errores</h2>
        <span style={{ color: '#6b7280', fontSize: 13 }}>
          lo que se rompió en el servidor, con el código que ve el cliente
        </span>
        <div style={{ flex: 1 }} />
        <button onClick={() => setVuelta((v) => v + 1)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', borderRadius: 10,
                         border: '1px solid #e5e7eb', background: '#fff', fontSize: 13, cursor: 'pointer' }}>
          <RefreshCw size={14} /> Actualizar
        </button>
      </div>

      {/* Las últimas 24 horas, de un vistazo. */}
      {resumen && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <div style={tarjeta}>
            <div style={rotulo}>Errores en 24 h</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: resumen.total ? '#dc2626' : '#16a34a' }}
                 data-testid="errores-24h">
              {resumen.total}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>
              {resumen.ultimo ? `el último ${fmtFecha(resumen.ultimo)}` : 'ninguno, todo en orden'}
            </div>
          </div>
          <div style={{ ...tarjeta, gridColumn: 'span 2' }}>
            <div style={rotulo}>Dónde</div>
            {resumen.rutas?.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                {resumen.rutas.slice(0, 6).map((r) => (
                  <button key={r.ruta} onClick={() => { setPagina(0); setRuta(r.ruta); }}
                          style={{ display: 'flex', justifyContent: 'space-between', background: 'none',
                                   border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', fontSize: 13 }}>
                    <code style={{ color: '#111827' }}>{r.ruta}</code>
                    <strong>{r.cuantos}</strong>
                  </button>
                ))}
              </div>
            ) : <span style={{ color: '#6b7280', fontSize: 13 }}>—</span>}
          </div>
        </div>
      )}

      {ruta && (
        <div style={{ fontSize: 13, color: '#6b7280' }}>
          Mostrando sólo <code>{ruta}</code>{' '}
          <button onClick={() => { setPagina(0); setRuta(''); }}
                  style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', fontSize: 13 }}>
            ver todos
          </button>
        </div>
      )}

      {cargando ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : lineas.length === 0 ? (
        <p style={{ color: '#6b7280' }}>No hay errores registrados{ruta ? ' en esa ruta' : ''}. Bien.</p>
      ) : (
        <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
          {lineas.map((l, i) => {
            const clave = `${l.rastro}-${i}`;
            const desplegada = abierta === clave;
            return (
              <div key={clave} style={{ borderTop: i ? '1px solid #f3f4f6' : 'none' }}>
                <button onClick={() => setAbierta(desplegada ? null : clave)}
                        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '10px 12px',
                                 background: desplegada ? '#f9fafb' : '#fff', border: 'none', textAlign: 'left',
                                 cursor: 'pointer', fontSize: 13 }}
                        data-testid={`error-${l.rastro}`}>
                  {desplegada ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <span style={{ background: COLOR_DE_STATUS(l.status) + '20', color: COLOR_DE_STATUS(l.status),
                                 padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 700 }}>
                    {l.status}
                  </span>
                  <code style={{ whiteSpace: 'nowrap' }}>{l.metodo} {l.ruta}</code>
                  <span style={{ color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.tipo}{l.mensaje ? `: ${l.mensaje}` : ''}
                  </span>
                  <div style={{ flex: 1 }} />
                  <code style={{ color: '#9ca3af', fontSize: 12 }}>{l.rastro}</code>
                  <span style={{ color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtFecha(l.cuando)}</span>
                </button>
                {desplegada && (
                  <div style={{ padding: '12px 12px 16px 37px', background: '#f9fafb', fontSize: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14, marginBottom: 10 }}>
                      <div><div style={rotulo}>Rastro</div><code>{l.rastro}</code></div>
                      <div><div style={rotulo}>Quién</div>{l.user_id || 'sin sesión'}</div>
                      <div><div style={rotulo}>Desde</div>{l.ip || '—'}</div>
                      <div><div style={rotulo}>Cuándo</div>{fmtFecha(l.cuando)}</div>
                    </div>
                    <div style={rotulo}>Mensaje</div>
                    <div style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>{l.mensaje || '—'}</div>
                    {l.traza && (<>
                      <div style={rotulo}>Traza</div>
                      <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', color: '#374151' }}>{l.traza}</pre>
                    </>)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {paginas > 1 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
          <button disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>Anterior</button>
          <span>{pagina + 1} / {paginas}</span>
          <button disabled={pagina + 1 >= paginas} onClick={() => setPagina((p) => p + 1)}>Siguiente</button>
        </div>
      )}
    </div>
  );
}
