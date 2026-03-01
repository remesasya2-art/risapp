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
    <div className="min-h-screen bg-[#820ad1] flex flex-col" style={{fontFamily: 'Inter, -apple-system, sans-serif'}}>
      
      {/* Header */}
      <header className="px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
            <span className="text-[#820ad1] font-bold text-lg">R</span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-6">
        <div className="w-full max-w-[400px]">
          
          <h1 className="text-[36px] font-bold text-white mb-3 leading-tight">
            ¡Hola!
          </h1>
          <p className="text-white/80 text-[17px] mb-10">
            Qué bueno verte de nuevo.
          </p>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-5">
              <label className="block text-white/90 text-sm font-medium mb-2">Tu email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                className="w-full h-[58px] px-5 text-[16px] rounded-2xl border-2 border-white/20 bg-white/10 text-white placeholder-white/50 transition-all focus:border-white focus:bg-white/20 focus:outline-none"
                placeholder="nombre@email.com"
              />
            </div>

            {/* Password */}
            <div className="mb-5">
              <label className="block text-white/90 text-sm font-medium mb-2">Tu contraseña</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input"
                  className="w-full h-[58px] px-5 pr-14 text-[16px] rounded-2xl border-2 border-white/20 bg-white/10 text-white placeholder-white/50 transition-all focus:border-white focus:bg-white/20 focus:outline-none"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-white/60 hover:text-white"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={22}/> : <Eye size={22}/>}
                </button>
              </div>
            </div>

            {/* Forgot password */}
            <div className="mb-8">
              <Link to="/forgot-password" className="text-white font-medium text-[15px] hover:underline" data-testid="forgot-password-link">
                Olvidé mi contraseña
              </Link>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[58px] bg-white hover:bg-white/90 text-[#820ad1] font-bold text-[16px] rounded-2xl transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? 'Ingresando...' : (
                <>
                  Entrar a mi cuenta
                  <ArrowRight size={20} />
                </>
              )}
            </button>
          </form>

          {/* Register */}
          <div className="mt-8 text-center">
            <p className="text-white/70 text-[15px]">
              ¿Aún no tienes cuenta?{' '}
              <Link to="/register" className="text-white font-bold hover:underline" data-testid="create-account-link">
                Regístrate
              </Link>
            </p>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="px-6 py-5">
        <div className="flex items-center justify-center gap-6 text-white/50 text-xs">
          <a href="#" className="hover:text-white">Ayuda</a>
          <span>•</span>
          <a href="#" className="hover:text-white">Privacidad</a>
          <span>•</span>
          <a href="#" className="hover:text-white">Términos</a>
        </div>
      </footer>
    </div>
  );
}
