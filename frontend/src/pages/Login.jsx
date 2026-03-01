import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Shield } from 'lucide-react';
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
    <div className="min-h-screen bg-[#f5f7fa] flex flex-col" style={{fontFamily: 'Inter, -apple-system, sans-serif'}}>
      
      {/* Header */}
      <header className="px-8 py-5 bg-white border-b border-[#e5e9f0]">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 bg-[#00b386] rounded-lg flex items-center justify-center">
              <span className="text-white font-bold">R</span>
            </div>
            <span className="text-[#1a1f36] font-semibold text-xl">RIS</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#" className="text-[#5e6c84] text-sm hover:text-[#1a1f36]">Ayuda</a>
            <Link to="/register" className="text-[#00b386] text-sm font-medium hover:underline">
              Registrarse
            </Link>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[440px]">
          
          {/* Card */}
          <div className="bg-white rounded-2xl shadow-sm border border-[#e5e9f0] overflow-hidden">
            <div className="p-10">
              <h1 className="text-[26px] font-bold text-[#1a1f36] mb-2">
                Iniciar sesión
              </h1>
              <p className="text-[#5e6c84] text-[15px] mb-8">
                Ingresa tus credenciales para acceder a tu cuenta
              </p>

              <form onSubmit={handleSubmit} data-testid="login-form">
                {/* Email */}
                <div className="mb-5">
                  <label className="block text-[#1a1f36] text-sm font-medium mb-2">
                    Correo electrónico
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    data-testid="login-email-input"
                    className="w-full h-[50px] px-4 text-[15px] rounded-xl border border-[#dfe3e8] bg-white text-[#1a1f36] placeholder-[#8492a6] transition-all focus:border-[#00b386] focus:ring-2 focus:ring-[#00b386]/20 focus:outline-none"
                    placeholder="nombre@empresa.com"
                  />
                </div>

                {/* Password */}
                <div className="mb-5">
                  <div className="flex justify-between items-center mb-2">
                    <label className="text-[#1a1f36] text-sm font-medium">Contraseña</label>
                    <Link to="/forgot-password" className="text-[#00b386] text-sm hover:underline" data-testid="forgot-password-link">
                      ¿Olvidaste tu contraseña?
                    </Link>
                  </div>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      data-testid="login-password-input"
                      className="w-full h-[50px] px-4 pr-12 text-[15px] rounded-xl border border-[#dfe3e8] bg-white text-[#1a1f36] placeholder-[#8492a6] transition-all focus:border-[#00b386] focus:ring-2 focus:ring-[#00b386]/20 focus:outline-none"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-[#8492a6] hover:text-[#1a1f36]"
                      data-testid="toggle-password-visibility"
                    >
                      {showPassword ? <EyeOff size={20}/> : <Eye size={20}/>}
                    </button>
                  </div>
                </div>

                {/* Submit */}
                <button
                  type="submit"
                  disabled={loading}
                  data-testid="login-submit-button"
                  className="w-full h-[50px] bg-[#00b386] hover:bg-[#00a078] text-white font-semibold text-[15px] rounded-xl transition-all disabled:opacity-50"
                >
                  {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
                </button>
              </form>

              {/* Divider */}
              <div className="flex items-center my-6">
                <div className="flex-1 h-px bg-[#e5e9f0]"/>
                <span className="px-4 text-[#8492a6] text-xs uppercase tracking-wider">o</span>
                <div className="flex-1 h-px bg-[#e5e9f0]"/>
              </div>

              {/* Google button */}
              <button className="w-full h-[50px] flex items-center justify-center gap-3 text-[15px] font-medium text-[#1a1f36] bg-white rounded-xl border border-[#dfe3e8] hover:bg-[#f5f7fa] transition-all">
                <svg width="20" height="20" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/><path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/></svg>
                Continuar con Google
              </button>
            </div>

            {/* Footer card */}
            <div className="px-10 py-5 bg-[#f5f7fa] border-t border-[#e5e9f0]">
              <p className="text-center text-[14px] text-[#5e6c84]">
                ¿No tienes una cuenta?{' '}
                <Link to="/register" className="text-[#00b386] font-medium hover:underline" data-testid="create-account-link">
                  Crear cuenta gratis
                </Link>
              </p>
            </div>
          </div>

          {/* Security badge */}
          <div className="mt-6 flex items-center justify-center gap-2 text-[#8492a6] text-xs">
            <Shield size={14} />
            <span>Conexión segura con encriptación de 256 bits</span>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="px-8 py-4 bg-white border-t border-[#e5e9f0]">
        <div className="max-w-6xl mx-auto flex items-center justify-center gap-6 text-[#8492a6] text-xs">
          <span>© 2024 RIS</span>
          <a href="#" className="hover:text-[#1a1f36]">Privacidad</a>
          <a href="#" className="hover:text-[#1a1f36]">Términos</a>
          <a href="#" className="hover:text-[#1a1f36]">Soporte</a>
        </div>
      </footer>
    </div>
  );
}
