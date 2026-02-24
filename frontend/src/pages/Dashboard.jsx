import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowUpRight, ArrowDownLeft, History, User, Settings, 
  Shield, TrendingUp, LogOut, Bell, Headphones, Menu, X
} from 'lucide-react';
import api from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout, refreshUser } = useAuth();
  const { rates } = useRate();
  const [showMenu, setShowMenu] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);

  useEffect(() => {
    loadNotifications();
  }, []);

  const loadNotifications = async () => {
    try {
      const response = await api.get('/notifications/unread');
      setUnreadNotifications(response.data.count || 0);
    } catch (error) {
      console.error('Error loading notifications:', error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const menuItems = [
    { icon: ArrowUpRight, label: 'Enviar a Venezuela', path: '/send', color: 'bg-blue-500' },
    { icon: ArrowDownLeft, label: 'Recargar', path: '/recharge', color: 'bg-green-500' },
    { icon: History, label: 'Historial', path: '/history', color: 'bg-purple-500' },
    { icon: User, label: 'Perfil', path: '/profile', color: 'bg-orange-500' },
    { icon: Headphones, label: 'Soporte', path: '/support', color: 'bg-pink-500' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-gradient-to-r from-primary-600 to-primary-700 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                <TrendingUp className="w-5 h-5" />
              </div>
              <span className="font-bold text-lg hidden sm:block">RIS</span>
            </div>

            <div className="flex items-center gap-3">
              <Link to="/notifications" className="relative p-2 hover:bg-white/10 rounded-lg transition-colors">
                <Bell className="w-5 h-5" />
                {unreadNotifications > 0 && (
                  <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-xs flex items-center justify-center rounded-full">
                    {unreadNotifications > 9 ? '9+' : unreadNotifications}
                  </span>
                )}
              </Link>
              
              <button 
                onClick={() => setShowMenu(!showMenu)}
                className="p-2 hover:bg-white/10 rounded-lg transition-colors lg:hidden"
              >
                {showMenu ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>

              <div className="hidden lg:flex items-center gap-3">
                <span className="text-sm">{user?.full_name}</span>
                <button 
                  onClick={handleLogout}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                >
                  <LogOut className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Menu */}
      {showMenu && (
        <div className="lg:hidden bg-white border-b shadow-lg">
          <div className="p-4 space-y-2">
            {menuItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setShowMenu(false)}
                className="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors"
              >
                <div className={`${item.color} w-10 h-10 rounded-xl flex items-center justify-center`}>
                  <item.icon className="w-5 h-5 text-white" />
                </div>
                <span className="font-medium text-gray-700">{item.label}</span>
              </Link>
            ))}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors text-red-600"
            >
              <div className="bg-red-100 w-10 h-10 rounded-xl flex items-center justify-center">
                <LogOut className="w-5 h-5 text-red-600" />
              </div>
              <span className="font-medium">Cerrar Sesión</span>
            </button>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Balance Card */}
        <div className="bg-gradient-to-br from-primary-600 to-primary-800 rounded-3xl p-6 text-white mb-6 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-blue-200 text-sm">Balance disponible</p>
              <h2 className="text-4xl font-bold">{user?.balance?.toFixed(2) || '0.00'} RIS</h2>
            </div>
            <div className="w-16 h-16 rounded-2xl bg-white/20 flex items-center justify-center">
              <TrendingUp className="w-8 h-8" />
            </div>
          </div>
          
          <div className="flex items-center gap-2 text-blue-200">
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span>
            <span className="live-dot ml-1"></span>
          </div>
        </div>

        {/* Quick Actions Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Link
            to="/send"
            className="bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
              <ArrowUpRight className="w-6 h-6 text-blue-600" />
            </div>
            <h3 className="font-semibold text-gray-900">Enviar</h3>
            <p className="text-sm text-gray-500">A Venezuela</p>
          </Link>

          <Link
            to="/recharge"
            className="bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
              <ArrowDownLeft className="w-6 h-6 text-green-600" />
            </div>
            <h3 className="font-semibold text-gray-900">Recargar</h3>
            <p className="text-sm text-gray-500">PIX o Bolívares</p>
          </Link>

          <Link
            to="/history"
            className="bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
              <History className="w-6 h-6 text-purple-600" />
            </div>
            <h3 className="font-semibold text-gray-900">Historial</h3>
            <p className="text-sm text-gray-500">Transacciones</p>
          </Link>

          <Link
            to="/profile"
            className="bg-white rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-orange-100 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
              <User className="w-6 h-6 text-orange-600" />
            </div>
            <h3 className="font-semibold text-gray-900">Perfil</h3>
            <p className="text-sm text-gray-500">Mi cuenta</p>
          </Link>
        </div>

        {/* Rate Calculator */}
        <div className="bg-white rounded-2xl p-6 shadow-sm mb-6">
          <h3 className="font-semibold text-gray-900 mb-4">Calculadora de tasas</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
            <div>
              <label className="block text-sm text-gray-500 mb-2">Envías (RIS)</label>
              <input
                type="number"
                placeholder="0.00"
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              />
            </div>
            <div className="flex justify-center">
              <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-primary-600" />
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-500 mb-2">Recibes (VES)</label>
              <input
                type="number"
                placeholder="0.00"
                readOnly
                className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50"
              />
            </div>
          </div>
        </div>

        {/* KYC Status */}
        {user?.kyc_status !== 'verified' && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
                <Shield className="w-5 h-5 text-amber-600" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-amber-800">Verifica tu identidad</h3>
                <p className="text-sm text-amber-600 mt-1">
                  Completa la verificación KYC para desbloquear todas las funciones.
                </p>
                <Link
                  to="/verification"
                  className="inline-block mt-3 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  Verificar ahora
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Admin Access */}
        {(user?.role === 'admin' || user?.role === 'super_admin') && (
          <Link
            to="/admin"
            className="mt-6 block bg-gradient-to-r from-slate-800 to-slate-900 rounded-2xl p-5 text-white hover:from-slate-700 hover:to-slate-800 transition-all"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center">
                <Settings className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold">Panel de Administración</h3>
                <p className="text-sm text-slate-300">Gestionar plataforma</p>
              </div>
            </div>
          </Link>
        )}
      </main>
    </div>
  );
}
