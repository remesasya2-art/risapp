import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  LayoutDashboard, Wallet, ArrowLeftRight, History, 
  LogOut, Plus, ArrowUpRight, TrendingUp, TrendingDown,
  ChevronRight, Settings, User, HelpCircle
} from 'lucide-react';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const menuItems = [
    { icon: LayoutDashboard, label: 'Inicio', path: '/' },
    { icon: Wallet, label: 'Recargar', path: '/recharge' },
    { icon: ArrowLeftRight, label: 'Enviar', path: '/send' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: User, label: 'Perfil', path: '/profile' },
    { icon: HelpCircle, label: 'Soporte', path: '/support' },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <div 
      className="min-h-screen bg-[#f8f9fc] flex"
      style={{ fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' }}
      data-testid="dashboard-page"
    >
      {/* Sidebar */}
      <aside className="w-[260px] bg-white border-r border-gray-100 flex flex-col fixed h-full">
        {/* Logo */}
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <img 
              src="/logo-ris.jpeg" 
              alt="RIS" 
              className="h-10 w-auto"
              style={{ borderRadius: '10px' }}
            />
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            {menuItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-3 transition-all ${
                    isActive(item.path)
                      ? 'bg-[#6366f1] text-white font-semibold'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                  style={{ borderRadius: '12px' }}
                >
                  <item.icon className="w-5 h-5" strokeWidth={1.5} />
                  <span className="text-sm">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User */}
        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-3 px-3 py-2 mb-3">
            <div 
              className="w-10 h-10 bg-[#6366f1] flex items-center justify-center text-white font-semibold text-sm"
              style={{ borderRadius: '12px' }}
            >
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-gray-900 text-sm font-medium truncate">{user?.name || 'Usuario'}</p>
              <p className="text-gray-400 text-xs truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-3 text-gray-500 hover:text-red-500 hover:bg-red-50 transition-all w-full"
            style={{ borderRadius: '12px' }}
            data-testid="logout-button"
          >
            <LogOut className="w-5 h-5" strokeWidth={1.5} />
            <span className="text-sm">Cerrar sesión</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 ml-[260px] p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-1">
              ¡Bienvenido, {user?.name?.split(' ')[0] || 'Usuario'}!
            </h1>
            <p className="text-gray-400 text-base">Aquí está el resumen de tu billetera.</p>
          </div>
          <button 
            className="w-10 h-10 bg-white border border-gray-200 hover:bg-gray-50 flex items-center justify-center transition-all"
            style={{ borderRadius: '12px' }}
          >
            <Settings className="w-5 h-5 text-gray-500" strokeWidth={1.5} />
          </button>
        </div>

        {/* Balance Card */}
        <div 
          className="p-8 mb-6"
          style={{ borderRadius: '20px', border: '1px solid #e5e7eb', backgroundColor: '#ffffff' }}
          data-testid="balance-card"
        >
          <div className="flex items-start justify-between mb-6">
            <div>
              <p className="text-gray-400 text-sm mb-2">Saldo Total</p>
              <p className="text-5xl font-bold text-gray-900">
                ${(user?.balance_ris || 0).toFixed(2)}
              </p>
              <p className="text-gray-400 text-sm mt-2">
                Tasa actual: 1 RIS = {rates?.ris_to_ves?.toFixed(2) || '0.00'} Bs
              </p>
            </div>
            <div className="flex gap-3">
              <div className="bg-green-50 p-4" style={{ borderRadius: '14px' }}>
                <div className="flex items-center gap-2 mb-1">
                  <TrendingUp className="w-4 h-4 text-green-500" strokeWidth={1.5} />
                  <span className="text-gray-500 text-xs">Ingresos (30d)</span>
                </div>
                <p className="text-lg font-bold text-gray-900">$0.00</p>
              </div>
              <div className="bg-red-50 p-4" style={{ borderRadius: '14px' }}>
                <div className="flex items-center gap-2 mb-1">
                  <TrendingDown className="w-4 h-4 text-red-500" strokeWidth={1.5} />
                  <span className="text-gray-500 text-xs">Gastos (30d)</span>
                </div>
                <p className="text-lg font-bold text-gray-900">$0.00</p>
              </div>
            </div>
          </div>
          <div className="flex gap-4">
            <Link
              to="/recharge"
              className="flex items-center justify-center gap-2 bg-[#6366f1] hover:bg-[#5558e3] text-white px-8 font-semibold text-sm transition-all"
              style={{ borderRadius: '14px', height: '52px' }}
              data-testid="recharge-button"
            >
              <Plus className="w-5 h-5" strokeWidth={2} />
              Recargar Saldo
            </Link>
            <Link
              to="/send"
              className="flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-gray-700 px-8 font-semibold text-sm transition-all"
              style={{ borderRadius: '14px', height: '52px', border: '1px solid #d1d5db' }}
              data-testid="send-button"
            >
              <ArrowUpRight className="w-5 h-5" strokeWidth={2} />
              Enviar Dinero
            </Link>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-2 gap-6">
          {/* Activity */}
          <div 
            className="bg-white p-6"
            style={{ borderRadius: '20px', border: '1px solid #e5e7eb' }}
          >
            <h2 className="text-lg font-bold text-gray-900 mb-6">Resumen de Actividad</h2>
            <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
              No hay datos de actividad aún.
            </div>
          </div>

          {/* Recent Transactions */}
          <div 
            className="bg-white p-6"
            style={{ borderRadius: '20px', border: '1px solid #e5e7eb' }}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-gray-900">Transacciones Recientes</h2>
              <Link to="/history" className="flex items-center gap-1 text-[#6366f1] hover:underline text-sm font-medium">
                Ver todo
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-gray-400 text-sm mb-3">No hay transacciones aún.</p>
              <Link to="/recharge" className="text-[#6366f1] hover:underline text-sm font-medium">
                Recarga saldo para comenzar
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
