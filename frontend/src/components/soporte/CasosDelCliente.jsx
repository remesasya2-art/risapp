/**
 * CasosDelCliente.jsx — La mesa de ayuda como la ve el cliente.
 *
 * UNA SOLA PIEZA PARA LOS DOS LUGARES
 *
 *   Esto vive en el botón flotante Y en la pantalla de Soporte. Escrito dos
 *   veces se separa al primer retoque en uno solo, y el cliente no ve «dos
 *   pantallas parecidas»: ve una aplicación donde el chat de la esquina y la
 *   sección de soporte se comportan distinto sin motivo.
 *
 * QUE CAMBIA RESPECTO DEL CHAT VIEJO
 *
 *   · Sus consultas son CASOS separados, con número. La de septiembre sobre un
 *     envío y la de noviembre sobre el KYC ya no son el mismo hilo.
 *   · Elige un motivo al abrir, y eso encamina el caso al área que corresponde
 *     desde el primer mensaje en vez de hacerlo rebotar entre asesores.
 *   · Puede adjuntar una imagen. Antes sólo podía el asesor, y la mitad de los
 *     problemas se explican con una captura.
 *   · Califica CADA caso. Antes la calificación colgaba del usuario: se
 *     calificaba una vez en la vida.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import usePulso from '../../hooks/usePulso';
import { confirmar } from '../flujo/confirmar.js';
import { Plus, Send, ArrowLeft, Paperclip, X, Check, CheckCheck, MessageSquare } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { rutaDeArchivo, abrirArchivo } from '../../utils/urlDeArchivo';
import { Boton, Aviso } from '../flujo';
import { C, etiqueta, campo, ayuda } from '../flujo/estilos';
import {
  haceCuanto, nombreDeEstado, problemaParaAbrirCaso, sePuedeCalificar,
  sePuedeCerrarPorElCliente, sePuedeEscribir, tonoDeEstado,
} from '../../utils/soporte';

const TONOS = {
  exito: [C.exitoSuave, C.exito],
  alerta: [C.alertaSuave, C.alerta],
  error: [C.errorSuave, C.error],
  info: [C.marcaSuave, C.marca],
  neutro: [C.fondo, C.suave],
};

function Etiqueta({ tono, children }) {
  const [fondo, color] = TONOS[tono] || TONOS.neutro;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', padding: '3px 9px',
      borderRadius: '999px', background: fondo, color,
      fontSize: '11.5px', fontWeight: 700, whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

function Burbuja({ msg }) {
  const mio = msg.autor === 'cliente';
  return (
    <div style={{ alignSelf: mio ? 'flex-end' : 'flex-start', maxWidth: '82%' }}>
      <div style={{
        padding: '10px 14px', fontSize: '14px', lineHeight: 1.5,
        borderRadius: mio ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        background: mio ? C.marca : C.lienzo,
        color: mio ? '#fff' : C.tinta,
        border: mio ? 'none' : `1px solid ${C.linea}`,
      }}>
        {!mio ? (
          <p style={{ margin: '0 0 3px 0', fontSize: '11px', fontWeight: 700, color: C.marca }}>
            {msg.autor_nombre || 'Soporte'}
          </p>
        ) : null}
        {msg.texto ? <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.texto}</p> : null}
        {msg.adjunto && rutaDeArchivo(msg.adjunto) ? (
          <img src={rutaDeArchivo(msg.adjunto)} alt="adjunto"
            onClick={() => abrirArchivo(msg.adjunto)}
            style={{
              marginTop: msg.texto ? '8px' : 0, maxWidth: '190px', maxHeight: '190px',
              borderRadius: '10px', display: 'block', cursor: 'pointer',
            }} />
        ) : null}
      </div>
      <p style={{
        margin: '3px 6px 0', fontSize: '10.5px', color: C.tenue,
        textAlign: mio ? 'right' : 'left',
      }}>
        {new Date(msg.creado_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}
      </p>
    </div>
  );
}

/* ─── La pieza ─────────────────────────────────────────────────────────── */

export default function CasosDelCliente({ onSinLeer }) {
  const [casos, setCasos] = useState([]);
  const [motivos, setMotivos] = useState([]);
  const [abierto, setAbierto] = useState(null);   // caso_id
  const [detalle, setDetalle] = useState(null);
  const [nuevo, setNuevo] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [texto, setTexto] = useState('');
  const [adjunto, setAdjunto] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [estrellas, setEstrellas] = useState(0);
  const [comentario, setComentario] = useState('');
  const hiloRef = useRef(null);
  const previos = useRef(0);
  const turno = useRef(0);

  const traerCasos = useCallback(async () => {
    try {
      const res = await api.get('/soporte/casos');
      const lista = res.data?.casos || [];
      setCasos(lista);
      onSinLeer?.(lista.reduce((t, c) => t + (c.sin_leer_cliente || 0), 0));
    } catch { /* se reintenta en el próximo ciclo */ }
  }, [onSinLeer]);

  // Cada pedido lleva su turno. Si el cliente salta de un caso a otro, la
  // respuesta del primero puede llegar después de la del segundo: sin esto,
  // quedaría leyendo la conversación de un caso bajo el título de otro.
  const traerDetalle = useCallback(async (casoId) => {
    if (!casoId) return;
    const mio = (turno.current += 1);
    try {
      const res = await api.get(`/soporte/casos/${casoId}`);
      if (turno.current === mio) setDetalle(res.data || null);
    } catch { /* silencioso */ }
  }, []);

  useEffect(() => {
    api.get('/soporte/motivos').then((r) => setMotivos(r.data?.motivos || [])).catch(() => {});
  }, []);

  usePulso(traerCasos, 15000);
  usePulso(() => traerDetalle(abierto), 8000, abierto);

  // Baja al último mensaje sólo cuando llegan nuevos, para no robarle el
  // scroll a quien está releyendo algo de más arriba.
  useEffect(() => {
    const el = hiloRef.current;
    const cuantos = detalle?.mensajes?.length || 0;
    if (el && cuantos > previos.current) el.scrollTop = el.scrollHeight;
    previos.current = cuantos;
  }, [detalle]);

  const elegirImagen = (e) => {
    const archivo = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!archivo) return;
    if (!archivo.type.startsWith('image/')) return toast.error('Sólo imágenes');
    if (archivo.size > 1.5 * 1024 * 1024) return toast.error('La imagen no puede pasar de 1,5 MB');
    const lector = new FileReader();
    lector.onload = () => setAdjunto(lector.result);
    lector.onerror = () => toast.error('No se pudo leer la imagen');
    lector.readAsDataURL(archivo);
  };

  const problemaNuevo = problemaParaAbrirCaso({ motivo, mensaje: texto });

  const abrirCaso = async () => {
    if (problemaNuevo) return toast.error(problemaNuevo);
    setOcupado(true);
    try {
      const res = await api.post('/soporte/casos', {
        motivo, mensaje: texto.trim(), adjunto,
      });
      toast.success(`Abrimos tu caso ${res.data?.caso?.numero || ''}`);
      setNuevo(false); setMotivo(''); setTexto(''); setAdjunto(null);
      await traerCasos();
      setAbierto(res.data?.caso?.caso_id || null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo abrir el caso');
    } finally {
      setOcupado(false);
    }
  };

  const responder = async () => {
    if (!texto.trim() && !adjunto) return;
    setOcupado(true);
    try {
      await api.post(`/soporte/casos/${abierto}/mensajes`, {
        mensaje: texto.trim(), adjunto,
      });
      setTexto(''); setAdjunto(null);
      await traerDetalle(abierto);
      await traerCasos();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo enviar');
    } finally {
      setOcupado(false);
    }
  };

  const cerrarMiCaso = async () => {
    const seguro = await confirmar({
      titulo: '¿Ya no necesitás esta consulta?',
      detalle: 'Se cierra y el equipo deja de trabajarla. Vas a poder calificar '
        + 'la atención, y si vuelve a pasarte, abrir una consulta nueva.',
      accion: 'Sí, ya está',
    });
    if (!seguro) return;
    setOcupado(true);
    try {
      await api.post(`/soporte/casos/${abierto}/cerrar`);
      await traerDetalle(abierto);
      await traerCasos();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo cerrar');
    } finally {
      setOcupado(false);
    }
  };

  const calificar = async () => {
    if (estrellas < 1) return;
    setOcupado(true);
    try {
      await api.post(`/soporte/casos/${abierto}/calificar`, {
        estrellas, comentario: comentario.trim() || null,
      });
      toast.success('¡Gracias por tu calificación!');
      setEstrellas(0); setComentario('');
      await traerDetalle(abierto);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo enviar');
    } finally {
      setOcupado(false);
    }
  };

  const caso = detalle?.caso;

  /* ── Un caso abierto ─────────────────────────────────────────────── */
  if (abierto && caso) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
        <div style={{
          padding: '11px 14px', borderBottom: `1px solid ${C.linea}`,
          display: 'flex', alignItems: 'center', gap: '10px',
        }}>
          <button type="button" onClick={() => { setAbierto(null); setDetalle(null); }}
            aria-label="Volver a mis consultas" data-testid="volver-a-casos"
            style={{ border: 'none', background: 'none', cursor: 'pointer', color: C.texto, display: 'inline-flex' }}>
            <ArrowLeft size={18} />
          </button>
          <span style={{ minWidth: 0, flex: 1 }}>
            <span style={{ display: 'block', fontSize: '13.5px', fontWeight: 700, color: C.tinta, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {caso.asunto}
            </span>
            <span style={{ display: 'block', fontSize: '11px', color: C.tenue }}>{caso.numero}</span>
          </span>
          <Etiqueta tono={tonoDeEstado(caso.estado)}>{nombreDeEstado(caso.estado, 'cliente')}</Etiqueta>
          {/* El que abrió la consulta es el que sabe si ya no la necesita. Sin
              esto, la que resolvió solo se quedaba en la cola del asesor como
              trabajo pendiente y le contaba contra su tope de consultas
              abiertas. */}
          {sePuedeCerrarPorElCliente(caso) ? (
            <button type="button" onClick={cerrarMiCaso} disabled={ocupado}
              className="env-tap" data-testid="cerrar-mi-caso"
              title="Ya no necesito esta consulta"
              style={{
                border: `1px solid ${C.lineaFuerte}`, background: C.lienzo,
                borderRadius: '9px', padding: '5px 9px', cursor: 'pointer',
                color: C.suave, fontSize: '12px', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: '5px',
                whiteSpace: 'nowrap', flexShrink: 0,
              }}>
              <CheckCheck size={14} /> Ya está
            </button>
          ) : null}
        </div>

        <div ref={hiloRef} style={{
          flex: 1, overflowY: 'auto', padding: '14px', background: C.fondo,
          display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0,
        }}>
          {(detalle?.mensajes || []).map((m) => <Burbuja key={m.mensaje_id} msg={m} />)}
        </div>

        {sePuedeCalificar(caso) ? (
          <div style={{ padding: '14px', borderTop: `1px solid ${C.linea}` }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '13.5px', fontWeight: 600, color: C.tinta, textAlign: 'center' }}>
              ¿Cómo fue la atención{caso.asignado_a_nombre ? ` de ${caso.asignado_a_nombre}` : ''}?
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '5px', marginBottom: '10px' }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" onClick={() => setEstrellas(n)}
                  aria-label={`${n} estrellas`}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer', fontSize: '26px',
                    lineHeight: 1, color: n <= estrellas ? C.alerta : C.lineaFuerte,
                  }}>
                  ★
                </button>
              ))}
            </div>
            <textarea className="env-campo" rows={2} value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              placeholder="Contanos algo más (opcional)"
              style={{ ...campo, resize: 'none', marginBottom: '9px' }} />
            <Boton tipo="primario" ancho onClick={calificar} Icono={Check}
              disabled={estrellas < 1 || ocupado} testid="calificar">
              Enviar calificación
            </Boton>
          </div>
        ) : caso.calificacion ? (
          <div style={{ padding: '13px 14px', borderTop: `1px solid ${C.linea}`, background: C.exitoSuave, textAlign: 'center' }}>
            <span style={{ fontSize: '13px', color: C.exito, fontWeight: 600 }}>
              ✓ Calificaste esta atención con {caso.calificacion.estrellas} ★
            </span>
          </div>
        ) : null}

        {sePuedeEscribir(caso) ? (
          <div style={{ padding: '11px 14px', borderTop: `1px solid ${C.linea}` }}>
            {adjunto ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '9px', marginBottom: '8px' }}>
                <img src={adjunto} alt="" style={{ width: '38px', height: '38px', objectFit: 'cover', borderRadius: '8px' }} />
                <span style={{ fontSize: '12.5px', color: C.suave, flex: 1 }}>Imagen lista</span>
                <button type="button" onClick={() => setAdjunto(null)}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: C.error }}>
                  <X size={15} />
                </button>
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
              <label style={{ cursor: 'pointer', color: C.suave, padding: '10px 2px', display: 'inline-flex' }}
                title="Adjuntar imagen">
                <Paperclip size={18} />
                <input type="file" accept="image/*" onChange={elegirImagen} style={{ display: 'none' }} />
              </label>
              <textarea className="env-campo" rows={1} value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); responder(); }
                }}
                placeholder="Escribí tu mensaje…" data-testid="mensaje-cliente"
                style={{ ...campo, flex: 1, resize: 'none', borderRadius: '20px', padding: '11px 15px' }} />
              <button type="button" onClick={responder} aria-label="Enviar"
                disabled={ocupado || (!texto.trim() && !adjunto)} data-testid="enviar-cliente"
                style={{
                  width: '42px', height: '42px', borderRadius: '50%', border: 'none', flexShrink: 0,
                  background: (texto.trim() || adjunto) ? C.marca : C.lineaFuerte, color: '#fff',
                  cursor: (texto.trim() || adjunto) ? 'pointer' : 'default',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}>
                <Send size={17} />
              </button>
            </div>
          </div>
        ) : (
          <div style={{ padding: '13px 14px', borderTop: `1px solid ${C.linea}` }}>
            <Aviso tono="info" testid="caso-cerrado">
              Este caso está cerrado. Si necesitás algo más, abrí una consulta nueva.
            </Aviso>
          </div>
        )}
      </div>
    );
  }

  /* ── Abrir una consulta nueva ────────────────────────────────────── */
  if (nuevo) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
        <div style={{ padding: '11px 14px', borderBottom: `1px solid ${C.linea}`, display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button type="button" onClick={() => setNuevo(false)} aria-label="Volver"
            style={{ border: 'none', background: 'none', cursor: 'pointer', color: C.texto, display: 'inline-flex' }}>
            <ArrowLeft size={18} />
          </button>
          <strong style={{ fontSize: '14px', color: C.tinta }}>Nueva consulta</strong>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 14px', minHeight: 0 }}>
          <label style={etiqueta} htmlFor="sc-motivo">¿Sobre qué es?</label>
          <select id="sc-motivo" className="env-campo" style={{ ...campo, marginBottom: '14px' }}
            value={motivo} onChange={(e) => setMotivo(e.target.value)} data-testid="motivo">
            <option value="">Elegí una opción…</option>
            {motivos.map((m) => <option key={m.clave} value={m.clave}>{m.texto}</option>)}
          </select>
          <p style={{ ...ayuda, marginTop: '-10px', marginBottom: '14px' }}>
            Nos ayuda a mandarte con quien puede resolverlo, sin pasarte de área en área.
          </p>

          <label style={etiqueta} htmlFor="sc-texto">Contanos qué pasó</label>
          <textarea id="sc-texto" className="env-campo" rows={5} value={texto}
            onChange={(e) => setTexto(e.target.value)} data-testid="texto-nuevo"
            placeholder="Cuanto más nos cuentes, menos vamos a tener que preguntarte."
            style={{ ...campo, resize: 'vertical', lineHeight: 1.5 }} />

          <div style={{ marginTop: '12px' }}>
            {adjunto ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '9px' }}>
                <img src={adjunto} alt="" style={{ width: '44px', height: '44px', objectFit: 'cover', borderRadius: '8px' }} />
                <span style={{ fontSize: '12.5px', color: C.suave, flex: 1 }}>Imagen adjunta</span>
                <button type="button" onClick={() => setAdjunto(null)}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: C.error }}>
                  <X size={15} />
                </button>
              </div>
            ) : (
              <label style={{
                display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer',
                fontSize: '13px', color: C.marca, fontWeight: 600,
              }}>
                <Paperclip size={15} /> Adjuntar una captura
                <input type="file" accept="image/*" onChange={elegirImagen} style={{ display: 'none' }} />
              </label>
            )}
          </div>
        </div>

        <div style={{ padding: '12px 14px', borderTop: `1px solid ${C.linea}` }}>
          <Boton tipo="primario" ancho onClick={abrirCaso} Icono={Send}
            disabled={ocupado || Boolean(problemaNuevo)} testid="abrir-caso">
            {ocupado ? 'Enviando…' : 'Enviar consulta'}
          </Boton>
          {problemaNuevo ? <p style={{ ...ayuda, textAlign: 'center' }}>{problemaNuevo}</p> : null}
        </div>
      </div>
    );
  }

  /* ── La lista de mis consultas ───────────────────────────────────── */
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {casos.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '38px 20px', color: C.tenue }}>
            <MessageSquare size={42} style={{ opacity: 0.4 }} />
            <p style={{ fontSize: '14px', color: C.suave, margin: '12px 0 0 0' }}>
              Todavía no nos escribiste.
            </p>
            <p style={{ ...ayuda }}>Abrí una consulta y te respondemos.</p>
          </div>
        ) : casos.map((c) => (
          <button key={c.caso_id} type="button" onClick={() => setAbierto(c.caso_id)}
            className="env-tap" data-testid={`mi-caso-${c.caso_id}`}
            style={{
              display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
              padding: '13px 15px', border: 'none', background: 'transparent',
              borderBottom: `1px solid ${C.linea}`,
            }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Etiqueta tono={tonoDeEstado(c.estado)}>{nombreDeEstado(c.estado, 'cliente')}</Etiqueta>
              <span style={{ fontSize: '11px', color: C.tenue }}>{c.numero}</span>
              <span style={{ flex: 1 }} />
              {c.sin_leer_cliente > 0 ? (
                <span style={{
                  background: C.error, color: '#fff', borderRadius: '999px',
                  padding: '1px 7px', fontSize: '11px', fontWeight: 700,
                }}>
                  {c.sin_leer_cliente}
                </span>
              ) : null}
            </span>
            <span style={{
              display: 'block', fontSize: '14px', fontWeight: 600, color: C.tinta,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {c.asunto}
            </span>
            <span style={{ display: 'block', fontSize: '11.5px', color: C.tenue, marginTop: '3px' }}>
              {haceCuanto(c.ultimo_mensaje_en || c.creado_en)}
            </span>
          </button>
        ))}
      </div>
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${C.linea}` }}>
        <Boton tipo="primario" ancho onClick={() => setNuevo(true)} Icono={Plus}
          testid="nueva-consulta">
          Nueva consulta
        </Boton>
      </div>
    </div>
  );
}
