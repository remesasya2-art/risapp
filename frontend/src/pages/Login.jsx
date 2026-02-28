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
    <div className="min-h-screen bg-[#FFF3CD] relative overflow-hidden" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'}}>
      {/* Background waves - right side */}
      <div className="absolute top-0 right-0 w-[55%] h-full pointer-events-none">
        <svg className="absolute top-0 right-0 w-full h-full" viewBox="0 0 800 1000" preserveAspectRatio="xMaxYMid slice">
          <defs>
            <linearGradient id="w1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#80E5FF"/>
              <stop offset="100%" stopColor="#80E5FF"/>
            </linearGradient>
            <linearGradient id="w2" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#EE931F"/>
              <stop offset="100%" stopColor="#F5A623"/>
            </linearGradient>
            <linearGradient id="w3" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FF6B9D"/>
              <stop offset="100%" stopColor="#FF8FB1"/>
            </linearGradient>
            <linearGradient id="w4" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#C17FFF"/>
              <stop offset="100%" stopColor="#9F6FE8"/>
            </linearGradient>
          </defs>
          <path d="M300 0 C400 200, 250 400, 350 600 C450 800, 300 900, 400 1000 L800 1000 L800 0 Z" fill="url(#w1)" opacity="0.9"/>
          <path d="M420 0 C520 180, 380 380, 480 580 C580 780, 430 900, 530 1000 L800 1000 L800 0 Z" fill="url(#w2)" opacity="0.9"/>
          <path d="M520 0 C620 160, 490 360, 590 560 C690 760, 540 900, 640 1000 L800 1000 L800 0 Z" fill="url(#w3)" opacity="0.9"/>
          <path d="M620 0 C720 140, 600 340, 700 540 C800 740, 650 900, 750 1000 L800 1000 L800 0 Z" fill="url(#w4)" opacity="0.9"/>
        </svg>
      </div>

      {/* Grid lines */}
      <div className="absolute top-0 left-[200px] w-px h-full bg-[#737070]/15 hidden lg:block"/>
      <div className="absolute top-[60px] left-0 right-0 h-px bg-[#737070]/15"/>
      <div className="absolute bottom-[50px] left-0 right-0 h-px bg-[#737070]/15"/>

      {/* Header - Logo */}
      <header className="relative z-10 h-[60px] flex items-center px-8">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-[#EE931F] flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white"/>
          </div>
          <span className="text-xl font-bold text-[#737070]">RIS</span>
        </div>
      </header>

      {/* Main - CENTERED card like Stripe */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-110px)] px-4">
        <div 
          className="w-full max-w-[420px] bg-white rounded-lg overflow-hidden"
          style={{boxShadow: '0 15px 35px rgba(0,0,0,0.1), 0 5px 15px rgba(0,0,0,0.07)'}}
        >
          {/* Form section */}
          <div className="p-10">
            <h1 className="text-2xl font-medium text-[#737070] mb-8">
              Inicia sesión en tu cuenta
            </h1>

            <form onSubmit={handleSubmit}>
              {/* Email */}
              <div className="mb-5">
                <label className="block text-sm text-[#737070] mb-2">Correo electrónico</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-12 px-4 text-sm rounded-md border border-[#737070]/30 bg-white text-[#737070] focus:border-[#EE931F] focus:ring-1 focus:ring-[#EE931F] focus:outline-none"
                />
              </div>

              {/* Password */}
              <div className="mb-5">
                <div className="flex justify-between mb-2">
                  <label className="text-sm text-[#737070]">Contraseña</label>
                  <Link to="/forgot-password" className="text-sm text-[#EE931F] hover:underline">
                    ¿No recuerdas la contraseña?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-12 px-4 pr-11 text-sm rounded-md border border-[#737070]/30 bg-white text-[#737070] focus:border-[#EE931F] focus:ring-1 focus:ring-[#EE931F] focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#737070]/50 hover:text-[#737070]"
                  >
                    {showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}
                  </button>
                </div>
              </div>

              {/* Remember me */}
              <label className="flex items-center gap-2 mb-6 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded border-[#737070]/30 text-[#EE931F] focus:ring-[#EE931F]"
                />
                <span className="text-sm text-[#737070]">Recuérdame en este dispositivo</span>
              </label>

              {/* Submit button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-12 text-sm font-medium text-white bg-[#EE931F] hover:bg-[#d98419] rounded-md transition-colors disabled:opacity-50"
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center my-6">
              <div className="flex-1 h-px bg-[#737070]/20"/>
              <span className="px-4 text-sm text-[#737070]/50">o</span>
              <div className="flex-1 h-px bg-[#737070]/20"/>
            </div>

            {/* Social buttons */}
            <div className="space-y-3">
              <button className="w-full h-12 flex items-center justify-center gap-2 text-sm text-[#737070] bg-white rounded-md border border-[#737070]/30 hover:bg-gray-50 transition-colors">
                <svg width="18" height="18" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                Inicia sesión con Google
              </button>

              <button className="w-full h-12 flex items-center justify-center gap-2 text-sm text-[#737070] bg-white rounded-md border border-[#737070]/30 hover:bg-gray-50 transition-colors">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="18" cy="6" r="3"/>
                  <path d="M15.5 8.5L12 12l-1.5 1.5M10.5 13.5L9 15l-1.5 1.5L6 18l-3 3M7.5 16.5l1.5 1.5M10.5 13.5l1.5 1.5"/>
                </svg>
                Iniciar sesión con una clave de acceso
              </button>

              <button className="w-full h-12 flex items-center justify-center gap-2 text-sm text-[#737070] bg-white rounded-md border border-[#737070]/30 hover:bg-gray-50 transition-colors">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M2 20h20M5 20V4h14v16M9 4v16M13 8h2M13 12h2"/>
                </svg>
                Iniciar sesión con SSO
              </button>
            </div>
          </div>

          {/* Bottom section - light background */}
          <div className="px-10 py-5 bg-[#FFF3CD]/50 border-t border-[#737070]/10">
            <p className="text-sm text-[#737070] text-center">
              ¿Eres nuevo en RIS?{' '}
              <Link to="/register" className="text-[#EE931F] hover:underline">Crea una cuenta</Link>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="absolute bottom-0 left-0 z-10 h-[50px] flex items-center px-8 gap-4">
        <span className="text-xs text-[#737070]/60">© RIS</span>
        <a href="#" className="text-xs text-[#737070]/60 hover:text-[#737070]">Privacidad y condiciones</a>
      </footer>
    </div>
  );
}
