import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  ArrowLeft, ArrowUpRight, ArrowDownLeft, Clock, CheckCircle, 
  XCircle, Filter, ChevronDown, Plus, Eye, X
} from 'lucide-react';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';

export default function History() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [showVoucherModal, setShowVoucherModal] = useState(false);
  const [selectedVoucher, setSelectedVoucher] = useState(null);

  useEffect(() => {
    loadTransactions();
  }, []);

  const loadTransactions = async () => {
    try {
      const response = await api.get('/transactions');
      setTransactions(response.data || []);
    } catch (error) {
      console.error('Error loading transactions:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredTransactions = transactions.filter(tx => {
    if (filter === 'all') return true;
    if (filter === 'withdrawals') return tx.type === 'withdrawal';
    if (filter === 'recharges') return tx.type === 'recharge';
    return true;
  });

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle style={{ width: '20px', height: '20px', color: '#16a34a' }} />;
      case 'pending':
      case 'pending_manual_approval': return <Clock style={{ width: '20px', height: '20px', color: '#d97706' }} />;
      case 'rejected': return <XCircle style={{ width: '20px', height: '20px', color: '#dc2626' }} />;
      default: return <Clock style={{ width: '20px', height: '20px', color: '#9ca3af' }} />;
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
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  };

  const pageStyle = {
    minHeight: '100vh',
    background: 'radial-gradient(ellipse at top left, #e8e0ff 0%, #f8f9fc 40%, #d4f0ff 100%)',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    border: '1px solid #e5e7eb'
  };

  const openVoucher = (tx) => {
    setSelectedVoucher(tx);
    setShowVoucherModal(true);
  };

  return (
    <div style={pageStyle} data-testid="history-page">
      <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button 
              onClick={() => navigate(-1)} 
              style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: 'rgba(255,255,255,0.8)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              data-testid="back-button"
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#111827', margin: 0 }}>Historial</h1>
              <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{filteredTransactions.length} transacciones</p>
            </div>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px',
              backgroundColor: 'rgba(255,255,255,0.8)', borderRadius: '12px', border: 'none',
              cursor: 'pointer', fontSize: '14px', fontWeight: '500', color: '#374151'
            }}
            data-testid="filter-button"
          >
            <Filter style={{ width: '16px', height: '16px' }} />
            Filtrar
            <ChevronDown style={{ width: '16px', height: '16px', transform: showFilters ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </button>
        </div>

        {/* Filters */}
        {showFilters && (
          <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
            {[
              { key: 'all', label: 'Todos' },
              { key: 'withdrawals', label: 'Envíos' },
              { key: 'recharges', label: 'Recargas' },
            ].map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  padding: '10px 20px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                  fontSize: '14px', fontWeight: '500', transition: 'all 0.2s',
                  backgroundColor: filter === f.key ? '#6366f1' : 'rgba(255,255,255,0.8)',
                  color: filter === f.key ? '#ffffff' : '#374151'
                }}
                data-testid={`filter-${f.key}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div style={{ ...cardStyle, padding: '64px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: '40px', height: '40px', border: '4px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
            <p style={{ color: '#6b7280', marginTop: '16px' }}>Cargando transacciones...</p>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div style={{ ...cardStyle, padding: '64px', textAlign: 'center' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '20px', backgroundColor: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
              <Clock style={{ width: '40px', height: '40px', color: '#d1d5db' }} />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#374151', margin: '0 0 8px 0' }}>Sin transacciones</h3>
            <p style={{ fontSize: '14px', color: '#6b7280', margin: '0 0 24px 0' }}>
              {filter !== 'all' ? 'Prueba cambiando el filtro' : 'Realiza tu primera operación para verla aquí'}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
              <Link to="/recharge" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 20px', backgroundColor: '#16a34a', color: '#ffffff', borderRadius: '12px', textDecoration: 'none', fontWeight: '500', fontSize: '14px' }}>
                <Plus style={{ width: '20px', height: '20px' }} /> Recargar saldo
              </Link>
              <Link to="/send" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 20px', backgroundColor: '#6366f1', color: '#ffffff', borderRadius: '12px', textDecoration: 'none', fontWeight: '500', fontSize: '14px' }}>
                <ArrowUpRight style={{ width: '20px', height: '20px' }} /> Enviar remesa
              </Link>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {filteredTransactions.map((tx) => (
              <div key={tx.transaction_id} style={{ ...cardStyle, padding: '20px' }} data-testid={`transaction-${tx.transaction_id}`}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                  <div style={{
                    width: '56px', height: '56px', borderRadius: '16px', flexShrink: 0,
                    backgroundColor: tx.type === 'withdrawal' ? '#dbeafe' : '#dcfce7',
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                  }}>
                    {tx.type === 'withdrawal' ? (
                      <ArrowUpRight style={{ width: '28px', height: '28px', color: '#2563eb' }} />
                    ) : (
                      <ArrowDownLeft style={{ width: '28px', height: '28px', color: '#16a34a' }} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                      <div>
                        <p style={{ fontSize: '16px', fontWeight: '600', color: '#111827', margin: 0 }}>
                          {tx.type === 'withdrawal' ? 'Envío a Venezuela' : 'Recarga'}
                        </p>
                        <p style={{ fontSize: '14px', color: '#6b7280', margin: '4px 0 0 0' }}>{formatDate(tx.created_at)}</p>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <p style={{ fontSize: '18px', fontWeight: '700', margin: 0, color: tx.type === 'withdrawal' ? '#dc2626' : '#16a34a' }}>
                          {tx.type === 'withdrawal' ? '-' : '+'}{tx.amount_input?.toFixed(2)} RIS
                        </p>
                        {tx.type === 'withdrawal' && tx.amount_output && (
                          <p style={{ fontSize: '14px', color: '#6b7280', margin: '2px 0 0 0' }}>{tx.amount_output.toFixed(2)} VES</p>
                        )}
                      </div>
                    </div>
                    {tx.type === 'withdrawal' && tx.beneficiary_data && (
                      <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#f8f9fa', borderRadius: '10px' }}>
                        <p style={{ fontSize: '14px', fontWeight: '500', color: '#374151', margin: 0 }}>{tx.beneficiary_data.full_name}</p>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0 0' }}>{tx.beneficiary_data.bank}</p>
                      </div>
                    )}
                    <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <div style={{
                        display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 12px',
                        borderRadius: '9999px', fontSize: '14px', fontWeight: '500', ...getStatusStyle(tx.status)
                      }}>
                        {getStatusIcon(tx.status)}
                        {getStatusText(tx.status)}
                      </div>
                      {/* Botón para ver comprobante */}
                      {tx.type === 'withdrawal' && tx.status === 'completed' && tx.proof_image && (
                        <button
                          onClick={() => openVoucher(tx)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 12px',
                            borderRadius: '9999px', fontSize: '14px', fontWeight: '500', cursor: 'pointer',
                            backgroundColor: '#e0f2fe', color: '#0369a1', border: 'none',
                            transition: 'all 0.2s'
                          }}
                          data-testid={`view-voucher-${tx.transaction_id}`}
                          title="Ver comprobante de pago"
                        >
                          <Eye style={{ width: '16px', height: '16px' }} />
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

      {/* Modal para ver comprobante */}
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
              width: '100%', maxWidth: '500px', maxHeight: '90vh', overflow: 'auto' 
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ fontSize: '20px', fontWeight: '700', color: '#111827', margin: 0 }}>
                Comprobante de Pago
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
                  <p style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: 0 }}>{selectedVoucher.amount_input?.toFixed(2)} RIS</p>
                </div>
                <div>
                  <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Monto recibido</p>
                  <p style={{ fontSize: '18px', fontWeight: '700', color: '#16a34a', margin: 0 }}>{selectedVoucher.amount_output?.toFixed(2)} VES</p>
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
                <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>{formatDate(selectedVoucher.completed_at || selectedVoucher.created_at)}</p>
              </div>
            </div>

            {/* Imagen del comprobante */}
            <div>
              <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '12px' }}>
                Imagen del comprobante
              </p>
              {selectedVoucher.proof_image ? (
                <img 
                  src={selectedVoucher.proof_image} 
                  alt="Comprobante de pago"
                  style={{ 
                    width: '100%', borderRadius: '12px', border: '1px solid #e5e7eb',
                    maxHeight: '400px', objectFit: 'contain', backgroundColor: '#f9fafb'
                  }}
                />
              ) : (
                <div style={{ 
                  padding: '40px', backgroundColor: '#f9fafb', borderRadius: '12px',
                  textAlign: 'center', border: '1px dashed #d1d5db'
                }}>
                  <p style={{ color: '#6b7280', margin: 0 }}>No hay comprobante disponible</p>
                </div>
              )}
            </div>

            <p style={{ fontSize: '12px', color: '#9ca3af', textAlign: 'center', marginTop: '16px' }}>
              ID: {selectedVoucher.transaction_id}
            </p>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
