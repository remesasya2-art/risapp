import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowUpRight, ArrowDownLeft, History, User, Settings, 
  Shield, TrendingUp, LogOut, Bell, Menu, X, ChevronRight,
  Wallet, CreditCard, Clock, CheckCircle, AlertCircle
} from 'lucide-react';
import api from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [showMenu, setShowMenu] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [calcAmount, setCalcAmount] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [notifRes, txRes] = await Promise.all([
        api.get('/notifications/unread-count').catch(() => ({ data: { count: 0 } })),
        api.get('/transactions').catch(() => ({ data: [] }))
      ]);
      setUnreadNotifications(notifRes.data.count || 0);
      setRecentTransactions((txRes.data || []).slice(0, 3));
    } catch (error) {
      console.error('Error loading data:', error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const calculatedVes = calcAmount ? (parseFloat(calcAmount) * rates.ris_to_ves).toFixed(2) : '0.00';

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'pending': return <Clock className="w-4 h-4 text-amber-500" />;
      default: return <AlertCircle className="w-4 h-4 text-red-500" />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center shadow-lg shadow-blue-600/20">
                <Wallet className="w-5 h-5 text-white" />
              </div>
              <div className="hidden sm:block">
                <h1 className="font-bold text-slate-900">RIS</h1>
                <p className="text-xs text-slate-500">Remesas Seguras</p>
              </div>
            </div>

            {/* Desktop Nav */}
            <nav className="hidden lg:flex items-center gap-1">
              <Link to="/send" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                Enviar
              </Link>
              <Link to="/recharge" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                Recargar
              </Link>
              <Link to="/history" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                Historial
              </Link>
              {(user?.role === 'admin' || user?.role === 'super_admin') && (
                <Link to="/admin" className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                  Admin
                </Link>
              )}
            </nav>

            {/* Right Actions */}
            <div className="flex items-center gap-2">
              <Link to="/notifications" className="relative p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
                <Bell className="w-5 h-5" />
                {unreadNotifications > 0 && (
                  <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full font-medium">
                    {unreadNotifications > 9 ? '9+' : unreadNotifications}
                  </span>
                )}
              </Link>
              
              <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-slate-200">
                <Link to="/profile" className="flex items-center gap-2 px-3 py-2 hover:bg-slate-100 rounded-lg transition-colors">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-sm font-medium">
                    {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                  </div>
                  <span className="text-sm font-medium text-slate-700 hidden md:block">{user?.name?.split(' ')[0]}</span>
                </Link>
                <button onClick={handleLogout} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                  <LogOut className="w-5 h-5" />
                </button>
              </div>

              <button onClick={() => setShowMenu(!showMenu)} className="lg:hidden p-2 text-slate-500 hover:bg-slate-100 rounded-lg">
                {showMenu ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        {showMenu && (
          <div className="lg:hidden border-t border-slate-200 bg-white">
            <div className="p-4 space-y-1">
              <Link to="/send" onClick={() => setShowMenu(false)} className="flex items-center gap-3 px-4 py-3 text-slate-700 hover:bg-slate-50 rounded-xl">
                <ArrowUpRight className="w-5 h-5 text-blue-500" />
                <span className="font-medium">Enviar a Venezuela</span>
              </Link>
              <Link to="/recharge" onClick={() => setShowMenu(false)} className="flex items-center gap-3 px-4 py-3 text-slate-700 hover:bg-slate-50 rounded-xl">
                <ArrowDownLeft className="w-5 h-5 text-green-500" />
                <span className="font-medium">Recargar saldo</span>
              </Link>
              <Link to="/history" onClick={() => setShowMenu(false)} className="flex items-center gap-3 px-4 py-3 text-slate-700 hover:bg-slate-50 rounded-xl">
                <History className="w-5 h-5 text-purple-500" />
                <span className="font-medium">Historial</span>
              </Link>
              <Link to="/profile" onClick={() => setShowMenu(false)} className="flex items-center gap-3 px-4 py-3 text-slate-700 hover:bg-slate-50 rounded-xl">
                <User className="w-5 h-5 text-orange-500" />
                <span className="font-medium">Mi perfil</span>
              </Link>
              {(user?.role === 'admin' || user?.role === 'super_admin') && (
                <Link to="/admin" onClick={() => setShowMenu(false)} className="flex items-center gap-3 px-4 py-3 text-slate-700 hover:bg-slate-50 rounded-xl">
                  <Settings className="w-5 h-5 text-slate-500" />
                  <span className="font-medium">Administración</span>
                </Link>
              )}
              <button onClick={handleLogout} className="w-full flex items-center gap-3 px-4 py-3 text-red-600 hover:bg-red-50 rounded-xl">
                <LogOut className="w-5 h-5" />
                <span className="font-medium">Cerrar sesión</span>
              </button>
            </div>
          </div>
        )}
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 lg:py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content - Left Column */}
          <div className="lg:col-span-2 space-y-6">
            {/* Balance Card */}
            <div className="bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 rounded-2xl p-6 text-white shadow-xl shadow-blue-600/20">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-blue-200 text-sm font-medium">Balance disponible</p>
                  <h2 className="text-4xl lg:text-5xl font-bold mt-1 tracking-tight">
                    {(user?.balance_ris || 0).toFixed(2)}
                    <span className="text-2xl lg:text-3xl ml-2 font-normal text-blue-200">RIS</span>
                  </h2>
                  <div className="flex items-center gap-2 mt-3">
                    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-white/10 rounded-full backdrop-blur-sm">
                      <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                      <span className="text-xs font-medium">1 RIS = {rates.ris_to_ves.toFixed(2)} VES</span>
                    </div>
                  </div>
                </div>
                <div className="w-14 h-14 rounded-2xl bg-white/10 backdrop-blur-sm flex items-center justify-center">
                  <Wallet className="w-7 h-7" />
                </div>
              </div>
              
              {/* Quick Actions */}
              <div className="grid grid-cols-2 gap-3 mt-6">
                <Link to="/send" className="flex items-center justify-center gap-2 py-3 bg-white/10 hover:bg-white/20 backdrop-blur-sm rounded-xl transition-colors">
                  <ArrowUpRight className="w-5 h-5" />
                  <span className="font-medium">Enviar</span>
                </Link>
                <Link to="/recharge" className="flex items-center justify-center gap-2 py-3 bg-white hover:bg-blue-50 text-blue-700 rounded-xl transition-colors font-medium">
                  <ArrowDownLeft className="w-5 h-5" />
                  <span>Recargar</span>
                </Link>
              </div>
            </div>

            {/* Calculator */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <h3 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-blue-500" />
                Calculadora de cambio
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-5 gap-4 items-end">
                <div className="sm:col-span-2">
                  <label className="block text-sm text-slate-500 mb-2">Envías (RIS)</label>
                  <input
                    type="number"
                    value={calcAmount}
                    onChange={(e) => setCalcAmount(e.target.value)}
                    placeholder="0.00"
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg font-medium"
                  />
                </div>
                <div className="hidden sm:flex justify-center pb-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                    <ChevronRight className="w-5 h-5 text-blue-600" />
                  </div>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm text-slate-500 mb-2">Reciben (VES)</label>
                  <div className="w-full px-4 py-3 rounded-xl bg-green-50 border border-green-200 text-lg font-bold text-green-700">
                    {calculatedVes}
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Transactions */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-slate-900">Actividad reciente</h3>
                <Link to="/history" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
                  Ver todo
                </Link>
              </div>
              
              {recentTransactions.length === 0 ? (
                <div className="text-center py-8">
                  <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-slate-100 flex items-center justify-center">
                    <History className="w-6 h-6 text-slate-400" />
                  </div>
                  <p className="text-slate-500 text-sm">No hay transacciones aún</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {recentTransactions.map((tx) => (
                    <div key={tx.transaction_id} className="flex items-center gap-3 p-3 hover:bg-slate-50 rounded-xl transition-colors">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                        tx.type === 'withdrawal' ? 'bg-blue-100' : 'bg-green-100'
                      }`}>
                        {tx.type === 'withdrawal' ? (
                          <ArrowUpRight className="w-5 h-5 text-blue-600" />
                        ) : (
                          <ArrowDownLeft className="w-5 h-5 text-green-600" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900 text-sm">
                          {tx.type === 'withdrawal' ? 'Envío a Venezuela' : 'Recarga'}
                        </p>
                        <p className="text-xs text-slate-500">
                          {new Date(tx.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className={`font-semibold text-sm ${tx.type === 'withdrawal' ? 'text-slate-900' : 'text-green-600'}`}>
                          {tx.type === 'withdrawal' ? '-' : '+'}{tx.amount_input?.toFixed(2)} RIS
                        </p>
                        <div className="flex items-center justify-end gap-1 mt-0.5">
                          {getStatusIcon(tx.status)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar - Right Column */}
          <div className="space-y-6">
            {/* KYC Status */}
            {user?.verification_status !== 'verified' && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
                    <Shield className="w-5 h-5 text-amber-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-amber-800 text-sm">Verificación pendiente</h3>
                    <p className="text-xs text-amber-600">Completa tu KYC</p>
                  </div>
                </div>
                <p className="text-sm text-amber-700 mb-3">
                  Verifica tu identidad para acceder a todas las funciones.
                </p>
                <Link to="/verification" className="block w-full py-2.5 bg-amber-500 hover:bg-amber-600 text-white text-center rounded-xl text-sm font-medium transition-colors">
                  Verificar ahora
                </Link>
              </div>
            )}

            {/* Quick Links */}
            <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
              <h3 className="font-semibold text-slate-900 mb-4">Accesos rápidos</h3>
              <div className="space-y-2">
                <Link to="/send" className="flex items-center justify-between p-3 hover:bg-slate-50 rounded-xl transition-colors group">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center">
                      <ArrowUpRight className="w-4 h-4 text-blue-600" />
                    </div>
                    <span className="font-medium text-slate-700 text-sm">Enviar dinero</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" />
                </Link>
                <Link to="/recharge" className="flex items-center justify-between p-3 hover:bg-slate-50 rounded-xl transition-colors group">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-green-100 flex items-center justify-center">
                      <CreditCard className="w-4 h-4 text-green-600" />
                    </div>
                    <span className="font-medium text-slate-700 text-sm">Recargar con PIX</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-green-500 transition-colors" />
                </Link>
                <Link to="/profile" className="flex items-center justify-between p-3 hover:bg-slate-50 rounded-xl transition-colors group">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-orange-100 flex items-center justify-center">
                      <User className="w-4 h-4 text-orange-600" />
                    </div>
                    <span className="font-medium text-slate-700 text-sm">Mi perfil</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-orange-500 transition-colors" />
                </Link>
              </div>
            </div>

            {/* Exchange Rate Info */}
            <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-5 text-white">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-5 h-5 text-green-400" />
                <span className="font-semibold">Tasa de cambio</span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">RIS → VES</span>
                  <span className="font-mono font-medium">{rates.ris_to_ves.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">VES → RIS</span>
                  <span className="font-mono font-medium">{rates.ves_to_ris.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">BRL → RIS</span>
                  <span className="font-mono font-medium">{rates.ris_to_brl?.toFixed(2) || '1.00'}</span>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-slate-700">
                <p className="text-xs text-slate-400">Actualizado en tiempo real</p>
              </div>
            </div>

            {/* Admin Panel Link */}
            {(user?.role === 'admin' || user?.role === 'super_admin') && (
              <Link to="/admin" className="block bg-white rounded-2xl p-5 shadow-sm border border-slate-200 hover:border-blue-300 transition-colors group">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-slate-100 group-hover:bg-blue-100 flex items-center justify-center transition-colors">
                    <Settings className="w-5 h-5 text-slate-600 group-hover:text-blue-600 transition-colors" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900 text-sm">Panel Admin</h3>
                    <p className="text-xs text-slate-500">Gestionar plataforma</p>
                  </div>
                </div>
              </Link>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
