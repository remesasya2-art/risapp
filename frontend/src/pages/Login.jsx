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
    <div className="min-h-screen bg-white flex flex-col" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif'}}>
      
      {/* Header */}
      <header className="py-4 px-6">
        <Link to="/" className="inline-flex items-center">
          <svg className="w-10 h-10 text-black" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
          </svg>
        </Link>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-4 pb-20">
        <div className="w-full max-w-[400px]">
          
          <h1 className="text-[32px] font-semibold text-black text-center mb-2" style={{letterSpacing: '-0.02em'}}>
            Inicia sesión
          </h1>
          <p className="text-[17px] text-[#6e6e73] text-center mb-8">
            con tu cuenta de RIS
          </p>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-4">
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Correo electrónico"
                  data-testid="login-email-input"
                  className="w-full h-[56px] px-4 text-[17px] rounded-xl border-2 border-[#d2d2d7] bg-white text-black placeholder-[#86868b] transition-all duration-200 focus:border-[#0071e3] focus:outline-none"
                />
              </div>
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
                  className="w-full h-[56px] px-4 pr-12 text-[17px] rounded-xl border-2 border-[#d2d2d7] bg-white text-black placeholder-[#86868b] transition-all duration-200 focus:border-[#0071e3] focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[#86868b] hover:text-black"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={20}/> : <Eye size={20}/>}
                </button>
              </div>
            </div>

            {/* Forgot password */}
            <div className="text-right mb-6">
              <Link 
                to="/forgot-password" 
                className="text-[14px] text-[#0071e3] hover:underline"
                data-testid="forgot-password-link"
              >
                ¿Olvidaste tu contraseña?
              </Link>
            </div>

            {/* Sign in button */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[56px] text-[17px] font-medium text-white bg-[#0071e3] hover:bg-[#0077ed] rounded-xl transition-all disabled:opacity-50"
            >
              {loading ? 'Iniciando...' : 'Iniciar sesión'}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center my-8">
            <div className="flex-1 h-px bg-[#d2d2d7]"/>
            <span className="px-4 text-[14px] text-[#86868b]">o</span>
            <div className="flex-1 h-px bg-[#d2d2d7]"/>
          </div>

          {/* Create account */}
          <Link 
            to="/register"
            className="block w-full h-[56px] text-[17px] font-medium text-[#0071e3] bg-white border-2 border-[#0071e3] hover:bg-[#f5f5f7] rounded-xl transition-all flex items-center justify-center"
            data-testid="create-account-link"
          >
            Crear cuenta nueva
          </Link>

        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 px-6 border-t border-[#d2d2d7]">
        <div className="flex items-center justify-center gap-6 text-[12px] text-[#6e6e73]">
          <span>© 2024 RIS</span>
          <a href="#" className="hover:text-black">Privacidad</a>
          <a href="#" className="hover:text-black">Términos</a>
        </div>
      </footer>
    </div>
  );
}
