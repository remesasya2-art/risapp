import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  Home, Wallet, Send, History, User, LogOut,
  Plus, ArrowUpRight, Eye, EyeOff, ChevronRight,
  TrendingUp, HelpCircle, Settings, Bell
} from 'lucide-react';
import api from '../utils/api';
import toast from 'react-hot-toast';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [showBalance, setShowBalance] = useState(true);
  const [greeting, setGreeting] = useState('');

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setGreeting('Buenos días');
    else if (hour < 18) setGreeting('Buenas tardes');
    else setGreeting('Buenas noches');
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const menuItems = [
    { icon: Home, label: 'Inicio', path: '/' },
    { icon: Wallet, label: 'Recargar', path: '/recharge' },
    { icon: Send, label: 'Enviar', path: '/send' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: User, label: 'Perfil', path: '/profile' },
  ];

  const isActive = (path) => location.pathname === path;

  const quickActions = [
    { icon: Plus, label: 'Recargar', path: '/recharge', color: 'bg-[#10B981]' },
    { icon: ArrowUpRight, label: 'Enviar', path: '/send', color: 'bg-[#3B82F6]' },
    { icon: History, label: 'Historial', path: '/history', color: 'bg-[#F59E0B]' },
    { icon: HelpCircle, label: 'Ayuda', path: '/support', color: 'bg-[#8B5CF6]' },
  ];

  return (
    <div className="min-h-screen bg-[#F8FAFC]" style={{fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'}} data-testid="dashboard-page">
      
      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-[240px] bg-white border-r border-[#E2E8F0] flex-col z-40">
        {/* Logo */}
        <div className="p-6 border-b border-[#E2E8F0]">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 bg-[#820AD1] rounded-2xl flex items-center justify-center shadow-lg shadow-[#820AD1]/20">
              <span className="text-white font-extrabold text-lg">R</span>
            </div>
            <span className="text-[#0F172A] font-bold text-xl">RIS</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            {menuItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-3.5 rounded-xl transition-all ${
                    isActive(item.path)
                      ? 'bg-[#F3E8FF] text-[#820AD1] font-semibold'
                      : 'text-[#64748B] hover:bg-[#F1F5F9] hover:text-[#0F172A]'
                  }`}
                >
                  <item.icon className="w-5 h-5" strokeWidth={isActive(item.path) ? 2.5 : 2} />
                  <span className="text-[15px]">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-[#E2E8F0]">
          <div className="flex items-center gap-3 px-3 py-2 mb-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#820AD1] to-[#A744F2] flex items-center justify-center text-white font-bold shadow-lg shadow-[#820AD1]/20">
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[#0F172A] text-sm font-semibold truncate">{user?.name || 'Usuario'}</p>
              <p className="text-[#64748B] text-xs truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-[#64748B] hover:bg-[#FEE2E2] hover:text-[#EF4444] transition-all w-full"
            data-testid="logout-button"
          >
            <LogOut className="w-5 h-5" />
            <span className="text-[15px]">Cerrar sesión</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:ml-[240px]">
        
        {/* Purple Header */}
        <div className="bg-[#820AD1] px-6 lg:px-8 pt-6 pb-32 relative overflow-hidden">
          {/* Background decoration */}
          <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-[#A744F2] rounded-full blur-[100px] opacity-50 -translate-y-1/2 translate-x-1/2"/>
          
          {/* Header Row */}
          <div className="relative z-10 flex items-center justify-between mb-8">
            <div>
              <p className="text-white/70 text-sm mb-1">{greeting},</p>
              <h1 className="text-white text-2xl font-bold">
                {user?.name?.split(' ')[0] || 'Usuario'}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <button className="w-11 h-11 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center transition-colors">
                <Bell className="w-5 h-5 text-white" />
              </button>
              <button className="w-11 h-11 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center transition-colors">
                <Settings className="w-5 h-5 text-white" />
              </button>
            </div>
          </div>

          {/* Balance */}
          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-2">
              <p className="text-white/80 text-sm font-medium">Tu saldo disponible</p>
              <button 
                onClick={() => setShowBalance(!showBalance)}
                className="text-white/60 hover:text-white transition-colors"
              >
                {showBalance ? <Eye size={18} /> : <EyeOff size={18} />}
              </button>
            </div>
            <p className="text-white text-[42px] font-extrabold tracking-tight">
              {showBalance ? `$${(user?.balance_ris || 0).toFixed(2)}` : '••••••'}
            </p>
          </div>
        </div>

        {/* Content Area */}
        <div className="px-6 lg:px-8 -mt-20 pb-8 relative z-20">
          
          {/* Quick Actions Card */}
          <div className="bg-white rounded-2xl shadow-xl shadow-black/5 p-6 mb-6" data-testid="balance-card">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[#0F172A] font-bold text-lg">Acciones rápidas</h2>
            </div>
            <div className="grid grid-cols-4 gap-4">
              {quickActions.map((action) => (
                <Link
                  key={action.path}
                  to={action.path}
                  className="flex flex-col items-center gap-3 p-4 rounded-2xl hover:bg-[#F8FAFC] transition-all group"
                  data-testid={action.label === 'Recargar' ? 'recharge-button' : action.label === 'Enviar' ? 'send-button' : undefined}
                >
                  <div className={`w-14 h-14 ${action.color} rounded-2xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform`}>
                    <action.icon className="w-6 h-6 text-white" />
                  </div>
                  <span className="text-[#64748B] text-sm font-medium group-hover:text-[#0F172A]">{action.label}</span>
                </Link>
              ))}
            </div>
          </div>

          {/* Exchange Rate Card */}
          <div className="bg-white rounded-2xl shadow-xl shadow-black/5 p-6 mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-[#10B981]/10 rounded-2xl flex items-center justify-center">
                  <TrendingUp className="w-6 h-6 text-[#10B981]" />
                </div>
                <div>
                  <p className="text-[#64748B] text-sm">Tasa de cambio actual</p>
                  <p className="text-[#0F172A] text-xl font-bold">1 RIS = {rates.ris_to_ves?.toFixed(2) || '0.00'} Bs</p>
                </div>
              </div>
              <div className="flex items-center gap-2 bg-[#10B981]/10 px-4 py-2 rounded-full">
                <div className="w-2 h-2 bg-[#10B981] rounded-full animate-pulse"/>
                <span className="text-[#10B981] text-sm font-semibold">EN VIVO</span>
              </div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-white rounded-2xl shadow-xl shadow-black/5 p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-[#0F172A] font-bold text-lg">Actividad reciente</h2>
              <Link to="/history" className="flex items-center gap-1 text-[#820AD1] text-sm font-semibold hover:underline">
                Ver todo
                <ChevronRight size={18} />
              </Link>
            </div>
            
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-20 h-20 bg-[#F1F5F9] rounded-full flex items-center justify-center mb-4">
                <History className="w-10 h-10 text-[#94A3B8]" />
              </div>
              <p className="text-[#64748B] text-center mb-2">No tienes transacciones aún</p>
              <p className="text-[#94A3B8] text-sm text-center mb-6">Comienza recargando tu cuenta</p>
              <Link 
                to="/recharge"
                className="bg-[#820AD1] hover:bg-[#6D08B0] text-white px-6 py-3 rounded-full font-semibold text-sm transition-all hover:shadow-lg hover:shadow-[#820AD1]/30"
              >
                Recargar ahora
              </Link>
            </div>
          </div>

        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-[#E2E8F0] px-2 py-2 z-50">
        <div className="flex items-center justify-around">
          {menuItems.slice(0, 5).map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center gap-1 px-4 py-2 rounded-xl transition-all ${
                isActive(item.path)
                  ? 'text-[#820AD1]'
                  : 'text-[#64748B]'
              }`}
            >
              <item.icon className="w-6 h-6" strokeWidth={isActive(item.path) ? 2.5 : 2} />
              <span className="text-xs font-medium">{item.label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}
