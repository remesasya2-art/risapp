/**
 * Nucleo — el laboratorio del núcleo de cuentas, sólo para el super
 * administrador.
 *
 * QUE ES
 *
 *   La arquitectura de fintech que se construye mientras se resuelve lo
 *   legal: cuentas de pago, partida doble nativa, libro encadenado por hash,
 *   cierre diario. Acá se prueba con plata de mentira: crear cuentas,
 *   acreditar, debitar, transferir, cobrar una tarifa, mirar el libro, ver el
 *   balance cuadrar, verificar la cadena y cerrar el día. Y la cola: cada
 *   asiento deja un evento, el trabajador lo convierte en un trabajo, y acá
 *   se ve pasar por pendiente, en curso, hecho o muerto — con dos trabajos
 *   de muestra para encolar a mano, uno que termina bien y uno que falla.
 *   Y los rieles: cobrar por PIX (un QR con el BR Code de verdad), pagar a
 *   una clave, devolver, consultar el DICT — contra un simulador con claves
 *   de prueba que se portan distinto (una rechaza, una tarda).
 *
 * APAGADO DE FABRICA
 *
 *   Con «Núcleo de cuentas» en 0 (Configuración), el servidor contesta 404 a
 *   todo, y esta pestaña dice eso y nada más. Los clientes no tienen ninguna
 *   puerta a esto: ni ruta, ni botón, ni clave en `/limits`. Hay tests que
 *   lo sostienen (backend/tests/test_nucleo_apagado_de_fabrica.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { Landmark, Plus, RefreshCw, ShieldCheck, ShieldAlert, Lock, Play, RotateCcw, QrCode, Send, Search, Undo2 } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

const tarjeta = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 16px' };
const rotulo = { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280', marginBottom: 4 };
const campo = { width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14 };
const boton = { padding: '9px 14px', borderRadius: 8, border: 'none', background: '#5B4FE9', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 };
const botonSuave = { ...boton, background: '#eef2ff', color: '#3B3A9E' };
const th = { textAlign: 'left', fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4, padding: '6px 8px', borderBottom: '1px solid #e5e7eb' };
const td = { padding: '7px 8px', borderBottom: '1px solid #f3f4f6', fontSize: 13, verticalAlign: 'top' };
const mono = { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 };
const centavos = (n) => (n / 100).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—');

// El color de cada estado de la cola. Muerto en rojo porque es lo único que
// pide que una persona haga algo.
const COLOR_DEL_ESTADO = {
  pendiente: { background: '#fef3c7', color: '#92400e' },
  en_curso: { background: '#dbeafe', color: '#1e40af' },
  hecho: { background: '#dcfce7', color: '#166534' },
  muerto: { background: '#fee2e2', color: '#991b1b' },
  // los de una operación por un riel
  activa: { background: '#e0e7ff', color: '#3730a3' },
  enviada: { background: '#dbeafe', color: '#1e40af' },
  liquidada: { background: '#dcfce7', color: '#166534' },
  rechazada: { background: '#fee2e2', color: '#991b1b' },
};
const DIRECCION = { entrada: 'Cobro', salida: 'Pago', devolucion: 'Devolución' };
const Etiqueta = ({ valor }) => (
  <span style={{ ...(COLOR_DEL_ESTADO[valor] || {}), padding: '2px 8px', borderRadius: 999, fontSize: 12, fontWeight: 600 }}>
    {valor === 'en_curso' ? 'en curso' : valor}
  </span>
);

export default function Nucleo() {
  const [estado, setEstado] = useState(null);       // null: cargando; {apagado:true}: 404
  const [cuentas, setCuentas] = useState([]);
  const [libro, setLibro] = useState([]);
  const [balance, setBalance] = useState(null);
  const [cierres, setCierres] = useState([]);
  const [cola, setCola] = useState(null);
  const [rieles, setRieles] = useState(null);
  const [cobro, setCobro] = useState({ cuenta: '', monto: '', descripcion: '' });
  const [ultimoCobro, setUltimoCobro] = useState(null);
  const [pago, setPago] = useState({ cuenta: '', clave: '', monto: '', descripcion: '' });
  const [titularDeLaClave, setTitularDeLaClave] = useState(null);
  const [devolviendo, setDevolviendo] = useState(null);   // { id, monto } del cobro que se está devolviendo
  const [vuelta, setVuelta] = useState(0);
  const [titular, setTitular] = useState('');
  const [mov, setMov] = useState({ tipo: 'acreditar', cuenta: '', desde: '', hacia: '', monto: '', referencia: '', descripcion: '' });
  const [diaCierre, setDiaCierre] = useState(() => new Date().toISOString().slice(0, 10));
  const [ocupado, setOcupado] = useState(false);

  const recargar = useCallback(() => setVuelta((v) => v + 1), []);

  useEffect(() => {
    let vigente = true;
    api.get('/nucleo/estado')
      .then(async (r) => {
        if (!vigente) return;
        setEstado(r.data);
        if (!r.data?.conectada) return;
        const [c, l, b, z, q, rl] = await Promise.all([
          api.get('/nucleo/laboratorio/cuentas'), api.get('/nucleo/laboratorio/libro?limite=30'),
          api.get('/nucleo/laboratorio/balance'), api.get('/nucleo/laboratorio/cierres'),
          api.get('/nucleo/laboratorio/cola?limite=30'), api.get('/nucleo/laboratorio/rieles?limite=30'),
        ]);
        if (!vigente) return;
        setCuentas(c.data || []); setLibro(l.data || []); setBalance(b.data || null); setCierres(z.data || []);
        setCola(q.data || null); setRieles(rl.data || null);
      })
      .catch((e) => {
        if (!vigente) return;
        // 404 es «apagado»: el servidor no anuncia lo que no está prendido.
        setEstado({ apagado: true, status: e?.response?.status });
      });
    return () => { vigente = false; };
  }, [vuelta]);

  const crearCuenta = async () => {
    if (!titular.trim()) return toast.error('Poné una referencia del titular (de prueba)');
    setOcupado(true);
    try {
      await api.post('/nucleo/laboratorio/cuentas', { titular_ref: titular.trim() });
      setTitular(''); toast.success('Cuenta de prueba creada'); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo crear'); }
    finally { setOcupado(false); }
  };

  const mover = async () => {
    setOcupado(true);
    try {
      const cuerpo = { tipo: mov.tipo, monto: mov.monto, referencia: mov.referencia || `lab-${Date.now()}` };
      if (mov.descripcion) cuerpo.descripcion = mov.descripcion;
      if (mov.tipo === 'transferir') { cuerpo.desde = mov.desde; cuerpo.hacia = mov.hacia; } else { cuerpo.cuenta = mov.cuenta; }
      const r = await api.post('/nucleo/laboratorio/movimientos', cuerpo);
      toast.success(`Asiento Nº ${r.data.numero}`);
      setMov((m) => ({ ...m, monto: '', referencia: '', descripcion: '' })); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo asentar'); }
    finally { setOcupado(false); }
  };

  const cerrar = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/cierres', { dia: diaCierre });
      toast.success(`Día ${r.data.dia} cerrado hasta el asiento ${r.data.hasta_asiento}`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo cerrar'); }
    finally { setOcupado(false); }
  };

  const encolar = async (tipo) => {
    setOcupado(true);
    try {
      const carga = tipo === 'eco' ? { mensaje: `hola desde el panel ${new Date().toLocaleTimeString('es-AR')}` } : { motivo: 'Falla a propósito, para ver la cola de muertos.' };
      const r = await api.post('/nucleo/laboratorio/cola/trabajos', { tipo, carga });
      toast.success(`Trabajo Nº ${r.data.id} encolado`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo encolar'); }
    finally { setOcupado(false); }
  };

  const procesar = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/cola/paso');
      const d = r.data;
      toast.success(`Despachados ${d.despachados} · corridos ${d.corridos} (hechos ${d.hechos}, reintentan ${d.reintentan}, muertos ${d.muertos})`);
      recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo procesar'); }
    finally { setOcupado(false); }
  };

  const reintentar = async (id) => {
    setOcupado(true);
    try {
      await api.post(`/nucleo/laboratorio/cola/trabajos/${id}/reintentar`);
      toast.success(`Trabajo Nº ${id} de vuelta en la cola`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo reintentar'); }
    finally { setOcupado(false); }
  };

  // Después de tocar un riel se procesa la cola enseguida y se recarga: el
  // trabajador también lo haría solo en unos segundos, pero acá se quiere
  // ver el resultado sin esperar.
  const procesarYRecargar = async () => {
    try { await api.post('/nucleo/laboratorio/cola/paso'); } catch { /* el trabajador lo hará solo */ }
    recargar();
  };

  const generarCobro = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/rieles/cobros', { cuenta: cobro.cuenta, monto: cobro.monto, descripcion: cobro.descripcion || undefined });
      setUltimoCobro(r.data); toast.success(`Cobro ${r.data.id} generado`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo generar el cobro'); }
    finally { setOcupado(false); }
  };

  const simularPago = async (op) => {
    setOcupado(true);
    try {
      await api.post(`/nucleo/laboratorio/rieles/cobros/${op.id}/simular_pago`, {});
      toast.success('Llegó el crédito del SPI'); await procesarYRecargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo simular'); }
    finally { setOcupado(false); }
  };

  const consultarClave = async () => {
    if (!pago.clave.trim()) return;
    setTitularDeLaClave(null);
    try {
      const r = await api.get(`/nucleo/laboratorio/rieles/claves/${encodeURIComponent(pago.clave.trim())}`);
      setTitularDeLaClave(r.data);
    } catch (e) { setTitularDeLaClave({ error: e?.response?.data?.detail || 'No se pudo consultar' }); }
  };

  const pagar = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/rieles/pagos', { cuenta: pago.cuenta, clave: pago.clave.trim(), monto: pago.monto, descripcion: pago.descripcion || undefined });
      toast.success(`Pago ${r.data.id} ordenado (${r.data.end_to_end})`);
      setPago((p) => ({ ...p, monto: '', descripcion: '' })); await procesarYRecargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo ordenar el pago'); }
    finally { setOcupado(false); }
  };

  const simularResultado = async (op, estadoFinal) => {
    setOcupado(true);
    try {
      await api.post(`/nucleo/laboratorio/rieles/pagos/${op.id}/simular_resultado`, estadoFinal === 'RJCT' ? { estado: 'RJCT', motivo: 'AB03' } : { estado: 'ACSC' });
      toast.success('El SPI contestó'); await procesarYRecargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo simular'); }
    finally { setOcupado(false); }
  };

  // Una devolución puede ser parcial, y sale de la cuenta del titular, que
  // puede haber gastado parte de lo que cobró: se pregunta cuánto, en la
  // misma fila (nunca con un cuadro del navegador: hay un guardián).
  const devolver = async () => {
    if (!devolviendo) return;
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/rieles/devoluciones', { operacion: devolviendo.id, monto: devolviendo.monto.trim(), motivo: 'MD06' });
      toast.success(`Devolución ${r.data.id} ordenada`); setDevolviendo(null); await procesarYRecargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo devolver'); }
    finally { setOcupado(false); }
  };

  if (estado === null) return <p style={{ color: '#6b7280' }}>Cargando…</p>;

  if (estado.apagado) {
    return (
      <div style={{ ...tarjeta, display: 'flex', gap: 14, alignItems: 'flex-start' }} data-testid="nucleo-apagado">
        <Lock size={22} color="#6b7280" />
        <div>
          <p style={{ margin: '0 0 6px', fontWeight: 700, color: '#111827' }}>El núcleo de cuentas está apagado</p>
          <p style={{ margin: 0, fontSize: 14, color: '#6b7280', lineHeight: 1.5 }}>
            Es la arquitectura de fintech que se construye mientras se resuelve lo legal. Se prende desde
            Configuración → «Núcleo de cuentas (fintech)» en 1 (laboratorio). Los clientes no lo ven en ningún modo.
          </p>
        </div>
      </div>
    );
  }

  const cadena = estado.cadena;
  return (
    <div style={{ display: 'grid', gap: 16 }} data-testid="nucleo">
      {/* Estado */}
      <div style={{ ...tarjeta, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14 }}>
        <div><div style={rotulo}>Modo</div><div style={{ fontWeight: 700 }}>{estado.modo_nombre}</div></div>
        <div><div style={rotulo}>Base</div><div style={{ fontWeight: 700 }}>{estado.conectada ? estado.base : 'sin configurar'}</div></div>
        <div><div style={rotulo}>Cuentas</div><div style={{ fontWeight: 700 }}>{estado.cuentas}</div></div>
        <div><div style={rotulo}>Asientos</div><div style={{ fontWeight: 700 }}>{estado.asientos}</div></div>
        <div><div style={rotulo}>Último cierre</div><div style={{ fontWeight: 700 }}>{estado.ultimo_cierre || '—'}</div></div>
        <div>
          <div style={rotulo}>Cola</div>
          <div style={{ fontWeight: 700, color: estado.cola?.muerto ? '#b91c1c' : undefined }} data-testid="nucleo-cola-resumen">
            {estado.cola ? `${estado.cola.pendiente} pendientes · ${estado.cola.muerto} muertos` : '—'}
          </div>
        </div>
        <div>
          <div style={rotulo}>Cadena</div>
          <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, color: cadena?.ok ? '#15803d' : '#b91c1c' }} data-testid="nucleo-cadena">
            {cadena ? (cadena.ok ? <><ShieldCheck size={16} /> íntegra</> : <><ShieldAlert size={16} /> rota en {cadena.roto_en}</>) : '—'}
          </div>
        </div>
      </div>

      {!estado.conectada ? (
        <div style={{ ...tarjeta, background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontSize: 14 }}>
          El núcleo no tiene base: falta <code>NUCLEO_DATABASE_URL</code> en el entorno del servidor (un Postgres aparte).
          {estado.detalle ? <> Detalle: {estado.detalle}.</> : null}
        </div>
      ) : null}

      {estado.conectada ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {/* Cuentas */}
            <div style={tarjeta}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Landmark size={16} /> Cuentas de prueba</strong>
                <button type="button" onClick={recargar} style={{ ...botonSuave, padding: '6px 10px' }}><RefreshCw size={13} /></button>
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <input style={campo} placeholder="Referencia del titular (p. ej. u_ana)" value={titular}
                  onChange={(e) => setTitular(e.target.value)} data-testid="nucleo-titular" />
                <button type="button" onClick={crearCuenta} disabled={ocupado} style={boton} data-testid="nucleo-crear-cuenta"><Plus size={14} /></button>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Cuenta</th><th style={th}>Titular</th><th style={{ ...th, textAlign: 'right' }}>Saldo</th></tr></thead>
                <tbody>
                  {cuentas.length === 0 ? <tr><td style={td} colSpan={3}>Todavía no hay cuentas.</td></tr> : cuentas.map((c) => (
                    <tr key={c.id}><td style={{ ...td, ...mono }}>{c.id}</td><td style={td}>{c.titular_ref}</td>
                      <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>R$ {c.saldo.replace('.', ',')}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Movimiento */}
            <div style={tarjeta}>
              <strong>Asentar un movimiento</strong>
              <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
                <select style={campo} value={mov.tipo} onChange={(e) => setMov({ ...mov, tipo: e.target.value })} data-testid="nucleo-tipo">
                  <option value="acreditar">Acreditar (entra plata a la cuenta)</option>
                  <option value="debitar">Debitar (sale plata de la cuenta)</option>
                  <option value="transferir">Transferir entre cuentas</option>
                  <option value="tarifa">Cobrar una tarifa</option>
                </select>
                {mov.tipo === 'transferir' ? (
                  <>
                    <select style={campo} value={mov.desde} onChange={(e) => setMov({ ...mov, desde: e.target.value })} data-testid="nucleo-desde">
                      <option value="">Desde…</option>{cuentas.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.titular_ref}</option>)}
                    </select>
                    <select style={campo} value={mov.hacia} onChange={(e) => setMov({ ...mov, hacia: e.target.value })} data-testid="nucleo-hacia">
                      <option value="">Hacia…</option>{cuentas.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.titular_ref}</option>)}
                    </select>
                  </>
                ) : (
                  <select style={campo} value={mov.cuenta} onChange={(e) => setMov({ ...mov, cuenta: e.target.value })} data-testid="nucleo-cuenta">
                    <option value="">Cuenta…</option>{cuentas.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.titular_ref}</option>)}
                  </select>
                )}
                <input style={campo} placeholder="Monto en reales, p. ej. 100.00" value={mov.monto} inputMode="decimal"
                  onChange={(e) => setMov({ ...mov, monto: e.target.value })} data-testid="nucleo-monto" />
                <input style={campo} placeholder="Referencia (idempotencia; vacía = una nueva)" value={mov.referencia}
                  onChange={(e) => setMov({ ...mov, referencia: e.target.value })} data-testid="nucleo-referencia" />
                <input style={campo} placeholder="Descripción (opcional)" value={mov.descripcion}
                  onChange={(e) => setMov({ ...mov, descripcion: e.target.value })} />
                <button type="button" onClick={mover} disabled={ocupado} style={boton} data-testid="nucleo-asentar">Asentar</button>
              </div>
            </div>
          </div>

          {/* Libro */}
          <div style={tarjeta}>
            <strong>Libro (últimos {libro.length})</strong>
            <div style={{ overflowX: 'auto', marginTop: 8 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }} data-testid="nucleo-libro">
                <thead><tr><th style={th}>Nº</th><th style={th}>Fecha</th><th style={th}>Comando</th><th style={th}>Descripción</th><th style={th}>Partidas</th><th style={th}>Hash</th></tr></thead>
                <tbody>
                  {libro.length === 0 ? <tr><td style={td} colSpan={6}>Todavía no hay asientos.</td></tr> : libro.map((a) => (
                    <tr key={a.numero}>
                      <td style={{ ...td, ...mono }}>{a.numero}</td><td style={td}>{a.fecha}</td><td style={td}>{a.comando}</td>
                      <td style={td}>{a.descripcion}<div style={{ ...mono, color: '#9ca3af' }}>ref {a.referencia}</div></td>
                      <td style={td}>{a.partidas.map((p, i) => (
                        <div key={i} style={mono}>{p.cuenta_contable}{p.cuenta ? ` · ${p.cuenta}` : ''} {p.debe ? `D ${centavos(p.debe)}` : `H ${centavos(p.haber)}`}</div>
                      ))}</td>
                      <td style={{ ...td, ...mono, color: '#9ca3af' }}>{a.hash.slice(0, 12)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>


          {/* Rieles PIX */}
          <div style={tarjeta} data-testid="nucleo-rieles">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong>Rieles PIX {rieles ? `· ${rieles.riel} · ISPB ${rieles.ispb}` : ''}</strong>
              {rieles ? (
                <span style={{ fontSize: 12, color: '#6b7280' }}>
                  Claves de prueba: {rieles.claves_de_prueba.map((c) => `${c.clave}${c.comportamiento !== 'normal' ? ` (${c.comportamiento})` : ''}`).join(' · ')}
                </span>
              ) : null}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 12 }}>
              {/* Cobrar */}
              <div style={{ border: '1px solid #f3f4f6', borderRadius: 10, padding: 12 }}>
                <strong style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}><QrCode size={15} /> Cobrar por PIX</strong>
                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  <select style={campo} value={cobro.cuenta} onChange={(e) => setCobro({ ...cobro, cuenta: e.target.value })} data-testid="rieles-cobro-cuenta">
                    <option value="">Cuenta que cobra…</option>{cuentas.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.titular_ref}</option>)}
                  </select>
                  <input style={campo} placeholder="Monto en reales, p. ej. 150.00" value={cobro.monto} inputMode="decimal"
                    onChange={(e) => setCobro({ ...cobro, monto: e.target.value })} data-testid="rieles-cobro-monto" />
                  <input style={campo} placeholder="Descripción (va en el QR, opcional)" value={cobro.descripcion}
                    onChange={(e) => setCobro({ ...cobro, descripcion: e.target.value })} />
                  <button type="button" onClick={generarCobro} disabled={ocupado} style={boton} data-testid="rieles-generar-cobro">Generar QR</button>
                </div>
                {ultimoCobro ? (
                  <div style={{ marginTop: 10, fontSize: 12 }} data-testid="rieles-ultimo-cobro">
                    <div style={rotulo}>BR Code · txid {ultimoCobro.txid}</div>
                    <textarea readOnly value={ultimoCobro.codigo_br} rows={3} style={{ ...campo, ...mono, resize: 'none', fontSize: 11 }} />
                    <button type="button" onClick={() => simularPago(ultimoCobro)} disabled={ocupado} style={{ ...botonSuave, marginTop: 6 }} data-testid="rieles-simular-pago">
                      Simular que lo pagaron
                    </button>
                  </div>
                ) : null}
              </div>

              {/* Pagar */}
              <div style={{ border: '1px solid #f3f4f6', borderRadius: 10, padding: 12 }}>
                <strong style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}><Send size={15} /> Pagar por PIX</strong>
                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  <select style={campo} value={pago.cuenta} onChange={(e) => setPago({ ...pago, cuenta: e.target.value })} data-testid="rieles-pago-cuenta">
                    <option value="">Cuenta que paga…</option>{cuentas.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.titular_ref} · R$ {c.saldo}</option>)}
                  </select>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <input style={campo} placeholder="Clave PIX (CPF, correo, teléfono, aleatoria)" value={pago.clave} list="rieles-claves"
                      onChange={(e) => { setPago({ ...pago, clave: e.target.value }); setTitularDeLaClave(null); }} data-testid="rieles-pago-clave" />
                    <datalist id="rieles-claves">{(rieles?.claves_de_prueba || []).map((c) => <option key={c.clave} value={c.clave} />)}</datalist>
                    <button type="button" onClick={consultarClave} style={{ ...botonSuave, padding: '6px 10px' }} title="Consultar el DICT" data-testid="rieles-consultar-clave"><Search size={13} /></button>
                  </div>
                  {titularDeLaClave ? (
                    <div style={{ fontSize: 12, color: titularDeLaClave.error ? '#b91c1c' : '#374151' }} data-testid="rieles-titular">
                      {titularDeLaClave.error ? titularDeLaClave.error : <>{titularDeLaClave.nombre} · {titularDeLaClave.documento} · {titularDeLaClave.banco} (ISPB {titularDeLaClave.ispb})</>}
                    </div>
                  ) : null}
                  <input style={campo} placeholder="Monto en reales" value={pago.monto} inputMode="decimal"
                    onChange={(e) => setPago({ ...pago, monto: e.target.value })} data-testid="rieles-pago-monto" />
                  <input style={campo} placeholder="Descripción (opcional)" value={pago.descripcion}
                    onChange={(e) => setPago({ ...pago, descripcion: e.target.value })} />
                  <button type="button" onClick={pagar} disabled={ocupado} style={boton} data-testid="rieles-pagar">Pagar</button>
                </div>
              </div>
            </div>

            {/* Operaciones */}
            <div style={{ overflowX: 'auto', marginTop: 12 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }} data-testid="rieles-operaciones">
                <thead><tr><th style={th}>Operación</th><th style={th}>Estado</th><th style={{ ...th, textAlign: 'right' }}>Monto</th><th style={th}>Contraparte</th><th style={th}>Punta a punta</th><th style={th}>Motivo</th><th style={th} /></tr></thead>
                <tbody>
                  {!rieles || rieles.operaciones.length === 0 ? <tr><td style={td} colSpan={7}>Todavía no hay operaciones por ningún riel.</td></tr> : rieles.operaciones.map((o) => (
                    <tr key={o.id} data-testid={`rieles-op-${o.direccion}-${o.estado}`}>
                      <td style={td}>{DIRECCION[o.direccion] || o.direccion}<div style={{ ...mono, color: '#9ca3af' }}>{o.id}</div></td>
                      <td style={td}><Etiqueta valor={o.estado} /></td>
                      <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>R$ {o.monto.replace('.', ',')}</td>
                      <td style={td}>{o.contraparte?.nombre || '—'}<div style={{ ...mono, color: '#9ca3af' }}>{o.clave}</div></td>
                      <td style={{ ...td, ...mono, color: '#6b7280' }}>{o.end_to_end || (o.txid ? `txid ${o.txid.slice(0, 10)}…` : '—')}</td>
                      <td style={{ ...td, color: '#991b1b', maxWidth: 260 }}>{o.motivo || ''}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        {o.direccion === 'entrada' && o.estado === 'activa' ? (
                          <button type="button" onClick={() => simularPago(o)} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="rieles-simular-pago-fila">Simular pago</button>
                        ) : null}
                        {o.direccion === 'entrada' && o.estado === 'liquidada' && devolviendo?.id !== o.id ? (
                          <button type="button" onClick={() => setDevolviendo({ id: o.id, monto: o.monto })} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="rieles-devolver"><Undo2 size={12} /> Devolver</button>
                        ) : null}
                        {o.direccion === 'entrada' && o.estado === 'liquidada' && devolviendo?.id === o.id ? (
                          <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                            <input style={{ ...campo, width: 90, padding: '5px 7px' }} value={devolviendo.monto} inputMode="decimal" title={`Hasta R$ ${o.monto}`}
                              onChange={(e) => setDevolviendo({ id: o.id, monto: e.target.value })} data-testid="rieles-devolver-monto" />
                            <button type="button" onClick={devolver} disabled={ocupado} style={{ ...boton, padding: '5px 9px' }} data-testid="rieles-devolver-confirmar">Devolver</button>
                            <button type="button" onClick={() => setDevolviendo(null)} style={{ ...botonSuave, padding: '5px 9px' }}>Cancelar</button>
                          </span>
                        ) : null}
                        {o.direccion !== 'entrada' && o.estado === 'enviada' ? (
                          <>
                            <button type="button" onClick={() => simularResultado(o, 'ACSC')} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px', marginRight: 4 }} data-testid="rieles-simular-acsc">Liquidar</button>
                            <button type="button" onClick={() => simularResultado(o, 'RJCT')} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px', background: '#fee2e2', color: '#991b1b' }} data-testid="rieles-simular-rjct">Rechazar</button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rieles ? (
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: 'pointer', fontSize: 13, color: '#374151' }}>Avisos del riel (últimos {rieles.avisos.length})</summary>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="rieles-avisos">
                  <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Identificador del riel</th><th style={th}>Resultado</th></tr></thead>
                  <tbody>
                    {rieles.avisos.length === 0 ? <tr><td style={td} colSpan={4}>Todavía no hay avisos.</td></tr> : rieles.avisos.map((a) => (
                      <tr key={a.id}><td style={{ ...td, ...mono }}>{a.id}</td><td style={td}>{a.tipo}</td>
                        <td style={{ ...td, ...mono, color: '#6b7280' }}>{a.id_externo}</td><td style={td}>{a.procesado ? a.resultado : 'sin procesar'}</td></tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ) : null}
          </div>

          {/* Cola de trabajos y eventos */}
          <div style={tarjeta} data-testid="nucleo-cola">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong>Cola de trabajos y eventos</strong>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" onClick={() => encolar('eco')} disabled={ocupado} style={botonSuave} data-testid="nucleo-encolar-eco">
                  <Plus size={13} /> Encolar un eco
                </button>
                <button type="button" onClick={() => encolar('fallar')} disabled={ocupado} style={botonSuave} data-testid="nucleo-encolar-fallar">
                  <Plus size={13} /> Encolar uno que falla
                </button>
                <button type="button" onClick={procesar} disabled={ocupado} style={boton} data-testid="nucleo-procesar">
                  <Play size={13} /> Procesar ahora
                </button>
              </div>
            </div>
            {cola ? (
              <>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', margin: '10px 0', fontSize: 13 }}>
                  <span>Pendientes <strong>{cola.resumen.pendiente}</strong></span>
                  <span>En curso <strong>{cola.resumen.en_curso}</strong></span>
                  <span>Hechos <strong>{cola.resumen.hecho}</strong></span>
                  <span style={{ color: cola.resumen.muerto ? '#b91c1c' : undefined }}>Muertos <strong>{cola.resumen.muerto}</strong></span>
                  <span>Eventos <strong>{cola.resumen.eventos}</strong> ({cola.resumen.eventos_sin_publicar} sin despachar)</span>
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }} data-testid="nucleo-trabajador">
                  Trabajador <span style={mono}>{cola.trabajador.nombre}</span> · {cola.trabajador.corriendo ? 'corriendo' : 'parado'}
                  {' · '}{cola.trabajador.vueltas} vueltas · última {hora(cola.trabajador.ultima_vuelta)}
                  {cola.trabajador.ultimo_error ? <span style={{ color: '#b91c1c' }}> · último error: {cola.trabajador.ultimo_error}</span> : null}
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }} data-testid="nucleo-trabajos">
                    <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Clave</th><th style={th}>Estado</th><th style={th}>Intentos</th><th style={th}>Próximo</th><th style={th}>Resultado / último error</th><th style={th} /></tr></thead>
                    <tbody>
                      {cola.trabajos.length === 0 ? <tr><td style={td} colSpan={8}>La cola está vacía.</td></tr> : cola.trabajos.map((t) => (
                        <tr key={t.id} data-testid={`nucleo-trabajo-${t.estado}`}>
                          <td style={{ ...td, ...mono }}>{t.id}</td><td style={td}>{t.tipo}</td>
                          <td style={{ ...td, ...mono, color: '#6b7280' }}>{t.clave}</td>
                          <td style={td}><Etiqueta valor={t.estado} /></td>
                          <td style={td}>{t.intentos} / {t.max_intentos}</td>
                          <td style={td}>{t.estado === 'pendiente' ? hora(t.proximo_intento) : '—'}</td>
                          <td style={{ ...td, maxWidth: 320 }}>
                            {t.resultado ? <span>{t.resultado}</span> : null}
                            {t.ultimo_error ? <span style={{ color: '#991b1b' }}>{t.ultimo_error}</span> : null}
                          </td>
                          <td style={td}>
                            {t.estado === 'muerto' ? (
                              <button type="button" onClick={() => reintentar(t.id)} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="nucleo-reintentar">
                                <RotateCcw size={12} /> Reintentar
                              </button>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details style={{ marginTop: 10 }}>
                  <summary style={{ cursor: 'pointer', fontSize: 13, color: '#374151' }}>Eventos (últimos {cola.eventos.length})</summary>
                  <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="nucleo-eventos">
                    <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Clave</th><th style={th}>Despachado</th></tr></thead>
                    <tbody>
                      {cola.eventos.length === 0 ? <tr><td style={td} colSpan={4}>Todavía no hay eventos.</td></tr> : cola.eventos.map((e) => (
                        <tr key={e.id}><td style={{ ...td, ...mono }}>{e.id}</td><td style={td}>{e.tipo}</td>
                          <td style={{ ...td, ...mono, color: '#6b7280' }}>{e.clave}</td><td style={td}>{e.publicado ? hora(e.publicado) : 'pendiente'}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              </>
            ) : null}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {/* Balance */}
            <div style={tarjeta}>
              <strong>Balance de comprobación {balance ? (balance.cuadra ? '· cuadra' : '· NO CUADRA') : ''}</strong>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }} data-testid="nucleo-balance">
                <thead><tr><th style={th}>Cuenta</th><th style={{ ...th, textAlign: 'right' }}>Debe</th><th style={{ ...th, textAlign: 'right' }}>Haber</th><th style={{ ...th, textAlign: 'right' }}>Saldo</th></tr></thead>
                <tbody>
                  {(balance?.filas || []).map((f) => (
                    <tr key={f.codigo}><td style={td}><span style={mono}>{f.codigo}</span> {f.nombre}</td>
                      <td style={{ ...td, textAlign: 'right' }}>{centavos(f.debe)}</td><td style={{ ...td, textAlign: 'right' }}>{centavos(f.haber)}</td>
                      <td style={{ ...td, textAlign: 'right', fontWeight: 600 }}>{centavos(f.saldo)}</td></tr>
                  ))}
                  {balance ? <tr><td style={{ ...td, fontWeight: 700 }}>Total</td>
                    <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{centavos(balance.total_debe)}</td>
                    <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{centavos(balance.total_haber)}</td><td style={td} /></tr> : null}
                </tbody>
              </table>
            </div>

            {/* Cierre */}
            <div style={tarjeta}>
              <strong>Cierre diario</strong>
              <div style={{ display: 'flex', gap: 8, margin: '10px 0' }}>
                <input type="date" style={campo} value={diaCierre} onChange={(e) => setDiaCierre(e.target.value)} data-testid="nucleo-dia" />
                <button type="button" onClick={cerrar} disabled={ocupado} style={boton} data-testid="nucleo-cerrar">Cerrar el día</button>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Día</th><th style={th}>Hasta</th><th style={th}>Asientos</th><th style={th}>Hash final</th></tr></thead>
                <tbody>
                  {cierres.length === 0 ? <tr><td style={td} colSpan={4}>Ningún día cerrado.</td></tr> : cierres.map((c) => (
                    <tr key={c.dia}><td style={td}>{c.dia}</td><td style={{ ...td, ...mono }}>{c.hasta_asiento}</td><td style={td}>{c.asientos}</td>
                      <td style={{ ...td, ...mono, color: '#9ca3af' }}>{c.hash_final.slice(0, 12)}…</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
