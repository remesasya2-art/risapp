import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Fingerprint, Smartphone } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Por favor completa todos los campos');
      return;
    }
    setLoading(true);
    try {
      await login(email, password);
      toast.success('¡Bienvenido!');
      navigate('/');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d0d0d] flex flex-col" style={{fontFamily: 'Inter, -apple-system, sans-serif'}}>
      
      {/* Header */}
      <header className="px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#00d4aa] rounded-lg flex items-center justify-center">
            <span className="text-black font-bold text-sm">R</span>
          </div>
          <span className="text-white font-semibold text-lg">RIS</span>
        </div>
        <Link to="/register" className="text-[#00d4aa] text-sm font-medium hover:underline">
          Crear cuenta
        </Link>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-6 pb-10">
        <div className="w-full max-w-[380px]">
          
          <h1 className="text-[28px] font-bold text-white mb-2">
            Bienvenido
          </h1>
          <p className="text-[#6b7280] text-[15px] mb-8">
            Ingresa a tu cuenta para continuar
          </p>

          {/* Biometric options */}
          <div className="grid grid-cols-2 gap-3 mb-8">
            <button className="h-[72px] bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl flex flex-col items-center justify-center gap-2 hover:border-[#00d4aa]/50 transition-all group">
              <Fingerprint className="w-6 h-6 text-[#00d4aa]" />
              <span className="text-white/70 text-xs group-hover:text-white">Touch ID</span>
            </button>
            <button className="h-[72px] bg-[#1a1a1a] border border-[#2a2a2a] rounded-2xl flex flex-col items-center justify-center gap-2 hover:border-[#00d4aa]/50 transition-all group">
              <Smartphone className="w-6 h-6 text-[#00d4aa]" />
              <span className="text-white/70 text-xs group-hover:text-white">Face ID</span>
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-8">
            <div className="flex-1 h-px bg-[#2a2a2a]"/>
            <span className="text-[#6b7280] text-xs uppercase tracking-wider">o usa tu email</span>
            <div className="flex-1 h-px bg-[#2a2a2a]"/>
          </div>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-4">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                data-testid="login-email-input"
                className="w-full h-[56px] px-5 text-[15px] rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] text-white placeholder-[#6b7280] transition-all focus:border-[#00d4aa] focus:outline-none"
              />
            </div>

            {/* Password */}
            <div className="mb-4">
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Contraseña"
                  data-testid="login-password-input"
                  className="w-full h-[56px] px-5 pr-14 text-[15px] rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] text-white placeholder-[#6b7280] transition-all focus:border-[#00d4aa] focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-[#6b7280] hover:text-white"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={20}/> : <Eye size={20}/>}
                </button>
              </div>
            </div>

            {/* Forgot password */}
            <div className="text-right mb-6">
              <Link to="/forgot-password" className="text-[#00d4aa] text-sm hover:underline" data-testid="forgot-password-link">
                ¿Olvidaste tu contraseña?
              </Link>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[56px] bg-[#00d4aa] hover:bg-[#00e5b8] text-black font-semibold text-[15px] rounded-2xl transition-all disabled:opacity-50"
            >
              {loading ? 'Ingresando...' : 'Continuar'}
            </button>
          </form>

        </div>
      </main>

      {/* Footer */}
      <footer className="px-6 py-4 border-t border-[#1a1a1a]">
        <p className="text-center text-[#6b7280] text-xs">
          Al continuar, aceptas nuestros <a href="#" className="text-[#00d4aa] hover:underline">Términos</a> y <a href="#" className="text-[#00d4aa] hover:underline">Privacidad</a>
        </p>
      </footer>
    </div>
  );
}
