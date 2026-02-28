import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet, Headphones } from 'lucide-react';
import toast from 'react-hot-toast';

// OPCIÓN A: Neo-Stripe (Minimalista Profesional)
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
    <div className="min-h-screen bg-white relative overflow-hidden font-['Inter']" data-testid="login-page">
      {/* Grid lines */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-[72px] left-0 right-0 h-px bg-gray-100"></div>
        <div className="absolute top-0 bottom-0 left-[12%] w-px bg-gray-100"></div>
        <div className="absolute top-0 bottom-0 right-[12%] w-px bg-gray-100"></div>
      </div>

      {/* Background waves */}
      <div className="absolute top-0 right-0 w-[50%] h-full pointer-events-none">
        <svg className="absolute right-0 top-0 h-full w-full" viewBox="0 0 600 800" fill="none" preserveAspectRatio="xMaxYMid slice">
          <path d="M300 0 Q450 200, 350 400 T400 800" stroke="url(#g1)" strokeWidth="180" fill="none" opacity="0.6"/>
          <path d="M400 -50 Q550 150, 450 350 T500 750" stroke="url(#g2)" strokeWidth="140" fill="none" opacity="0.5"/>
          <path d="M350 50 Q500 250, 400 450 T450 850" stroke="url(#g3)" strokeWidth="100" fill="none" opacity="0.4"/>
          <defs>
            <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#80E9FF"/>
              <stop offset="50%" stopColor="#635BFF"/>
              <stop offset="100%" stopColor="#A960EE"/>
            </linearGradient>
            <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FF80B5"/>
              <stop offset="100%" stopColor="#FF8C00"/>
            </linearGradient>
            <linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FFD700"/>
              <stop offset="100%" stopColor="#FF6B6B"/>
            </linearGradient>
          </defs>
        </svg>
      </div>

      {/* Header */}
      <header className="relative z-10 h-[72px] flex items-center px-[12%]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#635BFF] flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold text-[#0A2540]">RIS</span>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-120px)] px-4">
        <div className="w-full max-w-[440px]">
          <div className="bg-white rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-gray-100 p-10">
            <h1 className="text-[28px] font-bold text-[#0A2540] mb-2 tracking-tight">Inicia sesión</h1>
            <p className="text-gray-500 mb-8">Accede a tu cuenta RIS</p>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-[#0A2540] mb-2">Correo electrónico</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-[52px] px-4 rounded-lg border border-gray-200 focus:border-[#635BFF] focus:ring-2 focus:ring-[#635BFF]/20 transition-all text-[#0A2540]"
                  placeholder="tu@email.com"
                />
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm font-medium text-[#0A2540]">Contraseña</label>
                  <Link to="/forgot-password" className="text-sm text-[#635BFF] hover:underline">¿Olvidaste?</Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-[52px] px-4 pr-12 rounded-lg border border-gray-200 focus:border-[#635BFF] focus:ring-2 focus:ring-[#635BFF]/20 transition-all text-[#0A2540]"
                    placeholder="••••••••"
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400">
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} className="w-5 h-5 rounded border-gray-300 text-[#635BFF] focus:ring-[#635BFF]" />
                <span className="text-sm text-gray-600">Recuérdame</span>
              </label>

              <button type="submit" disabled={loading} className="w-full h-[52px] bg-[#635BFF] hover:bg-[#5851ea] text-white font-semibold rounded-lg transition-all">
                {loading ? 'Ingresando...' : 'Iniciar sesión'}
              </button>
            </form>

            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 h-px bg-gray-200"></div>
              <span className="text-sm text-gray-400">o</span>
              <div className="flex-1 h-px bg-gray-200"></div>
            </div>

            <button className="w-full h-[52px] bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-lg border border-gray-200 flex items-center justify-center gap-2">
              <Headphones className="w-5 h-5" />
              ¿Necesitas ayuda?
            </button>
          </div>

          <div className="mt-6 text-center">
            <p className="text-gray-600">¿Nuevo en RIS? <Link to="/register" className="text-[#635BFF] font-semibold hover:underline">Crear cuenta</Link></p>
          </div>
          <p className="text-center text-sm text-gray-400 mt-4">Tasa: 1 RIS = {rates.ris_to_ves.toFixed(2)} VES</p>
        </div>
      </main>

      <footer className="absolute bottom-4 left-[12%] text-sm text-gray-400">© RIS · Privacidad</footer>
    </div>
  );
}
