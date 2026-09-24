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
 *   Y la identidad: el legajo de cada titular (verificar, cruzar con las
 *   listas, aprobar con un nivel de riesgo), contra un simulador con
 *   personas de prueba. Sin legajo aprobado no se abre una cuenta.
 *   Y los reportes regulatorios: el balancete COSIF del mes, el CCS del día
 *   y la e-Financeira del semestre, generados sobre días cerrados, con su
 *   versión y su protocolo de transmisión (contra un simulador del STA).
 *   Y el respaldo: la exportación firmada de lo que la ley obliga a
 *   conservar (se baja y se guarda afuera; la base sólo registra que se
 *   hizo) y la comprobación que prueba que un respaldo se puede leer.
 *   Y la salud (qué se mira de verdad, y que avisa al equipo cuando cambia),
 *   los secretos (si cada credencial está y su huella, nunca el valor) y
 *   las métricas que un tablero externo puede leer en texto plano.
 *   Y la operación: la bitácora encadenada (quién hizo qué, con antes y
 *   después) y el cuatro ojos general: transmitir un reporte, comunicar un
 *   incidente o cambiar la configuración del núcleo prendido se PIDE acá y
 *   otra persona lo aprueba; recién ahí se ejecuta.
 *   Y el cumplimiento: el registro de incidentes (los relevantes se
 *   comunican al BCB con plazo), la ouvidoria (protocolo y diez días
 *   hábiles) y el calendario de obligaciones, que se deduce de las tablas.
 *   Y el riesgo: las alertas del monitoreo (umbrales configurables desde
 *   Configuración), el expediente de caso con sus plazos, los cuatro ojos
 *   para comunicar, y la comunicación al COAF contra un simulador.
 *
 * APAGADO DE FABRICA
 *
 *   Con «Núcleo de cuentas» en 0 (Configuración), el servidor contesta 404 a
 *   todo, y esta pestaña dice eso y nada más. Los clientes no tienen ninguna
 *   puerta a esto: ni ruta, ni botón, ni clave en `/limits`. Hay tests que
 *   lo sostienen (backend/tests/test_nucleo_apagado_de_fabrica.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { Landmark, Plus, RefreshCw, ShieldCheck, ShieldAlert, Lock, Play, RotateCcw, QrCode, Send, Search, Undo2, UserCheck, Fingerprint, ListChecks, Siren, FileText, FileOutput, CalendarClock, Eye, ScrollText, HeartPulse, KeyRound, Gauge, Archive, FileCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

const tarjeta = { background: 'var(--en-oscuro-superficie, #fff)', border: '1px solid var(--en-oscuro-linea, #e5e7eb)', borderRadius: 12, padding: '14px 16px' };
const rotulo = { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: 'var(--en-oscuro-texto-2, #6b7280)', marginBottom: 4 };
const campo = { width: '100%', padding: '9px 10px', border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', borderRadius: 8, fontSize: 14 };
const boton = { padding: '9px 14px', borderRadius: 8, border: 'none', background: 'var(--en-oscuro-acento, #5B4FE9)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 };
const botonSuave = { ...boton, background: 'var(--en-oscuro-acento-suave, #eef2ff)', color: 'var(--en-oscuro-acento, #3B3A9E)' };
const th = { textAlign: 'left', fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)', textTransform: 'uppercase', letterSpacing: 0.4, padding: '6px 8px', borderBottom: '1px solid var(--en-oscuro-linea, #e5e7eb)' };
const td = { padding: '7px 8px', borderBottom: '1px solid var(--en-oscuro-linea, #f3f4f6)', fontSize: 13, verticalAlign: 'top' };
const mono = { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 };
const centavos = (n) => (n / 100).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—');
const fechaYHora = (iso) => (iso ? new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');

// El color de cada estado de la cola. Muerto en rojo porque es lo único que
// pide que una persona haga algo.
const COLOR_DEL_ESTADO = {
  pendiente: { background: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #92400e)' },
  en_curso: { background: 'var(--en-oscuro-acento-suave, #dbeafe)', color: 'var(--en-oscuro-acento, #1e40af)' },
  hecho: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  muerto: { background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' },
  // los de una operación por un riel
  activa: { background: 'var(--en-oscuro-acento-suave, #e0e7ff)', color: 'var(--en-oscuro-acento, #3730a3)' },
  enviada: { background: 'var(--en-oscuro-acento-suave, #dbeafe)', color: 'var(--en-oscuro-acento, #1e40af)' },
  liquidada: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  rechazada: { background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' },
  // los de un legajo
  incompleto: { background: 'var(--en-oscuro-superficie-2, #f3f4f6)', color: 'var(--en-oscuro-texto, #374151)' },
  en_revision: { background: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #92400e)' },
  aprobado: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  rechazado: { background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' },
  vencido: { background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' },
  // los de un reporte regulatorio y del calendario
  generado: { background: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #92400e)' },
  transmitido: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  no_corresponde: { background: 'var(--en-oscuro-superficie-2, #f3f4f6)', color: 'var(--en-oscuro-texto, #374151)' },
  // los de un pedido de cuatro ojos
  ejecutado: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  fallido: { background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' },
  // los de un incidente y de un reclamo
  cerrado: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  respondido: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  // los de un caso
  abierto: { background: 'var(--en-oscuro-alerta-suave, #fef3c7)', color: 'var(--en-oscuro-alerta, #92400e)' },
  en_analisis: { background: 'var(--en-oscuro-acento-suave, #dbeafe)', color: 'var(--en-oscuro-acento, #1e40af)' },
  concluido: { background: 'var(--en-oscuro-acento-suave, #e0e7ff)', color: 'var(--en-oscuro-acento, #3730a3)' },
  comunicado: { background: 'var(--en-oscuro-exito-suave, #dcfce7)', color: 'var(--en-oscuro-exito, #166534)' },
  archivado: { background: 'var(--en-oscuro-superficie-2, #f3f4f6)', color: 'var(--en-oscuro-texto, #374151)' },
};
const DIRECCION = { entrada: 'Cobro', salida: 'Pago', devolucion: 'Devolución' };
const Etiqueta = ({ valor }) => (
  <span style={{ ...(COLOR_DEL_ESTADO[valor] || {}), padding: '2px 8px', borderRadius: 999, fontSize: 12, fontWeight: 600 }}>
    {valor === 'en_curso' ? 'en curso' : valor === 'en_revision' ? 'en revisión' : valor === 'en_analisis' ? 'en análisis' : valor}
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
  const [identidad, setIdentidad] = useState(null);
  const [nuevoTitular, setNuevoTitular] = useState({ documento: '', nombre: '', ocupacion: '', renta_declarada: '', origen_de_fondos: 'salario', pep_declarado: false });
  const [abierto, setAbierto] = useState(null);           // el titular cuyo legajo se está mirando
  const [nivel, setNivel] = useState('bajo');
  const [resolucion, setResolucion] = useState('');
  const [riesgo, setRiesgo] = useState(null);
  const [casoAbierto, setCasoAbierto] = useState(null);   // el caso que se está mirando
  const [como, setComo] = useState('');                   // laboratorio: a nombre de quién se actúa
  const [nota, setNota] = useState('');
  const [conclusion, setConclusion] = useState('');
  const [reportes, setReportes] = useState(null);
  const [pedidoDeReporte, setPedidoDeReporte] = useState({ tipo: 'balancete', periodo: new Date().toISOString().slice(0, 7) });
  const [reporteAbierto, setReporteAbierto] = useState(null);   // { id, archivo } del que se está leyendo
  const [cumplimiento, setCumplimiento] = useState(null);
  const [nuevoIncidente, setNuevoIncidente] = useState({ tipo: 'indisponibilidad', titulo: '', impacto: '', clientes_afectados: '0', relevante: true });
  const [incidenteAbierto, setIncidenteAbierto] = useState(null);
  const [cierre, setCierre] = useState({ causa: '', acciones: '' });
  const [nuevoReclamo, setNuevoReclamo] = useState({ canal: 'bcb', asunto: '', descripcion: '', caso_soporte: '' });
  const [respuesta, setRespuesta] = useState({ id: null, respuesta: '', resultado: 'procedente' });
  const [operacion, setOperacion] = useState(null);
  const [motivo, setMotivo] = useState('');                               // del pedido de cuatro ojos que se está armando
  const [pidiendo, setPidiendo] = useState(null);                         // { tipo: 'reporte'|'incidente', id } que espera motivo
  const [pedidoDeConfig, setPedidoDeConfig] = useState({ clave: 'nucleo_umbral_operacion', valor: '', motivo: '' });
  const [notaDeDecision, setNotaDeDecision] = useState('');
  const [salud, setSalud] = useState(null);
  const [secretos, setSecretos] = useState(null);
  const [metricas, setMetricas] = useState(null);
  const [respaldos, setRespaldos] = useState(null);
  const [ultimoRespaldo, setUltimoRespaldo] = useState(null);       // { hash, firma, filas } del recién creado
  const [aComprobar, setAComprobar] = useState({ contenido: '', nombre: '', firma: '' });
  const [comprobacion, setComprobacion] = useState(null);
  const [vuelta, setVuelta] = useState(0);
  const [titularDeLaCuenta, setTitularDeLaCuenta] = useState('');
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
        const [c, l, b, z, q, rl, idn, rg, rp, cu, opn, sl, sc, mt, rs] = await Promise.all([
          api.get('/nucleo/laboratorio/cuentas'), api.get('/nucleo/laboratorio/libro?limite=30'),
          api.get('/nucleo/laboratorio/balance'), api.get('/nucleo/laboratorio/cierres'),
          api.get('/nucleo/laboratorio/cola?limite=30'), api.get('/nucleo/laboratorio/rieles?limite=30'),
          api.get('/nucleo/laboratorio/identidad'), api.get('/nucleo/laboratorio/riesgo'),
          api.get('/nucleo/laboratorio/reportes'), api.get('/nucleo/laboratorio/cumplimiento'),
          api.get('/nucleo/laboratorio/operacion'), api.get('/nucleo/laboratorio/salud'),
          api.get('/nucleo/laboratorio/secretos'), api.get('/nucleo/laboratorio/metricas'),
          api.get('/nucleo/laboratorio/respaldos'),
        ]);
        if (!vigente) return;
        setCuentas(c.data || []); setLibro(l.data || []); setBalance(b.data || null); setCierres(z.data || []);
        setCola(q.data || null); setRieles(rl.data || null); setIdentidad(idn.data || null); setRiesgo(rg.data || null);
        setReportes(rp.data || null); setCumplimiento(cu.data || null); setOperacion(opn.data || null);
        setSalud(sl.data || null); setSecretos(sc.data || null); setMetricas(mt.data || null); setRespaldos(rs.data || null);
      })
      .catch((e) => {
        if (!vigente) return;
        // 404 es «apagado»: el servidor no anuncia lo que no está prendido.
        setEstado({ apagado: true, status: e?.response?.status });
      });
    return () => { vigente = false; };
  }, [vuelta]);

  const crearCuenta = async () => {
    if (!titularDeLaCuenta) return toast.error('Elegí un titular con legajo aprobado');
    setOcupado(true);
    try {
      await api.post('/nucleo/laboratorio/cuentas', { titular: titularDeLaCuenta });
      setTitularDeLaCuenta(''); toast.success('Cuenta de prueba creada'); recargar();
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

  const nombreDelTitular = (id) => (identidad?.titulares || []).find((t) => t.id === id)?.nombre || id;

  const crearTitular = async () => {
    setOcupado(true);
    try {
      const cuerpo = { ...nuevoTitular };
      Object.keys(cuerpo).forEach((k) => { if (cuerpo[k] === '') delete cuerpo[k]; });
      const r = await api.post('/nucleo/laboratorio/identidad/titulares', cuerpo);
      toast.success(`Legajo de ${r.data.nombre} creado`); setAbierto(r.data.id);
      setNuevoTitular({ documento: '', nombre: '', ocupacion: '', renta_declarada: '', origen_de_fondos: 'salario', pep_declarado: false }); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo crear el legajo'); }
    finally { setOcupado(false); }
  };

  const accionDeLegajo = async (id, accion, cuerpo) => {
    setOcupado(true);
    try {
      const rutas = {
        verificar: `/nucleo/laboratorio/identidad/titulares/${id}/verificar`,
        cruzar: `/nucleo/laboratorio/identidad/titulares/${id}/cruzar`,
        aprobar: `/nucleo/laboratorio/identidad/titulares/${id}/aprobar`,
        rechazar: `/nucleo/laboratorio/identidad/titulares/${id}/rechazar`,
      };
      await api.post(rutas[accion], cuerpo || {});
      toast.success({ verificar: 'Verificación hecha', cruzar: 'Listas consultadas', aprobar: 'Legajo aprobado', rechazar: 'Legajo rechazado' }[accion]);
      setAbierto(id); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo'); }
    finally { setOcupado(false); }
  };

  const resolverCruce = async (cruceId) => {
    if (!resolucion.trim()) return toast.error('Escribí cómo se resuelve el cruce');
    setOcupado(true);
    try {
      await api.post(`/nucleo/laboratorio/identidad/cruces/${cruceId}/resolver`, { resolucion: resolucion.trim() });
      toast.success('Cruce resuelto'); setResolucion(''); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo resolver'); }
    finally { setOcupado(false); }
  };

  const accionDeCaso = async (id, accion, cuerpo) => {
    setOcupado(true);
    try {
      const rutas = {
        tomar: `/nucleo/laboratorio/riesgo/casos/${id}/tomar`,
        anotar: `/nucleo/laboratorio/riesgo/casos/${id}/anotar`,
        concluir: `/nucleo/laboratorio/riesgo/casos/${id}/concluir`,
        aprobar_comunicacion: `/nucleo/laboratorio/riesgo/casos/${id}/aprobar_comunicacion`,
      };
      const r = await api.post(rutas[accion], { ...(cuerpo || {}), como: como.trim() || undefined });
      toast.success({ tomar: `Tomado por ${r.data.analista}`, anotar: 'Nota agregada', concluir: `Caso ${r.data.estado}`, aprobar_comunicacion: `Comunicado al COAF · acuse ${r.data.acuse}` }[accion]);
      if (accion === 'anotar') setNota('');
      if (accion === 'concluir') setConclusion('');
      setCasoAbierto(id); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo'); }
    finally { setOcupado(false); }
  };

  const declararNoOcurrencia = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/riesgo/no_ocurrencia', { anio: new Date().getFullYear() - 1, como: como.trim() || undefined });
      toast.success(`No ocurrencia ${r.data.periodo} · acuse ${r.data.acuse}`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo declarar'); }
    finally { setOcupado(false); }
  };

  const generarReporte = async () => {
    if (!pedidoDeReporte.periodo.trim()) return toast.error('Escribí el período');
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/reportes/generar', { tipo: pedidoDeReporte.tipo, periodo: pedidoDeReporte.periodo.trim() });
      toast.success(`${r.data.documento} ${r.data.periodo} · versión ${r.data.version}`);
      setReporteAbierto({ id: r.data.id, archivo: r.data.archivo }); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo generar'); }
    finally { setOcupado(false); }
  };

  const verReporte = async (id) => {
    if (reporteAbierto?.id === id) return setReporteAbierto(null);
    try {
      const r = await api.get(`/nucleo/laboratorio/reportes/${id}`);
      setReporteAbierto({ id, archivo: r.data.archivo });
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo leer'); }
  };

  const pedirConMotivo = async () => {
    if (!motivo.trim()) return toast.error('Escribí el motivo: quien aprueba tiene que saber por qué');
    setOcupado(true);
    try {
      const rutas = {
        reporte: `/nucleo/laboratorio/reportes/${pidiendo.id}/transmitir`,
        incidente: `/nucleo/laboratorio/cumplimiento/incidentes/${pidiendo.id}/comunicar`,
      };
      const r = await api.post(rutas[pidiendo.tipo], { motivo: motivo.trim() });
      toast.success(`Pedido ${r.data.id} · espera la aprobación de otra persona`);
      setPidiendo(null); setMotivo(''); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo pedir'); }
    finally { setOcupado(false); }
  };

  const pedirConfiguracion = async () => {
    if (!pedidoDeConfig.valor.trim() || !pedidoDeConfig.motivo.trim()) return toast.error('Escribí el valor y el motivo');
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/operacion/configuracion', pedidoDeConfig);
      toast.success(`Pedido ${r.data.id} · espera la aprobación de otra persona`);
      setPedidoDeConfig({ ...pedidoDeConfig, valor: '', motivo: '' }); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo pedir'); }
    finally { setOcupado(false); }
  };

  const decidir = async (id, aprobar) => {
    setOcupado(true);
    try {
      const r = await api.post(`/nucleo/laboratorio/operacion/aprobaciones/${id}/decidir`, { aprobar, nota: notaDeDecision.trim() || undefined, como: como.trim() || undefined });
      toast.success(aprobar ? `Aprobado y ejecutado · ${r.data.resultado}` : 'Rechazado');
      setNotaDeDecision(''); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo decidir'); recargar(); }
    finally { setOcupado(false); }
  };

  const abrirIncidente = async () => {
    if (!nuevoIncidente.titulo.trim() || !nuevoIncidente.impacto.trim()) return toast.error('Escribí qué pasó y qué impacto tuvo');
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/cumplimiento/incidentes', { ...nuevoIncidente, clientes_afectados: Number(nuevoIncidente.clientes_afectados) || 0 });
      toast.success(`Incidente ${r.data.id} registrado${r.data.relevante ? ' · comunicar al BCB antes de ' + fechaYHora(r.data.comunicar_hasta) : ''}`);
      setNuevoIncidente({ tipo: 'indisponibilidad', titulo: '', impacto: '', clientes_afectados: '0', relevante: true }); setIncidenteAbierto(r.data.id); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo registrar'); }
    finally { setOcupado(false); }
  };

  const accionDeIncidente = async (id, accion, cuerpo) => {
    setOcupado(true);
    try {
      const rutas = {
        anotar: `/nucleo/laboratorio/cumplimiento/incidentes/${id}/anotar`,
        cerrar: `/nucleo/laboratorio/cumplimiento/incidentes/${id}/cerrar`,
      };
      await api.post(rutas[accion], cuerpo || {});
      toast.success({ anotar: 'Nota agregada', cerrar: 'Incidente cerrado' }[accion]);
      if (accion === 'anotar') setNota('');
      if (accion === 'cerrar') setCierre({ causa: '', acciones: '' });
      setIncidenteAbierto(id); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo'); }
    finally { setOcupado(false); }
  };

  const abrirReclamo = async () => {
    if (!nuevoReclamo.asunto.trim() || !nuevoReclamo.descripcion.trim()) return toast.error('Escribí el asunto y la descripción');
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/cumplimiento/reclamos', { ...nuevoReclamo, caso_soporte: nuevoReclamo.caso_soporte.trim() || undefined });
      toast.success(`Reclamo ${r.data.protocolo} · responder antes del ${r.data.responder_hasta}`);
      setNuevoReclamo({ canal: 'bcb', asunto: '', descripcion: '', caso_soporte: '' }); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo registrar'); }
    finally { setOcupado(false); }
  };

  const responderReclamo = async () => {
    if (!respuesta.respuesta.trim()) return toast.error('Escribí la respuesta');
    setOcupado(true);
    try {
      const r = await api.post(`/nucleo/laboratorio/cumplimiento/reclamos/${respuesta.id}/responder`, { respuesta: respuesta.respuesta, resultado: respuesta.resultado });
      toast.success(`${r.data.protocolo} respondido · ${r.data.en_plazo ? 'en plazo' : 'FUERA DE PLAZO'}`);
      setRespuesta({ id: null, respuesta: '', resultado: 'procedente' }); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo responder'); }
    finally { setOcupado(false); }
  };

  const generarDelCalendario = async (obligacion, periodo) => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/reportes/generar', { tipo: obligacion, periodo });
      toast.success(`${r.data.documento} ${r.data.periodo} · versión ${r.data.version}`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo generar'); }
    finally { setOcupado(false); }
  };

  const crearRespaldo = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/respaldos');
      // El contenido se baja al navegador: el sentido de un respaldo es estar afuera.
      const url = URL.createObjectURL(new Blob([r.data.contenido], { type: 'application/x-ndjson' }));
      const a = document.createElement('a');
      a.href = url; a.download = `nucleo-respaldo-${r.data.momento.slice(0, 19).replaceAll(':', '')}.jsonl`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      setUltimoRespaldo({ hash: r.data.hash, firma: r.data.firma, filas: r.data.filas, firmado: r.data.firmado });
      toast.success(`Respaldo de ${r.data.filas} filas${r.data.firmado ? ', firmado' : ', SIN FIRMA (falta la llave)'}`); recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo crear el respaldo'); }
    finally { setOcupado(false); }
  };

  const elegirArchivo = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const lector = new FileReader();
    lector.onload = () => setAComprobar((x) => ({ ...x, contenido: String(lector.result || ''), nombre: f.name }));
    lector.readAsText(f);
  };

  const comprobarRespaldo = async () => {
    if (!aComprobar.contenido) return toast.error('Elegí el archivo del respaldo');
    setOcupado(true);
    try {
      const r = await api.post('/nucleo/laboratorio/respaldos/comprobar', { contenido: aComprobar.contenido, firma: aComprobar.firma.trim() || undefined });
      setComprobacion(r.data);
      (r.data.ok ? toast.success : toast.error)(r.data.ok ? `Respaldo íntegro · ${r.data.filas} filas · firma ${r.data.firma}` : `NO pasa: ${r.data.motivo}`);
      recargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo comprobar'); }
    finally { setOcupado(false); }
  };

  if (estado === null) return <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>Cargando…</p>;

  if (estado.apagado) {
    return (
      <div style={{ ...tarjeta, display: 'flex', gap: 14, alignItems: 'flex-start' }} data-testid="nucleo-apagado">
        <Lock size={22} style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }} />
        <div>
          <p style={{ margin: '0 0 6px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)' }}>El núcleo de cuentas está apagado</p>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--en-oscuro-texto-2, #6b7280)', lineHeight: 1.5 }}>
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
          <div style={{ fontWeight: 700, color: estado.cola?.muerto ? 'var(--en-oscuro-error, #b91c1c)' : undefined }} data-testid="nucleo-cola-resumen">
            {estado.cola ? `${estado.cola.pendiente} pendientes · ${estado.cola.muerto} muertos` : '—'}
          </div>
        </div>
        <div>
          <div style={rotulo}>Cadena</div>
          <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, color: cadena?.ok ? 'var(--en-oscuro-exito, #15803d)' : 'var(--en-oscuro-error, #b91c1c)' }} data-testid="nucleo-cadena">
            {cadena ? (cadena.ok ? <><ShieldCheck size={16} /> íntegra</> : <><ShieldAlert size={16} /> rota en {cadena.roto_en}</>) : '—'}
          </div>
        </div>
      </div>

      {!estado.conectada ? (
        <div style={{ ...tarjeta, background: 'var(--en-oscuro-alerta-suave, #fffbeb)', border: '1px solid var(--en-oscuro-alerta-borde, #fde68a)', color: 'var(--en-oscuro-alerta, #92400e)', fontSize: 14 }}>
          El núcleo no tiene base: falta <code>NUCLEO_DATABASE_URL</code> en el entorno del servidor (un Postgres aparte).
          {estado.detalle ? <> Detalle: {estado.detalle}.</> : null}
        </div>
      ) : null}

      {estado.conectada ? (
        <>

          {/* Identidad */}
          <div style={tarjeta} data-testid="nucleo-identidad">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><UserCheck size={16} /> Identidad y legajos {identidad ? `· ${identidad.verificador} · ${identidad.listas}` : ''}</strong>
              {identidad ? (
                <select style={{ ...campo, width: 'auto' }} value="" data-testid="identidad-persona-de-prueba"
                  onChange={(e) => { const p = identidad.personas_de_prueba.find((x) => x.documento === e.target.value); if (p) setNuevoTitular((n) => ({ ...n, documento: p.documento, nombre: p.nombre })); }}>
                  <option value="">Personas de prueba…</option>
                  {identidad.personas_de_prueba.map((p) => <option key={p.documento} value={p.documento}>{p.nombre} · {p.documento}{p.comportamiento !== 'normal' ? ` (${p.comportamiento.replaceAll('_', ' ')})` : ''}</option>)}
                </select>
              ) : null}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 12 }}>
              {/* Nuevo legajo */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Nuevo legajo</strong>
                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  <input style={campo} placeholder="CPF o CNPJ, sólo dígitos" value={nuevoTitular.documento} inputMode="numeric"
                    onChange={(e) => setNuevoTitular({ ...nuevoTitular, documento: e.target.value })} data-testid="identidad-documento" />
                  <input style={campo} placeholder="Nombre completo" value={nuevoTitular.nombre}
                    onChange={(e) => setNuevoTitular({ ...nuevoTitular, nombre: e.target.value })} data-testid="identidad-nombre" />
                  <input style={campo} placeholder="Ocupación" value={nuevoTitular.ocupacion}
                    onChange={(e) => setNuevoTitular({ ...nuevoTitular, ocupacion: e.target.value })} />
                  <input style={campo} placeholder="Renta declarada por mes, en reales" value={nuevoTitular.renta_declarada} inputMode="decimal"
                    onChange={(e) => setNuevoTitular({ ...nuevoTitular, renta_declarada: e.target.value })} />
                  <select style={campo} value={nuevoTitular.origen_de_fondos} onChange={(e) => setNuevoTitular({ ...nuevoTitular, origen_de_fondos: e.target.value })}>
                    {(identidad?.origenes_de_fondos || ['salario']).map((o) => <option key={o} value={o}>Origen de fondos: {o.replaceAll('_', ' ')}</option>)}
                  </select>
                  <label style={{ fontSize: 13, display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input type="checkbox" checked={nuevoTitular.pep_declarado} onChange={(e) => setNuevoTitular({ ...nuevoTitular, pep_declarado: e.target.checked })} />
                    Declara ser persona expuesta políticamente (PEP)
                  </label>
                  <button type="button" onClick={crearTitular} disabled={ocupado} style={boton} data-testid="identidad-crear">Crear legajo</button>
                </div>
              </div>

              {/* El legajo abierto */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }} data-testid="identidad-legajo">
                {(() => {
                  const t = (identidad?.titulares || []).find((x) => x.id === abierto);
                  if (!t) return <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: 13, margin: 0 }}>Elegí un legajo de la lista para verlo y decidir.</p>;
                  const ultima = t.verificaciones?.[0];
                  return (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                        <strong style={{ fontSize: 14 }}>{t.nombre} <span style={{ ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)', fontWeight: 400 }}>{t.documento}</span></strong>
                        <Etiqueta valor={t.estado} />
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '6px 0' }}>
                        {t.ocupacion || 'sin ocupación'} · renta {t.renta_declarada ? `R$ ${t.renta_declarada}` : '—'} · origen {t.origen_de_fondos || '—'}
                        {t.pep ? <strong style={{ color: 'var(--en-oscuro-alerta, #92400e)' }}> · PEP</strong> : null}
                        {t.nivel_de_riesgo ? <> · riesgo <strong>{t.nivel_de_riesgo}</strong> · vigente hasta {t.vigente_hasta}</> : null}
                        {t.motivo ? <span style={{ color: 'var(--en-oscuro-error, #991b1b)' }}> · {t.motivo}</span> : null}
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0' }}>
                        <button type="button" onClick={() => accionDeLegajo(t.id, 'verificar')} disabled={ocupado || t.estado === 'rechazado'} style={botonSuave} data-testid="identidad-verificar"><Fingerprint size={13} /> Verificar identidad</button>
                        <button type="button" onClick={() => accionDeLegajo(t.id, 'cruzar')} disabled={ocupado} style={botonSuave} data-testid="identidad-cruzar"><ListChecks size={13} /> Cruzar con listas</button>
                      </div>
                      {ultima ? (
                        <div style={{ fontSize: 12, padding: 8, borderRadius: 8, background: ultima.aprobada ? 'var(--en-oscuro-exito-suave, #f0fdf4)' : 'var(--en-oscuro-error-suave, #fef2f2)' }} data-testid="identidad-verificacion">
                          <strong>{ultima.aprobada ? 'Verificación aprobada' : 'Verificación NO aprobada'}</strong> · documento {ultima.puntaje_documento} · vida {ultima.puntaje_vida} · rostro {ultima.puntaje_rostro} · CPF {ultima.situacion_cpf}
                          {ultima.motivos.length ? <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>{ultima.motivos.map((m, i) => <li key={i}>{m}</li>)}</ul> : null}
                        </div>
                      ) : null}
                      {t.cruzado_en ? (
                        <div style={{ fontSize: 12, marginTop: 8 }} data-testid="identidad-cruces">
                          <strong>Listas:</strong> {t.cruces.length === 0 ? 'no aparece en ninguna' : ''}
                          {t.cruces.map((c) => (
                            <div key={c.id} style={{ padding: 6, borderRadius: 8, background: c.resuelto ? 'var(--en-oscuro-superficie-2, #f3f4f6)' : 'var(--en-oscuro-error-suave, #fef2f2)', marginTop: 4 }}>
                              <strong>{c.lista}</strong> ({c.clase}) · {c.nombre_en_lista} · {c.detalle}
                              {c.resuelto ? <div style={{ color: 'var(--en-oscuro-texto, #374151)' }}>Resuelto por {c.resuelto_por}: {c.resolucion}</div> : (
                                <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                                  <input style={{ ...campo, padding: '5px 8px' }} placeholder="falso positivo: … / confirmado: …" value={resolucion}
                                    onChange={(e) => setResolucion(e.target.value)} data-testid="identidad-resolucion" />
                                  <button type="button" onClick={() => resolverCruce(c.id)} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="identidad-resolver">Resolver</button>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {t.estado !== 'aprobado' && t.estado !== 'rechazado' ? (
                        <div style={{ display: 'flex', gap: 6, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                          <select style={{ ...campo, width: 'auto' }} value={nivel} onChange={(e) => setNivel(e.target.value)} data-testid="identidad-nivel">
                            {(identidad?.niveles_de_riesgo || []).map((n) => <option key={n} value={n}>riesgo {n}</option>)}
                          </select>
                          <button type="button" onClick={() => accionDeLegajo(t.id, 'aprobar', { nivel_de_riesgo: nivel })} disabled={ocupado} style={boton} data-testid="identidad-aprobar">Aprobar</button>
                          <button type="button" onClick={() => accionDeLegajo(t.id, 'rechazar', { motivo: 'Rechazado desde el laboratorio' })} disabled={ocupado} style={{ ...botonSuave, background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' }} data-testid="identidad-rechazar">Rechazar</button>
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </div>
            </div>

            {/* Lista de legajos */}
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }} data-testid="identidad-titulares">
              <thead><tr><th style={th}>Titular</th><th style={th}>Documento</th><th style={th}>Estado</th><th style={th}>Riesgo</th><th style={th}>Vigente hasta</th><th style={th} /></tr></thead>
              <tbody>
                {!identidad || identidad.titulares.length === 0 ? <tr><td style={td} colSpan={6}>Todavía no hay legajos.</td></tr> : identidad.titulares.map((t) => (
                  <tr key={t.id} data-testid={`identidad-titular-${t.estado}`} style={{ background: abierto === t.id ? 'var(--en-oscuro-acento-suave, #f5f3ff)' : undefined }}>
                    <td style={td}>{t.nombre}{t.pep ? <span style={{ color: 'var(--en-oscuro-alerta, #92400e)', fontSize: 11 }}> · PEP</span> : null}</td>
                    <td style={{ ...td, ...mono }}>{t.documento}</td>
                    <td style={td}><Etiqueta valor={t.estado} /></td>
                    <td style={td}>{t.nivel_de_riesgo || '—'}</td>
                    <td style={td}>{t.vigente_hasta || '—'}</td>
                    <td style={td}><button type="button" onClick={() => setAbierto(t.id)} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="identidad-abrir">Ver legajo</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {/* Cuentas */}
            <div style={tarjeta}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Landmark size={16} /> Cuentas de prueba</strong>
                <button type="button" onClick={recargar} style={{ ...botonSuave, padding: '6px 10px' }}><RefreshCw size={13} /></button>
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                <select style={campo} value={titularDeLaCuenta} onChange={(e) => setTitularDeLaCuenta(e.target.value)} data-testid="nucleo-titular">
                  <option value="">Titular con legajo aprobado…</option>
                  {(identidad?.titulares || []).filter((t) => t.estado === 'aprobado').map((t) => (
                    <option key={t.id} value={t.id}>{t.nombre} · {t.documento}</option>
                  ))}
                </select>
                <button type="button" onClick={crearCuenta} disabled={ocupado} style={boton} data-testid="nucleo-crear-cuenta"><Plus size={14} /></button>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Cuenta</th><th style={th}>Titular</th><th style={{ ...th, textAlign: 'right' }}>Saldo</th></tr></thead>
                <tbody>
                  {cuentas.length === 0 ? <tr><td style={td} colSpan={3}>Todavía no hay cuentas.</td></tr> : cuentas.map((c) => (
                    <tr key={c.id}><td style={{ ...td, ...mono }}>{c.id}</td><td style={td}>{nombreDelTitular(c.titular_ref)}</td>
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
                      <td style={td}>{a.descripcion}<div style={{ ...mono, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>ref {a.referencia}</div></td>
                      <td style={td}>{a.partidas.map((p, i) => (
                        <div key={i} style={mono}>{p.cuenta_contable}{p.cuenta ? ` · ${p.cuenta}` : ''} {p.debe ? `D ${centavos(p.debe)}` : `H ${centavos(p.haber)}`}</div>
                      ))}</td>
                      <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>{a.hash.slice(0, 12)}…</td>
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
                <span style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
                  Claves de prueba: {rieles.claves_de_prueba.map((c) => `${c.clave}${c.comportamiento !== 'normal' ? ` (${c.comportamiento})` : ''}`).join(' · ')}
                </span>
              ) : null}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 12 }}>
              {/* Cobrar */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
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
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
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
                    <div style={{ fontSize: 12, color: titularDeLaClave.error ? 'var(--en-oscuro-error, #b91c1c)' : 'var(--en-oscuro-texto, #374151)' }} data-testid="rieles-titular">
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
                      <td style={td}>{DIRECCION[o.direccion] || o.direccion}<div style={{ ...mono, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>{o.id}</div></td>
                      <td style={td}><Etiqueta valor={o.estado} /></td>
                      <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>R$ {o.monto.replace('.', ',')}</td>
                      <td style={td}>{o.contraparte?.nombre || '—'}<div style={{ ...mono, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>{o.clave}</div></td>
                      <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{o.end_to_end || (o.txid ? `txid ${o.txid.slice(0, 10)}…` : '—')}</td>
                      <td style={{ ...td, color: 'var(--en-oscuro-error, #991b1b)', maxWidth: 260 }}>{o.motivo || ''}</td>
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
                            <button type="button" onClick={() => simularResultado(o, 'RJCT')} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px', background: 'var(--en-oscuro-error-suave, #fee2e2)', color: 'var(--en-oscuro-error, #991b1b)' }} data-testid="rieles-simular-rjct">Rechazar</button>
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
                <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--en-oscuro-texto, #374151)' }}>Avisos del riel (últimos {rieles.avisos.length})</summary>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="rieles-avisos">
                  <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Identificador del riel</th><th style={th}>Resultado</th></tr></thead>
                  <tbody>
                    {rieles.avisos.length === 0 ? <tr><td style={td} colSpan={4}>Todavía no hay avisos.</td></tr> : rieles.avisos.map((a) => (
                      <tr key={a.id}><td style={{ ...td, ...mono }}>{a.id}</td><td style={td}>{a.tipo}</td>
                        <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{a.id_externo}</td><td style={td}>{a.procesado ? a.resultado : 'sin procesar'}</td></tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ) : null}
          </div>

          {/* Riesgo: alertas, casos, COAF */}
          <div style={tarjeta} data-testid="nucleo-riesgo">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Siren size={16} /> Riesgo: monitoreo, casos y COAF {riesgo ? `· ${riesgo.comunicador}` : ''}</strong>
              {riesgo ? (
                <span style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
                  Umbrales (Configuración): operación R$ {centavos(riesgo.umbrales.umbral_operacion)} · 30 días R$ {centavos(riesgo.umbrales.umbral_30_dias)} · 12 meses R$ {centavos(riesgo.umbrales.umbral_12_meses)} · fraccionamiento {riesgo.umbrales.fraccionamiento_horas} h · {riesgo.umbrales.velocidad_por_hora} op/h
                </span>
              ) : null}
            </div>
            {riesgo ? (
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', margin: '10px 0', fontSize: 13 }}>
                <span>Alertas <strong>{Object.values(riesgo.resumen_alertas).reduce((a, b) => a + b, 0)}</strong></span>
                <span>Casos abiertos <strong>{riesgo.resumen_casos.abierto}</strong></span>
                <span>En análisis <strong>{riesgo.resumen_casos.en_analisis}</strong></span>
                <span>Concluidos <strong>{riesgo.resumen_casos.concluido}</strong></span>
                <span>Comunicados <strong>{riesgo.resumen_casos.comunicado}</strong></span>
                <span style={{ color: riesgo.resumen_casos.vencidos ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>Con plazo vencido <strong>{riesgo.resumen_casos.vencidos}</strong></span>
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: 12 }}>Actuar como (laboratorio):</span>
                  <input style={{ ...campo, width: 160, padding: '5px 8px' }} placeholder="p. ej. ana.analista" value={como} onChange={(e) => setComo(e.target.value)} data-testid="riesgo-como" />
                </span>
              </div>
            ) : null}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
              {/* Casos */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Casos</strong>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }} data-testid="riesgo-casos">
                  <thead><tr><th style={th}>Caso</th><th style={th}>Titular</th><th style={th}>Estado</th><th style={th}>Plazo</th><th style={th} /></tr></thead>
                  <tbody>
                    {!riesgo || riesgo.casos.length === 0 ? <tr><td style={td} colSpan={5}>Ningún caso.</td></tr> : riesgo.casos.map((k) => (
                      <tr key={k.id} data-testid={`riesgo-caso-${k.estado}`} style={{ background: casoAbierto === k.id ? 'var(--en-oscuro-acento-suave, #f5f3ff)' : undefined }}>
                        <td style={td}><span style={mono}>{k.id}</span><div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>por {k.origen}</div></td>
                        <td style={td}>{nombreDelTitular(k.titular)}</td>
                        <td style={td}><Etiqueta valor={k.estado} /></td>
                        <td style={{ ...td, color: k.analisis_vencido || k.comunicacion_vencida ? 'var(--en-oscuro-error, #b91c1c)' : undefined, fontSize: 12 }}>
                          {k.estado === 'concluido' ? `comunicar antes de ${hora(k.comunicar_hasta)}` : k.estado === 'abierto' || k.estado === 'en_analisis' ? `analizar antes del ${(k.analizar_hasta || '').slice(0, 10)}` : k.acuse || '—'}
                        </td>
                        <td style={td}><button type="button" onClick={() => setCasoAbierto(k.id)} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="riesgo-abrir-caso">Ver</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* El caso abierto */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }} data-testid="riesgo-expediente">
                {(() => {
                  const k = (riesgo?.casos || []).find((x) => x.id === casoAbierto);
                  if (!k) return <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: 13, margin: 0 }}>Elegí un caso para ver el expediente.</p>;
                  const trabajable = k.estado === 'abierto' || k.estado === 'en_analisis';
                  return (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                        <strong style={{ fontSize: 14 }}>{k.id} · {nombreDelTitular(k.titular)}</strong><Etiqueta valor={k.estado} />
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '6px 0' }}>
                        {k.detalle} · analista {k.analista || '—'}{k.aprobado_por ? ` · aprobó ${k.aprobado_por}` : ''}{k.acuse ? ` · acuse ${k.acuse}` : ''}
                      </div>
                      {k.alertas.length ? (
                        <div style={{ fontSize: 12, marginBottom: 6 }}><strong>Alertas:</strong> {k.alertas.map((a) => <span key={a.id} style={{ ...mono, marginRight: 6 }}>{a.regla}</span>)}</div>
                      ) : null}
                      <div style={{ fontSize: 12, maxHeight: 120, overflowY: 'auto', background: 'var(--en-oscuro-superficie-2, #f9fafb)', borderRadius: 8, padding: 8 }}>
                        {k.notas.map((n, i) => <div key={i}><strong>{n.autor}</strong> · {hora(n.momento)} · {n.texto}</div>)}
                      </div>
                      {trabajable ? (
                        <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
                          {k.estado === 'abierto' ? <button type="button" onClick={() => accionDeCaso(k.id, 'tomar')} disabled={ocupado} style={botonSuave} data-testid="riesgo-tomar">Tomar para análisis</button> : null}
                          <div style={{ display: 'flex', gap: 6 }}>
                            <input style={campo} placeholder="Una nota del análisis" value={nota} onChange={(e) => setNota(e.target.value)} data-testid="riesgo-nota" />
                            <button type="button" onClick={() => accionDeCaso(k.id, 'anotar', { texto: nota })} disabled={ocupado || !nota.trim()} style={{ ...botonSuave, padding: '6px 10px' }} data-testid="riesgo-anotar">Anotar</button>
                          </div>
                          {k.estado === 'en_analisis' ? (
                            <>
                              <input style={campo} placeholder="Conclusión del análisis" value={conclusion} onChange={(e) => setConclusion(e.target.value)} data-testid="riesgo-conclusion" />
                              <div style={{ display: 'flex', gap: 6 }}>
                                <button type="button" onClick={() => accionDeCaso(k.id, 'concluir', { conclusion, comunicar: true })} disabled={ocupado || !conclusion.trim()} style={boton} data-testid="riesgo-concluir-comunicar"><FileText size={13} /> Concluir y comunicar al COAF</button>
                                <button type="button" onClick={() => accionDeCaso(k.id, 'concluir', { conclusion, comunicar: false })} disabled={ocupado || !conclusion.trim()} style={botonSuave} data-testid="riesgo-concluir-archivar">Concluir sin comunicar</button>
                              </div>
                            </>
                          ) : null}
                        </div>
                      ) : null}
                      {k.estado === 'concluido' ? (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto, #374151)', marginBottom: 6 }}>Concluido por <strong>{k.analista}</strong>: {k.conclusion}. Falta la segunda firma (otra persona).</div>
                          <button type="button" onClick={() => accionDeCaso(k.id, 'aprobar_comunicacion')} disabled={ocupado} style={boton} data-testid="riesgo-aprobar-comunicacion">Aprobar y comunicar al COAF</button>
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </div>
            </div>

            {/* Alertas */}
            <div style={{ overflowX: 'auto', marginTop: 12 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }} data-testid="riesgo-alertas">
                <thead><tr><th style={th}>Alerta</th><th style={th}>Regla</th><th style={th}>Titular</th><th style={th}>Operación</th><th style={th}>Detalle</th><th style={th}>Caso</th></tr></thead>
                <tbody>
                  {!riesgo || riesgo.alertas.length === 0 ? <tr><td style={td} colSpan={6}>Ninguna alerta del monitoreo.</td></tr> : riesgo.alertas.map((a) => (
                    <tr key={a.id} data-testid="riesgo-alerta">
                      <td style={{ ...td, ...mono }}>{a.id}</td><td style={td}><strong>{a.regla.replaceAll('_', ' ')}</strong></td>
                      <td style={td}>{nombreDelTitular(a.titular)}</td><td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{a.operacion}</td>
                      <td style={{ ...td, fontSize: 12 }}>{Object.entries(a.detalle).map(([k, v]) => `${k} ${typeof v === 'number' && v > 1000 ? centavos(v) : v}`).join(' · ')}</td>
                      <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{a.caso || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Comunicaciones */}
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--en-oscuro-texto, #374151)' }}>Comunicaciones al COAF ({riesgo?.comunicaciones.length || 0}) · <button type="button" onClick={declararNoOcurrencia} disabled={ocupado} style={{ ...botonSuave, padding: '3px 8px', fontSize: 12 }} data-testid="riesgo-no-ocurrencia">Declarar no ocurrencia del año pasado</button></summary>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="riesgo-comunicaciones">
                <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Caso / período</th><th style={th}>Acuse</th><th style={th}>Firmas</th></tr></thead>
                <tbody>
                  {(riesgo?.comunicaciones || []).map((m) => (
                    <tr key={m.id} data-testid="riesgo-comunicacion"><td style={{ ...td, ...mono }}>{m.id}</td><td style={td}>{m.tipo.replaceAll('_', ' ')}</td>
                      <td style={{ ...td, ...mono }}>{m.caso || m.periodo}</td><td style={{ ...td, ...mono }}>{m.acuse}</td><td style={td}>{m.enviada_por} · {m.aprobada_por}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          {/* Reportes regulatorios: balancete COSIF, CCS, e-Financeira */}
          <div style={tarjeta} data-testid="nucleo-reportes">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><FileOutput size={16} /> Reportes regulatorios: balancete COSIF, CCS y e-Financeira {reportes ? `· ${reportes.transmisor}` : ''}</strong>
              {reportes ? (
                <span style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
                  {Object.entries(reportes.resumen).map(([t, r]) => `${t}: ${r.generados} generados, ${r.transmitidos} transmitidos`).join(' · ')}
                </span>
              ) : null}
            </div>
            <p style={{ margin: '8px 0 10px', fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', lineHeight: 1.5 }}>
              Se generan sólo sobre días cerrados en el libro; al cerrar un día, la cola genera sola lo que quedó completo (el CCS del día, el balancete del mes, la e-Financeira del semestre).
              Generar de nuevo un período deja una versión nueva (sustitución), nunca pisa la anterior. Transmitir es siempre de una persona. Los códigos COSIF son provisorios hasta que el contador los confirme.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 10 }}>
              <div style={{ width: 160 }}>
                <div style={rotulo}>Reporte</div>
                <select style={campo} value={pedidoDeReporte.tipo} onChange={(e) => setPedidoDeReporte({ tipo: e.target.value, periodo: { balancete: new Date().toISOString().slice(0, 7), ccs: new Date().toISOString().slice(0, 10), efinanceira: `${new Date().getFullYear()}-S${new Date().getMonth() < 6 ? 1 : 2}`, incidentes: String(new Date().getFullYear() - 1), ouvidoria: `${new Date().getFullYear() - (new Date().getMonth() < 6 ? 1 : 0)}-S${new Date().getMonth() < 6 ? 2 : 1}` }[e.target.value] })} data-testid="reportes-tipo">
                  <option value="balancete">Balancete COSIF (4010)</option>
                  <option value="ccs">CCS del día</option>
                  <option value="efinanceira">e-Financeira</option>
                  <option value="incidentes">Informe anual de incidentes</option>
                  <option value="ouvidoria">Informe semestral de la ouvidoria</option>
                </select>
              </div>
              <div style={{ width: 140 }}>
                <div style={rotulo}>Período</div>
                <input style={campo} value={pedidoDeReporte.periodo} onChange={(e) => setPedidoDeReporte({ ...pedidoDeReporte, periodo: e.target.value })} placeholder="2026-09 · 2026-09-21 · 2026-S2" data-testid="reportes-periodo" />
              </div>
              <button type="button" onClick={generarReporte} disabled={ocupado} style={boton} data-testid="reportes-generar"><FileText size={13} /> Generar</button>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }} data-testid="reportes-tabla">
                <thead><tr><th style={th}>Nº</th><th style={th}>Documento</th><th style={th}>Período</th><th style={th}>Versión</th><th style={th}>Resumen</th><th style={th}>Estado</th><th style={th}>Protocolo</th><th style={th} /></tr></thead>
                <tbody>
                  {!reportes || reportes.reportes.length === 0 ? <tr><td style={td} colSpan={8}>Ningún reporte generado.</td></tr> : reportes.reportes.map((r) => (
                    <tr key={r.id} data-testid={`reportes-${r.estado}`} style={{ background: reporteAbierto?.id === r.id ? 'var(--en-oscuro-acento-suave, #f5f3ff)' : undefined }}>
                      <td style={{ ...td, ...mono }}>{r.id}</td>
                      <td style={td}>{r.documento}<div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>por {r.generado_por} · {hora(r.generado_en)}</div></td>
                      <td style={{ ...td, ...mono }}>{r.periodo}</td>
                      <td style={td}>{r.version}{r.resumen.tipo_remessa ? ` (${r.resumen.tipo_remessa})` : ''}</td>
                      <td style={{ ...td, fontSize: 12 }}>
                        {r.tipo === 'balancete' ? `${r.resumen.contas} cuentas COSIF · ${r.resumen.cuadra ? 'cuadra' : 'NO CUADRA'} · R$ ${centavos(r.resumen.total_debe)}` : null}
                        {r.tipo === 'ccs' ? `${r.resumen.altas} altas · ${r.resumen.bajas} bajas` : null}
                        {r.tipo === 'efinanceira' ? `${r.resumen.declarados} titulares · ${r.resumen.meses_informados} meses` : null}
                        {r.tipo === 'incidentes' ? `${r.resumen.total} incidentes · ${r.resumen.relevantes} relevantes · ${r.resumen.comunicados} comunicados` : null}
                        {r.tipo === 'ouvidoria' ? `${r.resumen.total} reclamos · ${r.resumen.respondidos} respondidos · ${r.resumen.en_plazo} en plazo` : null}
                      </td>
                      <td style={td}><Etiqueta valor={r.estado} /></td>
                      <td style={{ ...td, ...mono }}>{r.protocolo || '—'}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        <button type="button" onClick={() => verReporte(r.id)} style={{ ...botonSuave, padding: '5px 9px', marginRight: 6 }} data-testid="reportes-ver">{reporteAbierto?.id === r.id ? 'Cerrar' : 'Ver archivo'}</button>
                        {r.estado === 'generado' ? <button type="button" onClick={() => { setPidiendo({ tipo: 'reporte', id: r.id }); setMotivo(''); }} disabled={ocupado} style={{ ...boton, padding: '5px 9px' }} data-testid="reportes-transmitir"><Eye size={12} /> Pedir transmisión</button> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {reporteAbierto ? (
              <pre style={{ ...mono, background: 'var(--en-oscuro-superficie-2, #f9fafb)', border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 8, padding: 10, marginTop: 10, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap' }} data-testid="reportes-archivo">{reporteAbierto.archivo}</pre>
            ) : null}
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--en-oscuro-texto, #374151)' }}>Plan de cuentas y su código COSIF (provisorio)</summary>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="reportes-cosif">
                <thead><tr><th style={th}>Cuenta</th><th style={th}>Nombre</th><th style={th}>COSIF</th></tr></thead>
                <tbody>
                  {(reportes?.cosif || []).map((c) => (
                    <tr key={c.codigo}><td style={{ ...td, ...mono }}>{c.codigo}</td><td style={td}>{c.nombre}</td><td style={{ ...td, ...mono }}>{c.cosif}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          {/* Cumplimiento: calendario, incidentes, ouvidoria */}
          <div style={tarjeta} data-testid="nucleo-cumplimiento">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><CalendarClock size={16} /> Cumplimiento: calendario de obligaciones, incidentes y ouvidoria</strong>
              {cumplimiento ? (
                <span style={{ fontSize: 13, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  <span>Obligaciones pendientes <strong>{cumplimiento.resumen_calendario.pendientes}</strong></span>
                  <span style={{ color: cumplimiento.resumen_calendario.vencidas ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>Vencidas <strong>{cumplimiento.resumen_calendario.vencidas}</strong></span>
                  <span style={{ color: cumplimiento.resumen_calendario.acciones_vencidas ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>Acciones con plazo <strong>{cumplimiento.resumen_calendario.acciones}</strong></span>
                </span>
              ) : null}
            </div>

            {/* Acciones con plazo */}
            {cumplimiento && cumplimiento.acciones.length > 0 ? (
              <div style={{ margin: '10px 0', padding: 10, borderRadius: 10, background: 'var(--en-oscuro-alerta-suave, #fff7ed)', border: '1px solid var(--en-oscuro-alerta-borde, #fed7aa)' }} data-testid="cumplimiento-acciones">
                <strong style={{ fontSize: 13 }}>Hay que hacer</strong>
                {cumplimiento.acciones.map((a) => (
                  <div key={a.referencia} style={{ fontSize: 13, marginTop: 4, color: a.vencido ? 'var(--en-oscuro-error, #b91c1c)' : 'var(--en-oscuro-error, #7c2d12)' }} data-testid={`cumplimiento-accion-${a.accion}`}>
                    {a.accion === 'comunicar_incidente' ? 'Comunicar al BCB' : 'Responder el reclamo'} · {a.titulo} · vence {a.vence.length > 10 ? fechaYHora(a.vence) : a.vence}{a.vencido ? ' · VENCIDO' : ` · ${a.dias} día${a.dias === 1 ? '' : 's'}`} <span style={{ color: 'var(--en-oscuro-error, #9a3412)' }}>({a.fuente})</span>
                  </div>
                ))}
              </div>
            ) : null}

            {/* Calendario */}
            <div style={{ overflowX: 'auto', marginTop: 10 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }} data-testid="cumplimiento-calendario">
                <thead><tr><th style={th}>Obligación</th><th style={th}>Período</th><th style={th}>Vence</th><th style={th}>Estado</th><th style={th}>Fuente · plazo</th><th style={th} /></tr></thead>
                <tbody>
                  {!cumplimiento || cumplimiento.calendario.length === 0 ? <tr><td style={td} colSpan={6}>Ninguna obligación con período terminado todavía.</td></tr> : cumplimiento.calendario.map((o) => (
                    <tr key={`${o.obligacion}-${o.periodo}`} data-testid={`calendario-${o.estado}`} style={{ background: o.vencido ? 'var(--en-oscuro-error-suave, #fef2f2)' : undefined }}>
                      <td style={td}>{{ balancete: 'Balancete COSIF (4010)', ccs: 'CCS del día', efinanceira: 'e-Financeira', no_ocurrencia: 'No ocurrencia al COAF', incidentes: 'Informe anual de incidentes', ouvidoria: 'Informe de la ouvidoria' }[o.obligacion]}{o.detalle ? <div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{o.detalle}</div> : null}</td>
                      <td style={{ ...td, ...mono }}>{o.periodo}</td>
                      <td style={{ ...td, color: o.vencido ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>{o.vence}{o.estado === 'pendiente' ? <div style={{ fontSize: 11 }}>{o.vencido ? `vencido hace ${-o.dias} días` : `faltan ${o.dias} días`}</div> : null}</td>
                      <td style={td}><Etiqueta valor={o.estado} />{o.protocolo ? <div style={{ ...mono, fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{o.protocolo}</div> : null}</td>
                      <td style={{ ...td, fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{o.fuente}<div>{o.plazo}</div></td>
                      <td style={td}>{o.estado === 'pendiente' && o.obligacion !== 'no_ocurrencia' ? <button type="button" onClick={() => generarDelCalendario(o.obligacion, o.periodo)} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="calendario-generar">Generar</button> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginTop: 14 }}>
              {/* Incidentes */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Incidentes (Res. BCB 85/2021)</strong>
                {cumplimiento ? <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '4px 0 8px' }}>Abiertos {cumplimiento.resumen_incidentes.abierto} · cerrados {cumplimiento.resumen_incidentes.cerrado} · relevantes sin comunicar <strong style={{ color: cumplimiento.resumen_incidentes.relevantes_sin_comunicar ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>{cumplimiento.resumen_incidentes.relevantes_sin_comunicar}</strong></div> : null}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <select style={campo} value={nuevoIncidente.tipo} onChange={(e) => setNuevoIncidente({ ...nuevoIncidente, tipo: e.target.value })} data-testid="incidentes-tipo">
                    {(cumplimiento?.tipos_de_incidente || []).map((t) => <option key={t} value={t}>{t.replaceAll('_', ' ')}</option>)}
                  </select>
                  <input style={campo} type="number" min="0" placeholder="Clientes afectados" value={nuevoIncidente.clientes_afectados} onChange={(e) => setNuevoIncidente({ ...nuevoIncidente, clientes_afectados: e.target.value })} data-testid="incidentes-clientes" />
                  <input style={{ ...campo, gridColumn: '1 / -1' }} placeholder="Qué pasó (título)" value={nuevoIncidente.titulo} onChange={(e) => setNuevoIncidente({ ...nuevoIncidente, titulo: e.target.value })} data-testid="incidentes-titulo" />
                  <input style={{ ...campo, gridColumn: '1 / -1' }} placeholder="Impacto" value={nuevoIncidente.impacto} onChange={(e) => setNuevoIncidente({ ...nuevoIncidente, impacto: e.target.value })} data-testid="incidentes-impacto" />
                  <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <input type="checkbox" checked={nuevoIncidente.relevante} onChange={(e) => setNuevoIncidente({ ...nuevoIncidente, relevante: e.target.checked })} data-testid="incidentes-relevante" /> Relevante: se comunica al BCB
                  </label>
                  <button type="button" onClick={abrirIncidente} disabled={ocupado} style={boton} data-testid="incidentes-registrar"><Siren size={13} /> Registrar incidente</button>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 10 }} data-testid="incidentes-tabla">
                  <thead><tr><th style={th}>Incidente</th><th style={th}>Estado</th><th style={th}>BCB</th><th style={th} /></tr></thead>
                  <tbody>
                    {!cumplimiento || cumplimiento.incidentes.length === 0 ? <tr><td style={td} colSpan={4}>Ningún incidente registrado.</td></tr> : cumplimiento.incidentes.map((i) => (
                      <tr key={i.id} data-testid={`incidentes-${i.estado}`} style={{ background: incidenteAbierto === i.id ? 'var(--en-oscuro-acento-suave, #f5f3ff)' : undefined }}>
                        <td style={td}><strong>{i.titulo}</strong><div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{i.tipo.replaceAll('_', ' ')} · {i.clientes_afectados} clientes · desde {hora(i.inicio)}{i.fin ? ` hasta ${hora(i.fin)}` : ''}</div></td>
                        <td style={td}><Etiqueta valor={i.estado} /></td>
                        <td style={{ ...td, fontSize: 12 }}>{!i.relevante ? 'no relevante' : i.protocolo ? <span style={mono}>{i.protocolo}</span> : <span style={{ color: i.comunicacion_vencida ? 'var(--en-oscuro-error, #b91c1c)' : 'var(--en-oscuro-alerta, #92400e)' }}>comunicar antes de {fechaYHora(i.comunicar_hasta)}</span>}</td>
                        <td style={td}><button type="button" onClick={() => setIncidenteAbierto(incidenteAbierto === i.id ? null : i.id)} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="incidentes-ver">Ver</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {incidenteAbierto ? (() => {
                  const i = (cumplimiento?.incidentes || []).find((x) => x.id === incidenteAbierto);
                  if (!i) return null;
                  return (
                    <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: 'var(--en-oscuro-superficie-2, #f9fafb)', fontSize: 13 }} data-testid="incidentes-expediente">
                      <div><strong>{i.id}</strong> · {i.impacto}{i.causa ? <> · <strong>Causa:</strong> {i.causa} · <strong>Acciones:</strong> {i.acciones}</> : null}</div>
                      <div style={{ margin: '6px 0', color: 'var(--en-oscuro-texto, #374151)' }}>{i.notas.map((n, k) => <div key={k}><strong>{n.autor}</strong> · {hora(n.momento)} · {n.texto}</div>)}</div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <input style={{ ...campo, flex: 1, minWidth: 180 }} placeholder="Una nota" value={nota} onChange={(e) => setNota(e.target.value)} data-testid="incidentes-nota" />
                        <button type="button" onClick={() => accionDeIncidente(i.id, 'anotar', { texto: nota })} disabled={ocupado || !nota.trim()} style={{ ...botonSuave, padding: '6px 10px' }} data-testid="incidentes-anotar">Anotar</button>
                        {i.relevante && !i.protocolo ? <button type="button" onClick={() => { setPidiendo({ tipo: 'incidente', id: i.id }); setMotivo(''); }} disabled={ocupado} style={{ ...boton, padding: '6px 10px' }} data-testid="incidentes-comunicar"><Eye size={12} /> Pedir comunicación al BCB</button> : null}
                      </div>
                      {i.estado === 'abierto' ? (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 6, marginTop: 8 }}>
                          <input style={campo} placeholder="Causa" value={cierre.causa} onChange={(e) => setCierre({ ...cierre, causa: e.target.value })} data-testid="incidentes-causa" />
                          <input style={campo} placeholder="Acciones tomadas" value={cierre.acciones} onChange={(e) => setCierre({ ...cierre, acciones: e.target.value })} data-testid="incidentes-acciones" />
                          <button type="button" onClick={() => accionDeIncidente(i.id, 'cerrar', cierre)} disabled={ocupado || !cierre.causa.trim() || !cierre.acciones.trim()} style={botonSuave} data-testid="incidentes-cerrar">Cerrar incidente</button>
                        </div>
                      ) : null}
                    </div>
                  );
                })() : null}
              </div>

              {/* Ouvidoria */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Ouvidoria (Res. CMN 4.860/2020)</strong>
                {cumplimiento ? <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '4px 0 8px' }}>Abiertos {cumplimiento.resumen_reclamos.abierto} · respondidos {cumplimiento.resumen_reclamos.respondido} · vencidos <strong style={{ color: cumplimiento.resumen_reclamos.vencidos ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>{cumplimiento.resumen_reclamos.vencidos}</strong> · diez días hábiles para responder</div> : null}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <select style={campo} value={nuevoReclamo.canal} onChange={(e) => setNuevoReclamo({ ...nuevoReclamo, canal: e.target.value })} data-testid="ouvidoria-canal">
                    {(cumplimiento?.canales || []).map((c) => <option key={c} value={c}>{{ telefono: 'Teléfono', correo: 'Correo', panel: 'Panel del cliente', bcb: 'Vía Banco Central', procon: 'Vía Procon' }[c] || c}</option>)}
                  </select>
                  <input style={campo} placeholder="Caso de la mesa de ayuda (S-000123)" value={nuevoReclamo.caso_soporte} onChange={(e) => setNuevoReclamo({ ...nuevoReclamo, caso_soporte: e.target.value })} data-testid="ouvidoria-caso" />
                  <input style={{ ...campo, gridColumn: '1 / -1' }} placeholder="Asunto" value={nuevoReclamo.asunto} onChange={(e) => setNuevoReclamo({ ...nuevoReclamo, asunto: e.target.value })} data-testid="ouvidoria-asunto" />
                  <input style={{ ...campo, gridColumn: '1 / -1' }} placeholder="Qué reclama" value={nuevoReclamo.descripcion} onChange={(e) => setNuevoReclamo({ ...nuevoReclamo, descripcion: e.target.value })} data-testid="ouvidoria-descripcion" />
                  <button type="button" onClick={abrirReclamo} disabled={ocupado} style={{ ...boton, gridColumn: '1 / -1' }} data-testid="ouvidoria-registrar"><Plus size={13} /> Registrar reclamo</button>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 10 }} data-testid="ouvidoria-tabla">
                  <thead><tr><th style={th}>Protocolo</th><th style={th}>Asunto</th><th style={th}>Plazo</th><th style={th}>Estado</th><th style={th} /></tr></thead>
                  <tbody>
                    {!cumplimiento || cumplimiento.reclamos.length === 0 ? <tr><td style={td} colSpan={5}>Ningún reclamo.</td></tr> : cumplimiento.reclamos.map((r) => (
                      <tr key={r.id} data-testid={`ouvidoria-${r.estado}`} style={{ background: respuesta.id === r.id ? 'var(--en-oscuro-acento-suave, #f5f3ff)' : undefined }}>
                        <td style={{ ...td, ...mono }}>{r.protocolo}</td>
                        <td style={td}>{r.asunto}<div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{r.canal}{r.caso_soporte ? ` · mesa de ayuda ${r.caso_soporte}` : ''}{r.resultado ? ` · ${r.resultado}` : ''}</div></td>
                        <td style={{ ...td, fontSize: 12, color: r.vencido ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>{r.estado === 'abierto' ? `hasta ${r.responder_hasta}${r.vencido ? ' · VENCIDO' : ''}` : (r.en_plazo ? 'en plazo' : 'fuera de plazo')}</td>
                        <td style={td}><Etiqueta valor={r.estado} /></td>
                        <td style={td}>{r.estado === 'abierto' ? <button type="button" onClick={() => setRespuesta({ id: respuesta.id === r.id ? null : r.id, respuesta: '', resultado: 'procedente' })} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="ouvidoria-abrir-respuesta">Responder</button> : null}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {respuesta.id ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 6, marginTop: 8 }}>
                    <input style={campo} placeholder="Respuesta conclusiva al cliente" value={respuesta.respuesta} onChange={(e) => setRespuesta({ ...respuesta, respuesta: e.target.value })} data-testid="ouvidoria-respuesta" />
                    <select style={campo} value={respuesta.resultado} onChange={(e) => setRespuesta({ ...respuesta, resultado: e.target.value })} data-testid="ouvidoria-resultado">
                      {(cumplimiento?.resultados || []).map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                    <button type="button" onClick={responderReclamo} disabled={ocupado} style={boton} data-testid="ouvidoria-responder">Responder</button>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {/* Respaldo */}
          <div style={tarjeta} data-testid="nucleo-respaldo">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Archive size={16} /> Respaldo de lo que se conserva</strong>
              {respaldos ? <span style={{ fontSize: 12, color: respaldos.llave_configurada ? 'var(--en-oscuro-texto-2, #6b7280)' : 'var(--en-oscuro-alerta, #b45309)' }}>{respaldos.llave_configurada ? 'llave de respaldo configurada: los respaldos salen firmados' : 'SIN llave de respaldo (NUCLEO_SECRETO_LLAVE_DE_RESPALDO): los respaldos salen sin firma'} · {respaldos.tablas_que_se_conservan.length} tablas</span> : null}
            </div>
            <p style={{ margin: '8px 0 10px', fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', lineHeight: 1.5 }}>
              Exporta el libro, los legajos, las operaciones, los casos y comunicaciones, los reportes, los incidentes, los reclamos, la bitácora y las aprobaciones (no la cola ni el simulador) en un archivo de una línea por fila, con hash de cierre y firma. <strong>El archivo se baja y se guarda afuera</strong>; la base sólo registra que se hizo. Y un respaldo que no se probó es una esperanza: la comprobación recompone la cadena del libro y de la bitácora desde el archivo.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <button type="button" onClick={crearRespaldo} disabled={ocupado} style={boton} data-testid="respaldo-crear"><Archive size={13} /> Crear y bajar un respaldo</button>
                {ultimoRespaldo ? (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--en-oscuro-texto, #374151)' }} data-testid="respaldo-ultimo">
                    <div>{ultimoRespaldo.filas} filas · hash <span style={mono}>{ultimoRespaldo.hash.slice(0, 16)}…</span></div>
                    <div>{ultimoRespaldo.firmado ? <>Firma (guardala junto al archivo): <span style={{ ...mono, wordBreak: 'break-all' }} data-testid="respaldo-firma">{ultimoRespaldo.firma}</span></> : 'Sin firma: falta la llave de respaldo.'}</div>
                  </div>
                ) : null}
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 10 }} data-testid="respaldo-tabla">
                  <thead><tr><th style={th}>Cuándo</th><th style={th}>Quién</th><th style={th}>Filas</th><th style={th}>Firmado</th><th style={th}>Comprobación</th></tr></thead>
                  <tbody>
                    {!respaldos || respaldos.respaldos.length === 0 ? <tr><td style={td} colSpan={5}>Ningún respaldo todavía.</td></tr> : respaldos.respaldos.map((r) => (
                      <tr key={r.id} data-testid="respaldo-fila">
                        <td style={{ ...td, fontSize: 12 }}>{fechaYHora(r.momento)}<div style={{ ...mono, fontSize: 10, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>{r.hash.slice(0, 16)}…</div></td>
                        <td style={{ ...td, fontSize: 12 }}>{r.actor}</td>
                        <td style={{ ...td, fontSize: 12 }}>{r.filas} · {(r.bytes / 1024).toFixed(1)} KB</td>
                        <td style={td}>{r.firmado ? <Etiqueta valor="hecho" /> : <Etiqueta valor="pendiente" />}</td>
                        <td style={{ ...td, fontSize: 12 }}>{r.comprobacion ? <span style={{ color: r.comprobacion.ok ? 'var(--en-oscuro-exito, #166534)' : 'var(--en-oscuro-error, #b91c1c)' }} data-testid={`respaldo-comprobado-${r.comprobacion.ok ? 'ok' : 'falla'}`}>{r.comprobacion.ok ? 'íntegro' : 'NO PASA'} · {fechaYHora(r.comprobado_en)}</span> : <span style={{ color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>sin comprobar</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}><FileCheck size={14} /> Comprobar un respaldo</strong>
                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  <input type="file" accept=".jsonl,.txt,application/x-ndjson" onChange={elegirArchivo} style={{ fontSize: 13 }} data-testid="respaldo-archivo" />
                  {aComprobar.nombre ? <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{aComprobar.nombre} · {(aComprobar.contenido.length / 1024).toFixed(1)} KB</div> : null}
                  <input style={campo} placeholder="Firma (la que se guardó junto al archivo; opcional)" value={aComprobar.firma} onChange={(e) => setAComprobar({ ...aComprobar, firma: e.target.value })} data-testid="respaldo-firma-a-comprobar" />
                  <button type="button" onClick={comprobarRespaldo} disabled={ocupado || !aComprobar.contenido} style={botonSuave} data-testid="respaldo-comprobar">Comprobar</button>
                </div>
                {comprobacion ? (
                  <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: comprobacion.ok ? 'var(--en-oscuro-exito-suave, #f0fdf4)' : 'var(--en-oscuro-error-suave, #fef2f2)', fontSize: 13 }} data-testid={`respaldo-resultado-${comprobacion.ok ? 'ok' : 'falla'}`}>
                    <div><strong>{comprobacion.ok ? 'Íntegro' : 'NO PASA'}</strong>{comprobacion.motivo ? ` · ${comprobacion.motivo}` : ''}</div>
                    <div style={{ color: 'var(--en-oscuro-texto, #374151)', marginTop: 4 }}>hash del cierre {comprobacion.hash_ok ? 'coincide' : 'NO coincide'} · firma {comprobacion.firma.replaceAll('_', ' ')} · {comprobacion.filas} filas{comprobacion.libro ? ` · libro ${comprobacion.libro.ok ? 'encadena' : 'ROTO'} (${comprobacion.libro.asientos} asientos)` : ''}{comprobacion.bitacora ? ` · bitácora ${comprobacion.bitacora.ok ? 'encadena' : 'ROTA'} (${comprobacion.bitacora.renglones} renglones)` : ''}{comprobacion.registrado ? ' · es uno de los registrados' : ' · no figura entre los registrados'}</div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {/* Salud, secretos y métricas */}
          <div style={tarjeta} data-testid="nucleo-salud">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><HeartPulse size={16} style={{ color: salud ? (salud.ok ? '#166534' : '#b91c1c') : undefined }} /> Salud del núcleo {salud ? (salud.ok ? '· sano' : '· NO SANO') : ''}</strong>
              {salud ? <span style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>Revisado {fechaYHora(salud.revisado_en)} · la vigilancia avisa al equipo sólo cuando cambia · {salud.vigilancia.avisadores} avisador{salud.vigilancia.avisadores === 1 ? '' : 'es'} · sonda anónima en /api/health/nucleo</span> : null}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 10 }}>
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Comprobaciones</strong>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }} data-testid="salud-comprobaciones">
                  <tbody>
                    {(salud?.comprobaciones || []).map((c) => (
                      <tr key={c.nombre} data-testid={`salud-${c.ok ? 'ok' : 'falla'}`}>
                        <td style={{ ...td, width: 18 }}>{c.ok ? <ShieldCheck size={15} style={{ color: 'var(--en-oscuro-exito, #166534)' }} /> : <ShieldAlert size={15} style={{ color: c.grave ? '#b91c1c' : '#b45309' }} />}</td>
                        <td style={{ ...td, fontWeight: 600 }}>{c.nombre}{c.grave ? <span style={{ fontSize: 10, color: 'var(--en-oscuro-texto-2, #6b7280)', marginLeft: 4 }}>grave</span> : null}</td>
                        <td style={{ ...td, fontSize: 12, color: c.ok ? 'var(--en-oscuro-texto, #374151)' : 'var(--en-oscuro-error, #b91c1c)' }}>{c.detalle}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}><KeyRound size={14} /> Secretos {secretos ? <span style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>· puerto {secretos.puerto} · nunca se muestra el valor, sólo la huella</span> : null}</strong>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }} data-testid="secretos-tabla">
                  <thead><tr><th style={th}>Secreto</th><th style={th}>Está</th><th style={th}>Huella</th></tr></thead>
                  <tbody>
                    {(secretos?.secretos || []).map((s) => (
                      <tr key={s.nombre} data-testid={`secretos-${s.configurado ? 'configurado' : 'falta'}`}>
                        <td style={td}><span style={mono}>{s.nombre}</span>{s.obligatorio ? <span style={{ fontSize: 10, color: 'var(--en-oscuro-texto-2, #6b7280)', marginLeft: 4 }}>obligatorio</span> : null}<div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{s.para_que} · <span style={mono}>{s.variable}</span></div></td>
                        <td style={td}>{s.configurado ? <Etiqueta valor="hecho" /> : <Etiqueta valor={s.obligatorio ? 'muerto' : 'pendiente'} />}</td>
                        <td style={{ ...td, ...mono, fontSize: 11 }}>{s.huella || '—'}{s.rotado ? ' · rotado' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--en-oscuro-texto, #374151)', display: 'flex', alignItems: 'center', gap: 6 }}><Gauge size={14} /> Métricas (también en texto plano para un tablero: /api/nucleo/laboratorio/metricas/texto)</summary>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 8, marginTop: 8 }} data-testid="metricas-grilla">
                {Object.entries(metricas || {}).map(([k, v]) => (
                  <div key={k} style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 8, padding: '8px 10px' }} data-testid="metricas-valor">
                    <div style={rotulo}>{k.replaceAll('_', ' ')}</div>
                    <div style={{ fontSize: 18, fontWeight: 700 }}>{k.endsWith('centavos') ? `R$ ${centavos(v)}` : v}</div>
                  </div>
                ))}
              </div>
            </details>
          </div>

          {/* Operación: cuatro ojos y bitácora */}
          <div style={tarjeta} data-testid="nucleo-operacion">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Eye size={16} /> Operación: cuatro ojos y bitácora</strong>
              {operacion ? (
                <span style={{ fontSize: 13, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  <span>Pedidos pendientes <strong>{operacion.resumen_aprobaciones.pendiente}</strong></span>
                  <span>Ejecutados <strong>{operacion.resumen_aprobaciones.ejecutado}</strong></span>
                  <span style={{ color: operacion.resumen_aprobaciones.fallido ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>Fallidos <strong>{operacion.resumen_aprobaciones.fallido}</strong></span>
                  <span style={{ color: operacion.cadena_de_la_bitacora.ok ? 'var(--en-oscuro-exito, #166534)' : 'var(--en-oscuro-error, #b91c1c)' }}>Bitácora {operacion.cadena_de_la_bitacora.ok ? 'íntegra' : 'ROTA'} · {operacion.cadena_de_la_bitacora.asientos} renglones</span>
                </span>
              ) : null}
            </div>
            <p style={{ margin: '8px 0 10px', fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', lineHeight: 1.5 }}>
              Transmitir un reporte, comunicar un incidente al BCB y cambiar la configuración del núcleo mientras está prendido se <strong>piden</strong> acá y <strong>otra persona los aprueba</strong>; recién ahí se ejecutan. Quien pide no puede aprobar. Un pedido vence a las 72 horas. Todo queda en la bitácora, encadenada por hash como el libro.
              {' '}Con el núcleo prendido, la pantalla de Configuración rechaza los ajustes del núcleo y manda acá.
            </p>

            {pidiendo ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 10, borderRadius: 10, background: 'var(--en-oscuro-acento-suave, #eef2ff)', marginBottom: 10 }} data-testid="operacion-pedido-en-curso">
                <span style={{ fontSize: 13 }}>{pidiendo.tipo === 'reporte' ? `Pedir la transmisión del reporte ${pidiendo.id}` : `Pedir la comunicación al BCB del incidente ${pidiendo.id}`} · motivo:</span>
                <input style={{ ...campo, flex: 1 }} placeholder="Por qué (lo lee quien aprueba)" value={motivo} onChange={(e) => setMotivo(e.target.value)} data-testid="operacion-motivo" />
                <button type="button" onClick={pedirConMotivo} disabled={ocupado} style={boton} data-testid="operacion-pedir">Pedir</button>
                <button type="button" onClick={() => setPidiendo(null)} style={botonSuave}>Cancelar</button>
              </div>
            ) : null}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
              {/* Pedidos */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14 }}>Pedidos de cuatro ojos</strong>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, margin: '8px 0' }}>
                  <select style={campo} value={pedidoDeConfig.clave} onChange={(e) => setPedidoDeConfig({ ...pedidoDeConfig, clave: e.target.value })} data-testid="operacion-clave">
                    {(operacion?.claves_configurables || []).map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                  <input style={campo} placeholder="Valor nuevo" value={pedidoDeConfig.valor} onChange={(e) => setPedidoDeConfig({ ...pedidoDeConfig, valor: e.target.value })} data-testid="operacion-valor" />
                  <input style={campo} placeholder="Motivo" value={pedidoDeConfig.motivo} onChange={(e) => setPedidoDeConfig({ ...pedidoDeConfig, motivo: e.target.value })} data-testid="operacion-motivo-config" />
                  <button type="button" onClick={pedirConfiguracion} disabled={ocupado} style={boton} data-testid="operacion-pedir-config"><Eye size={13} /> Pedir el cambio</button>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ color: 'var(--en-oscuro-texto-2, #6b7280)', fontSize: 12 }}>Decidir como (laboratorio):</span>
                  <input style={{ ...campo, width: 150, padding: '5px 8px' }} placeholder="p. ej. jefa" value={como} onChange={(e) => setComo(e.target.value)} data-testid="operacion-como" />
                  <input style={{ ...campo, flex: 1, padding: '5px 8px' }} placeholder="Nota de la decisión (opcional)" value={notaDeDecision} onChange={(e) => setNotaDeDecision(e.target.value)} data-testid="operacion-nota" />
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }} data-testid="operacion-aprobaciones">
                  <thead><tr><th style={th}>Pedido</th><th style={th}>Estado</th><th style={th}>Quién</th><th style={th} /></tr></thead>
                  <tbody>
                    {!operacion || operacion.aprobaciones.length === 0 ? <tr><td style={td} colSpan={4}>Ningún pedido.</td></tr> : operacion.aprobaciones.map((a) => (
                      <tr key={a.id} data-testid={`operacion-${a.estado}`}>
                        <td style={td}><strong>{a.accion.replaceAll('_', ' ')}</strong> · <span style={mono}>{a.objetivo}</span>{a.accion === 'configurar' ? ` → ${a.carga.valor}` : ''}<div style={{ fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{a.motivo}{a.resultado ? ` · ${a.resultado}` : ''}{a.nota ? ` · nota: ${a.nota}` : ''}</div></td>
                        <td style={td}><Etiqueta valor={a.estado} /></td>
                        <td style={{ ...td, fontSize: 12 }}>pidió {a.pedido_por}{a.decidido_por ? <><br />decidió {a.decidido_por}</> : <><br />vence {fechaYHora(a.vence_en)}</>}</td>
                        <td style={{ ...td, whiteSpace: 'nowrap' }}>
                          {a.estado === 'pendiente' ? <>
                            <button type="button" onClick={() => decidir(a.id, true)} disabled={ocupado} style={{ ...boton, padding: '5px 9px', marginRight: 4 }} data-testid="operacion-aprobar">Aprobar</button>
                            <button type="button" onClick={() => decidir(a.id, false)} disabled={ocupado} style={{ ...botonSuave, padding: '5px 9px' }} data-testid="operacion-rechazar">Rechazar</button>
                          </> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Bitácora */}
              <div style={{ border: '1px solid var(--en-oscuro-linea, #f3f4f6)', borderRadius: 10, padding: 12 }}>
                <strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}><ScrollText size={14} /> Bitácora {operacion ? <span style={{ fontSize: 11, color: operacion.cadena_de_la_bitacora.ok ? 'var(--en-oscuro-exito, #166534)' : 'var(--en-oscuro-error, #b91c1c)' }}>{operacion.cadena_de_la_bitacora.ok ? '· cadena íntegra' : `· ROTA en el renglón ${operacion.cadena_de_la_bitacora.roto_en}`}</span> : null}</strong>
                <div style={{ maxHeight: 360, overflow: 'auto', marginTop: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }} data-testid="operacion-bitacora">
                    <thead><tr><th style={th}>Cuándo</th><th style={th}>Quién</th><th style={th}>Qué</th><th style={th}>Sobre</th></tr></thead>
                    <tbody>
                      {!operacion || operacion.bitacora.length === 0 ? <tr><td style={td} colSpan={4}>Todavía nada.</td></tr> : operacion.bitacora.map((b) => (
                        <tr key={b.id} data-testid="operacion-renglon">
                          <td style={{ ...td, fontSize: 12, whiteSpace: 'nowrap' }}>{fechaYHora(b.momento)}</td>
                          <td style={{ ...td, fontSize: 12 }}>{b.actor}</td>
                          <td style={{ ...td, fontSize: 12 }}><strong>{b.accion}</strong>{b.detalle ? <div style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{b.detalle}</div> : null}{b.antes || b.despues ? <div style={{ ...mono, fontSize: 11, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{b.antes ? `antes ${JSON.stringify(b.antes)} ` : ''}{b.despues ? `después ${JSON.stringify(b.despues)}` : ''}</div> : null}</td>
                          <td style={{ ...td, ...mono, fontSize: 11 }}>{b.objetivo}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
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
                  <span style={{ color: cola.resumen.muerto ? 'var(--en-oscuro-error, #b91c1c)' : undefined }}>Muertos <strong>{cola.resumen.muerto}</strong></span>
                  <span>Eventos <strong>{cola.resumen.eventos}</strong> ({cola.resumen.eventos_sin_publicar} sin despachar)</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--en-oscuro-texto-2, #6b7280)', marginBottom: 8 }} data-testid="nucleo-trabajador">
                  Trabajador <span style={mono}>{cola.trabajador.nombre}</span> · {cola.trabajador.corriendo ? 'corriendo' : 'parado'}
                  {' · '}{cola.trabajador.vueltas} vueltas · última {hora(cola.trabajador.ultima_vuelta)}
                  {cola.trabajador.ultimo_error ? <span style={{ color: 'var(--en-oscuro-error, #b91c1c)' }}> · último error: {cola.trabajador.ultimo_error}</span> : null}
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }} data-testid="nucleo-trabajos">
                    <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Clave</th><th style={th}>Estado</th><th style={th}>Intentos</th><th style={th}>Próximo</th><th style={th}>Resultado / último error</th><th style={th} /></tr></thead>
                    <tbody>
                      {cola.trabajos.length === 0 ? <tr><td style={td} colSpan={8}>La cola está vacía.</td></tr> : cola.trabajos.map((t) => (
                        <tr key={t.id} data-testid={`nucleo-trabajo-${t.estado}`}>
                          <td style={{ ...td, ...mono }}>{t.id}</td><td style={td}>{t.tipo}</td>
                          <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{t.clave}</td>
                          <td style={td}><Etiqueta valor={t.estado} /></td>
                          <td style={td}>{t.intentos} / {t.max_intentos}</td>
                          <td style={td}>{t.estado === 'pendiente' ? hora(t.proximo_intento) : '—'}</td>
                          <td style={{ ...td, maxWidth: 320 }}>
                            {t.resultado ? <span>{t.resultado}</span> : null}
                            {t.ultimo_error ? <span style={{ color: 'var(--en-oscuro-error, #991b1b)' }}>{t.ultimo_error}</span> : null}
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
                  <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--en-oscuro-texto, #374151)' }}>Eventos (últimos {cola.eventos.length})</summary>
                  <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }} data-testid="nucleo-eventos">
                    <thead><tr><th style={th}>Nº</th><th style={th}>Tipo</th><th style={th}>Clave</th><th style={th}>Despachado</th></tr></thead>
                    <tbody>
                      {cola.eventos.length === 0 ? <tr><td style={td} colSpan={4}>Todavía no hay eventos.</td></tr> : cola.eventos.map((e) => (
                        <tr key={e.id}><td style={{ ...td, ...mono }}>{e.id}</td><td style={td}>{e.tipo}</td>
                          <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{e.clave}</td><td style={td}>{e.publicado ? hora(e.publicado) : 'pendiente'}</td></tr>
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
                      <td style={{ ...td, ...mono, color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>{c.hash_final.slice(0, 12)}…</td></tr>
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
