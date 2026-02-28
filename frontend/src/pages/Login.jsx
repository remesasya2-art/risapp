import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet, Headphones, TrendingUp, Shield, Zap } from 'lucide-react';
import toast from 'react-hot-toast';

// FUTURISTIC FINTECH - Warm Tech Premium
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
    <div className="min-h-screen bg-[#FFF3CD] relative overflow-hidden font-['Inter',sans-serif]" data-testid="login-page">
      {/* Architectural grid lines */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-[5%] w-px h-full bg-[#737070]/20"></div>
        <div className="absolute top-0 left-[25%] w-px h-full bg-[#737070]/10"></div>
        <div className="absolute top-0 right-[25%] w-px h-full bg-[#737070]/10"></div>
        <div className="absolute top-0 right-[5%] w-px h-full bg-[#737070]/20"></div>
        <div className="absolute top-[10%] left-0 w-full h-px bg-[#737070]/10"></div>
        <div className="absolute bottom-[10%] left-0 w-full h-px bg-[#737070]/10"></div>
      </div>

      {/* Ambient orange glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#EE931F]/10 rounded-full blur-[150px] pointer-events-none"></div>

      {/* Header */}
      <header className="relative z-10 px-6 lg:px-12 py-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[#737070]/10 backdrop-blur-xl border border-[#737070]/20 flex items-center justify-center">
              <Wallet className="w-6 h-6 text-[#EE931F]" />
            </div>
            <div>
              <span className="text-xl font-bold tracking-[0.2em] text-[#737070]">RIS</span>
              <p className="text-[10px] tracking-[0.3em] text-[#737070]/60 uppercase">Terminal</p>
            </div>
          </div>
          
          {/* Live Rate Display - Fintech Style */}
          <div className="hidden sm:flex items-center gap-3 px-5 py-3 rounded-2xl bg-[#737070]/5 backdrop-blur-xl border border-[#737070]/20">
            <TrendingUp className="w-4 h-4 text-[#EE931F]" />
            <div className="text-right">
              <p className="text-[10px] tracking-[0.2em] text-[#737070]/60 uppercase">Tasa Live</p>
              <p className="text-sm font-bold tracking-wider text-[#737070]">1 RIS = <span className="text-[#EE931F]">{rates.ris_to_ves.toFixed(2)}</span> VES</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 px-6 lg:px-12 py-8 lg:py-16">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-24 items-center">
            
            {/* Left Column - Brand Message */}
            <div className="order-2 lg:order-1 space-y-8">
              <div>
                <p className="text-[11px] tracking-[0.4em] text-[#EE931F] uppercase mb-4 font-medium">Plataforma de Remesas</p>
                <h1 className="text-4xl lg:text-5xl font-bold text-[#737070] leading-tight tracking-tight">
                  El futuro de las
                  <br />
                  <span className="text-[#EE931F]">transferencias</span>
                </h1>
              </div>
              
              <p className="text-[#737070]/70 text-lg leading-relaxed max-w-md">
                Tecnología de última generación para enviar dinero de forma segura, rápida y transparente.
              </p>

              {/* Feature Cards - Glassmorphism */}
              <div className="space-y-4">
                <div className="flex items-center gap-4 p-5 rounded-2xl bg-white/40 backdrop-blur-xl border border-[#737070]/10 transition-all hover:border-[#EE931F]/30 hover:shadow-lg hover:shadow-[#EE931F]/5">
                  <div className="w-12 h-12 rounded-xl bg-[#EE931F]/10 flex items-center justify-center">
                    <Shield className="w-6 h-6 text-[#EE931F]" />
                  </div>
                  <div>
                    <p className="font-bold text-[#737070] tracking-wide">Seguridad Bancaria</p>
                    <p className="text-sm text-[#737070]/60">Encriptación de grado militar</p>
                  </div>
                </div>
                
                <div className="flex items-center gap-4 p-5 rounded-2xl bg-white/40 backdrop-blur-xl border border-[#737070]/10 transition-all hover:border-[#EE931F]/30 hover:shadow-lg hover:shadow-[#EE931F]/5">
                  <div className="w-12 h-12 rounded-xl bg-[#EE931F]/10 flex items-center justify-center">
                    <Zap className="w-6 h-6 text-[#EE931F]" />
                  </div>
                  <div>
                    <p className="font-bold text-[#737070] tracking-wide">Velocidad Instantánea</p>
                    <p className="text-sm text-[#737070]/60">Transferencias en minutos</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Login Form */}
            <div className="order-1 lg:order-2">
              {/* Glassmorphism Panel */}
              <div className="relative">
                {/* Orange glow behind card */}
                <div className="absolute -inset-4 bg-[#EE931F]/20 rounded-[32px] blur-2xl opacity-50"></div>
                
                <div className="relative bg-white/60 backdrop-blur-2xl rounded-[16px] border border-[#737070]/20 p-8 lg:p-10 shadow-2xl shadow-[#737070]/5">
                  {/* Header */}
                  <div className="mb-8">
                    <p className="text-[10px] tracking-[0.4em] text-[#737070]/60 uppercase mb-2">Acceso Seguro</p>
                    <h2 className="text-2xl font-bold text-[#737070] tracking-tight">Iniciar Sesión</h2>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6">
                    {/* Email Input */}
                    <div>
                      <label className="block text-[11px] tracking-[0.2em] text-[#737070]/70 uppercase mb-3 font-medium">
                        Correo Electrónico
                      </label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full h-14 px-5 rounded-[16px] bg-white/50 border border-[#737070]/20 focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 transition-all text-[#737070] placeholder-[#737070]/40 text-base"
                        placeholder="tu@email.com"
                        data-testid="email-input"
                      />
                    </div>

                    {/* Password Input */}
                    <div>
                      <div className="flex justify-between items-center mb-3">
                        <label className="text-[11px] tracking-[0.2em] text-[#737070]/70 uppercase font-medium">
                          Contraseña
                        </label>
                        <Link to="/forgot-password" className="text-[11px] tracking-wider text-[#EE931F] hover:text-[#EE931F]/80 uppercase font-medium">
                          ¿Olvidaste?
                        </Link>
                      </div>
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className="w-full h-14 px-5 pr-14 rounded-[16px] bg-white/50 border border-[#737070]/20 focus:border-[#EE931F] focus:ring-2 focus:ring-[#EE931F]/20 transition-all text-[#737070] placeholder-[#737070]/40 text-base"
                          placeholder="••••••••••"
                          data-testid="password-input"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-5 top-1/2 -translate-y-1/2 text-[#737070]/50 hover:text-[#EE931F] transition-colors"
                        >
                          {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                        </button>
                      </div>
                    </div>

                    {/* Remember Me */}
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <div className="relative">
                        <input
                          type="checkbox"
                          checked={rememberMe}
                          onChange={(e) => setRememberMe(e.target.checked)}
                          className="w-5 h-5 rounded-md border-2 border-[#737070]/30 text-[#EE931F] focus:ring-[#EE931F]/30 cursor-pointer bg-white/50"
                        />
                      </div>
                      <span className="text-sm text-[#737070]/70 group-hover:text-[#737070] transition-colors">
                        Mantener sesión activa
                      </span>
                    </label>

                    {/* Submit Button with Glow */}
                    <div className="relative pt-2">
                      <div className="absolute inset-0 bg-[#EE931F]/30 rounded-[16px] blur-xl"></div>
                      <button
                        type="submit"
                        disabled={loading}
                        className="relative w-full h-14 bg-[#EE931F] hover:bg-[#EE931F]/90 text-white font-bold tracking-[0.15em] uppercase text-sm rounded-[16px] transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#EE931F]/30 hover:shadow-xl hover:shadow-[#EE931F]/40 hover:scale-[1.02] active:scale-[0.98]"
                        data-testid="login-button"
                      >
                        {loading ? 'Verificando...' : 'Acceder'}
                      </button>
                    </div>
                  </form>

                  {/* Divider */}
                  <div className="flex items-center gap-4 my-8">
                    <div className="flex-1 h-px bg-[#737070]/20"></div>
                    <span className="text-[10px] tracking-[0.3em] text-[#737070]/40 uppercase">o</span>
                    <div className="flex-1 h-px bg-[#737070]/20"></div>
                  </div>

                  {/* Help Button */}
                  <button className="w-full h-14 bg-white/50 hover:bg-white/70 text-[#737070] font-medium tracking-wider rounded-[16px] border border-[#737070]/20 hover:border-[#737070]/30 flex items-center justify-center gap-3 transition-all">
                    <Headphones className="w-5 h-5 text-[#EE931F]" />
                    <span className="text-sm uppercase tracking-[0.1em]">Soporte 24/7</span>
                  </button>

                  {/* Register Link */}
                  <div className="mt-8 pt-6 border-t border-[#737070]/10 text-center">
                    <p className="text-sm text-[#737070]/60">
                      ¿Primera vez?{' '}
                      <Link to="/register" className="text-[#EE931F] font-bold hover:text-[#EE931F]/80 tracking-wide">
                        Crear Cuenta
                      </Link>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 px-6 lg:px-12 py-6">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] tracking-[0.2em] text-[#737070]/50 uppercase">
          <p>© 2024 RIS Terminal</p>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-[#EE931F] transition-colors">Privacidad</a>
            <a href="#" className="hover:text-[#EE931F] transition-colors">Términos</a>
            <a href="#" className="hover:text-[#EE931F] transition-colors">Seguridad</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
