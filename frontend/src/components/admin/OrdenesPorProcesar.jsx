import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { RefreshCw, Paperclip, CheckCircle, XCircle, Clock } from 'lucide-react';

// Colores por flujo
const FLUJO_STYLE = {
  ris_ves: { bg: '#EEF2FF', fg: '#4F46E5' },
  btc_ves: { bg: '#FFF7ED', fg: '#EA580C' },
  ves_ris: { bg: '#ECFDF5', fg: '#059669' },
};

function formatDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return '';
  return dt.toLocaleDateString('es-VE', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function OrdenesPorProcesar() {
  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [comprobantes, setComprobantes] = useState({}); // orden_id -> base64
  const [busy, setBusy] = useState(null); // orden_id en proceso

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/ordenes/pendientes');
      setOrdenes(res.data?.ordenes || []);
    } catch (e) {
      toast.error('No se pudieron cargar las órdenes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const onSelectComprobante = (ordenId, file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setComprobantes((prev) => ({ ...prev, [ordenId]: reader.result }));
    reader.readAsDataURL(file);
  };

  const limpiarComprobante = (ordenId) => {
    setComprobantes((prev) => { const c = { ...prev }; delete c[ordenId]; return c; });
  };

  // Procesar una orden que el admin PAGA (ris_ves, btc_ves) con comprobante
  const procesarPago = async (orden) => {
    const comprobante = comprobantes[orden.orden_id];
    if (!comprobante) { toast.error('Adjunta el comprobante de pago (JPG)'); return; }
    if (!window.confirm('¿Confirmas que ya realizaste el pago a este beneficiario?')) return;
    try {
      setBusy(orden.orden_id);
      if (orden.flujo === 'btc_ves') {
        await api.post('/admin/btc/marcar-enviado', { remesa_id: orden.orden_id, comprobante });
      } else {
        await api.post('/admin/withdrawals/process', {
          transaction_id: orden.orden_id,
          action: 'approve',
          proof_images: [comprobante],
        });
      }
      toast.success('Orden procesada');
      limpiarComprobante(orden.orden_id);
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al procesar la orden');
    } finally {
      setBusy(null);
    }
  };

  // Aprobar/rechazar una recarga (ves_ris): el admin revisa el comprobante del usuario
  const resolverRecarga = async (orden, accion) => {
    if (accion === 'reject') {
      const motivo = window.prompt('Motivo del rechazo (opcional):', '');
      if (motivo === null) return;
      try {
        setBusy(orden.orden_id);
        await api.post(`/admin/recharges/ves/process/${orden.orden_id}`, { action: 'reject', rejection_reason: motivo });
        toast.success('Recarga rechazada');
        await cargar();
      } catch (e) {
        toast.error(e?.response?.data?.detail || 'Error al rechazar');
      } finally { setBusy(null); }
      return;
    }
    if (!window.confirm('¿Aprobar esta recarga y acreditar el saldo al usuario?')) return;
    try {
      setBusy(orden.orden_id);
      await api.post(`/admin/recharges/ves/process/${orden.orden_id}`, { action: 'approve' });
      toast.success('Recarga aprobada');
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al aprobar');
    } finally { setBusy(null); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0 }}>Órdenes por procesar</h2>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>
            Todas las órdenes pendientes de pago en un solo lugar. {ordenes.length} pendiente{ordenes.length === 1 ? '' : 's'}.
          </p>
        </div>
        <button onClick={cargar} style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '8px 14px',
          borderRadius: '10px', border: '1px solid #e5e7eb', backgroundColor: '#fff',
          color: '#374151', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
        }}>
          <RefreshCw size={16} /> Actualizar
        </button>
      </div>

      {loading ? (
        <p style={{ color: '#6b7280' }}>Cargando órdenes…</p>
      ) : ordenes.length === 0 ? (
        <div style={{
          padding: '40px', textAlign: 'center', backgroundColor: '#F9FAFB',
          borderRadius: '14px', border: '1px dashed #e5e7eb',
        }}>
          <CheckCircle size={32} color="#10B981" style={{ marginBottom: '8px' }} />
          <p style={{ color: '#374151', fontWeight: 600, margin: 0 }}>No hay órdenes pendientes</p>
          <p style={{ color: '#9ca3af', fontSize: '13px', margin: '4px 0 0 0' }}>Cuando llegue una nueva, aparecerá aquí.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {ordenes.map((o) => {
            const st = FLUJO_STYLE[o.flujo] || { bg: '#F3F4F6', fg: '#374151' };
            const b = o.beneficiario || {};
            return (
              <div key={`${o.flujo}-${o.orden_id}`} style={{
                backgroundColor: '#fff', borderRadius: '14px', padding: '16px',
                border: '1px solid #eef0f4', boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
              }}>
                {/* Encabezado */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{
                      padding: '4px 10px', borderRadius: '8px', fontSize: '12px', fontWeight: 700,
                      backgroundColor: st.bg, color: st.fg,
                    }}>{o.flujo_label}</span>
                    {o.display_id && (
                      <span style={{ fontSize: '12px', color: '#9ca3af' }}>#{o.display_id}</span>
                    )}
                  </div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: '#9ca3af' }}>
                    <Clock size={13} /> {formatDate(o.created_at)}
                  </span>
                </div>

                {/* Montos */}
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px' }}>
                  <span style={{ fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                    {fmt(o.origen?.valor)} {o.origen?.unidad}
                  </span>
                  <span style={{ color: '#9ca3af' }}>→</span>
                  <span style={{ fontSize: '15px', fontWeight: 700, color: st.fg }}>
                    {fmt(o.destino?.valor)} {o.destino?.unidad}
                  </span>
                </div>

                {/* Usuario */}
                <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 8px 0' }}>
                  Usuario: <strong style={{ color: '#374151' }}>{o.user_name}</strong>
                  {o.user_email ? ` · ${o.user_email}` : ''}
                </p>

                {/* Beneficiario (solo pagos) */}
                {b && (b.nombre || b.documento || b.banco) && (
                  <div style={{
                    padding: '10px 12px', backgroundColor: '#FAFAFC', borderRadius: '10px',
                    border: '1px solid #EFEFF5', fontSize: '13px', color: '#374151', marginBottom: '10px',
                  }}>
                    <div><strong>{b.nombre || '—'}</strong>{b.documento ? ` · ${b.documento}` : ''}</div>
                    <div style={{ color: '#6b7280', marginTop: '2px' }}>
                      {b.tipo_pago === 'pago_movil' ? '📱 Pago Móvil' : '🏦 Transferencia'}
                      {b.banco ? ` · ${b.banco}` : ''}
                      {b.telefono ? ` · ${b.telefono}` : ''}
                      {b.cuenta ? ` · ${b.cuenta}` : ''}
                    </div>
                  </div>
                )}

                {/* Acción según el tipo de orden */}
                {o.accion === 'aprobar' ? (
                  <div>
                    {o.comprobante_usuario && (
                      <img src={o.comprobante_usuario} alt="comprobante usuario"
                        style={{ maxWidth: '200px', borderRadius: '10px', border: '1px solid #e5e7eb', marginBottom: '10px', display: 'block' }} />
                    )}
                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'approve')} style={{
                        flex: 1, padding: '10px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                        backgroundColor: '#10B981', color: '#fff', fontWeight: 700,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                      }}>
                        <CheckCircle size={16} /> Aprobar
                      </button>
                      <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'reject')} style={{
                        padding: '10px 14px', borderRadius: '10px', cursor: 'pointer',
                        backgroundColor: '#fff', color: '#dc2626', border: '1.5px solid #dc2626', fontWeight: 700,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                      }}>
                        <XCircle size={16} /> Rechazar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <label style={{
                      display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '13px',
                      fontWeight: 600, color: '#374151', cursor: 'pointer', marginBottom: '8px',
                    }}>
                      <Paperclip size={15} />
                      {comprobantes[o.orden_id] ? 'Comprobante adjunto ✓' : 'Adjuntar comprobante (JPG)'}
                      <input type="file" accept=".jpg,.jpeg,image/jpeg" style={{ display: 'none' }}
                        onChange={(e) => onSelectComprobante(o.orden_id, e.target.files?.[0])} />
                    </label>
                    {comprobantes[o.orden_id] && (
                      <img src={comprobantes[o.orden_id]} alt="comprobante"
                        style={{ maxWidth: '180px', borderRadius: '10px', border: '1px solid #e5e7eb', marginBottom: '10px', display: 'block' }} />
                    )}
                    <button
                      disabled={busy === o.orden_id || !comprobantes[o.orden_id]}
                      onClick={() => procesarPago(o)}
                      style={{
                        width: '100%', padding: '11px', borderRadius: '10px', border: 'none',
                        backgroundColor: '#6366f1', color: '#fff', fontWeight: 700,
                        cursor: comprobantes[o.orden_id] ? 'pointer' : 'not-allowed',
                        opacity: comprobantes[o.orden_id] ? 1 : 0.5,
                      }}>
                      {busy === o.orden_id ? 'Procesando…' : 'Procesar orden'}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

