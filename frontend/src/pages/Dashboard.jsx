import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  Home, Send, History, Users, LogOut, Wallet, 
  ArrowRight, CreditCard, MessageCircle, TrendingUp,
  User, Bell, Menu, X, CheckCircle, Settings, Plus, ArrowUpRight, Clock
} from 'lucide-react';
import api from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);

  useEffect(() => {
    loadNotifications();
  }, []);

  const loadNotifications = async () => {
    try {
      const response = await api.get('/notifications/unread-count').catch(() => ({ data: { count: 0 } }));
      setUnreadNotifications(response.data.count || 0);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const menuItems = [
    { icon: Home, label: 'Inicio', path: '/' },
    { icon: Send, label: 'Enviar Remesa', path: '/send' },
    { icon: Wallet, label: 'Recargar', path: '/recharge' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: Users, label: 'Beneficiarios', path: '/beneficiaries' },
    { icon: User, label: 'Mi Perfil', path: '/profile' },
  ];

  return (
    <div className="min-h-screen bg-gray-50" data-testid="dashboard-page">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            {/* Left: Hamburger + Logo */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setMenuOpen(true)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label="Abrir menú"
                data-testid="menu-button"
              >
                <Menu className="w-6 h-6 text-gray-700" />
              </button>
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center shadow-sm">
                  <Wallet className="w-5 h-5 text-white" />
                </div>
                <span className="font-bold text-gray-900 text-lg hidden sm:block">RIS</span>
              </div>
            </div>

            {/* Right: Notifications + Profile */}
            <div className="flex items-center gap-2">
              <Link 
                to="/notifications" 
                className="relative p-2.5 hover:bg-gray-100 rounded-xl transition-colors"
                data-testid="notifications-button"
              >
                <Bell className="w-5 h-5 text-gray-600" />
                {unreadNotifications > 0 && (
                  <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full font-bold">
                    {unreadNotifications}
                  </span>
                )}
              </Link>
              <Link 
                to="/profile" 
                className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-xl transition-colors"
                data-testid="profile-button"
              >
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center shadow-sm">
                  <span className="text-white font-semibold text-sm">{user?.name?.charAt(0)?.toUpperCase() || 'U'}</span>
                </div>
                <span className="text-sm font-medium text-gray-700 hidden md:block">{user?.name?.split(' ')[0]}</span>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Menu Overlay */}
      {menuOpen && (
        <div className="fixed inset-0 z-50">
          <div 
            className="absolute inset-0 bg-black/50 transition-opacity" 
            onClick={() => setMenuOpen(false)} 
          />
          
          <div className="absolute left-0 top-0 bottom-0 w-72 bg-white shadow-2xl animate-slideIn">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                  <Wallet className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h1 className="font-bold text-gray-900">RIS</h1>
                  <p className="text-xs text-gray-500">Remesas Seguras</p>
                </div>
              </div>
              <button 
                onClick={() => setMenuOpen(false)} 
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>

            <div className="p-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white font-bold">
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <div>
                  <p className="font-medium text-gray-900">{user?.name}</p>
                  <p className="text-sm text-gray-500">{user?.email}</p>
                </div>
              </div>
              <div className="mt-3 bg-orange-50 rounded-xl p-3">
                <p className="text-xs text-orange-600 mb-1">Balance disponible</p>
                <p className="text-xl font-bold text-orange-600">{(user?.balance_ris || 0).toFixed(2)} RIS</p>
              </div>
            </div>

            <nav className="p-4 flex-1 overflow-y-auto">
              <ul className="space-y-1">
                {menuItems.map((item) => (
                  <li key={item.path}>
                    <Link
                      to={item.path}
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-700 hover:bg-orange-50 hover:text-orange-600 transition-colors"
                    >
                      <item.icon className="w-5 h-5" />
                      <span className="font-medium">{item.label}</span>
                    </Link>
                  </li>
                ))}
                
                {(user?.role === 'admin' || user?.role === 'super_admin') && (
                  <li className="pt-4 mt-4 border-t border-gray-100">
                    <Link
                      to="/admin"
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-700 hover:bg-orange-50 hover:text-orange-600 transition-colors"
                    >
                      <Settings className="w-5 h-5" />
                      <span className="font-medium">Administración</span>
                    </Link>
                  </li>
                )}
              </ul>
            </nav>

            <div className="p-4 border-t border-gray-100">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-red-600 hover:bg-red-50 transition-colors w-full"
                data-testid="logout-button"
              >
                <LogOut className="w-5 h-5" />
                <span className="font-medium">Cerrar sesión</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {/* Welcome Section + Balance Card */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">
            Hola, {user?.name?.split(' ')[0] || 'Usuario'}
          </h1>
          <p className="text-gray-500">Bienvenido de vuelta a RIS</p>
        </div>

        {/* Balance Card - Prominent */}
        <div className="bg-gradient-to-r from-orange-500 to-orange-600 rounded-2xl p-6 mb-6 shadow-lg" data-testid="balance-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-orange-100 text-sm font-medium mb-1">Balance disponible</p>
              <p className="text-4xl font-bold text-white">{(user?.balance_ris || 0).toFixed(2)} <span className="text-2xl font-normal text-orange-200">RIS</span></p>
            </div>
            <div className="w-14 h-14 bg-white/20 rounded-2xl flex items-center justify-center">
              <Wallet className="w-7 h-7 text-white" />
            </div>
          </div>
          
          {/* Quick Actions */}
          <div className="flex gap-3">
            <Link 
              to="/recharge" 
              className="flex-1 flex items-center justify-center gap-2 bg-white text-orange-600 py-3 rounded-xl font-semibold hover:bg-orange-50 transition-colors shadow-sm"
              data-testid="recharge-button"
            >
              <Plus className="w-5 h-5" />
              Recargar
            </Link>
            <Link 
              to="/send" 
              className="flex-1 flex items-center justify-center gap-2 bg-white/20 text-white py-3 rounded-xl font-semibold hover:bg-white/30 transition-colors border border-white/30"
              data-testid="send-button"
            >
              <ArrowUpRight className="w-5 h-5" />
              Enviar
            </Link>
          </div>
        </div>

        {/* Exchange Rate Banner */}
        <div className="bg-white rounded-xl p-4 mb-6 border border-gray-100 shadow-sm flex items-center justify-between" data-testid="exchange-rate">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Tasa de cambio actual</p>
              <p className="font-bold text-gray-900 text-lg">1 RIS = {rates.ris_to_ves.toFixed(2)} Bs</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-green-600 bg-green-50 px-3 py-1.5 rounded-full">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-xs font-medium">EN VIVO</span>
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column */}
          <div className="lg:col-span-2 space-y-6">
            {/* Quick Actions Grid */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-lg font-bold text-gray-900 mb-4">Acciones rápidas</h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <Link 
                  to="/send" 
                  className="flex flex-col items-center gap-3 p-4 rounded-xl bg-gray-50 hover:bg-orange-50 hover:border-orange-200 border border-gray-100 transition-all group"
                  data-testid="quick-send"
                >
                  <div className="w-12 h-12 rounded-xl bg-orange-100 flex items-center justify-center group-hover:bg-orange-200 transition-colors">
                    <Send className="w-6 h-6 text-orange-600" />
                  </div>
                  <span className="text-sm font-medium text-gray-700">Enviar</span>
                </Link>
                
                <Link 
                  to="/recharge" 
                  className="flex flex-col items-center gap-3 p-4 rounded-xl bg-gray-50 hover:bg-orange-50 hover:border-orange-200 border border-gray-100 transition-all group"
                  data-testid="quick-recharge"
                >
                  <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center group-hover:bg-green-200 transition-colors">
                    <Plus className="w-6 h-6 text-green-600" />
                  </div>
                  <span className="text-sm font-medium text-gray-700">Recargar</span>
                </Link>
                
                <Link 
                  to="/history" 
                  className="flex flex-col items-center gap-3 p-4 rounded-xl bg-gray-50 hover:bg-orange-50 hover:border-orange-200 border border-gray-100 transition-all group"
                  data-testid="quick-history"
                >
                  <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center group-hover:bg-blue-200 transition-colors">
                    <History className="w-6 h-6 text-blue-600" />
                  </div>
                  <span className="text-sm font-medium text-gray-700">Historial</span>
                </Link>
                
                <Link 
                  to="/beneficiaries" 
                  className="flex flex-col items-center gap-3 p-4 rounded-xl bg-gray-50 hover:bg-orange-50 hover:border-orange-200 border border-gray-100 transition-all group"
                  data-testid="quick-beneficiaries"
                >
                  <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center group-hover:bg-purple-200 transition-colors">
                    <Users className="w-6 h-6 text-purple-600" />
                  </div>
                  <span className="text-sm font-medium text-gray-700">Beneficiarios</span>
                </Link>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-gray-900">Actividad reciente</h2>
                <Link to="/history" className="text-sm text-orange-500 hover:text-orange-600 font-medium flex items-center gap-1">
                  Ver todo
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
              
              <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mb-3">
                  <Clock className="w-8 h-8 text-gray-300" />
                </div>
                <p className="font-medium text-gray-500">Sin transacciones recientes</p>
                <p className="text-sm text-gray-400 mt-1">Tus transacciones aparecerán aquí</p>
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            {/* User Profile Card */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white text-xl font-bold shadow-md">
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-900 truncate">{user?.name}</h3>
                  <p className="text-sm text-gray-500 truncate">{user?.email}</p>
                </div>
              </div>
              
              {user?.verification_status === 'verified' ? (
                <div className="flex items-center gap-2 text-green-700 bg-green-50 px-4 py-2.5 rounded-xl border border-green-100">
                  <CheckCircle className="w-5 h-5" />
                  <span className="font-medium">Cuenta verificada</span>
                </div>
              ) : (
                <Link 
                  to="/verification" 
                  className="flex items-center justify-center gap-2 w-full bg-amber-50 text-amber-700 px-4 py-2.5 rounded-xl font-medium hover:bg-amber-100 transition-colors border border-amber-100"
                  data-testid="verify-account"
                >
                  <CheckCircle className="w-5 h-5" />
                  Verificar mi cuenta
                </Link>
              )}
            </div>

            {/* Payment Methods */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
              <h3 className="font-semibold text-gray-900 mb-4">Métodos de recarga</h3>
              <div className="space-y-3">
                <Link 
                  to="/recharge" 
                  className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 hover:bg-green-50 border border-gray-100 hover:border-green-200 transition-all"
                >
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                    <CreditCard className="w-5 h-5 text-green-600" />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">PIX (Brasil)</p>
                    <p className="text-xs text-gray-500">Pago instantáneo</p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </Link>
                
                <Link 
                  to="/recharge" 
                  className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 hover:bg-blue-50 border border-gray-100 hover:border-blue-200 transition-all"
                >
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                    <Wallet className="w-5 h-5 text-blue-600" />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">Bolívares (VES)</p>
                    <p className="text-xs text-gray-500">Transferencia bancaria</p>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </Link>
              </div>
            </div>

            {/* Support Card */}
            <div className="bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl p-5 text-white shadow-lg">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
                  <MessageCircle className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-lg">¿Necesitas ayuda?</h3>
              </div>
              <p className="text-orange-100 text-sm mb-4">
                Nuestro equipo de soporte está disponible 24/7 para ayudarte.
              </p>
              <Link
                to="/support"
                className="flex items-center justify-center gap-2 bg-white text-orange-600 py-3 rounded-xl font-semibold hover:bg-orange-50 transition-colors shadow-sm"
                data-testid="support-button"
              >
                <MessageCircle className="w-5 h-5" />
                Ir al chat de soporte
              </Link>
            </div>
          </div>
        </div>
      </main>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(-100%); }
          to { transform: translateX(0); }
        }
        .animate-slideIn {
          animation: slideIn 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
