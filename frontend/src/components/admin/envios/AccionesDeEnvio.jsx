/**
 * AccionesDeEnvio.jsx — Lo que se puede hacer con UN paquete, según dónde está.
 *
 * DOS DE ESTAS ACCIONES MUEVEN SALDO REAL
 *   Verificar el comprobante emite el cobro inicial. Repesar cobra la diferencia
 *   o la devuelve. Las dos van con una clave de idempotencia que NO cambia entre
 *   reintentos: un timeout seguido de un segundo clic es el caso normal en un
 *   mostrador con mala señal, y sin la clave el backend no tiene forma de saber
 *   que es el mismo cobro.
 *
 * LO QUE SE VERIFICA ES LO QUE DICE LA FOTO
 *   No lo que el usuario tipeó: con eso, cualquiera escribiría 0,1 kg y el
 *   servicio se cobraría solo. Por eso la foto se muestra al lado del formulario
 *   y no en otra pantalla.
 */
import { useEffect, useState } from 'react';
import {
  AlertTriangle, Camera, CheckCircle2, PackageCheck, Printer, Scale, Send, Truck,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { fmt } from '../../../utils/format';
import { Aviso, Boton, Campo, Cargando, Interruptor, Texto, Area } from '../../envios/ui';
import { COLOR, bajada, grilla, mensajeDeError, titulo } from '../../envios/estilos';
import { DESVIOS, DESVIOS_LEGALES, claveDe, olvidarClave } from './operacion';
import { imprimirTicket } from './ticket';

const MEDIDAS = [['peso_kg', 'Peso (kg)'], ['largo_cm', 'Largo (cm)'],
  ['ancho_cm', 'Ancho (cm)'], ['alto_cm', 'Alto (cm)']];

const VACIO = { peso_kg: '', largo_cm: '', ancho_cm: '', alto_cm: '' };

/**
 * Una medida válida: dígitos y, si acaso, un punto decimal.
 *
 * LA COMA ES EL ERROR CARO
 *   «6,5» es como se escribe seis kilos y medio en castellano y en portugués, y
 *   es lo que sale solo tipeando en un mostrador. El backend no la puede
 *   convertir a Decimal, así que el cobro falla — pero la verificación ya quedó
 *   escrita, y hasta hace poco eso dejaba el envío muerto: no se podía verificar
 *   de nuevo, no se podía repesar, y en la cola se veía sano. Se arregló del
 *   lado del servidor, y acá se ataja antes: es un error que no tiene por qué
 *   llegar a viajar.
 */
const NUMERO = /^\d+(\.\d+)?$/;

function problemaDeMedida(valor) {
  const texto = String(valor ?? '').trim();
  if (!texto) return 'Falta.';
  if (texto.includes(',')) return 'Usá punto, no coma: 6.5';
  if (!NUMERO.test(texto)) return 'Solo números.';
  const n = Number(texto);
  if (n <= 0) return 'Tiene que ser mayor que cero.';
  if (n > 1000) return 'Ese número no parece de un paquete.';
  return null;
}

const medidasCompletas = (m) => MEDIDAS.every(([k]) => !problemaDeMedida(m[k]));

/**
 * El monto del flete es PLATA, no una medida de la caja.
 *
 * Estaba validado con `problemaDeMedida`, que corta en 1000 porque «ese número
 * no parece de un paquete» — cierto para los centímetros de una caja y falso
 * para un flete. Un flete de mil y pico dejaba el botón muerto para siempre,
 * con un cartel que hablaba de paquetes y que además NO SE VEÍA: el campo no
 * mostraba el error, así que desde afuera el botón simplemente no andaba.
 *
 * El tope de acá es contra el error de tipeo —pegar un teléfono en el campo del
 * monto—, no contra un flete caro. El servidor no tiene tope: acepta cualquier
 * positivo finito, y este número no puede ser más estricto que él sin volver a
 * trabar lo que el servidor sí aceptaría.
 */
function problemaDeMonto(valor) {
  const texto = String(valor ?? '').trim();
  if (!texto) return 'Falta.';
  if (texto.includes(',')) return 'Usá punto, no coma: 1500.50';
  if (!NUMERO.test(texto)) return 'Solo números.';
  const n = Number(texto);
  if (n <= 0) return 'Tiene que ser mayor que cero.';
  if (n > 1000000) return 'Revisá el monto: parece un error de tipeo.';
  return null;
}

const num = (v) => (v === null || v === undefined || v === '' ? '—' : fmt(v, 2));

export default function AccionesDeEnvio({ envio, parada, borrador, onBorrador, onListo }) {
  const acciones = parada.acciones || [];
  const medidas = borrador || VACIO;
  return (
    <div style={{ paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {acciones.includes('verificar')
        ? <Verificar envio={envio} medidas={medidas} onMedidas={onBorrador}
            onListo={onListo} /> : null}
      {acciones.includes('repesar')
        ? <Repesar envio={envio} medidas={medidas} onMedidas={onBorrador}
            onListo={onListo} /> : null}
      {acciones.includes('despachar') ? <Despachar envio={envio} onListo={onListo} /> : null}
      {acciones.includes('entregar') ? <Entregar envio={envio} onListo={onListo} /> : null}
      <Flete envio={envio} onListo={onListo} />
      <Desviar envio={envio} estado={parada.estado} onListo={onListo} />
    </div>
  );
}

/**
 * El comprobante, traído por el mismo cliente HTTP que todo lo demás.
 *
 * NO con `<img src="/api/...">`, y por dos razones que se descubren tarde:
 *
 *   1. **Un `<img>` no lleva la sesión.** El cliente de la app agrega el token
 *      en un interceptor; una etiqueta `<img>` la pide el navegador sola, sin
 *      pasar por ahí. En un despliegue que autentique por cabecera y no por
 *      cookie, la foto da 401 y el operador ve un cuadrito roto.
 *
 *   2. **Un comprobante puede ser un PDF.** El backend acepta JPG, PNG, HEIC y
 *      PDF, y `<img>` no puede mostrar un PDF nunca: siempre dispara `onError`,
 *      con lo cual la pantalla le decía «no se pudo traer, probá de nuevo en un
 *      minuto» sobre un archivo que estaba perfecto — para siempre.
 *
 * Trayéndolo como blob se sabe el código de estado de verdad (404 / 410 / 503
 * significan cosas distintas para quien está en el mostrador) y se sabe el tipo
 * real, que es lo que decide cómo mostrarlo.
 */
function Comprobante({ envio }) {
  const [estado, setEstado] = useState({ cargando: true });
  const asset = envio.comprobante_asset_id;
  const envioId = envio.envio_id;

  useEffect(() => {
    if (!asset) return undefined;
    let url = null;
    let vigente = true;
    (async () => {
      try {
        const res = await api.get(
          `/admin/envios/envios/${envioId}/foto/${asset}`, { responseType: 'blob' });
        if (!vigente) return;
        url = URL.createObjectURL(res.data);
        setEstado({ url, tipo: res.data.type || '' });
      } catch (err) {
        if (!vigente) return;
        setEstado({ codigo: err?.response?.status || 503 });
      }
    })();
    return () => {
      vigente = false;
      // Sin esto, cada fila que se abre y se cierra deja un blob en memoria, y
      // el operador abre decenas por día sin recargar la página.
      if (url) URL.revokeObjectURL(url);
    };
  }, [envioId, asset]);

  if (!asset) {
    return (
      <Aviso tono="alerta" titulo="No hay foto del comprobante">
        Sin la foto no hay nada que verificar: el peso lo mediría quien lo tipea.
      </Aviso>
    );
  }

  const esPdf = (estado.tipo || '').includes('pdf');
  return (
    <div>
      {estado.cargando ? (
        <Cargando texto="Trayendo el comprobante…" />
      ) : estado.codigo ? (
        <Aviso tono={estado.codigo === 503 ? 'alerta' : 'error'}
          titulo={estado.codigo === 404 ? 'No encontramos el comprobante'
            : estado.codigo === 503 ? 'No se pudo traer el comprobante'
              : 'El comprobante no se puede recuperar'}>
          {estado.codigo === 503
            ? 'Probá de nuevo en un minuto. Mientras tanto no tipees un peso a ciegas.'
            : estado.codigo === 404
              ? 'La ficha del envío dice que hay uno, pero no está. Avisale a soporte con el número del envío.'
              : 'Está registrado pero lo que hay guardado no coincide con lo que se subió. No verifiques un peso sin verlo: avisale a soporte con el número del envío.'}
        </Aviso>
      ) : esPdf ? (
        <div>
          <embed src={estado.url} type="application/pdf"
            style={{ width: '100%', height: '380px', borderRadius: '12px',
              border: `1px solid ${COLOR.borde}` }} />
          <a href={estado.url} target="_blank" rel="noreferrer"
            style={{ fontSize: '13px', color: COLOR.primarioOscuro }}>
            Abrir el PDF en otra pestaña
          </a>
        </div>
      ) : (
        <a href={estado.url} target="_blank" rel="noreferrer">
          <img src={estado.url} alt="Comprobante de despacho"
            style={{ maxWidth: '100%', maxHeight: '380px', borderRadius: '12px',
              border: `1px solid ${COLOR.borde}`, display: 'block' }} />
        </a>
      )}
      {envio.foto_repetida_en ? (
        <Aviso tono="error" titulo="Esta misma foto ya está en otro envío"
          style={{ marginTop: '10px' }}>
          Está también en <strong>{envio.foto_repetida_en}</strong>. Puede ser un reintento
          legítimo del mismo usuario, o el mismo despacho cargado dos veces para que uno de
          los dos no se cobre. <strong>Miralo antes de verificar.</strong>
        </Aviso>
      ) : null}
    </div>
  );
}

function Medidas({ valores, onCambio, deshabilitado }) {
  return (
    <div style={grilla('140px')}>
      {MEDIDAS.map(([k, e]) => {
        const problema = valores[k] === '' ? null : problemaDeMedida(valores[k]);
        return (
          <Campo key={k} etiqueta={e} error={problema}>
            <Texto value={valores[k]} disabled={deshabilitado}
              inputMode="decimal" invalido={!!problemaDeMedida(valores[k])}
              onChange={(ev) => onCambio({ ...valores, [k]: ev.target.value })} />
          </Campo>
        );
      })}
    </div>
  );
}

function Verificar({ envio, medidas, onMedidas, onListo }) {
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState(null);
  const completo = medidasCompletas(medidas);
  const setMedidas = onMedidas;

  const verificar = async () => {
    setEnviando(true);
    try {
      const res = await api.post(
        `/admin/envios/envios/${envio.envio_id}/comprobante/verificar`,
        { ...medidas, idempotency_key: claveDe('verificar', envio.envio_id) });
      olvidarClave('verificar', envio.envio_id);
      setResultado(res.data);
      onListo({ envio, tipo: 'verificado', datos: res.data });
    } catch (err) {
      // La clave NO se olvida: si esto fue un timeout, el reintento tiene que
      // llevar la misma para que el backend no cobre dos veces.
      toast.error(mensajeDeError(err, 'No se pudo verificar.'));
    } finally {
      setEnviando(false);
    }
  };

  if (envio.comprobante_verificado) {
    return (
      <Aviso tono="ok" titulo="Ya está verificado">
        El cobro inicial ya se emitió. Marcalo disponible cuando llegue al mostrador.
      </Aviso>
    );
  }

  return (
    <div>
      <h4 style={titulo}><Camera size={16} /> Lo que dice la foto</h4>
      <p style={bajada}>
        Escribí lo que <strong>leés en el comprobante</strong>, no lo que declaró el usuario:
        de acá sale el cobro inicial, y la medición la hizo el transportista de origen.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '18px' }}>
        <Comprobante envio={envio} />
        <div>
          <Medidas valores={medidas} onCambio={setMedidas} deshabilitado={enviando} />
          <Aviso tono="alerta" style={{ marginTop: '14px' }}>
            Esto <strong>emite el cobro inicial</strong>. Si el usuario no tiene saldo, la
            partida queda pendiente y el envío sigue igual: el paquete ya está viajando y no
            depende de nosotros.
          </Aviso>
          <Boton style={{ marginTop: '14px' }} onClick={verificar}
            cargando={enviando} disabled={!completo}>
            <CheckCircle2 size={14} /> Verificar y emitir el cobro
          </Boton>
        </div>
      </div>
      {resultado ? (
        // Los nombres salen de `_cobro_de`: `cobro.monto_ris` y `cobro.estado`.
        // Leyendo `cobrado_ahora_ris` —que no existe— el operador veía «Cobro
        // emitido — RIS», y el caso «quedó pendiente», que es el que el aviso de
        // arriba se toma el trabajo de explicar, no se anunciaba nunca.
        <Aviso style={{ marginTop: '14px' }}
          tono={resultado.cobro?.estado === 'pagado' ? 'ok' : 'alerta'}
          titulo={resultado.cobro?.estado === 'pagado'
            ? 'Cobrado' : 'Cobro emitido, y quedó pendiente'}>
          {num(resultado.cobro?.monto_ris)} RIS.
          {resultado.cobro?.estado === 'pagado'
            ? ''
            : ' El usuario no tenía saldo. El paquete sigue viajando igual: la deuda '
              + 'recién frena algo cuando quiera salir de Pacaraima.'}
          {resultado.corregido
            ? ' (Se emitió ahora: había quedado verificado sin cobrar.)' : ''}
        </Aviso>
      ) : null}
    </div>
  );
}

function Repesar({ envio, medidas, onMedidas, onListo }) {
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState(null);
  const completo = medidasCompletas(medidas);
  const setMedidas = onMedidas;

  const repesar = async () => {
    setEnviando(true);
    try {
      const res = await api.post(`/admin/envios/envios/${envio.envio_id}/repesar`,
        { ...medidas, idempotency_key: claveDe('repesar', envio.envio_id) });
      olvidarClave('repesar', envio.envio_id);
      setResultado(res.data);
      // El resultado sube al panel: al refrescar, un envío repesado sale de esta
      // parada y la fila se desmonta — llevándose el cartel que dice si el
      // paquete puede subir a la camioneta, que es el dato más caro del día.
      onListo({ envio, tipo: 'repesado', datos: res.data });
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo repesar.'));
    } finally {
      setEnviando(false);
    }
  };

  const rama = resultado?.rama;
  return (
    <div>
      <h4 style={titulo}><Scale size={16} /> Repesaje con balanza propia</h4>
      <p style={bajada}>
        Acá se cierra el precio: hasta ahora era un estimado sobre lo que declaró el usuario.
        Hay tres resultados posibles y ninguno es un error —
        <strong> cobrar</strong> la diferencia, <strong>devolverla</strong>, o
        <strong> no tocar nada</strong> si no llega a la tolerancia configurada.
      </p>
      <Medidas valores={medidas} onCambio={setMedidas} deshabilitado={enviando} />
      <Boton style={{ marginTop: '14px' }} onClick={repesar}
        cargando={enviando} disabled={!completo}>
        <Scale size={14} /> Repesar y cerrar el precio
      </Boton>

      {resultado ? (
        <Aviso style={{ marginTop: '14px' }}
          tono={resultado.puede_salir ? 'ok' : 'alerta'}
          titulo={rama === 'cobrar' ? 'Se cobró la diferencia'
            : rama === 'devolver' ? 'Se devolvió la diferencia'
              : 'Sin ajuste: la diferencia no llegó a la tolerancia'}>
          Total final: <strong>{num(resultado.total_final_ris)} RIS</strong>
          {resultado.diferencia_ris && rama !== 'sin_ajuste'
            ? <> · diferencia {num(resultado.diferencia_ris)} RIS</> : null}.
          {resultado.puede_salir
            ? ' El paquete puede salir de Pacaraima.'
            : ' Quedó una partida impaga: el paquete NO sale hasta que se pague.'}
        </Aviso>
      ) : null}
    </div>
  );
}

function Despachar({ envio, onListo }) {
  const [enviando, setEnviando] = useState(false);
  const [imprimiendo, setImprimiendo] = useState(false);
  const bloqueado = !envio.puede_salir;

  // El ticket se pide al servidor y no se arma con lo que ya tiene la cola: la
  // dirección de la agencia no está congelada en el envío y hay que ir a
  // buscarla VIVA. Ver el comentario de `ticket()` en envios_operacion.py.
  const imprimir = async () => {
    setImprimiendo(true);
    try {
      const res = await api.get(`/admin/envios/envios/${envio.envio_id}/ticket`);
      if (!imprimirTicket(res.data)) {
        toast.error('El navegador bloqueó la ventana. Permití las ventanas '
          + 'emergentes de este sitio y volvé a intentar.');
      }
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo armar el ticket.'));
    } finally {
      setImprimiendo(false);
    }
  };

  const despachar = async () => {
    setEnviando(true);
    try {
      await api.post(`/admin/envios/envios/${envio.envio_id}/despachar`);
      toast.success('Despachado a Santa Elena');
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo despachar.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div>
      <h4 style={titulo}><Truck size={16} /> Salida hacia Santa Elena</h4>
      {bloqueado ? (
        <Aviso tono="alerta" titulo="Este paquete no puede salir">
          Tiene {envio.partidas_impagas?.length || 0} partida(s) impaga(s):{' '}
          {(envio.partidas_impagas || []).join(', ')}. No es un error del sistema — es la
          regla: <strong>el paquete no sale de Pacaraima con una partida impaga</strong>, y es
          la única palanca de cobro real que tiene el negocio.
          {' '}<strong>Si el usuario te muestra que ya pagó, actualizá la cola</strong>: pagar
          no cambia el estado del envío, así que esta pantalla no se entera sola.
        </Aviso>
      ) : (
        <p style={bajada}>Todo pago y el precio cerrado. Puede cargarse en la camioneta.</p>
      )}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <Boton onClick={despachar} cargando={enviando} disabled={bloqueado}>
          <Truck size={14} /> Despachar
        </Boton>
        {/*
          El ticket se puede imprimir aunque la caja esté trabada: el papel se
          prepara antes de cargar la camioneta, y si hay una partida impaga sale
          con la banda «NO DESPACHAR» arriba. Deshabilitarlo acá solo lograría
          que alguien rotule a mano.
        */}
        <Boton variante="secundario" onClick={imprimir} cargando={imprimiendo}>
          <Printer size={14} /> Imprimir ticket
        </Boton>
      </div>
      <p style={{ ...bajada, marginTop: '10px', marginBottom: 0 }}>
        El ticket va pegado sobre la caja: dice a quién se le entrega, en qué agencia
        y <strong>si hay que cobrarle el flete o no</strong>. Es lo único que mira quien
        la recibe en el mostrador de destino.
      </p>
    </div>
  );
}

function Entregar({ envio, onListo }) {
  const [guia, setGuia] = useState('');
  const [foto, setFoto] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const MAX = 8 * 1024 * 1024;
  const fotoGrande = foto && foto.size > MAX;

  // El candado del flete, ANTES del formulario y no despues de apretar.
  // `puede_entregar` viene calculado del servidor, igual que `puede_salir` en
  // Despachar: es el mismo dato que la transicion va a mirar, y no una segunda
  // version de la regla escrita en el frontend que se despega con el tiempo.
  const fleteTrabado = envio.puede_entregar === false;

  const entregar = async () => {
    setEnviando(true);
    const cuerpo = new FormData();
    cuerpo.append('guia', guia);
    if (foto) cuerpo.append('foto', foto);
    try {
      await api.post(`/admin/envios/envios/${envio.envio_id}/entregar`, cuerpo,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Entregado');
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo registrar la entrega.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div>
      <h4 style={titulo}><PackageCheck size={16} /> Entrega en la oficina del transportista</h4>
      <p style={bajada}>
        Acá termina el servicio de RIS App. La guía es obligatoria: sin ella, la única prueba
        de la entrega es la palabra del operador.
      </p>
      {fleteTrabado ? (
        <Aviso tono="alerta" titulo="Falta acreditar el flete del tramo final">
          Este envío es <strong>prepago</strong>: el usuario le manda la remesa al
          transportista de destino, y el paquete no se entrega hasta que esa remesa esté
          acreditada. No es un error del sistema — es la regla, y es lo único que evita
          soltar el paquete contra una remesa que nadie vio llegar.
          {' '}<strong>Abrí «El flete del tramo final», acá abajo</strong>: registrá el monto
          que pidió el transportista y, cuando veas la remesa, marcala como recibida. Ahí se
          habilita este botón.
        </Aviso>
      ) : null}
      <div style={grilla('220px')}>
        <Campo etiqueta="Número de guía"
          ayuda="El que emite el transportista de destino. Al menos cuatro caracteres."
          error={guia.trim() && guia.trim().length < 4 ? 'Muy corta.' : null}>
          <Texto value={guia} onChange={(e) => setGuia(e.target.value)}
            invalido={guia.trim().length < 4} />
        </Campo>
        <Campo etiqueta="Foto (opcional)"
          ayuda="El remito o la caja en el mostrador. Hasta 8 MB."
          error={fotoGrande
            ? `Pesa ${Math.round(foto.size / 1048576)} MB y el máximo son 8. Sacala de nuevo con menos resolución, o entregá sin foto — la guía es lo obligatorio.`
            : null}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input type="file" accept="image/*,application/pdf"
              onChange={(e) => setFoto(e.target.files?.[0] || null)}
              style={{ fontSize: '13px' }} />
            {foto ? (
              <button type="button" onClick={() => setFoto(null)}
                style={{ border: 'none', background: 'none', cursor: 'pointer',
                  fontSize: '12px', color: COLOR.primarioOscuro }}>
                quitar
              </button>
            ) : null}
          </div>
        </Campo>
      </div>
      <Boton style={{ marginTop: '14px' }} onClick={entregar}
        cargando={enviando}
        disabled={fleteTrabado || guia.trim().length < 4 || fotoGrande}>
        <PackageCheck size={14} /> Registrar la entrega
      </Boton>
    </div>
  );
}

function Flete({ envio, onListo }) {
  const [abierto, setAbierto] = useState(false);
  const [monto, setMonto] = useState('');
  const [referencia, setReferencia] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const llamar = async (fn, mensaje) => {
    setEnviando(true);
    try {
      await fn();
      toast.success(mensaje);
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo registrar.'));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ paddingTop: '14px', borderTop: `1px solid ${COLOR.borde}` }}>
      {!abierto ? (
        <Boton variante="secundario" onClick={() => setAbierto(true)}>
          <Send size={14} /> El flete del tramo final
        </Boton>
      ) : (
        <div>
          <h4 style={titulo}><Send size={16} /> El flete del tramo final</h4>
          <p style={bajada}>
            Lo que el transportista de destino pide por llevar el paquete hasta el domicilio.
            <strong> No es un cobro de RIS App</strong>: es el número que el usuario tiene que
            mandar como remesa, y hasta que el operador está en el mostrador no existe —
            nadie puede cotizarlo antes.
          </p>
          <div style={grilla('200px')}>
            {/* El error SE MUESTRA. Un botón deshabilitado sin un cartel al
                lado es indistinguible de un botón roto. */}
            <Campo etiqueta="Monto que pidió el transportista"
              ayuda="En RIS. Es lo que el usuario tiene que mandar como remesa."
              error={monto.trim() ? problemaDeMonto(monto) : null}>
              <Texto value={monto} onChange={(e) => setMonto(e.target.value)}
                inputMode="decimal" invalido={!!problemaDeMonto(monto)} />
            </Campo>
            <Campo etiqueta="Referencia de la remesa"
              ayuda="Al acreditar: la remesa se ejecuta fuera de este módulo y nadie de acá puede verla llegar.">
              <Texto value={referencia} onChange={(e) => setReferencia(e.target.value)} />
            </Campo>
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '14px', flexWrap: 'wrap' }}>
            <Boton variante="secundario" cargando={enviando}
              disabled={!!problemaDeMonto(monto)}
              onClick={() => llamar(
                () => api.put(`/admin/envios/envios/${envio.envio_id}/flete`,
                  { monto_ris: monto }), 'Flete registrado')}>
              Registrar el monto
            </Boton>
            <Boton variante="secundario" onClick={() => setAbierto(false)}>Cerrar</Boton>
          </div>

          {/*
            Acreditar SUELTA el paquete en modalidad prepago, contra una remesa
            que nadie de este lado puede ver llegar, y no hay ruta para
            des-acreditar. Merece la misma fricción que un desvío: la referencia
            —el único rastro que va a quedar— y una confirmación explícita. Antes
            era un botón secundario del mismo tamaño que «registrar el monto», y
            pegado al lado.
          */}
          <div style={{ marginTop: '18px', paddingTop: '14px',
            borderTop: `1px solid ${COLOR.borde}`, }}>
            <div style={{ marginBottom: '12px' }}>
              <Interruptor activo={confirmado} onChange={setConfirmado}
                etiqueta="Vi la remesa acreditada, y entiendo que esto no se puede deshacer"
                ayuda="La remesa se ejecuta fuera de este módulo: acá nadie la puede verificar." />
            </div>
            {/* Mismo criterio que el monto: si el botón está gris, que el
                cartel diga por qué. */}
            {(!confirmado || !referencia.trim()) ? (
              <p style={{ margin: '0 0 10px 0', fontSize: '12px', color: COLOR.suave }}>
                Para poder marcarla: {!referencia.trim() ? 'cargá la referencia de la remesa'
                  : ''}{(!referencia.trim() && !confirmado) ? ' y ' : ''}
                {!confirmado ? 'tildá la confirmación de arriba' : ''}.
              </p>
            ) : null}
            <Boton variante="peligro" cargando={enviando}
              disabled={!confirmado || !referencia.trim()}
              onClick={() => llamar(
                () => api.post(`/admin/envios/envios/${envio.envio_id}/flete/acreditar`,
                  { referencia }), 'Flete acreditado')}>
              Marcar la remesa como recibida
            </Boton>
          </div>
        </div>
      )}
    </div>
  );
}

function Desviar({ envio, estado, onListo }) {
  const [abierto, setAbierto] = useState(false);
  const [hacia, setHacia] = useState(null);
  const [motivo, setMotivo] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const desviar = async () => {
    setEnviando(true);
    try {
      await api.post(`/admin/envios/envios/${envio.envio_id}/desviar/${hacia}`, { motivo });
      toast.success('Registrado');
      setAbierto(false);
      setHacia(null);
      setMotivo('');
      setConfirmado(false);
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo registrar.'));
    } finally {
      setEnviando(false);
    }
  };

  const elegido = DESVIOS.find((d) => d.hacia === hacia);
  // Solo los que la máquina de estados acepta desde acá. Ofrecer los cuatro
  // siempre hacía completar un formulario de confirmación irreversible para
  // terminar en un 400.
  const legales = DESVIOS_LEGALES[estado] || DESVIOS.map((d) => d.hacia);
  const opciones = DESVIOS.filter((d) => legales.includes(d.hacia));

  return (
    <div style={{ paddingTop: '14px', borderTop: `1px solid ${COLOR.borde}` }}>
      {!abierto ? (
        <Boton variante="peligro" onClick={() => setAbierto(true)}>
          <AlertTriangle size={14} /> Sacarlo del circuito
        </Boton>
      ) : (
        <div>
          <h4 style={titulo}><AlertTriangle size={16} /> Las cuatro salidas</h4>
          <p style={bajada}>
            Ninguna se puede deshacer, y todas abren consecuencias. El motivo no es
            burocracia: dentro de seis meses es lo único que va a explicar por qué este
            paquete terminó así.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {opciones.map((d) => (
              <label key={d.hacia} style={{ display: 'flex', gap: '10px', cursor: 'pointer',
                padding: '10px 12px', borderRadius: '10px',
                border: `1px solid ${hacia === d.hacia ? COLOR.error : COLOR.borde}`,
                backgroundColor: hacia === d.hacia ? COLOR.errorSuave : '#fff' }}>
                <input type="radio" name={`desvio-${envio.envio_id}`} checked={hacia === d.hacia}
                  onChange={() => { setHacia(d.hacia); setConfirmado(false); }}
                  style={{ marginTop: '2px', accentColor: COLOR.error }} />
                <span>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: COLOR.texto }}>
                    {d.etiqueta}
                  </span>
                  <span style={{ display: 'block', fontSize: '12px', color: COLOR.suave,
                    lineHeight: 1.4 }}>{d.ayuda}</span>
                </span>
              </label>
            ))}
          </div>
          {hacia ? (
            <div style={{ marginTop: '14px' }}>
              <Campo etiqueta="Qué pasó"
                ayuda="Al menos diez caracteres. Lo va a leer alguien que no estuvo acá.">
                <Area value={motivo} filas={3} maxLength={500}
                  onChange={(e) => setMotivo(e.target.value)} />
              </Campo>
              <div style={{ marginTop: '12px' }}>
                <Interruptor activo={confirmado} onChange={setConfirmado}
                  etiqueta={`Entiendo que «${elegido?.etiqueta}» no se puede deshacer`} />
              </div>
            </div>
          ) : null}
          <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
            <Boton variante="peligro" cargando={enviando}
              disabled={!hacia || motivo.trim().length < 10 || !confirmado}
              onClick={desviar}>
              Registrar
            </Boton>
            <Boton variante="secundario" onClick={() => setAbierto(false)}>Cancelar</Boton>
          </div>
        </div>
      )}
    </div>
  );
}
