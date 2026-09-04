/**
 * RecargasVES.jsx — La mesa de aprobación de recargas en bolívares.
 *
 * QUE ERA ESTO ANTES
 *   Una lista de tarjetas sueltas dentro de `AdminPanel.jsx`. Se pedían las 100
 *   recargas más nuevas de CUALQUIER estado y el navegador filtraba las
 *   pendientes. De ahí salían dos defectos que no se ven en un día tranquilo:
 *   con historial y nada pendiente la pantalla quedaba muda, y con más de cien
 *   recargas la pendiente más vieja se caía de la cola. Los dos se arreglaron
 *   en el servidor (`services/recargas_ves.py`); acá está lo que se ve.
 *
 * QUE HACE QUE UNA COLA SEA UNA COLA
 *   No es el color de los botones. Es que el operador pueda contestar, sin
 *   pensar, cuatro preguntas:
 *
 *     1. ¿CUANTO HAY Y CUANTO PESA?  → la franja de arriba: cuántas esperan,
 *        cuánta plata representan, y cuánto lleva parada la más vieja.
 *     2. ¿QUE MIRO PRIMERO?          → orden FIFO y un semáforo de antigüedad.
 *        Antes una orden de tres días y una de dos minutos se veían idénticas.
 *     3. ¿ESTA ES MIA?               → el candado por operador. El backend ya
 *        rechazaba con 409 si otro la estaba trabajando, y la pantalla no tenía
 *        forma de mostrarlo: al segundo operador le llegaba un error crudo.
 *     4. ¿PUEDO APROBARLA?           → lo que le falta a la orden, dicho antes
 *        de tocar el botón y no después del error.
 *
 * POR QUE APROBAR PIDE CONFIRMACION
 *   Aprobar acredita plata real y no tiene vuelta atrás. Antes era un clic
 *   suelto, y sólo pedía confirmación si la referencia estaba repetida. Acá el
 *   botón abre una barra que repite el monto y a quién se le acredita. Es la
 *   última pantalla donde un error todavía es gratis.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, Ban, Check, CheckCircle2, ChevronLeft, ChevronRight, Clock,
  FileImage, Landmark, Lock, LockOpen, RefreshCw, Search, ShieldAlert, User,
} from 'lucide-react';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { rutaDeArchivo, sePuedeAbrir } from '../../utils/urlDeArchivo';

const COLOR = {
  fondo: '#f7f8fa',
  borde: '#e5e7eb', bordeFuerte: '#d1d5db',
  suave: '#6b7280', tenue: '#9ca3af', texto: '#111827',
  primario: '#4F46E5', primarioSuave: '#eef0ff', primarioBorde: '#c7d2fe',
  bien: '#15803d', bienSuave: '#f0fdf4', bienBorde: '#bbf7d0',
  alerta: '#b45309', alertaSuave: '#fffbeb', alertaBorde: '#fde68a',
  malo: '#b91c1c', maloSuave: '#fef2f2', maloBorde: '#fecaca',
};

/* Los números de plata van con cifras de ancho fijo. Sin esto las columnas
   bailan entre una fila y otra y el ojo no puede comparar dos montos de un
   vistazo, que es exactamente lo que hace un operador todo el día. */
const CIFRAS = { fontVariantNumeric: 'tabular-nums', fontFeatureSettings: '"tnum"' };

const MONO = { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' };

const tarjeta = {
  backgroundColor: '#fff', borderRadius: '14px',
  border: `1px solid ${COLOR.borde}`,
};

const ESTADOS = [
  { clave: 'pending', etiqueta: 'Por aprobar', contador: 'pendientes' },
  { clave: 'approved', etiqueta: 'Aprobadas', contador: 'aprobadas' },
  { clave: 'rejected', etiqueta: 'Rechazadas', contador: 'rechazadas' },
  { clave: 'all', etiqueta: 'Todas', contador: 'total' },
];

const SEMAFORO = {
  normal: { fondo: COLOR.bienSuave, borde: COLOR.bienBorde, texto: COLOR.bien },
  atencion: { fondo: COLOR.alertaSuave, borde: COLOR.alertaBorde, texto: COLOR.alerta },
  urgente: { fondo: COLOR.maloSuave, borde: COLOR.maloBorde, texto: COLOR.malo },
  desconocida: { fondo: '#f3f4f6', borde: COLOR.borde, texto: COLOR.suave },
};

const POR_PAGINA = 50;

/** «hace 3 h», «hace 2 d». Un número de horas con dos decimales no le dice
 *  nada a nadie a las tres de la tarde. */
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
  const opciones = { timeZone: 'America/Caracas' };
  return `${d.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric', ...opciones })} · ${d.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: true, ...opciones })}`;
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

function Kpi({ etiqueta, valor, detalle, acento }) {
  return (
    <div style={{ padding: '14px 16px', minWidth: 0 }}>
      <p style={{
        fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.6px',
        textTransform: 'uppercase', color: COLOR.tenue, margin: 0,
      }}>{etiqueta}</p>
      <p style={{
        fontSize: '22px', fontWeight: 700, margin: '4px 0 0 0',
        color: acento || COLOR.texto, ...CIFRAS,
      }}>{valor}</p>
      {detalle ? (
        <p style={{ fontSize: '11.5px', color: COLOR.suave, margin: '2px 0 0 0' }}>{detalle}</p>
      ) : null}
    </div>
  );
}

export default function RecargasVES({ accountingBanks = [], user, onProcesada }) {
  const [estado, setEstado] = useState('pending');
  const [busqueda, setBusqueda] = useState('');
  const [buscado, setBuscado] = useState('');
  const [pagina, setPagina] = useState(0);
  const [datos, setDatos] = useState({ recharges: [], total: 0, counters: null });
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);

  const [digitos, setDigitos] = useState({});
  const [choques, setChoques] = useState({});
  const [bancoManual, setBancoManual] = useState({});
  const [confirmando, setConfirmando] = useState(null);
  const [rechazando, setRechazando] = useState(null);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(null);
  const [abierta, setAbierta] = useState(null);

  const vivo = useRef(true);

  const cargar = useCallback(async ({ silencioso = false } = {}) => {
    if (silencioso) setRefrescando(true); else setCargando(true);
    try {
      const res = await api.get('/admin/recharges/ves', {
        params: {
          status: estado, q: buscado,
          limit: POR_PAGINA, skip: pagina * POR_PAGINA,
        },
      });
      if (!vivo.current) return;
      setDatos(res.data || { recharges: [], total: 0, counters: null });
    } catch (e) {
      if (!vivo.current) return;
      toast.error(e?.response?.data?.detail || 'No se pudo leer la cola de recargas');
      setDatos((p) => ({ ...p, recharges: [] }));
    } finally {
      if (vivo.current) { setCargando(false); setRefrescando(false); }
    }
  }, [estado, buscado, pagina]);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  /* Se refresca solo, en silencio: dos operadores sobre la misma cola tienen
     que ver que una orden ya fue tomada sin apretar «Actualizar». */
  useEffect(() => {
    const t = setInterval(() => cargar({ silencioso: true }), 20000);
    return () => clearInterval(t);
  }, [cargar]);

  const contadores = datos.counters || {};
  const filas = datos.recharges || [];
  const totalPaginas = Math.max(1, Math.ceil((datos.total || 0) / POR_PAGINA));

  const bancosVES = useMemo(
    () => (accountingBanks || []).filter((b) => b.currency === 'VES'),
    [accountingBanks],
  );

  const buscar = (e) => {
    e.preventDefault();
    setPagina(0);
    setBuscado(busqueda.trim());
  };

  const cambiarEstado = (clave) => {
    setEstado(clave);
    setPagina(0);
    setAbierta(null);
    setConfirmando(null);
    setRechazando(null);
  };

  const verificarDigitos = async (txId, valor) => {
    const limpio = String(valor || '').replace(/\D/g, '').slice(0, 3);
    setDigitos((p) => ({ ...p, [txId]: limpio }));
    if (limpio.length !== 3) {
      setChoques((p) => ({ ...p, [txId]: null }));
      return;
    }
    try {
      const res = await api.get('/admin/recharges/ves/check-reference', {
        params: { digits: limpio, exclude_transaction_id: txId },
      });
      setChoques((p) => ({ ...p, [txId]: res.data }));
    } catch { /* el chequeo informa, no bloquea */ }
  };

  const tomar = async (r) => {
    setOcupado(r.transaction_id);
    try {
      const res = await api.post('/admin/ordenes/tomar', {
        orden_id: r.transaction_id, flujo: 'ves_ris',
      });
      if (res.data?.success) toast.success('Orden asignada a vos');
      else toast.error(`Ya la tomó ${res.data?.assigned_to_name || 'otro operador'}`);
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo tomar la orden');
    } finally { setOcupado(null); }
  };

  const liberar = async (r) => {
    setOcupado(r.transaction_id);
    try {
      await api.post('/admin/ordenes/liberar', {
        orden_id: r.transaction_id, flujo: 'ves_ris',
      });
      toast.success('Orden liberada');
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo liberar la orden');
    } finally { setOcupado(null); }
  };

  /* Al cerrar una orden se abre la que sigue en la cola. Sin esto, procesar
     cien es cerrar, buscar dónde estabas, y abrir la próxima: cien veces. */
  const siguiente = (idActual) => {
    const lista = datos.recharges || [];
    const i = lista.findIndex((x) => x.transaction_id === idActual);
    const proxima = lista.slice(i + 1).find((x) => x.status === 'pending');
    setAbierta(proxima ? proxima.transaction_id : null);
  };

  const aprobar = async (r) => {
    setOcupado(r.transaction_id);
    try {
      await api.post(`/admin/recharges/ves/process/${r.transaction_id}`, {
        action: 'approve',
        reference_digits: digitos[r.transaction_id] || '',
        bank_id: bancoManual[r.transaction_id] || undefined,
      });
      toast.success(`Acreditados ${fmt(r.amount_ris)} RI$ a ${r.user_name || r.user_email}`);
      setConfirmando(null);
      siguiente(r.transaction_id);
      onProcesada?.();
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo aprobar');
      await cargar({ silencioso: true });
    } finally { setOcupado(null); }
  };

  const rechazar = async (r) => {
    if (!motivo.trim()) { toast.error('Escribí el motivo del rechazo'); return; }
    setOcupado(r.transaction_id);
    try {
      await api.post(`/admin/recharges/ves/process/${r.transaction_id}`, {
        action: 'reject', rejection_reason: motivo.trim(),
      });
      toast.success('Recarga rechazada');
      setRechazando(null);
      setMotivo('');
      siguiente(r.transaction_id);
      onProcesada?.();
      await cargar({ silencioso: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo rechazar');
    } finally { setOcupado(null); }
  };

  const masVieja = contadores.mas_vieja || {};
  const semaforoCola = SEMAFORO[masVieja.nivel] || SEMAFORO.desconocida;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>

      {/* ── Franja de estado de la cola ────────────────────────────────── */}
      <div style={{ ...tarjeta, overflow: 'hidden' }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 16px', borderBottom: `1px solid ${COLOR.borde}`,
          gap: '12px', flexWrap: 'wrap',
        }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700, color: COLOR.texto, margin: 0 }}>
              Recargas en bolívares
            </h3>
            <p style={{ fontSize: '12px', color: COLOR.suave, margin: '2px 0 0 0' }}>
              Mesa de aprobación · se atiende por orden de llegada
            </p>
          </div>
          <button
            type="button" onClick={() => cargar({ silencioso: true })}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '8px 14px', borderRadius: '9px', cursor: 'pointer',
              border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
              color: COLOR.suave, fontSize: '13px', fontWeight: 600,
            }}
          >
            <RefreshCw size={14} style={refrescando ? { animation: 'spin 1s linear infinite' } : undefined} />
            Actualizar
          </button>
        </div>

        <div style={{
          display: 'grid', gap: '1px', backgroundColor: COLOR.borde,
          gridTemplateColumns: 'repeat(auto-fit, minmax(165px, 1fr))',
        }}>
          <div style={{ backgroundColor: '#fff' }}>
            <Kpi etiqueta="Esperando" valor={contadores.pendientes ?? '—'}
              detalle="órdenes por aprobar" />
          </div>
          <div style={{ backgroundColor: '#fff' }}>
            <Kpi etiqueta="Plata en cola" valor={`${fmt(contadores.ves_pendiente || 0)}`}
              detalle="VES sin acreditar" />
          </div>
          <div style={{ backgroundColor: '#fff' }}>
            <Kpi etiqueta="La más vieja" valor={espera(masVieja)}
              detalle="sin atender" acento={semaforoCola.texto} />
          </div>
          <div style={{ backgroundColor: '#fff' }}>
            <Kpi etiqueta="Trabadas" valor={(contadores.sin_banco || 0) + (contadores.sin_comprobante || 0)}
              detalle={`${contadores.sin_banco || 0} sin banco · ${contadores.sin_comprobante || 0} sin comprobante`}
              acento={(contadores.sin_banco || contadores.sin_comprobante) ? COLOR.alerta : undefined} />
          </div>
        </div>
      </div>

      {/* ── Filtros ────────────────────────────────────────────────────── */}
      <div style={{
        ...tarjeta, padding: '12px 14px', display: 'flex', gap: '10px',
        alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {ESTADOS.map(({ clave, etiqueta, contador }) => {
            const activo = estado === clave;
            const n = contadores[contador];
            return (
              <button
                key={clave} type="button" onClick={() => cambiarEstado(clave)}
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
        </div>

        <form onSubmit={buscar} style={{ display: 'flex', gap: '6px', flex: '1 1 240px', maxWidth: '380px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={15} style={{
              position: 'absolute', left: '11px', top: '50%',
              transform: 'translateY(-50%)', color: COLOR.tenue,
            }} />
            <input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Orden, usuario, mail o referencia…"
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '9px 12px 9px 34px', borderRadius: '9px',
                border: `1px solid ${COLOR.borde}`, fontSize: '13px', outline: 'none',
              }}
              data-testid="buscar-recarga"
            />
          </div>
          <button type="submit" style={{
            padding: '9px 15px', borderRadius: '9px', border: 'none', cursor: 'pointer',
            backgroundColor: COLOR.primario, color: '#fff', fontSize: '13px', fontWeight: 700,
          }}>Buscar</button>
        </form>
      </div>

      {/* ── La cola ────────────────────────────────────────────────────
          Una FILA por orden, no una tarjeta. Con tarjetas, cien órdenes eran
          doce mil píxeles de scroll: el operador perdía más tiempo buscando la
          próxima que procesándola. El detalle completo sigue estando, pero se
          abre sólo en la orden que se está trabajando —una por vez— así que la
          página no crece con la cola. */}
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
            {buscado ? 'Ninguna orden coincide con la búsqueda'
              : estado === 'pending' ? 'No hay recargas esperando'
                : 'No hay órdenes en este estado'}
          </p>
          <p style={{ fontSize: '13px', color: COLOR.suave, margin: '6px 0 0 0' }}>
            {buscado ? 'Probá con el número de orden, el mail o los tres dígitos de la referencia.'
              : 'La cola está al día.'}
          </p>
        </div>
      ) : (
        <div style={{ ...tarjeta, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{
              width: '100%', minWidth: '880px', borderCollapse: 'collapse',
              fontSize: '13px',
            }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb' }}>
                  {[
                    { t: '#', ancho: '38px', der: false },
                    { t: 'Orden', ancho: '116px', der: false },
                    { t: 'Espera', ancho: '92px', der: false },
                    { t: 'Usuario', ancho: 'auto', der: false },
                    { t: 'Recibimos', ancho: '128px', der: true },
                    { t: 'Acreditamos', ancho: '116px', der: true },
                    { t: 'Banco', ancho: '160px', der: false },
                    { t: '', ancho: '150px', der: true },
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
                {filas.map((r) => (
                  <Fila
                    key={r.transaction_id}
                    r={r}
                    user={user}
                    bancosVES={bancosVES}
                    abierta={abierta === r.transaction_id}
                    onAbrir={() => {
                      setConfirmando(null); setRechazando(null);
                      setAbierta(abierta === r.transaction_id ? null : r.transaction_id);
                    }}
                    digitos={digitos[r.transaction_id] || ''}
                    choque={choques[r.transaction_id]}
                    bancoElegido={bancoManual[r.transaction_id] || ''}
                    confirmando={confirmando === r.transaction_id}
                    rechazando={rechazando === r.transaction_id}
                    motivo={motivo}
                    ocupado={ocupado === r.transaction_id}
                    onDigitos={(v) => verificarDigitos(r.transaction_id, v)}
                    onBanco={(v) => setBancoManual((p) => ({ ...p, [r.transaction_id]: v }))}
                    onPedirConfirmacion={() => { setRechazando(null); setConfirmando(r.transaction_id); }}
                    onCancelarConfirmacion={() => setConfirmando(null)}
                    onAprobar={() => aprobar(r)}
                    onPedirRechazo={() => { setConfirmando(null); setMotivo(''); setRechazando(r.transaction_id); }}
                    onCancelarRechazo={() => { setRechazando(null); setMotivo(''); }}
                    onMotivo={setMotivo}
                    onRechazar={() => rechazar(r)}
                    onTomar={() => tomar(r)}
                    onLiberar={() => liberar(r)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Paginación ─────────────────────────────────────────────────── */}
      {datos.total > POR_PAGINA && (
        <div style={{
          ...tarjeta, padding: '11px 14px', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', gap: '10px',
        }}>
          <span style={{ fontSize: '12.5px', color: COLOR.suave, ...CIFRAS }}>
            {pagina * POR_PAGINA + 1}–{Math.min((pagina + 1) * POR_PAGINA, datos.total)} de {datos.total}
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            {[
              { icono: ChevronLeft, texto: 'Anterior', ir: () => setPagina((p) => Math.max(0, p - 1)), off: pagina === 0 },
              { icono: ChevronRight, texto: 'Siguiente', ir: () => setPagina((p) => p + 1), off: pagina + 1 >= totalPaginas },
            ].map((b) => {
              const { texto, ir, off } = b;
              const Icono = b.icono;
              return (
              <button
                key={texto} type="button" onClick={ir} disabled={off}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                  padding: '7px 12px', borderRadius: '8px', fontSize: '13px', fontWeight: 600,
                  border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
                  color: off ? COLOR.tenue : COLOR.texto,
                  cursor: off ? 'not-allowed' : 'pointer',
                }}
              >
                {texto === 'Anterior' ? <Icono size={14} /> : null}
                {texto}
                {texto === 'Siguiente' ? <Icono size={14} /> : null}
              </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Una orden: la fila, y su detalle ───────────────────────────────────
   La fila entra en una línea y dice lo justo para decidir si hay que abrirla:
   cuánto esperó, quién, cuánto, contra qué banco, y qué la traba. Lo demás
   —comprobante, elección de banco, referencia, aprobar y rechazar— vive en el
   detalle, que se abre en una sola orden por vez. */
function Fila(props) {
  const { r, user, abierta, onAbrir, ocupado, onTomar } = props;
  const pendiente = r.status === 'pending';
  const sem = SEMAFORO[r.antiguedad?.nivel] || SEMAFORO.desconocida;
  const mia = r.assigned_to && user?.user_id && r.assigned_to === user.user_id;
  const deOtro = r.assigned_to && !mia;
  const banco = r.destination_bank_name || r.destination_bank || null;

  const celda = {
    padding: '8px 10px', borderBottom: `1px solid ${COLOR.borde}`,
    verticalAlign: 'middle',
  };

  return (
    <>
      <tr
        onClick={onAbrir}
        style={{
          cursor: 'pointer',
          backgroundColor: abierta ? COLOR.primarioSuave : deOtro ? '#fafafa' : '#fff',
        }}
        data-testid={`recarga-${r.transaction_id}`}
      >
        <td style={{ ...celda, color: COLOR.tenue, ...CIFRAS, fontSize: '12px' }}>
          {pendiente && r.posicion ? r.posicion : ''}
        </td>

        <td style={{ ...celda, whiteSpace: 'nowrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <ChevronRight size={13} style={{
              color: COLOR.tenue, flexShrink: 0,
              transform: abierta ? 'rotate(90deg)' : 'none', transition: 'transform .12s',
            }} />
            <span style={{ ...MONO, fontSize: '12.5px', fontWeight: 700, color: COLOR.texto }}>
              {r.referencia}
            </span>
          </div>
        </td>

        <td style={{ ...celda, whiteSpace: 'nowrap' }}>
          {pendiente ? (
            <Chip {...sem} titulo={`Ingresó ${fechaHora(r.created_at)}`}>
              <Clock size={10} />{espera(r.antiguedad)}
            </Chip>
          ) : (
            <Chip
              fondo={r.status === 'approved' ? COLOR.bienSuave : COLOR.maloSuave}
              borde={r.status === 'approved' ? COLOR.bienBorde : COLOR.maloBorde}
              texto={r.status === 'approved' ? COLOR.bien : COLOR.malo}
              titulo={fechaHora(r.processed_at)}
            >
              {r.status === 'approved' ? <Check size={10} /> : <Ban size={10} />}
              {r.status === 'approved' ? 'Aprobada' : 'Rechazada'}
            </Chip>
          )}
        </td>

        <td style={{ ...celda, maxWidth: 0 }}>
          <div style={{
            fontWeight: 600, color: COLOR.texto, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }} title={r.user_email}>
            {r.user_name || r.user_email || '—'}
          </div>
        </td>

        <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap', ...CIFRAS, fontWeight: 600 }}>
          {fmt(r.amount_ves)}
        </td>

        <td style={{
          ...celda, textAlign: 'right', whiteSpace: 'nowrap',
          ...CIFRAS, fontWeight: 700, color: COLOR.bien,
        }}>
          {fmt(r.amount_ris)}
        </td>

        <td style={{ ...celda, maxWidth: 0 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '5px', minWidth: 0,
            color: banco ? COLOR.suave : COLOR.alerta, fontSize: '12px',
          }} title={banco || 'sin registrar'}>
            <Landmark size={11} style={{ flexShrink: 0 }} />
            <span style={{
              minWidth: 0, overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>{banco || 'sin registrar'}</span>
          </div>
        </td>

        {/* Lo que traba la orden, en iconos: se puede saltear una fila sin
            abrirla. Con el detalle desplegado había que bajar hasta el fondo
            de cada tarjeta para descubrir que faltaba el comprobante. */}
        <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            {pendiente && r.falta_comprobante ? (
              <FileImage size={14} style={{ color: COLOR.malo }} aria-label="Sin comprobante" />
            ) : null}
            {pendiente && r.falta_banco ? (
              <AlertTriangle size={14} style={{ color: COLOR.alerta }} aria-label="Sin banco" />
            ) : null}
            {deOtro ? (
              <span title={`La tiene ${r.assigned_to_name || 'otro operador'}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '3px',
                  fontSize: '11px', fontWeight: 700, color: COLOR.alerta,
                  maxWidth: '84px', overflow: 'hidden', whiteSpace: 'nowrap',
                }}>
                <Lock size={11} />{r.assigned_to_name || 'otro'}
              </span>
            ) : mia ? (
              <Chip fondo={COLOR.primarioSuave} borde={COLOR.primarioBorde} texto={COLOR.primario}>
                <Lock size={10} />Tuya
              </Chip>
            ) : pendiente ? (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onTomar(); }}
                disabled={ocupado}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                  padding: '4px 9px', borderRadius: '7px', fontSize: '11.5px', fontWeight: 700,
                  border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
                  color: COLOR.suave, cursor: ocupado ? 'wait' : 'pointer',
                }}
                data-testid={`tomar-${r.transaction_id}`}
              >
                <Lock size={11} />Tomar
              </button>
            ) : null}
          </div>
        </td>
      </tr>

      {abierta ? (
        <tr>
          <td colSpan={8} style={{
            padding: 0, borderBottom: `1px solid ${COLOR.borde}`,
            backgroundColor: '#fbfbfd',
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
    r, user, bancosVES, digitos, choque, bancoElegido, confirmando, rechazando,
    motivo, ocupado, onDigitos, onBanco, onPedirConfirmacion,
    onCancelarConfirmacion, onAprobar, onPedirRechazo, onCancelarRechazo,
    onMotivo, onRechazar, onLiberar,
  } = props;

  const pendiente = r.status === 'pending';
  const mia = r.assigned_to && user?.user_id && r.assigned_to === user.user_id;
  const bancoResuelto = !r.falta_banco || !!bancoElegido;
  const puedeAprobar = bancoResuelto && !ocupado;
  const banco = r.destination_bank_name || r.destination_bank || null;

  return (
    <div style={{ padding: '14px 16px', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>

      {/* El comprobante, grande: es lo único que hay que MIRAR. */}
      {sePuedeAbrir(r.proof_image) ? (
        <a href={rutaDeArchivo(r.proof_image)} target="_blank" rel="noreferrer" title="Abrir el comprobante"
          style={{
            flexShrink: 0, display: 'block', width: '150px', height: '150px',
            borderRadius: '10px', overflow: 'hidden', cursor: 'zoom-in',
            border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
          }}>
          <img src={rutaDeArchivo(r.proof_image)} alt="Comprobante"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        </a>
      ) : (
        <div style={{
          flexShrink: 0, width: '150px', height: '150px', borderRadius: '10px',
          border: `1px dashed ${COLOR.maloBorde}`, backgroundColor: COLOR.maloSuave,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', gap: '7px', textAlign: 'center', padding: '12px',
        }}>
          <FileImage size={22} style={{ color: COLOR.malo }} />
          <span style={{ fontSize: '11.5px', fontWeight: 700, color: COLOR.malo, lineHeight: 1.3 }}>
            Sin comprobante
          </span>
          <span style={{ fontSize: '10.5px', color: COLOR.malo, lineHeight: 1.3 }}>
            No hay contra qué verificar
          </span>
        </div>
      )}

      <div style={{ flex: '1 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>

        <div style={{
          display: 'flex', gap: '18px', flexWrap: 'wrap', fontSize: '12px',
          color: COLOR.suave, alignItems: 'center',
        }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
            <User size={12} />{r.user_email || '—'}
          </span>
          <span style={{ ...CIFRAS }}>1 RI$ = {fmt(r.rate_used)} VES</span>
          <span>{fechaHora(r.created_at)} · Caracas</span>
          {mia && pendiente ? (
            <button type="button" onClick={onLiberar} disabled={ocupado} style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              padding: '3px 9px', borderRadius: '7px', fontSize: '11.5px', fontWeight: 600,
              border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
              color: COLOR.suave, cursor: ocupado ? 'wait' : 'pointer',
            }}><LockOpen size={11} />Liberar</button>
          ) : null}
        </div>

        {!pendiente && (
          <div style={{
            padding: '9px 12px', borderRadius: '9px', backgroundColor: '#fff',
            border: `1px solid ${COLOR.borde}`, fontSize: '12px', color: COLOR.suave,
          }}>
            <div>Procesada {fechaHora(r.processed_at)}{r.processed_by ? ` · por ${r.processed_by}` : ''}</div>
            {r.reference_digits ? <div>Referencia terminada en <strong style={MONO}>{r.reference_digits}</strong></div> : null}
            {r.rejection_reason ? (
              <div style={{ color: COLOR.malo, marginTop: '3px' }}>Motivo: {r.rejection_reason}</div>
            ) : null}
            {r.banco_elegido_a_mano ? (
              <div style={{ color: COLOR.alerta, marginTop: '3px' }}>El banco lo eligió a mano un operador.</div>
            ) : null}
          </div>
        )}

        {pendiente && (
          <>
            {r.falta_comprobante && (
              <Aviso tono="malo" Icono={AlertTriangle}>
                Confirmalo con el usuario antes de acreditar: sin comprobante no hay contra
                qué verificar el monto ni la referencia.
              </Aviso>
            )}

            {r.falta_banco && (
              <div style={{
                padding: '10px 12px', borderRadius: '10px',
                backgroundColor: COLOR.alertaSuave, border: `1px solid ${COLOR.alertaBorde}`,
              }}>
                <div style={{ display: 'flex', gap: '8px', fontSize: '12px', color: COLOR.alerta }}>
                  <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
                  <span>
                    Sin banco destino registrado. <strong>No es un error del usuario</strong>: se
                    perdió al crearse. Elegí a qué banco entró la plata, mirando el comprobante.
                    Queda anotado quién lo eligió y cuándo.
                  </span>
                </div>
                <select
                  value={bancoElegido}
                  onChange={(e) => onBanco(e.target.value)}
                  style={{
                    marginTop: '8px', width: '100%', maxWidth: '340px',
                    padding: '8px 11px', borderRadius: '8px',
                    border: `1px solid ${COLOR.alerta}`, fontSize: '13px', backgroundColor: '#fff',
                  }}
                  data-testid={`bank-select-${r.transaction_id}`}
                >
                  <option value="">Elegí el banco…</option>
                  {bancosVES.map((b) => (
                    <option key={b.bank_id} value={b.bank_id}>{b.name}</option>
                  ))}
                </select>
                {bancosVES.length === 0 && (
                  <div style={{ marginTop: '6px', fontSize: '11.5px', color: COLOR.alerta }}>
                    No hay ningún banco en VES cargado en Contabilidad, así que esta orden no se
                    puede aprobar. Cargalo en <strong>Contabilidad → Bancos</strong> y volvé.
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <label style={{ fontSize: '12px', fontWeight: 700, color: COLOR.texto }}>
                Últimos 3 dígitos de la referencia
              </label>
              <input
                value={digitos}
                onChange={(e) => onDigitos(e.target.value)}
                inputMode="numeric" maxLength={3} placeholder="000"
                style={{
                  ...MONO, ...CIFRAS, width: '84px', padding: '8px 10px',
                  borderRadius: '8px', border: `1px solid ${COLOR.bordeFuerte}`,
                  fontSize: '15px', letterSpacing: '4px', textAlign: 'center',
                }}
                data-testid={`ref-${r.transaction_id}`}
              />
              <span style={{ fontSize: '11.5px', color: COLOR.tenue }}>
                Detecta que el mismo pago se acredite dos veces.
              </span>
            </div>

            {choque?.has_collision && (
              <Aviso tono="malo" Icono={ShieldAlert}>
                Esta referencia ya aparece en una recarga de otro usuario: posible pago
                duplicado.
                {choque.first_registered ? (
                  <> La registró primero <strong>{choque.first_registered.user_name
                    || choque.first_registered.user_email}</strong>, y el saldo le corresponde
                    a quien la registró primero.</>
                ) : null}
              </Aviso>
            )}

            {!confirmando && !rechazando && (
              <div style={{ display: 'flex', gap: '9px', flexWrap: 'wrap' }}>
                <button
                  type="button" onClick={onPedirConfirmacion} disabled={!puedeAprobar}
                  title={!bancoResuelto ? 'Falta elegir el banco destino' : undefined}
                  style={{
                    flex: '0 1 220px', padding: '10px', borderRadius: '9px', border: 'none',
                    backgroundColor: puedeAprobar ? COLOR.bien : '#d1d5db',
                    color: '#fff', fontSize: '13px', fontWeight: 700,
                    cursor: puedeAprobar ? 'pointer' : 'not-allowed',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
                  }}
                  data-testid={`approve-recharge-${r.transaction_id}`}
                >
                  <Check size={15} />Aprobar y acreditar
                </button>
                <button
                  type="button" onClick={onPedirRechazo}
                  style={{
                    flex: '0 1 150px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
                    border: `1px solid ${COLOR.maloBorde}`, backgroundColor: '#fff',
                    color: COLOR.malo, fontSize: '13px', fontWeight: 700,
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '7px',
                  }}
                  data-testid={`reject-recharge-${r.transaction_id}`}
                >
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
                  Vas a acreditar {fmt(r.amount_ris)} RI$ a {r.user_name || r.user_email}
                </p>
                <p style={{ fontSize: '12px', color: COLOR.suave, margin: '0 0 10px 0' }}>
                  Contra {fmt(r.amount_ves)} VES recibidos en {banco || bancosVES.find((b) => b.bank_id === bancoElegido)?.name || '—'}
                  {digitos ? <>, referencia terminada en <strong style={MONO}>{digitos}</strong></> : ', sin referencia cargada'}.
                  Acredita saldo real y no se puede deshacer.
                </p>
                <div style={{ display: 'flex', gap: '9px', flexWrap: 'wrap' }}>
                  <button
                    type="button" onClick={onAprobar} disabled={ocupado}
                    style={{
                      flex: '0 1 200px', padding: '10px', borderRadius: '9px', border: 'none',
                      backgroundColor: COLOR.bien, color: '#fff', fontSize: '13px', fontWeight: 700,
                      cursor: ocupado ? 'wait' : 'pointer',
                    }}
                    data-testid={`confirm-approve-${r.transaction_id}`}
                  >
                    {ocupado ? 'Acreditando…' : 'Sí, acreditar ahora'}
                  </button>
                  <button
                    type="button" onClick={onCancelarConfirmacion} disabled={ocupado}
                    style={{
                      flex: '0 1 110px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
                      border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
                      color: COLOR.suave, fontSize: '13px', fontWeight: 600,
                    }}
                  >Volver</button>
                </div>
              </div>
            )}

            {rechazando && (
              <div style={{
                padding: '12px', borderRadius: '10px',
                backgroundColor: COLOR.maloSuave, border: `1px solid ${COLOR.maloBorde}`,
              }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: COLOR.malo, marginBottom: '5px' }}>
                  Motivo del rechazo — se lo va a leer el usuario
                </label>
                <textarea
                  value={motivo} onChange={(e) => onMotivo(e.target.value)} rows={2}
                  placeholder="Ej.: el comprobante muestra 80.000 VES y la solicitud dice 100.000"
                  style={{
                    width: '100%', boxSizing: 'border-box', padding: '9px 11px',
                    borderRadius: '8px', border: `1px solid ${COLOR.maloBorde}`,
                    fontSize: '13px', resize: 'vertical', fontFamily: 'inherit',
                  }}
                  data-testid={`motivo-${r.transaction_id}`}
                />
                <div style={{ display: 'flex', gap: '9px', marginTop: '9px', flexWrap: 'wrap' }}>
                  <button
                    type="button" onClick={onRechazar} disabled={ocupado || !motivo.trim()}
                    style={{
                      flex: '0 1 200px', padding: '10px', borderRadius: '9px', border: 'none',
                      backgroundColor: motivo.trim() ? COLOR.malo : '#d1d5db', color: '#fff',
                      fontSize: '13px', fontWeight: 700,
                      cursor: (ocupado || !motivo.trim()) ? 'not-allowed' : 'pointer',
                    }}
                    data-testid={`confirm-reject-${r.transaction_id}`}
                  >
                    {ocupado ? 'Rechazando…' : 'Rechazar la recarga'}
                  </button>
                  <button
                    type="button" onClick={onCancelarRechazo} disabled={ocupado}
                    style={{
                      flex: '0 1 110px', padding: '10px', borderRadius: '9px', cursor: 'pointer',
                      border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
                      color: COLOR.suave, fontSize: '13px', fontWeight: 600,
                    }}
                  >Volver</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Aviso(props) {
  const { tono, children } = props;
  const Icono = props.Icono;
  const c = tono === 'malo'
    ? { fondo: COLOR.maloSuave, borde: COLOR.maloBorde, texto: COLOR.malo }
    : { fondo: COLOR.alertaSuave, borde: COLOR.alertaBorde, texto: COLOR.alerta };
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: '8px',
      padding: '10px 13px', borderRadius: '10px', fontSize: '12.5px',
      backgroundColor: c.fondo, border: `1px solid ${c.borde}`, color: c.texto,
    }}>
      <Icono size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
      <span>{children}</span>
    </div>
  );
}
