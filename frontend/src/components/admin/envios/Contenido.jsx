/**
 * Contenido.jsx — Lo que el usuario lee y acepta, y los números de la operación.
 *
 * Son los dos bloques que parecen menores y no lo son:
 *
 *   · **Prohibidos** es lo único que frena a alguien antes de despachar. No hay
 *     un filtro por palabras adentro de la descripción, y es a propósito: buscar
 *     "arma" rechaza "armazón" y no atrapa a nadie que no escriba la palabra.
 *     Esta lista, visible al cotizar, es la barrera real.
 *
 *   · **Operación** hay que cargarlo aunque sea con los valores por defecto. Sin
 *     el bloque no hay tolerancia de ajuste, y sin tolerancia TODO repesaje
 *     mueve el precio: una diferencia de cincuenta gramos genera un cobro.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Save, Scale, ShieldAlert, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { Area, Aviso, Boton, Campo, Cargando, NoSePudoLeer, Texto } from '../../envios/ui';
import { COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo } from '../../envios/estilos';


/**
 * El bloque de configuración, sin los metadatos del guardado.
 *
 * `GET /config/{bloque}` devuelve el documento crudo de Mongo, con `setting_id`,
 * `actualizado_por` y `actualizado_at` adentro. Los modelos son `extra="forbid"`,
 * así que reenviar lo que se leyó devuelve 400 — y el efecto es que cada bloque
 * se puede guardar UNA sola vez: corregir un prohibido mal escrito después ya no
 * se puede desde la pantalla.
 */
const METADATOS = ['setting_id', 'actualizado_por', 'actualizado_at', '_id'];
const sinMetadatos = (o) => Object.fromEntries(
  Object.entries(o || {}).filter(([k]) => !METADATOS.includes(k)));

/** Un campo numérico vacío es "no tipeé nada", no cero. */
const entero = (v, actual) => (String(v).trim() === '' ? actual : Number(v));

const CONTENIDO_VACIO = {
  prohibidos: [], terminos_version: '', texto_estimado: '',
  descripcion_min_caracteres: 10,
};

const OPERACION_VACIA = {
  tolerancia_ajuste_ris: '2.00', ttl_cotizacion_horas: 48,
  ttl_espera_postagem_dias: 30, plazo_pago_pendiente_dias: 7,
  dias_guarda: 30, alertas_guarda_dias: [7, 15, 25], banda_variacion_pct: '0.15',
};

export default function Contenido() {
  const [contenido, setContenido] = useState(CONTENIDO_VACIO);
  const [operacion, setOperacion] = useState(OPERACION_VACIA);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(null);
  const [errores, setErrores] = useState({});
  const [nuevoProhibido, setNuevoProhibido] = useState('');
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  // Los avisos se editan como TEXTO. Derivando el value de la lista, tipear la
  // coma de «7, 15» la borraba en el momento de escribirla y no había forma de
  // agregar un cuarto aviso.
  const [alertas, setAlertas] = useState('');

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const [c, o] = await Promise.all([
        api.get('/admin/envios/config/contenido'),
        api.get('/admin/envios/config/operacion'),
      ]);
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setContenido({ ...CONTENIDO_VACIO, ...sinMetadatos(c.data) });
      const op = { ...OPERACION_VACIA, ...sinMetadatos(o.data) };
      setOperacion(op);
      setAlertas((op.alertas_guarda_dias || []).join(', '));
    } catch (err) {
      if (!vivo.current) return;
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudo leer la configuración.'));
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

  const guardarBloque = async (bloque, datos, aplicar) => {
    setGuardando(bloque);
    setErrores((e) => ({ ...e, [bloque]: null }));
    try {
      const res = await api.put(`/admin/envios/config/${bloque}`, sinMetadatos(datos));
      aplicar(sinMetadatos(res.data?.valor) || datos);
      toast.success('Guardado');
    } catch (err) {
      setErrores((e) => ({ ...e, [bloque]: mensajeDeError(err, 'No se pudo guardar.') }));
    } finally {
      setGuardando(null);
    }
  };

  const agregarProhibido = () => {
    const limpio = nuevoProhibido.trim();
    if (!limpio) return;
    if (contenido.prohibidos.some((p) => p.toLowerCase() === limpio.toLowerCase())) {
      return toast.error('Ya está en la lista.');
    }
    setContenido((c) => ({ ...c, prohibidos: [...c.prohibidos, limpio] }));
    setNuevoProhibido('');
  };

  if (cargando) return <Cargando texto="Leyendo la configuración…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="la configuración" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={titulo}><ShieldAlert size={16} /> Lo que no se puede mandar</h3>
        <p style={bajada}>
          Esta lista se le muestra al usuario ANTES de cotizar y tiene que aceptarla. Es la
          barrera real: no hay un filtro que busque estas palabras adentro de la descripción,
          porque buscar «arma» rechaza «armazón» y no frena a nadie que no la escriba.
          Cambiala cuando cambie un criterio de aduana, sin esperar un deploy.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
          {contenido.prohibidos.length === 0 ? (
            <span style={{ fontSize: '13px', color: COLOR.error }}>
              La lista no puede quedar vacía: una lista vacía se lee como «no hay nada prohibido».
            </span>
          ) : contenido.prohibidos.map((p) => (
            <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px',
              fontSize: '13px', padding: '6px 10px', borderRadius: '999px',
              backgroundColor: COLOR.errorSuave, border: '1px solid #fecaca', color: '#991b1b' }}>
              {p}
              <button type="button" aria-label={`Quitar ${p}`}
                onClick={() => setContenido((c) => ({
                  ...c, prohibidos: c.prohibidos.filter((x) => x !== p),
                }))}
                style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#991b1b',
                  display: 'inline-flex', padding: 0 }}>
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '8px', maxWidth: '460px' }}>
          <Texto value={nuevoProhibido} onChange={(e) => setNuevoProhibido(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); agregarProhibido(); } }}
            placeholder="Categoría prohibida" maxLength={80} />
          <Boton variante="secundario" onClick={agregarProhibido}><Plus size={14} /> Agregar</Boton>
        </div>

        <div style={{ ...grilla('260px'), marginTop: '20px' }}>
          <Campo etiqueta="Versión de los términos"
            ayuda="Queda congelada en cada envío. Cambiala cuando cambie el texto: es lo que permite saber qué aceptó alguien en marzo.">
            <Texto value={contenido.terminos_version}
              onChange={(e) => setContenido((c) => ({ ...c, terminos_version: e.target.value }))}
              placeholder="2026-08-a" maxLength={40} />
          </Campo>
          <Campo etiqueta="Mínimo de caracteres de la descripción"
            ayuda="Corto de más invita a escribir «cosas»; largo de más molesta al que dice la verdad.">
            <Texto type="number" min={3} max={200} value={contenido.descripcion_min_caracteres}
              onChange={(e) => setContenido((c) => ({
                ...c,
                descripcion_min_caracteres: entero(e.target.value,
                                                   c.descripcion_min_caracteres),
              }))} />
          </Campo>
        </div>

        <div style={{ marginTop: '16px' }}>
          <Campo etiqueta="Texto del aviso de precio estimado"
            ayuda="Se muestra en cada cotización, sin condición. El precio se cierra al repesar en Pacaraima con balanza propia, y eso hay que decirlo antes y no después.">
            <Area value={contenido.texto_estimado}
              onChange={(e) => setContenido((c) => ({ ...c, texto_estimado: e.target.value }))}
              filas={4} maxLength={4000} />
          </Campo>
        </div>

        {errores.contenido ? (
          <Aviso tono="error" titulo="No se guardó" style={{ marginTop: '14px' }}>
            {errores.contenido}
          </Aviso>
        ) : null}
        <Boton style={{ marginTop: '16px' }} cargando={guardando === 'contenido'}
          onClick={() => guardarBloque('contenido', contenido,
            (v) => setContenido({ ...CONTENIDO_VACIO, ...v }))}>
          <Save size={14} /> Guardar contenido
        </Boton>
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}><Scale size={16} /> Los números de la operación</h3>
        <p style={bajada}>
          Ninguno de estos toca el precio de la tarifa. <strong>Cargalo aunque dejes todo por
          defecto</strong>: sin este bloque no hay tolerancia de ajuste, y sin tolerancia
          cualquier diferencia al repesar genera un cobro o una devolución por centavos.
        </p>
        <div style={grilla('240px')}>
          <Campo etiqueta="Tolerancia del ajuste (RIS)"
            ayuda="Si la diferencia entre lo cobrado y el precio real no llega a esto, no se ajusta nada.">
            <Texto value={operacion.tolerancia_ajuste_ris}
              onChange={(e) => setOperacion((o) => ({ ...o, tolerancia_ajuste_ris: e.target.value }))}
              placeholder="2.00" />
          </Campo>
          <Campo etiqueta="La cotización vale (horas)"
            ayuda="Después de esto hay que volver a cotizar: los precios cambian.">
            <Texto type="number" min={1} max={720} value={operacion.ttl_cotizacion_horas}
              onChange={(e) => setOperacion((o) => ({
                ...o, ttl_cotizacion_horas: entero(e.target.value, o.ttl_cotizacion_horas),
              }))} />
          </Campo>
          <Campo etiqueta="Espera de despacho (días)"
            ayuda="Cuánto se espera el comprobante después de confirmar, antes de dar el envío por abandonado.">
            <Texto type="number" min={1} max={365} value={operacion.ttl_espera_postagem_dias}
              onChange={(e) => setOperacion((o) => ({
                ...o, ttl_espera_postagem_dias: entero(e.target.value, o.ttl_espera_postagem_dias),
              }))} />
          </Campo>
          <Campo etiqueta="Plazo para pagar una partida (días)"
            ayuda="Que quede impaga no es un error: el paquete simplemente no sale de Pacaraima.">
            <Texto type="number" min={1} max={90} value={operacion.plazo_pago_pendiente_dias}
              onChange={(e) => setOperacion((o) => ({
                ...o, plazo_pago_pendiente_dias: entero(e.target.value, o.plazo_pago_pendiente_dias),
              }))} />
          </Campo>
          <Campo etiqueta="Días de guarda"
            ayuda="Cuánto se guarda un paquete en Santa Elena antes de que sea un problema.">
            <Texto type="number" min={1} max={180} value={operacion.dias_guarda}
              onChange={(e) => setOperacion((o) => ({
                ...o, dias_guarda: entero(e.target.value, o.dias_guarda),
              }))} />
          </Campo>
          <Campo etiqueta="Avisos antes de que venza la guarda"
            ayuda="Días, separados por coma y de menor a mayor. Ej: 7, 15, 25.">
            <Texto value={alertas} onChange={(e) => setAlertas(e.target.value)} />
          </Campo>
          <Campo etiqueta="Banda de variación"
            ayuda="Cuánto puede moverse un precio observado antes de que el módulo desconfíe de la muestra. 0.15 es 15 %.">
            <Texto value={operacion.banda_variacion_pct}
              onChange={(e) => setOperacion((o) => ({ ...o, banda_variacion_pct: e.target.value }))} />
          </Campo>
        </div>

        {errores.operacion ? (
          <Aviso tono="error" titulo="No se guardó" style={{ marginTop: '14px' }}>
            {errores.operacion}
          </Aviso>
        ) : null}
        <Boton style={{ marginTop: '16px' }} cargando={guardando === 'operacion'}
          onClick={() => guardarBloque('operacion', {
            ...operacion,
            alertas_guarda_dias: alertas.split(',')
              .map((x) => parseInt(x.trim(), 10)).filter((x) => !isNaN(x)),
          }, (v) => {
            const op = { ...OPERACION_VACIA, ...v };
            setOperacion(op);
            setAlertas((op.alertas_guarda_dias || []).join(', '));
          })}>
          <Save size={14} /> Guardar operación
        </Boton>
      </div>
    </div>
  );
}
