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
import { Link, useParams } from 'react-router-dom';
import {
  Camera, CheckCircle2, CreditCard, Link2, PackageSearch, RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt } from '../utils/format';
import Chrome from '../components/envios/Chrome';
import Etiqueta from '../components/envios/Etiqueta';
import {
  Area, Aviso, Boton, Campo, Cargando, Texto, Vacio,
} from '../components/envios/ui';
import {
  COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo,
} from '../components/envios/estilos';
import { PIDE_ALGO, TITULOS, tonoDe } from '../components/envios/estados';

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
        <Aviso tono="alerta" titulo="Esta cotización todavía no está confirmada">
          <strong>No despaches nada hasta confirmarla.</strong> Una cotización sin confirmar
          se borra sola
          {envio.vence_at ? ` el ${fecha(envio.vence_at)}` : ' a las 48 horas'}, y si la caja
          ya salió no va a haber ningún envío que la reclame.
          <div style={{ marginTop: '10px' }}>
            <Link to="/envios/nuevo" style={{ textDecoration: 'none' }}>
              <Boton>Cotizar de nuevo</Boton>
            </Link>
          </div>
        </Aviso>
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

function Pagar({ envio, partidas, onListo }) {
  const [pagando, setPagando] = useState(null);
  const total = partidas.reduce((s, p) => s + Number(p.monto_ris || 0), 0);

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
      } else if (data?.motivo === 'saldo') {
        toast.error('No te alcanza el saldo. Cargá saldo y volvé a intentar.');
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
      {partidas.map((p) => (
        <div key={p.partida} style={{ display: 'flex', gap: '12px', alignItems: 'center',
          marginTop: '10px', flexWrap: 'wrap' }}>
          <span style={{ flex: 1, fontSize: '14px', color: '#92400e' }}>
            {p.concepto || p.partida} · <strong>{num(p.monto_ris)} {envio.moneda}</strong>
          </span>
          <Boton cargando={pagando === p.partida} onClick={() => pagar(p.partida)}>
            <CheckCircle2 size={14} /> Pagar con mi saldo
          </Boton>
        </div>
      ))}
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
