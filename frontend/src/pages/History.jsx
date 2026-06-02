import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useRate } from '../contexts/RateContext';
import { 
  ArrowLeft, ArrowUpRight, Clock, Filter, ChevronDown, Plus, X, Download
} from 'lucide-react';
import api from '../utils/api';
import NotificationBell from '../components/NotificationBell';
import TransactionItem from '../components/dashboard/TransactionItem';
import { fmt } from '../utils/format';

// Convertir URL de imagen a ruta accesible
const convertTwilioUrl = (url) => {
  if (!url) return url;
  // URLs locales ya funcionan via proxy Kubernetes
  if (url.startsWith('/api/static/') || url.startsWith('/api/media/')) return url;
  // Base64 inline
  if (url.startsWith('data:')) return url;
  // URLs directas de Twilio -> pasar por proxy backend
  if (url.includes('api.twilio.com')) {
    const match = url.match(/\/Accounts\/(AC[^/]+\/.*)/);
    if (match) return `/api/media/twilio/${match[1]}`;
  }
  return url;
};

export default function History() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { rates } = useRate();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [showVoucherModal, setShowVoucherModal] = useState(false);
  const [selectedVoucher, setSelectedVoucher] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Función para descargar una imagen
  const downloadImage = (base64Data, fileName) => {
    const link = document.createElement('a');
    link.href = base64Data;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Función para descargar todas las imágenes
  const downloadAllImages = (images, txId) => {
    images.forEach((img, index) => {
      setTimeout(() => {
        downloadImage(img, `comprobante_${txId}_${index + 1}.png`);
      }, index * 300); // Pequeño delay entre descargas
    });
  };

  useEffect(() => {
    loadTransactions();
  }, [page, filter]);

  const loadTransactions = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, limit: 10 });
      if (filter !== 'all') params.append('filter_type', filter);
      const response = await api.get(`/transactions?${params}`);
      const data = response.data;
      setTransactions(data.transactions || []);
      setTotalPages(data.pages || 1);
      setTotalCount(data.total || 0);
    } catch (error) {
      console.error('Error loading transactions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (newFilter) => {
    setFilter(newFilter);
    setPage(1);
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('es-VE', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'America/Caracas'
    });
  };

  const pageStyle = {
    minHeight: '100vh',
    backgroundColor: '#F4F5F9',
    fontFamily: 'Inter, Helvetica, -apple-system, sans-serif'
  };

  const cardStyle = {
    backgroundColor: '#ffffff',
    borderRadius: '20px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <button 
              onClick={() => navigate(-1)} 
              style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', backgroundColor: '#ffffff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
              data-testid="back-button"
            >
              <ArrowLeft style={{ width: '20px', height: '20px', color: '#374151' }} />
            </button>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#1A1A2E', margin: 0, letterSpacing: '-0.01em' }}>Historial</h1>
              <p style={{ fontSize: '13px', color: '#8E8E9A', margin: '2px 0 0 0' }}>
                {totalCount} {totalCount === 1 ? 'transacción' : 'transacciones'}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => setShowFilters(!showFilters)}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px',
                backgroundColor: '#ffffff', borderRadius: '12px', border: 'none',
                cursor: 'pointer', fontSize: '14px', fontWeight: 600, color: '#374151',
                boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
              }}
              data-testid="filter-button"
            >
              <Filter style={{ width: '16px', height: '16px' }} />
              Filtrar
              <ChevronDown style={{ width: '16px', height: '16px', transform: showFilters ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
            </button>
            <NotificationBell />
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}>
            {[
              { key: 'all', label: 'Todos' },
              { key: 'withdrawals', label: 'Envíos' },
              { key: 'recharges', label: 'Recargas' },
            ].map((f) => (
              <button
                key={f.key}
                onClick={() => handleFilterChange(f.key)}
                style={{
                  padding: '10px 20px', borderRadius: '12px', border: 'none', cursor: 'pointer',
                  fontSize: '14px', fontWeight: 600, transition: 'all 0.2s',
                  backgroundColor: filter === f.key ? '#5B4FE9' : '#ffffff',
                  color: filter === f.key ? '#ffffff' : '#374151',
                  boxShadow: filter === f.key ? '0 4px 10px rgba(91,79,233,0.30)' : '0 1px 3px rgba(0,0,0,0.06)',
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
            <div style={{ width: '40px', height: '40px', border: '4px solid #e5e7eb', borderTopColor: '#5B4FE9', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
            <p style={{ color: '#8E8E9A', marginTop: '16px' }}>Cargando transacciones...</p>
          </div>
        ) : transactions.length === 0 ? (
          <div style={{ ...cardStyle, padding: '64px', textAlign: 'center' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '20px', backgroundColor: '#F4F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
              <Clock style={{ width: '40px', height: '40px', color: '#C2C2D6' }} />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#1A1A2E', margin: '0 0 8px 0' }}>Sin transacciones</h3>
            <p style={{ fontSize: '14px', color: '#8E8E9A', margin: '0 0 24px 0' }}>
              {filter !== 'all' ? 'Prueba cambiando el filtro' : 'Realiza tu primera operación para verla aquí'}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <Link to="/recharge" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 20px', backgroundColor: '#38A169', color: '#ffffff', borderRadius: '12px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>
                <Plus style={{ width: '18px', height: '18px' }} /> Recargar saldo
              </Link>
              <Link to="/send" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '12px 20px', backgroundColor: '#5B4FE9', color: '#ffffff', borderRadius: '12px', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>
                <ArrowUpRight style={{ width: '18px', height: '18px' }} /> Enviar remesa
              </Link>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {transactions.map((tx) => (
              <TransactionItem
                key={tx.transaction_id}
                tx={tx}
                rates={rates}
                onViewVoucher={openVoucher}
              />
            ))}
          </div>
        )}

        {/* Paginación */}
        {!loading && totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginTop: '24px', paddingBottom: '24px' }} data-testid="pagination">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{
                padding: '10px 18px', borderRadius: '12px', border: 'none', cursor: page === 1 ? 'default' : 'pointer',
                backgroundColor: page === 1 ? '#E5E7EB' : '#5B4FE9', color: page === 1 ? '#9CA3AF' : '#fff',
                fontSize: '14px', fontWeight: 600, transition: 'all 0.2s',
                boxShadow: page === 1 ? 'none' : '0 4px 10px rgba(91,79,233,0.30)',
              }}
              data-testid="prev-page"
            >
              Anterior
            </button>
            <span style={{ fontSize: '14px', fontWeight: 600, color: '#374151', padding: '0 12px' }}>
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{
                padding: '10px 18px', borderRadius: '12px', border: 'none', cursor: page === totalPages ? 'default' : 'pointer',
                backgroundColor: page === totalPages ? '#E5E7EB' : '#5B4FE9', color: page === totalPages ? '#9CA3AF' : '#fff',
                fontSize: '14px', fontWeight: 600, transition: 'all 0.2s',
                boxShadow: page === totalPages ? 'none' : '0 4px 10px rgba(91,79,233,0.30)',
              }}
              data-testid="next-page"
            >
              Siguiente
            </button>
          </div>
        )}
      </div>

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
                      <span style={{ fontSize: '14px', color: '#16a34a', marginLeft: 6 }}>= $ {fmt(selectedVoucher.amount_output / rates.bcv_usd_ves, 2)} BCV</span>
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
                <p style={{ fontSize: '14px', color: '#374151', margin: 0 }}>{formatDate(selectedVoucher.completed_at || selectedVoucher.created_at)}</p>
              </div>
            </div>

            {/* Imágenes del comprobante */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', margin: 0 }}>
                  📷 {(selectedVoucher.proof_images?.length || (selectedVoucher.proof_image ? 1 : 0))} Imagen{(selectedVoucher.proof_images?.length || 1) > 1 ? 'es' : ''} de comprobante
                </p>
                {/* Botón descargar todas */}
                {(selectedVoucher.proof_images?.length > 0 || selectedVoucher.proof_image) && (
                  <button
                    onClick={() => {
                      const images = selectedVoucher.proof_images?.length > 0 
                        ? selectedVoucher.proof_images.map(convertTwilioUrl)
                        : [convertTwilioUrl(selectedVoucher.proof_image)];
                      const txId = selectedVoucher.display_id || selectedVoucher.transaction_id?.slice(0, 8);
                      downloadAllImages(images, txId);
                    }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '6px',
                      padding: '8px 14px', borderRadius: '10px', border: 'none',
                      backgroundColor: '#6366f1', color: 'white', cursor: 'pointer',
                      fontSize: '13px', fontWeight: '500', transition: 'all 0.2s'
                    }}
                    data-testid="download-all-images"
                  >
                    <Download style={{ width: '16px', height: '16px' }} />
                    Descargar {(selectedVoucher.proof_images?.length || 1) > 1 ? 'todas' : ''}
                  </button>
                )}
              </div>
              
              {/* Grid de imágenes */}
              {(selectedVoucher.proof_images?.length > 0 || selectedVoucher.proof_image) ? (
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: (selectedVoucher.proof_images?.length || 1) > 1 ? 'repeat(2, 1fr)' : '1fr', 
                  gap: '12px' 
                }}>
                  {(selectedVoucher.proof_images?.length > 0 ? selectedVoucher.proof_images : [selectedVoucher.proof_image]).map((img, idx) => (
                    <div key={idx} style={{ position: 'relative' }}>
                      <img 
                        src={convertTwilioUrl(img)} 
                        alt={`Comprobante ${idx + 1}`}
                        style={{ 
                          width: '100%', 
                          borderRadius: '12px', 
                          border: '1px solid #e5e7eb',
                          maxHeight: (selectedVoucher.proof_images?.length || 1) > 1 ? '200px' : '400px', 
                          objectFit: 'contain', 
                          backgroundColor: '#f9fafb',
                          cursor: 'pointer'
                        }}
                        onClick={() => window.open(convertTwilioUrl(img), '_blank')}
                        title="Click para ver en tamaño completo"
                      />
                      {/* Botón de descarga individual */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          const txId = selectedVoucher.display_id || selectedVoucher.transaction_id?.slice(0, 8);
                          downloadImage(convertTwilioUrl(img), `comprobante_${txId}_${idx + 1}.png`);
                        }}
                        style={{
                          position: 'absolute', top: '8px', right: '8px',
                          width: '32px', height: '32px', borderRadius: '8px',
                          backgroundColor: 'rgba(255,255,255,0.9)', border: 'none',
                          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          boxShadow: '0 2px 4px rgba(0,0,0,0.1)', transition: 'all 0.2s'
                        }}
                        title={`Descargar imagen ${idx + 1}`}
                        data-testid={`download-image-${idx}`}
                      >
                        <Download style={{ width: '16px', height: '16px', color: '#6366f1' }} />
                      </button>
                      {(selectedVoucher.proof_images?.length || 0) > 1 && (
                        <div style={{ 
                          position: 'absolute', bottom: '8px', left: '8px', 
                          backgroundColor: 'rgba(0,0,0,0.6)', color: 'white', 
                          fontSize: '12px', padding: '4px 8px', borderRadius: '6px',
                          fontWeight: '600'
                        }}>
                          #{idx + 1}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : selectedVoucher.voucher_url ? (
                <img 
                  src={selectedVoucher.voucher_url} 
                  alt="Comprobante"
                  style={{ 
                    width: '100%', borderRadius: '12px', border: '1px solid #e5e7eb',
                    maxHeight: '400px', objectFit: 'contain', backgroundColor: '#f9fafb',
                    cursor: 'pointer'
                  }}
                  onClick={() => window.open(selectedVoucher.voucher_url, '_blank')}
                  title="Click para ver en tamaño completo"
                />
              ) : (
                <div style={{ 
                  padding: '40px', backgroundColor: '#f9fafb', borderRadius: '12px',
                  textAlign: 'center', border: '1px dashed #d1d5db'
                }}>
                  <p style={{ color: '#6b7280', margin: 0 }}>No hay comprobante disponible</p>
                </div>
              )}
              
              <p style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'center', marginTop: '8px' }}>
                Toca una imagen para verla en tamaño completo
              </p>
            </div>

            <p style={{ fontSize: '12px', color: '#9ca3af', textAlign: 'center', marginTop: '16px' }}>
              ID: {selectedVoucher.display_id || selectedVoucher.transaction_id?.slice(0, 8)}
            </p>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
