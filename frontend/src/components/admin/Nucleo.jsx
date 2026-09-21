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
 *   balance cuadrar, verificar la cadena y cerrar el día.
 *
 * APAGADO DE FABRICA
 *
 *   Con «Núcleo de cuentas» en 0 (Configuración), el servidor contesta 404 a
 *   todo, y esta pestaña dice eso y nada más. Los clientes no tienen ninguna
 *   puerta a esto: ni ruta, ni botón, ni clave en `/limits`. Hay tests que
 *   lo sostienen (backend/tests/test_nucleo_apagado_de_fabrica.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { Landmark, Plus, RefreshCw, ShieldCheck, ShieldAlert, Lock } from 'lucide-react';
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

export default function Nucleo() {
  const [estado, setEstado] = useState(null);       // null: cargando; {apagado:true}: 404
  const [cuentas, setCuentas] = useState([]);
  const [libro, setLibro] = useState([]);
  const [balance, setBalance] = useState(null);
  const [cierres, setCierres] = useState([]);
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
        const [c, l, b, z] = await Promise.all([
          api.get('/nucleo/laboratorio/cuentas'), api.get('/nucleo/laboratorio/libro?limite=30'),
          api.get('/nucleo/laboratorio/balance'), api.get('/nucleo/laboratorio/cierres'),
        ]);
        if (!vigente) return;
        setCuentas(c.data || []); setLibro(l.data || []); setBalance(b.data || null); setCierres(z.data || []);
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
