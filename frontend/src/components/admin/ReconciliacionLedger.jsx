import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar } from '../flujo/confirmar.js';
import { RefreshCw, ShieldCheck, AlertTriangle, BookOpen, X, Play } from 'lucide-react';

const MOV_LABEL = {
  recarga_pix: 'Recarga PIX',
  recarga_ves: 'Recarga VES',
  pago_tarjeta: 'Pago tarjeta',
  bono_referido: 'Bono referido',
  envio_ves: 'Envío VES',
  envio_reais: 'Envío Reais',
  refund_envio: 'Devolución',
  saldo_apertura: 'Saldo apertura',
};

function fmtNum(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtFecha(d) {
  if (!d) return '';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function ReconciliacionLedger() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyOpening, setBusyOpening] = useState(false);
  const [verUser, setVerUser] = useState(null);     // {user_id, label}
  const [entries, setEntries] = useState(null);
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [buscarUid, setBuscarUid] = useState('');

  const reconciliar = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/ledger/reconcile');
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo reconciliar');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reconciliar(); }, []);

  const crearApertura = async () => {
    if (!await confirmar({
      titulo: '¿Crear las líneas de saldo de apertura?',
      detalle: 'Se crean sólo para los usuarios que todavía no la tienen. No duplica nada si se corre de nuevo.',
      accion: 'Crear apertura',
    })) return;
    setBusyOpening(true);
    try {
      const res = await api.post('/admin/ledger/opening');
      const r = res.data || {};
      toast.success(`Apertura: ${r.aperturas_creadas ?? 0} creadas de ${r.revisados ?? 0} revisados`);
      await reconciliar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo crear la apertura');
    } finally {
      setBusyOpening(false);
    }
  };

  const verLibro = async (uid, label) => {
    if (!uid) { toast.error('Indica el user_id'); return; }
    setVerUser({ user_id: uid, label: label || uid });
    setEntries(null);
    setEntriesLoading(true);
    try {
      const res = await api.get('/admin/ledger/entries', { params: { user_id: uid, limit: 200 } });
      setEntries(res.data);
    } catch (e) {
      toast.error('No se pudo cargar el libro del usuario');
    } finally {
      setEntriesLoading(false);
    }
  };

  const ok = data?.ok;
  const mismatches = data?.mismatches || [];

  const card = { backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #eef0f4' };
  const btnGhost = {
    display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '9px 14px', borderRadius: '10px',
    border: '1px solid #e5e7eb', backgroundColor: '#fff', color: '#374151', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0 }}>Libro mayor · Reconciliación</h2>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
            Compara el saldo guardado de cada usuario contra la suma de su libro. Si todo cuadra, el libro está sano.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button onClick={reconciliar} disabled={loading} style={btnGhost}>
            <RefreshCw size={15} /> {loading ? 'Reconciliando…' : 'Reconciliar'}
          </button>
          <button onClick={crearApertura} disabled={busyOpening} style={{ ...btnGhost, borderColor: '#6366f1', color: '#4F46E5' }}>
            <Play size={15} /> {busyOpening ? 'Creando…' : 'Crear líneas de apertura'}
          </button>
        </div>
      </div>

      {loading && !data ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : data ? (
        <>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
            <div style={{ ...card, flex: '1 1 160px' }}>
              <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>USUARIOS REVISADOS</p>
              <p style={{ fontSize: '24px', fontWeight: 800, color: '#111827', margin: '4px 0 0 0' }}>{data.checked}</p>
            </div>
            <div style={{ ...card, flex: '1 1 160px', backgroundColor: ok ? '#ECFDF5' : '#FEF2F2', border: `1px solid ${ok ? '#A7F3D0' : '#FECACA'}` }}>
              <p style={{ fontSize: '12px', color: ok ? '#047857' : '#b91c1c', margin: 0 }}>ESTADO</p>
              <p style={{ fontSize: '20px', fontWeight: 800, color: ok ? '#047857' : '#b91c1c', margin: '4px 0 0 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {ok ? <><ShieldCheck size={20} /> Todo cuadra</> : <><AlertTriangle size={20} /> {data.mismatches_count} descuadre{data.mismatches_count === 1 ? '' : 's'}</>}
              </p>
            </div>
          </div>

          {!ok && (
            <div style={{ ...card, marginBottom: '16px', padding: 0, overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                      {['Usuario', 'Saldo guardado', 'Suma del libro', 'Diferencia', ''].map((h) => (
                        <th key={h} style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mismatches.map((m) => (
                      <tr key={m.user_id} style={{ borderTop: '1px solid #f1f2f6' }}>
                        <td style={{ padding: '10px 12px' }}>
                          <div style={{ fontWeight: 600, color: '#111827' }}>{m.name || '—'}</div>
                          <div style={{ fontSize: '11px', color: '#9ca3af' }}>{m.email} · {m.role}</div>
                        </td>
                        <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{fmtNum(m.balance_ris)} RIS</td>
                        <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>{fmtNum(m.ledger_sum)} RIS</td>
                        <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', fontWeight: 700, color: '#dc2626' }}>{fmtNum(m.diff)}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <button onClick={() => verLibro(m.user_id, m.name || m.email)} style={{ ...btnGhost, padding: '6px 10px', fontSize: '12.5px' }}>
                            <BookOpen size={13} /> Ver libro
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ ...card }}>
            <p style={{ fontSize: '13px', fontWeight: 700, color: '#374151', margin: '0 0 10px 0' }}>Ver el libro de un usuario</p>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <input
                value={buscarUid} onChange={(e) => setBuscarUid(e.target.value.trim())}
                placeholder="user_id"
                style={{ flex: '1 1 220px', padding: '10px 12px', borderRadius: '10px', border: '1px solid #e5e7eb', fontSize: '14px' }}
              />
              <button onClick={() => verLibro(buscarUid, buscarUid)} style={{ ...btnGhost, borderColor: '#6366f1', color: '#4F46E5' }}>
                <BookOpen size={15} /> Ver libro
              </button>
            </div>
          </div>
        </>
      ) : null}

      {verUser && (
        <div onClick={() => setVerUser(null)} style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(17,24,39,0.55)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width: '100%', maxWidth: '760px', maxHeight: '85vh', overflowY: 'auto',
            backgroundColor: '#fff', borderRadius: '16px', padding: '20px', position: 'relative',
          }}>
            <button onClick={() => setVerUser(null)} style={{ position: 'absolute', top: '14px', right: '14px', border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={20} /></button>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', margin: '0 0 4px 0' }}>Libro de {verUser.label}</h3>
            {entriesLoading ? (
              <p style={{ color: '#9ca3af' }}>Cargando…</p>
            ) : entries ? (
              <>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', margin: '8px 0 14px 0' }}>
                  <span style={{ padding: '6px 10px', borderRadius: '8px', backgroundColor: '#F3F4F6', fontSize: '12.5px', fontWeight: 600 }}>Saldo: {fmtNum(entries.balance_ris)} RIS</span>
                  <span style={{ padding: '6px 10px', borderRadius: '8px', backgroundColor: '#F3F4F6', fontSize: '12.5px', fontWeight: 600 }}>Suma libro: {fmtNum(entries.ledger_sum)} RIS</span>
                  <span style={{ padding: '6px 10px', borderRadius: '8px', backgroundColor: Math.abs(entries.diff) < 0.01 ? '#ECFDF5' : '#FEF2F2', color: Math.abs(entries.diff) < 0.01 ? '#047857' : '#b91c1c', fontSize: '12.5px', fontWeight: 700 }}>Dif: {fmtNum(entries.diff)}</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
                    <thead>
                      <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                        {['Fecha', 'Movimiento', 'Monto', 'Antes', 'Después', 'Ref.'].map((h) => (
                          <th key={h} style={{ padding: '8px 10px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(entries.entries || []).map((e) => (
                        <tr key={e.entry_id} style={{ borderTop: '1px solid #f1f2f6' }}>
                          <td style={{ padding: '8px 10px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtFecha(e.created_at)}</td>
                          <td style={{ padding: '8px 10px', fontWeight: 600, color: '#111827', whiteSpace: 'nowrap' }}>{MOV_LABEL[e.movement_type] || e.movement_type}</td>
                          <td style={{ padding: '8px 10px', whiteSpace: 'nowrap', fontWeight: 700, color: e.direction === 'credit' ? '#16a34a' : '#dc2626' }}>
                            {e.direction === 'credit' ? '+' : '−'}{fmtNum(e.amount)}
                          </td>
                          <td style={{ padding: '8px 10px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{fmtNum(e.balance_before)}</td>
                          <td style={{ padding: '8px 10px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtNum(e.balance_after)}</td>
                          <td style={{ padding: '8px 10px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{e.display_id ? `#${e.display_id}` : (e.reference?.kind || '')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {(entries.entries || []).length === 0 && (
                  <p style={{ color: '#9ca3af', marginTop: '12px' }}>Este usuario no tiene movimientos en el libro.</p>
                )}
              </>
            ) : (
              <p style={{ color: '#9ca3af' }}>Sin datos.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
