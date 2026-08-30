/**
 * Precios.jsx — La consola de precios: borrador, simulador, publicación.
 *
 * TRES REGLAS QUE ESTA PANTALLA HACE VISIBLES
 *
 *   1. **Una versión publicada no se edita nunca.** Publicar crea una versión
 *      nueva. Un envío de marzo tiene congelada la suya, y eso es lo que permite
 *      contestar, seis meses después, por qué costó lo que costó.
 *
 *   2. **Se simula antes de publicar.** Es lo único que evita publicar un aumento
 *      del 40 % creyendo que era del 4 %. La simulación corre la MISMA función
 *      que la cotización real, contra el borrador y contra la vigente, lado a
 *      lado — y con fecha, porque sin fecha los recargos de temporada valen 1 y
 *      un aumento de temporada del 50 % se ve como 0 %.
 *
 *   3. **La nota es obligatoria.** No es burocracia: es lo que alguien va a leer
 *      dentro de seis meses para entender por qué cambió un precio.
 *
 * GUARDAR EL BORRADOR NO PUBLICA NADA y no valida la coherencia de la tabla: se
 * tiene que poder cargar cuatro escalones un martes y volver el jueves. Lo que se
 * valida es publicar, que es cuando el número empieza a cobrarse. Las
 * advertencias igual se muestran mientras se edita.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CalendarClock, FlaskConical, History, Plus, Rocket, Save, Trash2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { fmt } from '../../../utils/format';
import { Aviso, Boton, Campo, Cargando, NoSePudoLeer, Seleccion, Texto, Vacio } from './ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from './estilos';

const CAJAS_POR_DEFECTO = [
  { nombre: 'Chica', peso_kg: '1.0', largo_cm: '20', ancho_cm: '15', alto_cm: '10',
    valor_declarado: '0', bultos: 1 },
  { nombre: 'Media', peso_kg: '5.0', largo_cm: '40', ancho_cm: '30', alto_cm: '25',
    valor_declarado: '0', bultos: 1 },
  { nombre: 'Grande y liviana', peso_kg: '3.0', largo_cm: '60', ancho_cm: '50', alto_cm: '40',
    valor_declarado: '0', bultos: 1 },
];

const num = (v) => (v === null || v === undefined || v === '' ? '—' : fmt(v, 2));

/**
 * La fecha en la hora de acá.
 *
 * El campo «Vigente desde» es un `datetime-local`: se tipea en hora local y se
 * manda en UTC. Mostrar el string UTC crudo hacía que alguien programara un
 * aumento para las 10:00 y el historial se lo mostrara a las 14:00.
 */
const local = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d.getTime()) ? String(v).slice(0, 16).replace('T', ' ')
    : d.toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' });
};

export default function Precios() {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [borrador, setBorrador] = useState(null);
  const [advertencias, setAdvertencias] = useState([]);
  const [guardando, setGuardando] = useState(false);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  // Lo tipeado que todavía no se guardó. Simular y publicar corren contra el
  // borrador GUARDADO —el backend no recibe la tabla— así que con cambios sin
  // guardar los dos mienten: se simula una tabla y se publica otra.
  const [sucio, setSucio] = useState(false);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/tarifas');
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setDatos(res.data);
      setBorrador(res.data?.borrador || null);
      setSucio(false);
    } catch (err) {
      if (!vivo.current) return;
      // El 503 de esta ruta dice, con todas las letras, «no edites hasta que
      // vuelva: lo que guardes ahora puede pisar lo que ya había». Mandarlo a un
      // toast que se va en cuatro segundos, y después mostrar la pantalla de
      // «todavía no cargaste nada», es hacer exactamente lo contrario.
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudo leer la consola de precios.'));
      }
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const guardarBorrador = async () => {
    setGuardando(true);
    try {
      const res = await api.put('/admin/envios/tarifas/borrador', borrador);
      setBorrador(res.data?.borrador || borrador);
      setAdvertencias(res.data?.advertencias || []);
      setSucio(false);
      toast.success('Borrador guardado');
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo guardar el borrador.'));
    } finally {
      setGuardando(false);
    }
  };

  if (cargando) return <Cargando texto="Leyendo la consola de precios…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="la consola de precios" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }
  if (!borrador) {
    return (
      <Vacio titulo="No hay borrador ni versión vigente">
        Todavía no se publicó ninguna tarifa. Volvé a cargar la pantalla, o pedile al equipo la
        primera tabla de escalones.
      </Vacio>
    );
  }

  const escalones = borrador.escalones_peso || [];
  const editar = (fn) => { setSucio(true); setBorrador(fn); };
  const cambiar = (campo, valor) => editar((b) => ({ ...b, [campo]: valor }));
  const cambiarEscalon = (i, campo) => (e) => editar((b) => {
    const copia = [...(b.escalones_peso || [])];
    copia[i] = { ...copia[i], [campo]: e.target.value };
    return { ...b, escalones_peso: copia };
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <Vigente vigente={datos?.vigente} origen={datos?.origen_borrador} />

      <div style={tarjeta}>
        <h3 style={titulo}>La tabla de escalones</h3>
        <p style={bajada}>
          El precio del servicio propio es una función de una sola variable: el peso facturable.
          Un <strong>hueco</strong> deja un peso sin precio y la cotización cae al escalón
          anterior; un <strong>solape</strong> hace que dos filas contesten distinto para el
          mismo peso. Las dos cosas se avisan al guardar y bloquean al publicar.
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: COLOR.suave }}>
                {['Desde (kg)', 'Hasta (kg)', `Precio (${borrador.moneda || 'RIS'})`, ''].map((h) => (
                  <th key={h} style={{ padding: '8px 10px', fontWeight: 600,
                    borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {escalones.map((e, i) => (
                <tr key={i}>
                  <td style={{ padding: '4px 10px' }}>
                    <Texto value={e.desde_kg ?? ''} onChange={cambiarEscalon(i, 'desde_kg')} />
                  </td>
                  <td style={{ padding: '4px 10px' }}>
                    <Texto value={e.hasta_kg ?? ''} onChange={cambiarEscalon(i, 'hasta_kg')} />
                  </td>
                  <td style={{ padding: '4px 10px' }}>
                    <Texto value={e.precio ?? ''} onChange={cambiarEscalon(i, 'precio')} />
                  </td>
                  <td style={{ padding: '4px 10px' }}>
                    <button type="button" aria-label="Quitar escalón"
                      onClick={() => editar((b) => ({
                        ...b, escalones_peso: b.escalones_peso.filter((_, j) => j !== i),
                      }))}
                      style={{ border: 'none', background: 'none', cursor: 'pointer',
                        color: COLOR.error, display: 'inline-flex', padding: '6px' }}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Boton variante="secundario" style={{ marginTop: '10px' }}
          onClick={() => editar((b) => ({
            ...b,
            escalones_peso: [...(b.escalones_peso || []), {
              desde_kg: escalones.length ? escalones[escalones.length - 1].hasta_kg : '0.00',
              hasta_kg: '', precio: '',
            }],
          }))}>
          <Plus size={14} /> Agregar escalón
        </Boton>

        <div style={{ ...grilla('200px'), marginTop: '22px' }}>
          <Campo etiqueta="Adicional por kg"
            ayuda="Lo que se cobra por cada kilo por encima del último escalón. Sin esto, un paquete más pesado que la tabla no tiene precio.">
            <Texto value={borrador.adicional_por_kg ?? ''}
              onChange={(e) => cambiar('adicional_por_kg', e.target.value)} />
          </Campo>
          <Campo etiqueta="Tarifa mínima" ayuda="Ningún envío cuesta menos que esto.">
            <Texto value={borrador.tarifa_minima ?? '0'}
              onChange={(e) => cambiar('tarifa_minima', e.target.value)} />
          </Campo>
          <Campo etiqueta="Modo">
            <Seleccion value={borrador.modo_tarifa || 'peso'}
              onChange={(e) => cambiar('modo_tarifa', e.target.value)}
              opciones={[{ valor: 'peso', texto: 'Solo por peso' },
                { valor: 'peso_o_volumen', texto: 'La mayor entre peso y volumen' }]} />
          </Campo>
          <Campo etiqueta="Moneda">
            <Texto value={borrador.moneda || 'RIS'}
              onChange={(e) => cambiar('moneda', e.target.value)} maxLength={8} />
          </Campo>
        </div>

        <h4 style={{ ...titulo, marginTop: '22px' }}>Cómo cubicamos nosotros</h4>
        <div style={grilla('180px')}>
          <Campo etiqueta="Divisor volumétrico"
            ayuda="Sin divisor, un bulto grande y liviano cotiza solo por su peso real.">
            <Texto type="number" value={borrador.regla_peso?.divisor ?? ''}
              invalido={!borrador.regla_peso?.divisor}
              onChange={(e) => cambiar('regla_peso', {
                ...(borrador.regla_peso || {}),
                // Sin el `|| 5000` a propósito: borrar el campo para retipearlo
                // y guardar grababa 5000 con un toast verde, y el divisor cambia
                // el peso facturable de todo bulto grande y liviano.
                divisor: e.target.value === '' ? '' : Number(e.target.value),
              })} />
          </Campo>
          <Campo etiqueta="Escalón (kg)">
            <Texto value={borrador.regla_peso?.escalon_kg ?? '0.5'}
              onChange={(e) => cambiar('regla_peso', {
                ...(borrador.regla_peso || {}), escalon_kg: e.target.value,
              })} />
          </Campo>
          <Campo etiqueta="Mínimo facturable (kg)">
            <Texto value={borrador.regla_peso?.minimo_kg ?? '1.0'}
              onChange={(e) => cambiar('regla_peso', {
                ...(borrador.regla_peso || {}), minimo_kg: e.target.value,
              })} />
          </Campo>
          <Campo etiqueta="Tipo de margen"
            ayuda="Un margen fijo no es un porcentaje: son RIS por envío.">
            <Seleccion value={borrador.margen?.tipo || 'porcentual'}
              onChange={(e) => cambiar('margen', {
                ...(borrador.margen || {}), tipo: e.target.value,
              })}
              opciones={[{ valor: 'porcentual', texto: 'Porcentual (%)' },
                { valor: 'fijo', texto: `Fijo (${borrador.moneda || 'RIS'} por envío)` }]} />
          </Campo>
          <Campo
            etiqueta={borrador.margen?.tipo === 'fijo'
              ? `Margen (${borrador.moneda || 'RIS'})` : 'Margen (%)'}
            ayuda="Se aplica sobre el subtotal.">
            <Texto value={borrador.margen?.valor ?? '0'}
              onChange={(e) => cambiar('margen', {
                ...(borrador.margen || { tipo: 'porcentual' }), valor: e.target.value,
              })} />
          </Campo>
        </div>

        {advertencias.length ? (
          <Aviso tono="alerta" titulo="Esto va a bloquear la publicación" style={{ marginTop: '16px' }}>
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '18px' }}>
              {advertencias.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </Aviso>
        ) : null}

        <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
          <Boton onClick={guardarBorrador} cargando={guardando}>
            <Save size={14} /> Guardar borrador
          </Boton>
          <Boton variante="secundario" onClick={cargar}>Descartar cambios</Boton>
        </div>
        <p style={{ ...bajada, margin: '10px 0 0 0' }}>
          Guardar no publica nada y no cobra nada. La versión vigente sigue siendo la que está.
        </p>
      </div>

      <Simulador sucio={sucio} onPublicado={cargar} />
      <Historial filas={datos?.historial || []} />
    </div>
  );
}

function Vigente({ vigente, origen }) {
  if (!vigente) {
    return (
      <Aviso tono="alerta" titulo="No hay ninguna versión vigente">
        Hasta que publiques una, nadie puede cotizar.
      </Aviso>
    );
  }
  return (
    <div style={{ ...tarjeta, background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
      borderColor: '#c7d2fe' }}>
      <p style={{ fontSize: '12px', margin: 0, fontWeight: 700, letterSpacing: '0.04em',
        textTransform: 'uppercase', color: '#3730a3' }}>
        Versión vigente
      </p>
      <p style={{ fontSize: '20px', fontWeight: 800, margin: '4px 0 0 0', color: '#312e81',
        fontFamily: 'monospace' }}>
        {vigente.version_id}
      </p>
      <p style={{ fontSize: '13px', margin: '4px 0 0 0', color: '#4338ca', lineHeight: 1.5 }}>
        {vigente.nota || 'Sin nota.'}
        {origen === 'copia_de_vigente'
          ? ' · El borrador es una copia idéntica de esta versión: editá algo antes de publicar.'
          : ''}
      </p>
    </div>
  );
}

function Simulador({ sucio, onPublicado }) {
  const [cajas, setCajas] = useState(CAJAS_POR_DEFECTO);
  const [fecha, setFecha] = useState('');
  const [resultado, setResultado] = useState(null);
  const [simulando, setSimulando] = useState(false);
  const [nota, setNota] = useState('');
  const [desde, setDesde] = useState('');
  const [publicando, setPublicando] = useState(false);

  const simular = async () => {
    setSimulando(true);
    try {
      const res = await api.post('/admin/envios/tarifas/simular',
        { cajas, fecha: fecha || null });
      setResultado(res.data);
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo simular.'));
    } finally {
      setSimulando(false);
    }
  };

  const publicar = async () => {
    setPublicando(true);
    try {
      const res = await api.post('/admin/envios/tarifas/publicar', {
        nota, vigente_desde: desde ? new Date(desde).toISOString() : null,
      });
      toast.success(`Publicada ${res.data?.version_id}`);
      setNota('');
      setDesde('');
      setResultado(null);
      onPublicado();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo publicar.'));
    } finally {
      setPublicando(false);
    }
  };

  const bloqueos = resultado?.bloqueos || [];
  const comparacion = resultado?.comparacion || [];
  const simulado = !!resultado;

  return (
    <div style={tarjeta}>
      <h3 style={titulo}><FlaskConical size={16} /> Simulá antes de publicar</h3>
      <p style={bajada}>
        Cada caja se cotiza contra el borrador y contra la vigente, lado a lado, con la misma
        función que usa la cotización real. La fecha es opcional: sin ella los recargos de
        temporada valen 1, y un aumento de temporada del 50 % se vería como 0 %.
      </p>

      <div style={{ overflowX: 'auto', marginBottom: '12px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: COLOR.suave }}>
              {['Nombre', 'Peso (kg)', 'Largo', 'Ancho', 'Alto', 'Declarado', ''].map((h) => (
                <th key={h} style={{ padding: '8px 8px', fontWeight: 600,
                  borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cajas.map((c, i) => (
              <tr key={i}>
                {['nombre', 'peso_kg', 'largo_cm', 'ancho_cm', 'alto_cm', 'valor_declarado']
                  .map((k) => (
                    <td key={k} style={{ padding: '4px 8px' }}>
                      <Texto value={c[k] ?? ''} onChange={(e) => {
                        setResultado(null);   // otra caja, otra comparación
                        setCajas((cs) => {
                          const copia = [...cs];
                          copia[i] = { ...copia[i], [k]: e.target.value };
                          return copia;
                        });
                      }} />
                    </td>
                  ))}
                <td style={{ padding: '4px 8px' }}>
                  <button type="button" aria-label="Quitar caja"
                    onClick={() => setCajas((cs) => cs.filter((_, j) => j !== i))}
                    style={{ border: 'none', background: 'none', cursor: 'pointer',
                      color: COLOR.error, display: 'inline-flex', padding: '6px' }}>
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <Boton variante="secundario"
          onClick={() => setCajas((cs) => [...cs, { nombre: '', peso_kg: '1.0', largo_cm: '20',
            ancho_cm: '15', alto_cm: '10', valor_declarado: '0', bultos: 1 }])}>
          <Plus size={14} /> Otra caja
        </Boton>
        <div style={{ minWidth: '180px' }}>
          <Campo etiqueta="Simular una fecha" ayuda="Para ver una temporada sin esperarla.">
            <Texto type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </Campo>
        </div>
        <Boton onClick={simular} cargando={simulando} disabled={sucio}>
          <FlaskConical size={14} /> Simular
        </Boton>
      </div>

      {sucio ? (
        <Aviso tono="alerta" titulo="Guardá el borrador primero" style={{ marginTop: '14px' }}>
          La simulación y la publicación corren contra el borrador <strong>guardado</strong>,
          no contra lo que está en pantalla. Con cambios sin guardar, simularías una tabla y
          publicarías otra — y la que se cobra es la otra.
        </Aviso>
      ) : null}

      {resultado ? (
        <div style={{ marginTop: '18px' }}>
          <p style={{ ...bajada, margin: '0 0 10px 0' }}>
            Fecha simulada: <strong>{resultado.fecha_simulada}</strong>
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: COLOR.suave }}>
                  {['Caja', 'Peso facturable', 'Vigente', 'Borrador', 'Variación'].map((h) => (
                    <th key={h} style={{ padding: '8px 10px', fontWeight: 600,
                      borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparacion.map((f, i) => {
                  const v = f.variacion_pct === null ? null : Number(f.variacion_pct);
                  const fuerte = v !== null && Math.abs(v) >= 20;
                  return (
                    <tr key={i} style={{ borderBottom: `1px solid ${COLOR.borde}` }}>
                      <td style={{ padding: '8px 10px', fontWeight: 600 }}>
                        {f.caja?.nombre || `${f.caja?.peso_kg} kg`}
                      </td>
                      <td style={{ padding: '8px 10px' }}>
                        {num(f.nuevo?.peso_facturable_kg)} kg
                      </td>
                      <td style={{ padding: '8px 10px' }}>{num(f.actual?.total)}</td>
                      <td style={{ padding: '8px 10px', fontWeight: 700 }}>
                        {f.nuevo?.error ? (
                          <span style={{ color: COLOR.error }}>{f.nuevo.error}</span>
                        ) : num(f.nuevo?.total)}
                      </td>
                      <td style={{ padding: '8px 10px', fontWeight: 700,
                        color: v === null ? COLOR.suave : fuerte ? COLOR.error
                          : v > 0 ? COLOR.alerta : COLOR.ok }}>
                        {v === null ? '—' : `${v > 0 ? '+' : ''}${f.variacion_pct} %`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {comparacion.some((f) => f.variacion_pct !== null
            && Math.abs(Number(f.variacion_pct)) >= 20) ? (
              <Aviso tono="alerta" titulo="Hay variaciones de 20 % o más"
                style={{ marginTop: '12px' }}>
                Mirá que sea lo que querías. Es exactamente el caso que esta pantalla existe para
                atrapar.
              </Aviso>
            ) : null}
        </div>
      ) : null}

      <div style={{ marginTop: '24px', paddingTop: '18px', borderTop: `1px solid ${COLOR.borde}` }}>
        <h4 style={titulo}><Rocket size={16} /> Publicar</h4>
        <p style={bajada}>
          Crea una versión nueva; <strong>nunca edita una existente</strong>. Los envíos que ya
          se cotizaron mantienen la suya.
        </p>
        {bloqueos.length ? (
          <Aviso tono="error" titulo="No se puede publicar así" style={{ marginBottom: '14px' }}>
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '18px' }}>
              {bloqueos.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          </Aviso>
        ) : null}
        <div style={grilla('240px')}>
          <Campo etiqueta="Qué cambió y por qué"
            ayuda="Obligatorio. Alguien lo va a leer en seis meses para entender por qué un envío de marzo costó lo que costó.">
            <Texto value={nota} onChange={(e) => setNota(e.target.value)} maxLength={500} />
          </Campo>
          <Campo etiqueta="Vigente desde"
            ayuda="Vacío = ahora. Con fecha futura queda programada, y la actual sigue cobrando hasta ese día.">
            <Texto type="datetime-local" value={desde} onChange={(e) => setDesde(e.target.value)} />
          </Campo>
        </div>
        {!simulado ? (
          <Aviso tono="info" titulo="Simulá primero" style={{ marginTop: '14px' }}>
 Publicar sin haber mirado la comparación es cómo se publica un aumento del
            40 % creyendo que era del 4 %.
          </Aviso>
        ) : null}
        <Boton style={{ marginTop: '16px' }} cargando={publicando}
          disabled={!nota.trim() || bloqueos.length > 0 || !simulado || sucio}
          onClick={publicar}>
          <Rocket size={14} /> Publicar esta versión
        </Boton>
      </div>
    </div>
  );
}

function Historial({ filas }) {
  return (
    <div style={tarjeta}>
      <h3 style={titulo}><History size={16} /> Historial</h3>
      <p style={bajada}>
        Todas las versiones, de la más nueva a la más vieja. Ninguna se edita: se reemplazan.
      </p>
      {filas.length === 0 ? (
        <Vacio titulo="Sin versiones publicadas">Todavía no se publicó ninguna tarifa.</Vacio>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {filas.map((f) => (
            <div key={f.version_id} style={{ padding: '12px 14px', borderRadius: '12px',
              border: `1px solid ${COLOR.borde}`, backgroundColor: f.anulada ? '#f9fafb' : '#fff',
              opacity: f.anulada ? 0.6 : 1 }}>
              <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, fontFamily: 'monospace',
                color: COLOR.texto, display: 'flex', alignItems: 'center', gap: '8px',
                flexWrap: 'wrap' }}>
                {f.version_id}
                {f.anulada ? (
                  <span style={{ fontFamily: 'inherit', fontSize: '11px', padding: '2px 8px',
                    borderRadius: '999px', backgroundColor: '#f3f4f6', color: COLOR.suave }}>
                    anulada — nunca rigió
                  </span>
                ) : null}
              </p>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: COLOR.texto,
                lineHeight: 1.5 }}>
                {f.nota || 'Sin nota.'}
              </p>
              <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: COLOR.suave,
                display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CalendarClock size={12} />
                {local(f.vigente_desde)}
                {f.vigente_hasta ? ` → ${local(f.vigente_hasta)}` : ' → sin reemplazo'}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
