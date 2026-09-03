/**
 * LibroAuditoria.jsx — Quién hizo qué, sobre quién, cuándo y desde dónde.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   Había cuatro registros de auditoría en la base —`audit_log`,
 *   `admin_access_log`, `admin_logs`, `accounting_audit_log`— y NINGUNO tenía
 *   pantalla. Dos ni siquiera tenían endpoint. Un registro que nadie puede
 *   leer no es una auditoría: es un archivo que crece.
 *
 *   Ésta es la pantalla del libro único. Sólo lee: no hay forma de editar ni
 *   de borrar una línea, ni acá ni en el backend.
 */
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { RefreshCw, ScrollText, ChevronDown, ChevronRight, Filter } from 'lucide-react';

const COLOR_DE_CATEGORIA = {
  personal: '#7c3aed',
  kyc: '#2563eb',
  dinero: '#15803d',
  usuarios: '#d97706',
  configuracion: '#0891b2',
  sesion: '#6b7280',
  peligro: '#dc2626',
};

const POR_PAGINA = 50;

function fmtFecha(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleString('es-VE', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function Valor({ dato }) {
  if (dato === null || dato === undefined) return <span style={{ color: '#9ca3af' }}>—</span>;
  if (typeof dato !== 'object') return <code>{String(dato)}</code>;
  return (
    <div style={{ display: 'grid', gap: 2 }}>
      {Object.entries(dato).map(([k, v]) => (
        <div key={k}>
          <span style={{ color: '#6b7280' }}>{k}: </span>
          <code>{v === null || v === undefined ? '—' : (typeof v === 'object' ? JSON.stringify(v) : String(v))}</code>
        </div>
      ))}
    </div>
  );
}

export default function LibroAuditoria() {
  const [lineas, setLineas] = useState([]);
  const [total, setTotal] = useState(0);
  const [acciones, setAcciones] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [pagina, setPagina] = useState(0);
  const [filtros, setFiltros] = useState({ categoria: '', accion: '', actor_id: '', objetivo_id: '' });
  const [abierta, setAbierta] = useState(null);

  const consulta = (f, p) => {
    const q = new URLSearchParams({ limite: String(POR_PAGINA), saltar: String(p * POR_PAGINA) });
    Object.entries(f).forEach(([k, v]) => { if (v) q.set(k, v); });
    return `/admin/rrhh/auditoria/libro?${q.toString()}`;
  };

  useEffect(() => {
    let vigente = true;
    api.get(consulta(filtros, pagina))
      .then((r) => {
        if (!vigente) return;
        setLineas(r.data?.lineas || []);
        setTotal(r.data?.total || 0);
      })
      .catch((e) => {
        if (vigente) toast.error(e?.response?.data?.detail || 'No se pudo leer el libro');
      })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [filtros, pagina]);

  useEffect(() => {
    let vigente = true;
    api.get('/admin/rrhh/auditoria/acciones')
      .then((r) => { if (vigente) setAcciones(r.data?.acciones || []); })
      .catch(() => {});
    return () => { vigente = false; };
  }, []);

  const categorias = [...new Set(acciones.map((a) => a.categoria))].sort();
  const accionesDeLaCategoria = filtros.categoria
    ? acciones.filter((a) => a.categoria === filtros.categoria)
    : acciones;

  const cambiar = (campo, valor) => {
    setPagina(0);
    setFiltros((f) => ({
      ...f,
      [campo]: valor,
      // Cambiar de categoría deja sin sentido la acción elegida.
      ...(campo === 'categoria' ? { accion: '' } : {}),
    }));
  };

  const recargar = () => {
    setCargando(true);
    setFiltros((f) => ({ ...f }));   // dispara el efecto sin cambiar nada
  };

  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <ScrollText size={20} color="#7c3aed" />
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Libro de auditoría</h2>
        <span style={{ fontSize: 13, color: '#6b7280' }}>
          {total.toLocaleString('es-VE')} {total === 1 ? 'movimiento' : 'movimientos'}
        </span>
        <div style={{ flex: 1 }} />
        <button onClick={recargar} disabled={cargando} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px',
          background: '#f3f4f6', border: 'none', borderRadius: 8, fontSize: 13,
          fontWeight: 600, cursor: 'pointer',
        }}>
          <RefreshCw size={15} /> Actualizar
        </button>
      </div>

      <div style={{
        display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center',
        background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12,
      }}>
        <Filter size={15} color="#6b7280" />
        <select value={filtros.categoria} onChange={(e) => cambiar('categoria', e.target.value)} style={selector}>
          <option value="">Todas las categorías</option>
          {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filtros.accion} onChange={(e) => cambiar('accion', e.target.value)} style={selector}>
          <option value="">Todas las acciones</option>
          {accionesDeLaCategoria.map((a) => (
            <option key={a.accion} value={a.accion}>{a.etiqueta}</option>
          ))}
        </select>
        <input placeholder="Quién lo hizo (user_id)" value={filtros.actor_id}
               onChange={(e) => cambiar('actor_id', e.target.value)} style={{ ...selector, width: 200 }} />
        <input placeholder="Sobre quién (id)" value={filtros.objetivo_id}
               onChange={(e) => cambiar('objetivo_id', e.target.value)} style={{ ...selector, width: 200 }} />
        {(filtros.categoria || filtros.accion || filtros.actor_id || filtros.objetivo_id) && (
          <button onClick={() => { setPagina(0); setFiltros({ categoria: '', accion: '', actor_id: '', objetivo_id: '' }); }}
                  style={{ background: 'none', border: 'none', color: '#2563eb', fontSize: 13, cursor: 'pointer' }}>
            Limpiar
          </button>
        )}
      </div>

      {cargando ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : lineas.length === 0 ? (
        <p style={{ color: '#6b7280' }}>
          No hay movimientos con esos filtros.
        </p>
      ) : (
        <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
          {lineas.map((l, i) => {
            const clave = `${l.cuando}-${i}`;
            const desplegada = abierta === clave;
            return (
              <div key={clave} style={{ borderTop: i ? '1px solid #f3f4f6' : 'none' }}>
                <button
                  onClick={() => setAbierta(desplegada ? null : clave)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                    padding: '10px 12px', background: desplegada ? '#f9fafb' : '#fff',
                    border: 'none', textAlign: 'left', cursor: 'pointer', fontSize: 13,
                  }}>
                  {desplegada ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <span style={{
                    background: (COLOR_DE_CATEGORIA[l.categoria] || '#6b7280') + '20',
                    color: COLOR_DE_CATEGORIA[l.categoria] || '#6b7280',
                    padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}>
                    {l.categoria}
                  </span>
                  <strong style={{ whiteSpace: 'nowrap' }}>{l.etiqueta}</strong>
                  <span style={{ color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.objetivo?.descripcion || l.objetivo?.id || ''}
                  </span>
                  <div style={{ flex: 1 }} />
                  <span style={{ color: '#9ca3af', whiteSpace: 'nowrap' }}>
                    {l.actor?.email || '—'}
                  </span>
                  <span style={{ color: '#6b7280', whiteSpace: 'nowrap' }}>
                    {fmtFecha(l.cuando)}
                  </span>
                </button>

                {desplegada && (
                  <div style={{ padding: '12px 12px 16px 37px', background: '#f9fafb', fontSize: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                      <div>
                        <div style={rotulo}>Quién</div>
                        <div><strong>{l.actor?.nombre || '—'}</strong></div>
                        <div style={{ color: '#6b7280' }}>{l.actor?.email || '—'}</div>
                        <div style={{ color: '#9ca3af' }}>{l.actor?.rol} · {l.actor?.user_id || '—'}</div>
                      </div>
                      <div>
                        <div style={rotulo}>Sobre</div>
                        <div><strong>{l.objetivo?.descripcion || '—'}</strong></div>
                        <div style={{ color: '#9ca3af' }}>{l.objetivo?.tipo} · {l.objetivo?.id || '—'}</div>
                      </div>
                      <div>
                        <div style={rotulo}>Cuándo</div>
                        <div>{fmtFecha(l.cuando)}</div>
                        <div style={{ color: '#9ca3af' }}>Caracas: {l.cuando_caracas || '—'}</div>
                      </div>
                      <div>
                        <div style={rotulo}>Desde dónde</div>
                        <div>{l.origen?.ip || '—'} {l.origen?.pais ? `· ${l.origen.pais}` : ''}</div>
                        <div style={{ color: '#9ca3af', wordBreak: 'break-all' }}>{l.origen?.navegador || '—'}</div>
                      </div>
                    </div>

                    {(l.antes || l.despues) && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
                        <div>
                          <div style={rotulo}>Antes</div>
                          <Valor dato={l.antes} />
                        </div>
                        <div>
                          <div style={rotulo}>Después</div>
                          <Valor dato={l.despues} />
                        </div>
                      </div>
                    )}

                    {l.detalle && Object.keys(l.detalle).length > 0 && (
                      <div style={{ marginTop: 14 }}>
                        <div style={rotulo}>Detalle</div>
                        <Valor dato={l.detalle} />
                      </div>
                    )}

                    <div style={{ marginTop: 12, color: '#9ca3af' }}>
                      <code>{l.accion}</code>{l.exito === false ? ' · falló' : ''}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {paginas > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center' }}>
          <button onClick={() => setPagina((p) => Math.max(0, p - 1))} disabled={pagina === 0} style={btnPagina}>
            Anterior
          </button>
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            Página {pagina + 1} de {paginas}
          </span>
          <button onClick={() => setPagina((p) => Math.min(paginas - 1, p + 1))}
                  disabled={pagina >= paginas - 1} style={btnPagina}>
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}

const selector = {
  padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6,
  fontSize: 13, background: '#fff',
};
const rotulo = { color: '#6b7280', fontSize: 11, fontWeight: 600, marginBottom: 3 };
const btnPagina = {
  padding: '6px 14px', background: '#f3f4f6', border: '1px solid #e5e7eb',
  borderRadius: 6, fontSize: 13, cursor: 'pointer',
};
