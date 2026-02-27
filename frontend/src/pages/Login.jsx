import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, ArrowLeftRight, Shield, Zap, Wallet, Headphones, TrendingUp } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const { rates } = useRate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showSupportModal, setShowSupportModal] = useState(false);

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
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-50 flex items-center justify-center p-4" data-testid="login-page">
      <div className="w-full max-w-md">
        {/* Logo and Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-gradient-to-br from-blue-600 to-blue-700 shadow-xl shadow-blue-200 mb-4">
            <ArrowLeftRight className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-blue-900">RIS</h1>
          <p className="text-blue-600 text-sm mt-1">Remesas Internacionales Seguras</p>
        </div>

        {/* Rate Card */}
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-4 mb-6 border border-blue-200 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-green-600" />
              <span className="text-sm font-medium text-blue-900">Tasa del día</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-xs text-green-600 font-medium">EN VIVO</span>
            </div>
          </div>
          <p className="text-2xl font-bold text-blue-900 mt-2">
            1 RIS = {rates.ris_to_ves.toFixed(2)} <span className="text-lg font-normal text-blue-600">VES</span>
          </p>
        </div>

        {/* Login Form Card */}
        <div className="bg-white rounded-3xl shadow-xl shadow-blue-100 p-8 border border-blue-100">
          <h2 className="text-2xl font-bold text-blue-900 mb-1">Bienvenido</h2>
          <p className="text-blue-600 mb-6">Ingresa a tu cuenta RIS</p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-blue-900 mb-2">
                Correo electrónico
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3.5 rounded-xl bg-blue-50 border-2 border-blue-100 focus:bg-white focus:border-blue-500 focus:ring-0 transition-all text-blue-900 placeholder-blue-400"
                placeholder="tu@email.com"
                data-testid="email-input"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-blue-900 mb-2">
                Contraseña
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3.5 rounded-xl bg-blue-50 border-2 border-blue-100 focus:bg-white focus:border-blue-500 focus:ring-0 transition-all pr-12 text-blue-900 placeholder-blue-400"
                  placeholder="••••••••"
                  data-testid="password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-blue-400 hover:text-blue-600 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 rounded border-blue-300 text-blue-600 focus:ring-blue-500" />
                <span className="text-sm text-blue-700">Recordarme</span>
              </label>
              <Link to="/forgot-password" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
                ¿Olvidaste tu contraseña?
              </Link>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 px-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-200"
              data-testid="login-button"
            >
              {loading ? 'Iniciando sesión...' : 'Iniciar Sesión'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-blue-700">
              ¿No tienes cuenta?{' '}
              <Link to="/register" className="text-blue-600 hover:text-blue-800 font-semibold">
                Regístrate aquí
              </Link>
            </p>
          </div>
        </div>

        {/* Features */}
        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="bg-white/60 backdrop-blur-sm rounded-xl p-3 text-center border border-blue-100">
            <Shield className="w-6 h-6 text-blue-600 mx-auto mb-1" />
            <span className="text-xs text-blue-800 font-medium">Seguro</span>
          </div>
          <div className="bg-white/60 backdrop-blur-sm rounded-xl p-3 text-center border border-blue-100">
            <Zap className="w-6 h-6 text-blue-600 mx-auto mb-1" />
            <span className="text-xs text-blue-800 font-medium">Rápido</span>
          </div>
          <div className="bg-white/60 backdrop-blur-sm rounded-xl p-3 text-center border border-blue-100">
            <Wallet className="w-6 h-6 text-blue-600 mx-auto mb-1" />
            <span className="text-xs text-blue-800 font-medium">PIX</span>
          </div>
        </div>

        {/* Support Button */}
        <button
          onClick={() => setShowSupportModal(true)}
          className="w-full flex items-center justify-center gap-2 py-3 px-4 mt-4 bg-white/80 hover:bg-white text-blue-700 font-medium rounded-xl transition-all border border-blue-200"
          data-testid="support-button"
        >
          <Headphones className="w-5 h-5" />
          <span>¿No puedes acceder? Solicita ayuda</span>
        </button>

        {/* Security Badge */}
        <div className="mt-4 flex items-center justify-center gap-2 text-blue-600">
          <Shield className="w-4 h-4" />
          <span className="text-xs font-medium">Conexión segura y encriptada</span>
        </div>
      </div>

      {/* Support Modal */}
      {showSupportModal && (
        <div className="fixed inset-0 bg-blue-900/30 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl p-6 w-full max-w-md shadow-2xl border border-blue-100 animate-slideUp">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-2xl bg-blue-100 flex items-center justify-center">
                <Headphones className="w-6 h-6 text-blue-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-bold text-blue-900">Centro de Ayuda</h3>
                <p className="text-sm text-blue-600">Te ayudamos por WhatsApp</p>
              </div>
              <button
                onClick={() => setShowSupportModal(false)}
                className="w-8 h-8 rounded-full bg-blue-50 hover:bg-blue-100 flex items-center justify-center text-blue-600 transition-colors"
              >
                ✕
              </button>
            </div>

            <p className="text-blue-700 mb-4">
              Si tienes problemas para acceder a tu cuenta, contáctanos por WhatsApp y te ayudaremos.
            </p>

            <a
              href="https://wa.me/559584098171?text=Hola,%20necesito%20ayuda%20para%20acceder%20a%20mi%20cuenta%20RIS"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 py-3.5 px-4 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-xl transition-colors shadow-lg shadow-green-200"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
              </svg>
              Contactar por WhatsApp
            </a>

            <button
              onClick={() => setShowSupportModal(false)}
              className="w-full py-3 mt-3 text-blue-600 font-medium hover:bg-blue-50 rounded-xl transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        .animate-slideUp {
          animation: slideUp 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
