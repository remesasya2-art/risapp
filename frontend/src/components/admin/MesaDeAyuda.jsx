/**
 * MesaDeAyuda.jsx — La consola del asesor.
 *
 * QUE REEMPLAZA
 *
 *   La pestaña de chat del panel: una lista de personas y una caja de texto.
 *   El asesor tenía dos botones —tomar y soltar— y respondía a ciegas: para
 *   saber si el cliente tenía saldo, si estaba verificado o qué operación
 *   reclamaba, había que abrir otra pestaña y buscarlo por correo.
 *
 * LAS TRES COLUMNAS, Y POR QUE ESTAN EN UNA SOLA PANTALLA
 *
 *   IZQUIERDA · La bandeja, ordenada por lo que hay que hacer ahora: primero
 *   lo escalado, después lo que nadie tomó, después la prioridad. No por lo
 *   más reciente, que es lo que hacía la lista vieja y dejaba abajo al que
 *   llevaba tres horas esperando.
 *
 *   CENTRO · La conversación, con las notas internas y las líneas de sistema
 *   —quién lo tomó, quién lo transfirió y por qué— EN EL MISMO HILO. Un
 *   registro aparte no lo abre nadie; acá el que entra al caso lee la historia
 *   completa en orden.
 *
 *   DERECHA · El cliente y las herramientas. La ficha con saldo, verificación
 *   y últimas operaciones viene en la misma respuesta que el caso, así que no
 *   hay una segunda pantalla que abrir. Y debajo, lo que el asesor puede hacer
 *   sin soltar al cliente: cambiar el estado, transferir, escalar y pedirle
 *   algo a otra área.
 *
 * LO QUE DECIDE ESTA PANTALLA Y LO QUE NO
 *
 *   Qué botón se ve apagado sale de `utils/soporte.js`, que espeja al backend
 *   y se prueba. Acá no hay ninguna regla escrita a mano: si un botón se
 *   ofrece, el servidor lo va a aceptar.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import usePulso from '../../hooks/usePulso';
import {
  MessageSquare, Send, Lock, ArrowRightLeft, AlertTriangle, HelpCircle,
  Paperclip, X, Search, User, Wallet, ShieldCheck, Clock, Hash, Inbox,
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { fmt } from '../../utils/format';
import { rutaDeArchivo, abrirArchivo } from '../../utils/urlDeArchivo';
import { Boton, Aviso } from '../flujo';
import { C, HOJA, tarjeta, etiqueta, campo, ayuda } from '../flujo/estilos';
import { confirmar } from '../flujo/confirmar.js';
import {
  accionesDelAsesor, estadosPosibles, haceCuanto, nombreDeEstado, PRIORIDADES,
  problemaDelEscalamiento, problemaDelPedido, problemaDeLaTransferencia,
  problemaDeLaRespuestaAlPedido, minutosSinRespuesta, duracion, semaforo, tonoDeEstado,
} from '../../utils/soporte';

/* ─── Piezas ───────────────────────────────────────────────────────────── */

const COLOR_SEMAFORO = { rojo: C.error, amarillo: C.alerta, verde: C.exito };

const TONOS = {
  exito: [C.exitoSuave, C.exito],
  alerta: [C.alertaSuave, C.alerta],
  error: [C.errorSuave, C.error],
  info: [C.marcaSuave, C.marca],
  neutro: [C.fondo, C.suave],
};

function Etiqueta({ tono = 'neutro', children }) {
  const [fondo, color] = TONOS[tono] || TONOS.neutro;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 9px', borderRadius: '999px', background: fondo, color,
      fontSize: '11.5px', fontWeight: 700, whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

/** Una fila de la bandeja. */
function FilaDeCaso({ caso, elegido, onClick, ahora }) {
  const luz = COLOR_SEMAFORO[semaforo(caso, ahora)];
  const esperando = minutosSinRespuesta(caso, ahora);
  return (
    <button type="button" onClick={onClick} className="env-tap"
      data-testid={`caso-${caso.caso_id}`}
      style={{
        display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
        padding: '12px 14px', border: 'none',
        borderLeft: `3px solid ${elegido ? C.marca : 'transparent'}`,
        borderBottom: `1px solid ${C.linea}`,
        background: elegido ? C.marcaSuave : 'transparent',
      }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '3px' }}>
        {caso.escalado ? <AlertTriangle size={13} color={C.error} /> : null}
        {luz ? (
          <span title="Tiempo sin primera respuesta" style={{
            width: '8px', height: '8px', borderRadius: '50%', background: luz, flexShrink: 0,
          }} />
        ) : null}
        <span style={{ fontSize: '11.5px', fontWeight: 700, color: C.tenue }}>
          {caso.numero}
        </span>
        <span style={{ flex: 1 }} />
        {caso.sin_leer_asesor > 0 ? (
          <span style={{
            background: C.error, color: '#fff', borderRadius: '999px',
            padding: '1px 7px', fontSize: '11px', fontWeight: 700,
          }}>
            {caso.sin_leer_asesor}
          </span>
        ) : null}
      </span>
      <span style={{
        display: 'block', fontSize: '14px', fontWeight: 600, color: C.tinta,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {caso.user_name || 'Usuario'}
      </span>
      <span style={{
        display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {caso.asunto}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '6px', flexWrap: 'wrap' }}>
        <Etiqueta tono={tonoDeEstado(caso.estado)}>{nombreDeEstado(caso.estado)}</Etiqueta>
        {caso.prioridad !== 'normal' ? (
          <Etiqueta tono={caso.prioridad === 'urgente' ? 'error' : 'alerta'}>
            {caso.prioridad}
          </Etiqueta>
        ) : null}
        {/* Cuando la pelota la tiene la casa se dice así, y no «hace 3 h» a
            secas: es la diferencia entre un caso que está esperando y uno
            donde ya contestamos. Y es lo que decide el orden de esta lista,
            así que el asesor puede explicarse por qué está donde está. */}
        {esperando !== null ? (
          <span style={{ fontSize: '11px', color: C.error, fontWeight: 600 }}>
            Espera hace {duracion(esperando)}
          </span>
        ) : (
          <span style={{ fontSize: '11px', color: C.tenue }}>
            {haceCuanto(caso.ultimo_mensaje_en || caso.creado_en, ahora)}
          </span>
        )}
      </span>
      {caso.asignado_a_nombre ? (
        <span style={{ display: 'block', fontSize: '11px', color: C.exito, marginTop: '4px', fontWeight: 600 }}>
          ● {caso.asignado_a_nombre}
        </span>
      ) : null}
    </button>
  );
}

/** Un mensaje del hilo. Tres formas distintas, y se distinguen de un vistazo. */
function Mensaje({ msg }) {
  if (msg.autor === 'sistema') {
    return (
      <div style={{ alignSelf: 'center', maxWidth: '90%', textAlign: 'center' }}>
        <span style={{
          display: 'inline-block', padding: '5px 12px', borderRadius: '999px',
          background: C.fondo, border: `1px solid ${C.linea}`,
          fontSize: '11.5px', color: C.suave, lineHeight: 1.5,
        }}>
          {msg.texto}
        </span>
      </div>
    );
  }

  const delAsesor = msg.autor === 'asesor';
  // La nota interna se ve DISTINTA, no sólo etiquetada. Un asesor apurado
  // mirando de reojo tiene que saber que eso no lo leyó el cliente.
  const interno = msg.interno;
  return (
    <div style={{ alignSelf: delAsesor ? 'flex-end' : 'flex-start', maxWidth: '78%' }}>
      <div style={{
        padding: '10px 14px', borderRadius: '14px', fontSize: '14px', lineHeight: 1.5,
        background: interno ? C.alertaSuave : (delAsesor ? C.marca : C.lienzo),
        color: interno ? C.texto : (delAsesor ? '#fff' : C.tinta),
        border: interno ? `1px dashed ${C.alertaBorde}`
          : (delAsesor ? 'none' : `1px solid ${C.linea}`),
      }}>
        <p style={{
          margin: '0 0 4px 0', fontSize: '11px', fontWeight: 700,
          color: interno ? C.alerta : (delAsesor ? 'rgba(255,255,255,.85)' : C.marca),
        }}>
          {interno ? '🔒 Nota interna · ' : ''}{msg.autor_nombre || (delAsesor ? 'Soporte' : 'Cliente')}
        </p>
        {msg.texto ? <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.texto}</p> : null}
        {msg.adjunto && rutaDeArchivo(msg.adjunto) ? (
          <img src={rutaDeArchivo(msg.adjunto)} alt="adjunto"
            onClick={() => abrirArchivo(msg.adjunto)}
            style={{
              marginTop: msg.texto ? '8px' : 0, maxWidth: '220px', maxHeight: '220px',
              borderRadius: '10px', display: 'block', cursor: 'pointer',
            }} />
        ) : null}
      </div>
      <p style={{
        margin: '3px 6px 0', fontSize: '10.5px', color: C.tenue,
        textAlign: delAsesor ? 'right' : 'left',
      }}>
        {new Date(msg.creado_en).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })}
      </p>
    </div>
  );
}

/** La ventana de transferir / pedir / escalar. Una sola, con tres formas. */
function VentanaDeAccion({ accion, areas, asesores, onCerrar, onConfirmar, ocupado }) {
  const [area, setArea] = useState('');
  const [asesorId, setAsesorId] = useState('');
  const [texto, setTexto] = useState('');

  const problema = accion === 'transferir' ? problemaDeLaTransferencia({ area, nota: texto })
    : accion === 'pedir' ? problemaDelPedido({ area, detalle: texto })
      : problemaDelEscalamiento(texto);

  const titulos = {
    transferir: 'Transferir el caso',
    pedir: 'Pedirle algo a otra área',
    escalar: 'Escalar a un super administrador',
  };
  const detalles = {
    transferir: 'El caso pasa a esa área. Vos dejás de ser quien le habla al cliente.',
    pedir: 'Vos seguís atendiendo. La respuesta te vuelve al caso como nota interna.',
    escalar: 'El caso sube a lo más alto de la lista y se avisa a los super administradores.',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000, padding: '16px',
      background: 'rgba(16,24,40,.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div role="dialog" aria-modal="true" data-testid="ventana-accion"
        style={{ ...tarjeta, padding: '22px', width: '100%', maxWidth: '460px' }}>
        <h3 style={{ margin: '0 0 4px 0', fontSize: '17px', fontWeight: 700, color: C.tinta }}>
          {titulos[accion]}
        </h3>
        <p style={{ ...ayuda, marginBottom: '16px' }}>{detalles[accion]}</p>

        {accion !== 'escalar' ? (
          <div style={{ marginBottom: '12px' }}>
            <label style={etiqueta} htmlFor="ma-area">Área</label>
            <select id="ma-area" className="env-campo" style={campo} value={area}
              onChange={(e) => { setArea(e.target.value); setAsesorId(''); }}>
              <option value="">Elegí un área…</option>
              {areas.map((a) => <option key={a.clave} value={a.clave}>{a.nombre}</option>)}
            </select>
          </div>
        ) : null}

        {accion === 'transferir' && area ? (
          <div style={{ marginBottom: '12px' }}>
            <label style={etiqueta} htmlFor="ma-asesor">¿A alguien en particular?</label>
            <select id="ma-asesor" className="env-campo" style={campo} value={asesorId}
              onChange={(e) => setAsesorId(e.target.value)}>
              <option value="">A quien esté libre en el área</option>
              {asesores.map((a) => (
                <option key={a.user_id} value={a.user_id}>
                  {a.nombre}{a.cargo ? ` · ${a.cargo}` : ''}
                </option>
              ))}
            </select>
            <p style={ayuda}>Sin elegir a nadie, el caso queda en la bandeja del área.</p>
          </div>
        ) : null}

        <div style={{ marginBottom: '14px' }}>
          <label style={etiqueta} htmlFor="ma-texto">
            {accion === 'transferir' ? 'Qué se hizo y qué falta'
              : accion === 'pedir' ? 'Qué necesitás' : 'Por qué lo escalás'}
          </label>
          <textarea id="ma-texto" className="env-campo" rows={4} value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={accion === 'transferir'
              ? 'Ya verifiqué que el envío salió el martes. Falta confirmar si el banco lo devolvió.'
              : accion === 'pedir'
                ? 'El cliente subió el DNI el lunes y sigue pendiente. ¿Pueden revisarlo?'
                : 'Reclama una operación de hace 20 días y no puedo resolverlo con lo que tengo.'}
            style={{ ...campo, resize: 'vertical', lineHeight: 1.5 }} />
        </div>

        {problema ? (
          <div style={{ marginBottom: '14px' }}>
            <Aviso tono="error" testid="problema-accion">{problema}</Aviso>
          </div>
        ) : null}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <Boton onClick={onCerrar}>Cancelar</Boton>
          <Boton tipo={accion === 'escalar' ? 'peligro' : 'primario'}
            disabled={Boolean(problema) || ocupado} testid="confirmar-accion"
            onClick={() => onConfirmar({ area, asesorId: asesorId || null, texto: texto.trim() })}>
            {ocupado ? 'Enviando…' : titulos[accion]}
          </Boton>
        </div>
      </div>
    </div>
  );
}

/**
 * Los pedidos que le hicieron a MI área.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   Un asesor de soporte puede pedirle algo a Finanzas o a Verificaciones sin
 *   soltar el caso: sigue con el cliente y en paralelo pregunta a quien puede
 *   resolver. Eso está bien de este lado. Del otro lado, el pedido llegaba
 *   como un aviso y nada más: quien tenía que contestarlo no tenía dónde. El
 *   circuito quedaba abierto y el cliente esperando algo que nadie podía
 *   cerrar.
 *
 *   Acá se contesta. La respuesta vuelve al caso como nota interna —no como
 *   mensaje al cliente— porque traducir lo que dice Finanzas es trabajo del
 *   asesor que lo está atendiendo, que sabe qué le preguntaron.
 */
function Pedidos({ pedidos, areas, onResponder, ocupado }) {
  const [respuestas, setRespuestas] = useState({});

  const escribir = (id, texto) => setRespuestas((r) => ({ ...r, [id]: texto }));

  if (areas.length === 0) {
    return (
      <div style={{ ...tarjeta, padding: '40px 20px', textAlign: 'center' }}>
        <Inbox size={44} color={C.tenue} style={{ opacity: 0.4 }} />
        <p style={{ ...ayuda, marginTop: '10px' }}>
          Los pedidos los contesta el área que puede resolverlos. No tenés
          ninguna a cargo, así que acá no te va a llegar nada.
        </p>
      </div>
    );
  }

  return (
    <div style={{ ...tarjeta, padding: '16px', overflowY: 'auto', height: '100%' }}>
      <p style={{ ...ayuda, margin: '0 0 14px 0' }}>
        Te llegan los pedidos de {areas.length === 1 ? 'tu área' : 'tus áreas'}.
        Lo que contestes vuelve al caso como nota interna y lo lee el asesor que
        está con el cliente.
      </p>

      {pedidos.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '34px 16px' }}>
          <Inbox size={44} color={C.tenue} style={{ opacity: 0.4 }} />
          <p style={{ ...ayuda, marginTop: '10px' }}>No hay pedidos pendientes.</p>
        </div>
      ) : pedidos.map((p) => {
        const texto = respuestas[p.pedido_id] || '';
        const problema = problemaDeLaRespuestaAlPedido(texto);
        return (
          <div key={p.pedido_id} style={{
            border: `1px solid ${C.linea}`, borderRadius: '12px',
            padding: '14px', marginBottom: '11px', background: C.lienzo,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: '4px',
                padding: '3px 9px', borderRadius: '999px',
                background: C.marcaSuave, color: C.marca,
                fontSize: '11.5px', fontWeight: 700,
              }}>
                <Hash size={12} />{(p.caso_numero || '').replace(/^S-/, '')}
              </span>
              <span style={{ fontSize: '13px', fontWeight: 600, color: C.tinta }}>
                {p.pedido_por_nombre}
              </span>
              <span style={{ ...ayuda, margin: 0 }}>· {haceCuanto(p.creado_en)}</span>
            </div>

            <p style={{ margin: '0 0 11px 0', fontSize: '13.5px', color: C.texto, whiteSpace: 'pre-wrap' }}>
              {p.detalle}
            </p>

            <textarea className="env-campo" rows={2} value={texto}
              placeholder="Qué encontraste, qué se hizo, qué falta"
              onChange={(e) => escribir(p.pedido_id, e.target.value)}
              style={{ ...campo, fontSize: '13.5px', resize: 'vertical', marginBottom: '9px' }} />

            <div style={{
              display: 'flex', justifyContent: 'flex-end',
              alignItems: 'center', gap: '11px',
            }}>
              {/* Lo apagado dice por qué: un botón gris sin explicación deja a
                  quien lo mira probando cosas hasta que se enciende. */}
              {problema && texto ? (
                <span style={{ ...ayuda, margin: 0, textAlign: 'right' }}>{problema}</span>
              ) : null}
              <Boton tipo="primario" Icono={Send} testid={`responder-${p.pedido_id}`}
                disabled={Boolean(problema) || ocupado}
                onClick={async () => {
                  const ok = await onResponder(p.pedido_id, texto.trim());
                  if (ok) escribir(p.pedido_id, '');
                }}>
                {ocupado ? 'Enviando…' : 'Responder'}
              </Boton>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── La consola ───────────────────────────────────────────────────────── */

export default function MesaDeAyuda({ usuario }) {
  const [casos, setCasos] = useState([]);
  const [elegido, setElegido] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const turno = useRef(0);
  const [filtro, setFiltro] = useState('abiertos');
  const [soloMios, setSoloMios] = useState(false);
  const [buscar, setBuscar] = useState('');
  // Lo que se escribe y lo que se busca son dos cosas. Con una sola, cada
  // tecla dispara una consulta: escribir un correo son treinta pedidos al
  // servidor y treinta redibujados de la lista debajo del dedo.
  const [busqueda, setBusqueda] = useState('');
  const [respuesta, setRespuesta] = useState('');
  const [interno, setInterno] = useState(false);
  const [adjunto, setAdjunto] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [ventana, setVentana] = useState(null);
  const [areas, setAreas] = useState([]);
  const [asesores, setAsesores] = useState([]);
  const [rapidas, setRapidas] = useState([]);
  const [ahora, setAhora] = useState(() => Date.now());
  const [vista, setVista] = useState('casos');       // 'casos' | 'pedidos'
  const [pedidos, setPedidos] = useState([]);
  const [misAreas, setMisAreas] = useState([]);
  const hiloRef = useRef(null);
  const cantidadPrevia = useRef(0);

  const esSuperAdmin = usuario?.role === 'super_admin';
  const acciones = accionesDelAsesor({
    caso: detalle?.caso, yo: usuario?.user_id, esSuperAdmin,
  });

  const traerCasos = useCallback(async () => {
    try {
      const res = await api.get('/admin/soporte/casos', {
        params: { estado: filtro, mios: soloMios, buscar: busqueda || undefined },
      });
      setCasos(res.data?.casos || []);
    } catch { /* la lista se reintenta sola en el próximo ciclo */ }
  }, [filtro, soloMios, busqueda]);

  // Los pedidos de MI área. Se traen siempre, no sólo con la pestaña abierta:
  // el número en la solapa es lo único que le avisa al encargado que alguien
  // está esperando una respuesta suya.
  const traerPedidos = useCallback(async () => {
    try {
      const res = await api.get('/admin/soporte/pedidos', { params: { pendientes: true } });
      setPedidos(res.data?.pedidos || []);
      setMisAreas(res.data?.areas || []);
    } catch { /* se reintenta en el próximo ciclo */ }
  }, []);

  // Medio segundo de pausa antes de buscar: el tiempo que tarda alguien en
  // dejar de tipear, y el que hace que la lista no salte mientras escribe.
  useEffect(() => {
    const id = setTimeout(() => setBusqueda(buscar.trim()), 500);
    return () => clearTimeout(id);
  }, [buscar]);

  // Cada pedido lleva su turno, y sólo el último manda. Sin esto, saltar de un
  // caso a otro mientras el primero todavía viaja deja al asesor leyendo la
  // conversación de un cliente bajo el nombre de otro: el peor error posible
  // en esta pantalla, porque no se nota.
  const traerDetalle = useCallback(async (casoId) => {
    if (!casoId) return;
    const mio = (turno.current += 1);
    try {
      const res = await api.get(`/admin/soporte/casos/${casoId}`);
      if (turno.current === mio) setDetalle(res.data || null);
    } catch { /* silencioso: el caso pudo haberse cerrado en otra pestaña */ }
  }, []);

  useEffect(() => {
    api.get('/admin/soporte/areas').then((r) => setAreas(r.data?.areas || [])).catch(() => {});
    api.get('/admin/quick-replies').then((r) => setRapidas(r.data || [])).catch(() => {});
  }, []);

  // La bandeja se refresca sola. Antes el reloj vivía dentro del efecto del
  // caso elegido: el asesor que miraba la lista sin abrir nada no veía entrar
  // un caso nuevo hasta que abría alguno o recargaba la pantalla.
  usePulso(traerCasos, 12000, `${filtro}|${soloMios}|${busqueda}`);
  usePulso(traerPedidos, 20000);

  // El reloj de la pantalla. Sin esto el semáforo se quedaría en el color que
  // tenía al cargar, y un caso que entra en rojo mientras el asesor mira la
  // lista no se pondría en rojo hasta el próximo refresco. Va por `usePulso`
  // para que además se ponga en hora ni bien el asesor vuelve a la pestaña.
  usePulso(() => setAhora(Date.now()), 30000);

  usePulso(() => traerDetalle(elegido), 6000, elegido);

  // Bajar al último mensaje SOLO cuando llegan nuevos: en cada refresco robaría
  // el scroll al asesor que está releyendo algo de más arriba.
  useEffect(() => {
    const el = hiloRef.current;
    const cuantos = detalle?.mensajes?.length || 0;
    if (el && cuantos > cantidadPrevia.current) el.scrollTop = el.scrollHeight;
    cantidadPrevia.current = cuantos;
  }, [detalle]);

  useEffect(() => {
    if (ventana !== 'transferir') return;
    api.get('/admin/soporte/asesores').then((r) => setAsesores(r.data?.asesores || []))
      .catch(() => setAsesores([]));
  }, [ventana]);

  const conAviso = async (accion, exito) => {
    setOcupado(true);
    try {
      await accion();
      if (exito) toast.success(exito);
      await traerDetalle(elegido);
      await traerCasos();
      return true;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo completar');
      return false;
    } finally {
      setOcupado(false);
    }
  };

  const enviar = async () => {
    const texto = respuesta.trim();
    if (!texto && !adjunto) return;
    const ok = await conAviso(
      () => api.post(`/admin/soporte/casos/${elegido}/mensajes`,
        { mensaje: texto, adjunto, interno }),
      interno ? 'Nota interna guardada' : 'Respuesta enviada');
    if (ok) { setRespuesta(''); setAdjunto(null); }
  };

  const cambiarEstado = async (estado) => {
    if (estado === 'cerrado') {
      const seguro = await confirmar({
        titulo: '¿Cerrar el caso?',
        detalle: 'Cerrado no se reabre: si el cliente vuelve, va a abrir uno nuevo. '
          + 'Si creés que puede faltar algo, dejalo en «resuelto».',
        accion: 'Cerrar el caso',
        tono: 'peligro',
      });
      if (!seguro) return;
    }
    await conAviso(
      () => api.post(`/admin/soporte/casos/${elegido}/estado`, { estado }),
      `Caso en «${nombreDeEstado(estado)}»`);
  };

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

  const confirmarVentana = async ({ area, asesorId, texto }) => {
    const url = `/admin/soporte/casos/${elegido}`;
    const llamadas = {
      transferir: () => api.post(`${url}/transferir`, { area, asesor_id: asesorId, nota: texto }),
      pedir: () => api.post(`${url}/pedidos`, { area, detalle: texto }),
      escalar: () => api.post(`${url}/escalar`, { motivo: texto }),
    };
    const exitos = {
      transferir: 'Caso transferido',
      pedir: 'Pedido enviado al área',
      escalar: 'Caso escalado',
    };
    const ok = await conAviso(llamadas[ventana], exitos[ventana]);
    if (ok) setVentana(null);
  };

  const responderPedido = async (pedidoId, texto) => {
    setOcupado(true);
    try {
      await api.post(`/admin/soporte/pedidos/${pedidoId}/responder`, { respuesta: texto });
      toast.success('Respuesta enviada al caso');
      await traerPedidos();
      // El caso quedó tocado: si es el que está abierto, la nota tiene que
      // aparecer en el hilo sin esperar la próxima vuelta del reloj.
      if (elegido) await traerDetalle(elegido);
      return true;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo responder');
      return false;
    } finally {
      setOcupado(false);
    }
  };

  const caso = detalle?.caso;
  const cliente = detalle?.cliente || {};

  return (
    <div className="env" style={{ fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif' }}>
      <style>{HOJA}</style>

      {/* ── Las dos bandejas ────────────────────────────────────────────
          Casos es lo que el asesor atiende; Pedidos es lo que le pidieron a
          su área desde el caso de otro. Son dos colas distintas y con dos
          responsables distintos: mezclarlas hacía que la segunda no existiera
          para nadie. El número al lado es lo único que avisa. */}
      <div style={{ display: 'flex', gap: '7px', marginBottom: '12px' }}>
        {[
          { clave: 'casos', texto: 'Casos', cuenta: 0 },
          { clave: 'pedidos', texto: 'Pedidos a mi área', cuenta: pedidos.length },
        ].map((t) => (
          <button key={t.clave} type="button" onClick={() => setVista(t.clave)}
            className="env-chip" data-testid={`vista-${t.clave}`}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px',
              padding: '8px 15px', borderRadius: '10px', cursor: 'pointer',
              border: `1px solid ${vista === t.clave ? C.marca : C.lineaFuerte}`,
              background: vista === t.clave ? C.marcaSuave : C.lienzo,
              color: vista === t.clave ? C.marca : C.suave,
              fontSize: '13.5px', fontWeight: 600,
            }}>
            {t.texto}
            {t.cuenta > 0 ? (
              <span style={{
                minWidth: '19px', height: '19px', padding: '0 5px',
                borderRadius: '999px', background: C.error, color: '#fff',
                fontSize: '11px', fontWeight: 700,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {t.cuenta}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {vista === 'pedidos' ? (
        <div style={{ height: 'calc(100vh - 232px)', minHeight: '480px' }}>
          <Pedidos pedidos={pedidos} areas={misAreas}
            onResponder={responderPedido} ocupado={ocupado} />
        </div>
      ) : (
      <div style={{ display: 'flex', gap: '14px', height: 'calc(100vh - 232px)', minHeight: '520px' }}>

        {/* ── La bandeja ────────────────────────────────────────────── */}
        <div style={{ ...tarjeta, width: '310px', flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '12px 14px', borderBottom: `1px solid ${C.linea}` }}>
            <div style={{ position: 'relative', marginBottom: '10px' }}>
              <Search size={15} color={C.tenue} style={{ position: 'absolute', left: '11px', top: '13px' }} />
              <input className="env-campo" placeholder="Número, nombre o correo"
                value={buscar} onChange={(e) => setBuscar(e.target.value)}
                style={{ ...campo, padding: '9px 12px 9px 32px', fontSize: '13.5px' }} />
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {[['abiertos', 'Abiertos'], ['todos', 'Todos'], ['cerrado', 'Cerrados']].map(([v, t]) => (
                <button key={v} type="button" onClick={() => setFiltro(v)} className="env-chip"
                  style={{
                    padding: '5px 11px', borderRadius: '999px', cursor: 'pointer',
                    border: `1px solid ${filtro === v ? C.marca : C.lineaFuerte}`,
                    background: filtro === v ? C.marcaSuave : C.lienzo,
                    color: filtro === v ? C.marca : C.suave,
                    fontSize: '12px', fontWeight: 600,
                  }}>
                  {t}
                </button>
              ))}
              <button type="button" onClick={() => setSoloMios((s) => !s)} className="env-chip"
                style={{
                  padding: '5px 11px', borderRadius: '999px', cursor: 'pointer',
                  border: `1px solid ${soloMios ? C.marca : C.lineaFuerte}`,
                  background: soloMios ? C.marcaSuave : C.lienzo,
                  color: soloMios ? C.marca : C.suave, fontSize: '12px', fontWeight: 600,
                }}>
                Míos
              </button>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {casos.length === 0 ? (
              <p style={{ ...ayuda, textAlign: 'center', padding: '30px 16px' }}>
                No hay casos con este filtro.
              </p>
            ) : casos.map((c) => (
              <FilaDeCaso key={c.caso_id} caso={c} ahora={ahora}
                elegido={elegido === c.caso_id} onClick={() => { setDetalle(null); setElegido(c.caso_id); }} />
            ))}
          </div>
        </div>

        {/* ── La conversación ───────────────────────────────────────── */}
        <div style={{ ...tarjeta, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {!caso ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ textAlign: 'center', color: C.tenue }}>
                <MessageSquare size={52} style={{ opacity: 0.35 }} />
                <p style={{ fontSize: '14px', marginTop: '10px' }}>Elegí un caso de la izquierda.</p>
              </div>
            </div>
          ) : (
            <>
              <div style={{ padding: '13px 18px', borderBottom: `1px solid ${C.linea}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '9px', flexWrap: 'wrap' }}>
                  <Hash size={14} color={C.tenue} />
                  <strong style={{ fontSize: '13px', color: C.tenue }}>{caso.numero}</strong>
                  <Etiqueta tono={tonoDeEstado(caso.estado)}>{nombreDeEstado(caso.estado)}</Etiqueta>
                  {caso.escalado ? <Etiqueta tono="error"><AlertTriangle size={11} /> Escalado</Etiqueta> : null}
                  <span style={{ flex: 1 }} />
                  {acciones.tomar.puede ? (
                    <Boton tipo="primario" onClick={() => conAviso(
                      () => api.post(`/admin/soporte/casos/${elegido}/tomar`), 'Tomaste el caso')}
                      disabled={ocupado} testid="tomar-caso">
                      Atender este caso
                    </Boton>
                  ) : null}
                  {acciones.soltar.puede ? (
                    <Boton onClick={() => conAviso(
                      () => api.post(`/admin/soporte/casos/${elegido}/soltar`), 'Caso liberado')}
                      disabled={ocupado}>
                      Soltar
                    </Boton>
                  ) : null}
                </div>
                <p style={{ margin: '7px 0 0 0', fontSize: '15px', fontWeight: 700, color: C.tinta }}>
                  {caso.asunto}
                </p>
                {caso.escalado && caso.escalado_motivo ? (
                  <p style={{ margin: '6px 0 0 0', fontSize: '12.5px', color: C.error }}>
                    Escalado por {caso.escalado_por_nombre}: {caso.escalado_motivo}
                  </p>
                ) : null}
              </div>

              <div ref={hiloRef} style={{
                flex: 1, overflowY: 'auto', padding: '16px 18px', background: C.fondo,
                display: 'flex', flexDirection: 'column', gap: '11px',
              }}>
                {(detalle?.mensajes || []).map((m) => <Mensaje key={m.mensaje_id} msg={m} />)}
              </div>

              {/* ── Escribir ──────────────────────────────────────── */}
              <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.linea}` }}>
                {!acciones.responder.puede && !interno ? (
                  <div style={{ marginBottom: '10px' }}>
                    <Aviso tono="alerta" testid="no-podes-responder">
                      {acciones.responder.porque}
                    </Aviso>
                  </div>
                ) : null}

                {rapidas.length > 0 && acciones.responder.puede ? (
                  <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', marginBottom: '9px', paddingBottom: '3px' }}>
                    {rapidas.map((r) => (
                      <button key={r.qr_id} type="button" className="env-chip"
                        onClick={() => setRespuesta((p) => (p ? `${p} ` : '')
                          + r.text.replace(/\{nombre\}/g, (caso.user_name || '').split(' ')[0] || 'cliente'))}
                        style={{
                          padding: '5px 11px', borderRadius: '999px', flexShrink: 0,
                          border: `1px solid ${C.lineaFuerte}`, background: C.lienzo,
                          color: C.suave, fontSize: '12px', cursor: 'pointer', whiteSpace: 'nowrap',
                        }}>
                        {r.text.length > 40 ? `${r.text.slice(0, 40)}…` : r.text}
                      </button>
                    ))}
                  </div>
                ) : null}

                {adjunto ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '9px', marginBottom: '9px' }}>
                    <img src={adjunto} alt="" style={{ width: '42px', height: '42px', objectFit: 'cover', borderRadius: '8px' }} />
                    <span style={{ fontSize: '12.5px', color: C.suave, flex: 1 }}>Imagen lista para enviar</span>
                    <button type="button" onClick={() => setAdjunto(null)}
                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: C.error }}>
                      <X size={16} />
                    </button>
                  </div>
                ) : null}

                <textarea className="env-campo" rows={2} value={respuesta}
                  onChange={(e) => setRespuesta(e.target.value)}
                  placeholder={interno ? 'Nota para el equipo. El cliente NO la ve.' : 'Tu respuesta al cliente…'}
                  style={{
                    ...campo, resize: 'vertical', lineHeight: 1.5,
                    background: interno ? C.alertaSuave : C.lienzo,
                    borderColor: interno ? C.alertaBorde : C.lineaFuerte,
                  }} />

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '10px', flexWrap: 'wrap' }}>
                  <label style={{
                    display: 'inline-flex', alignItems: 'center', gap: '7px', cursor: 'pointer',
                    fontSize: '13px', fontWeight: 600, color: interno ? C.alerta : C.suave,
                  }}>
                    <input type="checkbox" checked={interno} onChange={(e) => setInterno(e.target.checked)}
                      data-testid="nota-interna" />
                    <Lock size={14} /> Nota interna
                  </label>
                  <label style={{ cursor: 'pointer', color: C.suave, display: 'inline-flex' }} title="Adjuntar imagen">
                    <Paperclip size={17} />
                    <input type="file" accept="image/*" onChange={elegirImagen} style={{ display: 'none' }} />
                  </label>
                  <span style={{ flex: 1 }} />
                  <Boton tipo="primario" onClick={enviar} Icono={Send} testid="enviar-respuesta"
                    disabled={ocupado || (!respuesta.trim() && !adjunto)
                      || (!interno && !acciones.responder.puede)}>
                    {interno ? 'Guardar nota' : 'Responder'}
                  </Boton>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ── El cliente y las herramientas ─────────────────────────── */}
        {caso ? (
          <div style={{ ...tarjeta, width: '290px', flexShrink: 0, overflowY: 'auto', padding: '16px' }}>
            <p style={{ margin: '0 0 12px 0', fontSize: '11px', fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: C.tenue }}>
              El cliente
            </p>
            <div style={{ display: 'grid', gap: '9px', marginBottom: '18px' }}>
              {[
                { icono: User, titulo: 'Nombre', valor: cliente.name || caso.user_name },
                { icono: Wallet, titulo: 'Saldo', valor: `RI$ ${fmt(cliente.balance_ris || 0)}` },
                { icono: ShieldCheck, titulo: 'Verificación', valor: cliente.verification_status || '—' },
                { icono: Clock, titulo: 'Casos anteriores', valor: String(detalle?.casos_previos ?? 0) },
              ].map((dato) => {
                // En mayúscula porque React sólo dibuja un componente si el
                // nombre empieza así; en la desestructuración el `eslint` lo
                // tomaba por un argumento sin usar.
                const Icono = dato.icono;
                const { titulo, valor } = dato;
                return (
                <div key={titulo} style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  padding: '9px 11px', background: C.fondo, borderRadius: '10px',
                }}>
                  <Icono size={15} color={C.tenue} style={{ flexShrink: 0 }} />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: '10.5px', color: C.tenue, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                      {titulo}
                    </span>
                    <span style={{ display: 'block', fontSize: '13px', color: C.tinta, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {valor}
                    </span>
                  </span>
                </div>
                );
              })}
            </div>

            {(detalle?.operaciones || []).length > 0 ? (
              <>
                <p style={{ margin: '0 0 8px 0', fontSize: '11px', fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: C.tenue }}>
                  Últimas operaciones
                </p>
                <div style={{ display: 'grid', gap: '5px', marginBottom: '18px' }}>
                  {detalle.operaciones.map((op) => (
                    <div key={op.transaction_id} style={{
                      display: 'flex', justifyContent: 'space-between', gap: '8px',
                      fontSize: '12px', padding: '6px 9px', background: C.fondo, borderRadius: '8px',
                    }}>
                      <span style={{ color: C.suave }}>{op.type}</span>
                      <span style={{ color: C.tinta, fontWeight: 600 }}>{fmt(op.amount || 0)}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {(detalle?.pedidos || []).length > 0 ? (
              <>
                <p style={{ margin: '0 0 8px 0', fontSize: '11px', fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: C.tenue }}>
                  Pedidos a otras áreas
                </p>
                <div style={{ display: 'grid', gap: '7px', marginBottom: '18px' }}>
                  {detalle.pedidos.map((p) => (
                    <div key={p.pedido_id} style={{
                      padding: '9px 11px', borderRadius: '10px', background: C.fondo,
                      border: `1px solid ${p.estado === 'pendiente' ? C.alertaBorde : C.linea}`,
                    }}>
                      <Etiqueta tono={p.estado === 'pendiente' ? 'alerta' : 'exito'}>
                        {p.estado}
                      </Etiqueta>
                      <p style={{ margin: '6px 0 0 0', fontSize: '12px', color: C.texto, lineHeight: 1.45 }}>
                        {p.detalle}
                      </p>
                      {p.respuesta ? (
                        <p style={{ margin: '6px 0 0 0', fontSize: '12px', color: C.exito, lineHeight: 1.45 }}>
                          ↳ {p.respuesta}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            <p style={{ margin: '0 0 9px 0', fontSize: '11px', fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: C.tenue }}>
              Herramientas
            </p>

            <label style={etiqueta} htmlFor="ma-estado">Estado</label>
            <select id="ma-estado" className="env-campo" value="" data-testid="cambiar-estado"
              onChange={(e) => e.target.value && cambiarEstado(e.target.value)}
              disabled={ocupado || estadosPosibles(caso.estado).length === 0}
              style={{ ...campo, marginBottom: '10px' }}>
              <option value="">Cambiar a…</option>
              {estadosPosibles(caso.estado).map((e) => (
                <option key={e} value={e}>{nombreDeEstado(e)}</option>
              ))}
            </select>

            <label style={etiqueta} htmlFor="ma-prioridad">Prioridad</label>
            <select id="ma-prioridad" className="env-campo" value={caso.prioridad || 'normal'}
              onChange={(e) => conAviso(
                () => api.post(`/admin/soporte/casos/${elegido}/prioridad`, { prioridad: e.target.value }),
                'Prioridad actualizada')}
              disabled={ocupado} style={{ ...campo, marginBottom: '14px' }}>
              {PRIORIDADES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>

            <div style={{ display: 'grid', gap: '8px' }}>
              {[
                { clave: 'transferir', icono: ArrowRightLeft, texto: 'Transferir a otra área', permiso: acciones.transferir },
                { clave: 'pedir', icono: HelpCircle, texto: 'Pedirle algo a otra área', permiso: acciones.pedir },
                { clave: 'escalar', icono: AlertTriangle, texto: 'Escalar', permiso: acciones.escalar },
              ].map((h) => (
                <div key={h.clave}>
                  <Boton ancho onClick={() => setVentana(h.clave)} Icono={h.icono}
                    disabled={!h.permiso.puede} testid={`abrir-${h.clave}`}>
                    {h.texto}
                  </Boton>
                  {!h.permiso.puede && h.permiso.porque ? (
                    <p style={{ ...ayuda, fontSize: '11.5px' }}>{h.permiso.porque}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      )}

      {ventana ? (
        <VentanaDeAccion accion={ventana} areas={areas} asesores={asesores}
          ocupado={ocupado} onCerrar={() => setVentana(null)}
          onConfirmar={confirmarVentana} />
      ) : null}
    </div>
  );
}
