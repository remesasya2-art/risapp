/**
 * Historial.jsx — Los envíos, para buscar. No para operar.
 *
 * LA COLA Y ESTA PANTALLA CONTESTAN PREGUNTAS DISTINTAS
 *   La cola muestra UN estado y sirve para mover paquetes: qué hay por pesar,
 *   qué hay por despachar. Esta contesta la que llega por teléfono: «¿qué pasó
 *   con mi envío?». Por eso acá se busca por identificador y se ve todo, incluso
 *   lo terminado, que es justamente lo que la cola no muestra.
 *
 * Y EL PASO QUE FALTABA: EL RETIRO EN LA OFICINA
 *   Nuestro servicio termina cuando dejamos la caja en la oficina del
 *   transportista. Para el usuario no: para él termina cuando su familiar la
 *   tiene en la mano, y eso pasa días después en un mostrador al que no tenemos
 *   acceso. El equipo sí lo averigua —entra a la web del transportista y ve la
 *   guía retirada, y por quién— y hasta ahora ese dato se quedaba en la cabeza
 *   de quien lo miró. Acá se registra, y al usuario le llega el aviso.
 *
 *   NO mueve el envío de estado. Es una observación de tercero, no algo que
 *   hicimos nosotros. Ver el encabezado de `services/envios_entrega_final.py`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { PackageSearch, Search, UserCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import {
  Aviso, Boton, Campo, Cargando, NoSePudoLeer, Texto, Vacio,
} from '../../envios/ui';
import { COLOR, bajada, grilla, mensajeDeError, tarjeta, titulo } from '../../envios/estilos';
import { TITULOS, tonoDe } from '../../envios/estados';

/** Los estados por los que se filtra. `''` es «todos». */
const FILTROS = [
  { valor: '', etiqueta: 'Todos' },
  { valor: 'entregado_transportista', etiqueta: 'Entregados' },
  { valor: 'en_transito_int', etiqueta: 'En camino a Santa Elena' },
  { valor: 'pago_pendiente', etiqueta: 'Esperando pago' },
  { valor: 'retenido', etiqueta: 'Retenidos' },
  { valor: 'devuelto', etiqueta: 'Devueltos' },
];

const fecha = (v) => (v ? new Date(v).toLocaleDateString('es', {
  day: '2-digit', month: '2-digit', year: 'numeric' }) : '—');

export default function Historial() {
  const [estado, setEstado] = useState('');
  const [texto, setTexto] = useState('');
  const [buscado, setBuscado] = useState('');
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

  // `vivo` corta las respuestas que llegan despues de que la pantalla se fue, o
  // despues de que se cambio el filtro: sin esto la respuesta vieja pisa la
  // nueva y la lista muestra el filtro anterior. Mismo patron que Almacen.jsx.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const { data } = await api.get('/admin/envios/envios/historial', {
        params: { estado: estado || undefined, buscar: buscado || undefined },
      });
      if (!vivo.current) return;
      setDatos(data);
    } catch (err) {
      if (vivo.current) setError(mensajeDeError(err, 'No se pudo leer el historial.'));
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, [estado, buscado]);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const envios = datos?.envios || [];
  // Las que el equipo tiene que ir a buscar a la web del transportista.
  const esperando = envios.filter((e) => e.espera_retiro).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={titulo}><PackageSearch size={16} /> Historial de envíos</h3>
        <p style={bajada}>
          Todos los envíos, del más nuevo al más viejo — también los terminados, que
          la cola no muestra. Acá se busca cuando alguien pregunta por el suyo, y se
          registra <strong>quién retiró el paquete</strong> en la oficina del
          transportista.
        </p>

        <form onSubmit={(e) => { e.preventDefault(); setBuscado(texto.trim()); }}>
          <div style={grilla('260px')}>
            <Campo etiqueta="Buscar"
              ayuda="Por número de envío (E000123) o código de objeto (AA123456789BR). Podés pegarlo con espacios o guiones.">
              <Texto value={texto} onChange={(e) => setTexto(e.target.value)}
                placeholder="E000123" data-testid="historial-buscar" />
            </Campo>
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '12px', flexWrap: 'wrap' }}>
            <Boton type="submit"><Search size={14} /> Buscar</Boton>
            {buscado ? (
              <Boton variante="secundario" type="button"
                onClick={() => { setTexto(''); setBuscado(''); }}>
                Ver todos
              </Boton>
            ) : null}
          </div>
        </form>

        {/* El filtro por estado no aplica mientras hay una busqueda: se busca UN
            envio por su identificador, y acotarlo por estado solo consigue que
            no aparezca el que se estaba buscando. */}
        {!buscado ? (
          <div style={{ display: 'flex', gap: '8px', marginTop: '14px', flexWrap: 'wrap' }}>
            {FILTROS.map((f) => (
              <button key={f.valor} type="button" onClick={() => setEstado(f.valor)}
                style={{ padding: '6px 12px', borderRadius: '999px', fontSize: '13px',
                  fontWeight: 600, cursor: 'pointer',
                  border: `1px solid ${estado === f.valor ? COLOR.primario : COLOR.borde}`,
                  backgroundColor: estado === f.valor ? COLOR.primarioSuave : '#fff',
                  color: estado === f.valor ? COLOR.primarioOscuro : COLOR.suave }}>
                {f.etiqueta}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {esperando > 0 ? (
        <Aviso tono="alerta" titulo={`${esperando} esperando el retiro`}>
          Estos ya los entregamos en la oficina del transportista y todavía nadie
          registró quién los retiró. <strong>Es lo que hay que ir a mirar en la web
          del transportista</strong>, y es la última cosa que el usuario espera saber
          de su envío.
        </Aviso>
      ) : null}

      {error ? (
        <NoSePudoLeer que="el historial" detalle={error} onReintentar={cargar}
          reintentando={cargando} />
      ) : cargando ? (
        <Cargando texto="Buscando…" />
      ) : envios.length === 0 ? (
        <Vacio titulo={buscado ? 'No encontramos ese envío' : 'Todavía no hay envíos'}>
          {buscado
            ? 'Se busca por número de envío o código de objeto, no por nombre. '
              + 'Revisá que el identificador esté completo.'
            : 'Cuando alguien cotice y confirme, va a aparecer acá.'}
        </Vacio>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {envios.map((e) => <Envio key={e.envio_id} envio={e} onListo={cargar} />)}
          {datos?.hay_mas ? (
            <p style={{ ...bajada, margin: 0, textAlign: 'center' }}>
              Hay más envíos de los que caben acá. Afiná la búsqueda o el filtro.
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Envio({ envio, onListo }) {
  const [abierto, setAbierto] = useState(false);
  const tono = tonoDe(envio.estado);
  return (
    <div style={{ ...tarjeta, padding: '14px 16px',
      borderColor: envio.espera_retiro ? '#fde68a' : COLOR.borde }}>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start',
        flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: '220px' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'monospace', fontSize: '14px', fontWeight: 700 }}>
              {envio.display_id}
            </span>
            <span style={{ fontSize: '11px', fontWeight: 700, padding: '3px 9px',
              borderRadius: '999px', backgroundColor: tono.fondo, color: tono.texto,
              border: `1px solid ${tono.borde}` }}>
              {TITULOS[envio.estado] || envio.estado}
            </span>
          </div>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: COLOR.suave }}>
            Para {envio.destinatario || '—'} · {envio.agencia || 'sin agencia'}
            {envio.ciudad ? `, ${envio.ciudad}` : ''}
          </p>
          <p style={{ margin: '2px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
            {fecha(envio.created_at)}
            {envio.codigo_objeto ? ` · ${envio.codigo_objeto}` : ''}
            {envio.guia ? ` · guía ${envio.guia}` : ''}
          </p>

          {envio.retirado_por ? (
            <p style={{ margin: '8px 0 0 0', fontSize: '13px', fontWeight: 600,
              color: '#166534' }}>
              <UserCheck size={13} style={{ display: 'inline', verticalAlign: '-2px' }} />
              {' '}Retirado por {envio.retirado_por} · {fecha(envio.retirado_at)}
            </p>
          ) : envio.espera_retiro ? (
            <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#92400e' }}>
              Todavía nadie registró quién lo retiró.
            </p>
          ) : null}
        </div>

        {envio.espera_retiro || envio.retirado_por ? (
          <Boton variante="secundario" onClick={() => setAbierto((v) => !v)}
            data-testid={`retiro-${envio.envio_id}`}>
            <UserCheck size={14} /> {envio.retirado_por ? 'Corregir' : 'Registrar retiro'}
          </Boton>
        ) : null}
      </div>

      {abierto ? (
        <Retiro envio={envio} onListo={() => { setAbierto(false); onListo(); }} />
      ) : null}
    </div>
  );
}

/**
 * El formulario del retiro en la oficina.
 *
 * El nombre lo tipea una persona leyendo la web de otra empresa. Se va a
 * equivocar, así que registrar de nuevo pisa el dato y deja OTRA línea en la
 * bitácora: la corrección es visible, no silenciosa. Y el usuario recibe un
 * aviso que dice que fue una corrección, en vez de repetirle el original.
 */
function Retiro({ envio, onListo }) {
  const [nombre, setNombre] = useState(envio.retirado_por || '');
  const [cuando, setCuando] = useState('');
  const [documento, setDocumento] = useState('');
  const [fuente, setFuente] = useState('Web del transportista');
  const [nota, setNota] = useState('');
  const [enviando, setEnviando] = useState(false);

  // La fecha LOCAL. Con `toISOString` alguien registrando a las 22:00 ve como
  // maximo el dia siguiente.
  const ahora = new Date();
  const hoy = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10);

  const corto = nombre.trim().length < 3;

  const guardar = async () => {
    setEnviando(true);
    try {
      await api.post(`/admin/envios/envios/${envio.envio_id}/retiro-final`, {
        retirado_por: nombre.trim(),
        retirado_at: cuando || hoy,
        documento: documento.trim(),
        fuente: fuente.trim(),
        nota: nota.trim(),
      });
      toast.success(envio.retirado_por ? 'Corregido, y le avisamos' : 'Registrado, y le avisamos');
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo registrar el retiro.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ marginTop: '14px', paddingTop: '14px',
      borderTop: `1px solid ${COLOR.borde}` }}>
      <p style={{ ...bajada, marginBottom: '12px' }}>
        Esto <strong>no cambia el estado del envío</strong> — nuestro servicio ya
        terminó. Es lo que viste en la web del transportista, y el usuario lo va a
        recibir como aviso, así que el nombre tiene que ser el que figura ahí.
      </p>
      <div style={grilla('220px')}>
        <Campo etiqueta="Retirado por"
          ayuda="Tal como figura en la web del transportista."
          error={nombre.trim() && corto ? 'Muy corto.' : null}>
          <Texto value={nombre} onChange={(e) => setNombre(e.target.value)}
            invalido={corto} data-testid="retiro-nombre" />
        </Campo>
        <Campo etiqueta="Cuándo lo retiró" ayuda="Si lo dejás vacío, se guarda hoy.">
          <Texto type="date" value={cuando} max={hoy}
            onChange={(e) => setCuando(e.target.value)} />
        </Campo>
        <Campo etiqueta="Documento (opcional)">
          <Texto value={documento} onChange={(e) => setDocumento(e.target.value)} />
        </Campo>
        {/* De donde salio el dato. Dentro de seis meses, «lo vi en la web» y «me
            lo dijo el destinatario por telefono» no valen lo mismo. */}
        <Campo etiqueta="De dónde sacaste el dato"
          ayuda="Dentro de seis meses, «lo vi en la web» y «me lo dijeron por teléfono» no valen lo mismo.">
          <Texto value={fuente} onChange={(e) => setFuente(e.target.value)} />
        </Campo>
      </div>
      <div style={{ marginTop: '12px' }}>
        <Campo etiqueta="Nota (opcional)">
          <Texto value={nota} onChange={(e) => setNota(e.target.value)} />
        </Campo>
      </div>
      <div style={{ marginTop: '14px' }}>
        <Boton onClick={guardar} cargando={enviando} disabled={corto}
          data-testid="retiro-guardar">
          <UserCheck size={14} /> {envio.retirado_por ? 'Corregir y avisar' : 'Registrar y avisar'}
        </Boton>
      </div>
    </div>
  );
}
