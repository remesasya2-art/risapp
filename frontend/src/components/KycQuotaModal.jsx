import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert, X } from 'lucide-react';
import api from '../utils/api';

/**
 * Ventana flotante que aparece cuando una cuenta sin verificar agota su cupo
 * (200 RIS o 2 operaciones, lo que pase primero).
 *
 * El bloqueo real vive en el servidor: esta ventana solo explica por que dejaron
 * de funcionar las operaciones y lleva a la verificacion. Por eso se puede cerrar
 * — dejarla fija no agrega seguridad y deja al usuario encerrado en la pantalla.
 * Al recargar vuelve a aparecer mientras el cupo siga agotado.
 */
export default function KycQuotaModal() {
  const navigate = useNavigate();
  const [cupo, setCupo] = useState(null);
  const [cerrado, setCerrado] = useState(false);

  useEffect(() => {
    api.get('/limits/me')
      .then((r) => setCupo(r.data?.cupo_kyc ?? null))
      .catch(() => setCupo(null)); // sin el dato no mostramos nada: el servidor igual bloquea
  }, []);

  if (cerrado || !cupo?.agotado) return null;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(17, 24, 39, 0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '16px', zIndex: 1000,
      }}
      data-testid="kyc-quota-modal"
    >
      <div style={{ backgroundColor: 'white', borderRadius: '16px', padding: '24px', maxWidth: '420px', width: '100%', boxShadow: '0 20px 40px rgba(0,0,0,0.2)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
          <div style={{ backgroundColor: '#fef3c7', borderRadius: '12px', padding: '10px', flexShrink: 0 }}>
            <ShieldAlert style={{ width: '22px', height: '22px', color: '#d97706' }} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
              Verificá tu cuenta para seguir operando
            </h3>
            <p style={{ fontSize: '14px', color: '#4b5563', margin: '8px 0 0 0', lineHeight: 1.5 }}>
              Alcanzaste el límite de {cupo.max_ops} operaciones o {cupo.max_ris} RIS que permite
              una cuenta sin verificar. Completá la verificación para levantar el límite y seguir
              usando RIS App.
            </p>
            <p style={{ fontSize: '13px', color: '#6b7280', margin: '10px 0 0 0' }}>
              Usaste {cupo.ops_usadas} de {cupo.max_ops} operaciones y {cupo.ris_usados} de {cupo.max_ris} RIS.
            </p>
          </div>
          <button
            onClick={() => setCerrado(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '2px' }}
            aria-label="Cerrar"
          >
            <X style={{ width: '18px', height: '18px' }} />
          </button>
        </div>
        <button
          onClick={() => navigate('/verification')}
          style={{
            width: '100%', marginTop: '20px', padding: '12px', borderRadius: '10px', border: 'none',
            backgroundColor: '#4f46e5', color: 'white', fontWeight: '600', fontSize: '15px', cursor: 'pointer',
          }}
          data-testid="kyc-quota-verificar"
        >
          Verificar mi cuenta
        </button>
      </div>
    </div>
  );
}
