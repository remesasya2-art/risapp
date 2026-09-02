/**
 * Matrices.jsx — Los precios de referencia de cada tramo.
 *
 * QUE SON ESTOS NUMEROS Y QUE NO SON
 *   Es lo que cada transportista cobraría por SU tramo. RIS App no los cobra:
 *   los dos tramos los contrata y los paga el usuario por su cuenta, y estos
 *   montos se le muestran como ORIENTACIÓN. Ninguno entra en ningún total.
 *
 * EL CIRCULO QUE NO CERRABA SOLO
 *   Las matrices se diseñaron para alimentarse con los precios que la operación
 *   observa y que alguien aprueba de a uno. En régimen funciona; al arrancar no
 *   funciona nunca, porque para observar un precio hay que haber despachado un
 *   paquete y para que alguien despache tiene que ver un precio. Esta pantalla
 *   es la entrada que faltaba.
 *
 * LO QUE TIENE QUE DECIR SIN QUE SE LO PIDAN
 *   QUE FALTA — cruzando los orígenes activos y las zonas de las agencias contra
 *   lo cargado. Es el aviso que evita que un usuario vea un bloque mudo.
 *   QUE ESTA VIEJO — a los 30 días el usuario ve la advertencia; verlo acá antes
 *   que allá es la diferencia entre corregirlo y enterarse por un reclamo.
 *   DE DONDE SALIO — `observado` es un precio que vimos operando, `manual` uno
 *   que alguien tipeó. Son dos niveles de confianza y no se pueden confundir.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Clock, Eye, Hand, Plus, Upload } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import {
  Aviso, Boton, Campo, Cargando, NoSePudoLeer, Seleccion, Texto, Vacio,
} from '../../envios/ui';
import {
  COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo,
} from '../../envios/estilos';

const VACIA = { transportista_id: '', clave: '', hasta_kg: '', precio: '', moneda: '' };

export default function Matrices() {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/matrices');
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setDatos(res.data);
    } catch (err) {
      if (!vivo.current) return;
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudieron leer las matrices.'));
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

  if (cargando) return <Cargando texto="Leyendo las matrices…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="las matrices de referencia" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  const filas = datos?.filas || [];
  const cobertura = datos?.cobertura?.transportistas || [];
  const viejas = filas.filter((f) => f.desactualizada);
  const conFaltantes = cobertura.filter((t) => t.faltan?.length);
  const porCodigo = Object.fromEntries(cobertura.map((t) => [t.transportista_id, t.codigo]));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={titulo}>Precios de referencia de cada tramo</h3>
        <p style={bajada}>
          Es lo que cada transportista cobraría por su tramo, y se le muestra al usuario como
          orientación. <strong>RIS App no cobra nada de esto</strong>: esos dos tramos los
          contrata y los paga él por su cuenta, y ninguno de estos números entra en ningún
          total.
        </p>
      </div>

      {conFaltantes.length ? (
        <Aviso tono="alerta" titulo="Hay tramos sin precio cargado">
          {conFaltantes.map((t) => (
            <div key={t.transportista_id}>
              <strong>{t.codigo}</strong> ({t.rol}): faltan {t.faltan.length} de{' '}
              {t.necesarias.length} — {t.faltan.join(', ')}
            </div>
          ))}
          <p style={{ margin: '6px 0 0 0' }}>
            Un envío desde esas ciudades cotiza igual, pero al usuario no le aparece ninguna
            referencia de ese tramo y no sabe por qué.
          </p>
        </Aviso>
      ) : null}

      {viejas.length ? (
        <Aviso tono="alerta"
          titulo={`${viejas.length} fila(s) con más de ${datos?.dias_frescura} días`}>
          El usuario ya está viendo «esta referencia es vieja: puede haber cambiado» en esos
          tramos. Una fila <strong>sin fecha de carga</strong> también cuenta como vieja: no
          podemos presentar como fresco un número que no sabemos cuándo se cargó.
        </Aviso>
      ) : null}

      <CargaManual transportistas={cobertura} onListo={cargar} />

      <div style={tarjeta}>
        <h3 style={titulo}>Lo cargado ({filas.length})</h3>
        {filas.length === 0 ? (
          <Vacio titulo="Todavía no hay ningún precio de referencia">
            Mientras esté vacío, al usuario le decimos que no tenemos una referencia de esos
            tramos. Cargá la primera fila arriba, o subí un CSV.
          </Vacio>
        ) : (
          <div style={{ overflowX: 'auto', marginTop: '12px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: COLOR.suave }}>
                  {['Transportista', 'Clave', 'Hasta (kg)', 'Precio', 'De dónde salió',
                    'Actualizada'].map((h) => (
                      <th key={h} style={{ padding: '8px 10px', fontWeight: 600,
                        borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {filas.map((f, i) => {
                  const celda = { padding: '8px 10px',
                    borderBottom: `1px solid ${COLOR.borde}` };
                  return (
                    <tr key={`${f.transportista_id}-${f.clave}-${f.hasta_kg}-${i}`}>
                      <td style={{ ...celda, fontFamily: 'monospace' }}>
                        {porCodigo[f.transportista_id] || f.transportista_id}
                      </td>
                      <td style={{ ...celda, fontWeight: 600 }}>{f.clave}</td>
                      <td style={celda}>{f.hasta_kg}</td>
                      <td style={celda}>{f.precio} {f.moneda || ''}</td>
                      <td style={celda}>
                        {f.origen === 'observado' ? (
                          <span style={{ color: COLOR.ok }}>
                            <Eye size={12} style={{ display: 'inline' }} /> observado
                          </span>
                        ) : (
                          <span style={{ color: COLOR.suave }}>
                            <Hand size={12} style={{ display: 'inline' }} /> a mano
                          </span>
                        )}
                      </td>
                      <td style={celda}>
                        {f.desactualizada ? (
                          <span style={{ color: COLOR.alerta }}>
                            <Clock size={12} style={{ display: 'inline' }} />{' '}
                            {f.actualizada_at ? 'vieja' : 'sin fecha'}
                          </span>
                        ) : <span style={{ color: COLOR.ok }}>al día</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ImportarCsv transportistas={cobertura} onListo={cargar} />
    </div>
  );
}


/** Una fila sola. Agregar un precio no puede exigir armar un archivo. */
function CargaManual({ transportistas, onListo }) {
  const [datos, setDatos] = useState(VACIA);
  const [guardando, setGuardando] = useState(false);

  const elegido = transportistas.find((t) => t.transportista_id === datos.transportista_id);
  const listo = datos.transportista_id && datos.clave && datos.hasta_kg && datos.precio;

  const guardar = async () => {
    setGuardando(true);
    try {
      await api.post('/admin/envios/matrices', {
        transportista_id: datos.transportista_id,
        clave: datos.clave,
        hasta_kg: datos.hasta_kg,
        precio: datos.precio,
        moneda: datos.moneda || null,
      });
      toast.success('Precio cargado');
      setDatos((d) => ({ ...VACIA, transportista_id: d.transportista_id,
        moneda: d.moneda }));
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo cargar.'));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div style={tarjeta}>
      <h3 style={titulo}><Plus size={15} style={{ display: 'inline' }} /> Cargar un precio</h3>
      <p style={bajada}>
        Cargar el mismo transportista, la misma clave y el mismo tope <strong>corrige</strong> la
        fila que ya está, no agrega otra.
      </p>
      <div style={grilla('170px')}>
        <Campo etiqueta="Transportista">
          <Seleccion value={datos.transportista_id}
            onChange={(e) => setDatos((d) => ({ ...d, transportista_id: e.target.value,
              clave: '' }))}
            opciones={[{ valor: '', texto: 'Elegí…' },
              ...transportistas.map((t) => ({ valor: t.transportista_id,
                texto: `${t.codigo} (${t.rol})` }))]} />
        </Campo>
        <Campo etiqueta="Clave"
          ayuda={elegido?.rol === 'brasil'
            ? 'El estado (UF) de origen.' : 'La zona de la agencia de destino.'}>
          {/* Se ofrecen las que hacen falta —las UF de los orígenes activos, o
              las zonas de las agencias— en vez de un campo libre: una clave
              tipeada que no corresponde a ninguna es una fila que nunca se va a
              consultar, y no hay nada que avise. */}
          <Seleccion value={datos.clave}
            onChange={(e) => setDatos((d) => ({ ...d, clave: e.target.value }))}
            opciones={[{ valor: '', texto: elegido ? 'Elegí…' : 'Elegí un transportista' },
              ...(elegido?.necesarias || []).map((c) => ({
                valor: c,
                texto: elegido.cargadas.includes(c) ? `${c} — ya tiene precio` : c,
              }))]} />
        </Campo>
        <Campo etiqueta="Hasta (kg)" ayuda="El tope de la franja.">
          <Texto inputMode="decimal" value={datos.hasta_kg} placeholder="30"
            onChange={(e) => setDatos((d) => ({ ...d, hasta_kg: e.target.value }))} />
        </Campo>
        <Campo etiqueta="Precio">
          <Texto inputMode="decimal" value={datos.precio} placeholder="120.00"
            onChange={(e) => setDatos((d) => ({ ...d, precio: e.target.value }))} />
        </Campo>
        <Campo etiqueta="Moneda">
          <Texto value={datos.moneda} maxLength={8} placeholder="BRL"
            onChange={(e) => setDatos((d) => ({ ...d, moneda: e.target.value }))} />
        </Campo>
      </div>
      <Boton onClick={guardar} cargando={guardando} disabled={!listo}
        style={{ marginTop: '14px' }}>
        <Plus size={14} /> Cargar
      </Boton>
    </div>
  );
}


function ImportarCsv({ transportistas, onListo }) {
  const [transportista, setTransportista] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [plan, setPlan] = useState(null);
  const [trabajando, setTrabajando] = useState(false);

  const enviar = async (confirmar) => {
    if (!archivo || !transportista) return;
    setTrabajando(true);
    try {
      const cuerpo = new FormData();
      cuerpo.append('transportista_id', transportista);
      cuerpo.append('archivo', archivo);
      cuerpo.append('confirmar', confirmar ? 'true' : 'false');
      // Ver el comentario en Origenes.jsx: sin este header axios manda el
      // FormData como JSON y el archivo no llega.
      const res = await api.post('/admin/envios/matrices/csv', cuerpo,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      if (confirmar) {
        toast.success(`${res.data.guardadas} fila(s) cargadas`);
        setPlan(null);
        setArchivo(null);
        onListo();
      } else {
        setPlan(res.data);
      }
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo leer el archivo.'));
    } finally {
      setTrabajando(false);
    }
  };

  return (
    <div style={tarjeta}>
      <h3 style={titulo}>
        <Upload size={15} style={{ display: 'inline' }} /> Subir una tabla entera
      </h3>
      <p style={bajada}>
        Un CSV de <code>clave,hasta_kg,precio,moneda</code>, para un transportista. Antes de
        guardar te mostramos qué va a pasar.
      </p>
      <div style={grilla('220px')}>
        <Campo etiqueta="Transportista">
          <Seleccion value={transportista}
            onChange={(e) => { setTransportista(e.target.value); setPlan(null); }}
            opciones={[{ valor: '', texto: 'Elegí…' },
              ...transportistas.map((t) => ({ valor: t.transportista_id,
                texto: `${t.codigo} (${t.rol})` }))]} />
        </Campo>
      </div>
      <input type="file" accept=".csv,text/csv" style={{ marginTop: '10px' }}
        onChange={(e) => { setArchivo(e.target.files?.[0] || null); setPlan(null); }} />
      <div style={{ marginTop: '12px' }}>
        <Boton variante="secundario" onClick={() => enviar(false)}
          cargando={trabajando} disabled={!archivo || !transportista}>
          Ver qué va a pasar
        </Boton>
      </div>

      {plan ? (
        <div style={{ marginTop: '16px' }}>
          <Aviso tono={plan.total_rechazadas ? 'alerta' : 'info'}
            titulo={`${plan.validas} fila(s) se van a cargar`
              + (plan.total_rechazadas ? ` · ${plan.total_rechazadas} no se entienden` : '')}>
            {plan.total_rechazadas ? (
              <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px' }}>
                {plan.rechazadas.slice(0, 10).map((r) => (
                  <li key={r.fila}>Línea {r.fila}: {r.motivo}</li>
                ))}
              </ul>
            ) : 'Todas las filas se entienden.'}
          </Aviso>
          <Boton onClick={() => enviar(true)} cargando={trabajando}
            disabled={!plan.validas} style={{ marginTop: '12px' }}>
            <AlertTriangle size={14} /> Cargar {plan.validas} fila(s)
          </Boton>
        </div>
      ) : null}
    </div>
  );
}
