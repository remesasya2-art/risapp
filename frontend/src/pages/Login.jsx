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
    <div className="min-h-screen relative overflow-hidden bg-[#f6f9fc]" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'}}>
      
      {/* Wave background */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1920 1080' preserveAspectRatio='xMaxYMid slice'%3E%3Cpath d='M1000 0 Q1100 250 1050 500 Q1000 750 1100 1080 L1920 1080 L1920 0 Z' fill='%2380e9ff'/%3E%3Cpath d='M1100 0 Q1200 220 1150 470 Q1100 720 1200 1080 L1920 1080 L1920 0 Z' fill='%23ffba27'/%3E%3Cpath d='M1200 0 Q1300 200 1250 450 Q1200 700 1300 1080 L1920 1080 L1920 0 Z' fill='%23ff6b9d'/%3E%3Cpath d='M1320 0 Q1420 180 1370 430 Q1320 680 1420 1080 L1920 1080 L1920 0 Z' fill='%23c490e4'/%3E%3C/svg%3E")`,
          backgroundSize: 'cover',
          backgroundPosition: 'center right'
        }}
      />

      {/* Vertical line */}
      <div className="absolute left-[280px] top-0 bottom-0 w-px bg-[#e3e8ee] hidden lg:block" />

      {/* Header */}
      <header className="relative z-10 px-8 py-6">
        <Link to="/" className="inline-flex items-center">
          <span className="text-[22px] font-bold text-[#0a2540]">RIS</span>
        </Link>
      </header>

      {/* Main */}
      <main className="relative z-10 flex justify-center px-4 pt-[40px]">
        <div 
          className="w-full max-w-[480px] bg-white rounded-2xl overflow-hidden"
          style={{boxShadow: '0 15px 35px rgba(50,50,93,0.1), 0 5px 15px rgba(0,0,0,0.07)'}}
        >
          <div className="px-12 pt-12 pb-10">
            <h1 className="text-[24px] font-semibold text-[#0a2540] mb-8">
              Sign in to your account
            </h1>

            <form onSubmit={handleSubmit} data-testid="login-form">
              <div className="mb-6">
                <label className="block text-[15px] font-medium text-[#0a2540] mb-2">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email-input"
                  className="w-full h-[48px] px-4 text-[16px] rounded-xl border border-[#e6ebf1] bg-white text-[#0a2540] transition-all focus:border-[#635bff] focus:ring-3 focus:ring-[#635bff]/20 focus:outline-none"
                  style={{boxShadow: 'rgba(50, 50, 93, 0.08) 0px 1px 3px'}}
                />
              </div>

              <div className="mb-6">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-[15px] font-medium text-[#0a2540]">Password</label>
                  <Link to="/forgot-password" className="text-[14px] text-[#635bff] hover:text-[#5046e5]">
                    Forgot your password?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    data-testid="login-password-input"
                    className="w-full h-[48px] px-4 pr-12 text-[16px] rounded-xl border border-[#e6ebf1] bg-white text-[#0a2540] transition-all focus:border-[#635bff] focus:ring-3 focus:ring-[#635bff]/20 focus:outline-none"
                    style={{boxShadow: 'rgba(50, 50, 93, 0.08) 0px 1px 3px'}}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-[#8898aa] hover:text-[#0a2540]"
                  >
                    {showPassword ? <EyeOff size={20}/> : <Eye size={20}/>}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-3 mb-6 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-5 h-5 rounded border-[#e6ebf1] text-[#635bff] focus:ring-[#635bff]"
                />
                <span className="text-[15px] text-[#3c4257]">Remember me on this device</span>
              </label>

              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit-button"
                className="w-full h-[48px] text-[16px] font-semibold text-white rounded-xl disabled:opacity-60"
                style={{
                  background: 'linear-gradient(to bottom, #7c7aff, #635bff)',
                  boxShadow: 'rgba(99, 91, 255, 0.25) 0px 4px 6px'
                }}
              >
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            <div className="flex items-center my-6">
              <div className="flex-1 h-px bg-[#e6ebf1]"/>
              <span className="px-4 text-[12px] font-medium text-[#8898aa] uppercase">Or</span>
              <div className="flex-1 h-px bg-[#e6ebf1]"/>
            </div>

            <div className="space-y-3">
              <button className="w-full h-[48px] flex items-center justify-center gap-3 text-[15px] font-medium text-[#3c4257] bg-white rounded-xl border border-[#e6ebf1] hover:bg-[#f7fafc]" style={{boxShadow: 'rgba(50, 50, 93, 0.08) 0px 1px 3px'}}>
                <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/><path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/></svg>
                Sign in with Google
              </button>
              <button className="w-full h-[48px] flex items-center justify-center text-[15px] font-medium text-[#3c4257] bg-white rounded-xl border border-[#e6ebf1] hover:bg-[#f7fafc]" style={{boxShadow: 'rgba(50, 50, 93, 0.08) 0px 1px 3px'}}>
                Sign in with passkey
              </button>
              <button className="w-full h-[48px] flex items-center justify-center text-[15px] font-medium text-[#3c4257] bg-white rounded-xl border border-[#e6ebf1] hover:bg-[#f7fafc]" style={{boxShadow: 'rgba(50, 50, 93, 0.08) 0px 1px 3px'}}>
                Sign in with SSO
              </button>
            </div>
          </div>

          <div className="px-12 py-5 bg-[#f7fafc] border-t border-[#e6ebf1]">
            <p className="text-[15px] text-[#3c4257] text-center">
              New to RIS? <Link to="/register" className="text-[#635bff] hover:text-[#5046e5] font-medium">Create account</Link>
            </p>
          </div>
        </div>
      </main>

      <footer className="absolute bottom-0 left-0 z-10 py-5 px-8 flex items-center gap-6">
        <span className="text-[13px] text-[#8898aa]">© RIS</span>
        <a href="#" className="text-[13px] text-[#8898aa] hover:text-[#3c4257]">Privacy & terms</a>
      </footer>
    </div>
  );
}
