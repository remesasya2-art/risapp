/**
 * CompletarRegistroGoogle — lo que Google no trae: nombre confirmado, CPF y
 * la aceptación de los términos.
 *
 * El correo NO se edita: es el que Google confirmó y el servidor lo saca de
 * la invitación, no de este formulario. Lo demás es el mismo formulario
 * del registro con correo, sin contraseña y sin código de seis dígitos.
 */
import { useState } from 'react';
import { ArrowLeft, Gift } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { formatearCpf, normalizarCpf, queLeFaltaAlCpf } from '../../utils/cpf';

const inputStyle = {
  width: '100%', padding: '16px', borderRadius: '14px', border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)',
  fontSize: '16px', color: 'var(--en-oscuro-texto, #111827)', backgroundColor: 'var(--en-oscuro-superficie, #ffffff)', outline: 'none',
};
const labelStyle = { display: 'block', fontSize: '14px', fontWeight: '600', color: 'var(--en-oscuro-texto, #374151)', marginBottom: '8px' };

export default function CompletarRegistroGoogle({ pendiente, referralInicial = '', onVolver }) {
  const [nombre, setNombre] = useState(pendiente?.nombre || '');
  const [cpf, setCpf] = useState('');
  const [referralCode, setReferralCode] = useState(referralInicial || '');
  const [acepta, setAcepta] = useState(false);
  const [loading, setLoading] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    if (!acepta) { toast.error('Debes aceptar los Términos y la Política de Privacidad'); return; }
    if (!nombre.trim()) { toast.error('Decinos tu nombre'); return; }
    const errorCpf = queLeFaltaAlCpf(cpf);
    if (errorCpf) { toast.error(errorCpf); return; }
    setLoading(true);
    try {
      const { data } = await api.post('/auth/google/completar', {
        pending_token: pendiente.pending_token,
        name: nombre.trim(),
        cpf_number: normalizarCpf(cpf),
        referred_by: referralCode.trim().toUpperCase() || null,
        accept_terms: true,
      });
      if (data?.session_token) {
        localStorage.setItem('has_session', '1');
        localStorage.setItem('last_activity', Date.now().toString());
        toast.success('¡Cuenta creada exitosamente!');
        // Recarga entera, como al confirmar el código: así el contexto de
        // sesión arranca limpio con la cuenta nueva.
        window.location.href = '/';
      } else {
        toast.error('No pudimos completar el registro');
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No pudimos completar el registro');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="completar-registro-google">
      <button type="button" onClick={onVolver} style={{ background: 'none', border: 'none', color: 'var(--en-oscuro-texto-2, #6b7280)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', padding: 0, marginBottom: '20px', fontSize: '14px' }}>
        <ArrowLeft size={16} /> Volver
      </button>
      <h1 style={{ fontSize: '24px', fontWeight: '700', color: 'var(--en-oscuro-texto, #111827)', textAlign: 'center', margin: '0 0 8px 0' }}>Casi listo</h1>
      <p style={{ fontSize: '15px', color: 'var(--en-oscuro-texto-2, #6b7280)', textAlign: 'center', margin: '0 0 24px 0' }}>
        Google confirmó tu correo. Falta lo que Google no sabe.
      </p>

      <form onSubmit={enviar} data-testid="completar-google-form">
        <div style={{ marginBottom: '20px' }}>
          <label style={labelStyle}>Correo</label>
          <input type="email" value={pendiente?.email || ''} readOnly data-testid="google-email" style={{ ...inputStyle, backgroundColor: 'var(--en-oscuro-superficie-2, #f9fafb)', color: 'var(--en-oscuro-texto-2, #6b7280)' }} />
        </div>
        <div style={{ marginBottom: '20px' }}>
          <label style={labelStyle}>Nombre completo</label>
          <input type="text" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Como figura en tu documento" data-testid="google-name-input" style={inputStyle} />
        </div>
        <div style={{ marginBottom: '20px' }}>
          <label style={labelStyle}>CPF</label>
          <input type="text" inputMode="numeric" value={cpf} onChange={(e) => setCpf(formatearCpf(e.target.value))} placeholder="000.000.000-00" data-testid="google-cpf-input" style={inputStyle} />
          <p style={{ fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '6px 0 0 0' }}>
            Es con el que vas a recargar. No vas a tener que cargarlo de nuevo al verificar tu cuenta.
          </p>
        </div>
        <div style={{ marginBottom: '20px' }}>
          <label style={labelStyle}>Código de referido (opcional)</label>
          <div style={{ position: 'relative' }}>
            <div style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: 'var(--en-oscuro-texto-3, #9ca3af)' }}><Gift size={20} /></div>
            <input type="text" value={referralCode} onChange={(e) => setReferralCode(e.target.value.toUpperCase())} placeholder="Ej: REF3A9F2B01" data-testid="google-referral-input" style={{ ...inputStyle, paddingLeft: '48px', textTransform: 'uppercase' }} />
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', margin: '0 0 16px 0' }}>
          <input type="checkbox" id="aceptaTerminosGoogle" checked={acepta} onChange={(e) => setAcepta(e.target.checked)} style={{ marginTop: '3px', cursor: 'pointer' }} />
          <label htmlFor="aceptaTerminosGoogle" style={{ fontSize: '13px', color: 'var(--en-oscuro-texto-2, #6b7280)', lineHeight: 1.5, cursor: 'pointer' }}>
            He leído y acepto los{' '}
            <a href="/legal#terminos" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--en-oscuro-acento, #6366f1)', textDecoration: 'underline' }}>Términos y Condiciones</a>
            {' '}y la{' '}
            <a href="/legal#privacidad" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--en-oscuro-acento, #6366f1)', textDecoration: 'underline' }}>Política de Privacidad</a>.
          </label>
        </div>
        <button
          type="submit"
          disabled={loading || !acepta}
          data-testid="google-completar-btn"
          style={{ width: '100%', padding: '16px', borderRadius: '14px', border: 'none', backgroundColor: 'var(--en-oscuro-acento, #6366f1)', color: '#fff', fontSize: '16px', fontWeight: '700', cursor: loading || !acepta ? 'not-allowed' : 'pointer', opacity: loading || !acepta ? 0.6 : 1 }}
        >
          {loading ? 'Creando cuenta...' : 'Crear cuenta'}
        </button>
      </form>
    </div>
  );
}
