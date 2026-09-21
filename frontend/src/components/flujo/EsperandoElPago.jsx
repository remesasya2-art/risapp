/**
 * EsperandoElPago — la línea que dice que la pantalla está atenta.
 *
 *   Debajo del QR. Sin esto, el cliente que ya pagó no sabe si tiene que
 *   hacer algo más: la pantalla se ve igual antes y después de pagar. El
 *   punto que late dice «estoy mirando», y el botón es para el impaciente
 *   —y para el que pagó hace treinta segundos y no quiere esperar la próxima
 *   vuelta de la pregunta—.
 */
import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { C } from './estilos';

export default function EsperandoElPago({ onRevisar, testid = 'esperando-pago' }) {
  const [revisando, setRevisando] = useState(false);

  const revisar = async () => {
    if (revisando) return;
    setRevisando(true);
    try { await onRevisar?.(); } finally { setRevisando(false); }
  };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: '12px', flexWrap: 'wrap', padding: '12px 14px', marginTop: '14px',
      background: C.fondo, borderRadius: '12px',
    }} data-testid={testid}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '9px',
        fontSize: '13px', color: C.texto }}>
        <span aria-hidden="true" style={{
          width: '9px', height: '9px', borderRadius: '50%', background: C.exito,
          boxShadow: `0 0 0 0 ${C.exitoBorde}`, animation: 'late 1.6s ease-out infinite',
        }} />
        Esperando tu pago… se confirma solo en cuanto entre.
      </span>
      <button type="button" onClick={revisar} disabled={revisando}
        data-testid={`${testid}-revisar`}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          background: 'transparent', border: 'none', cursor: revisando ? 'default' : 'pointer',
          color: C.marca, fontSize: '13px', fontWeight: 600, padding: 0,
          opacity: revisando ? 0.6 : 1,
        }}>
        <RefreshCw size={13} style={{ animation: revisando ? 'girar 0.9s linear infinite' : 'none' }} />
        {revisando ? 'Revisando…' : 'Ya pagué, revisar'}
      </button>
      <style>{`
        @keyframes late { 0% { box-shadow: 0 0 0 0 ${C.exitoBorde}; } 70% { box-shadow: 0 0 0 7px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
        @keyframes girar { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
