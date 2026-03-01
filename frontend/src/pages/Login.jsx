import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff } from 'lucide-react';
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
    <div className="min-h-screen relative flex items-center justify-center" style={{fontFamily: 'Inter, -apple-system, sans-serif'}}>
      
      {/* Background */}
      <div className="absolute inset-0 bg-[#fafafa]">
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-[#e0e7ff] rounded-full blur-[100px] opacity-60"/>
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-[#dbeafe] rounded-full blur-[100px] opacity-60"/>
      </div>

      {/* Card */}
      <div className="relative z-10 w-full max-w-[380px] mx-4">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          
          {/* Logo */}
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="w-9 h-9 bg-[#4f46e5] rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <span className="text-lg font-semibold text-[#111827]">RIS</span>
          </div>

          {/* Title */}
          <h1 className="text-xl font-semibold text-[#111827] text-center mb-1">
            Sign In
          </h1>
          <p className="text-[#6b7280] text-center text-sm mb-6">
            Access your digital wallet
          </p>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-4">
              <label className="block text-[#374151] text-sm font-medium mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                className="w-full h-11 px-3 text-sm rounded-lg border border-[#d1d5db] bg-white text-[#111827] placeholder-[#9ca3af] focus:border-[#4f46e5] focus:ring-1 focus:ring-[#4f46e5] focus:outline-none transition-all"
              />
            </div>

            {/* Password */}
            <div className="mb-5">
              <label className="block text-[#374151] text-sm font-medium mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input"
                  className="w-full h-11 px-3 pr-10 text-sm rounded-lg border border-[#d1d5db] bg-white text-[#111827] placeholder-[#9ca3af] focus:border-[#4f46e5] focus:ring-1 focus:ring-[#4f46e5] focus:outline-none transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#6b7280]"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-11 bg-[#4f46e5] hover:bg-[#4338ca] text-white font-medium text-sm rounded-lg transition-all disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          {/* Register */}
          <p className="text-center text-[#6b7280] text-sm mt-5">
            Don't have an account?{' '}
            <Link to="/register" className="text-[#4f46e5] font-medium hover:underline" data-testid="create-account-link">
              Sign up
            </Link>
          </p>

        </div>
      </div>

    </div>
  );
}
