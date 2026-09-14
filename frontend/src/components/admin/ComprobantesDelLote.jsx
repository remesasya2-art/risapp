import { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { rutaDeArchivo } from '../../utils/urlDeArchivo';
import {
  Upload, CheckCircle, AlertTriangle, XCircle, Eye, X, Loader2, HelpCircle,
} from 'lucide-react';

// Una sola carga para todo el lote. Es la razón de ser de esta pantalla: el
// agente vuelve de la banca en línea con once capturas en el teléfono, las
// suelta todas juntas, y el sistema dice de quién es cada una.
//
// Lo que el sistema NO puede decir con certeza queda marcado y lo resuelve una
// persona. Por qué el monto nunca adjudica, y por qué ante la duda no se
// elige, está explicado en `backend/services/comprobantes_del_lote.py`.

const C = {
  border: '#e5e7eb', bgSubtle: '#f9fafb', ink: '#111827', soft: '#6b7280',
  faint: '#9ca3af', primary: '#4338ca', primaryBg: '#eef2ff',
  green: '#047857', greenBg: '#ecfdf5', amber: '#b45309', amberBg: '#fffbeb',
  red: '#dc2626', redBg: '#fef2f2',
};

// Cómo se ve cada resultado. El texto dice QUE PASA, no cómo se llama el
// estado: «ambiguo» no le dice nada a quien está procesando pagos.
const ESTADOS = {
  seguro: { color: C.green, fondo: C.greenBg, icono: CheckCircle, texto: 'Asignado' },
  a_mano: { color: C.green, fondo: C.greenBg, icono: CheckCircle, texto: 'Asignado a mano' },
  revisar: { color: C.amber, fondo: C.amberBg, icono: AlertTriangle, texto: 'Revisar el monto' },
  ambiguo: { color: C.red, fondo: C.redBg, icono: HelpCircle, texto: 'Más de una orden' },
  repetido: { color: C.red, fondo: C.redBg, icono: HelpCircle, texto: 'Dos fotos, una orden' },
  sin_adjudicar: { color: C.red, fondo: C.redBg, icono: XCircle, texto: 'Sin asignar' },
  sin_lector: { color: C.soft, fondo: C.bgSubtle, icono: XCircle, texto: 'Asignar a mano' },
};

const chip = {
  display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 10px',
  borderRadius: '7px', border: '1px solid ' + C.border, fontSize: '12.5px',
  fontWeight: 600, color: '#374151', cursor: 'pointer', backgroundColor: '#fff',
};

function leerComoDataUrl(file) {
  return new Promise((resolve, reject) => {
    const lector = new FileReader();
    lector.onload = () => resolve(lector.result);
    lector.onerror = () => reject(new Error(`No se pudo leer ${file.name}`));
    lector.readAsDataURL(file);
  });
}

export default function ComprobantesDelLote({ lote, onCerrar }) {
  const [datos, setDatos] = useState(null);
  const [subiendo, setSubiendo] = useState(false);
  const [mirando, setMirando] = useState(null);
  const entrada = useRef(null);

  const cargar = async () => {
    try {
      const { data } = await api.get(`/admin/lotes/${lote.lote_id}/comprobantes`);
      setDatos(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudieron leer los comprobantes');
    }
  };

  // Se recarga al cambiar de lote. `cargar` no va en las dependencias a
  // propósito: se redefine en cada render y volvería a pedir todo cada vez.
  useEffect(() => { cargar(); }, [lote.lote_id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const subir = async (archivos) => {
    const fotos = [...(archivos || [])];
    if (!fotos.length) return;
    setSubiendo(true);
    try {
      const imagenes = await Promise.all(fotos.map(leerComoDataUrl));
      const { data } = await api.post(
        `/admin/lotes/${lote.lote_id}/comprobantes`, { imagenes });
      const r = data.resumen || {};
      const asignadas = (r.seguro || 0);
      const aMirar = fotos.length - asignadas;
      // El número que importa no es «se subieron once»: es cuántas quedaron
      // para mirar. Si el aviso dijera sólo que salió bien, las que quedaron
      // colgadas no se mirarían hasta que el cliente reclame.
      toast.success(aMirar
        ? `${asignadas} de ${fotos.length} asignadas. ${aMirar} para revisar.`
        : `Las ${fotos.length} quedaron asignadas.`);
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudieron subir los comprobantes');
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = '';
    }
  };

  const asignar = async (comprobanteId, ordenId) => {
    try {
      await api.post(
        `/admin/lotes/${lote.lote_id}/comprobantes/${comprobanteId}/asignar`,
        { orden_id: ordenId || null });
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo asignar');
    }
  };

  const ver = async (comprobanteId) => {
    try {
      const { data } = await api.get(
        `/admin/lotes/${lote.lote_id}/comprobantes/${comprobanteId}/imagen`);
      setMirando(data.imagen);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo abrir la foto');
    }
  };

  const comprobantes = datos?.comprobantes || [];
  const ordenes = datos?.ordenes || [];
  const sinFoto = ordenes.filter((o) => !o.tiene_comprobante);
  const paraMirar = comprobantes.filter((c) => !['seguro', 'a_mano'].includes(c.estado));

  return (
    <div style={{
      padding: '14px', marginBottom: '12px', borderRadius: '10px',
      border: '1px solid ' + C.border, backgroundColor: '#fff',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <b style={{ fontSize: '14px', color: C.ink }}>
          Comprobantes de {lote.numero}
        </b>
        <span style={{ fontSize: '12.5px', color: C.soft }}>
          {ordenes.length} orden(es) · {comprobantes.length} foto(s)
        </span>
        {datos && !datos.hay_lector && (
          // Sin lector no se rompe nada, pero el agente tiene que saber por qué
          // ninguna se asignó sola: si no, va a pensar que la pantalla falla.
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '12px',
            color: C.amber, backgroundColor: C.amberBg, padding: '4px 8px', borderRadius: '6px',
          }}>
            <AlertTriangle size={13} /> El servidor no tiene el lector: se asignan a mano
          </span>
        )}
        <button onClick={onCerrar} style={{ ...chip, marginLeft: 'auto' }}>
          <X size={13} /> Cerrar
        </button>
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
        padding: '12px', borderRadius: '9px', border: '1px dashed ' + C.border,
        backgroundColor: C.bgSubtle, marginBottom: '12px',
      }}>
        <input ref={entrada} type="file" accept="image/*" multiple
          style={{ display: 'none' }}
          onChange={(e) => subir(e.target.files)} />
        <button onClick={() => entrada.current?.click()} disabled={subiendo}
          style={{
            ...chip, backgroundColor: C.primary, color: '#fff',
            borderColor: C.primary, opacity: subiendo ? 0.6 : 1,
            cursor: subiendo ? 'wait' : 'pointer', padding: '9px 14px', fontSize: '13px',
          }}>
          {subiendo ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          {subiendo ? 'Leyendo las fotos…' : 'Subir todos los comprobantes'}
        </button>
        <span style={{ fontSize: '12.5px', color: C.soft }}>
          Elegí las {ordenes.length} capturas de una vez. El sistema las reparte
          comparando cuenta, teléfono y cédula contra cada orden.
        </span>
      </div>

      {sinFoto.length > 0 && (
        // Lo que falta se dice arriba y contado. Una orden sin comprobante es
        // un pago que no se puede probar, y nadie la busca si no se nombra.
        <div style={{
          padding: '9px 12px', marginBottom: '12px', borderRadius: '8px',
          backgroundColor: C.amberBg, border: '1px solid ' + C.amber + '33',
          fontSize: '12.5px', color: '#374151',
        }}>
          <b style={{ color: C.amber }}>{sinFoto.length} orden(es) sin comprobante:</b>{' '}
          {sinFoto.map((o) => o.display_id || o.orden_id).join(', ')}
        </div>
      )}

      {comprobantes.length === 0 ? (
        <div style={{ padding: '18px', textAlign: 'center', fontSize: '13px', color: C.faint }}>
          Todavía no se subió ninguna foto de este lote.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: C.soft }}>
                <th style={{ padding: '6px 8px', fontWeight: 600 }}>Foto</th>
                <th style={{ padding: '6px 8px', fontWeight: 600 }}>Resultado</th>
                <th style={{ padding: '6px 8px', fontWeight: 600 }}>Orden</th>
                <th style={{ padding: '6px 8px', fontWeight: 600 }}>Lo que se leyó</th>
                <th style={{ padding: '6px 8px', fontWeight: 600 }}>Asignar a</th>
              </tr>
            </thead>
            <tbody>
              {comprobantes.map((c, i) => {
                const e = ESTADOS[c.estado] || ESTADOS.sin_adjudicar;
                const Icono = e.icono;
                const leido = c.leido || {};
                const pistas = [
                  ...(leido.cuentas || []),
                  ...(leido.telefonos || []),
                  ...(leido.montos || []).map((m) => `Bs ${m}`),
                ];
                return (
                  <tr key={c.comprobante_id} style={{ borderTop: '1px solid ' + C.border }}>
                    <td style={{ padding: '8px' }}>
                      <button onClick={() => ver(c.comprobante_id)} style={chip} title="Ver la foto">
                        <Eye size={13} /> #{i + 1}
                      </button>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '5px',
                        padding: '3px 8px', borderRadius: '6px', fontWeight: 700,
                        color: e.color, backgroundColor: e.fondo,
                      }}>
                        <Icono size={13} /> {e.texto}
                      </span>
                      {c.motivo && (
                        <div style={{ marginTop: '3px', color: C.soft, maxWidth: '260px' }}>
                          {c.motivo}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '8px', color: C.ink }}>
                      {c.orden_id ? (
                        <>
                          <b>{c.display_id || c.orden_id}</b>
                          <div style={{ color: C.soft }}>{c.beneficiario}</div>
                          <div style={{ color: C.soft }}>Bs {fmt(c.monto)}</div>
                        </>
                      ) : <span style={{ color: C.faint }}>—</span>}
                    </td>
                    <td style={{ padding: '8px', color: C.soft, maxWidth: '230px' }}>
                      {pistas.length ? pistas.join(' · ')
                        : <span style={{ color: C.faint }}>no se leyó nada</span>}
                    </td>
                    <td style={{ padding: '8px' }}>
                      <select value={c.orden_id || ''}
                        onChange={(ev) => asignar(c.comprobante_id, ev.target.value)}
                        style={{
                          padding: '6px 8px', borderRadius: '7px', fontSize: '12.5px',
                          border: '1px solid ' + C.border, backgroundColor: '#fff',
                          maxWidth: '230px',
                        }}>
                        <option value="">— sin asignar —</option>
                        {ordenes.map((o) => (
                          <option key={o.orden_id} value={o.orden_id}
                            disabled={o.tiene_comprobante && o.orden_id !== c.orden_id}>
                            {o.display_id || o.orden_id} · {o.beneficiario} · Bs {fmt(o.monto)}
                            {o.tiene_comprobante && o.orden_id !== c.orden_id ? ' (ya tiene)' : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {paraMirar.length > 0 && (
        <div style={{ marginTop: '10px', fontSize: '12.5px', color: C.soft }}>
          Quedan <b style={{ color: C.red }}>{paraMirar.length}</b> foto(s) para
          resolver: abrilas y, según lo que digan, corregí la orden o confirmá
          el monto.
        </div>
      )}

      {mirando && (
        <div onClick={() => setMirando(null)}
          style={{
            position: 'fixed', inset: 0, zIndex: 1000, padding: '24px',
            backgroundColor: 'rgba(17,24,39,0.8)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out',
          }}>
          <img src={rutaDeArchivo(mirando)} alt="Comprobante"
            style={{ maxWidth: '100%', maxHeight: '100%', borderRadius: '8px' }} />
        </div>
      )}
    </div>
  );
}
