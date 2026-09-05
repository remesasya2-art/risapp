import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar } from '../flujo/confirmar.js';
import { fmt } from '../../utils/format';
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';

// Bandeja de envíos cripto cuyo pago llegó incompleto y el sistema no pudo
// resolver solo. Dos salidas posibles: aprobar igual, o cancelar devolviendo
// como saldo lo que sí llegó.

const C = {
  border: '#e5e7eb',
  bgSubtle: '#f9fafb',
  ink: '#111827',
  soft: '#6b7280',
  faint: '#9ca3af',
  green: '#047857',
  greenBg: '#ecfdf5',
  amber: '#b45309',
  amberBg: '#fffbeb',
  red: '#dc2626',
  redBg: '#fef2f2',
};

function formatDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return '';
  return dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function beneficiarioLinea(b) {
  if (!b) return '';
  return [b.documento, b.banco, b.telefono, b.cuenta].filter(Boolean).join(' · ');
}

function ratioColor(ratio) {
  if (ratio == null) return C.soft;
  if (ratio >= 0.95) return C.green;
  if (ratio >= 0.8) return C.amber;
  return C.red;
}

export default function DiferenciasPago() {
  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  // La busqueda se mantiene separada de los setState: el efecto de montaje solo
  // dispara la promesa y aplica el resultado en el callback, nunca sincronamente.
  const traer = () => api.get('/admin/ordenes/revision-pago').then(({ data }) => data);

  const aplicar = (data) => {
    setOrdenes(data?.ordenes || []);
    if (data?.vencidas_ahora > 0) {
      toast(`${data.vencidas_ahora} orden(es) con plazo vencido pasaron a revisión.`, { icon: '⏱️' });
    }
  };

  const avisarFallo = (error) => {
    toast.error(error.response?.data?.detail || 'No se pudieron cargar las diferencias de pago');
  };

  useEffect(() => {
    let cancelled = false;
    traer()
      .then((data) => { if (!cancelled) aplicar(data); })
      .catch((error) => { if (!cancelled) avisarFallo(error); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Recarga manual (boton Actualizar y despues de cada accion).
  const recargar = () => {
    setLoading(true);
    return traer().then(aplicar).catch(avisarFallo).finally(() => setLoading(false));
  };

  const aprobar = async (orden) => {
    if (!await confirmar({
      titulo: `¿Aprobar la orden ${orden.display_id || orden.orden_id} con la diferencia a favor del usuario?`,
      detalle: `Pedido: ${orden.pay_amount} ${orden.moneda} · Recibido: `
        + `${orden.recibido_total} ${orden.moneda}. Pasa a la cola de pagos como `
        + 'cualquier orden pagada.',
      accion: 'Aprobar',
    })) return;
    setBusyId(orden.orden_id);
    try {
      const { data } = await api.post(`/admin/ordenes/${orden.orden_id}/aprobar-con-diferencia`);
      toast.success(data?.message || 'Orden aprobada');
      recargar();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'No se pudo aprobar la orden');
    } finally {
      setBusyId(null);
    }
  };

  const rechazar = async (orden) => {
    if (!await confirmar({
      titulo: `¿Cancelar la orden ${orden.display_id || orden.orden_id}?`,
      detalle: `Se le devuelven ${orden.recibido_total} ${orden.moneda} como saldo `
        + 'al usuario. Desde el panel esto no se puede deshacer.',
      accion: 'Cancelar y devolver',
      cancelar: 'Dejarla como está',
      tono: 'peligro',
    })) return;
    setBusyId(orden.orden_id);
    try {
      const { data } = await api.post(`/admin/ordenes/${orden.orden_id}/rechazar-y-reembolsar-saldo`);
      toast.success(data?.message || 'Orden cancelada y saldo devuelto');
      recargar();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'No se pudo cancelar la orden');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: C.ink, margin: 0 }}>Diferencias de pago</h2>
          <p style={{ fontSize: 13, color: C.soft, margin: '4px 0 0 0' }}>
            Envíos cripto cuyo pago llegó incompleto. {ordenes.length} en revisión.
          </p>
        </div>
        <button
          onClick={recargar}
          disabled={loading}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px',
            borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: '#fff',
            color: C.soft, fontWeight: 600, fontSize: 13, cursor: loading ? 'default' : 'pointer',
          }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} /> Actualizar
        </button>
      </div>

      {loading ? (
        <p style={{ fontSize: 14, color: C.soft }}>Cargando...</p>
      ) : ordenes.length === 0 ? (
        <div style={{
          padding: '32px 20px', textAlign: 'center', borderRadius: 12,
          border: `1px dashed ${C.border}`, backgroundColor: C.bgSubtle, color: C.soft, fontSize: 14,
        }}>
          <CheckCircle size={22} color={C.green} style={{ marginBottom: 8 }} />
          <div>No hay envíos con pago incompleto pendientes de revisión.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {ordenes.map((o) => {
            const ratio = o.paid_ratio != null ? Number(o.paid_ratio) : null;
            const busy = busyId === o.orden_id;
            return (
              <div key={o.orden_id} style={{ border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, backgroundColor: '#fff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>
                      {o.display_id || o.orden_id}
                      {o.topup_expired && (
                        <span style={{
                          marginLeft: 8, display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: '2px 8px', borderRadius: 999, backgroundColor: C.amberBg,
                          color: C.amber, fontSize: 11, fontWeight: 600,
                        }}>
                          <Clock size={11} /> Plazo vencido
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12.5, color: C.soft, marginTop: 2 }}>
                      {o.user_name} · {o.user_email} · {formatDate(o.created_at)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: ratioColor(ratio) }}>
                      {ratio != null ? `${(ratio * 100).toFixed(1)}%` : '—'}
                    </div>
                    <div style={{ fontSize: 11, color: C.faint }}>del monto pedido</div>
                  </div>
                </div>

                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10,
                  padding: 12, borderRadius: 10, backgroundColor: C.bgSubtle, marginBottom: 10,
                }}>
                  <Dato label="Pedido" valor={`${o.pay_amount} ${o.moneda}`} />
                  <Dato label="Pago original" valor={`${o.actually_paid} ${o.moneda}`} />
                  <Dato label="Diferencia recibida" valor={`${o.topup_actually_paid} ${o.moneda}`} />
                  <Dato label="Falta" valor={`${o.faltante} ${o.moneda}`} destacado />
                  <Dato label="Red" valor={o.red || '—'} />
                  <Dato label="Destino" valor={`${fmt(o.amount_output || 0)} ${o.currency_output || 'VES'}`} />
                </div>

                <div style={{ fontSize: 13, color: C.ink, marginBottom: 12 }}>
                  <strong>{o.beneficiario?.nombre || '—'}</strong>
                  <span style={{ color: C.soft }}> · {beneficiarioLinea(o.beneficiario)}</span>
                </div>

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button
                    onClick={() => aprobar(o)}
                    disabled={busy}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 16px',
                      borderRadius: 10, border: 'none', backgroundColor: C.green, color: '#fff',
                      fontWeight: 600, fontSize: 13, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1,
                    }}
                  >
                    <CheckCircle size={15} /> Aprobar con diferencia
                  </button>
                  <button
                    onClick={() => rechazar(o)}
                    disabled={busy}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 16px',
                      borderRadius: 10, border: `1px solid ${C.red}`, backgroundColor: C.redBg, color: C.red,
                      fontWeight: 600, fontSize: 13, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.6 : 1,
                    }}
                  >
                    <XCircle size={15} /> Rechazar y devolver saldo
                  </button>
                </div>

                {ratio != null && ratio < 0.8 && (
                  <div style={{
                    marginTop: 10, display: 'flex', alignItems: 'center', gap: 6,
                    fontSize: 12, color: C.amber,
                  }}>
                    <AlertTriangle size={13} /> Llegó menos del 80% del monto: revisá antes de aprobar.
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

function Dato({ label, valor, destacado }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: C.faint, marginBottom: 2 }}>{label}</div>
      <div style={{
        fontSize: 13.5, fontWeight: destacado ? 700 : 600,
        color: destacado ? C.red : C.ink, fontVariantNumeric: 'tabular-nums',
      }}>
        {valor}
      </div>
    </div>
  );
}
