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
    <div className="min-h-screen relative overflow-hidden flex items-center justify-center">
      <div className="absolute inset-0 bg-[#f8f9fc]">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-[#e8e0ff] rounded-full blur-[120px] opacity-60"></div>
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-[#d4f0ff] rounded-full blur-[120px] opacity-60"></div>
      </div>
      <div className="relative z-10 w-full max-w-[440px] mx-4">
        <div className="bg-white rounded-2xl shadow-xl px-12 py-10 border border-gray-100">
          <div className="flex items-center justify-center gap-2 mb-8">
            <div className="w-10 h-10 bg-[#6366f1] rounded-xl flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-semibold text-[#1a1a2e]">NexPay</span>
          </div>
          <h1 className="text-2xl font-semibold text-[#1a1a2e] text-center mb-2">Sign In</h1>
          <p className="text-[#6b7280] text-center text-sm mb-8">Access your digital wallet</p>
          <button className="w-full h-[52px] flex items-center justify-center gap-3 text-[15px] font-medium text-[#1a1a2e] bg-white rounded-xl border border-gray-200 hover:bg-gray-50 transition-all mb-6" data-testid="google-login-btn">
            <svg width="20" height="20" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"></path>
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"></path>
              <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"></path>
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"></path>
            </svg>
            Sign in with Google
          </button>
          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-gray-200"></div>
            <span className="text-[#9ca3af] text-xs uppercase tracking-wider">Or continue with email</span>
            <div className="flex-1 h-px bg-gray-200"></div>
          </div>
          <form onSubmit={handleSubmit} data-testid="login-form">
            <div className="mb-5">
              <label className="block text-[#1a1a2e] text-sm font-medium mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9ca3af]" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  data-testid="email-input"
                  className="w-full h-[52px] pl-12 pr-4 text-[15px] rounded-xl border border-gray-200 bg-white text-[#1a1a2e] placeholder-[#9ca3af] transition-all focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20"
                />
              </div>
            </div>
            <div className="mb-6">
              <label className="block text-[#1a1a2e] text-sm font-medium mb-2">Password</label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9ca3af]" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  data-testid="password-input"
                  className="w-full h-[52px] pl-12 pr-12 text-[15px] rounded-xl border border-gray-200 bg-white text-[#1a1a2e] placeholder-[#9ca3af] transition-all focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#6b7280]"
                  data-testid="toggle-password"
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-btn"
              className="w-full h-[52px] bg-[#6366f1] hover:bg-[#5558e3] text-white font-semibold text-[15px] rounded-xl transition-all disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
          <p className="text-center text-[#6b7280] text-sm mt-6">
            Don't have an account? <Link to="/register" className="text-[#6366f1] font-medium hover:underline" data-testid="register-link">Sign up</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
