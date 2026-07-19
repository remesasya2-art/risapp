import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, ArrowLeft, Gift } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function Register() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  // Form fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [referralCode, setReferralCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  
  // Verification step
  const [step, setStep] = useState(1); // 1 = form, 2 = verification
  const [verificationCode, setVerificationCode] = useState('');
  const [resending, setResending] = useState(false);

  // Check for referral code in URL
  useEffect(() => {
    const refCode = searchParams.get('ref');
    if (refCode) {
      setReferralCode(refCode.toUpperCase());
    }
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!acceptedTerms) {
      toast.error('Debes aceptar los Términos y la Política de Privacidad');
      return;
    }
    
    if (!name || !email || !password || !confirmPassword) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    
    if (password.length < 6) {
      toast.error('La contraseña debe tener al menos 6 caracteres');
      return;
    }
    
    if (password !== confirmPassword) {
      toast.error('Las contraseñas no coinciden');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/auth/register', {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        confirm_password: confirmPassword,
        referral_code: referralCode.trim().toUpperCase() || null
      });
      
      toast.success(response.data.message || 'Código de verificación enviado');
      setStep(2); // Move to verification step
    } catch (error) {
      console.error('Register error:', error);
      toast.error(error.response?.data?.detail || 'Error al registrar');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    
    if (!verificationCode || verificationCode.length !== 6) {
      toast.error('Ingresa el código de 6 dígitos');
      return;
    }
    
    setLoading(true);
    try {
      const response = await api.post('/auth/verify-email', {
        email: email.trim().toLowerCase(),
        code: verificationCode
      });
      
      // Save session token and redirect
      if (response.data.session_token) {
        localStorage.setItem('has_session', '1');
        localStorage.setItem('last_activity', Date.now().toString());
        toast.success('¡Cuenta creada exitosamente!');
        // Force page reload to update auth state
        window.location.href = '/';
      } else {
        toast.success('Registro completado. Por favor inicia sesión.');
        navigate('/login');
      }
    } catch (error) {
      console.error('Verification error:', error);
      toast.error(error.response?.data?.detail || 'Código inválido');
    } finally {
      setLoading(false);
    }
  };

  const handleResendCode = async () => {
    setResending(true);
    try {
      const response = await api.post('/auth/resend-verification-code', {
        email: email.trim().toLowerCase()
      });
      toast.success(response.data.message || 'Código reenviado');
    } catch (error) {
      console.error('Resend error:', error);
      toast.error(error.response?.data?.detail || 'Error al reenviar código');
    } finally {
      setResending(false);
    }
  };

  const pageStyle = {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '16px',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)'
  };

  const cardStyle = {
    width: '100%',
    maxWidth: '420px',
    backgroundColor: '#ffffff',
    borderRadius: '24px',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.08), 0 12px 24px -8px rgba(0, 0, 0, 0.04)',
    padding: '48px 40px'
  };

  const inputStyle = {
    width: '100%',
    padding: '16px',
    borderRadius: '14px',
    border: '1px solid #d1d5db',
    fontSize: '16px',
    color: '#111827',
    backgroundColor: '#ffffff',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s'
  };

  const buttonStyle = {
    width: '100%',
    padding: '16px',
    borderRadius: '14px',
    border: 'none',
    backgroundColor: '#6366f1',
    color: '#ffffff',
    fontSize: '16px',
    fontWeight: '700',
    cursor: 'pointer',
    transition: 'background-color 0.2s'
  };

  const labelStyle = {
    display: 'block',
    fontSize: '14px',
    fontWeight: '600',
    color: '#374151',
    marginBottom: '8px'
  };

  // Verification Code Step (Step 2)
  if (step === 2) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>
          {/* Back Button */}
          <button
            type="button"
            onClick={() => setStep(1)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'none',
              border: 'none',
              color: '#6366f1',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              padding: 0,
              marginBottom: '24px'
            }}
          >
            <ArrowLeft size={18} />
            Volver
          </button>

          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '32px' }}>
            <img 
              src="/logo-ris.jpeg" 
              alt="RIS" 
              style={{ height: '48px', borderRadius: '12px' }}
            />
          </div>

          {/* Title */}
          <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#111827', textAlign: 'center', margin: '0 0 8px 0' }}>
            Verifica tu cuenta
          </h1>
          <p style={{ fontSize: '16px', color: '#9ca3af', textAlign: 'center', margin: '0 0 32px 0' }}>
            Ingresa el código de 6 dígitos enviado a <br/>
            <span style={{ color: '#6366f1', fontWeight: '500' }}>{email}</span>
          </p>

          <form onSubmit={handleVerifyCode} data-testid="verification-form">
            {/* Verification Code Input */}
            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
                Código de verificación
              </label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                data-testid="verification-code-input"
                style={{
                  ...inputStyle,
                  textAlign: 'center',
                  fontSize: '24px',
                  letterSpacing: '8px',
                  fontWeight: '600'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#6366f1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
                onBlur={(e) => { e.target.style.borderColor = '#d1d5db'; e.target.style.boxShadow = 'none'; }}
              />
            </div>

            {/* Verify Button */}
            <button
              type="submit"
              disabled={loading || verificationCode.length !== 6}
              data-testid="verify-submit-btn"
              style={{
                ...buttonStyle,
                opacity: loading || verificationCode.length !== 6 ? 0.6 : 1,
                cursor: loading || verificationCode.length !== 6 ? 'not-allowed' : 'pointer'
              }}
            >
              {loading ? 'Verificando...' : 'Verificar Código'}
            </button>
          </form>

          {/* Resend Code */}
          <div style={{ textAlign: 'center', marginTop: '24px' }}>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 8px 0' }}>
              ¿No recibiste el código?
            </p>
            <button
              type="button"
              onClick={handleResendCode}
              disabled={resending}
              style={{
                background: 'none',
                border: 'none',
                color: '#6366f1',
                fontSize: '14px',
                fontWeight: '600',
                cursor: resending ? 'not-allowed' : 'pointer',
                opacity: resending ? 0.6 : 1
              }}
            >
              {resending ? 'Reenviando...' : 'Reenviar código'}
            </button>
          </div>

          {/* Login Link */}
          <p style={{ textAlign: 'center', fontSize: '15px', color: '#6b7280', marginTop: '24px' }}>
            ¿Ya tienes cuenta?{' '}
            <Link to="/login" style={{ color: '#6366f1', fontWeight: '500', textDecoration: 'none' }}>
              Inicia sesión
            </Link>
          </p>
        </div>
      </div>
    );
  }

  // Registration Form (Step 1)
  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '32px' }}>
          <img 
            src="/logo-ris.jpeg" 
            alt="RIS" 
            style={{ height: '48px', borderRadius: '12px' }}
          />
        </div>

        {/* Title */}
        <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#111827', textAlign: 'center', margin: '0 0 8px 0' }}>
          Crear Cuenta
        </h1>
        <p style={{ fontSize: '16px', color: '#9ca3af', textAlign: 'center', margin: '0 0 32px 0' }}>
          Comienza con tu billetera digital
        </p>

        {/* Divider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
          <div style={{ flex: 1, height: '1px', backgroundColor: '#e5e7eb' }}></div>
          <span style={{ fontSize: '12px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>O continúa con email</span>
          <div style={{ flex: 1, height: '1px', backgroundColor: '#e5e7eb' }}></div>
        </div>

        <form onSubmit={handleSubmit} data-testid="register-form">
          {/* Name */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
              Nombre completo
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="name-input"
              style={inputStyle}
              onFocus={(e) => { e.target.style.borderColor = '#6366f1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
              onBlur={(e) => { e.target.style.borderColor = '#d1d5db'; e.target.style.boxShadow = 'none'; }}
            />
          </div>

          {/* Email */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
              Correo electrónico
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              data-testid="email-input"
              style={inputStyle}
              onFocus={(e) => { e.target.style.borderColor = '#6366f1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
              onBlur={(e) => { e.target.style.borderColor = '#d1d5db'; e.target.style.boxShadow = 'none'; }}
            />
          </div>

          {/* Password */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
              Contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="password-input"
                style={{ ...inputStyle, paddingRight: '48px' }}
                onFocus={(e) => { e.target.style.borderColor = '#6366f1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
                onBlur={(e) => { e.target.style.borderColor = '#d1d5db'; e.target.style.boxShadow = 'none'; }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                  color: '#9ca3af'
                }}
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            <p style={{ fontSize: '13px', color: '#9ca3af', margin: '6px 0 0 0' }}>Mínimo 7 caracteres con letras, números y símbolos</p>
          </div>

          {/* Confirm Password */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '8px' }}>
              Confirmar contraseña
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                data-testid="confirm-password-input"
                style={{ 
                  ...inputStyle, 
                  paddingRight: '48px',
                  borderColor: confirmPassword && password !== confirmPassword ? '#ef4444' : '#d1d5db'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#6366f1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.1)'; }}
                onBlur={(e) => { 
                  e.target.style.borderColor = confirmPassword && password !== confirmPassword ? '#ef4444' : '#d1d5db'; 
                  e.target.style.boxShadow = 'none'; 
                }}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                style={{
                  position: 'absolute',
                  right: '16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                  color: '#9ca3af'
                }}
              >
                {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            {confirmPassword && password !== confirmPassword && (
              <p style={{ fontSize: '13px', color: '#ef4444', margin: '6px 0 0 0' }}>Las contraseñas no coinciden</p>
            )}
            {confirmPassword && password === confirmPassword && password.length >= 6 && (
              <p style={{ fontSize: '13px', color: '#16a34a', margin: '6px 0 0 0' }}>Las contraseñas coinciden</p>
            )}
          </div>

          {/* Referral Code Field */}
          <div style={{ marginBottom: '20px' }}>
            <label style={labelStyle}>Código de referido (opcional)</label>
            <div style={{ position: 'relative' }}>
              <div style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }}>
                <Gift size={20} />
              </div>
              <input
                type="text"
                value={referralCode}
                onChange={(e) => setReferralCode(e.target.value.toUpperCase())}
                placeholder="Ej: JUAN2025"
                data-testid="register-referral-input"
                style={{
                  ...inputStyle,
                  paddingLeft: '48px',
                  textTransform: 'uppercase'
                }}
              />
            </div>
            {referralCode && (
              <p style={{ fontSize: '13px', color: '#6366f1', margin: '6px 0 0 0' }}>
                🎁 ¡Código aplicado! Tu referidor recibirá una bonificación.
              </p>
            )}
          </div>

          {/* Aceptar términos */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', margin: '0 0 16px 0' }}>
            <input
              type="checkbox"
              id="acceptTerms"
              checked={acceptedTerms}
              onChange={(e) => setAcceptedTerms(e.target.checked)}
              style={{ marginTop: '3px', cursor: 'pointer' }}
            />
            <label htmlFor="acceptTerms" style={{ fontSize: '13px', color: '#6b7280', lineHeight: 1.5, cursor: 'pointer' }}>
              He leído y acepto los{' '}
              <a href="/legal#terminos" target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'underline' }}>Términos y Condiciones</a>
              {' '}y la{' '}
              <a href="/legal#privacidad" target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'underline' }}>Política de Privacidad</a>.
            </label>
          </div>
          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !acceptedTerms}
            data-testid="register-submit-btn"
            style={{
              ...buttonStyle,
              opacity: loading ? 0.6 : 1,
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            {loading ? 'Enviando código...' : 'Continuar'}
          </button>
        </form>

        {/* Login Link */}
        <p style={{ textAlign: 'center', fontSize: '15px', color: '#6b7280', marginTop: '24px' }}>
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" style={{ color: '#6366f1', fontWeight: '500', textDecoration: 'none' }}>
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  );
}
