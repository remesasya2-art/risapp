import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Mail, Lock, CreditCard } from 'lucide-react';
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
      
      {/* Background with gradient blobs */}
      <div className="absolute inset-0 bg-[#fafafa]">
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-[#e0e7ff] rounded-full blur-[100px] opacity-70"/>
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-[#dbeafe] rounded-full blur-[100px] opacity-70"/>
      </div>

      {/* Card */}
      <div className="relative z-10 w-full max-w-[400px] mx-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          
          {/* Logo */}
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="w-10 h-10 bg-[#4f46e5] rounded-xl flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-[#111827]">RIS</span>
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-[#111827] text-center mb-1">
            Sign In
          </h1>
          <p className="text-[#6b7280] text-center text-sm mb-6">
            Access your digital wallet
          </p>

          {/* Google */}
          <button className="w-full h-12 flex items-center justify-center gap-3 text-sm font-medium text-[#111827] bg-white rounded-xl border border-[#e5e7eb] hover:bg-[#f9fafb] transition-all mb-5">
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
              <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
            </svg>
            Sign in with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-5">
            <div className="flex-1 h-px bg-[#e5e7eb]"/>
            <span className="text-[#9ca3af] text-xs">OR CONTINUE WITH EMAIL</span>
            <div className="flex-1 h-px bg-[#e5e7eb]"/>
          </div>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-4">
              <label className="block text-[#111827] text-sm font-medium mb-1.5">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9ca3af]" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  data-testid="login-email-input"
                  className="w-full h-12 pl-11 pr-4 text-sm rounded-xl border border-[#e5e7eb] bg-white text-[#111827] placeholder-[#9ca3af] focus:border-[#4f46e5] focus:ring-2 focus:ring-[#4f46e5]/20 focus:outline-none transition-all"
                />
              </div>
            </div>

            {/* Password */}
            <div className="mb-5">
              <label className="block text-[#111827] text-sm font-medium mb-1.5">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9ca3af]" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  data-testid="login-password-input"
                  className="w-full h-12 pl-11 pr-11 text-sm rounded-xl border border-[#e5e7eb] bg-white text-[#111827] placeholder-[#9ca3af] focus:border-[#4f46e5] focus:ring-2 focus:ring-[#4f46e5]/20 focus:outline-none transition-all"
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
              <div className="text-right mt-1.5">
                <Link to="/forgot-password" className="text-[#4f46e5] text-sm hover:underline" data-testid="forgot-password-link">
                  Forgot password?
                </Link>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-12 bg-[#4f46e5] hover:bg-[#4338ca] text-white font-semibold text-sm rounded-xl transition-all disabled:opacity-50"
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
