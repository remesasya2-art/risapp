/**
 * PuntoOrigen.jsx — La agencia de Pacaraima y la etiqueta que el usuario copia.
 *
 * LA VISTA PREVIA NO ES UN ADORNO
 *   `plantilla_direccion` se edita a ciegas si no se ve el resultado. Una
 *   plantilla mal armada no se descubre en el panel: se descubre cuando una caja
 *   llega a una agencia que no la esperaba. La vista previa la renderiza el
 *   BACKEND, con la misma función que usa la cotización — no una imitación de
 *   acá, que se separaría del original en el primer cambio.
 *
 * LOS TOKENS SE VALIDAN AL GUARDAR
 *   `{Razon_Social}` con mayúscula, o `{ retirador_nombre }` con espacios, no
 *   matchean: quedan literales y terminan impresos en la etiqueta. El backend los
 *   rechaza; acá se listan los que existen para que nadie tenga que adivinar.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, MapPin, RefreshCw, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { Area, Aviso, Boton, Campo, Cargando, NoSePudoLeer, Seleccion, Texto } from './ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from './estilos';

const TOKENS = ['razon_social', 'retirador_nombre', 'linea_agencia', 'agencia',
  'caixa_postal', 'direccion', 'ciudad', 'uf', 'cep'];

const PLANTILLA_POR_DEFECTO = '{razon_social}\nA/C {retirador_nombre}\n{linea_agencia}\n{ciudad} - {uf}\nCEP {cep}';


/**
 * El bloque de configuración, sin los metadatos del guardado.
 *
 * `GET /config/{bloque}` devuelve el documento crudo de Mongo, con `setting_id`,
 * `actualizado_por` y `actualizado_at` adentro. Los modelos son `extra="forbid"`,
 * así que reenviar lo que se leyó devuelve 400 — y el efecto es que cada bloque
 * se puede guardar UNA sola vez: corregir un CEP mal tipeado después ya no se
 * puede desde la pantalla, y el mensaje manda a alguien a editar Mongo a mano,
 * que es justo lo que el panel existe para evitar.
 */
const METADATOS = ['setting_id', 'actualizado_por', 'actualizado_at', '_id'];
const sinMetadatos = (o) => Object.fromEntries(
  Object.entries(o || {}).filter(([k]) => !METADATOS.includes(k)));

const VACIO = {
  nombre: '', cep: '', ciudad: 'Pacaraima', uf: 'RR', modalidad: 'caixa_postal',
  caixa_postal: '', direccion: '', razon_social: '',
  plantilla_direccion: PLANTILLA_POR_DEFECTO,
};

const MODALIDADES = [
  { valor: 'caixa_postal', texto: 'Caixa Postal' },
  { valor: 'posta_restante', texto: 'Posta Restante' },
  { valor: 'otro', texto: 'Otro' },
];

export default function PuntoOrigen() {
  const [datos, setDatos] = useState(VACIO);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [previa, setPrevia] = useState(null);
  const [errores, setErrores] = useState(null);
  const [noSeLeyo, setNoSeLeyo] = useState(null);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargarPrevia = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/retiro');
      if (!vivo.current) return;
      setPrevia(res.data?.vista_previa || null);
    } catch {
      setPrevia(null);   // la previa es un extra: no puede romper la pantalla
    }
  }, []);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/config/punto_origen');
      if (!vivo.current) return;
      const v = res.data || {};
      setNoSeLeyo(null);
      setDatos({
        ...VACIO, ...sinMetadatos(v),
        caixa_postal: v.caixa_postal || '',
        direccion: v.direccion || '',
        plantilla_direccion: v.plantilla_direccion || PLANTILLA_POR_DEFECTO,
        // Se conserva tal cual vino: el turno se designa en la nómina, que
        // además verifica que la persona siga vigente. Pero `PUT /config` NO
        // fusiona —hace $set del modelo entero— así que omitirlo acá lo escribe
        // en null y deja las cotizaciones nuevas rotulando a quien caiga.
        retirador_activo_id: v.retirador_activo_id ?? null,
      });
    } catch (err) {
      if (!vivo.current) return;
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudo leer el punto de origen.'));
      }
    } finally {
      if (vivo.current) setCargando(false);
    }
    cargarPrevia();
  }, [cargarPrevia]);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const cambiar = (campo) => (e) => {
    const valor = e?.target ? e.target.value : e;
    setDatos((d) => ({ ...d, [campo]: valor }));
  };

  const guardar = async () => {
    setGuardando(true);
    setErrores(null);
    try {
      // `retirador_activo_id` VIAJA, tal como se leyó. `PUT /config/{bloque}` no
      // fusiona: valida con el modelo y hace $set del dump completo, y el campo
      // tiene default None. Omitirlo lo escribía en null, y a partir de ahí las
      // cotizaciones nuevas se rotulaban con la primera persona vigente de la
      // nómina en vez de con la designada — sin un solo error en ningún lado, y
      // con la etiqueta sin coincidir con el documento en el mostrador.
      const res = await api.put('/admin/envios/config/punto_origen', {
        ...sinMetadatos(datos),
        caixa_postal: datos.caixa_postal || null,
        direccion: datos.direccion || null,
      });
      // Se muestra el valor EFECTIVO que devolvió el servidor, no lo que se
      // tipeó: así se ve lo que quedó guardado, con sus normalizaciones (el CEP
      // sin guion, los espacios recortados) y no lo que uno cree que guardó.
      const valor = res.data?.valor || {};
      setDatos((d) => ({ ...d, ...sinMetadatos(valor) }));
      toast.success('Punto de origen guardado');
      cargarPrevia();
    } catch (err) {
      setErrores(mensajeDeError(err, 'No se pudo guardar.'));
    } finally {
      setGuardando(false);
    }
  };

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(previa?.texto_copiable || '');
      toast.success('Copiado');
    } catch {
      toast.error('El navegador no dejó copiar. Seleccionalo a mano.');
    }
  };

  if (cargando) return <Cargando texto="Leyendo el punto de origen…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="el punto de origen" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  const usaCaixa = datos.modalidad === 'caixa_postal';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={titulo}><MapPin size={16} /> La agencia de Pacaraima</h3>
        <p style={bajada}>
          Es la dirección a la que el usuario despacha desde Brasil. Todo lo de acá abajo
          termina impreso en una etiqueta que alguien pega sobre una caja, y comparado
          contra un documento en un mostrador.
        </p>
        <div style={grilla()}>
          <Campo etiqueta="Razón social" ayuda="A nombre de quién se recibe. Va primero en la etiqueta.">
            <Texto value={datos.razon_social} onChange={cambiar('razon_social')}
              placeholder="RIS App LTDA" maxLength={120} />
          </Campo>
          <Campo etiqueta="Nombre de la agencia" ayuda="Como la conoce el mostrador.">
            <Texto value={datos.nombre} onChange={cambiar('nombre')}
              placeholder="Agencia Centro" maxLength={120} />
          </Campo>
          <Campo etiqueta="CEP" ayuda="Ocho dígitos. Se guarda sin guion y se imprime con guion.">
            <Texto value={datos.cep} onChange={cambiar('cep')} placeholder="69355000" maxLength={9} />
          </Campo>
          <Campo etiqueta="Ciudad">
            <Texto value={datos.ciudad} onChange={cambiar('ciudad')} maxLength={60} />
          </Campo>
          <Campo etiqueta="UF">
            <Texto value={datos.uf} onChange={cambiar('uf')} maxLength={2} />
          </Campo>
          <Campo etiqueta="Modalidad" ayuda="Cómo se retira en esa agencia.">
            <Seleccion value={datos.modalidad} onChange={cambiar('modalidad')}
              opciones={MODALIDADES} />
          </Campo>
          <Campo etiqueta={usaCaixa ? 'Caixa Postal' : 'Caixa Postal (no aplica)'}
            ayuda={usaCaixa ? 'El número de la casilla.' : 'Solo se usa con modalidad Caixa Postal.'}>
            <Texto value={datos.caixa_postal} onChange={cambiar('caixa_postal')}
              maxLength={20} disabled={!usaCaixa} />
          </Campo>
          <Campo etiqueta="Dirección de calle" ayuda="Opcional. Se usa cuando no hay Caixa Postal.">
            <Texto value={datos.direccion} onChange={cambiar('direccion')} maxLength={200} />
          </Campo>
        </div>
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}>La plantilla de la etiqueta</h3>
        <p style={bajada}>
          Los datos entre llaves se reemplazan al cotizar. Escribilos exactamente como están
          en la lista: <code>{'{Razon_Social}'}</code> con mayúscula o <code>{'{ cep }'}</code> con
          espacios no se reemplazan — quedan literales sobre la caja.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '14px' }}>
          {TOKENS.map((t) => (
            <button key={t} type="button"
              onClick={() => setDatos((d) => ({
                ...d, plantilla_direccion: `${d.plantilla_direccion}{${t}}`,
              }))}
              style={{ fontSize: '12px', fontFamily: 'monospace', padding: '4px 10px',
                borderRadius: '999px', border: `1px solid ${COLOR.borde}`,
                backgroundColor: '#f9fafb', color: COLOR.primarioOscuro, cursor: 'pointer' }}>
              {'{'}{t}{'}'}
            </button>
          ))}
        </div>
        <Area value={datos.plantilla_direccion} onChange={cambiar('plantilla_direccion')}
          filas={6} style={{ fontFamily: 'monospace', fontSize: '13px' }} maxLength={1000} />
        <Boton variante="secundario" style={{ marginTop: '10px' }}
          onClick={() => setDatos((d) => ({ ...d, plantilla_direccion: PLANTILLA_POR_DEFECTO }))}>
          <RefreshCw size={14} /> Volver a la plantilla por defecto
        </Boton>
      </div>

      {errores ? <Aviso tono="error" titulo="No se guardó">{errores}</Aviso> : null}

      <div style={{ display: 'flex', gap: '10px' }}>
        <Boton onClick={guardar} cargando={guardando}><Save size={14} /> Guardar</Boton>
        <Boton variante="secundario" onClick={cargar}>Descartar cambios</Boton>
      </div>

      <div style={{ ...tarjeta, backgroundColor: '#0f172a', borderColor: '#0f172a' }}>
        <h3 style={{ ...titulo, color: '#fff' }}>Lo que va a ver el usuario</h3>
        <p style={{ ...bajada, color: '#94a3b8' }}>
          Renderizado por el servidor, con la misma función que usa la cotización. Si acá se ve
          mal, se ve mal sobre la caja.
        </p>
        {previa?.disponible ? (
          <>
            <pre style={{ margin: 0, padding: '16px', borderRadius: '12px',
              backgroundColor: '#1e293b', color: '#e2e8f0', fontSize: '14px', lineHeight: 1.7,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
              {previa.texto_copiable}
            </pre>
            <Boton variante="secundario" style={{ marginTop: '12px' }} onClick={copiar}>
              <Copy size={14} /> Copiar
            </Boton>
          </>
        ) : (
          <Aviso tono="alerta" titulo="Todavía no se puede armar la etiqueta">
            {(previa?.faltantes || ['Guardá el punto de origen para verla.']).join(' ')}
          </Aviso>
        )}
      </div>
    </div>
  );
}
