import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff } from 'lucide-react';
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
    <div className="min-h-screen bg-white relative overflow-hidden" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Ubuntu, sans-serif'}}>
      {/* Exact Stripe background image */}
      <div 
        className="absolute top-0 right-0 w-[50%] h-full bg-no-repeat bg-right bg-cover"
        style={{
          backgroundImage: `url('https://b.stripecdn.com/site-statics-srv/assets/assets/img/v3/home-new/login-wave-dpr1-lg-3000x2500-f5c9a2df22d0e3e6ef68bde05c64df0e86e9e83c.webp')`,
        }}
      />

      {/* Vertical line - exactly at 200px from left */}
      <div className="absolute top-0 left-[200px] w-px h-full bg-[#e3e8ee] hidden lg:block" />
      
      {/* Horizontal line - exactly at 60px from top */}
      <div className="absolute top-[60px] left-0 right-0 h-px bg-[#e3e8ee]" />
      
      {/* Horizontal line - exactly at 60px from bottom */}
      <div className="absolute bottom-[52px] left-0 right-0 h-px bg-[#e3e8ee]" />

      {/* Header */}
      <header className="relative z-10 h-[60px] flex items-center pl-8">
        <div className="flex items-center gap-1">
          <svg className="w-[40px] h-[40px]" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="8" fill="#EE931F"/>
            <path d="M20 12L26 28H14L20 12Z" fill="white"/>
          </svg>
          <span className="text-[22px] font-semibold text-[#737070] ml-1">RIS</span>
        </div>
      </header>

      {/* Main content */}
      <main className="relative z-10 pt-[60px] pl-8 lg:pl-[248px]">
        {/* Card */}
        <div 
          className="w-[400px] max-w-[calc(100vw-32px)] bg-white rounded-[8px]"
          style={{
            boxShadow: '0 15px 35px 0 rgba(60,66,87,.08), 0 5px 15px 0 rgba(0,0,0,.12)'
          }}
        >
          <div className="p-10">
            {/* Title */}
            <h1 className="text-[24px] font-normal text-[#3c4257] mb-8" style={{letterSpacing: '-0.02em'}}>
              Inicia sesión en tu cuenta
            </h1>

            <form onSubmit={handleSubmit}>
              {/* Email */}
              <div className="mb-4">
                <label className="block text-[14px] font-medium text-[#3c4257] mb-1">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-[40px] px-3 text-[14px] rounded-[6px] border border-[#e3e8ee] bg-white text-[#3c4257] focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 focus:outline-none transition-shadow"
                  style={{boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02)'}}
                />
              </div>

              {/* Password */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[14px] font-medium text-[#3c4257]">Contraseña</label>
                  <Link to="/forgot-password" className="text-[14px] text-[#EE931F] hover:text-[#d17f17]">
                    ¿No recuerdas la contraseña?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-[40px] px-3 pr-10 text-[14px] rounded-[6px] border border-[#e3e8ee] bg-white text-[#3c4257] focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 focus:outline-none transition-shadow"
                    style={{boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02)'}}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8898aa] hover:text-[#3c4257]"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {/* Remember me */}
              <label className="flex items-center gap-2 mb-6 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded-[4px] border-[#e3e8ee] text-[#EE931F] focus:ring-[#EE931F]/30"
                />
                <span className="text-[14px] text-[#3c4257]">Recuérdame en este dispositivo</span>
              </label>

              {/* Submit button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-[40px] text-[14px] font-medium text-white rounded-[6px] transition-all disabled:opacity-60"
                style={{
                  backgroundColor: '#EE931F',
                  boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02), 0 0 0 1px rgba(238,147,31,.3), inset 0 1px 0 rgba(255,255,255,.1)'
                }}
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 h-px bg-[#e3e8ee]" />
              <span className="text-[12px] text-[#8898aa] uppercase tracking-wider">o</span>
              <div className="flex-1 h-px bg-[#e3e8ee]" />
            </div>

            {/* Social buttons */}
            <div className="space-y-3">
              {/* Google */}
              <button 
                className="w-full h-[40px] flex items-center justify-center gap-2 text-[14px] font-medium text-[#3c4257] bg-white rounded-[6px] border border-[#e3e8ee] hover:bg-[#f7fafc] transition-colors"
                style={{boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02)'}}
              >
                <svg width="18" height="18" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                Inicia sesión con Google
              </button>

              {/* Passkey */}
              <button 
                className="w-full h-[40px] flex items-center justify-center gap-2 text-[14px] font-medium text-[#3c4257] bg-white rounded-[6px] border border-[#e3e8ee] hover:bg-[#f7fafc] transition-colors"
                style={{boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02)'}}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3c4257" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="6" r="3"/>
                  <path d="M15.5 8.5L12 12l-1.5 1.5"/>
                  <path d="M10.5 13.5L9 15l-1.5 1.5L6 18l-3 3"/>
                  <path d="m7.5 16.5 1.5 1.5"/>
                  <path d="m10.5 13.5 1.5 1.5"/>
                </svg>
                Iniciar sesión con una clave de acceso
              </button>

              {/* SSO */}
              <button 
                className="w-full h-[40px] flex items-center justify-center gap-2 text-[14px] font-medium text-[#3c4257] bg-white rounded-[6px] border border-[#e3e8ee] hover:bg-[#f7fafc] transition-colors"
                style={{boxShadow: '0 1px 1px rgba(0,0,0,.03), 0 3px 6px rgba(0,0,0,.02)'}}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3c4257" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 20h20"/>
                  <path d="M5 20V4h14v16"/>
                  <path d="M9 4v16"/>
                  <path d="M13 8h2"/>
                  <path d="M13 12h2"/>
                </svg>
                Iniciar sesión con SSO
              </button>
            </div>
          </div>

          {/* Bottom section - light blue */}
          <div className="px-10 py-4 bg-[#f7fafc] rounded-b-[8px] border-t border-[#e3e8ee]">
            <p className="text-[14px] text-[#3c4257] text-center">
              ¿Eres nuevo en RIS?{' '}
              <Link to="/register" className="text-[#EE931F] hover:text-[#d17f17]">
                Crea una cuenta
              </Link>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="absolute bottom-0 left-0 z-10 h-[52px] flex items-center pl-8 gap-4">
        <span className="text-[12px] text-[#8898aa]">© RIS</span>
        <a href="#" className="text-[12px] text-[#8898aa] hover:text-[#3c4257]">Privacidad y condiciones</a>
      </footer>
    </div>
  );
}
