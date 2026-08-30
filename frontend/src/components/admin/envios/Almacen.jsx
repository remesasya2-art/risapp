/**
 * Almacen.jsx — Dónde viven las fotos, y cómo mudarlas.
 *
 * NO SE EDITAN CREDENCIALES DESDE ACA, Y ES A PROPOSITO
 *   Una clave con permiso de escritura sobre el bucket es la capacidad de
 *   reemplazar cualquier comprobante del historial. En la base queda en el mismo
 *   lugar que el log de auditoría y que los respaldos —más lectores y menos
 *   control que el original— y además editable desde una pantalla web. Van en
 *   variables de entorno, que en Railway se cargan desde su panel.
 *
 *   Esta pantalla contesta las tres preguntas que sí son suyas: ¿está prendido?,
 *   ¿funciona?, ¿cuánto falta mover?
 *
 * EL BOTON DE PROBAR EXISTE POR UNA RAZON CONCRETA
 *   Para descubrir que la credencial está mal ANTES de migrar tres mil fotos, y
 *   no en el medio.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Database, HardDrive, PlugZap, RefreshCw, Truck } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import { Aviso, Boton, Cargando } from '../../envios/ui';
import { COLOR, bajada, grilla, mensajeDeError, tarjeta, titulo } from '../../envios/estilos';

const VARIABLES = ['ENVIOS_R2_ENDPOINT', 'ENVIOS_R2_BUCKET', 'ENVIOS_R2_ACCESS_KEY_ID',
  'ENVIOS_R2_SECRET_ACCESS_KEY'];

function Dato({ etiqueta, valor, tono }) {
  // Un endpoint entra en 40 caracteres y el nombre de un bucket también. Sin
  // achicar y sin cortar palabras largas, la tarjeta los recortaba justo donde
  // hace falta leerlos: «cuenta.r2.cloudflarestorage.c…» no sirve para verificar
  // que la variable apunta a la cuenta correcta.
  const largo = String(valor ?? '').length;
  return (
    <div style={{ padding: '12px 14px', borderRadius: '12px',
      border: `1px solid ${COLOR.borde}`, backgroundColor: '#f9fafb', minWidth: 0 }}>
      <p style={{ margin: 0, fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em',
        textTransform: 'uppercase', color: COLOR.suave }}>{etiqueta}</p>
      <p style={{ margin: '4px 0 0 0', fontWeight: 800, color: tono || COLOR.texto,
        fontSize: largo > 24 ? '13px' : largo > 14 ? '16px' : '20px',
        overflowWrap: 'anywhere', lineHeight: 1.35,
        fontVariantNumeric: 'tabular-nums' }}>{valor}</p>
    </div>
  );
}

export default function Almacen() {
  const [estado, setEstado] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [probando, setProbando] = useState(false);
  const [prueba, setPrueba] = useState(null);
  const [migrando, setMigrando] = useState(false);
  const [informe, setInforme] = useState(null);

  // `vivo` corta las respuestas que llegan después de que la pantalla se fue.
  // El panel tiene siete sub-pantallas y se salta entre ellas mientras una
  // petición está en vuelo: sin esto, la respuesta vieja pisa lo que el usuario
  // ya empezó a editar en la nueva. Y el efecto arranca la carga adentro de una
  // función async a propósito: llamar algo que hace setState de forma sincrónica
  // adentro de un efecto dispara renders en cascada.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/almacen');
      if (!vivo.current) return;
      setEstado(res.data);
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo leer el estado del almacén.'));
    } finally {
      if (vivo.current) setCargando(false);
    }
  }, []);

  useEffect(() => {
    vivo.current = true;
    (async () => { await cargar(); })();
    return () => { vivo.current = false; };
  }, [cargar]);

  const probar = async () => {
    setProbando(true);
    setPrueba(null);
    try {
      const res = await api.post('/admin/envios/almacen/probar');
      setPrueba(res.data);
    } catch (err) {
      setPrueba({ ok: false, detalle: mensajeDeError(err, 'No se pudo probar.') });
    } finally {
      setProbando(false);
    }
  };

  const migrar = async () => {
    setMigrando(true);
    try {
      const res = await api.post('/admin/envios/almacen/migrar', { limite: 20 });
      setInforme(res.data);
      // Y se relee: `migrar_lote` no devuelve `en_mongo`, así que el spread
      // dejaba el contador clavado mientras el texto dice «repetí hasta que
      // llegue a cero». Alguien apretando y viendo el mismo número concluye que
      // no está haciendo nada.
      await cargar();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo migrar el lote.'));
    } finally {
      setMigrando(false);
    }
  };

  if (cargando && !estado) return <Cargando texto="Leyendo el almacén…" />;

  const activo = !!estado?.activo;
  const pendientes = estado?.en_mongo;
  const desconocido = pendientes === null || pendientes === undefined;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <Aviso tono={activo ? 'ok' : 'info'}
        titulo={activo ? 'El almacén de objetos está prendido' : 'Las fotos viven en la base'}>
        {activo ? (
          <>Las fotos nuevas se guardan en <strong>{estado.bucket}</strong>. Si el bucket no
          contesta al subir un comprobante, el archivo se guarda en la base y el usuario despacha
          igual: una caída nuestra no puede frenarlo.</>
        ) : (
          <>No hace falta hacer nada: así funciona y está bien. Sacarlas de la base ahorra plata
          cuando el volumen crece —un comprobante pesa entre 1 y 4 MB y se lee dos veces en su
          vida— pero es opcional.</>
        )}
      </Aviso>

      <div style={tarjeta}>
        <h3 style={titulo}><HardDrive size={16} /> Dónde están los bytes</h3>
        <div style={grilla('160px')}>
          <Dato etiqueta="En la base" valor={desconocido ? '—' : pendientes}
            tono={desconocido ? COLOR.suave : pendientes > 0 ? COLOR.alerta : COLOR.ok} />
          <Dato etiqueta="En el almacén"
            valor={estado?.en_almacen === null || estado?.en_almacen === undefined
              ? '—' : estado.en_almacen} />
          <Dato etiqueta="Con problema" valor={estado?.con_problema ?? '—'}
            tono={estado?.con_problema ? COLOR.error : COLOR.suave} />
        </div>
        {desconocido ? (
          <Aviso tono="alerta" style={{ marginTop: '14px' }}>
            No se pudieron contar. <strong>«No sé» no es «cero»</strong>: no des la migración por
            terminada con este número.
          </Aviso>
        ) : null}
        {estado?.con_problema ? (
          <Aviso tono="error" titulo="Hay fotos que no se pueden migrar" style={{ marginTop: '14px' }}>
            Sus bytes en la base no coinciden con el hash que se guardó al subirlas. No se migran
            a propósito: hacerlo propagaría la corrupción <em>y</em> borraría el único ejemplar
            que existe. Salieron de la cola y quedan para mirar a mano.
          </Aviso>
        ) : null}
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}><PlugZap size={16} /> Configuración</h3>
        <p style={bajada}>
          Se carga en el panel de Railway, no acá y no en la base. Una clave con escritura sobre
          el bucket puede reemplazar cualquier comprobante del historial, y este panel lo leen
          más personas de las que deberían poder hacer eso.{' '}
          <strong>Emití el token con Put y Get, sin borrar</strong>: el módulo no tiene una sola
          llamada de borrado al bucket.
        </p>
        <div style={grilla('180px')}>
          <Dato etiqueta="Endpoint" valor={estado?.endpoint_host || '—'} />
          <Dato etiqueta="Bucket" valor={estado?.bucket || '—'} />
          <Dato etiqueta="Prefijo" valor={estado?.prefijo || '—'} />
          <Dato etiqueta="Credenciales"
            valor={estado?.credenciales_cargadas ? 'cargadas' : 'faltan'}
            tono={estado?.credenciales_cargadas ? COLOR.ok : COLOR.suave} />
        </div>
        {estado?.variables_faltantes?.length ? (
          <Aviso tono="info" titulo="Faltan estas variables" style={{ marginTop: '14px' }}>
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '18px', fontFamily: 'monospace',
              fontSize: '12px' }}>
              {estado.variables_faltantes.map((v) => <li key={v}>{v}</li>)}
            </ul>
            <p style={{ margin: '8px 0 0 0' }}>
              Las cuatro son: {VARIABLES.join(', ')}. El endpoint tiene que ser <code>https</code>:
              con <code>http</code> el módulo se apaga solo, porque la firma viajaría en claro.
            </p>
          </Aviso>
        ) : null}
        {estado?.endpoint_https === false ? (
          <Aviso tono="error" titulo="El endpoint no es https" style={{ marginTop: '14px' }}>
            El almacén queda desactivado a propósito y las fotos siguen yendo a la base.
          </Aviso>
        ) : null}
        <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
          <Boton variante="secundario" onClick={() => { setCargando(true); cargar(); }} cargando={cargando}>
            <RefreshCw size={14} /> Releer
          </Boton>
          <Boton onClick={probar} cargando={probando} disabled={!activo}>
            <PlugZap size={14} /> Probar la conexión
          </Boton>
        </div>
        {prueba ? (
          <Aviso tono={prueba.ok ? 'ok' : 'error'} style={{ marginTop: '14px' }}
            titulo={prueba.ok ? 'El bucket responde' : 'No responde como debería'}>
            {prueba.detalle}
          </Aviso>
        ) : null}
      </div>

      <div style={tarjeta}>
        <h3 style={titulo}><Truck size={16} /> Mudar lo que quedó en la base</h3>
        <p style={bajada}>
          De a lotes, y se puede repetir: cada archivo <strong>se escribe, se vuelve a leer, se
          compara y recién entonces se borra de la base</strong> — nunca al revés. Sin esa
          relectura, un bucket que acepta la escritura y guarda otra cosa borraría el único
          ejemplar que existía. Repetí hasta que «en la base» llegue a cero.
        </p>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <Boton onClick={migrar} cargando={migrando}
            disabled={!activo || desconocido || pendientes === 0}>
            <Database size={14} /> Migrar 20
          </Boton>
        </div>
        {informe ? (
          <Aviso tono={informe.fallidos || informe.sospechosos ? 'alerta' : 'ok'}
            titulo={`${informe.migrados} migradas, ${informe.fallidos} fallidas, ${informe.sospechosos} con problema`}
            style={{ marginTop: '14px' }}>
            {informe.parcial ? (
              <p style={{ margin: '0 0 6px 0' }}>
                El lote se cortó por tiempo antes de terminar. Nada se perdió: volvé a apretar.
              </p>
            ) : null}
            {informe.ya_estaban ? (
              <p style={{ margin: '0 0 6px 0' }}>
                {informe.ya_estaban} ya estaba(n) migrada(s).
              </p>
            ) : null}
            {(informe.detalle || []).length ? (
              <ul style={{ margin: '4px 0 0 0', paddingLeft: '18px' }}>
                {informe.detalle.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            ) : 'Sin novedades.'}
          </Aviso>
        ) : null}
      </div>
    </div>
  );
}
