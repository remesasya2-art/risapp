import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, ArrowLeftRight, Shield, Zap, Wallet, Smartphone, Headphones } from 'lucide-react';
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
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex">
      {/* Left Side - Branding (hidden on mobile) */}
      <div className="hidden lg:flex lg:w-1/2 xl:w-2/5 flex-col justify-center p-12 bg-gradient-to-br from-primary-900 to-slate-900">
        <div className="max-w-md">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-14 h-14 rounded-2xl bg-gold-400/20 flex items-center justify-center">
              <ArrowLeftRight className="w-8 h-8 text-gold-400" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white">RIS</h1>
              <p className="text-blue-200 text-sm">Remesas Internacionales Seguras</p>
            </div>
          </div>

          {/* Features */}
          <div className="space-y-4 mb-8">
            <div className="flex items-center gap-3 text-white/90">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
                <Shield className="w-5 h-5 text-gold-400" />
              </div>
              <span>Transferencias seguras y verificadas</span>
            </div>
            <div className="flex items-center gap-3 text-white/90">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
                <Zap className="w-5 h-5 text-gold-400" />
              </div>
              <span>Envíos rápidos a Venezuela</span>
            </div>
            <div className="flex items-center gap-3 text-white/90">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
                <Wallet className="w-5 h-5 text-gold-400" />
              </div>
              <span>Recargas con PIX desde Brasil</span>
            </div>
            <div className="flex items-center gap-3 text-white/90">
              <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center">
                <Smartphone className="w-5 h-5 text-gold-400" />
              </div>
              <span>Disponible en web y móvil</span>
            </div>
          </div>

          {/* Support Button */}
          <button
            onClick={() => setShowSupportModal(true)}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-gold-400 hover:bg-gold-500 text-white rounded-xl transition-colors"
          >
            <Headphones className="w-5 h-5" />
            <span>¿No puedes acceder? Solicita ayuda</span>
          </button>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="flex-1 flex flex-col justify-center px-6 py-12 lg:px-12">
        <div className="w-full max-w-md mx-auto">
          {/* Mobile Logo */}
          <div className="lg:hidden flex items-center justify-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-xl bg-gold-400/20 flex items-center justify-center">
              <ArrowLeftRight className="w-6 h-6 text-gold-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">RIS</h1>
              <p className="text-blue-200 text-xs">Remesas Seguras</p>
            </div>
          </div>

          {/* Rate Card */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-4 mb-6 border border-white/10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="live-dot"></div>
                <span className="text-xs text-green-400 font-medium">EN VIVO</span>
              </div>
              <span className="text-xs text-white/60">Tasa del día</span>
            </div>
            <p className="text-2xl font-bold text-white mt-2">
              1 RIS = {rates.ris_to_ves.toFixed(2)} VES
            </p>
          </div>

          {/* Login Form Card */}
          <div className="bg-white rounded-3xl shadow-2xl p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Bienvenido</h2>
            <p className="text-gray-500 mb-6">Ingresa a tu cuenta RIS</p>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  placeholder="tu@email.com"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all pr-12"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <Link to="/forgot-password" className="text-sm text-primary-600 hover:text-primary-700 block text-right">
                ¿Olvidaste tu contraseña?
              </Link>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar Sesión'}
              </button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-gray-500">
                ¿No tienes cuenta?{' '}
                <Link to="/register" className="text-primary-600 hover:text-primary-700 font-medium">
                  Regístrate aquí
                </Link>
              </p>
            </div>

            {/* Security Badge */}
            <div className="mt-6 flex items-center justify-center gap-2 text-green-600">
              <Shield className="w-4 h-4" />
              <span className="text-xs">Conexión segura y encriptada</span>
            </div>
          </div>

          {/* Mobile Support Button */}
          <button
            onClick={() => setShowSupportModal(true)}
            className="lg:hidden w-full flex items-center justify-center gap-2 py-3 px-4 bg-gold-400 hover:bg-gold-500 text-white rounded-xl transition-colors mt-6"
          >
            <Headphones className="w-5 h-5" />
            <span>¿No puedes acceder? Solicita ayuda</span>
          </button>
        </div>
      </div>

      {/* Support Modal */}
      {showSupportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md animate-slideUp">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center">
                <Headphones className="w-6 h-6 text-primary-600" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">Centro de Ayuda</h3>
                <p className="text-sm text-gray-500">Te ayudamos por WhatsApp</p>
              </div>
              <button
                onClick={() => setShowSupportModal(false)}
                className="ml-auto text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <p className="text-gray-600 mb-4">
              Si tienes problemas para acceder a tu cuenta, contáctanos por WhatsApp y te ayudaremos.
            </p>

            <a
              href="https://wa.me/559584098171?text=Hola,%20necesito%20ayuda%20para%20acceder%20a%20mi%20cuenta%20RIS"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
              </svg>
              Contactar por WhatsApp
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
