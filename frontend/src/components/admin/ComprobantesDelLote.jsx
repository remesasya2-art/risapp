import { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { rutaDeArchivo } from '../../utils/urlDeArchivo';
import {
  Upload, CheckCircle, AlertTriangle, XCircle, Eye, X, Loader2, HelpCircle, Trash2,
  Undo2,
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

export default function ComprobantesDelLote({ lote, onCerrar, onCambio }) {
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

  const devolver = async (ordenId, motivo) => {
    try {
      await api.post(
        `/admin/lotes/${lote.lote_id}/ordenes/${ordenId}/devolver`, { motivo });
      toast.success('La orden volvió a la cola de pendientes');
      await cargar();
      onCambio?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo devolver la orden');
    }
  };

  const descartar = async (comprobanteId, motivo) => {
    try {
      await api.post(
        `/admin/lotes/${lote.lote_id}/comprobantes/${comprobanteId}/descartar`,
        { motivo });
      toast.success('Foto descartada');
      await cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo descartar');
    }
  };

  const comprobantes = datos?.comprobantes || [];
  const ordenes = datos?.ordenes || [];

  // ─── LOS TRES BLOQUES ────────────────────────────────────────────────────
  //
  // Antes esto era UNA tabla con todas las fotos mezcladas: las que salieron
  // bien, las dudosas y las que no son de nadie, todas juntas y en el mismo
  // tamaño de letra. Con dieciséis fotos eso es una pared, y lo que hay que
  // mirar —que son dos o tres— queda enterrado entre lo que ya está resuelto.
  //
  // Así que se separa por lo que el agente tiene que HACER con cada cosa:
  //
  //   ① nada, ya está;
  //   ② mirarla, porque falta la foto o el monto no coincide;
  //   ③ decidir de quién es esta foto, o sacarla.
  //
  // Quién va en ① lo decide el servidor (`listo_para_registrar`), no esta
  // pantalla: la regla vive al lado de los estados, en
  // `services/comprobantes_del_lote.py`.
  const porOrden = Object.fromEntries(
    comprobantes.filter((c) => c.orden_id).map((c) => [c.orden_id, c]));
  const listas = ordenes.filter((o) => o.listo_para_registrar);
  const porResolver = ordenes.filter((o) => !o.listo_para_registrar);
  const sinDueno = comprobantes.filter((c) => !c.orden_id);
  // Un lote cerrado se mira y no se toca: el servidor rechaza cualquier cambio,
  // y ofrecer botones que van a fallar es peor que no ofrecerlos.
  const abiertoElLote = (datos?.estado || 'abierto') === 'abierto';

  const tituloBloque = (texto, cuanto, color) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px',
      fontSize: '13px', fontWeight: 700, color: C.ink,
    }}>
      {texto}
      <span style={{
        padding: '1px 8px', borderRadius: '999px', fontSize: '12px',
        color, backgroundColor: color + '18',
      }}>{cuanto}</span>
    </div>
  );

  const bloque = { marginBottom: '14px' };

  const selectDeOrden = (c) => (
    <select value={c.orden_id || ''}
      onChange={(ev) => asignar(c.comprobante_id, ev.target.value)}
      style={{
        padding: '6px 8px', borderRadius: '7px', fontSize: '12.5px',
        border: '1px solid ' + C.border, backgroundColor: '#fff', maxWidth: '260px',
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
  );

  const loQueSeLeyo = (c) => {
    const l = c.leido || {};
    const pistas = [
      ...(l.cuentas || []), ...(l.telefonos || []),
      ...(l.montos || []).map((m) => `Bs ${m}`),
    ];
    return pistas.length ? pistas.join(' · ') : 'no se leyó nada';
  };

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
          {datos?.descartadas ? ` · ${datos.descartadas} descartada(s)` : ''}
        </span>
        {datos && !datos.hay_lector && (
          // Sin lector no se rompe nada, pero el agente tiene que saber por qué
          // ninguna se asignó sola: si no, va a pensar que la pantalla falla.
          //
          // Y va el MOTIVO, no «no está instalado». Ese texto era una
          // conjetura: podía ser eso, que estuviera en otro lado, o que le
          // faltara el idioma, y cada uno se arregla distinto. Lo lee un super
          // administrador, que es quien puede hacer algo con el dato.
          <span style={{
            display: 'inline-flex', alignItems: 'flex-start', gap: '5px', fontSize: '12px',
            color: C.amber, backgroundColor: C.amberBg, padding: '6px 9px',
            borderRadius: '6px', maxWidth: '420px',
          }}>
            <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>
              <b>Las fotos se asignan a mano.</b>{' '}
              {datos.por_que_no_hay_lector || 'El servidor no tiene el lector.'}
            </span>
          </span>
        )}
        <button onClick={onCerrar} style={{ ...chip, marginLeft: 'auto' }}>
          <X size={13} /> Cerrar
        </button>
      </div>

      {abiertoElLote && (
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
        padding: '12px', borderRadius: '9px', border: '1px dashed ' + C.border,
        backgroundColor: C.bgSubtle, marginBottom: '14px',
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
      )}

      {/* ① LISTAS — no hay nada que hacerles. Van plegadas: ocupan lugar y no
          piden atención. El número basta para saber cómo viene el lote. */}
      <div style={bloque}>
        {tituloBloque('Listas para registrar', listas.length, C.green)}
        {listas.length === 0 ? (
          <div style={{ fontSize: '12.5px', color: C.faint }}>
            Todavía ninguna orden tiene su comprobante confirmado.
          </div>
        ) : (
          <details>
            <summary style={{ cursor: 'pointer', fontSize: '12.5px', color: C.soft }}>
              Ver las {listas.length}
            </summary>
            <div style={{ marginTop: '8px' }}>
              {listas.map((o) => (
                <div key={o.orden_id} style={{
                  display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
                  padding: '7px 10px', borderTop: '1px solid ' + C.border, fontSize: '12.5px',
                }}>
                  <CheckCircle size={14} style={{ color: C.green, flexShrink: 0 }} />
                  <b style={{ color: C.ink }}>{o.display_id || o.orden_id}</b>
                  <span style={{ color: C.soft }}>{o.beneficiario}</span>
                  <span style={{ color: C.ink, marginLeft: 'auto' }}>Bs {fmt(o.monto)}</span>
                  {porOrden[o.orden_id] && (
                    <button onClick={() => ver(porOrden[o.orden_id].comprobante_id)}
                      style={chip} title="Ver el comprobante">
                      <Eye size={13} /> Foto
                    </button>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      {/* ② PARA RESOLVER — lo que pide una persona. Siempre desplegado: es a lo
          que hay que mirarle la cara antes de cerrar el lote. */}
      {porResolver.length > 0 && (
        <div style={bloque}>
          {tituloBloque('Las mira una persona', porResolver.length, C.amber)}
          <div style={{
            border: '1px solid ' + C.amber + '33', borderRadius: '9px',
            backgroundColor: C.amberBg, overflow: 'hidden',
          }}>
            {porResolver.map((o, i) => {
              const c = porOrden[o.orden_id];
              return (
                <div key={o.orden_id} style={{
                  display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
                  padding: '9px 11px', fontSize: '12.5px',
                  borderTop: i ? '1px solid ' + C.amber + '22' : 'none',
                }}>
                  <b style={{ color: C.ink }}>{o.display_id || o.orden_id}</b>
                  <span style={{ color: C.soft }}>{o.beneficiario}</span>
                  <span style={{ color: C.ink }}>Bs {fmt(o.monto)}</span>
                  <span style={{ color: C.amber, fontWeight: 600 }}>
                    {/* El motivo dice QUE HACER, no cómo se llama el estado. */}
                    {!c ? 'Sin comprobante'
                      : c.estado === 'revisar'
                        ? 'El monto de la foto no es el de la orden'
                        : 'Comprobante sin confirmar'}
                  </span>
                  {c && (
                    <>
                      <span style={{ color: C.soft }}>Leído: {loQueSeLeyo(c)}</span>
                      <div style={{ marginLeft: 'auto', display: 'flex', gap: '6px',
                        alignItems: 'flex-start', flexWrap: 'wrap' }}>
                        <button onClick={() => ver(c.comprobante_id)} style={chip}>
                          <Eye size={13} /> Ver la foto
                        </button>
                        {/* LAS DOS SALIDAS DE UNA ORDEN CON EL MONTO DISTINTO.
                            Sin ellas esta orden no se podía resolver y el lote
                            no cerraba nunca: la foto es de esa persona, así que
                            tampoco entraba en el bloque de las que no son de
                            nadie, donde están el desplegable y el descarte.

                            Mirada la foto, la respuesta es una de dos: el monto
                            está bien y la orden estaba mal cargada, o la foto no
                            corresponde. */}
                        {abiertoElLote && (
                          <button onClick={() => asignar(c.comprobante_id, o.orden_id)}
                            style={{ ...chip, color: C.green, borderColor: C.green + '55' }}
                            title="La miré y el comprobante es de esta orden">
                            <CheckCircle size={13} /> Confirmar el monto
                          </button>
                        )}
                        {abiertoElLote && (
                          <ConMotivo etiqueta="Descartar la foto" color={C.red} icono={Trash2}
                            marcador="¿Por qué? No corresponde, es de otro pago…"
                            onConfirmar={(motivo) => descartar(c.comprobante_id, motivo)} />
                        )}
                      </div>
                    </>
                  )}
                  {/* La salida de la orden que el banco NO pagó. Sólo para las
                      que no tienen foto: una con comprobante tiene la prueba de
                      que se pagó, y devolverla la haría pagar dos veces. Si esa
                      foto está mal, primero se descarta la foto. */}
                  {!c && abiertoElLote && (
                    <div style={{ marginLeft: 'auto' }}>
                      <ConMotivo etiqueta="Vuelve a la cola" color={C.red} icono={Undo2}
                        marcador="¿Por qué? El banco la rechazó, la cuenta no existe…"
                        onConfirmar={(motivo) => devolver(o.orden_id, motivo)} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ③ FOTOS SIN DUEÑO — con miniatura, porque acá la pregunta es «¿qué
          dice esta imagen?» y un renglón de texto no la contesta.
          La miniatura va SOLO en este bloque: cada foto es un pedido aparte al
          servidor con la imagen entera adentro, y ponerle miniatura a las
          dieciséis sería dieciséis descargas para mirar dos. */}
      {sinDueno.length > 0 && (
        <div style={bloque}>
          {tituloBloque('Fotos que el sistema no pudo adjudicar', sinDueno.length, C.red)}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
            {sinDueno.map((c) => {
              const e = ESTADOS[c.estado] || ESTADOS.sin_adjudicar;
              const Icono = e.icono;
              return (
                <div key={c.comprobante_id} style={{
                  width: '270px', border: '1px solid ' + C.border, borderRadius: '9px',
                  overflow: 'hidden', backgroundColor: '#fff',
                }}>
                  <Miniatura loteId={lote.lote_id} comprobanteId={c.comprobante_id}
                    onAmpliar={setMirando} />
                  <div style={{ padding: '9px 10px', fontSize: '12.5px' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: '5px',
                      padding: '3px 8px', borderRadius: '6px', fontWeight: 700,
                      color: e.color, backgroundColor: e.fondo,
                    }}>
                      <Icono size={13} /> {e.texto}
                    </span>
                    {c.motivo && (
                      <div style={{ marginTop: '4px', color: C.soft }}>{c.motivo}</div>
                    )}
                    <div style={{ marginTop: '4px', color: C.soft }}>
                      Leído: {loQueSeLeyo(c)}
                    </div>
                    {abiertoElLote && (
                      <div style={{ marginTop: '8px' }}>{selectDeOrden(c)}</div>
                    )}
                    {abiertoElLote && (
                      <ConMotivo etiqueta="Descartar" color={C.red} icono={Trash2}
                        marcador="¿Por qué? Repetida, comprobante errado…"
                        onConfirmar={(motivo) => descartar(c.comprobante_id, motivo)} />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {comprobantes.length === 0 && (
        <div style={{ padding: '18px', textAlign: 'center', fontSize: '13px', color: C.faint }}>
          Todavía no se subió ninguna foto de este lote.
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


// ─── LA MINIATURA ──────────────────────────────────────────────────────────
//
// Pide la foto sola, al montarse, y sólo se usa en el bloque de las que no
// tienen dueño. Cada imagen viaja entera adentro de la respuesta —no hay una
// versión chica en el servidor—, así que ponerle miniatura a todas las fotos
// del lote sería bajarlas todas para mirar dos.
//
// Si falla, no se rompe nada: queda el recuadro gris y el botón de ampliar
// sigue andando, porque el ampliar pide la foto por su cuenta.
function Miniatura({ loteId, comprobanteId, onAmpliar }) {
  const [imagen, setImagen] = useState(null);
  const [fallo, setFallo] = useState(false);

  useEffect(() => {
    let vivo = true;
    api.get(`/admin/lotes/${loteId}/comprobantes/${comprobanteId}/imagen`)
      .then(({ data }) => { if (vivo) setImagen(data.imagen); })
      .catch(() => { if (vivo) setFallo(true); });
    return () => { vivo = false; };
  }, [loteId, comprobanteId]);

  const marco = {
    height: '150px', display: 'flex', alignItems: 'center',
    justifyContent: 'center', backgroundColor: C.bgSubtle,
    borderBottom: '1px solid ' + C.border, overflow: 'hidden',
  };

  if (fallo) {
    return <div style={{ ...marco, fontSize: '12px', color: C.faint }}>
      No se pudo cargar la vista previa
    </div>;
  }
  if (!imagen) {
    return <div style={marco}><Loader2 size={18} className="animate-spin" style={{ color: C.faint }} /></div>;
  }
  return (
    <div style={{ ...marco, cursor: 'zoom-in' }} onClick={() => onAmpliar(imagen)}
      title="Tocá para verla en grande">
      <img src={rutaDeArchivo(imagen)} alt="Comprobante"
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
    </div>
  );
}


// ─── UNA ACCION QUE EXIGE ESCRIBIR POR QUE ─────────────────────────────────
//
// Dos toques y con el motivo escrito, a propósito. La usan las dos salidas de
// esta pantalla, y las dos dicen algo fuerte:
//
//   · descartar una foto es decir «este pago no está probado por esta foto»;
//   · devolver una orden a la cola es decir «esta se vuelve a pagar» — y si
//     resulta que sí se había pagado, se paga dos veces.
//
// Un botón suelto que lo hace de una es un clic de más en una pantalla de
// pagos. Y el motivo no es trámite: sin él, quien mire dentro de seis meses no
// puede distinguir una foto repetida de un cobro que no correspondía.
function ConMotivo({ etiqueta, marcador, color, icono: Icono, onConfirmar }) {
  const [abierto, setAbierto] = useState(false);
  const [motivo, setMotivo] = useState('');

  if (!abierto) {
    return (
      <button onClick={() => setAbierto(true)}
        style={{ ...chip, marginTop: '8px', color, borderColor: color + '55' }}>
        <Icono size={13} /> {etiqueta}
      </button>
    );
  }
  return (
    <div style={{ marginTop: '8px' }}>
      <input value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus
        placeholder={marcador}
        style={{
          width: '100%', padding: '7px 9px', borderRadius: '7px', fontSize: '12.5px',
          border: '1px solid ' + C.border, boxSizing: 'border-box',
        }} />
      <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
        <button disabled={motivo.trim().length < 4}
          onClick={() => onConfirmar(motivo)}
          style={{
            ...chip, backgroundColor: color, color: '#fff', borderColor: color,
            opacity: motivo.trim().length < 4 ? 0.5 : 1,
            cursor: motivo.trim().length < 4 ? 'not-allowed' : 'pointer',
          }}>
          {etiqueta}
        </button>
        <button onClick={() => { setAbierto(false); setMotivo(''); }} style={chip}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
