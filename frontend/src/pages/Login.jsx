import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const { rates } = useRate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

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
    <div className="min-h-screen relative overflow-hidden font-['Inter',system-ui,sans-serif]" data-testid="login-page">
      {/* Aurora/Mesh Gradient Background */}
      <div className="absolute inset-0 bg-[#FFF3CD]">
        {/* Fluid gradient waves - Aurora style */}
        <svg className="absolute top-0 right-0 w-full h-full" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
          <defs>
            <linearGradient id="aurora1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#87CEEB" stopOpacity="0.6"/>
              <stop offset="50%" stopColor="#FFF3CD" stopOpacity="0.3"/>
              <stop offset="100%" stopColor="#EE931F" stopOpacity="0.5"/>
            </linearGradient>
            <linearGradient id="aurora2" x1="100%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#EE931F" stopOpacity="0.7"/>
              <stop offset="40%" stopColor="#FF69B4" stopOpacity="0.6"/>
              <stop offset="100%" stopColor="#9370DB" stopOpacity="0.5"/>
            </linearGradient>
            <linearGradient id="aurora3" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="0%" stopColor="#FF1493" stopOpacity="0.5"/>
              <stop offset="100%" stopColor="#8A2BE2" stopOpacity="0.4"/>
            </linearGradient>
          </defs>
          
          {/* Light blue wave */}
          <path d="M800 0 Q900 100, 850 250 Q800 400, 900 550 Q1000 700, 950 800 L1200 800 L1200 0 Z" fill="url(#aurora1)"/>
          
          {/* Orange to pink wave */}
          <path d="M900 0 Q1000 150, 950 300 Q900 450, 1000 600 Q1100 750, 1050 800 L1200 800 L1200 0 Z" fill="url(#aurora2)"/>
          
          {/* Pink to purple wave */}
          <path d="M950 100 Q1050 250, 1000 400 Q950 550, 1050 700 Q1150 800, 1100 850 L1200 850 L1200 100 Z" fill="url(#aurora3)"/>
        </svg>
      </div>

      {/* Vertical line accent */}
      <div className="absolute top-0 left-[180px] w-px h-full bg-[#737070]/20 hidden lg:block"></div>

      {/* Header */}
      <header className="relative z-10 px-6 lg:px-12 py-6">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-[#EE931F] flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white" />
          </div>
          <span className="text-2xl font-bold text-[#737070]">RIS</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-140px)] px-4 py-8">
        {/* Glassmorphism Card */}
        <div className="w-full max-w-[420px] mx-auto lg:ml-[15%] lg:mr-auto">
          <div 
            className="bg-white/85 backdrop-blur-xl rounded-lg border border-[#737070]/30 shadow-2xl overflow-hidden"
            style={{ boxShadow: '0 25px 50px -12px rgba(115, 112, 112, 0.15)' }}
          >
            {/* Form Content */}
            <div className="p-8 lg:p-10">
              <h1 className="text-[26px] font-semibold text-[#737070] mb-8">
                Inicia sesión en tu cuenta
              </h1>

              <form onSubmit={handleSubmit}>
                {/* Email Field */}
                <div className="mb-5">
                  <label className="block text-[14px] text-[#737070] mb-2">
                    Correo electrónico
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full h-[48px] px-4 rounded-[8px] border border-[#737070]/30 bg-white focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 focus:outline-none transition-all text-[#737070]"
                    data-testid="email-input"
                  />
                </div>

                {/* Password Field */}
                <div className="mb-5">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-[14px] text-[#737070]">
                      Contraseña
                    </label>
                    <Link to="/forgot-password" className="text-[14px] text-[#EE931F] hover:text-[#EE931F]/80">
                      ¿No recuerdas la contraseña?
                    </Link>
                  </div>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full h-[48px] px-4 pr-12 rounded-[8px] border border-[#737070]/30 bg-white focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 focus:outline-none transition-all text-[#737070]"
                      data-testid="password-input"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-[#737070]/50 hover:text-[#737070]"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                {/* Remember Me */}
                <label className="flex items-center gap-3 mb-6 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="w-5 h-5 rounded border-[#737070]/30 text-[#EE931F] focus:ring-[#EE931F]/30 cursor-pointer"
                  />
                  <span className="text-[14px] text-[#737070]">Recuérdame en este dispositivo</span>
                </label>

                {/* Submit Button with Glow */}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full h-[48px] bg-[#EE931F] hover:bg-[#EE931F]/90 text-white font-medium rounded-[8px] transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-[0_0_20px_rgba(238,147,31,0.4)]"
                  data-testid="login-button"
                >
                  {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
                </button>
              </form>

              {/* Divider */}
              <div className="flex items-center gap-4 my-6">
                <div className="flex-1 h-px bg-[#737070]/20"></div>
                <span className="text-[14px] text-[#737070]/50">o</span>
                <div className="flex-1 h-px bg-[#737070]/20"></div>
              </div>

              {/* Social Login Buttons */}
              <div className="space-y-3">
                {/* Google Button */}
                <button className="w-full h-[48px] bg-white hover:bg-gray-50 text-[#737070] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-3 transition-all">
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                  </svg>
                  Inicia sesión con Google
                </button>

                {/* SSO Button */}
                <button className="w-full h-[48px] bg-white hover:bg-gray-50 text-[#737070] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-2 transition-all">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                  </svg>
                  Iniciar sesión con una clave de acceso
                </button>

                {/* Passkey Button */}
                <button className="w-full h-[48px] bg-white hover:bg-gray-50 text-[#737070] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-2 transition-all">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                  Iniciar sesión con SSO
                </button>
              </div>
            </div>

            {/* Register Section - Light blue background */}
            <div className="bg-[#E8F4FD] px-8 lg:px-10 py-5">
              <p className="text-[14px] text-[#737070] text-center">
                ¿Eres nuevo en RIS?{' '}
                <Link to="/register" className="text-[#EE931F] font-medium hover:underline">
                  Crea una cuenta
                </Link>
              </p>
            </div>
          </div>

          {/* Rate Info */}
          <div className="mt-4 text-center lg:text-left">
            <p className="text-[13px] text-[#737070]/60">
              Tasa actual: <span className="font-medium text-[#737070]">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 px-6 lg:px-12 py-4">
        <div className="flex items-center gap-4 text-[13px] text-[#737070]/60">
          <span>© RIS</span>
          <a href="#" className="hover:text-[#737070]">Privacidad y condiciones</a>
        </div>
      </footer>
    </div>
  );
}
