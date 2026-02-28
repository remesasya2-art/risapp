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
    <div className="min-h-screen relative overflow-hidden" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif', background: 'linear-gradient(135deg, #f6f9fc 0%, #f6f9fc 100%)'}}>
      
      {/* Stripe-style colorful wave background - right side */}
      <div className="absolute top-0 right-0 w-[60%] h-full pointer-events-none overflow-hidden">
        <svg className="absolute top-0 right-0 h-full" style={{width: '100%', minWidth: '800px'}} viewBox="0 0 800 1200" preserveAspectRatio="xMaxYMid slice">
          {/* Cyan wave */}
          <path d="M350 0 Q450 300, 350 600 Q250 900, 400 1200 L800 1200 L800 0 Z" fill="#80e9ff" opacity="1"/>
          {/* Orange wave */}
          <path d="M450 0 Q550 250, 450 550 Q350 850, 500 1200 L800 1200 L800 0 Z" fill="#f5b352" opacity="1"/>
          {/* Pink wave */}
          <path d="M530 0 Q630 200, 530 500 Q430 800, 580 1200 L800 1200 L800 0 Z" fill="#ff87a0" opacity="1"/>
          {/* Purple wave */}
          <path d="M610 0 Q710 150, 620 450 Q530 750, 680 1200 L800 1200 L800 0 Z" fill="#9a7bff" opacity="1"/>
        </svg>
      </div>

      {/* Header with Stripe logo style */}
      <header className="relative z-10 p-6">
        <Link to="/" className="inline-flex items-center">
          <svg className="h-8 w-auto" viewBox="0 0 60 25" fill="none">
            <path fill="#635bff" d="M5 10.2c0-.7.6-1 1.5-1 1.3 0 3 .4 4.3 1.1V6.5c-1.4-.6-2.9-.8-4.3-.8C3.2 5.7.8 7.5.8 10.5c0 4.7 6.5 3.9 6.5 5.9 0 .8-.7 1.1-1.7 1.1-1.5 0-3.4-.6-4.9-1.4v3.8c1.7.7 3.3 1 4.9 1 3.4 0 5.8-1.7 5.8-4.8 0-5-6.4-4.1-6.4-6zM17.5 20.9h4.2V5.9h-4.2v15zM17.5 4.5h4.2V.8h-4.2v3.7zM28.3 7.4l-.3-1.5h-3.7v15h4.2v-10c1-.6 2.7-.5 3.2-.3V6c-.5-.2-2.5-.5-3.4 1.4zM36.4 20.9h4.2V5.9h-4.2v15zM36.4 4.5h4.2V.8h-4.2v3.7zM47.2 15.8c0 3.3 2.5 5.1 6 5.1 1.8 0 3.2-.4 4.3-1v-3.4c-1.1.5-2.4.8-3.8.8-1.6 0-2.5-.6-2.5-2v-4.9h4.2V6.5h-4.2V2.4l-4 .9v3.2h-2.3v3.9h2.3v5.4z"/>
          </svg>
        </Link>
      </header>

      {/* Main content - centered form */}
      <main className="relative z-10 flex items-start justify-center pt-8 pb-20 px-4 md:pt-16">
        <div 
          className="w-full max-w-[400px] bg-white rounded-lg"
          style={{boxShadow: '0 15px 35px rgba(50,50,93,0.1), 0 5px 15px rgba(0,0,0,0.07)'}}
        >
          {/* Form container */}
          <div className="p-10">
            <h1 className="text-xl font-semibold text-[#3c4257] mb-6" style={{letterSpacing: '-0.02em'}}>
              Sign in to your account
            </h1>

            <form onSubmit={handleSubmit} data-testid="login-form">
              {/* Email field */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-[#3c4257] mb-1.5">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email-input"
                  className="w-full h-10 px-3 text-sm rounded-md border border-[#e6e6e6] bg-white text-[#3c4257] placeholder-[#8898aa] transition-all duration-150 focus:border-[#635bff] focus:ring-2 focus:ring-[#635bff]/20 focus:outline-none"
                  style={{boxShadow: '0 1px 3px rgba(50,50,93,0.08)'}}
                />
              </div>

              {/* Password field */}
              <div className="mb-4">
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-sm font-medium text-[#3c4257]">Password</label>
                  <Link 
                    to="/forgot-password" 
                    className="text-sm text-[#635bff] hover:text-[#5046e5] transition-colors"
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
                    className="w-full h-10 px-3 pr-10 text-sm rounded-md border border-[#e6e6e6] bg-white text-[#3c4257] placeholder-[#8898aa] transition-all duration-150 focus:border-[#635bff] focus:ring-2 focus:ring-[#635bff]/20 focus:outline-none"
                    style={{boxShadow: '0 1px 3px rgba(50,50,93,0.08)'}}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8898aa] hover:text-[#3c4257] transition-colors"
                    data-testid="toggle-password-visibility"
                  >
                    {showPassword ? <EyeOff size={16}/> : <Eye size={16}/>}
                  </button>
                </div>
              </div>

              {/* Remember me checkbox */}
              <label className="flex items-center gap-2 mb-6 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  data-testid="remember-me-checkbox"
                  className="w-4 h-4 rounded border-[#e6e6e6] text-[#635bff] focus:ring-[#635bff] focus:ring-offset-0 cursor-pointer"
                />
                <span className="text-sm text-[#3c4257]">Remember me on this device</span>
              </label>

              {/* Sign in button */}
              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit-button"
                className="w-full h-10 text-sm font-medium text-white rounded-md transition-all duration-150 disabled:opacity-60 disabled:cursor-not-allowed"
                style={{
                  background: 'linear-gradient(180deg, #635bff 0%, #5851ea 100%)',
                  boxShadow: '0 4px 6px rgba(99,91,255,0.25), 0 1px 3px rgba(0,0,0,0.1)'
                }}
                onMouseOver={(e) => !loading && (e.currentTarget.style.transform = 'translateY(-1px)', e.currentTarget.style.boxShadow = '0 7px 14px rgba(99,91,255,0.3), 0 3px 6px rgba(0,0,0,0.1)')}
                onMouseOut={(e) => (e.currentTarget.style.transform = 'translateY(0)', e.currentTarget.style.boxShadow = '0 4px 6px rgba(99,91,255,0.25), 0 1px 3px rgba(0,0,0,0.1)')}
              >
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center my-6">
              <div className="flex-1 h-px bg-[#e6e6e6]"/>
              <span className="px-4 text-xs font-medium text-[#8898aa] uppercase">Or</span>
              <div className="flex-1 h-px bg-[#e6e6e6]"/>
            </div>

            {/* Social login buttons */}
            <div className="space-y-3">
              {/* Google button */}
              <button 
                className="w-full h-10 flex items-center justify-center gap-2 text-sm font-medium text-[#3c4257] bg-white rounded-md border border-[#e6e6e6] hover:bg-[#f6f9fc] transition-all duration-150"
                style={{boxShadow: '0 1px 3px rgba(50,50,93,0.08)'}}
                data-testid="google-login-button"
              >
                <svg width="16" height="16" viewBox="0 0 18 18">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                Sign in with Google
              </button>

              {/* Passkey button */}
              <button 
                className="w-full h-10 flex items-center justify-center gap-2 text-sm font-medium text-[#3c4257] bg-white rounded-md border border-[#e6e6e6] hover:bg-[#f6f9fc] transition-all duration-150"
                style={{boxShadow: '0 1px 3px rgba(50,50,93,0.08)'}}
                data-testid="passkey-login-button"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3c4257" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3"/>
                  <circle cx="6" cy="12" r="4"/>
                  <path d="M18 8v7a3 3 0 0 1-3 3H9"/>
                </svg>
                Sign in with passkey
              </button>

              {/* SSO button */}
              <button 
                className="w-full h-10 flex items-center justify-center gap-2 text-sm font-medium text-[#3c4257] bg-white rounded-md border border-[#e6e6e6] hover:bg-[#f6f9fc] transition-all duration-150"
                style={{boxShadow: '0 1px 3px rgba(50,50,93,0.08)'}}
                data-testid="sso-login-button"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3c4257" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                  <line x1="3" y1="9" x2="21" y2="9"/>
                  <line x1="9" y1="21" x2="9" y2="9"/>
                </svg>
                Sign in with SSO
              </button>
            </div>
          </div>

          {/* Footer section with light background */}
          <div className="px-10 py-4 bg-[#f6f9fc] border-t border-[#e6e6e6] rounded-b-lg">
            <p className="text-sm text-[#3c4257] text-center">
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

      {/* Footer */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 py-4 px-6 flex items-center gap-4">
        <a href="#" className="text-xs text-[#8898aa] hover:text-[#3c4257] transition-colors">© RIS</a>
        <a href="#" className="text-xs text-[#8898aa] hover:text-[#3c4257] transition-colors">Privacy & terms</a>
      </footer>
    </div>
  );
}
