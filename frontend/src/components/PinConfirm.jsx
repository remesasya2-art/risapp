import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { Lock, X } from 'lucide-react';

/**
 * Modal de confirmación con PIN.
 * - Al abrirse consulta /pin/status.
 * - Si el usuario es super_admin o NO tiene PIN: continúa el envío sin pedir nada.
 * - Si tiene PIN: pide los 4 dígitos y verifica contra /pin/verify.
 *
 * Props: open (bool), onClose (), onVerified ()  -> se llama cuando se puede continuar.
 */
export default function PinConfirm({ open, onClose, onVerified }) {
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [needPin, setNeedPin] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!open) { setReady(false); setNeedPin(false); setPin(''); return; }
    let active = true;
    setReady(false);
    setNeedPin(false);
    setPin('');
    (async () => {
      try {
        const res = await api.get('/pin/status');
        const s = res.data || {};
        if (!active) return;
        if (s.is_super_admin || !s.has_pin) {
          onClose?.();
          onVerified?.();
        } else {
          setNeedPin(true);
          setReady(true);
        }
      } catch (e) {
        if (active) { onClose?.(); onVerified?.(); }
      }
    })();
    return () => { active = false; };
  }, [open]);

  if (!open || !needPin || !ready) return null;

  const onlyDigits = (v) => v.replace(/\D/g, '').slice(0, 4);

  const verificar = async () => {
    if (pin.length !== 4) { toast.error('Ingresa tu PIN de 4 dígitos'); return; }
    try {
      setBusy(true);
      await api.post('/pin/verify', { pin });
      onClose?.();
      onVerified?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'PIN incorrecto');
      setPin('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(17,24,39,0.55)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
    }}>
      <div style={{ width: '100%', maxWidth: '360px', backgroundColor: '#fff', borderRadius: '18px', padding: '24px', position: 'relative' }}>
        <button onClick={() => onClose?.()} style={{
          position: 'absolute', top: '14px', right: '14px', border: 'none', background: 'none', cursor: 'pointer', color: '#9ca3af',
        }}><X size={20} /></button>
        <div style={{ textAlign: 'center', marginBottom: '18px' }}>
          <div style={{ width: '52px', height: '52px', borderRadius: '50%', backgroundColor: '#EEF2FF', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: '10px' }}>
            <Lock size={24} color="#4F46E5" />
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#111827', margin: 0 }}>Confirma con tu PIN</h3>
          <p style={{ fontSize: '13px', color: '#6b7280', margin: '6px 0 0 0' }}>Ingresa tu PIN de 4 dígitos para autorizar esta operación.</p>
        </div>
        <input
          type="password" inputMode="numeric" autoFocus value={pin}
          onChange={(e) => setPin(onlyDigits(e.target.value))}
          onKeyDown={(e) => { if (e.key === 'Enter') verificar(); }}
          placeholder="••••"
          style={{
            width: '100%', textAlign: 'center', letterSpacing: '12px', fontSize: '24px',
            padding: '14px', borderRadius: '12px', border: '1px solid #e5e7eb', boxSizing: 'border-box',
          }}
        />
        <button onClick={verificar} disabled={busy} style={{
          width: '100%', marginTop: '16px', padding: '13px', borderRadius: '12px', border: 'none',
          backgroundColor: '#6366f1', color: '#fff', fontWeight: 700, fontSize: '15px', cursor: 'pointer',
          opacity: busy ? 0.6 : 1,
        }}>
          {busy ? 'Verificando…' : 'Confirmar'}
        </button>
      </div>
    </div>
  );
}
