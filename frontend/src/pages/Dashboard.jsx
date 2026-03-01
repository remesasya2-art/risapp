import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  LayoutDashboard, Wallet, ArrowLeftRight, History, 
  LogOut, Plus, ArrowUpRight, TrendingUp, TrendingDown,
  Copy, CreditCard, Bell, ChevronRight
} from 'lucide-react';
import api from '../utils/api';
import toast from 'react-hot-toast';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [showWelcome, setShowWelcome] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShowWelcome(false), 3000);
    return () => clearTimeout(timer);
  }, []);

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
    <div className="min-h-screen bg-[#0a0a0f] flex" style={{fontFamily: 'Inter, -apple-system, sans-serif'}} data-testid="dashboard-page">
      
      {/* Sidebar */}
      <aside className="w-[200px] bg-[#0f0f15] border-r border-[#1a1a24] flex flex-col fixed h-full">
        {/* Logo */}
        <div className="p-6">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 bg-[#6366f1] rounded-xl flex items-center justify-center">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
            <span className="text-white font-semibold text-lg">RIS</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3">
          <ul className="space-y-1">
            {menuItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                    isActive(item.path)
                      ? 'bg-[#6366f1]/10 text-[#6366f1]'
                      : 'text-[#6b7280] hover:text-white hover:bg-[#1a1a24]'
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  <span className="text-sm font-medium">{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-[#1a1a24]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] flex items-center justify-center text-white font-semibold">
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium truncate">{user?.name || 'Usuario'}</p>
              <p className="text-[#6b7280] text-xs truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-[#6b7280] hover:text-red-400 text-sm transition-colors w-full"
            data-testid="logout-button"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 ml-[200px] p-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold text-white mb-1">
              Welcome back, {user?.name?.split(' ')[0] || 'User'}
            </h1>
            <p className="text-[#6b7280] text-sm">Here's what's happening with your wallet.</p>
          </div>

          {/* Welcome Toast */}
          {showWelcome && (
            <div className="bg-[#10b981]/10 border border-[#10b981]/20 rounded-xl px-4 py-3 flex items-center gap-3">
              <div className="w-6 h-6 bg-[#10b981] rounded-full flex items-center justify-center">
                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <span className="text-[#10b981] text-sm font-medium">Welcome back!</span>
            </div>
          )}
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-3 gap-6 mb-6">
          {/* Balance Card */}
          <div className="col-span-2 bg-[#12121a] rounded-2xl p-6 border border-[#1a1a24]" data-testid="balance-card">
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="text-[#6b7280] text-sm mb-1">Total Balance</p>
                <p className="text-4xl font-bold text-white" style={{fontFamily: 'monospace'}}>
                  ${(user?.balance_ris || 0).toFixed(2)}
                </p>
              </div>
              <button className="p-3 bg-[#1a1a24] rounded-xl hover:bg-[#252530] transition-colors">
                <Copy className="w-5 h-5 text-[#6b7280]" />
              </button>
            </div>

            <div className="flex gap-3">
              <Link
                to="/recharge"
                className="flex items-center gap-2 bg-[#6366f1] hover:bg-[#5558e3] text-white px-5 py-3 rounded-xl font-medium transition-colors"
                data-testid="recharge-button"
              >
                <Plus className="w-5 h-5" />
                Add Money
              </Link>
              <Link
                to="/send"
                className="flex items-center gap-2 bg-[#1a1a24] hover:bg-[#252530] text-white px-5 py-3 rounded-xl font-medium transition-colors border border-[#2a2a34]"
                data-testid="send-button"
              >
                <ArrowUpRight className="w-5 h-5" />
                Send Money
              </Link>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="space-y-4">
            {/* Income */}
            <div className="bg-[#12121a] rounded-2xl p-5 border border-[#1a1a24]">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-[#10b981]/10 rounded-xl flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-[#10b981]" />
                </div>
                <span className="text-[#6b7280] text-sm">Income (30d)</span>
              </div>
              <p className="text-2xl font-bold text-white" style={{fontFamily: 'monospace'}}>$0.00</p>
            </div>

            {/* Spent */}
            <div className="bg-[#12121a] rounded-2xl p-5 border border-[#1a1a24]">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-[#ef4444]/10 rounded-xl flex items-center justify-center">
                  <TrendingDown className="w-5 h-5 text-[#ef4444]" />
                </div>
                <span className="text-[#6b7280] text-sm">Spent (30d)</span>
              </div>
              <p className="text-2xl font-bold text-white" style={{fontFamily: 'monospace'}}>$0.00</p>
            </div>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-2 gap-6">
          {/* Activity Overview */}
          <div className="bg-[#12121a] rounded-2xl p-6 border border-[#1a1a24]">
            <h2 className="text-lg font-semibold text-white mb-6">Activity Overview</h2>
            <div className="flex flex-col items-center justify-center py-12 text-[#6b7280]">
              <p className="text-sm">No activity data yet. Start by adding funds!</p>
            </div>
          </div>

          {/* Recent Transactions */}
          <div className="bg-[#12121a] rounded-2xl p-6 border border-[#1a1a24]">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Recent Transactions</h2>
              <Link to="/history" className="flex items-center gap-1 text-[#6b7280] hover:text-white text-sm transition-colors">
                View All
                <ChevronRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-[#6b7280] text-sm mb-3">No transactions yet.</p>
              <Link to="/recharge" className="text-[#6366f1] hover:text-[#8b5cf6] text-sm font-medium transition-colors">
                Add funds to get started
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
