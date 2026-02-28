import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet, Headphones, Heart, Shield, Zap } from 'lucide-react';
import toast from 'react-hot-toast';

// OPCIÓN C: Human Connection (Cálido/Amigable)
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
    <div className="min-h-screen bg-gradient-to-br from-[#FFF9F5] via-[#FFF5EE] to-[#FFEDE3] relative overflow-hidden font-['Nunito']" data-testid="login-page">
      {/* Decorative shapes */}
      <div className="absolute top-[-100px] right-[-100px] w-[400px] h-[400px] rounded-full bg-gradient-to-br from-orange-200/50 to-pink-200/50 blur-3xl"></div>
      <div className="absolute bottom-[-100px] left-[-100px] w-[300px] h-[300px] rounded-full bg-gradient-to-br from-teal-200/50 to-blue-200/50 blur-3xl"></div>

      {/* Header */}
      <header className="relative z-10 h-[80px] flex items-center justify-between px-8">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#FF6B35] to-[#FF8E53] flex items-center justify-center shadow-lg shadow-orange-300/50">
            <Wallet className="w-6 h-6 text-white" />
          </div>
          <div>
            <span className="text-2xl font-extrabold text-[#2D3436]">RIS</span>
            <p className="text-xs text-[#636E72]">Conectando familias</p>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-160px)] px-4">
        <div className="w-full max-w-[1000px] grid md:grid-cols-2 gap-12 items-center">
          {/* Left - Illustration/Info */}
          <div className="hidden md:block">
            <h2 className="text-4xl font-extrabold text-[#2D3436] mb-4 leading-tight">
              Envía dinero a tus seres queridos, <span className="text-[#FF6B35]">fácil y seguro</span>
            </h2>
            <p className="text-lg text-[#636E72] mb-8">Más de 10,000 familias confían en RIS para sus remesas.</p>
            
            <div className="space-y-4">
              <div className="flex items-center gap-4 bg-white/70 backdrop-blur-sm rounded-2xl p-4 shadow-sm">
                <div className="w-12 h-12 rounded-xl bg-teal-100 flex items-center justify-center">
                  <Shield className="w-6 h-6 text-teal-600" />
                </div>
                <div>
                  <p className="font-bold text-[#2D3436]">100% Seguro</p>
                  <p className="text-sm text-[#636E72]">Transacciones encriptadas</p>
                </div>
              </div>
              <div className="flex items-center gap-4 bg-white/70 backdrop-blur-sm rounded-2xl p-4 shadow-sm">
                <div className="w-12 h-12 rounded-xl bg-orange-100 flex items-center justify-center">
                  <Zap className="w-6 h-6 text-orange-600" />
                </div>
                <div>
                  <p className="font-bold text-[#2D3436]">Súper Rápido</p>
                  <p className="text-sm text-[#636E72]">Dinero en minutos</p>
                </div>
              </div>
              <div className="flex items-center gap-4 bg-white/70 backdrop-blur-sm rounded-2xl p-4 shadow-sm">
                <div className="w-12 h-12 rounded-xl bg-pink-100 flex items-center justify-center">
                  <Heart className="w-6 h-6 text-pink-600" />
                </div>
                <div>
                  <p className="font-bold text-[#2D3436]">Con Amor</p>
                  <p className="text-sm text-[#636E72]">Soporte 24/7 en español</p>
                </div>
              </div>
            </div>

            <p className="mt-8 text-sm text-[#636E72]">Tasa actual: <span className="font-bold text-[#2D3436]">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span></p>
          </div>

          {/* Right - Form */}
          <div className="w-full max-w-[420px] mx-auto">
            <div className="bg-white rounded-3xl shadow-xl shadow-orange-200/30 p-10 border border-orange-100/50">
              <div className="text-center mb-8">
                <h1 className="text-3xl font-extrabold text-[#2D3436] mb-2">¡Hola de nuevo! 👋</h1>
                <p className="text-[#636E72]">Ingresa a tu cuenta</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label className="block text-sm font-bold text-[#2D3436] mb-2">Correo electrónico</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full h-[56px] px-5 rounded-2xl bg-[#F8F9FA] border-2 border-transparent focus:border-[#FF6B35] focus:bg-white transition-all text-[#2D3436]"
                    placeholder="tu@email.com"
                  />
                </div>

                <div>
                  <div className="flex justify-between mb-2">
                    <label className="text-sm font-bold text-[#2D3436]">Contraseña</label>
                    <Link to="/forgot-password" className="text-sm text-[#FF6B35] hover:underline font-medium">¿Olvidaste?</Link>
                  </div>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full h-[56px] px-5 pr-12 rounded-2xl bg-[#F8F9FA] border-2 border-transparent focus:border-[#FF6B35] focus:bg-white transition-all text-[#2D3436]"
                      placeholder="••••••••"
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-4 top-1/2 -translate-y-1/2 text-[#636E72] hover:text-[#2D3436]">
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} className="w-5 h-5 rounded-lg border-2 border-gray-300 text-[#FF6B35] focus:ring-[#FF6B35]" />
                  <span className="text-sm text-[#636E72]">Recuérdame</span>
                </label>

                <button type="submit" disabled={loading} className="w-full h-[56px] bg-gradient-to-r from-[#FF6B35] to-[#FF8E53] hover:from-[#FF5722] hover:to-[#FF6B35] text-white font-bold rounded-2xl transition-all shadow-lg shadow-orange-300/50 hover:shadow-orange-400/50 hover:scale-[1.02] active:scale-[0.98]">
                  {loading ? 'Ingresando...' : 'Iniciar sesión'}
                </button>
              </form>

              <div className="flex items-center gap-4 my-6">
                <div className="flex-1 h-px bg-gray-200"></div>
                <span className="text-sm text-gray-400">o</span>
                <div className="flex-1 h-px bg-gray-200"></div>
              </div>

              <button className="w-full h-[56px] bg-[#F8F9FA] hover:bg-[#E9ECEF] text-[#2D3436] font-semibold rounded-2xl flex items-center justify-center gap-2 transition-all">
                <Headphones className="w-5 h-5 text-[#FF6B35]" />
                ¿Necesitas ayuda?
              </button>

              <div className="mt-6 text-center">
                <p className="text-[#636E72]">¿Nuevo en RIS? <Link to="/register" className="text-[#FF6B35] font-bold hover:underline">Crear cuenta</Link></p>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="absolute bottom-4 left-0 right-0 text-center text-sm text-[#636E72]">© 2024 RIS · Hecho con ❤️ para ti</footer>
    </div>
  );
}
