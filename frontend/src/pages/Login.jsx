import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff } from 'lucide-react';
import toast from 'react-hot-toast';
import PasswordRecovery from './PasswordRecovery';
import TwoFactorFlow from '../components/auth/TwoFactorFlow';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showRecovery, setShowRecovery] = useState(false);
  const [twoFactorState, setTwoFactorState] = useState(null); // { mode, pendingToken, email }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    setLoading(true);
    try {
      const response = await login(email, password);

      // Handle 2FA challenge or enrollment
      if (response.two_factor_required) {
        setTwoFactorState({ mode: 'verify', pendingToken: response.pending_token, email: response.email });
        return;
      }
      if (response.two_factor_enrollment_required) {
        setTwoFactorState({ mode: 'enroll', pendingToken: response.pending_token, email: response.email });
        return;
      }

      // Normal flow
      if (response.must_change_password) {
        toast.success('Por favor establece una nueva contraseña');
        navigate('/force-change-password');
      } else {
        toast.success('¡Bienvenido!');
        navigate('/');
      }
    } catch (error) {
      // 429 Rate limit (slowapi devuelve {"error": "..."} no {"detail": "..."})
      if (error.response?.status === 429) {
        toast.error('Demasiados intentos. Espera unos minutos e intenta de nuevo.', { duration: 5000 });
      } else {
        toast.error(error.response?.data?.detail || 'Error al iniciar sesión');
      }
    } finally {
      setLoading(false);
    }
  };

  if (twoFactorState) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, backgroundColor: '#f9fafb' }}>
        <TwoFactorFlow
          mode={twoFactorState.mode}
          pendingToken={twoFactorState.pendingToken}
          email={twoFactorState.email}
          onSuccess={() => {
            toast.success('¡Bienvenido!');
            navigate('/');
          }}
        />
      </div>
    );
  }

  const inputStyle = {
    borderRadius: '14px',
    border: '1px solid #d1d5db',
    height: '56px'
  };

  const buttonStyle = {
    borderRadius: '14px',
    height: '56px'
  };

  // Show password recovery flow
  if (showRecovery) {
    return (
      <PasswordRecovery 
        onBack={() => setShowRecovery(false)} 
        onSuccess={() => {
          setShowRecovery(false);
          toast.success('Ahora puedes iniciar sesión con tu nueva contraseña');
        }}
      />
    );
  }

  return (
    <div 
      className="min-h-screen flex items-center justify-center p-4"
      style={{
        fontFamily: 'Inter, Helvetica, -apple-system, sans-serif',
        background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)'
      }}
    >
      <div 
        className="w-full max-w-md bg-white"
        style={{
          borderRadius: '24px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.08), 0 12px 24px -8px rgba(0, 0, 0, 0.04)',
          padding: '48px 40px'
        }}
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <img 
            src="/logo-ris.png" 
            alt="RIS" 
            className="h-24 w-auto"
            style={{ borderRadius: '16px' }}
          />
        </div>

        {/* Title */}
        <h1 className="text-3xl font-bold text-gray-900 text-center mb-2">
          Iniciar Sesión
        </h1>
        <p className="text-gray-400 text-center text-base mb-8">
          Accede a tu cuenta
        </p>

        {/* Google Button */}
        <button 
          className="w-full flex items-center justify-center gap-3 text-base font-medium text-gray-700 bg-white hover:bg-gray-50 transition-all mb-6"
          style={{ ...buttonStyle, border: '1px solid #d1d5db' }}
          data-testid="google-login-btn"
        >
          <svg width="20" height="20" viewBox="0 0 18 18">
            <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"></path>
            <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"></path>
            <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"></path>
            <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"></path>
          </svg>
          Continuar con Google
        </button>

        {/* Divider */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1 h-px bg-gray-200"></div>
          <span className="text-gray-400 text-xs uppercase tracking-wider">O continúa con email</span>
          <div className="flex-1 h-px bg-gray-200"></div>
        </div>

        <form onSubmit={handleSubmit} data-testid="login-form">
          {/* Email */}
          <div className="mb-5">
            <label className="block text-gray-700 text-sm font-medium mb-2">Correo electrónico</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              data-testid="email-input"
              className="w-full px-4 text-base text-gray-900 bg-white focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20 outline-none transition-all"
              style={inputStyle}
            />
          </div>

          {/* Password */}
          <div className="mb-6">
            <label className="block text-gray-700 text-sm font-medium mb-2">Contraseña</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="password-input"
                className="w-full px-4 pr-12 text-base text-gray-900 bg-white focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20 outline-none transition-all"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                data-testid="toggle-password"
              >
                {showPassword ? <EyeOff size={20} strokeWidth={1.5} /> : <Eye size={20} strokeWidth={1.5} />}
              </button>
            </div>
          </div>

          {/* Forgot Password Link */}
          <div className="text-right mb-4">
            <button
              type="button"
              onClick={() => setShowRecovery(true)}
              className="text-[#6366f1] text-sm font-medium hover:underline"
              data-testid="forgot-password-link"
            >
              ¿Olvidaste tu contraseña?
            </button>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            data-testid="login-submit-btn"
            className="w-full bg-[#6366f1] hover:bg-[#5558e3] text-white font-bold text-base transition-all disabled:opacity-50"
            style={buttonStyle}
          >
            {loading ? 'Iniciando sesión...' : 'Iniciar Sesión'}
          </button>
        </form>

        {/* Register Link */}
        <p className="text-center text-gray-500 text-base mt-6">
          ¿No tienes cuenta?{' '}
          <Link to="/register" className="text-[#6366f1] font-medium hover:underline" data-testid="register-link">
            Regístrate
          </Link>
        </p>
      </div>
    </div>
  );
}
