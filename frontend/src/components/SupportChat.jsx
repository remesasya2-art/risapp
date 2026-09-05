/**
 * SupportChat.jsx — El botón azul de la esquina.
 *
 * Ahora es sólo el envase: la ventana, el globo con lo que no leíste y el
 * botón. Todo lo que pasa adentro vive en `components/soporte/CasosDelCliente`,
 * que es EL MISMO componente que dibuja la pantalla de Soporte.
 *
 * POR QUE ASI
 *
 *   Antes había un chat acá y otra pantalla de soporte por su cuenta, cada una
 *   con su código. Dos copias de lo mismo se separan al primer retoque en una
 *   sola, y el cliente no ve «dos pantallas parecidas»: ve una aplicación donde
 *   el chat de la esquina y la sección de soporte se comportan distinto sin
 *   ningún motivo.
 */
import { useState } from 'react';
import { MessageSquare, ChevronDown, X } from 'lucide-react';
import CasosDelCliente from './soporte/CasosDelCliente';
import { C, HOJA, tarjeta } from './flujo/estilos';

export default function SupportChat() {
  const [abierto, setAbierto] = useState(false);
  const [sinLeer, setSinLeer] = useState(0);

  return (
    <div className="env" style={{ fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif' }}>
      <style>{HOJA}</style>

      <button type="button" onClick={() => setAbierto((v) => !v)}
        aria-label={abierto ? 'Cerrar soporte' : 'Abrir soporte'}
        data-testid="support-chat-button"
        style={{
          position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000,
          width: '58px', height: '58px', borderRadius: '50%', border: 'none',
          background: C.marca, color: '#fff', cursor: 'pointer',
          boxShadow: '0 6px 22px rgba(79,70,229,.38)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
        {abierto ? <ChevronDown size={26} /> : <MessageSquare size={25} />}
        {!abierto && sinLeer > 0 ? (
          <span style={{
            position: 'absolute', top: '-3px', right: '-3px',
            minWidth: '21px', height: '21px', padding: '0 5px',
            borderRadius: '999px', background: C.error, color: '#fff',
            fontSize: '11.5px', fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {sinLeer}
          </span>
        ) : null}
      </button>

      {abierto ? (
        <div data-testid="support-chat-window" style={{
          ...tarjeta, position: 'fixed', bottom: '94px', right: '24px', zIndex: 1000,
          width: '370px', maxWidth: 'calc(100vw - 48px)',
          height: '520px', maxHeight: 'calc(100vh - 150px)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 14px 44px rgba(16,24,40,.18)',
        }}>
          <div style={{
            padding: '14px 16px', background: C.marca, color: '#fff',
            display: 'flex', alignItems: 'center', gap: '11px',
          }}>
            <span style={{
              width: '34px', height: '34px', borderRadius: '50%',
              background: 'rgba(255,255,255,.18)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <MessageSquare size={17} />
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: '15px', fontWeight: 700 }}>Soporte RIS</span>
              <span style={{ display: 'block', fontSize: '11.5px', opacity: 0.85 }}>
                Te respondemos por acá mismo
              </span>
            </span>
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar"
              style={{ border: 'none', background: 'none', color: '#fff', cursor: 'pointer', display: 'inline-flex' }}>
              <X size={18} />
            </button>
          </div>

          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <CasosDelCliente onSinLeer={setSinLeer} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
