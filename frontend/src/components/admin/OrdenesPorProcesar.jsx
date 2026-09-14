import { useState, useEffect, useRef, Fragment } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar, pedirTexto } from '../flujo/confirmar.js';
import { fmt } from '../../utils/format';
import { rutaDeArchivo } from '../../utils/urlDeArchivo';
import { useAuth } from '../../contexts/AuthContext';
import { RefreshCw, Paperclip, CheckCircle, XCircle, Clock, LayoutGrid, Table as TableIcon, UserCheck, UserX, Lock, Download, AlertTriangle } from 'lucide-react';

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

// Los flujos que terminan en un pago en BOLIVARES a una cuenta venezolana. Son
// los únicos que pueden ir al archivo que se pega en la banca en línea: un PIX
// a Brasil o una recarga que sólo hay que aprobar no tienen nada que pegar ahí.
const PAGA_BOLIVARES = new Set(['ris_ves', 'btc_ves', 'usdt_ves', 'usdc_ves']);

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
  const [elegidas, setElegidas] = useState(() => new Set());
  const [bancoPagador, setBancoPagador] = useState('');
  const [bancos, setBancos] = useState([]);
  const [resumen, setResumen] = useState(null);
  const [bajando, setBajando] = useState(false);
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

  useEffect(() => {
    api.get('/admin/ordenes/bancos-para-pagar')
      .then(({ data }) => setBancos(data?.bancos || []))
      .catch(() => setBancos([]));
  }, []);

  // ---- El archivo de pagos del lote ----
  const alternar = (o) => {
    setElegidas((prev) => {
      const copia = new Set(prev);
      if (copia.has(o.orden_id)) copia.delete(o.orden_id); else copia.add(o.orden_id);
      return copia;
    });
  };

  const seleccionables = visiblesQuePaganBolivares();
  function visiblesQuePaganBolivares() {
    const lista = filtro === 'all' ? ordenes : ordenes.filter((o) => o.flujo === filtro);
    return lista.filter((o) => PAGA_BOLIVARES.has(o.flujo));
  }

  const todasElegidas = seleccionables.length > 0
    && seleccionables.every((o) => elegidas.has(o.orden_id));

  const alternarTodas = () => {
    setElegidas((prev) => {
      const copia = new Set(prev);
      seleccionables.forEach((o) => (todasElegidas ? copia.delete(o.orden_id) : copia.add(o.orden_id)));
      return copia;
    });
  };

  const bajarArchivo = async () => {
    if (!bancoPagador) { toast.error('Elegí desde qué banco vas a pagar'); return; }
    setBajando(true);
    try {
      const { data } = await api.post('/admin/ordenes/archivo-de-pagos', {
        orden_ids: [...elegidas], banco_pagador: bancoPagador,
      });
      // El archivo se arma en el navegador a partir del texto que manda el
      // servidor. Así el servidor no tiene que guardar nada en disco ni servir
      // un archivo, y el texto viaja por la misma ruta autenticada que todo
      // lo demás.
      const url = URL.createObjectURL(new Blob([data.texto], { type: 'text/plain;charset=utf-8' }));
      const a = document.createElement('a');
      const hoy = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `pagos-${data.banco_pagador?.codigo || 'lote'}-${hoy}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      setResumen(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo armar el archivo');
    } finally { setBajando(false); }
  };

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
            {/* Sólo las que terminan en un pago en bolívares llevan casilla. En
                el resto no hay casilla, en vez de una apagada: una casilla que
                no se puede marcar es una pregunta sobre por qué, cada vez que
                alguien la mira. */}
            {PAGA_BOLIVARES.has(o.flujo) && (
              <input
                type="checkbox"
                checked={elegidas.has(o.orden_id)}
                onChange={() => alternar(o)}
                title="Incluir en el archivo de pagos"
                style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: C.primary }}
              />
            )}
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

      {seleccionables.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
          padding: '10px 12px', marginBottom: '12px', borderRadius: '9px',
          border: '1px solid ' + C.border, backgroundColor: C.bgSubtle,
        }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', fontSize: '13px', color: '#374151', cursor: 'pointer' }}>
            <input type="checkbox" checked={todasElegidas} onChange={alternarTodas}
              style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: C.primary }} />
            Todas las de bolívares ({seleccionables.length})
          </label>
          <span style={{ fontSize: '13px', color: elegidas.size ? C.ink : C.faint, fontWeight: elegidas.size ? 700 : 400 }}>
            {elegidas.size} elegida{elegidas.size === 1 ? '' : 's'}
          </span>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', fontSize: '13px', color: C.soft }}>
            Pago desde
            <select value={bancoPagador} onChange={(e) => setBancoPagador(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: '7px', border: '1px solid ' + C.border, fontSize: '13px', backgroundColor: '#fff' }}>
              <option value="">elegí el banco…</option>
              {bancos.map((b) => <option key={b.codigo} value={b.codigo}>{b.nombre} · {b.codigo}</option>)}
            </select>
          </label>
          <button onClick={bajarArchivo} disabled={!elegidas.size || !bancoPagador || bajando}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 14px',
              borderRadius: '7px', border: 'none', backgroundColor: C.primary, color: '#fff',
              fontWeight: 700, fontSize: '13px',
              cursor: (elegidas.size && bancoPagador && !bajando) ? 'pointer' : 'not-allowed',
              opacity: (elegidas.size && bancoPagador && !bajando) ? 1 : 0.45,
            }}>
            <Download size={14} /> {bajando ? 'Armando…' : 'Descargar archivo de pagos'}
          </button>
          {/* Bajar el archivo NO es pagar. Se dice acá, al lado del botón, y no
              en una ayuda que nadie abre. */}
          <span style={{ fontSize: '12px', color: C.faint }}>
            Bajar el archivo no cambia ninguna orden ni marca nada como pagado.
          </span>
        </div>
      )}

      {resumen && (
        <div style={{
          padding: '10px 12px', marginBottom: '12px', borderRadius: '9px',
          border: '1px solid ' + C.border, backgroundColor: '#fff', fontSize: '13px', color: '#374151',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
            <span>
              Archivo de <b>{resumen.total}</b> orden(es) para <b>{resumen.banco_pagador?.nombre}</b>:{' '}
              {resumen.por_seccion?.pago_movil || 0} pago móvil ·{' '}
              {resumen.por_seccion?.mismo_banco || 0} mismo banco ·{' '}
              {resumen.por_seccion?.otros_bancos || 0} otros bancos
            </span>
            <button onClick={() => setResumen(null)}
              style={{ border: 'none', background: 'none', color: C.soft, cursor: 'pointer', fontSize: '12px' }}>
              cerrar
            </button>
          </div>
          {/* Lo que quedó afuera se dice acá y en el archivo. Un archivo con
              menos pagos de los que se pidieron es un pago que no se hace y que
              nadie nota hasta que el cliente reclama. */}
          {resumen.por_seccion?.sin_datos > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', gap: '7px', alignItems: 'flex-start', color: C.amber }}>
              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
              <span>
                <b>{resumen.por_seccion.sin_datos} orden(es) sin datos completos</b> no se pueden pagar así:{' '}
                {resumen.sin_datos?.join(', ')}. Están al final del archivo, marcadas.
              </span>
            </div>
          )}
          {resumen.ya_no_estan?.length > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', gap: '7px', alignItems: 'flex-start', color: C.amber }}>
              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
              <span>
                <b>{resumen.ya_no_estan.length} orden(es) ya no estaban pendientes</b> cuando se armó el
                archivo y quedaron afuera: {resumen.ya_no_estan.join(', ')}.
              </span>
            </div>
          )}
        </div>
      )}

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
