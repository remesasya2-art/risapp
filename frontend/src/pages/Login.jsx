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
  const [rememberMe, setRememberMe] = useState(true);

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
    <div className="min-h-screen relative overflow-hidden" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'}}>
      
      {/* Full background with gradient waves - like Stripe */}
      <div className="absolute inset-0">
        {/* Base gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#f6f9fc] via-[#f6f9fc] to-[#f0f4f8]" />
        
        {/* Colorful wave background - full coverage */}
        <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1920 1080">
          <defs>
            <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#80e9ff"/>
              <stop offset="100%" stopColor="#7dd3fc"/>
            </linearGradient>
            <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#fbbf24"/>
              <stop offset="100%" stopColor="#f97316"/>
            </linearGradient>
            <linearGradient id="grad3" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#fb7185"/>
              <stop offset="100%" stopColor="#f472b6"/>
            </linearGradient>
            <linearGradient id="grad4" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#a78bfa"/>
              <stop offset="100%" stopColor="#8b5cf6"/>
            </linearGradient>
          </defs>
          {/* Cyan/Blue wave - leftmost */}
          <path d="M800 0 Q900 200, 850 400 Q800 600, 900 800 Q1000 1000, 950 1080 L1920 1080 L1920 0 Z" fill="url(#grad1)" opacity="0.9"/>
          {/* Orange/Yellow wave */}
          <path d="M950 0 Q1050 180, 1000 380 Q950 580, 1050 780 Q1150 980, 1100 1080 L1920 1080 L1920 0 Z" fill="url(#grad2)" opacity="0.95"/>
          {/* Pink wave */}
          <path d="M1100 0 Q1200 160, 1150 360 Q1100 560, 1200 760 Q1300 960, 1250 1080 L1920 1080 L1920 0 Z" fill="url(#grad3)" opacity="0.95"/>
          {/* Purple wave - rightmost */}
          <path d="M1250 0 Q1350 140, 1300 340 Q1250 540, 1350 740 Q1450 940, 1400 1080 L1920 1080 L1920 0 Z" fill="url(#grad4)" opacity="0.95"/>
        </svg>
      </div>

      {/* Vertical line on left - Stripe style */}
      <div className="absolute left-[280px] top-0 bottom-0 w-px bg-[#e3e8ee] hidden lg:block" />

      {/* Header with logo */}
      <header className="relative z-10 px-8 py-6">
        <Link to="/" className="inline-flex items-center">
          <span className="text-[22px] font-bold text-[#0a2540]" style={{letterSpacing: '-0.02em'}}>RIS</span>
        </Link>
      </header>

      {/* Main content */}
      <main className="relative z-10 flex items-start justify-center px-4 pt-8 md:pt-12">
        <div 
          className="w-full max-w-[420px] bg-white rounded-xl overflow-hidden"
          style={{boxShadow: '0 30px 60px -12px rgba(50,50,93,0.25), 0 18px 36px -18px rgba(0,0,0,0.3)'}}
        >
          {/* Form container */}
          <div className="px-10 pt-10 pb-8">
            <h1 className="text-[22px] font-semibold text-[#0a2540] mb-7" style={{letterSpacing: '-0.02em'}}>
              Sign in to your account
            </h1>

            <form onSubmit={handleSubmit} data-testid="login-form">
              {/* Email field */}
              <div className="mb-5">
                <label className="block text-[14px] font-medium text-[#0a2540] mb-2">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email-input"
                  className="w-full h-[44px] px-4 text-[15px] rounded-lg border border-[#e3e8ee] bg-white text-[#0a2540] placeholder-[#8898aa] transition-all duration-150 focus:border-[#635bff] focus:ring-4 focus:ring-[#635bff]/10 focus:outline-none"
                  style={{boxShadow: '0 1px 2px rgba(0,0,0,0.05)'}}
                />
              </div>

              {/* Password field */}
              <div className="mb-5">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-[14px] font-medium text-[#0a2540]">Password</label>
                  <Link 
                    to="/forgot-password" 
                    className="text-[14px] text-[#635bff] hover:text-[#5046e5] transition-colors"
                    data-testid="forgot-password-link"
                  >
                    Forgot your password?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    data-testid="login-password-input"
                    className="w-full h-[44px] px-4 pr-11 text-[15px] rounded-lg border border-[#e3e8ee] bg-white text-[#0a2540] placeholder-[#8898aa] transition-all duration-150 focus:border-[#635bff] focus:ring-4 focus:ring-[#635bff]/10 focus:outline-none"
                    style={{boxShadow: '0 1px 2px rgba(0,0,0,0.05)'}}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8898aa] hover:text-[#0a2540] transition-colors"
                    data-testid="toggle-password-visibility"
                  >
                    {showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}
                  </button>
                </div>
              </div>

              {/* Remember me checkbox - Stripe style with filled checkbox */}
              <label className="flex items-center gap-2.5 mb-6 cursor-pointer select-none">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    data-testid="remember-me-checkbox"
                    className="sr-only peer"
                  />
                  <div className="w-5 h-5 rounded border-2 border-[#e3e8ee] bg-white peer-checked:bg-[#635bff] peer-checked:border-[#635bff] transition-all duration-150 flex items-center justify-center">
                    {rememberMe && (
                      <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
                <span className="text-[14px] text-[#425466]">Remember me on this device</span>
              </label>

              {/* Sign in button - Stripe purple gradient */}
              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit-button"
                className="w-full h-[44px] text-[15px] font-semibold text-white rounded-lg transition-all duration-150 disabled:opacity-60 disabled:cursor-not-allowed hover:brightness-110"
                style={{
                  background: 'linear-gradient(to bottom, #7c7aff, #625afa)',
                  boxShadow: '0 4px 6px rgba(99,91,255,0.4), inset 0 1px 0 rgba(255,255,255,0.1)'
                }}
              >
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center my-6">
              <div className="flex-1 h-px bg-[#e3e8ee]"/>
              <span className="px-4 text-[12px] font-medium text-[#8898aa] uppercase tracking-wider">Or</span>
              <div className="flex-1 h-px bg-[#e3e8ee]"/>
            </div>

            {/* Social login buttons */}
            <div className="space-y-3">
              {/* Google button */}
              <button 
                className="w-full h-[44px] flex items-center justify-center gap-3 text-[15px] font-medium text-[#0a2540] bg-white rounded-lg border border-[#e3e8ee] hover:bg-[#f7fafc] transition-all duration-150"
                style={{boxShadow: '0 1px 2px rgba(0,0,0,0.05)'}}
                data-testid="google-login-button"
              >
                <svg width="18" height="18" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                Sign in with Google
              </button>

              {/* Passkey button - no icon, just text like Stripe */}
              <button 
                className="w-full h-[44px] flex items-center justify-center text-[15px] font-medium text-[#0a2540] bg-white rounded-lg border border-[#e3e8ee] hover:bg-[#f7fafc] transition-all duration-150"
                style={{boxShadow: '0 1px 2px rgba(0,0,0,0.05)'}}
                data-testid="passkey-login-button"
              >
                Sign in with passkey
              </button>

              {/* SSO button - no icon, just text like Stripe */}
              <button 
                className="w-full h-[44px] flex items-center justify-center text-[15px] font-medium text-[#0a2540] bg-white rounded-lg border border-[#e3e8ee] hover:bg-[#f7fafc] transition-all duration-150"
                style={{boxShadow: '0 1px 2px rgba(0,0,0,0.05)'}}
                data-testid="sso-login-button"
              >
                Sign in with SSO
              </button>
            </div>
          </div>

          {/* Footer section with light gray background - inside card like Stripe */}
          <div className="px-10 py-5 bg-[#f7fafc] border-t border-[#e3e8ee]">
            <p className="text-[14px] text-[#425466] text-center">
              New to RIS?{' '}
              <Link 
                to="/register" 
                className="text-[#635bff] hover:text-[#5046e5] font-medium transition-colors"
                data-testid="create-account-link"
              >
                Create account
              </Link>
            </p>
          </div>
        </div>
      </main>

      {/* Footer at bottom */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 py-5 px-8 flex items-center gap-6">
        <span className="text-[13px] text-[#8898aa]">© RIS</span>
        <a href="#" className="text-[13px] text-[#8898aa] hover:text-[#425466] transition-colors">Privacy & terms</a>
      </footer>
    </div>
  );
}
