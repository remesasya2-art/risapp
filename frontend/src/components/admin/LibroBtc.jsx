import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { RefreshCw, Bitcoin, X, FileCheck, FileX } from 'lucide-react';

function fmtNum(n, dec = 2) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('es-VE', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtInt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('es-VE');
}

function fmtFecha(d) {
  if (!d) return '';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function LibroBtc() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detalle, setDetalle] = useState(null);

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/ledger/btc', { params: { limit: 200 } });
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo cargar el libro de BTC');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const card = { backgroundColor: '#fff', borderRadius: '14px', padding: '16px', border: '1px solid #eef0f4' };
  const orders = data?.orders || [];
  const tot = data?.totales || {};

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bitcoin size={20} color="#EA580C" /> Libro de órdenes BTC
          </h2>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
            Órdenes directas BTC ya enviadas. No tocan el saldo RIS: es un libro independiente.
          </p>
        </div>
        <button onClick={cargar} disabled={loading} style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '9px 14px', borderRadius: '10px',
          border: '1px solid #e5e7eb', backgroundColor: '#fff', color: '#374151', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
        }}>
          <RefreshCw size={15} /> {loading ? 'Cargando…' : 'Actualizar'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
        <div style={{ ...card, flex: '1 1 130px' }}>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>ÓRDENES</p>
          <p style={{ fontSize: '22px', fontWeight: 800, color: '#111827', margin: '4px 0 0 0' }}>{data?.count ?? 0}</p>
        </div>
        <div style={{ ...card, flex: '1 1 130px' }}>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>VES PAGADOS</p>
          <p style={{ fontSize: '22px', fontWeight: 800, color: '#16a34a', margin: '4px 0 0 0' }}>{fmtNum(tot.ves)}</p>
        </div>
        <div style={{ ...card, flex: '1 1 130px' }}>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>USDI</p>
          <p style={{ fontSize: '22px', fontWeight: 800, color: '#EA580C', margin: '4px 0 0 0' }}>{fmtNum(tot.usdi)}</p>
        </div>
        <div style={{ ...card, flex: '1 1 130px' }}>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>SATS</p>
          <p style={{ fontSize: '22px', fontWeight: 800, color: '#2563eb', margin: '4px 0 0 0' }}>{fmtInt(tot.sats)}</p>
        </div>
      </div>

      {loading && !data ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : orders.length === 0 ? (
        <div style={{ ...card, textAlign: 'center', color: '#9ca3af', padding: '32px' }}>
          Aún no hay órdenes BTC registradas. Aparecerán aquí cuando marques una remesa BTC como enviada.
        </div>
      ) : (
        <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                  {['Fecha', 'Orden', 'Usuario', 'USDI', 'Sats', 'Tasa', 'VES pagados', 'Beneficiario', 'Comp.'].map((h) => (
                    <th key={h} style={{ padding: '10px 12px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.entry_id} onClick={() => setDetalle(o)} style={{ borderTop: '1px solid #f1f2f6', cursor: 'pointer' }}>
                    <td style={{ padding: '10px 12px', color: '#6b7280', whiteSpace: 'nowrap' }}>{fmtFecha(o.enviado_en || o.created_at)}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600, color: '#111827', whiteSpace: 'nowrap' }}>{o.display_id ? `#${o.display_id}` : (o.remesa_id || '').slice(0, 8)}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 600, color: '#111827' }}>{o.user_name || '—'}</div>
                      <div style={{ fontSize: '11px', color: '#9ca3af' }}>{o.user_email}</div>
                    </td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', fontWeight: 700, color: '#EA580C' }}>{fmtNum(o.usdi_cliente)}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: '#2563eb' }}>{fmtInt(o.sats)}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: '#6b7280' }}>{fmtNum(o.tasa_usdi_ves)}</td>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', fontWeight: 700, color: '#16a34a' }}>{fmtNum(o.ves_recibe)} Bs</td>
                    <td style={{ padding: '10px 12px' }}>{o.beneficiario?.full_name || '—'}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                      {o.comprobante ? <FileCheck size={16} color="#16a34a" /> : <FileX size={16} color="#d1d5db" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detalle && (
        <div onClick={() => setDetalle(null)} style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(17,24,39,0.55)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width: '100%', maxWidth: '560px', maxHeight: '85vh', overflowY: 'auto',
            backgroundColor: '#fff', borderRadius: '16px', padding: '20px', position: 'relative',
          }}>
            <button onClick={() => setDetalle(null)} style={{ position: 'absolute', top: '14px', right: '14px', border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af' }}><X size={20} /></button>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#111827', margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bitcoin size={18} color="#EA580C" /> Orden {detalle.display_id ? `#${detalle.display_id}` : detalle.remesa_id}
            </h3>
            {[
              ['Usuario', `${detalle.user_name || ''} (${detalle.user_email || ''})`],
              ['Cliente pagó', `${fmtNum(detalle.usdi_cliente)} USDI`],
              ['Sats enviados', fmtInt(detalle.sats)],
              ['BTC', detalle.btc_pagar],
              ['Precio BTC usado', detalle.precio_btc_usado ? `$${fmtNum(detalle.precio_btc_usado)}` : '—'],
              ['Precio con margen', detalle.precio_con_margen ? `$${fmtNum(detalle.precio_con_margen)}` : '—'],
              ['Tasa USDI → VES', fmtNum(detalle.tasa_usdi_ves)],
              ['Beneficiario recibe', `${fmtNum(detalle.ves_recibe)} Bs`],
              ['Beneficiario', detalle.beneficiario?.full_name],
              ['Cédula', detalle.beneficiario?.cedula],
              ['Banco', detalle.beneficiario?.bank],
              ['Cuenta', detalle.beneficiario?.account_number],
              ['Teléfono', detalle.beneficiario?.phone],
              ['Comprobante', detalle.comprobante ? 'Sí' : 'No'],
              ['Operador', detalle.operador_nombre || detalle.operador_id || '—'],
              ['Vía', detalle.completado_via],
              ['Enviado', fmtFecha(detalle.enviado_en)],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '8px 0', borderTop: '1px solid #f3f4f6', fontSize: '13.5px' }}>
                <span style={{ color: '#6b7280' }}>{k}</span>
                <span style={{ color: '#111827', fontWeight: 600, textAlign: 'right' }}>{(v === null || v === undefined || v === '') ? '—' : v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
