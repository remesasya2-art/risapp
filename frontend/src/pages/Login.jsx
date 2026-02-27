import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { Eye, EyeOff, Wallet, Headphones } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const { rates } = useRate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
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
    <div className="min-h-screen bg-white relative overflow-hidden" data-testid="login-page">
      {/* Grid lines like Stripe */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Horizontal line below header */}
        <div className="absolute top-[72px] left-0 right-0 h-px bg-gray-200"></div>
        {/* Left vertical line */}
        <div className="absolute top-0 bottom-0 left-[10%] w-px bg-gray-200"></div>
        {/* Right vertical line */}
        <div className="absolute top-0 bottom-0 right-[10%] w-px bg-gray-200"></div>
        {/* Bottom horizontal line */}
        <div className="absolute bottom-[60px] left-0 right-0 h-px bg-gray-200"></div>
      </div>

      {/* Background colorful waves - right side */}
      <div className="absolute top-0 right-0 w-[55%] h-full pointer-events-none overflow-hidden">
        <img 
          src="https://b.stripecdn.com/dashboard-fe-statics-srv/assets/public/login-wave-dpr1-lg-3000x2500.png"
          alt=""
          className="absolute top-0 right-0 w-full h-full object-cover object-left"
          style={{ minHeight: '100%', minWidth: '100%' }}
        />
      </div>

      {/* Header with logo */}
      <header className="relative z-10 h-[72px] flex items-center px-[10%]">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <Wallet className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold text-gray-900">RIS</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex justify-start px-[10%] pt-16">
        <div className="w-full max-w-[400px]">
          {/* Login Card */}
          <div className="bg-white rounded-lg shadow-2xl p-8 border border-gray-100">
            <h1 className="text-[22px] font-semibold text-gray-900 mb-8">Inicia sesión en tu cuenta</h1>

            <form onSubmit={handleSubmit}>
              {/* Email Field */}
              <div className="mb-5">
                <label className="block text-[14px] text-gray-600 mb-2">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-[44px] px-3 rounded-[5px] border border-gray-300 focus:border-[#635BFF] focus:ring-1 focus:ring-[#635BFF] focus:outline-none transition-colors text-[16px] text-gray-900 shadow-sm"
                  data-testid="email-input"
                />
              </div>

              {/* Password Field */}
              <div className="mb-5">
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-[14px] text-gray-600">
                    Contraseña
                  </label>
                  <Link to="/forgot-password" className="text-[14px] text-[#635BFF] hover:text-[#5851ea]">
                    ¿No recuerdas la contraseña?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-[44px] px-3 pr-10 rounded-[5px] border border-gray-300 focus:border-[#635BFF] focus:ring-1 focus:ring-[#635BFF] focus:outline-none transition-colors text-[16px] text-gray-900 shadow-sm"
                    data-testid="password-input"
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

              {/* Remember Me */}
              <label className="flex items-center gap-2 mb-6 cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-[#635BFF] focus:ring-[#635BFF] cursor-pointer" 
                />
                <span className="text-[14px] text-gray-600">Recuérdame en este dispositivo</span>
              </label>

              {/* Submit Button - Purple like Stripe */}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-[44px] bg-[#635BFF] hover:bg-[#5851ea] text-white font-medium rounded-[5px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-[16px] shadow-sm"
                data-testid="login-button"
              >
                {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-4 my-6">
              <div className="flex-1 h-px bg-gray-200"></div>
              <span className="text-[14px] text-gray-400">o</span>
              <div className="flex-1 h-px bg-gray-200"></div>
            </div>

            {/* Alternative Login Options */}
            <div className="space-y-3">
              <button
                onClick={() => setShowSupportModal(true)}
                className="w-full h-[44px] bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-[5px] border border-gray-300 transition-colors flex items-center justify-center gap-2 text-[14px] shadow-sm"
              >
                <Headphones className="w-5 h-5 text-gray-500" />
                ¿Necesitas ayuda para acceder?
              </button>
            </div>

            {/* Register Section */}
            <div className="mt-6 pt-6 bg-[#F7FAFC] -mx-8 -mb-8 px-8 pb-6 rounded-b-lg border-t border-gray-100">
              <p className="text-[14px] text-gray-600 text-center">
                ¿Eres nuevo en RIS?{' '}
                <Link to="/register" className="text-[#635BFF] hover:text-[#5851ea] font-medium">
                  Crea una cuenta
                </Link>
              </p>
            </div>
          </div>

          {/* Rate Info */}
          <div className="mt-4 text-center">
            <p className="text-[13px] text-gray-500">
              Tasa actual: <span className="font-medium text-gray-700">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 h-[60px] flex items-center px-[10%] border-t border-transparent">
        <div className="flex items-center gap-4 text-[13px] text-gray-500">
          <a href="#" className="hover:text-gray-700">© RIS</a>
          <a href="#" className="hover:text-gray-700">Privacidad y condiciones</a>
        </div>
      </footer>

      {/* Support Modal */}
      {showSupportModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md shadow-2xl animate-fadeIn">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-orange-100 flex items-center justify-center">
                <Headphones className="w-6 h-6 text-orange-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Centro de Ayuda</h3>
                <p className="text-sm text-gray-500">Te ayudamos por WhatsApp</p>
              </div>
              <button
                onClick={() => setShowSupportModal(false)}
                className="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <p className="text-gray-600 mb-4 text-[14px]">
              Si tienes problemas para acceder a tu cuenta, contáctanos por WhatsApp y te ayudaremos.
            </p>

            <a
              href="https://wa.me/559584098171?text=Hola,%20necesito%20ayuda%20para%20acceder%20a%20mi%20cuenta%20RIS"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full h-[44px] flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white font-medium rounded-[5px] transition-colors"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
              </svg>
              Contactar por WhatsApp
            </a>

            <button
              onClick={() => setShowSupportModal(false)}
              className="w-full h-[40px] mt-3 text-gray-600 font-medium hover:bg-gray-50 rounded-[5px] transition-colors text-[14px]"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.2s ease-out;
        }
      `}</style>
    </div>
  );
}
