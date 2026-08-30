/**
 * Transportistas.jsx — Las empresas de transporte, sus agencias y su cuenta.
 *
 * NINGUN NOMBRE DE EMPRESA VIVE EN EL CODIGO
 *   Se cargan acá y el sistema los referencia por su CÓDIGO alfanumérico. Por eso
 *   el código no se puede editar después: los envíos viejos, los logs y la
 *   auditoría lo referencian, y renombrarlo rompe la trazabilidad hacia atrás sin
 *   avisar a nadie.
 *
 * LOS DOS TRAMOS NO LOS COBRA RIS APP
 *   Estos transportistas los contrata y los paga el usuario. Lo que se carga acá
 *   —reglas de cubaje, límites— sirve para MOSTRARLE una orientación y para saber
 *   qué paquete no entra. Ninguna de estas cifras entra en ningún total.
 *
 * LA CUENTA BANCARIA ES EL CAMPO MAS SENSIBLE DEL PANEL
 *   Quien pueda editarla puede redirigir todos los fletes, y eso es plata que
 *   sale y no vuelve. Tiene su propio formulario, con el número tipeado dos veces
 *   —a mano, no pegado: un pegado repite el mismo error— y se versiona en vez de
 *   pisarse.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Building2, ChevronDown, ChevronRight, CreditCard, MapPin, Plus, Save, Upload,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { Area, Aviso, Boton, Campo, Cargando, Interruptor, NoSePudoLeer, Seleccion, Texto, Vacio } from '../../envios/ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from '../../envios/estilos';

const NUEVO = {
  codigo: '', nombre: '', rol: 'brasil', activo: true, orden: 1, moneda: '',
  regla_peso: { divisor: 5000, escalon_kg: '0.5', minimo_kg: '0', umbral_cubado_kg: '' },
  limites: {
    peso_max_kg: '', lado_max_cm: '', suma_lados_max_cm: '', largo_min_cm: '',
    ancho_min_cm: '', alto_min_cm: '', suma_lados_min_cm: '', valor_declarado_max: '',
  },
  plantilla_rastreo: '', fuente_referencia: '', notas: '',
};

const LIMITES = [
  ['peso_max_kg', 'Peso máximo (kg)'],
  ['lado_max_cm', 'Lado máximo (cm)'],
  ['suma_lados_max_cm', 'Suma de lados máx. (cm)'],
  ['largo_min_cm', 'Largo mínimo (cm)'],
  ['ancho_min_cm', 'Ancho mínimo (cm)'],
  ['alto_min_cm', 'Alto mínimo (cm)'],
  ['suma_lados_min_cm', 'Suma de lados mín. (cm)'],
  ['valor_declarado_max', 'Valor declarado máx.'],
];

/**
 * Los vacíos se mandan como null: `""` no es «sin límite», es un texto inválido.
 *
 * SOLO sobre los campos que el modelo declara Optional. `escalon_kg` y
 * `minimo_kg` son `str` con default, no opcionales: mandarlos en null devolvía
 * «Input should be a valid string» — y la ayuda del campo de al lado («Vacío = el
 * cubado se aplica siempre», que sí es opcional) invitaba justamente a vaciarlos.
 */
const nuloSiVacio = (o, opcionales) => Object.fromEntries(
  Object.entries(o)
    .filter(([k, v]) => opcionales.includes(k) || v !== '')
    .map(([k, v]) => [k, v === '' || v === undefined ? null : v]));

/** Los campos de `ReglaPeso` que aceptan null. Los otros tienen default. */
const REGLA_OPCIONAL = ['umbral_cubado_kg'];

export default function Transportistas() {
  const [lista, setLista] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [abierto, setAbierto] = useState(null);
  const [creando, setCreando] = useState(false);
  const [noSeLeyo, setNoSeLeyo] = useState(null);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/transportistas');
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setLista(res.data?.transportistas || []);
    } catch (err) {
      if (!vivo.current) return;
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudieron leer los transportistas.'));
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

  if (cargando) return <Cargando texto="Leyendo transportistas…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="los transportistas" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  const brasil = lista.filter((t) => t.rol === 'brasil');
  const venezuela = lista.filter((t) => t.rol === 'venezuela');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <Aviso tono="info" titulo="Hace falta uno de cada rol">
        El de <strong>Brasil</strong> lleva el paquete hasta Pacaraima; el de{' '}
        <strong>Venezuela</strong>, desde Santa Elena hasta el destino. Los dos los contrata y
        los paga el usuario: lo que cargues acá sirve para orientarlo y para saber qué paquete
        no entra, y no entra en ningún total que RIS App cobre.
      </Aviso>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '13px', color: COLOR.suave }}>
          Activos: <strong style={{ color: brasil.some((t) => t.activo) ? COLOR.ok : COLOR.error }}>
            {brasil.filter((t) => t.activo).length} en Brasil
          </strong>
          {' · '}
          <strong style={{ color: venezuela.some((t) => t.activo) ? COLOR.ok : COLOR.error }}>
            {venezuela.filter((t) => t.activo).length} en Venezuela
          </strong>
        </span>
        <Boton style={{ marginLeft: 'auto' }} onClick={() => setCreando((c) => !c)}>
          <Plus size={14} /> Nuevo transportista
        </Boton>
      </div>

      {creando ? (
        <Ficha nuevo transportista={NUEVO}
          onListo={() => { setCreando(false); cargar(); }}
          onCancelar={() => setCreando(false)} />
      ) : null}

      {lista.length === 0 && !creando ? (
        <Vacio titulo="Todavía no hay transportistas">
          Cargá al menos uno con rol Brasil y uno con rol Venezuela. Sin los dos, nadie puede
          cotizar.
        </Vacio>
      ) : null}

      {lista.map((t) => (
        <div key={t.transportista_id} style={{ ...tarjeta, padding: 0, overflow: 'hidden' }}>
          <button type="button"
            onClick={() => setAbierto((a) => (a === t.transportista_id ? null : t.transportista_id))}
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '12px',
              padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer',
              textAlign: 'left' }}>
            {abierto === t.transportista_id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <Building2 size={18} color={COLOR.suave} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: '14px', fontWeight: 700, color: COLOR.texto }}>
                {t.nombre}
              </span>
              <span style={{ display: 'block', fontSize: '12px', color: COLOR.suave,
                fontFamily: 'monospace' }}>
                {t.codigo} · {t.rol === 'brasil' ? 'Brasil → Pacaraima' : 'Santa Elena → destino'}
              </span>
            </span>
            <span style={{ fontSize: '11px', fontWeight: 700, padding: '4px 10px',
              borderRadius: '999px',
              backgroundColor: t.activo ? COLOR.okSuave : '#f3f4f6',
              color: t.activo ? '#065f46' : COLOR.suave }}>
              {t.activo ? 'activo' : 'inactivo'}
            </span>
          </button>
          {abierto === t.transportista_id ? (
            <div style={{ padding: '0 20px 20px 20px', borderTop: `1px solid ${COLOR.borde}` }}>
              <Ficha transportista={t} onListo={cargar} />
              {t.rol === 'venezuela' ? <Cuenta transportista={t} onListo={cargar} /> : null}
              <Agencias transportista={t} />
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function Ficha({ transportista, nuevo, onListo, onCancelar }) {
  const [datos, setDatos] = useState(() => ({
    ...NUEVO, ...transportista,
    moneda: transportista.moneda || '',
    plantilla_rastreo: transportista.plantilla_rastreo || '',
    fuente_referencia: transportista.fuente_referencia || '',
    notas: transportista.notas || '',
    regla_peso: { ...NUEVO.regla_peso, ...(transportista.regla_peso || {}),
      umbral_cubado_kg: transportista.regla_peso?.umbral_cubado_kg || '' },
    limites: { ...NUEVO.limites, ...(transportista.limites || {}) },
  }));
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    const cuerpo = {
      nombre: datos.nombre, rol: datos.rol, activo: datos.activo,
      orden: datos.orden === '' ? 1 : Number(datos.orden),
      moneda: datos.moneda || null,
      regla_peso: {
        ...nuloSiVacio(datos.regla_peso, REGLA_OPCIONAL),
        // Sin `|| 5000`: `Number('')` es 0 y `0 || 5000` es 5000, así que borrar
        // el campo para retipearlo y guardar grababa 5000 con un toast verde. El
        // divisor cambia el peso facturable de todo bulto grande y liviano, que
        // es justo lo que cada empresa cotiza distinto.
        divisor: datos.regla_peso.divisor === '' ? null : Number(datos.regla_peso.divisor),
      },
      limites: nuloSiVacio(datos.limites, Object.keys(NUEVO.limites)),
      plantilla_rastreo: datos.plantilla_rastreo || null,
      fuente_referencia: datos.fuente_referencia || null,
      notas: datos.notas || null,
    };
    try {
      if (nuevo) {
        await api.post('/admin/envios/transportistas', { ...cuerpo, codigo: datos.codigo });
        toast.success('Transportista creado');
      } else {
        // Sin `codigo` ni `cuenta_bancaria`: el backend los rechaza a propósito y
        // tiene razón — el código no cambia nunca y la cuenta tiene su propia
        // ruta, con confirmación tipeada.
        const res = await api.patch(
          `/admin/envios/transportistas/${transportista.transportista_id}`, cuerpo);
        // Se muestra lo que quedó, no lo que se tipeó: el servidor normaliza y
        // ver el valor efectivo es lo que evita creer que se guardó algo que no.
        if (res.data?.valor) setDatos((d) => ({ ...d, ...res.data.valor }));
        toast.success('Guardado');
      }
      onListo();
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo guardar.'));
    } finally {
      setGuardando(false);
    }
  };

  const campoLimite = (clave) => (e) => setDatos((d) => ({
    ...d, limites: { ...d.limites, [clave]: e.target.value },
  }));

  return (
    <div style={{ paddingTop: '18px' }}>
      <div style={grilla()}>
        {nuevo ? (
          <Campo etiqueta="Código"
            ayuda="Mayúsculas, números y guiones. NO se puede cambiar después: los envíos viejos lo referencian.">
            <Texto value={datos.codigo}
              onChange={(e) => setDatos((d) => ({ ...d, codigo: e.target.value.toUpperCase() }))}
              placeholder="TRP-7K2M" maxLength={20} />
          </Campo>
        ) : (
          <Campo etiqueta="Código" ayuda="No se edita nunca.">
            <Texto value={datos.codigo} disabled />
          </Campo>
        )}
        <Campo etiqueta="Nombre" ayuda="Como lo lee el usuario.">
          <Texto value={datos.nombre} onChange={(e) => setDatos((d) => ({ ...d, nombre: e.target.value }))}
            maxLength={80} />
        </Campo>
        <Campo etiqueta="Rol" ayuda={nuevo ? 'Brasil lleva hasta Pacaraima; Venezuela reparte desde Santa Elena.' : null}>
          <Seleccion value={datos.rol} onChange={(e) => setDatos((d) => ({ ...d, rol: e.target.value }))}
            opciones={[{ valor: 'brasil', texto: 'Brasil → Pacaraima' },
              { valor: 'venezuela', texto: 'Santa Elena → destino' }]} />
        </Campo>
        <Campo etiqueta="Moneda de sus tarifas" ayuda="Solo informativo. Ej: BRL, USD.">
          <Texto value={datos.moneda} onChange={(e) => setDatos((d) => ({ ...d, moneda: e.target.value }))}
            maxLength={8} />
        </Campo>
        <Campo etiqueta="Orden" ayuda="En qué orden se muestran.">
          <Texto type="number" min={0} max={999} value={datos.orden}
            onChange={(e) => setDatos((d) => ({ ...d, orden: e.target.value }))} />
        </Campo>
      </div>

      <div style={{ marginTop: '14px' }}>
        <Interruptor activo={datos.activo}
          onChange={(v) => setDatos((d) => ({ ...d, activo: v }))}
          etiqueta="Activo"
          ayuda="Desactivar no borra nada: los envíos viejos siguen apuntando a esta ficha. Sin ninguno activo del rol, nadie puede cotizar." />
      </div>

      <h4 style={{ ...titulo, marginTop: '22px' }}>Cómo cubica</h4>
      <p style={bajada}>
        No hay un divisor global: cada empresa cubica distinto, y usar el de una para la otra
        cambia el peso facturable de todos los paquetes grandes y livianos.
      </p>
      <div style={grilla('200px')}>
        <Campo etiqueta="Divisor volumétrico" ayuda="Largo × ancho × alto ÷ divisor.">
          <Texto type="number" min={1} value={datos.regla_peso.divisor}
            onChange={(e) => setDatos((d) => ({
              ...d, regla_peso: { ...d.regla_peso, divisor: e.target.value },
            }))} />
        </Campo>
        <Campo etiqueta="Escalón (kg)" ayuda="A cuánto se redondea hacia arriba.">
          <Texto value={datos.regla_peso.escalon_kg}
            onChange={(e) => setDatos((d) => ({
              ...d, regla_peso: { ...d.regla_peso, escalon_kg: e.target.value },
            }))} />
        </Campo>
        <Campo etiqueta="Mínimo facturable (kg)">
          <Texto value={datos.regla_peso.minimo_kg}
            onChange={(e) => setDatos((d) => ({
              ...d, regla_peso: { ...d.regla_peso, minimo_kg: e.target.value },
            }))} />
        </Campo>
        <Campo etiqueta="Umbral de cubado (kg)"
          ayuda="Vacío = el cubado se aplica siempre.">
          <Texto value={datos.regla_peso.umbral_cubado_kg}
            onChange={(e) => setDatos((d) => ({
              ...d, regla_peso: { ...d.regla_peso, umbral_cubado_kg: e.target.value },
            }))} />
        </Campo>
      </div>

      <h4 style={{ ...titulo, marginTop: '22px' }}>Qué acepta</h4>
      <p style={bajada}>
        Todo opcional. <strong>Lo que dejes vacío no restringe nada</strong>: inventar un techo
        que después nadie puede explicar es peor que no tenerlo.
      </p>
      <div style={grilla('180px')}>
        {LIMITES.map(([clave, etiqueta]) => (
          <Campo key={clave} etiqueta={etiqueta}>
            <Texto value={datos.limites[clave] ?? ''} onChange={campoLimite(clave)} />
          </Campo>
        ))}
      </div>

      <div style={{ ...grilla('260px'), marginTop: '22px' }}>
        <Campo etiqueta="Plantilla de rastreo"
          ayuda="La URL donde el usuario sigue el paquete. Usá {codigo} donde va el número.">
          <Texto value={datos.plantilla_rastreo}
            onChange={(e) => setDatos((d) => ({ ...d, plantilla_rastreo: e.target.value }))}
            maxLength={300} />
        </Campo>
        <Campo etiqueta="Fuente de la referencia"
          ayuda="De dónde salieron los precios orientativos que se muestran.">
          <Texto value={datos.fuente_referencia}
            onChange={(e) => setDatos((d) => ({ ...d, fuente_referencia: e.target.value }))}
            maxLength={300} />
        </Campo>
      </div>
      <div style={{ marginTop: '14px' }}>
        <Campo etiqueta="Notas internas" ayuda="No las ve el usuario.">
          <Area value={datos.notas} onChange={(e) => setDatos((d) => ({ ...d, notas: e.target.value }))}
            filas={3} maxLength={2000} />
        </Campo>
      </div>

      {error ? <Aviso tono="error" titulo="No se guardó" style={{ marginTop: '14px' }}>{error}</Aviso> : null}

      <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
        <Boton onClick={guardar} cargando={guardando}>
          <Save size={14} /> {nuevo ? 'Crear' : 'Guardar'}
        </Boton>
        {onCancelar ? <Boton variante="secundario" onClick={onCancelar}>Cancelar</Boton> : null}
      </div>
    </div>
  );
}

const TIPOS_CUENTA = [
  { valor: 'corriente', texto: 'Corriente' },
  { valor: 'ahorro', texto: 'Ahorro' },
  { valor: 'pago_movil', texto: 'Pago móvil' },
  { valor: 'otro', texto: 'Otro' },
];

function Cuenta({ transportista, onListo }) {
  const [abierto, setAbierto] = useState(false);
  const [cuenta, setCuenta] = useState({
    banco: '', tipo_cuenta: 'corriente', numero: '', titular: '', documento: '',
  });
  const [confirmacion, setConfirmacion] = useState('');
  const [motivo, setMotivo] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);
  const actual = transportista.cuenta_bancaria;

  // Al cerrar se borra TODO, no solo la confirmación. El número completo es lo
  // único que el resto del panel se cuida de no mostrar nunca; dejarlo en el
  // formulario para que reaparezca al reabrirlo lo contradice.
  const cerrar = () => {
    setAbierto(false);
    setError(null);
    setConfirmacion('');
    setMotivo('');
    setCuenta({ banco: '', tipo_cuenta: 'corriente', numero: '', titular: '', documento: '' });
  };

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const res = await api.put(
        `/admin/envios/transportistas/${transportista.transportista_id}/cuenta`,
        { cuenta, confirmacion_numero: confirmacion, motivo });
      toast.success(`Cuenta actualizada: ${res.data?.numero}`);
      cerrar();
      onListo();
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo cambiar la cuenta.'));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div style={{ marginTop: '26px', paddingTop: '18px', borderTop: `1px solid ${COLOR.borde}` }}>
      <h4 style={titulo}><CreditCard size={16} /> La cuenta que recibe los fletes</h4>
      <p style={bajada}>
        Es el campo más sensible del panel: quien lo edita puede redirigir todos los fletes, y
        eso es plata que sale y no vuelve. Se versiona en vez de pisarse, y{' '}
        <strong>no se congela dentro de cada envío</strong> — el transportista la puede cambiar
        sin avisar, y pagarle a una cuenta congelada es plata perdida.
      </p>
      {actual ? (
        <p style={{ fontSize: '14px', margin: '0 0 14px 0', color: COLOR.texto }}>
          Vigente: <strong>{actual.banco}</strong>{' '}
          <span style={{ fontFamily: 'monospace' }}>{actual.numero}</span>
        </p>
      ) : (
        <Aviso tono="alerta" style={{ marginBottom: '14px' }}>
          Sin cuenta cargada, un envío en modalidad prepago no tiene a dónde mandar el flete.
        </Aviso>
      )}

      {!abierto ? (
        <Boton variante="secundario" onClick={() => setAbierto(true)}>
          {actual ? 'Cambiar la cuenta' : 'Cargar la cuenta'}
        </Boton>
      ) : (
        <div style={{ padding: '16px', borderRadius: '12px', backgroundColor: COLOR.errorSuave,
          border: '1px solid #fecaca' }}>
          <div style={grilla('200px')}>
            <Campo etiqueta="Banco">
              <Texto value={cuenta.banco}
                onChange={(e) => setCuenta((c) => ({ ...c, banco: e.target.value }))} maxLength={80} />
            </Campo>
            <Campo etiqueta="Tipo">
              <Seleccion value={cuenta.tipo_cuenta} opciones={TIPOS_CUENTA}
                onChange={(e) => setCuenta((c) => ({ ...c, tipo_cuenta: e.target.value }))} />
            </Campo>
            <Campo etiqueta="Número" ayuda="Solo dígitos.">
              <Texto value={cuenta.numero}
                onChange={(e) => setCuenta((c) => ({ ...c, numero: e.target.value }))} maxLength={40} />
            </Campo>
            <Campo etiqueta="Titular">
              <Texto value={cuenta.titular}
                onChange={(e) => setCuenta((c) => ({ ...c, titular: e.target.value }))} maxLength={120} />
            </Campo>
            <Campo etiqueta="Documento del titular">
              <Texto value={cuenta.documento}
                onChange={(e) => setCuenta((c) => ({ ...c, documento: e.target.value }))} maxLength={30} />
            </Campo>
          </div>
          <div style={{ marginTop: '14px' }}>
            <Campo etiqueta="Escribí el número otra vez"
              ayuda="A mano, sin copiar y pegar: un pegado repite el mismo error, y esto existe para atrapar el dígito cambiado.">
              <Texto value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)}
                onPaste={(e) => {
                  e.preventDefault();
                  toast.error('Escribilo a mano: pegarlo repetiría el mismo error.');
                }} />
            </Campo>
          </div>
          <div style={{ marginTop: '14px' }}>
            <Campo etiqueta="Motivo" ayuda="Queda en la auditoría. Alguien lo va a leer en seis meses.">
              <Texto value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={200} />
            </Campo>
          </div>
          {error ? <Aviso tono="error" style={{ marginTop: '12px' }}>{error}</Aviso> : null}
          <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
            <Boton variante="peligro" onClick={guardar} cargando={guardando}>
              Cambiar la cuenta
            </Boton>
            <Boton variante="secundario" onClick={cerrar}>Cancelar</Boton>
          </div>
        </div>
      )}
    </div>
  );
}

const AGENCIA_NUEVA = {
  codigo: '', nombre: '', estado: '', ciudad: '', direccion: '', zona: '',
  codigo_postal: '', activa: true, es_punto_entrega: false,
};

function Agencias({ transportista }) {
  const [lista, setLista] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [nueva, setNueva] = useState(null);
  const [informe, setInforme] = useState(null);
  const [subiendo, setSubiendo] = useState(false);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const [editando, setEditando] = useState(null);
  const [guardandoFila, setGuardandoFila] = useState(false);
  const archivo = useRef(null);
  // Su propio corte: las agencias se leen al desplegar un transportista, y
  // plegarlo mientras la petición está en vuelo tiene que descartar la respuesta.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get(
        `/admin/envios/transportistas/${transportista.transportista_id}/agencias`);
      // El guard también acá: el comentario de arriba dice que plegar el
      // transportista tiene que descartar la respuesta, y cubrir solo
      // `setCargando` deja que la lista vieja se pinte igual.
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setLista(res.data?.agencias || []);
    } catch (err) {
      if (!vivo.current) return;
      // «Sin agencias» y «no se pudieron leer» mandan a lugares distintos: el
      // primero a importar un CSV, y ese CSV hace upsert por código — o sea que
      // reimportar el viejo pisa doscientas filas vivas.
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudieron leer las agencias.'));
      }
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, [transportista.transportista_id]);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const crear = async () => {
    try {
      await api.post(
        `/admin/envios/transportistas/${transportista.transportista_id}/agencias`,
        { ...nueva, direccion: nueva.direccion || null, zona: nueva.zona || null,
          codigo_postal: nueva.codigo_postal || null });
      toast.success('Agencia creada');
      setNueva(null);
      cargar();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo crear la agencia.'));
    }
  };

  const guardarFila = async (codigo, cambios) => {
    setGuardandoFila(true);
    try {
      await api.patch(
        `/admin/envios/transportistas/${transportista.transportista_id}/agencias/${encodeURIComponent(codigo)}`,
        cambios);
      toast.success('Agencia actualizada');
      setEditando(null);
      cargar();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo actualizar la agencia.'));
    } finally {
      setGuardandoFila(false);
    }
  };

  const importar = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setSubiendo(true);
    setInforme(null);
    const cuerpo = new FormData();
    cuerpo.append('archivo', f);
    try {
      const res = await api.post(
        `/admin/envios/transportistas/${transportista.transportista_id}/agencias/csv`,
        cuerpo, { headers: { 'Content-Type': 'multipart/form-data' } });
      setInforme(res.data);
      cargar();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo importar el CSV.'));
    } finally {
      setSubiendo(false);
      if (archivo.current) archivo.current.value = '';
    }
  };

  const entrega = lista.find((a) => a.es_punto_entrega);

  return (
    <div style={{ marginTop: '26px', paddingTop: '18px', borderTop: `1px solid ${COLOR.borde}` }}>
      <h4 style={titulo}><MapPin size={16} /> Agencias</h4>
      <p style={bajada}>
        Las oficinas donde el destinatario retira. Se cargan de a una o por CSV — una fila mala
        no aborta la importación, y el informe dice cuáles fallaron y por qué.
        {transportista.rol === 'venezuela' ? (
          <> Exactamente una tiene que estar marcada como <strong>punto de entrega</strong>: es
          la oficina de Santa Elena donde RIS App deja los paquetes, y sin ella el traslado no
          sabe dónde termina.</>
        ) : null}
      </p>

      {transportista.rol === 'venezuela' && !cargando && lista.length > 0 && !entrega ? (
        <Aviso tono="alerta" titulo="Falta marcar el punto de entrega" style={{ marginBottom: '14px' }}>
          Hay {lista.length} agencia(s) cargada(s) y ninguna es el punto de entrega.
        </Aviso>
      ) : null}

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <Boton variante="secundario" onClick={() => setNueva(nueva ? null : { ...AGENCIA_NUEVA })}>
          <Plus size={14} /> Agregar una
        </Boton>
        <Boton variante="secundario" cargando={subiendo}
          onClick={() => archivo.current?.click()}>
          <Upload size={14} /> Importar CSV
        </Boton>
        <input ref={archivo} type="file" accept=".csv,text/csv" onChange={importar}
          style={{ display: 'none' }} />
        <span style={{ fontSize: '12px', color: COLOR.suave, alignSelf: 'center' }}>
          Columnas: codigo, nombre, estado, ciudad, direccion, zona, codigo_postal, activa,
          es_punto_entrega
        </span>
      </div>

      {informe ? (
        <Aviso tono={informe.total_rechazadas ? 'alerta' : 'ok'}
          titulo={`${informe.creadas} creadas, ${informe.actualizadas} actualizadas, ${informe.total_rechazadas} rechazadas`}
          style={{ marginBottom: '14px' }}>
          {informe.total_rechazadas ? (
            <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px' }}>
              {(informe.rechazadas || []).slice(0, 12).map((r) => (
                <li key={r.fila}>Fila {r.fila}: {r.motivo}</li>
              ))}
            </ul>
          ) : 'Entró todo.'}
        </Aviso>
      ) : null}

      {nueva ? (
        <div style={{ padding: '16px', borderRadius: '12px', backgroundColor: '#f9fafb',
          border: `1px solid ${COLOR.borde}`, marginBottom: '14px' }}>
          <div style={grilla('180px')}>
            {[['codigo', 'Código'], ['nombre', 'Nombre'], ['estado', 'Estado'],
              ['ciudad', 'Ciudad'], ['direccion', 'Dirección'], ['zona', 'Zona'],
              ['codigo_postal', 'Código postal']].map(([k, e]) => (
              <Campo key={k} etiqueta={e}>
                <Texto value={nueva[k]}
                  onChange={(ev) => setNueva((n) => ({ ...n, [k]: ev.target.value }))} />
              </Campo>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '14px' }}>
            <Interruptor activo={nueva.activa} etiqueta="Activa"
              onChange={(v) => setNueva((n) => ({ ...n, activa: v }))} />
            <Interruptor activo={nueva.es_punto_entrega} etiqueta="Es el punto de entrega"
              ayuda="Solo una puede serlo. Marcar otra libera la anterior."
              onChange={(v) => setNueva((n) => ({ ...n, es_punto_entrega: v }))} />
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
            <Boton onClick={crear}><Save size={14} /> Crear</Boton>
            <Boton variante="secundario" onClick={() => setNueva(null)}>Cancelar</Boton>
          </div>
        </div>
      ) : null}

      {cargando ? <Cargando texto="Leyendo agencias…" /> : noSeLeyo ? (
        <NoSePudoLeer que="las agencias" detalle={noSeLeyo}
          onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />
      ) : lista.length === 0 ? (
        <Vacio titulo="Sin agencias">Cargá al menos una, o importá el CSV.</Vacio>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: COLOR.suave }}>
                {['Código', 'Nombre', 'Estado', 'Ciudad', '', ''].map((h, i) => (
                  <th key={`${h}-${i}`} style={{ padding: '8px 10px', fontWeight: 600,
                    borderBottom: `1px solid ${COLOR.borde}`, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.codigo} style={{ borderBottom: `1px solid ${COLOR.borde}`,
                  opacity: a.activa ? 1 : 0.5 }}>
                  <td style={{ padding: '8px 10px', fontFamily: 'monospace' }}>{a.codigo}</td>
                  <td style={{ padding: '8px 10px', fontWeight: 600 }}>{a.nombre}</td>
                  <td style={{ padding: '8px 10px' }}>{a.estado}</td>
                  <td style={{ padding: '8px 10px' }}>{a.ciudad}</td>
                  <td style={{ padding: '8px 10px' }}>
                    {a.es_punto_entrega ? (
                      <span style={{ fontSize: '11px', fontWeight: 700, padding: '3px 9px',
                        borderRadius: '999px', backgroundColor: COLOR.primarioSuave,
                        color: COLOR.primarioOscuro }}>
                        punto de entrega
                      </span>
                    ) : null}
                  </td>
                  <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                    <Boton variante="secundario"
                      onClick={() => setEditando(editando === a.codigo ? null : a.codigo)}>
                      {editando === a.codigo ? 'Cerrar' : 'Editar'}
                    </Boton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando ? (
        <FilaDeAgencia agencia={lista.find((a) => a.codigo === editando)}
          guardando={guardandoFila}
          onGuardar={(cambios) => guardarFila(editando, cambios)}
          onCancelar={() => setEditando(null)} />
      ) : null}
    </div>
  );
}

/**
 * Corregir una agencia ya cargada.
 *
 * Sin esto, marcar como punto de entrega una que se creó sin la marca solo se
 * podía hacer reimportando un CSV — y un CSV que no trae una columna la borra en
 * todas las filas. Alguien que instala el módulo una sola vez no tiene por qué
 * descubrir eso con la caja de otro esperando.
 */
function FilaDeAgencia({ agencia, guardando, onGuardar, onCancelar }) {
  const [datos, setDatos] = useState(() => ({
    nombre: agencia?.nombre || '', estado: agencia?.estado || '',
    ciudad: agencia?.ciudad || '', direccion: agencia?.direccion || '',
    zona: agencia?.zona || '', codigo_postal: agencia?.codigo_postal || '',
    activa: agencia?.activa !== false, es_punto_entrega: !!agencia?.es_punto_entrega,
  }));
  if (!agencia) return null;
  return (
    <div style={{ marginTop: '14px', padding: '16px', borderRadius: '12px',
      backgroundColor: '#f9fafb', border: `1px solid ${COLOR.borde}` }}>
      <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: COLOR.suave }}>
        Editando <strong style={{ fontFamily: 'monospace', color: COLOR.texto }}>
          {agencia.codigo}</strong> — el código no se cambia: es cómo la identifica el CSV.
      </p>
      <div style={grilla('180px')}>
        {[['nombre', 'Nombre'], ['estado', 'Estado'], ['ciudad', 'Ciudad'],
          ['direccion', 'Dirección'], ['zona', 'Zona'],
          ['codigo_postal', 'Código postal']].map(([k, e]) => (
          <Campo key={k} etiqueta={e}>
            <Texto value={datos[k]}
              onChange={(ev) => setDatos((d) => ({ ...d, [k]: ev.target.value }))} />
          </Campo>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '14px' }}>
        <Interruptor activo={datos.activa} etiqueta="Activa"
          ayuda="Desactivar no borra: los envíos viejos apuntan a esta fila."
          onChange={(v) => setDatos((d) => ({ ...d, activa: v }))} />
        <Interruptor activo={datos.es_punto_entrega} etiqueta="Es el punto de entrega"
          ayuda="Solo una puede serlo. Marcar esta libera la anterior."
          onChange={(v) => setDatos((d) => ({ ...d, es_punto_entrega: v }))} />
      </div>
      <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
        <Boton cargando={guardando} onClick={() => onGuardar({
          ...datos,
          direccion: datos.direccion || null, zona: datos.zona || null,
          codigo_postal: datos.codigo_postal || null,
        })}>
          <Save size={14} /> Guardar
        </Boton>
        <Boton variante="secundario" onClick={onCancelar}>Cancelar</Boton>
      </div>
    </div>
  );
}
