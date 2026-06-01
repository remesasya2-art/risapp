import { useState, useEffect } from 'react';
import { RotateCcw, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';

/**
 * Super admin only. Restore (unhide) transactions with multi-select UI.
 * Props:
 *  - userRole: current user role
 *  - onSuccess: callback after restore
 *  - size: 'sm' | 'md'
 */
export const RestoreButton = ({ userRole, onSuccess, size = 'md' }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [restoring, setRestoring] = useState(false);

  const loadHidden = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/hidden-transactions');
      setItems(res.data.transactions || []);
      setSelected(new Set());
    } catch (e) {
      toast.error('Error cargando transacciones');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadHidden();
  }, [open]);

  if (userRole !== 'super_admin') return null;

  const toggleOne = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map(i => i.transaction_id)));
  };

  const restoreSelected = async (all = false) => {
    if (!all && selected.size === 0) { toast.error('Selecciona al menos una'); return; }
    const body = all ? { restore_all: true } : { transaction_ids: Array.from(selected) };
    setRestoring(true);
    try {
      const res = await api.post('/admin/restore-transactions', body);
      toast.success(`${res.data.restored} restauradas`);
      setOpen(false);
      setSelected(new Set());
      if (onSuccess) onSuccess();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Error');
    } finally {
      setRestoring(false);
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Caracas' });
    } catch { return iso.substring(0, 16); }
  };

  const btnStyle = size === 'sm'
    ? { padding: '8px 12px', fontSize: '12px' }
    : { padding: '10px 16px', fontSize: '13px' };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          ...btnStyle,
          borderRadius: '10px', border: '1px solid #0891b2',
          backgroundColor: '#fff', color: '#0891b2',
          fontWeight: '600', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: '6px'
        }}
        data-testid="restore-btn"
      >
        <RotateCcw style={{ width: '14px', height: '14px' }} /> Restaurar
      </button>

      {open && (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, padding: '16px'
        }} onClick={() => !restoring && setOpen(false)}>
          <div onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: '#fff', borderRadius: '16px', padding: '24px',
              maxWidth: '900px', width: '100%', maxHeight: '85vh',
              display: 'flex', flexDirection: 'column',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
            }}
            data-testid="restore-modal"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
              <div style={{
                width: '44px', height: '44px', borderRadius: '12px',
                backgroundColor: '#ecfeff', display: 'flex',
                alignItems: 'center', justifyContent: 'center'
              }}>
                <RotateCcw style={{ width: '22px', height: '22px', color: '#0891b2' }} />
              </div>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
                  Restaurar Transacciones Ocultas
                </h3>
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>
                  Selecciona las transacciones que quieres mostrar de nuevo en admin/contabilidad
                </p>
              </div>
            </div>

            {loading ? (
              <p style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>Cargando...</p>
            ) : items.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center' }}>
                <AlertCircle style={{ width: '40px', height: '40px', color: '#9ca3af', margin: '0 auto 12px' }} />
                <p style={{ color: '#6b7280', fontSize: '14px' }}>No hay transacciones ocultas</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px', padding: '10px', backgroundColor: '#f9fafb', borderRadius: '10px' }}>
                  <input type="checkbox"
                    checked={items.length > 0 && selected.size === items.length}
                    onChange={toggleAll}
                    data-testid="restore-select-all"
                  />
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#374151' }}>
                    Seleccionar todo ({selected.size} / {items.length})
                  </span>
                </div>

                <div style={{ overflow: 'auto', flex: 1, border: '1px solid #e5e7eb', borderRadius: '10px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f3f4f6' }}>
                      <tr>
                        <th style={{ padding: '8px', textAlign: 'left', width: '40px' }}></th>
                        <th style={{ padding: '8px', textAlign: 'left' }}>ID</th>
                        <th style={{ padding: '8px', textAlign: 'left' }}>Fecha</th>
                        <th style={{ padding: '8px', textAlign: 'left' }}>Usuario</th>
                        <th style={{ padding: '8px', textAlign: 'left' }}>Tipo</th>
                        <th style={{ padding: '8px', textAlign: 'right' }}>Monto IN</th>
                        <th style={{ padding: '8px', textAlign: 'right' }}>Monto OUT</th>
                        <th style={{ padding: '8px', textAlign: 'center' }}>Moneda</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map(item => {
                        const isSel = selected.has(item.transaction_id);
                        return (
                          <tr key={item.transaction_id}
                            onClick={() => toggleOne(item.transaction_id)}
                            style={{
                              borderBottom: '1px solid #f3f4f6',
                              cursor: 'pointer',
                              backgroundColor: isSel ? '#ecfeff' : '#fff'
                            }}
                            data-testid={`restore-row-${item.transaction_id}`}
                          >
                            <td style={{ padding: '8px' }}>
                              <input type="checkbox" checked={isSel} onChange={() => {}} />
                            </td>
                            <td style={{ padding: '8px', fontWeight: '600' }}>{item.display_id}</td>
                            <td style={{ padding: '8px', color: '#6b7280' }}>{fmtDate(item.created_at)}</td>
                            <td style={{ padding: '8px', color: '#374151', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.user_name}</td>
                            <td style={{ padding: '8px' }}>
                              <span style={{
                                padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600',
                                backgroundColor: item.type === 'withdrawal' ? '#fef2f2' : '#dcfce7',
                                color: item.type === 'withdrawal' ? '#dc2626' : '#16a34a'
                              }}>{item.type}</span>
                            </td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>{fmt(item.amount_input)}</td>
                            <td style={{ padding: '8px', textAlign: 'right', fontWeight: '600' }}>{fmt(item.amount_output)}</td>
                            <td style={{ padding: '8px', textAlign: 'center', color: '#6b7280' }}>{item.currency || '-'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'space-between', marginTop: '16px' }}>
              <button onClick={() => setOpen(false)} disabled={restoring}
                style={{ padding: '10px 18px', borderRadius: '10px', border: '1px solid #d1d5db', backgroundColor: '#fff', color: '#374151', fontSize: '13px', fontWeight: '600', cursor: restoring ? 'not-allowed' : 'pointer' }}
              >Cerrar</button>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button onClick={() => restoreSelected(false)} disabled={restoring || selected.size === 0}
                  style={{
                    padding: '10px 18px', borderRadius: '10px', border: 'none',
                    backgroundColor: selected.size > 0 ? '#0891b2' : '#a5f3fc',
                    color: '#fff', fontSize: '13px', fontWeight: '700',
                    cursor: (restoring || selected.size === 0) ? 'not-allowed' : 'pointer'
                  }}
                  data-testid="restore-selected-btn"
                >
                  {restoring ? 'Restaurando...' : `Restaurar (${selected.size})`}
                </button>
                <button onClick={() => restoreSelected(true)} disabled={restoring || items.length === 0}
                  style={{
                    padding: '10px 18px', borderRadius: '10px', border: 'none',
                    backgroundColor: '#16a34a', color: '#fff', fontSize: '13px', fontWeight: '700',
                    cursor: (restoring || items.length === 0) ? 'not-allowed' : 'pointer'
                  }}
                  data-testid="restore-all-btn"
                >
                  Restaurar TODO ({items.length})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
