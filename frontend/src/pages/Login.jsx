import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Wallet } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
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
    <div className="min-h-screen bg-white relative" data-testid="login-page">
      {/* Vertical line - exactly like Stripe */}
      <div className="absolute top-0 left-[200px] w-[1px] h-full bg-[#737070]/20 hidden lg:block"></div>
      
      {/* Horizontal line below header */}
      <div className="absolute top-[60px] left-0 right-0 h-[1px] bg-[#737070]/20"></div>

      {/* Aurora gradient - RIGHT SIDE ONLY like Stripe */}
      <div className="absolute top-0 right-0 w-[55%] h-full overflow-hidden pointer-events-none">
        <svg className="absolute top-0 right-0 h-full" style={{width: '100%', minWidth: '600px'}} viewBox="0 0 600 900" preserveAspectRatio="xMaxYMid slice">
          {/* Light blue/cyan wave */}
          <path 
            d="M250 0 C300 150, 200 300, 280 450 C360 600, 280 750, 350 900 L600 900 L600 0 Z" 
            fill="#87CEEB" 
            opacity="0.5"
          />
          {/* Orange wave */}
          <path 
            d="M320 0 C400 200, 300 350, 400 500 C500 650, 400 800, 480 900 L600 900 L600 0 Z" 
            fill="#EE931F" 
            opacity="0.6"
          />
          {/* Pink/magenta wave */}
          <path 
            d="M380 0 C480 180, 400 360, 500 540 C600 720, 520 850, 580 900 L600 900 L600 0 Z" 
            fill="#FF69B4" 
            opacity="0.6"
          />
          {/* Purple wave */}
          <path 
            d="M450 50 C550 200, 480 400, 560 600 C640 800, 580 880, 620 950 L650 950 L650 50 Z" 
            fill="#9370DB" 
            opacity="0.5"
          />
        </svg>
      </div>

      {/* Header - Logo top left */}
      <header className="relative z-10 h-[60px] flex items-center px-6 lg:px-8">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-[#EE931F] flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold text-[#737070]">RIS</span>
        </div>
      </header>

      {/* Main - Card positioned like Stripe */}
      <main className="relative z-10 flex justify-center lg:justify-start px-4 lg:px-0 pt-12 lg:pt-20">
        <div className="w-full max-w-[400px] lg:ml-[240px]">
          {/* White Card - Simple shadow like Stripe */}
          <div className="bg-white rounded-lg shadow-[0_15px_35px_rgba(0,0,0,0.1)] border border-gray-100 p-8">
            {/* Title - Left aligned */}
            <h1 className="text-[24px] font-medium text-[#737070] mb-8">
              Inicia sesión en tu cuenta
            </h1>

            <form onSubmit={handleSubmit}>
              {/* Email */}
              <div className="mb-6">
                <label className="block text-[14px] text-[#737070] mb-2">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-[44px] px-3 rounded-[8px] border border-[#737070]/40 focus:border-[#EE931F] focus:ring-1 focus:ring-[#EE931F] focus:outline-none transition-colors text-[#737070]"
                  data-testid="email-input"
                />
              </div>

              {/* Password */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[14px] text-[#737070]">Contraseña</label>
                  <Link to="/forgot-password" className="text-[14px] text-[#EE931F] hover:underline">
                    ¿No recuerdas la contraseña?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-[44px] px-3 pr-10 rounded-[8px] border border-[#737070]/40 focus:border-[#EE931F] focus:ring-1 focus:ring-[#EE931F] focus:outline-none transition-colors text-[#737070]"
                    data-testid="password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#737070]/60 hover:text-[#737070]"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              {/* Remember me checkbox */}
              <label className="flex items-center gap-2 mb-6 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded border-[#737070]/40 text-[#EE931F] focus:ring-[#EE931F]"
                />
                <span className="text-[14px] text-[#737070]">Recuérdame en este dispositivo</span>
              </label>

              {/* Submit button - Orange */}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-[44px] bg-[#EE931F] hover:bg-[#d98419] text-white font-medium rounded-[8px] transition-colors disabled:opacity-50"
                data-testid="login-button"
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-3 my-6">
              <div className="flex-1 h-[1px] bg-[#737070]/20"></div>
              <span className="text-[14px] text-[#737070]/50">o</span>
              <div className="flex-1 h-[1px] bg-[#737070]/20"></div>
            </div>

            {/* Social buttons - Gray border like Stripe */}
            <div className="space-y-3">
              {/* Google */}
              <button className="w-full h-[44px] bg-white hover:bg-gray-50 text-[#737070] text-[14px] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-2 transition-colors">
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Inicia sesión con Google
              </button>

              {/* Passkey */}
              <button className="w-full h-[44px] bg-white hover:bg-gray-50 text-[#737070] text-[14px] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-2 transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
                </svg>
                Iniciar sesión con una clave de acceso
              </button>

              {/* SSO */}
              <button className="w-full h-[44px] bg-white hover:bg-gray-50 text-[#737070] text-[14px] font-medium rounded-[8px] border border-[#737070]/30 flex items-center justify-center gap-2 transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z" />
                </svg>
                Iniciar sesión con SSO
              </button>
            </div>

            {/* Register section - Light blue background like Stripe */}
            <div className="mt-6 -mx-8 -mb-8 px-8 py-5 bg-[#E8F4FD] rounded-b-lg">
              <p className="text-[14px] text-[#737070] text-center">
                ¿Eres nuevo en RIS?{' '}
                <Link to="/register" className="text-[#EE931F] hover:underline">
                  Crea una cuenta
                </Link>
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Footer - Bottom left like Stripe */}
      <footer className="absolute bottom-0 left-0 z-10 px-6 lg:px-8 py-4">
        <div className="flex items-center gap-4 text-[13px] text-[#737070]/60">
          <span>© RIS</span>
          <a href="#" className="hover:text-[#737070]">Privacidad y condiciones</a>
        </div>
      </footer>
    </div>
  );
}
