import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  LayoutDashboard, Wallet, ArrowLeftRight, History, 
  LogOut, Plus, ArrowUpRight, TrendingUp, TrendingDown,
  ChevronRight, Settings, User, HelpCircle, Menu, X
} from 'lucide-react';
import NotificationBell from '../components/NotificationBell';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (!mobile) setSidebarOpen(false);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Close sidebar when navigating on mobile
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [location.pathname]);

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

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e5e7eb',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
  };

  const buttonPrimaryStyle = {
    backgroundColor: '#6366f1',
    color: 'white',
    borderRadius: '14px',
    height: '52px',
    padding: '0 24px',
    fontWeight: '600',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    textDecoration: 'none',
    transition: 'all 0.2s',
    flex: isMobile ? 1 : 'none'
  };

  const buttonSecondaryStyle = {
    backgroundColor: '#ffffff',
    color: '#374151',
    borderRadius: '14px',
    height: '52px',
    padding: '0 24px',
    fontWeight: '600',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    textDecoration: 'none',
    border: '1px solid #d1d5db',
    transition: 'all 0.2s',
    flex: isMobile ? 1 : 'none'
  };

  return (
    <div 
      style={{ 
        minHeight: '100vh', 
        backgroundColor: '#f8f9fc', 
        display: 'flex',
        fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
      }}
      data-testid="dashboard-page"
    >
      {/* Mobile Overlay */}
      {isMobile && sidebarOpen && (
        <div 
          onClick={() => setSidebarOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            zIndex: 40,
            transition: 'opacity 0.3s'
          }}
        />
      )}

      {/* Sidebar */}
      <aside 
        style={{
          width: '260px',
          backgroundColor: '#ffffff',
          borderRight: '1px solid #f3f4f6',
          display: 'flex',
          flexDirection: 'column',
          position: 'fixed',
          height: '100%',
          zIndex: 50,
          transform: isMobile ? (sidebarOpen ? 'translateX(0)' : 'translateX(-100%)') : 'translateX(0)',
          transition: 'transform 0.3s ease-in-out'
        }}
      >
        {/* Logo */}
        <div style={{ padding: '24px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <img 
            src="/logo-ris.jpeg" 
            alt="RIS" 
            style={{ height: '40px', width: 'auto', borderRadius: '10px' }}
          />
          {isMobile && (
            <button
              onClick={() => setSidebarOpen(false)}
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                border: 'none',
                backgroundColor: '#f3f4f6',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '16px' }}>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {menuItems.map((item) => (
              <li key={item.path} style={{ marginBottom: '4px' }}>
                <Link
                  to={item.path}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    textDecoration: 'none',
                    transition: 'all 0.2s',
                    backgroundColor: isActive(item.path) ? '#6366f1' : 'transparent',
                    color: isActive(item.path) ? '#ffffff' : '#6b7280',
                    fontWeight: isActive(item.path) ? '600' : '400',
                    fontSize: '14px'
                  }}
                >
                  <item.icon style={{ width: '20px', height: '20px' }} strokeWidth={1.5} />
                  <span>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* User Section */}
        <div style={{ padding: '16px', borderTop: '1px solid #f3f4f6' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px', marginBottom: '12px' }}>
            <div 
              style={{
                width: '40px',
                height: '40px',
                backgroundColor: '#6366f1',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
                fontWeight: '600',
                fontSize: '14px'
              }}
            >
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ margin: 0, color: '#111827', fontSize: '14px', fontWeight: '500', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.name || 'Usuario'}
              </p>
              <p style={{ margin: 0, color: '#9ca3af', fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.email}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '12px 16px',
              width: '100%',
              backgroundColor: 'transparent',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              color: '#6b7280',
              fontSize: '14px',
              transition: 'all 0.2s'
            }}
            data-testid="logout-button"
          >
            <LogOut style={{ width: '20px', height: '20px' }} strokeWidth={1.5} />
            <span>Cerrar sesión</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main style={{ 
        flex: 1, 
        marginLeft: isMobile ? 0 : '260px', 
        padding: isMobile ? '16px' : '32px',
        paddingTop: isMobile ? '72px' : '32px'
      }}>
        {/* Mobile Header */}
        {isMobile && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            height: '56px',
            backgroundColor: '#ffffff',
            borderBottom: '1px solid #e5e7eb',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            zIndex: 30
          }}>
            <button
              onClick={() => setSidebarOpen(true)}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                border: 'none',
                backgroundColor: '#f3f4f6',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              data-testid="menu-button"
            >
              <Menu style={{ width: '22px', height: '22px', color: '#374151' }} />
            </button>
            <img src="/logo-ris.jpeg" alt="RIS" style={{ height: '32px', borderRadius: '8px' }} />
            <NotificationBell />
          </div>
        )}

        {/* Header - Desktop only */}
        {!isMobile && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px' }}>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>
                ¡Bienvenido, {user?.name?.split(' ')[0] || 'Usuario'}!
              </h1>
              <p style={{ fontSize: '16px', color: '#9ca3af', margin: 0 }}>
                Aquí está el resumen de tu billetera.
              </p>
            </div>
            <NotificationBell />
          </div>
        )}

        {/* Mobile greeting */}
        {isMobile && (
          <div style={{ marginBottom: '20px' }}>
            <h1 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: '0 0 4px 0' }}>
              ¡Hola, {user?.name?.split(' ')[0] || 'Usuario'}!
            </h1>
            <p style={{ fontSize: '14px', color: '#9ca3af', margin: 0 }}>
              Resumen de tu billetera
            </p>
          </div>
        )}

        {/* Balance Card */}
        <div style={{ ...cardStyle, padding: isMobile ? '20px' : '32px', marginBottom: '24px' }} data-testid="balance-card">
          <div style={{ 
            display: 'flex', 
            flexDirection: isMobile ? 'column' : 'row',
            alignItems: isMobile ? 'stretch' : 'flex-start', 
            justifyContent: 'space-between', 
            marginBottom: '24px',
            gap: isMobile ? '20px' : '0'
          }}>
            <div>
              <p style={{ fontSize: '14px', color: '#9ca3af', margin: '0 0 8px 0' }}>Saldo Total</p>
              <p style={{ fontSize: isMobile ? '36px' : '48px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0' }}>
                RI$ {(user?.balance_ris || 0).toFixed(2)}
              </p>
              <p style={{ fontSize: '14px', color: '#9ca3af', margin: 0 }}>
                Tasa actual: 1 RIS = {rates?.ris_to_ves?.toFixed(2) || '0.00'} Bs
              </p>
            </div>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <div style={{ backgroundColor: '#f0fdf4', padding: isMobile ? '12px 16px' : '16px', borderRadius: '14px', flex: isMobile ? 1 : 'none', minWidth: isMobile ? '45%' : 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <TrendingUp style={{ width: '16px', height: '16px', color: '#22c55e' }} strokeWidth={1.5} />
                  <span style={{ fontSize: '12px', color: '#6b7280' }}>Ingresos</span>
                </div>
                <p style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: '700', color: '#111827', margin: 0 }}>RI$ 0.00</p>
              </div>
              <div style={{ backgroundColor: '#fef2f2', padding: isMobile ? '12px 16px' : '16px', borderRadius: '14px', flex: isMobile ? 1 : 'none', minWidth: isMobile ? '45%' : 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <TrendingDown style={{ width: '16px', height: '16px', color: '#ef4444' }} strokeWidth={1.5} />
                  <span style={{ fontSize: '12px', color: '#6b7280' }}>Gastos</span>
                </div>
                <p style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: '700', color: '#111827', margin: 0 }}>RI$ 0.00</p>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <Link to="/recharge" style={buttonPrimaryStyle} data-testid="recharge-button">
              <Plus style={{ width: '20px', height: '20px' }} strokeWidth={2} />
              {isMobile ? 'Recargar' : 'Recargar Saldo'}
            </Link>
            <Link to="/send" style={buttonSecondaryStyle} data-testid="send-button">
              <ArrowUpRight style={{ width: '20px', height: '20px' }} strokeWidth={2} />
              {isMobile ? 'Enviar' : 'Enviar Dinero'}
            </Link>
          </div>
        </div>

        {/* Bottom Grid */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', 
          gap: isMobile ? '16px' : '24px' 
        }}>
          {/* Activity Summary */}
          <div style={{ ...cardStyle, padding: isMobile ? '20px' : '24px' }}>
            <h2 style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: '700', color: '#111827', margin: '0 0 24px 0' }}>
              Resumen de Actividad
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: isMobile ? '32px 0' : '48px 0', color: '#9ca3af', fontSize: '14px' }}>
              No hay datos de actividad aún.
            </div>
          </div>

          {/* Recent Transactions */}
          <div style={{ ...cardStyle, padding: isMobile ? '20px' : '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
              <h2 style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
                Transacciones Recientes
              </h2>
              <Link to="/history" style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#6366f1', textDecoration: 'none', fontSize: '14px', fontWeight: '500' }}>
                Ver todo
                <ChevronRight style={{ width: '16px', height: '16px' }} />
              </Link>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 0' }}>
              <p style={{ color: '#9ca3af', fontSize: '14px', margin: '0 0 12px 0', textAlign: 'center' }}>No hay transacciones aún.</p>
              <Link to="/recharge" style={{ color: '#6366f1', textDecoration: 'none', fontSize: '14px', fontWeight: '500' }}>
                Recarga saldo para comenzar
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
