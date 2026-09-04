/**
 * EnvioDetalle.jsx — Un envío: dónde está, qué falta, y qué se cobró.
 *
 * TRES COSAS QUE SE RESUELVEN ACA
 *   1. **La etiqueta congelada.** Es la que el usuario tiene que copiar sobre la
 *      caja, y tiene que decir lo mismo que decía cuando la leyó al confirmar —
 *      aunque después haya cambiado quién está de turno. El backend la guarda
 *      congelada en el envío justamente por eso.
 *   2. **Cargar el comprobante.** Sin API de rastreo, es la única forma de que
 *      el sistema se entere de que el paquete se despachó. No cobra nada: el
 *      cobro lo emite el operador cuando verifica la foto.
 *   3. **Pagar una partida pendiente.** Que quede impaga no es un error, es un
 *      estado del negocio — pero mientras esté impaga el paquete no sale de
 *      Pacaraima, y eso se dice con todas las letras.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Camera, CheckCircle2, CreditCard, Link2, PackageSearch, RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt } from '../utils/format';
import Chrome from '../components/envios/Chrome';
import Etiqueta from '../components/envios/Etiqueta';
import {
  Area, Aviso, Boton, Campo, Cargando, Interruptor, Texto, Vacio,
} from '../components/envios/ui';
import {
  COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo,
} from '../components/envios/estilos';
import { PIDE_ALGO, TITULOS, tonoDe } from '../components/envios/estados';
import { useAuth } from '../contexts/AuthContext';

const num = (v) => (v === null || v === undefined || v === '' ? '—' : fmt(v, 2));
/** Los estados en los que todavía hay una caja que rotular. */
// Solo `esperando_postagem`: en `cotizado` el envío TODAVIA NO ESTA CONFIRMADO
// y a las 48 h se borra solo por TTL. Mostrar ahí «copiá esto sobre la caja» es
// invitar a despachar contra un envío que va a dejar de existir — y la caja
// llega a Pacaraima con una etiqueta válida y nada que la reclame.
const ANTES_DE_DESPACHAR = ['esperando_postagem'];

/** En estos el backend no cobra nada: `_cobrable` devuelve 409. */
const TERMINALES = ['entregado_transportista', 'cancelado', 'devuelto', 'siniestrado'];

const fecha = (v) => (v ? new Date(v).toLocaleString('es-AR',
  { dateStyle: 'short', timeStyle: 'short' }) : '—');

export default function EnvioDetalle() {
  const { envioId } = useParams();
  const [envio, setEnvio] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    try {
      const res = await api.get(`/envios/${envioId}`);
      if (mia !== peticion.current) return;
      setNoSeLeyo(null);
      setEnvio(res.data);
    } catch (err) {
      if (mia !== peticion.current) return;
      setNoSeLeyo(mensajeDeError(err, esFallaDeLectura(err)
        ? 'No pudimos leer el envío. Probá de nuevo en un minuto.'
        : 'No encontramos ese envío.'));
    } finally {
      if (mia === peticion.current) setCargando(false);
    }
  }, [envioId]);

  useEffect(() => {
    (async () => { await cargar(); })();
    return () => { peticion.current += 1; };
  }, [cargar]);

  const refrescar = () => { setCargando(true); cargar(); };

  if (cargando && !envio) {
    return <Chrome titulo="Tu envío" volverA="/envios"><Cargando /></Chrome>;
  }
  if (!envio) {
    return (
      <Chrome titulo="Tu envío" volverA="/envios">
        <Vacio titulo="No pudimos abrir este envío">{noSeLeyo}</Vacio>
      </Chrome>
    );
  }

  const tono = tonoDe(envio.estado);
  const pide = PIDE_ALGO[envio.estado];
  // La partida `devolucion` llega con `estado: "acreditado"` — es plata que RIS
  // App le DEBE al usuario, de la rama «devolver» del repesaje. Filtrando por
  // `!== 'pagado'` entraba en la lista de deudas: se sumaba al total a pagar, se
  // le decía «mientras quede impago el paquete no sale de Pacaraima», y se le
  // ofrecía un botón que el backend rechaza con 404 —justamente porque ya blindó
  // ese agujero—. Y la lista, que usa `hay_algo_que_pagar` del servidor, decía lo
  // contrario en la misma pantalla de al lado.
  //
  // Y en un estado terminal no se cobra nada: `_cobrable` devuelve 409.
  const terminal = TERMINALES.includes(envio.estado);
  const impagas = terminal ? [] : (envio.cobros || []).filter(
    (c) => c.partida !== 'devolucion' && c.estado === 'pendiente' && c.monto_ris);
  const acreditadas = (envio.cobros || []).filter((c) => c.partida === 'devolucion');

  return (
    <Chrome titulo={envio.display_id || 'Tu envío'} volverA="/envios">
      <div style={{ ...tarjeta, backgroundColor: tono.fondo, borderColor: tono.borde }}>
        <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, letterSpacing: '0.04em',
          textTransform: 'uppercase', color: tono.texto, opacity: 0.8 }}>
          Estado
        </p>
        <p style={{ margin: '4px 0 0 0', fontSize: '22px', fontWeight: 800, color: tono.texto }}>
          {TITULOS[envio.estado] || envio.estado}
        </p>
        {pide ? (
          <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: tono.texto,
            lineHeight: 1.5 }}>{pide}</p>
        ) : null}
        <Boton variante="secundario" style={{ marginTop: '12px' }} onClick={refrescar}
          cargando={cargando}>
          <RefreshCw size={14} /> Actualizar
        </Boton>
      </div>

      {impagas.length ? <Pagar envio={envio} partidas={impagas} onListo={refrescar} /> : null}

      {acreditadas.map((c) => (
        <Aviso key={c.partida} tono="ok" titulo="Te devolvimos plata">
          El paquete pesó menos de lo que declaraste, así que te acreditamos{' '}
          <strong>{num(c.monto_ris)} {envio.moneda}</strong> a tu saldo
          {c.pagado_at ? ` el ${fecha(c.pagado_at)}` : ''} — no hay nada que hacer.
        </Aviso>
      ))}

      {terminal && (envio.cobros || []).some((c) => c.estado === 'pendiente') ? (
        <Aviso tono="alerta" titulo="Quedó un cobro sin saldar">
          Este envío ya está cerrado, así que no se puede pagar desde acá. Escribinos con el
          número del envío y lo resolvemos.
        </Aviso>
      ) : null}

      {envio.estado === 'cotizado' ? (
        <Confirmar envio={envio} onListo={refrescar} />
      ) : null}

      {envio.estado === 'esperando_postagem' ? (
        <Comprobante envio={envio} onListo={refrescar} />
      ) : null}

      {/*
        La etiqueta solo mientras el paquete NO se despachó. Después sigue siendo
        cierta —está congelada— pero ya no hay ninguna caja que rotular, y
        mostrarla arriba de todo en un envío que está esperando un pago le da al
        usuario una instrucción que no le corresponde hacer.
      */}
      {ANTES_DE_DESPACHAR.includes(envio.estado) && envio.retiro?.texto_copiable
        ? <Etiqueta retiro={envio.retiro} /> : null}

      <div style={tarjeta}>
        <h3 style={titulo}><PackageSearch size={16} /> El paquete</h3>
        <Dato etiqueta={envio.es_estimado ? 'Precio estimado' : 'Precio final'}
          valor={`${num(envio.total_ris)} ${envio.moneda}`} />
        <Dato etiqueta="Contenido" valor={envio.paquete?.contenido} />
        <Dato etiqueta="Declaraste"
          valor={envio.paquete?.declarado
            ? `${num(envio.paquete.declarado.peso_kg)} kg · ${envio.paquete.declarado.largo_cm}×${envio.paquete.declarado.ancho_cm}×${envio.paquete.declarado.alto_cm} cm`
            : '—'} />
        {envio.paquete?.verificado ? (
          <Dato etiqueta="Pesamos en Pacaraima"
            valor={`${num(envio.paquete.verificado.peso_kg)} kg · ${envio.paquete.verificado.largo_cm}×${envio.paquete.verificado.ancho_cm}×${envio.paquete.verificado.alto_cm} cm`} />
        ) : null}
        <Dato etiqueta="Va a" valor={`${envio.destino?.destinatario || '—'} — ${envio.destino?.agencia || '—'}, ${envio.destino?.ciudad || '—'}`} />
        {envio.guia_transportista ? (
          <Dato etiqueta="Guía del transportista" valor={envio.guia_transportista} />
        ) : null}
        {/*
          Lo que cargó, para que pueda verificar que no se equivocó de
          comprobante. El formulario desaparece apenas se carga, y sin esto no
          quedaba ni rastro del código que mandó.
        */}
        {envio.comprobante ? (
          <>
            <Dato etiqueta="Código de objeto" valor={envio.comprobante.codigo_objeto} />
            <Dato etiqueta="Despachado el"
              valor={envio.comprobante.posteado_at
                ? new Date(envio.comprobante.posteado_at).toLocaleDateString('es-AR')
                : '—'} />
            <Dato etiqueta="Comprobante"
              valor={envio.comprobante.verificado_at
                ? `Verificado el ${fecha(envio.comprobante.verificado_at)}`
                : 'Cargado, todavía sin verificar'} />
          </>
        ) : null}
      </div>

      <Cobros envio={envio} />

      {envio.timeline?.length ? (
        <div style={tarjeta}>
          <h3 style={titulo}>Por dónde pasó</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {envio.timeline.map((t, i) => (
              <div key={i} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start',
                padding: '8px 0' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%',
                  backgroundColor: i === envio.timeline.length - 1 ? COLOR.primario : COLOR.borde,
                  marginTop: '5px', flexShrink: 0 }} />
                <div>
                  <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: COLOR.texto }}>
                    {t.titulo || TITULOS[t.estado] || t.estado}
                  </p>
                  <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave }}>{fecha(t.at)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {envio.tracking_token ? (
        <div style={tarjeta}>
          <h3 style={titulo}><Link2 size={16} /> Compartir el seguimiento</h3>
          <p style={bajada}>
            Este link muestra en qué estado está el paquete y nada más:{' '}
            <strong>ningún dato personal</strong>, ni el tuyo ni el de quien recibe. Podés
            mandárselo a quien espera la caja.
          </p>
          <Boton variante="secundario" onClick={async () => {
            const url = `${window.location.origin}/seguimiento/${envio.tracking_token}`;
            try {
              await navigator.clipboard.writeText(url);
              toast.success('Link copiado');
            } catch {
              toast.error('El navegador no dejó copiar.');
            }
          }}>
            <Link2 size={14} /> Copiar el link
          </Boton>
        </div>
      ) : null}
    </Chrome>
  );
}

function Dato({ etiqueta, valor }) {
  return (
    <div style={{ display: 'flex', gap: '12px', padding: '8px 0',
      borderBottom: `1px solid ${COLOR.borde}` }}>
      <span style={{ fontSize: '13px', color: COLOR.suave, flex: '0 0 42%' }}>{etiqueta}</span>
      <span style={{ fontSize: '13px', color: COLOR.texto, fontWeight: 600, flex: 1 }}>
        {valor || '—'}
      </span>
    </div>
  );
}

function Cobros({ envio }) {
  const cobros = envio.cobros || [];
  return (
    <div style={tarjeta}>
      <h3 style={titulo}>Lo que cobra RIS App</h3>
      <p style={bajada}>
        Solo el servicio: retiro en Pacaraima, repesaje y traslado hasta la oficina del
        transportista en Santa Elena. <strong>Los tramos de transporte no están acá</strong>:
        esos los contratás y los pagás vos.
      </p>
      {cobros.length === 0 ? (
        <p style={{ ...bajada, margin: 0 }}>
          Todavía no se emitió ningún cobro. El primero sale cuando verifiquemos tu
          comprobante en Pacaraima.
        </p>
      ) : (
        cobros.map((c) => (
          <div key={c.partida} style={{ display: 'flex', gap: '12px', alignItems: 'center',
            padding: '10px 0', borderBottom: `1px solid ${COLOR.borde}` }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: COLOR.texto }}>
                {c.concepto || c.partida}
              </p>
              <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave }}>
                {c.partida === 'devolucion'
                  ? `Acreditado a tu saldo ${fecha(c.pagado_at)}`
                  : c.estado === 'pagado' ? `Pagado ${fecha(c.pagado_at)}` : 'Pendiente'}
              </p>
            </div>
            <span style={{ fontSize: '15px', fontWeight: 700,
              color: c.partida === 'devolucion' || c.estado === 'pagado'
                ? COLOR.ok : COLOR.alerta }}>
              {c.partida === 'devolucion' ? '+' : ''}{num(c.monto_ris)} {envio.moneda}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

/**
 * Confirmar una cotización que quedó a medias.
 *
 * EL AGUJERO QUE TAPA
 *
 *   Cotizar y confirmar vivían los dos en `EnvioNuevo`, en la misma pantalla.
 *   Si el usuario cotizaba y se iba —cerraba la pestaña, lo llamaron, se quedó
 *   sin señal—, el envío quedaba guardado en `cotizado` y VIGENTE por 48 horas,
 *   pero esta pantalla no ofrecía ninguna forma de confirmarlo: sólo «Cotizar
 *   de nuevo», que es empezar de cero y volver a tipear todo.
 *
 *   Y el botón «Actualizar» de arriba no arreglaba nada, porque no había nada
 *   que actualizar: el envío seguía igual. Desde afuera se leía como que la
 *   pantalla estaba rota.
 *
 * POR QUE LAS DOS ACEPTACIONES ESTAN ACA TAMBIEN
 *
 *   No se heredan de la pantalla anterior. `envios_crear` las exige en cada
 *   confirmación y con razón: son el registro que se lee el día que haya que
 *   defender un ajuste de precio. Reusarlas de una sesión que terminó hace dos
 *   días sería anotar una aceptación que nadie dio en este momento.
 *
 *   Van sin tildar, separadas, y con el mismo texto que en `EnvioNuevo`: si las
 *   dos pantallas dijeran cosas distintas, «aceptaste esto» dejaría de
 *   sostenerse.
 *
 * LA VERSION DE LOS TERMINOS
 *
 *   Se manda la que trae el envío, que es la que se congeló al cotizar y la
 *   que este bloque le está mostrando. Si el backend la ve distinta de la
 *   congelada, frena — y eso está bien: significaría que las condiciones
 *   cambiaron mientras el usuario no estaba.
 */
function Confirmar({ envio, onListo }) {
  const [contenido, setContenido] = useState(false);
  const [estimado, setEstimado] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [error, setError] = useState(null);

  // Una sola clave por cotización, generada en un efecto y no en el render:
  // `Date.now` y `Math.random` no son puras, y un render repetido no puede
  // cambiar la clave con la que ya se mandó una petición. Mismo criterio que
  // en EnvioNuevo.
  const clave = useRef(null);
  useEffect(() => {
    if (!clave.current) {
      clave.current = (globalThis.crypto?.randomUUID?.()
        || `c_${Date.now()}_${Math.random().toString(36).slice(2)}`);
    }
  }, []);

  // Se recalcula en cada render, así que basta con volver a pintar —lo que hace
  // «Actualizar»— para que una cotización que venció mientras la pantalla
  // estaba abierta deje de ofrecer el botón.
  const vencida = !envio.vence_at || new Date(envio.vence_at) <= new Date();

  const confirmar = async () => {
    setConfirmando(true);
    setError(null);
    try {
      await api.post('/envios/crear', {
        envio_id: envio.envio_id,
        declaracion: {
          // Los valores reales, no dos literales: una aceptación es un hecho,
          // no una interpretación.
          contenido_aceptado: contenido,
          estimado_aceptado: estimado,
          terminos_version: envio.terminos_version,
        },
        idempotency_key: clave.current || undefined,
      });
      toast.success('Envío confirmado');
      // Recargar y no navegar: la pantalla es la misma, y al volver ya está en
      // `esperando_postagem`, con la etiqueta para rotular la caja.
      onListo();
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo confirmar.'));
    } finally {
      setConfirmando(false);
    }
  };

  if (vencida) {
    return (
      <Aviso tono="alerta" titulo="Esta cotización venció">
        <strong>No despaches nada.</strong> Los precios y los límites pueden haber
        cambiado desde que la pediste, así que hay que cotizar otra vez. Si la caja
        ya salió, avisanos por el centro de ayuda antes de que llegue.
        <div style={{ marginTop: '10px' }}>
          <Link to="/envios/nuevo" style={{ textDecoration: 'none' }}>
            <Boton>Cotizar de nuevo</Boton>
          </Link>
        </div>
      </Aviso>
    );
  }

  return (
    <div style={{ ...tarjeta, borderColor: '#f5d787', backgroundColor: '#fffdf5' }}>
      <h3 style={titulo}><CheckCircle2 size={16} /> Falta confirmar este envío</h3>
      <p style={bajada}>
        <strong>No despaches nada hasta confirmarlo.</strong> Una cotización sin
        confirmar se borra sola el {fecha(envio.vence_at)}, y si la caja ya salió no
        va a haber ningún envío que la reclame.
      </p>

      <div style={{
        display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap',
        margin: '4px 0 16px', paddingBottom: '14px', borderBottom: '1px solid #f1e9cf',
      }}
      >
        <span style={{ fontSize: '13px', color: COLOR.suave }}>Precio estimado</span>
        <strong style={{ fontSize: '24px', color: COLOR.texto, letterSpacing: '-0.02em' }}>
          {num(envio.total_ris)} {envio.moneda}
        </strong>
      </div>

      <p style={bajada}>
        Confirmar <strong>no cobra nada</strong>. El primer cobro se emite cuando
        nuestro operador verifique tu comprobante en Pacaraima, con el peso que midió
        el transportista al despachar.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '14px' }}>
        <Interruptor activo={contenido} onChange={setContenido}
          etiqueta="Lo que mando no está en la lista de prohibidos"
          ayuda="Una caja con contenido prohibido queda retenida en la frontera, y el costo es tuyo." />
        <Interruptor activo={estimado} onChange={setEstimado}
          etiqueta="Entiendo que el precio es un estimado y se cierra al pesar en Pacaraima"
          ayuda="Si el peso real es mayor que el declarado, se cobra la diferencia; si es menor, se devuelve." />
      </div>

      {error ? <Aviso tono="error" style={{ marginTop: '14px' }}>{error}</Aviso> : null}

      <div style={{ display: 'flex', gap: '10px', marginTop: '18px', flexWrap: 'wrap' }}>
        <Boton onClick={confirmar} cargando={confirmando}
          disabled={!contenido || !estimado}
          style={{ flex: 1, justifyContent: 'center', padding: '14px' }}>
          Confirmar el envío
        </Boton>
        <Link to="/envios/nuevo" style={{ textDecoration: 'none' }}>
          <Boton variante="secundario">Cotizar de nuevo</Boton>
        </Link>
      </div>
    </div>
  );
}


function Pagar({ envio, partidas, onListo }) {
  const [pagando, setPagando] = useState(null);
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const total = partidas.reduce((s, p) => s + Number(p.monto_ris || 0), 0);

  // EL SALDO, ANTES DE APRETAR. Hasta ahora el usuario apretaba «pagar con mi
  // saldo», el servidor contestaba que no alcanzaba, y salía un toast que se iba
  // solo a los tres segundos sin dejar a dónde ir. Saber cuánto tiene y cuánto
  // falta es lo que convierte «no se pudo» en «me faltan 40».
  const saldo = Number(user?.balance_ris || 0);
  const alcanza = saldo >= total;
  const falta = Math.max(0, total - saldo);

  const pagar = async (partida) => {
    setPagando(partida);
    try {
      const { data } = await api.post(
        `/envios/${envio.envio_id}/cobros/${partida}/pagar`);
      // Sin saldo NO es un error HTTP: la ruta contesta 200 con
      // `estado: "pendiente"` y el motivo. Festejar cualquier 2xx le mostraba un
      // toast verde que decía «Pagado» a alguien que no pagó — y que se iba a
      // quedar esperando un paquete que no sale de Pacaraima.
      if (data?.estado === 'pagado') {
        toast.success(`Pagado ${num(data.monto_ris)} ${envio.moneda}`);
        // El saldo del contexto quedó viejo: sin esto la tarjeta sigue
        // mostrando lo que había ANTES de pagar.
        refreshUser?.();
      } else if (data?.motivo === 'saldo') {
        toast.error('No te alcanza el saldo. Cargá saldo y volvé a intentar.');
        refreshUser?.();
      } else if (data?.motivo === 'en_curso') {
        toast('Ya se está procesando. Esperá unos segundos y actualizá.');
      } else {
        toast.error('No se pudo completar el pago. Probá de nuevo en un momento.');
      }
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo pagar.'));
    } finally {
      setPagando(null);
    }
  };

  return (
    <div style={{ ...tarjeta, backgroundColor: COLOR.alertaSuave, borderColor: '#fde68a' }}>
      <h3 style={{ ...titulo, color: '#92400e' }}><CreditCard size={16} /> Hay algo por pagar</h3>
      <p style={{ ...bajada, color: '#92400e' }}>
        Son {num(total)} {envio.moneda} en total. <strong>Un paquete con un cobro impago
        no sale de Pacaraima</strong> — no es una multa ni un error: es la regla, y hasta
        que se salde el paquete espera ahí.
      </p>
      <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '10px',
        backgroundColor: '#fff', border: '1px solid #fde68a', fontSize: '13px',
        color: '#92400e', display: 'flex', justifyContent: 'space-between', gap: '10px',
        flexWrap: 'wrap' }}>
        <span>Tu saldo: <strong>{num(saldo)} {envio.moneda}</strong></span>
        {alcanza
          ? <span>Alcanza para pagarlo.</span>
          : <span><strong>Te faltan {num(falta)} {envio.moneda}.</strong></span>}
      </div>

      {!alcanza ? (
        /* El camino de salida, ACÁ. Decirle «cargá saldo» en un toast que se va
           solo, sin un botón, es mandarlo a buscar la pantalla de recargas por
           su cuenta — y el que no la encuentra deja el paquete parado. */
        <div style={{ marginTop: '12px' }}>
          <Boton onClick={() => navigate('/recharge')} data-testid="recargar-saldo">
            <CreditCard size={14} /> Recargar saldo
          </Boton>
          <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: '#92400e' }}>
            Cuando la recarga se acredite, volvé acá y pagá. El paquete te espera en
            Pacaraima mientras tanto.
          </p>
        </div>
      ) : null}

      {partidas.map((p) => {
        // Cada partida se paga sola, asi que lo que decide su boton es SU monto
        // y no el total: con dos partidas y saldo para una, la primera se puede
        // pagar y la segunda no.
        const alcanzaEsta = saldo >= Number(p.monto_ris || 0);
        return (
          <div key={p.partida} style={{ display: 'flex', gap: '12px', alignItems: 'center',
            marginTop: '10px', flexWrap: 'wrap' }}>
            <span style={{ flex: 1, fontSize: '14px', color: '#92400e' }}>
              {p.concepto || p.partida} · <strong>{num(p.monto_ris)} {envio.moneda}</strong>
            </span>
            <Boton cargando={pagando === p.partida} disabled={!alcanzaEsta}
              onClick={() => pagar(p.partida)}>
              <CheckCircle2 size={14} /> Pagar con mi saldo
            </Boton>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Cargar el comprobante de despacho.
 *
 * El código de objeto es el que imprime el transportista al despachar, y es lo
 * que después ata la caja física a este envío. La foto es lo que el operador
 * mira para leer el peso: de esa lectura sale el cobro inicial, y por eso no
 * alcanza con tipear el número.
 */
function Comprobante({ envio, onListo }) {
  const [codigo, setCodigo] = useState('');
  const [posteado, setPosteado] = useState('');
  const [foto, setFoto] = useState(null);
  const [servicio, setServicio] = useState('');
  const [monto, setMonto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  const MAX = 8 * 1024 * 1024;
  const grande = foto && foto.size > MAX;
  // La fecha LOCAL. Con `toISOString` un usuario en Brasil despachando a las
  // 22:00 ve como máximo el día siguiente.
  const ahora = new Date();
  const hoy = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10);
  // El mismo formato que exige el backend (S10: dos letras, nueve dígitos, dos
  // letras) y la misma normalización. Avisar mientras se tipea es mejor que un
  // 400 después de elegir la foto.
  const limpio = codigo.replace(/[\s.-]/g, '').toUpperCase();
  const codigoMal = limpio && !/^[A-Z]{2}\d{9}[A-Z]{2}$/.test(limpio);
  const listo = !codigoMal && limpio && posteado && foto && !grande;

  const enviar = async () => {
    setEnviando(true);
    setError(null);
    const cuerpo = new FormData();
    cuerpo.append('codigo_objeto', limpio);
    cuerpo.append('posteado_at', posteado);
    cuerpo.append('foto', foto);
    if (servicio.trim()) cuerpo.append('servicio', servicio.trim());
    if (monto.trim()) cuerpo.append('monto_pagado_brl', monto.trim());
    try {
      await api.post(`/envios/${envio.envio_id}/comprobante`, cuerpo,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Comprobante cargado');
      onListo();
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo cargar el comprobante.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={tarjeta}>
      <h3 style={titulo}><Camera size={16} /> Ya despaché: cargar el comprobante</h3>
      <p style={bajada}>
        Cargalo apenas despaches. Es la única forma de que nos enteremos —{' '}
        <strong>no cobra nada</strong>: el primer cobro sale cuando nuestro operador verifique
        la foto, con el peso que midió el transportista.
      </p>
      <div style={grilla('180px')}>
        <Campo etiqueta="Código de objeto"
          ayuda="El que te dio el transportista al despachar. Dos letras, nueve números y dos letras: AA123456789BR."
          error={codigoMal ? 'No tiene la forma de un código de objeto.' : null}>
          <Texto value={codigo} maxLength={40}
            onChange={(e) => setCodigo(e.target.value.toUpperCase())}
            invalido={!!codigoMal} />
        </Campo>
        <Campo etiqueta="Fecha del despacho" ayuda="La que figura en el comprobante.">
          <Texto type="date" value={posteado} max={hoy}
            onChange={(e) => setPosteado(e.target.value)} invalido={!posteado} />
        </Campo>
      </div>
      <div style={{ marginTop: '14px' }}>
        <Campo etiqueta="Foto del comprobante"
          ayuda="Que se lea el peso y las medidas. Hasta 8 MB. Le borramos los datos de ubicación antes de guardarla."
          error={grande
            ? `Pesa ${Math.round(foto.size / 1048576)} MB y el máximo son 8. Sacala de nuevo con menos resolución.`
            : null}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input type="file" accept="image/*,application/pdf"
              onChange={(e) => setFoto(e.target.files?.[0] || null)}
              style={{ fontSize: '13px' }} />
            {foto ? (
              <button type="button" onClick={() => setFoto(null)}
                style={{ border: 'none', background: 'none', cursor: 'pointer',
                  fontSize: '12px', color: COLOR.primarioOscuro }}>quitar</button>
            ) : null}
          </div>
        </Campo>
      </div>
      <details style={{ marginTop: '14px' }}>
        <summary style={{ fontSize: '13px', color: COLOR.suave, cursor: 'pointer' }}>
          Cuánto pagaste por este tramo (opcional)
        </summary>
        <p style={{ ...bajada, marginTop: '8px' }}>
          No lo cobramos ni lo devolvemos: nos sirve para que la orientación de precios que
          le mostramos a otros usuarios se parezca a la realidad.
        </p>
        <div style={grilla('160px')}>
          <Campo etiqueta="Servicio">
            <Texto value={servicio} maxLength={40} onChange={(e) => setServicio(e.target.value)} />
          </Campo>
          <Campo etiqueta="Monto (R$)">
            <Texto inputMode="decimal" value={monto}
              onChange={(e) => setMonto(e.target.value)} />
          </Campo>
        </div>
      </details>
      {error ? <Aviso tono="error" style={{ marginTop: '14px' }}>{error}</Aviso> : null}
      <Boton style={{ marginTop: '16px' }} onClick={enviar} cargando={enviando}
        disabled={!listo}>
        <Camera size={14} /> Cargar el comprobante
      </Boton>
    </div>
  );
}
