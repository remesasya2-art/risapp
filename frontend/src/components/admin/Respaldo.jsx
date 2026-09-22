/**
 * Respaldo de la base de la aplicación.
 *
 *   Mongo está en Railway, que no respalda la base por su cuenta. Acá el
 *   super administrador crea un respaldo (se baja al navegador; la base sólo
 *   registra que se hizo y quién) y comprueba uno guardado: hash del cierre,
 *   firma, cantidad de documentos, que cada línea se lea. El archivo lleva
 *   los datos de todos los clientes: se guarda donde se guardaría la base.
 */
import { useCallback, useEffect, useState } from 'react';
import { Archive, FileCheck, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

const tarjeta = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 16px' };
const campo = { width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14 };
const boton = { padding: '9px 14px', borderRadius: 8, border: 'none', background: '#5B4FE9', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 6 };
const botonSuave = { ...boton, background: '#eef2ff', color: '#3B3A9E' };
const th = { textAlign: 'left', fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4, padding: '6px 8px', borderBottom: '1px solid #e5e7eb' };
const td = { padding: '7px 8px', borderBottom: '1px solid #f3f4f6', fontSize: 13, verticalAlign: 'top' };
const mono = { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 };
const fechaYHora = (iso) => (iso ? new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');

export default function Respaldo() {
  const [datos, setDatos] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [ultimo, setUltimo] = useState(null);                 // { hash, firma, documentos, firmado } del recién creado
  const [aComprobar, setAComprobar] = useState({ contenido: '', nombre: '', firma: '' });
  const [comprobacion, setComprobacion] = useState(null);

  const cargar = useCallback(() => {
    api.get('/admin/respaldos').then((r) => setDatos(r.data)).catch((e) => toast.error(e?.response?.data?.detail || 'No se pudo cargar'));
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  const crear = async () => {
    setOcupado(true);
    try {
      const r = await api.post('/admin/respaldos');
      const url = URL.createObjectURL(new Blob([r.data.contenido], { type: 'application/x-ndjson' }));
      const a = document.createElement('a');
      a.href = url; a.download = `risapp-respaldo-${r.data.momento.slice(0, 19).replaceAll(':', '')}.jsonl`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      setUltimo({ hash: r.data.hash, firma: r.data.firma, documentos: r.data.documentos, firmado: r.data.firmado });
      toast.success(`Respaldo de ${r.data.documentos} documentos${r.data.firmado ? ', firmado' : ', SIN FIRMA (falta la llave)'}`);
      cargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo crear el respaldo'); }
    finally { setOcupado(false); }
  };

  const elegirArchivo = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const lector = new FileReader();
    lector.onload = () => setAComprobar((x) => ({ ...x, contenido: String(lector.result || ''), nombre: f.name }));
    lector.readAsText(f);
  };

  const comprobar = async () => {
    if (!aComprobar.contenido) return toast.error('Elegí el archivo del respaldo');
    setOcupado(true);
    try {
      const r = await api.post('/admin/respaldos/comprobar', { contenido: aComprobar.contenido, firma: aComprobar.firma.trim() || undefined });
      setComprobacion(r.data);
      (r.data.ok ? toast.success : toast.error)(r.data.ok ? `Respaldo íntegro · ${r.data.documentos} documentos · firma ${r.data.firma}` : `NO pasa: ${r.data.motivo}`);
      cargar();
    } catch (e) { toast.error(e?.response?.data?.detail || 'No se pudo comprobar'); }
    finally { setOcupado(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} data-testid="respaldo-de-la-base">
      <div style={tarjeta}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <strong style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16 }}><Archive size={18} /> Respaldo de la base de la aplicación</strong>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {datos ? <span style={{ fontSize: 12, color: datos.llave_configurada ? '#6b7280' : '#b45309' }}>{datos.llave_configurada ? 'llave configurada: los respaldos salen firmados' : 'SIN llave (LLAVE_DE_RESPALDO): los respaldos salen sin firma'} · {datos.colecciones_que_se_conservan.length} colecciones</span> : null}
            <button type="button" onClick={cargar} style={{ ...botonSuave, padding: '6px 9px' }} title="Actualizar"><RefreshCw size={14} /></button>
          </span>
        </div>
        <p style={{ margin: '8px 0 0', fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
          Mongo está en Railway, que no respalda la base por su cuenta. Este botón exporta las cuentas, las verificaciones, los envíos, los cobros, los libros, la configuración y la auditoría (no las sesiones ni lo que se regenera solo) en un archivo de una línea por documento, con hash de cierre y firma. <strong>El archivo se baja a tu computadora y se guarda afuera, en un lugar tan protegido como la base</strong>: lleva los datos de todos los clientes. La base sólo registra que se hizo, y quién. Y un respaldo que no se probó es una esperanza: la comprobación de la derecha lo lee entero.
        </p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
        <div style={tarjeta}>
          <button type="button" onClick={crear} disabled={ocupado} style={boton} data-testid="respaldo-crear"><Archive size={14} /> Crear y bajar un respaldo ahora</button>
          {ultimo ? (
            <div style={{ marginTop: 8, fontSize: 12, color: '#374151' }} data-testid="respaldo-ultimo">
              <div>{ultimo.documentos} documentos · hash <span style={mono}>{ultimo.hash.slice(0, 16)}…</span></div>
              <div>{ultimo.firmado ? <>Firma (guardala junto al archivo): <span style={{ ...mono, wordBreak: 'break-all' }} data-testid="respaldo-firma">{ultimo.firma}</span></> : 'Sin firma: falta la llave de respaldo.'}</div>
            </div>
          ) : null}
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }} data-testid="respaldo-tabla">
            <thead><tr><th style={th}>Cuándo</th><th style={th}>Quién</th><th style={th}>Documentos</th><th style={th}>Firmado</th><th style={th}>Comprobación</th></tr></thead>
            <tbody>
              {!datos || datos.respaldos.length === 0 ? <tr><td style={td} colSpan={5}>Ningún respaldo todavía.</td></tr> : datos.respaldos.map((r) => (
                <tr key={r.id} data-testid="respaldo-fila">
                  <td style={{ ...td, fontSize: 12 }}>{fechaYHora(r.momento)}<div style={{ ...mono, fontSize: 10, color: '#9ca3af' }}>{r.hash.slice(0, 16)}…</div></td>
                  <td style={{ ...td, fontSize: 12 }}>{r.actor}</td>
                  <td style={{ ...td, fontSize: 12 }}>{r.documentos} · {(r.bytes / 1024).toFixed(1)} KB</td>
                  <td style={{ ...td, fontSize: 12, color: r.firmado ? '#166534' : '#b45309' }}>{r.firmado ? 'sí' : 'no'}</td>
                  <td style={{ ...td, fontSize: 12 }}>{r.comprobacion ? <span style={{ color: r.comprobacion.ok ? '#166534' : '#b91c1c' }} data-testid={`respaldo-comprobado-${r.comprobacion.ok ? 'ok' : 'falla'}`}>{r.comprobacion.ok ? 'íntegro' : 'NO PASA'} · {fechaYHora(r.comprobado_en)}</span> : <span style={{ color: '#9ca3af' }}>sin comprobar</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={tarjeta}>
          <strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}><FileCheck size={14} /> Comprobar un respaldo guardado</strong>
          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            <input type="file" accept=".jsonl,.txt,application/x-ndjson" onChange={elegirArchivo} style={{ fontSize: 13 }} data-testid="respaldo-archivo" />
            {aComprobar.nombre ? <div style={{ fontSize: 12, color: '#6b7280' }}>{aComprobar.nombre} · {(aComprobar.contenido.length / 1024).toFixed(1)} KB</div> : null}
            <input style={campo} placeholder="Firma (la que se guardó junto al archivo; opcional)" value={aComprobar.firma} onChange={(e) => setAComprobar({ ...aComprobar, firma: e.target.value })} data-testid="respaldo-firma-a-comprobar" />
            <button type="button" onClick={comprobar} disabled={ocupado || !aComprobar.contenido} style={botonSuave} data-testid="respaldo-comprobar">Comprobar</button>
          </div>
          {comprobacion ? (
            <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: comprobacion.ok ? '#f0fdf4' : '#fef2f2', fontSize: 13 }} data-testid={`respaldo-resultado-${comprobacion.ok ? 'ok' : 'falla'}`}>
              <div><strong>{comprobacion.ok ? 'Íntegro' : 'NO PASA'}</strong>{comprobacion.motivo ? ` · ${comprobacion.motivo}` : ''}</div>
              <div style={{ color: '#374151', marginTop: 4 }}>hash del cierre {comprobacion.hash_ok ? 'coincide' : 'NO coincide'} · firma {comprobacion.firma.replaceAll('_', ' ')} · {comprobacion.documentos} documentos en {Object.keys(comprobacion.colecciones).length} colecciones{comprobacion.registrado ? ' · es uno de los registrados' : ' · no figura entre los registrados'}</div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
