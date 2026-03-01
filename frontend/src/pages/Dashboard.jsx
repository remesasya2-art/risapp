import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  LayoutDashboard, Wallet, ArrowLeftRight, History, 
  LogOut, Plus, ArrowUpRight, TrendingUp, TrendingDown,
  CreditCard, ChevronRight, Settings
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
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: Wallet, label: 'Wallet', path: '/recharge' },
    { icon: ArrowLeftRight, label: 'Transfer', path: '/send' },
    { icon: History, label: 'History', path: '/history' },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <div className="min-h-screen bg-[#09090b] flex" style={{fontFamily: 'Inter, -apple-system, sans-serif'}} data-testid="dashboard-page">
      
      {/* Sidebar */}
      <aside className="w-[220px] bg-[#0f0f12] border-r border-[#1f1f23] flex flex-col fixed h-full">
        {/* Logo */}
        <div className="p-5 border-b border-[#1f1f23]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-[#4f46e5] rounded-lg flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
            <span className="text-white font-semibold text-lg">RIS</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3">
          <ul className="space-y-1">
            {menuItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                    isActive(item.path)
                      ? 'bg-[#4f46e5]/10 text-[#4f46e5]'
                      : 'text-[#71717a] hover:text-white hover:bg-[#1f1f23]'
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  <span className="text-sm font-medium">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User */}
        <div className="p-4 border-t border-[#1f1f23]">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-full bg-[#4f46e5] flex items-center justify-center text-white font-semibold text-sm">
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium truncate">{user?.name || 'User'}</p>
              <p className="text-[#71717a] text-xs truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-[#71717a] hover:text-[#ef4444] text-sm transition-colors w-full px-1"
            data-testid="logout-button"
          >
            <LogOut className="w-4 h-4" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 ml-[220px] p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-white mb-0.5">
              Welcome back, {user?.name?.split(' ')[0] || 'User'}
            </h1>
            <p className="text-[#71717a] text-sm">Here's what's happening with your wallet.</p>
          </div>
          <button className="w-9 h-9 bg-[#1f1f23] hover:bg-[#27272a] rounded-lg flex items-center justify-center transition-colors">
            <Settings className="w-5 h-5 text-[#71717a]" />
          </button>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-3 gap-5 mb-5">
          {/* Balance */}
          <div className="col-span-2 bg-[#0f0f12] rounded-xl p-5 border border-[#1f1f23]" data-testid="balance-card">
            <div className="flex items-center justify-between mb-5">
              <div>
                <p className="text-[#71717a] text-sm mb-1">Total Balance</p>
                <p className="text-3xl font-bold text-white">
                  ${(user?.balance_ris || 0).toFixed(2)}
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <Link
                to="/recharge"
                className="flex items-center gap-2 bg-[#4f46e5] hover:bg-[#4338ca] text-white px-4 py-2.5 rounded-lg font-medium text-sm transition-colors"
                data-testid="recharge-button"
              >
                <Plus className="w-4 h-4" />
                Add Money
              </Link>
              <Link
                to="/send"
                className="flex items-center gap-2 bg-[#1f1f23] hover:bg-[#27272a] text-white px-4 py-2.5 rounded-lg font-medium text-sm transition-colors border border-[#27272a]"
                data-testid="send-button"
              >
                <ArrowUpRight className="w-4 h-4" />
                Send Money
              </Link>
            </div>
          </div>

          {/* Stats */}
          <div className="space-y-3">
            <div className="bg-[#0f0f12] rounded-xl p-4 border border-[#1f1f23]">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 bg-[#10b981]/10 rounded-lg flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-[#10b981]" />
                </div>
                <span className="text-[#71717a] text-sm">Income (30d)</span>
              </div>
              <p className="text-xl font-bold text-white">$0.00</p>
            </div>
            <div className="bg-[#0f0f12] rounded-xl p-4 border border-[#1f1f23]">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 bg-[#ef4444]/10 rounded-lg flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-[#ef4444]" />
                </div>
                <span className="text-[#71717a] text-sm">Spent (30d)</span>
              </div>
              <p className="text-xl font-bold text-white">$0.00</p>
            </div>
          </div>
        </div>

        {/* Bottom */}
        <div className="grid grid-cols-2 gap-5">
          <div className="bg-[#0f0f12] rounded-xl p-5 border border-[#1f1f23]">
            <h2 className="text-base font-semibold text-white mb-4">Activity Overview</h2>
            <div className="flex items-center justify-center py-10 text-[#71717a] text-sm">
              No activity data yet.
            </div>
          </div>
          <div className="bg-[#0f0f12] rounded-xl p-5 border border-[#1f1f23]">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white">Recent Transactions</h2>
              <Link to="/history" className="flex items-center gap-1 text-[#71717a] hover:text-white text-sm transition-colors">
                View All
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-[#71717a] text-sm mb-2">No transactions yet.</p>
              <Link to="/recharge" className="text-[#4f46e5] hover:underline text-sm font-medium">
                Add funds to get started
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
