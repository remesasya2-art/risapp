/**
 * Retiros.jsx — La cola de pagos.
 *
 * QUE ERA ESTO ANTES
 *   Una tabla dentro de `AdminPanel.jsx` que pedía los 200 retiros más nuevos
 *   de CUALQUIER estado y filtraba en el navegador, con un cartel arriba que
 *   decía «TOTAL VES NECESARIOS» y mentía dos veces.
 *
 * LOS DOS NUMEROS QUE MENTIAN
 *   1. El total mezclaba monedas. Un retiro sale en VES o en BRL, y los dos se
 *      sumaban en una sola cifra rotulada «VES». Quien mira ese número para
 *      saber cuánto poner en las cuentas venezolanas provisionaba mal.
 *      Acá el total va SIEMPRE por moneda: son cajas distintas.
 *   2. «0,00 RIS» siempre. La pantalla leía un campo que el servidor nunca
 *      devolvió.
 *
 * POR QUE UNA COLA DE PAGOS ES MAS EXIGENTE QUE UNA DE APROBACIONES
 *   Una recarga que tarda es un saldo que todavía no aparece. Un retiro que
 *   tarda es plata que alguien YA NO TIENE y todavía no recibió. Por eso el
 *   semáforo de antigüedad salta a las 3 horas y no a las 6, y por eso las
 *   pendientes salen de la más vieja a la más nueva.
 *
 * POR QUE PAGAR PIDE CONFIRMACION
 *   Marcar un retiro como pagado no mueve plata sola, pero cierra la orden y
 *   le avisa al usuario que ya cobró. Si se cierra sin haber transferido, el
 *   reclamo aparece cuando ya nadie se acuerda. La confirmación repite a quién
 *   se le paga, a qué cuenta y cuánto.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, Ban, Check, CheckCircle2, ChevronRight, Clock, Coins,
  CreditCard, FileImage, Landmark, Lock, LockOpen, RefreshCw, Search, User, X,
} from 'lucide-react';
import api from '../../utils/api';
import { fmt, formatAccountNumber } from '../../utils/format';

const COLOR = {
  borde: '#e5e7eb', bordeFuerte: '#d1d5db',
  suave: '#6b7280', tenue: '#9ca3af', texto: '#111827',
  primario: '#4F46E5', primarioSuave: '#eef0ff', primarioBorde: '#c7d2fe',
  bien: '#15803d', bienSuave: '#f0fdf4', bienBorde: '#bbf7d0',
  alerta: '#b45309', alertaSuave: '#fffbeb', alertaBorde: '#fde68a',
  malo: '#b91c1c', maloSuave: '#fef2f2', maloBorde: '#fecaca',
};

const CIFRAS = { fontVariantNumeric: 'tabular-nums', fontFeatureSettings: '"tnum"' };
const MONO = { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' };

const tarjeta = {
  backgroundColor: '#fff', borderRadius: '14px',
  border: `1px solid ${COLOR.borde}`,
};

const ESTADOS = [
  { clave: 'pending', etiqueta: 'Por pagar', contador: 'pendientes' },
  { clave: 'completed', etiqueta: 'Pagados', contador: 'pagados' },
  { clave: 'rejected', etiqueta: 'Rechazados', contador: 'rechazados' },
  { clave: 'all', etiqueta: 'Todos', contador: 'total' },
];

const SEMAFORO = {
  normal: { fondo: COLOR.bienSuave, borde: COLOR.bienBorde, texto: COLOR.bien },
  atencion: { fondo: COLOR.alertaSuave, borde: COLOR.alertaBorde, texto: COLOR.alerta },
  urgente: { fondo: COLOR.maloSuave, borde: COLOR.maloBorde, texto: COLOR.malo },
  desconocida: { fondo: '#f3f4f6', borde: COLOR.borde, texto: COLOR.suave },
};

const POR_PAGINA = 50;

function espera(antiguedad) {
  const h = antiguedad?.horas;
  if (h === null || h === undefined) return 'sin fecha';
  if (h < 1) return `hace ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} d`;
}

function fechaHora(valor) {
  if (!valor) return '—';
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return '—';
  const o = { timeZone: 'America/Caracas' };
  return `${d.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', ...o })} · ${d.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: true, ...o })}`;
}

/* Las URLs de Twilio no se pueden mostrar directo: van por el proxy. */
function urlComprobante(url) {
  if (!url) return url;
  if (typeof url === 'string' && url.startsWith('https://api.twilio.com')) {
    return `${api.defaults.baseURL || ''}/media/proxy?url=${encodeURIComponent(url)}`;
  }
  return url;
}

function Chip({ fondo, borde, texto, children, titulo }) {
  return (
    <span title={titulo} style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 9px', borderRadius: '999px', fontSize: '11.5px',
      fontWeight: 700, backgroundColor: fondo, color: texto,
      border: `1px solid ${borde}`, whiteSpace: 'nowrap',
    }}>{children}</span>
  );
}

export default function Retiros({ accountingBanks = [], user, onProcesada }) {
  const [estado, setEstado] = useState('pending');
  const [moneda, setMoneda] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [buscado, setBuscado] = useState('');
  const [pagina, setPagina] = useState(0);
  const [datos, setDatos] = useState({ withdrawals: [], total: 0, counters: null });
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);

  const [abierta, setAbierta] = useState(null);
  const [comprobantes, setComprobantes] = useState({});
  const [bancoPago, setBancoPago] = useState({});
  const [confirmando, setConfirmando] = useState(null);
  const [rechazando, setRechazando] = useState(null);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(null);

  const vivo = useRef(true);

  const cargar = useCallback(async ({ silencioso = false } = {}) => {
    if (silencioso) setRefrescando(true); else setCargando(true);
    try {
      const res = await api.get('/admin/withdrawals/all', {
        params: {
          status: estado, q: buscado, currency: moneda,
          limit: POR_PAGINA, skip: pagina * POR_PAGINA,
        },
      });
      if (!vivo.current) return;
      setDatos(res.data || { withdrawals: [], total: 0, counters: null });
    } catch (e) {
      if (!vivo.current) return;
      toast.error(e?.response?.data?.detail || 'No se pudo leer la cola de pagos');
      setDatos((p) => ({ ...p, withdrawals: [] }));
    } finally {
      if (vivo.current) { setCargando(false); setRefrescando(false); }
    }
  }, [estado, buscado, moneda, pagina]);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  /* Dos operadores sobre la misma cola tienen que ver que una orden ya fue
     tomada sin apretar «Actualizar». */
  useEffect(() => {
    const t = setInterval(() => cargar({ silencioso: true }), 20000);
    return () => clearInterval(t);
  }, [cargar]);

  const contadores = datos.counters || {};
  const filas = datos.withdrawals || [];
  const totalPaginas = Math.max(1, Math.ceil((datos.total || 0) / POR_PAGINA));
  const porMoneda = contadores.por_moneda || [];
  const porOrigen = contadores.por_origen || [];

  const bancosPorMoneda = useMemo(() => {
    const m = {};
    (accountingBanks || []).forEach((b) => {
      (m[b.currency] = m[b.currency] || []).push(b);
    });
    return m;
  }, [accountingBanks]);

  const buscar = (e) => {
    e.preventDefault();
    setPagina(0);
    setBuscado(busqueda.trim());
  };

  const cambiar = (cambios) => {
    setPagina(0);
    setAbierta(null);
    setConfirmando(null);
    setRechazando(null);
    if ('estado' in cambios) setEstado(cambios.estado);
    if ('moneda' in cambios) setMoneda(cambios.moneda);
  };

  /* Al cerrar una orden se abre la que sigue: procesar cien es, si no, cerrar,
     buscar dónde estabas y abrir la próxima, cien veces. */
  const siguiente = (idActual) => {
    const lista = datos.withdrawals || [];
    const i = lista.findIndex((x) => x.transaction_id === idActual);
    const proxima = lista.slice(i + 1).find((x) => x.status === 'pending');
    setAbierta(proxima ? proxima.transaction_id : null);
  };

  const tomar = async (w) => {
    setOcupado(w.transaction_id);
    try {
      const res = await api.post('/admin/ordenes/tomar', {
        orden_id: w.transaction_id, flujo: flujoDe(w),
      });
      if (res.data?.success) toast.success('Orden asignada a vos');
      else toast.error(`Ya la tomó ${res.data?.assigned_to_name || 'otro operador'}`);
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo tomar la orden');
    } finally { setOcupado(null); }
  };

  const liberar = async (w) => {
    setOcupado(w.transaction_id);
    try {
      await api.post('/admin/ordenes/liberar', {
        orden_id: w.transaction_id, flujo: flujoDe(w),
      });
      toast.success('Orden liberada');
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo liberar la orden');
    } finally { setOcupado(null); }
  };

  const pagar = async (w) => {
    const imgs = comprobantes[w.transaction_id] || [];
    setOcupado(w.transaction_id);
    try {
      await api.post('/admin/withdrawals/process', {
        transaction_id: w.transaction_id,
        action: 'approve',
        proof_images: imgs,
        proof_image: imgs[0],
        bank_id: bancoPago[w.transaction_id] || undefined,
      });
      toast.success(`Pagados ${fmt(w.amount_output)} ${w.currency_output} a ${w.beneficiary_data?.full_name || 'el beneficiario'}`);
      setConfirmando(null);
      siguiente(w.transaction_id);
      onProcesada?.();
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo registrar el pago');
      await cargar({ silencioso: true });
    } finally { setOcupado(null); }
  };

  const rechazar = async (w) => {
    if (!motivo.trim()) { toast.error('Escribí el motivo del rechazo'); return; }
    setOcupado(w.transaction_id);
    try {
      await api.post('/admin/withdrawals/process', {
        transaction_id: w.transaction_id,
        action: 'reject',
        rejection_reason: motivo.trim(),
      });
      toast.success('Retiro rechazado y saldo devuelto');
      setRechazando(null);
      setMotivo('');
      siguiente(w.transaction_id);
      onProcesada?.();
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo rechazar');
    } finally { setOcupado(null); }
  };

  const masVieja = contadores.mas_vieja || {};
  const semCola = SEMAFORO[masVieja.nivel] || SEMAFORO.desconocida;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

      {/* ── Lo que hay que pagar, POR MONEDA ────────────────────────────
          Antes era una sola cifra rotulada «VES» que sumaba también los
          reales. No hay un total único porque no existe: son cajas
          bancarias distintas y se cargan por separado. */}
      <div style={{ ...tarjeta, overflow: 'hidden' }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 16px', borderBottom: `1px solid ${COLOR.borde}`,
          gap: '12px', flexWrap: 'wrap',
        }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700, color: COLOR.texto, margin: 0 }}>
              Retiros por pagar
            </h3>
            <p style={{ fontSize: '12px', color: COLOR.suave, margin: '2px 0 0 0' }}>
              Cola de pagos · se atiende por orden de llegada
            </p>
          </div>
          <button type="button" onClick={() => cargar({ silencioso: true })} style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '8px 14px', borderRadius: '9px', cursor: 'pointer',
            border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
            color: COLOR.suave, fontSize: '13px', fontWeight: 600,
          }}>
            <RefreshCw size={14} style={refrescando ? { animation: 'spin 1s linear infinite' } : undefined} />
            Actualizar
          </button>
        </div>

        <div style={{
          display: 'grid', gap: '1px', backgroundColor: COLOR.borde,
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        }}>
          {porMoneda.length === 0 ? (
            <div style={{ backgroundColor: '#fff', padding: '16px' }}>
              <p style={{ fontSize: '13px', color: COLOR.suave, margin: 0 }}>
                No hay nada por pagar.
              </p>
            </div>
          ) : porMoneda.map((m) => (
            <div key={m.moneda} style={{ backgroundColor: '#fff', padding: '14px 16px' }}>
              <p style={{
                fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.6px',
                textTransform: 'uppercase', color: COLOR.tenue, margin: 0,
              }}>A pagar en {m.moneda}</p>
              <p style={{
                fontSize: '22px', fontWeight: 700, margin: '4px 0 0 0',
                color: COLOR.alerta, ...CIFRAS,
              }}>{fmt(m.total)}</p>
              <p style={{ fontSize: '11.5px', color: COLOR.suave, margin: '2px 0 0 0' }}>
                {m.ordenes} {m.ordenes === 1 ? 'orden' : 'órdenes'}
              </p>
            </div>
          ))}

          <div style={{ backgroundColor: '#fff', padding: '14px 16px' }}>
            <p style={{
              fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.6px',
              textTransform: 'uppercase', color: COLOR.tenue, margin: 0,
            }}>La más vieja</p>
            <p style={{
              fontSize: '22px', fontWeight: 700, margin: '4px 0 0 0',
              color: semCola.texto, ...CIFRAS,
            }}>{espera(masVieja)}</p>
            <p style={{ fontSize: '11.5px', color: COLOR.suave, margin: '2px 0 0 0' }}>
              sin pagar
            </p>
          </div>

          <div style={{ backgroundColor: '#fff', padding: '14px 16px' }}>
            <p style={{
              fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.6px',
              textTransform: 'uppercase', color: COLOR.tenue, margin: 0,
            }}>Ya debitado</p>
            <p style={{ fontSize: '17px', fontWeight: 700, margin: '4px 0 0 0', ...CIFRAS }}>
              {porOrigen.length === 0 ? '—'
                : porOrigen.map((o) => `${fmt(o.total)} ${o.moneda}`).join(' · ')}
            </p>
            <p style={{ fontSize: '11.5px', color: COLOR.suave, margin: '2px 0 0 0' }}>
              cobrado a los usuarios, sin pagar
            </p>
          </div>
        </div>

        {contadores.sin_beneficiario ? (
          <div style={{
            padding: '9px 16px', backgroundColor: COLOR.maloSuave,
            borderTop: `1px solid ${COLOR.maloBorde}`, fontSize: '12.5px',
            color: COLOR.malo, display: 'flex', alignItems: 'center', gap: '7px',
          }}>
            <AlertTriangle size={14} />
            {contadores.sin_beneficiario} {contadores.sin_beneficiario === 1
              ? 'orden no tiene datos del beneficiario'
              : 'órdenes no tienen datos del beneficiario'}: no hay a quién pagarle.
          </div>
        ) : null}
      </div>

      {/* ── Filtros ────────────────────────────────────────────────────── */}
      <div style={{
        ...tarjeta, padding: '12px 14px', display: 'flex', gap: '10px',
        alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
          {ESTADOS.map(({ clave, etiqueta, contador }) => {
            const activo = estado === clave;
            const n = contadores[contador];
            return (
              <button key={clave} type="button" onClick={() => cambiar({ estado: clave })}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '7px',
                  padding: '8px 13px', borderRadius: '9px', cursor: 'pointer',
                  fontSize: '13px', fontWeight: 700,
                  border: `1px solid ${activo ? COLOR.primarioBorde : COLOR.borde}`,
                  backgroundColor: activo ? COLOR.primarioSuave : '#fff',
                  color: activo ? COLOR.primario : COLOR.suave,
                }}
                data-testid={`filtro-${clave}`}
              >
                {etiqueta}
                {n !== undefined && n !== null ? (
                  <span style={{
                    ...CIFRAS, padding: '1px 7px', borderRadius: '999px',
                    fontSize: '11px', fontWeight: 700,
                    backgroundColor: activo ? '#fff' : '#f3f4f6',
                    color: activo ? COLOR.primario : COLOR.suave,
                  }}>{n}</span>
                ) : null}
              </button>
            );
          })}

          {/* Quien carga las cuentas venezolanas no quiere ver los reales. */}
          {porMoneda.length > 1 || moneda ? (
            <select value={moneda} onChange={(e) => cambiar({ moneda: e.target.value })}
              style={{
                padding: '8px 11px', borderRadius: '9px', fontSize: '13px',
                fontWeight: 600, border: `1px solid ${COLOR.borde}`,
                backgroundColor: '#fff', color: COLOR.suave, cursor: 'pointer',
              }}
              data-testid="filtro-moneda"
            >
              <option value="">Todas las monedas</option>
              {porMoneda.map((m) => (
                <option key={m.moneda} value={m.moneda}>Sólo {m.moneda}</option>
              ))}
            </select>
          ) : null}
        </div>

        <form onSubmit={buscar} style={{ display: 'flex', gap: '6px', flex: '1 1 240px', maxWidth: '400px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={15} style={{
              position: 'absolute', left: '11px', top: '50%',
              transform: 'translateY(-50%)', color: COLOR.tenue,
            }} />
            <input
              value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Orden, beneficiario, cédula o cuenta…"
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '9px 12px 9px 34px', borderRadius: '9px',
                border: `1px solid ${COLOR.borde}`, fontSize: '13px', outline: 'none',
              }}
              data-testid="buscar-retiro"
            />
          </div>
          <button type="submit" style={{
            padding: '9px 15px', borderRadius: '9px', border: 'none', cursor: 'pointer',
            backgroundColor: COLOR.primario, color: '#fff', fontSize: '13px', fontWeight: 700,
          }}>Buscar</button>
        </form>
      </div>

      {/* ── La cola ────────────────────────────────────────────────────── */}
      {cargando ? (
        <div style={{ ...tarjeta, padding: '56px', textAlign: 'center' }}>
          <RefreshCw size={28} style={{ color: COLOR.primario, animation: 'spin 1s linear infinite' }} />
        </div>
      ) : filas.length === 0 ? (
        <div style={{ ...tarjeta, padding: '56px 24px', textAlign: 'center' }}>
          <div style={{
            width: '56px', height: '56px', borderRadius: '50%', margin: '0 auto 14px',
            backgroundColor: COLOR.bienSuave, border: `1px solid ${COLOR.bienBorde}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <CheckCircle2 size={26} style={{ color: COLOR.bien }} />
          </div>
          <p style={{ fontSize: '15px', fontWeight: 700, color: COLOR.texto, margin: 0 }}>
            {buscado ? 'Ningún retiro coincide con la búsqueda'
              : estado === 'pending' ? 'No hay retiros esperando pago'
                : 'No hay retiros en este estado'}
          </p>
          <p style={{ fontSize: '13px', color: COLOR.suave, margin: '6px 0 0 0' }}>
            {buscado ? 'Probá con el número de orden, la cédula o la cuenta de destino.'
              : 'La cola está al día.'}
          </p>
        </div>
      ) : (
        <div style={{ ...tarjeta, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', minWidth: '920px', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb' }}>
                  {[
                    { t: '#', ancho: '38px', der: false },
                    { t: 'Orden', ancho: '104px', der: false },
                    { t: 'Espera', ancho: '92px', der: false },
                    { t: 'Beneficiario', ancho: 'auto', der: false },
                    { t: 'Se debitó', ancho: '116px', der: true },
                    { t: 'A pagar', ancho: '146px', der: true },
                    { t: 'Destino', ancho: '160px', der: false },
                    { t: '', ancho: '138px', der: true },
                  ].map((c) => (
                    <th key={c.t || 'acc'} style={{
                      width: c.ancho, padding: '9px 10px',
                      textAlign: c.der ? 'right' : 'left',
                      fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.5px',
                      textTransform: 'uppercase', color: COLOR.tenue,
                      borderBottom: `1px solid ${COLOR.borde}`, whiteSpace: 'nowrap',
                    }}>{c.t}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filas.map((w) => (
                  <Fila
                    key={w.transaction_id}
                    w={w}
                    user={user}
                    bancos={bancosPorMoneda[w.currency_output] || []}
                    abierta={abierta === w.transaction_id}
                    onAbrir={() => {
                      setConfirmando(null); setRechazando(null);
                      setAbierta(abierta === w.transaction_id ? null : w.transaction_id);
                    }}
                    comprobantes={comprobantes[w.transaction_id]
                      || (w.proof_images || []).map(urlComprobante)
                      || []}
                    bancoElegido={bancoPago[w.transaction_id] || ''}
                    confirmando={confirmando === w.transaction_id}
                    rechazando={rechazando === w.transaction_id}
                    motivo={motivo}
                    ocupado={ocupado === w.transaction_id}
                    onComprobantes={(imgs) => setComprobantes((p) => ({ ...p, [w.transaction_id]: imgs }))}
                    onBanco={(v) => setBancoPago((p) => ({ ...p, [w.transaction_id]: v }))}
                    onPedirConfirmacion={() => { setRechazando(null); setConfirmando(w.transaction_id); }}
                    onCancelarConfirmacion={() => setConfirmando(null)}
                    onPagar={() => pagar(w)}
                    onPedirRechazo={() => { setConfirmando(null); setMotivo(''); setRechazando(w.transaction_id); }}
                    onCancelarRechazo={() => { setRechazando(null); setMotivo(''); }}
                    onMotivo={setMotivo}
                    onRechazar={() => rechazar(w)}
                    onTomar={() => tomar(w)}
                    onLiberar={() => liberar(w)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {datos.total > POR_PAGINA && (
        <div style={{
          ...tarjeta, padding: '11px 14px', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', gap: '10px',
        }}>
          <span style={{ fontSize: '12.5px', color: COLOR.suave, ...CIFRAS }}>
            {pagina * POR_PAGINA + 1}–{Math.min((pagina + 1) * POR_PAGINA, datos.total)} de {datos.total}
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button type="button" onClick={() => setPagina((p) => Math.max(0, p - 1))}
              disabled={pagina === 0} style={botonPagina(pagina === 0)}>Anterior</button>
            <button type="button" onClick={() => setPagina((p) => p + 1)}
              disabled={pagina + 1 >= totalPaginas} style={botonPagina(pagina + 1 >= totalPaginas)}>Siguiente</button>
          </div>
        </div>
      )}
    </div>
  );
}

function botonPagina(apagado) {
  return {
    padding: '7px 12px', borderRadius: '8px', fontSize: '13px', fontWeight: 600,
    border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
    color: apagado ? COLOR.tenue : COLOR.texto,
    cursor: apagado ? 'not-allowed' : 'pointer',
  };
}

/* El flujo con el que el backend ubica esta orden para el candado. Un retiro
   en cripto se guarda con el mismo `type: "withdrawal"` pero se reclama con su
   propio flujo. */
function flujoDe(w) {
  const entra = (w.currency_input || 'RIS').toUpperCase();
  if (entra === 'USDT') return 'usdt_ves';
  if (entra === 'USDC') return 'usdc_ves';
  return (w.currency_output || 'VES').toUpperCase() === 'BRL' ? 'ris_reais' : 'ris_ves';
}

/* ─── Una orden: la fila, y su detalle ─────────────────────────────────── */
function Fila(props) {
  const { w, user, abierta, onAbrir, ocupado, onTomar } = props;
  const pendiente = w.status === 'pending';
  const sem = SEMAFORO[w.antiguedad?.nivel] || SEMAFORO.desconocida;
  const mia = w.assigned_to && user?.user_id && w.assigned_to === user.user_id;
  const deOtro = w.assigned_to && !mia;
  const b = w.beneficiary_data || {};
  const cuenta = b.account_number || b.phone;

  const celda = {
    padding: '8px 10px', borderBottom: `1px solid ${COLOR.borde}`,
    verticalAlign: 'middle',
  };

  return (
    <>
      <tr onClick={onAbrir} style={{
        cursor: 'pointer',
        backgroundColor: abierta ? COLOR.primarioSuave : deOtro ? '#fafafa' : '#fff',
      }} data-testid={`withdrawal-${w.transaction_id}`}>
        <td style={{ ...celda, color: COLOR.tenue, ...CIFRAS, fontSize: '12px' }}>
          {pendiente && w.posicion ? w.posicion : ''}
        </td>

        <td style={{ ...celda, whiteSpace: 'nowrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <ChevronRight size={13} style={{
              color: COLOR.tenue, flexShrink: 0,
              transform: abierta ? 'rotate(90deg)' : 'none', transition: 'transform .12s',
            }} />
            <span style={{ ...MONO, fontSize: '12.5px', fontWeight: 700, color: COLOR.texto }}>
              {w.display_id}
            </span>
          </div>
        </td>

        <td style={{ ...celda, whiteSpace: 'nowrap' }}>
          {pendiente ? (
            <Chip {...sem} titulo={`Ingresó ${fechaHora(w.created_at)}`}>
              <Clock size={10} />{espera(w.antiguedad)}
            </Chip>
          ) : (
            <Chip
              fondo={w.status === 'completed' ? COLOR.bienSuave : COLOR.maloSuave}
              borde={w.status === 'completed' ? COLOR.bienBorde : COLOR.maloBorde}
              texto={w.status === 'completed' ? COLOR.bien : COLOR.malo}
              titulo={fechaHora(w.completed_at)}
            >
              {w.status === 'completed' ? <Check size={10} /> : <Ban size={10} />}
              {w.status === 'completed' ? 'Pagado' : 'Rechazado'}
            </Chip>
          )}
        </td>

        <td style={{ ...celda, maxWidth: 0 }}>
          <div style={{
            fontWeight: 600, color: w.falta_beneficiario ? COLOR.malo : COLOR.texto,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }} title={b.full_name || b.name || ''}>
            {b.full_name || b.name || 'sin beneficiario'}
          </div>
          {b.cedula ? (
            <div style={{ ...MONO, fontSize: '11px', color: COLOR.tenue }}>{b.cedula}</div>
          ) : null}
        </td>

        <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap', ...CIFRAS }}>
          <span style={{ fontWeight: 600 }}>{fmt(w.amount_input)}</span>
          <span style={{ fontSize: '11px', color: COLOR.suave }}> {w.currency_input}</span>
        </td>

        {/* La moneda va PEGADA al monto. El cartel de arriba decía «VES» sobre
            una suma que incluía reales; acá cada fila dice la suya. */}
        <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap', ...CIFRAS }}>
          <span style={{ fontWeight: 700, color: COLOR.alerta, fontSize: '14px' }}>
            {fmt(w.amount_output)}
          </span>
          <span style={{ fontSize: '11px', color: COLOR.suave, fontWeight: 700 }}> {w.currency_output}</span>
        </td>

        <td style={{ ...celda, maxWidth: 0 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '5px', minWidth: 0,
            color: COLOR.suave, fontSize: '12px',
          }} title={`${b.bank || ''} ${cuenta || ''}`}>
            <Landmark size={11} style={{ flexShrink: 0 }} />
            <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {b.bank || <em style={{ color: COLOR.alerta }}>sin banco</em>}
            </span>
          </div>
        </td>

        <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            {pendiente && w.falta_destino ? (
              <AlertTriangle size={14} style={{ color: COLOR.malo }} aria-label="Sin cuenta de destino" />
            ) : null}
            {!pendiente && w.comprobantes > 0 ? (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: '3px',
                fontSize: '11.5px', fontWeight: 700, color: COLOR.bien,
              }}><FileImage size={12} />{w.comprobantes}</span>
            ) : null}
            {deOtro ? (
              <span title={`La tiene ${w.assigned_to_name || 'otro operador'}`} style={{
                display: 'inline-flex', alignItems: 'center', gap: '3px',
                fontSize: '11px', fontWeight: 700, color: COLOR.alerta,
                maxWidth: '84px', overflow: 'hidden', whiteSpace: 'nowrap',
              }}><Lock size={11} />{w.assigned_to_name || 'otro'}</span>
            ) : mia ? (
              <Chip fondo={COLOR.primarioSuave} borde={COLOR.primarioBorde} texto={COLOR.primario}>
                <Lock size={10} />Tuya
              </Chip>
            ) : pendiente ? (
              <button type="button" onClick={(e) => { e.stopPropagation(); onTomar(); }}
                disabled={ocupado} style={{
                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                  padding: '4px 9px', borderRadius: '7px', fontSize: '11.5px', fontWeight: 700,
                  border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
                  color: COLOR.suave, cursor: ocupado ? 'wait' : 'pointer',
                }} data-testid={`tomar-${w.transaction_id}`}>
                <Lock size={11} />Tomar
              </button>
            ) : null}
          </div>
        </td>
      </tr>

      {abierta ? (
        <tr>
          <td colSpan={8} style={{
            padding: 0, borderBottom: `1px solid ${COLOR.borde}`, backgroundColor: '#fbfbfd',
          }}>
            <Detalle {...props} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function Detalle(props) {
  const {
    w, user, bancos, comprobantes, bancoElegido, confirmando, rechazando,
    motivo, ocupado, onComprobantes, onBanco, onPedirConfirmacion,
    onCancelarConfirmacion, onPagar, onPedirRechazo, onCancelarRechazo,
    onMotivo, onRechazar, onLiberar,
  } = props;

  const pendiente = w.status === 'pending';
  const mia = w.assigned_to && user?.user_id && w.assigned_to === user.user_id;
  const b = w.beneficiary_data || {};
  const cuenta = b.account_number || b.phone;
  const puedePagar = comprobantes.length > 0 && !ocupado;

  const agregar = (e) => {
    const archivos = Array.from(e.target.files || []);
    if (!archivos.length) return;
    const leidas = [];
    let listas = 0;
    archivos.forEach((archivo) => {
      const lector = new FileReader();
      lector.onload = () => {
        leidas.push(lector.result);
        listas += 1;
        if (listas === archivos.length) onComprobantes([...comprobantes, ...leidas]);
      };
      lector.readAsDataURL(archivo);
    });
  };

  const quitar = (i) => onComprobantes(comprobantes.filter((_, j) => j !== i));

  return (
    <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '11px' }}>

      {/* A quién y a dónde. Es lo que el operador copia al home banking, así
          que va primero, junto, y en monoespaciada para no equivocarse. */}
      <div style={{
        display: 'grid', gap: '1px', backgroundColor: COLOR.borde,
        border: `1px solid ${COLOR.borde}`, borderRadius: '10px', overflow: 'hidden',
        gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
      }}>
        <Dato etiqueta="Beneficiario" valor={b.full_name || b.name}
          falta={!b.full_name && !b.name} Icono={User} />
        <Dato etiqueta="Documento" valor={b.cedula} mono Icono={CreditCard} />
        <Dato etiqueta="Banco" valor={b.bank} falta={!b.bank} Icono={Landmark} />
        <Dato etiqueta={b.account_number ? 'Cuenta' : 'Teléfono'}
          valor={cuenta ? (formatAccountNumber(cuenta) || cuenta) : null}
          falta={!cuenta} mono Icono={Coins} />
      </div>

      <div style={{
        display: 'flex', gap: '18px', flexWrap: 'wrap', fontSize: '12px',
        color: COLOR.suave, alignItems: 'center',
      }}>
        <span>Pidió {w.user_name || w.user_email || '—'}</span>
        <span style={CIFRAS}>Tasa {fmt(w.rate)}</span>
        <span>{fechaHora(w.created_at)} · Caracas</span>
        {w.is_gestor_transaction ? (
          <Chip fondo={COLOR.primarioSuave} borde={COLOR.primarioBorde} texto={COLOR.primario}>
            Gestor{w.client_name ? ` · ${w.client_name}` : ''}
          </Chip>
        ) : null}
        {mia && pendiente ? (
          <button type="button" onClick={onLiberar} disabled={ocupado} style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            padding: '3px 9px', borderRadius: '7px', fontSize: '11.5px', fontWeight: 600,
            border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
            color: COLOR.suave, cursor: ocupado ? 'wait' : 'pointer',
          }}><LockOpen size={11} />Liberar</button>
        ) : null}
      </div>

      {w.falta_destino && pendiente && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: '8px',
          padding: '10px 13px', borderRadius: '10px', fontSize: '12.5px',
          backgroundColor: COLOR.maloSuave, border: `1px solid ${COLOR.maloBorde}`, color: COLOR.malo,
        }}>
          <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
          <span>
            Esta orden no tiene cuenta ni teléfono de destino: <strong>no hay a dónde
            transferir</strong>. Confirmalo con el usuario antes de marcarla como pagada.
          </span>
        </div>
      )}

      {!pendiente && (
        <div style={{
          padding: '9px 12px', borderRadius: '9px', backgroundColor: '#fff',
          border: `1px solid ${COLOR.borde}`, fontSize: '12px', color: COLOR.suave,
        }}>
          <div>
            {w.status === 'completed' ? 'Pagado' : 'Rechazado'} {fechaHora(w.completed_at)}
            {w.processed_by ? ` · por ${w.processed_by}` : ''}
          </div>
          {w.rejection_reason ? (
            <div style={{ color: COLOR.malo, marginTop: '3px' }}>Motivo: {w.rejection_reason}</div>
          ) : null}
        </div>
      )}

      {/* Comprobantes del pago */}
      <div>
        <label style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          fontSize: '12px', fontWeight: 700, color: COLOR.texto, marginBottom: '7px',
        }}>
          <FileImage size={13} />
          Comprobantes de la transferencia ({comprobantes.length})
          {pendiente ? (
            <span style={{ fontWeight: 400, color: COLOR.tenue }}>
              — sin al menos uno no se puede cerrar la orden
            </span>
          ) : null}
        </label>

        {comprobantes.length > 0 && (
          <div style={{
            display: 'grid', gap: '9px', marginBottom: '9px',
            gridTemplateColumns: 'repeat(auto-fill, minmax(94px, 1fr))',
          }}>
            {comprobantes.map((img, i) => (
              <div key={`${i}-${String(img).slice(-24)}`} style={{
                position: 'relative', borderRadius: '9px', overflow: 'hidden',
                border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
              }}>
                <a href={img} target="_blank" rel="noreferrer" title="Abrir">
                  <img src={img} alt={`Comprobante ${i + 1}`}
                    style={{ width: '100%', height: '94px', objectFit: 'cover', display: 'block' }} />
                </a>
                {pendiente ? (
                  <button type="button" onClick={() => quitar(i)} aria-label="Quitar" style={{
                    position: 'absolute', top: '4px', right: '4px', width: '20px', height: '20px',
                    borderRadius: '50%', backgroundColor: COLOR.malo, color: '#fff',
                    border: 'none', cursor: 'pointer', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                  }}><X size={12} /></button>
                ) : null}
              </div>
            ))}
          </div>
        )}

        {pendiente ? (
          <input type="file" accept="image/*" multiple onChange={agregar}
            style={{ fontSize: '12.5px' }} data-testid={`subir-${w.transaction_id}`} />
        ) : comprobantes.length === 0 ? (
          <p style={{ fontSize: '12.5px', color: COLOR.tenue, margin: 0 }}>
            No quedaron comprobantes cargados en esta orden.
          </p>
        ) : null}
      </div>

      {pendiente && bancos.length > 0 && (
        <div>
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: COLOR.texto, marginBottom: '5px' }}>
            Banco desde el que se pagó <span style={{ fontWeight: 400, color: COLOR.tenue }}>(opcional)</span>
          </label>
          <select value={bancoElegido} onChange={(e) => onBanco(e.target.value)}
            style={{
              width: '100%', maxWidth: '340px', padding: '8px 11px', borderRadius: '8px',
              border: `1px solid ${COLOR.borde}`, fontSize: '13px', backgroundColor: '#fff',
            }}
            data-testid={`banco-${w.transaction_id}`}
          >
            <option value="">Sin especificar</option>
            {bancos.map((banco) => (
              <option key={banco.bank_id} value={banco.bank_id}>{banco.name}</option>
            ))}
          </select>
        </div>
      )}

      {pendiente && !confirmando && !rechazando && (
        <div style={{ display: 'flex', gap: '9px', flexWrap: 'wrap' }}>
          <button type="button" onClick={onPedirConfirmacion} disabled={!puedePagar}
            title={comprobantes.length === 0 ? 'Subí el comprobante de la transferencia' : undefined}
            style={{
              flex: '0 1 240px', padding: '10px', borderRadius: '9px', border: 'none',
              backgroundColor: puedePagar ? COLOR.bien : '#d1d5db', color: '#fff',
              fontSize: '13px', fontWeight: 700,
              cursor: puedePagar ? 'pointer' : 'not-allowed',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
            }}
            data-testid={`pagar-${w.transaction_id}`}
          >
            <Check size={15} />Registrar el pago
          </button>
          <button type="button" onClick={onPedirRechazo} style={{
            flex: '0 1 150px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
            border: `1px solid ${COLOR.maloBorde}`, backgroundColor: '#fff',
            color: COLOR.malo, fontSize: '13px', fontWeight: 700,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
          }} data-testid={`rechazar-${w.transaction_id}`}>
            <Ban size={15} />Rechazar
          </button>
        </div>
      )}

      {confirmando && (
        <div style={{
          padding: '12px', borderRadius: '10px',
          backgroundColor: COLOR.bienSuave, border: `1px solid ${COLOR.bienBorde}`,
        }}>
          <p style={{ fontSize: '13px', color: COLOR.texto, margin: '0 0 3px 0', fontWeight: 700 }}>
            Confirmás que ya transferiste {fmt(w.amount_output)} {w.currency_output} a {b.full_name || b.name || 'el beneficiario'}
          </p>
          <p style={{ fontSize: '12px', color: COLOR.suave, margin: '0 0 10px 0' }}>
            A {b.bank || 'su banco'}{cuenta ? `, cuenta ${formatAccountNumber(cuenta) || cuenta}` : ''}.
            Esto cierra la orden y le avisa al usuario que ya cobró: si todavía no
            transferiste, el reclamo va a aparecer cuando nadie se acuerde.
          </p>
          <div style={{ display: 'flex', gap: '9px', flexWrap: 'wrap' }}>
            <button type="button" onClick={onPagar} disabled={ocupado} style={{
              flex: '0 1 220px', padding: '10px', borderRadius: '9px', border: 'none',
              backgroundColor: COLOR.bien, color: '#fff', fontSize: '13px', fontWeight: 700,
              cursor: ocupado ? 'wait' : 'pointer',
            }} data-testid={`confirmar-pago-${w.transaction_id}`}>
              {ocupado ? 'Registrando…' : 'Sí, ya transferí'}
            </button>
            <button type="button" onClick={onCancelarConfirmacion} disabled={ocupado} style={{
              flex: '0 1 110px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
              border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
              color: COLOR.suave, fontSize: '13px', fontWeight: 600,
            }}>Volver</button>
          </div>
        </div>
      )}

      {rechazando && (
        <div style={{
          padding: '12px', borderRadius: '10px',
          backgroundColor: COLOR.maloSuave, border: `1px solid ${COLOR.maloBorde}`,
        }}>
          {/* Antes el motivo era fijo —«Rechazado por administrador»— así que al
              usuario le volvía la plata sin saber por qué, y volvía a intentar
              con el mismo error. */}
          <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: COLOR.malo, marginBottom: '5px' }}>
            Motivo del rechazo — se lo va a leer el usuario
          </label>
          <textarea value={motivo} onChange={(e) => onMotivo(e.target.value)} rows={2}
            placeholder="Ej.: la cuenta del beneficiario no existe en ese banco"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '9px 11px',
              borderRadius: '8px', border: `1px solid ${COLOR.maloBorde}`,
              fontSize: '13px', resize: 'vertical', fontFamily: 'inherit',
            }}
            data-testid={`motivo-${w.transaction_id}`}
          />
          <p style={{ fontSize: '11.5px', color: COLOR.malo, margin: '6px 0 0 0' }}>
            Se le devuelven {fmt(w.amount_input)} {w.currency_input} a su saldo.
          </p>
          <div style={{ display: 'flex', gap: '9px', marginTop: '9px', flexWrap: 'wrap' }}>
            <button type="button" onClick={onRechazar} disabled={ocupado || !motivo.trim()} style={{
              flex: '0 1 220px', padding: '10px', borderRadius: '9px', border: 'none',
              backgroundColor: motivo.trim() ? COLOR.malo : '#d1d5db', color: '#fff',
              fontSize: '13px', fontWeight: 700,
              cursor: (ocupado || !motivo.trim()) ? 'not-allowed' : 'pointer',
            }} data-testid={`confirmar-rechazo-${w.transaction_id}`}>
              {ocupado ? 'Rechazando…' : 'Rechazar y devolver'}
            </button>
            <button type="button" onClick={onCancelarRechazo} disabled={ocupado} style={{
              flex: '0 1 110px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
              border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
              color: COLOR.suave, fontSize: '13px', fontWeight: 600,
            }}>Volver</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Dato(props) {
  const { etiqueta, valor, falta, mono } = props;
  const Icono = props.Icono;
  return (
    <div style={{ backgroundColor: '#fff', padding: '10px 13px', minWidth: 0 }}>
      <p style={{
        fontSize: '10px', fontWeight: 700, letterSpacing: '0.5px',
        textTransform: 'uppercase', color: COLOR.tenue, margin: 0,
        display: 'flex', alignItems: 'center', gap: '4px',
      }}><Icono size={10} />{etiqueta}</p>
      <p style={{
        margin: '3px 0 0 0', fontSize: '13.5px', fontWeight: 600,
        color: falta ? COLOR.malo : COLOR.texto,
        wordBreak: 'break-word', ...(mono ? MONO : {}),
      }}>{valor || 'falta'}</p>
    </div>
  );
}
