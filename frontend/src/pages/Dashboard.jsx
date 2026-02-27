import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  Home, Send, History, Users, LogOut, Wallet, 
  ArrowRight, CreditCard, MessageCircle,
  User, Bell, Menu, X, CheckCircle, Settings
} from 'lucide-react';
import api from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [amount, setAmount] = useState('');
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

  const calculatedVes = amount ? (parseFloat(amount) * rates.ris_to_ves).toFixed(2) : '0.00';

  const menuItems = [
    { icon: Home, label: 'Inicio', path: '/' },
    { icon: Send, label: 'Enviar Remesa', path: '/send' },
    { icon: Wallet, label: 'Recargar', path: '/recharge' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: Users, label: 'Beneficiarios', path: '/beneficiaries' },
    { icon: User, label: 'Mi Perfil', path: '/profile' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
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
              >
                <Menu className="w-6 h-6 text-gray-700" />
              </button>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                  <Wallet className="w-4 h-4 text-white" />
                </div>
                <span className="font-bold text-gray-900 hidden sm:block">RIS</span>
              </div>
            </div>

            {/* Center: Balance + Recharge */}
            <div className="flex items-center gap-2">
              <div className="bg-gray-100 px-3 py-1.5 rounded-lg">
                <span className="font-bold text-gray-900 text-sm sm:text-base">{(user?.balance_ris || 0).toFixed(2)} RIS</span>
              </div>
              <Link
                to="/recharge"
                className="bg-orange-500 hover:bg-orange-600 text-white px-3 py-1.5 rounded-lg font-medium text-sm transition-colors"
              >
                Recargar
              </Link>
            </div>

            {/* Right: Notifications + Profile */}
            <div className="flex items-center gap-1">
              <Link to="/notifications" className="relative p-2 hover:bg-gray-100 rounded-lg">
                <Bell className="w-5 h-5 text-gray-600" />
                {unreadNotifications > 0 && (
                  <span className="absolute top-0.5 right-0.5 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full font-medium">
                    {unreadNotifications}
                  </span>
                )}
              </Link>
              <Link to="/profile" className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg">
                <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center">
                  <span className="text-orange-600 font-medium text-sm">{user?.name?.charAt(0)?.toUpperCase() || 'U'}</span>
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
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/50 transition-opacity" 
            onClick={() => setMenuOpen(false)} 
          />
          
          {/* Menu Panel */}
          <div className="absolute left-0 top-0 bottom-0 w-72 bg-white shadow-2xl animate-slideIn">
            {/* Menu Header */}
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

            {/* User Info */}
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
              <div className="mt-3 bg-orange-50 rounded-lg p-3">
                <p className="text-xs text-orange-600 mb-1">Balance disponible</p>
                <p className="text-xl font-bold text-orange-600">{(user?.balance_ris || 0).toFixed(2)} RIS</p>
              </div>
            </div>

            {/* Navigation */}
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
                
                {/* Admin Link */}
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

            {/* Logout */}
            <div className="p-4 border-t border-gray-100">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-red-600 hover:bg-red-50 transition-colors w-full"
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Send Money Card */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <h2 className="text-xl font-bold text-gray-900 mb-6">Enviar dinero</h2>
              
              <div className="space-y-5">
                {/* Amount Input */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Monto a enviar
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-full px-4 py-4 text-2xl font-semibold rounded-xl border border-gray-200 focus:ring-2 focus:ring-orange-500 focus:border-transparent pr-24"
                    />
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 bg-gray-100 px-3 py-1.5 rounded-lg">
                      <span className="text-lg">🇧🇷</span>
                      <span className="font-medium text-gray-700 text-sm">RIS</span>
                    </div>
                  </div>
                </div>

                {/* Result */}
                <div className="bg-green-50 rounded-xl p-4 border border-green-100">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-green-700 mb-1">Beneficiario recibe</p>
                      <p className="text-3xl font-bold text-green-600">
                        {calculatedVes} <span className="text-lg font-normal text-green-500">Bs</span>
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Tasa de cambio</p>
                      <p className="text-sm font-semibold text-gray-700">1 RIS = {rates.ris_to_ves.toFixed(2)} Bs</p>
                    </div>
                  </div>
                </div>

                {/* Payment Methods */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">Pagar con</label>
                  <div className="grid grid-cols-2 gap-3">
                    <button className="flex flex-col items-center gap-2 p-4 border-2 border-orange-500 bg-orange-50 rounded-xl">
                      <Wallet className="w-6 h-6 text-orange-500" />
                      <span className="text-sm font-medium text-gray-700">Saldo RIS</span>
                    </button>
                    <Link to="/recharge" className="flex flex-col items-center gap-2 p-4 border border-gray-200 rounded-xl hover:border-orange-300 hover:bg-orange-50 transition-colors">
                      <CreditCard className="w-6 h-6 text-gray-400" />
                      <span className="text-sm font-medium text-gray-500">PIX</span>
                    </Link>
                  </div>
                </div>

                {/* Send Button */}
                <Link
                  to="/send"
                  className="w-full bg-orange-500 hover:bg-orange-600 text-white py-4 rounded-xl font-semibold text-center block transition-colors text-lg"
                >
                  Enviar remesa
                </Link>
              </div>
            </div>

            {/* Promotional Card */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <h3 className="text-xl font-bold text-gray-900 mb-2">¡Recarga tu saldo!</h3>
              <p className="text-gray-600 mb-4">
                Recarga de forma rápida, confiable y segura usando PIX o Bolívares.
              </p>
              <Link
                to="/recharge"
                className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white px-6 py-3 rounded-xl font-medium transition-colors"
              >
                Ir a recargar
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* Right Column - Info Cards */}
          <div className="space-y-6">
            {/* Quick Rates */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
              <h3 className="font-semibold text-gray-900 mb-4">Tasas rápidas</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">🇧🇷</span>
                    <span className="text-sm text-gray-600">1 RIS</span>
                    <ArrowRight className="w-4 h-4 text-gray-400" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-gray-900">🇻🇪 {rates.ris_to_ves.toFixed(2)} Bs</span>
                    <Link to="/send" className="px-3 py-1 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors">
                      Enviar
                    </Link>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-gray-500">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span>Tasas actualizadas en tiempo real</span>
              </div>
            </div>

            {/* User Card */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white text-lg font-bold">
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">{user?.name}</h3>
                  <p className="text-sm text-gray-500">{user?.email}</p>
                </div>
              </div>
              
              {user?.verification_status === 'verified' ? (
                <div className="flex items-center gap-2 text-green-600 bg-green-50 px-3 py-2 rounded-lg">
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm font-medium">Cuenta verificada</span>
                </div>
              ) : (
                <Link to="/verification" className="block w-full text-center bg-amber-50 text-amber-700 px-3 py-2 rounded-lg text-sm font-medium hover:bg-amber-100 transition-colors">
                  Verificar mi cuenta
                </Link>
              )}
            </div>

            {/* Support */}
            <div className="bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl p-5 text-white">
              <div className="flex items-center gap-3 mb-3">
                <MessageCircle className="w-6 h-6" />
                <h3 className="font-semibold">¿Necesitas ayuda?</h3>
              </div>
              <p className="text-orange-100 text-sm mb-4">
                Nuestro equipo de soporte está disponible para ayudarte.
              </p>
              <Link
                to="/support"
                className="flex items-center justify-center gap-2 bg-white text-orange-600 py-2.5 rounded-xl font-medium hover:bg-orange-50 transition-colors"
              >
                <MessageCircle className="w-4 h-4" />
                Ir al chat de soporte
              </Link>
            </div>

            {/* Activity */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-gray-900">Actividad reciente</h3>
                <Link to="/history" className="text-sm text-orange-500 hover:text-orange-600 font-medium">
                  Ver todo
                </Link>
              </div>
              <div className="text-center py-6 text-gray-400">
                <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">Sin transacciones recientes</p>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Animation styles */}
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
