import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
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
    <div className="min-h-screen bg-[#820AD1] flex flex-col" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'}}>
      
      {/* Header */}
      <header className="px-8 py-6">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-lg">
            <span className="text-[#820AD1] font-extrabold text-xl">R</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-6 pb-8">
        <div className="w-full max-w-[420px]">
          
          {/* Welcome Text */}
          <div className="mb-10">
            <h1 className="text-[40px] font-extrabold text-white leading-tight mb-3">
              ¡Hola!
            </h1>
            <p className="text-white/80 text-lg">
              Qué bueno verte de nuevo.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-5">
              <label className="block text-white/90 text-sm font-semibold mb-2 tracking-wide">
                CORREO ELECTRÓNICO
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                placeholder="tu@email.com"
                className="w-full h-[56px] px-5 text-[17px] rounded-2xl border-2 border-white/30 bg-white/10 text-white placeholder-white/50 transition-all focus:border-white focus:bg-white/20 focus:outline-none backdrop-blur-sm"
              />
            </div>

            {/* Password */}
            <div className="mb-5">
              <label className="block text-white/90 text-sm font-semibold mb-2 tracking-wide">
                CONTRASEÑA
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input"
                  placeholder="••••••••"
                  className="w-full h-[56px] px-5 pr-14 text-[17px] rounded-2xl border-2 border-white/30 bg-white/10 text-white placeholder-white/50 transition-all focus:border-white focus:bg-white/20 focus:outline-none backdrop-blur-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={22}/> : <Eye size={22}/>}
                </button>
              </div>
            </div>

            {/* Forgot Password */}
            <div className="mb-8">
              <Link 
                to="/forgot-password" 
                className="text-white font-semibold text-[15px] hover:underline"
                data-testid="forgot-password-link"
              >
                Olvidé mi contraseña
              </Link>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[58px] bg-white hover:bg-white/95 text-[#820AD1] font-bold text-[17px] rounded-full transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-3 shadow-lg hover:shadow-xl hover:scale-[1.02] active:scale-[0.98]"
            >
              {loading ? (
                <div className="w-6 h-6 border-3 border-[#820AD1]/30 border-t-[#820AD1] rounded-full animate-spin"/>
              ) : (
                <>
                  Entrar a mi cuenta
                  <ArrowRight size={20} strokeWidth={2.5} />
                </>
              )}
            </button>
          </form>

          {/* Register Link */}
          <div className="mt-10 text-center">
            <p className="text-white/70 text-[16px]">
              ¿Primera vez aquí?{' '}
              <Link 
                to="/register" 
                className="text-white font-bold hover:underline"
                data-testid="create-account-link"
              >
                Crea tu cuenta
              </Link>
            </p>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="px-8 py-6">
        <div className="flex items-center justify-center gap-6 text-white/50 text-sm">
          <a href="#" className="hover:text-white transition-colors">Ayuda</a>
          <span className="w-1 h-1 bg-white/30 rounded-full"/>
          <a href="#" className="hover:text-white transition-colors">Privacidad</a>
          <span className="w-1 h-1 bg-white/30 rounded-full"/>
          <a href="#" className="hover:text-white transition-colors">Términos</a>
        </div>
      </footer>
    </div>
  );
}
