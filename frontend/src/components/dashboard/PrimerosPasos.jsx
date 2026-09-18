/**
 * components/dashboard/PrimerosPasos.jsx — Lo que le falta a una cuenta
 * nueva para andar.
 *
 * POR QUE ESTA ACA Y NO EN CADA PANTALLA
 *
 *   Los empujones a verificarse estaban repartidos —Perfil, Recarga, BTC,
 *   encomiendas, y la ventana que salta cuando se agota el cupo—, o sea que
 *   aparecían recién cuando algo se trababa. Esto se ve al llegar, dice los
 *   tres pasos en orden, y se va solo cuando ya no hace falta.
 *
 * EL ESTADO LO DICE EL SERVIDOR
 *
 *   «Ya recargó» vive en cinco colecciones distintas y esta pantalla sólo
 *   ve una. Se pregunta a `/primeros-pasos` y se dibuja lo que contesta.
 *   Ver backend/services/primeros_pasos.py.
 *
 * SE PUEDE OCULTAR, Y ESO SE RECUERDA EN ESTE NAVEGADOR
 *
 *   Quien ya sabe lo que hace no tiene por qué ver la lista cada vez. Es
 *   una comodidad de este navegador, no un dato de la cuenta: en otro
 *   dispositivo vuelve a aparecer, y no pasa nada.
 *
 * LA HUELLA ES UN CUARTO PASO QUE NO CUENTA
 *
 *   Sólo se ofrece si el dispositivo la soporta y no está activada, y no
 *   entra en el «listos»: una tarjeta que nunca se completa porque el
 *   teléfono no tiene lector es una tarjeta que la persona aprende a
 *   ignorar.
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, Clock, AlertCircle, ShieldCheck, Wallet, Send, Fingerprint, X } from 'lucide-react';
import api from '../../utils/api';
import { webauthnSupported } from '../../utils/webauthn';

const CLAVE_OCULTA = 'primeros_pasos_ocultos';

function leerOculto() {
  try { return localStorage.getItem(CLAVE_OCULTA) === '1'; } catch { return false; }
}

function recordarOculto() {
  try { localStorage.setItem(CLAVE_OCULTA, '1'); } catch { /* sin almacenamiento, se oculta igual esta vez */ }
}

const VERIFICACION = {
  sin_enviar: { estado: 'pendiente', texto: 'Tu documento y una selfie. Desbloquea los envíos sin tope y el bono, si tenés uno.', boton: 'Verificar' },
  en_revision: { estado: 'espera', texto: 'Recibimos tus documentos. Te avisamos cuando estén revisados.', boton: null },
  aprobada: { estado: 'hecho', texto: 'Identidad verificada.', boton: null },
  rechazada: { estado: 'atencion', texto: 'No pudimos aprobarla. Revisá el motivo y volvé a enviar.', boton: 'Volver a enviar' },
};

export default function PrimerosPasos({ user, isMobile = false }) {
  const navigate = useNavigate();
  const [estado, setEstado] = useState(null);
  const [oculto, setOculto] = useState(leerOculto);

  useEffect(() => {
    let vigente = true;
    api.get('/primeros-pasos')
      .then((r) => { if (vigente) setEstado(r.data || null); })
      .catch(() => { /* sin el dato no se dibuja nada: el panel sigue igual */ });
    return () => { vigente = false; };
  }, [user?.verification_status]);

  if (oculto || !estado || estado.completo) return null;

  const v = VERIFICACION[estado.verificacion] || VERIFICACION.sin_enviar;
  const pasos = [
    { clave: 'verificacion', Icono: ShieldCheck, titulo: 'Verificá tu identidad', ...v, ruta: '/verification', cuenta: true },
    { clave: 'recarga', Icono: Wallet, titulo: 'Cargá saldo', ruta: '/recharge', cuenta: true,
      estado: estado.recarga ? 'hecho' : 'pendiente',
      texto: estado.recarga ? 'Ya tenés saldo cargado.' : 'Por PIX, con tarjeta o con cripto.',
      boton: estado.recarga ? null : 'Recargar' },
    { clave: 'envio', Icono: Send, titulo: 'Hacé tu primer envío', ruta: '/send', cuenta: true,
      estado: estado.envio ? 'hecho' : 'pendiente',
      texto: estado.envio ? 'Ya hiciste tu primer envío.' : 'A Venezuela en bolívares, o a Brasil en reales.',
      boton: estado.envio ? null : 'Enviar' },
  ];
  if (webauthnSupported() && !estado.huella) {
    pasos.push({ clave: 'huella', cuenta: false, Icono: Fingerprint, titulo: 'Entrá con huella la próxima vez',
      ruta: '/profile', estado: 'pendiente', texto: 'Sin contraseña, desde este dispositivo.', boton: 'Activar' });
  }
  const queCuentan = pasos.filter((p) => p.cuenta);
  const hechos = queCuentan.filter((p) => p.estado === 'hecho').length;

  const ocultar = () => { recordarOculto(); setOculto(true); };

  const Boton = ({ paso }) => (
    <button
      type="button"
      onClick={() => navigate(paso.ruta)}
      style={{
        padding: '8px 14px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
        background: paso.estado === 'atencion' ? '#dc2626' : '#4f46e5', color: '#fff', whiteSpace: 'nowrap',
        marginTop: isMobile ? 8 : 0,
      }}
    >
      {paso.boton}
    </button>
  );

  const Marca = ({ estado: e }) => {
    if (e === 'hecho') return <CheckCircle2 size={20} color="#16a34a" />;
    if (e === 'espera') return <Clock size={20} color="#d97706" />;
    if (e === 'atencion') return <AlertCircle size={20} color="#dc2626" />;
    return <Circle size={20} color="#9ca3af" />;
  };

  return (
    <div
      data-testid="primeros-pasos"
      style={{
        backgroundColor: '#ffffff', borderRadius: '16px', border: '1px solid #eef0f4',
        boxShadow: '0 1px 3px rgba(0,0,0,0.03)', padding: isMobile ? '16px' : '18px 20px', marginBottom: '24px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
        <div>
          <h2 style={{ fontSize: isMobile ? '16px' : '17px', fontWeight: 700, color: '#111827', margin: 0 }}>Primeros pasos</h2>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }} data-testid="primeros-pasos-progreso">
            {hechos} de {queCuentan.length} listos
          </p>
        </div>
        <button
          type="button"
          onClick={ocultar}
          title="Ocultar"
          aria-label="Ocultar primeros pasos"
          data-testid="primeros-pasos-ocultar"
          style={{ width: 32, height: 32, borderRadius: 10, border: 'none', background: '#f3f4f6', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <X size={16} color="#6b7280" />
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {pasos.map((p) => (
          <div
            key={p.clave}
            data-testid={`paso-${p.clave}`}
            data-estado={p.estado}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 12,
              background: p.estado === 'hecho' ? '#f0fdf4' : '#f9fafb',
              border: '1px solid ' + (p.estado === 'hecho' ? '#dcfce7' : '#f3f4f6'),
            }}
          >
            <Marca estado={p.estado} />
            <span style={{
              width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              backgroundColor: '#eef2ff',
            }}>
              <p.Icono size={17} color="#4f46e5" />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '14px', fontWeight: 600, color: p.estado === 'hecho' ? '#166534' : '#111827',
                            textDecoration: p.estado === 'hecho' ? 'line-through' : 'none' }}>
                {p.titulo}
              </div>
              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: 2 }}>{p.texto}</div>
              {/* En el teléfono el botón va DEBAJO del texto: al costado, un
                  «Volver a enviar» le dejaba tres palabras por línea. */}
              {p.boton && isMobile ? <Boton paso={p} /> : null}
            </div>
            {p.boton && !isMobile ? <Boton paso={p} /> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
