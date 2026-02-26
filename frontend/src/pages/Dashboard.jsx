import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  Home, Send, History, Users, LogOut, Wallet, RefreshCw,
  ChevronDown, ArrowRight, CreditCard, Building, MessageCircle,
  User, Bell, Menu, X, CheckCircle, TrendingUp, Settings
} from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    { icon: Send, label: 'Remesas', path: '/send' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: Users, label: 'Beneficiarios', path: '/beneficiaries' },
  ];

  const quickRates = [
    { from: 'BRL', to: 'VES', rate: rates.ris_to_ves, flag: '🇧🇷' },
    { from: 'USD', to: 'VES', rate: rates.ris_to_ves * 0.18, flag: '🇺🇸' },
  ];

  return (
    <div className="min-h-screen bg-gray-100 flex">
      {/* Sidebar - Desktop */}
      <aside className="hidden lg:flex lg:flex-col lg:w-64 bg-white border-r border-gray-200 fixed h-full z-30">
        {/* Logo */}
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
              <Wallet className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-gray-900 text-lg">RIS</h1>
              <p className="text-xs text-gray-500">Remesas Seguras</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            {menuItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                      isActive 
                        ? 'bg-orange-50 text-orange-600 font-medium' 
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <item.icon className={`w-5 h-5 ${isActive ? 'text-orange-500' : 'text-gray-400'}`} />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* Admin Link */}
          {(user?.role === 'admin' || user?.role === 'super_admin') && (
            <div className="mt-6 pt-6 border-t border-gray-100">
              <Link
                to="/admin"
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-600 hover:bg-gray-50 transition-all"
              >
                <Settings className="w-5 h-5 text-gray-400" />
                <span>Administración</span>
              </Link>
            </div>
          )}
        </nav>

        {/* Logout */}
        <div className="p-4 border-t border-gray-100">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-600 hover:bg-red-50 hover:text-red-600 transition-all w-full"
          >
            <LogOut className="w-5 h-5" />
            <span>Cerrar sesión</span>
          </button>
        </div>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-72 bg-white shadow-xl">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                  <Wallet className="w-5 h-5 text-white" />
                </div>
                <span className="font-bold text-gray-900">RIS</span>
              </div>
              <button onClick={() => setSidebarOpen(false)} className="p-2 hover:bg-gray-100 rounded-lg">
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <nav className="p-4">
              <ul className="space-y-1">
                {menuItems.map((item) => (
                  <li key={item.path}>
                    <Link
                      to={item.path}
                      onClick={() => setSidebarOpen(false)}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-600 hover:bg-gray-50"
                    >
                      <item.icon className="w-5 h-5 text-gray-400" />
                      <span>{item.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-100">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-red-600 hover:bg-red-50 w-full"
              >
                <LogOut className="w-5 h-5" />
                <span>Cerrar sesión</span>
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 lg:ml-64">
        {/* Top Header */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
          <div className="px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              {/* Mobile menu button */}
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
              >
                <Menu className="w-5 h-5 text-gray-600" />
              </button>

              {/* Balance */}
              <div className="flex items-center gap-3">
                <div className="bg-gray-100 px-4 py-2 rounded-lg">
                  <span className="font-bold text-gray-900">{(user?.balance_ris || 0).toFixed(2)} RIS</span>
                </div>
                <Link
                  to="/recharge"
                  className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg font-medium transition-colors hidden sm:block"
                >
                  Recargar saldo
                </Link>
              </div>

              {/* Right side */}
              <div className="flex items-center gap-2">
                <Link to="/notifications" className="relative p-2 hover:bg-gray-100 rounded-lg">
                  <Bell className="w-5 h-5 text-gray-600" />
                  {unreadNotifications > 0 && (
                    <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full">
                      {unreadNotifications}
                    </span>
                  )}
                </Link>
                <Link to="/profile" className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg">
                  <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center">
                    <User className="w-4 h-4 text-orange-600" />
                  </div>
                  <span className="text-sm font-medium text-gray-700 hidden md:block">
                    {user?.name?.split(' ')[0]}
                  </span>
                </Link>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="p-4 sm:p-6 lg:p-8">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column - Main Actions */}
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
                          className="w-full px-4 py-4 text-2xl font-semibold rounded-xl border border-gray-200 focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                        />
                        <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2 bg-gray-100 px-3 py-1.5 rounded-lg">
                          <span className="text-lg">🇧🇷</span>
                          <span className="font-medium text-gray-700">RIS</span>
                        </div>
                      </div>
                    </div>

                    {/* Result */}
                    <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm text-gray-500 mb-1">Beneficiario recibe</p>
                          <p className="text-3xl font-bold text-green-600">{calculatedVes} <span className="text-lg font-normal text-gray-500">Bs</span></p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm text-gray-500">Tasa de cambio</p>
                          <p className="text-sm font-medium text-gray-700">1 RIS = {rates.ris_to_ves.toFixed(2)} Bs</p>
                        </div>
                      </div>
                    </div>

                    {/* Payment Methods */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-3">
                        Pagar con
                      </label>
                      <div className="grid grid-cols-2 gap-3">
                        <button className="flex flex-col items-center gap-2 p-4 border-2 border-orange-500 bg-orange-50 rounded-xl">
                          <Wallet className="w-6 h-6 text-orange-500" />
                          <span className="text-sm font-medium text-gray-700">Saldo RIS</span>
                        </button>
                        <button className="flex flex-col items-center gap-2 p-4 border border-gray-200 rounded-xl hover:border-gray-300 transition-colors">
                          <CreditCard className="w-6 h-6 text-gray-400" />
                          <span className="text-sm font-medium text-gray-500">PIX</span>
                        </button>
                      </div>
                    </div>

                    {/* Send Button */}
                    <Link
                      to="/send"
                      className="w-full bg-orange-500 hover:bg-orange-600 text-white py-4 rounded-xl font-semibold text-center block transition-colors"
                    >
                      Enviar remesa
                    </Link>
                  </div>
                </div>

                {/* Promotional Card */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <h3 className="text-xl font-bold text-gray-900 mb-2">¡Recarga tu saldo!</h3>
                  <p className="text-gray-600 mb-4">
                    Recarga tu saldo de forma rápida, confiable y segura usando PIX o Bolívares.
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

              {/* Right Column - Quick Info */}
              <div className="space-y-6">
                {/* Quick Rates */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <h3 className="font-semibold text-gray-900 mb-4">Tasas rápidas</h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">🇧🇷</span>
                        <span className="text-sm text-gray-600">1 RIS</span>
                        <ArrowRight className="w-4 h-4 text-gray-400" />
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-bold text-gray-900">🇻🇪 {rates.ris_to_ves.toFixed(2)} Bs</span>
                        <Link to="/send" className="px-3 py-1 bg-orange-500 hover:bg-orange-600 text-white text-sm rounded-lg transition-colors">
                          Enviar
                        </Link>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-sm text-gray-500">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span>Tasas actualizadas en tiempo real</span>
                  </div>
                </div>

                {/* User Profile Card */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <div className="flex items-center gap-4 mb-4">
                    <div className="w-14 h-14 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center text-white text-xl font-bold">
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
                    <Link
                      to="/verification"
                      className="block w-full text-center bg-amber-50 text-amber-700 px-3 py-2 rounded-lg text-sm font-medium hover:bg-amber-100 transition-colors"
                    >
                      Verificar mi cuenta
                    </Link>
                  )}
                </div>

                {/* WhatsApp Support */}
                <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-2xl p-5 text-white">
                  <div className="flex items-center gap-3 mb-3">
                    <MessageCircle className="w-6 h-6" />
                    <h3 className="font-semibold">¿Necesitas ayuda?</h3>
                  </div>
                  <p className="text-green-100 text-sm mb-4">
                    Contáctanos por WhatsApp para soporte inmediato.
                  </p>
                  <a
                    href="https://wa.me/5511999999999"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 bg-white text-green-600 py-2.5 rounded-xl font-medium hover:bg-green-50 transition-colors"
                  >
                    <MessageCircle className="w-4 h-4" />
                    Solicitar información
                  </a>
                </div>

                {/* Recent Activity Preview */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-900">Actividad reciente</h3>
                    <Link to="/history" className="text-sm text-orange-500 hover:text-orange-600 font-medium">
                      Ver todo
                    </Link>
                  </div>
                  <div className="text-center py-6 text-gray-400">
                    <History className="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Sin transacciones recientes</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
