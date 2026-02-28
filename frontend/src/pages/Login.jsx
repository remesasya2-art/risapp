import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet, Headphones, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';

// OPCIÓN B: Nubank Kinetic (Dark Mode + Glassmorphism)
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
    <div className="min-h-screen bg-[#0D001A] relative overflow-hidden font-['Poppins']" data-testid="login-page">
      {/* Animated gradient background */}
      <div className="absolute inset-0">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-gradient-to-r from-purple-600/30 to-pink-600/30 blur-[120px] animate-pulse"></div>
        <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-gradient-to-r from-blue-600/30 to-purple-600/30 blur-[120px] animate-pulse" style={{animationDelay: '1s'}}></div>
        <div className="absolute top-[40%] right-[20%] w-[30%] h-[30%] rounded-full bg-gradient-to-r from-orange-500/20 to-yellow-500/20 blur-[100px] animate-pulse" style={{animationDelay: '2s'}}></div>
      </div>

      {/* Header */}
      <header className="relative z-10 h-[80px] flex items-center justify-between px-8">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-purple-500/30">
            <Wallet className="w-6 h-6 text-white" />
          </div>
          <span className="text-2xl font-bold text-white">RIS</span>
        </div>
        <div className="flex items-center gap-2 text-purple-300 text-sm">
          <Sparkles className="w-4 h-4" />
          <span>Tasa: 1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-160px)] px-4">
        <div className="w-full max-w-[480px]">
          {/* Glassmorphism Card */}
          <div className="backdrop-blur-xl bg-white/10 rounded-3xl border border-white/20 p-10 shadow-2xl">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-white mb-2">Bienvenido de vuelta</h1>
              <p className="text-purple-200">Ingresa a tu cuenta RIS</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-purple-200 mb-2">Correo electrónico</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-[56px] px-5 rounded-xl bg-white/5 border border-white/10 focus:border-purple-400 focus:ring-2 focus:ring-purple-400/30 transition-all text-white placeholder-white/40"
                  placeholder="tu@email.com"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm font-medium text-purple-200">Contraseña</label>
                  <Link to="/forgot-password" className="text-sm text-purple-400 hover:text-purple-300">¿Olvidaste?</Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-[56px] px-5 pr-12 rounded-xl bg-white/5 border border-white/10 focus:border-purple-400 focus:ring-2 focus:ring-purple-400/30 transition-all text-white placeholder-white/40"
                    placeholder="••••••••"
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-4 top-1/2 -translate-y-1/2 text-white/40 hover:text-white">
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} className="w-5 h-5 rounded bg-white/10 border-white/20 text-purple-500 focus:ring-purple-500" />
                <span className="text-sm text-purple-200">Recuérdame en este dispositivo</span>
              </label>

              <button type="submit" disabled={loading} className="w-full h-[56px] bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50 hover:scale-[1.02]">
                {loading ? 'Ingresando...' : 'Iniciar sesión'}
              </button>
            </form>

            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 h-px bg-white/10"></div>
              <span className="text-sm text-white/40">o</span>
              <div className="flex-1 h-px bg-white/10"></div>
            </div>

            <button className="w-full h-[56px] bg-white/5 hover:bg-white/10 text-white font-medium rounded-xl border border-white/10 flex items-center justify-center gap-2 transition-all">
              <Headphones className="w-5 h-5 text-purple-400" />
              ¿Necesitas ayuda?
            </button>

            <div className="mt-8 text-center">
              <p className="text-purple-200">¿Nuevo en RIS? <Link to="/register" className="text-purple-400 font-semibold hover:text-purple-300">Crear cuenta</Link></p>
            </div>
          </div>
        </div>
      </main>

      <footer className="absolute bottom-6 left-0 right-0 text-center text-sm text-white/30">© 2024 RIS · Privacidad y condiciones</footer>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}
