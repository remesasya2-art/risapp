/**
 * Origenes.jsx — El catálogo de ciudades de Brasil desde donde se despacha.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *   La UF de origen es la CLAVE con la que se busca el precio del tramo
 *   brasileño. Antes la tipeaba cada usuario en un campo de dos letras al lado
 *   del CEP, y un error de dos letras trae el precio de otro estado sin que
 *   nadie se entere: la referencia sale, es plausible, y está mal.
 *
 *   Acá se carga una vez por ciudad, mirando lo que se carga.
 *
 * TRES FORMAS DE CARGAR, Y LA DE UNA CIUDAD ES LA PRINCIPAL
 *   Agregar un CEP no puede exigir armar un CSV entero. El alta rápida está
 *   arriba de todo, con tres campos; el CSV es para la carga inicial de muchas;
 *   y la cola de propuestos es para las que la gente ya pidió.
 *
 * LA COLUMNA «MATRIZ» ES UN AVISO QUE NO EXISTIA
 *   Un origen sin precios cargados cotiza igual, pero su bloque de referencia
 *   queda mudo — y eso pasa sin que nadie se entere hasta que un usuario
 *   pregunta. Decirlo en la misma tabla donde se cargan los orígenes convierte
 *   ese silencio en una tarea visible.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Check, Inbox, MapPin, Plus, Search, Table2, Upload, X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../../utils/api';
import {
  Aviso, Boton, Campo, Cargando, NoSePudoLeer, Seleccion, Texto, Vacio,
} from '../../envios/ui';
import {
  COLOR, bajada, esFallaDeLectura, grilla, mensajeDeError, tarjeta, titulo,
} from '../../envios/estilos';

const VACIO = { cep: '', ciudad: '', uf: '' };

/** El CEP como lo escribe la gente, mientras lo escribe. */
const conGuion = (crudo) => {
  const digitos = String(crudo || '').replace(/\D/g, '').slice(0, 8);
  return digitos.length > 5 ? `${digitos.slice(0, 5)}-${digitos.slice(5)}` : digitos;
};

export default function Origenes({ onIr }) {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [noSeLeyo, setNoSeLeyo] = useState(null);
  const [busqueda, setBusqueda] = useState('');
  // La UF que acaba de entrar al catálogo sin tener precios. Se guarda para
  // decirlo EN EL MOMENTO de aprobar, con el atajo puesto: es cuando la persona
  // todavía tiene el contexto y puede resolverlo de una.
  const [sinPrecio, setSinPrecio] = useState(null);

  // Corta las respuestas que llegan después de que la pantalla se fue: el panel
  // tiene ocho sub-pantallas y se salta entre ellas con peticiones en vuelo.
  const vivo = useRef(true);

  const cargar = useCallback(async () => {
    try {
      const res = await api.get('/admin/envios/origenes');
      if (!vivo.current) return;
      setNoSeLeyo(null);
      setDatos(res.data);
    } catch (err) {
      if (!vivo.current) return;
      // Un catálogo que no se puede leer NO es un catálogo vacío. Mostrar la
      // pantalla de «todavía no cargaste nada» invita a subir un CSV encima de
      // datos que sí estaban.
      if (esFallaDeLectura(err)) {
        setNoSeLeyo(mensajeDeError(err, 'La base no contestó.'));
      } else {
        toast.error(mensajeDeError(err, 'No se pudo leer el catálogo de orígenes.'));
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

  if (cargando) return <Cargando texto="Leyendo el catálogo de orígenes…" />;
  if (noSeLeyo) {
    return <NoSePudoLeer que="el catálogo de orígenes" detalle={noSeLeyo}
      onReintentar={() => { setCargando(true); cargar(); }} reintentando={cargando} />;
  }

  const origenes = datos?.origenes || [];
  const propuestos = datos?.propuestos || [];
  const filtro = busqueda.trim().toLowerCase();
  const visibles = filtro
    ? origenes.filter((o) => `${o.ciudad} ${o.uf} ${o.cep_legible}`.toLowerCase().includes(filtro))
    : origenes;
  const sinMatriz = origenes.filter((o) => o.tiene_matriz === false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={tarjeta}>
        <h3 style={titulo}>Desde dónde despacha la gente</h3>
        <p style={bajada}>
          Cada ciudad que cargás acá le aparece al usuario como una opción para elegir, en vez
          de tener que escribir su CEP y su estado a mano. El <strong>estado (UF)</strong> es lo
          que después busca el precio del tramo brasileño: si está mal, la referencia que ve el
          usuario es la de otro estado.
        </p>
      </div>

      {sinPrecio ? (
        <Aviso tono="alerta" titulo={`${sinPrecio} todavía no tiene precios cargados`}>
          La ciudad ya está en el catálogo y cotiza, pero al usuario no le va a aparecer
          ninguna referencia del tramo dentro de Brasil hasta que cargues precios para{' '}
          <strong>{sinPrecio}</strong>.
          {onIr ? (
            <div style={{ marginTop: '10px' }}>
              <Boton onClick={() => onIr('matrices')}>
                <Table2 size={14} /> Cargar precios de {sinPrecio}
              </Boton>
            </div>
          ) : null}
        </Aviso>
      ) : null}

      {sinMatriz.length ? (
        <Aviso tono="alerta" titulo={`${sinMatriz.length} ciudad(es) sin precios cargados`}>
          {sinMatriz.map((o) => `${o.ciudad} (${o.uf})`).join(', ')}. Cotizan igual, pero al
          usuario no le va a aparecer ninguna referencia del tramo dentro de Brasil.
          {onIr ? (
            <div style={{ marginTop: '10px' }}>
              <Boton variante="secundario" onClick={() => onIr('matrices')}>
                <Table2 size={14} /> Ir a cargar precios
              </Boton>
            </div>
          ) : null}
        </Aviso>
      ) : null}

      <AltaRapida uf={datos?.uf_disponibles || []} onListo={cargar} />

      {propuestos.length ? (
        <ColaDePropuestos filas={propuestos} uf={datos?.uf_disponibles || []}
          conMatriz={new Set(origenes.filter((o) => o.tiene_matriz).map((o) => o.uf))}
          onListo={cargar} onSinPrecio={setSinPrecio} />
      ) : null}

      <div style={tarjeta}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <h3 style={{ ...titulo, margin: 0 }}>
            El catálogo ({origenes.length})
          </h3>
          {origenes.length > 8 ? (
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '11px',
                color: COLOR.suave }} />
              <Texto placeholder="Buscar ciudad, UF o CEP" value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                style={{ paddingLeft: '30px', minWidth: '220px' }} />
            </div>
          ) : null}
        </div>

        {origenes.length === 0 ? (
          <Vacio titulo="Todavía no cargaste ninguna ciudad">
            Agregá la primera con el formulario de arriba, o subí un CSV si tenés muchas.
            Mientras el catálogo esté vacío, el usuario escribe su CEP y su estado a mano.
          </Vacio>
        ) : (
          <Tabla filas={visibles} uf={datos?.uf_disponibles || []}
            matrizLegible={datos?.matriz_legible} onListo={cargar} />
        )}
      </div>

      <ImportarCsv onListo={cargar} />
    </div>
  );
}


/** El alta de UNA ciudad. Tres campos, arriba de todo. */
function AltaRapida({ uf, onListo }) {
  const [datos, setDatos] = useState(VACIO);
  const [guardando, setGuardando] = useState(false);

  const digitos = datos.cep.replace(/\D/g, '');
  const listo = digitos.length === 8 && datos.ciudad.trim().length >= 2 && datos.uf;

  const guardar = async () => {
    setGuardando(true);
    try {
      const res = await api.post('/admin/envios/origenes', {
        cep: digitos, ciudad: datos.ciudad.trim(), uf: datos.uf,
      });
      // Se dice cuál de las dos cosas pasó: cargar un CEP que ya estaba lo
      // CORRIGE, y quien lo hizo tiene que saber que corrigió y no que agregó.
      toast.success(res.data?.ya_existia
        ? `${datos.ciudad.trim()} ya estaba: se actualizó`
        : `${datos.ciudad.trim()} agregada`);
      setDatos(VACIO);
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo agregar.'));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div style={tarjeta}>
      <h3 style={titulo}><Plus size={15} style={{ display: 'inline' }} /> Agregar una ciudad</h3>
      <p style={bajada}>
        Para una sola no hace falta armar un archivo. Si el CEP ya está cargado, esto lo corrige.
      </p>
      <div style={grilla('180px')}>
        <Campo etiqueta="CEP">
          <Texto inputMode="numeric" value={datos.cep} maxLength={9} placeholder="01310-100"
            onChange={(e) => setDatos((d) => ({ ...d, cep: conGuion(e.target.value) }))} />
        </Campo>
        <Campo etiqueta="Ciudad">
          <Texto value={datos.ciudad} maxLength={80} placeholder="São Paulo"
            onChange={(e) => setDatos((d) => ({ ...d, ciudad: e.target.value }))} />
        </Campo>
        <Campo etiqueta="Estado (UF)"
          ayuda="Es lo que busca el precio del tramo brasileño.">
          <Seleccion value={datos.uf}
            onChange={(e) => setDatos((d) => ({ ...d, uf: e.target.value }))}
            opciones={[{ valor: '', texto: 'Elegí…' },
              ...uf.map((u) => ({ valor: u, texto: u }))]} />
        </Campo>
      </div>
      <Boton onClick={guardar} cargando={guardando} disabled={!listo}
        style={{ marginTop: '14px' }}>
        <Plus size={14} /> Agregar
      </Boton>
    </div>
  );
}


function Tabla({ filas, uf, matrizLegible, onListo }) {
  return (
    <div style={{ overflowX: 'auto', marginTop: '12px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: COLOR.suave }}>
            {['CEP', 'Ciudad', 'UF', 'Matriz', 'Estado', ''].map((h) => (
              <th key={h} style={{ padding: '8px 10px', fontWeight: 600,
                borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((o) => (
            <Fila key={o.cep} origen={o} uf={uf} matrizLegible={matrizLegible}
              onListo={onListo} />
          ))}
        </tbody>
      </table>
    </div>
  );
}


function Fila({ origen, uf, matrizLegible, onListo }) {
  const [editando, setEditando] = useState(false);
  const [datos, setDatos] = useState({ ciudad: origen.ciudad, uf: origen.uf });
  const [guardando, setGuardando] = useState(false);

  const patch = async (cuerpo, mensaje) => {
    setGuardando(true);
    try {
      await api.patch(`/admin/envios/origenes/${origen.cep}`, cuerpo);
      toast.success(mensaje);
      setEditando(false);
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo guardar.'));
    } finally {
      setGuardando(false);
    }
  };

  const celda = { padding: '8px 10px', borderBottom: `1px solid ${COLOR.borde}` };

  return (
    <tr style={{ opacity: origen.activo === false ? 0.55 : 1 }}>
      <td style={{ ...celda, fontFamily: 'monospace' }}>{origen.cep_legible}</td>
      <td style={celda}>
        {editando ? (
          <Texto value={datos.ciudad} maxLength={80}
            onChange={(e) => setDatos((d) => ({ ...d, ciudad: e.target.value }))} />
        ) : origen.ciudad}
      </td>
      <td style={celda}>
        {editando ? (
          <Seleccion value={datos.uf}
            onChange={(e) => setDatos((d) => ({ ...d, uf: e.target.value }))}
            opciones={uf.map((u) => ({ valor: u, texto: u }))} />
        ) : origen.uf}
      </td>
      <td style={celda}>
        {/* `null` es «no lo pude averiguar», y se muestra distinto de «no tiene»:
            mandar a cargar precios que ya están es peor que no avisar. */}
        {!matrizLegible || origen.tiene_matriz === null ? (
          <span style={{ color: COLOR.suave }}>—</span>
        ) : origen.tiene_matriz ? (
          <span style={{ color: COLOR.ok }}>con precio</span>
        ) : (
          <span style={{ color: COLOR.alerta }}>
            <AlertTriangle size={12} style={{ display: 'inline' }} /> sin matriz
          </span>
        )}
      </td>
      <td style={celda}>
        {origen.activo === false
          ? <span style={{ color: COLOR.suave }}>Desactivada</span>
          : <span style={{ color: COLOR.ok }}>Activa</span>}
      </td>
      <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap' }}>
        {editando ? (
          <>
            <Boton onClick={() => patch({ ciudad: datos.ciudad.trim(), uf: datos.uf },
              'Guardado')} cargando={guardando}>
              <Check size={13} /> Guardar
            </Boton>{' '}
            <Boton variante="secundario" onClick={() => setEditando(false)}>Cancelar</Boton>
          </>
        ) : (
          <>
            <Boton variante="secundario" onClick={() => setEditando(true)}>Editar</Boton>{' '}
            <Boton variante="secundario" cargando={guardando}
              onClick={() => patch({ activo: origen.activo === false },
                origen.activo === false ? 'Activada' : 'Desactivada')}>
              {origen.activo === false ? 'Activar' : 'Desactivar'}
            </Boton>
          </>
        )}
      </td>
    </tr>
  );
}


/** Lo que la gente pidió y no estaba, del más pedido al menos pedido. */
function ColaDePropuestos({ filas, uf, conMatriz, onListo, onSinPrecio }) {
  return (
    <div style={tarjeta}>
      <h3 style={titulo}>
        <Inbox size={15} style={{ display: 'inline' }} /> Ciudades que pidieron ({filas.length})
      </h3>
      <p style={bajada}>
        Alguien cotizó desde estos CEP y no estaban en el catálogo. Están ordenadas por cuántas
        personas las pidieron. <strong>Nada entra solo</strong>: revisá la ciudad y el estado
        antes de aprobar, porque los escribió el usuario.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: COLOR.suave }}>
              {['CEP', 'Ciudad declarada', 'UF', 'Pedidos', 'Matriz', ''].map((h) => (
                <th key={h} style={{ padding: '8px 10px', fontWeight: 600,
                  borderBottom: `1px solid ${COLOR.borde}` }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((p) => (
              <Propuesto key={p.cep} fila={p} uf={uf} conMatriz={conMatriz}
                onListo={onListo} onSinPrecio={onSinPrecio} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function Propuesto({ fila, uf, conMatriz, onListo, onSinPrecio }) {
  const [datos, setDatos] = useState({ ciudad: fila.ciudad || '', uf: fila.uf || '' });
  const [trabajando, setTrabajando] = useState(false);
  const celda = { padding: '8px 10px', borderBottom: `1px solid ${COLOR.borde}` };

  const resolver = async (estado) => {
    setTrabajando(true);
    try {
      await api.post(`/admin/envios/origenes/propuestos/${fila.cep}`, {
        estado,
        ...(estado === 'aprobado'
          ? { ciudad: datos.ciudad.trim(), uf: datos.uf } : {}),
      });
      toast.success(estado === 'aprobado' ? 'Agregada al catálogo' : 'Descartada');
      // El encargo lo pide con todas las letras: si esa UF no tiene matriz,
      // decirlo ACA MISMO. Aprobar una ciudad cuyo tramo no tiene precio deja un
      // bloque mudo en la pantalla de un usuario, y enterarse después es
      // enterarse por un reclamo.
      if (estado === 'aprobado' && conMatriz && !conMatriz.has(datos.uf)) {
        onSinPrecio?.(datos.uf);
      }
      onListo();
    } catch (err) {
      toast.error(mensajeDeError(err, 'No se pudo resolver.'));
    } finally {
      setTrabajando(false);
    }
  };

  const puedeAprobar = datos.ciudad.trim().length >= 2 && datos.uf;

  return (
    <tr>
      <td style={{ ...celda, fontFamily: 'monospace' }}>{fila.cep_legible}</td>
      <td style={celda}>
        <Texto value={datos.ciudad} maxLength={80}
          onChange={(e) => setDatos((d) => ({ ...d, ciudad: e.target.value }))} />
      </td>
      <td style={celda}>
        {/* La UF es opcional en el formulario del usuario, así que puede venir
            vacía. No es un error suyo: es lo que esta pantalla viene a completar,
            y sin ella la ciudad nunca encontraría su matriz. */}
        <Seleccion value={datos.uf}
          onChange={(e) => setDatos((d) => ({ ...d, uf: e.target.value }))}
          opciones={[{ valor: '', texto: 'Elegí…' },
            ...uf.map((u) => ({ valor: u, texto: u }))]} />
      </td>
      <td style={{ ...celda, fontWeight: 700 }}>{fila.pedidos}</td>
      <td style={celda}>
        {datos.uf && conMatriz && !conMatriz.has(datos.uf) ? (
          <span style={{ color: COLOR.alerta, fontSize: '12px' }}>
            <AlertTriangle size={11} style={{ display: 'inline' }} /> {datos.uf} sin precios
          </span>
        ) : null}
      </td>
      <td style={{ ...celda, textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Boton onClick={() => resolver('aprobado')} cargando={trabajando}
          disabled={!puedeAprobar}>
          <Check size={13} /> Aprobar
        </Boton>{' '}
        <Boton variante="secundario" onClick={() => resolver('descartado')}
          cargando={trabajando}>
          <X size={13} /> Descartar
        </Boton>
      </td>
    </tr>
  );
}


/** El CSV, con la vista previa que el servidor calcula y que no escribe nada. */
function ImportarCsv({ onListo }) {
  const [archivo, setArchivo] = useState(null);
  const [plan, setPlan] = useState(null);
  const [trabajando, setTrabajando] = useState(false);

  const enviar = async (confirmar) => {
    if (!archivo) return;
    setTrabajando(true);
    try {
      const cuerpo = new FormData();
      cuerpo.append('archivo', archivo);
      cuerpo.append('confirmar', confirmar ? 'true' : 'false');
      // El header va SI O SI: el cliente de axios tiene
      // `Content-Type: application/json` por defecto, y con eso axios convierte
      // el FormData a JSON (`formDataToJSON`) en vez de mandarlo como multipart.
      // El archivo se pierde en el camino y el servidor contesta «Field required».
      const res = await api.post('/admin/envios/origenes/csv', cuerpo,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      if (confirmar) {
        toast.success(`${res.data.nuevas} nuevas, ${res.data.actualiza} actualizadas`);
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
        <Upload size={15} style={{ display: 'inline' }} /> Subir muchas de una vez
      </h3>
      <p style={bajada}>
        Un archivo CSV con tres columnas: <code>cep,ciudad,uf</code>. Antes de guardar nada te
        mostramos qué va a pasar — cuántas se agregan, cuántas se corrigen y cuáles no se
        entienden. <strong>Recién ahí se confirma.</strong>
      </p>
      <input type="file" accept=".csv,text/csv"
        onChange={(e) => { setArchivo(e.target.files?.[0] || null); setPlan(null); }} />
      <div style={{ marginTop: '12px' }}>
        <Boton variante="secundario" onClick={() => enviar(false)}
          cargando={trabajando} disabled={!archivo}>
          Ver qué va a pasar
        </Boton>
      </div>

      {plan ? (
        <div style={{ marginTop: '16px' }}>
          <Aviso tono={plan.total_rechazadas ? 'alerta' : 'info'}
            titulo={`${plan.nuevas} nuevas · ${plan.actualiza} se corrigen`
              + (plan.total_rechazadas ? ` · ${plan.total_rechazadas} no se entienden` : '')}>
            {plan.total_rechazadas ? (
              <ul style={{ margin: '6px 0 0 0', paddingLeft: '18px' }}>
                {plan.rechazadas.slice(0, 10).map((r) => (
                  <li key={r.fila}>Línea {r.fila}: {r.motivo}</li>
                ))}
                {plan.rechazadas.length > 10
                  ? <li>…y {plan.rechazadas.length - 10} más.</li> : null}
              </ul>
            ) : 'Todas las filas se entienden.'}
          </Aviso>

          {plan.muestra_actualiza?.length ? (
            <p style={{ ...bajada, marginTop: '10px' }}>
              Ejemplos de lo que se corrige:{' '}
              {plan.muestra_actualiza.slice(0, 3).map((m) => (
                `${m.cep_legible} ${m.antes?.ciudad} (${m.antes?.uf}) → ${m.ciudad} (${m.uf})`
              )).join(' · ')}
            </p>
          ) : null}

          <Boton onClick={() => enviar(true)} cargando={trabajando}
            disabled={!plan.nuevas && !plan.actualiza} style={{ marginTop: '12px' }}>
            <MapPin size={14} /> Guardar {plan.nuevas + plan.actualiza} ciudad(es)
          </Boton>
        </div>
      ) : null}
    </div>
  );
}
