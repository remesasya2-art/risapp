import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { Shield, Trash2, Plus, RefreshCw, Mail, CreditCard, FileText } from 'lucide-react';

const TYPE_META = {
  email:    { label: 'Email',     Icon: Mail,       color: '#2563eb', bg: '#eff6ff' },
  cpf:      { label: 'CPF',       Icon: CreditCard, color: '#7c3aed', bg: '#f5f3ff' },
  document: { label: 'Documento', Icon: FileText,   color: '#ea580c', bg: '#fff7ed' },
};

function fmtFecha(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function ListaNegra() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState('email');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState('all');

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/blacklist');
      setItems(res.data?.items || []);
    } catch (e) {
      toast.error('No se pudo cargar la lista negra');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const add = async () => {
    const v = value.trim();
    if (!v) { toast.error('Escribe un valor para agregar'); return; }
    setAdding(true);
    try {
      const res = await api.post('/admin/blacklist', { type, value: v, reason: reason.trim() });
      toast.success(res.data?.message || 'Agregado a la lista negra');
      setValue('');
      setReason('');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al agregar');
    } finally {
      setAdding(false);
    }
  };

  const remove = async (id, val) => {
    if (!window.confirm(`¿Quitar "${val}" de la lista negra? Esto permitirá su uso de nuevo.`)) return;
    try {
      await api.delete(`/admin/blacklist/${id}`);
      toast.success('Eliminado de la lista negra');
      setItems((prev) => prev.filter((it) => it.blacklist_id !== id));
    } catch (e) {
      toast.error('No se pudo eliminar');
    }
  };

  const shown = filter === 'all' ? items : items.filter((it) => it.type === filter);

  const card = { backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #eef0f4' };
  const input = { padding: '11px 13px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '14px', outline: 'none', boxSizing: 'border-box' };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Shield size={20} color="#dc2626" /> Lista negra
          </h2>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
            Correos, CPF o documentos bloqueados. Un correo en la lista no puede registrarse, y un CPF/documento marca riesgo alto en KYC.
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '9px 14px', borderRadius: '10px',
          border: '1px solid #e5e7eb', backgroundColor: '#fff', color: '#374151', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
        }}>
          <RefreshCw size={15} /> {loading ? 'Cargando…' : 'Actualizar'}
        </button>
      </div>

      <div style={{ ...card, marginBottom: '16px' }}>
        <p style={{ fontSize: '13px', fontWeight: 700, color: '#111827', margin: '0 0 12px 0' }}>Agregar a la lista negra</p>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>Tipo</label>
            <select value={type} onChange={(e) => setType(e.target.value)} style={{ ...input, cursor: 'pointer' }}>
              <option value="email">Email</option>
              <option value="cpf">CPF</option>
              <option value="document">Documento</option>
            </select>
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label style={{ display: 'block', fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>Valor</label>
            <input value={value} onChange={(e) => setValue(e.target.value)} placeholder={type === 'email' ? 'correo@dominio.com' : (type === 'cpf' ? '000.000.000-00' : 'Número de documento')} style={{ ...input, width: '100%' }} />
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label style={{ display: 'block', fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>Motivo (opcional)</label>
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ej: fraude, correo desechable…" style={{ ...input, width: '100%' }} />
          </div>
          <button onClick={add} disabled={adding} style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '11px 18px', borderRadius: '10px',
            border: 'none', backgroundColor: '#dc2626', color: '#fff', fontWeight: 700, fontSize: '14px', cursor: 'pointer', opacity: adding ? 0.6 : 1,
          }}>
            <Plus size={16} /> {adding ? 'Agregando…' : 'Agregar'}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        {[['all', `Todos (${items.length})`], ['email', 'Emails'], ['cpf', 'CPF'], ['document', 'Documentos']].map(([k, lbl]) => (
          <button key={k} onClick={() => setFilter(k)} style={{
            padding: '7px 14px', borderRadius: '999px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
            border: filter === k ? '1px solid #dc2626' : '1px solid #e5e7eb',
            backgroundColor: filter === k ? '#fef2f2' : '#fff', color: filter === k ? '#b91c1c' : '#6b7280',
          }}>{lbl}</button>
        ))}
      </div>

      {loading && items.length === 0 ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : shown.length === 0 ? (
        <div style={{ ...card, textAlign: 'center', color: '#9ca3af', padding: '32px' }}>
          {items.length === 0 ? 'La lista negra está vacía. Agrega correos, CPF o documentos para bloquearlos.' : 'No hay elementos de este tipo.'}
        </div>
      ) : (
        <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                  {['Tipo', 'Valor', 'Motivo', 'Agregado por', 'Fecha', ''].map((h) => (
                    <th key={h} style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((it) => {
                  const meta = TYPE_META[it.type] || TYPE_META.email;
                  return (
                    <tr key={it.blacklist_id} style={{ borderTop: '1px solid #f1f2f6' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '4px 10px', borderRadius: '999px', backgroundColor: meta.bg, color: meta.color, fontWeight: 700, fontSize: '12px' }}>
                          <meta.Icon size={13} /> {meta.label}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', fontWeight: 600, color: '#111827', wordBreak: 'break-all' }}>{it.value}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{it.reason || '—'}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280', whiteSpace: 'nowrap' }}>{it.banned_by_name || '—'}</td>
                      <td style={{ padding: '10px 12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{fmtFecha(it.banned_at)}</td>
                      <td style={{ padding: '10px 12px' }}>
                        <button onClick={() => remove(it.blacklist_id, it.value)} title="Quitar de la lista negra" style={{
                          display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '6px 10px', borderRadius: '8px',
                          border: '1px solid #fecaca', backgroundColor: '#fff', color: '#dc2626', fontWeight: 600, fontSize: '12.5px', cursor: 'pointer',
                        }}>
                          <Trash2 size={13} /> Quitar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
