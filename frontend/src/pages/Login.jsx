import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Mail, Lock } from 'lucide-react';
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
    <div className="min-h-screen relative overflow-hidden flex items-center justify-center" style={{fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif'}}>
      
      {/* Animated gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#1a1a2e] via-[#16213e] to-[#0f3460]">
        {/* Floating orbs */}
        <div className="absolute top-[10%] left-[10%] w-[500px] h-[500px] bg-purple-500/30 rounded-full blur-[120px] animate-pulse"/>
        <div className="absolute bottom-[10%] right-[10%] w-[400px] h-[400px] bg-blue-500/30 rounded-full blur-[100px] animate-pulse" style={{animationDelay: '1s'}}/>
        <div className="absolute top-[50%] left-[50%] w-[300px] h-[300px] bg-pink-500/20 rounded-full blur-[80px] animate-pulse" style={{animationDelay: '2s'}}/>
      </div>

      {/* Glass card */}
      <div className="relative z-10 w-full max-w-[420px] mx-4">
        <div 
          className="rounded-3xl p-10 border border-white/10"
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255,255,255,0.1)'
          }}
        >
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 mb-4">
              <span className="text-2xl font-bold text-white">R</span>
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">Bienvenido a RIS</h1>
            <p className="text-white/50 text-sm">Ingresa a tu cuenta para continuar</p>
          </div>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-5">
              <label className="block text-sm font-medium text-white/70 mb-2">Correo electrónico</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40"/>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@email.com"
                  data-testid="login-email-input"
                  className="w-full h-[52px] pl-12 pr-4 text-[15px] rounded-xl border border-white/10 bg-white/5 text-white placeholder-white/30 transition-all focus:border-purple-500/50 focus:bg-white/10 focus:outline-none"
                />
              </div>
            </div>

            {/* Password */}
            <div className="mb-5">
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-white/70">Contraseña</label>
                <Link to="/forgot-password" className="text-sm text-purple-400 hover:text-purple-300" data-testid="forgot-password-link">
                  ¿Olvidaste?
                </Link>
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40"/>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  data-testid="login-password-input"
                  className="w-full h-[52px] pl-12 pr-12 text-[15px] rounded-xl border border-white/10 bg-white/5 text-white placeholder-white/30 transition-all focus:border-purple-500/50 focus:bg-white/10 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}
                </button>
              </div>
            </div>

            {/* Sign in button */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[52px] text-[15px] font-semibold text-white rounded-xl transition-all disabled:opacity-50 relative overflow-hidden group"
              style={{
                background: 'linear-gradient(135deg, #7c3aed 0%, #db2777 100%)',
              }}
            >
              <span className="relative z-10">{loading ? 'Ingresando...' : 'Iniciar sesión'}</span>
              <div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-pink-600 opacity-0 group-hover:opacity-100 transition-opacity"/>
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center my-6">
            <div className="flex-1 h-px bg-white/10"/>
            <span className="px-4 text-xs text-white/40 uppercase tracking-wider">o continuar con</span>
            <div className="flex-1 h-px bg-white/10"/>
          </div>

          {/* Social buttons */}
          <div className="grid grid-cols-2 gap-3">
            <button className="h-[48px] flex items-center justify-center gap-2 text-sm font-medium text-white/80 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 transition-all" data-testid="google-login-button">
              <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#fff" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" opacity="0.8"/><path fill="#fff" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" opacity="0.6"/><path fill="#fff" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" opacity="0.4"/><path fill="#fff" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" opacity="0.5"/></svg>
              Google
            </button>
            <button className="h-[48px] flex items-center justify-center gap-2 text-sm font-medium text-white/80 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 transition-all">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="white" opacity="0.8"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              GitHub
            </button>
          </div>

          {/* Create account */}
          <p className="text-center text-sm text-white/50 mt-8">
            ¿No tienes cuenta?{' '}
            <Link to="/register" className="text-purple-400 hover:text-purple-300 font-medium" data-testid="create-account-link">
              Regístrate gratis
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
