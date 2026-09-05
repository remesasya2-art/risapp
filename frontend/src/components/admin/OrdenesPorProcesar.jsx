import { useState, useEffect, useRef, Fragment } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar, pedirTexto } from '../flujo/confirmar.js';
import { fmt } from '../../utils/format';
import { rutaDeArchivo } from '../../utils/urlDeArchivo';
import { useAuth } from '../../contexts/AuthContext';
import { RefreshCw, Paperclip, CheckCircle, XCircle, Clock, LayoutGrid, Table as TableIcon, UserCheck, UserX, Lock } from 'lucide-react';

// ---- Paleta profesional / corporativa (plana, sin sombras decorativas) ----
const C = {
  border: '#e5e7eb',
  borderLight: '#eef0f3',
  bgSubtle: '#f9fafb',
  ink: '#111827',
  soft: '#6b7280',
  faint: '#9ca3af',
  primary: '#4338ca',
  primaryBg: '#eef2ff',
  green: '#047857',
  greenBg: '#ecfdf5',
  amber: '#b45309',
  amberBg: '#fffbeb',
  red: '#dc2626',
  redBg: '#fef2f2',
};

// Colores por flujo (identidad visual sobria, no saturada)
const FLUJO_STYLE = {
  ris_ves: { bg: '#EEF2FF', fg: '#4338CA' },
  btc_ves: { bg: '#FFF7ED', fg: '#C2410C' },
  ves_ris: { bg: '#ECFDF5', fg: '#047857' },
  ris_reais: { bg: '#FEFCE8', fg: '#A16207' },
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
  const { user } = useAuth();
  const miId = user?.user_id;

  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [comprobantes, setComprobantes] = useState({});
  const [busy, setBusy] = useState(null);
  const [vista, setVista] = useState('tarjetas');  // 'tarjetas' | 'tabla'
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
    setNuevosIds([]);
    const reader = new FileReader();
    reader.onload = () => setComprobantes((prev) => ({ ...prev, [ordenId]: reader.result }));
    reader.readAsDataURL(file);
  };

  // ---- Asignación (reclamar / liberar orden) ----
  const tomarOrden = async (o) => {
    try {
      setBusy(o.orden_id);
      const res = await api.post('/admin/ordenes/tomar', { orden_id: o.orden_id, flujo: o.flujo });
      if (res.data?.success) {
        toast.success('Orden asignada a ti');
      } else {
        toast.error(`Ya la tomó ${res.data?.assigned_to_name || 'otro operador'}`);
      }
      await cargar({ fromAction: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo tomar la orden');
    } finally {
      setBusy(null);
    }
  };

  const liberarOrden = async (o) => {
    try {
      setBusy(o.orden_id);
      await api.post('/admin/ordenes/liberar', { orden_id: o.orden_id, flujo: o.flujo });
      toast.success('Orden liberada');
      await cargar({ fromAction: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo liberar la orden');
    } finally {
      setBusy(null);
    }
  };

  /**
   * El 409 de «otro operador está en esta orden», que aparece igual en los tres
   * caminos. Devuelve si hay que reintentar pisando el candado.
   *
   * El texto sale del servidor: se muestra como texto, nunca como marcado.
   */
  const pisarElCandado = async (e) => confirmar({
    titulo: 'Otro operador está trabajando en esta orden',
    detalle: `${e?.response?.data?.detail || 'Está tomada por otra sesión.'} Si seguís, pisás lo que esté haciendo.`,
    accion: 'Seguir igual',
    cancelar: 'Dejarla',
    tono: 'peligro',
  });

  // ---- Procesar pago (retiros RIS→VES/Reais y BTC→VES) ----
  const procesarPago = async (orden, force = false) => {
    const comprobante = comprobantes[orden.orden_id];
    if (!comprobante) { toast.error('Adjunta el comprobante (JPG)'); return; }
    if (!force && !await confirmar({
      titulo: '¿Ya le pagaste al beneficiario?',
      detalle: 'Al confirmar, la orden queda como pagada y el usuario recibe el aviso.',
      accion: 'Sí, ya pagué',
    })) return;
    try {
      setBusy(orden.orden_id);
      if (orden.flujo === 'btc_ves') {
        await api.post('/admin/btc/marcar-enviado', { remesa_id: orden.orden_id, comprobante, force });
      } else {
        await api.post('/admin/withdrawals/process', {
          transaction_id: orden.orden_id, action: 'approve', proof_images: [comprobante], force,
        });
      }
      toast.success('Orden procesada');
      setComprobantes((prev) => { const c = { ...prev }; delete c[orden.orden_id]; return c; });
      await cargar({ fromAction: true });
    } catch (e) {
      if (e?.response?.status === 409) {
        if (await pisarElCandado(e)) { await procesarPago(orden, true); }
        return;
      }
      toast.error(e?.response?.data?.detail || 'Error al procesar la orden');
    } finally {
      setBusy(null);
    }
  };

  // ---- Aprobar / rechazar recargas VES→RIS ----
  const resolverRecarga = async (orden, accion, force = false) => {
    if (accion === 'reject') {
      const motivo = await pedirTexto({
        titulo: '¿Rechazar esta recarga?',
        detalle: 'El usuario ve el motivo, y queda asentado en el libro de auditoría.',
        etiqueta: 'Motivo del rechazo',
        placeholder: 'Ej.: el comprobante no coincide con el monto',
        opcional: true,
        accion: 'Rechazar',
        tono: 'peligro',
      });
      if (motivo === null) return;
      try {
        setBusy(orden.orden_id);
        await api.post(`/admin/recharges/ves/process/${orden.orden_id}`, { action: 'reject', rejection_reason: motivo, force });
        toast.success('Recarga rechazada');
        await cargar({ fromAction: true });
      } catch (e) {
        if (e?.response?.status === 409) {
          if (await pisarElCandado(e)) { await resolverRecarga(orden, accion, true); }
          return;
        }
        toast.error(e?.response?.data?.detail || 'Error al rechazar');
      } finally { setBusy(null); }
      return;
    }
    if (!force && !await confirmar({
      titulo: '¿Aprobar esta recarga?',
      detalle: 'Se le acredita el saldo al usuario en el momento.',
      accion: 'Aprobar y acreditar',
    })) return;
    try {
      setBusy(orden.orden_id);
      await api.post(`/admin/recharges/ves/process/${orden.orden_id}`, { action: 'approve', force });
      toast.success('Recarga aprobada');
      await cargar({ fromAction: true });
    } catch (e) {
      if (e?.response?.status === 409) {
        if (await pisarElCandado(e)) { await resolverRecarga(orden, accion, true); }
        return;
      }
      toast.error(e?.response?.data?.detail || 'Error al aprobar');
    } finally { setBusy(null); }
  };

  const visibles = filtro === 'all' ? ordenes : ordenes.filter((o) => o.flujo === filtro);
  const nuevosSet = new Set(nuevosIds);
  const firstNewIdx = visibles.findIndex((o) => nuevosSet.has(idDe(o)));

  const btnGhost = (active) => ({
    display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '7px 12px',
    borderRadius: '7px', border: '1px solid ' + (active ? C.primary : C.border),
    backgroundColor: active ? C.primary : '#fff', color: active ? '#fff' : '#374151',
    fontWeight: 600, fontSize: '13px', cursor: 'pointer',
  });
  const badge = (st) => ({
    padding: '2px 8px', borderRadius: '5px', fontSize: '11px', fontWeight: 700,
    backgroundColor: st.bg, color: st.fg, whiteSpace: 'nowrap',
  });
  const btnPrimary = (on) => ({
    padding: '6px 12px', borderRadius: '7px', border: 'none', fontWeight: 700, fontSize: '13px',
    backgroundColor: C.primary, color: '#fff', cursor: on ? 'pointer' : 'not-allowed', opacity: on ? 1 : 0.45,
  });
  const chip = {
    display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 10px', borderRadius: '7px',
    border: '1px solid ' + C.border, fontSize: '12.5px', fontWeight: 600, color: '#374151', cursor: 'pointer',
  };

  const Separador = () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: '4px 0' }}>
      <div style={{ flex: 1, height: '1px', background: '#d1d5db' }} />
      <span style={{ fontSize: '11px', fontWeight: 600, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.5px' }}>nuevas órdenes</span>
      <div style={{ flex: 1, height: '1px', background: '#d1d5db' }} />
    </div>
  );

  const Asignacion = ({ o }) => {
    const asignadoA = o.assigned_to;
    const esMio = asignadoA && asignadoA === miId;

    if (!asignadoA) {
      return (
        <button
          onClick={() => tomarOrden(o)}
          disabled={busy === o.orden_id}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '5px 10px',
            borderRadius: '6px', border: '1px dashed ' + C.faint, backgroundColor: '#fff',
            color: C.soft, fontSize: '11.5px', fontWeight: 600, cursor: 'pointer',
          }}
          title="Reclamar esta orden para procesarla"
        >
          <UserCheck size={13} /> Tomar orden
        </button>
      );
    }

    if (esMio) {
      return (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '4px 9px',
            borderRadius: '6px', backgroundColor: C.primaryBg, color: C.primary,
            fontSize: '11.5px', fontWeight: 700,
          }}>
            <UserCheck size={13} /> En proceso — Tú
          </span>
          <button
            onClick={() => liberarOrden(o)}
            disabled={busy === o.orden_id}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 8px',
              borderRadius: '6px', border: '1px solid ' + C.border, backgroundColor: '#fff',
              color: C.soft, fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            }}
            title="Liberar esta orden"
          >
            <UserX size={12} /> Liberar
          </button>
        </div>
      );
    }

    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '4px 9px',
        borderRadius: '6px', backgroundColor: C.amberBg, color: C.amber,
        fontSize: '11.5px', fontWeight: 700,
      }} title="Puedes forzar la acción, pero se te avisará antes de continuar">
        <Lock size={12} /> En proceso — {o.assigned_to_name || 'otro operador'}
      </span>
    );
  };

  const Accion = ({ o }) => {
    if (o.accion === 'aprobar') {
      return (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {o.comprobante_usuario && (
            <img src={rutaDeArchivo(o.comprobante_usuario)} alt="comp" onClick={() => setVerImg(o.comprobante_usuario)}
              style={{ width: '36px', height: '36px', borderRadius: '6px', objectFit: 'cover', cursor: 'pointer', border: '1px solid ' + C.border }} />
          )}
          <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'approve')}
            style={{ padding: '6px 12px', borderRadius: '7px', border: 'none', backgroundColor: C.green, color: '#fff', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}>
            Aprobar
          </button>
          <button disabled={busy === o.orden_id} onClick={() => resolverRecarga(o, 'reject')}
            style={{ padding: '6px 12px', borderRadius: '7px', backgroundColor: '#fff', color: C.red, border: '1.5px solid ' + C.red, fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}>
            Rechazar
          </button>
        </div>
      );
    }

    const tiene = !!comprobantes[o.orden_id];
    return (
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={chip}>
          <Paperclip size={13} /> {tiene ? 'JPG ✓' : 'Adjuntar comprobante'}
          <input type="file" accept=".jpg,.jpeg,image/jpeg" style={{ display: 'none' }}
            onChange={(e) => onSelectComprobante(o.orden_id, e.target.files?.[0])} />
        </label>
        {tiene && (
          <img src={rutaDeArchivo(comprobantes[o.orden_id])} alt="comp" onClick={() => setVerImg(comprobantes[o.orden_id])}
            style={{ width: '36px', height: '36px', borderRadius: '6px', objectFit: 'cover', cursor: 'pointer', border: '1px solid ' + C.border }} />
        )}
        <button disabled={busy === o.orden_id || !tiene} onClick={() => procesarPago(o)} style={btnPrimary(tiene && busy !== o.orden_id)}>
          {busy === o.orden_id ? '…' : 'Procesar pago'}
        </button>
      </div>
    );
  };

  const Tarjeta = ({ o }) => {
    const st = FLUJO_STYLE[o.flujo] || { bg: '#F3F4F6', fg: '#374151' };
    const bl = beneficiarioLinea(o.beneficiario);
    return (
      <div style={{ backgroundColor: '#fff', borderRadius: '10px', padding: '12px 14px', border: '1px solid ' + C.borderLight }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flexWrap: 'wrap' }}>
            <span style={badge(st)}>{o.flujo_label}</span>
            <span style={{ fontSize: '13px', color: '#374151' }}>
              {fmt(o.origen?.valor)} {o.origen?.unidad} <span style={{ color: C.faint }}>→</span>{' '}
              <b style={{ color: st.fg }}>{fmt(o.destino?.valor)} {o.destino?.unidad}</b>
            </span>
            {o.display_id && <span style={{ fontSize: '11px', color: C.faint }}>#{o.display_id}</span>}
          </div>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: C.faint, whiteSpace: 'nowrap' }}>
            <Clock size={12} /> {formatDate(o.created_at)}
          </span>
        </div>
        <div style={{ fontSize: '12.5px', color: C.soft, margin: '6px 0 10px 0' }}>
          {bl ? bl : `Usuario: ${o.user_name}`}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap', paddingTop: '10px', borderTop: '1px solid ' + C.borderLight }}>
          <Asignacion o={o} />
          <Accion o={o} />
        </div>
      </div>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <div>
          <h2 style={{ fontSize: '19px', fontWeight: 700, color: C.ink, margin: 0 }}>Órdenes por procesar</h2>
          <p style={{ fontSize: '12.5px', color: C.soft, margin: '3px 0 0 0' }}>
            {visibles.length} mostrada{visibles.length === 1 ? '' : 's'} · se actualiza cada 15s
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ display: 'inline-flex', borderRadius: '7px', border: '1px solid ' + C.border, overflow: 'hidden' }}>
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

      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
        {FILTROS.map((f) => (
          <button key={f.key} onClick={() => setFiltro(f.key)} style={btnGhost(filtro === f.key)}>{f.label}</button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: C.soft }}>Cargando órdenes…</p>
      ) : visibles.length === 0 ? (
        <div style={{ padding: '36px', textAlign: 'center', backgroundColor: C.bgSubtle, borderRadius: '12px', border: '1px dashed ' + C.border }}>
          <CheckCircle size={30} color={C.green} style={{ marginBottom: '6px' }} />
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
        <div style={{ overflowX: 'auto', border: '1px solid ' + C.borderLight, borderRadius: '10px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
            <thead>
              <tr style={{ backgroundColor: C.bgSubtle, textAlign: 'left' }}>
                {['Flujo', 'Monto', 'Usuario', 'Beneficiario', 'Fecha', 'Asignación', 'Acción'].map((h) => (
                  <th key={h} style={{ padding: '8px 10px', color: C.soft, fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
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
                      <tr><td colSpan={7} style={{ padding: 0 }}><Separador /></td></tr>
                    )}
                    <tr style={{ borderTop: '1px solid ' + C.borderLight }}>
                      <td style={{ padding: '8px 10px' }}><span style={badge(st)}>{o.flujo_label}</span></td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                        {fmt(o.origen?.valor)} {o.origen?.unidad} → <b style={{ color: st.fg }}>{fmt(o.destino?.valor)} {o.destino?.unidad}</b>
                      </td>
                      <td style={{ padding: '8px 10px' }}>{o.user_name}</td>
                      <td style={{ padding: '8px 10px', color: C.soft, maxWidth: '220px' }}>{bl || '—'}</td>
                      <td style={{ padding: '8px 10px', color: C.faint, whiteSpace: 'nowrap' }}>{formatDate(o.created_at)}</td>
                      <td style={{ padding: '8px 10px' }}><Asignacion o={o} /></td>
                      <td style={{ padding: '8px 10px' }}><Accion o={o} /></td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {verImg && (
        <div onClick={() => setVerImg(null)} style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(17,24,39,0.75)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px',
        }}>
          <img src={rutaDeArchivo(verImg)} alt="comprobante" style={{ maxWidth: '90%', maxHeight: '90%', borderRadius: '10px' }} />
        </div>
      )}
    </div>
  );
}
