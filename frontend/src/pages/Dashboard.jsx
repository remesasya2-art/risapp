import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  LayoutDashboard, Wallet, ArrowLeftRight, History, 
  LogOut, Plus, ArrowUpRight, ArrowDownLeft, TrendingUp, TrendingDown,
  ChevronRight, Settings, User, HelpCircle, Menu, X, Clock, CheckCircle, XCircle, Eye, Download
} from 'lucide-react';
import NotificationBell from '../components/NotificationBell';
import SupportChat from '../components/SupportChat';
import api from '../utils/api';
import { fmt } from '../utils/format';

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { rates } = useRate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [loadingTransactions, setLoadingTransactions] = useState(true);
  
  // Modal para comprobantes
  const [showVoucherModal, setShowVoucherModal] = useState(false);
  const [selectedVoucher, setSelectedVoucher] = useState(null);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (!mobile) setSidebarOpen(false);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Load recent transactions
  useEffect(() => {
    const loadRecentTransactions = async () => {
      try {
        const response = await api.get('/transactions');
        // Backend may return {transactions: [...]} or an array directly
        const list = Array.isArray(response.data)
          ? response.data
          : (response.data?.transactions || response.data?.items || []);
        setRecentTransactions(list.slice(0, 5));
      } catch (error) {
        console.error('Error loading transactions:', error);
      } finally {
        setLoadingTransactions(false);
      }
    };
    loadRecentTransactions();
  }, []);

  // Close sidebar when navigating on mobile
  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [location.pathname]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Voucher functions
  const openVoucher = (tx) => {
    setSelectedVoucher(tx);
    setShowVoucherModal(true);
  };

  const downloadImage = (base64Data, fileName) => {
    const link = document.createElement('a');
    link.href = base64Data;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadAllImages = (images, txId) => {
    images.forEach((img, index) => {
      setTimeout(() => {
        downloadImage(img, `comprobante_${txId}_${index + 1}.png`);
      }, index * 300);
    });
  };

  // Transaction helper functions
  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle style={{ width: '16px', height: '16px', color: '#16a34a' }} />;
      case 'pending':
      case 'pending_manual_approval': return <Clock style={{ width: '16px', height: '16px', color: '#d97706' }} />;
      case 'rejected': return <XCircle style={{ width: '16px', height: '16px', color: '#dc2626' }} />;
      default: return <Clock style={{ width: '16px', height: '16px', color: '#9ca3af' }} />;
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'completed': return 'Completado';
      case 'pending': return 'Pendiente';
      case 'pending_manual_approval': return 'En revisión';
      case 'rejected': return 'Rechazado';
      default: return status;
    }
  };

  const getStatusStyle = (status) => {
    switch (status) {
      case 'completed': return { backgroundColor: '#dcfce7', color: '#16a34a' };
      case 'pending':
      case 'pending_manual_approval': return { backgroundColor: '#fef3c7', color: '#d97706' };
      case 'rejected': return { backgroundColor: '#fee2e2', color: '#dc2626' };
      default: return { backgroundColor: '#f3f4f6', color: '#6b7280' };
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-ES', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  };
  
  const formatDateFull = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-ES', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  };

  // Base menu items
  const baseMenuItems = [
    { icon: LayoutDashboard, label: 'Inicio', path: '/' },
    { icon: Wallet, label: 'Recargar', path: '/recharge' },
    { icon: ArrowLeftRight, label: 'Enviar', path: '/send' },
    { icon: History, label: 'Historial', path: '/history' },
    { icon: User, label: 'Perfil', path: '/profile' },
    { icon: HelpCircle, label: 'Soporte', path: '/support' },
  ];

  // Build menu based on user role
  const menuItems = [...baseMenuItems];
  
  // Add role-specific menu items
  if (user?.role === 'socio' || user?.role === 'socio_gestor') {
    menuItems.splice(4, 0, { icon: TrendingUp, label: 'Socio', path: '/partner' });
  }
  if (user?.role === 'socio_gestor') {
    menuItems.splice(5, 0, { icon: Settings, label: 'Gestor', path: '/gestor' });
  }
  if (user?.role === 'admin' || user?.role === 'super_admin') {
    menuItems.splice(4, 0, { icon: Settings, label: 'Admin', path: '/admin' });
    menuItems.splice(5, 0, { icon: TrendingUp, label: 'Contabilidad', path: '/admin/accounting' });
    menuItems.splice(6, 0, { icon: TrendingUp, label: 'Contabilidad v2 (Enterprise)', path: '/admin/accounting-v2' });
  }

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
                RI$ {fmt((user?.balance_ris || 0))}
              </p>
              <p style={{ fontSize: '14px', color: '#9ca3af', margin: 0 }}>
                Tasa actual: 1 RIS = {fmt(rates?.ris_to_ves) || '0.00'} Bs
              </p>
              {rates?.bcv_usd_ves && (
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: '8px',
                  marginTop: '10px', padding: '6px 12px',
                  backgroundColor: '#fef3c7', borderRadius: '999px',
                  border: '1px solid #fcd34d'
                }}
                data-testid="dashboard-bcv-usd"
                >
                  <span style={{ fontSize: '13px' }}>🇺🇸</span>
                  <span style={{ fontSize: '12px', color: '#92400e', fontWeight: '600' }}>BCV</span>
                  <span style={{ fontSize: '13px', color: '#78350f', fontWeight: '700' }}>
                    1 USD = Bs. {fmt(rates.bcv_usd_ves, 2)}
                  </span>
                </div>
              )}
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

        {/* Recent Transactions */}
        <div style={{ ...cardStyle, padding: isMobile ? '20px' : '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
            <h2 style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: '700', color: '#111827', margin: 0 }}>
              Transacciones Recientes
            </h2>
            <Link to="/history" style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#6366f1', textDecoration: 'none', fontSize: '14px', fontWeight: '500' }}>
              Ver todo
              <ChevronRight style={{ width: '16px', height: '16px' }} />
            </Link>
          </div>
          
          {loadingTransactions ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 0' }}>
              <div style={{ width: '32px', height: '32px', border: '3px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : recentTransactions.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 0' }}>
              <p style={{ color: '#9ca3af', fontSize: '14px', margin: '0 0 12px 0', textAlign: 'center' }}>No hay transacciones aún.</p>
              <Link to="/recharge" style={{ color: '#6366f1', textDecoration: 'none', fontSize: '14px', fontWeight: '500' }}>
                Recarga saldo para comenzar
              </Link>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {recentTransactions.map((tx) => (
                <div 
                  key={tx.transaction_id} 
                  style={{ 
                    padding: isMobile ? '14px' : '16px', 
                    backgroundColor: '#f9fafb', 
                    borderRadius: '14px',
                    border: '1px solid #f3f4f6'
                  }}
                  data-testid={`recent-tx-${tx.transaction_id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                    {/* Icon */}
                    <div style={{
                      width: isMobile ? '44px' : '48px', 
                      height: isMobile ? '44px' : '48px', 
                      borderRadius: '12px', 
                      flexShrink: 0,
                      backgroundColor: tx.type === 'withdrawal' ? '#dbeafe' : '#dcfce7',
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center'
                    }}>
                      {tx.type === 'withdrawal' ? (
                        <ArrowUpRight style={{ width: '22px', height: '22px', color: '#2563eb' }} />
                      ) : (
                        <ArrowDownLeft style={{ width: '22px', height: '22px', color: '#16a34a' }} />
                      )}
                    </div>
                    
                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                        <div>
                          <p style={{ fontSize: isMobile ? '14px' : '15px', fontWeight: '600', color: '#111827', margin: 0 }}>
                            {tx.type === 'withdrawal' ? 'Envío a Venezuela' : 'Recarga'}
                          </p>
                          <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{formatDate(tx.created_at)}</p>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <p style={{ fontSize: isMobile ? '15px' : '16px', fontWeight: '700', margin: 0, color: tx.type === 'withdrawal' ? '#dc2626' : '#16a34a' }}>
                            {tx.type === 'withdrawal' ? '-' : '+'}{fmt(tx.amount_input)} RIS
                          </p>
                          {tx.type === 'withdrawal' && tx.amount_output && (
                            <p style={{ fontSize: '12px', color: '#374151', margin: '2px 0 0 0', fontWeight: '600' }}>
                              {fmt(tx.amount_output)} VES
                              {rates?.bcv_usd_ves && (
                                <span style={{ color: '#16a34a' }}> = $ {fmt(tx.amount_output / rates.bcv_usd_ves, 2)} BCV</span>
                              )}
                            </p>
                          )}
                        </div>
                      </div>
                      
                      {/* Beneficiary info for withdrawals */}
                      {tx.type === 'withdrawal' && tx.beneficiary_data && (
                        <div style={{ marginTop: '10px', padding: '10px', backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
                          <p style={{ fontSize: '13px', fontWeight: '500', color: '#374151', margin: 0 }}>{tx.beneficiary_data.full_name}</p>
                          <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>
                            {tx.beneficiary_data.bank} • {tx.beneficiary_data.phone || tx.beneficiary_data.account_number}
                          </p>
                        </div>
                      )}
                      
                      {/* Status badge */}
                      <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        <div style={{
                          display: 'inline-flex', 
                          alignItems: 'center', 
                          gap: '5px', 
                          padding: '4px 10px',
                          borderRadius: '9999px', 
                          fontSize: '12px', 
                          fontWeight: '500', 
                          ...getStatusStyle(tx.status)
                        }}>
                          {getStatusIcon(tx.status)}
                          {getStatusText(tx.status)}
                        </div>
                        
                        {/* Botón para ver comprobante(s) */}
                        {tx.type === 'withdrawal' && tx.status === 'completed' && (tx.proof_images?.length > 0 || tx.proof_image) && (
                          <button
                            onClick={() => openVoucher(tx)}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '4px 10px',
                              borderRadius: '9999px', fontSize: '12px', fontWeight: '500', cursor: 'pointer',
                              backgroundColor: '#e0f2fe', color: '#0369a1', border: 'none'
                            }}
                            data-testid={`view-voucher-${tx.transaction_id}`}
                          >
                            <Eye style={{ width: '14px', height: '14px' }} />
                            Ver comprobante
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Modal para ver comprobante(s) */}
      {showVoucherModal && selectedVoucher && (
        <div 
          style={{ 
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', 
            display: 'flex', alignItems: 'center', justifyContent: 'center', 
            padding: '16px', zIndex: 50 
          }}
          onClick={() => setShowVoucherModal(false)}
        >
          <div 
            style={{ 
              backgroundColor: '#ffffff', borderRadius: '24px', padding: '24px', 
              width: '100%', maxWidth: '550px', maxHeight: '90vh', overflow: 'auto' 
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>
                Comprobante{(selectedVoucher.proof_images?.length || 1) > 1 ? 's' : ''} de Pago
              </h3>
              <button 
                onClick={() => setShowVoucherModal(false)}
                style={{ 
                  width: '36px', height: '36px', borderRadius: '10px', 
                  border: 'none', backgroundColor: '#f3f4f6', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}
              >
                <X style={{ width: '20px', height: '20px', color: '#6b7280' }} />
              </button>
            </div>

            {/* Información de la transacción */}
            <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '14px', marginBottom: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Monto enviado</p>
                  <p style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>{fmt(selectedVoucher.amount_input)} RIS</p>
                </div>
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Monto recibido</p>
                  <p style={{ fontSize: '18px', fontWeight: '700', color: '#16a34a', margin: 0 }}>
                    {fmt(selectedVoucher.amount_output)} VES
                    {rates?.bcv_usd_ves && (
                      <span style={{ fontSize: '14px', marginLeft: 6 }}>= $ {fmt(selectedVoucher.amount_output / rates.bcv_usd_ves, 2)} BCV</span>
                    )}
                  </p>
                </div>
              </div>
              {selectedVoucher.beneficiary_data && (
                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #e5e7eb' }}>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Beneficiario</p>
                  <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', margin: 0 }}>{selectedVoucher.beneficiary_data.full_name}</p>
                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '2px 0 0 0' }}>{selectedVoucher.beneficiary_data.bank}</p>
                </div>
              )}
              <div style={{ marginTop: '12px' }}>
                <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Fecha de proceso</p>
                <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>{formatDateFull(selectedVoucher.completed_at || selectedVoucher.created_at)}</p>
              </div>
            </div>

            {/* Imágenes del comprobante */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', margin: 0 }}>
                  📷 {(selectedVoucher.proof_images?.length || (selectedVoucher.proof_image ? 1 : 0))} Imagen{(selectedVoucher.proof_images?.length || 1) > 1 ? 'es' : ''}
                </p>
                {(selectedVoucher.proof_images?.length > 0 || selectedVoucher.proof_image) && (
                  <button
                    onClick={() => {
                      const images = selectedVoucher.proof_images?.length > 0 
                        ? selectedVoucher.proof_images 
                        : [selectedVoucher.proof_image];
                      const txId = selectedVoucher.display_id || selectedVoucher.transaction_id?.slice(0, 8);
                      downloadAllImages(images, txId);
                    }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '6px',
                      padding: '8px 14px', borderRadius: '10px', border: 'none',
                      backgroundColor: '#6366f1', color: 'white', cursor: 'pointer',
                      fontSize: '13px', fontWeight: '500'
                    }}
                  >
                    <Download style={{ width: '16px', height: '16px' }} />
                    Descargar
                  </button>
                )}
              </div>
              
              {/* Grid de imágenes */}
              <div style={{ display: 'grid', gridTemplateColumns: (selectedVoucher.proof_images?.length || 1) > 1 ? '1fr 1fr' : '1fr', gap: '12px' }}>
                {selectedVoucher.proof_images?.length > 0 ? (
                  selectedVoucher.proof_images.map((img, index) => (
                    <div key={index} style={{ position: 'relative' }}>
                      <img 
                        src={img} 
                        alt={`Comprobante ${index + 1}`}
                        style={{ 
                          width: '100%', borderRadius: '12px', 
                          border: '1px solid #e5e7eb', cursor: 'pointer' 
                        }}
                        onClick={() => window.open(img, '_blank')}
                      />
                    </div>
                  ))
                ) : selectedVoucher.proof_image ? (
                  <div style={{ position: 'relative' }}>
                    <img 
                      src={selectedVoucher.proof_image} 
                      alt="Comprobante"
                      style={{ 
                        width: '100%', borderRadius: '12px', 
                        border: '1px solid #e5e7eb', cursor: 'pointer' 
                      }}
                      onClick={() => window.open(selectedVoucher.proof_image, '_blank')}
                    />
                  </div>
                ) : (
                  <p style={{ color: '#9ca3af', fontSize: '14px', textAlign: 'center', padding: '20px' }}>
                    No hay imágenes disponibles
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Support Chat */}
      <SupportChat />

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
