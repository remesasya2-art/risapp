import { useState, useEffect } from 'react';
import { History, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';

const CHANGE_TYPE_LABEL = {
  manual: { text: 'Manual', bg: '#dbeafe', color: '#1e40af' },
  auto_off_hours: { text: 'Auto - Fuera horario', bg: '#fef3c7', color: '#ca8a04' },
  auto_in_hours: { text: 'Auto - En horario', bg: '#dcfce7', color: '#16a34a' },
  auto_weekend: { text: 'Auto - Domingo', bg: '#fce7f3', color: '#be185d' },
  auto_holiday: { text: 'Auto - Feriado VE', bg: '#ede9fe', color: '#7c3aed' },
};

const ROUTE_LABEL = {
  brl_ves: 'BRL → VES',
  ves_brl: 'VES → BRL',
};

export const RateHistoryButton = ({ userRole }) => {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [routeFilter, setRouteFilter] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const qs = routeFilter ? `?route=${routeFilter}` : '';
      const res = await api.get(`/admin/rate-history${qs}`);
      setEntries(res.data.entries || []);
    } catch (e) {
      toast.error('Error cargando historial');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, routeFilter]);

  if (userRole !== 'super_admin') return null;

  const fmtDate = (iso) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleString('es-VE', {
        dateStyle: 'short', timeStyle: 'medium', timeZone: 'America/Caracas'
      });
    } catch { return iso.substring(0, 19); }
  };

  return (
    <>
      <button onClick={() => setOpen(true)}
        style={{
          padding: '8px 12px', borderRadius: '8px',
          border: '1px solid #6366f1', backgroundColor: '#fff',
          color: '#6366f1', fontSize: '12px', fontWeight: '600',
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px'
        }}
        data-testid="rate-history-btn"
      >
        <History style={{ width: '14px', height: '14px' }} /> Historial
      </button>

      {open && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, padding: '16px'
        }} onClick={() => setOpen(false)}>
          <div onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: '#fff', borderRadius: '16px', padding: '24px',
              maxWidth: '900px', width: '100%', maxHeight: '85vh',
              display: 'flex', flexDirection: 'column',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
            }}
            data-testid="rate-history-modal"
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '12px', backgroundColor: '#eef2ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <History style={{ width: '22px', height: '22px', color: '#6366f1' }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>Historial de Tasas</h3>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                    Registro completo de cambios (manual y automático) — zona Caracas
                  </p>
                </div>
              </div>
              <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
                <X style={{ width: '22px', height: '22px', color: '#6b7280' }} />
              </button>
            </div>

            <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
              <select value={routeFilter} onChange={e => setRouteFilter(e.target.value)}
                style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '13px' }}
                data-testid="rate-history-route-filter"
              >
                <option value="">Todas las rutas</option>
                <option value="brl_ves">BRL → VES</option>
                <option value="ves_brl">VES → BRL</option>
              </select>
              <button onClick={load} disabled={loading}
                style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #d1d5db', backgroundColor: '#fff', fontSize: '13px', cursor: loading ? 'not-allowed' : 'pointer' }}
              >{loading ? 'Cargando...' : 'Recargar'}</button>
            </div>

            {entries.length === 0 && !loading ? (
              <p style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
                No hay cambios de tasa registrados aún
              </p>
            ) : (
              <div style={{ overflow: 'auto', flex: 1, border: '1px solid #e5e7eb', borderRadius: '10px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f3f4f6' }}>
                    <tr>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Fecha/Hora</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Ruta</th>
                      <th style={{ padding: '8px', textAlign: 'right' }}>Anterior</th>
                      <th style={{ padding: '8px', textAlign: 'right' }}>Nueva</th>
                      <th style={{ padding: '8px', textAlign: 'right' }}>Cambio</th>
                      <th style={{ padding: '8px', textAlign: 'center' }}>Motivo</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Admin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e, i) => {
                      const delta = e.old_rate != null ? e.new_rate - e.old_rate : null;
                      const up = delta != null && delta > 0;
                      const label = CHANGE_TYPE_LABEL[e.change_type] || { text: e.change_type, bg: '#f3f4f6', color: '#6b7280' };
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                          <td style={{ padding: '8px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtDate(e.timestamp)}</td>
                          <td style={{ padding: '8px', fontWeight: '600' }}>{ROUTE_LABEL[e.route] || e.route}</td>
                          <td style={{ padding: '8px', textAlign: 'right', color: '#6b7280' }}>{e.old_rate != null ? fmt(e.old_rate) : '—'}</td>
                          <td style={{ padding: '8px', textAlign: 'right', fontWeight: '700' }}>{fmt(e.new_rate)}</td>
                          <td style={{ padding: '8px', textAlign: 'right', fontWeight: '600', color: delta == null ? '#6b7280' : up ? '#16a34a' : '#dc2626' }}>
                            {delta != null ? (up ? '+' : '') + fmt(delta) : '—'}
                          </td>
                          <td style={{ padding: '8px', textAlign: 'center' }}>
                            <span style={{ padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600', backgroundColor: label.bg, color: label.color }}>
                              {label.text}
                            </span>
                          </td>
                          <td style={{ padding: '8px', color: '#374151', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {e.admin_email || '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <p style={{ fontSize: '11px', color: '#9ca3af', margin: '10px 0 0 0' }}>
              Total: {entries.length} cambios
            </p>
          </div>
        </div>
      )}
    </>
  );
};
