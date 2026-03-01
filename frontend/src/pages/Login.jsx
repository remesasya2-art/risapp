import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Eye, EyeOff, Mail, Lock, User } from 'lucide-react';
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
    <div className="min-h-screen relative flex items-center justify-center py-10" style={{fontFamily: 'Inter, -apple-system, sans-serif'}}>
      
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#f8fafc] via-[#f1f5f9] to-[#e0e7ff]">
        <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] bg-[#c7d2fe] rounded-full blur-[120px] opacity-50"/>
        <div className="absolute bottom-1/4 right-1/4 w-[300px] h-[300px] bg-[#bfdbfe] rounded-full blur-[100px] opacity-50"/>
      </div>

      {/* Card */}
      <div className="relative z-10 w-full max-w-[440px] mx-4">
        <div className="bg-white rounded-3xl shadow-2xl shadow-gray-200/50 px-10 py-10">
          
          {/* Logo */}
          <div className="flex items-center justify-center gap-2.5 mb-8">
            <div className="w-10 h-10 bg-[#6366f1] rounded-xl flex items-center justify-center shadow-lg shadow-[#6366f1]/30">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <span className="text-xl font-semibold text-[#1e293b]">RIS</span>
          </div>

          {/* Title */}
          <h1 className="text-[28px] font-semibold text-[#1e293b] text-center mb-2">
            Sign In
          </h1>
          <p className="text-[#64748b] text-center text-[15px] mb-8">
            Access your digital wallet
          </p>

          {/* Google Button */}
          <button className="w-full h-[52px] flex items-center justify-center gap-3 text-[15px] font-medium text-[#1e293b] bg-white rounded-xl border border-[#e2e8f0] hover:bg-[#f8fafc] hover:border-[#cbd5e1] transition-all mb-6 shadow-sm">
            <svg width="20" height="20" viewBox="0 0 18 18">
              <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
              <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
              <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
              <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
            </svg>
            Sign in with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-[#e2e8f0]"/>
            <span className="text-[#94a3b8] text-xs font-medium tracking-wide">OR CONTINUE WITH EMAIL</span>
            <div className="flex-1 h-px bg-[#e2e8f0]"/>
          </div>

          <form onSubmit={handleSubmit} data-testid="login-form">
            {/* Email */}
            <div className="mb-5">
              <label className="block text-[#1e293b] text-[14px] font-medium mb-2">Email</label>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-[#94a3b8]">
                  <Mail size={18} strokeWidth={1.5} />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  data-testid="login-email-input"
                  className="w-full h-[52px] pl-12 pr-4 text-[15px] rounded-xl border border-[#e2e8f0] bg-white text-[#1e293b] placeholder-[#94a3b8] focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20 focus:outline-none transition-all"
                />
              </div>
            </div>

            {/* Password */}
            <div className="mb-2">
              <label className="block text-[#1e293b] text-[14px] font-medium mb-2">Password</label>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-[#94a3b8]">
                  <Lock size={18} strokeWidth={1.5} />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  data-testid="login-password-input"
                  className="w-full h-[52px] pl-12 pr-12 text-[15px] rounded-xl border border-[#e2e8f0] bg-white text-[#1e293b] placeholder-[#94a3b8] focus:border-[#6366f1] focus:ring-2 focus:ring-[#6366f1]/20 focus:outline-none transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[#94a3b8] hover:text-[#64748b] transition-colors"
                  data-testid="toggle-password-visibility"
                >
                  {showPassword ? <EyeOff size={18} strokeWidth={1.5}/> : <Eye size={18} strokeWidth={1.5}/>}
                </button>
              </div>
            </div>

            {/* Helper text */}
            <p className="text-[#94a3b8] text-[13px] mb-6">Must be at least 6 characters</p>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              data-testid="login-submit-button"
              className="w-full h-[52px] bg-[#6366f1] hover:bg-[#4f46e5] text-white font-semibold text-[15px] rounded-xl transition-all disabled:opacity-50 shadow-lg shadow-[#6366f1]/30 hover:shadow-xl hover:shadow-[#6366f1]/40"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          {/* Register */}
          <p className="text-center text-[#64748b] text-[15px] mt-6">
            Don't have an account?{' '}
            <Link to="/register" className="text-[#6366f1] font-semibold hover:underline" data-testid="create-account-link">
              Sign up
            </Link>
          </p>

        </div>
      </div>

    </div>
  );
}
