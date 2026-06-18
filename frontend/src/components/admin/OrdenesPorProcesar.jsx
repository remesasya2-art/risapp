import { useState, useEffect, useRef, Fragment } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { RefreshCw, Paperclip, CheckCircle, XCircle, Clock, LayoutGrid, Table as TableIcon } from 'lucide-react';

// Colores por flujo
const FLUJO_STYLE = {
  ris_ves: { bg: '#EEF2FF', fg: '#4F46E5' },
  btc_ves: { bg: '#FFF7ED', fg: '#EA580C' },
  ves_ris: { bg: '#ECFDF5', fg: '#059669' },
  ris_reais: { bg: '#FEF9C3', fg: '#CA8A04' },
};

const FILTROS = [
  { key: 'all', label: 'Todas' },
  { key: 'btc_ves', label: 'BTC→VES' },
  { key: 'ris_ves', label: 'RIS→VES' },
  { key: 'ves_ris', label: 'VES→RIS' },
  { key: 'ris_reais', label: 'RIS→Reais' },
];

function formatDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return '';
  return dt.toLocaleDateString('es-VE', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function beneficiarioLinea(b) {
  if (!b || !(b.nombre || b.documento || b.banco || b.pix_key)) return '';
  const partes = [];
  if (b.tipo_pago === 'pix_br') partes.push('🇧🇷 PIX');
  else if (b.tipo_pago === 'pago_movil') partes.push('📱 P.Móvil');
  if (b.documento) partes.push(b.documento);
  if (b.pix_key) partes.push('PIX ' + b.pix_key);
  if (b.banco) partes.push(b.banco);
  if (b.telefono) partes.push(b.telefono);
  if (b.cuenta) partes.push(b.cuenta);
  return partes.join(' · ');
}

export default function OrdenesPorProcesar() {
  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [comprobantes, setComprobantes] = useState({});
  const [busy, setBusy] = useState(null);
  const [vista, setVista] = useState('tarjetas');   // 'tarjetas' | 'tabla'
  const [filtro, setFiltro] = useState('all');
  const [nuevosIds, setNuevosIds] = useState([]);
  const [verImg, setVerImg] = useState(null);
  const prevIdsRef = useRef(null);

  const idDe = (o) => `${o.flujo}-${o.orden_id}`;

  const cargar = async (opts = {}) => {
    if (!opts.silent) setLoading(true);
    try {
      const res = await api.get('/admin/ordenes/pendientes');
      const lista = res.data?.ordenes || [];
      const currentIds = lista.map(idDe);

      if (prevIdsRef.current === null) {
        setNuevosIds([]); // primer cargado: nada es nuevo
      } else if (opts.fromAction) {
        setNuevosIds([]); // tocar/procesar limpia la marca
      } else {
        const prev = new Set(prevIdsRef.current);
        const nuevos = currentIds.filter((id) => !prev.has(id));
        if (nuevos.length > 0) setNuevosIds(nuevos); // se reubica al nuevo lote
        // si no hay nuevos, se mantiene la marca anterior
      }
      prevIdsRef.current = currentIds;
      setOrdenes(lista);
    } catch (e) {
      if (!opts.silent) toast.error('No se pudieron cargar las órdenes');
    } finally {
      if (!opts.silent) setLoading(false);
    }
  };

  useEffect(() => {
    cargar();
    const t = setInterval(() => cargar({ silent: true }), 15000);
    return () => clearInterval(t);
  }, []);

  const onSelectComprobante = (ordenId, file) => {
    if (!file) return;
    setNuevosIds([]); // tocar una orden limpia la separación de "nuevas"
    const reader = new FileReader();
    reader.onload = () => setComprobantes((prev) => ({ ...prev, [ordenId]: reader.result }));
    reader.readAsDataURL(file);
  };

  const procesarPago = async (orden) => {
    const comprobante = comprobantes[orden.orden_id];
    if (!comprobante) { toast.error('Adjunta el comprobante (JPG)'); return; }
    if (!window.confirm('¿Confirmas que ya pagaste a este beneficiario?')) return;
    try {
      setBusy(orden.orden_id);
      if (orden.flujo === 'btc_ves') {
        await api.post('/admin/btc/marcar-enviado', { remesa_id: orden.orden_id, comprobante });
      } else {
        await api.post('/admin/withdrawals/process', {
          transaction_id: orden.orden_id, action: 'approve', proof_images: [comprobante],
        });
      }
      toast.success('Orden procesada');
      setComprobantes((prev) => { const c = { ...prev }; delete c[orden.orden_id]; return c; });
      await cargar({ fromAction: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al procesar la orden');
    } finally {
      setBusy(null);
    }
  };

  const resolverRecarga = async (orden, accion) => {
    if (accion === 'reject') {
      const motivo = window.prompt('Motivo del rechazo (opcional):', '');
      if (motivo === null) return;
      try {
        setBusy(orden.orden_id);
        await api.post(`/admin/recharges/ves/process/${orden.orden_id}`, { action: 'reject', rejection_reason: motivo });
        toast.success('Recarga rechazada');
        await cargar({ fromAction: true });
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
      await cargar({ fromAction: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error al aprobar');
    } finally { setBusy(null); }
  };

  const visibles = filtro === 'all' ? ordenes : ordenes.filter((o) => o.flujo === filtro);
  const nuevosSet = new Set(nuevosIds);
  const firstNewIdx = visibles.findIndex((o) => nuevosSet.has(idDe(o)));

  // ---- estilos reutilizables ----
  const btnGhost = (active) => ({
    display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '7px 12px',
    borderRadius: '8px', border: '1px solid ' + (active ? '#6366f1' : '#e5e7eb'),
    backgroundColor: active ? '#6366f1' : '#fff', color: active ? '#fff' : '#374151',
    fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  });
  const badge = (st) => ({
    padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 700,
    backgroundColor: st.bg, color: st.fg, whiteSpace: 'nowrap',
  });
  const btnPrimary = (on) => ({
    padding: '6px 12px', borderRadius: '8px', border: 'none', fontWeight: 700, fontSize: '13px',
    backgroundColor: '#6366f1', color: '#fff', cursor: on ? 'pointer' : 'not-allowed', opacity: on ? 1 : 0.5,
  });
  const chip = {
    display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 10px', borderRadius: '8px',
    border: '1px solid #e5e7eb', fontSize: '12.5px', fontWeight: 600, color: '#374151', cursor: 'pointer',
  };

  const Separador = () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: '4px 0' }}>
      <div style={{ flex: 1, height: '1px', background: '#d1d5db' }} />
      <span style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>nuevas órdenes</span>
      <div style={{ flex: 1, height: '1px', background: '#d1d5db' }} />
    </div>
  );

  // ---- acción compacta (compartida por tarjeta y tabla) ----
  const Accion = ({ o }) => {
    if (o.accion === 'aprobar') {
      return (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {o.comprobante_usuario && (
            <img src={o.comprobante_usuario} alt="comp" onClick={() => setVerImg(o.comprobante_usuario)}
              style={{ width: '38px', height: '38px', borderRadius: '6px', objectFit: 'cover', cursor: 'pointer', border: '1px solid #e5e7eb' }} />
          )}
          <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'approve')}
            style={{ padding: '6px 12px', borderRadius: '8px', border: 'none', backgroundColor: '#10B981', color: '#fff', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}>
            Aprobar
          </button>
          <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'reject')}
            style={{ padding: '6px 12px', borderRadius: '8px', backgroundColor: '#fff', color: '#dc2626', border: '1.5px solid #dc2626', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}>
            Rechazar
          </button>
        </div>
      );
    }

    const tiene = !!comprobantes[o.orden_id];
    return (
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={chip}>
          <Paperclip size={14} /> {tiene ? 'JPG ✓' : 'Adjuntar'}
          <input type="file" accept=".jpg,.jpeg,image/jpeg" style={{ display: 'none' }}
            onChange={(e) => onSelectComprobante(o.orden_id, e.target.files?.[0])} />
        </label>
        {tiene && (
          <img src={comprobantes[o.orden_id]} alt="comp" onClick={() => setVerImg(comprobantes[o.orden_id])}
            style={{ width: '38px', height: '38px', borderRadius: '6px', objectFit: 'cover', cursor: 'pointer', border: '1px solid #e5e7eb' }} />
        )}
        <button disabled={busy === o.orden_id || !tiene} onClick={() => procesarPago(o)} style={btnPrimary(tiene && busy !== o.orden_id)}>
          {busy === o.orden_id ? '…' : 'Procesar'}
        </button>
      </div>
    );
  };

  const Tarjeta = ({ o }) => {
    const st = FLUJO_STYLE[o.flujo] || { bg: '#F3F4F6', fg: '#374151' };
    const bl = beneficiarioLinea(o.beneficiario);
    return (
      <div style={{ backgroundColor: '#fff', borderRadius: '10px', padding: '10px 12px', border: '1px solid #eef0f4' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flexWrap: 'wrap' }}>
            <span style={badge(st)}>{o.flujo_label}</span>
            <span style={{ fontSize: '13px', color: '#374151' }}>
              {fmt(o.origen?.valor)} {o.origen?.unidad} <span style={{ color: '#9ca3af' }}>→</span>{' '}
              <b style={{ color: st.fg }}>{fmt(o.destino?.valor)} {o.destino?.unidad}</b>
            </span>
            {o.display_id && <span style={{ fontSize: '11px', color: '#9ca3af' }}>#{o.display_id}</span>}
          </div>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
            <Clock size={12} /> {formatDate(o.created_at)}
          </span>
        </div>
        <div style={{ fontSize: '12.5px', color: '#6b7280', margin: '5px 0 8px 0' }}>
          {bl ? bl : `Usuario: ${o.user_name}`}
        </div>
        <Accion o={o} />
      </div>
    );
  };

  return (
    <div>
      {/* Encabezado + controles */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#111827', margin: 0 }}>Órdenes por procesar</h2>
          <p style={{ fontSize: '12.5px', color: '#6b7280', margin: '3px 0 0 0' }}>
            {visibles.length} mostrada{visibles.length === 1 ? '' : 's'} · se actualiza cada 15s
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ display: 'inline-flex', borderRadius: '8px', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
            <button onClick={() => setVista('tarjetas')} title="Tarjetas"
              style={{ ...btnGhost(vista === 'tarjetas'), border: 'none', borderRadius: 0 }}>
              <LayoutGrid size={15} /> Tarjetas
            </button>
            <button onClick={() => setVista('tabla')} title="Tabla"
              style={{ ...btnGhost(vista === 'tabla'), border: 'none', borderRadius: 0 }}>
              <TableIcon size={15} /> Tabla
            </button>
          </div>
          <button onClick={() => cargar()} style={btnGhost(false)}><RefreshCw size={15} /> Actualizar</button>
        </div>
      </div>

      {/* Filtros por flujo */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
        {FILTROS.map((f) => (
          <button key={f.key} onClick={() => setFiltro(f.key)} style={btnGhost(filtro === f.key)}>{f.label}</button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: '#6b7280' }}>Cargando órdenes…</p>
      ) : visibles.length === 0 ? (
        <div style={{ padding: '36px', textAlign: 'center', backgroundColor: '#F9FAFB', borderRadius: '14px', border: '1px dashed #e5e7eb' }}>
          <CheckCircle size={30} color="#10B981" style={{ marginBottom: '6px' }} />
          <p style={{ color: '#374151', fontWeight: 600, margin: 0 }}>No hay órdenes en esta vista</p>
        </div>
      ) : vista === 'tarjetas' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {visibles.map((o, i) => (
            <Fragment key={idDe(o)}>
              {i === firstNewIdx && firstNewIdx > -1 && <Separador />}
              <Tarjeta o={o} />
            </Fragment>
          ))}
        </div>
      ) : (
        <div style={{ overflowX: 'auto', border: '1px solid #eef0f4', borderRadius: '12px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F9FAFB', textAlign: 'left' }}>
                {['Flujo', 'Monto', 'Usuario', 'Beneficiario', 'Fecha', 'Acción'].map((h) => (
                  <th key={h} style={{ padding: '8px 10px', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibles.map((o, i) => {
                const st = FLUJO_STYLE[o.flujo] || { bg: '#F3F4F6', fg: '#374151' };
                const bl = beneficiarioLinea(o.beneficiario);
                return (
                  <Fragment key={idDe(o)}>
                    {i === firstNewIdx && firstNewIdx > -1 && (
                      <tr><td colSpan={6} style={{ padding: 0 }}><Separador /></td></tr>
                    )}
                    <tr style={{ borderTop: '1px solid #f1f2f6' }}>
                      <td style={{ padding: '8px 10px' }}><span style={badge(st)}>{o.flujo_label}</span></td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                        {fmt(o.origen?.valor)} {o.origen?.unidad} → <b style={{ color: st.fg }}>{fmt(o.destino?.valor)} {o.destino?.unidad}</b>
                      </td>
                      <td style={{ padding: '8px 10px' }}>{o.user_name}</td>
                      <td style={{ padding: '8px 10px', color: '#6b7280', maxWidth: '260px' }}>{bl || '—'}</td>
                      <td style={{ padding: '8px 10px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{formatDate(o.created_at)}</td>
                      <td style={{ padding: '8px 10px' }}><Accion o={o} /></td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Visor de comprobante */}
      {verImg && (
        <div onClick={() => setVerImg(null)} style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px',
        }}>
          <img src={verImg} alt="comprobante" style={{ maxWidth: '90%', maxHeight: '90%', borderRadius: '10px' }} />
        </div>
      )}
    </div>
  );
}
