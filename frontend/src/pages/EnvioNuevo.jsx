/**
 * EnvioNuevo.jsx — Cotizar y confirmar un envío.
 *
 * LO QUE ESTA PANTALLA TIENE QUE DEJAR CLARISIMO
 *   RIS App cobra UN SOLO servicio: retiro en Pacaraima, repesaje y traslado
 *   hasta la oficina del transportista en Santa Elena. Los dos tramos de
 *   transporte los contrata y los paga el usuario, y lo que se le muestra de
 *   esos dos es ORIENTATIVO.
 *
 *   El peor malentendido posible es que alguien crea que pagando acá ya cubrió
 *   el envío entero. Eso no se arregla después, con un reclamo: se arregla en
 *   esta pantalla, poniendo el concepto escrito, el total en un bloque, y las
 *   referencias en otro que dice quién las cobra. El backend ya separa los dos
 *   bloques en la respuesta; acá se respeta esa separación.
 *
 * COTIZAR NO COBRA NADA, CONFIRMAR TAMPOCO
 *   El primer cobro se emite cuando el operador verifica el comprobante en
 *   Pacaraima, contra el peso que midió el transportista de origen. Se dice acá,
 *   antes de pedir ninguna aceptación.
 *
 * LAS DOS ACEPTACIONES SON DOS
 *   Una es el contenido; la otra, que el precio es un estimado. Juntarlas en un
 *   checkbox esconde la del precio detrás de la del contenido — y «aceptaste que
 *   podía variar» no se sostiene el día que haya que defender un ajuste si esa
 *   frase estaba adentro de una casilla que decía otra cosa.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, Calculator, Copy, PackagePlus, ShieldAlert,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { fmt } from '../utils/format';
import { useAuth } from '../contexts/AuthContext';
import Chrome from '../components/envios/Chrome';
import Etiqueta from '../components/envios/Etiqueta';
import {
  Area, Aviso, Boton, Campo, Cargando, Interruptor, Seleccion, Texto, Vacio,
} from '../components/envios/ui';
import { COLOR, bajada, grilla, mensajeDeError, tarjeta, titulo } from '../components/envios/estilos';

const num = (v) => (v === null || v === undefined || v === '' ? '—' : fmt(v, 2));

/**
 * Las medidas viajan en TEXTO y con punto.
 *
 * El backend rechaza la coma con un mensaje que lo dice, pero recibirlo después
 * de completar seis campos es peor que no poder escribirla: acá se avisa en el
 * campo, mientras se tipea.
 */
const NUMERO = /^\d+(\.\d+)?$/;

function problemaDeMedida(valor, { obligatorio = true } = {}) {
  const texto = String(valor ?? '').trim();
  if (!texto) return obligatorio ? 'Falta.' : null;
  if (texto.includes(',')) return 'Usá punto, no coma: 2.30';
  if (!NUMERO.test(texto)) return 'Solo números.';
  if (Number(texto) <= 0 && obligatorio) return 'Tiene que ser mayor que cero.';
  return null;
}

const VACIO = {
  origen: { cep: '', ciudad: '', uf: '' },
  destino: { transportista_id: '', agencia_codigo: '',
    destinatario: { nombre: '', documento: '', telefono: '' } },
  paquete: { peso_kg: '', largo_cm: '', ancho_cm: '', alto_cm: '',
    contenido_descripcion: '', valor_declarado_brl: '0' },
  modalidad_flete: 'destino',
};

export default function EnvioNuevo() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [limites, setLimites] = useState(null);
  const [catalogo, setCatalogo] = useState(null);
  const [cargando, setCargando] = useState(true);
  // El CEP del perfil como valor INICIAL, no como efecto: es el dato que más
  // cuesta tipear y el que menos cambia, y aplicarlo desde un efecto pisaría lo
  // que el usuario ya escribió si el perfil llega tarde.
  const [datos, setDatos] = useState(() => (user?.cep_origen
    ? { ...VACIO, origen: { ...VACIO.origen, cep: user.cep_origen } }
    : VACIO));
  const [cotizacion, setCotizacion] = useState(null);
  const [cotizando, setCotizando] = useState(false);
  const [error, setError] = useState(null);
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const [l, c] = await Promise.all([
        api.get('/envios/limites'),
        api.get('/envios/catalogo'),
      ]);
      if (!vivo.current) return;
      setLimites(l.data);
      setCatalogo(c.data);
    } catch (err) {
      if (!vivo.current) return;
      toast.error(mensajeDeError(err, 'No se pudo abrir el formulario.'));
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  if (cargando) return <Cargando texto="Abriendo el formulario…" />;

  // Cotizar ESCRIBE el nombre, el documento y el teléfono de un tercero en
  // Venezuela, así que la ruta pide cuenta verificada. Avisarlo recién al apretar
  // «Ver el precio» —con un 403 en inglés— es hacerle cargar todo eso a alguien
  // que no va a poder cotizar.
  if (user && user.verification_status !== 'verified') {
    return (
      <Chrome titulo="Enviar un paquete" volverA="/envios">
        <Vacio titulo="Necesitás verificar tu cuenta">
          Para cotizar hay que cargar el nombre, el documento y el teléfono de quien recibe en
          Venezuela. Pedimos la verificación antes de guardar los datos de otra persona.
          <div style={{ marginTop: '14px' }}>
            <Link to="/verification" style={{ textDecoration: 'none' }}>
              <Boton>Verificar mi cuenta</Boton>
            </Link>
          </div>
        </Vacio>
      </Chrome>
    );
  }

  if (!limites?.disponible) {
    return (
      <Chrome titulo="Enviar un paquete" volverA="/">
        <Vacio titulo="El servicio no está disponible por ahora">
          {(limites?.faltantes || []).join(' ') || 'Volvé a intentar más tarde.'}
        </Vacio>
      </Chrome>
    );
  }

  const transportista = (catalogo?.transportistas || [])
    .find((t) => t.transportista_id === datos.destino.transportista_id);
  const agencias = transportista?.agencias || [];

  const minimoDescripcion = limites?.descripcion_min_caracteres || 10;

  const problemas = {
    cep: /^\d{8}$/.test(datos.origen.cep.replace(/\D/g, '')) ? null : 'Ocho dígitos.',
    peso: problemaDeMedida(datos.paquete.peso_kg),
    largo: problemaDeMedida(datos.paquete.largo_cm),
    ancho: problemaDeMedida(datos.paquete.ancho_cm),
    alto: problemaDeMedida(datos.paquete.alto_cm),
    valor: problemaDeMedida(datos.paquete.valor_declarado_brl, { obligatorio: false }),
    nombre: datos.destino.destinatario.nombre.trim().split(/\s+/).length >= 2
      ? null : 'Nombre y apellido.',
    // Los mismos mínimos que el modelo: recibirlos como 422 después de completar
    // todo el formulario es peor que no poder avanzar.
    documento: datos.destino.destinatario.documento.trim().length >= 5
      ? null : 'Al menos cinco caracteres.',
    telefono: datos.destino.destinatario.telefono.trim().length >= 7
      ? null : 'Al menos siete caracteres.',
    uf: !datos.origen.uf.trim() || datos.origen.uf.trim().length === 2
      ? null : 'Dos letras, o dejalo vacío.',
    // El mínimo lo publica `/envios/limites`: es un criterio de aduana que el
    // super administrador cambia sin deploy. Escribirlo acá garantizaba que un
    // día la pantalla anunciara un requisito que ya no era el del servidor.
    descripcion: datos.paquete.contenido_descripcion.trim().length >= minimoDescripcion
      ? null : `Al menos ${minimoDescripcion} caracteres.`,
  };
  const listo = Object.values(problemas).every((p) => !p)
    && datos.destino.transportista_id && datos.destino.agencia_codigo;

  const cotizar = async () => {
    setCotizando(true);
    setError(null);
    try {
      const res = await api.post('/envios/cotizar', {
        origen: {
          cep: datos.origen.cep.replace(/\D/g, ''),
          ciudad: datos.origen.ciudad || null,
          // Menos de dos letras no es una UF: el modelo pide exactamente dos,
          // y mandar una sola devuelve un 422 con el texto de Pydantic.
          uf: datos.origen.uf.trim().length === 2
            ? datos.origen.uf.trim().toUpperCase() : null,
        },
        destino: {
          transportista_id: datos.destino.transportista_id,
          agencia_codigo: datos.destino.agencia_codigo,
          destinatario: datos.destino.destinatario,
        },
        paquete: {
          ...datos.paquete,
          // `""` no es cero: el validador lo rechaza con «no puede estar vacío».
          valor_declarado_brl: datos.paquete.valor_declarado_brl.trim() || '0',
        },
        modalidad_flete: datos.modalidad_flete,
      });
      setCotizacion(res.data);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo cotizar.'));
    } finally {
      setCotizando(false);
    }
  };

  if (cotizacion) {
    return (
      <Chrome titulo="Tu cotización" volverA="/envios">
        <Cotizacion cotizacion={cotizacion} limites={limites}
          onVolver={() => setCotizacion(null)}
          onCreado={(id) => navigate(`/envios/${id}`)} />
      </Chrome>
    );
  }

  const campoPaquete = (k) => (e) => setDatos((d) => ({
    ...d, paquete: { ...d.paquete, [k]: e.target.value },
  }));

  return (
    <Chrome titulo="Enviar un paquete" volverA="/envios">
      <Prohibidos limites={limites} />

      <div style={tarjeta}>
        <h3 style={titulo}><PackagePlus size={16} /> El paquete</h3>
        <p style={bajada}>
          Las medidas de la caja cerrada, con el paquete adentro. El precio se calcula
          sobre el peso facturable, que es el mayor entre el peso real y el volumétrico.
        </p>
        <div style={grilla('140px')}>
          <Campo etiqueta="Peso (kg)" error={datos.paquete.peso_kg ? problemas.peso : null}>
            <Texto inputMode="decimal" value={datos.paquete.peso_kg}
              onChange={campoPaquete('peso_kg')} invalido={!!problemas.peso} />
          </Campo>
          <Campo etiqueta="Largo (cm)" error={datos.paquete.largo_cm ? problemas.largo : null}>
            <Texto inputMode="decimal" value={datos.paquete.largo_cm}
              onChange={campoPaquete('largo_cm')} invalido={!!problemas.largo} />
          </Campo>
          <Campo etiqueta="Ancho (cm)" error={datos.paquete.ancho_cm ? problemas.ancho : null}>
            <Texto inputMode="decimal" value={datos.paquete.ancho_cm}
              onChange={campoPaquete('ancho_cm')} invalido={!!problemas.ancho} />
          </Campo>
          <Campo etiqueta="Alto (cm)" error={datos.paquete.alto_cm ? problemas.alto : null}>
            <Texto inputMode="decimal" value={datos.paquete.alto_cm}
              onChange={campoPaquete('alto_cm')} invalido={!!problemas.alto} />
          </Campo>
        </div>
        <div style={{ marginTop: '14px' }}>
          <Campo etiqueta="Qué mandás" error={datos.paquete.contenido_descripcion
            ? problemas.descripcion : null}
            ayuda="Con detalle. Es lo que se declara en la frontera, y una descripción vaga es lo que hace que una caja quede retenida.">
            <Area value={datos.paquete.contenido_descripcion} filas={3} maxLength={500}
              onChange={campoPaquete('contenido_descripcion')}
              invalido={!!problemas.descripcion} />
          </Campo>
        </div>
        <div style={{ ...grilla('180px'), marginTop: '14px' }}>
          <Campo etiqueta="Valor declarado (R$)" error={problemas.valor}
            ayuda="Lo que cuesta reponer el contenido. Puede afectar el precio.">
            <Texto inputMode="decimal" value={datos.paquete.valor_declarado_brl}
              onChange={campoPaquete('valor_declarado_brl')} invalido={!!problemas.valor} />
          </Campo>
        </div>
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}>Desde dónde despachás</h3>
        <p style={bajada}>
          Tu ciudad en Brasil. Sirve para estimar lo que te va a cobrar el transportista
          hasta Pacaraima — un monto que <strong>no cobra RIS App</strong>.
        </p>
        <div style={grilla('160px')}>
          <Campo etiqueta="CEP" error={datos.origen.cep ? problemas.cep : null}>
            <Texto inputMode="numeric" value={datos.origen.cep} maxLength={9}
              invalido={!!problemas.cep}
              onChange={(e) => setDatos((d) => ({
                ...d, origen: { ...d.origen, cep: e.target.value },
              }))} />
          </Campo>
          <Campo etiqueta="Ciudad" ayuda="Opcional.">
            <Texto value={datos.origen.ciudad} maxLength={80}
              onChange={(e) => setDatos((d) => ({
                ...d, origen: { ...d.origen, ciudad: e.target.value },
              }))} />
          </Campo>
          <Campo etiqueta="UF" ayuda="Opcional. Sin ella igual se cotiza."
            error={problemas.uf}>
            <Texto value={datos.origen.uf} maxLength={2} invalido={!!problemas.uf}
              onChange={(e) => setDatos((d) => ({
                ...d, origen: { ...d.origen, uf: e.target.value.toUpperCase() },
              }))} />
          </Campo>
        </div>
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}>A dónde va</h3>
        {catalogo?.degradado ? (
          <Aviso tono="alerta" style={{ marginBottom: '12px' }}>
            La lista de agencias puede estar incompleta. Si no ves la que buscás, probá de
            nuevo en un rato.
          </Aviso>
        ) : null}
        <div style={grilla('200px')}>
          <Campo etiqueta="Transportista en Venezuela"
            ayuda="Lo contratás y lo pagás vos. RIS App deja el paquete en su oficina de Santa Elena.">
            <Seleccion value={datos.destino.transportista_id}
              onChange={(e) => setDatos((d) => ({
                ...d,
                destino: { ...d.destino, transportista_id: e.target.value, agencia_codigo: '' },
              }))}
              opciones={[{ valor: '', texto: 'Elegí uno' },
                ...(catalogo?.transportistas || []).map((t) => ({
                  valor: t.transportista_id, texto: t.nombre,
                }))]} />
          </Campo>
          <Campo etiqueta="Agencia donde retiran"
            ayuda={transportista ? `${agencias.length} agencia(s).` : 'Elegí primero el transportista.'}>
            <Seleccion value={datos.destino.agencia_codigo} disabled={!transportista}
              onChange={(e) => setDatos((d) => ({
                ...d, destino: { ...d.destino, agencia_codigo: e.target.value },
              }))}
              opciones={[{ valor: '', texto: 'Elegí una' },
                ...agencias.map((a) => ({
                  valor: a.codigo,
                  texto: `${a.nombre} — ${a.ciudad}, ${a.estado}`,
                }))]} />
          </Campo>
        </div>

        <h4 style={{ ...titulo, marginTop: '20px' }}>Quién recibe</h4>
        <div style={grilla('180px')}>
          <Campo etiqueta="Nombre y apellido"
            error={datos.destino.destinatario.nombre ? problemas.nombre : null}
            ayuda="Los dos: es lo que el mostrador compara contra el documento.">
            <Texto value={datos.destino.destinatario.nombre} maxLength={120}
              invalido={!!problemas.nombre}
              onChange={(e) => setDatos((d) => ({
                ...d,
                destino: { ...d.destino,
                  destinatario: { ...d.destino.destinatario, nombre: e.target.value } },
              }))} />
          </Campo>
          <Campo etiqueta="Documento"
            error={datos.destino.destinatario.documento ? problemas.documento : null}>
            <Texto value={datos.destino.destinatario.documento} maxLength={30}
              invalido={!!problemas.documento}
              onChange={(e) => setDatos((d) => ({
                ...d,
                destino: { ...d.destino,
                  destinatario: { ...d.destino.destinatario, documento: e.target.value } },
              }))} />
          </Campo>
          <Campo etiqueta="Teléfono"
            error={datos.destino.destinatario.telefono ? problemas.telefono : null}>
            <Texto value={datos.destino.destinatario.telefono} maxLength={30}
              invalido={!!problemas.telefono}
              onChange={(e) => setDatos((d) => ({
                ...d,
                destino: { ...d.destino,
                  destinatario: { ...d.destino.destinatario, telefono: e.target.value } },
              }))} />
          </Campo>
        </div>
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}>El tramo final, hasta el domicilio</h3>
        <p style={bajada}>
          Lo cobra el transportista de Venezuela, <strong>no RIS App</strong>. Elegí quién lo
          paga — no cambia ni un centavo de lo que cotizamos acá.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {[['destino', 'Lo paga quien recibe', 'Al retirar en la agencia. RIS App no toca esa plata.'],
            ['prepago', 'Lo pago yo', 'Se lo mandás como remesa cuando el operador te diga el monto — recién se sabe en el mostrador.']]
            .map(([valor, etiqueta, ayuda]) => (
              <label key={valor} style={{ display: 'flex', gap: '10px', cursor: 'pointer',
                padding: '12px', borderRadius: '10px',
                border: `1px solid ${datos.modalidad_flete === valor ? COLOR.primario : COLOR.borde}`,
                backgroundColor: datos.modalidad_flete === valor ? COLOR.primarioSuave : '#fff' }}>
                <input type="radio" name="modalidad" checked={datos.modalidad_flete === valor}
                  onChange={() => setDatos((d) => ({ ...d, modalidad_flete: valor }))}
                  style={{ marginTop: '2px', accentColor: COLOR.primario }} />
                <span>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: COLOR.texto }}>
                    {etiqueta}
                  </span>
                  <span style={{ display: 'block', fontSize: '12px', color: COLOR.suave,
                    lineHeight: 1.4 }}>{ayuda}</span>
                </span>
              </label>
            ))}
        </div>
      </div>

      {error ? <Aviso tono="error" titulo="No se pudo cotizar">{error}</Aviso> : null}

      <Boton onClick={cotizar} cargando={cotizando} disabled={!listo}
        style={{ justifyContent: 'center', padding: '14px' }}>
        <Calculator size={16} /> Ver el precio
      </Boton>
      <p style={{ ...bajada, textAlign: 'center', margin: 0 }}>
        Cotizar es gratis y no reserva nada.
      </p>
    </Chrome>
  );
}

function Prohibidos({ limites }) {
  const [abierto, setAbierto] = useState(false);
  const lista = limites?.prohibidos || [];
  if (!lista.length) return null;
  return (
    <div style={{ ...tarjeta, backgroundColor: COLOR.errorSuave, borderColor: '#fecaca' }}>
      <button type="button" onClick={() => setAbierto((a) => !a)}
        style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%',
          border: 'none', background: 'none', cursor: 'pointer', padding: 0,
          textAlign: 'left' }}>
        <ShieldAlert size={16} color="#991b1b" />
        <span style={{ fontSize: '14px', fontWeight: 700, color: '#991b1b', flex: 1 }}>
          Qué no se puede mandar
        </span>
        <span style={{ fontSize: '12px', color: '#991b1b' }}>
          {abierto ? 'ocultar' : `ver los ${lista.length}`}
        </span>
      </button>
      {abierto ? (
        <ul style={{ margin: '10px 0 0 0', paddingLeft: '20px', fontSize: '13px',
          color: '#991b1b', lineHeight: 1.7 }}>
          {lista.map((p) => <li key={p}>{p}</li>)}
        </ul>
      ) : null}
    </div>
  );
}

function Cotizacion({ cotizacion, onVolver, onCreado }) {
  const [contenido, setContenido] = useState(false);
  const [estimado, setEstimado] = useState(false);
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState(null);
  // Una sola clave por cotización: el doble clic en «confirmar» no puede crear
  // dos envíos, y un reintento después de un timeout tiene que devolver el
  // mismo, no uno nuevo. Se genera en un efecto y no durante el render: `Date.now`
  // y `Math.random` no son puras, y un render que se repite no puede cambiar la
  // clave con la que ya se mandó una petición.
  const clave = useRef(null);
  useEffect(() => {
    if (!clave.current) {
      clave.current = (globalThis.crypto?.randomUUID?.()
        || `c_${Date.now()}_${Math.random().toString(36).slice(2)}`);
    }
  }, []);

  const pago = cotizacion.a_pagar_en_risapp || {};
  const vence = cotizacion.vence_at ? new Date(cotizacion.vence_at) : null;

  const confirmar = async () => {
    setCreando(true);
    setError(null);
    try {
      const res = await api.post('/envios/crear', {
        envio_id: cotizacion.envio_id,
        declaracion: {
          // Los valores REALES, no dos literales. El gate del botón ya los exige,
          // pero esto es el registro que se lee el día que haya que defender un
          // ajuste, y «una aceptación es un hecho, no una interpretación».
          contenido_aceptado: contenido,
          estimado_aceptado: estimado,
          terminos_version: cotizacion.terminos_version,
        },
        idempotency_key: clave.current || undefined,
      });
      toast.success('Envío confirmado');
      onCreado(res.data?.envio_id || cotizacion.envio_id);
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo confirmar.'));
    } finally {
      setCreando(false);
    }
  };

  return (
    <>
      <div style={{ ...tarjeta, background: 'linear-gradient(135deg,#5B4FE9,#7A6FF0)',
        border: 'none', color: '#fff' }}>
        <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, letterSpacing: '0.04em',
          textTransform: 'uppercase', opacity: 0.85 }}>
          {pago.concepto || 'El servicio de RIS App'}
        </p>
        <p style={{ margin: '6px 0 0 0', fontSize: '34px', fontWeight: 800,
          fontVariantNumeric: 'tabular-nums' }}>
          {num(pago.total_estimado_ris)} <span style={{ fontSize: '18px' }}>
            {cotizacion.moneda}</span>
        </p>
        <p style={{ margin: '8px 0 0 0', fontSize: '13px', lineHeight: 1.5, opacity: 0.9 }}>
          Peso facturable {num(cotizacion.peso_facturable?.propio?.kg)} kg
          {' '}(real {num(cotizacion.peso_real_kg)}, volumétrico
          {' '}{num(cotizacion.peso_facturable?.propio?.volumetrico_kg)}).
        </p>
      </div>

      <Aviso tono="alerta" titulo="Es un estimado, y puede cambiar">
        {cotizacion.aviso_estimado}
        {cotizacion.banda_variacion_pct
          ? ` Normalmente la diferencia no pasa del ${cotizacion.banda_variacion_pct} %.`
          : ''}
      </Aviso>

      <div style={tarjeta}>
        <h3 style={titulo}>Lo que vas a pagar por fuera</h3>
        <p style={bajada}>
          Estos <strong>no los cobra RIS App</strong> y no están sumados arriba: los contratás
          y los pagás vos. Los montos son una orientación para que sepas con qué contar.
        </p>
        {(cotizacion.referencias || []).length === 0 ? (
          <p style={{ ...bajada, margin: 0 }}>No tenemos referencias de estos tramos.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {cotizacion.referencias.map((r) => (
              <div key={`${r.rol}-${r.codigo}`} style={{ display: 'flex', gap: '12px',
                alignItems: 'flex-start', padding: '12px', borderRadius: '10px',
                backgroundColor: '#f9fafb', border: `1px solid ${COLOR.borde}` }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: COLOR.texto }}>
                    {r.etiqueta}
                  </p>
                  <p style={{ margin: '2px 0 0 0', fontSize: '12px', color: COLOR.suave,
                    fontFamily: 'monospace' }}>
                    {r.codigo}
                  </p>
                  {r.detalle ? (
                    <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: COLOR.suave }}>
                      {r.detalle}
                    </p>
                  ) : null}
                  {r.desactualizada ? (
                    <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: COLOR.alerta }}>
                      <AlertTriangle size={11} style={{ display: 'inline' }} />{' '}
                      Esta referencia es vieja: puede haber cambiado.
                    </p>
                  ) : null}
                </div>
                <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <span style={{ fontSize: '15px', fontWeight: 700, color: COLOR.texto }}>
                    {r.monto === null ? '—' : `${num(r.monto)} ${r.moneda || ''}`}
                  </span>
                  <span style={{ display: 'block', fontSize: '11px', color: COLOR.suave }}>
                    no se cobra acá
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/*
        La dirección de despacho, A LA VISTA y ANTES de las dos aceptaciones.
        Confirmar es comprometerse a mandar una caja a nombre de alguien, y
        pedirle eso a una persona que no vio ese nombre es pedirle una firma en
        blanco. Ya viene congelada en la respuesta de `cotizar`, en el mismo
        momento que el precio: mostrarla acá no adelanta ninguna decisión.

        Va en modo `previa`: se ve el texto, no el botón de copiar. La versión
        accionable —«rotulá la caja así»— vive en el detalle del envío, que es
        adonde se llega al confirmar. Estaba plegada acá abajo justamente
        porque entregar el texto listo para copiar ANTES de confirmar hizo que
        alguien lo copiara, fuera a despachar y no confirmara nunca: a las 48 h
        la cotización se borra por TTL y la caja llega sin envío que la reclame.
        Mostrar sin accionar resuelve las dos cosas.
      */}
      <Etiqueta retiro={cotizacion.retiro} previa />

      <div style={tarjeta}>
        <h3 style={titulo}>Antes de confirmar</h3>
        <p style={bajada}>
          Confirmar <strong>no cobra nada</strong>. El primer cobro se emite cuando nuestro
          operador verifique tu comprobante en Pacaraima, con el peso que midió el
          transportista al despachar.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <Interruptor activo={contenido} onChange={setContenido}
            etiqueta="Lo que mando no está en la lista de prohibidos"
            ayuda="Una caja con contenido prohibido queda retenida en la frontera, y el costo es tuyo." />
          <Interruptor activo={estimado} onChange={setEstimado}
            etiqueta="Entiendo que el precio es un estimado y se cierra al pesar en Pacaraima"
            ayuda="Si el peso real es mayor que el declarado, se cobra la diferencia; si es menor, se devuelve." />
        </div>
        {error ? <Aviso tono="error" style={{ marginTop: '14px' }}>{error}</Aviso> : null}
        <div style={{ display: 'flex', gap: '10px', marginTop: '18px', flexWrap: 'wrap' }}>
          <Boton onClick={confirmar} cargando={creando}
            disabled={!contenido || !estimado}
            style={{ flex: 1, justifyContent: 'center', padding: '14px' }}>
            Confirmar el envío <ArrowRight size={16} />
          </Boton>
          <Boton variante="secundario" onClick={onVolver}>Cambiar algo</Boton>
        </div>
        {vence ? (
          <p style={{ ...bajada, margin: '12px 0 0 0', textAlign: 'center' }}>
            {/* Sin punto final: `toLocaleString` en es-AR ya termina en «p. m.»
                y agregar otro deja «4:35 p. m..» */}
            Esta cotización vale hasta el {vence.toLocaleString('es-AR',
              { dateStyle: 'short', timeStyle: 'short' })}
          </p>
        ) : null}
      </div>
    </>
  );
}
